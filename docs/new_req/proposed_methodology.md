# Stoa — A Methodology for AI-Assisted Product Development

> *Run product development like a well-tuned database: append-only WAL, CRDT-merging humans, AI as the query planner.*

**Author:** Ivan Avramov
**Status:** Draft, in active iteration. Not ready for external distribution.
**Audience:** Engineers, PMs, architects, and managers evaluating whether to adopt Stoa on their own projects.
**Companion artifacts:**
- design-methodology.md — trial report (post-hoc analysis of the adopter project that produced this proposal; held privately by that project's team). Read for evidence.
- [context_log.md](../context_log.md) — the WAL of decisions that shaped this proposal itself. Read for traceability.
- [`stoa-claude.md`](../stoa-claude.md) — the composed Claude runtime. The methodology in operational form. Adopters fetch the unified [`dist/`](../dist/) bundle and run [`dist/install.sh install`](../dist/install.sh); the runtime drops at the repo root.
- [`src/`](../src/) — the editable canonical source the runtime composes from. Spec edits start here.

---

## TL;DR

**Stoa is the design-time layer that makes AI-assisted coding actually work for non-trivial systems.** It does two things. First, it produces deeply-refined, phased implementation plans (grounded in Product Management's intent and the Engineering organization's architecture and design) that agentic coding tools (Kiro, Cursor, Codex, Claude Code, Anthropic Skills, ...) need to ship production-quality work. Second, it keeps code, design, and rationale in lockstep automatically as both evolve. Async-required teams especially.

Stoa makes **design** a first-class engineering activity that is auditable, referenceable, parallelizable, and lives next to the code. The root motivation is enabling rigorous design work in **fully-remote, async-required** organizations, where synchronous design conversations are structurally hard.

Stoa's core primitive is a **write-ahead log (WAL) of decisions** that an AI agent can read, interpret, and synthesize on demand. Around the WAL sit lightweight conventions for *refining sessions* (the active phase before a decision settles, in **solo** or **shared** flow), *attribution* (who decided what, and which AI tools they used), *multi-role collaboration* (Slack-bridged `/stoa ask @<handle>` and `/stoa respond` between participants), *solo catch-up* (anyone self-serves into a thread async), *execution-validated design* (load-bearing decisions backed by working PoCs), *GDocs round-trip for review* (markdown stays canonical in the repo; `/stoa publish-doc` mirrors it to a Google Doc reviewers comment on with the GDocs UX they already know; `/stoa fetch-comments` + `/stoa triage-comments` pull threads back as structured markdown, resolve surgical concerns as edits, and route substantive concerns into refining sessions whose conclusions land in the WAL, using the comment surface stakeholders already know with code as the canonical truth), and *open extensibility* (Slack and Jira are first-class integrations; everything else stays loose).

The methodology is intentionally **loose, semi-structured, AI-interpretable**, not strict-schema. AI is what makes maintenance affordable; without AI, the upkeep cost would defeat the value.

**Adoption is dial-able.** At the minimum, Stoa sits in the background and the AI captures substantial decisions during normal work. At the maximum, operators drive deliberate refining sessions for non-trivial questions, walk the coherence cadence at every commit, and run `/stoa audit` periodically. **Refining is the recommended mode, not a prescribed one. Use as much of Stoa as your work needs.**

**WAL management is autonomous AI.** The AI manages `context_log.md` end-to-end via a three-tier model: **T1** (conversation context, mutable) → **T2** (`context_log.md` file, append-only, AI-autonomous, judged against a class-based yardstick with default-to-no-candidate under uncertainty) → **T3** (git commits, host-integration, operator-driven). The operator does not approve individual WAL entries; the operator's touchpoints are substance, the explicit-log primitive (*"log this"*), `/stoa coherence <subject>` for in-flight checks, `/stoa audit` for retrospective audit of AI's autonomous management, cadence-#6 Superseding-verdict menus, override-ask response when AI surfaces substrate counter-evidence against a directive, harness-level commit permission, and classification override. The propose-confirm pattern that earlier iterations used for WAL writes is dissolved; the AI's judgment is the gate, and the chat-anchor (`[stoa] appended <hex> — <headline>. Consistency: <clean | Superseding <prior-hex> (rollback appended)>. Artifact-coherence: <named-tracked-artifacts | none>.`) is the operator-visible artifact of every write. The `Artifact-coherence:` clause is mandatory on `EC:STRONG` and `EC:DEFERRED` entries (`decision`, `won't-do`, `rollback`, `table`); on `observation` writes it is omitted. Methodology stops at T2; the AI treats `context_log.md` like any other tracked artifact at the git boundary (OP4 — Stoa does not prescribe commit cadence).

For a concrete end-to-end illustration, see [Worked example: a PM brings a customer ask through the system](#worked-example-a-pm-brings-a-customer-ask-through-the-system). A PM brings a customer ask all the way from initial scoping through async cross-role collaboration to phased delivery. Two interactive demos render the show-don't-tell versions: the **[multi-role workflow demo](../demos/workflow-demo.html)** dramatizes the worked example end-to-end, and the **[Aurora-pivot demo](../demos/aurora-pivot-demo.html)** walks through the actual refinement-loop + execution-validated-design + WAL-preserved-supersession arc from the trial (Aurora → DynamoDB).

The proposal name is **Stoa**, after the colonnades of ancient Athens where philosophers and citizens deliberated in public, a structured space for collective reasoning, anchored in place but open to anyone.

---

## Why Stoa exists

Many engineering organizations (Stoa included) are **fully-remote, all-timezones, async-required**. Daily synchronous overlap between any two engineers is small or nonexistent. The org's working culture is async-first, not async-optional.

This makes design (the activity traditionally most synchronous-collaboration-hungry) structurally hard. The product-development industry's default tools assume synchronous design conversations: whiteboards, war rooms, half-day workshops. Async-distributed teams either work around that (someone travels, someone wakes up at 3am, design becomes a single-person bottleneck) or pay the structural cost (drift between docs and code, decisions made in the head of one person, new joiners need a sync handoff before they can contribute).

Stoa exists because *design as a first-class engineering activity* requires an async-friendly substrate, and that substrate hasn't existed. AI-mediated context synthesis over an append-only decision log lets a fully-remote, all-timezones team carry a rigorous design conversation forward without ever needing two people online at the same time.

Every other claim in this proposal (auditability, parallelizability, collaboration, the staggered-tracks model) descends from this root motivation. If the org were colocated and synchronous, simpler patterns might suffice. Most modern engineering orgs are not, and they don't.

---

## Positioning — what Stoa is, and isn't

Stoa is **Stoa's internal methodology for AI-assisted development**, released openly in case other teams find the patterns useful. It is:

- A **methodology + a unified installable bundle** ([`dist/`](../dist/), with per-host payloads under `dist/claude/` and `dist/codex/`) that installs Stoa for every supported host at once and drops into any repo via [`dist/install.sh install`](../dist/install.sh). The runtime composes from editable canonical source under [`src/`](../src/) and lands at the repo root as [`stoa-claude.md`](../stoa-claude.md). Codex ships in beta alongside Claude: the adapter and composed runtime are maintained, and the install mechanics plus the live boot path (the SessionStart hook firing, bootcheck injection, and native-subagent spawn) are validated on a real Codex CLI; skill loading and the behavioral surface (prose-intent routing, the WAL guardrail, drift detection) remain to be confirmed — see [`tests/codex-smoke-test.md`](../tests/codex-smoke-test.md).
- **Not a product.** No commercial roadmap, no pricing, no SaaS surface, no enterprise tier.
- **Not a consulting offering.** No paid implementation help. The proposal, the trial report, the bootstrap, and the slash-command surface are open for anyone to adopt as-is.
- **Not seeking adoption beyond people who find it independently useful.** The primary audience is Stoa engineers. The secondary audience is whoever picks it up because the patterns resonate.
- **Not a competitor to anyone.** Kiro, Cursor, Claude Code, Notion AI, Linear, Confluence: Stoa sits upstream of those (refining decisions before code is written) and consumes whichever of them a team already uses. The lightness story (one file, agent-agnostic, downstream-coder-agnostic) follows from "we wanted low-friction internal adoption," not from a positioning play.

This shapes everything that follows. The seven value-props are framed as *what Stoa's methodology is designed to deliver*, not as competitive marketing copy. The beta v0.1 plan ([Getting started](#getting-started)) is sized for real internal validation, not for go-to-market. Tooling investments are funded by whichever team feels the pain first, not by a budget line item. *(WAL: positioning settled here. See follow-up commit on this proposal.)*

### Stoa is NOT (pattern-match deflection)

What people often assume Stoa is, that it isn't:

- **NOT a new artifact format.** Decision-log artifacts have existed in various forms for years (ADR being the established example; see [Origin and prior art](#the-closest-tradition-architecture-decision-records-adrs) below). The novelty is the operational layer that makes them maintainable at scale, not the file format itself.
- **NOT a strict methodology.** The loose-framework principle is load-bearing. Rigid validators, mandatory schemas, and gate-checks at PR time have repeatedly failed at scale; engineers route around them. Stoa's discipline lives in AI interpretation of loose conventions, not in coded gates that punish experimentation.
- **NOT a replacement for personal AI workflows.** Stoa is the substrate (the WAL + the coordination primitives). Per-engineer AI workflow customization (skills, rules, command surfaces, personal slash-command sets) composes over the substrate without conflict. Operators extend Stoa per-repo by appending to `CLAUDE.md` (or `AGENTS.md`) after the dispatcher block — those files are operator-owned and never touched by Stoa upgrades.
- **NOT waterfall.** Refining sessions are free-form; decisions can be revisited freely via `rollback`; PoC findings reshape design before commitment. Stoa captures the design-implementation loop in both directions, not a single forward sweep. (Worked example: the Aurora pivot in [Scope](#scope--stoa-is-upstream-of-agentic-implementation) below.)
- **NOT a synchronous-team tool.** Async-required is the target. Synchronous teams may find Stoa useful; async-required teams need it. Different design space, not different artifact format.
- **NOT an agentic coder.** Stoa doesn't write code. Its job is to make sure the agentic coder gets the most detailed spec possible, one that reflects Product Management's intent and is consistent with the engineering organization's architecture and design. See [Scope](#scope--stoa-is-upstream-of-agentic-implementation) for the full framing.

These deflections are pattern-match noise to clear out of the way. The substantive scoping (evidence gaps, what's not yet specified) lives further down in [What this proposal does NOT claim](#what-this-proposal-does-not-claim).

---

## Scope — Stoa is upstream of agentic implementation

Stoa is **not an agentic coder.** It doesn't write code. **Its job is to make sure the agentic coder gets the most detailed spec possible, one that reflects Product Management's intent and is consistent with the engineering organization's architecture and design.** Many teams will adopt agent-driven coding workflows (Claude Code, Cursor, Codex, [Kiro](https://kiro.dev/), ...) at their own pace; each picks a flavor that fits its stack and risk tolerance. Stoa stays out of that fight. The hard problem Stoa solves sits **upstream**: the multi-role design refinement loop, aligning PMs, DevManagers, architects, and devs on *what to build and why*, async, across timezones, with traceable rationale. **This isn't a scope limitation; it's where the value is.** *"Make me an online shopping site"* produces a vibe-coded toy because the upstream cognitive work hasn't happened. Stoa is what produces the refined spec that turns the same agentic coder into a production-quality output.

The word "loop" is doing real work in that sentence. Stoa is not a one-way pipeline that ends when implementation begins. The [staggered-tracks model](#the-staggered-tracks-model) has design slightly ahead of planning slightly ahead of execution, but discoveries flow in both directions. Implementation surfaces real-world constraints that can and do invalidate design assumptions, sometimes substantially. **The boundary is porous;** Stoa's WAL primitives (append-only entries + `rollback` for supersession) make the round-trip clean rather than chaotic. This is the staggered-tracks model in action when execution finds something design didn't see, not a special escape hatch.

> **Concrete from the adopter PoC.** The original metadata-and-scheduling design was Aurora + pg_cron + plpython3u. Implementation surfaced that AWS had removed plpython3u from Aurora 15+. Not a small tweak; it forced a full-rethink-back-to-design pass that landed on DynamoDB + EventBridge Scheduler + Lambda. The WAL captured both the original decision and the supersession, the rationale for each, and the alternatives reconsidered the second time around. A future reader sees the whole arc, not a sanitized *"we picked DynamoDB"* with no thread to the design history.

There's also a positive directional claim: **Stoa makes downstream agentic implementation work better.** Tools like Kiro consume a spec as their input. They implement well when given a refined one, less well when the spec under-specifies edge cases, integration touchpoints, or inter-role tradeoffs. **Producing the refined spec is itself substantial cognitive work (multi-angle, multi-perspective, often multi-human), comparable in difficulty to writing well-architected code.** Stoa is the multi-role refinement loop that produces that spec; Kiro-shaped tools then implement against it. Concretely: agents implement well when given concrete acceptance criteria plus PoCs that have validated the load-bearing design choices (see [Execution-validated design](#6-execution-validated-design)). Same PoC: Phase 5 was decomposed into v2 sub-phases with a data-catalog preflight spike before any implementation began; implementation quality jumped substantively once the spec was that refined. (See [Kiro in Origin and prior art](#the-closest-agentic-implementation-cousin-kiro-kirodev) for the full Stoa↔Kiro complementarity treatment; [`9d2f8a3`](../context_log.md#2026-05-09--observation--authors-ivanclaudeopus471m--9d2f8a3).)

**Net.** Stoa scopes itself to the human-collaboration problem (multi-role design refinement). Agentic implementation tooling is the team's choice. The loop boundary admits round-trip; execution-side discoveries flow back through the WAL when they need to, and the next-cycle agentic implementation gets a better-validated spec for it. *(WAL: [`8c4e2d1`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--8c4e2d1))*

---

## Empirical anchor — the adopter PoC

Stoa was forged on a real, non-trivial PoC: a large multi-service adopter project's multi-tenant compute integration with a data-warehouse system. The architecture is production-grade for financial-sector enterprise customers, with per-tenant VPC isolation, cross-account data-catalog integration with per-user credential vending under KMS-asymmetric policy, multi-VPC ENI attachment at runtime for warm-pool assignment, an 8-table DynamoDB substrate for metadata and scheduling, six build phases from bootstrap to teardown, all running against a real customer data catalog. **One engineer designed and built the entire end-to-end working demo using Stoa as the methodology backbone. The design-through-Phase-4 milestone landed in ~6 days; full Phase 5 + Phase 6 extended a couple of weeks beyond.** The WAL kept design and implementation in lockstep, AI absorbed the documentation maintenance cost, and execution-validated design caught load-bearing pivots (Aurora → DynamoDB) before they became technical debt. Whether the time-to-result represents a real speedup is for the reader to judge against the scope above.

Two patterns from the trial are referenced throughout this proposal: the [Aurora pivot](#scope--stoa-is-upstream-of-agentic-implementation) and the [Phase 5 sub-phase decomposition](#6-execution-validated-design). The latter is concretely the kind of refined sub-phased spec that downstream agentic tools like Kiro implement cleanly. *The spec is the load-bearing artifact*, and producing it is itself the multi-role cognitive work Stoa makes affordable. The full trial report is held privately by the adopter project's team.

---

## Core value-props of Stoa

Seven claims Stoa is designed to deliver. Each is a separable benefit. A team that adopts Stoa for one of them tends to surface the others within weeks of use.

> **Confidence calibration.** Two of the seven (V1, V6) were exercised end-to-end during the solo trial and the evidence sits in the adopter project's trial report (held privately by that team). The other five (V2 async-native, V3 threaded refinement at scale, V4 solo catch-up across multiple operators, V5 long-lifecycle context preservation, V7 self-consistent state under pre-commit / post-decision cadences) are *designed for* but not yet exercised under multi-role load. Each section below carries an inline tag making this distinction explicit. **Beta v0.1 is the mechanism for closing that gap.** See [What this proposal does NOT claim](#what-this-proposal-does-not-claim).

### 1. Design as auditable engineering, alongside the code

*Status: exercised solo on the adopter trial (46 WAL entries, full supersession graph). Multi-author auditability is what beta v0.1 will surface.*

Every architectural decision carries attribution (who decided), rationale (why), alternatives considered (what was rejected), and a traceable supersession history (what later changed and why). The WAL is the audit trail. Future readers (humans or AI) can ask *"what was decided about X, by whom, when, and why?"* and get a real answer rooted in the WAL. Design lives next to the code in the same git repo, not in a separate ungoverned silo (Google Drive, Notion, Confluence). Drift is detectable; alignment is enforceable through standing conventions inherited from the trial methodology.

The reframe Stoa offers:

> There is no longer an excuse not to produce and maintain a rigorous design doc. Every feature **will have a design doc reference**.
> And it almost just naturally falls out of the process itself, it is automatically maintained, grounded in auditable decisions and **always** up to date.

Design becomes to product development what testing became to code: a first-class activity with tooling, conventions, audit trails, and a culture that expects it to exist. The cost of *maintaining* a design has historically been the killer; AI absorbs that cost. What's left is the cost of *making* the decisions, which the team has to do anyway. Stoa adds rigor without adding net effort.

### 2. Async-native by construction

*Status: designed for; not yet exercised under multi-role load. Beta v0.1 is the test.*

The methodology is designed to assume no synchronous overlap. Every primitive (refining sessions, the WAL, ask/stoa respond handoffs, solo catch-up, multi-laptop reconciliation) is intended to work without two people being online at the same time. Slack is the notification fabric, not a synchronous transcript; the repo + WAL is the durable shared state. Synchronous moments (Zoom calls, war-room debugs) remain available and useful, but they are *acceleration*, not *prerequisite*.

This is the value-prop that makes Stoa aimed at fully-remote, multi-timezone organizations. Other methodologies degrade gracefully when synchronous collaboration is unavailable; Stoa is built for that condition as the default. (*The Slack adapter that this property leans on is named but unspecified; concrete adapter mechanics are part of the v0.1 work.*)

### 3. Staggered + threaded refinement

*Status: staggered tracks were exercised solo on the trial; threaded refinement at scale (multiple concurrent threads with AI-mediated reconciliation) is designed for, not yet exercised.*

Design slightly ahead of planning slightly ahead of execution, with refining loops at every level. Multiple concurrent refinement threads on different topics within the same layer. AI is intended to be the reconciliation substrate — when two parallel threads touch the same surface, the goal is for conflicts to surface on the in-progress tracks, not after both have hardened into incompatible commits.

This is the methodology's signature mental model. See [The staggered-tracks model](#the-staggered-tracks-model) for the deep treatment.

### 4. Solo catch-up as a first-class pattern

*Status: exercised solo on the trial (resuming tabled threads against the WAL); cross-operator catch-up (a different operator picking up a thread someone else started) is designed for, not yet exercised.*

The intent: anyone (a new joiner, a returning teammate, a participant pulled into a thread mid-conversation) onboards by themselves, async, over the WAL + Slack-attached snippets. Today's pattern across most teams is the synchronous-handoff model: find a person who knows, schedule a meeting, have them brief you. Stoa's design is for that bottleneck to disappear: the WAL holds the durable record; AI synthesizes "where are we" on demand.

The same pattern handles three sub-cases that look distinct but share the substrate:

- A new participant joining a thread mid-flow.
- Someone resuming a topic that was tabled weeks earlier.
- A new team member onboarding to a long-running project.

### 5. Context survives delivery

*Status: the structural property (WAL is append-only, rationale chain remains readable) is exercised by construction; the long-lifecycle behavior at month 12 / month 36 is unverified, too early in the trial timeline to know.*

When a feature ships, the WAL and design docs already hold the full reasoning chain that produced it. Slack snippets that helped during refining become non-load-bearing scaffolding — they age out gracefully (no automated GC needed). Future iteration on the feature, customer feedback that asks *"why was this designed this way?"*, and new-joiner onboarding to the codebase all read the same record. Nothing has to be reconstructed from human memory.

This is the long-tail value-prop. The acute pain of "we need design discipline now" gets you in the door; the durable benefit is what you find six months in, when the original architects have moved on and the customer-feedback cycle starts asking hard questions. *(WAL: [`d4e7a91`](../context_log.md#2026-05-08--decision--authors-ivanclaudeopus471m--d4e7a91), [`4f8c3a2`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--4f8c3a2))*

### 6. Execution-validated design

*Status: exercised end-to-end on the trial. Aurora pivot ([scope](#scope--stoa-is-upstream-of-agentic-implementation)) and Phase 5 data-catalog preflight spike are concrete instances. This is the value-prop with the most evidence behind it.*

The classic mental model (*"implementation is expensive, so design must be done well first"*) no longer holds when AI makes building a working PoC of a design choice cheap. **The corollary flip: every load-bearing design decision should be backed by a working PoC before it commits.** Architectural decisions get a small spike against real fixtures; UX decisions get a working prototype (the HTML demo for this proposal is exactly such an instance: execution-validated UX design dogfooded); API decisions get a mock server + client; data-model decisions get a toy migration.

The [threaded-refinement dimension of the staggered-tracks model](#horizontal-threading--multiple-parallel-refinements) is what makes this scalable: multiple concurrent design tracks can each spawn their own PoC track, with AI managing reconciliation when PoC results invalidate or refine sibling decisions. Without threaded refinement, PoC-backed design is a sequential bottleneck; with it, it's a parallel exploration. This value-prop is also what underwrites the positive directional claim in [Scope — Stoa is upstream of agentic implementation](#scope--stoa-is-upstream-of-agentic-implementation): execution-validated design produces refined sub-phased plans + PoC-validated decisions, which is exactly what downstream agentic implementation needs to perform well. *(WAL: [`3b9f7a6`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--3b9f7a6))*

### 7. Self-consistent state, by construction

*Status: pre-commit drift walks were exercised solo on the trial; the post-decision propagation pass and `/stoa audit` cadence are designed but lightly exercised. Whether AI-discipline-only enforcement holds at multi-author scale (vs. needing deterministic hooks) is one of beta v0.1's load-bearing questions.*

Addresses the recurring stakeholder question (*"I saw the plan / demo / summary last week; is that still valid?"*) by construction. The intent: **anything in the repo is current.** HTML demos reflect current consensus, not last-week's stale version. Executive summaries update on every commit (effectively hourly, not weekly). Design docs are always-true relative to settled WAL state. The exec who keeps asking *"is that still the plan?"* gets a 30-second answer instead of a 2-day round-trip with the architect.

This is **distinct from value-prop #5** (Context survives delivery). #5 is forward-looking *durability*: when execution lands months later, the WAL still holds the rationale chain that produced the work. #7 is *current-state coherence* at any point in time: at any commit, every artifact in the repo is mutually consistent with the others. Coherence cadences enforce alignment between canonical sources and derivative artifacts (summaries, demos, runbooks) at seven trigger events: pre-commit drift walk, post-decision propagation pass, pre-commit WAL audit, pre-compact/pre-clear WAL audit, operator-triggered `/stoa audit`, content-triggered WAL semantic-merge audit (the `.stoa/audit-cache` coverage delta — `WAL − covered` certificates — fires catchup via the next-session bootcheck coverage scan or stale-cache rejection on the next T2 write, catching every integration path including server-side PR merges and fresh clones; `/stoa pull` is the operator-driven pre-merge halt-point UX), and end-of-implementation WAL audit (four sub-steps: (a) T1 audit + (b) session-aggregated artifact-coherence nudge driven by anchor-level `Artifact-coherence:` flags + (c) execute-phase substrate sweep that elevates substrate-grounded findings to WAL entries by default + (d) a forest-grounded DONE check that grounds *"is this done?"* against the EC:STRONG decisions the work committed to, before any arc-completion language). See [`stoa-claude.md`](../stoa-claude.md) §"Coherence cadence". Most are AI-discipline-based, the deliberate stress-test of the *AI as interpreter of loose framework* premise; one is structurally reinforced — cadence #3 (pre-commit WAL audit) by a deterministic git-hook backstop after beta data showed it degraded under sustained commit pressure. The classification step across all cadences routes through a unified `/stoa coherence` primitive — one procedure for what used to be six separately-evolved code paths. AI absorbs the maintenance cost that has historically been the killer of self-consistent docs. Combined with #6, the HTML demo for this proposal dogfoods both: execution-validated UX design that's also always-current. *(WAL: [`5d1c8b3`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--5d1c8b3), [`d5a8f10`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--d5a8f10), [`b0122b1f`](../context_log.md#b0122b1facf5413eaaf25896fbc0c706--decision--2026-05-18))*

---

## What this proposal does NOT claim

Promoted up-front so the reader meets the honest scoping before the long worked-example fiction. The methodology is **first-attempt, evidenced on a single solo trial**; everything below is a known gap. Beta v0.1 (see [Getting started](#getting-started)) is the mechanism for closing them.

- **A multi-author scaling proof.** The trial was solo. Multi-author Stoa is designed-for but not battle-tested. Scenarios 3–5 of bootstrap describe the entry points; real adoption will surface gaps.
- **Domain generalization.** The trial was infrastructure-heavy with strong external docs to ground in (AWS plus a data-warehouse integration). For domains with weaker public-doc anchors (proprietary internal systems, novel research areas), some patterns may need adapting.
- **Long-lifecycle properties.** What does a Stoa project look like at month 12? Month 36? Decision-log archaeology, invariant drift, summary-doc rot — unverified at long horizons.
- **A finished tooling stack.** The unified [`dist/`](../dist/) bundle (composed from [`src/`](../src/) via [`build/compose.sh`](../build/compose.sh)) is the deliverable; it installs Claude and Codex hosts in one pass. Codex ships in beta with install mechanics and the live boot path (SessionStart hook + bootcheck injection + native-subagent spawn) validated on a real Codex CLI; skill loading and the behavioral surface remain to be confirmed ([`tests/codex-smoke-test.md`](../tests/codex-smoke-test.md)). Skills (`/stoa init`, `/stoa orient`, `/stoa backfill`), hook templates, integration adapters, and validators are follow-on work.
- **A measured "Stoa makes downstream agentic implementation work better" claim.** The directional claim in [Scope](#scope--stoa-is-upstream-of-agentic-implementation) is plausible and pattern-evidenced (Phase 5 sub-phase decomposition + data-catalog preflight); a controlled comparison against the same project without Stoa is not part of this proposal.
- **Independence from one specific AI provider.** The methodology depends on AI-as-interpreter being reliable. Provider churn, model deprecation, and prompt-cache evolution all touch the substrate; the loose-framework principle is the bet that any sufficiently-capable model works, but that's a bet, not a proof.
- **A multi-role worked example backed by evidence.** The PM/dev-manager/architect/developer flow that follows this section is illustrative, not a transcript. It shows the *intended* shape of the cross-role refining loop. Whether teams actually behave that way under real deadline pressure is what beta v0.1 will tell us.

The full taxonomy of unaddressed sub-threads — workflow gaps, integration specs, multi-project / cross-system, tooling lifecycle — is in [What's not yet specified](#whats-not-yet-specified) further down. *Read both before you decide whether to take Stoa seriously.*

---

## Worked example: a PM brings a customer ask through the system

To make Stoa concrete, here is a realistic flow against the adopter PoC project (the multi-tenant compute ↔ data-warehouse integration the methodology was forged on — see [Empirical anchor](#empirical-anchor--the-adopter-poc)). Every step has a literal sequence; each is annotated with a *today / Stoa* delta.

**Cast:**

- **Priya** — Product Manager.
- **Marcus** — Development Manager.
- **Diego** — Architect.
- **Lena** — Developer.

**Scenario.** Customer X wants to use the product to train custom LLMs (super-alignment work). Customer X has a CSP-side deal for GPU instances and wants to bring those rather than use the platform's compute. Priya's questions:

1. Is this scenario supported by the product today?
2. If not, what are the implications?
3. What design decisions would we have to make to accommodate it?

**Assumed setup:** the project is already running on Stoa — `CLAUDE.md` installed, WAL maintained, Slack channel bound to the repo, four roles present in the channel.

### Phase 1 — Priya in solo flow

Priya checks out the repo and runs Claude. She asks her three questions in plain English. Claude reads the WAL, the design doc, and the canonical artifacts; produces a grounded answer; offers to render an architecture diagram from the current state to help Priya visualize. Priya iterates: she asks clarifying questions, requests a sequence diagram for the warm-pool assignment chain, asks *"where would external compute even hook in?"*. Within ~30 minutes she has an accurate mental model of where the product sits and where the gap is: external compute is not supported; the closest design assumption (single-account warm pool inside the platform's AWS account) actively conflicts with the customer's request.

> *Today, this phase doesn't really exist.* The PM either doesn't know enough to scope the question (and pings someone synchronously to start), or guesses (and gets the framing wrong). Either way, the conversation that *should* be informed by current product state starts under-informed.
>
> *In Stoa,* Priya builds the right context herself, alone, in her own timezone, in less time than it takes to schedule a meeting. She shows up to the next phase already-correct.

### Phase 2 — Solo → Shared handoff

Priya is ready to pull Diego in. From her Claude session she runs `/stoa ask @diego`. Claude generates a 1–3 paragraph context summary from the live session (gap diagnosis, current-state diagram, the specific surface Priya thinks would be affected) and attaches it as Slack note files in the project channel. Diego gets pinged with the question, the snippets, Priya's git HEAD, and the question ID.

> *Today, this phase is a Google Doc.* Priya copy-pastes summaries, hand-curates context; the doc may or may not align with what's currently in code; the conversation happens in a doc that isn't connected to the codebase. Round trips are expensive; the architect spends time correcting the framing before answering the question.
>
> *In Stoa,* the context Priya built lives in her Claude session, gets summarized faithfully, and is delivered to Diego with a git HEAD reference for alignment. Diego opens his own Claude session over the same repo at the same HEAD; the context is grounded by construction.

### Phase 3 — Shared flow with Diego (async or sync)

Diego responds when his timezone allows. Either asynchronously over Slack (his Claude session reads the snippets + WAL + repo, drafts a response, Diego refines and posts) or synchronously on a Zoom call where both are looking at the same repo. The substrate is the same; the cadence is whatever fits.

The conversation explores three potential approaches to support external compute. At one point Diego asks Claude to spin up a 30-minute PoC of one approach — extending the warm-pool reconciler to launch instances against a customer-provided AWS account via a per-tenant `AssumeRole` plus reused launch templates. The PoC immediately surfaces a sharp trade-off: the cross-account credential refresh path is materially harder than the design assumed, which becomes a load-bearing data point in the conversation. *Execution-validated design ([#6](#6-execution-validated-design)) in action — implementation didn't begin without the design first being PoC-tested.*

None of the three approaches is a clean fit; trade-offs cluster differently across them. Both Priya and Diego agree this is a non-trivial design question that should be tabled for the next planning round, not decided in this thread.

### Phase 4 — Bringing Marcus in for funding

Diego and Priya realize the question now has a funding dimension: any of the three approaches needs developer time. They pull Marcus in.

Marcus is in a different timezone and not online. He picks the thread up later. Before joining the shared conversation he opens his own Claude session, ingests the snippets and the WAL, and **catches up by himself** — solo catch-up. He may even add an observation to the WAL while doing so (e.g. recording a known capacity constraint that affects which approach is feasible). Then he joins the shared thread with full context.

> *Today, this is the painful step.* Marcus gets pinged; he asks Diego or Priya to brief him; someone has to summarize the current state for him; the conversation pauses. If Marcus's timezone doesn't overlap, it pauses for a day.
>
> *In Stoa,* Marcus is a new participant who self-serves into the conversation. The team's productivity is preserved.

For a simpler version of this scenario, Marcus might say *"approach B is the right fit; I have Lena available next sprint."* For our scenario the funding picture is also complex. The conclusion: three viable approaches, no lock-in, tabled for the next planning round.

### Phase 5 — Tabled for the planning round

The thread settles into a `table` WAL entry. Body: the three approaches, the trade-offs identified, the open questions, the constraint Marcus flagged. Resumption pointers: revisit at the next planning round; ping when customer X commits to a delivery timeline.

> *Today, this state often gets lost.* The Google Doc gets archived; the Slack thread scrolls off; the rationale for "we considered these three" decays into "I think we talked about this once."
>
> *In Stoa,* the table entry preserves not just the choices but the thought process — what was rejected, what was conditional, what triggered the deferral. Anyone reading the WAL 2 weeks later sees the active topic and the reasoning.

### Phase 6 — 1–2 weeks later, revisited

Planning round arrives. Anyone in the team can read the WAL and catch up on the tabled topic without anyone briefing them — solo catch-up, same pattern Marcus used to join, now used to resume. The team converges on approach B.

### Phase 7 — Design-to-execution

Diego and Lena continue the conversation in the shared flow, refining the design into phased deliverables. Priya and Marcus can stay loosely engaged (they read the WAL on their own time) or fully passive; they do not have to be active in the thread. The phased plan lands as a `decision` WAL entry: phases, dependencies, acceptance criteria. Priya and Marcus read it and sign off (each writes a small assent entry, or is named as Participant on the plan entry); the design is committed.

A Jira task with sub-tasks is created for the work. The company-wide planning channel gets a notification post: link to the Jira, link to the WAL entry, link to the original Slack thread for anyone who wants the full backstory.

> *Today, the planning hand-off is its own paper trail.* The design doc says one thing, the Jira says another, the Slack thread that informed both is gone. Reconciliation is human work.
>
> *In Stoa,* the WAL entry, the Jira, and the planning announcement reference each other. The design rationale is one click away from anyone who lands on the Jira.

### Phase 8 — Delivery and beyond

Lena ships the work over the planned phases. Each phase commit must update the WAL (the project's discipline cadence enforces this); phased delivery and design rationale stay aligned by construction. By the time the feature is in production, the WAL + design docs hold the full reasoning chain.

Mid-cycle, an exec drops into Priya's DMs: *"I saw the demo of approach B at the all-hands two weeks ago, is that still the plan?"* Priya doesn't have to remember; she opens the project and the answer is one click away. The HTML demo at HEAD reflects the current consensus; the executive summary updates on every commit; the WAL entry shows whether the plan has shifted since the all-hands. A 30-second answer instead of a 2-day round-trip with the architect. *Self-consistent state by construction ([#7](#7-self-consistent-state-by-construction)) in action.*

When customer X provides feedback six months later (*"we want to extend this further"*), the team reads the original WAL entry, sees the rejected alternatives, sees the constraints that shaped the decision, and can make an informed iteration without re-litigating settled points. When a new engineer joins the project, they read the WAL and see not just *what* was built but *why*. The Slack snippets that helped during refining are still there but no longer load-bearing; they age out gracefully without anyone GC-ing them.

This phase is invisible at the time the work is happening, which is exactly why most teams don't pay for it. Stoa pays for it as a side-effect of the discipline that solved the immediate problem.

---

## The staggered-tracks model

The mental model that makes Stoa's value-props cohere. Two dimensions, both load-bearing.

### Vertical staggering — design, planning, execution

Three tracks run concurrently:

- **Design** — what should we build, and why?
- **Planning** — when, by whom, broken into what units?
- **Execution** — actually building it.

Each track is slightly *ahead* of the next. Design has thought through next quarter's features while planning is committing this quarter's work to people; planning has named next sprint's deliverables while execution is shipping this sprint. The staggering is intentional. Pure waterfall freezes design before planning starts, which produces stale designs the moment execution discovers something. Pure agile collapses the three (design ↔ planning ↔ execution all at once), which is fast for small features but loses the thread on multi-quarter architectural arcs. Staggered tracks preserve the architectural arc *and* the responsiveness.

Refining loops happen at every level. Within a design topic (*"what's the right primitive for X?"*), within planning (*"how does this decompose?"*), within execution (*"what's the concrete implementation?"*). Refining loops *also* span the pipeline: a discovery during execution can trigger a planning revision can trigger a design revision. Each loop's settled outcome lands as a WAL entry; the chain stays traceable backward.

### Horizontal threading — multiple parallel refinements

The classic gotcha: designs are big; people focus on smaller parts; local optimization misses ripple effects. Today's mitigation is heroic; one person holds the whole thing in their head and catches conflicts at integration time. That scales linearly with that person's bandwidth, which is the wrong scaling.

Stoa supports multiple concurrent refinement threads on different topics within the same layer. The `branch` WAL entry type is the visibility primitive: when a refining session opens (and especially when one branches), the entry announces the topic as in-flight. The refining session itself lives in the live conversation (per the no-on-disk-file principle), but its **existence** is visible to anyone reading the WAL. AI is the reconciliation substrate: when a refining session touches a surface that another active branch also touches, AI surfaces the cross-impact on the active session.

This is also what makes [Execution-validated design](#6-execution-validated-design) scalable: multiple concurrent design tracks can each spawn their own PoC track, with AI handling reconciliation when a PoC's results refine or invalidate sibling decisions.

The meaningful claim:

> Stoa catches incompatibilities and cracks **early**, on in-progress tracks, not after both have hardened into incompatible commits.

This is genuinely novel relative to ADRs (sequential, no parallelism) and design-log (single-author). The branching infrastructure was already in the primitives; this section elevates the strategic value-prop of using it.

### How the two dimensions interact

Vertical staggering and horizontal threading compose. A snapshot of an active project might show:

- **Design layer:** three branches active, refining the API surface for X, the storage model for Y, and the security posture for Z.
- **Planning layer:** two branches active: phased plan for feature A (which descends from a settled design from last quarter), and capacity planning for next sprint.
- **Execution layer:** the team is shipping feature A's phase 2.

Any of the three design branches might intersect with feature A's planning (e.g. if Y's storage refinement changes the storage assumptions phase 3 was going to make). AI sees both, surfaces the conflict on whichever session is active, and either reconciliation lands as a `reconciliation` WAL entry or one of the branches re-frames around the other.

The companion HTML demo renders this visually as a parallel mental-model layer alongside the literal UI of the workflow.

### Implication: Slack snippets age out gracefully

A downstream effect of this model: by the time execution lands, the WAL and design docs have absorbed all load-bearing context from the refining threads that produced the decisions. The Slack snippets that ferried context between participants during refining are no longer load-bearing; nothing future-relevant requires them. They can age out via Slack's normal retention without explicit GC. The methodology does NOT propose a snippet-archive primitive; none is needed. *(WAL: [`2a7f4e5`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--2a7f4e5))*

---

## Three audiences — what each role gets

Stoa is designed to work for every role in the product-development cycle, not just the architect. Each of the four roles in the worked example gets a distinct value-prop slice.

### Product Manager (Priya)

Build correct context fast, alone, in your own timezone. Today's PM workflow leans on synchronous handoffs (*"can you brief me on X?"*) and disconnected docs (Google Drive, Notion). Stoa replaces both with self-service grounding over the actual code + WAL. The PM walks into the next conversation already-informed, which means the conversation gets to the substantive question faster and produces better answers. Customer asks no longer require a triage-meeting before they can be scoped.

### Development Manager (Marcus)

See active design and planning state without interrupting people. The DevManager's hardest problem is allocating capacity against a shifting priority list; Stoa's WAL surfaces both committed decisions and in-flight refinements (`branch` entries) so the funding picture is grounded in current state, not stale Jira. Sign-off on phased plans is a small WAL-entry act, not a meeting. Cross-team coordination converges on the WAL as the canonical state, eliminating the "who has the latest version of the plan?" question.

### Developer (Lena)

Inherit the full reasoning chain when picking up the work. No more *"why did we do it this way?"* archaeology; the WAL records the rationale at decision time. New developers onboard via solo catch-up: read the WAL, build the mental model, ask grounded clarifying questions. Productive day-1 instead of productive day-30. When unexpected production discoveries force a design revision, the original constraints are right there to argue against or with, not lost to the original-author's memory.

### Architect (Diego)

Carry multiple parallel design refinements without losing the thread on any. AI-mediated reconciliation catches cross-impact on in-progress tracks, so the architect's mental load shifts from "remember everything" to "review what AI surfaces." Async refining lets the architect serve a remote-distributed team without becoming the synchronous bottleneck. The architect's scarcest resource (uninterrupted thinking time) gets defended by construction.

---

## Second-order benefits — Stoa's self-improvement loop

The WAL is data **about Stoa itself**, not just about the project. Stoa is a methodology in active iteration; the WAL of every project that adopts it is a feedback signal for whether the methodology is producing the outcomes it claims. The same AI-as-interpreter pattern that lets a future reader synthesize *"what was decided about X"* lets the methodology synthesize *"is the methodology working?"*

These benefits compound at scale. They are not what gets you in the door (those are the seven [first-order value-props](#core-value-props-of-stoa)). They are what keeps the methodology relevant at month 12, month 36, project 5, project 50.

### 1. Did the right collaborations happen at the right times?

Synthesis target: when the AI suggested an `/stoa ask @<handle>` handoff, did the operator follow through? When customer-facing decisions settled, did the WAL show PM Participants? Are refining sessions reaching conclusion without pulling in roles the WAL retroactively shows would have caught a known issue?

What this tells us about Stoa: the `/stoa ask` mechanism may be too friction-heavy; the discovery problem (operators don't know who plays a role) may be biting; AI may not be suggesting handoffs proactively enough. Methodology fixes follow.

### 2. Are decisions reaching conclusion efficiently?

Synthesis target: which decisions take longest to settle, and why? Did they get tabled and never resumed? Did they go through `branch` → reconvergence or straight-through? Did cross-laptop decisions take 3× longer than equivalent-scope solo ones?

What this tells us about Stoa: a class of decision is consistently slow → bootstrap should suggest specific structure for it. Tabled topics never resume → the resumption-trigger mechanism is broken (escalate `/stoa list-open-threads`). Cross-laptop handoff cost is real → snippet packaging or catch-up tooling needs work.

### 3. Is Stoa transferring context to new joiners?

Synthesis target: time from a new joiner's first WAL Participant entry to their first Author entry; time from first solo session to first `/stoa ask` handoff; citation distance vs. project average.

What this tells us about Stoa: the stoa.md isn't enough → strengthen `/stoa orient`. Solo catch-up is being skipped → the catch-up mechanism needs to be more proactive. The WAL is hard to read for outsiders → suggest summary-doc cadences in the bootstrap.

### 4. Cross-project decision pattern matching

Synthesis target: when a new question opens, surface structurally-similar prior decisions from any project the org runs.

Compounds with adoption: one project's WAL doesn't give pattern-match value; 50 projects' WALs do. As adoption grows, the marginal cost of decision-making drops because past similar decisions surface automatically. The feedback loop also tells the methodology where its terminology is failing: when AI can't cluster across WALs because terms are project-idiosyncratic, the suggestion menu / starter conventions need sharpening.

### 5. Audit / compliance auto-generation

Synthesis target: regulator-readable rationale documents derived from WAL data.

For regulated industries (finance, health, gov), the decision trail for compliance reviews is an enormous manual effort today: engineers and auditors writing post-hoc rationale from oral history and Slack scrollback. Stoa's append-only, attributed, refs-cross-linked WAL **is** the compliance trail; AI renders it into whatever format the regulator wants. The act of generating these reports also surfaces gaps (entries lacking rationale, alternatives, or attribution) which feed back into the methodology's discipline.

### The unifying thread: Stoa improving Stoa

The WAL is data about *what worked*, *what didn't*, *what got stuck*, *what got missed*. Stoa applies its own discipline to itself: every methodology version is informed by the WAL data of projects running the previous version. Calendar-based versioning (*"Stoa as of 2026-05"*) becomes a meaningful evolution path because each version draws on real-use signal from its predecessor.

Stoa is not a static methodology; it is a methodology that gets better the more it gets used. *(WAL: [`e4a7c3b`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--e4a7c3b))*

---

## Where decisions live today

In most teams I've worked with, decisions are scattered across surfaces:

- **Slack threads.** Fast and conversational, but ephemeral; unsearchable in practice once a thread is a few weeks old.
- **Zoom calls.** High-bandwidth, no durable record unless someone takes notes (and those notes typically end up in another scattered surface).
- **Google Docs with comments.** The closest current cousin to Stoa's intent: a structured-ish document with comments that ping participants on Slack for async input.
- **The repo.** Rarely the home for decisions; usually code, plus maybe a stale design doc that nobody reads.

The Google-Docs-with-Slack-pings workflow is what motivated Stoa's multi-role collaboration design. It actually works *for the active phase* — people get notified, respond async, the doc serves as a focal point. But it has three load-bearing failures the moment the active phase ends:

- **Auditability rots.** Comments get resolved and disappear. The doc gets rewritten. The decision trail evaporates within months.
- **Disconnected from code.** Docs live in a separate system from the codebase; references to "this part of the system" rot as the system changes.
- **Conversational, not focused.** Comments are *conversation*. What actually *settled* often isn't recorded as such — readers have to reconstruct it from threading.

Stoa inherits the spirit that works (notification-driven async collaboration, focal-point document, comment-as-question pattern) and fixes those three failures: the WAL is auditable by construction (append-only, attributed); the repo is the home, not a separate doc; refining-session discipline separates conversation (ephemeral) from settled-decision (durable).

The Slack integration in Stoa is the auditable, code-anchored, focus-keeping descendant of the GDocs-comment-pings-Slack workflow — same notification fabric, same async posture, but with a durable trail and the code as the anchor.

---

## The loose-framework principle

> *Approach the work as a set of refinement activities which produce a sequence of decisions.*

Stoa is **loose by design**. Settled outcomes get recorded in the WAL; in-flight work stays fuzzy. The AI is the interpreter that makes sense of state and outcome on demand, not a strict-schema enforcer.

Concretely, this means:

- **No rigid sub-typing** where the type would force premature category judgments. Record the substance; let interpretation happen later.
- **No mandatory persona enumeration.** Stoa supports PM / dev / architect / exec / oncall / test / UI roles, but doesn't require a project to declare them. People play whatever role fits the moment.
- **No prescribed workflow style.** Stoa is *below* the workflow layer (TDD, agile, kanban, whatever) and orthogonal to it.
- **Fixed-shape conventions exist** (entry types, actor grammar, founding principles) only because they pay for themselves at read time. The set is small.

What stops the methodology from collapsing into chaos under that looseness? **AI-as-interpreter.** A future reader (human or AI) ingests the WAL + repo state + attribution and synthesizes "where are we" without needing every decision pre-categorized. The opinionated core gives the AI enough scaffolding to do that synthesis reliably; everything else stays free.

The trade-off this principle accepts: Stoa does not produce machine-checkable proofs of consistency. It produces a high-fidelity decision trail that AI can interpret. For multi-role product development teams, that's the right trade. *(WAL: [`c8b4d09`](../context_log.md#2026-05-08--decision--authors-ivanclaudeopus471m--c8b4d09))*

**Adoption is dial-able.** The loose-framework principle extends to adoption itself; operators choose how much of Stoa to engage. At the **minimum**, Stoa sits in the background. The AI watches for substantial decisions during normal work and proposes WAL entries when something looks settled; operators accept or decline. No deliberate refining sessions, no scheduled coherence walks. At the **maximum**, operators drive deliberate refining sessions for non-trivial questions, walk the coherence cadence at every commit, and run `/stoa audit` periodically. The full pattern produces the deepest specs and the strongest code-coupling guarantees, but **even the minimum already beats no methodology**. A casual decision log with AI-mediated lookup is far more useful than nothing. **Refining is the recommended mode, not a prescribed one. Use as much of Stoa as your work needs.**

**Stoa's opinionation, owned explicitly.** The loose-framework principle is sometimes read as *"Stoa has no opinions"*; that's wrong. Stoa is **loose about implementation, opinionated about coordination primitives.** The asymmetry is intentional. What's opinionated: the WAL guardrail's append-only contract, the canonical entry header form, the seven-trigger coherence cadence, the founding principles (no on-disk refining sessions, stable hex IDs, refining-narrows-not-just-loops), the six entry types, and (v0.6.0+) the Agent-first quality principle and the unified Superseding/Converging/Adjacent vocabulary for all coherence operations. What's loose: how operators drive refining sessions, how often they happen, what depth they reach, what gets recorded as `observation` vs `decision`, and how operators extend Stoa per-repo. Each opinionated bit pays for itself at read time and at AI-interpretation time; each loose bit accommodates the variation real engineers actually exhibit.

### What this means in practice

**Stoa is AI-assisted by design, and that's the point.**

The methodology's quality and consistency depend on the agent doing the interpretation. A high-quality model (one that reads context faithfully, surfaces ambiguity, follows discipline rules without slipping) makes Stoa reliable. A weak model, or a strong one running out of context, or one that confabulates, introduces drift. **Mistakes happen.** They're not bugs in coded rules; they're interpretation slips by an AI reasoning over loose conventions.

Why accept that? Because **rigid alternatives have repeatedly failed**. Methodologies that encode their discipline as strict validators, mandatory schemas, gate-checks before commit, or lint rules at PR time have all been tried, and engineers reject them at scale. Not because rigor is bad, but because engineers want **freedom to experiment**: to deviate from the prescribed path, to try the unusual approach, to skip ceremony when the situation doesn't fit it. A methodology that punishes experimentation gets routed around, or quietly abandoned, which has the same effect.

The asymmetry Stoa accepts: **better to be occasionally fuzzy than universally bypassed.** AI mistakes are recoverable: the next session reads the WAL, an `[stoa]` suggestion catches what was missed, an operator-triggered `/stoa audit` sweeps for drift. Operator-bypass is catastrophic; when people stop using the methodology, the WAL fills with gaps that nothing recovers from.

This also means **Stoa's value compounds with agent capability**. As models improve (better context handling, better domain reasoning, fewer hallucinations), Stoa's interpretation reliability rises and the cost of AI-fuzziness drops over time. v0.1 BETA's premise is that agents are *already* good enough to make this work; the beta tests that empirically. *(WAL: [`f8b3c52`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--f8b3c52))*

**v0.2 escalated one cadence — narrowly.** Beta data through v0.1.4 surfaced one recurring failure mode that imperative-wording fixes could not stabilize: the pre-commit WAL audit (coherence cadence #3) degraded under sustained commit pressure across four documented instances. v0.2 shipped a git pre-commit hook (`.githooks/pre-commit` + `.stoa/hooks/wal-audit`, now in [`src/hooks/`](../src/hooks/)) as the deterministic backstop for that one cadence; the other AI-discipline cadences remained unchanged. The hook is intentionally narrow scope — heuristic check on intersection of staged files with `.stoa/artifacts.md`, blocking when `context_log.md` isn't also staged — and rides on standard git mechanism (no new tooling). When the commit-boundary T1 re-audit finds no decision to record, the AI clears the gate with a scoped `STOA_NO_DECISION=1` flag — skipping only this check while any adopter hooks still run; `git commit --no-verify` is avoided because it skips every client-side hook (see [`c8c3c6d1`](../context_log.md#c8c3c6d1d32148ecb173f7cd24d0bd06--decision--2026-06-04)). The escalation pattern that emerged: **AI-discipline first, beta data identifies recurring failures, then narrow deterministic backstops for specifically-failing cadences**. The loose-framework default holds for everything else. See [`c2a6d18`](../context_log.md#c2a6d18--decision--2026-05-11) for the beta data + scope decision.

**v0.12.3 added a non-blocking advisory to that hook.** Forensics on a six-entry attribution gap — entries appended via hand-composed shell heredocs that dropped the `**Authors:**` line ([`fe41ae07`](../context_log.md#fe41ae079bf44bb78875de06ef2057af--observation--2026-06-25)) — showed the hook's blocking pass validates only co-staging, never entry content, so the lapse ran uncaught across six commits. The fix ([`b79e0c97`](../context_log.md#b79e0c9753d94222add40a4ad1fc51bc--decision--2026-06-25)) adds an **advisory well-formedness check**: on any commit staging `context_log.md` it scans the *staged diff* for newly-added entry headers and warns — never blocks, exit unchanged — on a missing `**Authors:**` line, an unrecognized type, or a malformed header. Staged-diff-scoped (existing/imported history is never re-flagged) and structure-only. It is deliberately advisory rather than a gate: a *blocking* content-validator was rolled back earlier after false-positives ([`22b364ac`](../context_log.md#22b364acec524f4e8eeaa52a40d78500--rollback--2026-05-26)), and attribution stays AI-discipline + `git blame` fallback. The check is intentionally **letter-free** — "Pass B" (the v0.4.0 coherence-indicator, below) and "Pass C" (the rolled-back content-validator) name *removed* passes; only the blocking co-staging pass ("Pass A") remains alongside this advisory.

**v0.3.6 added cadence #6 — multi-author WAL integration.** The original methodology was forged in a single-author / single-laptop trial (the adopter PoC). Multi-author scenarios require reconciling **parallel decision streams across clones** — Alice and Bob each refine, log, and commit decisions on their own clones; when one pulls from the other, the WALs must reconcile not just *textually* (git's job) but *semantically* (Stoa's job). Cadence #6 is the multi-author analogue of cadence #3: where #3 catches *unlogged decisions before they commit* on a single clone, #6 catches *semantic conflicts between independently-logged decisions before they merge* across clones.

The detection is **M×N entry-level pairwise classification**: for `M` new entries on the upstream side and `N` new entries on the local side, every pair `(m, n)` gets classified. Entry-level (not arc-level) for detection — catches cross-arc conflicts the arc view would miss; presentation groups results by inferred arc for operator readability (the M×N detail stays under the hood). v0.6.0 routes the classification step through `/stoa coherence --pairwise <M> <N>` and unifies the verdict labels with the rest of Stoa. Three buckets:

- **Adjacent** — disjoint topics, or one side strengthens the other on the same arc. Safe to merge; AI may optionally propose cross-ref enrichment.
- **Converging** — both sides reached the same conclusion independently. Strong signal worth recording — **keep both decision entries** (the dual audit trail is the value; never dedup) and propose an `observation` entry recording the convergence.
- **Superseding** — direct contradiction OR partial-arc invalidation (a later entry's premise breaks an earlier entry's reasoning). Halt; surface a resolution menu: (a) append a rollback on one of the two citing the new evidence/argument; (b) append a reconciling decision integrating both; (c) defer for async resolution with the other operator.

(The pre-v0.6.0 CLEAN / CONVERGENT / CONTRADICTING labels map directly onto Adjacent / Converging / Superseding; see WAL [`97bb6dee`](../context_log.md#97bb6dee48b14c45b500ec7419d6ba65--rollback--2026-05-18) for the vocabulary rollback.)

The cadence rides on a **union-merge git substrate**: the WAL file gets a `.gitattributes` `merge=union` rule (line-level concatenation, no conflict markers) so any integration — a plain `git pull` merge, or a rebase if the operator's own git config chooses one — auto-concatenates both sides' entries without conflict markers. Stoa imposes no pull strategy and sets no `branch.<main>.rebase` config; `/stoa pull` runs a plain `git pull` under the operator's own merge/rebase config. File order is incidental: two clones can hold the same entries in different order, and that's fine. WAL entries are append-only and never rewritten, and divergent blocks only `Refs:` their common ancestor, so file position carries no meaning. Causality lives in the `Refs:` graph (an entry can only `Refs:` entries that already existed) and authored-time lives in the date header — readers and coherence checks key off those, never file position. (See the [Attribution section](#3-attribution).)

The union-merge strategy has one wart that prompted a narrow guardrail exception: the line-level concatenation can eat the `---` separator at the concatenation boundary between Alice's last entry and Bob's first entry. A **post-pull integrity check** verifies entry-boundary structure after the merge or rebase; if a separator is missing, the AI re-inserts `\n\n---\n\n` between the affected entries. This is the **second exception to the WAL guardrail** (alongside *append a complete entry*) — and it's tightly scoped: restoration of separator lines only, in immediate post-pull state, never re-ordering, never modifying bodies, never changing hex IDs. Restoring a separator the merge ate is recovering the well-formed WAL contract, not reinterpreting decisions. *(WAL: [`6f2b8a3`](../context_log.md#6f2b8a3--decision--2026-05-12), [`1b5d9f7`](../context_log.md#1b5d9f7--decision--2026-05-12))*

A second pass after the merge handles **cross-artifact propagation** over the `M + N` arcs against committed-HEAD tracked artifacts — the multi-author counterpart to cadence #2's post-decision propagation. Scope is committed-HEAD only; working-tree artifact edits are out of scope for the audit on the assumption that an artifact edit reflecting a decision would already have its WAL entry (cadence #2 would have caught it). The audit does emit a one-line **sanity-warn** if Bob has uncommitted edits in tracked artifacts — a backstop for the "Bob meant to log but forgot" case. Strength of the nudge scales with Pass-1 verdict: Adjacent/Converging → soft nudge to walk the tracked-artifacts list; Superseding (after operator resolves) → strong, targeted nudge naming the specific artifacts touched by the contested premise. Detection is **bilateral** — both sides' new arcs get audited against the other's; the AI doesn't privilege "upstream is right" or "local is right." See WAL [`7c4b9d2`](../context_log.md#7c4b9d2--decision--2026-05-12), [`2e8f3a1`](../context_log.md#2e8f3a1--decision--2026-05-12), [`9d1c5b4`](../context_log.md#9d1c5b4--decision--2026-05-12), [`4a7e6c0`](../context_log.md#4a7e6c0--decision--2026-05-12), [`6f2b8a3`](../context_log.md#6f2b8a3--decision--2026-05-12), [`1b5d9f7`](../context_log.md#1b5d9f7--decision--2026-05-12) for the design arc.

**v0.3.6 added the `[stoa-preflight]` rule — a different escalation pattern.** Cadence #3's v0.2 escalation went *AI-discipline → deterministic git hook*. The settling-cue + AI-side phase-settlement triggers (the rules that say "propose a WAL entry before executing on a settling cue") had no equivalent structural backstop because there's no git surface to hook them on — they fire mid-conversation, not at commit time. The empirical observation from the v0.3.6 implementation session: the AI silently misses these triggers under task-momentum pressure (same failure pattern as cadence #3's v0.1 → v0.2 escalation, just on a different surface). The escalation ladder for the preflight rule:

1. **Discipline rules alone** (v0.1) — the triggers exist; the AI is told to honor them. Silent misses observed.
2. **Structural mitigation** (v0.2-v0.3) — added cadence #4 (pre-compact/pre-clear WAL audit) and refined the settling-cue trigger list. Improvement, but silent misses persist.
3. **Wording strengthening** (v0.3.x) — moved imperatives to *"MUST"* / *"shall"* shape. Some improvement; still silent under pressure.
4. **Visible-output requirement** (v0.3.6) — the AI MUST emit a literal `[stoa-preflight]` block as its first user-visible content for any turn that hits a trigger, BEFORE any Edit/Write/Bash tool calls.
5. **Family extension** (v0.5.2) — visible-output applied to two more cadences after wording-tightening saturated on them: `[stoa-init]` for session-boot boundary moments (session start, post-`/compact`, post-`/clear`; three recorded skips across two repos) and `[stoa-propagation]` for pre-commit drift walk (cadence #1; two recorded misses across release boundaries). The family — `[stoa-init]`, `[stoa-preflight]`, `[stoa-propagation]` — shares one shape: a literal `[stoa-*]` block as the first user-visible content of a turn, with the AI's compliance operator-verifiable in-turn.
6. **Informational sibling** (v0.6.0) — `[stoa-coherence]` joins the family as the **informational** member. Emitted by every `/stoa coherence` invocation (1-vs-corpus, M×N pairwise, M×M internal-sweep). Same `[stoa-*]` shape, but **not blocking** — it surfaces classification (Superseding / Converging / Adjacent buckets + a verdict line) and lets the operator decide. The three blocking blocks plus the one informational block cover the four surfaces an operator now sees from Stoa per turn.
7. **Boundary-moment block to host hook** (later iterations) — `[stoa-init]` is the one block whose escalation continued past visible-output discipline, on the same ladder cadence #3 climbed when it reached a git pre-commit hook. The session boot check runs a read-only probe (`.stoa/hooks/bootcheck-probe`) at each boundary moment (session start, resume, post-`/compact`, post-`/clear`) and renders the result as the `[stoa-init]` block. Visible-output discipline alone could not guarantee the probe ran — the AI could skip the boundary-moment check under task momentum. The escalation: a host SessionStart hook runs the probe and injects its output into session context, and the AI renders `[stoa-init]` from that injection rather than deciding to invoke it. On Claude Code the hook lives in committed `.claude/settings.json` (command `bash .stoa/hooks/session-bootstrap`, matchers `startup|resume|clear|compact`); the wrapper activates git hooks non-clobber, runs the probe, and prints the result, which Claude Code injects into context. A short degradation floor covers the cases the hook can't reach — folder not yet trusted on this machine, disabled by enterprise policy, hook clobbered or absent, or a non-Claude host: the AI runs the probe itself before substantive work, then renders the block. This is the bootcheck's analogue of cadence #3's git-hook escalation — deterministic where the surface allows it, AI-discipline floor where it doesn't.

The tradeoff is honest: this is **still AI-discipline at root** — a sufficiently lazy AI could emit a perfunctory `[stoa-preflight]` block claiming "none" and proceed past missed decisions. But what's bought is the failure mode shifts from **silent omission → recoverable omission**: every multi-step task starts with an artifact the operator can verify, and the AI is forced to *consciously address* the question on every turn. If the block is missing, the operator sees the omission immediately and can call for it. If the block lists "none" but the operator knows decisions WERE settled, the operator corrects in-turn. Visibility moves the gap from invisible to inspectable.

**Future contingency.** If empirical beta data shows preflight-discipline ALSO degrades, v0.4 may escalate to host-specific hooks — Claude Code's `UserPromptSubmit` hook, Codex's equivalent, and others — that fire the preflight check structurally before the AI's first turn-output goes out. But that path multiplies host-fragmentation cost; the escalation is justified only with data, not speculation. The two-line generalization: **AI-discipline first; observe; structural-where-possible; visible-where-not; host-hooks as last resort.** *(WAL: [`d8e4a2c`](../context_log.md#d8e4a2c--decision--2026-05-12), [`b4d8e1c`](../context_log.md#b4d8e1c--observation--2026-05-12) — the latter is the meta-observation that v0.2's cadence-#3 escalation and v0.3.6's preflight escalation are the *same convergence arc on a different surface*.)*

**v0.4.0 added symmetric operator/AI flow capture.** Beta data from the adopter project through v0.3.7 revealed a structural asymmetry: the settling-cue handling was operator-driven (yes-cues, transition-cues, directive-cues, lifecycle-cues), but AI auto-refinement under task-momentum pressure happened invisibly — real content decisions made mid-flow that never reached the WAL because no operator cue fired. v0.4.0 reframes a Stoa-using session as a **Human+AI local collaborator pair**: both sides contribute to the decision arc, and the WAL records both. Three additions land together:

- **Auto-refinement cues** (fifth category in §"Settling-cue triggers"): AI-side phrases that signal mid-flow course correction — *"actually, on reflection..."*, *"correction: ..."*, *"I'm changing approach because..."*, *"re-reading X..."*, etc. — get treated as settlement signals on the same footing as operator directive-cues. The preflight rule fires; the AI proposes a WAL `decision` entry; operator approves; entry lands with `Authors: [@<operator>;<tool>(<model>)]` attribution (operator is decider, AI is session-context).
- **Coherence check on AI-proposed WAL entries** (v0.4.0; broadened v0.4.2; routed through `/stoa coherence` in v0.6.0). Originally scoped to auto-refinement-cue WAL proposals: the AI classified related prior arcs into **Superseding** / **Converging** / **Adjacent** buckets and surfaced the classification inline in the proposed entry. v0.4.2 broadened the rule to *all* AI-proposed WAL entries (any type) — pure-AI defense against CLI-proxy filtering of Pass B's stderr handoff (see the hook-coherence-indicator bullet below). v0.6.0 routes the check through the unified `/stoa coherence <candidate>` primitive, which delegates to a subagent that slurps the WAL when feasible and falls back to retrieval at scale. Catches the silent-drift failure mode where new entries invalidate earlier settled arcs without anyone noticing.
- **Pre-commit hook coherence indicator** (v0.4.0; refined v0.4.1 → bash-detects + AI-instruction stderr handoff for arc-coherency reasoning; reframed v0.4.2 → backstop-only). The deterministic pre-commit hook (`.stoa/hooks/wal-audit`, added in v0.2) gains an informational second pass: for each staged WAL entry, it emits a structured `[stoa-wal-coherence:ai-instruction]` block to stderr that hands off arc-coherency reasoning to the AI on its next turn. Never blocks. Empirical discovery during the v0.4.1 implementation session: hook stderr is fragile to CLI-proxy environments (`rtk` and similar token-savings tools at Stoa filter the structured stderr silently). v0.4.2 moved the primary coherence-check to AI-draft-time (the broadened cue-handling rule, pure AI, CLI-proxy-immune); the hook remains as a backstop for operator hand-edit commits.

The multi-author merge substrate (cadence #6, v0.3.6+) handles convergence across pairs: a Stoa-running org is a network of Human+AI pairs whose records merge into shared truth via the same M×N pairwise classification. **The model:** within-pair symmetry (v0.4.0) + cross-pair symmetry (v0.3.6) compose into a uniform capture pattern at every scale. *(WAL: [`f4a3c81`](../context_log.md#f4a3c81--decision--2026-05-15) for the thesis, [`4a2e7b3`](../context_log.md#4a2e7b3--decision--2026-05-15) for the cues, [`6d8a3f1`](../context_log.md#6d8a3f1--decision--2026-05-15) for the coherence check + [`5e2c8b9`](../context_log.md#5e2c8b9--decision--2026-05-15) for its v0.4.2 broadening, [`e91b4c7`](../context_log.md#e91b4c7--decision--2026-05-15) + [`3b4f7a2`](../context_log.md#3b4f7a2--decision--2026-05-15) + [`9c4d8a2`](../context_log.md#9c4d8a2--observation--2026-05-15) for the hook indicator + its v0.4.1 refinement + the v0.4.1 CLI-proxy discovery that motivated v0.4.2.)*

**v0.4.x design principle (reaffirmed at v0.4.2):** *anything that can impact cadence detection should be as pure AI as possible* — file reads + conversation context + AI reasoning, not CLI tool stderr that proxies might filter. RTK was the immediate motivator; the principle generalizes to any CLI-proxy / output-summarizer / IDE-plugin layer. v0.4.x cadence design treats CLI-stderr handoffs as fragile and prefers AI-discipline at the moment of decision. Hooks remain as backstops where they can degrade gracefully (Pass A's exit-1 BLOCKING always surfaces; Pass B's informational stderr might not).

**v0.6.0 shifted the coherence architecture to Agent-first.** Earlier versions framed the vector index (added in v0.5.0) as the primary substrate for WAL semantic operations. Empirical context-handling improvements through 2026 made a different framing more honest: the WAL is **curated, high-relevance-density data** — every entry is operator-confirmed signal. At slurp-feasible scale, an Agent reasoning directly over the loaded corpus produces better coherence judgments than cosine-similarity pre-filtering, which replaces LLM judgment with a degraded proxy. The bet is that Agent capability scales faster than RAG-tuning effort; 1M-token contexts already exist and grow rapidly. The vector index inverts from primary substrate to **scale-extension fallback** when the WAL outgrows what a subagent can slurp. A unified `/stoa coherence` primitive (three modes: 1-vs-corpus, M×N pairwise, M×M internal-sweep) backs every coherence operation; cadence #6's prior CLEAN / CONVERGENT / CONTRADICTING vocabulary unifies into the Stoa-wide **Superseding / Converging / Adjacent** set. Index install becomes opt-in or scale-triggered rather than first-run mandatory. *(WAL: [`717a71fc`](../context_log.md#717a71fc0e4f49c8b5835761be4c3f16--decision--2026-05-18) (Agent-first principle), [`d45489b7`](../context_log.md#d45489b75cb246298c9ddb9fe6717e46--rollback--2026-05-18) (vector inversion), [`b0122b1f`](../context_log.md#b0122b1facf5413eaaf25896fbc0c706--decision--2026-05-18) (`/stoa coherence` primitive), [`97bb6dee`](../context_log.md#97bb6dee48b14c45b500ec7419d6ba65--rollback--2026-05-18) (vocabulary unification), [`d5b9df87`](../context_log.md#d5b9df8715a448ada7e04f6b9aa997af--decision--2026-05-18) (opt-in install discipline), [`fabf69ef`](../context_log.md#fabf69ef489c47049a1f8a232d124e58--decision--2026-05-18) (coherence-doubt cues).)*

**v0.7.0 dissolved the propose-confirm gate; later iterations retired the visible-output ceremony blocks.** Empirical beta data showed three live operators rubber-stamping the propose-then-append loop without reading the proposed entry. Under FP4 (substance is human; coherence is AI), the loop was asking the operator to do AI's coherence work — a category violation that produced ceremony without signal. v0.7.0 collapsed the loop: AI judges T1→T2 promotion autonomously per the class-based yardstick (does this fit one of the five entry types?) and writes entries directly; the `[stoa]` chat anchor at every T2 write is the operator-visible artifact. The `[stoa-preflight]` and `[stoa-propagation]` visible-output blocks introduced in v0.3.6 / v0.5.2 were deprecated at the same time — they had become ceremony when the underlying mechanism became AI-autonomous. `[stoa-init]` at boundary moments stayed (different purpose: install-state probe evidence, not behavioral compliance) and later escalated further — from AI-discipline rendering to a host SessionStart hook that runs the read-only probe and injects its output, with the AI rendering the block from that injection. See escalation step 7 above.

**Subsequent refinements** ([`a88b435b`](../context_log.md#a88b435bc4ea4c3d818d74d652f7f1c3--decision--2026-05-19) autonomy; [`b90a584f`](../context_log.md#b90a584fb50742178c6a0d117fe5749b--decision--2026-05-19) ceremony deprecation; [`b6e06d0e`](../context_log.md#b6e06d0ec18d4622961b9184e492aaf5--decision--2026-05-19) three-tier WAL model; [`d4561471`](../context_log.md#d4561471acf1457d8539836b14888e75--decision--2026-05-26) cadence #7 artifact-coherence nudge; [`a274252c`](../context_log.md#a274252c993246988e63cd42ce495715--decision--2026-05-26) WAL grounding) layered in the four post-autonomy patches that drove the most recent stress-test improvement (override-ask, self-validated cues, execute-phase substrate sweep, default-shift). Mean decision-arc-reconstruction-fidelity moved from 0.69-0.81 to 0.91 across nine controlled runs; see [arc-capture-quality](../experiments/arc-capture-quality.md) for the instrument and the per-run scores.

**Post-autonomy refinements (most recent layer).** Empirical work since autonomy shipped surfaced four patches that materially improved decision-arc-reconstruction-fidelity in stress-test runs (mean 0.91 vs prior 0.69-0.81 baseline; see [arc-capture-quality](../experiments/arc-capture-quality.md)):

- **Override-ask on operator directive.** When the operator emits a directive AND AI has substrate-grounded reason to refute its premise, AI MUST surface the substance reasoning before acting. Silent override is forbidden; observation-only refutation is also forbidden. The pattern produces an explicit operator-touchpoint that turns silent disagreement into a settlement event.
- **Self-validated cue recognition.** Operator emits proposal + immediate self-validation in the same turn (*"I think we should require API-key auth for that endpoint. Makes sense to me."*); the AI treats this as a directive-cue without needing a prior AI proposal-and-agree exchange.
- **Execute-phase substrate sweep** (added as cadence #7 sub-step (c)). At end-of-impl, AI scans execute-phase artifacts (generated code, configs, plan docs) for substrate findings made during implementation work that didn't get WAL'd as they happened. Three patterns elevate: substrate confirmation, substrate contradiction (triggers override-ask), and new architectural choices introduced during execute. What counts as "architecturally meaningful" is judged against the **decision line** — render-relative, not code-specific. For code the line sits at architecture and contracts; for prose, at characters and storylines; for a data model, at schema and relationships. For any render type, a choice above the line is an inflection worth elevating; a choice below it stays render-internal. The AI interprets where the line falls for the render in front of it.
- **Default-shift rule.** If AI is documenting a substrate finding inside a code comment, artifact header, or plan-doc "Open questions" section, AI has ALREADY crossed the "this is worth noting" threshold — the next step is automatic: write the WAL entry too. The decision-line carve-out (what stays render-internal) covers only the below-the-line choices for that render type: for code, variable names, control-flow style, equivalent syntactic forms, and formatting; the analogous render-internal choices for prose or a data model are carved out the same way.

**Verification as a coherence primitive (the most recent layer).** A subsequent patch added a fifth cadence #7 sub-step and the operational principle behind it. The framing is that *verifying a work block is done* is not a separate layer bolted on after decision-capture — it is the same coherence primitive Stoa already runs (WAL↔WAL, WAL↔artifact), now pointed at a freshly produced render.

- **Semantic DONE is the agent's; mechanical satisfaction is the host's (OP5).** A work block is DONE when its render embodies the EC:STRONG decisions it committed to, and AI owns validating that against the decision forest. Stoa *defines* what DONE means — the forest of commitments — and the agent *does* the validating. Driving mechanical checks (tests, builds) to green is the host's job, not AI's. OP5 is a sibling to OP4: where OP4 draws the line at the git boundary (decisions are in scope; commit mechanics are not), OP5 draws it on a different axis — semantic satisfaction is in scope; the iterate-to-green test/build loop is not.
- **Forest-grounded DONE check** (cadence #7 sub-step (d)). Before any arc-completion language (*"that's working now"*, *"the refactor is in"*, *"tests pass"*), AI grounds *"is this done?"* in the forest via the WAL-librarian: which EC:STRONG decisions did this work commit to, and does the render embody them? For a decision satisfied only behaviorally, AI confirms its test exists and is wired — it does not run the iterate-to-green loop (that's the host's, per OP5). Findings report ONLY in decision vocabulary, never as a diff or word critique: a render that confirms a decision earns an optional `observation` citing it; a render that contradicts one triggers the override-ask (F1-A); a render that surfaces an undecided inflection above the decision line gets recorded or surfaced as ambiguity.

**Honest disclaimer for adopters:** you are signing up for a methodology whose quality depends on the AI you give it. Run it with a strong model and current context; budget for the AI to occasionally miss things; trust the WAL to be the durable record even when AI surfaces are noisy.

---

## Core primitives

These are the pieces every Stoa project has. Everything else is optional.

### 1. The WAL (decision log)

The project's primary durable record. Append-only. Lives at a single file `context_log.md` at the repo root.

**v1 is single-file by default.** Multi-file rotation (when the file gets unwieldy) is deferred — see *What's not yet specified*. Append-only + git's merge semantics handle concurrent appends cleanly; no explicit locking required.

**The WAL is text-markdown, stored as text in git.** Not a binary blob — keeps GitHub web rendering, syntax highlighting, search, and anchor-link addressability into specific entries.

**PR diffs are suppressed by convention via `.gitattributes`:**

```
context_log.md linguist-generated=true
```

GitHub collapses the WAL diff in PR review by default; reviewers can expand if curious. WAL writes are NOT a PR review surface — quality is enforced at write time (refining-session discipline + AI-proposes-user-confirms), not at review time. The decision that justifies a code change should be linked from the PR description (e.g. `Refs WAL: <hash>`), giving reviewers an auditable thread without forcing them to wade through the diff. *(WAL: [`f5a3c20`](../context_log.md#2026-05-08--decision--authors-ivanclaudeopus471m--f5a3c20))*

**Each entry records:**

- ISO timestamp + 7-char random hex ID for stable referencing (collision-resistant within a project; generated inline without external tooling).
- Type tag (`decision`, `wont-do`, `table`, `branch`, `observation`, `rollback`, `manual-edit`, `reconciliation`).
- Authors and Participants (see Attribution below).
- Body — the substance.
- `Refs:` cross-linking earlier entries by ID.

**Append-only is non-negotiable.** To "change" an earlier decision, append a new entry that explicitly supersedes it via a `rollback` type. The earlier entry stays. This preserves the audit trail at all times.

**Entry types in detail:**

| Type | When to use |
|---|---|
| `decision` | Settled commit (do X). Default for most concluded sessions. |
| `wont-do` | Explicit rejection. Audit trail; future readers don't re-litigate. |
| `table` | Parked for later. Body must include sparse pointers: what was being explored, what triggers should reopen it, refs to relevant adjacent entries. (No file to "save and resume"; the table entry is the resumption seed.) |
| `branch` | Decomposed into named children. Supports both dependent (parent re-synthesizes) and disjoint (parent closes) branching; the distinction is handled organically as resolution progresses, not pre-declared. |
| `observation` | Non-decision recording. Something noticed worth keeping but not a settled outcome. |
| `rollback` | Supersedes a prior entry. Append-only — the original entry stays; the rollback adds the supersession. |
| `manual-edit` | Human directly modified an artifact; AI captures the change after the fact. |
| `reconciliation` | Alignment-pass output for the multi-laptop duplicate-logs case. |

Per the loose-framework principle, picking the "wrong" type for an entry isn't an error; the body is the substance.

**WAL discipline — when to write an entry:**

1. A refining session reaches a conclusion: commit / won't-do / table / branch.
2. The user manually instructs ("log this", "note this").
3. **Must-log: every git commit.** Commit is a forcing function; the WAL stays aligned with the working tree's history.

**When NOT to write:** every observation, every clarification, every evolving claim mid-conversation. Default is silence. Stoa's WAL is a sparse trail of decisions, not a transcript. *(WAL: [`aa74270`](../context_log.md#2026-05-08--decision--ivanclaude--aa74270), #0013)*

### 2. Refining sessions

The **active phase** before a WAL commit. A refining session is a back-and-forth (operator + AI; sometimes other humans via Slack threads) on a single topic until it reaches one of four outcomes:

- **commit** — settled; outcome lands as a `decision` WAL entry.
- **won't-do** — explicit rejection; lands as a `wont-do` entry.
- **table** — parked; lands as a `table` entry with resumption pointers.
- **branch** — decomposed; lands as a `branch` entry naming children.

**Sessions live only in the live AI conversation. There is no on-disk file representing an active refining session.** The local AI session-tracking is the in-memory carrier for the live context. Lose the laptop → lose the in-flight session. Bounded loss; recovery is "pick up from the most recent committed entry."

**Why no on-disk session file:** Eliminates a class of state-management problems (open/close semantics, paused-vs-active state, decomposition file trees). Forces the WAL entry to do its job; the WAL is *the* durable record. Keeps Stoa lightweight; adopters don't learn a session lifecycle. The bounded-loss trade-off is acceptable because refining is *cheap to redo* given the WAL context, but *expensive to over-formalize*.

**Multiple refining sessions run in parallel.** Architect refining UX with PM in one thread, the same architect refining cache coherence with a dev in another, debugging in a third. Each session is independent until it commits. *(WAL: [`e8d3458`](../context_log.md#2026-05-08--decision--ivanclaude--e8d3458), [`f1c2a87`](../context_log.md#2026-05-08--decision--authors-ivanclaudeopus471m--f1c2a87), #0009)*

**Solo and shared journey types.** Every refining session runs in one of two modes:

- **Solo flow** — operator + AI alone, working over the repo. Used for fresh exploration, for **catching up alone on a thread someone else started** (the *solo catch-up* pattern — see [Core value-prop #4](#4-solo-catch-up-as-a-first-class-pattern)), and for any exploration that does not yet need other humans.
- **Shared flow** — multi-person collaboration via Slack-bridged `/stoa ask @<handle>` and `/stoa respond <question-id>` between operators on different laptops. Used when a question needs another participant's input or a decision needs multiple sign-offs.

The same primitive (refining session) covers both. Most non-trivial work hops between the two: solo to build context → shared to involve others → solo (or solo catch-up by a different participant) → shared again, until the topic settles. The WAL is the substrate that makes the hops cheap. The name "solo" was chosen over "local" because "local" overloads with git/laptop semantics; "solo" captures *alone with AI* whether the topic is fresh or being-caught-up-on. *(WAL: [`6e1b9d7`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--6e1b9d7))*

### 3. Attribution

Every WAL entry records *who decided* and *what tools they used*, kept distinct. v0.3.6 formalized the attribution shape into the canonical entry form: an `**Authors:**` line is **required** on every new entry; a `**Participants:**` line is **optional** (omit when empty).

**Actor grammar:**

```
actor := @<handle> [(<version>)] [;<tool>(<model>)]
```

- `@<handle>` — humans, named agents, service accounts. Required. One namespace.
- `(<version>)` — agent code version. Present for agents (`@cross-ref-checker(v0.3)`); absent for humans.
- `;<tool>(<model>)` — AI tooling suffix. Present when the actor was working with AI. The `;` separator is deliberate: human accountability lives in `@handle`; AI is session-context, not co-decider.

**Two attribution fields per entry:**

- `Authors: [<actor>, ...]` — primary decision-owner(s). All listed are equally accountable. **Required (v0.3.6+).**
- `Participants: [<actor>, ...]` — others who shaped the decision but didn't own it. **Optional**: omit the line entirely if empty.

**Examples:**

```
Authors: [@marcus;claude(opus4.7/1M)]
Participants: [@john, @rich;gpt-5.3-codex(256k), @cross-ref-checker(v0.3);claude(opus4.7/1M)]
```

Reads as *"human Marcus working with Claude opus-4.7/1M-context, shaped by John, Rich-with-Codex, and the cross-ref-checker agent."*

**Standalone-AI emission** (rare; a tool acting as primary author for an autonomous bot entry):

```
Authors: [@drift-detector(v1.1);claude(haiku-4.5/200k)]
Triggered-by: commit a3f2b1c by @marcus
```

The split between human accountability (`@handle`) and AI tooling (`;tool(model)`) matters: when a future reader asks *"who decided X?"* the answer is the *human* (with the AI session as context), not *"Marcus+Claude"* (which would make the AI sound co-equally accountable for an architectural choice it cannot be accountable for). The `;` separator preserves that distinction visually; human and tool live on different sides of it.

**Backward compatibility.** Entries written before v0.3.6 may lack the `Authors:` line. Reader logic tolerates both shapes; for unattributed entries, `git blame` on `context_log.md` is the fallback for *who wrote what when*. No backfill required. *(WAL: [`81463df`](../context_log.md#2026-05-08--decision--authors-ivanclaudeopus471m--81463df))*

**Causal order vs. authorship date vs. file position.** Each entry's date header is authoritative for *when the decision was authored*. The **`Refs:` graph is authoritative for causal order**: an entry can only `Refs:` entries that already existed, so the reference edges encode what-came-before independent of where anything sits in the file. File position is incidental — two clones can hold the same entries in different order after independent pulls, and that's fine. Because entries are append-only and never rewritten, and divergent blocks only `Refs:` their common ancestor, reading top-to-bottom carries no guaranteed meaning across clones. To answer *"when was decision X authored?"*, read entry X's date header; to answer *"what did decision X build on?"*, follow its `Refs:` edges.

### 4. The agent rulebook (AGENTS.md + stoa-claude.md)

A small set of files at the repo root that an AI session reads at the start of every conversation. It encodes:

- The Stoa methodology the project uses (the composed runtime).
- Project-specific rules (allowed commands, code style, integrations enabled).
- Pointers to where the WAL lives, how to write to it, how to interpret authority.

The agent rulebook splits as follows: [`AGENTS.md`](../AGENTS.md) is the host-neutral project entry point — operator-owned content plus a delimited `STOA::DISPATCHER` block injected by the installer that routes the AI to the host adapter. [`CLAUDE.md`](../CLAUDE.md) is a thin `@AGENTS.md` shim Claude Code reads natively. [`stoa-claude.md`](../stoa-claude.md) at the repo root is the composed Claude runtime — the full Stoa methodology in operational form, generated by `build/compose.sh` from editable source under [`src/`](../src/).

Adopters fetch the unified [`dist/`](../dist/) bundle and run [`dist/install.sh install`](../dist/install.sh) once in the target repo; one command installs every supported host and handles fresh install and upgrade transparently via per-file content-hash drift detection. Existing `CLAUDE.md`/`AGENTS.md` content is preserved — the install injects the dispatcher block into `AGENTS.md` (creating it if absent), thins `CLAUDE.md` to `@AGENTS.md`, places spec-owned files (`.claude/commands/stoa.md`, `.claude/agents/stoa-*.md`, `.githooks/*`, `.stoa/hooks/{wal-audit,bootcheck-probe,session-bootstrap}`), merges Stoa's SessionStart hook entry into `.claude/settings.json` without disturbing adopter hooks or keys, seeds-and-preserves templates (`.stoa/artifacts.md`, `.stoa/beta_tracker.md`, `context_log.md`), wires git hooks, and writes `.stoa/installed` with content hashes. Codex ships in the same bundle (`src/adapters/codex.md` + `dist/codex/`, with the Codex SessionStart binding via `.codex/hooks.json` + `.codex/config.toml`); its install mechanics and the live boot path (SessionStart hook + bootcheck injection + native-subagent spawn) are validated on a real Codex CLI, while skill loading and the behavioral surface remain to be confirmed — see [`tests/codex-smoke-test.md`](../tests/codex-smoke-test.md).

### 5. Knowledge base

A `knowledge-base/` folder for external reference material: Zoom transcripts, vendor docs, research notes, PDF extracts, AI-authored KB articles on specific topics. Distinct from canonical docs (authoritative spec) and from scratch (forward-staged plans).

**Two ingestion modes:**

1. **Direct drop** — operator places the artifact under `knowledge-base/`; AI may reference but does not edit it.
2. **AI-authored KB article** — operator instructs Claude to write up a topic; output lives in `knowledge-base/` marked clearly as AI-authored.

**Freshness is git's job.** Stoa does NOT require date-stamping or operator-driven "stale" flags. AI cites the doc at its current version; when git records a file update, AI re-analyzes on next access. Simple, durable, no convention overhead. *(WAL: #0007, #0011)*

### The `/stoa coherence` primitive (v0.6.0)

A unified coherence-classification primitive that replaces what used to be six separately-evolved code paths (cadence #3's silent-decision check, the AI's pre-WAL-append draft-time check, cadence #6's M×N pairwise audit, `/stoa audit`'s WAL internal-conflict sweep, the pre-commit hook's Pass B handoff, the end-of-impl audit). One primitive, three modes:

- `/stoa coherence <candidate>` — **1-vs-corpus** classification. The candidate is a body of text describing a proposed WAL entry or in-flight proposition. Returns related prior arcs from the WAL classified into the three buckets.
- `/stoa coherence --pairwise <M-hexes> <N-hexes>` — **M×N pairwise** classification across two committed-entry sets. Used by cadence #6 during `/stoa pull`.
- `/stoa coherence --internal-sweep` — **M×M conflict detection** across all `decision` and `observation` entries (or a filtered subset). Used by `/stoa audit`'s internal-conflict sweep.

All three modes return the same Stoa-wide classification vocabulary:

- **Superseding** — candidate contradicts the prior arc; rollback recommended.
- **Converging** — candidate reaches the same conclusion independently; cross-ref recommended.
- **Adjacent** — candidate touches related material without contradicting; cite as `Refs:`.

Output is a `[stoa-coherence]` block (Subject / Mode / Path-taken / three buckets / Verdict). **Informational, not blocking** — Stoa never gates work on the classification. Operator decides.

Under the hood, the primitive delegates to a WAL-librarian subagent, which composes its retrieval to meet its coverage obligation (slurp feasible at small WAL size; retrieval beyond). The parent refining session never carries the WAL beyond grep-for-specific-hex calls; the subagent pays the slurp cost per-checkpoint invocation. See [§Scalability — the WAL bottleneck](#scalability--the-wal-bottleneck) for the retrieval-scopes rule that governs which entries land in scope. *(WAL: [`b0122b1f`](../context_log.md#b0122b1facf5413eaaf25896fbc0c706--decision--2026-05-18) (primitive extraction), [`8c65450c`](../context_log.md#8c65450caa024834886df98f5844900e--decision--2026-05-18) (subagent slurp), [`717a71fc`](../context_log.md#717a71fc0e4f49c8b5835761be4c3f16--decision--2026-05-18) (Agent-first principle).)*

---

## Multi-role collaboration

Stoa is designed from day one for multi-role, multi-laptop collaboration, not solo IC + AI. PM, architect, dev, exec, oncall, test, UI all check out the same repo locally with their own AI session, and hop between [solo and shared flows](#2-refining-sessions) as the work demands.

For a full end-to-end illustration of multi-role flow, see [Worked example: a PM brings a customer ask through the system](#worked-example-a-pm-brings-a-customer-ask-through-the-system). This section focuses on the **mechanics** of the cross-laptop primitives (the ask/stoa respond handoff and the multi-laptop logging pattern) that the worked example invokes.

### The /stoa ask handoff

Cross-laptop handoff is **lightweight**: no mid-refinement git commits required. The handoff packet:

1. **The question** — concisely framed.
2. **Named markdown snippets** — small, focused context blocks (1-3 paragraphs each, generated by the asker's AI from the live session) attached via the Slack integration. The architect's local Slack integration downloads them; the architect's AI reads them.
3. **Asker's git head** — short hash. The architect can compare against their own HEAD: if ahead, they may know about updates the asker is unaware of (which itself can become the answer); if behind, they pull first.
4. **Repo-state references** — file paths, prior WAL entry hashes, code locations. The architect's AI reads these from their own checkout, version-aligned to the asker's head if needed.

**Nothing is committed mid-flight.** The packet is ephemeral; only the conclusion of the refining session lands in the WAL. If the asker's in-flight thinking is too substantial to fit in a handful of small snippets, that's a useful signal: *some has settled and should be committed first* before the ask. The methodology surfaces that distinction naturally.

**Async-friendly by construction.** The architect doesn't have to be online when the question is asked. Slack is the notification fabric; the repo is the durable shared state. The architect picks up later, reads the snippets + the repo at the asker's head, responds. *(WAL: [`a52859f`](../context_log.md#2026-05-08--decision--authors-ivanclaudeopus471m--a52859f))*

### Multi-laptop logging (duplicate logs + reconciliation)

When a refining session crosses laptops, **each side writes its own WAL entry** capturing what *it* observed of the conclusion. Two entries; same topic; cross-referenced by handle. Storage is cheap; the audit trail (who said what) is preserved.

The two sides may misalign, captured in slightly different language, or recording subtly different decisions. A periodic **reconciliation pass** (manual at first, AI-assisted later) compares the two entries and either confirms alignment or emits a `reconciliation` entry resolving the discrepancy.

The reconciliation process is intentionally informal per the loose-framework principle. AI compares; human confirms. *(WAL: [`808fda8`](../context_log.md#2026-05-08--decision--ivanclaude--808fda8))*

---

## Comments and review on design docs

> **DRAFT — direction recorded; NOT settled. Multiple sub-threads need further refining. See WAL [`3a72b09`](../context_log.md#2026-05-08--branch--authors-ivanclaudeopus471m--3a72b09).**

**The unifying insight.** Comments and feedback are refining sessions where the reviewer is a Participant. Surgical concerns (typos, link fixes) resolve as text edits without WAL entries. Substantive concerns (load-bearing claims, alternative proposals, disagreements) become refining sessions; the conclusion lands in the WAL with the reviewer attributed.

### Two paths

**Path A — GDocs round-trip (recommended for teams already authoring / commenting in GDocs).** "Meet customer where they are." The team's commenting habit is preserved; markdown stays canonical (code-as-truth holds). Mechanism:

1. Author writes the design doc as markdown in the repo.
2. `/stoa publish-doc` pushes the markdown to a Google Doc (one-way; markdown remains canonical).
3. Reviewers comment on the GDoc using GDocs' native commenting UX (mouse-select-to-comment, threaded replies, notifications).
4. `/stoa fetch-comments` pulls comments back as structured markdown — author + timestamp + anchored quote + threaded replies + resolved status.
5. `/stoa triage-comments` walks the AI through accept / reject / discuss for each comment. Surgical → markdown edit. Substantive → refining session → WAL entry with the reviewer as Participant. Replies posted back to the GDoc.
6. `/stoa publish-doc` re-runs to push markdown updates while preserving comments on unchanged sections.

The implementation seed is the [design-docs](https://github.com/iavramov/design-docs) PoC (markdown-canonical → GDocs-render-only round-trip). **Status: PoC-grade implementation, not battle-tested.** The *pattern* is novel relative to what's published; the comment-reconciliation problem (preserving comments through markdown updates) is a documented industry blocker, and `design-docs` solves it. *But* implementation has had only single-author validation; multi-reviewer scale and the OAuth-setup friction for non-builder team members are unproven. Productization + validation is part of Stoa's roadmap, not a finished deliverable.

**Path B — PR review comments (fallback for teams without a GDocs habit).** GitHub's native PR-review-comment-on-diff UI. Lower setup cost; weaker comment UX. Substantive concerns still become refining sessions; resolutions still land in the WAL. Same discipline as Path A. Most successful in-repo design docs (Rust RFCs, Kubernetes KEPs, etc.) work this way today.

### Author-initiated review request

Either path: `/stoa request-review` is the slash command authors use to invite reviewers. For Path A it publishes/updates the GDoc and pings reviewers in Slack with the GDoc URL. For Path B it opens a "review PR" (a no-op marker change so reviewers have a diff to comment on) and pings.

### Honest framing

The GDocs-comment-UX gap on in-repo markdown is real, widely felt, and unsolved as of May 2026 (per WAL [`c5e4f81`](../context_log.md#2026-05-08--observation--authors-ivanclaudeopus471m--participants-research-subagentclaudeopus471m--c5e4f81)). Stoa's two-path approach doesn't claim to *invent* a better commenting UX; it claims to *preserve markdown-as-canonical* without forcing teams to abandon their familiar review habits. The GCP+OAuth setup cost is real and disclosed.

**See WAL [`3a72b09`](../context_log.md#2026-05-08--branch--authors-ivanclaudeopus471m--3a72b09) for the open sub-threads on this section.** WAL integration shape in triage, notification mechanism, multi-doc scaling, OAuth friction, comment thread depth, behavior under heavy revision, productization plan: none of these are settled; this section is provisional.

---

## Origin and prior art

Stoa was developed independently during a 6-day experimentation period on a real infrastructure project (the trial documented in the adopter project's design-methodology report, held privately by that team). The patterns emerged from the work, not from any prior framework. Only after the methodology had settled did a literature pass reveal that others have been converging on related ideas.

The proposal credits the prior art that exists, positions Stoa as an extension rather than a wholesale invention, and identifies the gap Stoa fills.

### The closest tradition: Architecture Decision Records (ADRs)

Originated by [Michael Nygard's Nov 2011 post](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions); conceptual roots in Philippe Kruchten's "Decision View." ThoughtWorks moved ADRs to "Adopt" on the Tech Radar around 2018. The ecosystem at [adr.github.io](https://adr.github.io/) hosts variants (MADR, Y-Statements, Nygardian) and tools like [log4brains](https://github.com/thomvaill/log4brains).

ADRs are the right tradition to descend from: committed-markdown decision records, version-controlled alongside the code, with a prescribed structure (proposed/accepted/superseded). They've been refined for over a decade and have a real ecosystem.

**The honest framing.** The artifact shape (an append-only log of decisions) is **not novel**. ADR has been a known-good idea for well over a decade. What's interesting is that adoption has been spotty in practice, which is data, not failure of the idea. The artifact was the cheap part; everything around it (writing discipline, supersession links, drift detection against code, finding the relevant prior art for a new question, capturing the deliberation rather than the conclusion) was what humans couldn't sustain. **AI flips that economics, and Stoa is what falls out: the operational layer that makes ADR-class artifacts maintainable at scale.**

Five concrete distinctions, beyond artifact format:

1. **ADR is post-hoc; Stoa is in-process.** ADR records decisions that happened *somewhere else*: a meeting, a hallway chat, a PR thread. The deliberation isn't in the artifact; one person writes it after the fact, summarizing what happened elsewhere. Stoa's deliberation happens *at the WAL*; the multi-angle weighing of alternatives IS the entry, not a summary of conclusions reached elsewhere.
2. **ADR doesn't try to keep itself coupled to code; Stoa does it automatically.** ADRs drift from code as a known weakness. Stoa's coherence cadence (pre-commit walk, post-decision propagation pass, on-demand audit) keeps decision-record and code in lockstep without human discipline.
3. **Real-world ADRs are thin in practice; Stoa's workflow enforces depth.** Title + one-line decision is common in ADR shops; barely better than a code comment. The best ADR practice is writing the record *before* finalization as a forcing function for articulating reasoning, but that discipline rarely sticks at team scale. Stoa puts the discipline in the workflow itself: a refining session that doesn't articulate multi-angle reasoning literally cannot reach settlement.
4. **ADR was designed for colocated teams; Stoa is built for async-required ones.** ADR has no structured primitives for branched decisions, multi-user contribution to a single thread, or solo catch-up. Stoa's `branch` type, `/stoa ask`/`respond` (post-v0.1), distributed hex IDs, and `reconciliation` type address this directly: primitives required for the team shape Stoa actually has (5+ timezones, no synchronous overlap).
5. **The artifact has always been the cheap part; the operational layer is the gap.** Until AI was good enough to interpret a loose schema and absorb the maintenance cost, the operational layer was unaffordable. AI flips that economics. Stoa is what the operational layer looks like once it does.

The table below summarizes the surface-level deltas; the deeper claim is that **Stoa is to ADR what CI is to running tests by hand**. The artifact existed; the operational discipline that makes it routine is the new thing.

**Where Stoa departs from ADRs:**

| Concern | ADR | Stoa |
|---|---|---|
| Granularity | One file per decision | Append-only WAL (one file or split-by-time) |
| Lifecycle states | proposed / accepted / superseded | commit / wont-do / table / branch / observation / rollback / reconciliation |
| AI-as-interpreter | Not assumed | Foundational |
| Multi-role / multi-laptop | Silent | First-class (Slack-bridged ask/stoa respond) |
| Refining (in-flight) | Implicit | Named primitive distinct from durable record |
| Integrations | Not addressed | Slack + Jira first-class; KB folder for everything else |

### The closest contemporary cousin: the Design-Log Methodology

[Wix Engineering, 2025](https://www.wix.engineering/post/why-i-stop-prompting-and-start-logging-the-design-log-methodology) ([DEV mirror](https://dev.to/cypheroxide/stop-prompting-use-the-design-log-method-to-build-predictable-tools-2773)). A `./design-log/` folder of markdown decisions, version-controlled, designed explicitly so AI can read project history. Pillars: "Read Before Write," "Design Before Implement," frozen-design + appended-results, Socratic-questions-in-log.

This converges on much of Stoa's spirit independently: strong validation that the direction is right.

**Stoa's differentiators relative to Design-Log:**

- Append-only WAL with explicit transaction states vs. one-file-per-decision (ADR-shaped).
- Multi-role / multi-laptop collaboration as a first-class concern; Design-Log is single-author.
- Refining sessions as a named primitive distinct from the durable record; Design-Log doesn't model the in-flight phase.
- First-class Slack + Jira integration with KB folder for everything else; Design-Log doesn't address integrations.

### The closest agentic-implementation cousin: Kiro (kiro.dev)

[Kiro](https://kiro.dev/) is an AWS-built agentic IDE (VS Code base, Claude Sonnet 4.5) that markets **spec-driven development**. Each spec produces three files committed to the repo: `requirements.md` (using [EARS notation](https://teachmeidea.com/kiro-ai-ide-spec-driven-development/) — Easy Approach to Requirements Syntax, originally Rolls-Royce), `design.md` (architecture + sequence diagrams), `tasks.md` (sequenced implementation tasks). Has agent hooks (event-triggered background tasks), MCP integration, per-prompt cost visibility.

Kiro independently validates several Stoa instincts: design / spec is a first-class repo artifact (not a separate doc silo), AI lowers the maintenance cost of structured artifacts, decision rationale must be capturable at the time of the decision (not reconstructed later), "vibe coding" without structure is a real failure mode.

**Stoa and Kiro sit at different seams.** They're complementary, not competitive:

| Concern | Kiro | Stoa |
|---|---|---|
| Position in the stack | Spec → code-generation seam (downstream) | Human-collaboration seam (upstream) |
| Schema | Strict (3 files, EARS notation) | Loose-framework with AI as interpreter |
| Authorship model | Single-author by default | Multi-laptop multi-role-native (`/stoa ask @<handle>`, solo catch-up, duplicate-logs reconciliation) |
| Decision record | Spec files ARE the record (history via git) | WAL distinct from canonical docs (explicit `rollback` linkage) |
| Form factor | Product (adopt the IDE) | Methodology (works with any AI client) |
| Install footprint | Adopt the IDE; switch your editor | One installer ([`dist/install.sh`](../dist/install.sh)) run in the repo root |
| Driver lock-in | Kiro IDE only | None — any agent that reads markdown drives it (Claude Code, Cursor, Codex, Copilot, Windsurf, ...) |
| Downstream-coder lock-in | Kiro is itself the coder | None — the WAL-grounded spec feeds *any* downstream agentic coder, including Kiro |

**The lightness contrast is structural, not stylistic.** Stoa is a small set of files at the repo root plus a delimited dispatcher block in `AGENTS.md`. Run [`dist/install.sh install`](../dist/install.sh) once and the methodology is live. There is no IDE to install, no service to provision, no vendor to standardize on. The driver (the agent that reads the WAL, runs refining sessions, proposes WAL entries) can be **any AI client your team already uses**: Claude Code today, Cursor next quarter, Codex on a sensitive workload, a self-hosted local model on a laptop that can't reach the cloud. Switching drivers does not migrate the methodology; the methodology is a file in the repo. Equally, the **downstream agentic coder** that consumes Stoa-produced specs is also unconstrained: Kiro is one valid consumer, but so is Claude Code in implementation mode, Cursor's agent, an internal CI-driven codegen pipeline, or a future tool that doesn't exist yet. Stoa is upstream-agnostic of the driver and downstream-agnostic of the coder by construction; it is the one piece that doesn't need to be re-picked when either side of it churns.

A team can adopt **both**: Stoa upstream of Kiro. **Where Kiro stops (single-author spec → execution), Stoa starts (multi-role async refinement of the spec itself, with the rationale chain preserved in the WAL).** The phased plan that lands as a Stoa `decision` WAL entry (refined sub-phases + PoC-validated assumptions per [Execution-validated design](#6-execution-validated-design)) is exactly the input Kiro-shaped tools implement cleanly. The "Stoa makes downstream agentic implementation work better" claim in [Scope](#scope--stoa-is-upstream-of-agentic-implementation) is concretized by Kiro as one valid downstream consumer. *(WAL: [`9d2f8a3`](../context_log.md#2026-05-09--observation--authors-ivanclaudeopus471m--9d2f8a3))*

### Validation from RFC-process literature

A 2026 survey of GitHub-centric design-doc review (per WAL [`c5e4f81`](../context_log.md#2026-05-08--observation--authors-ivanclaudeopus471m--participants-research-subagentclaudeopus471m--c5e4f81)) found that [PEP 1](https://peps.python.org/pep-0001/) **explicitly discourages PR-line comments for substantive issues**, citing fragmentation, and routes substantive discussion to a separate canonical thread (Discourse / mailing list). Stoa's WAL is structurally that canonical thread: the methodology converges with a battle-tested PEP discipline by independent design. The survey also confirmed that the GDocs-comment-UX gap on in-repo markdown is real, widely felt, and unsolved as of May 2026; the [design-docs](https://github.com/iavramov/design-docs) round-trip pattern (canonical markdown + GDocs-as-render-only-comment-surface) addresses the documented comment-reconciliation blocker.

### AI-tool-side context/memory mechanisms

Per-tool config files — Claude Code's `CLAUDE.md`, Cursor's `.cursor/rules/*.mdc`, Codex `AGENTS.md`, Copilot `copilot-instructions.md`, Windsurf `.windsurfrules` — are static instruction files, not decision logs. They tell the agent *how to work*, not *what was decided*. Stoa uses CLAUDE.md (or equivalent) for the agent rulebook role, but the WAL is a separate, complementary primitive.

Runtime memory frameworks — [Letta/MemGPT](https://github.com/letta-ai/letta), [Mem0](https://vectorize.io/articles/mem0-vs-letta), LangGraph + LangMem — provide three-tier or episodic/semantic/procedural memory for agents, but they are runtime infrastructure, not human-readable team-collaboration artifacts. They don't substitute for a decision log a human can read.

### The gap Stoa fills

No surveyed system combines all four:

1. WAL-style append-only log with explicit transaction states
2. Multi-role / multi-laptop human collaboration with lightweight handoff
3. AI-as-interpreter of a loose schema
4. First-class integrations (Slack + Jira) plus KB folder for everything else

ADRs hit (1) weakly; Design-Log hits (1) + (3); memory frameworks are runtime-only. **Stoa's distinctive contribution is binding decision-record discipline to AI-mediated multi-role collaboration as a methodology — not a tool.** *(WAL: [`7a3f128`](../context_log.md#2026-05-08--observation--authors-ivanclaudeopus471m--participants-research-subagentclaudeopus471m--7a3f128))*

---

## Open extensibility

Stoa names two **first-class** integrations:

- **Slack** — the messaging / notification fabric for refining-with-collaborators. First-class because the multi-role refining flow depends on a real-time bidirectional comms channel.
- **Jira** — the project-management hygiene surface. First-class because work tracking outside the WAL (sprints, roadmap, ownership) is a real organizational concern.

**Everything else is loose.** Zoom-transcript ingestion is "drop the file in `knowledge-base/`"; PDFs are the same; alternative chat tools or ticket trackers are user-discretion adapters that Stoa does not specify but does not forbid. Federated / local AI providers (for sensitive workloads) plug in via the same actor grammar — `;<tool>(<model>)` accepts any model identifier.

**MCP servers are the recommended substrate for adapters.** The [Model Context Protocol](https://modelcontextprotocol.io/) is the modern integration interface that AI clients (Claude Code, Cursor, etc.) already speak. Stoa adapters — Slack, Jira, GDocs round-trip, future planning-channel broadcast — are most naturally implemented as MCP servers the AI session can invoke. Stoa does not specify a particular MCP server registry or hosting model; that's a deployment concern.

**The DB-with-WAL analogy.** Stoa is to AI-assisted development what a database with a WAL is to data persistence: opinionated about the **core consistency primitive** (the WAL), opinionated about **how transactions begin and end** (refining → commit), liberal about **client connections** (whatever tools the team uses to read/write the system). Slack and Jira are sanctioned client connections with documented adapters; others are encouraged but unsupported. *(WAL: #0008, [`9c2b5fa`](../context_log.md#2026-05-08--decision--authors-ivanclaudeopus471m--9c2b5fa), [`c8b4d09`](../context_log.md#2026-05-08--decision--authors-ivanclaudeopus471m--c8b4d09))*

---

## Doc-set scope (the suggestion menu)

A Stoa project has a small **mandatory** set:

- The WAL (`context_log.md`)
- The agent entry point (`AGENTS.md` with the `STOA::DISPATCHER` block; thin `CLAUDE.md` shim for Claude Code)
- The composed runtime (`stoa-claude.md` at the repo root — placed by `install.sh`)
- Knowledge base (`knowledge-base/`)
- The project's actual deliverables (code, IaC, content)

Beyond that, Stoa offers a **suggestion menu** of common document roles teams have found useful:

| Role | Use when... |
|---|---|
| Canonical spec (e.g. `design_doc.md`) | Architecture or system shape needs a single authoritative reference distinct from running code |
| Operational runbook (e.g. `RUNBOOK.md`) | Humans need step-by-step procedures to operate / deploy / debug |
| Audience-tailored summaries (e.g. `*_summary.md`, weekly notes) | Specific stakeholders need a framing the canonical docs don't serve |
| Scratch / forward-staged plans (e.g. `scratch-ideas/`) | Ideas in flight that need version control but aren't ready to be authoritative |
| External research summaries | Background research that informs decisions but isn't itself authoritative |
| Structured-requirements specs ([EARS notation](https://teachmeidea.com/kiro-ai-ide-spec-driven-development/)) | High-stakes requirement specification needs testable, machine-readable acceptance criteria — regulatory specs, API contracts, formal QA gates. Compatible with the loose-framework principle: it's a tool teams *can* pick when warranted, not a default. (Borrowed from Kiro's spec-driven model — see [Origin and prior art](#the-closest-agentic-implementation-cousin-kiro-kirodev) — [`9d2f8a3`](../context_log.md#2026-05-09--observation--authors-ivanclaudeopus471m--9d2f8a3).) |

Stoa does NOT require teams to instantiate this menu fully. A solo project might run with WAL + CLAUDE.md + README + code, nothing else. A multi-role enterprise project might use the full menu plus role-specific summaries. Both are valid Stoa projects. *(WAL: [`9c2b5fa`](../context_log.md#2026-05-08--decision--authors-ivanclaudeopus471m--9c2b5fa))*

---

## Getting started

The bootstrap mechanism is intentionally **mechanical**: fetch the unified [`dist/`](../dist/) bundle (locally if you've cloned the repo, or via `curl -fsSL https://raw.githubusercontent.com/ivan-avramov/stoa-ai/main/dist/install.sh | bash -s install|curl -fsSL https://raw.githubusercontent.com/ivan-avramov/stoa-ai/main/dist/install.sh |curl -fsSL https://raw.githubusercontent.com/ivan-avramov/stoa-ai/main/dist/install.sh | bash -s install` for the private-repo case) and run [`dist/install.sh install`](../dist/install.sh) in the target repo. One command installs every supported host (Claude + Codex) at once and:

- Injects a delimited `STOA::DISPATCHER` block into `AGENTS.md` (creating it if absent).
- Thins `CLAUDE.md` to `@AGENTS.md` (or creates it).
- Places the composed runtime `stoa-claude.md` at the repo root.
- Places spec-owned files: `.claude/commands/stoa.md`, `.claude/agents/stoa-*.md`, `.githooks/pre-commit`, `.stoa/hooks/{wal-audit,bootcheck-probe,session-bootstrap}`.
- Merges Stoa's SessionStart hook entry into `.claude/settings.json` (the boot-check hook — command `bash .stoa/hooks/session-bootstrap`, matchers `startup|resume|clear|compact`).
- Seeds-and-preserves templates: `.stoa/artifacts.md`, `.stoa/beta_tracker.md`, `context_log.md`, `.stoa/audit-cache` (committed, union-merged log of coherence certificates).
- Wires `git config core.hooksPath .githooks` (only when unset — an existing Husky/Lefthook path is left untouched), and writes the `merge=union` rules for `context_log.md` and `.stoa/audit-cache` to `.gitattributes`.
- Writes `.stoa/installed` with per-file content hashes.

Three artifact-ownership categories follow from that list. **Spec-owned files** (`stoa-claude.md`, the dispatcher block, the `.claude/commands` / `.claude/agents` / `.githooks` / `.stoa/hooks` files) are hash-checked and replaced on drift. **Seed-and-preserve templates** (`.stoa/artifacts.md`, `.stoa/beta_tracker.md`, `context_log.md`, `.stoa/audit-cache`) seed once and are never overwritten. **Merge-and-coexist** is the third, holding one member: `.claude/settings.json`. It is adopter-owned, so the installer merges only Stoa's single SessionStart entry — idempotently, via `python3` (no `jq` dependency), never clobbering adopter hooks or keys. Drift on it is detected by entry-presence, not whole-file hash. The `session-bootstrap` wrapper also self-activates `core.hooksPath` (non-clobber) on the first trusted session, so a fresh clone self-heals its git backstops without an explicit install.

Re-running `install.sh install` upgrades — content-hash drift detection replaces spec-owned files where source has changed; seeded templates are never overwritten; the SessionStart entry is re-merged only if absent. A `doctor` mode (`install.sh doctor`) diagnoses install state without modifying anything. An `uninstall` mode (`install.sh uninstall`) surgically removes Stoa's SessionStart entry, the spec-owned files, and the dispatcher block, unsets `core.hooksPath` only if it is Stoa's `.githooks`, and **preserves operator data** — `context_log.md`, `.stoa/artifacts.md`, and `.stoa/beta_tracker.md` are left in place.

**Why a build-script-driven bundle rather than a single self-extracting file:** the previous iteration was a single self-extracting `stoa.md`. That worked for solo dogfooding but didn't scale — adapter content (host-specific subagent invocation, hook semantics, command dispatch) couldn't stay clean inside one host-neutral markdown file, and the self-strip mechanic accumulated failure modes. The current architecture separates editable canonical source ([`src/`](../src/)) from a unified distribution ([`dist/`](../dist/), with shared machinery at the root and per-host payloads under `dist/claude/` and `dist/codex/`) composed by a dumb concatenation composer ([`build/compose.sh`](../build/compose.sh)). The composer is host-agnostic; `install.sh` installs every supported host in one pass. Codex ships in beta from `src/adapters/codex.md` + a manifest entry, with the shared methodology source unchanged. The boot-check mechanism carries over — the same read-only probe runs from a Codex SessionStart hook wired through `.codex/hooks.json` + `.codex/config.toml` instead of Claude Code's `.claude/settings.json`. Codex install mechanics and the live boot path (the SessionStart hook firing, bootcheck injection, and native-subagent spawn — autonomously, including under a restrictive tool policy and via the generic-launcher fallback) are validated on a real Codex CLI; skill loading and the behavioral surface (prose-intent routing, the WAL guardrail, drift detection) remain to be confirmed — see [`tests/codex-smoke-test.md`](../tests/codex-smoke-test.md).

For the operator-facing install walkthrough, see [getting_started.md](getting_started.md).

### Bootstrap scenarios

**1. Brand-new project, brand-new team.** Empty repo, no prior context.
- Run [`dist/install.sh install`](../dist/install.sh) in the empty repo. Install creates `AGENTS.md` with the dispatcher block, a thin `CLAUDE.md`, the composed runtime `stoa-claude.md`, and the rest of the spec-owned + seeded files.
- First refining session is *the project itself*: "what are we building, why, who's involved?" First WAL entries land in `context_log.md`.
- Tracked artifacts list grows organically via `[stoa]` proactive suggestions and `/stoa init` / `/stoa track` operator commands.

**2. Brand-new project, team with prior context.** No code yet, but the team has Zoom transcripts, prior research, vendor docs.
- Same as #1, but pre-populate `knowledge-base/` with relevant material before the first refining session.
- AI ingests `knowledge-base/` to ground the early refining.

**3. Existing project mid-flight.** Code, tribal knowledge, git history, chat scrollback exist; methodology being layered on. The hardest case.
- **Selective backfill:** AI scans codebase + git log, drafts WAL entries for the most load-bearing decisions ("we use DynamoDB because…"). Team reviews, accepts/edits. Heavy upfront, complete record.
- **Just start:** Empty WAL. New decisions land here. Old decisions stay tribal until they need revisiting; on revisit, they get logged. Lightweight, gradual.
- Both are valid. Most teams will pick "just start" with selective backfill of the most load-bearing decisions.

**4. New person joining an existing Stoa project.** The recurring case.
- At session start the SessionStart hook runs the read-only boot-check probe and injects its output; the AI renders the `[stoa-init]` block from that injection and reads `stoa-claude.md` (via the dispatcher block) to load the methodology. The first trusted session also self-activates the git backstops. (If the folder isn't yet trusted on this machine or the hook is otherwise blocked, the AI runs the probe itself per the degradation floor.)
- Run `/stoa orient` (when available): persona-aware briefing from current state.
- Manually: read recent WAL entries, decision-summary table, canonical docs, repo state. Start refining when ready.

**5. Existing project with existing `CLAUDE.md` or `AGENTS.md` (migration).** Common real-world bootstrap path.
- Run `install.sh install`. It detects existing files and proposes the right path: if `AGENTS.md` exists, the dispatcher block is injected (or replaced if a prior version is present); if only `CLAUDE.md` exists, a new `AGENTS.md` is created with the block and `CLAUDE.md` is prepended with `@AGENTS.md`. Existing operator content is preserved.
- The operator's `AGENTS.md` and `CLAUDE.md` content outside the delimited dispatcher block is **never** modified by re-running `install.sh`. Existing `.claude/settings.json` hooks and keys are likewise preserved — only Stoa's one SessionStart entry is merged. Stoa-version updates regenerate spec-owned files (the dispatcher block content, the composed runtime, hooks, subagent files) based on content-hash drift.
- The boot check surfaces install state at every session start; the operator can opt out at any time via `install.sh uninstall`, which preserves the WAL and the operator-owned templates.

### What ships in the bundle

The unified [`dist/`](../dist/) bundle is what adopters fetch. Shared machinery sits at the root; per-host payloads live under `dist/claude/` and `dist/codex/`, and one installer wires up whichever hosts are present.

At the root:

- [`install.sh`](../dist/install.sh) — adopter-facing installer covering every supported host. `install` mode handles fresh install + upgrade transparently; `doctor` mode diagnoses state without modifying anything; `uninstall` mode removes Stoa's machinery while preserving operator data. Supports local-mode (when the bundle is on disk) and remote-mode (`gh api` fetch for private-repo bootstrap).

Under `dist/claude/` (the Claude payload):

- [`stoa-claude.md`](../dist/claude/stoa-claude.md) — composed runtime. The full Stoa methodology in operational form. Adopters end up with a copy at their repo root.
- `AGENTS.md.dispatcher` — the dispatcher block content the installer injects.
- `CLAUDE.md.template` — the `@AGENTS.md` shim, used when no `CLAUDE.md` exists.
- `.claude/commands/stoa.md` — the composed `/stoa` dispatcher.
- `.claude/agents/stoa-*.md` — subagent procedure files.
- `.githooks/pre-commit` — the deterministic cadence #3 git hook.
- `.stoa/hooks/wal-audit` — the cadence #3 WAL audit hook.
- `.stoa/hooks/bootcheck-probe` — the read-only boot-check probe (install-state, drift, hook activation, orphan-T2, audit-cache coverage delta, attribution).
- `.stoa/hooks/session-bootstrap` — the SessionStart wrapper the merged `.claude/settings.json` entry runs: activates git hooks non-clobber, runs the probe, prints its output for context injection.
- `.stoa/templates/*` — seed files for `artifacts.md`, `beta_tracker.md`, `context_log.md`, `audit-cache`.

Under `dist/codex/` (the Codex payload, beta): the Codex composed runtime plus the Codex SessionStart binding (`.codex/hooks.json` + `.codex/config.toml`). Install mechanics and the live boot path (SessionStart hook + bootcheck injection + native-subagent spawn) are validated on a real Codex CLI; skill loading and the behavioral surface remain to be confirmed — see [`tests/codex-smoke-test.md`](../tests/codex-smoke-test.md).

Source: editable canonical content under [`src/`](../src/) composes into the per-host payloads under [`dist/`](../dist/) via [`build/compose.sh`](../build/compose.sh) (dumb concatenation per [`build/manifest.txt`](../build/manifest.txt)). No templating, no conditionals — content variation lives at the file level (different files in `src/adapters/`).

---

## What's not yet specified

Honest framing of what Stoa does NOT yet answer. These are queued for follow-up refining sessions; none block initial adoption.

**Workflow gaps:**

- **Git branching + PR review with long context chains.** When a feature branch carries weeks of refining + multiple WAL entries, how does merging integrate the branch's WAL with main's? How does PR review present a long context chain to a reviewer who wasn't in the refining sessions?
- **Manual-work-without-AI workflow.** A human edits a doc directly, no AI session involved. How is the WAL updated to capture the change — pre-commit hook prompting for a `manual-edit` entry, AI catch-up scan at next session start, explicit `/stoa log-manual-change` command? `manual-edit` type exists; the workflow around it doesn't.
- **Out-of-band WAL entries.** A side observation comes up while you're committing something else. Stoa supports it (just write an entry) but the workflow around "this is unrelated to the current commit" hasn't been refined. Probably trivial; worth stating.
- **Reconciliation process for multi-laptop duplicate logs.** v0 = manual / AI-assisted comparison. Triggers, automation, and entry shape need design.
- **WAL multi-file rotation.** v1 ships single-file. When a project's `context_log.md` grows past usable size (estimate: 20k-50k lines for active multi-role projects) the rotation strategy needs spec — file naming, cross-file references, the close-commit problem when an old file shouldn't accept new appends.

**Integration specs:**

- **Slack adapter spec.** Slash commands (`/stoa ask @<handle>`, `/stoa respond`, possibly `/stoa refine`), snippet attachment mechanics, snippet lifecycle/expiry, channel-to-repo binding. (No role-to-handle mapping; commands target Slack handles directly — see [`b4f2e9c`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--b4f2e9c).)
- **Jira adapter spec.** When a WAL entry implies a Jira ticket; when a Jira ticket gets its own WAL entry; how the two stay in sync; what happens on close/transition.
- **Federated / local AI for sensitive work.** Stoa's actor grammar admits any model identifier; the *mechanics* (does a local AI session sync via git only? does it have parity on context capabilities?) aren't refined.
- **Slack mandatory vs. optional per project.** Currently first-class but not mandatory; solo projects can skip. Worth stating explicitly per project via CLAUDE.md.

**Multi-project / cross-system:**

- **Repo discovery — "which repo do I even start in?"** The worked example assumes Manish "somehow knows" which repo holds the decisions relevant to his customer ask. Today's pattern is human-routed: Slack-ping someone you think should know, they point you at the doc. Not a hard blocker — same pattern works in the GDocs world today — but a **meta-repo / root knowledge-base** that catalogs the company's project repos (with handles + brief descriptions + canonical-contact pointers) would be a cheap accelerator. The same hook also addresses cross-repo decisions (next item).
- **Cross-repo dependencies.** When a decision in repo A affects repo B — cross-reference both WALs? Linked-decision primitive? "Owner" repo vs. "consumer" repo? Open thread. Likely shares the meta-repo / root-knowledge-base mechanism with the discovery problem above.
- **Diagram support.** How visual artifacts (architecture diagrams, sequence flows) participate in cross-references and the WAL. The trial used Excalidraw committed to repo + PNG renderings; whether to formalize this in Stoa or leave to teams' discretion.
- **Org-wide adoption mechanics.** Bootstrap of the methodology *itself* in an org with N existing projects. Tabled per WAL entry [`b7e0c14`](../context_log.md#2026-05-08--table--authors-ivanclaudeopus471m--b7e0c14); revisit when 2-3 individual projects have used Stoa in production.

**Tooling / lifecycle:**

- **The Stoa tooling reference.** Skills shipped with Stoa (`/stoa init`, `/stoa orient`, `/stoa backfill`, `/stoa ask`, `/stoa respond`, plus the Path-A doc-review tools `/stoa publish-doc`, `/stoa fetch-comments`, `/stoa triage-comments`, `/stoa request-review`) are named but not specified. Probably belongs in a separate "Stoa tooling reference" doc.
- **Project automation via GitHub.** Server-side counterparts to local Stoa hooks: GitHub Actions for pre-merge coherence checks (mirror of `/stoa check-coherence` running on PR open / push), PR description templates referencing relevant WAL entry IDs, Stoa-version validation (does a branch's CLAUDE.md match a known-good Stoa release?). Currently the methodology specifies only *local* enforcement (git hooks via `/stoa install-hooks`); a server-side story is needed for teams that want enforced discipline beyond opt-in.
- **Comments-and-review section open sub-threads.** Per WAL [`3a72b09`](../context_log.md#2026-05-08--branch--authors-ivanclaudeopus471m--3a72b09): WAL integration shape in triage workflow, notification mechanism for new comments, multi-doc project scaling, OAuth-setup friction handling, comment thread depth round-tripping, behavior under heavy in-flight revision, `design-docs` productization plan. *The "Comments and review on design docs" section above is a draft on these sub-threads.*
- **Well-tracked unaddressed-items list as a Stoa primitive.** Per WAL [`7b1e9d4`](../context_log.md#2026-05-08--table--authors-ivanclaudeopus471m--7b1e9d4) (tabled). Currently *What's not yet specified* (this section) is the only mechanism. Idea: every Stoa project gets a built-in mechanism — a dedicated `OPEN_THREADS.md` file the AI maintains, a `/stoa list-open` slash command synthesizing pending items from the WAL + repo, `/stoa orient` surfacing them by default. Refining session deferred until comments-and-review settles.
- **`design-docs` productization status.** PoC implementation, single-author validation. Path A claims in this proposal are pattern-sound but tooling-unproven at scale.
- **Methodology versioning.** The Claude-first refactor removed SemVer stamps from the operational spec entirely. Update propagation runs via re-running [`dist/install.sh install`](../dist/install.sh) (compares per-file content hashes recorded in `.stoa/installed` against the current bundle; replaces spec-owned files where drift is detected; seeded templates untouched). No version-stamp arithmetic; no `/stoa upgrade` command. The original dual-stamp resolution (calendar + adoption-package version) was consolidated to a single SemVer stamp ([`75787857`](../context_log.md#757878578cf44e279611b0fe324ce371--decision--2026-05-24)), then the SemVer stamp itself was removed from spec content in the Claude-first refactor ([`5a1835bb`](../context_log.md#5a1835bb2fd54cab9c27d76ee4fde121--decision--2026-05-27)).
- **PAT-expiry-style failure modes for AI providers.** What happens when a model is deprecated mid-project; how the WAL's `;tool(model)` references behave when the named model no longer exists.
- **Watch-item — adjacent-platform AI features as an early-fail signal.** Notion AI, Linear's project docs + AI assist, Confluence AI, and GitHub Copilot Workspace are all evolving toward "team-grade memory of decisions with rationale chains" inside their existing surfaces. If any of them lands a credible "auditable decision history with supersession links and AI-mediated cross-cutting synthesis" feature inside the surface a team already uses for project tracking, the wedge for a separate methodology-as-file approach narrows. **Beta-retrospective question:** *"Did adopters reach for Stoa, or for whichever platform their team already lives in?"* If the answer is the latter, the right move is to fold Stoa's primitives (append-only WAL, refining sessions, supersession discipline, execution-validated design) into a positioning that complements those platforms rather than tries to substitute for them. This is also the natural moment to revisit [Positioning](#positioning--what-stoa-is-and-isnt) — internal-methodology stays, but the form factor may shift.

**From the worked-example refactor (per WAL [`4f8c3a2`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--4f8c3a2)):**

- **Planning-channel broadcast spec.** The worked example ends with a notification post to a company-wide planning channel linking the Jira + WAL entry + Slack thread. Mechanism intentionally under-specified — likely a `/stoa announce-plan` slash command or part of the Jira adapter spec. Light enough to skip in a beta-test rollout.
- **Phased-plan sign-off as a usage pattern.** Manish + Ravi sign off the phased plan in the worked example. Not a new primitive — each signer writes a `decision` entry (or is named as Participant on the plan entry); happens at any scope, large or small. Naming this pattern explicitly so it doesn't get reinvented per-project.
- **`/stoa catch-up <thread>` slash command.** v1's solo catch-up mechanism is ad-hoc per loose-framework principle: operator says "Claude, here are the snippets, reconcile against the WAL." A future `/stoa catch-up` could formalize the snippet-fetch + WAL-reconciliation step. Not blocking adoption.

**From the Kiro prior-art research (per WAL [`9d2f8a3`](../context_log.md#2026-05-09--observation--authors-ivanclaudeopus471m--9d2f8a3)):**

- **Bug-fix worked example.** Kiro distinguishes feature specs from bug specs (the `bugfix.md` shape). Stoa's only worked example is a feature/architecture decision; a bug-fix worked example (smaller, faster, no multi-week tabling) would round out the proposal and make the methodology feel right-sized for everyday work, not just multi-quarter arcs.
- **Rapid solo prototyping walkthrough.** Kiro markets weekend-to-prod timelines. Stoa's "Solo project, no Slack" bootstrap covers this in spirit; a quick-mode walkthrough in [getting_started.md](getting_started.md) — "smallest viable Stoa for a solo prototype" — would land the use case for solo developers and small startups who want decision discipline without ceremony.
- **Stoa → agentic-implementation handoff worked example.** The directional claim in [Scope](#scope--stoa-is-upstream-of-agentic-implementation) ("Stoa makes downstream agentic implementation work better") is currently abstract. A concrete worked example showing how a Stoa phased-plan WAL entry feeds Kiro / Claude Code agents / Cursor — including what the agentic tool reads, what it does, and how its output flows back if it discovers something — would make the seam tangible.
- **Multi-spec / multi-feature project scenario.** The current worked example is single-thread (Customer-X external GPU compute). A "what does this look like at 5 features in flight" appendix or worked example would show threaded refinement at scale and AI-mediated reconciliation in action across concurrent design tracks. Kiro implicitly handles N specs in one project via N spec folders; Stoa handles N concurrent topics via `branch` WAL entries and the staggered-tracks model — the parity is worth demonstrating.
- **Agent hooks generalized library.** Kiro has event-triggered background tasks. Stoa v0.1 BETA has the three-trigger AI-discipline coherence cadence (pre-commit drift, post-decision propagation, on-demand `/stoa audit` per [`d5a8f10`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--d5a8f10)) but **no deterministic event hooks**. A small hook library — WAL-drift detection on commit, post-decision propagation as an actual hook (not relying on AI to remember), planning-channel auto-broadcast on phased-plan-decision-entry, summary-doc auto-refresh — would extend value-prop #7 (self-consistent state) from AI-compliance-based to deterministically-enforced. Beta retrospective question: *"Did operators stop having to ask?"* If yes, AI-discipline is enough. If no, escalate to hooks.
- **Cost-transparency surface.** Stoa's actor grammar names `;tool(model)` but provides no aggregate view. A `/stoa cost-report` synthesizing per-WAL-entry AI spend across a project would surface a dimension teams care about (especially at scale). Niche but real; Kiro's per-prompt cost visibility is the inspiration.

---

## Scalability — the WAL bottleneck

The WAL is the methodology's centerpiece, and its hardest scaling question. Beyond a few MB, single-file WALs strain AI synthesis: the corpus exceeds usable subagent context budgets, new-joiner orient becomes infeasible, and cross-cutting queries get slow.

**Empirical reference points:** the adopter PoC's `conversation_log.md` is 316KB / 42 entries after ~3 months active development. This proposal's `context_log.md` is 136KB / 36 entries after ~1 month. Average entry size ~5-7KB — uncomfortably high relative to a leaner 1-3KB target. Commit-count proxies suggest typical Stoa projects produce **~3-30MB of WAL over their lifespan**; of 17 Stoa repos surveyed, roughly half are at or past the single-file cliff if Stoa were retroactively applied. (Full empirical analysis: WAL [`e7c4b29`](../context_log.md#2026-05-10--observation--authors-ivanclaudeopus471m--e7c4b29).)

**Agent-first access architecture.** The WAL is curated, high-relevance-density data: at slurp-feasible scale, an Agent reasoning directly over the loaded corpus produces better coherence judgments than embedding-based pre-filtering. The vector index is positioned as a **scale-extension fallback** when the WAL outgrows what a subagent can slurp, not as the primary substrate. The slurp budget — empirically ~30% of a subagent's context window — sets the threshold; below it, direct reasoning wins on quality; above it, retrieval extends viable scale.

**Where the cliffs are:**

| Project age / WAL size | Tokens | Access pattern |
|---|---|---|
| 0-1y / <1MB | <250K | Slurp feasible: subagent loads the WAL directly and reasons over the corpus. Lexical/positional lookups stay on grep. Vector index optional. |
| 1-3y / 1-3MB | 250K-750K | Slurp still feasible at the upper end of subagent context budgets; retrieval becomes the alternative for tight-latency mid-session checks. |
| 3-10y / 3-15MB | 750K-3.75M | Retrieval (`/stoa query`-backed) takes over as primary. Slurp reserved for high-recall checkpoint moments (cadence #6, end-of-impl, pre-substance grounding per WAL-grounding rule). |
| 10y+ / 15MB+ | 3.75M+ | Retrieval baseline; operator-UX considerations may motivate WAL rollover (deferred; see [`4d7f1a8`](../context_log.md#4d7f1a8)). |

**What scales naturally:** append-only writes (O(1)), targeted grep + read (~10MB ceiling), GitHub markdown rendering, conflict-free git merges. **What needs the index at scale:** whole-WAL synthesis when the corpus outgrows a subagent's slurp budget, cross-arc semantic discovery under terminology drift, cadence #6 M×N pairwise audit on large deltas.

**Mitigation paths, layered:**

1. **Entry-size discipline** (v0.1+): push toward 1-3KB entries with link-out for depth. Cheap; should already be applied.
2. **AI access pattern discipline** (v0.1+, formalized in [`stoa.md`](../stoa.md) §"WAL access pattern"): never slurp into parent context. The main agent routes by a parent-context-lean principle — handle in the parent whatever you can name and fetch with a bounded targeted read; for queries that require surveying entries you can't enumerate up front — cross-cutting synthesis, orient-style "where are we?", multi-entry history, any coherence-shape question — **delegate to a WAL-librarian subagent**, which composes its retrieval (slurp, grep, semantic) to meet its coverage obligation. Subagents already exist in Claude Code; this is AI-discipline, not new tooling.
3. **Vector index over the WAL** (installed by default, best-effort): semantic-retrieval substrate for when the WAL outgrows slurp. Local `sqlite-vec` + `BAAI/bge-base-en-v1.5` (selected empirically over alternatives — see WAL [`c4f9e87`](../context_log.md#c4f9e87)); gitignored; hook-maintained. **Ships + installs by default**, built best-effort by `install.sh` (degrades to slurp+grep if the environment can't build it; `STOA_NO_INDEX=1` opts out; `/stoa index install` repairs). Use stays slurp-primary per OP1 — the index is a *use*-fallback engaged only beyond slurp. See WAL [`7e9c4a3`](../context_log.md#7e9c4a3) (architecture), [`d45489b7`](../context_log.md#d45489b75cb246298c9ddb9fe6717e46--rollback--2026-05-18) (vector inversion to scale-extension fallback), [`d5b9df87`](../context_log.md#d5b9df8715a448ada7e04f6b9aa997af--decision--2026-05-18) → [`f16a4142`](../context_log.md#f16a414274554962a92fdf50470f1777--rollback--2026-06-03) (opt-in install, reversed to always-install), [`e192c0fc`](../context_log.md#e192c0fc55f4404aac5aad91ea35fdbf--decision--2026-06-03) (always-ship design).
4. **AI-generated digest** (deferred): periodic summary of current state + key decisions. Live WAL appends as before; digest is the fast-read entry point. Cadence and format open.
5. **WAL rollover / log-splitting** (tabled, see [`4d7f1a8`](../context_log.md#4d7f1a8)): file-size-of-`context_log.md` mitigation. With slurp + retrieval covering the AI-context-pressure mitigation, the remaining motivation is operator-experience (editor lag, diff noise, GitHub web view). Design sketched; deferred pending empirical operator-UX pain.

**WAL grounding before substantive proposals.** AI must ground substantive ideas — proposals, settlements, recommendations, paths forward — in `context_log.md` via the WAL-librarian subagent *before* surfacing them to the operator. The trigger surface mirrors cadence #7's: any moment AI is about to author a substantive direction (proposal, recommendation, settlement nudge, completion summary that frames a next step). Skip only on plainly non-substantive moments: acknowledgments, clarifying questions, mechanical lookups (hex-by-ID, recency-by-date, literal grep). Apparent novelty of the operator's topic is **not** grounds for skipping — the relevant prior arc may be on adjacent vocabulary; the subagent's job is to find it. Thread-continuity ("we just discussed this") is also not grounds — sessions span `/compact` and `/clear` boundaries that destroy continuity assumptions. Engineering-shape: this shifts the WAL-librarian subagent from **reactive** (invoked when the parent AI recognizes a non-trivial query) to **proactive** (invoked as a groundedness gate before substantive output). The rule sits on top of OP1 (Agent-first quality on the curated decision forest — direct reasoning over the WAL is preferred to embedding-based pre-filtering) and OP2 (pre-delegation settling — substantive direction settles before delegation). Cost is one extra subagent invocation per substantive turn; benefit is that AI cannot surface a proposal that contradicts, duplicates, or ignores settled WAL content.

**Retrieval-scopes rule.** Coherence-check operations consult three retrieval scopes in order regardless of how the subagent composes its retrieval: **In-flight scope** (candidates proposed this turn but not yet in WAL; relevant when N>1 candidates land in the same batch), **WAL-not-indexed scope** (entries newer than the index's last-indexed marker; the staleness gate handles the inline embed transparently), **Indexed-WAL scope** (standard retrieval when the index exists at scale). The rule keeps intra-batch contradictions and just-appended entries in scope; without it, both classes get missed. See WAL [`a8a0b715`](../context_log.md#a8a0b7155913467b9c1ab1cbc027437a--decision--2026-05-18). The rule was renamed from "Three-tier consultation" to "Retrieval scopes" ([`789194aa`](../context_log.md#789194aaf6e54c77a98b49813405f90b--observation--2026-05-26)) to eliminate vocabulary collision with the three-tier WAL model (T1/T2/T3) and two-layer coherence (Layer 1/Layer 2).

---

## How to start tomorrow (smallest viable adoption)

The 30-minute exercise that validates Stoa on a real piece of work without committing to the rest:

1. Pick an active design question on a project you're already working on.
2. Run [`dist/install.sh install`](../dist/install.sh) in the repo (see [getting_started.md](getting_started.md) for the full command).
3. Open Claude Code; ask *"help me start a refining session on \<question\>."*
4. Refine until you reach a conclusion.
5. The AI writes the WAL entry autonomously; you see the `[stoa] appended ...` anchor in the same turn.
6. Commit the entry. That's your first stone in the cairn — no, in the stoa.

If the result feels like a useful artifact, keep going. If it feels like ceremony, stop. The methodology earns its place by producing readable artifacts that your future self (and your stakeholders) actually want.

---

## A spark — Stoa beyond software?

An afterthought, on the way out.

Stoa's substrate is *decision-driven creative-or-engineering work*. The PoC validated software design, but the underlying primitives — append-only WAL, refining sessions, tracked-artifact coherence, AI as interpreter, loose framework — are domain-agnostic by construction. They plausibly apply anywhere decisions accumulate over time and a team needs the rationale to survive.

Some shapes that might fit:

- **Novel writing.** Plot file as source of truth; chapter files derived from it. Decisions about character arcs, theme, pacing land in the WAL. AI checks chapter coherence against the plot when either side changes.
- **Movie production.** Screenplay + shot list + schedule. Decisions about casting, location, scene cuts, budget tradeoffs. AI surfaces inconsistencies before the shoot, not in post.
- **Songwriting.** Lyrics + structure + production notes. Decisions about key, tempo, sound palette, narrative arc. WAL preserves the why behind a take that didn't land but informed the one that did.
- **Automotive parts design.** CAD source + tolerance specs + test plans. Decisions about materials, geometry, manufacturability. WAL holds the why a tolerance was chosen and which alternatives were considered.
- **Business planning.** Strategy doc + OKRs + budget. Decisions about markets, pricing, hiring. AI synthesizes "what was decided about X" across multiple planning cycles.
- **Portfolio design and management.** Investment thesis + holdings + rebalancing rules. Decisions about allocations, risk posture, thesis evolution. The WAL becomes the audit trail regulators or LPs ask for.

What's portable across domains: the methodology core (the primitives above). What needs adaptation per domain: integration adapters (the equivalents of git/Slack/Jira), vocabulary recipes (what to call things), default cadences (parallel-and-tight in software vs. sequential-and-slow in some creative pipelines), and how much value AI can usefully add today (current models are strong on prose-consistency, decent on plot-coherence, weaker on judgment-heavy creative novelty or specialized engineering tolerance analysis — *Stoa's value tracks the AI's domain affordances*; see [§What this means in practice](#what-this-means-in-practice)).

We have not validated this. Cross-domain claims here are hand-traced reasoning, not evidence. **If you adapt Stoa to a non-software domain — try it on a novel, a song, a business plan, a regulated portfolio, anything — we'd love to hear what worked, what cracked, and what needed reshaping.** Cross-domain feedback is the only way the generalization story moves from speculation to substance. *(WAL: [`a4d9e02`](../context_log.md#2026-05-09--decision--authors-ivanclaudeopus471m--a4d9e02))*

---

## Working notes

(Iteration scratch — items here are not yet in the proposal proper. Delete before sharing.)

- Need to write the actual starter CLAUDE.md as a separate file.
- The "How design becomes auditable" angle could be expanded into a worked example — show a stakeholder asking "what was decided about X" and an AI session producing the answer from the WAL.
- The Slack adapter spec is the largest piece of follow-on work. Probably its own document.
- Diagram support open thread — the trial used Excalidraw + PNG renderings. Whether to formalize this in Stoa or leave to teams' discretion.
- "PAT-expiry-style" failure modes for AI providers — probably worth its own paragraph somewhere.
- Methodology versioning approach — calendar-based ("Stoa as of YYYY-MM-DD") vs. semver. Lean toward calendar.
- Consider: a `stoa-changelog.md` documenting the methodology's own evolution over time, eating its own dogfood.
