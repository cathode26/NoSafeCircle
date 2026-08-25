# Parallel ChatGPT Task Orchestrator Rules

## Status

This document is **mandatory operating guidance** for any ChatGPT instance that selects, claims, starts, orchestrates, releases, or closes real No Safe Circle work while multiple ChatGPT task-orchestrator windows may be active.

It is the short operational contract layered on top of:

- `Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md`;
- `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md`;
- `Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md`;
- `Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md`;
- `Docs/AI-Pipeline/REAL_TASK_DELIVERY_WINDOWS_CLONE_NOTE.md`;
- `Pipeline/ExecutionCrew/README.md`;
- `Pipeline/TaskDelivery/README.md`;
- `Pipeline/TaskDecomposition/README.md`.

The detailed documents above remain authoritative for their respective subsystems. This file exists so a fresh ChatGPT window cannot miss the coordination protocol.

## Core rule

**Do not choose or start work from TaskGraph alone. GitHub Issue state is the shared operational coordination layer for parallel ChatGPT orchestrators.**

TaskGraph still owns durable scope, dependencies, acceptance criteria, completion gates, resources, canon evidence, and conformance. GitHub Issues only own shared operational visibility: available, claimed, released, waiting for review, and orchestration-finished.

A generic human instruction such as **"Go pick a task and start on it"** is sufficient human authorization to select one bounded work unit under the committed selection policy. The human does not need to preselect an NSC ID.

## Selectable orchestrator work types

A generic task-picking request may select either:

1. **`work_type: implementation`** — fresh implementation of an undelivered concrete executable TaskGraph contract;
2. **`work_type: decomposition`** — Stage D1B.1 read-only decomposition of an existing active decomposition-relevant parent contract.

`decomposition` is an orchestrator work type, not a new TaskGraph `kind`, and does not receive a fabricated NSC ID merely to represent the act of decomposing a parent.

Decomposition remains progressive and just-in-time. Do not use generic selection authority to decompose the whole backlog speculatively.

## Issue-state convention

For the Issue whose title begins with the exact `NSC-###` ID:

| GitHub state | Operational meaning |
| --- | --- |
| no Issue | available; create the ticket before claiming |
| open + unassigned | available / released |
| open + assigned | claimed / being worked or deliberately reserved for review; do not pick it |
| closed | orchestration finished; do not pick it |

For the current MVP, assignment is the claim marker/reservation marker. No atomic distributed lock is implemented. The human operator accepts that simultaneous duplicate claims are possible and will correct them manually if needed.

A review-ready decomposition awaiting human review/application should remain clearly reserved/marked so another fresh orchestrator does not immediately rerun the same parent contract/hash.

## Mandatory pre-selection procedure

Before selecting work, every orchestrator must:

1. identify itself with a worker ID such as `chatgpt-1` through `chatgpt-5`;
2. read current `main`, `AI_PIPELINE.md`, `Docs/AI-Pipeline/START_HERE.md`, this file, `TASK_SELECTION_AND_CHECKOUT.md`, `GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md`, `GITHUB_TICKET_ORCHESTRATION_MVP.md`, and the applicable execution/decomposition runbook;
3. inspect current TaskGraph rather than relying on conversation memory;
4. inspect current evidence-derived task states using the repository tools;
5. build plausible **fresh implementation** candidates from current undelivered concrete work;
6. also inspect active contracts for **decomposition-work** candidates accepted by the production Progressive Decomposer preflight;
7. search GitHub Issues for each plausible candidate's exact NSC ID;
8. exclude any candidate whose Issue is open and assigned;
9. exclude any candidate whose Issue is closed;
10. inspect each candidate's `exclusive_resources` and compare them with currently claimed tickets before deciding whether parallel work is sensible;
11. never infer dependency readiness merely from contract shape or Issue state; dependency readiness remains a separate unimplemented policy unless the human explicitly directs the work.

A ticket being unclaimed does **not** mean two tasks with the same Unity scene/builder/resource are safe to implement simultaneously. Resource conflicts must be surfaced.

For generic task selection, an assigned/closed/conflicted/otherwise unsuitable first candidate is **not** a reason to stop. Skip it and continue to another sensible candidate.

## Mandatory ticket contents

If a selected task has no Issue, create one before execution. Its title must begin with the exact task ID:

```text
NSC-044 — Ruined Entry Spatial Blockout
```

The Issue body must provide enough information for another ChatGPT instance or the human to understand the work without reconstructing an old chat. Include:

- task title and ID;
- what the task accomplishes;
- why the task is bounded / what responsibility it owns;
- dependencies;
- acceptance criteria;
- completion / validation gates;
- downstream integration obligations;
- execution/decomposition state;
- exclusive resources;
- relevant GDD/canon evidence or references;
- explicit out-of-scope notes;
- `Tasks/<TASK-ID>.yaml` path, contract revision, and reconciliation key;
- the Issue-state convention.

Do not replace the TaskGraph contract with prose in the Issue. The Issue is a human-facing operational mirror.

## Mandatory claim procedure

When the orchestrator chooses an available work unit:

1. assign the Issue to `cathode26`;
2. identify the ChatGPT worker ID in a **Claim / Planned Approach** comment;
3. explicitly write either `work_type: implementation` or `work_type: decomposition`;
4. only after the GitHub claim exists, start the selected pipeline;
5. for implementation, create the isolated task checkout from current GitHub `main` using the checkout helper;
6. for decomposition, use the documented D1B.1 physically read-only source/output workflow rather than an implementation checkout.

Implementation checkout helper:

```powershell
python Pipeline/Supervisor/task_checkout.py checkout NSC-044 --worker-id chatgpt-1
```

The Claim / Planned Approach comment must record:

- worker ID;
- work type;
- exact base/source `main` commit;
- branch/checkout path when applicable;
- decomposition provider/output location when applicable;
- a concrete description of how the orchestrator plans to accomplish the work;
- expected implementation surfaces/files or decomposition outcome when known;
- expected validation/review boundary;
- implementation choices it already expects to make;
- assumptions, risks, resource conflicts, or uncertainties.

The **planned approach must describe the intended method**, not merely restate acceptance criteria.

## Implementation decisions and missing information

During implementation work, the orchestrator must distinguish between:

1. **implementation choice** — freedom legitimately left to the implementer;
2. **missing or underspecified design** — information that requires design authority rather than invention;
3. **necessary supporting addition** — a helper/test/small integration required to complete the approved task;
4. **scope expansion** — additional work not required by the task and not automatically authorized.

The orchestrator must keep a record of material choices and discoveries for closeout.

If design is genuinely missing, follow the existing contract/design/artifact authority rules. Do not silently invent canon just to finish a ticket.

## Normal implementation delivery workflow remains mandatory

Claiming a GitHub Issue does not bypass the established delivery process. For `work_type: implementation`, continue through the applicable existing workflow, including:

- isolated checkout;
- Contract Locality Auditor;
- ExecutionCrew when appropriate;
- human candidate review;
- Unity tests/runtime/human validation;
- clean authoritative validation evidence;
- TaskDelivery review/finalize;
- committed evidence;
- TaskGraph-derived current conformance;
- human merge authority.

The Issue is the dashboard around those systems, not a replacement for them.

## Decomposition workflow remains review-only

For `work_type: decomposition`, follow `Pipeline/TaskDecomposition/README.md` and the Stage D1B.1 read-only pipeline.

A generic task-picking instruction permits selecting and running an eligible decomposition proposal. It does **not** permit applying the graph delta automatically.

D1B.1 may produce semantic decisions:

- `already_concrete`;
- `decomposed`;
- `needs_artifact`;
- `needs_human`.

A `review_ready` run is successful completion of the decomposition work unit even if the semantic decision is `needs_artifact` or `needs_human`.

Post a **Decomposition Closeout** comment containing:

1. worker ID and `work_type: decomposition`;
2. parent task ID/revision/source commit;
3. provider and run ID;
4. semantic decision;
5. decomposition-result and graph-delta paths/identities when present;
6. concise proposed-child or blocker summary;
7. explicit `review_only_not_applied` statement;
8. required human/review/application next action.

Do not claim that the parent implementation is delivered/conformant merely because decomposition succeeded. Stage D1C reusable graph application remains unimplemented.

## Mandatory implementation closeout report

For implementation work, before closing the Issue, generate a closeout draft when the helper is available:

```powershell
python Pipeline/Supervisor/task_checkout.py draft-closeout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC044
```

Then post a final **Closeout Report** comment to the GitHub Issue. It must explicitly contain all of these sections:

1. **Outcome** — what usable result exists now?
2. **What changed** — what code/content/behavior/files changed?
3. **How I accomplished the task** — what implementation approach and major steps were used?
4. **Decisions and choices I made** — what implementation choices were made and why?
5. **Missing or underspecified items I encountered** — what did the task/canon not specify clearly?
6. **Additions beyond the original task** — what extra support work was added, if any, and why was it necessary?
7. **Validation performed** — tests, Unity/runtime checks, human checks, manifests/evidence, and results.
8. **Remaining follow-ups / risks** — anything unresolved, deferred, fragile, or intentionally out of scope.
9. **TaskGraph closeout state** — the actual evidence-derived current state after authoritative delivery/merge.
10. **Final branch / commits / merge information** — enough Git identity to trace the implementation and closeout.

If a section has nothing to report, write `None.`. Do not silently omit sections.

The implementation Issue may be closed as completed only after the normal orchestration/delivery/merge path is finished and the closeout report is posted. Closing the Issue does not create TaskGraph conformance; it records operational completion.

## Generic retry behavior

When the human gave a **generic** task-picking instruction, the orchestrator must continue candidate selection when the first candidate does not work out for a genuine selection/blocker reason.

### Before claim

Skip and keep trying if a candidate is:

- assigned;
- closed;
- materially resource-conflicted;
- inactive/invalid;
- already delivered when seeking fresh implementation;
- rejected by the production decomposition-selection preflight;
- otherwise plainly unsuitable from current repository evidence.

Do not spam GitHub with comments for merely inspected/unclaimed skipped candidates.

### After claim

Do not abandon a task because normal execution is hard. Compilation errors, test failures, implementation bugs, and ordinary bounded repair stay inside the selected work unit's normal execution/GER/validation loop.

If a **hard blocker** makes the work impossible or unauthorized within its bounded scope/budget:

1. post a comment describing the blocker and useful current state;
2. preserve useful branch/checkout/decomposition/log artifacts;
3. unassign/release the Issue as appropriate;
4. refresh current `main`, TaskGraph states, and GitHub claims;
5. choose the next sensible implementation or decomposition candidate;
6. continue until viable work is started or the safe candidate pool is exhausted.

Typical hard blockers include `CONTRACT_REVIEW_REQUIRED` for missing design/nonlocal scope, unauthorized scope expansion, unavoidable resource conflicts, exhausted decomposition rejection/failure, or unresolved external prerequisites.

### Successful decomposition is not a failure

If decomposition reaches `review_ready`, stop at the human/review/application boundary. Do not immediately retry another task as though the decomposition run failed.

## Release / abandonment

If the worker stops without finishing an implementation/decomposition attempt:

1. post a comment describing why the work is being released and what state the branch/checkout/output is in;
2. unassign the Issue unless it must remain deliberately reserved awaiting human review;
3. leave the Issue open unless the relevant orchestration work is truly finished under the current convention;
4. preserve useful branch/checkout/log/output artifacts until the human decides what to do with them.

For a generic task-picking request, releasing a genuinely blocked work unit normally returns the orchestrator to the candidate-selection loop rather than ending the run.

## Explicit-task exception

The retry/substitution rule applies to generic requests such as:

```text
Go pick a task and start on it.
```

If the human explicitly names the task, for example:

```text
Work on NSC-042.
```

then a blocker must be reported for that task. Do not silently switch to a different NSC task unless the human separately authorizes substitution.

## Required behavior for a fresh ChatGPT window

When the human says anything equivalent to **"pick a task," "work on a task," "start another task," or "be an orchestrator"** without naming a specific NSC ID, the ChatGPT instance must apply this process:

```text
read current repo + orchestration docs
        ↓
inspect TaskGraph and current task states
        ↓
build fresh implementation candidates
        +
build decomposition-work candidates
        ↓
search GitHub Issues for candidate NSC IDs
        ↓
exclude assigned/closed tickets
        ↓
inspect exclusive-resource conflicts
        ↓
choose one available work unit
        ↓
create/fill Issue if absent
        ↓
assign Issue + post Claim / Planned Approach + work_type
        ↓
implementation → isolated checkout + normal delivery workflow
OR
decomposition → Stage D1B.1 read-only proposal workflow
        ↓
genuine hard blocker/release under generic request
        ↓
refresh and KEEP TRYING another candidate
        ↓
stop when viable implementation is underway, review-ready decomposition is produced,
or the safe candidate pool is exhausted and human intervention is required
```

Do not ask the human to repeat this protocol when it is already committed in the repository.
