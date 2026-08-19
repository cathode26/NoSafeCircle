# Architecture Decisions — No Safe Circle AI Pipeline

This is a lightweight decision log. Add new entries when a decision materially changes how the pipeline operates.

---

## ADR-001 — Repository state beats conversation memory

**Decision:** Persistent pipeline state, task definitions, dependencies, and architectural documentation live in the repository.

**Reason:** AI chat contexts are temporary and may not contain all prior detail.

---

## ADR-002 — Local supervisor owns autonomy

**Decision:** Claude does not own the infinite/continuous loop. A local deterministic supervisor chooses and launches bounded worker executions.

**Reason:** This allows recovery from session limits, failures, restarts, and cost limits.

---

## ADR-003 — Claude receives one bounded ticket

**Decision:** Normal coding workers receive one task contract rather than the whole project roadmap.

**Reason:** Reduces token use, scope drift, and repeated rediscovery.

---

## ADR-004 — Task dependency graph is persistent and local

**Decision:** Work items are stored as local task artifacts with explicit dependencies. Local code calculates ready/actionable tasks.

**Reason:** Dependency readiness is computation, not something an LLM should reconstruct on every run.

---

## ADR-005 — GitHub is the dashboard, not the project brain

**Decision:** Local/versioned task artifacts define durable work. GitHub Issues/Projects/PRs mirror operational state and provide human visibility.

**Reason:** Workers need fast deterministic local access, while the user needs a convenient remote dashboard.

---

## ADR-006 — `main` is protected from autonomous direct development

**Decision:** Each coding ticket gets its own branch and preferably its own Git worktree.

**Reason:** Provides isolation, reviewability, recovery, and a path to future parallelism.

---

## ADR-007 — Done means merged

**Decision:** A task satisfies downstream dependencies only after its implementation is merged into `main`.

**Reason:** Code existing on an unmerged worker branch is not project state.

---

## ADR-008 — RAG is the canon retrieval layer

**Decision:** Assignment 4 RAG retrieves relevant GDD evidence for tasks instead of repeatedly sending the entire GDD to an LLM.

**Reason:** Reduces context size and keeps generated work grounded in canonical design information.

---

## ADR-009 — Assignment 3 crew executes tickets

**Decision:** Planner → Implementer → Validator operates inside one selected task.

**Reason:** The persistent graph decides WHAT to build; the crew decides HOW to build that bounded work.

---

## ADR-010 — GER is the bounded self-correction loop for project work

**Decision:** Assignment 6 GER (Generator/Implementer → Evaluator → Refiner → Circuit Breaker) is used as the general bounded repair pattern for work that can be evaluated and refined, including Unity implementation code and generated game/content artifacts.

**Reason:** Assignment 6 successfully used GER to implement and repair the isometric camera. The architecture therefore should not restrict GER to generated content. The useful abstraction is a bounded work product with explicit acceptance evidence, structured failure feedback, refinement, and escalation.

**Supersedes:** The earlier wording "GER gates generated artifacts."

---

## ADR-011 — Cheap deterministic validation should run before expensive semantic review when practical

**Decision:** Git checks, scope checks, static checks, Unity compilation/tests, and other deterministic validation should detect cheap/objective failures before spending model tokens on fresh semantic review whenever the task allows it.

**Reason:** Do not spend model tokens on failures a local tool can detect.

**Clarification:** This does not mean deterministic checks alone can approve interactive Unity behavior.

---

## ADR-012 — Newly discovered substantial work becomes a task

**Decision:** A worker that discovers a substantial independently-testable prerequisite must stop/block rather than silently absorb it.

**Reason:** Preserves ticket scope and keeps the dependency graph truthful.

---

## ADR-013 — Start with one worker

**Decision:** Continuous parallel Claude workers are deferred until one-ticket execution is reliable.

**Reason:** Unity scenes, prefabs, `.meta` files, and shared systems can create expensive merge conflicts.

---

## ADR-014 — Every autonomous loop has budgets/circuit breakers

**Decision:** Ticket execution, repair, and GER loops have runtime/retry/cost limits and escalate when exceeded.

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

**Decision:** Ticket validation should aggregate required deterministic, Unity/runtime, and semantic evidence into a form that can either approve work or produce structured Refiner feedback.

**Reason:** Assignment 6 succeeded once Unity observations could be fed back into the same repair loop. A single evaluator result is too narrow for many game-development tasks.

---

## ADR-018 — Old goal-selection artifacts are not current codebase truth

**Decision:** Saved Assignment 5 planning/goal-selection output may be reused as historical evidence, but task completion and readiness must be reconciled against the current `main` branch before seeding the durable dependency graph.

**Reason:** Assignment outputs can become stale as features are merged or changed. Persistent project state must reflect the repository that actually ships.

---

## ADR-019 — The pipeline must advance the game while it is being built

**Decision:** After the minimum deterministic task graph exists, pipeline work should be exercised on real ready No Safe Circle gameplay tasks rather than waiting for the entire autonomous platform to be finished.

**Reason:** The pipeline is infrastructure for developing No Safe Circle, not a separate capstone that should indefinitely block game progress. Real tickets will expose the next infrastructure requirements more accurately than speculative over-building.

---

## ADR-020 — Style evaluation is an evaluator specialization, not a separate architecture

**Decision:** When Assignment 7/player-facing content is ready, style enforcement should plug into GER as a specialized scored evaluator that returns `SCORE + REASON` and feeds the Refiner.

**Reason:** Assignment 7 uses the same Generator → Evaluator → Refiner structure already proven by Assignment 6. Reusing the execution architecture avoids parallel pipelines and allows style checks to remain tied to actual No Safe Circle content.
