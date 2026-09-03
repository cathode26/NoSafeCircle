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
- no active durable-checkout manifest points at the removed checkout.

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

### 6. Archive the active checkout manifest

Move the exact active manifest:

```text
C:\NSC\NSC\.task-review-agent\<TASK-ID>.json
```

to a no-overwrite timestamped directory under:

```text
C:\NSC\NSC\.task-review-agent\archive\<TASK-ID>\<UTC-TIMESTAMP>\
```

Retain `outputs\<TASK-ID>\<RUN-ID>` directories in place. They are immutable diagnostics, use unique run IDs, and do not authorize resume by themselves.

### 7. Verify fresh availability

Refresh remote refs with pruning, then prove:

- the controller is clean and `main == origin/main`;
- the abandoned remote branch is absent;
- no matching claim refs exist;
- the canonical and auxiliary checkout paths are absent;
- no active checkout manifest exists;
- the old PR and Issue are closed;
- `taskcontrol.py state <TASK-ID>` reports `not_delivered`;
- `taskcontrol.py validate` passes.

Only after all checks pass may the task be launched fresh:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-### -ExecutionProvider claude
```

## Repeat a merged task in a disposable rehearsal repository

Use this procedure only when Vincent explicitly requests another end-to-end run
of the same task in the same disposable private rehearsal repository. It is not
a recovery path for a merged production task.

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
8. Move the exact active checkout manifest to a no-overwrite timestamped archive
   under `.task-review-agent/archive/<TASK-ID>/<UTC-TIMESTAMP>/`. Retain every
   immutable output/run directory.
9. Re-fetch with pruning and prove: clean synchronized rehearsal `main`,
   TaskGraph state `not_delivered`, TaskGraph validation PASS, no active matching
   Issue, no task branch, no claim ref, no task checkout, and no active manifest.
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
