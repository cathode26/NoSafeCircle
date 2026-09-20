# Branch reconciliation report

Generated 2026-09-16 by a read-only git inventory pass over
`C:\NSC\NSC\NoSafeCircle`. Local `main` = `22955c5a8`, unpushed (`origin/main` = `96a6293c4`).

**Scope.** `git branch --no-merged main` (which only lists `refs/heads/*`, so `refs/archive/*` is
already excluded) returns **115 branches**. Every one of them is accounted for exactly once
in the buckets below. This does *not* include branches that live only in separate clones/checkouts
outside this repo (e.g. `C:\NSC\AssistantControlViewerRegression-20260913`,
`C:\nscrev\codex-revision-review-fixes-20260913`, `C:\nscrev\final-integration`,
`C:\NSC\ClaudeSemiAutonomous-20260905`) -- those have no `refs/heads/*` entry in this repo at all
(verified with `git rev-parse --verify`), so `git branch` cannot see them. This folder's sibling
file, `unfinished-work.md` (already present when this report was written, not created by this
pass), covers that adjacent territory in detail and is worth reading alongside this report --
several of its findings (NSC-066's superseded implementation, the NSC-093 north-east cleaver
question) directly corroborate what this inventory found independently.

**Method.** For each branch: tip SHA/date/author, commit count vs main, `git cherry main <branch>`
(patch-id equivalence), and `git merge-tree --write-tree main <branch>` (exit code, conflict paths,
diff stat against the result). A branch is **ALREADY-LANDED/SUPERSEDED** when its merge tree is
byte-identical to main's tree, or when `git cherry` shows every commit as already patch-equivalent
(`-`) -- confirmed in every spot-check by comparing the actual conflicting blobs directly
(`git rev-parse main:<path>` vs `git rev-parse <branch>:<path>`): where cherry said equivalent, the
files really were byte-identical or the conflicting files were independently-added duplicates of
content main got some other way. Three published prior reports
(`C:\nscrev\reports\branch-recovery\waves45-inventory.md`,
`C:\NSC\nsc-codex-0913-0914-digest.md`, `Desktop\nsc-codex-0913-0914-context.md`) were computed
against older `main` snapshots (`03804a785` / `9a3d22c56`); their conclusions are cited below only
where re-verified against the current tip, and several are now superseded by main's own progress
(e.g. NSC-057/060 DOTween-and-mana-feedback work the older reports still flagged "to evaluate" is
now fully patch-equivalent, i.e. landed).

## Counts per bucket

| Bucket | Count |
|---|---|
| ALREADY-LANDED / SUPERSEDED | 66 |
| PIPELINE / VIEWER / CONTRACTS | 20 |
| DONE-THIS-WEEK | 10 |
| OUT-OF-SCOPE | 7 |
| NEEDS-VISUAL-PICK | 5 |
| NEEDS-CODE-REVIEW | 4 |
| MERGE-CANDIDATE | 3 |

## DONE-THIS-WEEK (10)

These are the branches the task brief already identifies as landed this week, kept
here (rather than folded into ALREADY-LANDED) so the family groupings stay visible.

- **The seven NSC-073 branches** (hat-fix motion candidates): `assistant/NSC-073-current`,
  `assistant/nsc-073-pixellab`, `codex/nsc073-alt-current-stage-20260914`,
  `codex/nsc073-main-validation-20260914`, `codex/nsc073-ne-alternate-20260914` (all five below,
  still unmerged but content-superseded) plus `codex/nsc073-reuse-alt-20260914` and
  `codex/nsc073-visual-stage-20260914`, both **already ancestors of main** (verified with
  `git merge-base --is-ancestor`), so git itself excludes them from the 115-branch count above.
- **The five NSC-074 branches** (cardinal-walk source audit): `codex/nsc074-current-review-20260914`,
  `codex/nsc074-exact-unity-20260914`, `codex/nsc073-074-current-review-20260914`,
  `assistant/nsc-074-cardinal-art` (all four below) plus `assistant/NSC-074-current`, already an
  ancestor of main and excluded from the count.
- **The two NSC-093 branches**: `codex/nsc093-pixellab-walk-20260914` (below, byte-identical merge
  tree to the one that landed) plus `codex/nsc093-current-main-review-20260914`, already an ancestor
  of main.
- **NSC-053 and NSC-017** (`codex/nsc053-keep-distance-20260914`,
  `codex/nsc017-locked-door-attack-20260914`): both already ancestors of main, so neither appears
  anywhere in this report's 115. Their branch refs and worktrees (plus `verify/nsc017-locked-door-20260915`,
  `verify/nsc053-keep-distance-20260915`) still exist and are listed in the cleanup section.



| Branch | Tip | Date | What it adds / why superseded | Conflicts | Recommended action |
|---|---|---|---|---|---|
| `assistant/NSC-073-current` | `ae91820c2` | 2026-09-13 | One of several hat-fix motion candidates (variant A, per prior review notes). Superseded: Vincent picked a different variant (`codex/nsc073-reuse-alt-20260914`, merged as `18089b060`). Directly confirmed patch-equivalent to current main (`git cherry`: all '-') -- its content already landed some other way, even though its own tree is not a literal match to the winning branch's tree. | 3 | No action -- already landed this week. Delete branch + worktree once Vincent confirms. |
| `assistant/nsc-073-pixellab` | `be3ac9548` | 2026-09-13 | One of the NSC-073 hat-fix candidate branches. Patch-equivalent to current main (`git cherry`: all '-'); safe to close even though its raw tree differs from the other NSC-073 variants (each carries slightly different unrelated history alongside the same landed hat-fix content). | 3 | No action -- already landed this week. Delete branch + worktree once Vincent confirms. |
| `assistant/nsc-074-cardinal-art` | `a0602783f` | 2026-09-13 | Name is misleading -- diff carries zero art files, only registry/task-graph churn (RESOURCE_GROUPS.yaml, WORK_ID_MAP.json, authoritative_validation_policy.json) and one test file, all superseded by main's own subsequent edits to those same files. | 4 | No action -- already landed this week. Delete branch + worktree once Vincent confirms. |
| `codex/nsc073-074-current-review-20260914` | `9cf7ae95f` | 2026-09-14 | The pre-reconciled NSC-073+074 combo Vincent's memory explicitly rules out (carries hat variant A, not the chosen variant C). | 3 | No action -- already landed this week. Delete branch + worktree once Vincent confirms. |
| `codex/nsc073-alt-current-stage-20260914` | `6abb92b73` | 2026-09-14 | One of the NSC-073 hat-fix candidate branches. Patch-equivalent to current main (`git cherry`: all '-'); safe to close. | 2 | No action -- already landed this week. Delete branch + worktree once Vincent confirms. |
| `codex/nsc073-main-validation-20260914` | `911e66f6c` | 2026-09-13 | One of the NSC-073 hat-fix candidate branches. Patch-equivalent to current main (`git cherry`: all '-'); safe to close. | 3 | No action -- already landed this week. Delete branch + worktree once Vincent confirms. |
| `codex/nsc073-ne-alternate-20260914` | `48cc3e653` | 2026-09-13 | One of the NSC-073 hat-fix candidate branches. Patch-equivalent to current main (`git cherry`: all '-'); safe to close. | 3 | No action -- already landed this week. Delete branch + worktree once Vincent confirms. |
| `codex/nsc074-current-review-20260914` | `5b8c4634b` | 2026-09-14 | Pre-reconciled NSC-074 combo carrying hat variant A. Superseded by the actual NSC-074 merge (`22955c5a8`, from assistant/NSC-074-current) stacked on the variant-C hat fix. | 2 | No action -- already landed this week. Delete branch + worktree once Vincent confirms. |
| `codex/nsc074-exact-unity-20260914` | `5b8c4634b` | 2026-09-14 | Same tip as codex/nsc074-current-review-20260914 (duplicate). | 2 | No action -- already landed this week. Delete branch + worktree once Vincent confirms. |
| `codex/nsc093-pixellab-walk-20260914` | `d23987945` | 2026-09-14 | Byte-identical merge tree to codex/nsc093-current-main-review-20260914 (already merged to main as 7d8d98361/981002959). | 1 | No action -- already landed this week. Delete branch + worktree once Vincent confirms. |

## MERGE-CANDIDATE (3)

Small, clean (`git merge-tree` exit 0, zero conflicts), pipeline-only changes. Safe to merge directly; verify each with its own test file after merging.


| Branch | Tip | Date | What it adds / why superseded | Conflicts | Recommended action |
|---|---|---|---|---|---|
| `assistant/integrate-background-plus-decomp` | `8d8ae6cd0` | 2026-09-13 | Clean merge (no conflicts). Real unique content is exactly 2 files: `Pipeline/AssistantControl/docker_workers.py` (+`test_docker_workers.py`) -- adds `_canonical_host_path()` to recognize Docker Desktop's `/host_mnt/c/...`-style translations of a Windows bind-mount source as the same path as `C:\...`, so worker-container-ownership verification doesn't false-negative on Windows. Pipeline-only, no Unity/game files. Directly relevant given Docker-based Codex workers are in active use (the running NSC-075 job). | 0 | Merge directly onto main (clean, small, no conflicts); run its own test file first. |
| `assistant/restored-meta-companion-fix` | `807bd7b86` | 2026-09-13 | Clean merge (no conflicts). Real unique content is exactly 2 files: `Pipeline/AssistantControl/assistant_restored_candidate.py` (+ its test) -- lets a restored candidate's new-file scope include a deterministic Unity `.meta` companion for each new file, validated against `unity_meta_bytes()` rather than rejected as out-of-scope. Pipeline-only. | 0 | Merge directly onto main (clean, small, no conflicts); run its own test file first. |
| `codex/nsc061-source-review-20260914` | `cc403ce2f` | 2026-09-14 | Clean merge (no conflicts). Adds one doc, `Docs/Art/Wizard/NSC-061_SOURCE_REVIEW_20260914.md`: the original written record of the exact defect NSC-073 was created to fix (feminine-light NE walk frames 004/005 losing the hat). Harmless to add for the paper trail; purely historical now that the fix landed. | 0 | Merge directly onto main (clean, small, no conflicts); run its own test file first. |

## NEEDS-VISUAL-PICK (5)

Art/content candidates where Vincent needs to choose or approve before anything merges.


| Branch | Tip | Date | What it adds / why superseded | Conflicts | Recommended action |
|---|---|---|---|---|---|
| `codex/nsc044-visual-tint-20260914` | `1a89f35b9` | 2026-09-14 | Rewrites `Assets/Scenes/Rooms/RuinedEntry.unity` wholesale (~29,000 line scene diff, reported here as 14571+/14398-) to mute the blockout floor/rubble placeholders. Deliberately skipped in the 2026-09-15 wave-3 merge because Ruined Entry is not_delivered and gets rebuilt from `RoomSceneComposer`/its scene builder -- never merge scene YAML directly. If the tint intent is still wanted, re-express it as a builder change, not by taking this diff. | 0 | Do not merge the scene YAML. If the floor/rubble tint is still wanted, re-implement via the room's scene builder. |
| `codex/nsc063-melee-ne-single-cleaver-20260914` | `01e3b8ffd` | 2026-09-14 | A rejected PixelLab exploration for NSC-063's melee enemy (README explicitly includes `rejected_first_inpaint.png`). NSC-063 itself is already resolved on main (its Walk sprites are the melee/ranged art already merged). Low-value; keep only if Vincent wants to revisit the single-cleaver weapon silhouette. Related: a same-day companion inpaint against this character's static reference image did land as documented in this folder's unfinished-work.md item 5, which separately flags that the double-cleaver defect may still be visible in the merged north-east walk cycle -- a Vincent visual check, unrelated to whether this specific branch merges. | 0 | Low priority; show Vincent only if he wants to revisit the melee weapon silhouette. |
| `codex/nsc064-connections-20260914` | `b589afbd7` | 2026-09-14 | Confirmed ancestor-superset of both codex/nsc064-main-review-20260914 and its duplicate codex/nsc064-pixellab-20260914 (same tip). Adds 10 more architecture-kit PNGs (corner/doorway/wall-brick-ns/wall-end-cap) and a much longer PIXELLAB_GENERATION.md (432 vs 209 lines) on top of what main-review/pixellab carry. This is the one to show Vincent for the NSC-064 dungeon-architecture visual pick; clean merge (mt exit 0), no conflicts. | 0 | Show Vincent this one first (it's the superset of the NSC-064 trio); clean merge if picked. |
| `codex/nsc064-main-review-20260914` | `f99d419cf` | 2026-09-14 | Subset of codex/nsc064-connections-20260914 (confirmed ancestor via `git merge-base --is-ancestor`). Its merge-tree result against main is oid-identical to codex/nsc064-pixellab-20260914's (different tip SHAs, same net content once merged). Superseded by connections for review purposes -- keep for reference only. | 0 | Superseded by codex/nsc064-connections-20260914 for review purposes; no separate action. |
| `codex/nsc064-pixellab-20260914` | `7924beb78` | 2026-09-14 | Different tip SHA than codex/nsc064-main-review-20260914, but its merge-tree result against main is oid-identical (`2eceec34...`) -- an exact functional duplicate. | 0 | Duplicate of codex/nsc064-main-review-20260914; no separate action. |

## NEEDS-CODE-REVIEW (4)

Unique code with real conflicts or of large size, or that needs a human diff before any decision. The three NSC-077 branches are one family (see notes); the fourth is independent.


| Branch | Tip | Date | What it adds / why superseded | Conflicts | Recommended action |
|---|---|---|---|---|---|
| `assistant/foreground-nsc-067-selection` | `edc2526bb` | 2026-09-12 | 139-conflict wizard-art footprint largely matching the already-superseded foreground-nsc-062/review-wizard-lobby snapshot, BUT its own commit adds `WizardGameEntryPlayModeTests.cs`. Direct blob compare shows main's current `WizardGameEntryPlayModeTests.cs` has a DIFFERENT hash than this branch's version (main's is independently written) -- so nothing to salvage automatically, but worth a 5-minute human diff of that one file before closing, since main's WizardSelection/WizardGameEntry test scaffolding may have grown from a different angle than this branch took. | 139 | Before closing, diff WizardGameEntryPlayModeTests.cs against main's version by hand (5 minutes) in case main's angle missed something this branch covered. |
| `codex/nsc077-current-main-review-20260914` | `cb4bf04c4` | 2026-09-14 | Ancestor of codex/nsc077-gameplay-visibility-20260914. Only diff from main is the scene file. Same treatment as gameplay-visibility -- rebuild, don't merge YAML. | 1 | No separate merge -- only unique content is the scene file. Superseded by gameplay-visibility in the same chain. |
| `codex/nsc077-gameplay-visibility-20260914` | `a9c11258e` | 2026-09-14 | current-main-review is its ancestor (chain: current-main-review -> gameplay-visibility). Only remaining diff from main is `Assets/Scenes/DoorPrototype.unity` -- per project rule, never merge a scene file; rebuild it from the builder after taking stationary-enemies' code/art. No separate action needed beyond that rebuild. | 1 | No separate merge -- only unique content is the scene file. Rebuild from the builder after taking stationary-enemies. |
| `codex/nsc077-stationary-enemies-20260914` | `c374b5282` | 2026-09-14 | The real NSC-077 content: 19 files differ from main, all Art/Enemies idle-sprite .meta files (GUIDs) plus the review scene -- the 16 idle PNGs themselves are already BYTE-IDENTICAL to what's on main (confirmed by blob hash). What is genuinely missing from main is the placement/integration code: no 'StationaryEnemy' controller or equivalent found anywhere on main, and NSC-077 AC-004 specifically requires a stationary, presentation-only placement (no pursuit/AI), which is a different shape than the pursuit-capable enemies already on main. Needs a code read of the prefab/placement C# in this branch, not just an art pick. | 19 | Read the placement/prefab C# by hand; art is already on main so only the integration code is in question. Rebuild the review scene afterward rather than merging it. |

## PIPELINE / VIEWER / CONTRACTS (20)

Tooling, the viewer, `Tasks/*.yaml`, or `Pipeline/*`, where main either already has
newer versions (the stale 11-branch cluster below) or where the branch is actively tied up in the
running NSC-075 job (hold, don't touch/merge in parallel).


| Branch | Tip | Date | What it adds / why superseded | Conflicts | Recommended action |
|---|---|---|---|---|---|
| `assistant/cardinal-staging` | `b1e70b5ec` | 2026-09-13 | Per the task brief, likely covered by assistant/nsc-075-builder-prep (the base the running NSC-075 job started from). Direct check: none of its 5 conflicting files (WizardArtIntegrationTests.cs, WizardCardinalSourceAuditTests.cs, RESOURCE_GROUPS.yaml, WORK_ID_MAP.json, authoritative_validation_policy.json) are byte-identical to main, so it does carry some independent edits -- but they read as task-graph/test-registry bookkeeping around the NSC-074 handoff, not new gameplay code. Hold until NSC-075 lands, then check by diff whether anything survives; do not merge in parallel with the running job (both touch WizardArtIntegrationTests.cs). | 5 | Hold until NSC-075 lands (shares WizardArtIntegrationTests.cs with the running job); then diff to see if anything survives. |
| `assistant/nsc-075-builder-prep` | `5a139770e` | 2026-09-13 | **This is the exact branch the running Codex NSC-075 job started from** (`C:\nscrev\nsc075-codex`, branch `codex/nsc075-eight-direction-20260916`). Do not touch, merge, or base other work on top of it while that job is active -- it will be absorbed or superseded when NSC-075 lands. Its only conflict, `WizardArtIntegrationTests.cs`, is exactly the NSC-075 collision file. | 1 | DO NOT TOUCH while the NSC-075 Codex job is running (it started from this branch). Revisit only after that job lands or is abandoned. |
| `assistant/nsc-075-integration-prep` | `ba2a16bd4` | 2026-09-13 | Per the task brief, covered by assistant/nsc-075-builder-prep. Clean merge, 2 files (+146/-42), 'Add NSC-075 eight-direction classifier tests' -- but merging it separately now would race the in-flight NSC-075 job on the same test file. Hold until NSC-075 lands, then check whether anything here wasn't already carried forward. | 0 | Hold until NSC-075 lands, then diff against the result before deciding whether anything survives. |
| `assistant/task-nsc-070-wizard-animation-audit` | `f14404e92` | 2026-09-12 | Adds `Tasks/NSC-070.yaml` at contract revision 1 ('Four-Wizard Directional Animation Audit and Repair'). Main already has NSC-070 at revision 2 ('Four-Wizard Directional Animation State Repair') -- a newer contract revision has already superseded this one. Safe to close. | 4 | Hold / low priority -- see note. |
| `codex/batch-history-identity-validation` | `18c867c33` | 2026-09-05 | Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 67 | Hold / low priority -- see note. |
| `codex/bulk-retired-completion-filter` | `0e8a06392` | 2026-09-05 | Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 67 | Hold / low priority -- see note. |
| `codex/combine-orchestration-scale` | `2bc1a2963` | 2026-09-05 | Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 73 | Hold / low priority -- see note. |
| `codex/fix-required-decomposition-resume-route` | `18c867c33` | 2026-09-05 | Same tip as codex/batch-history-identity-validation (exact duplicate). Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 67 | Hold / low priority -- see note. |
| `codex/integrate-scale-prereqs-0e8a` | `ebaa5e5bb` | 2026-09-05 | Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 68 | Hold / low priority -- see note. |
| `codex/integrate-thousand-readiness-ebaa` | `827cf4539` | 2026-09-05 | Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 74 | Hold / low priority -- see note. |
| `codex/integrate-thousand-readiness-ebaa-v2` | `2fef3dc68` | 2026-09-05 | Same tip as codex/source-admission-snapshot-perf (exact duplicate). Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 73 | Hold / low priority -- see note. |
| `codex/nsc070-validation-20260914` | `7680cf3af` | 2026-09-14 | Both commits patch-inequivalent, but the only real diff from main is `Assets/Scenes/DoorPrototype.unity` -- per project rule, never merge a scene file. NSC-070 (Four-Wizard Directional Animation State Repair) is already at contract revision 2 on main and is squarely in the area the running NSC-075 job is rebuilding (wizard animation state). Hold; let NSC-075 subsume it, then rebuild the scene from the builder if anything is still missing. | 1 | Hold -- overlaps the area NSC-075 is rebuilding; only unique content is a scene file (rebuild, don't merge YAML). |
| `codex/source-admission-snapshot-perf` | `2fef3dc68` | 2026-09-05 | Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 73 | Hold / low priority -- see note. |
| `docs/context-2026-08-31-live-gauntlet` | `181c7a820` | 2026-08-31 | Adds 388 lines to `Docs/AI-Pipeline/Historical-Context-Sessions/CURRENT_CONTEXT.md` as of 2026-08-31. This is a rolling context snapshot that main has certainly rewritten many times since (it's the same kind of document as this very report's neighboring memory files) -- stale, not worth merging as 'current' content. | 1 | Hold / low priority -- see note. |
| `fix/latest-effective-pr-checks` | `fc157eba6` | 2026-08-29 | Same divergence point as pipeline/history-identity-migration-v2 (`2cf2806ab`, 212 subsequent main commits in the area). 59 commits ahead, but all patch-equivalent to current main (`git cherry`: every commit '-') -- effectively landed in substance already; conflicts are add/add noise against a heavily-rewritten area. Kept in this bucket rather than folded into the plain LANDED table only because of its unusual size and age -- a human skim is cheap insurance given how large it is. | 15 | Hold / low priority -- see note. |
| `fix/retired-decomposition-completion` | `0b173cec5` | 2026-09-05 | Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 68 | Hold / low priority -- see note. |
| `fix/structured-synthetic-pump` | `2cee98528` | 2026-09-04 | Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 47 | Hold / low priority -- see note. |
| `pipeline/history-identity-migration-v2` | `cb66ec904` | 2026-08-29 | Diverges from main at `2cf2806ab` (2026-08-28); main has made 212 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since. 86 commits ahead, all patch-inequivalent, 20 conflicts. Pre-dates the current pipeline architecture; likely not worth reconciling line by line. | 20 | Hold / low priority -- see note. |
| `review/extract-production-scheduler-factory` | `c552a62b7` | 2026-09-04 | Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 47 | Hold / low priority -- see note. |
| `review/orchestration-gauntlet-followup` | `7a8ba026f` | 2026-09-04 | Shares merge-base `73fae3818` (2026-09-04) with 10 sibling branches below; main has made 69 subsequent commits to Pipeline/TaskReviewAgent + Pipeline/AssistantControl since they diverged. All commits are patch-inequivalent (cherry: all '+') and conflicts run 50-75 files deep, entirely inside paths main has rewritten repeatedly since. Very unlikely to be worth reconciling line-by-line; treat as an abandoned early-September wave unless Vincent specifically wants something out of one of them. | 56 | Hold / low priority -- see note. |

## ALREADY-LANDED / SUPERSEDED (66)

Confirmed already on main in substance -- either the merge tree is byte-identical
to main's tree, or every commit is patch-equivalent (`git cherry` all `-`), spot-checked against
actual blob content where the merge-tree still reported conflicts (typically independent add/add
duplicates: both main and the branch added the same file separately, sometimes with different
`.meta` GUIDs, after diverging). Safe to close without merging once Vincent is ready; see the
worktree-cleanup section for what that unblocks.


| Branch | Tip | Date | What it adds / why superseded | Conflicts | Recommended action |
|---|---|---|---|---|---|
| `assistant-ci-boundary-20260912` | `8af9a0940` | 2026-09-12 | 35 commits, 0 patch-equivalent individually, but its tip is the same 'assistant-control: integrate direct game-task orchestration' subject as assistant-control-main-20260912 (1 commit, already patch-equivalent) -- this is the pre-squash history of the same effort. All 51 conflicts are add/add on Pipeline/AssistantControl, Pipeline/TaskReviewAgent and .github/workflows paths main has independently rewritten many times since (see the stale pipeline-scale cluster below). Superseded. | 51 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant-control-main-20260912` | `b5718a228` | 2026-09-12 | All commits patch-equivalent to main (`git cherry main assistant-control-main-2` shows only '-'). Conflicts (44) are add/add duplicates of content main already has independently: CONFLICT(44): Pipeline/AssistantControl[27], Pipeline/TaskReviewAgent[4], Pipeline/ExecutionCrew[3], Docs/AI-Pipeline[2], Pipeline/TaskReviewAgent/GauntletView/tests[2] | 44 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/NSC-060` | `b0e03b511` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main NSC-060` shows only '-'). Conflicts (4) are add/add duplicates of content main already has independently: CONFLICT(4): Assets/NoSafeCircle/DoorPrototype[1], Assets/NoSafeCircle/DoorPrototype/Scripts[1], Docs/Engineering[1], ProjectSettings[1] | 4 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/NSC-089-editmode-path` | `2471f8dab` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main NSC-089-editmode-path` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Assets/NoSafeCircle/DoorPrototype/Editor[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/enemy-eight-direction-contract` | `4183ae0a1` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main enemy-eight-direction-co` shows only '-'). Conflicts (2) are add/add duplicates of content main already has independently: CONFLICT(2): Pipeline/TaskGraph[1], Tasks[1] | 2 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/fix-exact-worker-scope` | `b0395709c` | 2026-09-12 | All commits patch-equivalent to main (`git cherry main fix-exact-worker-scope` shows only '-'). Conflicts (2) are add/add duplicates of content main already has independently: CONFLICT(2): Pipeline/AssistantControl[1], Pipeline/TaskReviewAgent[1] | 2 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/foreground-nsc-062-materialization` | `3f99eff7d` | 2026-09-12 | 169-conflict wizard-art footprint (32 Generated .anim clips + 128 PixelLab standing/walk .meta files), all add/add against paths main has since regenerated via NSC-073/074. Its own journal (carried in the diff) records the candidate as blocked on human review, never approved. Superseded. | 169 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/foreground-nsc-066-title-screen` | `1be73b24c` | 2026-09-12 | Its own unique commit is 'Implement NSC-066 title screen flow' (`d17d07aa2`). Direct blob compare: `TitleScreenController.cs` is BYTE-IDENTICAL to main's (main added the same file 2026-09-12 19:54, 5 minutes before this branch's tip) -- so the controller already landed via a different commit path. The only real differences left are `DoorPrototypeSceneBuilder.cs` and the scene, which have simply moved on since. Per the parallel research in this same folder's unfinished-work.md (item 6), NSC-066 is scheduled for a fresh owner-contract revision anyway (the current contract locks the wrong builder file) and this implementation still carries the solid background panel Vincent wants removed -- do not resurrect it, let the NSC-066 revision produce a new implementation. | 2 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/integrate-nsc-070` | `16ecdb2f4` | 2026-09-12 | All commits patch-equivalent to main (`git cherry main integrate-nsc-070` shows only '-'). Conflicts (3) are add/add duplicates of content main already has independently: CONFLICT(3): Pipeline/TaskGraph[2], Pipeline/TaskReviewAgent[1] | 3 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/nsc-046-chapel` | `c6cad1cab` | 2026-09-13 | All commits patch-equivalent to main (`git cherry main nsc-046-chapel` shows only '-'). Conflicts (3) are add/add duplicates of content main already has independently: CONFLICT(3): Assets/NoSafeCircle/DoorPrototype/Editor/Rooms[1], Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms[1], Assets/Scenes/Rooms[1] | 3 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/nsc-047-vault` | `6bc4ccae3` | 2026-09-13 | All commits patch-equivalent to main (`git cherry main nsc-047-vault` shows only '-'). Conflicts (3) are add/add duplicates of content main already has independently: CONFLICT(3): Assets/NoSafeCircle/DoorPrototype/Editor/Rooms[1], Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms[1], Assets/Scenes/Rooms[1] | 3 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/nsc-048-final` | `389e4e525` | 2026-09-13 | All commits patch-equivalent to main (`git cherry main nsc-048-final` shows only '-'). Conflicts (4) are add/add duplicates of content main already has independently: CONFLICT(4): Assets/NoSafeCircle/DoorPrototype/Editor/Rooms[1], Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms[1], Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms[1], Assets/Scenes/Rooms[1] | 4 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/nsc-070-runtime-stability` | `899af1c60` | 2026-09-13 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/review-wizard-lobby` | `651fd6298` | 2026-09-12 | 168-conflict wizard-art footprint, same stale NSC-062-era wizard materialization snapshot as foreground-nsc-062-materialization (different GUIDs, add/add conflicts on every Generated .anim and PixelLab standing .meta). No unique gameplay logic found. Superseded by the NSC-073/074/075 wizard art line now on main. | 169 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/review-wizard-rooms` | `55974fab1` | 2026-09-13 | All commits patch-equivalent to main (`git cherry main review-wizard-rooms` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Assets/Scenes[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/room-composition-a` | `f95f5d5ee` | 2026-09-13 | All commits patch-equivalent to main (`git cherry main room-composition-a` shows only '-'). Conflicts (4) are add/add duplicates of content main already has independently: CONFLICT(4): Assets/Scenes/Rooms[2], Assets/NoSafeCircle/DoorPrototype/Editor/Rooms[1], Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms[1] | 4 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/room-composition-b` | `5279e1ae2` | 2026-09-13 | All commits patch-equivalent to main (`git cherry main room-composition-b` shows only '-'). Conflicts (5) are add/add duplicates of content main already has independently: CONFLICT(5): Assets/Scenes/Rooms[3], Assets/NoSafeCircle/DoorPrototype/Editor/Rooms[1], Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms[1] | 5 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/room-nsc-044` | `61514b006` | 2026-09-12 | All commits patch-equivalent to main (`git cherry main room-nsc-044` shows only '-'). Conflicts (15) are add/add duplicates of content main already has independently: CONFLICT(15): Tasks[8], Pipeline/TaskGraph[2], Assets/NoSafeCircle/DoorPrototype/Editor/Rooms[1], Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms[1], Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms[1] | 15 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/room-nsc-045` | `678a5148f` | 2026-09-12 | 3 of 4 commits are unique (Bone Archive room blockout + repair + conformance). Confirmed by direct diff: main's current `BoneArchiveSceneBuilder.cs` (last touched 2026-09-13 by room-composition-b, `c9b2605ff`) is a differently-authored implementation (different helper names, different scene-building style) -- an independent, later Bone Archive build superseded this one. Also conflicts on 8 live Tasks/*.yaml (NSC-029/044/045/046/047/048/049/069) as pure add/add registry churn. | 19 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/taskgraph-nsc-068` | `c95d97af8` | 2026-09-12 | All commits patch-equivalent to main (`git cherry main taskgraph-nsc-068` shows only '-'). Conflicts (2) are add/add duplicates of content main already has independently: CONFLICT(2): Pipeline/TaskGraph[2] | 2 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/viewer-external-active` | `63f5814d2` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `assistant/world-multiscene-graph` | `c9b3b3641` | 2026-09-12 | All commits patch-equivalent to main (`git cherry main world-multiscene-graph` shows only '-'). Conflicts (11) are add/add duplicates of content main already has independently: CONFLICT(11): Tasks[8], Pipeline/TaskGraph[2], Pipeline/TaskReviewAgent[1] | 11 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/conformance-cherry-pick-content-20260914` | `723ccc183` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/ger-active-viewer-20260914` | `8240fedee` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main ger-active-viewer-202609` shows only '-'). Conflicts (4) are add/add duplicates of content main already has independently: CONFLICT(4): Pipeline/AssistantControl[2], Pipeline/TaskDesignGER[1], Pipeline/TaskReviewAgent/GauntletView[1] | 4 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/ger-held-viewer-20260914` | `11fdce64d` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main ger-held-viewer-20260914` shows only '-'). Conflicts (3) are add/add duplicates of content main already has independently: CONFLICT(3): Pipeline/AssistantControl[2], Pipeline/TaskReviewAgent/GauntletView[1] | 3 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/missing-validation-policy-review-20260914` | `65ff86439` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main missing-validation-polic` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Pipeline/AssistantControl[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc-new-file-scope-repair` | `fdbeb9634` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc-new-file-scope-repai` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Pipeline/TaskReviewAgent/tests[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc013-main-ready-20260914` | `86d366a49` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc013-provisional-20260914` | `27006ceff` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc013-provisional-20260` shows only '-'). Conflicts (4) are add/add duplicates of content main already has independently: CONFLICT(4): Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies[2], Assets/NoSafeCircle/DoorPrototype/Tests[2] | 4 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc013-validation-20260914` | `132c2c92e` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc013-validation-202609` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc013-validation2-20260914` | `86d366a49` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc042-delivery-20260914` | `257d8702c` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc042-evidence-handoff-20260914` | `31a3a8e0a` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc044-ger-room-20260914` | `28fd1224a` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc050-current-main-20260914` | `a2b6778ee` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc050-current-main-2026` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Assets/NoSafeCircle/DoorPrototype/Scripts[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc052-val003-20260914` | `229edb4ab` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc057-tooling-20260914` | `950110a42` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc057-tooling-20260914` shows only '-'). Conflicts (3) are add/add duplicates of content main already has independently: CONFLICT(3): Assets/NoSafeCircle/DoorPrototype[1], Docs/Engineering[1], ProjectSettings[1] | 3 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc058-hierarchy-fader-20260914` | `2f6e8bd9d` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc060-current-main-20260914` | `cb29e220a` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc060-current-main-2026` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Assets/NoSafeCircle/DoorPrototype/Scripts[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc060-lifecycle-validation-20260914` | `b13c01821` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc063-art-recovery-20260914` | `117b21dc6` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc063-art-recovery-2026` shows only '-'). Conflicts (20) are add/add duplicates of content main already has independently: CONFLICT(20): Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source[16], Docs/Art/Enemies[4] | 20 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc063-current-main-revision-20260914` | `f9565c927` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc063-current-main-revi` shows only '-'). Conflicts (18) are add/add duplicates of content main already has independently: CONFLICT(18): Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source[16], Assets/NoSafeCircle/DoorPrototype/Art[1], Assets/NoSafeCircle/DoorPrototype/Art/Enemies[1] | 18 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc063-pixellab-revision-20260914` | `4d5f119e8` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc065-retained-art-review-20260914` | `affcd0b53` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc065-retained-art-revi` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Docs/Art/Doors[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc065-source-delivery-20260914` | `973389feb` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc090-main-validation-20260914` | `eecab3def` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc090-main-validation-2` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Assets/NoSafeCircle/DoorPrototype/Scripts/World[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc091-main-ready-20260914` | `1d38f8011` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc091-main-ready-202609` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc091-provisional-20260914` | `2450ee45a` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc091-provisional-20260` shows only '-'). Conflicts (2) are add/add duplicates of content main already has independently: CONFLICT(2): Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies[1], Assets/NoSafeCircle/DoorPrototype/Scripts/World[1] | 2 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc092-diagnostic-20260914` | `b01d7f92d` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc092-diagnostic-202609` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc092-main-ready-20260914` | `b01d7f92d` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc092-main-ready-202609` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc092-obstacle-fix-20260914` | `d81492f1e` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc092-obstacle-fix-2026` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/nsc092-provisional-20260914` | `c1366b886` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main nsc092-provisional-20260` shows only '-'). Conflicts (4) are add/add duplicates of content main already has independently: CONFLICT(4): Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies[2], Assets/NoSafeCircle/DoorPrototype/Tests[2] | 4 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/parallel-scene-reservation-20260914` | `021707113` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/remove-blocking-audits` | `8892d26bb` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main remove-blocking-audits` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Docs/AI-Pipeline[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `codex/viewer-instructions-20260914` | `1db32df46` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main viewer-instructions-2026` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Docs/AI-Pipeline[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `docs/ger-agent-runbook-20260914` | `ba06509e3` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main ger-agent-runbook-202609` shows only '-'). Conflicts (1) are add/add duplicates of content main already has independently: CONFLICT(1): Pipeline/TaskDesignGER[1] | 1 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `docs/nsc042-wall-tiling-standard` | `9caa222d8` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `executioncrew-human-review-retry` | `12fad9358` | 2026-08-23 | Old (2026-08-23) 'Fix NSC-005 zero-mana denied feedback' -- same finding as nsc-005-closeout: main's PlayerMana/PlayerManaUI already implement CastDenied + visual flash feedback via a different, later commit. Superseded. | 2 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `nsc-005-closeout` | `ba1bb4df3` | 2026-08-23 | Old (2026-08-23) NSC-005 Unity validation log artifact. Main's `PlayerMana.cs` already exposes `CastDenied`, and `PlayerManaUI.cs` already has a full `HandleCastDenied` red-flash implementation (`deniedColor`/`deniedFlashDuration`/DOTween sequence) -- the feature this closeout evidence was for is already built, independently, on main. Superseded. | 2 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `nsc-011-active-enemy-registry` | `bb3c27e16` | 2026-08-24 | All commits patch-equivalent to main (`git cherry main nsc-011-active-enemy-reg` shows only '-'). Conflicts (2) are add/add duplicates of content main already has independently: CONFLICT(2): Assets/NoSafeCircle/DoorPrototype/Scripts[1], Assets/NoSafeCircle/DoorPrototype/Tests[1] | 2 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `nsc-061-pixellab-wizard-art-selection` | `aadf2d78b` | 2026-09-12 | All commits patch-equivalent to main (`git cherry main nsc-061-pixellab-wizard-` shows only '-'). Conflicts (4) are add/add duplicates of content main already has independently: CONFLICT(4): Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east[2], Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab[1], Docs/Art/Wizard[1] | 4 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `nsc-062-animated-wizard-unity-integration` | `aadf2d78b` | 2026-09-12 | All commits patch-equivalent to main (`git cherry main nsc-062-animated-wizard-` shows only '-'). Conflicts (4) are add/add duplicates of content main already has independently: CONFLICT(4): Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east[2], Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab[1], Docs/Art/Wizard[1] | 4 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `pipeline/narrow-doorprototype-builder-commit-20260902-025607` | `f5d482527` | 2026-09-02 | All commits patch-equivalent to main (`git cherry main narrow-doorprototype-bui` shows only '-'). Conflicts (2) are add/add duplicates of content main already has independently: CONFLICT(2): Pipeline/TaskReviewAgent[1], Pipeline/TaskReviewAgent/tests[1] | 2 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `release/policy-nsc071-40a` | `814c1f66f` | 2026-09-14 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `streaming-verification-refinement` | `2c6ccb698` | 2026-08-21 | All commits patch-equivalent to main (`git cherry main streaming-verification-r` shows only '-'). Conflicts (4) are add/add duplicates of content main already has independently: CONFLICT(4): .claude[1], (root)[1], Docs/GDD[1], Pipeline/Reconciliation/prompts[1] | 4 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |
| `viewer-held-overlay` | `c610b3f34` | 2026-09-14 | All commits patch-equivalent to main (`git cherry main viewer-held-overlay` shows only '-'). Conflicts (3) are add/add duplicates of content main already has independently: CONFLICT(3): Pipeline/AssistantControl[2], Pipeline/TaskReviewAgent/GauntletView[1] | 3 | No action -- content already on main. Delete branch + worktree once Vincent confirms. |

## OUT-OF-SCOPE (7)

Coursework/assignment history from before the game took its current shape, plus one
dated hazard.

**`demo/gauntlet-20260916` is not ordinary coursework -- it is a live hazard.** Dated today, it
deliberately breaks NSC-042 ("break NSC-042 and graft the synthetic gauntlet tasks") and grafts fake
`NSC-1101/1103/1104/1105/1107/1108/1110` and `NSC-200/201` tasks onto the graph for a Gauntlet
rehearsal -- exactly the kind of rehearsal task-graph state the standing rule says must never reach
upstream (`gauntlet-to-upstream-porting-rule`). It also touches the real
`Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` and
`Assets/Scenes/DoorPrototype.unity` incidentally. **Do not merge this branch under any circumstances.**


| Branch | Tip | Date | What it adds / why superseded | Conflicts | Recommended action |
|---|---|---|---|---|---|
| `assignment-4-RAG` | `1cbe305fc` | 2026-08-06 | All commits patch-equivalent to main (`git cherry main assignment-4-RAG` shows only '-'). Conflicts (2) are add/add duplicates of content main already has independently: CONFLICT(2): Docs/GDD[2] | 2 | No action needed for reconciliation. Archive/delete at Vincent's convenience. |
| `assignment-5-goal-oriented-agent` | `3fa0f7b09` | 2026-08-13 | All commits patch-equivalent to main (`git cherry main assignment-5-goal-orient` shows only '-'). Conflicts (6) are add/add duplicates of content main already has independently: CONFLICT(6): Assets/NoSafeCircle/DoorPrototype/Scripts[2], Docs/GDD[2], Assets/NoSafeCircle/DoorPrototype/Editor[1], Assets/NoSafeCircle/DoorPrototype/Tests[1] | 6 | No action needed for reconciliation. Archive/delete at Vincent's convenience. |
| `assignment-6-GER` | `be431529b` | 2026-08-18 | All commits patch-equivalent to main (`git cherry main assignment-6-GER` shows only '-'). Conflicts (4) are add/add duplicates of content main already has independently: CONFLICT(4): Assets/NoSafeCircle/DoorPrototype/Editor[1], Assets/NoSafeCircle/DoorPrototype/Scenes[1], Assets/NoSafeCircle/DoorPrototype/Scripts[1], Assets/NoSafeCircle/DoorPrototype/Tests/Editor[1] | 4 | No action needed for reconciliation. Archive/delete at Vincent's convenience. |
| `assignment-7-style-guide-agent` | `ce5a9110a` | 2026-08-20 | Merge-tree result is tree-identical to main -- a pure no-op merge. | 0 | No action needed for reconciliation. Archive/delete at Vincent's convenience. |
| `assignment3-agent-crew` | `fe94bfd9a` | 2026-08-04 | All commits patch-equivalent to main (`git cherry main assignment3-agent-crew` shows only '-'). Conflicts (14) are add/add duplicates of content main already has independently: CONFLICT(14): Assets/NoSafeCircle/DoorPrototype/Scripts[5], (root)[3], Assets/NoSafeCircle/DoorPrototype/Tests[2], Assets/NoSafeCircle/DoorPrototype/Tests/Editor[2], Assets/NoSafeCircle/DoorPrototype/Editor[1] | 14 | No action needed for reconciliation. Archive/delete at Vincent's convenience. |
| `demo/gauntlet-20260916` | `2a77d0967` | 2026-09-16 | CONFLICT(2): Assets/NoSafeCircle/DoorPrototype/Editor[1], Assets/Scenes[1] | 2 | DO NOT MERGE. Deliberately breaks NSC-042 and grafts fake NSC-1101/1103/1104/1105/1107/1108/1110/NSC-200/201 gauntlet-rehearsal tasks; also touches the real DoorPrototypeSceneBuilder.cs/scene incidentally. Close without merging; if anything in the worker-config staging is wanted, extract it by hand. |
| `milestone-2a-current-gdd-rag` | `3d838f088` | 2026-08-21 | All commits patch-equivalent to main (`git cherry main milestone-2a-current-gdd` shows only '-'). Conflicts (3) are add/add duplicates of content main already has independently: CONFLICT(3): Pipeline/GDDRAG[1], Pipeline/GDDRAG/knowledge_base[1], Pipeline/GDDRAG/tests[1] | 3 | No action needed for reconciliation. Archive/delete at Vincent's convenience. |

## Duplicate branches (same tip SHA, or oid-identical merge-tree result against main)

- `codex/batch-history-identity-validation`  <->  `codex/fix-required-decomposition-resume-route`  (same tip SHA; bucket: PIPELINE / VIEWER / CONTRACTS)
- `codex/integrate-thousand-readiness-ebaa-v2`  <->  `codex/source-admission-snapshot-perf`  (same tip SHA; bucket: PIPELINE / VIEWER / CONTRACTS)
- `codex/nsc074-current-review-20260914`  <->  `codex/nsc074-exact-unity-20260914`  (same tip SHA; bucket: DONE-THIS-WEEK)
- `codex/nsc013-main-ready-20260914`  <->  `codex/nsc013-validation2-20260914`  (same tip SHA; bucket: ALREADY-LANDED / SUPERSEDED)
- `nsc-061-pixellab-wizard-art-selection`  <->  `nsc-062-animated-wizard-unity-integration`  (same tip SHA; bucket: ALREADY-LANDED / SUPERSEDED)
- `codex/nsc092-diagnostic-20260914`  <->  `codex/nsc092-main-ready-20260914`  (same tip SHA; bucket: ALREADY-LANDED / SUPERSEDED)
- `codex/nsc064-main-review-20260914`  <->  `codex/nsc064-pixellab-20260914`  (different tips, but merge-tree result against main is oid-identical (`2eceec34...`); bucket: NEEDS-VISUAL-PICK)

## Branches touching NSC-075's active files

The running Codex job (started from `assistant/nsc-075-builder-prep`, clone `C:\nscrev\nsc075-codex`,
not touched by this pass) owns `WizardAnimationController.cs`, `DoorPrototypeGlobalSceneBuilder.cs`,
`WizardArtIntegrationTests.cs`, `WizardAnimationPlayModeTests.cs`, `Art/Wizard/Generated/` and
`Assets/Scenes/DoorPrototype.unity`. These branches conflict on at least one of those paths:

| Branch | Bucket | Which NSC-075 file(s) |
|---|---|---|
| `assistant/cardinal-staging` | PIPELINE / VIEWER / CONTRACTS | WizardArtIntegrationTests.cs |
| `assistant/foreground-nsc-062-materialization` | ALREADY-LANDED / SUPERSEDED | Art/Wizard/Generated/* |
| `assistant/foreground-nsc-066-title-screen` | ALREADY-LANDED / SUPERSEDED | Assets/Scenes/DoorPrototype.unity |
| `assistant/foreground-nsc-067-selection` | NEEDS-CODE-REVIEW | Art/Wizard/Generated/* (via PixelLab source) |
| `assistant/nsc-075-builder-prep` | PIPELINE / VIEWER / CONTRACTS | WizardArtIntegrationTests.cs (its own base) |
| `assistant/review-wizard-lobby` | ALREADY-LANDED / SUPERSEDED | Art/Wizard/Generated/* |
| `assistant/review-wizard-rooms` | ALREADY-LANDED / SUPERSEDED | Assets/Scenes/* (room scenes, adjacent) |
| `codex/nsc070-validation-20260914` | PIPELINE / VIEWER / CONTRACTS | Assets/Scenes/DoorPrototype.unity |
| `codex/nsc077-current-main-review-20260914` | NEEDS-CODE-REVIEW | Assets/Scenes/DoorPrototype.unity |
| `codex/nsc077-gameplay-visibility-20260914` | NEEDS-CODE-REVIEW | Assets/Scenes/DoorPrototype.unity |
| `codex/nsc077-stationary-enemies-20260914` | NEEDS-CODE-REVIEW | Assets/Scenes/DoorPrototype.unity |
| `demo/gauntlet-20260916` | OUT-OF-SCOPE | DoorPrototypeSceneBuilder.cs + Assets/Scenes/DoorPrototype.unity |

## Proposed merge order

1. **Cleanup pass first (no code risk).** Close everything in ALREADY-LANDED/SUPERSEDED and
   DONE-THIS-WEEK: delete the 76 branches (66 + 10) and their worktrees once Vincent confirms, using
   the same archive-then-delete pattern as the 2026-09-15 wave-2 cleanup
   (`refs/archive/<branch>` before `branch -D`). This is pure housekeeping and unblocks disk/worktree
   slots without touching main.
2. **Small pipeline fixes (`MERGE-CANDIDATE`).** `assistant/integrate-background-plus-decomp`,
   `assistant/restored-meta-companion-fix`, `codex/nsc061-source-review-20260914` -- clean, no
   conflicts, Pipeline-only, independent of everything else. Merge any time.
3. **Art picks (`NEEDS-VISUAL-PICK`).** Show Vincent `codex/nsc064-connections-20260914` for the
   NSC-064 dungeon-architecture set (clean merge once picked); `codex/nsc044-visual-tint-20260914`
   and `codex/nsc063-melee-ne-single-cleaver-20260914` are low-priority/skip-by-default (scene YAML
   and a rejected candidate respectively).
4. **NSC-077 code review (`NEEDS-CODE-REVIEW`).** Read `codex/nsc077-stationary-enemies-20260914`'s
   placement/prefab C# by hand (its art is already on main byte-identical); once accepted, rebuild
   `Assets/Scenes/DoorPrototype.unity` from the builder rather than merging the two scene-only
   follow-on branches. Separately spend 5 minutes diffing `WizardGameEntryPlayModeTests.cs` from
   `assistant/foreground-nsc-067-selection` against main before closing it.
5. **Everything touching NSC-075's files waits.** Do not merge or rebase
   `assistant/cardinal-staging`, `assistant/nsc-075-builder-prep`, `assistant/nsc-075-integration-prep`,
   `codex/nsc070-validation-20260914`, or the NSC-077 scene-only pair while the Codex job in
   `C:\nscrev\nsc075-codex` is running -- re-diff each against the post-NSC-075 main afterward;
   most will likely fold into ALREADY-LANDED at that point.
6. **Stale pipeline-scale cluster and contract branches last, if ever.** The 11-branch 2026-09-04/05
   cluster and the two 2026-08-28-era branches are 69-212 main commits stale in their area; only worth
   a look if Vincent specifically remembers wanting something out of one of them. `demo/gauntlet-20260916`
   is never merged.

## Worktrees available for cleanup

`git worktree list` currently shows 162 entries. Below: worktrees whose branch is in
ALREADY-LANDED/SUPERSEDED, DONE-THIS-WEEK or OUT-OF-SCOPE (safe to `worktree remove` once the branch
itself is deleted per Vincent's go-ahead), followed by the DONE-THIS-WEEK ancestor branches whose
worktrees/refs still exist even though the branches are already merged, followed by ones this pass
deliberately leaves alone.

### Safe-to-clean once branches are confirmed dead

- `C:/NSC/NoSafeCircle-AssistantControl-CI-20260912`  ->  `assistant-control-main-20260912`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NSC/NSC-060`  ->  `assistant/NSC-060`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-AssistantCheckouts/NSC-073-current`  ->  `assistant/NSC-073-current`  (DONE-THIS-WEEK)
- `C:/NSC/NoSafeCircle-AssistantCheckouts/NSC-089-editmode-path`  ->  `assistant/NSC-089-editmode-path`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-AssistantCheckouts/enemy-eight-direction-contract`  ->  `assistant/enemy-eight-direction-contract`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-WorkerScope-Enforcement`  ->  `assistant/fix-exact-worker-scope`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Foreground-NSC-062-Fix`  ->  `assistant/foreground-nsc-062-materialization`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Foreground-NSC-066`  ->  `assistant/foreground-nsc-066-title-screen`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-NSC070-Integration`  ->  `assistant/integrate-nsc-070`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Room-NSC-046`  ->  `assistant/nsc-046-chapel`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Room-NSC-047`  ->  `assistant/nsc-047-vault`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Room-NSC-048`  ->  `assistant/nsc-048-final`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Wizard-Runtime-Stability`  ->  `assistant/nsc-070-runtime-stability`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-NSC073-PixelLab`  ->  `assistant/nsc-073-pixellab`  (DONE-THIS-WEEK)
- `C:/NSC/NoSafeCircle-NSC074-CardinalArt`  ->  `assistant/nsc-074-cardinal-art`  (DONE-THIS-WEEK)
- `C:/NSC/NoSafeCircle-Review-Wizard-Lobby`  ->  `assistant/review-wizard-lobby`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Combined-Review`  ->  `assistant/review-wizard-rooms`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Room-Composition-A`  ->  `assistant/room-composition-a`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Room-Composition-B`  ->  `assistant/room-composition-b`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Room-NSC-044`  ->  `assistant/room-nsc-044`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-Room-NSC-045`  ->  `assistant/room-nsc-045`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/TaskGraph-NSC-068-20260912`  ->  `assistant/taskgraph-nsc-068`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-AssistantCheckouts/viewer-external-active`  ->  `assistant/viewer-external-active`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-World-Multiscene-Graph`  ->  `assistant/world-multiscene-graph`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/conformance-cherrypick-content-20260914`  ->  `codex/conformance-cherry-pick-content-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/ger-active-viewer`  ->  `codex/ger-active-viewer-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/viewer-held-live`  ->  `codex/ger-held-viewer-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/missing-validation-policy-review`  ->  `codex/missing-validation-policy-review-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-NewFileScopeRepair`  ->  `codex/nsc-new-file-scope-repair`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc013-main-ready-20260914`  ->  `codex/nsc013-main-ready-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc013-provisional-20260914`  ->  `codex/nsc013-provisional-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc013-validation-20260914`  ->  `codex/nsc013-validation-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc013-validation2-20260914`  ->  `codex/nsc013-validation2-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc042-delivery-20260914`  ->  `codex/nsc042-delivery-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc042-evidence-handoff-20260914`  ->  `codex/nsc042-evidence-handoff-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc044-ger-room-20260914`  ->  `codex/nsc044-ger-room-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc050-current-main-20260914`  ->  `codex/nsc050-current-main-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc052-val003-20260914`  ->  `codex/nsc052-val003-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc057-tooling-20260914`  ->  `codex/nsc057-tooling-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc058-hierarchy-fader-20260914`  ->  `codex/nsc058-hierarchy-fader-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc060-current-main-20260914`  ->  `codex/nsc060-current-main-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc060-lifecycle-validation-20260914`  ->  `codex/nsc060-lifecycle-validation-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc063-art-recovery-20260914`  ->  `codex/nsc063-art-recovery-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc063-current-main-revision-20260914`  ->  `codex/nsc063-current-main-revision-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc063-pixellab-revision-20260914`  ->  `codex/nsc063-pixellab-revision-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc065-retained-art-review-20260914`  ->  `codex/nsc065-retained-art-review-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc065-source-delivery-20260914`  ->  `codex/nsc065-source-delivery-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc073-074-current-review-20260914`  ->  `codex/nsc073-074-current-review-20260914`  (DONE-THIS-WEEK)
- `C:/NSC/_worktrees/nsc073-alt-current-stage-20260914`  ->  `codex/nsc073-alt-current-stage-20260914`  (DONE-THIS-WEEK)
- `C:/NSC/_worktrees/nsc073-main-validation-20260914`  ->  `codex/nsc073-main-validation-20260914`  (DONE-THIS-WEEK)
- `C:/NSC/_worktrees/nsc073-ne-alternate-20260914`  ->  `codex/nsc073-ne-alternate-20260914`  (DONE-THIS-WEEK)
- `C:/NSC/_worktrees/nsc074-current-review-20260914`  ->  `codex/nsc074-current-review-20260914`  (DONE-THIS-WEEK)
- `C:/NSC/_worktrees/nsc074-exact-unity-20260914`  ->  `codex/nsc074-exact-unity-20260914`  (DONE-THIS-WEEK)
- `C:/NSC/_worktrees/nsc090-main-validation-20260914`  ->  `codex/nsc090-main-validation-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc091-main-ready-20260914`  ->  `codex/nsc091-main-ready-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc091-provisional-20260914`  ->  `codex/nsc091-provisional-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc092-diagnostic-20260914`  ->  `codex/nsc092-diagnostic-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc092-main-ready-20260914`  ->  `codex/nsc092-main-ready-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc092-obstacle-fix-20260914`  ->  `codex/nsc092-obstacle-fix-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc092-provisional-20260914`  ->  `codex/nsc092-provisional-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/nsc093-pixellab-walk-20260914`  ->  `codex/nsc093-pixellab-walk-20260914`  (DONE-THIS-WEEK)
- `C:/NSC/_worktrees/parallel-scene-reservation-20260914`  ->  `codex/parallel-scene-reservation-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NoSafeCircle-RemoveAudits`  ->  `codex/remove-blocking-audits`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/_worktrees/viewer-instructions-20260914`  ->  `codex/viewer-instructions-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/nscrev/ger-agent-runbook-20260914`  ->  `docs/ger-agent-runbook-20260914`  (ALREADY-LANDED / SUPERSEDED)
- `C:/nscrev/nsc042-wall-tiling-standard`  ->  `docs/nsc042-wall-tiling-standard`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NSC/NSC-061`  ->  `nsc-061-pixellab-wizard-art-selection`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/NSC/NSC-062`  ->  `nsc-062-animated-wizard-unity-integration`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/ReleasePolicyFix40a`  ->  `release/policy-nsc071-40a`  (ALREADY-LANDED / SUPERSEDED)
- `C:/NSC/viewer-held-overlay`  ->  `viewer-held-overlay`  (ALREADY-LANDED / SUPERSEDED)

(70 of the 115 branches above have a live worktree; the rest were never checked out or already had their worktree removed in earlier waves.)

### DONE-THIS-WEEK ancestors (already merged into main, refs/worktrees still present)

- `codex/nsc073-reuse-alt-20260914`  --  worktree C:/NSC/_worktrees/nsc073-reuse-alt-20260914 (already an ancestor of main)
- `codex/nsc073-visual-stage-20260914`  --  worktree C:/NSC/_worktrees/nsc073-visual-stage-20260914 (already an ancestor of main)
- `assistant/NSC-074-current`  --  worktree C:/NSC/NoSafeCircle-AssistantCheckouts/NSC-074-current (already an ancestor of main)
- `codex/nsc093-current-main-review-20260914`  --  worktree C:/NSC/_worktrees/nsc093-current-main-review-20260914 (already an ancestor of main)
- `codex/nsc053-keep-distance-20260914`  --  worktree C:/NSC/_worktrees/nsc053-keep-distance-20260914 (already an ancestor of main)
- `codex/nsc017-locked-door-attack-20260914`  --  worktree C:/NSC/_worktrees/nsc017-locked-door-attack-20260914 (already an ancestor of main)
- `verify/nsc017-locked-door-20260915`  --  no live worktree found (already an ancestor of main)
- `verify/nsc053-keep-distance-20260915`  --  no live worktree found (already an ancestor of main)

### Leave alone -- explicitly out of this pass's hard rules
- `C:\nscrev\branch-verify` (detached HEAD) -- in active use by another process; do not touch per
  the task's hard rules. Its checked-out commit changed at least once during this pass, confirming
  it is live, not idle.
- `C:\nscrev\nsc075-codex` -- not a linked worktree of this repo at all (separate clone for the
  running Codex NSC-075 job); out of this pass's hard rules regardless.

## Limitations

- Three prior reports were computed against older `main` snapshots; every conclusion reused from
  them here was re-verified against current `main` (`22955c5a8`) with fresh `git cherry` /
  `git merge-tree` / blob-identity checks, not copied blind.
- `NEEDS-CODE-REVIEW` and `NEEDS-VISUAL-PICK` items still need an actual human (Vincent) look; this
  pass established what's unique and what already exists, not final go/no-go.
- Branches living only in other clones (see Scope, above) are outside this inventory entirely.
