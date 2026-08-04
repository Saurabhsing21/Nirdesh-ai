#!/usr/bin/env python3
"""Replay annotated WAV utterances through the live application WebSocket.

This script is intentionally excluded from CI because it requires a running local
server, a funded JWT, and live Sarvam credentials. Audio is sent at its recorded
rate so VAD and endpointing measurements remain valid.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import os
import platform
import statistics
import time
import wave
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from app.voice.metrics import percentile
from app.voice.protocol import CaptureFrame, encode_capture_frame

FRAME_SAMPLES = 512
SAMPLE_RATE_HZ = 16_000
FRAME_BYTES = FRAME_SAMPLES * 2
STAGE_NAMES = (
    "endpoint_window_ms",
    "stt_ms",
    "llm_ttft_ms",
    "first_speakable_ms",
    "tts_connection_wait_ms",
    "tts_ttfb_ms",
    "transport_playback_ms",
    "e2e_voice_to_voice_ms",
)


@dataclass(frozen=True)
class CorpusCase:
    case_id: str
    path: Path
    language: str
    tags: tuple[str, ...]
    expected_turns: int = 1
    max_endpoint_ms: float = 1000.0
    leading_silence_ms: int = 250
    trailing_silence_ms: int = 1200


@dataclass
class TurnResult:
    run_index: int
    cohort: str
    connection_temperature: Literal["cold", "warm"]
    strategy: Literal["local_vad", "sarvam"]
    case_id: str
    language: str
    tags: list[str]
    outcome: Literal["success", "interrupted", "error"]
    valid: bool
    started_at_utc: str
    stages: dict[str, float | None] = field(default_factory=dict)
    dimensions: dict[str, Any] = field(default_factory=dict)
    false_endpoint_count: int = 0
    false_continuation_count: int = 0
    transcript_count: int = 0
    audio_bytes: int = 0
    error: str | None = None
    exclusion_reason: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--token", default=os.getenv("BENCHMARK_JWT"))
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8000/ws/voice")
    parser.add_argument("--output", type=Path, default=Path("artifacts/latency-replay.json"))
    parser.add_argument(
        "--turns-per-cohort",
        type=int,
        default=25,
        help="Turns for each of local/cold, local/warm, sarvam/cold, sarvam/warm.",
    )
    parser.add_argument("--local-cold-turns", type=int, default=None)
    parser.add_argument("--local-warm-turns", type=int, default=None)
    parser.add_argument("--sarvam-cold-turns", type=int, default=None)
    parser.add_argument("--sarvam-warm-turns", type=int, default=None)
    parser.add_argument("--warm-session-size", type=int, default=25)
    parser.add_argument("--turn-timeout-seconds", type=float, default=180)
    parser.add_argument(
        "--outlier-turns",
        type=int,
        default=10,
        help="Extra local-VAD first-turn turns for each cold/warm outlier cohort.",
    )
    parser.add_argument("--corpus-id", default=None)
    parser.add_argument("--region", default="Asia/Kolkata")
    parser.add_argument("--configuration-label", default="phase6-default")
    parser.add_argument("--verbose-turns", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Run one turn per main cohort.")
    args = parser.parse_args()
    if not args.token:
        parser.error("--token or BENCHMARK_JWT is required")
    if args.turns_per_cohort < 1 or args.warm_session_size < 1 or args.outlier_turns < 0:
        parser.error("cohort sizes must be positive and outlier turns cannot be negative")
    overrides = (
        args.local_cold_turns,
        args.local_warm_turns,
        args.sarvam_cold_turns,
        args.sarvam_warm_turns,
    )
    if any(value is not None and value < 0 for value in overrides):
        parser.error("cohort overrides cannot be negative")
    return args


def load_manifest(path: Path) -> tuple[str, list[CorpusCase]]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("manifest must be an object with a cases array")
    root = path.parent
    cases: list[CorpusCase] = []
    for raw in payload["cases"]:
        if not isinstance(raw, dict):
            raise ValueError("each corpus case must be an object")
        audio_path = Path(str(raw["path"]))
        if not audio_path.is_absolute():
            audio_path = (root / audio_path).resolve()
        case = CorpusCase(
            case_id=str(raw["case_id"]),
            path=audio_path,
            language=str(raw["language"]),
            tags=tuple(str(tag) for tag in raw.get("tags", [])),
            expected_turns=int(raw.get("expected_turns", 1)),
            max_endpoint_ms=float(raw.get("max_endpoint_ms", 1000)),
            leading_silence_ms=int(raw.get("leading_silence_ms", 250)),
            trailing_silence_ms=int(raw.get("trailing_silence_ms", 1200)),
        )
        validate_wav(case.path)
        cases.append(case)
    if not cases:
        raise ValueError("manifest contains no cases")
    languages = {case.language for case in cases}
    if len(languages) < 3:
        raise ValueError("benchmark corpus must include at least three languages")
    corpus_id = str(payload.get("corpus_id") or path.stem)
    return corpus_id, cases


def validate_wav(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    with wave.open(str(path), "rb") as source:
        properties = (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
            source.getcomptype(),
        )
    if properties != (1, 2, SAMPLE_RATE_HZ, "NONE"):
        raise ValueError(f"{path} must be mono PCM16 at 16 kHz, got {properties}")


def read_case_pcm(case: CorpusCase) -> bytes:
    with wave.open(str(case.path), "rb") as source:
        pcm = source.readframes(source.getnframes())
    return silence(case.leading_silence_ms) + pcm + silence(case.trailing_silence_ms)


def silence(duration_ms: int) -> bytes:
    return b"\0\0" * round(SAMPLE_RATE_HZ * max(0, duration_ms) / 1000)


def ws_url(base_url: str, token: str, strategy: str) -> str:
    separator = "&" if "?" in base_url else "?"
    query = urlencode(
        {
            "token": token,
            "probe": "true",
            "endpointing_strategy": strategy,
        }
    )
    return f"{base_url}{separator}{query}"


async def send_pcm_realtime(connection, pcm: bytes, *, capture_seq: int) -> int:
    started = time.perf_counter()
    frame_count = math.ceil(len(pcm) / FRAME_BYTES)
    for frame_index in range(frame_count):
        target = started + frame_index * FRAME_SAMPLES / SAMPLE_RATE_HZ
        delay = target - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        offset = frame_index * FRAME_BYTES
        chunk = pcm[offset : offset + FRAME_BYTES].ljust(FRAME_BYTES, b"\0")
        await connection.send(
            encode_capture_frame(
                CaptureFrame(
                    capture_seq=capture_seq + frame_index,
                    capture_time_ms=time.perf_counter() * 1000,
                    pcm=chunk,
                )
            )
        )
    return capture_seq + frame_count


async def await_ready(connection, timeout_seconds: float) -> dict[str, Any]:
    async with asyncio.timeout(timeout_seconds):
        async for raw in connection:
            if isinstance(raw, bytes):
                continue
            event = json.loads(raw)
            if event.get("type") == "error":
                raise RuntimeError(str(event.get("message")))
            if event.get("type") == "ready":
                return event
    raise RuntimeError("voice socket closed before ready")


async def replay_turn(
    connection,
    *,
    case: CorpusCase,
    run_index: int,
    cohort: str,
    temperature: Literal["cold", "warm"],
    strategy: Literal["local_vad", "sarvam"],
    capture_seq: int,
    timeout_seconds: float,
) -> tuple[TurnResult, int]:
    result = TurnResult(
        run_index=run_index,
        cohort=cohort,
        connection_temperature=temperature,
        strategy=strategy,
        case_id=case.case_id,
        language=case.language,
        tags=list(case.tags),
        outcome="error",
        valid=False,
        started_at_utc=datetime.now(UTC).isoformat(),
    )
    audio_start: dict[str, Any] | None = None
    playback_started = False
    playback_start_ms: float | None = None
    metrics: dict[str, Any] | None = None
    interrupt_seen = False
    terminal_error: str | None = None
    with wave.open(str(case.path), "rb") as source:
        utterance_duration_seconds = source.getnframes() / source.getframerate()
    expected_speech_end = (
        time.perf_counter() + case.leading_silence_ms / 1000 + utterance_duration_seconds
    )
    early_final_count = 0
    pcm = read_case_pcm(case)
    sender = asyncio.create_task(
        send_pcm_realtime(connection, pcm, capture_seq=capture_seq),
        name=f"replay-{run_index}",
    )
    try:
        async with asyncio.timeout(timeout_seconds):
            async for raw in connection:
                if isinstance(raw, bytes):
                    result.audio_bytes += len(raw)
                    if audio_start is not None and not playback_started:
                        playback_started = True
                        received_ms = time.perf_counter() * 1000
                        decode_ms = time.perf_counter() * 1000
                        scheduled_ms = time.perf_counter() * 1000
                        playback_start_ms = scheduled_ms + 10.0
                        await connection.send(
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
                                    "playback_start_perf_ms": playback_start_ms,
                                    "e2e_voice_to_voice_ms": playback_start_ms
                                    - float(audio_start["last_speech_capture_time_ms"]),
                                }
                            )
                        )
                    continue

                event = json.loads(raw)
                event_type = event.get("type")
                if event_type == "final_transcript":
                    result.transcript_count += 1
                    if time.perf_counter() + 0.05 < expected_speech_end:
                        early_final_count += 1
                elif event_type == "audio_start":
                    audio_start = event
                elif event_type == "interrupt":
                    interrupt_seen = True
                    now_ms = time.perf_counter() * 1000
                    await connection.send(
                        json.dumps(
                            {
                                "type": "interrupt_ack",
                                "turn_id": event["turn_id"],
                                "interrupt_received_perf_ms": now_ms,
                                "queue_cleared_perf_ms": now_ms,
                                "audio_queue_cleared": True,
                                "played_audio_ms": 0,
                            }
                        )
                    )
                elif event_type == "tool_request":
                    await connection.send(
                        json.dumps(
                            {
                                "type": "tool_result",
                                "call_id": event["call_id"],
                                "result": {
                                    "ok": False,
                                    "error": "tools are disabled in the latency corpus",
                                },
                            }
                        )
                    )
                elif event_type == "turn_metrics":
                    metrics = event
                elif event_type == "error":
                    raise RuntimeError(str(event.get("message", "voice session error")))
                elif event_type == "call_ended":
                    terminal_error = f"call ended early: {event.get('reason')}"
                    if event.get("reason") != "error":
                        raise RuntimeError(terminal_error)
                elif event_type == "turn_complete":
                    if audio_start is not None and playback_start_ms is not None:
                        duration_ms = result.audio_bytes / (24_000 * 2) * 1000
                        await connection.send(
                            json.dumps(
                                {
                                    "type": "playback_finished",
                                    "turn_id": audio_start["turn_id"],
                                    "playback_end_perf_ms": playback_start_ms + duration_ms,
                                    "played_audio_ms": duration_ms,
                                }
                            )
                        )
                    break
        capture_seq = await sender
        if terminal_error is not None:
            raise RuntimeError(terminal_error)
        if metrics is None:
            raise RuntimeError("turn completed without turn_metrics")
        result.stages = {
            name: _optional_float(metrics.get("stages", {}).get(name)) for name in STAGE_NAMES
        }
        result.dimensions = dict(metrics.get("dimensions") or {})
        result.false_endpoint_count = early_final_count + max(
            0, result.transcript_count - case.expected_turns
        )
        endpoint_ms = result.stages.get("endpoint_window_ms")
        result.false_continuation_count = int(
            endpoint_ms is not None and endpoint_ms > case.max_endpoint_ms
        )
        result.outcome = "interrupted" if interrupt_seen else "success"
        missing_headline = [
            name
            for name in ("endpoint_window_ms", "stt_ms", "llm_ttft_ms", "tts_ttfb_ms")
            if result.stages.get(name) is None
        ]
        result.valid = result.outcome == "success" and not missing_headline
        if missing_headline:
            result.exclusion_reason = f"missing stages: {', '.join(missing_headline)}"
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        result.exclusion_reason = "turn_error"
        if not sender.done():
            sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
    return result, capture_seq


async def run_session(
    *,
    args: argparse.Namespace,
    cases: list[CorpusCase],
    run_indices: list[int],
    cohort: str,
    strategy: Literal["local_vad", "sarvam"],
    temperature: Literal["cold", "warm"],
) -> list[TurnResult]:
    results: list[TurnResult] = []
    capture_seq = 0
    async with connect(
        ws_url(args.ws_url, args.token, strategy),
        max_size=16 * 1024 * 1024,
        open_timeout=20,
        ping_interval=20,
        ping_timeout=20,
    ) as connection:
        await await_ready(connection, args.turn_timeout_seconds)
        if temperature == "warm":
            warmup, capture_seq = await replay_turn(
                connection,
                case=cases[0],
                run_index=-1,
                cohort=f"{cohort}_warmup",
                temperature="cold",
                strategy=strategy,
                capture_seq=capture_seq,
                timeout_seconds=args.turn_timeout_seconds,
            )
            print(
                json.dumps(
                    {"warmup": asdict(warmup) if args.verbose_turns else compact_progress(warmup)},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if not warmup.valid:
                raise RuntimeError(f"warmup failed: {warmup.error or warmup.exclusion_reason}")
        for run_index in run_indices:
            case = cases[run_index % len(cases)]
            result, capture_seq = await replay_turn(
                connection,
                case=case,
                run_index=run_index,
                cohort=cohort,
                temperature=temperature,
                strategy=strategy,
                capture_seq=capture_seq,
                timeout_seconds=args.turn_timeout_seconds,
            )
            results.append(result)
            print(
                json.dumps(
                    {
                        "progress": asdict(result)
                        if args.verbose_turns
                        else compact_progress(result)
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            append_checkpoint(args.output, result)
            if result.outcome == "error":
                break
        with contextlib.suppress(Exception):
            await connection.send(json.dumps({"type": "end_call"}))
    return results


async def run_cohort(
    *,
    args: argparse.Namespace,
    cases: list[CorpusCase],
    start_index: int,
    count: int,
    cohort: str,
    strategy: Literal["local_vad", "sarvam"],
    temperature: Literal["cold", "warm"],
) -> list[TurnResult]:
    results: list[TurnResult] = []
    remaining = list(range(start_index, start_index + count))
    while remaining:
        group_size = 1 if temperature == "cold" else args.warm_session_size
        group = remaining[:group_size]
        try:
            session_results = await run_session(
                args=args,
                cases=cases,
                run_indices=group,
                cohort=cohort,
                strategy=strategy,
                temperature=temperature,
            )
            results.extend(session_results)
            completed = max(1, len(session_results))
            remaining = remaining[completed:]
        except Exception as exc:
            run_index = remaining.pop(0)
            result = TurnResult(
                run_index=run_index,
                cohort=cohort,
                connection_temperature=temperature,
                strategy=strategy,
                case_id=cases[run_index % len(cases)].case_id,
                language=cases[run_index % len(cases)].language,
                tags=list(cases[run_index % len(cases)].tags),
                outcome="error",
                valid=False,
                started_at_utc=datetime.now(UTC).isoformat(),
                error=f"{type(exc).__name__}: {exc}",
                exclusion_reason="connection_error",
            )
            results.append(result)
            print(
                json.dumps(
                    {
                        "progress": asdict(result)
                        if args.verbose_turns
                        else compact_progress(result)
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            append_checkpoint(args.output, result)
    return results


def summarize(results: list[TurnResult]) -> dict[str, Any]:
    grouped: dict[str, list[TurnResult]] = defaultdict(list)
    for result in results:
        grouped[result.cohort].append(result)
    summaries: dict[str, Any] = {}
    for cohort, rows in grouped.items():
        valid_rows = [row for row in rows if row.valid]
        stage_summary: dict[str, Any] = {}
        for stage in STAGE_NAMES:
            values = [row.stages[stage] for row in valid_rows if row.stages.get(stage) is not None]
            stage_summary[stage] = distribution([float(value) for value in values])
        summaries[cohort] = {
            "attempted": len(rows),
            "valid": len(valid_rows),
            "errors": sum(row.outcome == "error" for row in rows),
            "interrupted": sum(row.outcome == "interrupted" for row in rows),
            "false_endpoint_count": sum(row.false_endpoint_count for row in rows),
            "false_continuation_count": sum(row.false_continuation_count for row in rows),
            "stages": stage_summary,
        }
    all_valid = [row for row in results if row.valid]
    summaries["overall"] = {
        "attempted": len(results),
        "valid": len(all_valid),
        "errors": sum(row.outcome == "error" for row in results),
        "interrupted": sum(row.outcome == "interrupted" for row in results),
        "false_endpoint_count": sum(row.false_endpoint_count for row in results),
        "false_continuation_count": sum(row.false_continuation_count for row in results),
        "stages": {
            stage: distribution(
                [float(row.stages[stage]) for row in all_valid if row.stages.get(stage) is not None]
            )
            for stage in STAGE_NAMES
        },
    }
    return summaries


def distribution(values: list[float]) -> dict[str, float | int | None]:
    return {
        "n": len(values),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99) if len(values) >= 100 else None,
        "mean": statistics.fmean(values) if values else None,
        "max": max(values) if values else None,
    }


def compact_progress(result: TurnResult) -> dict[str, Any]:
    return {
        "run_index": result.run_index,
        "cohort": result.cohort,
        "case_id": result.case_id,
        "temperature": result.connection_temperature,
        "outcome": result.outcome,
        "valid": result.valid,
        "stt_ms": result.stages.get("stt_ms"),
        "e2e_ms": result.stages.get("e2e_voice_to_voice_ms"),
        "false_endpoint_count": result.false_endpoint_count,
        "false_continuation_count": result.false_continuation_count,
        "error": result.error,
    }


def append_checkpoint(output_path: Path, result: TurnResult) -> None:
    checkpoint = output_path.with_suffix(".jsonl")
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint.open("a", encoding="utf-8") as destination:
        destination.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def _optional_float(value: Any) -> float | None:
    if isinstance(value, int | float) and math.isfinite(value):
        return float(value)
    return None


async def async_main(args: argparse.Namespace) -> int:
    manifest_corpus_id, cases = load_manifest(args.manifest)
    corpus_id = args.corpus_id or manifest_corpus_id
    checkpoint = args.output.with_suffix(".jsonl")
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text("")
    main_count = 1 if args.smoke else args.turns_per_cohort
    outlier_count = 0 if args.smoke else args.outlier_turns
    cohort_counts = {
        "local_vad_cold": main_count if args.local_cold_turns is None else args.local_cold_turns,
        "local_vad_warm": main_count if args.local_warm_turns is None else args.local_warm_turns,
        "sarvam_cold": main_count if args.sarvam_cold_turns is None else args.sarvam_cold_turns,
        "sarvam_warm": main_count if args.sarvam_warm_turns is None else args.sarvam_warm_turns,
    }
    specifications = [
        ("local_vad_cold", "local_vad", "cold", cohort_counts["local_vad_cold"]),
        ("local_vad_warm", "local_vad", "warm", cohort_counts["local_vad_warm"]),
        ("sarvam_cold", "sarvam", "cold", cohort_counts["sarvam_cold"]),
        ("sarvam_warm", "sarvam", "warm", cohort_counts["sarvam_warm"]),
        ("saaras_first_turn_cold", "local_vad", "cold", outlier_count),
        ("saaras_later_turn_warm", "local_vad", "warm", outlier_count),
    ]
    results: list[TurnResult] = []
    next_index = 0
    for cohort, strategy, temperature, count in specifications:
        if count == 0:
            continue
        cohort_results = await run_cohort(
            args=args,
            cases=cases,
            start_index=next_index,
            count=count,
            cohort=cohort,
            strategy=strategy,
            temperature=temperature,
        )
        results.extend(cohort_results)
        next_index += count
    payload = {
        "schema_version": 1,
        "metadata": {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "corpus_id": corpus_id,
            "manifest": str(args.manifest.resolve()),
            "application_region": args.region,
            "configuration_label": args.configuration_label,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "real_time_replay": True,
            "warm_session_size": args.warm_session_size,
            "main_cohort_counts": cohort_counts,
            "outlier_turns_per_cohort": outlier_count,
            "p99_minimum_n": 100,
        },
        "summary": summarize(results),
        "turns": [asdict(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "summary": payload["summary"]}, indent=2))
    valid_main = sum(
        row.valid
        for row in results
        if row.cohort in {"local_vad_cold", "local_vad_warm", "sarvam_cold", "sarvam_warm"}
    )
    required = sum(cohort_counts.values())
    return 0 if valid_main >= required else 2


def main() -> int:
    return asyncio.run(async_main(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
