from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect


class SarvamSttError(RuntimeError):
    pass


@dataclass(frozen=True)
class SttConfig:
    api_key: str
    model: str
    language_code: str
    sample_rate_hz: int
    input_audio_codec: str
    audio_encoding: str


class SarvamSttClient:
    def __init__(self, config: SttConfig) -> None:
        self._config = config
        self._connection: ClientConnection | None = None
        self._send_lock = asyncio.Lock()

    async def connect(self) -> None:
        self._connection = await self._open_connection()

    async def reconnect(self) -> None:
        async with self._send_lock:
            if self._connection is not None:
                await self._connection.close()
            self._connection = await self._open_connection()

    async def _open_connection(self) -> ClientConnection:
        query = urlencode(
            {
                "model": self._config.model,
                "mode": "transcribe",
                "language-code": self._config.language_code,
                "sample_rate": str(self._config.sample_rate_hz),
                "input_audio_codec": self._config.input_audio_codec,
                "flush_signal": "true",
                "vad_signals": "true",
            }
        )
        return await connect(
            f"wss://api.sarvam.ai/speech-to-text/ws?{query}",
            additional_headers={"Api-Subscription-Key": self._config.api_key},
            max_size=8 * 1024 * 1024,
            open_timeout=15,
            ping_interval=20,
            ping_timeout=20,
        )

    async def send_audio(self, pcm: bytes) -> dict[str, Any]:
        message = {
            "audio": {
                "data": base64.b64encode(pcm).decode("ascii"),
                "sample_rate": str(self._config.sample_rate_hz),
                "encoding": self._config.audio_encoding,
            }
        }
        await self._send_json(message)
        return {
            "audio": {
                "data": f"<base64:{len(message['audio']['data'])} chars>",
                "sample_rate": message["audio"]["sample_rate"],
                "encoding": message["audio"]["encoding"],
            }
        }

    async def flush(self) -> dict[str, str]:
        message = {"type": "flush"}
        await self._send_json(message)
        return message

    async def messages(self) -> AsyncIterator[dict[str, Any]]:
        connection = self._require_connection()
        async for raw_message in connection:
            if not isinstance(raw_message, str):
                raise SarvamSttError("Saaras returned a non-JSON message")
            parsed = json.loads(raw_message)
            if not isinstance(parsed, dict):
                raise SarvamSttError("Saaras returned a non-object JSON message")
            yield parsed

    async def close(self) -> None:
        async with self._send_lock:
            if self._connection is not None:
                await self._connection.close()
                self._connection = None

    async def _send_json(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            # Resolve the connection only after acquiring the same lock used by
            # reconnect(). Otherwise a sender can retain the old connection,
            # wait for rotation to finish, and then send on the closed socket.
            connection = self._require_connection()
            await connection.send(json.dumps(message, separators=(",", ":")))

    def _require_connection(self) -> ClientConnection:
        if self._connection is None:
            raise SarvamSttError("Saaras WebSocket is not connected")
        return self._connection
