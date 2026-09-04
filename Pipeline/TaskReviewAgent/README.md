# TaskReviewAgent — durable Issue workflow to human Unity work

TaskReviewAgent is the goal-oriented OpenAI supervisor around the existing No Safe Circle pipeline.

The workflow is designed so a task can survive interruptions, model changes, browser closure, and human delay without requiring a task-specific resume command.

```text
generic agent starts
        ↓
resume a valid agent-ready Issue before selecting new work
        ↓
acquire the Issue lease
        ↓
create/resume canonical checkout and task branch
        ↓
implement candidate
        ↓
refresh current main and apply the candidate on top of it
        ↓
test, commit, and push the exact integrated candidate
        ↓
write the branch, commit, summary, and Unity checklist into the Issue
        ↓
Issue becomes human_action_required
        ↓
Vincent posts PASS or FAIL and adds nsc-state:agent-ready
        ↓
GitHub Action validates the result and changes the phase
        ↓
any later generic agent resumes the same Issue
```

After Vincent actually completes the Issue checklist and chooses PASS,
`pass_and_resume_task.py` is the standard combined PASS/label/wait/resume entry
point. It binds the PASS to the exact clean handoff commit and waits for the
GitHub workflow state and hashed event count to agree before it launches the
agent. See `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md` for the command.

## Durable Issue controller

The task Issue now carries three operational layers.

### Visible dashboard

The top of the Issue says:

```text
Current state
Current owner
Current phase
Branch
Commit
Checkout
Next action
```

This is the human recovery view when returning after a distraction.

### Managed state block

A hidden `nsc-workflow-state` JSON block records:

- exact task ID and task-contract SHA-256;
- state and phase;
- human or agent ownership;
- worker and lease identities;
- branch, commit, and checkout;
- human handoff commit and PASS/FAIL result;
- state version and final event ID.

Humans do not edit this block.

### Append-only event comments

Every transition appends a readable comment with a hidden `nsc-workflow-event` object. Events carry a sequence, prior event ID, state/phase transition, actor, timestamp, task-contract hash, and SHA-256 event identity.

The next agent validates the entire chain. Missing, edited, duplicated, forked, reordered, or stale events fail closed.

## States and phases

Main states:

| State | Next owner |
| --- | --- |
| `agent_ready` | any generic agent may resume |
| `agent_working` | the recorded worker owns the lease |
| `human_action_required` | Vincent owns the recorded Unity/runtime checklist |
| `blocked` | a human decision or external prerequisite is required |
| `complete` | no further workflow action |

State labels mirror the managed state:

```text
nsc-state:agent-ready
nsc-state:agent-working
nsc-state:human-action
nsc-state:blocked
nsc-state:complete
```

A human applying `nsc-state:agent-ready` in the GitHub UI is label-ahead-of-body
until the state Action converges the body. That bounded window
(`PENDING_TRANSITION_MAX_AGE_SECONDS`) is dated by GitHub's own `labeled` event for
the target label (`gh api repos/<repo>/issues/<n>/events`), read only for a legal,
convergible label-ahead Issue and cached per Issue inside the scheduler's
plan-scoped snapshot; a comment, body edit, assignment, or any other Issue
activity refreshes `updated_at` but never renews the window. A transition whose
label event cannot be proven (no event support, no matching event, or a
malformed id/timestamp) is ordinary invalid managed state and fails closed.

The phase tells the next agent what work to perform:

```text
implementation
repair
unity_runtime_validation
delivery_evidence
merge_closeout
decomposition
decomposition_apply_authorization
decomposition_apply
```

A human PASS moves the Issue to `agent_ready / delivery_evidence`. A human FAIL moves it to `agent_ready / repair`.

An exact-commit human PASS also supplies the delivery authorization for that
unchanged commit. After authoritative Unity tests pass and the hash-bound
delivery proposal is generated, the controller proceeds to `merge_closeout`
without asking Vincent for a second approval. This automatic continuation is
allowed only while the canonical checkout is clean and still points to the
human-tested commit. Any new or uncommitted repository change stops for human
reconciliation instead of reusing the earlier PASS.

If `origin/main` advances after that PASS, the controller merges current main
into the task branch and pushes the resulting merge commit. Every such merge,
including one classified as automation-only, creates a new exact-commit human
handoff. Vincent must test and approve that integrated commit. Once it passes,
the unchanged integrated commit proceeds through delivery and merge closeout
without a second approval.

These are intentionally two independent current-main boundaries. Before the
first human handoff, the candidate is validated against current `origin/main`,
the task branch is advanced to that exact base, and the candidate is committed
and tested there. After the human PASS, downstream delivery fetches
`origin/main` again. A no-op second synchronization preserves the exact tested
commit and continues automatically; a synchronization that creates a new
commit invalidates the older PASS and returns the integrated commit for another
human test. A merge conflict is a repair problem at the task checkout, never
permission to overwrite either side.

## Decomposition handoff and application

The software architect may include eligible `work_type: decomposition`
candidates in the same ordered admission batch as implementation work. It must
record a disposition for every candidate/work-type pair and may admit at most
one work type per task up to current local capacity. Decomposition does not wait
for the implementation portfolio to become empty. Each selected parent acquires
the ordinary durable Issue/task claim, while the Docker
round-robin service receives a physically read-only repository and writes only
to the external no-overwrite output root.

Decomposition uses the same canonical standalone task checkout and
deterministic task branch as implementation work. The scheduler may therefore
fast-forward its separate clean controller `main` between polls without moving
the repository beneath an active decomposition provider. A wrong, dirty,
stale, or differently bound `C:\NSC\NSC\<TASK-ID>` checkout stops visibly and
is never reset or replaced.

Validated resumable work, including an approved decomposition apply, appears
first without hiding fresh implementation or decomposition work from the same
architect call. A safe resume is therefore not starved behind newly eligible
tasks, while a deferred resume cannot consume another paid call before fresh
work is considered. One response may launch multiple workers up to local
capacity. Before every launch, the scheduler refreshes source main, obtains a
new Issue snapshot and consistency budget, reruns Stage 2, and rechecks current
reservations. A withdrawn candidate is skipped; a global observation failure or
moved source HEAD discards the remaining batch.

When a committed validation policy contains a decomposition-child template,
only a D1C-generated child whose provenance names that exact parent and exact
pre-decomposition parent contract hash may inherit its platform/filter pair.
The resulting plan remains bound to the child's own exact contract hash. This
lets reviewed synthetic children run the same named Edit Mode test without
repository discovery or a guessed filter.

The disposable gauntlet uses
`Pipeline/TaskReviewAgent/synthetic_gauntlet_approver.py` as a deliberately
narrow operator boundary. It refuses production and public repositories,
ignores NSC-042, recognizes only the exact gauntlet lineage, runs the committed
Edit Mode filter before advancing an implementation handoff, and verifies the
exact two-child resource partition before decomposition application. It accepts only
the exact private `cathode26/NoSafeCircle-Homework-Rehearsal` repository; a
private lookalike is not eligible. Successful checks append agent-owned,
hash-bound automated-validation or automated-decomposition evidence through the
ordinary Issue workflow service. They never create a human PASS, human approval,
or `human_result`. One invocation serially processes every currently eligible
synthetic Issue, re-reading each Issue immediately before validation. After a
verified transition it removes only that task's exact Vincent routing comment
and publishes an advisory local wake hint. The launcher immediately re-reads
the authoritative GitHub state; a missing or malformed hint merely falls back
to its normal wait.

A `review_ready` plan is published as an exact `plan_id` handoff in
`human_action_required / decomposition_apply_authorization`. It is still
review-only. Vincent may approve that exact plan with:

```powershell
python Pipeline\TaskReviewAgent\pass_and_resume_task.py NSC-### --source . --checkout-root C:\NSC\NSC --execution-provider claude --approve-decomposition --apply
```

The helper reads the plan identity from the durable Issue, posts an exact-plan
APPROVE, waits for GitHub to enter `agent_ready / decomposition_apply`, and
starts the distinct host application boundary. Application is serialized by a
global D1C claim, requires the authorized source to remain exact current main,
uses the network-free `apply_graph_delta()` transaction, pushes the exact
resulting commit, and records completion. If main moved while the plan waited,
the plan is not applied; its lease is released to fresh decomposition so child
IDs and graph rewrites are replanned against the new graph.

## Agent lease and resource conflict checks

Before checkout work, the agent:

1. validates current Git and TaskGraph state;
2. checks every declared dependency;
3. inspects managed open Issues;
4. blocks tasks whose exclusive resources overlap another `agent_working`, `human_action_required`, or `blocked` Issue;
5. creates or initializes the task Issue when needed;
6. appends an `agent_lease_acquired` event;
7. changes the Issue to `agent_working`;
8. verifies the resulting Issue state and event chain.

If two agents race from the same state, duplicate sequence/previous-event relationships produce an invalid chain instead of silently granting both agents authority.

## Canonical checkout

After a valid Issue lease, the agent may create or resume only:

```text
C:\NSC\NSC\<TASK-ID>
```

Checkout preparation still enforces:

- clean controller with `HEAD == origin/main`;
- approved GitHub remote;
- standalone clone rather than a Windows worktree;
- deterministic task branch;
- exact source commit/tree and task-contract hash;
- TaskGraph validation in the clone;
- clean checkout;
- external checkout identity manifest.

A wrong or dirty existing checkout becomes a human conflict. It is never reset, deleted, overwritten, or bypassed with a differently named directory.

Before every live scheduling poll, the controller fetches `origin/main` and
fast-forwards attached clean `main` when possible. Dirt or divergence stops new
admissions; the scheduler never rebases or resets the controller. This keeps
later task admissions and both task-branch synchronization boundaries based on
the exact mainline produced by earlier completed workers.

If a D1C commit was created locally and its push genuinely failed while
`origin/main` remained at the approved parent, the scheduler recognizes only
the exact canonical commit for that approved `plan_id`. During recovery it
excludes every other task and resumes only that decomposition application, which
retries the identical ordinary push without reapplying the graph. Arbitrary
local-ahead history, a moved remote, an ambiguous D1C commit, or an unprovable
Issue/plan binding remains a hard stop; the controller is never reset, rebased,
or force-pushed.

Durable reservation discovery and Stage-2 planning share one plan-scoped
read-only Issue/comment cache. Each worker launch begins a fresh capacity pass
and therefore a fresh GitHub snapshot, while one admission decision avoids a
second full Issue listing and contradictory within-pass observations.

Production Claude ExecutionCrew runs use a repository-scoped pool of four
role-isolated provider conversations per active task: Contract Locality Auditor,
Implementer, Test Author, and Validator. The host reserves those sessions only
after the exact task checkout, routed model, worker slot, source commit, and
external canonical checkout manifest are known. The polling scheduler alone
enables pooling; direct/manual launchers remain ephemeral even when a model is
selected. The host passes one strict lease bundle,
the exact run ID, repository identity, and the read-only manifest into Docker.
The manifest's byte hash is the cross-OS checkout identity, so a Windows path is
never compared directly with `/workspace`.

Pool state is outside the repository under
`<checkout-root>/.task-review-agent/session-pools/<repository-sha256>/` and is
protected by a short cross-process lock. Up to ten tasks may hold four leases
each. Active leases are never stolen after a restart; exact terminal role
evidence settles once, explicit uninvoked roles return without consuming worker
budget, and invalid evidence withdraws the session from reuse. A pool-state
persistence failure after a valid ExecutionCrew result writes pool-degraded
evidence but does not invalidate the candidate. Codex and manual ExecutionCrew
runs remain ephemeral unless and until their exact resume sandbox contract is
available to this host owner.

Scheduler-launched workers publish an identity-bound `run_result.json` beside
their `run.json` as their final durable write. The scheduler derives that path
itself and accepts a terminal result only when the run ID, worker ID, task,
source commit, task-contract hash, process ID, timestamps, status, and observed
exit code agree. Missing, stale, malformed, or contradictory results fail
closed even when the operating-system exit code is zero.

Exit `0` is reserved for `human_action_required` or `completed`; exit `3`
reports a deterministic `blocked` state, and exit `4` reports
`no_safe_work`. Blocked and idle workers free local capacity without being
counted as completed work or stopping other safe admissions. Exit `2` and all
unknown operating-system codes are fatal and trigger the bounded drain of
already-running children.

## Human handoff

The downstream implementation stage will call `publish_human_handoff` only after it has committed and pushed the branch. The Issue comment records:

- branch and exact commit to test;
- canonical checkout path;
- what was implemented;
- checks already completed;
- numbered Unity steps;
- exact expected result;
- a PASS/FAIL comment template.

The Issue then becomes:

```text
human_action_required / unity_runtime_validation
```

On the real production composition, that verified transition also posts one routing comment to the
open authorized `NSC-Vincent` Issue. The notification points back to the source task Issue and exact
commit/checkout; it does not duplicate the Unity checklist or become workflow/evidence authority.
Vincent records PASS/FAIL on the source Issue. The canonical approval helper
deletes the one task-, source-Issue-, and commit-bound `NSC-Vincent`
notification after GitHub confirms the human-result transition. If the helper
is not used, Vincent may still delete that routing comment manually. An exact
handoff retry is notification-idempotent and does not repeat the source Issue
transition.

Vincent posts a result such as:

```text
## Human validation result

Result: FAIL
Tested commit: `0123456789abcdef0123456789abcdef01234567`

Failed step:
...

Reproduction:
...

Expected:
...

Observed:
...
```

Then Vincent adds:

```text
nsc-state:agent-ready
```

`.github/workflows/nsc-issue-workflow.yml` validates that the Issue is actually human-owned, finds the latest result, requires the exact handoff commit, appends the human workflow event, updates the dashboard/state block, and selects `repair` or `delivery_evidence`.

No task-specific PowerShell resume command is required.

## Generic-agent queue

Before selecting fresh TaskGraph work, a generic agent should run:

```powershell
python Pipeline/TaskReviewAgent/issue_queue.py --source .
```

Only Issues whose managed state, state label, and complete event chain all prove `agent_ready` are returned. Generic selection must resume these Issues before choosing a new task.

## Undoing an unconsumed decomposition

`reset_task.py --undo-decomposition` is the coordinated Stage D1C inverse. A
dry run binds one exact `graph_delta.json`, current clean `main`, the exact D1C
commit, and every child-consumption signal. Applied mode delegates the sole
inverse algorithm to `TaskGraph/undo_graph_delta.py`, creates one additive
commit, publishes it by ordinary fast-forward, and archives only the parent's
active controller state. It never resets, rebases, force-pushes, or deletes
child work.

If publication stops after commit creation, `--resume-report` reuses that exact
commit. Before any publication or state archive it requires clean `main`, local
`HEAD` at the receipt's undo commit, and `origin/main` at either the recorded D1C
commit or the undo commit. See
`Docs/AI-Pipeline/FRESH_TASK_RESET_RUNBOOK.md` for the guarded commands and full
refusal conditions.

## Current real command

For an eligible explicit task, the deterministic mode can initialize/acquire the Issue lease and prepare the checkout in one bounded stage:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-### -Mode checkout-real -WorkerId task-review-agent-vincent
```

The OpenAI-driven equivalent is:

```powershell
python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt
$env:OPENAI_API_KEY = "..."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-### -Mode openai-checkout-real -WorkerId task-review-agent-vincent
```

The OpenAI agent receives only:

```text
observe_goal_state
acquire_agent_lease
prepare_task_checkout
```

It cannot yet plan write paths, run ExecutionCrew, edit gameplay/tests, commit, push, publish a human handoff, run Unity, merge, package evidence, or claim conformance.

## Current NSC-050 result

`NSC-050` still stops before Issue/checkout changes because its current declared dependency states are:

```text
NSC-020 = not_delivered
NSC-004 = needs_testing
```

The workflow state and checkout boundaries are tested using deterministic in-memory Issues and temporary synthetic Git repositories instead of creating an inappropriate live NSC-050 task.

## Autonomous graph controller integration status

<!-- autonomous-graph-controller:start -->
`autonomous_graph_run.py` is currently a deterministic, dependency-injected
controller boundary over `PollingOrchestrator`; it is not yet a production
launcher. The production coherent snapshotter, exact manifest/receipt path
selection, structured synthetic-evidence pump adapter, command-line entry point,
and launcher wiring remain intentionally unwired. No caller should approximate
those authority-bearing adapters from mutable or partial observations.

The production polling entry point now decorates its existing architect callable
with a durable provider-session lifecycle owner; it does not replace or restart
`PollingOrchestrator`, so active worker assignments survive architect rotation.
One paid, successfully confirmed portfolio call is one completed
`admission_cycle`, including a valid all-WAIT batch. Cached decisions, capacity
waits, Issue waits, worker waits, and every poll that makes no provider call cost
zero. Provider/output failures do not increase the completed-cycle count. The
shared AgentRuntime policy retires after 100 completed architect cycles, two
consecutive provider/output failures, an exact incompatibility or identity
failure, or explicit context-window evidence at its threshold. Latency retirement
stays disabled until a caller can supply an exact comparison key and baseline.

Current state and append-only transition telemetry live below
`Pipeline/ArchitectureReview/outputs/orchestrator/architect-sessions/<provider>/<role>`.
The durable binding also records the exact provider, model, reasoning effort,
protocol, and capability set; a restart with any different value retires the old
session before the next paid call instead of silently resuming it.
An interrupted persisted `assigned` state blocks reuse pending explicit
reconciliation. Claude supports caller-bound fresh and resumed UUIDs. A fresh
Codex pooled session deliberately fails before a paid call because Codex assigns
its UUID only after launch; an already-known Codex resume still passes through
the adapter's verified sandbox-policy guard and fails closed if that guard is not
available. The previous 12-attempt scheduler-fatal cap has been removed; the
independent per-poll admission-call cap remains an operator safety bound.
<!-- autonomous-graph-controller:end -->

## Validation

```powershell
python Pipeline/TaskReviewAgent/tests/task_review_agent_smoke_test.py
python Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py
python Pipeline/TaskReviewAgent/tests/real_checkout_smoke_test.py
python Pipeline/TaskReviewAgent/run_agent.py --task-id NSC-050 --mode observe-real --source .
python -m compileall -q Pipeline/TaskReviewAgent
```

The Issue workflow tests prove:

- state and event round trips;
- hash-chain verification;
- agent lease creation and later-agent resume;
- committed human handoff state;
- exact-commit PASS/FAIL enforcement;
- FAIL → repair and PASS → delivery-evidence phase selection;
- agent-ready queue discovery;
- exclusive-resource conflict rejection;
- tampered history rejection.

## Next boundary

The next implementation slice connects bounded repository read/search and deterministic implementation/test path planning. After that, real ExecutionCrew can generate the candidate, and the later application stage can commit and push before calling the already-defined human handoff transition.

Patch application and Unity execution remain separate authority boundaries.
