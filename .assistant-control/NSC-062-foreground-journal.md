# NSC-062 foreground journal

## Done

- Confirmed the checkout is `assistant/foreground-nsc-062-materialization` and kept all work inside this checkout.
- Confirmed the four NSC-061 approved PixelLab source variants are present under `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab`.
- Extended Door Prototype materialization authority so the deterministic Unity builder may write the task-owned wizard directory, while crew changes remain exact-file scoped.
- Restricted generated output under that directory to Unity-serialized files and retained cleanup of incidental tracked Unity output.
- Added the NSC-062 authoritative EditMode and PlayMode test filters.
- Added focused regression coverage for generated wizard-root handling.
- Implemented `WizardAnimationController` and builder wiring for the persistent player visual.
- Imported the approved source frames in Unity and generated the four-variant animation candidate.
- Corrected the canonical initial direction to `south-east` in both the runtime controller and builder default-sprite binding.
- Added regression coverage for non-null saved Player/Visual sprite, canonical initial direction/state, Player/Visual versus WallTilemap sorting, Pivot sorting, and camera CustomAxis sorting.
- Rebuilt the task-owned scene successfully with Unity 6000.1.8f1.

## Approved art

- Manifest: `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/source-inventory.json`.
- `masculine-dark`: `.../masculine-dark/raw/Wizard_-_Masculine_Dark.zip`, SHA-256 `97cc3eeb9a0fd4d7a7c2202b38939e8806668315b5d21f889fa963433c197967`.
- `feminine-dark`: `.../feminine-dark/raw/Wizard_-_Feminine_Dark.zip`, SHA-256 `717b1f30ea923a7a13d19c79277328e947871ead114334d17bbb620d52c008cf`.
- `masculine-light`: `.../masculine-light/raw/Wizard_-_Masculine_Light.zip`, SHA-256 `a36540da22f603a63535f6275f3c4d5926795270c6798fcad4bc6f289f89fe49`.
- `feminine-light`: `.../feminine-light/raw/Wizard_-_Feminine_Light.zip`, SHA-256 `63b30bd14e456fe4210b5045bdf044c332da2d433fc5c7606441dcc356a304d0`.
- Each raw hash matches `Docs/Art/Wizard/PIXELLAB_GENERATION.md`; each selected directory contains 32 authorized PNGs and all 128 selected PNG hashes match the manifest. Optional raw animations remain excluded.

## Imported paths

- Source `.meta` files: `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/**`.
- Generated clips: `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Wizard_{Masculine,Feminine}_{White,Black}_{idle,walk}_{north-east,north-west,south-east,south-west}.anim` (32 clips plus `.meta`).
- Controller: `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/WizardAnimator.controller` plus `.meta`.
- Runtime component: `Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs` plus `.meta`.
- Scene: `Assets/Scenes/DoorPrototype.unity`.

## Current

- Correction commit: `102660586d810ec1144e599dae28743232d79e69`.
- The corrected NSC-062 Unity candidate is ready for Vincent to reopen. It contains all four approved variants, 128 imported source frames, 32 generated idle/walk clips, one Animator controller, and the player-owned presentation driver.
- Unity 6000.1.8f1 built the candidate scene and generated assets successfully. The visual candidate is ready for focused automated validation and Vincent's visual review.

## Next

- Re-run focused Unity EditMode and PlayMode validation after Vincent closes the open Unity Editor instance holding the project lock.
- Vincent opens project `C:\NSC\NoSafeCircle-Foreground-NSC-062-Fix` and scene `Assets/Scenes/DoorPrototype.unity` in Play Mode.

## Blockers

- Direct focused EditMode validation was blocked after licensing succeeded because Vincent's open Editor owns the project: `HandleProjectAlreadyOpenInAnotherInstance`; no XML was produced. The preserved log is `C:\NSC\NSC-062-foreground-editmode-correction.log`.
- The incidental `ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json` modification remains unstaged by design.
- Unity visual approval remains pending and cannot be claimed by automated tests.

## Files

- `Pipeline/AssistantControl/unity_materialization.py`
- `Pipeline/AssistantControl/test_unity_materialization.py`
- `Pipeline/TaskReviewAgent/door_prototype_materialization.py`
- `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`
- `.assistant-control/NSC-062-foreground-journal.md`

## Tests

- `python -m unittest Pipeline.AssistantControl.test_unity_materialization -v` — PASS, 9 tests in 140.462s.
- `git diff --check` — PASS.
- Unity executable check — PASS: `C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe` exists.
- Earlier pre-correction focused Unity EditMode attempt — blocked before test discovery by licensing IPC; exit code 199. Log: `C:\Users\VincentLiguori\AppData\Local\Temp\NoSafeCircle-UnityTests-b772e412ff184a6a8342d7844898703c\unity.log`.
- Focused Unity EditMode correction run — BLOCKED by open project lock after license connection; log `C:\NSC\NSC-062-foreground-editmode-correction.log`.
- Focused Unity PlayMode — NOT RUN because the open project lock prevented the focused EditMode run.
- Required Unity visual check — pending Vincent's re-review of the corrected `Assets/Scenes/DoorPrototype.unity`.
- Unity builder correction — PASS: `Door Prototype scene built at Assets/Scenes/DoorPrototype.unity`; log `C:\NSC\NSC-062-foreground-unity-build-correction.log`.
- Serialized scene verification — Player/Visual prefab override has non-null `m_Sprite` `{fileID: 21300000, guid: ba32e804c3c549e43aa53b4a61cad7be, type: 3}`, resolving to `masculine-light/selected/standing/south-east.png.meta`; world sprite sorting is Default layer/order 0 with Pivot sort point, matching WallTilemap; camera is built with CustomAxis.
- Remaining visual checklist: all four presentation/skin choices, idle and walking loops in north-east/north-west/south-east/south-west, gameplay-scale readability, respectful treatment, feet contact, and wall/door sorting.
