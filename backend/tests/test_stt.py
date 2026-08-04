from __future__ import annotations

import asyncio

import pytest

from app.voice.stt import SarvamSttClient, SttConfig


class FakeSttConnection:
    def __init__(
        self,
        name: str,
        *,
        close_started: asyncio.Event | None = None,
        allow_close: asyncio.Event | None = None,
    ) -> None:
        self.name = name
        self.close_started = close_started
        self.allow_close = allow_close
        self.closed = False
        self.sent_messages: list[str] = []

    async def close(self) -> None:
        if self.close_started is not None:
            self.close_started.set()
        if self.allow_close is not None:
            await self.allow_close.wait()
        self.closed = True

    async def send(self, message: str) -> None:
        if self.closed:
            raise RuntimeError(f"send used stale closed connection: {self.name}")
        self.sent_messages.append(message)


@pytest.mark.asyncio
async def test_audio_waiting_during_reconnect_uses_new_connection(monkeypatch) -> None:
    close_started = asyncio.Event()
    allow_close = asyncio.Event()
    old_connection = FakeSttConnection(
        "old",
        close_started=close_started,
        allow_close=allow_close,
    )
    new_connection = FakeSttConnection("new")
    client = SarvamSttClient(
        SttConfig(
            api_key="test",
            model="saaras:v3",
            language_code="unknown",
            sample_rate_hz=16000,
            input_audio_codec="pcm_s16le",
            audio_encoding="audio/wav",
        )
    )
    client._connection = old_connection  # type: ignore[assignment]

    async def open_new_connection() -> FakeSttConnection:
        return new_connection

    monkeypatch.setattr(client, "_open_connection", open_new_connection)

    reconnect = asyncio.create_task(client.reconnect())
    await close_started.wait()
    send = asyncio.create_task(client.send_audio(b"pcm"))
    await asyncio.sleep(0)
    allow_close.set()

    await reconnect
    await send

    assert old_connection.sent_messages == []
    assert len(new_connection.sent_messages) == 1
