# Waves 4-5 branch inventory -- No Safe Circle Unity repo

Read-only inspection. No branch was checked out, merged, pushed, or deleted. 
Working tree left untouched on `wizard-art/codex-20260915` at `03804a785e853f23209bd1c48eda030910c0b2ee` (same commit as local `main`).

## Scope

Per `C:\nscrev\reports\branch-recovery-plan-20260914.md`, Waves 1-3 (plan items 1-13) are already closed out. 
This report covers exactly the plan's **Wave 4** ("art staged for Vincent's visual review", items 14-21, 23 branches) 
and **Wave 5** ("two days ago, likely superseded", items 22-28, 12 branches) -- 35 branches total, all confirmed present 
as local branches in the canonical checkout as of this inspection. The plan labels these waves explicitly, so no branches 
beyond this named set were treated as in-scope -- the repository holds well over 100 other branches (pipeline/GER/decomposition 
work, coursework assignments, etc.) that belong to unrelated efforts and are not part of this recovery queue.

All 35 branches were compared against local `main` at commit `03804a785e853f23209bd1c48eda030910c0b2ee` 
(tree `cfedcbe98e15b3ab2c2382362fd9db7c3afc9867`), which is 73 commits ahead of `origin/main` (`96a6293c4`, the main referenced in the 09-14 plan).

## Methodology notes (read before the table)

- **(a) Ancestor check**: `git merge-base --is-ancestor <branch> main`. Result: **none of the 35 branches are ancestors of main**, 
and none produce a merge-tree result byte-identical to main's own tree either -- every branch would change at least one file if merged as-is.
- **(b)/(e) Merge simulation**: `git merge-tree --write-tree main <branch>`, then `git diff --stat main <tree>` for the stat line and 
`git diff --name-only main <tree>` for the file list. 14 of the 35 branches return a non-zero exit from `merge-tree` with explicit 
`CONFLICT (...)` messages (mostly `add/add` on Unity `.meta`/`.anim` files, i.e. the branch and main independently created the same-named 
asset with a different GUID -- exactly the GUID-collision risk the recovery plan warns about). 
**Caveat**: the task's suggested `<<<<<<<`-marker search under-detects conflicts on binary paths (e.g. the `.unity` scene file) -- 
git cannot embed text conflict markers in a binary blob, so `merge-tree` reports the conflict only in its message stream ("Cannot merge 
binary files" / `CONFLICT (content)`), not as inline `<<<<<<<` text in the diff. This report therefore treats a branch as conflicting when 
`merge-tree`'s own exit code and CONFLICT messages say so, not only when a `<<<<<<<` marker literally appears in the diff text.
- **(c) Non-art paths**: the art prefix is exactly `Assets/NoSafeCircle/DoorPrototype/Art/`. Anything else counts as "outside" per the task 
brief, but not all of it carries equal weight -- 14 branches touch nothing outside that prefix except `Docs/Art/**` markdown and PNGs 
(art-review staging material, not code), which are listed separately as low-materiality. 21 branches touch real code, tests, `Tasks/*.yaml` 
contracts, a `.unity` scene, or `Pipeline/` files -- these are listed individually below.
- **Names and subjects are not reliable.** Per the task brief's own caveat, at least one branch here (`assistant/nsc-074-cardinal-art`) is named 
for cardinal wizard art but contains zero art files. A second finding this inspection turned up independently: `assistant/cardinal-staging` and 
`assistant/nsc-074-cardinal-art` share the exact same commit **subject line** ("Clarify NSC-074 Windows source audit") but have completely 
different trees and file counts -- commit subjects are exactly as unreliable as branch names here. Every disposition below was made from the 
actual diff, never from a name or subject.

## Per-branch inventory

| Item | Branch | Ancestor of main? (a) | Merge-tree diff (b) | Top dirs | Non-art paths? (c) | Conflicts? (e) | Tip SHA | Author | Date | Subject (d) |
|---|---|---|---|---|---|---|---|---|---|---|
| 14 | `codex/nsc073-main-validation-20260914` | no | 4 files, +129/-4 | Assets, Docs | Docs-only (1) -- see Low-materiality list | No | 911e66f6c | No Safe Circle TaskReviewAgent | 2026-09-13 | Replace defective White Female north-east walk frames 004/005 |
| 14 | `assistant/NSC-073-current` | no | 4 files, +129/-4 | Assets, Docs | Docs-only (1) -- see Low-materiality list | No | ae91820c2 | No Safe Circle TaskReviewAgent | 2026-09-13 | Replace defective White Female north-east walk frames 004/005 |
| 14 | `codex/nsc073-ne-alternate-20260914` | no | 4 files, +129/-4 | Assets, Docs | Docs-only (1) -- see Low-materiality list | No | 48cc3e653 | No Safe Circle TaskReviewAgent | 2026-09-13 | Replace defective White Female north-east walk frames 004/005 |
| 14 | `codex/nsc073-visual-stage-20260914` | no | 4 files, +129/-4 | Assets, Docs | Docs-only (1) -- see Low-materiality list | No | 7fe174fc5 | No Safe Circle Art Recovery | 2026-09-14 | Clarify NSC-073 fallback visual limit and preserved sprite GUIDs |
| 14 | `codex/nsc073-reuse-alt-20260914` | no | 4 files, +134/-4 | Assets, Docs | Docs-only (1) -- see Low-materiality list | No | 17af0ace6 | No Safe Circle Art Recovery | 2026-09-14 | Stage existing PixelLab northeast tail as NSC-073 visual alternate |
| 14 | `codex/nsc073-alt-current-stage-20260914` | no | 4 files, +134/-4 | Assets, Docs | Docs-only (1) -- see Low-materiality list | No | 6abb92b73 | No Safe Circle Art Recovery | 2026-09-14 | Stage existing PixelLab northeast tail as NSC-073 visual alternate |
| 14 | `assistant/nsc-073-pixellab` | no | 4 files, +129/-4 | Assets, Docs | Docs-only (1) -- see Low-materiality list | No | be3ac9548 | No Safe Circle TaskReviewAgent | 2026-09-13 | Replace defective White Female north-east walk frames 004/005 |
| 15 | `codex/nsc074-current-review-20260914` | no | 213 files, +2100/-1 | Assets, Docs | YES -- 4 path(s), see Touches-non-art-paths section | No | 5b8c4634b | No Safe Circle TaskReviewAgent | 2026-09-14 | Stage retained cardinal wizard walks on current source |
| 15 | `codex/nsc074-exact-unity-20260914` | no | 213 files, +2100/-1 | Assets, Docs | YES -- 4 path(s), see Touches-non-art-paths section | No | 5b8c4634b | No Safe Circle TaskReviewAgent | 2026-09-14 | Stage retained cardinal wizard walks on current source |
| 15 | `assistant/NSC-074-current` | no | 212 files, +2094/-1 | Assets, Docs | YES -- 3 path(s), see Touches-non-art-paths section | No | f7cb0f478 | No Safe Circle Art Recovery | 2026-09-14 | art: stage NSC-074 cardinal wizard walks for review |
| 15 | `codex/nsc073-074-current-review-20260914` | no | 214 files, +2222/-5 | Assets, Docs | YES -- 3 path(s), see Touches-non-art-paths section | No | 9cf7ae95f | No Safe Circle Art Review | 2026-09-14 | docs: correct NSC-073 sprite GUID provenance on current base |
| 15 | `assistant/nsc-074-cardinal-art` | no | 5 files, +350/-0 | Assets, Pipeline | YES -- 5 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | a0602783f | No Safe Circle TaskReviewAgent | 2026-09-13 | Clarify NSC-074 Windows source audit |
| 16 | `codex/nsc077-gameplay-visibility-20260914` | no | 52 files, +3142/-0 | Assets | YES -- 19 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | a9c11258e | No Safe Circle TaskReviewAgent | 2026-09-14 | Make NSC-077 review enemies visible from gameplay camera |
| 16 | `codex/nsc077-current-main-review-20260914` | no | 52 files, +3142/-0 | Assets | YES -- 19 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | cb4bf04c4 | No Safe Circle TaskReviewAgent | 2026-09-14 | Materialize stationary enemy sprites, prefabs, and review scene |
| 16 | `codex/nsc077-stationary-enemies-20260914` | no | 70 files, +3442/-0 | Assets | YES -- 19 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | c374b5282 | No Safe Circle TaskReviewAgent | 2026-09-14 | Materialize stationary enemy sprites, prefabs, and review scene |
| 17 | `codex/nsc064-connections-20260914` | no | 21 files, +432/-0 | Assets, Docs | Docs-only (7) -- see Low-materiality list | No | b589afbd7 | No Safe Circle TaskReviewAgent | 2026-09-14 | Document unresolved PixelLab wall perimeter joins |
| 17 | `codex/nsc064-main-review-20260914` | no | 11 files, +209/-0 | Assets, Docs | Docs-only (3) -- see Low-materiality list | No | f99d419cf | No Safe Circle TaskReviewAgent | 2026-09-14 | Select PixelLab dungeon architecture source art for review |
| 17 | `codex/nsc064-pixellab-20260914` | no | 11 files, +209/-0 | Assets, Docs | Docs-only (3) -- see Low-materiality list | No | 7924beb78 | No Safe Circle TaskReviewAgent | 2026-09-14 | Select PixelLab dungeon architecture source art for review |
| 18 | `codex/nsc063-melee-ne-single-cleaver-20260914` | no | 4 files, +46/-0 | Docs | Docs-only (4) -- see Low-materiality list | No | 01e3b8ffd | No Safe Circle TaskReviewAgent | 2026-09-14 | Stage NSC-063 single-cleaver northeast idle review candidate |
| 19 | `codex/nsc093-current-main-review-20260914` | no | 102 files, +2550/-0 | Assets, Docs | Docs-only (5) -- see Low-materiality list | No | d8bea33fc | No Safe Circle NSC-093 Art Worker | 2026-09-14 | Stage PixelLab enemy eight-direction walk source for visual review |
| 19 | `codex/nsc093-pixellab-walk-20260914` | no | 102 files, +2550/-0 | Assets, Docs | Docs-only (5) -- see Low-materiality list | No | d23987945 | No Safe Circle NSC-093 Art Worker | 2026-09-14 | Stage PixelLab enemy eight-direction walk source for visual review |
| 20 | `codex/nsc070-validation-20260914` | no | 1 files, +50/-0 | Assets | YES -- 1 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | 7680cf3af | No Safe Circle TaskReviewAgent | 2026-09-14 | Preserve NSC-070 builder-materialized scene for visual review |
| 21 | `codex/nsc061-source-review-20260914` | no | 1 files, +9/-0 | Docs | Docs-only (1) -- see Low-materiality list | No | cc403ce2f | No Safe Circle Wizard Source Review | 2026-09-14 | Document NSC-061 source selection blocker |
| 22 | `assistant/room-nsc-045` | no | 21 files, +1227/-0 | Assets, Pipeline, Tasks | YES -- 21 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | 678a5148f | No Safe Circle TaskReviewAgent | 2026-09-12 | Correct Bone Archive scene conformance |
| 23 | `assistant/foreground-nsc-066-title-screen` | no | 1 files, +496/-0 | Assets | YES -- 1 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | 1be73b24c | No Safe Circle TaskReviewAgent | 2026-09-12 | Document NSC-066 validation results |
| 24 | `assistant/foreground-nsc-062-materialization` | no | 168 files, +1271/-0 | Assets, Pipeline | YES -- 8 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | 3f99eff7d | No Safe Circle TaskReviewAgent | 2026-09-12 | task-review-agent: fix NSC-062 wizard initial sprite |
| 24 | `assistant/review-wizard-lobby` | no | 168 files, +1476/-0 | Assets, Pipeline | YES -- 8 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | 651fd6298 | No Safe Circle TaskReviewAgent | 2026-09-12 | Document NSC-066 validation results |
| 24 | `assistant/foreground-nsc-067-selection` | no | 137 files, +1643/-0 | Assets, Pipeline | YES -- 9 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | edc2526bb | No Safe Circle TaskReviewAgent | 2026-09-12 | Implement NSC-068 wizard game entry |
| 25 | `assistant/nsc-075-builder-prep` | no | 4 files, +192/-50 | Assets | YES -- 4 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | 5a139770e | No Safe Circle TaskReviewAgent | 2026-09-13 | Validate wizard sorting in composed room world |
| 25 | `assistant/nsc-075-integration-prep` | no | 2 files, +146/-42 | Assets | YES -- 2 path(s), see Touches-non-art-paths section | No | ba2a16bd4 | No Safe Circle TaskReviewAgent | 2026-09-13 | Add NSC-075 eight-direction classifier tests |
| 25 | `assistant/cardinal-staging` | no | 9 files, +542/-62 | Assets, Pipeline | YES -- 9 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | b1e70b5ec | No Safe Circle TaskReviewAgent | 2026-09-13 | Clarify NSC-074 Windows source audit |
| 26 | `assistant/task-nsc-070-wizard-animation-audit` | no | 4 files, +222/-0 | Pipeline, Tasks | YES -- 4 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | f14404e92 | No Safe Circle TaskReviewAgent | 2026-09-12 | Add NSC-070 wizard animation audit task |
| 27 | `assistant/restored-meta-companion-fix` | no | 2 files, +34/-4 | Pipeline | YES -- 2 path(s), see Touches-non-art-paths section | No | 807bd7b86 | No Safe Circle TaskReviewAgent | 2026-09-13 | Allow deterministic Unity metadata on restored candidates |
| 27 | `assistant/integrate-background-plus-decomp` | no | 2 files, +73/-2 | Pipeline | YES -- 2 path(s), see Touches-non-art-paths section | No | 8d8ae6cd0 | No Safe Circle TaskReviewAgent | 2026-09-13 | AssistantControl: normalize Windows Docker bind mounts |
| 28 | `assistant-ci-boundary-20260912` | no | 51 files, +1586/-0 | .github, AGENTS.md, Docs, Pipeline | YES -- 51 path(s), see Touches-non-art-paths section | YES (merge-tree exit 1, CONFLICT messages -- see Conflicts appendix) | 8af9a0940 | No Safe Circle TaskReviewAgent | 2026-09-12 | assistant-control: integrate direct game-task orchestration |

## Duplicate groups (byte-identical resulting merge tree)

Grouped by the resulting tree hash from `git merge-tree --write-tree main <branch>`. Branches in the same group would land 
**exactly** the same content if merged -- there is no difference between them for main's purposes.

- **NSC-073 variant A** -- tree `e956aca916b5e8eda60a26b48aa6191dea255e8e`:
  - assistant/NSC-073-current (primary)
  - codex/nsc073-main-validation-20260914
  - codex/nsc073-ne-alternate-20260914
  - assistant/nsc-073-pixellab
- **NSC-073 variant C (reused tail)** -- tree `37c82c7adc8a1969f06f02c89c7ce9d880653c19`:
  - codex/nsc073-reuse-alt-20260914 (primary)
  - codex/nsc073-alt-current-stage-20260914
- **NSC-074 current-review (same tip commit 5b8c4634b)** -- tree `6ee4f687fd502ba3684e280798eb72846915713b`:
  - codex/nsc074-current-review-20260914 (primary)
  - codex/nsc074-exact-unity-20260914
- **NSC-064 main-review** -- tree `4d8f359e80b3d2c2a16496268b6d3778e33531fa`:
  - codex/nsc064-main-review-20260914 (primary)
  - codex/nsc064-pixellab-20260914
- **NSC-093 current-main-review** -- tree `9be2df676847766dc6cffc550c7bfd75fa78f09f`:
  - codex/nsc093-current-main-review-20260914 (primary)
  - codex/nsc093-pixellab-walk-20260914

29 of the 35 branches produce a tree not shared by any other in-scope branch (including several that are near-identical in file/line 
counts to a sibling -- e.g. the three NSC-077 branches, and the NSC-062-materialization/review-wizard-lobby/foreground-nsc-067-selection trio -- 
but differ enough at the byte level (different scene-conflict resolution, one extra test file, etc.) that they are not filed as exact duplicates. 
Those near-duplicates are called out in the per-branch notes and in the Recommended disposition section instead.

## Touches non-art paths

### High materiality -- code, tests, `Tasks/*.yaml` contracts, scenes, or `Pipeline/`

- **`codex/nsc074-current-review-20260914`**:
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs.meta`
  - `Docs/Art/Wizard/PIXELLAB_CARDINAL_CONTACT_SHEET.png`
  - `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- **`codex/nsc074-exact-unity-20260914`**:
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs.meta`
  - `Docs/Art/Wizard/PIXELLAB_CARDINAL_CONTACT_SHEET.png`
  - `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- **`assistant/NSC-074-current`**:
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs.meta`
  - `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- **`codex/nsc073-074-current-review-20260914`**:
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs.meta`
  - `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- **`assistant/nsc-074-cardinal-art`**:
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs.meta`
  - `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`
  - `Pipeline/TaskGraph/WORK_ID_MAP.json`
  - `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`
- **`codex/nsc077-gameplay-visibility-20260914`**:
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Enemies.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Enemies/StationaryEnemyPresentationBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Enemies/StationaryEnemyPresentationBuilder.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryMeleeEnemy.prefab`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryMeleeEnemy.prefab.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryRangedEnemy.prefab`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryRangedEnemy.prefab.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyDirection.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyDirection.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyPresentation.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyPresentation.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/StationaryEnemyReviewPlacement.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/StationaryEnemyReviewPlacement.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/StationaryEnemyPresentationIntegrationTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/StationaryEnemyPresentationIntegrationTests.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/StationaryEnemyStationaryBehaviorPlayModeTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/StationaryEnemyStationaryBehaviorPlayModeTests.cs.meta`
- **`codex/nsc077-current-main-review-20260914`**:
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Enemies.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Enemies/StationaryEnemyPresentationBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Enemies/StationaryEnemyPresentationBuilder.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryMeleeEnemy.prefab`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryMeleeEnemy.prefab.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryRangedEnemy.prefab`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryRangedEnemy.prefab.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyDirection.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyDirection.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyPresentation.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyPresentation.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/StationaryEnemyReviewPlacement.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/StationaryEnemyReviewPlacement.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/StationaryEnemyPresentationIntegrationTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/StationaryEnemyPresentationIntegrationTests.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/StationaryEnemyStationaryBehaviorPlayModeTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/StationaryEnemyStationaryBehaviorPlayModeTests.cs.meta`
- **`codex/nsc077-stationary-enemies-20260914`**:
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Enemies.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Enemies/StationaryEnemyPresentationBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Enemies/StationaryEnemyPresentationBuilder.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryMeleeEnemy.prefab`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryMeleeEnemy.prefab.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryRangedEnemy.prefab`
  - `Assets/NoSafeCircle/DoorPrototype/Generated/Enemies/StationaryRangedEnemy.prefab.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyDirection.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyDirection.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyPresentation.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/StationaryEnemyPresentation.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/StationaryEnemyReviewPlacement.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/StationaryEnemyReviewPlacement.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/StationaryEnemyPresentationIntegrationTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/StationaryEnemyPresentationIntegrationTests.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/StationaryEnemyStationaryBehaviorPlayModeTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/StationaryEnemyStationaryBehaviorPlayModeTests.cs.meta`
- **`codex/nsc070-validation-20260914`**:
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs`
- **`assistant/room-nsc-045`**:
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Rooms.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/BoneArchiveSceneBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/World.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/BoneArchiveNavigationPlayModeTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/BoneArchiveNavigationPlayModeTests.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms/BoneArchiveSceneTests.cs`
  - `Assets/Scenes/Rooms.meta`
  - `Assets/Scenes/Rooms/BoneArchive.unity`
  - `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`
  - `Pipeline/TaskGraph/WORK_ID_MAP.json`
  - `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`
  - `Tasks/NSC-029.yaml`
  - `Tasks/NSC-044.yaml`
  - `Tasks/NSC-045.yaml`
  - `Tasks/NSC-046.yaml`
  - `Tasks/NSC-047.yaml`
  - `Tasks/NSC-048.yaml`
  - `Tasks/NSC-049.yaml`
  - `Tasks/NSC-069.yaml`
- **`assistant/foreground-nsc-066-title-screen`**:
  - `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`
- **`assistant/foreground-nsc-062-materialization`**:
  - `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/WizardAnimationPlayModeTests.cs`
  - `Pipeline/AssistantControl/test_unity_materialization.py`
  - `Pipeline/AssistantControl/unity_materialization.py`
  - `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`
  - `Pipeline/TaskReviewAgent/door_prototype_materialization.py`
- **`assistant/review-wizard-lobby`**:
  - `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/WizardAnimationPlayModeTests.cs`
  - `Pipeline/AssistantControl/test_unity_materialization.py`
  - `Pipeline/AssistantControl/unity_materialization.py`
  - `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`
  - `Pipeline/TaskReviewAgent/door_prototype_materialization.py`
- **`assistant/foreground-nsc-067-selection`**:
  - `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/WizardAnimationPlayModeTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/WizardGameEntryPlayModeTests.cs`
  - `Pipeline/AssistantControl/test_unity_materialization.py`
  - `Pipeline/AssistantControl/unity_materialization.py`
  - `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`
  - `Pipeline/TaskReviewAgent/door_prototype_materialization.py`
- **`assistant/nsc-075-builder-prep`**:
  - `Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/WizardAnimationPlayModeTests.cs`
- **`assistant/nsc-075-integration-prep`**:
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/WizardAnimationPlayModeTests.cs`
- **`assistant/cardinal-staging`**:
  - `Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs.meta`
  - `Assets/NoSafeCircle/DoorPrototype/Tests/WizardAnimationPlayModeTests.cs`
  - `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`
  - `Pipeline/TaskGraph/WORK_ID_MAP.json`
  - `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`
- **`assistant/task-nsc-070-wizard-animation-audit`**:
  - `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`
  - `Pipeline/TaskGraph/WORK_ID_MAP.json`
  - `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`
  - `Tasks/NSC-070.yaml`
- **`assistant/restored-meta-companion-fix`**:
  - `Pipeline/AssistantControl/assistant_restored_candidate.py`
  - `Pipeline/AssistantControl/test_assistant_restored_candidate.py`
- **`assistant/integrate-background-plus-decomp`**:
  - `Pipeline/AssistantControl/docker_workers.py`
  - `Pipeline/AssistantControl/test_docker_workers.py`
- **`assistant-ci-boundary-20260912`**:
  - `.github/workflows/assistant-candidate-ci.yml`
  - `.github/workflows/d1b2-core-deterministic.yml`
  - `.github/workflows/task-review-agent-deterministic.yml`
  - `AGENTS.md`
  - `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md`
  - `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md`
  - `Pipeline/AssistantControl/CURRENT.md`
  - `Pipeline/AssistantControl/README.md`
  - `Pipeline/AssistantControl/__main__.py`
  - `Pipeline/AssistantControl/admission.py`
  - `Pipeline/AssistantControl/assistant_restored_candidate.py`
  - `Pipeline/AssistantControl/automation_policy.py`
  - `Pipeline/AssistantControl/candidate.py`
  - `Pipeline/AssistantControl/decomposition.py`
  - `Pipeline/AssistantControl/dependencies.py`
  - `Pipeline/AssistantControl/graph_controller.py`
  - `Pipeline/AssistantControl/inspect_project.py`
  - `Pipeline/AssistantControl/post_crew_workflow.py`
  - `Pipeline/AssistantControl/readiness.py`
  - `Pipeline/AssistantControl/source_update.py`
  - `Pipeline/AssistantControl/test_admission.py`
  - `Pipeline/AssistantControl/test_admission_worktree.py`
  - `Pipeline/AssistantControl/test_assistant_restored_candidate.py`
  - `Pipeline/AssistantControl/test_decomposition.py`
  - `Pipeline/AssistantControl/test_graph_controller.py`
  - `Pipeline/AssistantControl/test_inspect_project.py`
  - `Pipeline/AssistantControl/test_post_crew_workflow.py`
  - `Pipeline/AssistantControl/test_scope.py`
  - `Pipeline/AssistantControl/test_source_update.py`
  - `Pipeline/AssistantControl/test_unity_materialization.py`
  - `Pipeline/AssistantControl/test_viewer.py`
  - `Pipeline/AssistantControl/unity_materialization.py`
  - `Pipeline/AssistantControl/viewer.py`
  - `Pipeline/ExecutionCrew/role_profiles.py`
  - `Pipeline/ExecutionCrew/run_crew.py`
  - `Pipeline/ExecutionCrew/session_pool.py`
  - `Pipeline/TaskDecomposition/prompts.py`
  - `Pipeline/TaskDecomposition/round_robin_decomposition.py`
  - `Pipeline/TaskDecomposition/tests/live_decomposition_smoke_test.py`
  - `Pipeline/TaskReviewAgent/GauntletView/index.html`
  - `Pipeline/TaskReviewAgent/GauntletView/server.py`
  - `Pipeline/TaskReviewAgent/GauntletView/tests/browser_smoke_test.cjs`
  - `Pipeline/TaskReviewAgent/GauntletView/tests/gauntlet_view_smoke_test.py`
  - `Pipeline/TaskReviewAgent/authoritative_candidate_validation.py`
  - `Pipeline/TaskReviewAgent/door_prototype_materialization.py`
  - `Pipeline/TaskReviewAgent/provider_budget.py`
  - `Pipeline/TaskReviewAgent/provider_profiles.py`
  - `Pipeline/TaskReviewAgent/tests/ci_workflow_split_smoke_test.py`
  - `Pipeline/TaskReviewAgent/tests/provider_profiles_test.py`
  - `Pipeline/TaskReviewAgent/tests/public_synthetic_authority_smoke_test.py`
  - `Pipeline/TaskReviewAgent/tests/task_id_width_smoke_test.py`

(21 of 35 branches fall in this list.)

### Low materiality -- `Docs/Art/**` markdown and PNGs only (art-review staging, not code)

- `codex/nsc073-main-validation-20260914`: `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- `assistant/NSC-073-current`: `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- `codex/nsc073-ne-alternate-20260914`: `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- `codex/nsc073-visual-stage-20260914`: `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- `codex/nsc073-reuse-alt-20260914`: `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- `codex/nsc073-alt-current-stage-20260914`: `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- `assistant/nsc-073-pixellab`: `Docs/Art/Wizard/PIXELLAB_GENERATION.md`
- `codex/nsc064-connections-20260914`: `Docs/Art/Environment/PIXELLAB_CONTACT_SHEET.png`, `Docs/Art/Environment/PIXELLAB_CORNER_ANCHOR_TRIALS.png`, `Docs/Art/Environment/PIXELLAB_DOOR_ORDER_TRIALS.png`, `Docs/Art/Environment/PIXELLAB_GENERATION.md`, `Docs/Art/Environment/PIXELLAB_WALL_CONNECTION_CHECK.png`, `Docs/Art/Environment/PIXELLAB_WALL_REPEAT_CHECK.png`, `Docs/Art/Environment/PIXELLAB_WEST_END_TRIALS.png`
- `codex/nsc064-main-review-20260914`: `Docs/Art/Environment/PIXELLAB_CONTACT_SHEET.png`, `Docs/Art/Environment/PIXELLAB_GENERATION.md`, `Docs/Art/Environment/PIXELLAB_WALL_REPEAT_CHECK.png`
- `codex/nsc064-pixellab-20260914`: `Docs/Art/Environment/PIXELLAB_CONTACT_SHEET.png`, `Docs/Art/Environment/PIXELLAB_GENERATION.md`, `Docs/Art/Environment/PIXELLAB_WALL_REPEAT_CHECK.png`
- `codex/nsc063-melee-ne-single-cleaver-20260914`: `Docs/Art/Enemies/Candidates/melee_ne_single_cleaver/README.md`, `Docs/Art/Enemies/Candidates/melee_ne_single_cleaver/idle_single_cleaver.png`, `Docs/Art/Enemies/Candidates/melee_ne_single_cleaver/original_vs_single_cleaver_gameplay.png`, `Docs/Art/Enemies/Candidates/melee_ne_single_cleaver/rejected_first_inpaint.png`
- `codex/nsc093-current-main-review-20260914`: `Docs/Art/Enemies/PIXELLAB_WALK_GENERATION.md`, `Docs/Art/Enemies/Walk/melee_contact_sheet.png`, `Docs/Art/Enemies/Walk/melee_gameplay_scale.png`, `Docs/Art/Enemies/Walk/ranged_contact_sheet.png`, `Docs/Art/Enemies/Walk/ranged_gameplay_scale.png`
- `codex/nsc093-pixellab-walk-20260914`: `Docs/Art/Enemies/PIXELLAB_WALK_GENERATION.md`, `Docs/Art/Enemies/Walk/melee_contact_sheet.png`, `Docs/Art/Enemies/Walk/melee_gameplay_scale.png`, `Docs/Art/Enemies/Walk/ranged_contact_sheet.png`, `Docs/Art/Enemies/Walk/ranged_gameplay_scale.png`
- `codex/nsc061-source-review-20260914`: `Docs/Art/Wizard/NSC-061_SOURCE_REVIEW_20260914.md`

(14 of 35 branches fall in this list; the remaining branches touch nothing outside the art prefix at all -- there were none of those in this set, every branch changes at least one non-art path.)

## Conflicts appendix -- merge-tree CONFLICT messages

14 branches produce a non-zero exit from `git merge-tree --write-tree main <branch>`. Their actual CONFLICT/warning messages 
(cleanly auto-merged paths omitted):

**`assistant/nsc-074-cardinal-art`** (4 paths auto-merged cleanly, 3 conflict/warning messages):
```
CONFLICT (content): Merge conflict in Pipeline/TaskGraph/RESOURCE_GROUPS.yaml
CONFLICT (content): Merge conflict in Pipeline/TaskGraph/WORK_ID_MAP.json
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/authoritative_validation_policy.json
```

**`codex/nsc077-gameplay-visibility-20260914`** (1 paths auto-merged cleanly, 2 conflict/warning messages):
```
warning: Cannot merge binary files: Assets/Scenes/DoorPrototype.unity (main vs. codex/nsc077-gameplay-visibility-20260914)
CONFLICT (content): Merge conflict in Assets/Scenes/DoorPrototype.unity
```

**`codex/nsc077-current-main-review-20260914`** (1 paths auto-merged cleanly, 2 conflict/warning messages):
```
warning: Cannot merge binary files: Assets/Scenes/DoorPrototype.unity (main vs. codex/nsc077-current-main-review-20260914)
CONFLICT (content): Merge conflict in Assets/Scenes/DoorPrototype.unity
```

**`codex/nsc077-stationary-enemies-20260914`** (19 paths auto-merged cleanly, 20 conflict/warning messages):
```
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_melee_e_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_melee_n_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_melee_ne_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_melee_nw_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_melee_s_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_melee_se_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_melee_sw_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_melee_w_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_e_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_n_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_ne_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_nw_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_s_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_se_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_sw_idle_00.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_w_idle_00.png.meta
warning: Cannot merge binary files: Assets/Scenes/DoorPrototype.unity (main vs. codex/nsc077-stationary-enemies-20260914)
CONFLICT (content): Merge conflict in Assets/Scenes/DoorPrototype.unity
```

**`codex/nsc070-validation-20260914`** (1 paths auto-merged cleanly, 2 conflict/warning messages):
```
warning: Cannot merge binary files: Assets/Scenes/DoorPrototype.unity (main vs. codex/nsc070-validation-20260914)
CONFLICT (content): Merge conflict in Assets/Scenes/DoorPrototype.unity
```

**`assistant/room-nsc-045`** (19 paths auto-merged cleanly, 19 conflict/warning messages):
```
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Editor/Rooms.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/BoneArchiveSceneBuilder.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Scripts/World.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms/BoneArchiveSceneTests.cs
CONFLICT (add/add): Merge conflict in Assets/Scenes/Rooms.meta
CONFLICT (add/add): Merge conflict in Assets/Scenes/Rooms/BoneArchive.unity
CONFLICT (content): Merge conflict in Pipeline/TaskGraph/RESOURCE_GROUPS.yaml
CONFLICT (content): Merge conflict in Pipeline/TaskGraph/WORK_ID_MAP.json
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/authoritative_validation_policy.json
CONFLICT (content): Merge conflict in Tasks/NSC-029.yaml
CONFLICT (content): Merge conflict in Tasks/NSC-044.yaml
CONFLICT (content): Merge conflict in Tasks/NSC-045.yaml
CONFLICT (content): Merge conflict in Tasks/NSC-046.yaml
CONFLICT (content): Merge conflict in Tasks/NSC-047.yaml
CONFLICT (content): Merge conflict in Tasks/NSC-048.yaml
CONFLICT (content): Merge conflict in Tasks/NSC-049.yaml
CONFLICT (add/add): Merge conflict in Tasks/NSC-069.yaml
```

**`assistant/foreground-nsc-066-title-screen`** (2 paths auto-merged cleanly, 3 conflict/warning messages):
```
CONFLICT (content): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
warning: Cannot merge binary files: Assets/Scenes/DoorPrototype.unity (main vs. assistant/foreground-nsc-066-title-screen)
CONFLICT (content): Merge conflict in Assets/Scenes/DoorPrototype.unity
```

**`assistant/foreground-nsc-062-materialization`** (169 paths auto-merged cleanly, 170 conflict/warning messages):
```
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_idle_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_idle_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_idle_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_idle_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_walk_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_walk_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_walk_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_walk_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_idle_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_idle_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_idle_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_idle_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_walk_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_walk_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_walk_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_walk_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_idle_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_idle_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_idle_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_idle_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_walk_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_walk_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_walk_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_walk_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_idle_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_idle_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_idle_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_idle_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_walk_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_walk_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_walk_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_walk_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_005.png.meta
CONFLICT (content): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/WizardAnimationPlayModeTests.cs
warning: Cannot merge binary files: Assets/Scenes/DoorPrototype.unity (main vs. assistant/foreground-nsc-062-materialization)
CONFLICT (content): Merge conflict in Assets/Scenes/DoorPrototype.unity
CONFLICT (content): Merge conflict in Pipeline/AssistantControl/test_unity_materialization.py
CONFLICT (content): Merge conflict in Pipeline/AssistantControl/unity_materialization.py
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/authoritative_validation_policy.json
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/door_prototype_materialization.py
```

**`assistant/review-wizard-lobby`** (169 paths auto-merged cleanly, 170 conflict/warning messages):
```
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_idle_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_idle_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_idle_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_idle_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_walk_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_walk_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_walk_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_Black_walk_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_idle_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_idle_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_idle_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_idle_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_walk_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_walk_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_walk_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Feminine_White_walk_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_idle_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_idle_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_idle_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_idle_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_walk_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_walk_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_walk_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_Black_walk_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_idle_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_idle_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_idle_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_idle_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_walk_north-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_walk_north-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_walk_south-east.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_Masculine_White_walk_south-west.anim
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_005.png.meta
CONFLICT (content): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/WizardAnimationPlayModeTests.cs
warning: Cannot merge binary files: Assets/Scenes/DoorPrototype.unity (main vs. assistant/review-wizard-lobby)
CONFLICT (content): Merge conflict in Assets/Scenes/DoorPrototype.unity
CONFLICT (content): Merge conflict in Pipeline/AssistantControl/test_unity_materialization.py
CONFLICT (content): Merge conflict in Pipeline/AssistantControl/unity_materialization.py
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/authoritative_validation_policy.json
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/door_prototype_materialization.py
```

**`assistant/foreground-nsc-067-selection`** (138 paths auto-merged cleanly, 139 conflict/warning messages):
```
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/south-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/walk/south-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/walk/south-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/north-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/north-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/north.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/west.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/north-west/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_005.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_000.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_001.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_002.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_003.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_004.png.meta
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-west/frame_005.png.meta
CONFLICT (content): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/WizardAnimationPlayModeTests.cs
CONFLICT (add/add): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/WizardGameEntryPlayModeTests.cs
warning: Cannot merge binary files: Assets/Scenes/DoorPrototype.unity (main vs. assistant/foreground-nsc-067-selection)
CONFLICT (content): Merge conflict in Assets/Scenes/DoorPrototype.unity
CONFLICT (content): Merge conflict in Pipeline/AssistantControl/test_unity_materialization.py
CONFLICT (content): Merge conflict in Pipeline/AssistantControl/unity_materialization.py
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/authoritative_validation_policy.json
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/door_prototype_materialization.py
```

**`assistant/nsc-075-builder-prep`** (3 paths auto-merged cleanly, 1 conflict/warning messages):
```
CONFLICT (content): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs
```

**`assistant/cardinal-staging`** (6 paths auto-merged cleanly, 4 conflict/warning messages):
```
CONFLICT (content): Merge conflict in Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs
CONFLICT (content): Merge conflict in Pipeline/TaskGraph/RESOURCE_GROUPS.yaml
CONFLICT (content): Merge conflict in Pipeline/TaskGraph/WORK_ID_MAP.json
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/authoritative_validation_policy.json
```

**`assistant/task-nsc-070-wizard-animation-audit`** (4 paths auto-merged cleanly, 4 conflict/warning messages):
```
CONFLICT (content): Merge conflict in Pipeline/TaskGraph/RESOURCE_GROUPS.yaml
CONFLICT (content): Merge conflict in Pipeline/TaskGraph/WORK_ID_MAP.json
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/authoritative_validation_policy.json
CONFLICT (add/add): Merge conflict in Tasks/NSC-070.yaml
```

**`assistant-ci-boundary-20260912`** (56 paths auto-merged cleanly, 51 conflict/warning messages):
```
CONFLICT (add/add): Merge conflict in .github/workflows/assistant-candidate-ci.yml
CONFLICT (content): Merge conflict in .github/workflows/d1b2-core-deterministic.yml
CONFLICT (content): Merge conflict in .github/workflows/task-review-agent-deterministic.yml
CONFLICT (content): Merge conflict in AGENTS.md
CONFLICT (add/add): Merge conflict in Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md
CONFLICT (content): Merge conflict in Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/CURRENT.md
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/README.md
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/__main__.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/admission.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/assistant_restored_candidate.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/automation_policy.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/candidate.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/decomposition.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/dependencies.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/graph_controller.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/inspect_project.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/post_crew_workflow.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/readiness.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/source_update.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_admission.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_admission_worktree.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_assistant_restored_candidate.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_decomposition.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_graph_controller.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_inspect_project.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_post_crew_workflow.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_scope.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_source_update.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_unity_materialization.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/test_viewer.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/unity_materialization.py
CONFLICT (add/add): Merge conflict in Pipeline/AssistantControl/viewer.py
CONFLICT (add/add): Merge conflict in Pipeline/ExecutionCrew/role_profiles.py
CONFLICT (content): Merge conflict in Pipeline/ExecutionCrew/run_crew.py
CONFLICT (add/add): Merge conflict in Pipeline/ExecutionCrew/session_pool.py
CONFLICT (content): Merge conflict in Pipeline/TaskDecomposition/prompts.py
CONFLICT (content): Merge conflict in Pipeline/TaskDecomposition/round_robin_decomposition.py
CONFLICT (content): Merge conflict in Pipeline/TaskDecomposition/tests/live_decomposition_smoke_test.py
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/GauntletView/index.html
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/GauntletView/server.py
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/GauntletView/tests/browser_smoke_test.cjs
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/GauntletView/tests/gauntlet_view_smoke_test.py
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/authoritative_candidate_validation.py
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/door_prototype_materialization.py
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/provider_budget.py
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/provider_profiles.py
CONFLICT (content): Merge conflict in Pipeline/TaskReviewAgent/tests/ci_workflow_split_smoke_test.py
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/tests/provider_profiles_test.py
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/tests/public_synthetic_authority_smoke_test.py
CONFLICT (add/add): Merge conflict in Pipeline/TaskReviewAgent/tests/task_id_width_smoke_test.py
```

## Recommended disposition

Sorted MERGE first, then NEEDS-HUMAN-EYE, then DUPLICATE, then SUPERSEDED. Reasoning for every branch is in its own line -- 
none of this is name-based; all of it traces to the actual merge-tree/diff output above.

| Branch | Disposition | Why |
|---|---|---|
| `codex/nsc061-source-review-20260914` | **MERGE** | 1 file, pure prose (Docs/Art/Wizard/NSC-061_SOURCE_REVIEW_20260914.md, +9), clean merge, zero risk. Safe to land as documentation regardless of what happens to the rest of the wizard-art queue. |
| `assistant/nsc-075-integration-prep` | **MERGE** | 2 files (WizardAnimationController.cs, WizardAnimationPlayModeTests.cs), 146+/42-, clean merge with NO conflicts -- the only gameplay-code branch in this entire wave that merges cleanly. Adds NSC-075 eight-direction classifier tests. Best candidate in waves 4-5 for a normal code review and merge. |
| `assistant/integrate-background-plus-decomp` | **MERGE** | 2 files (docker_workers.py + its test), 73+/2-, clean merge, no conflicts. Small, tested, low-risk pipeline fix normalizing Windows Docker bind mounts. |
| `assistant/restored-meta-companion-fix` | **MERGE** | 2 files (assistant_restored_candidate.py + its test), 34+/4-, clean merge, no conflicts. Small, tested, low-risk pipeline fix for deterministic Unity metadata on restored candidates. |
| `assistant/NSC-073-current` | **NEEDS-HUMAN-EYE** | Primary of a 4-way byte-identical duplicate group (variant A: 129+/4-). One of three competing visual fixes for the same defective frames; pick against variant B (codex/nsc073-visual-stage) and variant C (codex/nsc073-reuse-alt). |
| `codex/nsc073-reuse-alt-20260914` | **NEEDS-HUMAN-EYE** | Primary of a 2-way duplicate group. Variant C (134+/4-): reuses an existing PixelLab northeast tail rather than regenerating frames 004/005. A materially different visual approach from variants A/B. |
| `codex/nsc073-visual-stage-20260914` | **NEEDS-HUMAN-EYE** | Variant B (129+/4-, different tree than variant A despite identical stat line). Later (09-14) commit message claims to fix GUID preservation on top of variant A's approach -- worth checking first. |
| `assistant/NSC-074-current` | **NEEDS-HUMAN-EYE** | 212 files, clean merge; near-identical to codex/nsc074-current-review-20260914 but missing the PIXELLAB_CARDINAL_CONTACT_SHEET.png doc image (not a byte-identical tree, so not filed as DUPLICATE, but appears to be a strict subset -- compare after picking among the current-review family). |
| `codex/nsc073-074-current-review-20260914` | **NEEDS-HUMAN-EYE** | Largest of the NSC-074 family (214 files, 2222+/5-), combines an NSC-073 sprite-GUID-provenance doc correction with the NSC-074 cardinal set. Latest author ("Art Review", 09-14) -- likely the most refined candidate; review this one first in the family. |
| `codex/nsc074-current-review-20260914` | **NEEDS-HUMAN-EYE** | Primary of a 2-way byte-identical duplicate (same tip commit 5b8c4634b as codex/nsc074-exact-unity, confirming the plan's note). Clean merge, 213 files (209 art), includes WizardCardinalSourceAuditTests.cs. Needs visual review of the cardinal walk set. |
| `codex/nsc077-current-main-review-20260914` | **NEEDS-HUMAN-EYE** | Same file count and insertion count as codex/nsc077-gameplay-visibility (52 files, 3142+) but a different resulting tree -- not a byte-identical duplicate. Same scene conflict and same 19 non-art code/prefab/test files. Compare directly against codex/nsc077-gameplay-visibility before picking one; likely near-redundant with it. |
| `codex/nsc077-gameplay-visibility-20260914` | **NEEDS-HUMAN-EYE** | 52 files, 3142+, conflicts on the DoorPrototype.unity scene (binary, cannot auto-merge) plus real gameplay code (StationaryEnemy* scripts/prefabs/tests). The 2026-09-14 plan guessed this was the superset of codex/nsc077-current-main-review; current data shows codex/nsc077-stationary-enemies is actually larger (70 files) -- the plan's superset assumption has flipped since main moved. Needs a human to diff the code against stationary-enemies and rebuild the scene via the builder rather than merging YAML. |
| `codex/nsc077-stationary-enemies-20260914` | **NEEDS-HUMAN-EYE** | Broadest of the three (70 files, 3442+): includes 18 extra Source/*.meta add/add conflicts the other two lack, i.e. it independently stages enemy source art main doesn't have in this exact form. Conflicts on the same DoorPrototype.unity scene. Review this one first in the family -- it is the current superset, not codex/nsc077-gameplay-visibility as the 09-14 plan assumed. |
| `codex/nsc064-connections-20260914` | **NEEDS-HUMAN-EYE** | 21 files (14 art + 7 Docs images/md), clean merge, no conflicts. Matches the plan's characterization as the superset holding selection, connection pieces and the joins doc. Recommended pick of the NSC-064 family, pending visual review. |
| `codex/nsc064-main-review-20260914` | **NEEDS-HUMAN-EYE** | Primary of a 2-way byte-identical duplicate. 11 files (8 art + 3 docs), clean merge; its 3 non-art doc files are all also present in codex/nsc064-connections-20260914's larger set, so this looks like a strict subset of that branch. Compare against codex/nsc064-connections-20260914 first -- likely redundant with it. |
| `codex/nsc063-melee-ne-single-cleaver-20260914` | **NEEDS-HUMAN-EYE** | 4 files, all under Docs/Art/Enemies/Candidates/melee_ne_single_cleaver/ (a README plus 3 comparison PNGs incl. one explicitly named 'rejected_first_inpaint.png'). Clean merge, no conflicts. Pure art-candidate staging; needs Vincent's visual call, not a code review. |
| `codex/nsc093-current-main-review-20260914` | **NEEDS-HUMAN-EYE** | Primary of a 2-way byte-identical duplicate. 102 files (97 art + 5 docs), clean merge, no conflicts -- adds a full new eight-direction enemy walk set main doesn't have. Needs visual review before merge. |
| `codex/nsc070-validation-20260914` | **NEEDS-HUMAN-EYE** | Net content is a single test file (WizardArtIntegrationTests.cs, +50) but merge-tree reports a real conflict on the DoorPrototype.unity scene (binary, cannot auto-merge) even though the written tree happens to match main's blob there (so the plain file diff under-reports it -- see Methodology note). Needs a human to actually open the preserved review scene in Unity, per the branch's own stated purpose. |
| `assistant/foreground-nsc-066-title-screen` | **NEEDS-HUMAN-EYE** | Commit subject says 'Document NSC-066 validation results' but the actual diff is 496 insertions of code to Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs -- another case where the label does not match the content. Conflicts on the DoorPrototype.unity scene. Needs a code-level read, not just a name or subject check, to see if any of the 496 lines are still missing from main's scene builder. |
| `assistant/foreground-nsc-067-selection` | **NEEDS-HUMAN-EYE** | 137 files, same pervasive wizard-art add/add conflict pattern as its two siblings above, EXCEPT it uniquely adds Assets/NoSafeCircle/DoorPrototype/Tests/WizardGameEntryPlayModeTests.cs, which neither sibling has. Otherwise as redundant as the other two -- but that one test file may be worth extracting by hand before this branch is closed. |
| `assistant/cardinal-staging` | **NEEDS-HUMAN-EYE** | 9 files, same commit subject ('Clarify NSC-074 Windows source audit') as assistant/nsc-074-cardinal-art but a completely different tree and twice the file count -- confirms branches can share a subject line and still hold unrelated content, so subjects need the same skepticism as branch names. Conflicts on the same 3 hot pipeline registry files as the already-SUPERSEDED nsc-074-cardinal-art, but additionally touches DoorPrototypeGlobalSceneBuilder.cs and WizardAnimationController.cs, which that sibling does not. Worth a quick code diff before closing, since the registry-file conflicts alone don't prove the 2 extra code files are redundant. |
| `assistant/nsc-075-builder-prep` | **NEEDS-HUMAN-EYE** | 4 files, subject 'Validate wizard sorting in composed room world'. Only 1 of 4 files actually conflicts (WizardArtIntegrationTests.cs); the other 3 (DoorPrototypeGlobalSceneBuilder.cs, WizardAnimationController.cs, WizardAnimationPlayModeTests.cs) are real gameplay-sorting code. Small, isolated conflict -- worth a quick human look rather than closing outright. |
| `assistant/nsc-073-pixellab` | **DUPLICATE OF `assistant/NSC-073-current`** | Byte-identical resulting merge tree -- see Duplicate groups above. |
| `codex/nsc073-alt-current-stage-20260914` | **DUPLICATE OF `codex/nsc073-reuse-alt-20260914`** | Byte-identical resulting merge tree -- see Duplicate groups above. |
| `codex/nsc073-main-validation-20260914` | **DUPLICATE OF `assistant/NSC-073-current`** | Byte-identical resulting merge tree -- see Duplicate groups above. |
| `codex/nsc073-ne-alternate-20260914` | **DUPLICATE OF `assistant/NSC-073-current`** | Byte-identical resulting merge tree -- see Duplicate groups above. |
| `codex/nsc074-exact-unity-20260914` | **DUPLICATE OF `codex/nsc074-current-review-20260914`** | Byte-identical resulting merge tree -- see Duplicate groups above. |
| `codex/nsc064-pixellab-20260914` | **DUPLICATE OF `codex/nsc064-main-review-20260914`** | Byte-identical resulting merge tree -- see Duplicate groups above. |
| `codex/nsc093-pixellab-walk-20260914` | **DUPLICATE OF `codex/nsc093-current-main-review-20260914`** | Byte-identical resulting merge tree -- see Duplicate groups above. |
| `assistant/nsc-074-cardinal-art` | **SUPERSEDED** | MISLEADING NAME: despite the NSC-074 cardinal-art name, this branch's diff against current main contains ZERO art files. Its only content is 3 conflicting edits to hot pipeline registry files (RESOURCE_GROUPS.yaml, WORK_ID_MAP.json, authoritative_validation_policy.json) plus a conflicting edit to WizardCardinalSourceAuditTests.cs -- all superseded by main's own independent edits to those same files (all four are add/add or content conflicts). No unique art or code value found. |
| `assistant/room-nsc-045` | **SUPERSEDED** | Conflicts on Assets/Scenes/Rooms/BoneArchive.unity plus 8 Tasks/*.yaml contracts (NSC-029/044/045/046/047/048/049/069) and 3 Editor/Scripts files, all as add/add against main's own versions. This is a 09-12 branch; per this session's memory, NSC-045-048/049/069 room layouts were independently revised and committed to local main on 09-15, i.e. after this branch. Main's contracts and scene should already supersede it, but given the branch touches 8 live task contracts this is worth a spot-check, not a blind close. |
| `assistant/foreground-nsc-062-materialization` | **SUPERSEDED** | 168 files, almost entirely add/add conflicts: every one of the ~160 Wizard Generated/.anim and Source/PixelLab/*.meta files collides with content main already has independently (different GUIDs from an old materialization pass). The 8 non-art code files (SceneBuilder, WizardAnimationController, 2 tests, 4 Pipeline materialization scripts) all conflict too. No content found here that main plausibly lacks. |
| `assistant/review-wizard-lobby` | **SUPERSEDED** | 168 files, same conflict pattern and same 8 non-art code files as assistant/foreground-nsc-062-materialization (different tree, not byte-identical, but functionally the same old wizard-materialization snapshot). No unique value found beyond that sibling. |
| `assistant/task-nsc-070-wizard-animation-audit` | **SUPERSEDED** | Adds Tasks/NSC-070.yaml as an add/add conflict, meaning main already has its own NSC-070 task contract independent of this 09-12 branch. Also conflicts on the same 3 hot pipeline registry files seen across several other superseded branches. codex/nsc070-validation-20260914 (wave 4, dated 09-14) represents the more current NSC-070 thread. |
| `assistant-ci-boundary-20260912` | **SUPERSEDED** | 51 files changed, every single one an add/add or content conflict (.github/workflows, AGENTS.md, and the bulk of Pipeline/AssistantControl, ExecutionCrew, TaskDecomposition, TaskReviewAgent). This 09-12 orchestration line has been completely superseded by main's own independent evolution of the same modules -- exactly the outcome the 2026-09-14 plan predicted ('likely close it, salvage individual fixes only if main lacks them'). 100% conflict rate found no gaps to salvage. |

### Totals

- MERGE: 4
- NEEDS-HUMAN-EYE: 18
- DUPLICATE: 7
- SUPERSEDED: 6
- Total inspected: 35
