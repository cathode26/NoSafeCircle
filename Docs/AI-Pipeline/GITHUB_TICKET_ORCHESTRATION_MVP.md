# GitHub Ticket Orchestration MVP

## Purpose

This is the minimum coordination layer for running several **human-directed ChatGPT orchestrators in parallel** against No Safe Circle.

It implements the small operational slice already anticipated by `03_SUPERVISOR_GIT_GITHUB_CONTEXT.md`:

```text
select task
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
close Issue
```

This is intentionally **not** the final autonomous Supervisor. It does not implement dependency readiness, automatic priority selection, lease expiry, heartbeats, distributed locking, automatic PRs, automatic merge, GitHub Projects, budgets, or continuous polling.

The human operator accepts the possibility that two ChatGPT windows might claim the same ticket at nearly the same time and will correct that manually if it occurs.

## Source-of-truth split

### TaskGraph owns durable work truth

`Tasks/NSC-###.yaml` owns:

- task identity/title;
- scope;
- dependencies;
- acceptance criteria;
- completion gates;
- downstream integration obligations;
- exclusive resources;
- canon/GDD evidence;
- contract revision/provenance.

Committed TaskGraph evidence owns current conformance.

### GitHub owns operational visibility

A GitHub Issue owns the shared answer to:

- Is somebody currently working on this task?
- Which ChatGPT orchestration window claimed it?
- What approach did that orchestrator intend to use?
- What branch/base commit/checkout did it use?
- What did it actually implement?
- What choices did it make?
- What was missing or underspecified?
- What did it add beyond the original task?
- What validation happened?
- What follow-up remains?

GitHub operational state never replaces TaskGraph authority.

## Issue state convention

For an Issue whose title starts with the exact task ID:

| GitHub state | Meaning |
| --- | --- |
| no Issue | available; ticket has not been created yet |
| open + unassigned | available/released |
| open + assigned | claimed / in progress |
| closed | orchestration finished |

For this MVP, assignment is the claim marker. No labels or Projects board are required.

## Issue title

Use:

```text
NSC-044 — Ruined Entry Spatial Blockout
```

The exact NSC ID must begin the title so other orchestrators can search reliably.

## Issue body

The Issue body should be generated from the committed task contract and include:

- what the task accomplishes;
- why it is bounded;
- dependencies;
- acceptance criteria;
- completion/validation gates;
- downstream integration obligations;
- exclusive resources;
- canon/design evidence;
- task contract path/revision/reconciliation key;
- the operational-state convention.

`Pipeline/Supervisor/task_checkout.py checkout ...` emits an `issue-body.md` that follows this format.

## Claim protocol for each ChatGPT window

Before picking a task:

1. Read the current repository/task graph.
2. Identify candidate `active`, `implementation`, `single_agent`, `concrete` tasks appropriate to the human request.
3. For each candidate, search GitHub Issues for its exact NSC ID.
4. Exclude an open Issue that is already assigned.
5. Exclude a closed Issue.
6. When selecting an unclaimed task:
   - create its Issue if needed;
   - assign the Issue to `cathode26`;
   - identify this orchestration window with a worker ID such as `chatgpt-1`;
   - create the isolated checkout;
   - post a Claim / Planned Approach comment.

### Local checkout

From a clean current NoSafeCircle checkout:

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

## Claim / Planned Approach comment

Every claimed Issue should contain a comment with:

```text
Worker
Exact base main commit
Branch
Checkout
Planned approach
Expected validation
Assumptions / risks
```

The **Planned approach** should explain what the orchestrator intends to do to accomplish the task, not merely repeat acceptance-criterion text.

The orchestrator should identify implementation choices it already expects to make. If it discovers missing design rather than implementation freedom, it must follow the existing contract/design authority rules rather than silently inventing canon.

## Normal implementation

After claim/checkout, follow the existing real-task delivery workflow. This MVP does not replace:

- Contract Locality Auditor;
- ExecutionCrew;
- human candidate review;
- Unity validation;
- TaskDelivery review/finalize;
- evidence publication;
- TaskGraph conformance derivation;
- human merge authority.

The Issue is the shared orchestration dashboard around those systems.

## Closeout protocol

Before closing a ticket, generate a closeout draft from the task checkout:

```powershell
python Pipeline/Supervisor/task_checkout.py draft-closeout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC044
```

The report is written outside the repository under:

```text
%USERPROFILE%\Downloads\NoSafeCircleOutput\TicketOrchestration\<TASK-ID>\<timestamp>\
```

The orchestrator must fill every required section.

### Required closeout narrative

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

### Closing

After the closeout report is posted and normal delivery/merge is finished:

- close the GitHub Issue as completed;
- leave the closeout report as durable operational history.

Closing a GitHub Issue does not itself establish conformance. The report should quote the actual TaskGraph-derived state rather than inventing completion truth.

## Release / abandonment

If a worker stops without completing the task:

1. add an Issue comment explaining why the work is being released;
2. unassign the Issue;
3. keep the Issue open.

That returns the task to the available pool without misrepresenting it as done.

Do not delete the branch, checkout, or logs automatically. Preserve them until the human decides whether they contain useful work.

## Five-window startup prompt

The human can give each ChatGPT window the following instruction, changing only the worker number:

> You are `chatgpt-1`, one No Safe Circle task orchestrator. Read `AI_PIPELINE.md`, `Docs/AI-Pipeline/START_HERE.md`, `Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md`, and the real-task delivery runbook. Pick one appropriate current TaskGraph implementation task. Before selecting it, search GitHub Issues for the exact NSC ID. Do not pick a task whose open Issue is already assigned or whose Issue is closed. Create the Issue if absent, fill it from the committed task contract, and assign it to `cathode26` to claim it. Then give me the exact PowerShell command to create its isolated checkout using `Pipeline/Supervisor/task_checkout.py`. After checkout, post a Claim / Planned Approach comment explaining how you intend to accomplish it. Carry the task through the existing ExecutionCrew/Unity/TaskDelivery workflow. At the end, generate and fill the structured closeout report, post it to the Issue, and close the Issue only after orchestration is finished. Explicitly document implementation choices, anything missing/underspecified, and anything added beyond the original task.

Use worker IDs `chatgpt-1` through `chatgpt-5`.

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
- automatic release after failures;
- automatic merge/close.

These should be added only when real usage demonstrates that they are worth the complexity.
