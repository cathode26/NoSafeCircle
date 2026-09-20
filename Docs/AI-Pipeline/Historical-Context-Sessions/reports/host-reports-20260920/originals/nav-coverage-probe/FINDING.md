# Final Room NavMesh: why two spawn assertions failed (2026-09-17)

Game Agent, during verification of `fix/melee-leash-and-spawns-20260917`.

## The failure

`EnemySpawnPlacementTests` (new in that branch) reported, after the scene was materialized at
`0f569e063`:

```
MeleeEnemy spawn (8.00, 0.00, 74.00) did not sample onto the baked NavMesh within 0.1 units.
MeleeEnemy spawn (-8.00, 0.00, 77.00) did not sample onto the baked NavMesh within 0.1 units.
```

Both are Final Room guards that the leash/spawn fix never moved, so the failure could not have
been caused by the fix.

## What was measured

Two scratch Editor probes (`NavCoverageProbe.cs`, `NavCoverageProbe2.cs`, kept in this folder,
never committed) opened the committed `Assets/Scenes/DoorPrototype.unity` in Unity 6000.1.8f1 and
dumped the real bake. Raw output: `coverage.txt`, `coverage2.txt`.

1. The scene **does** carry baked data: `GameplayNavigation` owns a live `NavMeshData`, agent type
   0, `collectObjects=All`, `useGeometry=PhysicsColliders`. The Edit Mode assertion was therefore
   testing something real, not an empty navigation system. The project tracks no NavMesh data
   asset, so the data lives in the scene the builder saved.
2. Bake bounds are x [-13.167, 13.167], z [-25.167, 85.303] - the Final Room (z 64..86) is inside
   the bake, not beyond its edge.
3. `Room_FinalRoom/GameplayGeometry/FloorCollision` (non-trigger, top face at y=0) sits directly
   under both failing spawns, exactly as `Room_LowerVault`'s does under the spawn that passes.
4. The sampled surface height is **not uniform in the Final Room**. Nearest navigable y over a
   grid, centre line to west wall at z=74: 0.083, 0.083, 0.097, 0.123, 0.135, 0.136. Every other
   room is flat at 0.083. Polygon vertices in the room are still at 0.083; the rise comes from
   voxelization around the room's raised geometry - the two benches (sampled 0.48) and the central
   obstacle (sampled 2.083).
5. At both failing spawns the nearest navigable point is **(8, 0.136, 74)** and **(-8, 0.117, 77)**:
   horizontal displacement zero. The floor is underfoot; only the vertical offset exceeded 0.1.

## Conclusion

Test premise, not a game defect and not a room defect. A 0.1 absolute 3D tolerance is smaller than
the bake's own vertical error in that room, so it rejects spawns that stand on navigable floor.

Fixed by expressing what the design requires - navigable floor *underfoot* - as a generous vertical
allowance (0.5) plus a strict horizontal one (0.05), with a new negative test proving the
horizontal half still rejects a probe standing in the Final Room's west wall. Loosening the
vertical number alone would have been an unguarded weakening of the check.

## Separate observation, for the GER Agent

The bake puts walkable polygons on top of the Final Room's central obstacle (y=2.083, 8 vertices)
and on both benches (y=0.48). They are islands with no connection to the floor, so nothing can
path onto them and gameplay is unaffected today; the surfaces are simply flat and high enough for
the agent profile to voxelize as walkable. If the room ever gains ledge or jump traversal, or if
anything samples nearest-navmesh near the room centre, these want a `NavMeshModifier` marking them
non-walkable. Raised here as a room-geometry note, not a blocker.

## What the 0.5 vertical allowance does and does not cover

Worth stating plainly, because the number should not drift upward later.

- It admits the measured voxel error (max 0.156 in the Final Room, 0.083 everywhere else) with room to
  spare, and nothing more that matters: the horizontal half still demands the sampled point be
  underfoot within 0.05.
- It does **not** by itself reject a point standing inside the Final Room's benches. They are 0.7
  tall and the bake puts walkable polygons on their tops at 0.48, directly overhead - inside the
  allowance and with zero horizontal displacement. What rejects such a point is the second half of
  the test, the 0.5-radius capsule overlap check against non-trigger gameplay colliders. Both halves
  are load-bearing; neither is redundant.
- Raising the vertical allowance past ~0.7 would start admitting points buried in that kind of prop
  with only the collider check standing in the way. 0.5 is already generous against a 0.156 worst
  case and should not grow.

## The negative test, and why the first version of it was wrong

The first attempt asserted that a probe on the Final Room's west wall centre line would be reported
by the *horizontal* half. It failed, correctly: the bake carves the wall, so that probe is rejected
by the sample radius ("found no baked NavMesh within 0.5 units") and by the collider overlap - never
reaching the horizontal comparison. No authored point in this scene sits beside a gap narrow enough
to exercise that half through the bake.

So the suite now proves both halves where each one actually lives:

- `PlacementCheck_RejectsAProbeStandingInARoomWall` - on the real scene, that a point in a wall is
  rejected by the check at all.
- `HorizontalRule_AcceptsTheMeasuredFinalRoomOffset_AndRejectsADisplacedSample` - directly on the
  rule, that a sample 0.136 above and exactly underfoot is accepted (the measured guard at
  (8, 0, 74), which the old 0.1 radius rejected) while the same offset displaced 0.4 sideways is not.
