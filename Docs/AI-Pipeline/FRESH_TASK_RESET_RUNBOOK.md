# Fresh Task Reset Runbook

## Purpose

Use this runbook only when Vincent explicitly decides that an undelivered task must be abandoned and restarted from current `main` as fresh work.

A fresh-task reset removes operational work-in-progress state. It does **not** remove the TaskGraph contract, rewrite `main`, erase committed delivery evidence, or pretend that the abandoned run completed.

## Required authority

A reset is destructive and requires explicit human authorization naming the task ID. Never infer reset authority from a failed command, stale checkout, old branch, or desire to retry a provider.

If the task implementation or delivery evidence is already merged into `main`, stop. That is not a fresh-task reset; use a separately reviewed revert or follow-up task.

The only exception is a repository that Vincent explicitly identifies as a
disposable private rehearsal repository. Use the separate procedure below; do
not apply it to production `main` or disguise it as an ordinary abandoned-task
reset.

## Fresh-state definition

An implementation task is operationally fresh when all of the following are true:

- its active TaskGraph contract remains committed on current `main`;
- TaskGraph derives it as `not_delivered`, with no committed delivery record being removed;
- no open GitHub Issue owns the task;
- no open pull request targets its abandoned task branch;
- no remote task branch exists;
- no task or resource claim ref from the abandoned run exists;
- `C:\NSC\NSC\<TASK-ID>` does not exist;
- no task-specific auxiliary worktree or local branch from the abandoned run remains;
- no active task-specific controller state file remains for the abandoned run.

Historical Issue/PR discussion and immutable run logs are retained as audit evidence. A later fresh launch creates a new managed Issue, checkout, branch, and run ID.

## Safety preflight

From the clean shared controller checkout, record and verify:

1. current `main` and `origin/main` identities;
2. TaskGraph state and the exact committed task-contract hash;
3. managed Issue number, state, labels, head commit, and handoff commit;
4. pull-request number, state, base branch, head branch, and head OID;
5. local and remote task branches;
6. all `refs/nsc/claims/*` refs associated with the task or its resources;
7. every Git worktree whose path or branch is task-specific;
8. canonical checkout root, origin, branch, HEAD, upstream, staged state, tracked changes, and untracked files;
9. active durable-checkout manifest and immutable output directories;
10. processes or containers that still use the checkout.

Stop instead of resetting when:

- the canonical checkout or an auxiliary worktree is dirty;
- local HEAD differs from its pushed upstream;
- the task branch is already merged into `main`;
- a claim belongs to a live worker;
- the Issue or PR identities do not match the intended task;
- any target path resolves outside the explicitly expected task directories;
- Unity, an IDE, terminal, file explorer, provider process, or container is using a target checkout.

Do not use `git reset --hard`, `git clean`, or a force-push to manufacture a clean precondition.

## Reset sequence

Perform the reset in this order so each destructive step is fenced by the state recorded immediately before it.

### Production cache-only cleanup helper

When the full inventory already proves that production TaskGraph is
`not_delivered`, every matching Issue and pull request is closed, and the task
has no checkout, local/remote branch, or claim ref, the remaining exact
controller cache files can be archived by the general helper. It will not revert
or commit production code:

```powershell
python Pipeline/TaskReviewAgent/reset_task.py NSC-042 --source C:\NSC\NSC\NoSafeCircle --checkout-root C:\NSC\NSC --production-state-cleanup
```

After reviewing that dry run, apply the exact cache-only cleanup with:

```powershell
python Pipeline/TaskReviewAgent/reset_task.py NSC-042 --source C:\NSC\NSC\NoSafeCircle --checkout-root C:\NSC\NSC --production-state-cleanup --apply --confirm-repository cathode26/NoSafeCircle
```

This mode deliberately refuses delivered production work, an existing checkout,
any branch or claim, or an open Issue/PR. A production delivery revert remains a
separately reviewed Git change; it is never inferred from stale cache cleanup.

When Vincent explicitly authorizes repeating a task whose delivery is already
conformant on production `main`, use the separate delivered-production mode:

```powershell
python Pipeline/TaskReviewAgent/reset_task.py NSC-### --source C:\NSC\NSC\NoSafeCircle --checkout-root C:\NSC\NSC --revert-delivered-production --archive-repository cathode26/NoSafeCircle-Archive --apply --confirm-repository cathode26/NoSafeCircle
```

This mode requires one valid closed `complete` Issue and its exact merged PR. It
refuses the revert when any active direct or transitive dependent task is past
`not_delivered`. It also proves the merge is an ancestor of current `main` and
refuses when any later commit changed a task-delivery path. The helper creates a
normal revert on top of current `main`, verifies only the exact PR path set
changed and every reverted tree entry equals the merge's first parent, requires
TaskGraph to return to `not_delivered`, and preserves later unrelated production
commits. The archive repository must already exist and be private. No production
reset, rebase, or force-push is permitted.

### 1. Close the abandoned pull request

Close the open PR with a comment that identifies:

- the task ID;
- the abandoned head branch and exact head OID;
- that Vincent requested a fresh reset;
- that the PR was not merged;
- the replacement run will start from current `main`.

Do not mark the PR merged and do not delete its historical discussion.

### 2. Close the abandoned managed Issue

Add a final reset comment containing the same exact branch/commit facts, then close the Issue. Leave its managed state incomplete; do not fabricate PASS, FAIL, or `complete`.

The TaskReviewAgent ignores a closed incomplete Issue for fresh dispatch while retaining it as audit history. Do not delete and recreate Issue history merely to make the sidebar look clean.

### 3. Delete the exact remote task branch

Re-read the remote branch OID after closing the PR. Delete only when it still equals the recorded abandoned head. Use an exact `--force-with-lease=<full-ref>:<expected-oid>` fence; never use an unfenced force-push and never delete a wildcard branch set.

If the ref moved, stop and inspect the new commit. Do not delete it using the old authorization.

### 4. Release stale claim refs, if any

Normally a completed handoff has already released its claims. If task/resource claims remain, use `GitRefClaimClient.inspect_claims()` and confirm the owning process is dead. Remove them only through `repair_stale_claim()` with the exact reported claim OID.

Never delete claim refs by name alone.

### 5. Remove verified local task state

Close programs using the directories. Recheck each checkout immediately before removal.

For the canonical standalone checkout, require:

- resolved path equals `C:\NSC\NSC\<TASK-ID>` exactly;
- origin equals the controller repository origin;
- branch and HEAD equal the abandoned branch/OID;
- upstream equals HEAD;
- porcelain status is empty.

For any task-specific linked worktree, require an explicitly inventoried path, branch, clean status, and exact HEAD. Remove it with `git worktree remove`, then delete only its exact local branch. Never prune or delete unrelated worktrees while resetting one task.

After those checks, remove the canonical task directory by its literal absolute path. Do not use a wildcard, computed parent directory, recursive repository-root target, `git clean`, or `git reset`.

### 6. Archive active task controller state

Inventory and move every existing exact task-owned controller state file:

```text
C:\NSC\NSC\.task-review-agent\<TASK-ID>.json
C:\NSC\NSC\.task-review-agent\<TASK-ID>.scope.json
C:\NSC\NSC\.task-review-agent\<TASK-ID>.execution.json
C:\NSC\NSC\.task-review-agent\<TASK-ID>.integration.json
C:\NSC\NSC\.task-review-agent\<TASK-ID>.downstream.json
```

to a no-overwrite timestamped directory under:

```text
C:\NSC\NSC\.task-review-agent\archive\<TASK-ID>\<UTC-TIMESTAMP>\
```

Some files may be absent when the abandoned run stopped before that phase. Verify
the archived filename set exactly equals the task-specific files that existed at
preflight. Retain `outputs\<TASK-ID>\<RUN-ID>` directories in place. They are
immutable diagnostics, use unique run IDs, and do not authorize resume by
themselves.

### 7. Verify fresh availability

Refresh remote refs with pruning, then prove:

- the controller is clean and `main == origin/main`;
- the abandoned remote branch is absent;
- no matching claim refs exist;
- the canonical and auxiliary checkout paths are absent;
- no active task-specific controller state file exists;
- the old PR and Issue are closed;
- `taskcontrol.py state <TASK-ID>` reports `not_delivered`;
- `taskcontrol.py validate` passes.

Only after all checks pass may the task be launched fresh:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-### -ExecutionProvider claude
```

## Repeat a merged task in a disposable rehearsal repository

For an incomplete, unmerged task in a disposable private rehearsal repository,
use the general helper's abandoned-rehearsal mode. It closes the exact
incomplete Issue and any exact open PR, fences deletion of the exact remote
branch, verifies/removes only the clean canonical checkout, archives active
state, retains immutable outputs, and leaves `main` unchanged:

```powershell
python C:\NSC\NSC\NoSafeCircle\Pipeline\TaskReviewAgent\reset_task.py NSC-901 --source C:\NSC\Rehearsal\NoSafeCircle-Homework-Rehearsal --checkout-root C:\NSC\Rehearsal --abandon-incomplete-rehearsal
```

After reviewing the dry run:

```powershell
python C:\NSC\NSC\NoSafeCircle\Pipeline\TaskReviewAgent\reset_task.py NSC-901 --source C:\NSC\Rehearsal\NoSafeCircle-Homework-Rehearsal --checkout-root C:\NSC\Rehearsal --abandon-incomplete-rehearsal --apply --confirm-repository cathode26/NoSafeCircle-Homework-Rehearsal
```

This mode refuses a completed Issue, a task already contained in `main`, a
dirty/unpushed checkout, a changed remote branch, live claims, or any repository
that cannot be proven to be private and explicitly named as rehearsal.

If Windows interrupts checkout removal on a read-only Git object, do not delete
the remainder manually. Resume the exact no-overwrite stopped receipt; the
helper revalidates main, the closed Issue, the absent remote branch, and the
preflight checkout identity before retrying read-only removal. Re-run the same
applied command with `--resume-report` set to the exact `report_path` printed by
the stopped run.

Use this procedure only when Vincent explicitly requests another end-to-end run
of the same task in the same disposable private rehearsal repository. It is not
a recovery path for a merged production task.

The checked-in helper performs this procedure with exact-ref and repository
guards. It is read-only unless `--apply` is supplied:

```powershell
python C:\NSC\NSC\NoSafeCircle\Pipeline\TaskReviewAgent\reset_rehearsal_task.py NSC-901 --source C:\NSC\Rehearsal\NoSafeCircle-Homework-Rehearsal --checkout-root C:\NSC\Rehearsal
```

After reviewing the dry-run inventory, the complete one-command reset is:

```powershell
python C:\NSC\NSC\NoSafeCircle\Pipeline\TaskReviewAgent\reset_rehearsal_task.py NSC-901 --source C:\NSC\Rehearsal\NoSafeCircle-Homework-Rehearsal --checkout-root C:\NSC\Rehearsal --apply --confirm-repository cathode26/NoSafeCircle-Homework-Rehearsal
```

The helper derives the default private Issue archive as
`<owner>/<source-repository>-Archive`; pass `--archive-repository owner/name`
when a different private archive is intended. The confirmation value is checked
against the source checkout's actual `origin`, not trusted as repository
authority. The helper refuses repositories that are public, archived, do not
contain `rehearsal` in their GitHub name, or whose exact merge/Issue/PR/checkout
identities cannot be proven.

“Uncommit” in this procedure always means a new additive revert commit. The
helper never resets, rebases, force-pushes, or deletes the original merge from
history. Its no-overwrite JSON receipt is retained under
`.task-review-agent/reset-runs/<TASK-ID>/`, so a partial external failure has an
exact recovery record.

1. Record the rehearsal repository, task ID, merged PR, merge commit, first
   parent, task branch/head, completed Issue, checkout, active manifest, claims,
   and immutable output directories.
2. Verify that the merge commit is current `origin/main`, has the expected first
   parent, and contains only the rehearsal task implementation and its delivery
   evidence relative to that parent.
3. Fast-forward the clean rehearsal controller to that exact merge commit. Create
   a normal `git revert -m 1` commit with the guarded automation identity. Do not
   reset, rebase, force-push, delete, or otherwise rewrite `main` history.
4. Before pushing, prove the revert commit's tree equals the merge commit's first
   parent tree. Push the revert by exact SHA-to-`refs/heads/main` refspec, then
   re-fetch and verify `main == origin/main` at the revert.
5. Preserve the closed `complete` Issue outside the active rehearsal repository,
   for example by transferring it to a private rehearsal-Issue archive owned by
   the same account. Do not delete its discussion or edit its hashed workflow
   history. Verify the active repository's complete issue listing no longer
   returns it for the task ID.
6. Preserve the merged PR and its checks. Delete only the exact old remote task
   branch, after re-reading its head and using
   `--force-with-lease=<full-ref>:<expected-oid>`.
7. Verify the standalone task checkout's resolved path, origin, branch, HEAD,
   upstream, and clean status; verify no Unity, IDE, terminal, provider process,
   or container uses it; then remove only that literal task directory.
8. Move every exact active task-specific controller state file (checkout,
   scope, execution, integration, and downstream when present) to one
   no-overwrite timestamped archive under
   `.task-review-agent/archive/<TASK-ID>/<UTC-TIMESTAMP>/`. Verify the archived
   filename set and retain every immutable output/run directory.
9. Re-fetch with pruning and prove: clean synchronized rehearsal `main`,
   TaskGraph state `not_delivered`, TaskGraph validation PASS, no active matching
   Issue, no task branch, no claim ref, no task checkout, and no active
   task-specific controller state file.
10. Commit and validate any pipeline fixes on rehearsal `main` before starting the
    next task run. Launch the same task ID explicitly only after all fresh-state
    checks pass.

The required report includes both the original merge and the additive revert,
the archived Issue URL, preserved PR URL, deleted task branch/head, removed
checkout, archived manifest, retained logs, new rehearsal-main commit, and final
TaskGraph state. The original merge remains in history as proof of run 1; the
revert makes the current tree eligible for run 2 without claiming run 1 never
happened.

## Required reset report

Report:

- current `main` commit;
- closed Issue and PR URLs;
- deleted remote branch and its final OID;
- removed canonical and auxiliary checkout paths;
- archived manifest path;
- whether claim refs existed and how they were fenced;
- retained output/log location;
- final TaskGraph state;
- every error or target deliberately left untouched.
