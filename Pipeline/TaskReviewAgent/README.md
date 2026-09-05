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
or `human_result`. The structured `process_one_synthetic_handoff()` API advances
at most one exact task and returns the appended event ID plus the semantic hash
of its evidence as the autonomous controller's `SyntheticEvidencePumpResult`;
the controller never parses CLI output to infer progress. The CLI preserves its
process-all behavior by looping that one-task API, re-reading each Issue
immediately before validation. After a verified transition it removes only that
task's exact Vincent routing comment and publishes an advisory local wake hint.
The launcher immediately re-reads the authoritative GitHub state; a missing or
malformed hint merely falls back to its normal wait.

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

If that exact additive undo was already published without a reset receipt and
unrelated private-rehearsal commits followed it, use the separate
`--recover-published-decomposition-undo` mode. It does not relax the ordinary
undo's exact-HEAD rule and never creates or pushes another commit. The recovery
binds the completed parent Issue to the reviewed plan and apply commit, proves
the immediate undo commit and untouched later history, refuses every child
consumption signal, then closes the stale parent Issue, removes its exact clean
manifest-bound checkout, and archives its active state. Applied and resumed
recovery require explicit repository, plan-ID, and undo-commit confirmations.

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
`autonomous_graph_run.py` remains the deterministic controller boundary over
`PollingOrchestrator`. Production composition is now provided by
`run_autonomous_graph.py` and the canonical `Start-AutonomousGraphRun.ps1`
launcher. The CLI uses the same scheduler factory as the polling entry point,
refreshes and rechecks source `main`, reads TaskGraph state in one bulk payload,
and derives managed Issue state plus durable reservations from one cached Issue
batch. Only the current scheduler's in-memory children count as active
assignments; a prior-process lease remains a reservation and is never adopted or
stolen.

`Start-GameTaskAgent.ps1` is the normal operator entry point into this
controller. A top-level explicit `-TaskId` with no scheduler `-RunId`
delegates here exactly once with `--max-workers 1` and a generated durable
run identity; a scheduler-spawned worker carrying a `-RunId` stays on the
direct `run_pipeline_agent.py` path and cannot recurse back into the
controller that started it; `-DirectManual` selects the conservative direct
worker deliberately. See `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md`.

`--target-task-id` is expanded transitively through each task's committed
decomposition children, minus `--exclude-task-id`, and that set is the
scheduler's admission allowlist. `depends_on` is deliberately not expanded:
an undelivered dependency leaves its dependent undispatchable rather than
pulling unrelated work into run scope.

Each run creates an immutable repository-bound manifest before scheduler or
provider work under:

```text
<checkout-root>/.task-review-agent/autonomous-runs/<repository-sha256>/<run-id>/
    manifest.json
    progress.json
    graph-complete.json
    events.jsonl
```

A resume may omit targets, exclusions, and capacity and load them from the exact
manifest. If any are supplied again, they must match. A valid existing
`graph-complete.json` returns success before source refresh, GitHub observation,
Docker, the architect, or a worker is invoked. Example private rehearsal run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-AutonomousGraphRun.ps1 `
  -RunId gauntlet-922 `
  -ConfirmRepository cathode26/NoSafeCircle-Homework-Rehearsal `
  -TargetTaskId NSC-922 `
  -ExcludeTaskId NSC-042 `
  -MaxWorkers 1 `
  -ExecutionProvider claude `
  -EnableSyntheticEvidence
```

`-EnableSyntheticEvidence` is opt-in and remains restricted to exact committed
private rehearsal tasks. It advances one relevant waiting Issue per controller
step with hash-bound automated evidence and never creates `human_result` or a
human PASS. NSC-042 is categorically excluded from this path.

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
An interrupted persisted `assigned` state is never reused. A replacement
controller first acquires the repository scheduler lock, appends an exact
`assignment_interrupted` retirement event for the stranded assignment, and then
starts a fresh provider conversation. Loading the state does not authorize a
provider call: normal architect invocation remains blocked, and the production
reconciliation entry point rejects unless its exact scheduler lock is acquired.
A second scheduler therefore cannot reconcile another live controller's
assignment. Claude supports caller-bound fresh and resumed UUIDs.
A fresh Codex pooled session deliberately fails before a paid call because Codex
assigns its UUID only after launch; an already-known Codex resume still passes
through the adapter's verified sandbox-policy guard and fails closed if that
guard is not available. The previous 12-attempt scheduler-fatal cap has been
removed; the independent per-poll admission-call cap remains an operator safety
bound.
<!-- autonomous-graph-controller:end -->

## Deterministic host-forced actions

When the durable downstream state permits exactly one action, the host executes
that action itself and the supervisor provider is never invoked. `last_usage` for
such a turn records zero input, output, and total tokens under the authority
`deterministic_host_single_action`, so an operator can tell a host action from a
paid one in the usage log.

Two conditions must both hold:

- `allowed_actions_for` narrowed the menu to exactly one action for the observed
  durable state, and
- the host can derive and validate every required argument for that action from
  durable state alone.

Actions with no arguments have always qualified. Two parameterized actions now
qualify as well, because their arguments were already durable:

| Action | Arguments | Durable source |
| --- | --- | --- |
| `run_authoritative_unity_test` | `test_platform`, `test_filter` | `downstream.authoritative_test_plan` (from `validation_plan_for`), minus platforms whose manifests are already in `downstream.receipt.validation_manifests` |
| `acquire_agent_lease` | `planned_approach`, `expected_validation` | Generated as fixed auditable text naming the task, phase, and committed validation plan |

The measured NSC-914 delivery run `scheduler-nsc-914-adac4ceeac204e5f` paid
17,808 input tokens for `acquire_agent_lease` and 18,746 for
`run_authoritative_unity_test`. In the second case the host had already computed
the exact platform and filter and pasted them into the prompt as a
"Host-authorized exact plan" before paying the provider to echo them back.

`planned_approach` and `expected_validation` are recorded rationale, not
decisions. The host has already established that the Issue is agent_ready and
that the lease is the only available action, so the text is generated
deterministically rather than bought. It is auditable: it names the task, the
phase, and the committed platform/filter pairs it was derived from.

### Fail closed, never fall back

Argument derivation is all-or-nothing. A derivable action whose durable state is
missing, malformed, or already satisfied raises `DownstreamPipelineError` rather
than returning to the provider, because falling through is exactly how an
inferred Unity filter or an invented lease rationale would re-enter the pipeline.
Refusals cover a missing or malformed `authoritative_test_plan`, a missing or
blank filter for the chosen platform, and a state where every required platform
already has durable evidence.

### What still costs a provider turn

Genuinely judgmental states are untouched. `create_delivery_review_proposal`
needs the reviewer's own summary, so the host does not manufacture it and that
turn still consults the pooled supervisor. The short-circuit also still depends
entirely on host narrowing: an unnarrowed menu always reaches the provider, and a
derivation is keyed to the exact action it was computed for so it can never be
applied to a different one.

Regressions: `Pipeline/TaskReviewAgent/tests/forced_action_arguments_smoke_test.py`.

## Durable supervisor session pool

`supervisor_session_pool.py` keeps one task-scoped Codex supervisor
conversation resumable across separate `codex_supervisor_turn.py` subprocesses:
every judgment turn of one worker, the worker returning at
`human_action_required`, and the later delivery-evidence or merge-closeout
worker for the same task. Pooling means persisting and safely resuming the
provider conversation identity; no Docker, Python, or CLI process stays alive.
Deterministic host-forced actions still never reach the provider and never
check a session out.

The owner is built on the shared AgentRuntime contracts rather than a second
protocol: `provider_sessions.py` names and proves the conversation,
`session_lifecycle.py` decides every budget and retirement, and the new
provider-neutral `Pipeline/AgentRuntime/durable_session_pool.py` records the
same idle/active/probation/quarantined/expired/retired state machine the
ExecutionCrew pool applies to crew roles.

### Compatibility and identity

A conversation is offered back only to a turn whose scope is exactly equal:

| Bound fact | Value |
| --- | --- |
| protocol version | `SUPERVISOR_SESSION_PROTOCOL_VERSION` (`1.0`) |
| role | `task_supervisor` |
| provider | `openai-codex` |
| model | the exact resolved supervisor model |
| reasoning effort | the exact resolved effort |
| repository identity | the source checkout's `origin` URL |
| resume control | SHA-256 of the exact operator-verified `codex exec resume` argv fragment |
| conversation store | `compose:<project>/codex-config`, the Docker Compose volume the session files live in |
| task | the exact `NSC-###` |

A different value for any of them cold-starts and retires the old record
explicitly (`session_incompatibility`); another task can never inherit the
conversation because the task ID is part of the key. A different repository is
a different pool file altogether. The conversation store is the compose
project the supervisor container runs under (`NSC_TASK_AGENT_COMPOSE_PROJECT`,
default `nosafecircle`): Codex keeps its session files in that project's
`codex-config` volume, so a launch under another project could never find the
thread and must start its own. The provider and the owner resolve the project
the same way, and a provider built for a different project than its owner is
refused before any turn.

The scheduler routes one supervisor model and effort per task and passes them
to every worker of that task; the downstream (delivery-evidence and
merge-closeout) worker now builds its supervisor from the routed effort as
well, so the task's conversation keeps one key from implementation through
closeout instead of cold-starting a second one at the phase boundary.

Codex assigns its thread UUID only after the first call, so a cold lease
carries no identity. The container reports the exact `thread.started`
identity the AgentRuntime adapter proved from the transcript as
`provider_session_confirmation`, and only that proof makes the conversation
poolable. A missing or malformed confirmation quarantines; a confirmation that
names a different thread than a resume asked for retires the conversation for
`identity_failure` and the decision from that turn is rejected. Exit code 0
proves nothing.

### Codex resume gate (explicit activation)

`codex exec resume` does not accept `--sandbox` (verified against Codex CLI
0.151.0 on the host and 0.149.0 in the `nosafecircle-codex-supervisor` image),
so the adapter refuses to resume unless an operator-verified argument that
reproduces the pinned `--sandbox danger-full-access` policy through an option
resume does accept is supplied. Warm pooling is therefore **off by default**.
With the gate off the worker constructs no owner at all: every turn is the
historical ephemeral turn with `--ephemeral`, no pool state is written, and
the worker records `warm_pooling_active: false` with the reason in its
`supervisor_session_pool` progress event, on every `supervisor_decision`
event, and in the worker result. A conversation an earlier activation left
behind is never resumed while the gate is off; it expires on its own, and an
owner constructed after re-activation retires it explicitly if it no longer
matches.

To activate it, export the exact control once, at the top of the process
tree, as a JSON array of argv strings, then launch as usual:

```powershell
$env:NSC_CODEX_RESUME_SANDBOX_ARGUMENT = '["-c","sandbox_mode=\"danger-full-access\""]'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-###
```

`-CodexResumeSandboxArgument '-c','sandbox_mode="danger-full-access"'` is the
equivalent parameter for an in-process call (`& .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 ...`
or `powershell.exe -Command "& ..."`); it cannot be passed through
`powershell.exe -File`, whose arguments are native tokens rather than
PowerShell array expressions. Either way the launcher validates the control
and keeps it in `NSC_CODEX_RESUME_SANDBOX_ARGUMENT`, which the architect
controller, every scheduler-spawned worker, and the direct worker read. The
control is deliberately never forwarded as a native command-line argument:
Windows PowerShell 5.1 does not escape embedded quotes for native executables,
so the JSON would arrive corrupted. The launcher reports `ACTIVE` only for an
`openai`-mode launch whose control passed validation.

The control is an allowlist, not a free argv fragment: `-c`/`--config` flag
and `sandbox...=value` pairs only. `--sandbox` is not accepted by resume,
`--last` selects a session by recency, `--all` widens session lookup beyond
the current working directory, `--ephemeral` discards the session files a
resume needs, the bypass flag is a wider policy, and working-directory,
approval, profile, model, or feature flags would widen what the resumed turn
may do beyond what the pinned start had. All of those, and bare session IDs,
are refused before any pipeline starts, by the launcher and again by the
worker.

The fragment above is the *candidate* the adapter's own tests use; it has not
been proven live by this repository. Before activating it, an operator must
run one verification in each container image that will resume Codex under it
-- `nosafecircle-codex-supervisor` for the supervisor, `round-robin-decompose`
for decomposition -- with that image's real credential volume, and confirm
all three facts:

1. `codex exec resume <uuid> -c sandbox_mode="danger-full-access" ...` is
   accepted under `--strict-config --ignore-user-config` from a *different*
   working directory than the one that started the thread;
2. the resumed turn reports the same sandbox policy as the start (the
   non-JSON `codex exec` banner prints `sandbox: danger-full-access`);
3. the resumed `--json` transcript contains exactly one `thread.started`
   event whose `thread_id` equals the resumed UUID.

If step 1 fails only because resume-by-UUID is filtered by working directory,
that is a finding to report, not a reason to add `--all` to the control: the
allowlist would have to be widened by a reviewed change. Until the
verification passes, leave the gate off. Nothing in this repository claims
warm pooling while it is off.

### Authority capsule

Every pooled turn's prompt is led by a fresh capsule that closes and revokes
the previous assignment in the conversation, names the current task, run,
worker, turn, phase, Issue state and state version, source HEAD and tree, and
checkout status, lists the current allowed actions and zero capabilities, and
states that earlier prompts, observations, paths, plans, and conclusions are
context only. A cold start states that the conversation holds no prior
authority. The deterministic observation the prompt was rendered from is the
one the capsule names, because the pipelines bind it immediately before the
turn.

### Lifetime and retirement

One paid judgment turn is one completed cycle of the committed lifecycle
policy's decision-call class. The conversation retires after 100 completed
turns, after two consecutive provider/output failures (a first counted failure
parks it on probation and the next turn is its one deliberate retry), after an
identity failure or incompatibility, or when a known context-window
utilization reaches 70%. Utilization is known only when the operator states
the model's context window explicitly (`-SupervisorContextWindowTokens` or
`NSC_TASK_SUPERVISOR_CONTEXT_WINDOW_TOKENS`); it is derived from the exact
input token count Codex reported for the turn and is otherwise unknown. A
returned conversation expires after 7 idle days and nothing survives 14 days
from creation. No bound ever touches an active assignment.

### Crash and concurrency behavior

Pool state lives outside the repository at
`<checkout-root>/.task-review-agent/session-pools/<repository-sha256>/task-supervisor/`
(`state.json`, an append-only `events.jsonl` that never carries prompt text,
and one `liveness/<TASK-ID>.alive` lock per task). Transitions are atomic,
verified writes under a short cross-process lock that is never held while
Docker runs. The active lease is persisted before the provider is called and
settled from the container's proof afterwards. An identical terminal
settlement replay is a no-op; a different one fails closed.

Exactly one active lease exists per task. The owner holds the task's liveness
lock for the whole worker process; a second live owner for the same task fails
closed at construction. A stranded lease -- an owner that died mid-turn -- is
reconciled only by the owner that now holds that exact lock on the same host
and platform, and only by retiring the conversation as
`interrupted_assignment`; a lease recorded on another host cannot be proven
stranded and fails closed. Timeouts, transport failures, and unparseable
responses retire the conversation as uncertain. Nothing uncertain is ever
resumed.

Regressions: `Pipeline/AgentRuntime/tests/durable_session_pool_smoke_test.py`,
`Pipeline/TaskReviewAgent/tests/supervisor_session_pool_smoke_test.py`, and
`Pipeline/TaskReviewAgent/tests/supervisor_pool_launcher_smoke_test.py`.

## Durable decomposition author and reviewer sessions

`decomposition_session_pool.py` is the host owner for role-scoped D1B
conversations: `task_decomposer` and `decomposition_reviewer`, one lease per
`<provider>:<role>` pair the circuit can reach. It is built on the same
provider-neutral primitive as the supervisor pool and shares nothing with the
architect, supervisor, or ExecutionCrew pools. The scheduler enables it by
passing `--enable-decomposition-session-pool` to
`host_decomposition_launcher.py`; a direct launch stays ephemeral. The
launcher mints a host-owned run ID, reserves the reachable leases, mounts the
bundle read-only into `round-robin-decompose`, pins the reserved provider
models into the container environment so the round's route cannot silently
differ, and settles every lease from the run's artifacts after Docker returns.
Uninvoked leases are cancelled without charge; a pool failure after a valid
result writes `pool_degraded.json` beside the run and leaves the review-ready
handoff untouched, while the still-active leases are reclaimed as stranded by
the next owner and never reused.

Pool state lives at
`<checkout-root>/.task-review-agent/session-pools/<repository-sha256>/decomposition/`
with the same atomic writes, short cross-process lock, append-only prompt-free
journal, and per-run liveness lock as the supervisor pool. Every lease binds
its provider's conversation store, `compose:<project>/<provider>-config`,
from the launcher's exact `--compose-project`, because the round-robin
container finds a session only in that project's configuration volume; a
launch under another project reserves other conversations. Codex
conversations are reserved only under the verified resume control described
above; Claude conversations always pool when the scheduler enables the pool.
See
`Pipeline/TaskDecomposition/README.md` for the container-side contract,
evidence binding, and lifetime.

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
