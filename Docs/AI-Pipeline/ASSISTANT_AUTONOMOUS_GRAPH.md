# AssistantControl Autonomous Graph Loop (Operator + Developer Guide)

This guide is for local graph execution with `Pipeline/AssistantControl`.

## Scope
Use `graph-controller` mode only for local, non-publishing work.
The loop:

- discovers active committed tasks,
- plans bounded graph transitions,
- executes safe graph actions,
- stops at operator-visible handoff points,
- never pushes or creates remote PRs.

## Ground rules

- `NSC-042` is always human-only. The CLI enforces this (`GraphPolicy` requires it in `human_review_tasks`).
- Auto-approve/integrate is for **synthetic Gauntlet tasks only** when `--auto-approve-gauntlet` is enabled.
- No provider/Git/Unity retry policy beyond what existing commands already define.
- On unknown provider/test/runtime/Git failures, stop and report.

## Actual CLI contract (implemented)

Use only:

- `graph-plan` (read-only plan preview)
- `graph-preflight` (persist the exact plan and policy/config binding; no workers)
- `run-graph` (bounded execution)

All three commands require `--checkout-root` and one or more explicit `--task` targets.
`run-graph` also requires a prior matching `graph-preflight` in that checkout
root. Repeat preflight after Source or execution settings change. Use the same
flags, including the worker config and spend authorization if the later run
will launch a provider. `graph-plan` alone does not persist this binding.
The display-only viewer may show the entire committed task graph regardless of
the execution targets. `--capacity 3` reserves up to three task worker slots;
provider-family rotation is a separate operator responsibility.

### Command syntax

```powershell
python -m Pipeline.AssistantControl.__main__ `
  --source C:\NSC\TenTaskFinalIntegration-20260905 `
  --checkout-root C:\NSC\TenTaskFinalIntegration-20260905-Checkouts `
  graph-plan `
  --task NSC-1001 `
  --task NSC-1003 `
  --human-review-task NSC-042 `
  --auto-approve-gauntlet
```

```powershell
python -m Pipeline.AssistantControl.__main__ `
  --source C:\NSC\TenTaskFinalIntegration-20260905 `
  --checkout-root C:\NSC\TenTaskFinalIntegration-20260905-Checkouts `
  run-graph `
  --task NSC-1001 `
  --task NSC-1003 `
  --worker-config C:\NSC\TenTaskFinalIntegration-20260905\Pipeline\AssistantControl\worker-haiku.example.json `
  --human-review-task NSC-042 `
  --auto-approve-gauntlet `
  --authorize-provider-spend `
  --max-actions 10 `
  --capacity 1
```

### Required flags

- `--worker-config <path>`: JSON object for implementation workers. It is
  required for normal execution and optional with `--delegate-safe`.
- `--authorize-provider-spend`: required for provider-launch actions (`start_worker` and `decompose`).
- `--human-review-task NSC-042`: accepted, but cannot remove 042 from human gate.
- `--max-actions N`: positive int, bounded transitions (default `100`, must be >= 1).
- `--once`: perform one durable transition equivalent to `--max-actions 1`.
- `--delegate-safe`: restrict execution to safe non-sensitive actions only.

## Deterministic loop behavior

1. `run-graph` loads current `HEAD` and branch. Source must be on an attached branch.
2. For each target task, it includes committed descendants and transitive
   prerequisites, then checks dependency completeness.
3. It emits one prioritized action from `next_actions` at a time:
   - `prepare`, `refresh_prepared`, `scope`, `reserve`, `start_worker`, `wait_worker`, `wait_job`, `settle_worker`, `post_crew`, `decompose`, `apply_decomposition`, `sync_candidate`, `auto_approve`, `integrate`.
4. It executes exactly one action per loop iteration and re-plans after each successful action.
   Priority within one cycle: `settle_worker` first; then launching `decompose` and
   `post_crew` as owned background jobs (bounded by `--background-jobs`); then
   `prepare`/`refresh_prepared`/`scope`; then `reserve`/`start_worker`; then the
   Source-moving lane (`apply_decomposition`, `sync_candidate`, `auto_approve`,
   `integrate`) in planner order; waiting last. A wait returns as soon as any
   watched worker exits or any background job ends.
   A decomposition proposal binds every round to the Source head and tree it
   started from, so while any `decompose` job is active the two Source-advancing
   actions, `integrate` and `apply_decomposition`, are held and everything else
   in the cycle continues; at most one proposal is in flight, a second waiting
   until the first has ended and its apply has landed or been recorded as
   failed; and a Source-moving action ready in the same cycle as a new
   `decompose` launch goes first, the launch following on the next cycle. A held
   action stays in `next_actions` carrying a `held` record, is repeated in the
   plan's `held` list, and is journaled once as `source_lane_held`.
   An action that cannot take this checkout root's `checkouts.lock` within its
   budget, and that provably had not written anything durable when it asked, is
   deferred rather than failed: the controller journals `action_deferred` with the
   task, kind, reason `lock_contention`, the lock path, the seconds waited and the
   deferral count, leaves the task unblocked and `last_error` unset, keeps the
   invocation `running`, pauses a bounded three seconds, and re-plans, which
   re-emits the action. The deferrable kinds are the two launches plus `prepare`,
   `refresh_prepared`, `scope`, `reserve`, `start_worker`, `settle_worker`,
   `sync_candidate`, `auto_approve` and `integrate`
   (`LOCK_DEFERRABLE_ACTION_KINDS`, which records the pre-mutation proof for
   each); `apply_decomposition`, which never takes that lock, and the wait kinds,
   which reach it only inside receipt harvesting and container-cleanup recording,
   keep the ordinary failure path. The bound is six consecutive deferrals of the
   same action, after which the original `TimeoutError` is raised exactly as it
   would have been without the deferral, so a wedged lock still ends the run with
   status `blocked`, `last_error` set and exit 1. Deferral counts live only in the
   running invocation; a restarted controller carries none. The run result lists
   every deferral in `lock_deferrals`.
5. It harvests ended background jobs' receipts before every plan, and updates
   durable controller state (`graph-controller.json`, `background_jobs` summary)
   for replay/resume. A restarted controller observes a live job by its recorded
   process identity or harvests its retained receipt; it never launches the same
   ticket twice. A failed or receipt-less dead job blocks only its task until an
   operator runs `clear-background-job <task> --job-id <id>`. A child's own lost
   `checkouts.lock` wait used to reach that state, so the two record transactions
   a post-crew child performs (candidate registration, and the persist of a
   finished validation) wait far longer than the controller does before failing,
   and the persist re-verifies the exact candidate when it acquires the lock.
6. Each child is contained in a run-derived named Job Object before it may work
   (worker-launcher handoff: the parent holds its handle until the exact child
   acknowledges with `job.opened.json`), and its receipt must carry the PID and
   process identity recorded at launch. Ctrl+C writes a bound `stop.request.json`
   per active job, waits a bounded cooperative grace period, then terminates
   only that recorded Job Object tree; the ticket is retained as `cancelled` and
   never relaunched. `stop-graph` asks a running controller to do the same
   without Ctrl+C (a stop request bound to its invocation, PID and process
   identity; it returns status `stopped`; repeating it is idempotent);
   `stop-background-jobs` repeats the job stop after the controller process
   was lost and refuses while a controller is running.
7. A decomposition ticket fixes its exact provider container name, compose
   project and labels before Docker can start. The name is checkout-exact: the
   job id it derives from includes the Source path and checkout root, so two
   checkouts of the same Source commit never share a container identity, and
   the container itself carries the ticket's job and checkout labels
   (`docker compose run --label`), so one found under the name without them is
   another run's and is refused, never removed. The child's own cooperative
   stop is held to the same standard: it inspects that exact name first and
   stops the container by its exact id only when the name, compose project,
   service and both ownership labels are its ticket's, recording the decision
   in the run root and never failing the child. After the child's tree has ended, only
   that name is inspected, only that exact container id is removed, the name
   is watched for the whole bounded window and verified only when its final
   stability interval was absent; a kill-path cleanup keeps a one-minute
   tombstone and stays pending until that bound has passed and a final exact
   recheck is recorded, which every stop, every controller start and the
   running loop drive forward (`stop-background-jobs` waits the bound out
   before claiming `stopped`). A Docker failure or an interrupt after the
   container was seen or removed keeps that partial progress durable and
   restarts the bound from it; the bound only ever moves forward, so no
   failure can restore an older deadline or complete a cleanup that saw its
   container. Every retry reauthenticates the immutable ticket (a missing,
   empty, truncated or malformed request file fails the recorded hash rather
   than skipping it) and the recorded identity (PID, complete process
   identity, Job Object name, derived container name and compose project,
   owned run directory) against the artifacts its own run wrote, and fails
   closed on a mismatch with `authentication_failed` and nothing inspected,
   removed, signalled or terminated. A refusal never overwrites a generation
   in flight under a live owner: that owner still records its removals,
   sightings and renewed bound, and its generation lands as refused rather than
   discarded, so no retry can run against a shortened deadline. A cleanup in progress under a live owner
   is awaited, an abandoned one taken over, and a ticket cleared or superseded
   meanwhile is an expected concurrency outcome that the loop journals and
   continues past instead of failing the controller. The outcome is retained
   on the index; a mismatch or an unavailable Docker is retained as a refusal
   with nothing removed; Docker work never runs while the checkout lock is
   held. An index that cannot be read or authenticated is never "nothing
   remains": `stop-graph` and `stop-background-jobs` fail closed with a
   cleanup-pending status, a nonzero exit and the exact path and error, a
   controller start refuses, and nothing is repaired automatically.
8. A restarting controller reconciles every retained ticket under its lock
   before the first plan: authenticated live children are adopted (Job Object
   handle reopened, never relaunched), ended children harvested with their
   container reconciled, live children with a bound identity but a ticket that
   no longer authenticates stopped exactly and quarantined (only their task
   blocked, with the reason), and an unbound identity, an unverifiable child or
   an unverified container refuses startup with nothing killed or removed.

## `--delegate-safe` semantics (required by request)

`DELEGATE_SAFE_ACTIONS` is exactly:

- `prepare`
- `refresh_prepared`
- `scope`

When `--delegate-safe` is set:

- `--authorize-provider-spend` is rejected, and no worker config is required.
- If the planner’s next action is one of the above, it executes it.
- If the next action needs reservation, a provider, Docker, Unity, worker
  observation/settlement, receipt processing, graph mutation, synchronization,
  approval, or integration, it must stop first.
- On first blocked action, status is `handoff_required` with `handoff_action` and `allowed_actions` in output.

Use this for conservative operator-assisted progression.

### Small-agent assignment

Give a cheaper helper only the repository path, checkout-root path, selected task
IDs, and this instruction:

> Run `graph-plan`, then run the same selection with `run-graph --delegate-safe`
> and the checked-in Haiku example config. Do not remove `--delegate-safe`, edit
> task contracts, use Docker or Unity, inspect/settle workers, process crew
> receipts, reserve work, launch providers, approve, integrate, publish, or retry
> a failure. Return the JSON when the command reports `handoff_required`,
> `blocked`, `awaiting_human`, or `complete`.

The command enforces the authority boundary even if the helper misunderstands
the prose. The main assistant reviews the returned exact action before continuing.

## Human-review boundary (042)

- `NSC-042` is forcibly included in `human_review_tasks` and enforced in `GraphPolicy.__post_init__`.
- Any `awaiting_human`/non-auto task state for `NSC-042` is surfaced through `waiting_human`.
- Auto-approve path (`auto_approve` action) never applies to `NSC-042` because it is not allowed to leave human review.

## Gauntlet-only auto-approve behavior

`auto_approve` action is only generated when:

- task is in `awaiting_human`,
- task is synthetic Gauntlet (`is_synthetic_gauntlet(...)`),
- `--auto-approve-gauntlet` is enabled,
- source is in sync.

For non-042 Gauntlet tasks, the planner first sends a candidate without
retained focused-validation facts (a freshly registered or a source-synchronized
one) to a background `post_crew` job; `auto_approve` is emitted only once those
facts exist, records a distinct `assistant_gauntlet_automation` approval from
them without running Unity again, and the graph continues toward `integrate`.
`auto_approve` fails closed if the exact candidate carries no retained
validation. It does not record or imitate Vincent's human approval.

## Planning cost per cycle

`plan()` re-reads Source every cycle but keeps, per exact Source HEAD: every
committed contract (read in one `git cat-file --batch` process), one committed
conformance view for never-started tasks, and each integration or decomposition
proof keyed by the bytes of the record it was derived from. All of it is
discarded the moment HEAD or worktree dirtiness changes. On the 102-task fresh
gauntlet graph a warm cycle costs about 0.2 s and four git processes; the first
cycle after a HEAD move costs about 5 s.

## Dependency/source recheck after integration/decomposition

The planner recomputes task completeness every cycle; after `integrate` or `apply_decomposition` the next `run-graph` iteration re-reads:

- current `HEAD`/branch,
- dependency graph completion,
- candidate/integration status,
- reservation and worker state,

so newly eligible children become visible automatically in the next plan.

For explicit control, prefer:

- `graph-plan` after each `run-graph` batch,
- check `waiting_human`, `blocked`, `handoff_required`, and `status` before continuing.

## No-provider planning preview mode

Use `graph-plan` for dry planning (no provider launch, no post-worker execution):

```powershell
python -m Pipeline.AssistantControl.__main__ `
  --source C:\NSC\TenTaskFinalIntegration-20260905 `
  --checkout-root C:\NSC\TenTaskFinalIntegration-20260905-Checkouts `
  graph-plan `
  --task NSC-1001 --task NSC-1003 `
  --human-review-task NSC-042 `
  --auto-approve-gauntlet
```

To get the same bounded effect with an explicit transition cap, use:

```powershell
python -m Pipeline.AssistantControl.__main__ `
  --source C:\NSC\TenTaskFinalIntegration-20260905 `
  --checkout-root C:\NSC\TenTaskFinalIntegration-20260905-Checkouts `
  run-graph `
  --task NSC-1001 `
  --worker-config C:\NSC\TenTaskFinalIntegration-20260905\Pipeline\AssistantControl\worker-haiku.example.json `
  --human-review-task NSC-042 `
  --authorize-provider-spend `
  --max-actions 1
```

## Resume behavior

- state is persisted to `<checkout-root>/.assistant-control/graph-controller.json`.
- on restart, rerun `run-graph` with same targets and config to continue from recorded state.

## Never-do list

- Never run `run-graph` with publish/push semantics (there are no push/PR actions here).
- Never treat `graph-plan` as an executing pipeline.
- Never bypass `--authorize-provider-spend` for provider actions.
- Never use `run-graph` for unknown retry loops; stop on novel failure statuses.
