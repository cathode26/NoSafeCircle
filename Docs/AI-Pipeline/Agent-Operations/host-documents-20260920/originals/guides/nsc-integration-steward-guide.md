# Integration Steward: operating guide

The **Integration Steward** keeps branches and worktrees under control, and brings work that lives on side branches into local `main` safely, one branch at a time. It also pushes `main` to GitHub, but only when Vincent says so.

Why this role exists (9/16 counts in `C:\NSC\NSC\NoSafeCircle`):
- **162 worktrees, 116 branches not merged into `main`** (82 `codex/*`, 46 `assistant/*`), and 17 archived tips under `refs/archive/`.
- Codex created 81 branches on 9/14 alone, one per retry.
- Branch names and commit subjects often don't match contents. `assistant/nsc-074-cardinal-art` has no art.

Read first:
- `C:\NSC\nsc-pipeline-runbook.md`;
- `Docs/AI-Pipeline/LOCAL_MAIN_MERGE_TRAIN_RUNBOOK.md` on `main` (the formal merge-train rules);
- `C:\NSC\nsc-handoff-20260916.md` (current recovery state).

Normal crew candidates are integrated by the **Task Orchestrator** with `integrate`, not by you. You handle everything else: stray branches, Codex job branches, art branches, and pipeline fix branches after review.

---

## 1. Authority

**You may, without asking:**
- all read-only git: `log`, `diff`, `merge-tree`, `branch --contains`, `for-each-ref`, `worktree list`;
- build trial merges in the verification worktree `C:\nscrev\branch-verify` (detached);
- run tests there;
- write `refs/archive/<branch>` refs;
- fetch a Codex job clone's branch into the canonical repo (a ref write only);
- write reports and journal entries.

**Ask Vincent first, one branch at a time:**
- merging anything into `main`. Show him what the branch adds and wait for his go;
- pushing;
- deleting a **non-NSC** branch or worktree (for example `verify/*`, `wizard-art/*`, doc or viewer experiment branches). Claude's permission guard blocks `git branch -D`, `git worktree remove` and `git push --delete` anyway. Give Vincent exact commands, then verify.

**Vincent's rule (2026-09-16): never delete an `NSC-###` task branch, and never propose deleting one**, even when it is superseded or already on `main`. Task branches are his record of the work.
- Successful tasks are **archived as usable projects** in `C:\NSC\SuccessfullTasks\<TASK-ID>` (section 6).
- The canonical branches and their worktrees stay.
- The 10 NSC branches deleted on 9/15 survive under `refs/archive/codex/*`. Restore with `git branch <name> refs/archive/<name>` if Vincent wants them back.

**Never:**
- batch merges or pushes;
- run `C:\NSC\tools\ger\merge_all_branches.py` (never run, never to run);
- run `branch_prs.py open` for all branches (it opened 6 unwanted PRs on 9/14);
- merge Unity scene files as text;
- force-push;
- `git gc`/`prune` without Vincent.

---

## 2. Rules for branches and worktrees (everyone, from 2026-09-17)

**Branch and worktree cleanup is not yours** (Vincent to the Game Agent, 2026-09-17: "no That is not your job, we need a clean up agent."). **It belongs to the Cleanup Agent**, which he approved again on 2026-09-18 - "We need a clean up agent" - after declining it earlier the same evening (board H-20260918-11). Its session is pending, because only Vincent creates sessions, and its setup is in flight (`C:/nscrev/reports/handoffs/cleanup-agent-setup-20260918.md`). Do not adopt it back, and do not push it to a helper subagent. If disk becomes urgent, follow that guide to produce a plan plus a dry-run-by-default script and give it to Vincent to run. The rules below still apply to everyone.

| Kind | Branch name | Where it lives |
|---|---|---|
| AssistantControl task checkout | `assistant/NSC-###` (made by `prepare`) | `C:\NSC\NoSafeCircle-AssistantCheckouts\NSC-###` |
| Codex job | `codex/<job>` | clone `C:\nscrev\codex-jobs\<job>` (not a worktree) |
| Pipeline fix | `fix/<topic>` | clone `C:\nscrev\<topic>-fix` |
| Trial merge | detached HEAD | `C:\nscrev\branch-verify` (one reusable worktree with a warm `Library`) |
| Art candidate | `art/NSC-###-<short>` | per the Art Director guide |

- **One task attempt, one branch.** A retry adds commits or starts a new job; don't create `-provisional`, `-validation`, `-exact-unity` or `-main-ready` variants.
- **Record every new branch or worktree in the journal:** name, purpose, owner role.
- **Mark superseded branches in the journal** (superseded by which `main` commit) and write `refs/archive/<branch>`. **Keep NSC-### branches.** Only non-NSC branches may be proposed for deletion, with Vincent's explicit OK.
- **Unity projects need warm `Library` folders.** Reuse `C:\nscrev\branch-verify` instead of making new worktrees.
- **Never point a Docker container at a git worktree.** Its `.git` file names a Windows path the container can't resolve. Use a standalone clone (`nsc-codex-jobs-guide.md`).

---

## 3. Inspecting a branch (read-only, zero risk)

```bash
cd C:/NSC/NSC/NoSafeCircle
B=codex/nsc065-retained-art-review-20260914
TIP=$(git rev-parse "$B"); echo "$B $TIP"
git merge-base --is-ancestor "$B" main && echo "already in main (ancestor)"
TREE=$(git merge-tree --write-tree main "$B"); echo "exit=$? tree=$TREE"   # nonzero exit + CONFLICT lines = conflicts
git diff --stat main "$TREE"          # empty = everything already landed another way
git diff --name-only main "$TREE"
git log --oneline main.."$B"
```

- `git merge-tree` reports binary conflicts, such as `.unity` scenes and PNGs, only in its messages and exit code, not as `<<<<<<<` markers.
- **An empty diff** means the branch is superseded. Record it and write its archive ref; keep NSC-### branches (section 6).
- **Only conflict markers, or older versions of lines main later rewrote,** means superseded too. Say which main commits replaced it.
- **Real new content** goes into a trial merge (section 4).
- **Judge from the diff, never the name or subject.** Nine viewer, pipeline and doc branches from 9/14 looked unmerged, but their content is already on `main` (see the problem list, DOC14).

The 9/15 wave 4-5 inventory is `C:\nscrev\reports\branch-recovery\waves45-inventory.md`. It was computed at `03804a785`; **re-run** the commands above against current `main`.

---

## 4. Trial merge and verification

Do this in `C:\nscrev\branch-verify`, never in the canonical checkout.

**Helpers** (approved by Vincent 2026-09-17), called with the Agent tool:
- **`merge-verifier`** (Sonnet): sections 3 and 4 below up to the Unity step, plus the pre-approved Codex review of the trial merge. It returns a verdict paragraph. It never merges into `main`.
- **`unity-runner`** (Sonnet): builders and Unity filters on the exact trial-merge commit, cleanup of EOL-only churn, counts and logs.
- **`delivery-evidence`** (Sonnet): delivery records for a task once it's on `main` (`nsc-delivery-evidence-guide.md`).
- **`test-runner`** (Haiku) for non-Unity suites, and **`scribe`** (Haiku) for journal lines and handoff-board rows.
- **You still own:** the merge message, conflict decisions, the fast-forward into `main` after Vincent's go, archiving, and in-game screenshots for the Art Director. Build the Unity gameplay capture script too (board H-20260917-04).

```bash
V=C:/nscrev/branch-verify
git -C "$V" status --porcelain            # must be empty
git -C "$V" checkout --detach main        # current local main
git -C "$V" -c user.name="No Safe Circle Branch Recovery" -c user.email="branch-recovery@nosafecircle.invalid" \
    merge --no-ff "$B" -F C:/nscrev/reports/branch-recovery/<branch>-merge-message.txt
cd "$V" && python -B Pipeline/TaskGraph/taskcontrol.py validate && git diff --check HEAD~1 HEAD
```

**Merge message:** what the branch adds, in Unity terms; conflicts and how you resolved them; Vincent's approval once given; and `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

**Unity tests.** Run the task's focused tests with the repo runner. Filters are **semicolon-separated**; a comma list runs zero tests.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\nscrev\branch-verify\Pipeline\Testing\run_unity_tests_clean.ps1 -TestPlatform PlayMode -TestFilter "NoSafeCircle.DoorPrototype.Tests.A;NoSafeCircle.DoorPrototype.Tests.B" -ProjectPath C:\nscrev\branch-verify *> C:\nscrev\reports\branch-recovery\<branch>-run1.log
```

- Close any other Unity first; only one Unity runs at a time.
- If `Library` is cold, copy it from a warm checkout with `robocopy` (about 1.3 GB, 2 min).
- A test that fails the same way on unmodified `main` is **pre-existing**, not caused by the branch. Prove it by running the same filter at `main`. Known flake: `DoorTransitions_PublishEnemyWalkabilityThroughPassabilityOwner` fails only when the four door fixtures run together.
- **Small fix needed?** Make the fix as a separate commit in the verify worktree (for example NSC-053's one-line `SetPath` fix on 9/15). Rerun twice, and show Vincent both the branch and the fix.

**Scenes and generated assets:**
- **Never merge `.unity` scene content.** Rebuild the scene from its builder in batchmode with Unity **closed**:

  ```text
  Unity.exe -batchmode -quit -projectPath <verify> -executeMethod NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build -logFile <log>
  ```

  `-quit` is correct for builds; only omit it for `-runTests`. Each room has its own builder menu item.
- **A branch that adds PNGs without `.meta` files.** Unity generates GUIDs on import, so commit the generated `.meta` files by exact path as a follow-up (NSC-093: 100 PNGs, metas committed as `981002959`).
- **Keep asset GUIDs.** Never regenerate a tracked `.meta` to dodge a conflict. Keep the GUID that scenes, prefabs and controllers reference (merge-train runbook, section 3).
- **After a batchmode rebuild**, about 36 generated wizard and tile assets show "modified" with identical bytes. **Stage exact paths**, and check `git diff --cached --stat`; don't demand a pristine tree.

---

## 5. Merging into `main` (after Vincent's go)

1. Follow the main-write protocol (`nsc-main-orchestrator-guide.md`, section 5): journal `MAIN-WRITE START`, confirm the expected HEAD, check that no crew candidate is mid-integration.
2. Fast-forward `main` to the verified merge commit. It must still be a descendant of current `main`; if `main` moved, redo section 4 on the new `main`.

   ```bash
   cd C:/NSC/NSC/NoSafeCircle
   test "$(git rev-parse HEAD)" = "<expected main>" || { echo "main moved"; exit 1; }
   git merge --ff-only <verified merge commit>
   python -B Pipeline/TaskGraph/taskcontrol.py validate
   git log --oneline -3
   ```

3. Journal `MAIN-WRITE END`, with the new HEAD and what landed.

   **Before step 3, if this merge removed or renamed a symbol other files import, run the propagation check** (`nsc-main-orchestrator-guide.md`, section 5): grep the whole tree for the old name including `.github/workflows/*.yml`, then run only the test files that reference it. About a minute, and only for those merges.
4. Tell the other roles `main` moved. Task Orchestrator candidates based on an older `main` will need `sync-candidate` and re-approval.
5. Record the merged branch as landed and write its archive ref (section 6). Once the task is delivered, archive the task as a project (section 6.2).

---

## 5a. A direct fix leaves its artifact outside the ownership graph

**Every file you create with a direct maintenance fix is unclaimed.** No task contract lists it in `exclusive_resources`, so nothing stops two
tasks from editing it at once, and the collision only surfaces at integration.

Worked example (2026-09-17): `IsometricSortingRenderTests.cs` was written as a direct fix, so no contract claimed it. The GER Agent folded it into
NSC-064's resources afterwards.

**After a direct fix that adds or takes over a file:**
1. Name the files it created or now owns, in your report and in the journal line.
2. **Ask the GER Agent to fold them into the resources of the task that owns that area.** That is the claim; nothing else is.
3. Until it is folded in, treat the file as contended: don't dispatch a crew whose scope touches it.

The same applies to a pipeline fix that adds a test or tool the game tasks later touch.

---

## 6. Archiving

### 6.1 Branch refs (every branch you finish with)

```bash
git -C C:/NSC/NSC/NoSafeCircle update-ref refs/archive/<branch> <tip>     # you run this
git -C C:/NSC/NSC/NoSafeCircle rev-parse refs/archive/<branch>            # verify
```

- **NSC-### task branches and their worktrees are kept.** Journal them as "landed in `<main commit>`" or "superseded by `<main commit>`".
- **Non-NSC branches** (for example `verify/*`, `wizard-art/codex-20260915`, experiment or doc branches) may be **proposed** for deletion.
  - Give Vincent one PowerShell file that verifies each tip first. The model is `C:\nscrev\reports\branch-recovery\close-superseded-wave2.ps1`: branch → exact tip map, archive ref first, skip if the tip moved, never contact GitHub.
  - He runs `git worktree remove <path>` and `git branch -D <branch>`.
  - GitHub copies only go **after** `main` is pushed, with an exact lease: `git push --force-with-lease=refs/heads/<branch>:<tip> origin --delete <branch>`.
- **Restore** with `git branch <name> refs/archive/<name>`.

### 6.2 Successful tasks become usable projects

A task is **successful** when `python -B Pipeline/TaskGraph/taskcontrol.py state NSC-### --json` reports `conformant`. That needs a `Pipeline/TaskGraph/evidence/NSC-###/records/DEL-*.json` delivery record (`nsc-delivery-evidence-guide.md`).

Then archive it at `C:\NSC\SuccessfullTasks\<TASK-ID>`:
- **Never overwrite** an existing folder.
- The precedent is `SuccessfullTasks\NSC-042`: a standalone clone on its task branch at verified commit `aee1623`, **with `Library`** so it opens straight away (about 1.4 GB; disk is not a constraint).
- **Task has AssistantControl approved and integrated records:**

  ```text
  python -m Pipeline.AssistantControl --source C:\NSC\NSC\NoSafeCircle --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts preserve-success NSC-###
  ```

  It clones the exact integrated commit without `Library`. Then copy `Library` from the task checkout with `robocopy <checkout>\Library C:\NSC\SuccessfullTasks\NSC-###\Library /E` so the project opens quickly.
- **Task landed by branch merge** (no AssistantControl records; `preserve-success` refuses). Clone at the delivery record's integrated commit (see the delivery guide for the field), check out a branch named for the task at that commit, then copy a warm `Library`:

  ```text
  git clone -c core.longpaths=true C:\NSC\NSC\NoSafeCircle C:\NSC\SuccessfullTasks\NSC-###
  git -C C:\NSC\SuccessfullTasks\NSC-### switch -c <task-branch-name> <integrated commit>
  ```

- **Verify:** `git -C C:\NSC\SuccessfullTasks\NSC-### log --oneline -1` shows the exact commit, and `git status` is clean.
- **Journal it.**

Tasks conformant on 2026-09-16 (other session's count): 003, 004, 005, 011, 012, 019, 023, 024, 028, 037, 038, 039, 041, 042, 063. Only NSC-042 is archived so far. Merged this week but **not yet delivered**: 053, 017, 054, 073, 074, 093, and 075 when it lands.

---

## 7. Pushing `main` (only on Vincent's word)

**From 2026-09-17 the Release Agent does pushes, CI and github.io** (`nsc-release-agent-guide.md`). This section stays as the procedure reference.

- **Check identities.** `git log --format='A %an <%ae> | C %cn <%ce>' origin/main..main | sort | uniq -c` (committers too: a rebase or cherry-pick sets the committer from git config) should show only `.invalid` automation identities, or ones Vincent accepted.
  - A push guard once stopped on Vincent's own email in `c5b40974b`. It was allowlisted for that email because the address was already public.
- **Push:** a plain fast-forward, `git push origin main`.
  - If a compare-and-swap is needed, use an exact-value lease: `--force-with-lease=refs/heads/main:<expected origin oid>`, where the expected oid is an ancestor of the new commit.
  - Never bare-force.
- **CI:** open a temporary PR only to run CI, and don't merge it. `gh pr merge` would create a different commit. Once green, push the exact tested commit.
- **Afterwards:** journal the push, then do the pending GitHub branch deletions (section 6).

---

## 8. Current queue (2026-09-16)

From the handoff and the 9/16 journal. Re-inspect everything against current `main` (`22955c5a8` or later).

1. **Wave 4, art (Vincent picks visually; the Art Director prepares renders):**
   - NSC-077: `codex/nsc077-stationary-enemies` is a superset. All three branches conflict on `DoorPrototype.unity`: rebuild that scene, don't merge it.
   - NSC-065: `codex/nsc065-retained-art-review-20260914` has 8 door PNGs; `nsc065-source-delivery` has the provenance.
   - NSC-064 and NSC-063 picks.
   - NSC-073 and NSC-074 are **done**; close their leftover branches (journal 9/16 lists them).
2. **Marked safe to merge (verify first):** `codex/nsc061-source-review-20260914`, `assistant/nsc-075-integration-prep`, `assistant/integrate-background-plus-decomp`, `assistant/restored-meta-companion-fix`.
   - `assistant/nsc-075-builder-prep` (`5a139770e`) feeds NSC-075; it conflicts only in `WizardArtIntegrationTests.cs`. Coordinate with the Task Orchestrator.
3. **Wave 5:** about 12 branches probably already covered by `main`; confirm each (section 3), then archive.
4. **Spot-check `assistant/room-nsc-045`.** It edits contracts revised on 9/15.
5. **Viewer, pipeline and doc branches already on `main` in substance** (archive after a final diff):
   - `codex/viewer-instructions-20260914`, `codex/ger-held-viewer-20260914`, `codex/ger-active-viewer-20260914`;
   - `viewer-held-overlay`, `assistant/viewer-external-active`;
   - `docs/ger-agent-runbook-20260914`, `codex/remove-blocking-audits`;
   - `codex/parallel-scene-reservation-20260914`, `codex/missing-validation-policy-review-20260914`.
6. **Pending:**
   - Archive the conformant tasks as projects (section 6.2).
   - Non-NSC branches that may be proposed for deletion, with Vincent's OK: `wizard-art/codex-20260915`, `verify/*`, and GitHub copies of closed non-NSC branches (after a push).
   - **Keep** the NSC-053, NSC-017, NSC-073 and NSC-074 branches and worktrees.
7. **NSC-075** is being finished by the branch-recovery session:
   - Codex branch `codex/nsc075-eight-direction-20260916`, tip `a9109a380`, is under verification in `C:\nscrev\branch-verify`.
   - The fix commit `0d28b0bf5` handles stub `.meta` files importing as cubemaps.
   - Coordinate before touching it.
8. **Unmerged fixes that matter** (hand to the Pipeline Maintainer to port and review, not to merge blindly): see `nsc-pipeline-problems.md` P3, D2, D3, D4, D6, D7, E4.

---

## 9. Reporting

Examples for Vincent:
- "Branch `codex/nsc065-retained-art-review`: adds 8 door PNGs (renders: <folder>). Merge?"
- "Wave 5: 7 branches already in main; recorded as superseded and kept."
- "NSC-063 is conformant; archived to `C:\NSC\SuccessfullTasks\NSC-063`."
- "Need your go to push main (50 commits, all automation identities)."

Journal entry per branch: name, tip, verdict (superseded / merged / skipped / waiting), commits, tests and logs, archive ref, cleanup status.
