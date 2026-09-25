# Conversation-operated task tools

## Graph preparation gate

Before `run-graph`, invoke `graph-preflight` with the **same** Source, checkout
root, targets, capacity, worker config, provider settings, human-review settings,
and spend authorization intended for that run. It persists a plan and a binding
to the exact Source commit, policy and worker-config bytes. It starts no workers.
`run-graph` refuses a missing or stale binding; after Source advances or any of
those settings changes, preflight again. A bounded run preserves the binding
across ordinary handoffs so a restart does not quietly discard the preparation.

The viewer's display scope is independent of execution targets. Showing every
contract does not authorize every task to run, and a code commit is not TaskGraph
completion evidence. Keep real game visual candidates at Vincent's explicit
review gate. `--capacity 3` is three worker slots, not a promise of three
persistent agents or a mixed-provider scheduler; configure and verify actual
provider assignments separately before starting workers.

For the operating role, read
[Assistant Software Architect operating guide](../../Docs/AI-Pipeline/ASSISTANT_SOFTWARE_ARCHITECT.md).
For a short handoff, read [CURRENT.md](CURRENT.md). Historical test details are in
`STATUS.md`.

Vincent talks to the assistant to select work, start or stop workers, request
changes, and approve a tested result. The visualizer displays the same task
records. It does not start work or grant approval.

Before creating or revising a game task, read [Game Task Lessons Learned](../../Docs/AI-Pipeline/GAME_TASK_LESSONS_LEARNED.md). Keep new visual-bug lessons there so the next task benefits from previous investigations.

## Available now

From the repository root, `python -m Pipeline.AssistantControl.inspect_project`
returns JSON with the checkout, branch, commit, local edits, and committed task
definitions. Add `--task NSC-042` for its complete contract. `--source` can name
another checkout. These commands do not start providers, contact GitHub, refresh
the Git index, or modify files. A dirty Unity project remains inspectable.

The inventory does **not** claim tasks are ready to run or delivered. It reports
exact file conflicts for declared scene/file resources, including rename sources.
Worker liveness and dependency evidence are available through the separate
commands below.

`python -m Pipeline.AssistantControl dependencies NSC-042` separately reads the
existing TaskGraph conformance evaluator at one committed HEAD. It reports the
task's evidence and each dependency's evidence, rather than inferring delivery
from a green viewer node or an Issue label. This is not permission to execute:
resource ownership, worker capacity and scope still need to be checked.

`python -m Pipeline.AssistantControl readiness NSC-042` performs those remaining
checks without reserving capacity or starting anything. It reports a compact list
of blockers covering dependency evidence, owned checkout and scope state, worker
capacity, resource reservations, and conflicting local Source edits. A ready
result still grants no execution authority; an explicit `reserve` and authorized
worker launch remain separate actions.

The common interface is `python -m Pipeline.AssistantControl`. Its `status`
command is read-only. `prepare` accepts a task ID and a required `--source-commit`
copied from inspection, plus global `--source` and `--checkout-root` arguments.
It creates a standalone clone under `<checkout-root>/<TASK-ID>` and records its
starting commit outside Source. It never starts a worker or copies uncommitted
changes. `checkout <TASK-ID>` reports the current branch, commit and edits.
These are assistant-facing commands; Vincent does not need to paste them.

Preparation is idempotent: reopening an owned checkout preserves worker edits.
An existing unowned folder is refused, never overwritten. Interrupted staging
is preserved for inspection; publication completed before its receipt can be
recovered only if the checkout still matches the exact clean starting commit.
Preparation alone neither admits nor launches work; a prepared project is not
reported as running.

`refresh-prepared TASK --source-commit SHA` updates only a clean, never-started
owned checkout to the inspected Source commit. It refuses work or admission
history, clears the previous scope, and retains preparation history. Source's
working edits are not copied. A task that has actually run uses the candidate
revision/synchronization workflow instead.

The `viewer` subcommand serves the existing Gauntlet graph on localhost (port
8813 by default). It requires `--checkout-root`. It starts no workers, and all
POST/PUT/PATCH/DELETE requests are refused. The task panel shows each owned
checkout's current commit and folder. Broken task records remain visible as
blocked. Verified candidates show human review, approval pending integration,
or requested changes. Approval alone never means locally accepted. Worker and
launch records supply task status, including exact process-identity checks.
When any candidate needs Vincent's test, the page headline changes to
`🐴 Vincent needed` and lists the waiting task IDs.
The viewer has been HTTP-tested and its conversation-control idle state checked
in a browser. It does not replace or stop an
already running viewer.

For the current graph team, serve port 8828 from the canonical Source and the
**same checkout root used by the live workers**:

```powershell
python -m Pipeline.AssistantControl --source C:\NSC\NSC\NoSafeCircle --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts viewer --port 8828
```

The viewer reads worker, checkout and candidate records from that root's
`.assistant-control` directory. A copied or isolated read-only viewer root can
show every task contract while reporting zero workers; refreshing the browser
does not make that copy follow live work. Confirm the page's Project Checkout
path and compare a suspect task with `worker-status` against the live root
before concluding that Graph Sol has stopped.

Viewer builds with the held-task overlay read
`<checkout-root>/.assistant-control/held-task-ids.json`, for example:

```json
{"schema_version":"assistant-viewer-held-tasks/v1","task_ids":["NSC-044"]}
```

Those IDs display as **Outside Current Run** without changing task contracts
or worker records. The file is a display annotation, not an execution hold;
Graph Sol must still exclude held tasks during selection as described in the
[graph team startup guide](../../Docs/AI-Pipeline/GRAPH_TEAM_STARTUP.md).

`review` records Vincent's explicit approve/reject message and exact tested
commit; a changed or dirty candidate cannot reuse that approval. `integrate`
requires an approved registered candidate, the expected Source commit, and the
target branch. It performs a local fast-forward only, never pushes, and refuses
to overwrite local edits. If Source has diverged, the candidate must be updated
and reviewed again. Rejection keeps the task checkout and feedback. A crash
after Git finishes but before the integration record is saved is recoverable.

GitHub publication remains a separate explicit boundary. `publish-approved TASK
--candidate-commit SHA [--base-branch main]` accepts only Vincent's exact human
approval; synthetic Gauntlet approval is insufficient. It pushes that literal
commit to the recorded `assistant/TASK` branch with an exact remote-head lease,
then creates or reuses the sole matching pull request. Source `origin` is the
only repository authority, and `--repo owner/name` is only a matching assertion.
It never uses Issues, integrates Source, pushes the base branch, or merges.

`inspect-ci TASK --candidate-commit SHA [--base-branch main]` verifies the
remote task branch and pull-request head still equal that approved commit before
classifying GitHub's check rollup. Empty, ambiguous, and unknown checks remain
pending. Both commands retain a hash-chained, atomic receipt at
`.assistant-control/publications/TASK.json`; interrupted branch or PR operations
must reconcile their exact remote result before another mutation.

`sync-candidate TASK --candidate-commit SHA --source-commit SHA` handles a clean
merge when Source advanced after this candidate was created. An unreviewed
`awaiting_human` candidate may be synchronized before Vincent's first test, and
an exactly approved candidate may be synchronized before integration. It
merges only the inspected committed Source version in staging, verifies Git's
merge tree and original task paths, then fast-forwards the owned task checkout.
Source's working files stay untouched. The original candidate and approval are
retained as history; the new commit is marked mechanically synchronized and must
be tested and explicitly approved again. It has no new crew review. Conflicts
retain staging and leave the original task checkout unchanged. An interrupted
publication can be recovered by repeating the exact original command.

When an exact crew candidate failed only because AssistantControl's committed
validation or Unity-materialization host was defective, use
`retry-candidate-validation TASK --candidate-commit SHA
--failed-validation-sha256 SHA256 --host-fix-commit SHA`, followed by the exact
`sync-candidate` command it authorizes. The recovery binds the retained failure,
original crew receipt and scope, unchanged task contract, clean owned checkout,
and one exact descendant Source commit containing the host fix. It grants no
approval. The synchronized candidate must pass materialization and validation
again, then still enters Vincent's visual review gate. A changed contract,
different failure, later Source advance, active reservation, malformed marker,
or non-crew candidate is refused without changing the retained failure.

Rejecting a synchronized candidate now preserves that merged version as the next
worker's base. A fresh scoped crew receives the exact rejection notes through
`revision_feedback_file`; it does not replay the old candidate patch or inherit
old scope/provider settings. Its result must bind the saved feedback bytes before
candidate registration. Every crew run keeps its own commit receipt, and observing
an already registered result preserves Vincent's existing decision.

Fresh-feedback execution requires a checkout with the updated ExecutionCrew
runtime. Older prepared checkouts do not understand the new CLI option; they have
not been silently edited or upgraded. Repeated clean synchronizations retain each
prior candidate and require approval again. Replaying an old completed operation
does not roll back newer work. Merge conflicts remain retained for inspection
rather than auto-resolved.

`candidate TASK --run-id CREW_RUN --config FILE` verifies an existing crew receipt
and commits it for human review. Recovery after commit-before-registration uses
a disposable base clone and real bridge/committer checks. This passed fixture
artifact integration tests, not a paid-provider run. Other gate tests install
fixture candidate records explicitly. Neither fixture grants real human
approval; the assistant must never invent Vincent's test result to call `review`.

For a Door Prototype result, `materialize-candidate TASK --candidate-commit SHA`
runs `DoorPrototypeSceneBuilder.Build` in that owned checkout, accepts only the
Unity-generated paths registered by the task scope, commits those exact outputs,
and runs the task's committed Unity tests against the resulting clean commit. It
launches no model and grants no approval. A failing test is retained as feedback
for another crew. The failed commit cannot be approved; `revise` converts its
exact validation error into a fresh-feedback worker baseline. A passing result
still needs Vincent's visual inspection.

`post-crew TASK --run-id CREW_RUN --config FILE [--unity-executable PATH]` is the
one bounded command for the Windows orchestrator to use right after a crew run
ends. It calls the existing `candidate` step. When the task's scope registers a
Unity-serialized DoorPrototype output **and the candidate actually edits that
output's builder**, it calls the existing `materialize-candidate` step. A task
may reserve a scene without changing its builder; that code-only candidate goes
directly to committed task validation without rebuilding the scene. It adds no new Git, scope,
receipt or Unity-builder logic of its own. It returns one compact
JSON result: task ID, checkout path, the crew's original candidate commit, the
materialized candidate commit (`null` when no Unity builder applies), the
generated paths, the Unity log path, focused test results, `status:
awaiting_human`, and exact visual reproduction instructions. If Unity cannot be
resolved before launch, it retains the crew-reviewed candidate untouched and
reports `status: NEEDS_MATERIALIZATION` with the exact error and
`materialize-candidate` command to rerun once Unity is available — this is never
treated as a source defect. A failure after materialization starts is retained
as `status: materialization_failed` for inspection and is never shown as ready
for human review. If the focused Unity tests fail, it reports `status: validation_failed`
with the failure text and the exact `revise` command; it never calls `revise`
itself. Re-running the same task/run-id after a crash recovers the same
candidate or materialization outcome instead of creating a duplicate commit or
relaunching Unity on an already-retained failure. It never approves,
integrates, pushes, publishes, or starts another crew.

For the specific NSC-032 failure where Unity imported the already committed
`Scripts/Enemies` folder and created its missing `Enemies.meta`, use the explicit
`recover-nsc032-materialization` command with the exact original candidate and
SHA-256 of the retained failure journal. It requires that journal, settled
worker capacity, the original candidate at checkout HEAD, and no unrelated
untracked or non-Unity edits. It copies every dirty Unity file and the failed
record/journal into a no-overwrite archive under `.assistant-control`, restores
the original clean candidate, and marks it `needs_materialization`. Inspect
the returned archive, then rerun `materialize-candidate` for that same commit.
The builder now verifies that exact Unity folder meta against the committed
Enemies folder, preserves an evidence copy, and includes it in the materialized
candidate commit. Keeping the folder meta committed prevents the following
Unity test run from regenerating an untracked file. Other untracked paths still
stop materialization; the materialized candidate needs its own review.
If materialization commits an exact clean candidate but the committed
authoritative validation policy is missing or stale, the candidate remains
`awaiting_human` with `automated_unity_validation: not_run`. No focused test
pass is claimed. A real focused test failure still produces `validation_failed`.
For the already retained NSC-032 missing-policy misclassification, use
`recover-nsc032-missing-validation-policy` with the exact original and
materialized commits and the failed journal's SHA-256. The recovery preserves
the failed journal bytes, verifies the clean commit and receipt, and changes
only the task's journal and review record; it runs no Unity or provider.
If a completed recovery reports `checkout_clean: true` but Windows Git still
shows modified tracked Unity files, use `refresh-nsc032-recovered-index` with
that same candidate and failed-journal SHA-256 before materialization. It
binds to the exact recovery archive, checks each remaining Unity file's
normalized Git blob against candidate HEAD, then refreshes index stat
entries without staging content. It refuses any real edit or any remaining
porcelain status. New recoveries perform this check before returning clean.

For a code-only candidate with no committed authoritative validation policy,
or a policy whose exact task-contract hash is stale, `post-crew` keeps the
authenticated clean candidate at `awaiting_human`. Its result says
`automated_unity_validation: not_run`, lists no focused test results, and names
the policy gap for Vincent's review. It does not claim a test pass or grant
automated approval. A `validation_failed` record caused solely by one of these
exact policy errors can be recovered by rerunning `post-crew` with the same
task, run ID, and config after the host fix; the command rechecks the retained
candidate identity and does not create another candidate commit. Real test
failures remain `validation_failed` and still require a revised candidate.

`python -m Pipeline.AssistantControl --source SOURCE --checkout-root ROOT
register-restored-candidate TASK --base-commit SHA --candidate-commit SHA --candidate-tree SHA
--task-contract-sha256 SHA --changed-paths FILE --evidence FILE
--reference-provenance FILE` registers a committed assistant-restored Unity
candidate for Vincent's review. The owned checkout must be clean, on its recorded
branch, based exactly on the pinned commit, and have no active reservation or
unsettled worker. The supplied changed paths must match the committed diff and
the registered scope. The record marks `kind: assistant_restored` and
`crew_review: false`, retains worker history, clears approval, and enters
`awaiting_human`. Evidence and reference provenance are recorded as claims for
Vincent to inspect; they do not grant approval, admit a worker, or publish to
GitHub. This path is separate from the authenticated crew receipt adapter.

Use `scope TASK --plan FILE --lease-id ID` to validate an explicit JSON
ExecutionScopePlan for an owned clean checkout. This reuses the existing scope
validator; it does not admit or launch a worker.

Pass `--checkout-root` before `dependencies TASK` to include assistant-approved
local integrations. A candidate must be integrated into Source, match its
receipt and current task contract, and have the exact human approval. This
does not claim production delivery or Unity conformance.

Current implementation status and delegated work are recorded in `STATUS.md`.

## Fresh local Gauntlet replay

`gauntlet-replay --branch gauntlet-replay/NAME` creates the one fixed eight-task
replay family for local visual testing. Run it only in a clean local clone whose
current branch has that exact name and which has no Git remote. It creates fresh
root contracts for NSC-998, NSC-1101, NSC-1103, NSC-1104, NSC-1105, NSC-1107,
NSC-1108 and NSC-1110, plus separate replay tests and validation policy. It does
not create implementation scripts or decomposition children; the architect
allocates child IDs later. NSC-042 and NSC-899 are deliberately excluded. The
command has no custom task mapping and runs `taskcontrol validate` before it
reports success.

`reserve TASK --run-id ID --capacity 1` checks dependencies, scope and resource
ownership without launching a provider. `run-worker TASK --run-id ID --lease-id
LEASE --config FILE --authorize-provider-spend` runs the admitted crew in the
foreground by waiting for a dedicated contained child. Ctrl-C sends that run a
cooperative stop request. Use only after Vincent has authorized that provider work. Model and
provider and `credential_volume` (existing named Docker volume) must be explicit
in the JSON configuration. A per-run Compose override maps the provider to that
external volume without reading credentials or changing the shared Compose
project. Codex effort can be set
with `execution_reasoning_effort`; this existing bridge does not support a
Claude effort argument. No provider work has been launched in verification.

For Vincent-authorized concurrent scene work, prepare and scope each task in
its own task checkout under the same live checkout root. Run `readiness TASK
--capacity 3 --allow-resource-overlap` to preview admission, then `reserve TASK
--run-id ID --capacity 3 --allow-resource-overlap` for a later task that overlaps
an active scene or file reservation. The default still blocks overlap. The
opt-in records the overlapping owner task, run and paths in the new durable
reservation. It shares repository paths only between distinct owned task
checkouts under that one root; logical locks, dependency checks, Source and
scope identity, and the capacity of three still apply. This option is for the
direct task workflow, not the retired `run-graph` controller.

Each worker changes its own scene copy. Candidate integration remains serial
and fast-forward-only. Review and integrate one candidate, then synchronize a
later candidate with the updated main. If its scene or builder conflicts,
`sync-candidate` retains the conflict for a worker to reconcile in that task
checkout; it does not resolve it automatically. Validate and review the
reconciled candidate again before its integration. A reservation never
authorizes provider spend, approves a candidate or merges either branch.

`worker-status TASK` checks the retained worker and Windows process identity.

## Small maintenance tickets

Maintenance is for looking at work that already exists. Create one ticket with
`maintenance-plan TASK --action inspect-worker|verify-candidate|settle-worker|cleanup-worker-docker --run-id ID`,
then run it with `maintenance-run TICKET.json`. Tickets are tied to this source,
checkout, branch, commit, task contract, worker and run. They cannot launch an
agent, change Git, run Unity, approve work, or remove volumes. Docker cleanup is
allowed only after the worker is terminal, capacity is released, and its host
and job are confirmed finished. A completed ticket can be run again safely; it
returns the saved receipt.
`inspect-result TASK [--run-id ASSISTANT_RUN]` is read-only. It re-hashes the
retained `crew_result.json` and candidate patch, verifies their task/run/source/
contract identities, and returns a bounded summary plus the exact artifact paths.
It does not trust a test name or worker label as proof that the bytes still match.
`stop-worker TASK --run-id ID` writes a cooperative stop request for that exact
run. A request is not an exit confirmation. Neither command releases capacity,
deletes work, or claims Docker child cleanup. `start-worker` accepts the same
arguments as `run-worker` and launches a hidden dedicated process after saving
a bound readiness receipt. Before that receipt is published, the child is assigned
to a Windows Job Object so its future host descendants can be stopped together.
`stop-worker --force` stops that owned process tree and only run-bound containers,
preserving files. `settle-worker TASK --run-id ID` releases capacity after host,
contained-tree and container exit checks; succeeded crews also require unchanged
result artifacts. Failed/stopped runs require a contained tree. A launch that
never created a child can settle from its explicit spawn-failure record; a
pre-readiness child failure requires confirmed exit through its retained handle.
After settlement a different run can retry, retaining the previous attempt and
all task files. Existing edits must still satisfy admission; retry never resets
the checkout. Both `start-worker` and `run-worker` use the same contained launcher.
The complete live provider/Unity workflow still needs verification.

After approved integration, `preserve-success` keeps a standalone Git/Unity
project at `C:\NSC\SuccessfullTasks\<TASK-ID>` (override with `--success-root`
for tests). It clones the exact approved commit, retaining Git history while
leaving the worker's project in place; ignored Unity Library/cache files are
not copied. It refuses any pre-existing unowned destination. In particular the
working `SuccessfullTasks\NSC-042` Vincent found must not be overwritten or
automatically adopted. The viewer shows the saved folder only after checking
its commit and the corresponding approved integration in Source.

## Bounded graph controller

`graph-plan` reads the selected committed task graph and reports the next
deterministic actions without changing files, reserving capacity, or starting a
provider. Repeat `--task` to select several roots; committed descendants are
included automatically, transitive prerequisites are brought into scope, and
dependencies are rechecked after every Source change.

```powershell
python -m Pipeline.AssistantControl `
  --source C:\NSC\TenTaskFinalIntegration-20260905 `
  --checkout-root C:\NSC\AssistantGauntletPublishRetry `
  graph-plan --task NSC-898 --task NSC-1008 --auto-approve-gauntlet
```

`run-graph` resumes those actions from durable AssistantControl records. Provider
work requires both a worker configuration and `--authorize-provider-spend`.
`--auto-approve-gauntlet` applies only to authenticated synthetic Gauntlet tasks;
NSC-042 always stops at exact-commit human review. The controller never pushes.

For cheaper delegated help, add `--delegate-safe`. That mode may prepare or
refresh checkouts and create exact scopes. It returns `handoff_required` before
reservation, provider or Docker interaction, worker waiting/settlement,
post-crew processing, decomposition, candidate synchronization, approval, or
integration. This lets a small agent perform portable setup without giving it
authority over the graph or final results. Delegated mode does not require a
worker config and rejects `--authorize-provider-spend`.

Expensive management work that never moves Source runs as an owned background
job instead of blocking the loop: `decompose` (the two-call proposal) and
`post_crew` (candidate registration and focused Unity validation, including the
revalidation of a synchronized Gauntlet candidate). The controller launches a
detached child bound to an exact ticket (task, Source commit, contract hash,
provider configuration, process identity), keeps settling finished workers and
admitting unrelated tasks while it runs, and harvests the child's retained
receipt from `<checkout-root>/.assistant-control/background-jobs/<task>/<job>/`.
Every Source-moving action (`apply_decomposition`, `sync_candidate`,
`auto_approve`, `integrate`) still runs one at a time in the single controller
thread. A restarted controller observes the same live child or harvests its
receipt; it never launches the same ticket twice. A child that fails or dies
without a receipt blocks only its task and is never relaunched automatically:
inspect its `stderr.log`, then `clear-background-job <task> --job-id <id>` to
archive the index before the planner may issue a fresh ticket.
`--background-jobs N` (default 4) bounds concurrent jobs.

One `checkouts.lock` serializes every record transaction in a checkout root, and
with several jobs in flight two transactions regularly want it at once: a
post-crew child holds it about 9 s to register its candidate and a foreground
`sync_candidate` 13-16 s, against a 10 s wait. Losing that wait is contention,
never proof that something is wrong, so a controller action that cannot take the
lock *before it has written anything durable* is deferred to the next planning
cycle instead of failing the invocation. The controller journals `action_deferred`
(task, kind, reason `lock_contention`, lock path, seconds waited, deferral count),
leaves the task unblocked with no `last_error`, keeps the invocation `running`,
pauses three seconds and lets the planner re-emit the action. Only action kinds
whose lock acquisition provably precedes every durable write are deferrable
(`LOCK_DEFERRABLE_ACTION_KINDS` in `graph_controller.py` records the proof per
kind: both launches plus `prepare`, `refresh_prepared`, `scope`, `reserve`,
`start_worker`, `settle_worker`, `sync_candidate`, `auto_approve`, `integrate`);
`apply_decomposition` and the wait kinds keep the old failure path because their
acquisitions are not pre-mutation. After six consecutive deferrals of the same
action the original `TimeoutError` is raised exactly as before, so a wedged lock
still stops the run loudly; the count is per invocation and a restarted controller
starts fresh. Inside a post-crew child the same race used to fail the whole job
and force an operator `clear-background-job`, so candidate registration and the
post-validation persist wait far longer than the controller does (still bounded,
and the persist still refuses a candidate that changed while validation ran).
`materialize_candidate` is the remaining known offender: it holds `checkouts.lock`
across the whole Unity builder and its validation, minutes at a time, which no
waiter's budget can cover; reducing that hold needs its own change, because the
lock is taken before the Source integration and registry locks and releasing it in
the middle would invert that order.

A decomposition proposal reads Source for minutes and binds every round to the
exact head and tree it started from, so the controller holds the Source lane
around one. While any `decompose` job is active, `integrate` and
`apply_decomposition` wait; settlement, post-crew launches, setup, admission,
`sync_candidate` and `auto_approve` all continue, because none of them advances
the Source commit. At most one proposal is in flight: a second decompose-ready
parent waits until the first job has ended and its `apply_decomposition` has
landed or been recorded as failed. When a Source-moving action and a new
`decompose` launch are ready in the same cycle the Source move goes first and
the proposal launches on the next cycle, so an integration is never delayed by
minutes for a proposal that could have started a few seconds later. A held
action keeps its place in the plan's `next_actions` carrying a `held` record
(`reason`, `blocking_task_id`, `blocking_job_id`), is repeated in the plan's
`held` list for `graph-plan` and the viewer, is journaled once per invocation as
`source_lane_held`, and runs unchanged on the first cycle that no longer holds
it. Every input is durable, so a restarted controller rebuilds the same holds
from the job indexes alone.

Every child is assigned to a run-derived named Windows Job Object before it may
work, with the worker launcher's handoff: the controller keeps its handle until
the exact child has opened the named job and written `job.opened.json`, and the
child's receipt must carry the PID and process identity the controller
recorded. Ctrl+C in `run-graph` writes an authenticated `stop.request.json`
(ticket, child identity, Job Object name) for every active job, waits a bounded
grace period for the child to stop itself, then terminates only that recorded
Job Object tree. A decomposition child's cooperative stop is destructive, so it
is held to the same standard as a removal: it inspects its ticket's exact
recorded name once, and stops the container **by its exact id** only when the
name, compose project, `-decompose` service and both ownership labels are the
ones its ticket records. A mismatch, a missing label, an absent container, a
Docker failure or a ticket that does not authenticate stops nothing. The
decision (what was inspected, what was decided, the id stopped, any error) is
written to `cooperative-stop.json` in the run root and never raised, so a
refused cooperative stop cannot turn the child's own `stopped` receipt into a
failure. The job is retained as `cancelled`: never a provider failure, never
relaunched automatically. A controller without a console (a detached runner)
is stopped with `stop-graph [--reason ..] [--grace-seconds N] [--wait-seconds N]`:
it writes `graph-controller.stop.json` bound to the running controller's
invocation, PID and process identity; the controller honors it between actions
and on every wait poll exactly like Ctrl+C and returns status `stopped`. A
request that does not bind to the running invocation is archived and ignored.
`stop-graph` is idempotent: a repeat reuses the bound request, and once the
owner has released it reports `already_released`; it refuses only when no
controller ever owned the graph or the owner record is stale. If the controller
process itself was lost, `stop-background-jobs [--grace-seconds N]` performs
the same job stop; it refuses while a graph controller owns the graph.

A decomposition ticket records, before Docker can start, the exact provider
container it may create (`provider_container`: `nsc-decompose-<job-id prefix>`,
the compose project, and the `labels` that container must carry). The job id is
derived from this checkout as well as the work — kind, task, identity, attempt,
**Source path and checkout root** — so two checkouts, or two clones of the same
Source commit, can never derive the same ticket id or the same container name.
The child puts the same identity on the container itself: `docker compose run`
is given `--label com.nosafecircle.assistant.job=<job id>` and
`--label com.nosafecircle.assistant.checkout=<sha256 of Source + checkout
root>`, and a container found under the ticket's name whose labels are missing
or different belongs to another run and is refused, never removed, exactly as a
compose-project or service mismatch is. After a child's tree has ended (receipt, death,
cooperative stop or Job Object termination) the controller inspects only that
name every 0.5 s for the whole 15 s window, removes only that exact container
id on every sighting, and records `verified_absent` only when the final 3 s of
the window were continuously absent (a late sighting extends the watch until
they are; a name that keeps reappearing is retained as `unverified`). Because
one Docker operation may take up to a minute, a kill-path cleanup also keeps a
tombstone (`tombstone_until_utc`, 60 s) and the cleanup stays *pending* until
that bound has passed and one more exact look has been recorded as
`final_recheck_at_utc` (a sighting there removes the container, reruns the
whole window and starts a fresh bound). Every stop and every controller start
retries a pending cleanup: a stop takes one exact look while the bound is
active and reports `retry_after_utc`; `stop-background-jobs` waits the bound
out (about a minute) and records the final recheck, so its `stopped` (exit 0)
means done, while `cleanup_pending` (exit 1) names what is left;
`stop-graph` reports `stopped_cleanup_pending` or, after the owner released,
`already_released_cleanup_pending` (both exit 1) and points at
`stop-background-jobs`; a controller start waits the bound out and records
the final recheck before its first plan, and the running loop retries
pending cleanups after their bound (`job_container_verified` /
`job_cleanup_pending` events). `clear-background-job` refuses until the
cleanup is final, and a retry ticket for the task is refused until then.
Every retry reauthenticates first and fails closed on any mismatch. The
authenticated set is the immutable ticket (the request bytes against the
recorded hash — a request file that is missing, empty, truncated or malformed
fails that comparison, it never skips it — plus the ticket schema, task id,
job id, kind, identity, Job Object name, Source and checkout root) and the
recorded identity (the owned run directory, the Job Object name derived from
it, the container name derived from the job id with its compose project, the
recorded PID and the complete process identity dict, each checked against the
`launcher.identity.json`, `child.identity.json` and `job.opened.json` its own
run wrote). On any mismatch the cleanup is retained as `refused` with
`authentication_failed` and the index records an `authentication` block
listing every problem: nothing is inspected, removed, signalled or
terminated, the task stays blocked, startup refuses to plan beside it, and it
is never retried automatically. The job id itself is re-derived from this
checkout and compared, and the ticket's recorded container labels must be the
ones this checkout derives, so a ticket carrying another checkout's identity
authenticates nowhere. A refusal never overwrites a cleanup generation that is
in flight under a live owner: its status, generation, owner, removals,
sightings, deadline and final-recheck state stand, the refusal is recorded
beside them, and that owner's own result is still written — as `refused` with
`authentication_failed`, never verified, with its renewed deadline intact. A
refusal with nothing in flight keeps every progress field and can only ever
keep or extend the recorded deadline. The same identity set is re-proven inside
`request_stop` before a stop request is bound and again in the enforcement
immediately before the only destructive call, so an index that names another
job's child reaches no process and no container. The result is retained on
the index as `provider_container_cleanup` (`verified_absent` with the
removed ids and observations, or `refused` with the reason when Docker
cannot answer or the container under that name carries another compose
project or service, in which case nothing is removed). A Docker failure
that happens *after* the exact container was seen or removed keeps that
partial progress durable: the removal is recorded, the operation bound
restarts from it, `final_recheck_at_utc` is owed again and the cleanup stays
pending with `retry_after_utc`. The bound only ever moves forward, so no
failure, and no interrupt between beginning and finishing a generation, can
restore an older deadline or let a cleanup that saw its container read as
complete. Docker work never runs while `checkouts.lock` is held: the cleanup
is recorded as `in_progress` with a generation and its owning process under
the lock, runs without it, and is recorded again only for that generation. A
cleanup in progress under a live owner is waited for (bounded), never
superseded; one whose owner is gone is taken over; a result that was
superseded meanwhile is discarded and the durable record reread. A ticket
cleared or replaced by a newer one while its Docker work ran unlocked is an
expected concurrency outcome (`cleanup_concurrency`, journaled as
`job_cleanup_superseded`), never an exception into the controller loop, and
the loop journals and continues past any cleanup or harvest error rather
than blocking unrelated tasks. After the final recheck a repeated stop makes
no Docker call.

A background-job index that cannot be read or authenticated (missing,
empty, truncated, malformed, or naming another Source or checkout root) is
never read as "nothing remains". `stop-background-jobs` reports it as an
`unreadable_index` job with `cleanup_pending`, so the command reports
`cleanup_pending` and exits 1 with the exact path and error in
`unreadable_indexes`; `stop-graph` reports `stopped_cleanup_pending` or
`already_released_cleanup_pending` (exit 1) with the same diagnostics in its
`unreadable_indexes` and `note`; a controller start refuses (`startup_refused`)
before it plans. Nothing deletes or repairs such a record automatically: an
operator repairs or archives the file by hand, after which the same commands
report finished again.

A restarting controller reconciles every retained ticket under its lock before
the first plan: an authenticated live child (ticket bytes, index, launcher and
child identity handshake, Job Object acknowledgement and containment all
agree) is adopted, its Job Object handle reopened, and harvested later without
relaunch; an ended child is harvested and its container reconciled; a live
child whose identity binds to its run root but whose ticket no longer
authenticates is stopped exactly (bound request, grace, its own Job Object
tree, its exact container) and quarantined, blocking only its task with the
recorded reason; a live child whose identity cannot be bound to its ticket, an
unverifiable child, or a container that is not verified absent refuses startup
(`startup_refused` in the journal, state `blocked`) and nothing is killed or
removed on a guess.

`worker-haiku.example.json` is the checked-in, non-secret worker configuration
used by the examples. It names the existing Docker credential volume but contains
no credential bytes. The graph controller adds execution authority only at an
explicitly authorized provider launch.

The detailed policy and examples are in
[ASSISTANT_AUTONOMOUS_GRAPH.md](../../Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md).

## Workflow

1. Inspect committed tasks, delivery evidence, active workers and resource use.
   The assistant chooses work with Vincent. No background architect chooses it.
2. Create an isolated, complete Git/Unity checkout, plan its scope, then reserve
   the task. The checkout is named
   exactly for its task ID. Pin the source commit and task contract. Existing
   edits in Vincent's project remain untouched; they are never silently copied
   into a worker's starting point.
3. Launch the existing ExecutionCrew against an explicit approved scope. Record
   the provider/model/effort, process identity, checkout, output paths and result.
   Stop must reach the worker and its child processes. A stale PID is not proof
   that a worker is alive or permission to kill another process.
4. Inspect the durable crew result and patch, verify permitted changes and Unity
   .meta companions, then commit the reviewed code candidate in its task checkout.
   Run any registered Unity builder and focused tests before human review.
   Neither crew review nor task completion grants human approval.
5. Show the exact folder and commit in the read-only visualizer. Vincent opens
   that Unity project, tests it, and approves or requests changes in conversation.
6. Record approval against that exact commit. Integrate approved work locally
   only when the target can be updated without overwriting Vincent's edits.
   A changed candidate requires another approval. If changes are needed to
   resolve integration conflicts, present the resulting version for testing.
7. Update dependency evidence after integration. Decomposition children retain
   their parent and go through the same checkout, review and approval path.

## Implementation boundaries

- Reuse `ExecutionCrewBridge`, scope validation, patch validation and the Git
  identity guard where their preconditions apply. Do not invent legacy Issue
  leases just to pass an old controller check.
- `LocalTaskCheckoutManager` currently requires a LocalRunContext and its lease
  history. Extract or adapt the isolated-clone mechanics rather than running an
  autonomous scheduler to obtain those records.
- Persist assistant-owned task records outside the Unity Source directory.
  Commands and the viewer must read one source of state, surviving chat restarts.
- A read-only viewer must refuse mutation routes on the server, not just hide
  buttons. Keep existing modes available until this replacement is proven.
- GitHub publication is an explicit operation, not a side effect of local review.
- Tests use disposable Git repositories and fixture workers. They must exercise
  failure, restart and changed-commit approval cases. Paid-provider and Unity
  testing remain separate and require an authorized live demonstration.

## Completion evidence still required

Focused tests cover capacity/resource reservations, worker launch/stop/retry,
validated candidate commit, exact approval/rejection, integration recovery,
and viewer projection. A fixture demonstration covers candidate verification
through approval, local integration and successful-project preservation.

`revise TASK --candidate-commit SHA` preserves an exactly rejected candidate as
the new starting commit, retains prior review/worker records, and clears approval.
It requires settled worker capacity and a fresh scope/admission. The revision
state and approval boundaries are fixture-tested. For an ordinary candidate the
worker passes exact rejection notes through ExecutionCrew's existing retry path.
A synchronized candidate uses the separate fresh-feedback path described above.
A real-Git component
test exercises that retry with fixture provider responses and verifies the notes
in implementer, test-author and validator prompts. The previous candidate is
verified as already present; Source remains unchanged. Retry currently requires
compatible scope and the same provider/model/effort configuration. This proves
feedback delivery to provider requests, not paid-provider behavior or Unity visuals.

Still pending: broader live demonstrations with Vincent's actual test decisions.
Existing child contracts can be inspected and processed as tasks. AssistantControl
also supports an explicit decomposition boundary: `decompose` runs one bounded
author/reviewer pair against read-only Source. `claude,codex` is independent by
provider identity. A same-provider pair such as `claude,claude` is independent
only as two separate conversations, so that route reserves one durable session
per role from the decomposition session pool and settles both from the run's own
artifacts. A pooled same-provider run needs a `--run-id` that is a lowercase
slug of 1..64 characters (`[a-z0-9-]`, no leading or trailing hyphen), because
the pool and the container both require that form; `claude,codex` still accepts
the older mixed-case and dotted run id.
`inspect-decomposition` rechecks its exact durable artifacts, and
`apply-decomposition` creates the canonical local D1C commit only while the reviewed
source, contract and plan are still exact. These commands never push.

### Diagnosing a stopped decomposition

`diagnose-decomposition TASK --run-id RUN` reads that run's retained
`decomposition_run_result.json` (through its current or archived receipt) and
routes it to one primary cause: `SETUP` (launch or provider configuration),
`BUDGET` (a valid reviewer revision used the last permitted call), `AUTHOR` (a
candidate or revision failed deterministic validation), `CONTRACT` (the output
asked for human or design authority, which means contract review, not that the
contract is wrong) or `STOP` (source or evidence problems, success, or nothing
recognised). Secondary causes, such as the reviewer findings behind a budget
stop, are kept. It is read-only and every result says `retry_authorized:
false`; choosing and authorizing a retry stays a separate decision.

### Decomposing in an isolated clone

The apply-time gate compares the reviewed Source commit with Source HEAD under
`Tasks`, `Pipeline/TaskGraph` and the validation policy, so delivery records that
other agents land on the shared checkout invalidate an in-flight plan. Pass
`--source` a standalone clone nobody else commits to and `--checkout-root` a
directory disjoint from it (the records root must not nest inside the source).
The proposal, `inspect-decomposition` and `apply-decomposition` then run exactly
as they do on the shared checkout. The D1C commit moves to the shared checkout as
an ordinary merge candidate with its ancestry intact (no cherry-pick or rebase);
validate the combined graph on a trial merge with that checkout's own
`taskcontrol.py validate` before merging, replay the reviewed plan against the
trial merge (`inspect_graph_delta_replay` must report `already_applied`), and
compare each new child's `validation_plan_for` result on the candidate and on
the trial merge. A `None` plan on both sides means no validation policy is
configured for that child, not that validation passed. The decomposition
receipt stays in the clone's records root, bound to the clone: it is never
copied, relabelled or deleted to make the shared checkout accept it. On the
shared checkout a committed decomposed parent is an aggregate while its
children are pending and complete once committed TaskGraph evidence makes it
conformant; a settled (`failed`, `review_ready` or `applied`) receipt does not
veto that committed-conformance route, while a `running` or unrecognised one
still does.
There is no separate decomposition `approve` command; application is the
explicit `apply-decomposition` call.
No fixture result is evidence that NSC-042's gameplay works.
