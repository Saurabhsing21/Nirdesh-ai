# Voice latency benchmarks

This report is the reproducible Phase 6 baseline for NirdeshAI's sandwich voice architecture. Raw
turn rows are emitted by `backend/scripts/latency_replay.py`; no valid slow turn is removed from a
reported percentile.

## Status

Completed on 2026-07-12: 185 measured attempts produced 139 valid turns and 46 errors. The strict
harness exited nonzero because not every planned turn was valid, but it preserved all measured rows.
The 100-turn cold local-VAD cohort is large enough to quote a preliminary p99.

## Methodology

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| Application location | Asia/Kolkata, India |
| Provider region | Not disclosed by Sarvam |
| Corpus ID | `phase6-synthetic-multilingual-v1` |
| Languages | English (`en-IN`), Hindi (`hi-IN`), Tamil (`ta-IN`) |
| Corpus shape | Three short conversational requests |
| Replay | Mono PCM16 at 16 kHz, sent in real time as 512-sample frames |
| Endpointing | `local_vad` at 500 ms versus Sarvam built-in endpointing |
| Models | Saaras v3, `sarvam-105b` with `reasoning_effort:null`, Bulbul v3 at 24 kHz PCM |
| Main sample | 100 local/cold, 25 local/warm, 20 Sarvam/cold, 20 Sarvam/warm |
| Outlier plan | 10 first-turn cold plus 10 later-turn warm local-VAD turns |
| Client playback proxy | First PCM receive plus 10 ms scheduled-playback offset |

Cold means a new application WebSocket for the measured turn. Warm means an uncounted warm-up turn
followed by measured turns on the same application WebSocket. The current implementation rotates the
Saaras socket after every final transcript and creates a fresh Bulbul socket per response, so "warm"
does not imply vendor-socket reuse. This distinction matters when interpreting cold-versus-warm data.

All three WAVs use macOS system voices. This makes the corpus reproducible and multilingual but does
not represent microphones, room noise, speaker variation, natural hesitation, number/list dictation,
or code-mixing. A release benchmark needs human recordings that cover those categories.

## Main cohorts

| Cohort | Valid / attempted | e2e p50 | e2e p90 | e2e p95 | False endpoints | False continuations |
|---|---:|---:|---:|---:|---:|---:|
| Local VAD, cold | 100 / 100 | 2,956.2 ms | 3,834.9 ms | 3,991.1 ms | 0 | 0 |
| Local VAD, warm | 21 / 25 | 2,266.1 ms | 2,930.5 ms | 3,058.9 ms | 0 | 0 |
| Sarvam endpointing, cold | 0 / 20 | N/A | N/A | N/A | 0 observed | 0 observed |
| Sarvam endpointing, warm | 1 / 20 | 2,638.8 ms* | 2,638.8 ms* | 2,638.8 ms* | 0 | 0 |

`*` One valid sample is shown descriptively and is not a meaningful percentile. Sarvam endpointing
did not produce enough complete turns for a latency comparison. The failures remain part of the
reported outcome rather than being excluded from the denominator.

## Per-stage distribution

The following consistent distribution is the 100-turn cold local-VAD cohort. Smaller cohorts do not
quote p99. `first_speakable` is visible-token to first TTS-eligible chunk and can include a tool detour.
Pipelined stages overlap, so their percentiles must not be added to reconstruct e2e.

| Stage | N | p50 | p90 | p95 | p99 if eligible |
|---|---:|---:|---:|---:|---:|
| Endpoint window | 100 | 512.2 ms | 513.1 ms | 513.6 ms | 513.9 ms |
| STT flush to final | 100 | 307.8 ms | 742.9 ms | 916.7 ms | 1,227.3 ms |
| LLM visible TTFT | 100 | 411.8 ms | 496.3 ms | 521.5 ms | 848.6 ms |
| First speakable after first visible token | 100 | 1,444.6 ms | 2,123.2 ms | 2,236.8 ms | 2,578.2 ms |
| TTS TTFB | 100 | 246.0 ms | 270.6 ms | 292.4 ms | 424.6 ms |
| Client transport and scheduled playback | 100 | 10.0 ms | 10.0 ms | 10.0 ms | 10.0 ms |
| End-to-end voice to voice | 100 | 2,956.2 ms | 3,834.9 ms | 3,991.1 ms | 4,339.3 ms |

## Target evaluation

| Target | Result |
|---|---|
| e2e p50 at or below 1.5 s | **Failed:** 2.96 s in the 100-turn cold local-VAD cohort |
| e2e p95 at or below 2.5 s | **Failed:** 3.99 s in the 100-turn cold local-VAD cohort |

## Agent and failure findings

- 128 of 139 valid turns (92.1 percent) invoked at least one tool even though the corpus prompts were
  intended as ordinary conversational requests. The tool-call counts were 109 `todo_add` and 70
  `web_search`; some turns invoked both. This is observed agent behavior, not a harness exclusion.
- Tool turns measured e2e p50 2,867.6 ms and p95 3,955.8 ms across N=128. The small no-tool subset
  measured p50 1,969.7 ms and p95 3,021.5 ms across N=11. The no-tool subset is too small and
  non-random for a release claim, but it shows that tool selection materially affected the headline.
- Local-VAD warm sessions completed 21 of 25 attempts. Server logs for failed multilingual turns
  included Bulbul language validation errors where generated text contained no accepted character for
  the selected TTS language.
- Sarvam endpointing completed 1 of 40 measured attempts. Server logs frequently showed the Bulbul
  WebSocket closing before response completion after STT had finalized. The current evidence does not
  isolate endpointing as the cause; it establishes that this full application cohort was unstable.
- One uncounted Sarvam warm-up turn reached 33.9 seconds e2e. Warm-ups are excluded by design from
  measured cohort percentiles, so it is disclosed here as a setup outlier rather than silently omitted.

## Saaras first-turn outlier study

The dedicated cohort measures the recurring 9.85 s, 20 s, and 23.2 s first-turn
flush-to-final observations seen during earlier manual probes. It compares new application connections
with later turns on a pre-warmed application connection while recording the current per-turn Saaras
socket rotation behavior.

| Cohort | Valid / attempted | STT p50 | STT p90 | STT p95 | STT max |
|---|---:|---:|---:|---:|---:|
| First turn, cold application connection | 10 / 10 | 309.7 ms | 801.7 ms | 1,123.2 ms | 1,444.6 ms |
| Later turn, warm application connection | 7 / 10 | 373.3 ms | 593.8 ms | 635.9 ms | 677.9 ms |

The earlier 9.85 s, 20 s, and 23.2 s Saaras flush-to-final incidents did not recur in these 20
dedicated measured attempts. Cold had the worse p95 and maximum, but this small cohort is not enough to
declare the first-turn problem fixed. Three warm measured turns failed elsewhere in the response path.

Potential mitigations to evaluate after measurement:

- Preconnect the application and Saaras sockets before the first utterance.
- Add bounded reconnect and retry policy with a visible error state rather than an unbounded wait.
- Compare built-in Saaras endpointing with local manual flush at replay scale.
- Keep a vendor connection pool only if authenticated testing proves the protocol safely supports reuse.
- Preserve the slower first-turn cohort in product SLO reporting instead of hiding it with warm-up.

## Caveats

- Single client location and one network path.
- Small synthetic corpus with one voice per language and no representative noise.
- Provider deployment region and provider load are unknown.
- Scheduled Web Audio start is a client proxy, not acoustic loopback measurement.
- The prompts were intended to avoid tool calls; any unexpected tool use remains visible in raw turn
  dimensions and is not silently discarded. In this run it occurred on most valid turns.
- The false-endpoint detector flags a final transcript before the annotated utterance end; the
  false-continuation detector flags endpoint windows above the manifest threshold. Both counters were
  zero, but the synthetic corpus is too narrow to establish production endpoint quality.
- These results characterize this configuration and date, not a general Sarvam service-level claim.

## Reproduce

Start the backend with live keys and a funded wallet, then run:

```bash
cd backend
PYTHONPATH=. python scripts/latency_replay.py \
  --manifest /absolute/path/to/corpus-manifest.json \
  --token "$JWT" \
  --local-cold-turns 100 \
  --local-warm-turns 25 \
  --sarvam-cold-turns 20 \
  --sarvam-warm-turns 20 \
  --warm-session-size 5 \
  --outlier-turns 10 \
  --output artifacts/phase6-replay.json
```

For corpus structure, copy `backend/scripts/benchmark-corpus.example.json`. Keep recordings and raw
results out of source control when they contain private speech.

## Related documentation

- [Architecture](architecture.md)
- [Voice metrics research](voice-metrics.md)
- [Sarvam API research](sarvam-api-research.md)
- [Requirements](../requirement.md)
- [Project README](../README.md)
