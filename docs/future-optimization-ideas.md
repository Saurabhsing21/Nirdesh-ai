# Future voice-latency optimization ideas

Last updated: 2026-07-22

## Goal and current evidence

NirdeshAI should feel conversational even though its production path is a
pipeline: speech-to-text (Saaras) -> text model (Sarvam) -> text-to-speech
(Bulbul). This has more independently variable stages than a native
speech-to-speech model, but it is not a fixed design ceiling. Streaming,
pipelining, connection reuse, turn detection, and careful playback policy can
still reduce both real and perceived latency.

Two baselines must remain distinct:

- The user-observed normal-conversation range is approximately 1.5-2.5 seconds.
- The 2026-07-12 synthetic cold local-VAD replay measured p50 2,956 ms and p95
  3,991 ms. That corpus was heavily affected by accidental tool routing, so it
  is not a clean normal-conversation benchmark.

In that replay, the largest median stage was the 1,445 ms from the first visible
LLM token to the first TTS-eligible chunk. This makes phrase-aware chunking the
first evidence-backed optimization. Tool routing remains important but is a
lower priority for the current normal-conversation pass.

## What LiveKit and similar real-time systems do

LiveKit's agent guidance combines several techniques instead of relying on one
latency trick:

- WebRTC transport for adaptive real-time media delivery.
- Turn-detection tuning, including semantic end-of-turn models, to avoid paying
  a fixed silence window on every utterance.
- Preemptive generation, where LLM/TTS work starts before the final turn commit
  and is discarded if the turn resumes.
- Streaming text into TTS as soon as a safe phrase is available.
- Optional background/thinking audio to reduce uncertainty during long waits.
- Per-stage observability so endpointing, transcription, model, synthesis, and
  playback latency are not collapsed into one number.

Relevant primary documentation:

- [LiveKit turn detection tuning](https://docs.livekit.io/agents/logic/turns/tuning/)
- [LiveKit preemptive generation](https://docs.livekit.io/agents/multimodality/audio/)
- [LiveKit background audio](https://docs.livekit.io/agents/multimodality/audio/background-audio/)
- [OpenAI voice-agent architectures](https://developers.openai.com/api/docs/guides/voice-agents)
- [OpenAI Realtime VAD](https://developers.openai.com/api/docs/guides/realtime-vad)

The often-repeated “500 ms” OpenAI figure is not used as an NirdeshAI design
fact or SLO. Native speech-to-speech can remove explicit STT -> text model ->
TTS boundaries, but actual latency still depends on endpointing, model/service
time, network location, buffering, and playback.

## Accepted first version

### 1. Phrase-aware answer chunking

Replace sentence-only release with a policy that:

- emits complete sentences as before;
- may emit at a clause boundary after a provider-safe minimum;
- forces the first chunk near a configurable cap, preferring whitespace;
- keeps later chunks larger for natural prosody;
- never emits punctuation/markup-only content.

Bulbul currently uses a minimum buffer of about 50 characters in this project,
so emitting tiny 5-15 character answer fragments is not useful. The goal is an
earlier useful first phrase, not per-token TTS.

### 2. Cached acknowledgement cue

The first version uses a short, non-semantic acknowledgement such as “hmm,”
preloaded by the browser. It does not claim understanding and does not
paraphrase the question. Language detection selects a compatible asset, while
an unsupported or low-confidence language falls back to the neutral cue.

The cue controller is state-based rather than LLM-based:

1. STT produces a final transcript and a turn ID.
2. The backend schedules at most one cue after a deterministic delay.
3. If real answer audio starts first, the pending cue is cancelled.
4. If the cue starts first, it plays on an independent Web Audio channel.
5. `audio_start`, new user speech, interruption, call end, or a stale turn ID
   immediately fades/stops the cue.
6. Missing or undecodable cue assets fail silently and never fail the call.

The cue must never be inserted in the main answer playback queue: doing so
would make a latency-masking feature delay the real answer.

### 3. Cancel while thinking

Confirmed new speech must cancel an active response even before answer audio is
sent. This differs from playback barge-in:

- cancel the exact old response and matching TTS task/socket;
- cancel pending client tools;
- reject stale text/audio for the old turn;
- preserve and forward the new turn's pre-roll frames once;
- do not require playback interruption acknowledgement or playback-history
  truncation when no assistant audio was spoken.

### 4. Separate latency accounting

Never substitute the acknowledgement for the answer in latency reporting.

- `feedback_voice_to_voice_ms`: last user speech capture -> actual cue playback
  start, entirely in the browser clock.
- `answer_voice_to_voice_ms`: last user speech capture -> actual answer playback
  start, entirely in the browser clock; this preserves the existing real UX
  metric.
- `answer_after_feedback_ms`: cue playback start -> answer playback start,
  entirely in the browser clock.
- `response_cue_dispatch_ms`: STT final -> cue dispatch, entirely in the server
  clock.

Cue timestamps are optional. Turns without a cue must remain valid and must not
be marked censored.

## Safety and quality gates

- Feature flags and a kill switch for the cue and phrase-chunking policy.
- One cue maximum per turn plus a session cooldown to prevent repetition.
- Unique `turn_id` and `cue_id` on schedule, cancel, and playback-start events.
- Epoch/generation checks after asynchronous browser fetch/decode/resume so a
  cancelled cue cannot start later.
- Answer audio wins every race and cue/answer overlap is measured.
- Speaker, headphones, mobile, and throttled-network smoke tests check echo,
  overlap, loudness, stale playback, and disconnect cleanup.
- A dedicated no-tool multilingual corpus is required before claiming an
  improvement. Report cold/warm and per-language cohorts and preserve failure
  counts.

## Prioritized backlog after version 1

1. Tune the first phrase thresholds from live replay data and compare prosody
   and Bulbul validation failures.
2. Reuse or preconnect Saaras and Bulbul sockets if authenticated tests prove
   reuse is safe; keep first-turn cold cohorts visible.
3. Add hybrid/semantic endpointing and evaluate latency together with false
   endpoint and false continuation rates.
4. Fix accidental tool routing and add a clean no-tool routing benchmark.
5. Evaluate Sarvam-30B as an explicit latency/quality/cost experiment; keep
   Sarvam-105B as the quality-first default until measurements justify change.
6. Add event-aware cached cues for genuine long operations (for example,
   “checking that now”) only when the application, not the model, knows the
   operation is actually running.
7. Consider preemptive LLM/TTS generation with strict discard semantics.
8. Evaluate LiveKit/WebRTC when packet loss, mobile networks, telephony, or
   multi-region media routing justify its additional operational complexity.
9. Evaluate native speech-to-speech as a separate architecture experiment,
   comparing latency, Indic-language quality, tool control, observability,
   cost, and vendor lock-in.

## Explicit non-goals for version 1

- Do not generate a semantic paraphrase while the real model is still thinking.
- Do not say “I understand” when only pipeline state is known.
- Do not hide answer-latency regressions behind faster cue latency.
- Do not migrate the transport to WebRTC or change the default LLM.
- Do not prioritize tool-routing changes in this pass.
