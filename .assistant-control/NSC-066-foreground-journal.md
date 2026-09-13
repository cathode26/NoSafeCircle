# NSC-066 Foreground Journal

## Current state

- Worktree: `C:\NSC\NoSafeCircle-Foreground-NSC-066`
- Branch: `assistant/foreground-nsc-066-title-screen`
- Starting commit: `eab9bad9325a3e28894a64b6bbde92ee58e75476`
- Task contract: `Tasks/NSC-066.yaml` revision 1
- Status: implementation complete; preparing exact-path commit and clean validation

## Reference evidence

- Authorized reference checkout: `C:\NSC\NSC\ReferenceProjects\SpaceInvaders`
- Snapshot commit: `f7f09483cc2ed76d31c71aa2e2690744170f36f1`
- The reference checkout already had a deleted `SpaceInvaders.zip`; it was treated as read-only and left unchanged.
- Inspected `Assets/Scripts/MainMenuUI.cs`, `Assets/Scripts/MainMenuElements.cs`, and `Assets/Scenes/MainMenuScene.unity`.
- Reused idea: one screen-space Canvas, a large primary button, and a direct callback that hides the menu and requests the next flow step. No code or assets were copied.

## TODO

- Commit the exact NSC-066 changed paths with the guarded automation identity.
- Run clean committed Edit Mode and Play Mode validation.
- Inspect the committed diff and final Git status.

## Changed paths

- `.assistant-control/NSC-066-foreground-journal.md`
- `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`
- `Assets/NoSafeCircle/DoorPrototype/Scripts/TitleScreenController.cs`
- `Assets/NoSafeCircle/DoorPrototype/Scripts/TitleScreenController.cs.meta`
- `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/TitleScreenSceneBuilderTests.cs`
- `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/TitleScreenSceneBuilderTests.cs.meta`
- `Assets/NoSafeCircle/DoorPrototype/Tests/TitleScreenPlayModeTests.cs`
- `Assets/NoSafeCircle/DoorPrototype/Tests/TitleScreenPlayModeTests.cs.meta`
- `Assets/Scenes/DoorPrototype.unity`

## Test commands and results

- Unity executable/version: `C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe`, Unity `6000.1.8f1`.
- Scene materialization: `-batchmode -nographics -quit -executeMethod NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build`; exit `0`; `C:\NSC\NSC-066-build.log` records `Door Prototype scene built` and successful batch exit.
- Development Edit Mode filter: `NoSafeCircle.DoorPrototype.Tests.Editor.TitleScreenSceneBuilderTests`; latest result `Passed`, total `3`, passed `3`, failed `0`, skipped `0`; XML `C:\NSC\NSC-066-editmode-dev.xml`; log `C:\NSC\NSC-066-editmode-dev.log`.
- Development Play Mode filter: `NoSafeCircle.DoorPrototype.Tests.TitleScreen`; latest result `Passed`, total `3`, passed `3`, failed `0`, skipped `0`; XML `C:\NSC\NSC-066-playmode-dev.xml`; log `C:\NSC\NSC-066-playmode-dev.log`.
- `python Pipeline\TaskGraph\taskcontrol.py validate`: PASS, 68 active task contracts, connected/acyclic parent hierarchy, acyclic dependency graph.
- `git diff --check`: PASS after normalizing Unity-authored YAML trailing spaces.
- Clean committed validation: pending.
- Unity repeatedly generated 177 `.meta` files for preexisting, out-of-scope wizard source art and settings-only churn. The pre-run status proved these were new Unity import side effects; their inventory was inspected and they were removed/restored without changing the source art.

## Commit

- Pending.

## Blockers

- Automatic approval review rejected running the whole legacy `DoorPrototypeSceneBuilderTests` fixture in this dirty worktree because it considered the production scene-builder call path capable of rewriting the canonical scene. The safer NSC-066 in-memory fixture now directly covers the existing NSC-039 camera axis and Tilemap/SpriteRenderer sorting bands.
- The first sandboxed Unity launch could not write the licensing database and exited `199`. The authorized rerun outside the filesystem sandbox connected to the existing license, compiled, built the scene, and exited `0`.

## Visual review

- Unity project: `C:\NSC\NoSafeCircle-Foreground-NSC-066`
- Scene: `Assets/Scenes/DoorPrototype.unity`
- Enter Play Mode at the canonical 1920x1080 reference resolution, confirm the opaque title screen is readable, then click **Start Game** once and confirm the title hides while gameplay input remains suspended for the wizard-selection boundary.
