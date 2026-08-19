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

## ADR-010 — GER gates generated artifacts

**Decision:** Assignment 6 GER (Generator → Evaluator → Refiner → Circuit Breaker) is used for generated game/content artifacts that downstream tickets may depend on.

**Reason:** Generated content should be evaluated against GDD-specific rules before becoming trusted project input.

---

## ADR-011 — Deterministic validation runs before AI review

**Decision:** Git checks, scope checks, static checks, Unity compilation/tests, and other deterministic validation happen before a fresh semantic LLM diff review.

**Reason:** Do not spend model tokens on failures a local tool can detect.

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
