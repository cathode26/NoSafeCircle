# CURRENT STATE — No Safe Circle AI Pipeline

> Update this file whenever a milestone or important implementation slice changes.

Last updated: 2026-08-21, after Milestone 1 completion and merge into `main`, then merge of current `main` into `adversarial-architecture-review`.

## Current Phase

**Milestone 1 — Persistent Work Graph is complete.**

The project now has a durable, deterministic operational work graph under `Tasks/` and a local `taskcontrol` CLI that can validate the graph, inspect work, reconstruct hierarchy/dependencies, and calculate the executable ready frontier without an LLM.

The next infrastructure milestone is **Milestone 2 — RAG + Project Scanner + Compact Context + Progressive Decomposition + Artifact Authority**, described in:

`02_RAG_SCANNER_CONTEXT.md`

Before committing significant new infrastructure to Milestone 2, run/review the adversarial architecture review against the now-Milestone-1-complete repository. The review exists specifically to challenge the architecture and milestone order before more infrastructure is added.

Architecture review entry point:

`Pipeline/ArchitectureReview/README.md`

The pipeline must now begin earning its keep by advancing real No Safe Circle gameplay while the remaining autonomy layers are built. Do not spend another long stretch on infrastructure without using a real game task as the test case.

## Milestone 1 — COMPLETE

Milestone 1 established the persistent planning foundation promised by `01_MILESTONE_TASK_GRAPH.md`.

### Approved Bootstrap Provenance

The initial persistent graph was seeded only after independent reconciliation verification and explicit human approval.

Source reconciliation:

`20260821T193541Z-998ee7b5`

Successful verification:

`20260821T195959Z-43dba5de`

Verification result:

- initial material findings: 21
- final material findings: 0
- status: `verified_with_findings`
- persistent graph remained unmutated during reconciliation/verification
- human approval was required before bootstrap

Approval manifest:

`Pipeline/TaskGraph/APPROVED_BOOTSTRAP.json`

Bootstrap completion marker:

`Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json`

### Persistent Graph State at Bootstrap

The approved bootstrap produced:

- 37 persistent work records
- 12 feature records
- 25 implementation records
- 0 artifact records at bootstrap
- 36 open records
- 1 complete record
- 59 dependency edges
- 36 parent edges
- 7 exclusive-resource groups
- 17 non-code project requirements
- one root: `NSC-001` / `no-safe-circle`

The only record complete at bootstrap was:

`NSC-023 — Fixed Isometric Camera`

The persistent graph lives under:

`Tasks/NSC-001.yaml` through `Tasks/NSC-037.yaml`

Metadata lives under:

- `Pipeline/TaskGraph/WORK_ID_MAP.json`
- `Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml`
- `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`
- `Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json`

The `.yaml` task/metadata files intentionally use a deterministic JSON-compatible YAML 1.2 subset so Python's standard `json` parser can read them without an added YAML dependency.

### `taskcontrol` State

Implemented commands:

```text
python Pipeline/TaskGraph/taskcontrol.py validate
python Pipeline/TaskGraph/taskcontrol.py list
python Pipeline/TaskGraph/taskcontrol.py show NSC-003
python Pipeline/TaskGraph/taskcontrol.py ready
python Pipeline/TaskGraph/taskcontrol.py graph
```

The real persistent graph passes `taskcontrol validate`.

The first real `ready` calculation returned seven executable one-agent implementation tasks:

- `NSC-003` — Mouse-Directed Player Movement, Shared Pointer Projection, and Movement Restriction
- `NSC-004` — Player Health Ownership, Restore, Death Transition, and Feedback
- `NSC-005` — Player Mana Ownership, Restart Reset, and Denied-Cast Feedback
- `NSC-011` — Active Enemy Registry
- `NSC-020` — Shared Doorway-Crossing State
- `NSC-024` — Tilemap and AI Navigation Package Configuration
- `NSC-037` — Windows Build Scene Registration

`ready` is deterministic. It returns only work that is:

1. `open`;
2. `kind` = `implementation` or `artifact`;
3. `execution_scope` = `single_agent`;
4. and whose dependencies are all complete.

Feature nodes and records requiring execution decomposition are not treated as executable work.

### Milestone 1 Important Implementation Files

- `Pipeline/TaskGraph/bootstrap_inputs.py`
- `Pipeline/TaskGraph/work_graph_transform.py`
- `Pipeline/TaskGraph/work_graph_validate.py`
- `Pipeline/TaskGraph/work_graph_persist.py`
- `Pipeline/TaskGraph/seed_work_graph.py`
- `Pipeline/TaskGraph/persistent_work_graph.py`
- `Pipeline/TaskGraph/taskcontrol.py`
- associated smoke tests under `Pipeline/TaskGraph/`

The bootstrap is intentionally one-shot. Do not rerun `seed_work_graph.py --apply` against an already-bootstrapped repository.

## Source-of-Truth Boundaries Now in Force

### GDD / Canon

The GDD remains root game-design canon.

Approved design artifacts may later extend canon only through the Artifact Authority + evaluation process. Unapproved drafts are not trusted project input.

### Reconciliation

Reconciliation outputs are immutable point-in-time observations.

They are **not** the mutable work database.

A future reconciliation run creates a new immutable snapshot and may propose a delta against the living persistent graph. It does not directly rewrite `Tasks/*.yaml`.

### Persistent Work Graph

`Tasks/*.yaml` is now the durable operational work definition.

Stable `NSC-###` IDs and `reconciliation_key` values preserve traceability back to the reconciliation records that originally proposed the work.

### Repository State

Integrated repository state remains the authority for what implementation is actually complete.

Production completion semantics should require implementation work to be merged into `main` before the task becomes complete.

## Existing Course/Production Building Blocks

The production pipeline continues to reuse the course assignments rather than treating them as disconnected demos:

- Assignment 3: Planner → Implementer → Validator crew concept.
- Assignment 4: GDD RAG/retrieval and consistency infrastructure.
- Assignment 5: goal-oriented analysis and bounded implementation agent.
- Assignment 6: proven GER orchestration — Implement/Generate → Evaluate → Refine → Circuit Breaker, including structured runtime feedback.
- Assignment 7: not yet implemented; planned as a scored Style Evaluator specialization when real style-sensitive artifact work exists.

### Assignment 6 Lesson Still Applies

Static/source-level success is not sufficient evidence that an interactive Unity feature works.

The camera implementation passed static evaluation before runtime behavior was correct. Runtime failures were converted into structured feedback and re-entered into the Refiner loop.

Future implementation execution must collect the strongest practical evidence available, such as:

- Git/scope checks
- static checks
- Unity compilation
- EditMode tests
- PlayMode tests
- runtime observations
- semantic task/GDD review
- artifact/canon/style evaluation when applicable

A worker never declares itself complete merely because it says implementation succeeded.

## Current Target Architecture

```text
GDD / Root Canon
   ↓
Persistent Work Graph                    ← Milestone 1 COMPLETE
   ↓
Ready / Near-Ready Frontier              ← Milestone 1 COMPLETE
   ↓
Targeted GDD + Project Context            ← Milestone 2 NEXT
   ↓
Progressive Decomposer
   ↓
Enough approved information to execute?
   │
   ├─ YES → Concrete Artifact or Implementation Work
   │
   └─ NO
        ↓
   Proposed Missing Artifact
        ↓
   Artifact Authority Gate
        ↓
   Authorized?
      /     \
    YES      NO
     ↓        ↓
Artifact GER  Re-plan / Human Review
     ↓
Approved Artifact
     ↓
Back to Progressive Decomposer
     ↓
Concrete Work Item
     ↓
Local Supervisor                           ← Milestone 3
     ↓
Branch / Worktree / Draft PR
     ↓
Bounded Worker
     ↓
==============================
        GER REPAIR LOOP                    ← Milestone 4 production integration
------------------------------
Implement / Generate
   ↓
Evaluate against task + canon
   ↓
Deterministic / Unity / Runtime Evidence
   ↓
PASS? ───────────────→ Approved
   │
   └─ FAIL
        ↓
   Structured Feedback
        ↓
      Refiner
        ↓
    Re-evaluate
        ↓
   Retry to Budget
        ↓
  Circuit Breaker
==============================
   ↓
Fresh AI Diff Review
   ↓
Merge / Approve Artifact
   ↓
Work Complete
   ↓
Dependency Graph Recalculates
   ↓
Continuous safe backlog processing         ← Milestone 5
```

GER remains the bounded self-correction mechanism around project work. Generated content is one GER application, not its definition.

## Immediate Next Goal

### Checkpoint — Adversarial Architecture Review

Run/review the architecture-review system against the current M1-complete branch before making a large Milestone 2 investment.

The review should answer:

1. Does the architecture still look fundamentally sound now that the persistent graph actually exists?
2. Does the next milestone create enough near-term gameplay leverage to justify itself?
3. Is any part of Milestone 2 overbuilt relative to the immediate needs of No Safe Circle?

Do not treat reviewer majority as authority. Read the synthesis and fresh adversarial critique, then make a human architecture decision.

### Milestone 2 — RAG + Scanner + Context + Progressive Decomposition

Assuming the architecture still holds, implement Milestone 2 incrementally.

The preferred order is:

1. Build the smallest compact context path for **one real near-term task**.
2. Reuse/wrap Assignment 4 GDD retrieval rather than rebuilding RAG from scratch.
3. Extract/reuse deterministic repository-scanning capabilities already proven inside reconciliation where practical.
4. Combine task + relevant canon + relevant repository evidence into a compact context pack.
5. Use a real No Safe Circle task as the test case; do not build generic infrastructure in isolation.
6. Add Progressive Decomposition for near-frontier records that are not safe one-agent handoffs.
7. Distinguish execution-size decomposition from missing-design decomposition.
8. When design is genuinely missing, emit an artifact proposal instead of inventing the design.
9. Add the Artifact Authority Gate before any generated design artifact becomes trusted input.
10. Generate/evaluate only the smallest authorized artifact needed to unblock decomposition.
11. Re-run decomposition after artifact approval.
12. Feed resulting concrete implementation work back into the persistent graph and validate deterministically.

See:

`Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md`

### Recommended Real Task Anchor

`NSC-003 — Mouse-Directed Player Movement, Shared Pointer Projection, and Movement Restriction`

is already a concrete, ready, `single_agent` implementation record and is a strong test case for the first compact-context/execution path because later systems depend on its movement, pointer-projection, reset, restriction, and suspend interfaces.

Milestone 2 should not block visible gameplay progress. Use real task execution to test the context machinery whenever possible.

## Deferred Until Later Milestones

Do not start these merely because Milestone 1 is complete:

- fully autonomous continuous worker execution
- parallel Claude workers
- automatic merge
- merge queue
- broad GitHub Projects synchronization
- automatic backlog replenishment
- speculative full-game decomposition

Milestone 3 owns the first restartable one-ticket supervisor, claims, Git worktrees, Draft PRs, and GitHub operational visibility.

Milestone 4 productionizes generic ticket validation/repair around the GER lessons already proven in Assignment 6.

Milestone 5 adds continuous safe backlog processing, budgets, blockers, observability, and only later safe parallelism.

## Known Important Constraints

- Persistent work definitions are local and versioned.
- Reconciliation history is immutable observation, not mutable task state.
- A new reconciliation may propose graph changes but may not silently mutate the graph.
- Readiness and dependency cascading remain deterministic `taskcontrol` behavior.
- Feature nodes are organizational/decomposition nodes and are not direct implementation handoffs.
- Missing design becomes an artifact proposal rather than silent invention.
- Execution decomposition may split already-approved implementation responsibilities but may not invent mechanics/content.
- Approved artifacts are subordinate to GDD canon.
- Unity scenes, prefabs, ProjectSettings, shared builders, and Input Actions require conservative conflict handling.
- Static evaluation cannot replace Unity/runtime evidence for visual or interactive behavior.
- A no-op repair while failures remain counts as failed progress.
- All autonomous repair loops require bounded retries/runtime/cost and a Circuit Breaker.
- Do not introduce parallel workers until one-ticket autonomous execution is reliable.
- Infrastructure work must advance or directly enable real gameplay rather than becoming the product itself.

## Assignment 7 Position

Assignment 7 still has a concrete architectural role, but it is not the immediate next pipeline task.

When Progressive Decomposition identifies a real authorized style-sensitive artifact, Assignment 7 can supply the scored Style Evaluator inside Artifact GER:

```text
Generator → Style Evaluator (SCORE + REASON) → Refiner
```

The Style Evaluator judges the quality/style of content already authorized to exist. It does not authorize new design.

## Next Window Instructions

Read, in order:

1. `START_HERE.md`
2. this file
3. `00_MASTER_CONTEXT.md`
4. `02_RAG_SCANNER_CONTEXT.md`
5. `DECISIONS.md` when architecture/authority/decomposition semantics matter
6. inspect the actual repository state

Then:

1. confirm the M1-complete graph still passes `python Pipeline/TaskGraph/taskcontrol.py validate`;
2. inspect `python Pipeline/TaskGraph/taskcontrol.py ready`;
3. review/run `Pipeline/ArchitectureReview/architecture_review.py` if the post-M1 architecture checkpoint has not yet been accepted;
4. choose the smallest Milestone 2 slice that advances a real No Safe Circle task;
5. do not rebuild Milestone 1;
6. do not run the one-time bootstrap again;
7. do not fully decompose the distant backlog.

A new window should be able to resume from repository state without needing the prior chat transcript.
