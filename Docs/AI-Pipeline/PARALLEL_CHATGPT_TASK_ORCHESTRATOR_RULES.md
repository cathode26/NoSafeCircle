# Parallel ChatGPT Task Orchestrator Rules

## Status

This document is **mandatory operating guidance** for any ChatGPT instance that selects, claims, starts, orchestrates, releases, or closes a real No Safe Circle task while multiple ChatGPT task-orchestrator windows may be active.

It is the short operational contract layered on top of:

- `Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md`;
- `Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md`;
- `Docs/AI-Pipeline/REAL_TASK_DELIVERY_WINDOWS_CLONE_NOTE.md`;
- `Pipeline/ExecutionCrew/README.md`;
- `Pipeline/TaskDelivery/README.md`.

The detailed documents above remain authoritative for their respective subsystems. This file exists so a fresh ChatGPT window cannot miss the coordination protocol.

## Core rule

**Do not choose or start a task from TaskGraph alone. GitHub Issue state is the shared operational coordination layer for parallel ChatGPT orchestrators.**

TaskGraph still owns durable scope, dependencies, acceptance criteria, completion gates, resources, canon evidence, and conformance. GitHub Issues only own shared operational visibility: available, claimed, released, and orchestration-finished.

## Issue-state convention

For the Issue whose title begins with the exact `NSC-###` ID:

| GitHub state | Operational meaning |
| --- | --- |
| no Issue | available; create the ticket before claiming |
| open + unassigned | available / released |
| open + assigned | claimed / being worked; do not pick it |
| closed | orchestration finished; do not pick it |

For the current MVP, assignment is the claim marker. No atomic distributed lock is implemented. The human operator accepts that simultaneous duplicate claims are possible and will correct them manually if needed.

## Mandatory pre-selection procedure

Before selecting a task, every orchestrator must:

1. identify itself with a worker ID such as `chatgpt-1` through `chatgpt-5`;
2. read current `main`, `AI_PIPELINE.md`, `Docs/AI-Pipeline/START_HERE.md`, this file, `GITHUB_TICKET_ORCHESTRATION_MVP.md`, and the real-task delivery runbook;
3. inspect current TaskGraph rather than relying on conversation memory;
4. inspect current evidence-derived task states using the repository tools;
5. identify candidate `active`, `implementation`, `single_agent`, `concrete` tasks appropriate to the human request;
6. search GitHub Issues for each candidate's exact NSC ID;
7. exclude any candidate whose Issue is open and assigned;
8. exclude any candidate whose Issue is closed;
9. inspect each candidate's `exclusive_resources` and compare them with currently claimed tickets before deciding whether parallel work is sensible;
10. never infer dependency readiness merely from contract shape or Issue state; dependency readiness remains a separate unimplemented policy unless the human explicitly directs the work.

A ticket being unclaimed does **not** mean two tasks with the same Unity scene/builder/resource are safe to implement simultaneously. Resource conflicts must be surfaced to the human.

## Mandatory ticket contents

If a selected task has no Issue, create one before implementation. Its title must begin with the exact task ID:

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
- exclusive resources;
- relevant GDD/canon evidence or references;
- explicit out-of-scope notes;
- `Tasks/<TASK-ID>.yaml` path, contract revision, and reconciliation key;
- the Issue-state convention.

Do not replace the TaskGraph contract with prose in the Issue. The Issue is a human-facing operational mirror.

## Mandatory claim procedure

When the orchestrator chooses an available ticket:

1. assign the Issue to `cathode26`;
2. identify the ChatGPT worker ID in a **Claim / Planned Approach** comment;
3. only after the GitHub claim exists, create the isolated task checkout;
4. create the checkout from the current GitHub remote `main`, never by cloning the local checkout and never with a Git worktree for Docker-backed execution;
5. use the checkout helper when available:

```powershell
python Pipeline/Supervisor/task_checkout.py checkout NSC-044 --worker-id chatgpt-1
```

The Claim / Planned Approach comment must record:

- worker ID;
- exact base `main` commit;
- branch name;
- checkout path;
- a concrete description of how the orchestrator plans to accomplish the task;
- expected implementation surfaces/files when known;
- expected validation;
- implementation choices it already expects to make;
- assumptions, risks, resource conflicts, or uncertainties.

The **planned approach must describe the intended method**, not merely restate acceptance criteria.

## Implementation decisions and missing information

During the task, the orchestrator must distinguish between:

1. **implementation choice** — freedom legitimately left to the implementer;
2. **missing or underspecified design** — information that requires design authority rather than invention;
3. **necessary supporting addition** — a helper/test/small integration required to complete the approved task;
4. **scope expansion** — additional work not required by the task and not automatically authorized.

The orchestrator must keep a record of material choices and discoveries for closeout.

If design is genuinely missing, follow the existing contract/design/artifact authority rules. Do not silently invent canon just to finish a ticket.

## Normal delivery workflow remains mandatory

Claiming a GitHub Issue does not bypass the established delivery process. After checkout, continue through the applicable existing workflow, including:

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

## Mandatory closeout report

Before closing the Issue, generate a closeout draft when the helper is available:

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

The Issue may be closed as completed only after the normal orchestration/delivery/merge path is finished and the closeout report is posted. Closing the Issue does not create TaskGraph conformance; it records operational completion.

## Release / abandonment

If the worker stops without finishing:

1. post a comment describing why the work is being released and what state the branch/checkout is in;
2. unassign the Issue;
3. leave the Issue open;
4. preserve useful branch/checkout/log artifacts until the human decides what to do with them.

This returns the task to the available pool without falsely marking it done.

## Required behavior for a fresh ChatGPT window

When the human says anything equivalent to **"pick a task," "work on a task," "start another task," or "be an orchestrator"**, the ChatGPT instance must apply this process before selecting work:

```text
read current repo + orchestration docs
        ↓
inspect TaskGraph and current task states
        ↓
search GitHub Issues for candidate NSC IDs
        ↓
exclude assigned or closed tickets
        ↓
inspect exclusive-resource conflicts
        ↓
choose one available task
        ↓
create/fill Issue if absent
        ↓
assign Issue + post Claim / Planned Approach
        ↓
create isolated GitHub clone/branch with task_checkout.py
        ↓
perform normal implementation/delivery workflow
        ↓
post structured Closeout Report
        ↓
close Issue only when orchestration is finished
```

Do not ask the human to repeat this protocol when it is already committed in the repository.
