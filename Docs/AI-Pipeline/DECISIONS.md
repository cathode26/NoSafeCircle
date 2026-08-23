# Architecture Decisions — No Safe Circle AI Pipeline

This is a lightweight decision log. Add new entries when a decision materially changes how the pipeline operates.

---

## ADR-001 — Repository state beats conversation memory

**Decision:** Persistent pipeline state, work definitions, dependencies, and architectural documentation live in the repository.

**Reason:** AI chat contexts are temporary and may not contain all prior detail.

---

## ADR-002 — Local supervisor owns autonomy

**Decision:** Claude does not own the infinite/continuous loop. A local deterministic supervisor chooses and launches bounded worker executions.

**Reason:** This allows recovery from session limits, failures, restarts, and cost limits.

---

## ADR-003 — Claude receives one bounded ticket

**Decision:** Normal coding workers receive one work contract rather than the whole project roadmap.

**Reason:** Reduces token use, scope drift, and repeated rediscovery.

---

## ADR-004 — Task dependency graph is persistent and local

**Decision:** Work items are stored as local artifacts with explicit dependencies. Local code calculates ready/actionable work.

**Reason:** Dependency readiness is computation, not something an LLM should reconstruct on every run.

---

## ADR-005 — GitHub is the dashboard, not the project brain

**Decision:** Local/versioned work artifacts define durable work. GitHub Issues/Projects/PRs mirror operational state and provide human visibility.

**Reason:** Workers need fast deterministic local access, while the user needs a convenient remote dashboard.

---

## ADR-006 — `main` is protected from autonomous direct development

**Decision:** Each coding ticket gets its own branch and preferably its own Git worktree.

**Reason:** Provides isolation, reviewability, recovery, and a path to future parallelism.

---

## ADR-007 — Done means merged

**Decision:** An implementation task satisfies downstream dependencies only after its implementation is merged into `main`.

**Reason:** Code existing on an unmerged worker branch is not project state.

---

## ADR-008 — RAG is the canon retrieval layer

**Decision:** Assignment 4 RAG retrieves relevant GDD evidence for work instead of repeatedly sending the entire GDD to an LLM.

**Reason:** Reduces context size and keeps generated work grounded in canonical design information.

---

## ADR-009 — Assignment 3 crew executes tickets

**Decision:** Planner → Implementer → Validator operates inside one selected bounded implementation task.

**Reason:** The persistent graph decides WHAT to build; the crew decides HOW to build that bounded work.

---

## ADR-010 — GER is the bounded self-correction loop for project work

**Decision:** Assignment 6 GER (Generator/Implementer → Evaluator → Refiner → Circuit Breaker) is used as the general bounded repair pattern for work that can be evaluated and refined, including Unity implementation code and generated game/content artifacts.

**Reason:** Assignment 6 successfully used GER to implement and repair the isometric camera. The architecture therefore should not restrict GER to generated content. The useful abstraction is a bounded work product with explicit acceptance evidence, structured failure feedback, refinement, and escalation.

**Supersedes:** The earlier wording "GER gates generated artifacts."

---

## ADR-011 — Cheap deterministic validation should run before expensive semantic review when practical

**Decision:** Git checks, scope checks, static checks, Unity compilation/tests, and other deterministic validation should detect cheap/objective failures before spending model tokens on fresh semantic review whenever the work allows it.

**Reason:** Do not spend model tokens on failures a local tool can detect.

**Clarification:** This does not mean deterministic checks alone can approve interactive Unity behavior.

---

## ADR-012 — Newly discovered substantial work becomes a task

**Decision:** A worker that discovers a substantial independently-testable prerequisite must stop/block rather than silently absorb it.

**Reason:** Preserves work scope and keeps the dependency graph truthful.

---

## ADR-013 — Start with one worker

**Decision:** Continuous parallel Claude workers are deferred until one-ticket execution is reliable.

**Reason:** Unity scenes, prefabs, `.meta` files, and shared systems can create expensive merge conflicts.

---

## ADR-014 — Every autonomous loop has budgets/circuit breakers

**Decision:** Ticket execution, repair, artifact generation, and GER loops have runtime/retry/cost limits and escalate when exceeded.

**Reason:** Autonomous must mean bounded safe progress, not unlimited token spending.

---

## ADR-015 — Runtime evidence is first-class validation input

**Decision:** For visual, interactive, timing-sensitive, or scene-dependent Unity behavior, runtime evidence must be able to fail a task even when static/GDD evaluation passes. Runtime failures are converted into structured feedback and re-enter the Refiner loop.

**Reason:** Assignment 6's camera passed static evaluation while facing the wrong direction, lacking usable following behavior, and later framing the game incorrectly. Unity runtime testing found defects the source-level evaluator did not.

---

## ADR-016 — A no-op refinement is failed progress

**Decision:** If unresolved failures remain and a Refiner produces no relevant project change, that attempt is counted as a failed repair and consumes repair budget.

**Reason:** Assignment 6 observed a Refiner reporting `implemented` while making no changes under `Assets/`. Accepting that result would allow false success or an infinite repair loop.

---

## ADR-017 — Validation should produce an evidence/feedback bundle

**Decision:** Work validation should aggregate required deterministic, Unity/runtime, and semantic evidence into a form that can either approve work or produce structured Refiner feedback.

**Reason:** Assignment 6 succeeded once Unity observations could be fed back into the same repair loop. A single evaluator result is too narrow for many game-development tasks.

---

## ADR-018 — Old goal-selection artifacts are not current codebase truth

**Decision:** Saved Assignment 5 planning/goal-selection output may be reused as historical evidence, but completion and readiness must be reconciled against the current `main` branch before seeding the durable dependency graph.

**Reason:** Assignment outputs can become stale as features are merged or changed. Persistent project state must reflect the repository that actually ships.

---

## ADR-019 — The pipeline must advance the game while it is being built

**Decision:** After the minimum deterministic work graph exists, pipeline work should be exercised on real ready No Safe Circle gameplay work rather than waiting for the entire autonomous platform to be finished.

**Reason:** The pipeline is infrastructure for developing No Safe Circle, not a separate capstone that should indefinitely block game progress. Real work will expose the next infrastructure requirements more accurately than speculative over-building.

---

## ADR-020 — Style evaluation is an evaluator specialization, not a separate architecture

**Decision:** When Assignment 7/player-facing content is ready, style enforcement should plug into GER as a specialized scored evaluator that returns `SCORE + REASON` and feeds the Refiner.

**Reason:** Assignment 7 uses the same Generator → Evaluator → Refiner structure already proven by Assignment 6. Reusing the execution architecture avoids parallel pipelines and allows style checks to remain tied to actual No Safe Circle content.

**Clarification:** Style evaluation does not authorize creation of new canon or design content. Artifact creation must already have passed the Artifact Authority Gate before the Style Evaluator is used.

---

## ADR-021 — Task decomposition is progressive and just-in-time

**Decision:** The pipeline does not attempt to fully decompose the entire capstone into low-level implementation tickets in advance. High-level work is expanded as it approaches the actionable frontier.

**Reason:** Distant work often lacks design information, and premature decomposition either wastes LLM reasoning or causes invented requirements.

---

## ADR-022 — Missing design creates an artifact proposal, not silent invention

**Decision:** When work cannot be concretely decomposed because required design/content is missing, the Decomposer proposes a new artifact dependency instead of inventing the missing information during implementation.

**Reason:** Implementation agents must not silently become game designers or turn hallucinated decisions into project requirements.

---

## ADR-023 — Generated design requires authority before generation

**Decision:** A proposed design/content artifact must pass an authority check before generation. The check identifies why the artifact is needed, which existing requirements permit expansion, and which areas are outside its authority.

**Reason:** Evaluating whether generated content is good is different from deciding whether the AI was allowed to invent that content in the first place.

---

## ADR-024 — Approved artifacts may become subordinate project design state

**Decision:** After passing authority and required post-generation evaluators, an approved artifact may become trusted downstream design input subordinate to the GDD.

**Reason:** Progressive decomposition needs a durable way to carry forward authorized design decisions without forcing later agents to regenerate or reinterpret them.

**Constraint:** Approved artifacts may add detail where canon permits expansion but may not contradict or silently replace GDD canon.

---

## ADR-025 — Reconciliation results are immutable point-in-time snapshots

**Decision:** Every full Reconciliation Agent run creates a new versioned snapshot. A later run never overwrites an earlier reconciliation snapshot, and later gameplay progress never edits old reconciliation results.

**Reason:** Reconciliation answers what the GDD and integrated repository looked like at one moment. Keeping that evidence immutable preserves an audit trail and prevents historical observations from being confused with the living operational work state.

**Implementation note:** `Pipeline/Reconciliation/outputs/LATEST.json` may be overwritten as a convenience pointer, but the snapshot directory it references is append-only.

---

## ADR-026 — Reconciliation proposes graph deltas but never directly mutates the persistent graph

**Decision:** Reconciliation output is compared against `Tasks/*.yaml` through a deterministic diff/review/apply boundary. The Reconciliation Agent may propose new, changed, conflicting, or stale work records, but it does not rewrite the persistent graph itself.

**Reason:** A new LLM interpretation must not trigger uncontrolled cascading edits across the project's operational state. Deterministic graph logic should own dependency satisfaction, readiness propagation, status derivation, and application of approved reconciliation changes.

**Bootstrap clarification:** Before `Tasks/*.yaml` exists, reconciliation emits proposed seed records. Human approval plus the deterministic Work Graph Seeder turns those records into the initial graph.



---

## ADR-027 — Reconciliation bootstrap requires independent multi-model verification

**Decision:** A reconciliation snapshot is not eligible for bootstrap seeding merely because the Generator and deterministic schema/graph validators succeeded. Before initial graph seeding, the candidate must be independently audited for GDD coverage, dependency/decomposition structure, repository evidence, and execution-scope suitability. At least two coverage audits use different requested Claude models when the configured model pool permits it.

**Reason:** Deterministic validators catch structural defects but cannot prove semantic completeness. A single model can correctly notice a requirement yet still bury it inside the wrong work item, omit a reusable required capability, or accept its own evidence framing. Independent role-specialized audits reduce correlated semantic failure.

**Finding policy:** Verifier findings are unioned, not majority-voted. One credible blocker/error must be resolved or explicitly escalated for human review.

**Refinement policy:** Material findings may produce a bounded refined candidate, but the original reconciliation snapshot remains immutable. The refined candidate is independently re-verified before human approval.

**Model policy:** Requested model assignments and the random assignment seed are saved with each verification run. Model diversity is an error-discovery technique, not a replacement for deterministic checks or the human approval gate.


## ADR-029 — Design decomposition and execution scope are separate axes

**Decision:** Every durable work item distinguishes whether the approved design is sufficiently concrete (`decomposition_state`) from whether the implementation work is a safe bounded one-agent handoff (`execution_scope`).

**Why:** A requirement can be fully designed while still bundling multiple systems, files, integrations, or independently verifiable outcomes. Treating `concrete` as automatically executable would let `taskcontrol ready` hand an oversized task to one agent.

**Consequence:** `taskcontrol ready` eventually returns only open artifact/implementation work with complete dependencies and `execution_scope: single_agent`. `needs_execution_decomposition`, `human_integration_required`, and `unknown` remain non-autonomous states. The Progressive Decomposer may later split concrete implementation responsibilities without inventing new design.

## ADR-030 — Current output view is mutable; run history stays nested and immutable

**Decision:** `Pipeline/Reconciliation/outputs/current/` is the human-facing convenience view. Reconciliation history remains under `outputs/runs/<run-id>/`, and new verification history lives under `outputs/runs/<run-id>/verifications/<verification-id>/`.

**Why:** Separate top-level reconciliation and verification trees made it difficult to know which files were the current answer and which verification belonged to which source snapshot.

**Consequence:** `current/` may be overwritten whenever the latest candidate changes. It is never historical truth. Existing legacy `outputs/verifications/` directories can be moved once with the deterministic layout-migration utility.

---

## ADR-035 — Provider-adapter enforcement

**Accepted:** 2026-08-23.

**Decision:** Accept ADR-035's fail-closed initial provider boundaries. Adapters never weaken `AgentRequest`; unsupported capabilities and budgets are rejected. Initial Codex support is limited to empty capabilities and empty `context_paths` in a new empty temporary workspace. Initial repository writing and approved command execution remain unsupported. The accepted prerequisite is a separately reviewed request-schema revision making `turn_limit` optional, with null meaning no requested hard provider-internal limit and non-null requiring proven enforcement or rejection.

**Output and error policy:** `provider.log` is exact stdout, successful stderr is empty, and malformed provider output raises provider-neutral `ProviderOutputInvalid` normalized to `schema_error`. There is no automatic fallback.

**Authority:** Deterministic Git, Unity, TaskGraph, evidence, readiness, dispatch, and human authority are unchanged.
