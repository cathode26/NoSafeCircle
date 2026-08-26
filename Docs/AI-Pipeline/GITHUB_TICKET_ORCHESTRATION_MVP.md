# GitHub Ticket Orchestration MVP

## Purpose

This is the minimum coordination layer for running several **human-directed ChatGPT orchestrators in parallel** against No Safe Circle.

It supports:

- `work_type: implementation` — fresh implementation of a suitable undelivered concrete executable contract;
- `work_type: decomposition` — Stage D1B.1 read-only decomposition of an eligible decomposition-relevant parent.

The canonical Windows task path is defined by:

```text
Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md
```

## Source-of-truth split

### TaskGraph owns durable work truth

`Tasks/NSC-###.yaml` owns task identity, scope, dependencies, acceptance criteria, completion gates, downstream obligations, execution/decomposition state, exclusive resources, canon evidence, and provenance.

Committed TaskGraph evidence owns current conformance.

### GitHub owns operational visibility

A GitHub Issue answers:

- is the task currently claimed/reserved?;
- which ChatGPT worker owns the orchestration?;
- what work type is active?;
- which base commit, branch/checkout, provider/run/output is being used?;
- what approach, decisions, blockers, validation, and closeout were recorded?

GitHub never replaces TaskGraph authority.

## Issue state convention

For the Issue whose title starts with the exact task ID:

| GitHub state | Meaning |
| --- | --- |
| no Issue | available; create before claiming |
| open + unassigned | available / released |
| open + assigned | claimed / in progress or deliberately reserved |
| closed | orchestration finished |

Assignment is the current claim marker. Simultaneous claim atomicity is intentionally deferred.

## Issue title/body

Use:

```text
NSC-044 — Ruined Entry Spatial Blockout
```

The body should mirror the committed task contract: purpose, bounded/decomposition reason, dependencies, acceptance criteria, completion gates, downstream obligations, execution/decomposition state, exclusive resources, canon evidence, scope notes, contract path/revision/reconciliation key, and the Issue-state convention.

For decomposition work, keep the existing parent NSC ID; do not fabricate a new TaskGraph task for the act of decomposition.

## Claim protocol

Before selecting work:

1. inspect current TaskGraph state and active decomposition candidates;
2. inspect candidate contracts;
3. search GitHub Issues for exact NSC IDs;
4. skip assigned/closed candidates;
5. inspect exclusive-resource conflicts;
6. under a generic request, continue to another candidate when an early one is unsuitable.

When selecting an available work unit:

1. create/fill its Issue if absent;
2. assign it to `cathode26`;
3. identify the worker ID;
4. explicitly identify `work_type: implementation` or `work_type: decomposition`;
5. post a **Claim / Planned Approach**;
6. create/enter the canonical task checkout;
7. start the applicable bounded pipeline.

## Canonical checkout path

Shared operator/main checkout:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle
```

Claimed NSC task checkout:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>
```

Examples:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

Preserve the hyphenated task ID. Do not use `NoSafeCircle-NSC...`, `-DECOMP`, or timestamped checkout-directory variants as the normal task path.

### Implementation checkout

Use the Supervisor helper with an explicit canonical path:

```powershell
python Pipeline/Supervisor/task_checkout.py checkout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

The helper must clone from GitHub/current remote `main`, use a standalone clone, create the task branch, validate TaskGraph, and leave the checkout clean before provider work.

### Decomposition checkout

Decomposition uses the same task directory:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021
```

and a filesystem-disjoint authoritative output sibling, normally:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021-Outputs
```

Read `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md` before D1B.1.

## Claim / Planned Approach comment

Record information applicable to the work type:

```text
Worker
work_type: implementation | decomposition
Exact base/source main commit
Canonical checkout path
Branch                         # implementation
Provider + output location     # decomposition
Planned approach
Expected validation/review boundary
Assumptions / risks
```

The planned approach must describe how the orchestrator intends to accomplish the work, not merely repeat acceptance criteria.

## Implementation workflow

After claim/checkout, follow the established real-task delivery path:

- Contract Locality Auditor;
- ExecutionCrew when applicable;
- human candidate review;
- Unity/runtime/human validation;
- authoritative validation evidence;
- TaskDelivery review/finalize;
- committed evidence;
- TaskGraph-derived conformance;
- human merge authority.

The Issue is the dashboard around those systems.

## Decomposition workflow

Follow `Pipeline/TaskDecomposition/README.md` and `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md`.

D1B.1 may return:

- `already_concrete`;
- `decomposed`;
- `needs_artifact`;
- `needs_human`.

Outputs remain `review_only_not_applied`; `graph_delta.json`, when present, is not automatically applied.

A `review_ready` result is successful completion of the decomposition work unit even when the semantic result is `needs_artifact` or `needs_human`.

## Implementation closeout

Generate the draft using the canonical task directory:

```powershell
python Pipeline/Supervisor/task_checkout.py draft-closeout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

The final Closeout Report must state:

1. outcome;
2. what changed;
3. how the task was accomplished;
4. decisions/choices made;
5. missing/underspecified items;
6. additions beyond original task;
7. validation performed/results;
8. remaining follow-ups/risks;
9. actual TaskGraph closeout state;
10. final branch/commit/merge identities.

If a section has nothing to report, write `None.`.

Close the Issue only after the normal delivery/merge path is finished. Issue closure does not establish conformance.

## Decomposition closeout

If D1B.1 reaches `review_ready`, post a **Decomposition Closeout** containing:

1. worker ID and `work_type: decomposition`;
2. parent ID/revision/source commit;
3. canonical source checkout and output paths;
4. provider/run ID;
5. semantic decision;
6. `decomposition_result.json` and `graph_delta.json` identities when present;
7. concise proposal/blocker summary;
8. explicit `review_only_not_applied` statement;
9. required human/review/application next action.

Do not mark the parent implementation delivered merely because decomposition succeeded. Keep review-ready work clearly reserved while awaiting human review/application.

## Release / abandonment

If a worker stops without completing the work unit:

1. comment why and record useful state;
2. preserve useful canonical checkout/log/output artifacts;
3. unassign unless the Issue must remain intentionally reserved for review;
4. keep it open unless orchestration is truly finished.

Under a generic request, a genuine hard blocker normally returns the orchestrator to the candidate-selection loop. Do not task-hop merely because ordinary implementation/validation is difficult.

## Existing checkout rule

Never overwrite, delete, reset, or casually reuse:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>
```

Inspect and reconcile it. Do not create a differently named duplicate checkout as the normal collision workaround.

## Explicit-task exception

Generic selection may retry/substitute candidates. If the human explicitly names a task, report that task's blocker rather than silently switching to another NSC ID.

## Fresh-window prompt

A short instruction is enough because the repository now contains the full process:

> Go pick a task and start on it. Follow the current repository's mandatory TaskGraph selection, GitHub claim, canonical task checkout, implementation/decomposition, retry, validation, and closeout rules.

A fresh window should read `AI_PIPELINE.md`, `START_HERE.md`, `TASK_SELECTION_AND_CHECKOUT.md`, `TASK_CHECKOUT_PATH_CONVENTION.md`, `GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md`, and the applicable runbook.

## Known MVP limitations

Still deliberately deferred:

- simultaneous-claim atomicity;
- dependency-readiness policy;
- automatic ranking;
- GitHub Projects;
- automatic PR/merge;
- lease heartbeat;
- automatic release;
- D1C reusable graph application;
- D1B.2 independent decomposition verification/refinement.
