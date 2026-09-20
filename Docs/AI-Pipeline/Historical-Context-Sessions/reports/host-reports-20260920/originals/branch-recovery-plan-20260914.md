# Branch recovery plan (2026-09-14)

We recover unmerged branches one at a time: open it, verify what is good, then merge the good part into main.

## Starting point

- **main** is `96a6293c`, the same locally and on GitHub.
- **Branches:** 53 have commits whose changes are not on main. All are pushed to GitHub.
- **PRs:** 6 draft PRs exist (#128–#133). Nothing has been merged.
- **Codex** is out of usage until Sep 19, so no other agent writes to main while we work.

## Ground rules

- **One branch at a time.** Each branch has three points where I stop and wait for Vincent's go:
  1. after the inspection summary;
  2. before merging;
  3. before pushing.
- **Merge locally.** Push main with an exact-value lease (the sanctioned way to move main).
- **Never** use `gh pr merge`, never force-push without a lease, and never hand-merge Unity scene or prefab YAML.
- **Branches** are deleted only with Vincent's OK.

## Steps for each branch

1. **Open.**
   - The branch is already on GitHub. Open its draft PR if it doesn't have one yet.
   - The PR body lists the commits not on main, the files changed, and notes about duplicates or diagnostic commits.
2. **Inspect**, in the verification clone reset to current main:
   - Trial-merge the branch (`git merge --no-commit --no-ff`) and list any conflicts.
   - Diff exactly what the merge would add to main. If the diff is empty, the work already landed: close the PR as landed and stop here.
   - Name the task contract it serves (current revision). Flag any diagnostic or revert commits, and any duplicate or alternate branches.
   - **Output:** a short summary for Vincent covering what it changes, what looks good, what to drop, and the risks.
3. **Verify the good part.** How depends on the branch type:
   - **Gameplay code:**
     - Review against the current contract's acceptance criteria and gates.
     - Run the task's focused Edit Mode and Play Mode tests in Unity batchmode on the verification clone.
     - Run `taskcontrol validate` and `git diff --check`.
     - Add a human Play Mode check where a gate asks for one.
   - **Scene changes:**
     - Confirm the scene came from its builder, not hand edits.
     - If the scene conflicts with main, re-run the builder on the merged code instead of merging YAML.
     - Run the committed-scene tests, then have Vincent look in Unity.
   - **Art staged for review:**
     - Vincent's visual review comes first; that is what these branches were staged for.
     - Then check `.meta` GUIDs and duplicate assets.
     - Pick one branch out of any alternates.
   - **Pipeline code:** run the focused Python tests for the modules it changes.
   - **Superseded:** show that main already has the same or a later version, then close the PR with a comment.
4. **Merge into local main.**
   - Merge only the verified commits. Use the whole branch with `--no-ff`, or cherry-picks when dropping diagnostics or reverts.
   - Commit under a pipeline `.invalid` identity, then run `taskcontrol validate`.
5. **Push main** with the lease, when Vincent says. GitHub then marks the PR merged, or I close it with a note.
6. **Record** a journal line. Delivery evidence is recorded only if the branch completes the task's gates; that is a separate step and Vincent's call.
7. **Tidy.** Delete the branch locally and on GitHub, only with Vincent's OK.

## Verification environment

- **Clone:** `C:\nscrev\branch-verify`, cloned `--no-local` from the canonical repo with long paths on. Reuse it for every branch so Unity's Library cache stays warm.
- **Unity:**
  - Run batchmode against the clone, at the version in `ProjectSettings/ProjectVersion.txt`.
  - The canonical checkout stays open in the Editor, untouched.
  - The first import will be slow.
- **Evidence:** keep XML results and logs outside the repo. Record HEAD and tree, and check the tree is clean before and after, per the Unity testing policy.

## Queue

### Wave 1: probably already on main

These are quick checks that also prove the procedure works.

| # | Branch | Task | What it holds | Expectation |
|---|---|---|---|---|
| 1 | `codex/nsc054-ranged-attack-20260914` | NSC-054 | Projectile attack plus two test fixes | Likely landed squashed; NSC-054 is conformant |
| 2 | `codex/nsc042-saved-scene-proof-20260914`, `codex/nsc042-saved-scene-traversal-20260914` | NSC-042 | Saved-scene wall traversal tests | Likely superseded; NSC-042 is conformant |
| 3 | `codex/nsc089-current-main-20260914`, `codex/nsc090-current-main-20260914` | NSC-089/090 | "Implement NSC-089" | A commit with the same title is on main |
| 4 | `codex/nsc050-052-retained-stage-20260914` | NSC-050/052 | "Add door breach feedback" | A commit with the same title is on main |
| 5 | `codex/decomposition-contract-fixes-20260914` | Contracts | Contract edit validator and a restart contract fix | The contract fix is on main; the validator may be new |

### Wave 2: real gameplay work (highest value)

| # | Branch | Task | What it holds | Notes |
|---|---|---|---|---|
| 6 | `codex/nsc053-keep-distance-20260914` | NSC-053 | Keep-distance navigation and side-route fixes (12 commits, including diagnose/revert pairs) | Merge before NSC-017, because NSC-017 turns this component off and on |
| 7 | `codex/nsc017-locked-door-attack-20260914` | NSC-017 | Routes pursuing enemies to locked doors, breach timing, and test fixes (5 commits) | Check against contract revision 4 |
| 8 | `codex/nsc052-current-main-stage-20260914` (duplicate: `codex/nsc052-verification-20260914`) | NSC-052 | Crack stages connected to breach feedback, scene materialization, test fixes (6 commits) | Scene change |
| 9 | `codex/nsc051-final-main-20260914` (duplicate: `codex/nsc051-door-passability-20260914`) | NSC-051 | Passability on the five authored doors | Scene change |
| 10 | `codex/nsc032-current-main-recovery-20260914` | NSC-032 | Floor restart controller in the gameplay scene | Scene change |

### Wave 3: small visual and pipeline fixes

| # | Branch | Task | What it holds | Notes |
|---|---|---|---|---|
| 11 | `codex/nsc044-visual-tint-20260914` | NSC-044 | Mutes the Ruined Entry floor and rubble placeholders | Large scene diff; needs Vincent's look |
| 12 | `nsc089-checkout-recovery`, `codex/nsc089-managed-recovery` | Pipeline | Stale checkout recovery and managed Issue recovery guards | Python tests |
| 13 | `release/public-policy-scope-731` | Pipeline | One-line test scope fix | Test |

### Wave 4: art staged for Vincent's visual review

| # | Task | Branches | Plan |
|---|---|---|---|
| 14 | NSC-073 White Female northeast walk frames | `codex/nsc073-main-validation-20260914`, `assistant/NSC-073-current`, `codex/nsc073-ne-alternate-20260914`, `codex/nsc073-visual-stage-20260914`, `codex/nsc073-reuse-alt-20260914`, `codex/nsc073-alt-current-stage-20260914`, `assistant/nsc-073-pixellab` | Seven alternates of one fix. Review, pick one, close the rest |
| 15 | NSC-074 cardinal wizard walks | `codex/nsc074-current-review-20260914` (same tip as `codex/nsc074-exact-unity-20260914`), `assistant/NSC-074-current`, `codex/nsc073-074-current-review-20260914`, `assistant/nsc-074-cardinal-art` | Pick one. The 09-13 branch holds audit-script fixes |
| 16 | NSC-077 stationary enemies | `codex/nsc077-gameplay-visibility-20260914`, `codex/nsc077-current-main-review-20260914`, `codex/nsc077-stationary-enemies-20260914` | The first looks like a superset with the visibility fix |
| 17 | NSC-064 dungeon architecture art | `codex/nsc064-connections-20260914`, `codex/nsc064-main-review-20260914`, `codex/nsc064-pixellab-20260914` | The first holds selection, connection pieces and the joins doc |
| 18 | NSC-063 single-cleaver northeast idle | `codex/nsc063-melee-ne-single-cleaver-20260914` | Review |
| 19 | NSC-093 enemy eight-direction walk source | `codex/nsc093-current-main-review-20260914`, `codex/nsc093-pixellab-walk-20260914` | Duplicates; keep one |
| 20 | NSC-070 animator audit | `codex/nsc070-validation-20260914` | Audit plus a preserved review scene |
| 21 | NSC-061 source selection blocker | `codex/nsc061-source-review-20260914` | Doc only |

### Wave 5: two days ago, likely superseded

Confirm each one and close it.

| # | Branch | What it holds | Expectation |
|---|---|---|---|
| 22 | `assistant/room-nsc-045` (#133) | Old Bone Archive blockout | Main has a later version |
| 23 | `assistant/foreground-nsc-066-title-screen` (#130) | Title screen flow | Compare with main's title screen |
| 24 | `assistant/foreground-nsc-062-materialization` (#129), `assistant/review-wizard-lobby` (#131), `assistant/foreground-nsc-067-selection` (#132) | The same "prepare NSC-062 wizard materialization" commit on all three | One check covers all three |
| 25 | `assistant/nsc-075-builder-prep` (contains `assistant/nsc-075-integration-prep`), `assistant/cardinal-staging` | Eight-direction wizard prep | Compare with main |
| 26 | `assistant/task-nsc-070-wizard-animation-audit` | Adds an NSC-070 audit task | Likely superseded |
| 27 | `assistant/restored-meta-companion-fix`, `assistant/integrate-background-plus-decomp` | Small pipeline fixes | Check whether main already has them |
| 28 | `assistant-ci-boundary-20260912` (#128) | 35-commit orchestration integration line (364 files) | Do this last. Likely close it, and salvage individual fixes only if main lacks them |

The queue covers all 53 branches. Uncommitted changes inside worker checkouts are not covered. The known one is `C:\NSC\NSC\NSC-062`, which has 6 modified files from 09-12.
