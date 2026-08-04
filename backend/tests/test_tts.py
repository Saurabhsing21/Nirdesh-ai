from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

from app.voice import tts as tts_module
from app.voice.tts import SarvamTtsClient, TtsConfig


class FakeTtsConnection:
    def __init__(self) -> None:
        self.receive_started = asyncio.Event()
        self.receive_cancelled = asyncio.Event()
        self.receive_tasks: list[asyncio.Task[object]] = []

    async def send(self, _message: str) -> None:
        return

    async def recv(self) -> object:
        task = asyncio.current_task()
        assert task is not None
        self.receive_tasks.append(task)
        self.receive_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.receive_cancelled.set()
            raise

    async def close(self, **_kwargs) -> None:
        return


class FakeConnectContext:
    def __init__(self, connection: FakeTtsConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeTtsConnection:
        return self.connection

    async def __aexit__(self, *_args) -> None:
        return None


@pytest.mark.asyncio
async def test_cancelling_synthesis_awaits_audio_receiver(monkeypatch) -> None:
    connection = FakeTtsConnection()
    monkeypatch.setattr(
        tts_module,
        "connect",
        lambda *_args, **_kwargs: FakeConnectContext(connection),
    )
    client = SarvamTtsClient(
        TtsConfig(
            api_key="test",
            model="bulbul:v3",
            speaker="anushka",
            target_language_code="en-IN",
            sample_rate_hz=24000,
            output_audio_codec="linear16",
        )
    )

    async def blocked_chunks():
        await asyncio.Future()
        yield "unreachable"

    async def observe(_name: str, _timestamp: float, _details: dict) -> None:
        return

    async def probe(_direction: str, _message: dict) -> None:
        return

    async def consume() -> None:
        async for _audio in client.synthesize(
            blocked_chunks(),
            observer=observe,
            probe=probe,
        ):
            pass

    consumer = asyncio.create_task(consume())
    await connection.receive_started.wait()
    consumer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer

    try:
        assert connection.receive_cancelled.is_set()
        assert all(task.done() for task in connection.receive_tasks)
    finally:
        for task in connection.receive_tasks:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
