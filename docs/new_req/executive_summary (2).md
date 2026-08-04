# Stoa — Executive Summary

> *Run product development like a well-tuned database: append-only WAL, CRDT-merging humans, AI as the query planner.*

**Audience:** Stoa management and ICs evaluating whether to adopt Stoa as the org's design methodology.
**Status:** Draft proposal, in active iteration. Reflects the state of [proposed_methodology.md](proposed_methodology.md) at this commit.
**Length:** ~8-minute read.
**Always-current.** The summary updates on every commit; the version you are reading reflects what we agreed at HEAD, not last week. (See [§7 Self-consistent state, by construction](proposed_methodology.md#7-self-consistent-state-by-construction).)

> *Empirical signal at this commit.* Across nine controlled stress-test runs after the most recent spec patches (override-ask on operator directive; self-validated cue handling; execute-phase substrate sweep; default-shift on substrate findings), the AI-mediated WAL maintains decision-arc reconstruction fidelity at a 0.91 mean (vs 0.69-0.81 baseline) — load-bearing for the "AI maintains the substrate" thesis below. Full instrument: [arc-capture-quality](../experiments/arc-capture-quality.md).

---

## The pitch in one sentence

**Stoa is the design-time layer that makes AI-assisted coding actually work for non-trivial systems. It does two things. First, it produces deeply-refined, phased implementation plans (grounded in Product Management's intent and the Engineering organization's architecture) that agentic coding tools need to ship production-quality work. Second, it keeps code, design, and rationale in lockstep automatically as both evolve.** Async-required teams especially.

The artifact shape (an append-only log of decisions) is **not novel**. Architecture Decision Records (ADRs) have been a known-good idea for well over a decade. ADR adoption is spotty in practice not because of the artifact but because of the **operational layer around it**: writing discipline, supersession links, drift detection against code, finding the relevant prior art for a new question, capturing the deliberation that produced the decision rather than the conclusion. That layer was too expensive for humans to sustain at scale. **AI now makes it cheap. Stoa is what that cheap layer looks like, and the artifact it produces is exactly the input agentic coding tools have been missing.**

---

## The problem

Design is the engineering activity hardest to sustain at the rigor we apply to testing or deployment. Design docs go stale within months. Decisions get lost. The rationale behind a load-bearing choice evaporates as the people who made it move on. New engineers take 3+ months to be productive because the *why* lives in nobody's head and is documented nowhere.

For fully-remote, async-required organizations like Stoa (engineers in 5+ timezones, no synchronous overlap with most peers), this gets dramatically worse. Synchronous design conversations are a rare option. Either someone wakes up early, or design becomes a single-person bottleneck, or the org pays the structural cost: code-doc drift, archaeology before any change, feedback that re-litigates settled decisions.

**The arrival of AI-assisted coding has changed the stakes.** We are now asking AI to write production code, and it does that well only when given a deeply-refined, phased spec that captures multi-angle deliberation, names alternatives considered, decomposes the work into sub-phases, and validates load-bearing assumptions with PoCs. *"Make me an online shopping site"* produces a vibe-coded toy. Production-quality output requires a spec refined across thousands of threads (technical details, design issues surfaced during implementation, stakeholder questions), each settled and recorded with context. **The cognitive work that produces that spec is the new bottleneck.** It is multi-angle by nature, often multi-human, and async by necessity for distributed teams.

Few teams sustain a serious design record at scale, even when they want to. The required discipline (writing decisions in real time, keeping them coupled to the code as both evolve, capturing the deliberation rather than the conclusion, surfacing relevant prior context when a new question comes up) is too expensive to maintain by hand. **Stoa is what design discipline looks like when AI absorbs the maintenance cost.**

---

## What Stoa is

A methodology for AI-assisted product development. It makes design a first-class engineering activity that is auditable, async-native, parallelizable, and living next to the code.

*Named after the colonnades of ancient Athens where philosophers and citizens deliberated in public, a structured space for collective reasoning, anchored in place but open to anyone.*

Stoa's core primitive is a **write-ahead log (WAL) of decisions** that an AI agent can read, interpret, and synthesize on demand. The deliberation that produces each entry happens **at the WAL**, in *refining sessions* between operator and AI, not in some other channel that gets summarized later. Around the WAL sit lightweight conventions: refining sessions, a seven-trigger coherence cadence (pre-commit drift walk, post-decision propagation, pre-commit WAL audit, pre-compact/clear audit, on-demand `/stoa audit`, content-triggered semantic-merge catchup, end-of-implementation audit + artifact-coherence nudge), a unified `/stoa coherence` primitive backing every Superseding/Converging/Adjacent classification, self-extracting installation, repo-specific extensions for per-project customization, and Slack/Jira/GDocs integration adapters for async multi-role collaboration.

The methodology is intentionally **loose, semi-structured, AI-interpretable**, not strict-schema. AI is what makes maintenance affordable; without AI, the upkeep cost would defeat the value.

**AI's role: substance is human, coherence is AI** (founding principle #4). The operator brings substance — what the decisions actually are, the engaged expertise that gives the WAL its value. The AI brings coherence — recording, classification, surfacing, reconciliation across the WAL. Stoa makes no claim to provide intelligence; the methodology amplifies engaged expertise rather than substituting for it. Non-engaged use produces coherent records of mediocre decisions; selection for engaged expertise is by design. WAL management is autonomous: the AI judges T1→T2 promotion against a class-based yardstick (does this fit one of the five entry types?), writes entries directly, runs self-coherence on every write, and treats `context_log.md` like any other tracked artifact at the git boundary. The operator does not approve individual WAL entries; the operator's feedback loop is `/stoa audit` (four sweeps, with the session-reflective sweep as the primary calibration channel during beta), the override-ask response when AI surfaces substrate counter-evidence against a directive, classification override, and the explicit-log primitive (*"log this"*).

**Adoption is dial-able.** At the minimum, Stoa sits in the background and the AI captures substantial decisions during normal work. At the maximum, operators drive deliberate refining sessions for non-trivial questions, walk the coherence cadence at every commit, and run `/stoa audit` periodically. The full pattern produces the deepest specs and the strongest code-coupling guarantees, but **even the minimum already beats no methodology**. A casual decision log with AI-mediated lookup is far more useful than nothing. **Refining is the recommended mode, not a prescribed one. Use as much of Stoa as your work needs.**

**Stoa is iterative by construction. The iteration has a direction.** A refining session is a free-form back-and-forth between operator and AI that **narrows a design question down to a settled answer**. Refining is the act of narrowing, not just looping. The granularity is whatever the work needs: a technical detail, a design issue surfaced during implementation, a stakeholder's question. The session settles into a WAL entry when the question reaches resolution; otherwise it tables, branches, or stays in-flight. Decisions can be revisited and superseded freely via `rollback` entries. Both directions of the design-implementation loop land in the WAL in real time. **Nothing is frozen.** (Worked example: the Aurora pivot in the trial below.)

Refining sessions are **explicitly multi-role**: they integrate Product Management's intent, the engineering organization's architecture and design constraints, and implementation-side discoveries, converging on a settled answer that reflects all three. The output that accumulates over time is a phased implementation plan with all of its reasoning, alternatives, and PoC-validated assumptions traveling alongside the code.

**A Stoa-using session is a Human+AI local collaborator pair.** Both sides contribute to the decision arc: operator-led settlements (cued by phrases like *"let's go with that"* / *"let's implement X"* / *"commit"*; or operator self-validated proposals like *"I think we should require API-key auth. Makes sense to me."* — proposal + settlement in one turn) and AI-led auto-refinement (cued by mid-flow course-corrections like *"actually, on reflection..."* / *"I'm changing approach because..."*). The AI judges T1→T2 promotion for both kinds against the class-based yardstick and writes entries directly — every write surfaces inline as a `[stoa]` chat anchor. The multi-author merge substrate (cadence #6 — union merge plus a semantic audit) handles convergence across coworker pairs — pair-A's record integrates with pair-B's symmetrically. The model: a Stoa-running org is a network of Human+AI pairs whose records merge into shared truth.

---

## What you get (the three big shifts)

1. **Produces the spec agentic coding can actually execute.** Refining sessions explore design questions multi-angle, name and weigh alternatives, decompose work into phased sub-plans, and validate load-bearing assumptions with PoCs before commitment. The output is a phased implementation plan that **reflects Product Management's intent and is consistent with the engineering organization's architecture and design**. This is the kind of refined input agentic coding tools need to ship production-quality systems, not the *"make me a shopping site"* prompt that produces vibe-coded toys. **Stoa is the bridge between PM intent, engineering architecture, and the coder.**

2. **Self-consistent state, by construction.** Code, design docs, summaries, and demos all update together via the coherence cadence. The decision record and the code stay coupled automatically. Stakeholders ask *"is this still valid?"* and get a 30-second answer.

3. **Staggered + threaded refinement (async-native).** Multiple parallel design tracks. AI catches incompatibilities **early**, on in-progress work, not after both have hardened into incompatible commits. New joiners, returning teammates, and mid-conversation invitees self-serve into threads by reading the WAL, with no synchronous handoff to the original author. This is what makes async-required teams viable: 5+ timezones, no synchronous overlap, no waiting on sync windows to discover conflict. Multi-author WAL semantic-merge runs as cadence #6 — the `.stoa/audit-cache` coverage delta (committed, union-merged certificates of what's been certified-together) fires catchup on the next session-start bootcheck scan or T2 write, catching every integration path including server-side PR merges and fresh clones, plus a `/stoa pull` operator-driven pre-merge halt-point that lets you resolve cross-author Superseding decisions before integration replays. Two operators logging on parallel branches don't silently cross wires.

**Agent-first coherence architecture.** The WAL is curated, high-relevance-density data: every entry is signal. At slurp-feasible scale, a subagent loads the WAL into its own context and reasons directly over the corpus; the parent refining session stays lean. RAG-style retrieval is a scale-extension fallback when the WAL outgrows slurp, not the primary substrate. A single `/stoa coherence` primitive (three modes: 1-vs-corpus, M×N pairwise, M×M internal-sweep) backs every coherence operation across the methodology, with a unified Superseding / Converging / Adjacent classification vocabulary. Autonomous WAL management: the AI manages `context_log.md` end-to-end without per-entry operator confirmation, gated by its own judgment (class-based yardstick, default-to-no-candidate under uncertainty), backstopped by `/stoa audit`, self-coherence on every T2 write, and AI-judged batch coherence at commit. (See [proposed_methodology.md §Core primitives → `/stoa coherence`](proposed_methodology.md#the-stoa-coherence-primitive).)

### And four properties that fall out

4. **In-process, not post-hoc.** The deliberation happens AT the WAL. Operator and AI iterate through the question, alternatives surface, tradeoffs get weighed, and the entry that lands is the distilled product of the actual thinking, not a summary written after the meeting. The WAL IS the record of how we thought, not just what we concluded.
5. **Execution-validated design.** Load-bearing decisions are backed by working PoCs before they commit. AI makes building the PoC cheap; implementation discoveries reshape the design *before* commitment, not after.
6. **Context survives delivery.** When a feature ships, the WAL holds the full reasoning chain. Customer feedback six months later starts informed, not from scratch. The new engineer joining in month 12 reads the WAL and gets the full *why*, not just the *what*.
7. **Auditable engineering alongside the code.** Every decision has attribution, rationale, alternatives considered. Stakeholders ask *"what was decided about X, by whom, when, and why?"* and get a real answer rooted in the WAL.

---

## And one second-order benefit, compounding at scale

Beyond the seven first-order value-adds above (the three shifts plus the four properties), the WAL data itself becomes a feedback signal at scale. As more projects adopt Stoa, the methodology gets data about its own effectiveness: *did the right collaborations happen at the right times? Are decisions reaching conclusion efficiently? Is context transferring to new joiners? Where do similar decisions cluster across projects? What does the audit trail look like when an external regulator asks?* Stoa applies its own discipline to itself: every methodology version is informed by the WAL data of projects running the previous version. The methodology is **calendar-versioned and evolves**. *Stoa as of 2026-05* is not the last word; it's a snapshot. The data dividend feeds the next version. (See [§Second-order benefits in the proposal](proposed_methodology.md#second-order-benefits--stoas-self-improvement-loop) for the full treatment.)

---

## What Stoa is NOT

Pattern-match deflection. What people assume Stoa is, that it isn't:

- **NOT a new artifact format.** Decision-log artifacts have existed in various forms for years. The novelty is the operational layer that makes them maintainable, not the file format itself.
- **NOT a strict methodology.** The loose-framework principle is load-bearing. Rigid validators, mandatory schemas, and gate-checks at PR time have repeatedly failed at scale; engineers route around them. Stoa's discipline lives in AI interpretation of loose conventions, not in coded gates that punish experimentation.
- **NOT a replacement for personal AI workflows.** Stoa is the substrate (the WAL + the coordination primitives). Per-engineer AI workflow customization (skills, rules, command surfaces) composes over the substrate without conflict. Operators extend Stoa per-repo via the `Repo-specific extensions` section in [stoa.md](../stoa.md).
- **NOT waterfall.** Refining sessions are free-form; decisions can be revisited freely via `rollback`; PoC findings reshape design before commitment. Stoa captures the design-implementation loop in both directions, not a single forward sweep. (See the Aurora pivot below.)
- **NOT a synchronous-team tool.** Async-required is the target. Synchronous teams may find Stoa useful; async-required teams need it.
- **NOT an agentic coder.** Stoa doesn't write code. Its job is to make sure the agentic coder gets the most detailed spec possible, one that reflects Product Management's intent and is consistent with the engineering organization's architecture and design. Stoa sits *upstream* of coding tools (Kiro, Cursor, Codex, Claude Code, Anthropic Skills, ...) and produces the refined spec they consume. Teams pick their downstream agentic flavor at their own pace; Stoa stays out of that fight. The boundary is porous; execution discoveries flow back through the WAL into design. Stoa's primary job is the design-time cognitive work that connects PM intent to engineering execution, not the coding loop itself.

---

## The honest tradeoff

Stoa is **AI-assisted by design**. Quality depends on the agent doing the interpretation. A strong model (current context, faithful instruction-following) makes Stoa reliable; a weaker one introduces drift. **Mistakes happen.** They're interpretation slips, not bugs in coded rules. We accept this tradeoff because the alternative (rigid validators, mandatory schemas, gate-checks at PR time) has repeatedly failed at scale: engineers route around methodologies that punish experimentation. **Better to be occasionally fuzzy than universally bypassed.** AI mistakes are recoverable (next session reads the WAL; `[stoa]` chat anchors surface every T2 write inline; `/stoa audit` sweeps on demand, with the session-reflective sweep specifically targeted at AI's own autonomous-management calibration). Operator-bypass is catastrophic. Stoa's value also compounds with agent capability; as models improve, the AI-fuzziness cost drops. **Decision-arc-reconstruction-fidelity testing is the calibration substrate over time:** can a fresh AI session reconstruct the project's intended artifact from the WAL alone? The empirical answer drives methodology iteration — the latest stress-test run lands at 0.91 mean fidelity vs a 0.69-0.81 prior baseline (see [arc-capture-quality](../experiments/arc-capture-quality.md) for the instrument). (Full framing: [proposed_methodology.md §"What this means in practice"](proposed_methodology.md#what-this-means-in-practice).)

---

## Concrete evidence from the trial

Stoa was developed during a 6-day trial on a large multi-service adopter project's multi-tenant compute integration PoC. The PoC itself is non-trivial: a production-grade SaaS architecture for financial-sector enterprise customers, with per-tenant VPC isolation, cross-account data-catalog integration with per-user credential vending under KMS-asymmetric policy, multi-VPC ENI attachment at runtime for warm-pool assignment, and an 8-table DynamoDB substrate for metadata and scheduling, all running against a real customer data catalog. **One engineer designed and built the entire end-to-end demo using Stoa as the methodology backbone in under 6 days.** The WAL kept design and implementation in lockstep across seven build phases, AI absorbed the documentation maintenance cost, and execution-validated design caught load-bearing pivots before they became technical debt. The kind of architecture that historically takes a small team months was here delivered by one person without sacrificing rigor.

Two patterns from the trial illustrate Stoa's two top value-adds (the full trial report lived in the adopter project's own repo and is not part of this open-source distribution):

- **Phase 5 sub-phase decomposition + data-catalog preflight: the refined-spec → better-implementation loop.** The largest implementation phase was refined into seven sub-phases with a small spike validating the trickiest data-catalog-integration assumption *before* implementation began. Once the spec was that refined (phases named, dependencies traced, load-bearing assumption PoC-validated), implementation quality jumped substantively. **This is the upstream effect Stoa-fed input has on downstream agentic implementation.** Without the refinement, the agent would have hit the same load-bearing assumption mid-implementation and produced lower-quality work or stalled.
- **The Aurora pivot: design-implementation-design loop, captured live.** Original design: Aurora + pg_cron + plpython3u for metadata and scheduling. Implementation surfaced that AWS had removed plpython3u from Aurora 15+. The full rethink landed on DynamoDB + EventBridge Scheduler + Lambda. The WAL captured both the original decision and the rollback, the rationale for each, and the alternatives reconsidered the second time around. Both directions of the loop, in real time. *Without Stoa, that pivot's reasoning would have been lost within a quarter.*

A subsequent self-trial validated an early beta against itself: 28 scenarios across install, opt-in, WAL operations, guardrail, tracked artifacts, coherence cadence, session restart, WAL queries, and Codex emulation; 7 spec gaps surfaced and addressed; a reusable test harness shipped at [`tests/`](../tests/). The harness later evolved into an adherence-measuring stress-test substrate (since removed) that scored tier-1/2/3/4 cue capture under controlled cognitive load; the most recent run feeds the 0.91-vs-0.69-0.81 number above.

---

## What we're asking for

A **3-week beta** on 2–3 projects across the org. Each picks an active design question and tries Stoa against it. We learn what works, what cracks, and where the methodology needs sharpening. See [getting_started.md](getting_started.md) for the engineer-facing onboarding.

---

## What it costs

Minimal up-front:

- Fetch the unified [`dist/`](../dist/) bundle and run [`dist/install.sh install`](../dist/install.sh) in the target repo. One command installs every supported host (Claude + Codex) at once and handles fresh install and upgrade transparently. For private-repo bootstrap, install.sh fetches the bundle via `gh api`. Existing `CLAUDE.md`/`AGENTS.md` content is preserved — install injects a delimited `STOA::DISPATCHER` block into `AGENTS.md` (creating it if absent), and `CLAUDE.md` is thinned to `@AGENTS.md`.
- Each engineer needs a supported host. Claude Code is the most-exercised; Codex ships in beta alongside it, with install mechanics and the live boot path (SessionStart hook + bootcheck injection + native-subagent spawn) validated on a real Codex CLI; skill loading and the behavioral surface remain to be confirmed (see [`tests/codex-smoke-test.md`](../tests/codex-smoke-test.md)).
- A `.gitattributes` line to suppress WAL diffs in PR review (added automatically by the installer).
- A few minutes per project — the install is mechanical, not conversational.

There is **no proprietary tooling to install, no SaaS to subscribe to, no vendor lock-in.** The methodology evolves under the org's control. A local OSS vector-index substrate (Python + `sentence-transformers` + a local embedding model) is the scale-extension fallback when the WAL outgrows the subagent slurp budget — installed by default (best-effort), all open-source, all local, no data leaves the operator's machine. Ongoing cost is git discipline (commit messages reference WAL entries) and AI usage (which the org already pays for).

---

## Where to learn more

- **[proposed_methodology.md](proposed_methodology.md)** — the full proposal (~950 lines). The engineering-detail version of this summary.
- **Interactive demos** (open the HTML files locally; ← / → navigate):
  - **[Multi-role workflow demo](../demos/workflow-demo.html)** — end-to-end PM → architect → DevManager → developer flow on a customer ask, ending in a phased implementation plan ready for agentic coding.
  - **[Aurora-pivot demo](../demos/aurora-pivot-demo.html)** — the refinement-loop + execution-validated-design + WAL-preserved-supersession arc from the trial (Aurora → DynamoDB). Claude built this from the actual WAL with a 1-sentence prompt, another side benefit of having the knowledge in the WAL.
- **[getting_started.md](getting_started.md)** — beta-test guide for Stoa engineers ready to try it on a project.
- **The trial report** — evidence behind the proposal; it lived in the adopter project's own repo and is not part of this open-source distribution.
- **[context_log.md](../context_log.md)** — the WAL of decisions that shaped this proposal itself.
