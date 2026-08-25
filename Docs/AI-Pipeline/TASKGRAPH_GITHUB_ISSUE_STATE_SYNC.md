# TaskGraph → GitHub Issue State Sync

## Purpose

This policy defines the on-demand synchronization requested by a human with instructions such as:

> Sync the TaskGraph states to the GitHub Issues.

That instruction means: read the evidence-derived TaskGraph state for current committed `main`, find the existing GitHub Issue for each matching `NSC-###` task, and update a bounded mirror block in the Issue body so GitHub visibly reflects the current TaskGraph state.

TaskGraph remains authoritative. GitHub is only a human-facing operational mirror.

## Source of truth

Always begin from current remote `main`. Do not use remembered task state from an old conversation or an old Issue comment.

Run once:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --json
```

The returned `state`, `head_commit`, `selected_record_id`, and task identity are the authoritative inputs for this sync.

Do not infer current TaskGraph state from:

- whether an Issue is open or closed;
- whether an Issue was previously marked completed;
- an old closeout comment;
- the presence of an evidence directory alone;
- `contract_disposition: active` alone.

## Which Issues are synchronized

Default on-demand sync updates **existing** Issues whose title begins with the exact TaskGraph ID (`NSC-###`). Search both open and closed Issues.

Do not create missing Issues merely because a sync was requested. Under the current orchestration MVP, `no Issue` still has its existing operational meaning. Report missing Issues separately.

If the human explicitly asks to materialize/create missing Issues as well, that is a separate action and should use the normal TaskGraph-contract Issue-body format.

If more than one Issue begins with the same exact `NSC-###` ID, fail closed for that task: report the duplicates and do not guess which Issue owns the mirror.

## Managed mirror block

The Issue body owns exactly one managed block:

```markdown
<!-- TASKGRAPH_STATE_MIRROR:START -->
## TaskGraph State Mirror

- Derived state: `needs_testing`
- Evaluated from: `main@<commit-sha>`
- Selected evidence: `<record-id>`
- Meaning: Previously completed/evidenced work may need testing again because current HEAD changed a tracked surface or lineage. This is not fresh implementation work.

TaskGraph is authoritative; this block is a GitHub mirror only.
<!-- TASKGRAPH_STATE_MIRROR:END -->
```

Rules:

1. If the block exists, replace only the text between the exact start/end markers.
2. If the block does not exist, append it to the Issue body.
3. Preserve all other Issue-body content exactly.
4. Do not create a new comment on every sync merely to repeat the state; the managed body block is intentionally idempotent.
5. Do not treat manually written prose elsewhere in the Issue as current state authority.

Use `(none)` when `selected_record_id` is null.

## Required state meanings

Use these meanings in the managed block:

| TaskGraph state | GitHub mirror meaning |
| --- | --- |
| `conformant` | Completed/evidenced work is currently proven against committed HEAD. |
| `needs_testing` | Previously completed/evidenced work may need testing again because tracked current-state evidence changed. **Not fresh implementation work.** |
| `needs_replan` | Prior evidence exists, but the current task contract changed; planning/contract review is required before claiming current conformance. |
| `needs_human` | Current evidence requires a human approval/decision that is not yet satisfied. |
| `not_delivered` | No usable committed evidence currently proves delivery; this may be a fresh-work candidate only after normal scope/dependency/claim checks. |
| `invalid_evidence` | Committed evidence is structurally or semantically invalid and requires investigation. |
| `ambiguous_evidence` | More than one maximal current-valid evidence record prevents a unique conformance result. |
| `aggregate` | This contract is aggregate/non-executable under current TaskGraph semantics. |
| `superseded` | The task contract is superseded. |
| `cancelled` | The task contract is cancelled. |

The mirror text should be concise but must preserve these semantics.

## `needs_testing` is mandatory to propagate

A sync must update existing Issues that were previously completed/closed if their current TaskGraph state is now `needs_testing`.

Example:

```text
old Issue history: implementation merged and Issue closed
current TaskGraph: needs_testing
```

Correct sync behavior:

```text
Issue remains closed
managed mirror block becomes: needs_testing
```

Do **not** leave the Issue mirror saying `conformant` merely because the historical implementation orchestration finished successfully.

`needs_testing` means the task was completed/evidenced before, but current HEAD is no longer proven without another testing/revalidation pass. It does not mean the implementation was never completed.

## Do not change Issue lifecycle state during a pure state sync

A pure TaskGraph-state sync updates the managed mirror block only.

It must **not**, solely because of the derived state:

- reopen a closed Issue;
- close an open Issue;
- assign or unassign an Issue;
- create a claim;
- release a claim;
- create a branch/checkout;
- start testing or implementation;
- create or rewrite TaskGraph evidence.

GitHub open/closed/assignment state answers orchestration questions. TaskGraph state answers evidence-derived project-state questions. They are intentionally separate axes.

If the human separately asks to act on `needs_testing`, that becomes a testing/revalidation work decision, not part of the mirror sync itself.

## Sync algorithm for a fresh ChatGPT instance

Use this order:

```text
read current main + AI pipeline routing docs
        ↓
run taskcontrol states --json once
        ↓
index TaskGraph states by exact NSC ID
        ↓
search GitHub Issues (open + closed)
        ↓
index Issues by exact leading NSC ID
        ↓
for every existing uniquely matched Issue:
    build current mirror block
    replace existing block or append one
    preserve Issue lifecycle/assignment
        ↓
report updated / already-current / missing / duplicate / failed counts
```

Before writing, compare the desired block with the current block. If already identical, do not issue a no-op GitHub update.

## Sync completion report

After an on-demand sync, report at minimum:

- TaskGraph source `main` commit;
- total TaskGraph states inspected;
- existing Issues updated;
- existing Issues already current;
- TaskGraph tasks with no Issue;
- duplicate/ambiguous Issue mappings;
- failed Issue updates;
- count of Issues mirrored as `needs_testing`.

If any duplicate mapping or failed update exists, report the exact NSC IDs instead of claiming a complete sync.

## Authority boundary

This process is a mirror operation only.

It does not establish dependency readiness, execution authorization, delivery, conformance, testing success, merge authority, or autonomous dispatch authority. It does not modify TaskGraph contracts or evidence.

The direction of authority is one-way:

```text
TaskGraph committed HEAD
        ↓
GitHub Issue mirror
```

Never use a GitHub mirror value to overwrite or infer TaskGraph truth.
