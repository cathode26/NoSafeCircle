# Handoff: the runtime camera reapplies the inverted sort axis (Vincent's door-over-wizard bug)

From: GER Agent. To: Game Agent. Date: 2026-09-17.

## Finding

The code sets two different camera transparency sort axes, and at runtime the wrong one wins.

- **Builder:** `DoorPrototypeGlobalSceneBuilder.BuildCamera` sets `IsometricTransparencySortAxis = (0, 1, 0.26)`. This came from commit `9a3d22c56`, "Playable build", on 09-16.
  - Its comment says Unity draws the larger dot product first, so the Z coefficient must be positive.
  - It also says "A negative coefficient inverted depth and rendered a door in front of a wizard standing south of it."
- **Runtime:** `Scripts/IsometricCameraFollow.cs` is `[ExecuteAlways]`. Its `OnEnable` reapplies `(0, 1, -0.26).normalized` every time the scene loads (commit `f3d461dcc`, 09-13, "Reapply isometric camera sorting on scene load"). `9a3d22c56` did not change this file.
- **Result:** the camera component overrides the builder's +0.26 both in Play Mode and in `BuildInMemoryForTests`. The game therefore runs with the inverted axis. That matches Vincent's 2026-09-17 report: "The door wizard sorting order is wrong," with the D1 door sprite drawn over the wizard's upper body.

## Why tests didn't catch it

- `DoorPrototypeSceneBuilderTests.Build_PlayerAndDoorDepthKeysCrossAtTheDoorGroundPlane` only checks that the wizard's key crosses the door key, so it passes with either sign.
- Three test sites still encode -0.26:
  - `DoorPrototypeSceneBuilderTests.cs:1713` (an assertion);
  - `TitleScreenSceneBuilderTests.cs:126` (`Build_TitleScreenPreservesExistingIsometricSortingConvention`);
  - `Rooms/RuinedEntrySceneTests.cs:285` (the NSC-044 review-capture camera).

## Derivation (please confirm in Unity)

- The camera sits at -Z and +X of its target, looking toward +Z, so a larger world Z is farther.
- With CustomAxis sorting, Unity draws larger dot products first. A positive Z coefficient therefore draws a wizard south of a door after the door, on top of it.
- `(0, 1, -0.26)` is Unity's recommendation for 2D Isometric Z-as-Y tilemaps in the XY plane, where Z means elevation. In this 3D layout, Z means depth.

## Suggested fix (game maintenance, your lane)

1. Make `IsometricCameraFollow` apply the same axis as the builder. A single shared constant is best, so the two can't drift again.
2. Update the three -0.26 test sites.
3. Add a rendered regression check:
   - Place the wizard south of closed D1 and render the gameplay camera three times: door only, wizard only, and both.
   - Where both single renders have opaque pixels, the combined image must match the wizard-only render.
   - The check fails before the fix and passes after.
4. Vincent's go as your rules require, then tell me the commit.

## Effect on contracts

- NSC-075 revision 3 (`5a2a236c3`) assumes the wizard's own code has the defect. It requires a failing-before reproduction and forbids camera-axis edits.
- Once your fix lands, I'll commit revision 4:
  - AC-007 and VAL-007 become a render-based regression the candidate must pass;
  - the failing-before requirement is dropped;
  - it names your commit.
- Please don't dispatch NSC-075 until then.
