# Room builders: rework cost of option (b), camera-plane isometric Tilemap visuals

Game Agent, 2026-09-17. Answers item 5 in `C:\nscrev\reports\ger-orchestrator\vincent-decisions-20260917.md`. Based on a code survey of local main.

## What exists today
- **Ruined Entry:** RuinedEntrySceneBuilder builds five world-plane visual Tilemaps under one Grid (cell size 1 x 0.5 x 1):
  - floor at Euler(-90, 0, 0);
  - north and west full walls, south and east low walls, at identity or Euler(0, 90, 0).
- **Architectural tile generation and placement:** DoorPrototypeSceneBuilder (about 30 Tilemap references) and RoomSceneComposer, including the NSC-042 wall and floor tiles.
- **The other four rooms** (Bone Archive, Chapel of Ash, Lower Vault, Final Room) build 3D block geometry, with no Tilemaps at all. Under (b) each needs new visual work, not a conversion.
- **Collision and NavMesh** come from separate colliders and NavMeshModifier (one per room builder). Under (b) they can stay as they are, invisible.
- **Tests:** about 140 Tilemap assertions would need rewriting: DoorPrototypeSceneBuilderTests 102, RuinedEntrySceneTests 20, and LongWallTraversal, TitleScreen and NavMeshAgentConfiguration tests.

## Cost of (b)
Large: about three task contracts, several crew runs, and a Unity verification and in-game review each.
1. A camera-plane isometric visual Grid and its mapping from world cells to iso cells (floor, wall height offsets). Sorting rules against world-space sprites (wizard, enemies, doors, props) and wall occlusion. Ruined Entry converted first.
2. The other four rooms get iso floor and wall visuals over their existing block collision.
3. Test migration, plus the NSC-042 generator and tile-visual checks moved to the new layer.

**Main risk: sorting and occlusion.** It's the same area as the door-in-front-of-wizard bug Vincent just saw. The checkerboard floor defect probably belongs to the same work.

## Cost of (a)
Close to zero builder work: new textures on today's planes. The soft look under the angled camera stays.

## Recommendation
Do the Art Director's small trial first, in a throwaway scene rather than the builders.
- Build one floor patch and one wall run as camera-plane iso tiles, next to the wizard and a Dungeon Brute.
- Judge two things: crispness, and sorting (a character in front of and behind the wall, and beside a door).

If (b) is clearly better and sorting is solvable, stage the rework in the order above. Otherwise take (a).
