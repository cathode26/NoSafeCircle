# START HERE — No Safe Circle AI Pipeline

This is the first file any AI assistant or developer should read before working on the autonomous development pipeline.

## Purpose

The pipeline is built across multiple work sessions and AI contexts. Do not rely on conversation memory as the source of truth.

**The repository is the source of truth.**

## Current Status Snapshot

Stage 4B is complete on `provider-adapters`. The current bounded extension is **Stage 4B.2 — Practical Repository Read/Search**. The initial fail-closed `ClaudeCodeProvider` and shared bounded `StandardProcessRunner` were committed at:

```text
ae046fd828f168dac6c87c49878fe1812f6c1fd7
```

The provider preserves structured-output invocations with empty capabilities and now also supports:

```text
repository_read -> Claude Read
repository_search -> Claude Glob and Grep
both -> Claude Read, Glob, and Grep
token_limit = null
```

Empty-capability invocations still run in a fresh empty temporary workspace with no tools. Repository-capable invocations run in the actual repository root (`/workspace` in Docker) and may accept validated repository-relative `context_paths` as prompt guidance. Repository writing, shell and approved command execution, and web access remain unsupported. See ADR-038 for the trusted single-user boundary and accepted limited read-containment risk.

The deterministic AgentRuntime, process-runner, and Claude-provider suites all pass. No live `ClaudeCodeProvider` invocation has yet been performed through `AgentRunner`; validation to date consists of the earlier isolated CLI discovery probe plus deterministic injected-process and real bounded child-process fixtures.

Stage 4C remains the OpenAI/Codex Provider stage; it is not renamed. After practical Claude read/search validation, infrastructure should move toward useful Execution Crew and game-development capability rather than further repository-security research. Initial Codex support remains empty-capability/empty-context only in a fresh temporary workspace, using the approved temporary timeout translation:

```text
effective_timeout_seconds = min(timeout_seconds, turn_limit * 30)
```

This is a bounded-execution policy, not a cross-provider-equivalent turn measurement.

AgentRuntime now has the repository inspection capability needed by future repository-aware roles. This slice does not implement ExecutionCrew, Reconciliation orchestration, TaskGraph changes, or write/command authority.

As of 2026-08-21:

- **Milestone 1 — Persistent Work Graph is COMPLETE.**
- The approved persistent graph contains 37 work records under `Tasks/`.
- `taskcontrol validate`, `list`, `show`, `ready`, and `graph` work against the real persisted graph.
- The first deterministic ready frontier contains seven executable `single_agent` implementation tasks.
- Reconciliation/verification history is immutable; `Tasks/*.yaml` is the living operational work graph.
- The one-time bootstrap is complete and must not be rerun.
- Current `main` has been merged into `adversarial-architecture-review` so the architecture-review branch includes the completed Milestone 1 implementation.

The next planned infrastructure milestone is **Milestone 2 — RAG + Project Scanner + Compact Context + Progressive Decomposition + Artifact Authority**.

Before a large Milestone 2 investment, use the adversarial architecture review as a checkpoint against the now-M1-complete repository:

`Pipeline/ArchitectureReview/README.md`

The next infrastructure work should also advance a real No Safe Circle task rather than creating another infrastructure-only stretch.

## Required Reading Order

1. Read `Docs/AI-Pipeline/CURRENT_STATE.md`.
2. Read `Docs/AI-Pipeline/08_STAGE_4B_CLAUDE_CODE_PROVIDER.md` for the latest provider implementation state.
3. Read `Docs/AI-Pipeline/ADR-037_CLAUDE_CODE_PROVIDER_BOUNDARY.md` and `Docs/AI-Pipeline/ADR-038_PRACTICAL_REPOSITORY_READ_SEARCH.md` for the Claude boundaries.
4. Read `Docs/AI-Pipeline/00_MASTER_CONTEXT.md` for the target architecture.
5. Read the milestone/context file named by `CURRENT_STATE.md`.
6. Read `Docs/AI-Pipeline/DECISIONS.md` when the work touches architecture, Git workflow, task semantics, autonomy, RAG, GER, evaluation, refinement, validation, progressive decomposition, or artifact authority.
7. Inspect the actual repository state before changing anything.

Any work touching Unity tests, validation harnesses, scenes, prefabs, builders/generators, or evidence-producing Unity runs must also read `Docs/Engineering/UNITY_TESTING_POLICY.md`.

For current post-M1 work, the primary milestone context is:

`Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md`

`01_MILESTONE_TASK_GRAPH.md` is now a **completed milestone record and semantic reference**, not the active implementation plan.

Do not read every milestone file unless you need broader architecture context.

## Milestone Routing Table

Current work | Read this file
--- | ---
Completed persistent graph semantics, stable IDs, readiness, taskcontrol | `01_MILESTONE_TASK_GRAPH.md`
**Current next milestone:** RAG canon retrieval, Unity/code scanner, context packs, progressive decomposition, artifact authority | `02_RAG_SCANNER_CONTEXT.md`
Supervisor, task claiming, Git branches, worktrees, GitHub Issues/Projects/PRs | `03_SUPERVISOR_GIT_GITHUB_CONTEXT.md`
Assignment 3 crew, Assignment 6 GER, bounded repair loops, deterministic tests, Unity/runtime validation, evaluator specializations | `04_EXECUTION_GER_VALIDATION_CONTEXT.md`
Provider-neutral AgentRuntime, Claude/OpenAI adapters, and production Execution Crew architecture | `06_PROVIDER_NEUTRAL_EXECUTION_CREW_PLAN.md`
Provider-adapter implementation, capability mapping, and fail-closed enforcement | `07_PROVIDER_ADAPTER_CAPABILITY_MAPPING.md` and `ADR-035_PROVIDER_ADAPTER_ENFORCEMENT.md`
Completed Stage 4B Claude Code provider and accepted containment/lifecycle boundary | `08_STAGE_4B_CLAUDE_CODE_PROVIDER.md` and `ADR-037_CLAUDE_CODE_PROVIDER_BOUNDARY.md`
Continuous autonomous ticket processing, budgets, blockers, parallel workers, planning refresh | `05_CONTINUOUS_AUTONOMY_CONTEXT.md`

## Milestone 1 Commands

The completed persistent graph can be inspected locally with:

```text
python Pipeline/TaskGraph/taskcontrol.py validate
python Pipeline/TaskGraph/taskcontrol.py list
python Pipeline/TaskGraph/taskcontrol.py show NSC-003
python Pipeline/TaskGraph/taskcontrol.py ready
python Pipeline/TaskGraph/taskcontrol.py graph
```

Do **not** rerun the initial persistent-graph bootstrap. `Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json` marks it complete.

## Current First Real Task Anchor

The current graph already has executable work. A strong first gameplay/context-pipeline anchor is:

`NSC-003 — Mouse-Directed Player Movement, Shared Pointer Projection, and Movement Restriction`

It is `open`, `implementation`, `single_agent`, and has no dependencies.

Use real near-term work such as this to test compact context generation and later execution orchestration. Do not build a generic context/supervisor platform while leaving the game untouched.

## Important GER Lesson

Assignment 6 demonstrated that GER is not only a gate for generated content.

For No Safe Circle, the successful loop was:

`bounded task → implement → evaluate → collect validation/runtime feedback → refine → re-evaluate → approve or circuit-break`

The camera implementation passed static evaluation before it was actually usable in Unity. Runtime failures were converted into structured feedback and sent back through the Refiner.

Future execution work must therefore treat runtime evidence as first-class validation input rather than assuming source-level success means the feature works.

Reference:

- `Assignment6GER/README_Assignment6.md`
- `Docs/AI-Pipeline/00_MASTER_CONTEXT.md`
- `Docs/AI-Pipeline/DECISIONS.md`

## Important Progressive-Decomposition Lesson

The task graph does not need the entire game decomposed into low-level implementation tickets in advance.

When high-level work approaches the actionable frontier, the Progressive Decomposer determines why it is not yet a safe one-agent handoff.

There are two distinct cases:

1. **Execution-size problem** — approved design is concrete, but the implementation record is too broad. Split only the already-approved responsibilities.
2. **Design-information problem** — approved design/content is missing. Propose the smallest missing artifact instead of inventing the design.

Detecting missing design and generating missing design are separate actions.

Artifact creation must pass the Artifact Authority Gate before generation.

## Important Artifact-Authority Lesson

An AI-generated artifact is not trusted merely because it exists.

The trust path is:

```text
Missing approved design detected
        ↓
Artifact proposal
        ↓
Artifact Authority Gate
        ↓
Authorized generation
        ↓
Artifact GER / required evaluators
        ↓
Approved artifact
        ↓
Trusted downstream context
```

Approved artifacts may add authorized detail where the GDD leaves room, but they may not contradict or silently replace root canon.

## Important Reconciliation-Snapshot Lesson

Reconciliation is not the mutable task database.

Each full Reconciliation Agent run produces an immutable point-in-time snapshot of GDD requirements versus repository state.

The initial persistent graph was seeded only after independent verification and human approval.

Later implementation work updates the persistent graph; it does not rewrite old reconciliation snapshots.

A later reconciliation creates a new snapshot and may propose a graph delta. That delta must cross an explicit review/diff/apply boundary before changing persistent work.

Safe cascading readiness changes remain deterministic `taskcontrol` behavior, not direct LLM graph rewrites.

## Independent Reconciliation Verification Gate

A successful Reconciliation Agent run is a candidate snapshot, not automatic graph truth.

Before the initial bootstrap, the multi-model Reconciliation Verification Crew independently audited:

- GDD coverage;
- dependency/decomposition semantics;
- repository evidence;
- execution scope / one-agent handoff size.

Material findings were unioned rather than majority-voted, repaired through bounded refinement, and independently re-verified before human approval.

The approved bootstrap source ended with zero material findings.

This verification architecture remains available for later substantial reconciliation events; do not rerun it for every ordinary implementation ticket.

## Current-Output Convention

Use:

`Pipeline/Reconciliation/outputs/current/`

for the latest human-facing reconciliation/verification status.

Treat:

`Pipeline/Reconciliation/outputs/runs/`

as immutable audit history.

Do not use mutable `outputs/current/` as authority for the already-approved initial bootstrap. The approval manifest binds the specific immutable verification artifacts used for that seed.

## Core Principle

**Use deterministic local tools for facts and computation. Use LLMs for judgment and bounded implementation.**

The local supervisor will eventually own the autonomous loop. Claude or another coding model is a bounded worker operating on one selected piece of work at a time.

A worker does not declare itself successful. Project evidence does.

An implementation worker also does not silently create new game design. Missing design becomes an explicit artifact proposal.

## Current Development Rule

From this point forward, pipeline implementation should be tested by advancing the actual game.

Prefer this pattern:

```text
real ready/near-ready No Safe Circle work
        ↓
implement only the infrastructure needed for that work
        ↓
use it on the real task
        ↓
measure what failed / what was missing
        ↓
add the next bounded infrastructure slice
```

Avoid building later autonomous layers speculatively before the preceding single-task path has proven reliable.

## End-of-Session Rule

Before ending a meaningful pipeline work session:

1. Update `CURRENT_STATE.md` when the milestone/slice changed.
2. Update the active milestone completion/status notes when appropriate.
3. Add an entry to `DECISIONS.md` if an architectural decision changed.
4. Ensure commands and newly-created files are documented.
5. Commit the documentation with the implementation it describes.

A new AI window should be able to resume by reading the repository without needing the previous chat transcript.
