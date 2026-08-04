# Voice-agent latency metrics

Research date: 2026-07-12

Scope: evidence and measurement design for `requirement.md` section 3a. Vendor figures below are published claims or documentation, not measurements of this repository. They are useful baselines, not guarantees.

## Executive conclusions

- Measure the user-perceived gap from the last acoustic speech frame to audio actually starting at the client. Do not start the end-to-end clock at the endpoint decision, because that hides the endpointing delay.
- The current timestamp schema conflates last speech with the later endpoint decision and subtracts timestamps from different clock domains. Both must be corrected before implementation.
- A 700 ms fixed silence threshold is workable as a conservative baseline but consumes nearly half of the 1.5 second p50 budget before STT, LLM, TTS, or transport. Current Sarvam and LiveKit guidance exposes a 500 ms conversational preset; semantic turn detection can reduce false cutoffs without forcing every turn to wait a long fixed silence.
- Track p50, p95, and p99. p50 describes the normal turn, but p99 is the operational headline because a multi-turn call gives users many opportunities to encounter a slow tail event.
- The requirement's p50 <= 1.5 s and p95 <= 2.5 s are reasonable initial service objectives for a cascaded system, but they are not human-equivalent. Human turn gaps cluster around 200 ms. Published modern voice systems commonly target or claim roughly 500-800 ms end to end under favorable conditions.

## Standard voice-to-voice latency decomposition

For a cascaded STT to LLM to TTS agent, the critical path is:

```text
last acoustic user speech
  -> end-of-turn decision
  -> final transcript available
  -> LLM request admitted
  -> first visible LLM text
  -> first speakable text segment
  -> TTS request admitted
  -> first audio bytes
  -> server send
  -> client receive/decode/schedule
  -> audio rendering starts
```

The user-perceived response latency is:

```text
voice_to_voice = client_audio_render_start - last_user_speech_frame
```

A useful first-order decomposition is:

```text
voice_to_voice
  = endpoint_decision_delay
  + transcript_ready_after_endpoint
  + orchestration_queueing
  + LLM time to first speakable text
  + TTS time to first audio
  + downstream network/decode/playout delay
```

This sum is conceptual. In a pipelined implementation stages can overlap, so separately summed durations may exceed or understate the wall-clock critical path. Store timestamps and spans, not only derived scalar durations.

LiveKit's current per-turn model tracks transcription delay, end-of-turn delay, LLM TTFT, TTS TTFB, playback latency, and an end-to-end field. Its approximate pipeline sum is end-of-utterance delay plus LLM TTFT plus TTS TTFB. LiveKit also notes that default room output can report playback too early because forwarding a frame to a track does not prove client audibility. Sources: [LiveKit data hooks](https://docs.livekit.io/deploy/observability/data/), [LiveKit metrics schema](https://docs.livekit.io/reference/python/livekit/agents/llm/).

Pipecat's user-bot observer uses the same user-stop to bot-start concept and also records service TTFB, text aggregation, user-turn duration, function calls, and first-greeting latency. Source: [Pipecat User-Bot Latency Observer](https://docs.pipecat.ai/api-reference/server/utilities/observers/user-bot-latency-observer).

Deepgram distinguishes transcript latency from end-of-turn latency. For voice agents, it calls the latter the critical metric and measures from actual speech end to the end-of-turn event. Its client-side measurement includes network overhead. Source: [Deepgram measuring streaming latency](https://developers.deepgram.com/docs/measuring-streaming-latency).

## Why p99 matters more than the mean

The mean hides multimodal and long-tail behavior. A service can average 700 ms while a small set of turns take several seconds because of connection acquisition, provider queueing, cold starts, retries, tool calls, network jitter, or an endpoint timeout.

In a conversation, tail exposure compounds. If each turn independently has a 1 percent chance of being at or beyond p99, the probability that a 20-turn call contains at least one such turn is:

```text
1 - 0.99^20 = 18.2%
```

At 50 turns it is 39.5 percent. Independence is only an illustration; correlated load or bad networks can make real sessions worse.

Pipecat explicitly models time-to-final-segment with measured p99 values because this tail determines how long turn-stop strategies need to wait. Its benchmark tool reports p50, p90, and p99 and recommends deployment-specific measurements. Source: [Pipecat STT latency tuning](https://docs.pipecat.ai/pipecat/fundamentals/stt-latency-tuning).

Deepgram recommends tracking p50, p95, and p99 rather than a single measurement because latency fluctuates over time. Source: [Deepgram measuring streaming latency](https://developers.deepgram.com/docs/measuring-streaming-latency).

This is consistent with general production guidance: percentile SLOs expose degradation in the slowest requests that a typical-performance SLO misses. Source: [Google Cloud latency SLO guidance](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/sli-metrics/lb-metrics).

Recommended reporting:

- p50: typical conversational feel.
- p95: a practical user-facing SLO and regression gate.
- p99: tail-health headline and incident detector.
- max plus sample count: debugging only, not an SLO.
- histogram buckets or raw per-turn rows: required so percentiles can be recomputed correctly.

Do not average precomputed percentiles across days. Merge raw distributions or histogram counts.

## Published latency baselines

### Human conversation

Levinson and Torreira review natural conversation and report turn gaps on the order of 200 ms even though language production itself generally takes more than 600 ms. This means people predict turn endings and plan responses before the prior speaker has fully stopped. Source: [Levinson and Torreira, 2015](https://pure.mpg.de/view/item_2161027_6).

Stivers et al. found a broadly shared turn-taking organization across ten languages, with language-level average gaps varying within about 250 ms of the cross-language mean. This is evidence for a tight human scale, but not a universal requirement that every reply begin at exactly 200 ms. Source: [Stivers et al., 2009](https://pubmed.ncbi.nlm.nih.gov/19553212/).

An Interspeech study of filler timing found the most suitable response timing around 200-500 ms after the previous speaker finished. Source: [Lala et al., 2019](https://www.isca-archive.org/interspeech_2019/lala19_interspeech.html).

Interpretation for this project:

- 200-500 ms is a human conversational reference, not a realistic initial budget for this quality-first `sarvam-105b` cascade.
- Sub-second response onset is an excellent stretch goal.
- 1.0-1.5 seconds can still feel usable, especially for complex answers.
- Beyond roughly 2 seconds, fillers or explicit state cues can reduce uncertainty, but they do not remove the underlying latency.

### Pipecat

Pipecat states that typical complete round-trip voice interactions are 500-800 ms and describes under-one-second behavior in its quickstart. These are framework-level claims, dependent on provider, region, transport, and configuration. Sources: [Pipecat introduction](https://docs.pipecat.ai/pipecat/get-started/introduction), [Pipecat overview](https://docs.pipecat.ai/pipecat/learn/overview).

Pipecat also says local Silero VAD can detect speech 150-200 ms faster by avoiding a provider round trip. More importantly, it treats each STT provider's p99 time-to-final-segment as a turn-detection input. Source: [Pipecat speech-to-text guidance](https://docs.pipecat.ai/pipecat/learn/speech-to-text).

### Deepgram

Deepgram publishes these approximate ranges:

| Component | Typical range |
|---|---:|
| Network transit | 20-200 ms |
| Transcription processing | 150-300 ms |
| Total transcript latency at client | 200-500 ms |
| Flux end-of-turn detection | 100-500 ms |

It says Nova-3 streaming transcription is generally sub-300 ms and that integrated Flux turn detection can reduce agent response latency by 200-600 ms compared with a traditional STT plus VAD path. These are vendor figures and must not be transferred to Sarvam. Source: [Deepgram measuring streaming latency](https://developers.deepgram.com/docs/measuring-streaming-latency).

Deepgram's published private-VPC voice-agent example reports median end-to-end latency below 700 ms and p90 below one second. The deployment and model stack differ from this project, so this is a reference point only. Source: [Deepgram and NVIDIA voice-agent benchmark](https://deepgram.com/learn/voice-agents-deepgram-nvidia-nemotron).

### Cartesia

Cartesia documents Sonic 2 first audio at 90 ms and Sonic Turbo at 40 ms. This is TTS time to first byte, not voice-to-voice latency, and it is a vendor best-case capability claim. Source: [Cartesia API overview](https://docs.cartesia.ai/2025-04-16/get-started/overview).

The important lesson is metric scope: a 40-90 ms TTS TTFB does not imply a 40-90 ms conversation gap. Endpointing, final transcript readiness, LLM text generation, network delivery, decoding, and client playout remain outside that number.

### LiveKit

LiveKit's standard VAD-only endpointer historically used a 500 ms `min_endpointing_delay`. Lowering it responds faster but causes more accidental interruptions. Its semantic end-of-utterance model dynamically shortens or extends the VAD timeout and, in LiveKit's testing, reduced unintentional interruptions by 85 percent while falsely extending a completed turn 3 percent of the time. Source: [LiveKit transformer turn detection](https://blog.livekit.io/using-a-transformer-to-improve-end-of-turn-detection).

LiveKit's current observability model treats end-of-turn delay, LLM TTFT, TTS TTFB, and playback as distinct fields, reinforcing the waterfall proposed here. Source: [LiveKit data hooks](https://docs.livekit.io/deploy/observability/data/).

## Silence endpointing versus semantic turn detection

### Silence-only endpointing

Silence endpointing is easy to reason about:

```text
if VAD reports no speech for threshold_ms:
    end the turn
```

Benefits:

- Deterministic upper contribution for a clean stop.
- Language-agnostic.
- Works without a transcript.
- Easy to replay and unit-test.

Costs:

- Every normal turn pays at least the silence threshold.
- Short thresholds cut off hesitation, list dictation, numbers, and mid-sentence pauses.
- Long thresholds make the agent feel sluggish.
- Noise and echo can delay or prevent silence detection.

Deepgram's classic endpointing is a configurable VAD silence duration. Its documentation emphasizes pairing endpointing with interim results and treating `speech_final` as a pause-based boundary. Source: [Deepgram endpointing](https://developers.deepgram.com/docs/endpointing).

Sarvam currently documents roughly 1 second silence for ordinary VAD and 0.5 seconds for `high_vad_sensitivity=true`, plus frame-level controls. Source: [Sarvam streaming STT guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/streaming-api).

For the requirement's 700 ms threshold:

- It alone consumes 47 percent of a 1.5 second p50 budget.
- Lowering it to 500 ms returns 200 ms of budget on every clean turn.
- A 500 ms starting point is supported by both Sarvam's high-sensitivity guidance and LiveKit's historical default, but must be evaluated in the target languages and acoustic conditions.

### Semantic or hybrid turn detection

A semantic detector asks whether the utterance is linguistically complete, usually from partial or final transcript context. A hybrid system uses that result to shorten or extend the VAD silence window.

Benefits:

- Can wait through "my account number is..." and similar incomplete constructions.
- Can respond quickly after clearly complete questions.
- Reduces the forced tradeoff of one threshold for all turns.

Costs:

- Depends on transcript availability and accuracy.
- Adds inference and orchestration work.
- Can be language-specific. LiveKit's cited 2024 model was English-only.
- Mistakes have asymmetric UX costs: a premature end interrupts the user, while a false continuation adds silence.

The best published quantitative result among the requested sources is LiveKit's 85 percent reduction in unintentional interruptions with a 3 percent false continuation rate, compared with VAD alone. Source: [LiveKit transformer turn detection](https://blog.livekit.io/using-a-transformer-to-improve-end-of-turn-detection).

Deepgram's current guidance says Flux integrated end-of-turn detection typically takes 100-500 ms and can save 200-600 ms relative to traditional STT plus VAD. Source: [Deepgram measuring streaming latency](https://developers.deepgram.com/docs/measuring-streaming-latency).

Recommendation for this project:

1. Start with local VAD and a 500 ms configurable silence threshold, not a hard-coded 700 ms assumption.
2. Record false endpoints, user resumptions within 1 second, and abandoned long pauses. Latency alone cannot evaluate turn quality.
3. Keep the turn-detector interface pluggable.
4. Do not promise semantic endpointing until there is an Indic-language model or enough project data to validate one.
5. Sarvam partial transcripts are not documented, so transcript-driven preemptive generation is currently `UNVERIFIED` for this stack.

## Review of the section 3a timestamp schema

### Critical corrections

#### 1. Split acoustic speech end from endpoint decision

Current section 3a defines `t_speech_end` as "endpoint fired", then defines `endpoint_delay` as `speech_end - last speech frame`, but no `last speech frame` timestamp exists. It also defines end-to-end from `t_speech_end`, which excludes the largest fixed cost.

Replace it with:

- `t_last_speech_frame_server`: server receipt/classification time of the last frame considered speech.
- `t_endpoint_decision`: time the turn detector commits the end of turn.
- `endpoint_delay_ms = t_endpoint_decision - t_last_speech_frame_server`.
- `e2e_voice_to_voice_ms = t_client_playback_start - t_last_speech_frame`, using a valid cross-clock method described below.

This aligns with Deepgram's end-of-turn definition and LiveKit's end-of-utterance delay. Sources: [Deepgram measuring streaming latency](https://developers.deepgram.com/docs/measuring-streaming-latency), [LiveKit data hooks](https://docs.livekit.io/deploy/observability/data/).

#### 2. Do not subtract server and browser monotonic clocks

Server `monotonic()` and browser `performance.now()` have unrelated origins. The expression `t_client_playback - t_speech_end` is invalid unless both timestamps share a clock domain.

Preferred designs, in descending order:

1. Measure the full interval in one clock domain. The browser can timestamp the local last speech sample and local playback start, provided audio worklet capture timestamps are carried through with a turn ID.
2. Synchronize clocks with a repeated ping exchange and store estimated offset plus uncertainty. This is more complex and still approximate.
3. Keep server and client submetrics separate. Use server time from last received speech frame to first audio send, then client time from first audio receive to scheduled playback. Do not label their unsynchronized raw difference as exact end to end.

For Phase 2, option 1 is the strongest: attach a browser capture sequence number and capture-time to each upstream frame, echo the relevant turn/capture marker in the first downstream audio metadata, then report browser-local playback start.

#### 3. Define actual playback, not enqueue

`playback_started` must mean the first sample is scheduled or rendered by Web Audio, not merely received or appended to a queue. Record separately:

- `t_client_audio_received`.
- `t_client_decode_complete`, if decoding is used.
- `t_client_audio_scheduled` with the Web Audio context time.
- `t_client_playback_start` when the scheduled source starts.

Browser code cannot directly observe the physical speaker cone. Treat scheduled/render start as the practical boundary and state that hardware/output buffering remains outside measurement.

#### 4. Add an interrupt acknowledgement

Section 3a refers to `t_interrupt_flushed` as a client acknowledgement, but the protocol has only a server-to-client `interrupt` message. Add:

```json
{"type":"interrupt_ack","turn_id":"...","audio_queue_cleared":true}
```

Record:

- `t_barge_speech_detected_server`.
- `t_interrupt_sent_server`.
- `t_interrupt_received_client`.
- `t_playback_queue_cleared_client`.
- `t_interrupt_ack_received_server`.

Report local client flush delay and server round-trip acknowledgement separately. The true acoustic stop includes the browser/audio-device output buffer and is not exactly observable without loopback capture.

### Recommended timestamp additions

| Timestamp or span | Why it matters |
|---|---|
| `t_audio_frame_client_capture` and sequence | Establishes a browser clock anchor and detects upstream buffering. |
| `t_audio_frame_server_receive` | Separates upstream transport from endpointing. |
| `t_stt_flush_sent` | Makes STT finalization duration well-defined. |
| `t_stt_final` | Already present; pair with flush and last speech. |
| `t_llm_request_start` | TTFT needs a start boundary. |
| `t_llm_first_reasoning_token` | Reasoning can arrive before user-visible content on Sarvam. |
| `t_llm_first_visible_token` | More accurate UX TTFT than generic first token. |
| `t_llm_first_speakable_chunk` | Sentence completion may be too conservative; record the actual chunking policy. |
| `t_llm_complete` | Useful for throughput and cancellation waste. |
| Tool-call start/end spans | Tools can dominate individual turns and should not be folded into unexplained LLM time. |
| `t_tts_text_submitted` | TTS TTFB requires a start boundary. |
| `t_tts_first_chunk` and `t_tts_complete` | First response and total synthesis behavior. |
| TTS connection acquire start/end and reused flag | Connection setup and reconnects create tail latency. LiveKit measures these fields. Source: [LiveKit metrics reference](https://docs.livekit.io/reference/python/livekit/agents/metrics/index.html). |
| `t_audio_sent_server` | Already present; include chunk/turn ID. |
| `t_audio_received_client` | Separates network transit from decode and queueing. |
| `t_client_playback_start` | Already intended; clarify clock and semantics. |
| `t_client_playback_end` | Needed for spoken-history truncation and playback throughput. |
| Retry, timeout, cancel, and provider request spans | Explains p99 outliers and wasted work. |

### Recommended derived metrics

- `upstream_audio_transport_ms`: client capture to server receipt, measured with synchronized or same-domain markers.
- `endpoint_decision_ms`: last speech frame to turn commit.
- `stt_flush_to_final_ms`: flush sent to final transcript.
- `stt_eot_ms`: last speech frame to final transcript.
- `orchestrator_queue_ms`: final transcript or turn commit to LLM request start.
- `llm_visible_ttft_ms`: request start to first visible content token.
- `llm_first_speakable_ms`: request start to first TTS-eligible text.
- `tts_ttfb_ms`: first text submitted to first audio bytes.
- `downstream_to_playback_ms`: server send to client playback, with clock method recorded.
- `e2e_voice_to_voice_ms`: last acoustic speech to client playback start.
- `barge_detection_ms`: barge speech onset to server detection.
- `barge_client_flush_ms`: interrupt receipt to local queue clear.
- `barge_in_stop_ack_ms`: detected onset to acknowledgement received, clearly labeled as an acknowledgement proxy rather than proof of acoustic silence.
- `audio_queue_depth_ms_at_first_playback`: catches over-buffering.
- `realtime_factor`: generated audio duration divided by synthesis duration.
- `interrupted_audio_generated_ms` and `interrupted_audio_played_ms`: quantifies wasted TTS and supports accurate conversation history.
- `turn_false_endpoint`: user resumes within a configured window after endpoint.
- `turn_false_continuation`: complete-looking turn waited past the maximum desired delay, determined in replay annotation.

### Dimensions and data-quality fields

Store enough context to explain distributions:

- model IDs and explicit model parameters.
- language code and auto-detection confidence when available.
- audio codec, sample rate, frame size, and input duration.
- provider region and application region.
- connection reused, cold start, retry count, and HTTP/WebSocket close reason.
- tool use and tool name.
- interrupted, timed out, errored, or balance-cutoff outcome.
- missing/censored timestamp flags.
- software version, configuration hash, and test corpus ID.

Never coerce a missing timestamp to zero. Exclude invalid turns from a percentile only with a named reason and report the exclusion count.

## Proposed requirements changes for section 3a

The following wording is recommended when `requirement.md` is revised:

1. Define `t_last_speech_frame` as the ground-truth user stop and `t_endpoint_decision` as a separate later event.
2. Define end-to-end latency from last speech frame to client playback start, not from endpoint decision.
3. State the clock domain for every timestamp. Do not subtract raw client and server monotonic clocks.
4. Add start timestamps for STT flush, LLM request, and TTS submission so all stage durations are well-defined.
5. Split first LLM token into reasoning token, visible content token, and first speakable chunk for Sarvam's default reasoning mode.
6. Add client receive, decode, schedule, and playback timestamps.
7. Add `interrupt_ack` to the protocol and label the resulting measure as a queue-flush acknowledgement proxy.
8. Store tool spans, connection acquisition/reuse, retries, errors, and censored turns.
9. Change the baseline endpoint setting from a claimed fixed 700 ms budget to a configurable initial value of 500 ms, then select the production value from multilingual replay data that considers both latency and false endpoints.
10. Keep p50 <= 1.5 s and p95 <= 2.5 s as initial acceptance thresholds, add a p99 reporting target after the Phase 2 replay baseline, and never infer p99 from fewer than 100 turns. For a stable p99 estimate, use substantially more traffic and attach the sample count.

## Benchmark protocol for this repository

To make the numbers comparable and actionable:

1. Use at least English plus two Indic languages, with a mix of short questions, hesitant speech, list/number dictation, code-mixing, and background noise.
2. Replay in real time. Sending a WAV faster than real time invalidates endpoint and transcript-lag measurements.
3. Run warm and cold connection cohorts separately.
4. Record at least 100 valid turns for a preliminary p99 and more for release claims. The requirement's N >= 20 is enough for a smoke test, not a meaningful p99. With 20 observations, the empirical p99 is effectively the maximum.
5. Measure both latency and turn quality: false endpoint rate, false continuation rate, interruption detection rate, and STT accuracy.
6. Report p50, p95, p99, sample count, failures, exclusions, model/configuration, region, and date.
7. Preserve raw per-turn rows so future changes can be compared against the same corpus.

The correct Phase 0 outcome is not to assert Sarvam will meet the requirement's stage budgets. Sarvam publishes no percentile latency numbers for Saaras v3, Sarvam-105B, or Bulbul v3. Those budgets remain hypotheses until the authenticated replay harness measures them.

## Related documentation

- [Architecture](architecture.md)
- [Sarvam API research](sarvam-api-research.md)
- [Replay benchmarks](BENCHMARKS.md)
- [Requirements](../requirement.md)
- [Project README](../README.md)
