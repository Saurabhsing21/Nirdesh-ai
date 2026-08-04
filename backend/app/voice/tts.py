from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect

TtsObservationCallback = Callable[[str, float, dict[str, Any]], Awaitable[None]]
TtsProbeCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class SarvamTtsError(RuntimeError):
    pass


@dataclass(frozen=True)
class TtsConfig:
    api_key: str
    model: str
    speaker: str
    target_language_code: str
    sample_rate_hz: int
    output_audio_codec: str


class SarvamTtsClient:
    def __init__(self, config: TtsConfig) -> None:
        self._config = config
        self._connection: ClientConnection | None = None
        self._discarded = False
        self._connection_id = str(uuid.uuid4())

    @property
    def connection_id(self) -> str:
        return self._connection_id

    async def close_and_discard(self, reason: str = "interrupted") -> None:
        self._discarded = True
        connection = self._connection
        if connection is not None:
            await connection.close(code=1000, reason=reason[:123])

    async def synthesize(
        self,
        text_chunks: AsyncIterator[str],
        *,
        observer: TtsObservationCallback,
        probe: TtsProbeCallback,
    ) -> AsyncIterator[bytes]:
        query = urlencode({"model": self._config.model, "send_completion_event": "true"})
        connection_details = {"state": "cold", "connection_id": self._connection_id}
        await observer("t_tts_connection_acquire_start", time.monotonic(), connection_details)
        try:
            async with connect(
                f"wss://api.sarvam.ai/text-to-speech/ws?{query}",
                additional_headers={"Api-Subscription-Key": self._config.api_key},
                max_size=16 * 1024 * 1024,
                open_timeout=15,
                ping_interval=20,
                ping_timeout=20,
            ) as connection:
                self._connection = connection
                await observer(
                    "t_tts_connection_acquire_end",
                    time.monotonic(),
                    connection_details,
                )
                config_message = {
                    "type": "config",
                    "data": {
                        "speaker": self._config.speaker,
                        "target_language_code": self._config.target_language_code,
                        "speech_sample_rate": self._config.sample_rate_hz,
                        "output_audio_codec": self._config.output_audio_codec,
                        "pace": 1.0,
                        "temperature": 0.6,
                        "min_buffer_size": 50,
                        "max_chunk_length": 200,
                    },
                }
                await connection.send(json.dumps(config_message, separators=(",", ":")))
                await probe("sent", config_message)

                async def send_text() -> None:
                    submitted = False
                    async for text in text_chunks:
                        if self._discarded:
                            return
                        message = {"type": "text", "data": {"text": text}}
                        await connection.send(json.dumps(message, separators=(",", ":")))
                        await probe("sent", message)
                        if not submitted:
                            submitted = True
                            await observer("t_tts_text_submitted", time.monotonic(), {})
                    if self._discarded:
                        return
                    flush_message = {"type": "flush"}
                    await connection.send(json.dumps(flush_message, separators=(",", ":")))
                    await probe("sent", flush_message)

                sender = asyncio.create_task(send_text(), name="bulbul-text-sender")
                receive_task: asyncio.Task[str | bytes] | None = None
                first_audio = True
                try:
                    while not self._discarded:
                        if sender.done():
                            sender.result()
                            raw_message = await connection.recv()
                        else:
                            receive_task = asyncio.create_task(
                                connection.recv(), name="bulbul-audio-receiver"
                            )
                            done, _ = await asyncio.wait(
                                {sender, receive_task},
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            if sender in done and sender.exception() is not None:
                                receive_task.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await receive_task
                                sender.result()
                            raw_message = await receive_task
                            receive_task = None
                        if not isinstance(raw_message, str):
                            raise SarvamTtsError("Bulbul returned a non-JSON message")
                        message = json.loads(raw_message)
                        if not isinstance(message, dict):
                            raise SarvamTtsError("Bulbul returned a non-object JSON message")
                        await probe("received", message)
                        message_type = message.get("type")
                        data = message.get("data")
                        if message_type == "audio" and isinstance(data, dict):
                            encoded_audio = data.get("audio")
                            if not isinstance(encoded_audio, str):
                                raise SarvamTtsError("Bulbul audio message omitted audio data")
                            if first_audio:
                                first_audio = False
                                await observer(
                                    "t_tts_first_chunk",
                                    time.monotonic(),
                                    {
                                        "content_type": data.get("content_type"),
                                        "request_id": data.get("request_id"),
                                        "connection_id": self._connection_id,
                                    },
                                )
                            if not self._discarded:
                                yield base64.b64decode(encoded_audio)
                        elif message_type == "event" and isinstance(data, dict):
                            if data.get("event_type") == "final":
                                await observer("t_tts_complete", time.monotonic(), {})
                                break
                        elif message_type == "error":
                            raise SarvamTtsError(f"Bulbul error: {data}")
                    await sender
                finally:
                    if receive_task is not None:
                        if not receive_task.done():
                            receive_task.cancel()
                        # Always retrieve completion, including a normal-close
                        # exception raised while the parent stream is cancelled.
                        await asyncio.gather(receive_task, return_exceptions=True)
                    if not sender.done():
                        sender.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await sender
        except asyncio.CancelledError:
            await observer("t_tts_complete", time.monotonic(), {"cancelled": True})
            raise
        finally:
            self._connection = None
