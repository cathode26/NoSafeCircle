# Worktree inventory (Cleanup Agent, 2026-09-18 ~21:25 CDT)

Read-only. Nothing was moved, removed, pruned or reset. Raw data and the scripts that produced it: `C:\nscrev\reports\cleanup\data-20260918\` (`wt_inventory.json`, `wt_sizes_k.tsv`, `scan_20260918_2125.txt`).
Sizes are `du -sk` per top-level folder in `C:\NSC\_worktrees`. Every figure below was measured tonight; none is quoted from a handover.

## 1. What is registered (canonical `git worktree list --porcelain`)

| | count |
|---|---|
| registered worktrees | **138** (137 besides canonical itself) |
| under `C:\NSC\_worktrees` | **79** |
| elsewhere under `C:\NSC` | 54 |
| in `C:\nscrev` | 4 |
| detached HEAD | 23 |
| locked / prunable | 0 / 0 |
| all paths exist on disk | yes (138 of 138) |

## 2. `C:\NSC\_worktrees`: 57.9 GB, 132 entries (matches the Documentation Agent's 58 GB of 2026-09-17)

| kind | entries | size |
|---|---|---|
| registered, **task-named**, clean, merged | 21 | 6.4 GB |
| registered, task-named, clean, unmerged | 35 | 11.2 GB |
| registered, task-named, **dirty**, merged | 5 | 6.7 GB |
| registered, task-named, **dirty**, unmerged | 18 | 24.7 GB |
| independent clones (`.git` is a directory), 6 | 6 | 7.4 GB |
| worktrees of *another* repo (`.git` file, not in canonical's list), 4 | 4 | 1.5 GB |
| plain directories (no `.git`) | 6 | ~0 |
| loose files (logs, xml, json, png, py) | 37 | ~0 |

**All 79 registered ones are task-named** (`nsc0NN-...-20260914` and similar), so under guide section 3 none of them can be planned for removal until Vincent decides how the tasks are archived (the Game Agent owes him that). That is 49.0 GB of the 57.9.

Points the removal decision has to carry with it:
- **3 detached worktrees hold a HEAD that no ref reaches.** Removing the worktree leaves those commits unreferenced (collectable):
  - `C:\NSC\_worktrees\nsc058-exact-unity-20260914` `baf13ab3bf`, 2 changed files
  - `C:\NSC\_worktrees\nsc065-unity-import-20260914` `8e9ee232e6`, 11 changed files
  - `C:\NSC\NoSafeCircle-NSC069-Review` `3d27c447fd`, **179** changed files
  A `refs/archive/` ref for each would be the first line of any script.
- **The 6 independent clones** (`nsc050-052-current-main-unity`, `nsc050-052-unity-validation`, `nsc051-unity-validation`, `nsc090-provisional`, `nsc090-unity-validation`, `nsc090-unity-validation-warm`, all `-20260914`): every branch in them is already an object canonical holds. Uncommitted files: 39, 39 and 39 in the first three, 0 in `nsc090-provisional`, 3 and 2 in the last two (not yet classified as churn or edits).
- **`nsc090-implementation-20260914` is a worktree of the clone `nsc090-provisional-20260914`**, so removing the clone first orphans it. The other three foreign-parent worktrees (`nsc050-candidate-validation`, `nsc050-final-validation`, `nsc089-final-validation`) belong to the clones `C:\NSC\NoSafeCircle-AssistantCheckouts\NSC-050` and `NSC-089`, which are guarded. Order matters.
- Nothing in the board, the journal or an agent state file mentions the folders below by name; `_worktrees` itself is mentioned (board 2, agent-state 3) only in general terms.

## 3. The 7 worktrees the Game Agent handed over (all under `C:\NSC\`, **not** under `_worktrees`)

`git status` and a blob-hash comparison against `main` (a file counts as "identical to main" when its normalised blob hash equals `main:<path>`).

| folder | branch state | uncommitted | verdict |
|---|---|---|---|
| `NoSafeCircle-D4-Grounding-Hotfix` | HEAD in main | 1 file: `ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json`, **0 content diff** (line endings only) | churn only |
| `NoSafeCircle-Door-UI-Sorting-Hotfix` | HEAD in main | same single file, 0 content diff | churn only |
| `NoSafeCircle-FiveRoom-Wizard-Review` | HEAD in main | same single file, 0 content diff | churn only |
| `NoSafeCircle-Game-Candidate` | HEAD in main | same single file, 0 content diff | churn only |
| `NoSafeCircle-D4-Opening-Hotfix` | HEAD in main | **39 files** (+14629/-14183): 36 of them identical to main; **3 differ from main**: `WizardAnimator.controller`, `Assets/Scenes/DoorPrototype.unity`, `Assets/Scenes/Rooms/FinalRoom.unity`. All dated 2026-09-13 09:52 (one Unity run) | probably Unity re-serialisation, but 3 files unproven; ask Vincent |
| `NoSafeCircle-Room-Composition-B` | HEAD **not** an ancestor of main, but `git cherry` shows its 1 commit (`Repair room composition source scenes`) patch-equivalent to main | 3 files: `Settings.json` (identical to main), `BoneArchive.unity` and `ChapelOfAsh.unity` **differ from main** (+2857/-2857 each way) | ask Vincent |
| `NoSafeCircle-ClaudeGuidancePort-20260914` | HEAD in main | **4 real edits**, none identical to main: `Pipeline/TaskDecomposition/{README.md,policy.py,prompts.py,review_prompts.py}` (+214/-17). This is genuine uncommitted guidance work, not churn | keep; the Decomposition Agent or Pipeline Maintainer should say whether it matters |

A worktree with even one modified tracked file refuses `git worktree remove` (no `--force`), so the four churn-only ones need their `Settings.json` reset (`git checkout -- <file>`, discarding a zero-content-diff change) before removal. That discards uncommitted state, so it needs Vincent's per-item go.

## 4. Other non-task worktrees at `C:\NSC` top level (26 in all, incl. the 7 above)

- **4 clean, detached, HEAD in main, `git cherry` 0 plus, no mention anywhere:** `OrchestratorCrewPreflight-20260913` (41 MB), `ProviderSmokeVerify-20260906` (29 MB), `ReleaseBaseF560` (55 MB), `ReleasePublish40a` (55 MB). Newest file 2026-09-06 to 09-14. 180 MB total: **the only plannable worktrees tonight, and a trivial reclaim.** `ReleaseBaseF560` and `ReleasePublish40a` look like Release Agent names, so no plan until that agent has answered my 21:18 message.
- **14 clean, unmerged (cherry shows 1 to 84 commits not on main):** `BulkRetirementFilter`, `CombinedScale-20260905-18c867c`, `DecompositionResumeRouteFix`, `RetiredCompletionFix\NoSafeCircle`, `SyntheticPumpOne\NoSafeCircle`, `TaskGraphPerf\NoSafeCircle`, `NoSafeCircle-AssistantControl-SpeedIntegration`, `NoSafeCircle-Cardinal-Staging`, `NoSafeCircle-Restored-Meta-Fix`, `ScalePrereqIntegration-...-wt`, `SchedulerFactoryExtraction`, `SourceAdmissionSnapshot-...`, `ThousandScaleIntegration-...-ebaa` and `-v2`. Their branches survive worktree removal, but they are the throughput and gauntlet experiments from the clone-only question (section 6). Not touched.
- **1 more dirty:** `NoSafeCircle-Review-Wizard-Lobby` (unmerged, +1 cherry, 39 changed files).

## 5. `MOVE-NSC-FOLDERS.ps1` against runbook rule 21: FAILS, do not run it as written

Read in full for its guards (`C:\NSC-History-20260918\MOVE-NSC-FOLDERS.ps1`, 878 lines).
- It **moves worktrees**. `Get-FreshDirGuardFailure` (line ~700) treats a `.git` *file* the same as a `.git` directory: if the tip is on main and the tree is clean it passes. The apply loop (line 808) merely *records* `$isWorktree` and prints a note at the end (line 873) telling someone to run `git worktree prune`. It never skips one. Moving by `robocopy /MOVE` is exactly the operation rule 21 forbids.
- Exposure measured tonight: **1 of its 416 embedded directory names is a registered worktree, `ProviderSmokeVerify-20260906`** (HEAD in main, clean, so it would pass every guard and be moved, leaving canonical's `.git\worktrees\` entry dangling). Only 1 of the 416 is an independent repo at all, and it is parent to no other worktree. 415 are plain directories.
- `C:\NSC\_worktrees` is **not** in its list (checked by parsing the list), so the large reclaim is not exposed. The hard-guard list (`NSC`, `NoSafeCircle-AssistantCheckouts`, `agent-state`, `SuccessfullTasks`) does not name it either; it is safe only because the list is a fixed set of names.
- Fix needed before any run: skip when `$isWorktree` (a `.git` file), or remove `ProviderSmokeVerify-20260906` from the list and handle it through `git worktree remove`. I have not edited the file: it lives in the history folder and the fix is a change to a script another agent wrote. I will make a corrected copy under `C:\nscrev\reports\cleanup\` when the `C:\NSC` pass is my next job.

## 6. Fresh safety scan (`cleanup-safety-scan.py`, 2026-09-18 21:25, both roots, popups suppressed by a wrapper, tool untouched)

`C:\nscrev` alone reproduced the handover's shape; with `C:\NSC` added the figures are larger:
- scanned: **204** directories with a `.git` file, **211** independent clones, **573** plain directories (depth 1 only);
- **198 branches in 109 clones exist only there** (the handover's 81 in 32 was `C:\nscrev` alone; the scan's "worktrees of canonical" label counts `.git`-file directories, not verified registrations, which is why 204 exceeds 138).
That widens the "~60 undecided clone-only branches" question, so I am not quoting ~60 any more. `C:\NSC\_worktrees` is depth 2, so this scan never saw it; I checked its 6 clones separately (section 2).

## 7. What needs Vincent

1. **Task-named worktrees (79, 49.0 GB):** waiting on his archive decision with the Game Agent. Biggest single lever; not plannable until then.
2. **The four churn-only worktrees** (D4-Grounding, Door-UI-Sorting, FiveRoom, Game-Candidate): OK to reset `Settings.json` and remove them?
3. **D4-Opening-Hotfix, Room-Composition-B, ClaudeGuidancePort:** per-folder go or keep, with the differences above.
4. **`MOVE-NSC-FOLDERS.ps1`:** do not run; needs the worktree skip.
