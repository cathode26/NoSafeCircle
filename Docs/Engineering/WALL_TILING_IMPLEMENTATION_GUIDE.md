# Wall Tiling Implementation Guide

**Authority:** Vincent requires this standard for every future wall task. It
records the reusable NSC-042 implementation convention on canonical `main`; it
does not make a task complete or replace that task's contract, tests, visual
review, or conformance record.

## Required wall convention

1. Build a straight visual wall as contiguous, independently sortable Tilemap
   cells. Reuse one shared wall `Tile` asset across the run. Do not substitute
   one long renderer or create one unique tile/sprite asset per cell.
2. Make the wall texture horizontally periodic. Its visible block/mortar repeat
   period must divide the texture width exactly, so the last pixel column joins
   the first without a truncated block, seam, or pattern restart.
3. Keep the visual Tilemap separate from collision, walkability, door behavior,
   and navigation. Wall art does not create or redefine gameplay geometry.
4. Keep wall cells in the existing isometric sorting convention: use individual
   Tilemap rendering in the established world-sprite sorting layer/order band.
   Do not solve continuity by bypassing positional sorting with a fixed
   foreground order.
5. Put repeated-run placement in one reusable helper. A longer wall increases
   the helper's cell count; it does not duplicate the loop or expand the asset
   set.

## Required proof for a wall task

Add focused Editor tests that prove all of the following for the task's wall
asset and builder:

- the texture repeat period divides its width;
- representative 3-, 10-, and 100-cell runs have no missing cells;
- every cell in a run references the same wall Tile asset;
- rebuilding replaces stale persisted pixel content when the authored wall
  convention changes; and
- the visual wall remains separate from the task's gameplay collision.

Capture a normal gameplay-camera review for the task's actual wall placement.
The tests above prove the asset and builder convention; they do not prove that
the wall looks correct in every room or establish task delivery.

## NSC-042 source and limits

The reference implementation is
`Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`:
`PaintStraightWallRun` paints one shared Tile along the existing `x = -y`
diagonal, and `CreateWallPixels` uses a 32-pixel block width in a 64-pixel-wide
texture. The materialized
`Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/WallTile.asset`
is a 64×160, bottom-pivoted visual Tile with no Tile collider. The focused
tests are in
`Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs`.
The reusable requirements come from `Tasks/NSC-042.yaml` and the approved
architecture in `Docs/GDD/No_Safe_Circle_GDD.md`: repeatable visual tiles and
their sorting must remain independent of collision, doors, walkability, and
navigation.

This standard covers straight repeatable wall runs only. It does not prescribe
corner, junction, end-cap, doorway, room-dressing, collision, navigation, or
final-art rules. A task needing any of those must state and validate its own
requirements without weakening the five rules above.

The implementation entered canonical `main` in `bd041fc3f3b2aa85b7d27329ef0032090e20eb70`
and its materialized Unity assets in
`eac8a9fd633287d249dcfe5459626ea1fb741142`.
