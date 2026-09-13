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

- The authenticated NSC-062 Unity candidate is committed on this branch. It contains all four approved variants, 128 imported source frames, 32 generated idle/walk clips, one Animator controller, and the player-owned presentation driver.
- Unity 6000.1.8f1 built the candidate scene and generated assets successfully. The visual candidate is ready for focused automated validation and Vincent's visual review.

## Next

- Re-run focused Unity EditMode and PlayMode validation when the Unity licensing IPC service is available.
- Vincent opens project `C:\NSC\NoSafeCircle-Foreground-NSC-062-Fix` and scene `Assets/Scenes/DoorPrototype.unity` in Play Mode.

## Blockers

- Unity EditMode and PlayMode runner validation is blocked by Unity licensing startup: both EditMode attempts exited 199 after `Timed-out after 60.01s, waiting for channel: "LicenseClient-VincentLiguori"`; the runner cleanup reported a clean worktree. The second artifact is `C:\Users\VincentLiguori\AppData\Local\Temp\NoSafeCircle-UnityTests-b772e412ff184a6a8342d7844898703c`.
- Unity visual approval remains pending and cannot be claimed by automated tests.

## Files

- `Pipeline/AssistantControl/unity_materialization.py`
- `Pipeline/AssistantControl/test_unity_materialization.py`
- `Pipeline/TaskReviewAgent/door_prototype_materialization.py`
- `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`
- `.assistant-control/NSC-062-foreground-journal.md`

## Tests

- `python -m unittest Pipeline.AssistantControl.test_unity_materialization -v` — PASS, 9 tests in 77.418s.
- `git diff --check` — PASS.
- Unity executable check — PASS: `C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe` exists.
- Focused Unity EditMode — BLOCKED before test discovery by licensing IPC; exit code 199. Log: `C:\Users\VincentLiguori\AppData\Local\Temp\NoSafeCircle-UnityTests-b772e412ff184a6a8342d7844898703c\unity.log`.
- Focused Unity PlayMode — NOT RUN because the identical Unity licensing startup failure prevented the focused EditMode run.
- Required Unity visual check — pending Vincent's review of the integrated candidate in `Assets/Scenes/DoorPrototype.unity`.
- Unity builder — PASS: `Door Prototype scene built at Assets/Scenes/DoorPrototype.unity`; log `C:\NSC\NSC-062-foreground-unity-build.log`.
- Remaining visual checklist: all four presentation/skin choices, idle and walking loops in north-east/north-west/south-east/south-west, gameplay-scale readability, respectful treatment, feet contact, and wall/door sorting.
