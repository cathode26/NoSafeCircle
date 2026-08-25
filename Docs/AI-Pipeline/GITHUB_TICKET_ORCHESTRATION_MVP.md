# GitHub Ticket Orchestration MVP

## Purpose

This is the minimum coordination layer for running several **human-directed ChatGPT orchestrators in parallel** against No Safe Circle.

It supports two bounded orchestrator work types under generic selection:

- `work_type: implementation` — fresh implementation of a suitable undelivered concrete executable contract;
- `work_type: decomposition` — Stage D1B.1 read-only decomposition of an eligible decomposition-relevant parent contract.

`decomposition` is an orchestrator work type, not a new TaskGraph `kind` or fabricated `NSC-###` work contract.

The implementation flow is:

```text
select implementation task
    ↓
check GitHub Issue
    ↓
claim Issue
    ↓
create isolated standalone clone + task branch
    ↓
perform normal ExecutionCrew / Unity / TaskDelivery workflow
    ↓
publish structured closeout to Issue
    ↓
close Issue after normal delivery/merge
```

The decomposition flow is:

```text
select decomposition-relevant parent
    ↓
check GitHub Issue
    ↓
claim/reserve parent Issue
    ↓
run Stage D1B.1 against physically read-only source
    ↓
publish Decomposition Closeout + review-only artifacts
    ↓
stop at human review/application boundary
```

This is intentionally **not** the final autonomous Supervisor. It does not implement dependency readiness, automatic priority selection, lease expiry, heartbeats, distributed locking, automatic PRs, automatic merge, GitHub Projects, budgets, or continuous polling.

The human operator accepts the possibility that two ChatGPT windows might claim the same ticket at nearly the same time and will correct that manually if it occurs.

For generic task-picking behavior, including candidate retry and decomposition selection, read:

```text
Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md
Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md
```

## Source-of-truth split

### TaskGraph owns durable work truth

`Tasks/NSC-###.yaml` owns:

- task identity/title;
- scope;
- dependencies;
- acceptance criteria;
- completion gates;
- downstream integration obligations;
- execution/decomposition state;
- exclusive resources;
- canon/GDD evidence;
- contract revision/provenance.

Committed TaskGraph evidence owns current conformance.

### GitHub owns operational visibility

A GitHub Issue owns the shared answer to:

- Is somebody currently working on or reserving this task?
- Which ChatGPT orchestration window claimed it?
- Is the current orchestration work implementation or decomposition?
- What approach did that orchestrator intend to use?
- What branch/base commit/checkout did it use for implementation?
- What provider/run/output did it use for decomposition?
- What did it actually implement or propose?
- What choices did it make?
- What was missing or underspecified?
- What validation/review happened?
- What follow-up remains?

GitHub operational state never replaces TaskGraph authority.

## Issue state convention

For an Issue whose title starts with the exact task ID:

| GitHub state | Meaning |
| --- | --- |
| no Issue | available; ticket has not been created yet |
| open + unassigned | available/released |
| open + assigned | claimed/in progress or deliberately reserved awaiting review |
| closed | orchestration finished under the applicable workflow |

For this MVP, assignment is the claim/reservation marker. No labels or Projects board are required.

A review-ready decomposition that still awaits human review/application should remain clearly reserved or otherwise marked so another orchestrator does not immediately rerun the same parent contract/hash.

## Issue title

Use the existing TaskGraph task ID:

```text
NSC-044 — Ruined Entry Spatial Blockout
```

For decomposition work, still use the **existing parent NSC ID**. Do not create a fake new TaskGraph ID for the act of decomposition.

The exact NSC ID must begin the title so other orchestrators can search reliably.

## Issue body

The Issue body should be generated from the committed task contract and include:

- what the task accomplishes;
- why it is bounded or why it requires decomposition;
- dependencies;
- acceptance criteria;
- completion/validation gates;
- downstream integration obligations;
- execution/decomposition state;
- exclusive resources;
- canon/design evidence;
- task contract path/revision/reconciliation key;
- the operational-state convention.

`Pipeline/Supervisor/task_checkout.py checkout ...` emits an `issue-body.md` for implementation work that follows the existing implementation format. Decomposition claims may use the same parent contract body and add decomposition-specific context in the Claim / Planned Approach.

## Claim protocol for each ChatGPT window

Before picking work:

1. Read the current repository/task graph and mandatory selection docs.
2. Build fresh implementation candidates from appropriate current `not_delivered` concrete executable work.
3. Also inspect active contracts for decomposition-work candidates accepted by the production Progressive Decomposer preflight.
4. For each plausible candidate, search GitHub Issues for its exact NSC ID.
5. Exclude an open Issue that is already assigned.
6. Exclude a closed Issue.
7. Inspect exclusive-resource conflicts with current claims.
8. Under a generic task-picking request, if the first candidate is unavailable/unsuitable, **continue to the next sensible candidate rather than stopping**.
9. When selecting an unclaimed work unit:
   - create its Issue if needed;
   - assign the Issue to `cathode26`;
   - identify this orchestration window with a worker ID such as `chatgpt-1`;
   - explicitly identify `work_type: implementation` or `work_type: decomposition`;
   - post a Claim / Planned Approach comment;
   - start the appropriate bounded pipeline.

### Local checkout for implementation

For `work_type: implementation`, from a clean current NoSafeCircle checkout:

```powershell
python Pipeline/Supervisor/task_checkout.py checkout NSC-044 --worker-id chatgpt-1
```

The helper follows the authoritative Windows rule:

- clone from `https://github.com/cathode26/NoSafeCircle.git`;
- do not clone the local working copy;
- do not use a Git worktree for Docker-backed execution;
- start from the exact current remote `main`;
- create an isolated descriptive task branch;
- validate TaskGraph before work begins.

For provider-backed Docker commands inside the standalone clone, continue to use the documented fixed Compose project:

```text
docker compose -p nosafecircle ...
```

### Read-only source for decomposition

For `work_type: decomposition`, do **not** create an implementation checkout merely because the old MVP flow always did so.

Follow `Pipeline/TaskDecomposition/README.md`. Stage D1B.1 requires a clean, physically read-only source mount and a filesystem-disjoint output root. The documented provider-backed command uses the decomposition compose profiles.

The authoritative decomposition eligibility check is `Pipeline/TaskDecomposition/context_builder.py::validate_task_selection`.

## Claim / Planned Approach comment

Every claimed Issue should contain a comment with the information applicable to its work type:

```text
Worker
work_type: implementation | decomposition
Exact base/source main commit
Branch + Checkout                         # implementation
Provider + decomposition output location  # decomposition
Planned approach
Expected validation/review boundary
Assumptions / risks
```

The **Planned approach** should explain what the orchestrator intends to do to accomplish the work, not merely repeat acceptance-criterion text.

For implementation, identify implementation choices already expected. If missing design is discovered rather than implementation freedom, follow existing contract/design authority rules rather than silently inventing canon.

For decomposition, explain why the parent is decomposition-relevant and what D1B.1 is expected to decide/propose. Do not imply that the resulting graph delta will be applied automatically.

## Normal implementation

After an implementation claim/checkout, follow the existing real-task delivery workflow. This MVP does not replace:

- Contract Locality Auditor;
- ExecutionCrew;
- human candidate review;
- Unity validation;
- TaskDelivery review/finalize;
- evidence publication;
- TaskGraph conformance derivation;
- human merge authority.

The Issue is the shared orchestration dashboard around those systems.

## Decomposition execution

After a decomposition claim, follow the existing Stage D1B.1 pipeline in `Pipeline/TaskDecomposition/README.md`.

The decomposition result may be:

- `already_concrete`;
- `decomposed`;
- `needs_artifact`;
- `needs_human`.

D1B.1 outputs remain `review_only_not_applied`. `graph_delta.json`, when present, is not automatic graph authority. Stage D1C reusable graph application remains unimplemented.

A generic task-picking request authorizes selecting and running an eligible decomposition proposal, not silently applying its result.

## Implementation closeout protocol

Before closing an implementation ticket, generate a closeout draft from the task checkout:

```powershell
python Pipeline/Supervisor/task_checkout.py draft-closeout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC044
```

The report is written outside the repository under:

```text
%USERPROFILE%\Downloads\NoSafeCircleOutput\TicketOrchestration\<TASK-ID>\<timestamp>\
```

The orchestrator must fill every required section.

### Required implementation closeout narrative

The final Issue comment must explicitly answer:

1. **Outcome** — what result exists now?
2. **What changed** — what behavior/content/code was added or changed?
3. **How I accomplished the task** — what approach/steps were used?
4. **Decisions and choices I made** — what implementation freedom was exercised?
5. **Missing or underspecified items I encountered** — what was not specified clearly?
6. **Additions beyond the original task** — what extra was added and why?
7. **Validation performed** — which tests/runtime/human checks ran and what happened?
8. **Remaining follow-ups / risks** — what still needs attention?
9. **TaskGraph closeout state** — what did current conformance report after authoritative delivery/merge?

If a section has nothing to report, write `None.`. Do not omit the section.

### Closing implementation

After the closeout report is posted and normal delivery/merge is finished:

- close the GitHub Issue as completed;
- leave the closeout report as durable operational history.

Closing a GitHub Issue does not itself establish conformance. The report should quote the actual TaskGraph-derived state rather than inventing completion truth.

## Decomposition closeout protocol

If D1B.1 reaches `review_ready`, post a **Decomposition Closeout** comment with:

1. worker ID and `work_type: decomposition`;
2. parent task ID/revision/source commit;
3. provider and run ID;
4. semantic decision;
5. `decomposition_result.json` identity/path;
6. `graph_delta.json` identity/path when present;
7. concise proposed-child or `needs_artifact` / `needs_human` summary;
8. explicit `review_only_not_applied` statement;
9. required human/review/application next action.

A `review_ready` result is successful completion of the **decomposition work unit** even when the semantic decision is `needs_artifact` or `needs_human`.

Do not claim the parent implementation is delivered/conformant merely because decomposition succeeded. Keep the parent clearly reserved/marked while the review-ready output awaits human review/application so another orchestrator does not immediately duplicate the run.

## Release / abandonment

If a worker stops without completing the selected work unit:

1. add an Issue comment explaining why the work is being released;
2. preserve useful branch/checkout/log/decomposition-output artifacts;
3. unassign the Issue unless it must remain deliberately reserved awaiting human review;
4. keep the Issue open unless orchestration is truly finished under the applicable workflow.

For a **generic task-picking request**, release of a genuinely blocked candidate normally returns the orchestrator to current candidate selection:

```text
release blocked candidate
        ↓
refresh current main + TaskGraph + Issues
        ↓
choose next sensible implementation or decomposition candidate
        ↓
continue until viable work starts or safe candidates are exhausted
```

Do not task-hop because normal implementation is difficult. Compilation errors, failing tests, implementation bugs, and ordinary bounded repair stay inside the selected task's normal execution/GER/validation loop.

Do not delete the branch, checkout, logs, or decomposition outputs automatically. Preserve them until the human decides whether they contain useful work.

## Explicit-task exception

Automatic substitution/retry applies to a generic request such as:

> Go pick a task and start on it.

If the human explicitly names the target (`Work on NSC-042` or `Decompose NSC-021`), a blocker must be reported for that target rather than silently substituting another NSC task unless the human separately authorizes substitution.

## Five-window startup prompt

The human can give each ChatGPT window a short generic instruction because the repository now contains the selection policy. For example, changing only the worker number:

> You are `chatgpt-1`, one No Safe Circle task orchestrator. Go pick a task and start on it. Follow the current repository's mandatory task-selection, retry, decomposition, GitHub-claim, checkout/execution, and closeout instructions. Keep trying sensible candidates if an early generic candidate is unavailable or genuinely blocked; do not substitute another task if I explicitly name one.

Use worker IDs `chatgpt-1` through `chatgpt-5`.

A fully fresh window should read `AI_PIPELINE.md`, `START_HERE.md`, `TASK_SELECTION_AND_CHECKOUT.md`, `GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md`, and the applicable implementation/decomposition runbook rather than relying on this example prompt as the complete policy.

## Known MVP limitations

Deliberately deferred:

- simultaneous-claim atomicity;
- automatic issue synchronization for every TaskGraph item;
- dependency-readiness policy;
- automatic task ranking;
- GitHub Projects;
- Draft PR creation;
- bot/GitHub App authentication;
- lease timeout/heartbeat;
- resource-level claims;
- automatic merge/close;
- reusable automatic graph application for decomposition (D1C);
- D1B.2 independent decomposition verification/refinement.

Generic orchestrator retry after a genuine candidate skip/release is now a documented human-authorized behavior, but it is still performed by the ChatGPT orchestrator rather than a persistent local autonomous polling supervisor.
