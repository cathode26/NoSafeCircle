# Author report: fix/builder-tests-spawn-camera-20260917

Author: Game Agent (Claude). Head `a2762a3e4`, base local main `a58d21e31`. One commit changes one file: `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs`.

## Why
- Since `9a3d22c56` ("Playable build: chase enemy, fire-caster enemy, fireball, win and death screens", 2026-09-16), `DoorPrototypeGlobalSceneBuilder.PlayerSpawnPosition` has been (-10, 0, -22), in the Ruined Entry's south-west corner.
- Two Edit Mode tests still assumed the old start and fail on main. Reproduced on `32c6223d3` by the Game Agent on 2026-09-17: 2 tests, 0 passed; log `C:\nscrev\reports\nsc077\unity\main-32c6223d3-builder-tests.log`.
  - `Build_PlayerStartsAtCharacterControllerGroundedHeight`: "Expected: 0.0f +/- 9.99999975E-05f But was: -10.0f".
  - `Build_MainCamera_FramesPlayerAndStartingDoorInView`: "Starting door must be comfortably inside the camera view at scene start, was viewport (1.56, 0.66, 24.64)".

## Intended test behaviour (decided by the GER Agent, 2026-09-17)
- **Spawn test:** the player starts at the builder's `PlayerSpawnPosition` at CharacterController grounded height (y = skinWidth 0.08), not at a literal (0, -4).
  - `PlayerSpawnPosition` is `private static readonly` in the `internal` class `NoSafeCircle.DoorPrototype.Editor.World.DoorPrototypeGlobalSceneBuilder`. The test reads it by reflection, the same way `WizardArtIntegrationTests` reads `WizardDirections`.
- **Camera test:** the main camera frames the player at scene start, with the player's viewport position within 0.15 of the center on both axes and z > 0.
  - The starting-door-in-view check is dropped: the run deliberately starts far from D1.
  - The test name is kept for continuity with recorded evidence XMLs under `Pipeline/TaskGraph/evidence/`.
- The spawn, the camera and every gameplay or builder file are untouched.

## Expected geometry (derived, not measured)
- The camera sits at player + (10, 10, -10) with Euler (30, -45, 0), orthographic size 8.
- The player's feet project about 1.585 units below the view center, which is viewport about (0.50, 0.40).

## Tests
- Unity Edit Mode `NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests` on `a2762a3e4`: run by the Game Agent. The result is appended below when it finishes.
- Codex cannot run Unity. Review by reading the code.
