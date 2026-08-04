# Sarvam API research

Research date: 2026-07-12

Scope: live Sarvam documentation for the three contracts asserted in `requirement.md` section 2. This is documentation research only. No authenticated API calls were made, so runtime-only behavior is marked `UNVERIFIED`.

## Required edits to `requirement.md`

These are the exact edits recommended before Phase 1. They are listed first because the current contract has implementation-breaking discrepancies.

1. Replace the STT URL with a contract that includes automatic language detection and explicitly enables manual flush:

   ```text
   wss://api.sarvam.ai/speech-to-text/ws?model=saaras:v3&mode=transcribe&language-code=unknown&sample_rate=16000&input_audio_codec=pcm_s16le&flush_signal=true
   ```

   The raw endpoint reference spells the query parameter `language-code`, while the SDK guide spells its Python argument `language_code`. The current endpoint reference marks the language parameter required, although the Saaras model page says omission or `unknown` enables detection. Use `unknown` explicitly until a live handshake test proves omission works. The current docs also require `input_audio_codec` for raw PCM despite a changelog entry saying it had been removed, so keep it for raw PCM. Sources: [STT WebSocket reference](https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe/ws?explorer=true), [streaming STT guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/streaming-api), [Saaras model page](https://docs.sarvam.ai/api-reference-docs/getting-started/models/saaras), [changelog](https://docs.sarvam.ai/api-reference-docs/changelog).

2. Do not promise native partial transcripts or wire `partial_transcript` UI events directly to Saaras. The streaming docs describe one final transcript per utterance, triggered by VAD end-of-speech or `flush()`, and do not document interim transcript revisions. Mark partial STT captions out of scope unless an authenticated probe confirms an undocumented interim event. Source: [STT API selection guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/which-api-to-use).

3. Change the STT response contract from an open-ended `{"type":"data","data":{"transcript","language_code",...}}` assertion to the documented WebSocket minimum:

   ```json
   {
     "type": "data",
     "data": {
       "request_id": "...",
       "transcript": "...",
       "metrics": {
         "audio_duration": 1.1,
         "processing_latency": 1.1
       }
     }
   }
   ```

   The WebSocket example does not show `language_code`. REST documents `language_code` and `language_probability`, but carrying them over to WebSocket is `UNVERIFIED`. Source: [STT WebSocket reference](https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe/ws?explorer=true).

4. Change downstream audio assumptions from "PCM16 22.05 kHz" to a configured value. Bulbul v3 defaults to 24 kHz. For the proposed browser pipeline, explicitly request PCM at 16 kHz or 24 kHz in the TTS config and make the client protocol carry or negotiate the sample rate. Do not silently assume 22.05 kHz. Sources: [Bulbul model page](https://docs.sarvam.ai/api-reference-docs/getting-started/models/bulbul), [TTS sample-rate guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/how-to/set-the-sample-rate).

5. Amend barge-in behavior: Bulbul's TTS socket has no `cancel` or `clear` message. On interruption, stop browser playback immediately, close the current TTS socket, discard in-flight audio, and open a fresh socket for the next response. A long-lived single TTS connection cannot safely serve an interrupted utterance followed by the next utterance. Source: [TTS WebSocket guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/streaming-api/web-socket).

6. Amend the chat latency plan. `sarvam-105b` is supported, but Sarvam describes `sarvam-30b` as the lower-latency model suited to voice agents, while `sarvam-105b` prioritizes quality and has higher time to first token. Keep `sarvam-105b` only as an explicit quality choice, and disable reasoning for short voice replies with `reasoning_effort: null`; otherwise reasoning tokens stream before visible content and increase latency. Source: [chat overview](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/chat-completion/overview).

7. Correct the "Gaps" claim. Sarvam now ships STT-side VAD, server endpointing, `START_SPEECH` / `END_SPEECH` signals, and fine VAD controls. The project may still use its own backend VAD for silence gating, deterministic timing, and vendor independence, but it is no longer accurate to say Sarvam provides none of these capabilities. Sarvam does not provide the application's full barge-in action, browser playback flush, or browser-to-backend transport. Source: [streaming STT guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/streaming-api).

## Verification summary

| Requirement assertion | Verdict | Current documented contract |
|---|---|---|
| Saaras v3 streaming STT over WSS | Confirmed with corrections | `GET wss://api.sarvam.ai/speech-to-text/ws`; `model=saaras:v3`; five modes; raw PCM and WAV streaming; `Api-Subscription-Key` header. Add explicit language selection, `flush_signal=true`, and raw PCM codec. |
| Sarvam-105B OpenAI-compatible streaming chat | Confirmed | `POST /v1/chat/completions`; SSE with `stream:true`; OpenAI-style chunks and function tools. Reasoning is enabled by default and affects visible TTFT. |
| Bulbul v3 streaming TTS over WSS | Confirmed with corrections | `GET wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v3`; config first, then text and flush; default output rate 24 kHz; no in-band cancel or clear. |
| Exact STT message shapes in section 2 | Partly confirmed | Audio and flush shapes are documented. The example WebSocket response does not document `language_code`. No interim transcript message is documented. |
| Exact TTS message shapes in section 2 | Partly confirmed | Config and audio result shapes are documented. The live guide exposes the message categories but not all raw text/flush JSON examples in its rendered contract, so those exact raw shapes remain `UNVERIFIED`. |

## Authentication

Sarvam authenticates all endpoints with an API subscription key. The preferred header is:

```http
api-subscription-key: YOUR_SARVAM_API_KEY
```

The same key is also accepted as `Authorization: Bearer YOUR_SARVAM_API_KEY`, chiefly for OpenAI-compatible clients. WebSocket endpoint references spell the header `Api-Subscription-Key`; HTTP header names are case-insensitive. Authentication failures are documented as HTTP 403 rather than 401. Source: [authentication](https://docs.sarvam.ai/api-reference-docs/authentication).

The backend must hold the key. It must not be sent to browser code.

## Saaras v3 streaming speech-to-text

### Connection

Documented endpoint:

```text
wss://api.sarvam.ai/speech-to-text/ws
```

Relevant query parameters are:

- `model=saaras:v3`, currently the default and recommended model.
- `mode=transcribe|translate|verbatim|translit|codemix`.
- `language-code=<BCP-47 code>` in the raw endpoint reference. Use `unknown` for automatic detection.
- `sample_rate=16000|8000`, default 16000.
- `input_audio_codec=wav|pcm_s16le|pcm_l16|pcm_raw` for streaming formats.
- `flush_signal=true|false` to enable manual finalization.
- `vad_signals=true|false` to receive speech-boundary events.
- Optional server VAD controls, discussed under Gaps.

The endpoint reference and model page disagree about whether the language parameter is required. The safest raw WebSocket contract is to send `language-code=unknown` explicitly. Sources: [STT WebSocket reference](https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe/ws?explorer=true), [Saaras model page](https://docs.sarvam.ai/api-reference-docs/getting-started/models/saaras).

### Supported languages

Saaras v3 documents 23 languages, automatic language detection, dialect/accent support, and code-mixed audio:

| Language | Code | Language | Code |
|---|---|---|---|
| Hindi | `hi-IN` | Assamese | `as-IN` |
| Bengali | `bn-IN` | Urdu | `ur-IN` |
| Kannada | `kn-IN` | Nepali | `ne-IN` |
| Malayalam | `ml-IN` | Konkani | `kok-IN` |
| Marathi | `mr-IN` | Kashmiri | `ks-IN` |
| Odia | `od-IN` | Sindhi | `sd-IN` |
| Punjabi | `pa-IN` | Sanskrit | `sa-IN` |
| Tamil | `ta-IN` | Santali | `sat-IN` |
| Telugu | `te-IN` | Manipuri | `mni-IN` |
| English | `en-IN` | Bodo | `brx-IN` |
| Gujarati | `gu-IN` | Maithili | `mai-IN` |
| | | Dogri | `doi-IN` |

Source: [Saaras model page](https://docs.sarvam.ai/api-reference-docs/getting-started/models/saaras).

### Send and receive messages

The documented audio message matches section 2:

```json
{
  "audio": {
    "data": "<base64 audio>",
    "sample_rate": "16000",
    "encoding": "audio/wav"
  }
}
```

For raw PCM, use the matching codec/encoding and ensure the connection and message sample rates agree. The SDK guide says a mismatch produces poor transcription or errors. Source: [streaming STT guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/streaming-api).

Manual finalization is:

```json
{"type":"flush"}
```

The documented transcription example is:

```json
{
  "type": "data",
  "data": {
    "request_id": "request_id",
    "transcript": "transcript",
    "metrics": {
      "audio_duration": 1.1,
      "processing_latency": 1.1
    }
  }
}
```

Source: [STT WebSocket reference](https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe/ws?explorer=true).

`language_code` and `language_probability` are documented for the REST response and model-level response format. They are not present in the WebSocket response example. Their presence on WebSocket `data` messages is `UNVERIFIED`. Source for the REST-only fields: [STT REST reference](https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe).

### Partial transcripts

No interim or partial transcript message is documented for Saaras v3 streaming. Sarvam describes WebSocket results as a final transcript per utterance, delivered on its VAD end-of-speech or `flush()`. The streaming response types list speech start, speech end, and final transcript, not transcript revisions. Therefore:

- Partial transcripts: `UNVERIFIED` and must not be assumed.
- Final utterance transcript: confirmed.
- VAD boundary events: confirmed when `vad_signals=true`.

Sources: [STT API selection guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/which-api-to-use), [streaming STT guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/streaming-api).

### Documented latency

Sarvam uses qualitative language such as "milliseconds" and "near-instantaneous" for streaming STT. It returns `metrics.processing_latency` in the example WebSocket payload, but the docs do not define its clock boundaries or publish a p50, p95, or p99 target. Any specific Saaras latency budget is `UNVERIFIED` until measured with a real key and representative audio. Sources: [streaming STT guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/streaming-api), [STT WebSocket reference](https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe/ws?explorer=true).

## Sarvam-105B chat completions

### Endpoint, streaming, and tools

The section 2 endpoint is correct:

```http
POST https://api.sarvam.ai/v1/chat/completions
```

`model: "sarvam-105b"` is supported, the format is documented as OpenAI-compatible, and `stream: true` returns server-sent events. Each event is a `data:` line containing a `chat.completion.chunk`; visible text arrives at `choices[0].delta.content`; reasoning arrives separately at `delta.reasoning_content`; the final usage event has an empty `choices` array; the stream terminates with `data: [DONE]`. Source: [chat overview](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/chat-completion/overview).

Function tools are documented with OpenAI-style shapes:

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "...",
    "parameters": {"type": "object", "properties": {}}
  }
}
```

A requested call uses `finish_reason: "tool_calls"` and `message.tool_calls[].function.arguments` as a JSON string. The application executes it, appends the assistant tool-call message plus `{"role":"tool","tool_call_id":"...","content":"..."}`, then calls chat completions again. `tool_choice` supports `auto`, `none`, `required`, and a forced function. Source: [chat overview](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/chat-completion/overview).

### Supported languages

Sarvam-105B documents the same 11-language set as Bulbul v3, with native-script, romanized, and code-mixed input: Hindi, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Marathi, Punjabi, Odia, and English. Source: [models language overview](https://docs.sarvam.ai/api-reference-docs/getting-started/models).

### Limits and latency implications

- Context window: 128K tokens.
- `max_tokens`: Starter 4096, Pro 16384, Business 128000.
- Reasoning is enabled by default. Documentation is internally inconsistent on whether its default effort is `low` or `medium`; set it explicitly.
- For short voice responses, `reasoning_effort: null` avoids reasoning tokens consuming time and the token budget before visible speech text.
- Sarvam labels `sarvam-30b` as lower latency and better suited to real-time conversational workloads. It labels `sarvam-105b` as the quality-first model.

No p50, p95, p99, or absolute TTFT number is published for either model. Specific chat latency targets are `UNVERIFIED`. Sources: [Sarvam-105B model page](https://docs.sarvam.ai/api-reference-docs/getting-started/models/sarvam-105b), [chat overview](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/chat-completion/overview).

## Bulbul v3 streaming text-to-speech

### Connection and messages

Documented endpoint:

```text
wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v3&send_completion_event=true
```

The first message must be config. A documented example is:

```json
{
  "type": "config",
  "data": {
    "speaker": "shubh",
    "target_language_code": "en-IN",
    "pace": 1.2,
    "min_buffer_size": 50,
    "max_chunk_length": 200,
    "output_audio_codec": "mp3",
    "output_audio_bitrate": "128k"
  }
}
```

The guide confirms text, flush, ping, and close as client operations. It shows the received audio envelope as:

```json
{
  "type": "audio",
  "data": {
    "content_type": "content_type",
    "audio": "<base64 audio>"
  }
}
```

With `send_completion_event=true`, an event whose `data.event_type` is `final` signals completion. Sources: [TTS WebSocket reference](https://docs.sarvam.ai/api-reference-docs/text-to-speech/stream?explorer=true), [TTS WebSocket guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/streaming-api/web-socket).

The rendered live guide does not expose complete raw JSON examples for the text and flush messages. The likely SDK-equivalent text envelope is `{"type":"text","data":{"text":"..."}}`, but because that exact raw contract is not visible in the cited Sarvam page, it remains `UNVERIFIED`. Use the official SDK or an authenticated protocol probe before implementing a raw client.

### Supported languages

Bulbul v3 supports 11 languages: Hindi (`hi-IN`), Bengali (`bn-IN`), Tamil (`ta-IN`), Telugu (`te-IN`), Gujarati (`gu-IN`), Kannada (`kn-IN`), Malayalam (`ml-IN`), Marathi (`mr-IN`), Punjabi (`pa-IN`), Odia (`od-IN`), and English (`en-IN`). Source: [Bulbul model page](https://docs.sarvam.ai/api-reference-docs/getting-started/models/bulbul).

### Voices

Speaker names are case-sensitive lowercase strings. The documented Bulbul v3 speakers are:

- Male: `shubh` (default), `aditya`, `rahul`, `rohan`, `amit`, `dev`, `ratan`, `varun`, `manan`, `sumit`, `kabir`, `aayan`, `ashutosh`, `advait`, `anand`, `tarun`, `sunny`, `mani`, `gokul`, `vijay`, `mohit`, `rehan`, `soham`.
- Female: `ritu`, `priya`, `neha`, `pooja`, `simran`, `kavya`, `ishita`, `shreya`, `roopa`, `tanya`, `shruti`, `suhani`, `kavitha`, `rupali`.

The docs also publish language-specific recommended voices. Source: [speaker guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/how-to/change-the-speaker-voice).

### Codecs and sample rates

WebSocket config documents `mp3`, `wav`, `aac`, `opus`, `flac`, `pcm` (LINEAR16), `mulaw`, and `alaw`. Bulbul v3's default sample rate is 24000 Hz. The dedicated sample-rate guide says all streaming modes support 8000, 16000, 22050, and 24000 Hz, while 32000, 44100, and 48000 Hz are REST-only. Source: [TTS sample-rate guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/how-to/set-the-sample-rate).

The Bulbul model page contains a contradiction: one limits-table line says high rates are available for REST and WebSocket, while its prose and the dedicated guide say they are REST-only. Treat 32000, 44100, and 48000 Hz over WebSocket as `UNVERIFIED`; do not use them in Phase 2.

### Documented latency and connection behavior

Sarvam describes the WebSocket API as low latency and says playback starts when the first audio chunk is synthesized. It publishes no absolute TTFB percentile or service-level target for Bulbul v3. Therefore the proposed 200-300 ms TTS budget is `UNVERIFIED` for Sarvam and must be measured. The TTS guide says idle sockets close after about one minute and recommends ping messages for long-lived connections. Source: [TTS WebSocket guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/streaming-api/web-socket).

## Rate limits

Limits apply per account, shared by all keys, using independent per-API pools. Published limits are:

| API | Starter | Pro | Business |
|---|---:|---:|---:|
| STT WebSocket | 20 concurrent | 100 concurrent | 100 concurrent |
| Bulbul v3 TTS WebSocket | 30 concurrent | 200 concurrent | 1,000 concurrent |
| Sarvam-30B / Sarvam-105B chat | 40 requests/min | 60 requests/min | 120 requests/min |

Sarvam warns that WebSocket burst admission can reject connections below the listed concurrent ceiling. Rejected sockets close with code 1003 and are not queued. The burst threshold is not fixed, so reconnects should be staggered with backoff. Source: [credits and rate limits](https://docs.sarvam.ai/api-reference-docs/ratelimits).

## Gaps

The requested claim that Sarvam supplies none of VAD, endpointing, barge-in, or transport cannot be confirmed. Current docs show a mixed result:

| Capability | Native Sarvam support | What this project still must build |
|---|---|---|
| VAD | Yes, in streaming STT. `high_vad_sensitivity`, `vad_signals`, speech thresholds, frame counts, volume threshold, pre-speech padding, and initial-frame suppression are documented. | Local/backend VAD is still useful to prevent silence from ever reaching Sarvam, control cost, create vendor-independent semantics, and timestamp local acoustic boundaries. |
| Endpointing | Yes, in streaming STT. Default silence behavior and tunable negative-frame windows are documented; `END_SPEECH` and final transcript events are available. | Product-specific turn policy, timeout strategy, false-end recovery, semantic endpointing, and consistent behavior across vendor outages. |
| Barge-in | Partial primitives only. STT can emit `START_SPEECH` and exposes `interrupt_min_speech_frames`. | The application must stop browser playback, cancel LLM work, close and replace the Bulbul socket, discard stale chunks, manage history truncation, and acknowledge that output is actually silent. Bulbul has no in-band cancel/clear. |
| Transport | Vendor WebSockets exist for STT and TTS; chat streams over SSE. | Sarvam does not provide the browser-to-FastAPI session transport, microphone capture, playback queue, reconnection policy for the application socket, JWT authorization, tool proxying, billing events, or a full duplex media session such as WebRTC/LiveKit. |

Sarvam's VAD frame is documented as 512 samples, which is 32 ms at 16 kHz and 64 ms at 8 kHz. The high-sensitivity preset uses an approximately 0.5 second silence boundary; the ordinary mode uses approximately 1 second. Fine defaults include `negative_frames_count=18` in a 24-frame window and `interrupt_min_speech_frames=2`. Source: [streaming STT guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/streaming-api).

Conclusion: keep the project's local VAD and orchestration if the goal is silence gating, exact local measurement, and full control. Describe it as a deliberate local implementation despite overlapping Sarvam features, not as a capability Sarvam lacks.

## Phase 2a probe results

Probe date: 2026-07-12

These results came from authenticated calls to the deployed Sarvam APIs through
[`backend/scripts/ws_probe.py`](../backend/scripts/ws_probe.py). The input was a
2.226-second English utterance stored as mono 16 kHz PCM16 WAV. The successful
manual-flush run and a separate no-flush run both completed the full application
path: application WebSocket -> Saaras -> `create_agent` with Sarvam-105B ->
sentence chunker -> Bulbul -> application WebSocket. The no-flush run appended
1.8 seconds of silence and relied only on Saaras `START_SPEECH` / `END_SPEECH`
endpointing.

The current machine-readable contracts used to prepare the probes were
[Sarvam AsyncAPI](https://docs.sarvam.ai/asyncapi.json), the
[official Sarvam SDK listing](https://pypi.org/project/sarvamai/), and the
[TTS WebSocket guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/streaming-api/web-socket).

### Saaras raw PCM and final response

The exact working raw PCM contract for this application is:

```text
wss://api.sarvam.ai/speech-to-text/ws
  ?model=saaras:v3
  &mode=transcribe
  &language-code=unknown
  &sample_rate=16000
  &input_audio_codec=pcm_s16le
  &flush_signal=true
  &vad_signals=true
```

Each 16-bit little-endian PCM chunk is sent as:

```json
{
  "audio": {
    "data": "<base64 raw PCM bytes>",
    "sample_rate": "16000",
    "encoding": "audio/wav"
  }
}
```

The apparently mismatched values are intentional. `input_audio_codec=pcm_s16le`
declares the raw bytes at connection time, while the per-message `encoding`
field still must be the literal string `audio/wav`. A negative control using
`"encoding":"pcm_s16le"` was rejected by the deployed socket with a validation
error stating that the only accepted value is `audio/wav`. The other documented
raw codecs (`pcm_l16` and `pcm_raw`) were not exercised because the browser and
probe source is specifically little-endian PCM16.

The successful final payload was:

```json
{
  "type": "data",
  "data": {
    "request_id": "<request id>",
    "transcript": "Hello, what is the capital of India?",
    "timestamps": null,
    "diarized_transcript": null,
    "language_code": "en-IN",
    "language_probability": 1.0,
    "metrics": {
      "audio_duration": 2.88,
      "processing_latency": 0.37012529373168945
    }
  }
}
```

Therefore `language_code` and `language_probability` are **CONFIRMED over the
Saaras v3 WebSocket** when `language-code=unknown`. They remain nullable fields
in the machine-readable schema and callers must not assume a non-null value for
every mode or input. No interim or partial transcript was observed. The deployed
socket emitted `START_SPEECH`, `END_SPEECH`, then one final `data` message.

The no-flush run also completed successfully. Saaras emitted `END_SPEECH` and
the final transcript without any application flush signal, confirming that its
built-in endpointing is sufficient for the temporary Phase 2a loop.

### Bulbul raw config, text, flush, and PCM output

The authenticated working connection was:

```text
wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v3&send_completion_event=true
```

The accepted config was:

```json
{
  "type": "config",
  "data": {
    "speaker": "shubh",
    "target_language_code": "en-IN",
    "speech_sample_rate": 24000,
    "output_audio_codec": "linear16",
    "pace": 1.0,
    "temperature": 0.6,
    "min_buffer_size": 50,
    "max_chunk_length": 200
  }
}
```

`speech_sample_rate` was accepted as a JSON number. The model stays in the URL
query and is not duplicated in config data. `min_buffer_size=20` was rejected;
the documented range starts at 30, so the implementation uses 50. Source:
[Sarvam buffer-size guide](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/how-to/set-buffer-size-to-start-processing).

The exact accepted text and flush messages are:

```json
{"type":"text","data":{"text":"The capital of India is New Delhi."}}
```

```json
{"type":"flush"}
```

Bulbul returned one or more messages shaped as:

```json
{
  "type": "audio",
  "data": {
    "request_id": "<request id>",
    "content_type": "audio/pcm",
    "audio": "<base64 LINEAR16 bytes>"
  }
}
```

It ended with `{"type":"event","data":{"event_type":"final"}}`. A negative
control using `output_audio_codec:"pcm"` was rejected with code 422. The exact
deployed WebSocket wire value is therefore **`linear16`**, even though the prose
WebSocket guide currently calls the same format `pcm` (LINEAR16). The successful
output was wrapped by the probe as mono 24 kHz PCM16 WAV: 115,392 audio bytes,
2.404 seconds, RMS 3539.4, and peak magnitude 23,340, confirming a valid
non-silent waveform.

### LangChain stream observability

`ChatOpenAI` was configured with Sarvam's base URL, `model="sarvam-105b"`,
`reasoning_effort=None`, `extra_body={"reasoning_effort": None}`, and streaming
enabled. It was passed to LangChain `create_agent` with no tools and an
`InMemorySaver` under one call-scoped `thread_id`.

All three Phase 2a boundaries needed by the future `TurnTimer` were observable:

| Boundary | Observed mechanism | Result |
|---|---|---|
| Request start | Async `on_chat_model_start` callback passed through `create_agent.astream` | Confirmed before any visible chunk |
| First visible token | First non-empty `AIMessageChunk.text` from `stream_mode="messages"` | Confirmed |
| First speakable chunk | First sentence emitted by the pure `SentenceChunker` while agent messages were still streaming | Confirmed |

The implementation raises `AgentObservabilityError` if visible text arrives
without the request-start callback or if the callback never occurs. No hidden
hot-path boundary was found, so the Phase 2a stop condition did not trigger.
LangChain's documented mechanisms are described in its
[streaming guide](https://docs.langchain.com/oss/python/langchain/streaming),
[voice-agent guide](https://docs.langchain.com/oss/python/langchain/voice-agent),
and [short-term memory guide](https://docs.langchain.com/oss/python/langchain/short-term-memory).

### Informal observed latency

These are development-machine observations from one generated English question,
not benchmarks, distributions, or acceptance evidence:

| Span | Observations |
|---|---:|
| Saaras flush sent -> final received | 927.6 ms in the successful manual-flush run |
| Saaras provider `metrics.processing_latency` | 370.1 ms manual-flush run; 167.2 ms built-in endpointing run |
| Sarvam-105B request callback -> first visible token | 609.2 ms manual-flush run; 413.5 ms built-in endpointing run |
| Sarvam-105B request callback -> first speakable sentence | 697.7 ms; 485.0 ms |
| Bulbul first text submitted -> first audio message | 258.0 ms; 268.0 ms |

The provider's STT `processing_latency` is not the same span as the application's
flush-to-final measurement. Sample counts are one per row value, so none of
these numbers supports p50, p95, or p99 claims.

### Corrections needed in the approved baselines

Do not edit the baselines without review. The probe indicates these exact
follow-up edits:

1. In `requirement.md` section 2, replace Bulbul
   `output_audio_codec:"pcm"` with `output_audio_codec:"linear16"`. Keep
   `speech_sample_rate:24000` as a JSON number and note that returned
   `content_type` is `audio/pcm`.
2. In `requirement.md` sections 2 and 3, replace the Saaras WebSocket
   `language_code` / `language_probability` `UNVERIFIED` wording with the
   confirmed nullable contract above. The Phase 2a probe task for those fields
   can be marked complete.
3. In `requirement.md` section 2, replace the raw-PCM encoding probe placeholder
   with the confirmed pair: connection query
   `input_audio_codec=pcm_s16le`, message `encoding:"audio/wav"`.
4. In `architecture.md` section 9, keep all budget rows explicitly informal,
   but replace `UNVERIFIED until measured` with a link to these first
   observations. The single flush-to-final sample (927.6 ms) exceeded the
   150-300 ms planning hypothesis; it is not enough data to revise a percentile
   budget, but the table should no longer imply that no authenticated
   measurement exists.

No other Phase 2a finding contradicts the approved architecture. In particular,
the no-flush run confirms its temporary use of Sarvam endpointing, and
`linear16` is still raw PCM16 at 24 kHz on the application downlink.

## Related documentation

- [Architecture](architecture.md)
- [Voice metrics research](voice-metrics.md)
- [Replay benchmarks](BENCHMARKS.md)
- [Requirements](../requirement.md)
- [Project README](../README.md)
