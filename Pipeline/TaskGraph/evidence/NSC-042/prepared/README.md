# NSC-042 delivery preparation — 2026-09-14

This is an evidence handoff, **not** a delivery record. The canonical gameplay
scene still needs the combined NSC-052 and room-tile materialization before a
delivery record can truthfully name the validated commit.

- **VAL-001:** `Unity-EditMode-VAL001-eac8a9fd6332.xml` is the existing
  Unity 6000.1.8f1 EditMode result for implementation commit
  `eac8a9fd633287d249dcfe5459626ea1fb741142`: 50/50 passed. It includes
  `PaintStraightWallRun_ScalesWallLengthByRepeatingOneSharedTileWithoutGaps`
  for 3, 10, and 100 cells. This is historical evidence, not a new run on
  current main.
- **VAL-002:** `Unity-PlayMode-38a1eb012.xml` is a 1/1 passing PlayMode run
  using Unity 6000.1.8f1 on clean isolated commit
  `38a1eb01284de25af73342178ffdb573db9fd217`. That commit regenerated
  `Assets/Scenes/DoorPrototype.unity` from current room sources in a disposable
  checkout. The test loads the saved gameplay scene, checks the composed
  Ruined Entry 12-cell `WallTile` run and separate collider, then drives the
  scene's `PlayerMovement` along both sides and through the open D1 gap.
  Its wizard/wall sorting checks passed. Exact command:
  `Unity.exe -batchmode -nographics -projectPath C:\NSC\_worktrees\nsc042-unity-exact-20260914 -runTests -testPlatform PlayMode -testFilter NoSafeCircle.DoorPrototype.Tests.LongWallTraversalPlayModeTests -testResults C:\NSC\AssistantControlEvidence\NSC-042\saved-scene-traversal-20260914\final-results.xml -logFile C:\NSC\AssistantControlEvidence\NSC-042\saved-scene-traversal-20260914\final-unity.log`.
  The source tree was clean before and after this run. Earlier test attempts
  failed because the old global scene lacked the tiled wall and one chosen
  waypoint entered adjacent room collision; neither failure was counted as
  a pass.
- **VAL-003:** Vincent said "42 is complete" in the current 2026-09-14
  orchestration conversation. He also said to use NSC-042 as the example for
  properly tiled walls and that future wall tiling must follow its standard.
  This records his stated acceptance of the wall-tiling result. It does not
  claim a fresh visual inspection of isolated commit `38a1eb012` or the
  forthcoming combined scene.

The source room `Assets/Scenes/Rooms/RuinedEntry.unity` gained its tiled wall
at `cf8ad216a`, after the global gameplay scene's last materialization at
`ab0e2f371`. The isolated builder run restored `NorthFullWallTilemap` to the
global scene and changed only `Assets/Scenes/DoorPrototype.unity` as a Git
blob, but that scene commit is deliberately not included here because
NSC-052 is materializing the same global scene. Once the combined scene is
committed, rerun the focused PlayMode test on its exact clean commit. Package
the resulting XML and this human-decision citation into the final NSC-042
delivery record only if the combined test passes.
