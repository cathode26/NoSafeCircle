# NSC-062 foreground journal

## Done

- Confirmed the checkout is `assistant/foreground-nsc-062-materialization` and kept all work inside this checkout.
- Confirmed the four NSC-061 approved PixelLab source variants are present under `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab`.
- Extended Door Prototype materialization authority so the deterministic Unity builder may write the task-owned wizard directory, while crew changes remain exact-file scoped.
- Restricted generated output under that directory to Unity-serialized files and retained cleanup of incidental tracked Unity output.
- Added the NSC-062 authoritative EditMode and PlayMode test filters.
- Added focused regression coverage for generated wizard-root handling.

## Current

- The materialization plumbing is ready for an authenticated reviewed NSC-062 code candidate.
- The canonical builder in this checkout still creates the purple placeholder wizard. No wizard controller, runtime presentation component, generated animation assets, or reviewable four-variant Unity candidate exists yet.

## Next

- Parent agent supplies the reviewed NSC-062 candidate changing the builder, wizard presentation/controller code, and focused Unity tests.
- Run `materialize-candidate NSC-062 --candidate-commit <exact-sha>` with Unity 6000.1.8f1 available.
- Run the committed EditMode and PlayMode validation, then have Vincent inspect `Assets/Scenes/DoorPrototype.unity` in Play Mode for all four combinations and four directions.

## Blockers

- No authenticated NSC-062 candidate record is present in this checkout, so Unity materialization cannot be launched safely yet.
- Unity visual approval remains pending and cannot be claimed by automated tests.

## Files

- `Pipeline/AssistantControl/unity_materialization.py`
- `Pipeline/AssistantControl/test_unity_materialization.py`
- `Pipeline/TaskReviewAgent/door_prototype_materialization.py`
- `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`
- `.assistant-control/NSC-062-foreground-journal.md`

## Tests

- `python -m unittest Pipeline.AssistantControl.test_unity_materialization -v` — PASS, 9 tests in 52.263s.
- `git diff --check` — PASS.
- Unity executable check — PASS: `C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe` exists.
- Required Unity visual check — pending the integrated candidate; inspect `Assets/Scenes/DoorPrototype.unity` in Play Mode after materialization.
