# START HERE — No Safe Circle AI Pipeline

This is the first file any AI assistant or developer should read before working on the autonomous development pipeline.

## Purpose

The pipeline is built across multiple work sessions and AI contexts. Do not rely on conversation memory as the source of truth.

**The repository is the source of truth.**

## Current Status Snapshot

The repository has moved beyond the original provider-adapter proving phase. The persistent TaskGraph, provider-neutral AgentRuntime/TaskExecution boundary, Claude and OpenAI/Codex adapters, clean Unity validation runner, schema-v2 task contracts, committed conformance evidence, Stage D1B.1 live decomposition, and the Minimum Production ExecutionCrew are all implemented.

The validated persistent graph currently contains **40 active schema-v2 contracts**. `taskcontrol state` derives current conformance from committed evidence. Dependency readiness and autonomous dispatch remain intentionally unavailable:

```text
TASK READINESS: UNAVAILABLE — DISPATCH POLICY NOT ENABLED
EXECUTION AUTHORIZATION: DENIED
```

A task being `active`, `implementation`, `single_agent`, and `concrete` makes it eligible for a human-selected ExecutionCrew run; it does **not** prove that the task is ready, authorized, or even semantically local enough to execute safely.

The current ExecutionCrew order is:

```text
clean source + authoritative persistent-TaskGraph preflight
    ↓
read-only Contract Locality Auditor (high_reasoning)
    ↓
    ├── contract problem → CONTRACT_REVIEW_REQUIRED → human contract review/repair
    └── local contract
            ↓
        Implementer
            ↓
        deterministic Git scope check
            ↓
        Unity Test Author
            ↓
        deterministic Git scope check
            ↓
        read-only Validator
            ↓
        optional one bounded repair cycle
            ↓
        human review
```

The Contract Locality Auditor classifies every current AC/VAL as `local_to_task`, `requires_declared_dependency`, `downstream_integration`, `missing_design`, or `ambiguous` before any writer role runs. It does not edit the task contract or graph. A contract that requires undeclared/future behavior returns `CONTRACT_REVIEW_REQUIRED` rather than spending an implementation cycle trying to fake the integration.

The Validator also uses structured reason codes. `runtime_not_executed` means the task is locally valid but authoritative Unity/runtime evidence still has to run, so semantic `REVIEW_READY` may still be correct. `missing_integration_dependency` or `design_ambiguity` means the task contract itself needs review and cannot be hidden behind a generic `not_proven`.

ExecutionCrew still does **not** run Unity, apply candidate patches, commit, push, merge, publish evidence automatically, grant conformance, derive readiness, or authorize autonomous dispatch.

Progressive decomposition remains separate. Stage D1B.1 is implemented and live-proven. Stage **D1B.2 independent decomposition verification/refinement** is the next planned pipeline architecture slice. D1B.2 checks proposed decomposition before graph application; the Contract Locality Auditor is the execution-time safety net for an already-approved concrete task.

For real gameplay delivery, do not reconstruct the process from old chat transcripts. Follow the committed runbook and current-state file.

## Required Reading Order

1. Read `Docs/AI-Pipeline/CURRENT_STATE.md`.
2. If you are executing or closing out a real gameplay task, read `Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md` and `Pipeline/ExecutionCrew/README.md` before constructing commands.
3. If the work changes provider/runtime behavior, read `Docs/AI-Pipeline/08_STAGE_4B_CLAUDE_CODE_PROVIDER.md`, `ADR-037_CLAUDE_CODE_PROVIDER_BOUNDARY.md`, and `ADR-038_PRACTICAL_REPOSITORY_READ_SEARCH.md`.
4. Read `Docs/AI-Pipeline/00_MASTER_CONTEXT.md` when broader target architecture is relevant.
5. Read the milestone/context file named by `CURRENT_STATE.md` for the active architecture slice.
6. Read `Docs/AI-Pipeline/DECISIONS.md` whenever the work touches architecture, Git workflow, task semantics, autonomy, RAG, GER, evaluation/refinement, validation, progressive decomposition, locality, artifact authority, or evidence authority.
7. Inspect the actual repository, current branch, TaskGraph, and committed source state before changing anything.

Any work touching Unity tests, validation harnesses, scenes, prefabs, builders/generators, or evidence-producing Unity runs must also read `Docs/Engineering/UNITY_TESTING_POLICY.md`.

For current pipeline architecture work, `CURRENT_STATE.md` is the routing authority. The next planned slice is D1B.2 independent decomposition verification/refinement; `Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md` remains broader semantic context for progressive decomposition and artifact authority.

`01_MILESTONE_TASK_GRAPH.md` is a completed milestone record and semantic reference, not the active implementation plan.

Do not read every milestone file unless the current work requires broader architecture context.

## Milestone Routing Table

Current work | Read this file
--- | ---
**Current next pipeline slice:** D1B.2 independent decomposition verification/refinement | `CURRENT_STATE.md` plus `02_RAG_SCANNER_CONTEXT.md`
Real gameplay task execution, contract locality, bounded repair, human review, Unity validation, evidence closeout | `REAL_TASK_DELIVERY_RUNBOOK.md`, `Pipeline/ExecutionCrew/README.md`, and `04_EXECUTION_GER_VALIDATION_CONTEXT.md`
Completed persistent graph semantics, stable IDs, task contracts, conformance | `01_MILESTONE_TASK_GRAPH.md`
RAG canon retrieval, scanner/context packs, progressive decomposition, artifact authority | `02_RAG_SCANNER_CONTEXT.md`
Supervisor, task claiming, Git branches/worktrees, GitHub Issues/Projects/PRs | `03_SUPERVISOR_GIT_GITHUB_CONTEXT.md`
Provider-neutral AgentRuntime, Claude/OpenAI adapters, and production ExecutionCrew architecture | `06_PROVIDER_NEUTRAL_EXECUTION_CREW_PLAN.md`
Provider-adapter implementation and fail-closed capability mapping | `07_PROVIDER_ADAPTER_CAPABILITY_MAPPING.md` and `ADR-035_PROVIDER_ADAPTER_ENFORCEMENT.md`
Completed Stage 4B Claude Code provider and accepted containment/lifecycle boundary | `08_STAGE_4B_CLAUDE_CODE_PROVIDER.md` and `ADR-037_CLAUDE_CODE_PROVIDER_BOUNDARY.md`
Continuous autonomous ticket processing, budgets, blockers, parallel workers, planning refresh | `05_CONTINUOUS_AUTONOMY_CONTEXT.md`

## Milestone 1 Commands

The completed persistent graph can be inspected locally with:

```text
python Pipeline/TaskGraph/taskcontrol.py validate
python Pipeline/TaskGraph/taskcontrol.py list
python Pipeline/TaskGraph/taskcontrol.py show NSC-003
python Pipeline/TaskGraph/taskcontrol.py state NSC-011 --json
python Pipeline/TaskGraph/taskcontrol.py graph
```

`taskcontrol ready` and `taskcontrol authorize` remain intentionally disabled/unavailable under schema v2 until separate dependency-readiness and dispatch policies are implemented and approved.

Do **not** rerun the initial persistent-graph bootstrap. `Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json` marks it complete.

## Current Human-Selected Gameplay Task

Do not hard-code an old "first task" from this document. Gameplay work advances while pipeline work is being developed.

Before starting a real task:

1. read `CURRENT_STATE.md`;
2. run `taskcontrol validate`;
3. inspect the human-selected task with `taskcontrol show <TASK-ID>`;
4. inspect relevant committed conformance with `taskcontrol state <TASK-ID> --json`;
5. follow `REAL_TASK_DELIVERY_RUNBOOK.md`;
6. let the mandatory Contract Locality Auditor decide whether the selected concrete task is semantically local enough to proceed to writer roles.

If the result is `CONTRACT_REVIEW_REQUIRED`, repair the task contract through the human-reviewed TaskGraph workflow instead of forcing implementation tests to simulate systems that do not exist.

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
