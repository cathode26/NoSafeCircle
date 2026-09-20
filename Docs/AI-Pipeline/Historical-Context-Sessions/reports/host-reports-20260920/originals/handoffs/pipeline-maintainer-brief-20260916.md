# Pipeline Maintainer handoff: two pipeline defects (2026-09-16)

From the game developer / integration steward session. Vincent assigned both to the Pipeline Maintainer.

## 1. Stub `.meta` files import as cubemap cookies

**Defect.**
- `Pipeline/ExecutionCrew/run_crew.py` `unity_meta_bytes` writes deterministic GUID-only metas: `fileFormatVersion: 2` + `guid`, plus `folderAsset: yes` for folders.
- In Unity 6000.1.8f1, a PNG with such a meta imports with the importer's native defaults, not new-asset defaults: `textureShape: 2` (Cube), `cookieLightType: 2` (Point) and `applyGammaDecoding: 1`.
- Unity never rewrites a stub meta, so the tree stays clean and nothing fails until a builder needs a Sprite.

**Evidence.**
- The NSC-074 cardinal wizard frames (96 PNGs, `Art/Wizard/Source/PixelLab/*/selected/walk/{north,east,south,west}`) shipped with stub metas.
- NSC-075's `DoorPrototypeSceneBuilder.Build` threw `Wizard source did not import as a Sprite` on the first cardinal frame. Log: `C:\nscrev\reports\nsc075\builder-run1.log`.
- All 248 non-stub texture metas in the repo have `textureShape: 1`. So do the NSC-093 enemy walk metas, which Unity created from no meta at all.

**Workaround already on main,** in `DoorPrototypeGlobalSceneBuilder.ImportWizardSprite`:
- `0d28b0bf5` sets `importer.textureShape = TextureImporterShape.Texture2D`;
- `bf97d116c` resets `m_ApplyGammaDecoding` and `m_CookieLightType` through a SerializedObject.
- This only covers wizard sources. Any other builder that converts crew-staged art (enemies, doors, environment) will hit the same defect.

**Ask.**
- Fix it at the source: write importer-complete metas, or stop writing stub metas for textures. Alternatively, provide one shared normalization helper for builders.
- Add a regression test.
- Check the related unmerged branch `assistant/restored-meta-companion-fix` (`807bd7b86`), which lets restored candidates carry deterministic `unity_meta_bytes` companions. The integration steward will merge it only after your view.

## 2. The viewer regression suite fails on main

**Defect.** On local main `7fc15c528` (2026-09-16), `python -m unittest Pipeline.AssistantControl.test_viewer` reports 57 tests, **4 failures, 16 errors**.

**Existing fix, never merged.**
- Checkout `C:\NSC\AssistantControlViewerRegression-20260913`, branch `assistant/viewer-regression-suite-20260913`, commit `c12f70287` ("Repair AssistantControl viewer regression fixtures"), on the old base `2eee4670b`.
- Reported root cause: the shared disposable Git fixtures still used legacy minimal task contracts, while the viewer's full-graph conformance reader requires schema-v2 contracts.
- The fix added a shared schema-v2 fixture builder and updated stale assertions.
- Its green status was never independently confirmed, and main has moved a long way since. It needs a port onto current main and a full green run.

## For context only (no action requested here)

- **Decomposition-reliability stack:** `C:\nscrev\final-integration`, `throughput/decomposition-final-integration` @ `4fd54b8c`, 33/34 suites green on 9/14. None of it is on main. Standing rule: it waits for Astra's review, then Codex integrates.
  - The cut-off work-in-progress in `C:\nscrev\codex-revision-review-fixes-20260913` appears redundant with it.
- **Clean pipeline branch waiting on the integration steward:** `assistant/integrate-background-plus-decomp` (`8d8ae6cd0`), a Windows Docker bind-mount path fix in `docker_workers.py` with a test.
- **Research reports:**
  - `C:\nscrev\reports\resume-plan-research\unfinished-work.md`;
  - `C:\nscrev\reports\merge-and-resume-plan-20260916.md`.
