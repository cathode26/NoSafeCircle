# Generic Task Selection: Retry Loop and Decomposition Work

## Purpose

This policy defines what a fresh ChatGPT orchestrator should do when the human gives a generic instruction such as:

> Go pick a task and start on it.

That instruction is sufficient human authorization to select one bounded unit of work using the committed repository process. The orchestrator must not require the human to preselect an `NSC-###` ID when the repository already contains enough information to choose safely.

This policy adds two selectable orchestrator work types:

1. **fresh implementation work** — implement an existing concrete TaskGraph contract that has not yet been delivered;
2. **decomposition work** — run the existing Progressive Decomposer against an existing decomposition-relevant TaskGraph contract and produce review-ready decomposition artifacts.

`decomposition` is an **orchestrator work type**, not a new TaskGraph `kind`. Durable TaskGraph product-work kinds remain `feature`, `artifact`, and `implementation`. Decomposition operates on an existing parent contract and does not invent a synthetic NSC task merely to represent the act of decomposing it.

## Candidate pool A — fresh implementation work

Start with:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
```

A fresh implementation candidate should then be checked with:

```powershell
python Pipeline/TaskGraph/taskcontrol.py show <TASK-ID>
```

Normal fresh implementation work should be an active, bounded contract appropriate to the human's request, normally:

- `kind: implementation` or an explicitly executable artifact;
- `execution_scope: single_agent`;
- `decomposition_state: concrete`;
- not already delivered/evidenced;
- not operationally claimed by another orchestrator;
- not blocked by an unacceptable exclusive-resource conflict;
- not obviously dependent on unavailable or missing required work.

`needs_testing` is not fresh implementation work. It means prior completed/evidenced work may need another testing/revalidation pass after later tracked changes.

## Candidate pool B — decomposition work

Also inspect the active TaskGraph for work that is meaningfully decomposition-relevant:

```powershell
python Pipeline/TaskGraph/taskcontrol.py list --disposition active
```

Inspect plausible parents with:

```powershell
python Pipeline/TaskGraph/taskcontrol.py show <TASK-ID>
```

A decomposition-work candidate must satisfy the production Progressive Decomposer's own committed preflight in `Pipeline/TaskDecomposition/context_builder.py::validate_task_selection`. In practical terms, the parent must be:

- a valid active schema-v2 non-root task;
- not already `decomposition_state: decomposed`;
- not already concrete `single_agent` work;
- meaningfully decomposition-relevant under the current execution/decomposition axes.

A common high-confidence decomposition candidate is a task whose approved design is concrete but whose execution scope is:

```text
needs_execution_decomposition
```

`human_integration_required` and `unknown` may also be decomposition-relevant, subject to the production preflight and the current contract/canon.

Do not decompose distant work merely because it can theoretically be split. ADR-021 remains controlling: decomposition is progressive and just-in-time. Prefer decomposition when it unlocks useful near-frontier work, when a high-value parent is explicitly too broad for one agent, or when no equally useful fresh implementation candidate can safely proceed.

## How to run decomposition work

Decomposition work uses the existing Stage D1B.1 read-only pipeline. Read:

```text
Pipeline/TaskDecomposition/README.md
```

The production command is:

```bash
python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id <TASK-ID> --provider <claude|codex>
```

For the normal Docker-backed authenticated workflow, use the documented read-only compose command from `Pipeline/TaskDecomposition/README.md`.

The orchestrator must preserve the existing authority boundary:

- D1B.1 source access is read-only;
- the result may be `already_concrete`, `decomposed`, `needs_artifact`, or `needs_human`;
- accepted outputs are immutable review artifacts;
- `graph_delta.json`, when produced, is review-only and is **not automatically applied**;
- decomposition does not grant readiness, execution authority, delivery, conformance, or merge authority;
- Stage D1C reusable graph application is not implemented.

A generic task-picking instruction authorizes selecting and running an eligible decomposition proposal. It does **not** authorize silently applying proposed child contracts to the persistent TaskGraph.

## GitHub coordination for decomposition work

Decomposition work still needs shared operational coordination so two ChatGPT windows do not decompose the same parent simultaneously.

Use the GitHub Issue for the existing parent `NSC-###` contract. In the Claim / Planned Approach comment, explicitly record:

```text
work_type: decomposition
```

Do not create a fake new TaskGraph ID for the decomposition activity.

If the decomposition reaches `review_ready`, post a **Decomposition Closeout** comment containing:

- worker ID;
- parent task ID, revision, and source commit;
- provider and run ID;
- decomposition decision;
- paths/identities of `decomposition_result.json` and `graph_delta.json` when present;
- a concise summary of proposed children or the `needs_artifact` / `needs_human` result;
- explicit statement that the artifacts are review-only and have not been applied;
- what human/review/application action is required next.

A review-ready decomposition is a successful completion of the **decomposition work unit** even though the parent implementation is not delivered. Do not falsely close the parent implementation as delivered or conformant.

While a review-ready proposal is awaiting human review/application, keep the parent operationally reserved or otherwise clearly marked in its Issue so another orchestrator does not immediately rerun the same decomposition against the same parent contract/hash.

## Generic candidate retry loop

For a generic instruction such as `Go pick a task and start on it`, selecting one bad candidate must not end the attempt.

Use this loop:

```text
refresh current main + TaskGraph + GitHub claims
        ↓
build fresh-implementation candidates
        +
build decomposition-work candidates
        ↓
rank sensible available work
        ↓
try best candidate
        ↓
viable?
  yes → claim and execute the appropriate work type
  no  → record why it was skipped/released
          ↓
        refresh state if needed
          ↓
        try the next sensible candidate
```

Continue until either:

1. one viable unit of work is successfully started; or
2. the orchestrator has exhausted the sensible safe candidate pool and must report the concrete blockers requiring human intervention.

Do not stop merely because the first candidate is assigned, closed, resource-conflicted, clearly nonlocal, rejected by deterministic preflight, or otherwise unsuitable.

## Before-claim skip reasons

Skip a candidate and continue to the next one when, for example:

- its GitHub Issue is already assigned or closed;
- its exclusive resources materially conflict with currently claimed work;
- its current contract is no longer active;
- the task is already delivered when the intent is fresh implementation;
- the candidate does not match the requested work type;
- a decomposition candidate fails the deterministic decomposition-selection preflight;
- current repository evidence shows the candidate is plainly inappropriate to start.

Record meaningful skip reasons in the orchestrator's working notes; do not create noisy GitHub comments for every unclaimed candidate merely inspected and skipped.

## After-claim hard blockers

Do not task-hop because normal implementation is difficult. Compilation failures, failing tests, implementation bugs, and ordinary bounded repair belong to the normal ExecutionCrew/GER/validation loop.

Release a claimed task and return to generic selection only when a genuine hard blocker makes the selected work unsuitable to continue within its authority/budget, for example:

- `CONTRACT_REVIEW_REQUIRED` exposes missing design, an undeclared required integration, or a materially nonlocal contract;
- the work requires unauthorized scope expansion rather than a bounded implementation choice;
- an unavoidable shared-resource conflict appears after claim;
- deterministic decomposition preflight proves the selected parent is not decomposition-relevant;
- a decomposition run is rejected/blocked and the bounded retry policy is exhausted;
- a required external prerequisite cannot be resolved within the selected work unit.

When releasing after claim, follow the existing release/abandonment procedure: preserve useful branch/output artifacts, post the blocker, unassign/release the Issue as appropriate, then refresh current state and try another candidate.

## Successful decomposition is not a failed candidate

If D1B.1 returns `review_ready`, decomposition work succeeded even when the semantic decision is `needs_artifact` or `needs_human`. The useful result is the reviewed diagnosis/proposal. Stop that work unit at the existing human/review boundary rather than immediately selecting another task as though decomposition failed.

If the run is `agent_failed`, `rejected`, or deterministically blocked, use the bounded retry/release rules and then continue candidate selection when appropriate.

## Explicit-task exception

The automatic candidate retry/substitution rule applies to generic human instructions such as:

> Pick a task and start on it.

It does **not** authorize replacing an explicitly named task. If the human says:

> Work on NSC-042.

then a blocker on NSC-042 must be reported for that task rather than silently switching to NSC-021 or another candidate, unless the human separately authorizes substitution.

## Selection preference

The orchestrator should choose the unit of work that best advances the current game/project frontier while respecting dependencies, claims, resource conflicts, and authority boundaries.

When two candidates are comparably valuable and safe, prefer fresh implementation because it advances playable game state directly. Decomposition may take priority when it unlocks important blocked work or when the current implementation frontier has no sensible one-agent candidate.

The goal is productive forward motion, not maximizing the number of decomposition runs or keeping every worker busy at any cost.
