# No Safe Circle: merge and resume plan (2026-09-16)

- Local main is `22955c5a8`, 50 commits ahead of origin, not pushed.
- Sources:
  - `resume-plan-research\branch-reconciliation.md`, covering all 115 unmerged branches;
  - `resume-plan-research\unfinished-work.md`, covering the 11 cut-off or open items.
- Claude re-checked every status below against git on 2026-09-16.
- Rules still apply:
  - one branch at a time;
  - verify merges in `C:\nscrev\branch-verify`;
  - save each tip under `refs/archive/` before deleting its branch;
  - never push without Vincent's go.

## Corrections to the handoff and the research

- **NSC-065 door art is already on main.**
  - `167a7f8e8` (9/14) added the 7 bonestone door sprites and the contact sheet.
  - `codex/nsc065-retained-art-review-20260914` now differs from main by one 8-line doc note. There is nothing to merge.
  - The sprites still need wiring into the rebuilt levels.
- **Four "unmerged" branches are already on main as cherry-picks with identical subjects:**
  - `codex/viewer-instructions-20260914` as `244e0b1b8`;
  - `codex/ger-active-viewer-20260914` as `223c89f85` and `cce02484a`;
  - `codex/missing-validation-policy-review-20260914` as `56e86c80d`;
  - `codex/nsc057-tooling-20260914` (DOTween and Signals) as `e1be57039` and `d8dbf0df7`.
- **The melee enemy has two cleavers facing north-east on main.** Its NE idle frame and all six NE walk frames show two; every other direction shows one. Claude checked this visually. The render is `resume-plan-research\melee_ne_check.png`.
- **The viewer test suite is broken on main today.** `python -m unittest Pipeline.AssistantControl.test_viewer` reports 57 tests, 4 failures and 16 errors.
- **NSC-077 is real unmerged work.** `codex/nsc077-stationary-enemies-20260914` adds 70 files: the StationaryEnemy scripts, prefabs and Play Mode tests. Main has no StationaryEnemy files.

## Phase 0: finish what is in flight

1. **NSC-075, eight-direction wizard movement.**
   - Verified in branch-verify at `664de19c2`:
     - Edit Mode 12/12 and Play Mode 20/20;
     - the builder's generated animation assets are identical on a second run (the binary scene still differs byte-wise);
     - the stack includes two builder fixes found during verification (texture shape and cookie import defaults).
   - **Found by Vincent's in-Unity check:** north and south were flipped. The camera (30, -45, 0) looks toward world -X +Z, but the classifier used X - Z as screen up.
     - The same inversion was already in main's four-direction code, so the diagonals were vertically flipped too: +X showed the north-east back view while moving down-right.
     - Fixed in branch-verify (uncommitted): vertical = Z - X, and the Play Mode test vectors were corrected to match. The tests could not catch this because they encoded the same inverted mapping.
   - **Vincent:** walk the 4 wizards in 8 directions in the open branch-verify Unity, close Unity, then say go.
   - **Claude:**
     - fast-forward main to `664de19c2` and write the journal entry;
     - close the NSC-075 family: `codex/nsc075-eight-direction-20260916`, `assistant/nsc-075-builder-prep`, `assistant/nsc-075-integration-prep`, and `assistant/cardinal-staging` after a re-diff;
     - close `codex/nsc070-validation-20260914`, which only carries a scene file;
     - write owner revisions for NSC-070 (32 states), NSC-068 AC-003 and NSC-062, so their four-direction wording doesn't read as broken.
2. **Pipeline bug found tonight.**
   - `run_crew.py unity_meta_bytes` writes GUID-only `.meta` files. Unity 6000.1 imports those as cubemap cookies.
   - **Codex:** make the crew write importer-complete metas, or give art builders one shared normalization step, and add a test.
   - Do this before the crew stages any more art. It will bite NSC-077 and any future PixelLab art.

## Phase 1: finish merging

1. **Archive successful tasks. Do not delete NSC-### branches.** Vincent's rule, 2026-09-16.
   - A task is successful when `taskcontrol states` reports it `conformant`, backed by a `DEL-*.json` delivery record.
   - Archive each successful task as a usable Unity project at `C:\NSC\SuccessfullTasks\<TASK-ID>`, never overwriting an existing one. The project is a standalone clone at the record's `integrated_commit`, with the task's branches, its Library copied from an existing worktree when there is one, and a receipt. NSC-042 is the precedent.
   - Ready now, since they are conformant and still have branches:
     - NSC-003, NSC-005, NSC-011 and NSC-028;
     - NSC-063, once Vincent decides on the north-east double cleaver. It is conformant because its contract only required Claude's art review; Vincent's in-engine check was assigned to NSC-077.
   - Later: NSC-053, 017, 054, 073, 074, 093 and 075 are archived once Phase 2.3 writes their delivery records.
   - All NSC branches and worktrees stay in the canonical repo.
   - The 10 NSC attempt branches deleted on 9/15 still exist under `refs/archive/codex/*` and can be restored as branches.
   - Non-NSC branches are deleted only with Vincent's explicit OK. That covers the stale pipeline cluster, the 6 coursework branches (`assignment-*`, `milestone-2a-current-gdd-rag`) and `demo/gauntlet-20260916`. Never merge the demo branch: it breaks NSC-042 and grafts rehearsal tasks.
2. **Three clean merges**, each verified first:
   1. `assistant/integrate-background-plus-decomp`: Windows Docker bind-mount path fix. Useful now that Docker jobs are running.
   2. `assistant/restored-meta-companion-fix`: lets restored candidates carry deterministic `.meta` files. Review it together with Phase 0.2.
   3. `codex/nsc061-source-review-20260914`: one doc recording the original hat defect.
3. **Visual picks for Vincent.**
   1. NSC-064 dungeon architecture: `codex/nsc064-connections-20260914`, the superset of its two siblings. Claude renders a contact sheet.
   2. The melee north-east double cleaver. If Vincent confirms it's a defect, Claude runs one bounded PixelLab fix for the NE idle frame and 6 NE walk frames. The 9/14 single-cleaver idle candidate on `codex/nsc063-melee-ne-single-cleaver-20260914` is a starting point.
   3. `codex/nsc044-visual-tint-20260914`: don't merge the 29,000-line scene diff. Carry the floor and rubble tint into the Ruined Entry rebuild.
4. **Code review.**
   1. NSC-077 stationary enemies.
      - Codex ports the branch onto main after NSC-075 lands, because both touch `DoorPrototype.unity`.
      - Claude reviews the port. The builder rebuilds the scene, then the Unity tests run.
      - Close its two scene-only siblings.
   2. `assistant/foreground-nsc-067-selection`: a 5-minute diff of its `WizardGameEntryPlayModeTests.cs` against main, then close it.
5. **Stale branches.** 15 pipeline branches from 8/28 to 9/5 (69 to 212 main commits behind), plus the superseded NSC-070 rev 1 contract branch. Close them with archive refs unless Vincent wants something from one.
6. **Push main (Vincent's call).** Afterwards, delete the GitHub copies of the closed branches and close draft PRs #128 to #133.

## Phase 2: resume where Codex stopped

| # | Item | Status, verified 9/16 | Next step | Who |
|---|---|---|---|---|
| 1 | Viewer regression suite | Fix `c12f70287` is in `C:\NSC\AssistantControlViewerRegression-20260913` on an old base. Main still fails (57 tests: 4 failures, 16 errors). | Port the fix onto current main until the suite is green; review; merge. | Codex, then Claude |
| 2 | Decomposition reliability (accepted mid-dev review fixes) | Finished stack `throughput/decomposition-final-integration` @ `4fd54b8c` in `C:\nscrev\final-integration` passed 33/34 suites on 9/14. None of it is on main. The cut-off work-in-progress in `C:\nscrev\codex-revision-review-fixes-20260913` is redundant. | Standing rule: Astra reviews, Codex integrates. Vincent asks Astra or waives the review; then Codex rebases and integrates. | Vincent, Astra, Codex |
| 3 | Completion evidence for NSC-061/062/067/068/069 | None has an evidence record on main. | After NSC-075 lands, Codex gathers evidence against current main and Claude writes the evidence records. | Codex, Claude |
| 4 | "23 should be completed" recount | Its three small fixes already landed as cherry-picks. | Claude recounts derived task states after #3 and resyncs the viewer. | Claude |
| 5 | NSC-093 melee north-east double cleaver | Confirmed on main. | See Phase 1.3.2. | Vincent, Claude |
| 6 | NSC-066 title screen | The owner revision was never written; the contract still names the wrong builder file. | Claude writes the revision: global builder, chase backdrop cycling each wizard against each enemy, keep the taglines, no solid panel, SpaceInvaders as the reference. Codex implements; Vincent's visual gate. | Claude, Codex, Vincent |
| 7 | NSC-015 decomposition returned "revise" | The split weakened the parent's validation gates. | Codex redrafts; Claude reviews and applies; Vincent approves the plan. This gates NSC-033. | Codex, Claude, Vincent |
| 8 | Design decisions for NSC-007, 008, 009, 030, 078 | The evidence pack is done (`design-decisions\seven-task-evidence.md`). No decision has been written. | Claude decides and commits owner revisions; Codex implements afterwards. This is the biggest block of work that can start now. | Claude, then Codex |
| 9 | NSC-085 side-chamber wing, NSC-088 Spectral Decoy | Approved, but both contradict the current GDD text. | Claude drafts GDD amendments and contract revisions; Vincent approves the wording. | Claude, Vincent |
| 10 | Level rebuild, NSC-044 to 049 | Waiting. | Include the floor visual fix, door sorting (NSC-039), wiring the bonestone door sprites, and the Ruined Entry tint. | Codex, Vincent |
| 11 | Semi-autonomous admission (`claude/add-semi-autonomous-admission`, parked since 9/5) | Parked. | Stays parked until autonomous runs are clean. | Vincent |

## Suggested order

1. **Tonight:**
   - Vincent's NSC-075 check, then landing it;
   - the cleanup script;
   - the three clean merges.
2. **Next:** two Codex jobs in parallel, since they touch different files: Phase 0.2 (the meta fix, in `Pipeline/ExecutionCrew`) and Phase 2.1 (the viewer suite, in `Pipeline/AssistantControl`).
3. **Then, in order:**
   - the NSC-064 pick and the melee NE fix;
   - the NSC-077 port;
   - the design decisions and the NSC-066 revision;
   - the evidence audit and recount;
   - the push.
4. **Waiting on others:** Astra, for Phase 2.2.

## Not in this plan

- The TenTask demo work from early 9/16, in a separate repo: `C:\NSC\TenTaskFinalIntegration-20260905`, branch `demo/run-20260916`, handoff `tentask-demo-handoff-20260916.md`.
- `demo/gauntlet-20260916` in the canonical repo.
- Decide on both after the demo.
