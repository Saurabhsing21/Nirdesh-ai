# Plans

| Task | Content | DoD | Depends | Status |
|---|---|---|---|---|
| 1 | Make TTS failures recoverable and proxy logs token-safe | Non-speakable chunks are filtered; a Sarvam TTS rejection reports a turn error but the response worker continues; Nginx does not log query-string JWTs; tests and production build pass; server deployment is healthy | — | cc:完了 |
| 2 | Recover from transient upstream network failures | DNS/connectivity failures get one bounded retry; an exhausted retry fails only the affected turn, returns the session to listening, and leaves the response worker available for later turns; focused and full tests pass; production deployment is healthy | 1 | cc:完了 |
| 3 | Handle expired authentication explicitly | Expired and invalid JWTs emit token-safe structured rejection logs; HTTP 401 and voice WebSocket 4401 clear the stale browser session and return the user to OTP login with a specific message; backend tests and the frontend production build pass; production deployment is healthy | 2 | cc:完了 |
| 4 | Use the deployed origin for browser API calls | With no explicit Vite API override, HTTP and voice WebSocket URLs resolve from the page origin rather than localhost; regression tests and both frontend builds pass; the public bundle reaches the production login API | 3 | cc:完了 |
| 5 | `[Contract]` `[lane:gate]` `[tdd:skip:docs-contract]` Record the latency research, accepted v1, and future optimization backlog | `docs/future-optimization-ideas.md` distinguishes pipeline limits, real answer latency, perceived feedback latency, accepted safeguards, rejected scope, and future work; `requirement.md` defines the protocol and product behavior; `git diff --check` passes | 4 | cc:完了 |
| 6 | `[Feature]` `[lane:gate]` `[tdd:required]` Implement perceived-latency v1 for normal conversation | Phrase-aware chunking emits a provider-safe first phrase; one cached non-semantic cue is independently played and deterministically cancelled by answer/new speech; thinking responses cancel without stale output/history; feedback and answer metrics stay separate and optional; focused backend/frontend tests, Ruff, typecheck, and build pass | 5 | cc:完了 |
| 7 | `[Refactor]` `[lane:gate]` `[tdd:required]` Isolate the optional knowledge RAG flow into add-on modules | Core application, voice, and frontend shell contain only generic add-on hooks; RAG lifecycle, models, voice tool/prompt, API, UI, and capability mapping live in dedicated knowledge feature files; off/on behavior and full regression suites pass | 6 | cc:完了 |

## Task 6 implementation contract

- **Spec delta:** `requirement.md` FR-5, FR-7, FR-10, FR-11, the WebSocket
  protocol, timestamp definitions, derived metrics, Phase 2d, and test plan.
- **Research record:** `docs/future-optimization-ideas.md`.
- **Required:** phrase-aware first-chunk policy, non-semantic cached cue,
  `turn_id` + `cue_id`, independent feedback playback, answer/new-speech
  cancellation, thinking cancellation, stale-output guards, split metrics,
  kill switches, and automated tests.
- **Recommended validation:** throttled-browser and speaker/headphone/mobile
  smoke checks followed by a dedicated no-tool multilingual replay.
- **Deferred:** tool-routing repair, semantic acknowledgements, socket reuse,
  semantic endpointing, model switch, WebRTC/LiveKit migration, and native
  speech-to-speech.
- **team_validation_mode:** `subagent` (Product/Skeptic,
  Architecture/Security, and QA/Regression perspectives).
- **formatter_baseline:** `configured` — backend Ruff config and CI commands in
  `backend/pyproject.toml` / `.github/workflows/ci.yml`; frontend `test`,
  `typecheck`, and `build` scripts in `frontend/package.json`.
- **TDD evidence required:** failing tests for first phrase release, cue policy,
  cue metrics, stale/cancelled events, and thinking cancellation before the
  production implementation is accepted.

### Task 6 closeout evidence

- TDD red: missing `PhraseChunker`, response-cue policy, feedback lifecycle,
  and thinking-cancellation behavior failed before implementation.
- Backend: 46 focused voice/latency tests pass; changed Python files pass Ruff
  lint and format checks.
- Frontend: 11 tests, TypeScript typecheck, and production build pass.
- Review: `APPROVE` after fixing the hard first-phrase cap and removing cue
  cancellation I/O from the answer-audio critical path; scoped AI-residual scan
  also reports `APPROVE`.
- Full backend suite: 106 tests pass and 2 unrelated in-progress knowledge
  reindex tests fail (`run_pending_jobs`/profile activation); this latency task
  did not modify that subsystem.
- Remaining release gate: manual speaker/headphone/mobile echo and overlap smoke
  tests plus the dedicated no-tool multilingual replay require a running browser
  and live Sarvam credentials.
