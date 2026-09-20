# Request: a Cleanup Agent role (Game Agent to Documentation Agent, 2026-09-17)

Vincent, 2026-09-17, after the Game Agent started doing this work by hand: "no That is not your job, we need a clean up agent."

## Why
Repository hygiene has become its own recurring job, and it keeps landing on the Integration Steward between merges. Today's pass alone: 272 branches examined, 133 archived-and-deleted, 139 worktrees classified, about 56 GB in `C:\NSC\_worktrees`.

## Suggested scope
- **Branches:** find branches whose commits are all in local main (ancestry or `git cherry` patch-equivalence), save each tip under `refs/archive/<branch>`, then delete the local branch. Never delete an NSC-### branch (Vincent's standing rule).
- **Worktrees:** `git worktree list` triage, removal of merged non-task worktrees, `git worktree prune`, and reporting worktrees that hold uncommitted work instead of forcing them.
- **Disk:** stale clones and job folders under `C:\nscrev`, old Codex and Claude job clones, Unity `Library` folders in dead worktrees.
- **Reporting:** a plan file plus a ready-to-run PowerShell script for Vincent, never destructive without his go.

## Not in scope
- Deleting remote branches: that is a push, which belongs to the Release Agent.
- Merging, delivery evidence, or SuccessfullTasks archives: those stay with the Game Agent.
- Anything holding uncommitted work, without Vincent's per-item go.

## Work already done today, for the new agent to continue
- Plan and lists: `C:\nscrev\reports\branch-cleanup-20260917.md`, `branch-triage-20260917.md`, `worktree-cleanup-20260917.txt`.
- Scripts that Vincent ran: `branch-cleanup-20260917-delete.ps1`, `worktree-cleanup-20260917.ps1`.
- Result: local branches 201 -> 131; 103 archive refs written; about 26 worktrees removed.

## Open items to hand over
1. **7 merged non-task worktrees** that refused removal because they hold uncommitted or untracked files. Their committed work is in main:
   `NoSafeCircle-ClaudeGuidancePort-20260914`, `NoSafeCircle-D4-Grounding-Hotfix`, `NoSafeCircle-D4-Opening-Hotfix`, `NoSafeCircle-Door-UI-Sorting-Hotfix`, `NoSafeCircle-FiveRoom-Wizard-Review`, `NoSafeCircle-Game-Candidate`, `NoSafeCircle-Room-Composition-B`.
   Next step: report what is uncommitted in each (real edits versus Unity `Library` noise), then ask Vincent per folder.
2. **114 worktrees still registered**, 24 of them detached. 72 are task-named and merged; the Game Agent still owes Vincent a decision on how those tasks get archived, so leave those until he answers.
3. **56 GB** under `C:\NSC\_worktrees` before today's removals; re-measure after.

## What the Game Agent keeps
Merges into local main, delivery evidence, SuccessfullTasks archives, Unity runs, and game code fixes.
