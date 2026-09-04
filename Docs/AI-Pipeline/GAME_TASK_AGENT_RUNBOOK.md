# Game Task Agent — one command to a committed human Unity handoff

## Purpose

The Game Task Agent connects the durable GitHub Issue workflow to the existing real implementation pipeline:

```text
explicit eligible task or validated agent-ready Issue
        ↓
managed Issue lease
        ↓
canonical task checkout and branch
        ↓
bounded repository inspection
        ↓
exact implementation/test scope validation
        ↓
ExecutionCrew
  Contract Locality Auditor
  Implementer
  Test Author
  Validator
  bounded repair
        ↓
verified review-ready candidate.patch
        ↓
independent apply/check in disposable clone
        ↓
apply to canonical task checkout
        ↓
commit and push exact task branch
        ↓
Issue checklist for Vincent
        ↓
human_action_required
```

The agent does not ask Vincent to review a raw patch or finish implementation. It commits and pushes the work before handing over the Issue.

## Prerequisites

From the clean shared controller checkout:

```text
C:\NSC\NSC\NoSafeCircle
```

confirm:

- Git is available;
- GitHub CLI is authenticated with `gh auth login`;
- Docker Desktop and Docker Compose are running;
- Claude or Codex provider authentication used by the repository is available;
- `OPENAI_API_KEY` is set for the OpenAI supervisor;
- the OpenAI Agents SDK dependency is installed.

Install the isolated Python dependency once:

```powershell
python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt
```

## Start one explicit task

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-### -ExecutionProvider claude
```

The explicit task must pass the real TaskGraph eligibility and dependency checks. The agent does not silently switch to another task when the named task is blocked.

Use Codex for ExecutionCrew instead:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-### -ExecutionProvider codex
```

The OpenAI supervisor model can be selected independently:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-### -ExecutionProvider claude -Model gpt-5.6
```

## Resume durable agent-ready work

Run the same launcher without a task ID:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1
```

The launcher first finds fully validated `nsc-state:agent-ready` Issues. It resumes the oldest valid Issue rather than selecting a new task. The Issue state, event chain, phase, branch, commit, human result, and task-contract identity are revalidated before work begins.

When no validated agent-ready Issue exists, generic resume stops and asks for an explicit task ID. It does not guess dependency readiness or autonomously invent fresh work.

For supervised multi-task operation, each live scheduler poll first fetches
`origin/main` and fast-forwards the clean attached controller `main`. A dirty or
diverged controller stops admissions without reset or overwrite. Every
implementation and decomposition provider runs from its own canonical
standalone task checkout, so this refresh cannot move the repository beneath an
active worker.

One local-ahead controller state has a deterministic recovery path. If D1C
created its canonical graph-application commit but the ordinary push did not
reach `origin/main`, the next poll proves the exact approved `plan_id`, the
commit's sole authorized parent, the fully applied graph, and the unchanged
remote parent. It then excludes every other committed task and resumes only
that decomposition application to retry the same non-force push. Any other
local-ahead or diverged history still stops without reset, rebase, overwrite,
or force-push. A timed-out Git command is reported through the same durable
lease-release and worker-result path rather than escaping as an unrecorded
process failure.

One scheduler poll may admit multiple workers, bounded by both `--max-workers`
and `--architect-max-invocations-per-poll`. After every launch it repeats the
source refresh, Stage-2 plan, and reservation observation before paying for the
next architect decision. A validated durable resume receives a dedicated
architect decision before fresh candidates. If that resume must wait, the
cached non-start decision permits disjoint fresh work later in the same bounded
capacity pass.

Each scheduler session also appends its exact JSON event stream to
`Pipeline/ArchitectureReview/outputs/orchestrator/events/<scheduler-id>.jsonl`.
Use that journal to diagnose admission delays, worker parentage, drain behavior,
and process failures; console output alone is not durable evidence.

GitHub can briefly expose an updated managed-Issue body before its matching
event comment. Queue and reservation reads retry that narrowly recognized skew
through exact single-Issue reads under one bounded scan deadline. A missing
exact read is not treated as closure: only a positive `CLOSED` Issue releases
the reservation, while persistent incoherence remains fail-closed.

Within one scheduler capacity pass, durable reservation discovery and Stage-2
planning share one read-only Issue/comment snapshot. A fresh snapshot is built
after every worker launch, avoiding both duplicate full-repository pagination
and contradictory GitHub views within one admission decision.

If one scheduler-owned worker fails, new admissions stop and the scheduler
supervises already-running workers for the configured bounded fatal-drain
interval (30 minutes by default). It does not terminate those workers or
release their leases. Ctrl+C during a fatal drain preserves the failure exit
code, and the final event reports any worker whose operating-system survival
cannot be guaranteed.

Every scheduler-launched worker writes `run_result.json` beside its `run.json`
as its last durable result. The scheduler derives the artifact path from its
own task/run identity; it never trusts a path supplied by the child. It accepts
the result only when the run ID, unguessable worker ID, task, admitted main
commit, task-contract hash, process ID, timestamps, status, and observed exit
code all agree. A missing, stale, malformed, or contradictory artifact is a
fatal child failure even when the process exits zero.

Exit `0` is reserved for the successful `human_action_required` and
`completed` artifact states. Exit `3` means a deterministic `blocked` result
(including `needs_human` and `checks_pending`); it emits `worker_blocked` and
frees capacity without counting the task as complete or halting other safe
admissions. Exit `4` means `no_safe_work` and emits `worker_idle`. Exit `2` or
any unknown/operating-system code emits `worker_failed`, stops new admissions,
and starts the bounded drain.

For a bounded rehearsal that must leave a legitimate task untouched, pass a
repeatable session exclusion such as `--exclude-task-id NSC-042` to
`polling_orchestrator.py`. The scheduler supplies that ID to Stage 2 on every
poll and records it in `poll_started`; it does not change the task contract,
Issue, claim, checkout, or branch. This is an operator boundary for the session,
not a statement that the task is complete.

## What happens during a fresh implementation run

1. The controller validates the selected task, TaskGraph, dependencies, controller `HEAD`, working-tree cleanliness, and exclusive-resource availability.
2. It creates or initializes the task Issue and records a hashed agent lease.
3. It creates or resumes:

   ```text
   C:\NSC\NSC\<TASK-ID>
   ```

4. The OpenAI supervisor receives bounded repository read, search, and exact file-list tools. It does not receive unrestricted shell or direct game-code write authority.
5. The supervisor proposes the smallest exact implementation and Unity-test file set.
6. Deterministic validation rejects wrong existing/new classifications, missing committed parents, ignored paths, test/implementation overlap, protected repository areas, unrelated resource roots, and unsafe file types.
7. The existing Docker ExecutionCrew performs implementation, test authorship, semantic validation, and its bounded repair cycle.
8. A `review_ready` result is checked against its persisted `crew_result.json`, source commit, task-contract hash, exact requested paths, final changed paths, and candidate SHA-256.
9. Immediately before the first human handoff, the integrator fetches current
   `origin/main`. The reviewed candidate is applied with Git three-way
   resolution in a disposable clone based on that exact main commit. When main
   advanced without changing the task contract, the clean task branch advances
   to current main before the candidate is applied. An overlapping candidate
   that cannot be resolved safely is rejected for repair; stale code is not
   committed for human testing.
10. The candidate is applied to the canonical task checkout, and its path set,
    whitespace, TaskGraph, and task-contract identity are revalidated against
    the refreshed main base. Only the exact verified task paths are staged and
    committed locally. The local commit is necessary because authoritative
    tests must identify the exact immutable commit and tree they validated.
11. When the committed task-specific validation policy names authoritative
    Unity checks, the clean runner executes them against that exact local
    commit. Its hash-verified manifest is preserved outside the checkout and
    bound into the integration receipt. A failed test or any test-created
    repository mutation stops the handoff; the task branch is not pushed.
12. Only after the pre-handoff checks pass is the exact commit pushed without
    force. The Issue receives the exact branch, commit, concrete implementation
    summary, checks already completed, numbered Unity steps, expected result,
    and PASS/FAIL template.
13. The Issue changes to:

    ```text
    human_action_required / unity_runtime_validation
    ```

The agent then stops.

## Vincent's task

The Issue is the durable to-do item. It states:

- the canonical checkout;
- exact branch;
- exact commit to test;
- scene or setup to open;
- numbered Play Mode steps;
- observable PASS criteria;
- what to include in a failure reproduction.

Test only the commit named in the Issue.

Post a result comment:

```text
## Human validation result

Result: PASS
Tested commit: `<exact 40-character SHA>`

Completed steps:
- ...

Notes:
...
```

or:

```text
## Human validation result

Result: FAIL
Tested commit: `<exact 40-character SHA>`

Failed step:
...

Reproduction:
1. ...

Expected:
...

Observed:
...
```

Then apply:

```text
nsc-state:agent-ready
```

The GitHub Action validates the managed state, event chain, exact tested commit, and PASS/FAIL format before changing the phase.

For a confirmed PASS, the normal one-command handoff is:

```powershell
python Pipeline\TaskReviewAgent\pass_and_resume_task.py NSC-### --source . --checkout-root C:\NSC\NSC --execution-provider claude --tested-commit <exact-40-character-SHA> --apply
```

Run this only after completing the managed Issue's Unity checklist. The helper
fails closed unless the supplied SHA equals the clean local checkout, its
remote-tracking task branch, and both exact commit fields in the current human
handoff. It posts the canonical PASS comment, replaces the human-action state
label with `nsc-state:agent-ready`, and waits for GitHub to publish a valid,
event-count-consistent `agent_ready / delivery_evidence` state before invoking
`Start-GameTaskAgent.ps1`. This wait prevents a fast restart from observing a
partially updated Issue dashboard/event chain.

## Resume behavior after human work

The Issue workflow records:

```text
PASS -> agent_ready / delivery_evidence
FAIL -> agent_ready / repair
```

A later generic agent therefore knows which branch and commit to resume and whether it is handling repair or delivery continuation. It never relies on the previous browser conversation.

For a PASS, the exact-commit human decision carries forward through delivery
evidence and merge closeout. The downstream controller performs the second
current-main synchronization, reruns the task's authoritative Unity checks on
the resulting exact commit, generates hash-bound evidence, and continues
without a redundant second delivery-proposal approval when the canonical
checkout remains clean and the commit is still exactly the one Vincent tested.
A changed commit, uncommitted file, scope drift, failed check, merge conflict,
or other reconciliation anomaly still stops before evidence publication or
merge.

If `origin/main` advanced, the downstream controller first merges current main
into the task branch and pushes the merge commit. The new commit always returns
to `human_action_required` for exact-commit testing, even when the mainline drift
is automation-only. A PASS on that integrated commit then authorizes delivery
and merge closeout without another approval while the checkout remains clean
and unchanged.

These are two separate current-main boundaries. The first runs before the local
candidate commit and its pre-handoff authoritative tests. The second runs after
the human PASS and immediately before authoritative delivery validation. Both
may be no-ops. If either produces a different commit, validation applies to the
new integrated commit; a post-PASS merge always invalidates the older
exact-commit PASS and returns to `human_action_required`.

During merge closeout, one launcher invocation waits for the exact pull request's
required checks for up to 15 minutes while continuing to print normal work
heartbeats. If the checks pass, it proceeds through the existing exact-head merge
and post-merge verification without requiring another command. A failed check
still stops immediately; a timeout releases the lease safely so a later generic
invocation can resume. Operators may override the bounded wait and poll intervals
with `NSC_MERGE_CHECK_WAIT_SECONDS` and `NSC_MERGE_CHECK_POLL_SECONDS`.

## Read-only inspection

To inspect what the production controller would do without acquiring a lease or writing an Issue:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-### -Mode observe
```

## Reset an abandoned task to fresh availability

Do not delete or reset a task checkout merely to retry the launcher. When Vincent explicitly abandons an undelivered run and requests a fresh start, follow:

```text
Docs/AI-Pipeline/FRESH_TASK_RESET_RUNBOOK.md
```

That procedure closes the abandoned Issue and PR without fabricating completion, fences deletion of the exact remote branch, verifies and removes only clean task-specific checkouts, archives the active checkout manifest, retains immutable run logs, and proves the TaskGraph task is still `not_delivered` before another explicit launch.

## Safety boundaries

The Game Task Agent cannot:

- edit `main`;
- force-push a task branch;
- silently widen the validated file scope;
- edit the selected task contract or GDD as part of implementation;
- treat non-`review_ready` ExecutionCrew output as applyable;
- hand off an uncommitted or unpushed candidate;
- claim that human Unity validation occurred;
- claim TaskGraph delivery or conformance;
- merge the task.

A wrong branch, unexpected remote movement, dirty checkout, changed task contract, candidate hash mismatch, path mismatch, TaskGraph failure, Issue event-chain problem, or resource conflict stops for reconciliation and remains visible in the durable Issue log.
