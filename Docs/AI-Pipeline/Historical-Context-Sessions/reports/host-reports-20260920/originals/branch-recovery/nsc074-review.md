# NSC-074 cardinal wizard walk: branch review (2026-09-16)

Read-only review. Nothing was merged, committed or deleted. Main is `9a3d22c56`.

## Recommendation

Merge `assistant/NSC-074-current` (tip `f7cb0f478`), but only **after** the NSC-073 hat fix.

The contract graph sets the order:

- NSC-073 (hat fix, depends on NSC-070) comes first.
- NSC-074 (cardinal art, depends on NSC-073) comes second.
- NSC-075 (8-direction integration, rev 2, depends on NSC-062, 068, 070, 073 and 074) comes last.

Vincent confirmed on 2026-09-16 that the goal is 8-direction movement and that the hat fix repairs the existing 4-direction walk. On main, frames 004 and 005 of the light female wizard's north-east walk also turn her to face the camera. The comparison is in `nsc073-art/`.

If Vincent picks hat version A (frame_005 = `ebcece952`), `codex/nsc073-074-current-review-20260914` delivers NSC-073 and NSC-074 in one merge with the conflicts already resolved.

**Update 2026-09-16: C is the recommended hat version.** The source is the 9/13-9/14 record Vincent recovered (`C:\NSC\nsc-codex-0913-0914-digest.md`).
- On 09-14 the Art Recovery session reviewed A in motion. It demoted A to a "tested fallback" (`7fe174fc5`): its frames 004/005 rotate too far toward a rear view.
- It then staged C (`17af0ace6`). C replaces frame 005 with cached PixelLab index 6 from the same animation `1a6e4335`, which returns toward the north-east three-quarter view.
- Frame 004 (index 1) is unchanged and still turns somewhat rearward.
- The 09-15 Codex recommendation of A was based only on diff size and did not know about that review.
- With C, the combined branch above does not apply. Merge `codex/nsc073-reuse-alt-20260914`, then this branch, keeping both sides of the `source-inventory.json` and `PIXELLAB_GENERATION.md` conflicts.

For NSC-075, `assistant/nsc-075-builder-prep` (`5a139770e`, from 09-13) already has the 8-way classifier (`WizardAnimationController.cs`), builder preparation and tests.
- Its merge-tree against main conflicts only in `WizardArtIntegrationTests.cs`.
- `assistant/nsc-075-integration-prep` is its first commit and merges cleanly.
- `assistant/cardinal-staging` is an older copy of the same line and also conflicts in three pipeline registry files.

## What the candidates hold

| Branch | Tip | Cardinal PNG / meta | Art signature |
|---|---|---|---|
| `codex/nsc074-current-review-20260914` | `5b8c4634b` | 96 / 96 | `a74888be15ad` |
| `codex/nsc074-exact-unity-20260914` | `5b8c4634b` (same commit) | 96 / 96 | `a74888be15ad` |
| `assistant/NSC-074-current` | `f7cb0f478` | 96 / 96 | `a74888be15ad` |
| `codex/nsc073-074-current-review-20260914` | `9cf7ae95f` | 96 / 96 | `a74888be15ad` |
| `assistant/nsc-074-cardinal-art` | `a0602783f` | 0 / 0 | none |

- The signature is the SHA-1 of `git ls-tree -r` over `walk/{north,east,south,west}/`, so the art and its metas are byte-identical on every complete branch. This matches Codex's report from 09-15.
- The branches differ only in extras:
  - The `codex/nsc074-*` pair also adds `Docs/Art/Wizard/PIXELLAB_CARDINAL_CONTACT_SHEET.png`.
  - The combined `nsc073-074` branch also carries the NSC-073 hat fix.

## What merging `assistant/NSC-074-current` adds

`git merge-tree --write-tree main assistant/NSC-074-current` exits 0 with tree `eb518697a`: 212 files, +2094/-1.

- 96 frame PNGs and 96 frame `.meta` files, covering 4 wizards x north/east/south/west x frames 000-005.
- 16 direction-folder `.meta` files.
- `source-inventory.json` gains a `cardinal_walk_extension` block. The 128 existing entries keep their hashes.
- `Docs/Art/Wizard/PIXELLAB_GENERATION.md` gets a new NSC-074 section of 140 lines.
- `Tests/Editor/WizardCardinalSourceAuditTests.cs` and its `.meta` add 5 Edit Mode tests:
  - folder layout;
  - each frame is a transparent 180x180 image;
  - deterministic GUIDs that match AssetDatabase;
  - the inventory matches the files on disk;
  - the existing 128 standing and diagonal files are unchanged.
- GUIDs: 113 new metas, none duplicated and none colliding with main.

## Findings

1. **Gameplay does not change.** `WizardAnimationController.cs:106-127` only selects the four diagonals. Using the cardinal walks needs NSC-075's 8-direction work and an NSC-070 revision (see Codex's Task 4 report in `codex-wizard-art-run.log`).
2. **The 96 frame metas are 2-line stubs** (`fileFormatVersion` and `guid`), with no importer block. The inventory's `unity_meta_policy` explains why: "No sprite import settings are written; NSC-075 owns import settings."
   - Expect Unity to fill in its defaults on first import, and plan a follow-up metadata commit like NSC-093's `981002959`. Confirm this in branch-verify.
   - The defaults are not sprite settings. The NSC-093 enemy walk metas on main show what Unity produces: `textureType: 0`, `filterMode: 1`, `spritePixelsToUnits: 100`, pivot at the center. The diagonal wizard frames use `textureType: 8`, point filtering, 180 PPU and a bottom pivot.
   - The repo has no `AssetPostprocessor`, so NSC-075 must set the import settings for the cardinal frames, and NSC-094 must do the same for the enemy walk art.
3. **NSC-073 conflicts after this merge.** Stacking any NSC-073 variant on the merged tree gives 2 conflicts. Both files have additions at the end: `source-inventory.json` (`corrections` vs `cardinal_walk_extension`) and `PIXELLAB_GENERATION.md`. The fix is to keep both sides.
   - The NSC-073 branches do update the `sources` hashes for frames 004/005, so the NSC-074 preservation test still passes once both are in.
4. **Alternative:** `codex/nsc073-074-current-review-20260914` is NSC-074 plus the NSC-073 hat fix with frame_005 = `ebcece952` (variant A), already reconciled.
   - Both top-level inventory keys are present, and all 128 `sources` hashes match their files.
   - Choosing it settles the NSC-073 frame pick now instead of waiting on Codex.

## Verification result (2026-09-16)

- The hat fix, version C, was merged in branch-verify as `18089b060`. Local main was fast-forwarded to it. `WizardArtIntegrationTests` passed 3/3.
- NSC-074 was merged on top as `22955c5a8`.
  - Both conflicts were resolved by keeping both sides.
  - NSC-074's `serialization_note` and generation-doc paragraph were reworded to record the reconciliation.
  - `WizardCardinalSourceAuditTests` and `WizardArtIntegrationTests` passed 8/8 on Unity 6000.1.8f1, and the repository stayed clean.
- **Correction to finding 2:** Unity did not rewrite the GUID-only stub metas during the run, so no follow-up metadata commit is needed.
- `22955c5a8` stays in branch-verify until Vincent confirms the hat in Unity.

## Visual review files

- `nsc074-art/nsc074_cardinal_contact_sheet.png`: every frame, rendered from `assistant/NSC-074-current`.
- `nsc074-art/nsc074_cardinal_walk_loop.gif`: rows are wizards, columns are directions, looped at 120 ms per frame.
- A first look finds no hat, hair or robe continuity breaks. In the south rows, feminine-light frame 003 and masculine-light frame 003 show a blink or expression change.

## After Vincent's go

1. Detach `C:\nscrev\branch-verify` at main and merge `assistant/NSC-074-current` there.
2. Run the Edit Mode filter `NoSafeCircle.DoorPrototype.Tests.Editor.WizardCardinalSourceAuditTests;NoSafeCircle.DoorPrototype.Tests.Editor.WizardArtIntegrationTests` with `Pipeline\Testing\run_unity_tests_clean.ps1`.
3. If Unity expanded the 96 stub metas, commit them as a follow-up.
4. Merge into local main only if the tests pass. Don't push.
