# Sarvam Voice Agent - Requirements & Implementation Plan

A real-time, multilingual (Indic) voice agent built on the Sarvam AI platform
(Saaras STT → Sarvam-105B → Bulbul TTS), with backend silence detection,
barge-in interruption, agent tools (web search, browser-local todos),
email-OTP authentication, a wallet with per-minute billing and usage
analytics, and **first-class latency instrumentation** (per-turn stage
timestamps, p50/p95/p99 rollups) built into the first production pipeline
slice in Phase 2b, immediately after Phase 2a proves the raw vendor loop.

Build order is research-first: verify Sarvam's actual API surface and the
industry's voice-latency benchmarks (Phase 0) before committing to the
architecture below, then build in independently testable phases.

---

## 1. Functional Requirements

| # | Requirement | Notes |
|---|-------------|-------|
| FR-1 | **General Q&A by voice.** User speaks; agent answers by voice with streamed, low-latency audio. | Sarvam-105B chat completions (streaming). |
| FR-2 | **Internet lookup.** Agent can perform a quick web search when the question needs fresh/factual data. | `web_search` tool → Exa API, executed server-side. |
| FR-3 | **Todo list, stored in the browser.** Agent can add/list/complete/delete todos by voice; data lives only in `localStorage`. | Tool calls are proxied over the WebSocket to the client for execution ("client-side tools"). A visual todo panel allows manual edits too. |
| FR-4 | **Backend-only silence detection.** Silence is detected on the server; silent audio is never forwarded to the STT/agent. | Silero VAD (ONNX) per 32 ms frame; speech-gated forwarding with pre-roll. Also used for turn endpointing. |
| FR-5 | **Optimized.** Minimize tokens, bandwidth, and vendor cost. | VAD gating (no silence to STT), phrase-aware TTS pipelining with provider-safe chunk sizes, binary PCM frames client↔server, connection reuse. |
| FR-6 | **Email OTP verification.** Login = email → 6-digit OTP → JWT. | Resend for delivery; dev fallback logs OTP to server console when no key configured. |
| FR-7 | **Interruption (barge-in and thinking cancellation).** If the user starts speaking while the agent is talking or still preparing an answer, the old response stops and the agent listens. | Playback barge-in flushes audio and reconciles spoken history. Before playback, confirmed speech cancels the exact LLM/TTS/tool work without requiring a playback acknowledgement or retaining unspoken assistant text. |
| FR-8 | **Wallet + usage billing + analytics.** User adds money (no payment gateway); calls are charged at a per-minute rate; analytics for recent minutes/day/week. | Per-second proration; auto-cutoff at zero balance; SQLite persistence; charts in frontend. |
| FR-9 | **Performant real-time behavior.** | Latency budget below; async single event loop per session, no blocking calls in the hot path. |
| FR-10 | **Latency observability.** Every turn records timestamps at each pipeline stage; per-stage and end-to-end latencies are persisted and reported as p50/p95/p99. | `TurnTimer` in VoiceSession; `turn_metrics` table; percentile rollups in analytics; optional dev latency HUD in the call screen. |
| FR-11 | **Responsive acknowledgement cue.** On eligible slow normal turns, the browser may play one short cached, non-semantic acknowledgement while the real answer is being prepared. | The cue is deterministic, language-compatible, cooldown-limited, independently mixed, fail-silent, and preempted by answer audio/new speech. Cue latency is never reported as answer latency. |

### Non-functional requirements

- **Scope emphasis: backend-first.** The engineering depth of this project is
  the backend - the voice pipeline, VAD gating, barge-in, latency
  instrumentation, billing, and tests. The frontend stays deliberately simple:
  functional pages, minimal styling, no design system, no polish passes. Any
  frontend complexity must be justified by a functional requirement (e.g., the
  instant-flush playback queue for FR-7); otherwise the simplest working UI wins.
- **Latency hypotheses pending measurement:** end of the user's last acoustic
  speech frame → first agent audio playback is initially targeted at
  **p50 ≤ 1.5 s, p95 ≤ 2.5 s** (voice-to-voice, measured rather than estimated
  per FR-10; see §3a). Sarvam publishes no p50/p95/p99 latency numbers for
  Saaras v3, Sarvam-105B, or Bulbul v3, so every stage number below is a
  hypothesis until the authenticated real-time replay harness measures it:
  - Endpoint decision (trailing-silence window): initial default ~500 ms; the
    final value is selected from multilingual replay data that also measures
    false endpoints and false continuations.
  - STT finalization (flush → final transcript): hypothesis ~150-300 ms.
  - LLM first speakable text: hypothesis ~400-800 ms, streamed and tracked
    separately from first reasoning and first visible tokens.
  - TTS first audio chunk: hypothesis ~200-300 ms, streamed and pipelined with
    the LLM.
  - Barge-in acknowledgement proxy (speech detection → client queue-clear ack):
    hypothesis **≤ 250 ms p95**. This is not proof of physical speaker silence.
- **No unmeasured hot path:** any stage in the voice loop must emit its
  timestamps through `TurnTimer`; the hypotheses above are validated against
  recorded percentiles rather than treated as facts. Published Phase 0
  benchmarks provide context only; Sarvam-specific budgets are set from the
  Phase 2 replay corpus.
- **Readability/extensibility:** small modules with single responsibilities,
  typed interfaces, dependency injection via FastAPI, no hidden globals.
- **Testability:** pure-logic components (VAD gate, billing, chunker,
  analytics) are isolated from I/O and covered by unit tests; network clients
  are thin and mockable.
- **Security:** JWT (HS256) with expiry; OTP rate-limited with max attempts &
  TTL; API keys only in `.env` (never committed); voice WS requires a valid token.

---

## 2. External Services & API Keys

| Env var | Provider | Used for | Where to get |
|---------|----------|----------|--------------|
| `SARVAM_API_KEY` | Sarvam AI | STT (Saaras v3), LLM (`sarvam-105b`), TTS (Bulbul v3) | https://dashboard.sarvam.ai |
| `EXA_API_KEY` | Exa | `web_search` agent tool | https://dashboard.exa.ai |
| `RESEND_API_KEY` | Resend | OTP delivery emails | https://resend.com |

No other external services. `JWT_SECRET` is generated locally. SQLite requires no setup.

**Dev fallbacks (no keys required to boot):** missing `RESEND_API_KEY` → OTP is
logged to the backend console; missing `EXA_API_KEY` → search tool reports it is
unconfigured; missing `SARVAM_API_KEY` → voice call is rejected with a clear error.

### Sarvam API contracts used

- **Chat:** `POST https://api.sarvam.ai/v1/chat/completions`, header
  `api-subscription-key`, model `sarvam-105b`, OpenAI-compatible messages/tools,
  `stream: true` (SSE), and `reasoning_effort: null` for voice turns. Sarvam's
  default reasoning tokens stream before visible content and inflate visible
  TTFT. `sarvam-105b` remains the required default; `sarvam-30b` is documented
  only as a lower-latency fallback and is not used by this implementation.
  `AgentRunner` uses LangChain's LangGraph-backed `create_agent` with
  `ChatOpenAI(base_url="https://api.sarvam.ai/v1", model="sarvam-105b",
  reasoning_effort=None)` and an `InMemorySaver` checkpointer. One LangGraph
  `thread_id` is scoped to each voice call, so conversation history survives
  turns within that call but is not persisted across calls.
- **STT:** `wss://api.sarvam.ai/speech-to-text/ws?model=saaras:v3&mode=transcribe&language-code=unknown&sample_rate=16000&input_audio_codec=pcm_s16le&flush_signal=true&vad_signals=true`,
  header `Api-Subscription-Key`. Client sends
  `{"audio": {"data": <b64>, "sample_rate": "16000", "encoding": "audio/wav"}}`
  and `{"type": "flush"}` to finalize; server sends
  `{"type":"data","data":{"request_id":"...","transcript":"...","language_code":"en-IN","language_probability":1.0,"metrics":{"audio_duration":1.1,"processing_latency":1.1}}}`.
  The Phase 2a authenticated probe confirmed `language_code` and
  `language_probability` over WebSocket when `language-code=unknown`; both
  remain nullable and callers must handle `null`. For raw PCM16, the confirmed
  pairing is connection query `input_audio_codec=pcm_s16le` with per-message
  `encoding:"audio/wav"`; the apparently mismatched literals are required by
  the deployed socket.
  Saaras does not document interim/partial transcripts, so only final utterance
  transcripts are in scope.
- **TTS:** `wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v3&send_completion_event=true`.
  The first client message is `config` with `speaker`,
  `target_language_code`, `output_audio_codec: "linear16"`, and
  `speech_sample_rate: 24000`; text messages and `flush` follow. The server
  streams `{"type":"audio","data":{"content_type":"audio/pcm","audio":"<b64>"}}`.
  Bulbul v3 has no in-band cancel/clear message. Its documented idle timeout is
  about one minute, so the implementation uses per-turn sockets or a ping
  keepalive, and always replaces a socket after interruption.

---

## 3. Architecture

```
┌──────────────────────── Browser (React + Vite + TS) ────────────────────────┐
│  Mic (AudioWorklet, 16 kHz PCM16 mono)     Playback queue (Web Audio)       │
│  Todo store (localStorage) ⇄ tool executor  Auth/Wallet/Analytics pages     │
└───────────────┬───────────────────────────────────▲─────────────────────────┘
        binary PCM frames + JSON control       audio chunks + JSON events
                │        /ws/voice (JWT)            │
┌───────────────▼───────────────────────────────────┴─────────────────────────┐
│                        FastAPI backend (asyncio)                            │
│                                                                             │
│  VoiceSession orchestrator (one per call)                                   │
│   ├─ VadGate: Silero VAD → skip silence, pre-roll, endpointing, barge-in    │
│   ├─ SarvamSTT ws client   (speech frames only)                             │
│   ├─ AgentRunner: LangChain create_agent + Sarvam stream                     │
│   │    ├─ web_search  → Exa (server-side)                                   │
│   │    └─ todo_*      → proxied to browser, awaits result                   │
│   ├─ PhraseChunker → SarvamTTS ws client → audio chunks → client            │
│   └─ BillingMeter: per-second tick, debit wallet, cutoff at 0               │
│                                                                             │
│  REST: /auth (OTP, JWT) · /wallet (topup, balance, txns) · /analytics       │
│  SQLite (SQLAlchemy async): users, wallet_transactions, usage_sessions      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key design decisions

1. **Application-owned speech control is server-side.** The browser streams
   PCM continuously; the production VAD, endpointing, silence gating, and
   interruption policy run in FastAPI. Sarvam also ships server-side VAD,
   endpointing, and `START_SPEECH` / `END_SPEECH` signals. Phase 2a temporarily
   uses Sarvam's `END_SPEECH` signal to prove the minimal voice loop, then
   Phase 2b places local VAD in front of the vendor boundary. This deliberate
   local choice ensures silent audio never leaves our server, reduces vendor
   traffic and cost, gives exact local timing, and keeps behavior vendor
   independent. Sarvam's own VAD runs only after audio has crossed the vendor
   boundary, so it cannot satisfy FR-4's requirement that silence is never sent
   to Sarvam. The client remains a microphone, speaker, metric anchor, and tool
   executor.
2. **Client-side tools for todos.** Since todos live in `localStorage`
   (FR-3), the LLM's `todo_*` tool calls are forwarded to the browser as
   `tool_request` messages; the browser executes them against `localStorage`
   and replies with `tool_result`. The server never stores todo data.
3. **Barge-in is VAD-driven and replaces the TTS socket.** While the agent is
   speaking, the same local VAD watches the incoming mic stream. On sustained
   speech onset the server cancels the LLM, emits `interrupt`, and stops
   accepting audio from the current Bulbul stream. The browser immediately
   clears playback and replies with `interrupt_ack`. Because Bulbul has no
   in-band cancel/clear operation, the server closes and discards that TTS
   socket, opens a fresh socket for the next response, truncates assistant
   history to audio actually played, and begins the new user turn. The client
   acknowledgement measures queue-flush control latency, not physical acoustic
   silence. Non-interrupted sockets are either scoped per turn or kept alive
   with pings before the documented approximately one-minute idle timeout.
4. **Per-second proration of a per-minute price.** `PRICE_PER_MINUTE`
   (default ₹2.00) is prorated per connected second; stored as integer
   **paise** to avoid float money errors.
5. **Multilingual by detection.** Saaras is
   connected with `language-code=unknown`. The agent replies in the detected
   language and TTS follows it. Phase 2a confirmed `language_code` and
   `language_probability` in the raw WebSocket response; both fields remain
   nullable and must be handled as optional values.
6. **VAD implementation is pluggable.** `SileroOnnxVad` (preferred) with an
   `EnergyVad` fallback behind the same interface, so the pipeline runs on any
   machine and the gate logic is unit-testable with fake VADs.
7. **Transport: WebSocket + raw PCM, not WebRTC (deliberate).** WebRTC was
   evaluated and deferred. Rationale: (a) the backend is Python/asyncio and
   server-side WebRTC there means `aiortc`, which adds SDP/ICE/DTLS complexity
   and a second event model for no demo-scale benefit; (b) WebRTC's advantages
   - jitter buffering, FEC/packet-loss concealment, NAT traversal - matter on
   lossy public networks at scale, not for a controlled demo; (c) owning raw
   PCM frames end-to-end makes FR-10 instrumentation exact, since we timestamp
   every frame at every hop; (d) browser echo cancellation and noise
   suppression come from `getUserMedia` constraints, not from WebRTC transport.
   **Upgrade path** (documented, not built): swap the transport layer behind
   the same `VoiceSession` interface for LiveKit/WebRTC when moving to
   telephony or unreliable networks. Opus compression is the intermediate
   optimization if PCM bandwidth (~256 kbps upstream) ever matters.
8. **Turn detection: local silence endpointing after the minimal slice.**
   Sarvam's built-in end-of-speech signal is used only in Phase 2a. Phase 2b
   replaces it with the local VAD trailing-silence window
   (`VAD_END_SILENCE_MS`, initial default 500 ms). The production value is
   selected from multilingual replay data, balancing latency against false
   endpoints and false continuations. Mid-sentence pauses can still trigger
   premature endpoints. Barge-in makes them recoverable, and the turn-detector
   interface remains pluggable for a future semantic or hybrid model. Saaras
   partial transcripts are not documented, so no current design depends on
   them. The tradeoff is discussed in `docs/voice-metrics.md`.
9. **AgentRunner uses LangChain's sandwich-agent pattern.** `ChatOpenAI` points
   at Sarvam's OpenAI-compatible base URL, and LangChain's LangGraph-backed
   `create_agent` owns the model/tool loop. An `InMemorySaver` maintains the
   per-call message state under one call-scoped `thread_id`. `web_search` and
   `todo_*` are LangChain tools; `web_search` executes in FastAPI, while a
   `todo_*` tool suspends on a call-ID future, emits `tool_request` over the
   application WebSocket, and resumes when the browser returns `tool_result`.
   On barge-in, AgentRunner cancels the active graph/model stream and reconciles
   the checkpointed assistant message to only what playback confirms was
   spoken.

### Client ↔ server WebSocket protocol (`/ws/voice?token=<jwt>`)

Upstream binary messages contain a small versioned timing header
(`capture_seq`, browser `capture_time_ms`) followed by 16 kHz mono PCM16 mic
samples. The timing marker lets the server echo the last-speech anchor back to
the browser without attempting to compare browser and server clocks.

| Direction | JSON message | Purpose |
|---|---|---|
| S→C | `{"type":"ready", session_id, balance_paise, price_per_minute_paise, tts_sample_rate_hz:24000}` | Call accepted, billing started; declares downstream PCM rate |
| S→C | `{"type":"final_transcript", text, language_code?, language_probability?}` | Final utterance caption; both confirmed Saaras WebSocket language fields are nullable |
| S→C | `{"type":"agent_text", text}` | Agent reply text (per sentence) |
| S→C | `{"type":"audio_start", turn_id, last_speech_capture_seq, last_speech_capture_time_ms}` | Echoes the browser-clock speech-end marker before the first audio chunk |
| S→C | `{"type":"response_cue", turn_id, cue_id, cue_key, language_code, delay_ms}` | Requests one cached, non-semantic feedback cue for the active thinking turn |
| S→C | `{"type":"response_cue_cancel", turn_id, cue_id, reason}` | Stops a pending/playing cue without touching the answer playback queue |
| S→C | binary frame | TTS audio chunk (PCM16 at the rate declared by `ready`, initially 24 kHz) |
| S→C | `{"type":"agent_state", state: listening|thinking|speaking}` | UI indicator; listening is driven by VAD signals/state, not partial text |
| S→C | `{"type":"interrupt", turn_id}` | Flush playback queue immediately |
| C→S | `{"type":"interrupt_ack", turn_id, interrupt_received_perf_ms, queue_cleared_perf_ms, audio_queue_cleared:true}` | Confirms local queue clear; ack proxy for barge-in control latency |
| S→C | `{"type":"tool_request", call_id, name, arguments}` | Execute todo tool in browser |
| C→S | `{"type":"tool_result", call_id, result}` | Tool output back to agent |
| S→C | `{"type":"billing", seconds, cost_paise, balance_paise}` | Periodic meter update |
| S→C | `{"type":"call_ended", reason: user|balance_exhausted|error}` | Terminal |
| C→S | `{"type":"playback_started", turn_id, last_speech_capture_seq, audio_received_perf_ms, decode_complete_perf_ms?, scheduled_perf_ms, playback_start_perf_ms, e2e_voice_to_voice_ms}` | Web Audio playback started; all client spans and end-to-end use the browser clock (§3a) |
| C→S | `{"type":"response_cue_started", turn_id, cue_id, cue_start_perf_ms, feedback_voice_to_voice_ms}` | Confirms actual cached-cue playback start in the browser clock |
| C→S | `{"type":"playback_finished", turn_id, playback_end_perf_ms, played_audio_ms}` | Records actual scheduled playback extent for history truncation |
| S→C | `{"type":"turn_metrics", turn_id, stages:{...}}` | Per-turn latency waterfall for the dev HUD (when `METRICS_HUD`) |
| C→S | `{"type":"end_call"}` | User hangs up |

---

## 3a. Latency Instrumentation & Metrics (FR-10)

Every conversational turn gets a `TurnTimer` record. It stores timestamps and
spans rather than relying only on precomputed durations, because pipelined
stages can overlap. `TurnTimer` wraps the LangChain agent invocation and its
stream callbacks/events to capture LLM request start, first visible token,
first speakable chunk, completion/cancellation, and every tool-call span. The
Phase 2a protocol spike must prove these boundaries through `create_agent`.
`ChatOpenAI` does not guarantee preservation of provider-specific response
fields such as Sarvam's `reasoning_content`; voice turns disable reasoning, but
if any required timestamp cannot be observed through LangChain events,
callbacks, or a thin model wrapper, implementation stops and the gap is raised
for review rather than silently omitting the metric.

### Clock domains and the end-to-end anchor

There are two unrelated monotonic clocks:

- **Browser clock:** `performance.now()` and AudioWorklet/Web Audio timing.
  Upstream binary audio messages carry a `capture_seq` and browser
  `capture_time_ms`. When local VAD identifies the last speech frame, the
  backend retains that frame's browser marker and echoes it in `audio_start`.
  The browser computes `e2e_voice_to_voice_ms` as its local playback-start
  time minus the echoed local capture time.
- **Server clock:** Python's monotonic clock for FastAPI, VAD, STT, LLM, TTS,
  tool, connection, send, retry, and acknowledgement spans.

Raw browser and server monotonic timestamps are never subtracted. Cross-hop
latency is either computed within the browser clock using echoed markers or
reported as separate server and client submetrics.

### Turn timestamps

| Timestamp | Clock | Captured where | Meaning |
|---|---|---|---|
| `t_audio_frame_client_capture` + `capture_seq` | Browser | AudioWorklet | Capture time and sequence for every upstream PCM frame |
| `t_audio_frame_server_receive` | Server | VoiceSession | Frame arrival, used to observe upstream buffering separately |
| `t_speech_start_server` | Server | VadGate | First frame classified as speech; opens the turn |
| `t_last_speech_frame_server` | Server | VadGate | Server time of the last frame classified as speech |
| `last_speech_capture_time_ms` + `last_speech_capture_seq` | Browser marker echoed by server | VadGate / protocol | Same frame's original browser capture anchor |
| `t_endpoint_decision` | Server | VadGate | Turn detector commits end of turn after trailing silence |
| `t_stt_flush_sent` | Server | STT client | Manual flush sent to Saaras |
| `t_stt_final` | Server | STT client | Final transcript received |
| `t_llm_request_start` | Server | LLM client | Chat-completion request starts |
| `t_llm_first_reasoning_token` | Server | LLM client | First `delta.reasoning_content`, if any; normally absent because voice turns set `reasoning_effort:null` |
| `t_llm_first_visible_token` | Server | LLM client | First user-visible `delta.content` |
| `t_llm_first_speakable_chunk` | Server | SentenceChunker | First TTS-eligible text chunk, which may be a complete sentence or policy-approved shorter chunk |
| `t_llm_complete` | Server | LLM client | LLM stream completed or was cancelled |
| `t_tts_connection_acquire_start` / `end` | Server | TTS client | Socket acquisition; includes reused/cold/replaced dimension |
| `t_tts_text_submitted` | Server | TTS client | First speakable text submitted to Bulbul |
| `t_tts_first_chunk` | Server | TTS client | First audio bytes received |
| `t_tts_complete` | Server | TTS client | Final TTS event received or stream cancelled |
| `t_audio_sent_server` | Server | VoiceSession | First TTS chunk written to the application WebSocket |
| `t_client_audio_received` | Browser | WS handler | First downstream audio chunk received |
| `t_client_decode_complete` | Browser | Playback queue | Decode/conversion complete, when applicable |
| `t_client_audio_scheduled` | Browser | Web Audio | First audio source scheduled |
| `t_client_playback_start` | Browser | Web Audio | First sample begins scheduled rendering; practical proxy for audible start |
| `t_client_playback_end` | Browser | Web Audio | Last played sample, used for history truncation |
| `t_response_cue_sent_server` | Server | VoiceSession | Optional cached-cue dispatch for an eligible thinking turn |
| `t_client_response_cue_start` | Browser | Feedback audio player | Optional actual cue playback start; never substituted for answer playback start |
| Tool-call start/end spans | Server or browser, kept in their own clock | AgentRunner/tool executor | Each server-side Exa or client-side todo call, including timeout/error |
| `t_barge_speech_onset_server` | Server | VadGate | First frame of the sustained barge-in candidate |
| `t_barge_speech_detected_server` | Server | VadGate | Sustained barge-in speech recognized |
| `t_interrupt_sent_server` | Server | VoiceSession | `interrupt` control message sent |
| `t_interrupt_received_client` | Browser | WS handler | Client receives interruption |
| `t_playback_queue_cleared_client` | Browser | Playback queue | Local queue and scheduled sources cleared |
| `t_interrupt_ack_received_server` | Server | VoiceSession | `interrupt_ack` received |

`t_client_playback_start` means scheduled Web Audio rendering, not receipt or
enqueue. Browser and hardware output buffering beyond that point is not exactly
observable without acoustic loopback capture.

### Derived metrics

- `upstream_audio_transport_ms`: browser capture to server receipt only when a
  valid same-clock/synchronized calculation is available; otherwise store the
  two submetrics without subtracting them.
- `endpoint_decision_ms = t_endpoint_decision - t_last_speech_frame_server`.
- `stt_flush_to_final_ms = t_stt_final - t_stt_flush_sent`.
- `stt_eot_ms = t_stt_final - t_last_speech_frame_server`.
- `orchestrator_queue_ms`: final transcript/turn commit to LLM request start.
- `llm_visible_ttft_ms = t_llm_first_visible_token - t_llm_request_start`.
- `llm_first_speakable_ms = t_llm_first_speakable_chunk - t_llm_request_start`.
- `tts_ttfb_ms = t_tts_first_chunk - t_tts_text_submitted`.
- `downstream_to_playback_ms`: first audio receive to playback start in the
  browser clock, with server-send time reported separately.
- `e2e_voice_to_voice_ms = t_client_playback_start - last_speech_capture_time_ms`
  in the browser clock. This includes endpointing and is the UX metric.
- `feedback_voice_to_voice_ms = t_client_response_cue_start - last_speech_capture_time_ms`
  in the browser clock. This is perceived feedback onset, not answer latency.
- `answer_after_feedback_ms = t_client_playback_start - t_client_response_cue_start`
  in the browser clock, when both events exist.
- `response_cue_dispatch_ms = t_response_cue_sent_server - t_stt_final` in the
  server clock. Cue timestamps are optional and never censor a non-cued turn.
- `barge_detection_ms = t_barge_speech_detected_server - t_barge_speech_onset_server`.
- `barge_client_flush_ms = t_playback_queue_cleared_client - t_interrupt_received_client`.
- `barge_in_stop_ack_ms`: server detection to acknowledgement receipt. The
  existing user-facing name `barge_in_stop_ms` aliases this value but must be
  labeled an acknowledgement proxy, not proof of acoustic silence.
- `audio_queue_depth_ms_at_first_playback`, `realtime_factor`,
  `interrupted_audio_generated_ms`, and `interrupted_audio_played_ms`.
- Turn-quality outcomes: `turn_false_endpoint` when the user resumes within the
  annotated recovery window, and `turn_false_continuation` when a completed
  turn waits beyond the annotated maximum desired delay.

**Storage & reporting**
- Per-turn rows in `turn_metrics` link to `usage_sessions` and preserve the
  timestamps, derived metrics, tool spans, and data-quality fields needed to
  recompute distributions. Structured JSON logs use the same turn ID.
- Dimensions include model IDs and explicit parameters; language and detection
  confidence when available; audio codec/rate/frame size/input duration;
  provider and application regions; connection reuse/cold start/replacement,
  retries, close reason, and request IDs; tool name/use; interruption, timeout,
  error, or balance-cutoff outcome; missing/censored timestamps; software
  version, configuration hash, and replay corpus ID.
- Missing timestamps are never coerced to zero. Exclusions require a named
  reason and the analytics response reports exclusion counts.
- Analytics endpoint reports p50/p95/p99 per stage over a window; p99 is the
  headline (conversational UX is judged by the worst turns, not the average).
- p99 is not quoted from fewer than 100 valid turns, and every percentile is
  accompanied by its sample count. Precomputed daily percentiles are not
  averaged; raw rows or mergeable histogram buckets are aggregated. A numeric
  p99 acceptance target is set only after the Phase 2 real-time replay baseline
  establishes the achievable distribution.
- Dev-mode latency HUD in the call screen: per-turn stage waterfall from the
  server's `{"type":"turn_metrics", ...}` event after each turn.
- A percentile helper is pure logic (unit-tested); no external metrics stack
  (Prometheus etc.) - out of scope for the assignment, noted as the
  production path.

---

## 4. Repository Layout

```
Sarvam_Project/
├── requirement.md              ← this file
├── README.md                   ← run instructions
├── docs/
│   ├── sarvam-api-research.md  # Phase 0: verified Sarvam API surface
│   ├── voice-metrics.md        # Phase 0: latency benchmarks & metric definitions
│   └── architecture.md         # Phase 0: standalone reviewed system design
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── app/
│   │   ├── main.py             # app factory, routers, lifespan
│   │   ├── config.py           # pydantic-settings (all tunables)
│   │   ├── db.py               # async engine/session
│   │   ├── models.py           # ORM: User, OtpChallenge, WalletTransaction, UsageSession
│   │   ├── auth/               # router, service (OTP+JWT), email (Resend)
│   │   ├── wallet/             # router, service (billing), analytics
│   │   └── voice/
│   │       ├── router.py       # /ws/voice endpoint
│   │       ├── session.py      # VoiceSession orchestrator
│   │       ├── vad.py          # Silero ONNX + Energy VAD implementations
│   │       ├── gate.py         # VadGate state machine (pure logic)
│   │       ├── stt.py          # Sarvam STT WS client
│   │       ├── llm.py          # sarvam-105b streaming chat client
│   │       ├── tts.py          # Bulbul TTS WS client
│   │       ├── agent.py        # LangChain create_agent, per-call memory, stream instrumentation
│   │       ├── tools.py        # tool registry, Exa search, todo tool defs
│   │       ├── chunker.py      # sentence chunker (pure logic)
│   │       ├── metrics.py      # TurnTimer, percentile math (pure logic)
│   │       ├── languages.py    # language_code → TTS speaker map
│   │       └── protocol.py     # client/server message schema
│   └── tests/                  # pytest suite (unit; no network)
└── frontend/
    ├── package.json
    └── src/
        ├── api/                # REST client, auth token handling
        ├── audio/              # worklet capture, playback queue
        ├── voice/              # useVoiceSession hook (WS protocol)
        ├── store/              # todos (localStorage), auth
        ├── pages/              # Login, Call, Wallet, Analytics
        └── components/
```

---

## 5. Data Model (SQLite)

- **users** - id, email (unique), created_at, is_verified
- **otp_challenges** - id, email, code_hash, expires_at, attempts, consumed
- **wallet_transactions** - id, user_id, amount_paise (+credit/−debit), kind
  (`topup` | `usage`), usage_session_id?, created_at.
  Balance = `SUM(amount_paise)` (ledger style - auditable, no drift).
- **usage_sessions** - id, user_id, started_at, ended_at?, billed_seconds,
  cost_paise, end_reason. One row per voice call; debit rows reference it.
- **turn_metrics** - one row per turn with id, usage_session_id, turn_index;
  browser speech anchor sequence/time; server endpoint, STT, LLM, TTS, audio
  send, and interruption timestamps; client receive/decode/schedule/playback
  durations; and the derived metrics from §3a (`endpoint_decision_ms`,
  `stt_flush_to_final_ms`, `stt_eot_ms`, `orchestrator_queue_ms`,
  `llm_visible_ttft_ms`, `llm_first_speakable_ms`, `tts_ttfb_ms`,
  `downstream_to_playback_ms`, `e2e_voice_to_voice_ms`,
  `barge_detection_ms`, `barge_client_flush_ms`, `barge_in_stop_ack_ms`,
  queue depth, realtime factor, and interrupted audio generated/played).
  Outcome fields include interrupted, false endpoint, false continuation,
  timeout/error/censored state, and exclusion reason. Dimension fields include
  model IDs/parameters, language/detection confidence, audio format, regions,
  connection lifecycle/retries/close reason/request IDs, tools, software and
  config versions, and replay corpus ID. Tool spans and extensible dimensions
  may be stored as structured JSON alongside indexed headline columns.

Analytics are computed by aggregating `usage_sessions` over time windows
(last 60 min, last 24 h, last 7 days with per-day buckets).

---

## 6. Implementation Phases

Each phase is independently runnable/testable; later phases don't rewrite earlier ones.

- **Phase 0 - Research & scaffold:** produce `docs/sarvam-api-research.md`
  (verify the API contracts in §2 against live Sarvam docs; correct this file
  if they differ) and `docs/voice-metrics.md` (latency decomposition,
  industry percentile benchmarks, metric definitions backing §3a), reconcile
  this requirements file, and produce the standalone reviewed design in
  `docs/architecture.md`. Repo layout, tooling. ✅ exit: all three docs and the
  reconciled requirements are reviewed and approved. No application code
  before this gate.
- **Phase 1 - Backend foundation:** config, DB models/migrations-by-create,
  auth (OTP request/verify, JWT), `/auth/me`. ✅ exit: login flow works via curl.
- **Phase 2a - Minimal voice loop:** browser microphone → application WS →
  Saaras STT → `sarvam-105b` with `reasoning_effort:null` → Bulbul TTS →
  browser playback. No local VAD, tools, or barge-in. Endpointing may
  temporarily use Sarvam's built-in `END_SPEECH` signal. Run the authenticated
  raw-protocol probe, which confirmed nullable STT language fields, the
  `pcm_s16le` plus `audio/wav` raw-PCM pairing, and TTS text/flush shapes.
  Instantiate `ChatOpenAI` against Sarvam and invoke it
  through `create_agent` with a call-scoped `thread_id` and `InMemorySaver`;
  prove token/event/callback visibility needed by `TurnTimer` before Phase 2b.
  ✅ exit: one complete English voice turn and raw vendor messages captured.
- **Phase 2b - Backend VAD gating and metrics:** place pluggable Silero ONNX
  VAD in front of Sarvam, drop all silent frames before the vendor boundary,
  add pre-roll, and replace temporary Sarvam endpointing with the local 500 ms
  trailing-silence policy. Wire `TurnTimer`, browser capture anchors, all stage
  timestamps, persistence, and the latency waterfall in this slice.
  ✅ exit: silence produces no Sarvam audio traffic; measured full turns are
  visible in logs/HUD.
- **Phase 2c - Barge-in:** detect sustained speech during playback, cancel the
  LLM, emit `interrupt`, receive `interrupt_ack`, close/discard the current
  Bulbul socket, create a fresh one for the next response, discard stale audio,
  and truncate assistant history to audio actually played.
  ✅ exit: interruption clears playback and reports the acknowledgement proxy.
- **Phase 2d - Perceived-latency v1:** replace sentence-only release with
  phrase-aware chunking; add cached, non-semantic response cues with deterministic
  timing, independent playback, answer/new-speech cancellation, and separate
  feedback/answer metrics; cancel active responses while still thinking.
  ✅ exit: cues never delay answer audio, stale turn output is rejected, and a
  no-tool multilingual replay reports feedback and answer latency separately.
- **Phase 3 - Agent tools:** implement Exa `web_search` first as a LangChain
  tool, then add the client-proxied `todo_*` LangChain tools and their
  `tool_request` / `tool_result` await loop.
  ✅ exit: "search the web for X" works before "add milk to my todo list".
- **Phase 4 - Wallet & analytics:** top-up/balance/transactions, per-second
  billing meter wired into VoiceSession, cutoff, analytics endpoints.
- **Phase 5 - Frontend (kept simple, per scope emphasis):** login/OTP, call
  screen (worklet capture, playback queue + instant flush, final captions, state
  indicator), todo panel, wallet, analytics charts. Plain functional UI; the
  only components that warrant care are the audio worklet capture and the
  playback queue, because FR-7's <250 ms flush depends on them.
- **Phase 6 - Tests & hardening:** full unit suite green, latency replay
  harness (below), README with a measured-latency table, `.env.example`.

---

## 7. Test Plan

Principle: **pure logic gets unit tests; I/O boundaries get thin, mockable
clients.** The automated unit/integration suite never talks to a real network;
the explicitly invoked latency replay harness is the only real-key exception.

### Backend (pytest + pytest-asyncio, httpx ASGI client)

| Area | Tests |
|---|---|
| `gate.py` VadGate | silence never forwarded; pre-roll included on speech onset; endpoint fires after trailing-silence window; barge-in fires only on sustained speech while agent speaking; counters reset per turn |
| Billing | per-second proration math (paise, rounding), ledger balance, cutoff when balance hits 0, session finalization writes usage row + debit |
| Analytics | window aggregation (hour/day/week), per-day bucketing, empty windows |
| Auth | OTP issue/verify happy path, wrong code, expiry, attempt limit, JWT round-trip, `/auth/me` |
| Chunker | sentence and safe clause splitting incl. Indic punctuation; provider-safe first-chunk cap; fragmented pushes; min-length buffering; deterministic flush/remainder |
| Response cue | one cue per eligible turn; cooldown; language fallback; answer/new-speech cancellation; stale IDs and missing assets fail silent; feedback and answer clocks remain separate |
| AgentRunner/tools | `create_agent` with fake chat model + `InMemorySaver`; call-scoped thread history; streamed visible-token and speakable-chunk hooks; tool spans; Exa client (mocked httpx); todo proxy await/timeout; cancellation and checkpoint truncation |
| Wallet API | topup validation (positive amounts), balance, transaction listing |
| `metrics.py` TurnTimer | stage ordering enforced, derived latencies computed correctly, interrupted turns marked, missing client ack handled |
| Percentiles | p50/p95/p99 math against known distributions, small-n and empty windows |

### Latency replay harness (semi-automated, real Sarvam key)

A script (`backend/scripts/latency_replay.py`) replays recorded WAV utterances
at real-time speed through the real application WS endpoint. The corpus covers
English plus at least two Indic languages, short questions, hesitation,
number/list dictation, code-mixing, and representative noise. It separates warm
and cold connection cohorts and records false-endpoint, false-continuation,
interruption-detection, and STT-quality outcomes alongside latency.

N≥20 valid turns is a smoke test only. No p99 is quoted until a cohort has at
least 100 valid turns; release claims use substantially more traffic and always
report sample count, failures, exclusions, model/configuration, region, date,
and corpus ID. The harness preserves raw per-turn rows, prints p50/p95/p99 only
when statistically eligible, and evaluates the §1 hypotheses rather than
assuming the budgets are already proven.

### Frontend (vitest)

- Todo store: CRUD against a mocked `localStorage`, tool-call executor mapping
  (`todo_add`/`todo_list`/`todo_complete`/`todo_delete`).
- Playback queue: enqueues chunks, `flush()` empties instantly, emits
  `interrupt_ack`, and reports receive/decode/schedule/playback timestamps.

### Manual/integration checklist (needs real keys)

1. OTP email arrives; wrong/expired codes rejected.
2. Voice loop in English and ≥2 Indic languages; replies in the spoken language.
3. Speak over the agent: playback flushes immediately, the old Bulbul socket is
   closed/discarded, a fresh socket is used for the next turn, and the
   acknowledgement proxy is <250 ms p95. Acoustic stop is observed separately.
4. Silent mic for 30 s → no STT traffic (verify via logs), no transcripts.
5. Wallet: top-up, live meter during call, call auto-ends at ₹0, analytics reflect usage.

---

## 8. Configuration (backend `.env`)

```
SARVAM_API_KEY=
SARVAM_CHAT_BASE_URL=https://api.sarvam.ai/v1
EXA_API_KEY=
RESEND_API_KEY=
RESEND_FROM="Voice Agent <onboarding@resend.dev>"
JWT_SECRET=<generate: openssl rand -hex 32>
DATABASE_URL=sqlite+aiosqlite:///./voiceagent.db
PRICE_PER_MINUTE_PAISE=200          # ₹2/min, prorated per second
LOW_BALANCE_WARN_PAISE=100
OTP_TTL_SECONDS=600
OTP_MAX_ATTEMPTS=5
VAD_END_SILENCE_MS=500              # initial hypothesis; finalize from replay data
VAD_BARGE_IN_MS=200                 # sustained speech to trigger interrupt
METRICS_HUD=true                    # emit per-turn turn_metrics events to client
LLM_MODEL=sarvam-105b
LLM_REASONING_EFFORT=                # empty/null for voice turns; avoids reasoning TTFT
STT_MODEL=saaras:v3
TTS_MODEL=bulbul:v3
TTS_SAMPLE_RATE_HZ=24000             # explicit Bulbul v3 PCM output rate
```
