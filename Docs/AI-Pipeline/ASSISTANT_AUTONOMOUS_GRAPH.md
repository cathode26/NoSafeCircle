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
- `run-graph` (bounded execution)

Both commands require `--checkout-root` and one or more explicit `--task` targets.

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
   - `prepare`, `refresh_prepared`, `scope`, `reserve`, `start_worker`, `wait_worker`, `settle_worker`, `post_crew`, `decompose`, `apply_decomposition`, `sync_candidate`, `auto_approve`, `integrate`.
4. It executes exactly one action per loop iteration and re-plans after each successful action.
5. It updates durable controller state (`graph-controller.json`) for replay/resume.

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

For non-042 Gauntlet tasks, this runs post-crew validation, records a distinct
`assistant_gauntlet_automation` approval, then continues toward `integrate`. It
does not record or imitate Vincent's human approval.

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
