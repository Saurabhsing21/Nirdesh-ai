#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.voice.protocol import CaptureFrame, encode_capture_frame

FRAME_SAMPLES = 512
INPUT_SAMPLE_RATE_HZ = 16_000


@dataclass(frozen=True)
class ProbeResult:
    strategy: str
    output_wav: Path
    stages: dict[str, float | None]
    dimensions: dict[str, object]
    audio_bytes: int
    duration_seconds: float
    billing_events: tuple[dict[str, object], ...]
    final_billing: dict[str, object]


@dataclass(frozen=True)
class BargeProbeResult:
    interrupted_turn_id: str
    resumed_turn_id: str
    interrupt_ack_ms: float | None
    old_audio_chunks_after_interrupt: int
    interrupted_tts_connection_id: str
    resumed_tts_connection_id: str
    interrupted_output_wav: Path
    resumed_output_wav: Path
    interrupted_audio_bytes: int
    resumed_audio_bytes: int
    tts_socket_teardown_status: str


@dataclass(frozen=True)
class ToolProbeResult:
    web_search_turn_id: str
    todo_turn_id: str
    web_search_span: dict[str, object]
    todo_span: dict[str, object]
    todo_request: dict[str, object]
    web_search_output_wav: Path
    todo_output_wav: Path
    web_search_audio_bytes: int
    todo_audio_bytes: int
    web_search_spoken_text: str
    todo_spoken_text: str


@dataclass(frozen=True)
class BalanceExhaustionProbeResult:
    billing_events: tuple[dict[str, object], ...]
    warning_seen: bool
    terminal_event: dict[str, object]
    call_ended_reason: str
    close_code: int
    close_reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay 16 kHz PCM through /ws/voice and save returned TTS audio."
    )
    parser.add_argument("input_wav", type=Path)
    parser.add_argument("output_wav", type=Path)
    parser.add_argument("--token", required=True, help="JWT returned by /auth/verify-otp")
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8000/ws/voice")
    parser.add_argument("--flush", action="store_true", help="Sarvam-mode probe flush")
    parser.add_argument("--leading-silence-ms", type=int, default=750)
    parser.add_argument("--mid-utterance-pause-ms", type=int, default=250)
    parser.add_argument("--trailing-silence-ms", type=int, default=1500)
    parser.add_argument(
        "--endpointing-strategy",
        choices=("local_vad", "sarvam"),
        default="local_vad",
    )
    parser.add_argument(
        "--compare-strategies",
        action="store_true",
        help="Run local_vad and sarvam sequentially and print both waterfalls.",
    )
    parser.add_argument("--stt-codec", default=None)
    parser.add_argument("--stt-encoding", default=None)
    parser.add_argument("--tts-codec", default=None)
    parser.add_argument(
        "--barge-in-wav",
        type=Path,
        default=None,
        help="Inject this second utterance after first playback starts.",
    )
    parser.add_argument("--barge-in-delay-ms", type=int, default=25)
    parser.add_argument(
        "--require-active-teardown",
        action="store_true",
        help="Fail unless interruption closes an actively streaming Bulbul socket.",
    )
    parser.add_argument(
        "--tool-probe-todo-wav",
        type=Path,
        default=None,
        help=(
            "Run the Phase 3 two-turn probe: input_wav asks for web search and this WAV "
            "asks to add buy milk."
        ),
    )
    parser.add_argument(
        "--expect-balance-exhaustion",
        action="store_true",
        help=(
            "Connect without streaming audio and require low-balance warning plus close code 4403."
        ),
    )
    return parser.parse_args()


def read_input(
    path: Path,
    *,
    leading_silence_ms: int,
    mid_utterance_pause_ms: int,
    trailing_silence_ms: int,
) -> bytes:
    with wave.open(str(path), "rb") as wav_file:
        properties = {
            "channels": wav_file.getnchannels(),
            "sample_width": wav_file.getsampwidth(),
            "sample_rate": wav_file.getframerate(),
            "compression": wav_file.getcomptype(),
        }
        expected = {
            "channels": 1,
            "sample_width": 2,
            "sample_rate": INPUT_SAMPLE_RATE_HZ,
            "compression": "NONE",
        }
        if properties != expected:
            raise ValueError(f"input WAV must be mono PCM16 at 16 kHz: {properties}")
        pcm = wav_file.readframes(wav_file.getnframes())
    insertion = _quiet_midpoint_offset(pcm)
    leading = _silence(leading_silence_ms)
    pause = _silence(mid_utterance_pause_ms)
    trailing = _silence(trailing_silence_ms)
    return leading + pcm[:insertion] + pause + pcm[insertion:] + trailing


def _quiet_midpoint_offset(pcm: bytes) -> int:
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    if len(samples) < FRAME_SAMPLES * 3:
        return len(pcm) // 2 // 2 * 2
    start = len(samples) // 3
    stop = len(samples) * 2 // 3
    window = 320
    candidates = range(start, max(start + 1, stop - window), window)
    quietest = min(
        candidates,
        key=lambda offset: sum(abs(sample) for sample in samples[offset : offset + window]),
    )
    return quietest * 2


def _silence(duration_ms: int) -> bytes:
    samples = round(INPUT_SAMPLE_RATE_HZ * duration_ms / 1000)
    return b"\x00\x00" * samples


def build_url(args: argparse.Namespace, strategy: str) -> str:
    query: dict[str, str] = {
        "token": args.token,
        "probe": "true",
        "endpointing_strategy": strategy,
    }
    if args.stt_codec:
        query["stt_codec"] = args.stt_codec
    if args.stt_encoding:
        query["stt_encoding"] = args.stt_encoding
    if args.tts_codec:
        query["tts_codec"] = args.tts_codec
    separator = "&" if "?" in args.ws_url else "?"
    return f"{args.ws_url}{separator}{urlencode(query)}"


async def stream_audio(
    connection,
    pcm: bytes,
    ready: asyncio.Event,
    flush: bool,
    *,
    start_capture_seq: int = 0,
) -> int:
    await ready.wait()
    frame_bytes = FRAME_SAMPLES * 2
    start = time.perf_counter()
    frame_count = 0
    for frame_index, offset in enumerate(range(0, len(pcm), frame_bytes)):
        capture_seq = start_capture_seq + frame_index
        frame_count += 1
        chunk = pcm[offset : offset + frame_bytes]
        if len(chunk) < frame_bytes:
            chunk += b"\x00" * (frame_bytes - len(chunk))
        target_time = start + frame_index * FRAME_SAMPLES / INPUT_SAMPLE_RATE_HZ
        delay = target_time - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        await connection.send(
            encode_capture_frame(
                CaptureFrame(
                    capture_seq=capture_seq,
                    capture_time_ms=time.perf_counter() * 1000,
                    pcm=chunk,
                )
            )
        )
    if flush:
        await connection.send(json.dumps({"type": "probe_flush"}))
    return start_capture_seq + frame_count


def _write_output_wav(path: Path, pcm: bytes, sample_rate_hz: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)
        wav_file.writeframes(pcm)


async def run_probe(
    args: argparse.Namespace,
    *,
    strategy: str,
    output_wav: Path,
) -> ProbeResult:
    pcm = read_input(
        args.input_wav,
        leading_silence_ms=args.leading_silence_ms,
        mid_utterance_pause_ms=args.mid_utterance_pause_ms,
        trailing_silence_ms=args.trailing_silence_ms,
    )
    ready = asyncio.Event()
    returned_audio = bytearray()
    output_rate = 24_000
    completed = False
    metrics: dict[str, object] | None = None
    audio_start: dict[str, object] | None = None
    playback_reported = False
    billing_events: list[dict[str, object]] = []

    async with connect(build_url(args, strategy), max_size=16 * 1024 * 1024, open_timeout=15) as ws:
        sender = asyncio.create_task(
            stream_audio(ws, pcm, ready, args.flush and strategy == "sarvam")
        )
        try:
            async with asyncio.timeout(180):
                async for message in ws:
                    if isinstance(message, bytes):
                        received_ms = time.perf_counter() * 1000
                        returned_audio.extend(message)
                        if audio_start is not None and not playback_reported:
                            playback_reported = True
                            decode_ms = time.perf_counter() * 1000
                            scheduled_ms = time.perf_counter() * 1000
                            playback_ms = scheduled_ms + 10
                            await ws.send(
                                json.dumps(
                                    {
                                        "type": "playback_started",
                                        "turn_id": audio_start["turn_id"],
                                        "last_speech_capture_seq": audio_start[
                                            "last_speech_capture_seq"
                                        ],
                                        "audio_received_perf_ms": received_ms,
                                        "decode_complete_perf_ms": decode_ms,
                                        "scheduled_perf_ms": scheduled_ms,
                                        "playback_start_perf_ms": playback_ms,
                                        "e2e_voice_to_voice_ms": playback_ms
                                        - float(audio_start["last_speech_capture_time_ms"]),
                                    }
                                )
                            )
                        continue
                    event = json.loads(message)
                    print(
                        json.dumps(
                            {"strategy": strategy, "event": event},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        flush=True,
                    )
                    if event.get("type") == "ready":
                        output_rate = int(event["tts_sample_rate_hz"])
                        ready.set()
                    elif event.get("type") == "audio_start":
                        audio_start = event
                    elif event.get("type") == "billing":
                        billing_events.append(event)
                    elif event.get("type") == "turn_metrics":
                        metrics = event
                    elif event.get("type") == "error":
                        raise RuntimeError(event.get("message", "voice session failed"))
                    elif event.get("type") == "turn_complete":
                        completed = True
                        await ws.send(json.dumps({"type": "end_call"}))
                    elif event.get("type") == "call_ended":
                        break
        finally:
            if not sender.done():
                sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)

    if not completed:
        raise RuntimeError(f"{strategy} voice loop ended without a completed turn")
    if not returned_audio:
        raise RuntimeError(f"{strategy} voice loop returned no TTS audio")
    if metrics is None:
        raise RuntimeError(f"{strategy} voice loop returned no turn_metrics event")
    final_billing = next(
        (event for event in reversed(billing_events) if event.get("final") is True),
        None,
    )
    if final_billing is None or int(final_billing.get("cost_paise", 0)) <= 0:
        raise RuntimeError(f"{strategy} voice loop returned no final billing deduction")
    _write_output_wav(output_wav, returned_audio, output_rate)
    duration = len(returned_audio) / (output_rate * 2)
    return ProbeResult(
        strategy=strategy,
        output_wav=output_wav,
        stages=metrics["stages"],
        dimensions=metrics["dimensions"],
        audio_bytes=len(returned_audio),
        duration_seconds=duration,
        billing_events=tuple(billing_events),
        final_billing=final_billing,
    )


async def run_balance_exhaustion_probe(args: argparse.Namespace) -> BalanceExhaustionProbeResult:
    billing_events: list[dict[str, object]] = []
    call_ended_reason: str | None = None
    close_code: int | None = None
    close_reason = ""
    try:
        async with connect(
            build_url(args, "local_vad"),
            max_size=16 * 1024 * 1024,
            open_timeout=15,
        ) as ws:
            try:
                async with asyncio.timeout(30):
                    async for message in ws:
                        if isinstance(message, bytes):
                            continue
                        event = json.loads(message)
                        print(
                            json.dumps(
                                {"strategy": "balance_exhaustion", "event": event},
                                ensure_ascii=False,
                                indent=2,
                            ),
                            flush=True,
                        )
                        if event.get("type") == "billing":
                            billing_events.append(event)
                        elif event.get("type") == "call_ended":
                            call_ended_reason = str(event.get("reason"))
            except ConnectionClosed as exc:
                close_code = exc.code
                close_reason = exc.reason
    except ConnectionClosed as exc:
        close_code = exc.code
        close_reason = exc.reason

    warning_index = next(
        (
            index
            for index, event in enumerate(billing_events)
            if event.get("warning") == "low_balance"
        ),
        None,
    )
    terminal_index = next(
        (
            index
            for index, event in enumerate(billing_events)
            if event.get("terminated_reason") == "balance_exhausted"
        ),
        None,
    )
    if warning_index is None or terminal_index is None or warning_index > terminal_index:
        raise RuntimeError("balance exhaustion probe did not warn before termination")
    if call_ended_reason != "balance_exhausted":
        raise RuntimeError(f"unexpected call_ended reason: {call_ended_reason}")
    if close_code != 4403:
        raise RuntimeError(f"unexpected balance exhaustion close code: {close_code}")
    terminal_event = billing_events[terminal_index]
    if terminal_event.get("final") is not True or terminal_event.get("balance_paise") != 0:
        raise RuntimeError("balance termination event was not final at zero paise")
    return BalanceExhaustionProbeResult(
        billing_events=tuple(billing_events),
        warning_seen=True,
        terminal_event=terminal_event,
        call_ended_reason=call_ended_reason,
        close_code=close_code,
        close_reason=close_reason,
    )


async def run_barge_probe(args: argparse.Namespace) -> BargeProbeResult:
    if args.barge_in_wav is None:
        raise ValueError("--barge-in-wav is required for the barge-in probe")
    first_pcm = read_input(
        args.input_wav,
        leading_silence_ms=args.leading_silence_ms,
        mid_utterance_pause_ms=args.mid_utterance_pause_ms,
        trailing_silence_ms=args.trailing_silence_ms,
    )
    second_pcm = read_input(
        args.barge_in_wav,
        leading_silence_ms=0,
        mid_utterance_pause_ms=args.mid_utterance_pause_ms,
        trailing_silence_ms=args.trailing_silence_ms,
    )
    first_frame_count = (len(first_pcm) + FRAME_SAMPLES * 2 - 1) // (FRAME_SAMPLES * 2)
    ready = asyncio.Event()
    output_rate = 24_000
    first_turn_id: str | None = None
    second_turn_id: str | None = None
    current_audio_turn: str | None = None
    playback_reported: set[str] = set()
    audio_by_turn: dict[str, bytearray] = {}
    metrics_by_turn: dict[str, dict[str, object]] = {}
    interrupt_resolved: dict[str, object] | None = None
    interrupt_received = False
    old_audio_chunks_after_interrupt = 0
    second_sender: asyncio.Task[int] | None = None

    async with connect(
        build_url(args, "local_vad"),
        max_size=16 * 1024 * 1024,
        open_timeout=15,
    ) as ws:
        first_sender = asyncio.create_task(
            stream_audio(ws, first_pcm, ready, False),
            name="probe-first-utterance",
        )
        try:
            async with asyncio.timeout(180):
                async for message in ws:
                    if isinstance(message, bytes):
                        received_ms = time.perf_counter() * 1000
                        if current_audio_turn is None:
                            continue
                        if interrupt_received and current_audio_turn == first_turn_id:
                            old_audio_chunks_after_interrupt += 1
                            continue
                        audio_by_turn.setdefault(current_audio_turn, bytearray()).extend(message)
                        if current_audio_turn not in playback_reported:
                            playback_reported.add(current_audio_turn)
                            playback_ms = time.perf_counter() * 1000 + 10
                            await ws.send(
                                json.dumps(
                                    {
                                        "type": "playback_started",
                                        "turn_id": current_audio_turn,
                                        "last_speech_capture_seq": 0,
                                        "audio_received_perf_ms": received_ms,
                                        "decode_complete_perf_ms": received_ms + 0.1,
                                        "scheduled_perf_ms": received_ms + 0.2,
                                        "playback_start_perf_ms": playback_ms,
                                    }
                                )
                            )
                            if current_audio_turn == first_turn_id and second_sender is None:
                                await first_sender
                                if args.barge_in_delay_ms > 0:
                                    await asyncio.sleep(args.barge_in_delay_ms / 1000)
                                second_sender = asyncio.create_task(
                                    stream_audio(
                                        ws,
                                        second_pcm,
                                        ready,
                                        False,
                                        start_capture_seq=first_frame_count,
                                    ),
                                    name="probe-barge-utterance",
                                )
                        continue

                    event = json.loads(message)
                    print(
                        json.dumps(
                            {"strategy": "barge_in", "event": event},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        flush=True,
                    )
                    event_type = event.get("type")
                    if event_type == "ready":
                        output_rate = int(event["tts_sample_rate_hz"])
                        ready.set()
                    elif event_type == "audio_start":
                        current_audio_turn = str(event["turn_id"])
                        if first_turn_id is None:
                            first_turn_id = current_audio_turn
                        elif current_audio_turn != first_turn_id:
                            second_turn_id = current_audio_turn
                    elif event_type == "interrupt":
                        interrupt_received = True
                        interrupt_received_ms = time.perf_counter() * 1000
                        turn_id = str(event["turn_id"])
                        generated_ms = (
                            len(audio_by_turn.get(turn_id, b"")) / (output_rate * 2) * 1000
                        )
                        played_ms = min(generated_ms, 250.0)
                        cleared_ms = time.perf_counter() * 1000
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "interrupt_ack",
                                    "turn_id": turn_id,
                                    "interrupt_received_perf_ms": interrupt_received_ms,
                                    "queue_cleared_perf_ms": cleared_ms,
                                    "audio_queue_cleared": True,
                                    "played_audio_ms": played_ms,
                                }
                            )
                        )
                    elif event_type == "interrupt_resolved":
                        interrupt_resolved = event
                    elif event_type == "turn_metrics":
                        metrics_by_turn[str(event["turn_id"])] = event
                    elif event_type == "error":
                        raise RuntimeError(event.get("message", "voice session failed"))
                    elif event_type == "turn_complete":
                        completed_turn = str(event["turn_id"])
                        if second_turn_id is not None and completed_turn == second_turn_id:
                            await ws.send(json.dumps({"type": "end_call"}))
                    elif event_type == "call_ended":
                        break
        finally:
            tasks = [first_sender]
            if second_sender is not None:
                tasks.append(second_sender)
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    if first_turn_id is None or second_turn_id is None:
        raise RuntimeError("barge-in probe did not produce two audio turns")
    if interrupt_resolved is None:
        raise RuntimeError("barge-in probe did not receive interrupt_resolved")
    first_metrics = metrics_by_turn.get(first_turn_id)
    second_metrics = metrics_by_turn.get(second_turn_id)
    if first_metrics is None or second_metrics is None:
        raise RuntimeError("barge-in probe did not receive metrics for both turns")
    first_dimensions = first_metrics["dimensions"]
    second_dimensions = second_metrics["dimensions"]
    if first_dimensions.get("interrupted") is not True:
        raise RuntimeError("first turn was not persisted as interrupted")
    first_connection = str(first_dimensions.get("tts_connection_id"))
    second_connection = str(second_dimensions.get("tts_connection_id"))
    if first_connection == second_connection:
        raise RuntimeError("interrupted and resumed turns reused the same TTS connection")
    if old_audio_chunks_after_interrupt:
        raise RuntimeError("stale audio arrived after the interrupt event")
    teardown_status = str(interrupt_resolved.get("tts_socket_teardown_status"))
    if args.require_active_teardown and teardown_status != "closed_and_discarded":
        raise RuntimeError(f"Bulbul socket was not actively torn down: {teardown_status}")
    interrupted_audio = bytes(audio_by_turn.get(first_turn_id, b""))
    resumed_audio = bytes(audio_by_turn.get(second_turn_id, b""))
    if not interrupted_audio or not resumed_audio:
        raise RuntimeError("barge-in probe did not receive audio for both turns")
    interrupted_path = args.output_wav.with_name(
        f"{args.output_wav.stem}.interrupted{args.output_wav.suffix}"
    )
    _write_output_wav(interrupted_path, interrupted_audio, output_rate)
    _write_output_wav(args.output_wav, resumed_audio, output_rate)
    return BargeProbeResult(
        interrupted_turn_id=first_turn_id,
        resumed_turn_id=second_turn_id,
        interrupt_ack_ms=interrupt_resolved.get("barge_in_stop_ack_ms"),
        old_audio_chunks_after_interrupt=old_audio_chunks_after_interrupt,
        interrupted_tts_connection_id=first_connection,
        resumed_tts_connection_id=second_connection,
        interrupted_output_wav=interrupted_path,
        resumed_output_wav=args.output_wav,
        interrupted_audio_bytes=len(interrupted_audio),
        resumed_audio_bytes=len(resumed_audio),
        tts_socket_teardown_status=teardown_status,
    )


async def run_tool_probe(args: argparse.Namespace) -> ToolProbeResult:
    if args.tool_probe_todo_wav is None:
        raise ValueError("--tool-probe-todo-wav is required for the tool probe")
    first_pcm = read_input(
        args.input_wav,
        leading_silence_ms=args.leading_silence_ms,
        mid_utterance_pause_ms=args.mid_utterance_pause_ms,
        trailing_silence_ms=args.trailing_silence_ms,
    )
    second_pcm = read_input(
        args.tool_probe_todo_wav,
        leading_silence_ms=args.leading_silence_ms,
        mid_utterance_pause_ms=args.mid_utterance_pause_ms,
        trailing_silence_ms=args.trailing_silence_ms,
    )
    first_frame_count = (len(first_pcm) + FRAME_SAMPLES * 2 - 1) // (FRAME_SAMPLES * 2)
    ready = asyncio.Event()
    output_rate = 24_000
    turn_ids: list[str] = []
    current_audio_turn: str | None = None
    audio_by_turn: dict[str, bytearray] = {}
    agent_text_by_turn: dict[str, list[str]] = {}
    metrics_by_turn: dict[str, dict[str, object]] = {}
    playback_reported: set[str] = set()
    todo_request: dict[str, object] | None = None
    second_sender: asyncio.Task[int] | None = None
    first_sender: asyncio.Task[int] | None = None

    async with connect(
        build_url(args, "local_vad"),
        max_size=16 * 1024 * 1024,
        open_timeout=15,
    ) as ws:
        first_sender = asyncio.create_task(
            stream_audio(ws, first_pcm, ready, False),
            name="probe-web-search-turn",
        )
        try:
            async with asyncio.timeout(240):
                async for message in ws:
                    if isinstance(message, bytes):
                        if current_audio_turn is None:
                            continue
                        received_ms = time.perf_counter() * 1000
                        audio_by_turn.setdefault(current_audio_turn, bytearray()).extend(message)
                        if current_audio_turn not in playback_reported:
                            playback_reported.add(current_audio_turn)
                            playback_ms = received_ms + 10
                            await ws.send(
                                json.dumps(
                                    {
                                        "type": "playback_started",
                                        "turn_id": current_audio_turn,
                                        "last_speech_capture_seq": 0,
                                        "audio_received_perf_ms": received_ms,
                                        "decode_complete_perf_ms": received_ms + 0.1,
                                        "scheduled_perf_ms": received_ms + 0.2,
                                        "playback_start_perf_ms": playback_ms,
                                    }
                                )
                            )
                        continue

                    event = json.loads(message)
                    print(
                        json.dumps(
                            {"strategy": "phase3_tools", "event": event},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        flush=True,
                    )
                    event_type = event.get("type")
                    if event_type == "ready":
                        output_rate = int(event["tts_sample_rate_hz"])
                        ready.set()
                    elif event_type == "audio_start":
                        current_audio_turn = str(event["turn_id"])
                        if current_audio_turn not in turn_ids:
                            turn_ids.append(current_audio_turn)
                    elif event_type == "agent_text":
                        turn_id = str(event["turn_id"])
                        agent_text_by_turn.setdefault(turn_id, []).append(str(event["text"]))
                    elif event_type == "tool_request":
                        if event.get("name") != "todo_add":
                            raise RuntimeError(
                                f"unexpected client tool request: {event.get('name')}"
                            )
                        todo_request = event
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "tool_result",
                                    "call_id": event["call_id"],
                                    "result": {
                                        "ok": True,
                                        "todo": {
                                            "id": "probe-todo-1",
                                            "text": "buy milk",
                                            "completed": False,
                                        },
                                        "todos": [
                                            {
                                                "id": "probe-todo-1",
                                                "text": "buy milk",
                                                "completed": False,
                                            }
                                        ],
                                    },
                                }
                            )
                        )
                    elif event_type == "turn_metrics":
                        metrics_by_turn[str(event["turn_id"])] = event
                    elif event_type == "error":
                        raise RuntimeError(event.get("message", "voice session failed"))
                    elif event_type == "turn_complete":
                        completed_turn = str(event["turn_id"])
                        played_ms = (
                            len(audio_by_turn.get(completed_turn, b"")) / (output_rate * 2) * 1000
                        )
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "playback_finished",
                                    "turn_id": completed_turn,
                                    "playback_end_perf_ms": time.perf_counter() * 1000,
                                    "played_audio_ms": played_ms,
                                }
                            )
                        )
                        if second_sender is None:
                            await first_sender
                            second_sender = asyncio.create_task(
                                stream_audio(
                                    ws,
                                    second_pcm,
                                    ready,
                                    False,
                                    start_capture_seq=first_frame_count,
                                ),
                                name="probe-todo-turn",
                            )
                        else:
                            await second_sender
                            await ws.send(json.dumps({"type": "end_call"}))
                    elif event_type == "call_ended":
                        break
        finally:
            tasks = [task for task in (first_sender, second_sender) if task is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    if len(turn_ids) != 2:
        raise RuntimeError(f"tool probe expected two audio turns, received {len(turn_ids)}")
    web_turn, todo_turn = turn_ids
    web_metrics = metrics_by_turn.get(web_turn)
    todo_metrics = metrics_by_turn.get(todo_turn)
    if web_metrics is None or todo_metrics is None:
        raise RuntimeError("tool probe did not receive metrics for both turns")
    web_spans = [
        span for span in web_metrics.get("tool_spans", []) if span.get("name") == "web_search"
    ]
    todo_spans = [
        span for span in todo_metrics.get("tool_spans", []) if span.get("name") == "todo_add"
    ]
    if not web_spans or web_spans[0].get("outcome") != "success":
        raise RuntimeError(f"web_search did not complete successfully: {web_spans}")
    if todo_request is None or not todo_spans or todo_spans[0].get("outcome") != "success":
        raise RuntimeError("todo_add did not complete its scripted client round-trip")
    web_audio = bytes(audio_by_turn.get(web_turn, b""))
    todo_audio = bytes(audio_by_turn.get(todo_turn, b""))
    web_text = " ".join(agent_text_by_turn.get(web_turn, [])).strip()
    todo_text = " ".join(agent_text_by_turn.get(todo_turn, [])).strip()
    if not web_audio or not todo_audio or not web_text or not todo_text:
        raise RuntimeError("tool probe requires spoken text and audio for both turns")
    web_output = args.output_wav.with_name(
        f"{args.output_wav.stem}.web-search{args.output_wav.suffix}"
    )
    todo_output = args.output_wav.with_name(f"{args.output_wav.stem}.todo{args.output_wav.suffix}")
    _write_output_wav(web_output, web_audio, output_rate)
    _write_output_wav(todo_output, todo_audio, output_rate)
    return ToolProbeResult(
        web_search_turn_id=web_turn,
        todo_turn_id=todo_turn,
        web_search_span=web_spans[0],
        todo_span=todo_spans[0],
        todo_request=todo_request,
        web_search_output_wav=web_output,
        todo_output_wav=todo_output,
        web_search_audio_bytes=len(web_audio),
        todo_audio_bytes=len(todo_audio),
        web_search_spoken_text=web_text,
        todo_spoken_text=todo_text,
    )


def strategy_output_path(path: Path, strategy: str, compare: bool) -> Path:
    if not compare:
        return path
    return path.with_name(f"{path.stem}.{strategy}{path.suffix}")


async def async_main(args: argparse.Namespace) -> None:
    if args.expect_balance_exhaustion:
        result = await run_balance_exhaustion_probe(args)
        print(
            json.dumps(
                {"balance_exhaustion_verification": result.__dict__},
                indent=2,
                default=str,
            )
        )
        return
    if args.tool_probe_todo_wav is not None:
        result = await run_tool_probe(args)
        print(json.dumps({"phase3_tool_verification": result.__dict__}, indent=2, default=str))
        return
    if args.barge_in_wav is not None:
        result = await run_barge_probe(args)
        print(json.dumps({"barge_in_verification": result.__dict__}, indent=2, default=str))
        return
    strategies = (
        ("local_vad", "sarvam") if args.compare_strategies else (args.endpointing_strategy,)
    )
    results = []
    for strategy in strategies:
        result = await run_probe(
            args,
            strategy=strategy,
            output_wav=strategy_output_path(args.output_wav, strategy, args.compare_strategies),
        )
        results.append(result)
    print(
        json.dumps(
            {
                "waterfall_comparison": {
                    result.strategy: {
                        "stages_ms": result.stages,
                        "gated_silent_frames": result.dimensions.get("gated_silent_frames"),
                        "received_frames": result.dimensions.get("received_frames"),
                        "forwarded_frames": result.dimensions.get("forwarded_frames"),
                        "silent_frames_forwarded": result.dimensions.get("silent_frames_forwarded"),
                        "output_wav": str(result.output_wav),
                        "audio_bytes": result.audio_bytes,
                        "duration_seconds": round(result.duration_seconds, 3),
                        "billing_event_count": len(result.billing_events),
                        "final_billing": result.final_billing,
                    }
                    for result in results
                }
            },
            indent=2,
        )
    )


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(async_main(args))
    except Exception as exc:
        print(f"ws_probe failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
