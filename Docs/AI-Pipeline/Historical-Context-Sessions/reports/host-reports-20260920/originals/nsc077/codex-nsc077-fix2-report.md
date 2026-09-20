codex
1. Commit `79a22f35003583ce4b3f3d684ea6973a7ddb40d7` updates only `EnemyArtIntegrationTests.cs`.

2. Added assertions that:

   - Reflect `EnemySpawnPositions` and `LanternWraithSpawnPositions` using `BindingFlags.NonPublic | BindingFlags.Static`.
   - Verify both fields are `Vector3[]`, non-null, and non-empty.
   - Require matching MeleeEnemy and LanternWraith counts, no extra children, and no `FireCasterEnemy`.
   - Verify each enemy matches a distinct array position within `0.001` on X and Z.

3. Unity was unavailable, so compilation and Edit Mode execution were not verified. Static review and `git diff --check` completed; the working tree is clean.
