"""Replace the leash item's NEXT block in the Game Agent state file with current facts."""
import io

path = r'C:\NSC\agent-state\game-agent.md'
data = io.open(path, 'r', encoding='utf-8', newline='').read()

old = """   - The job report is `C:\\nscrev\\claude-jobs\\melee-leash-spawns-20260917\\report.md`. It was built by Docker Claude (Sonnet) and is NOT yet reviewed or Unity-verified.
   - NEXT:
     1. an independent Docker Claude review (Opus; Codex is out);
     2. Unity in branch-verify: Build twice, then Edit Mode plus the new fixture, then Play Mode;
     3. Vincent's go and in-game check.
"""

new = """   - The job report is `C:\\nscrev\\claude-jobs\\melee-leash-spawns-20260917\\report.md` (Docker Claude, Sonnet).
   - REVIEWED (FIX FIRST, both findings handled) and being Unity-verified in `C:\\nscrev\\branch-verify`, which is
     DETACHED at the authoritative tip. The branch ref in `cj-melee-leash-spawns` is STALE at `13c16bf2d`.
   - History at the tip: `3e2dbe781` leash removed and spawns moved (Bone Archive melee (-6,10) to (-3,10),
     Chapel wraith (-9,27) to (-9,31), Lower Vault melee (-7,53) to (-2,53)); `85fc8b449` tests;
     `13c16bf2d` review minor (Enemies root name by reflection - a direct reference to the internal const
     does not compile from the test assembly); `0f569e063` the materialized scene, which the review
     correctly required because the leash and the old spawns were baked into the committed scene.
   - Unity so far: Build exit 0, 0 compile errors. Edit Mode 59 total / 58 passed / 1 failed, and that one
     failure was diagnosed to the test's own premise, not the fix:
     `EnemySpawnPlacementTests` rejected the two Final Room guards (8,0,74) and (-8,0,77), spawns this fix
     never touched. Two scratch Unity probes proved `Room_FinalRoom/GameplayGeometry/FloorCollision` sits
     directly under both, nearest navigable point (8,0.136,74) and (-8,0.117,77) - zero horizontal
     displacement, vertical offset only. The bake's sampled surface rises from 0.083 on that room's centre
     line to 0.156 beside its benches while every other room is flat at 0.083, so the 0.1 absolute radius
     was smaller than the bake's own vertical error. Evidence: `C:\\nscrev\\reports\\nav-coverage-probe\\FINDING.md`.
   - Fix applied on top: placement is now validated as navigable floor underfoot (0.5 vertical allowance,
     0.05 horizontal), plus a NEW negative test proving the horizontal half still rejects a probe standing
     in the Final Room's west wall. Commit message ready at
     `C:\\nscrev\\reports\\nav-coverage-probe\\commit-message.txt`.
   - NEXT:
     1. Edit Mode rerun (EnemySpawnPlacementTests;DoorPrototypeSceneBuilderTests;NavMeshAgentConfigurationTests);
     2. Play Mode `EnemyPursuitPlayModeTests` (runner: `run_playmode.ps1` in that folder);
     3. commit the test fix, point the branch ref at the new tip, restore the whitespace churn;
     4. Vincent's go and in-game check. NOTE: the release-pause exception does NOT cover merges.
   - For the GER Agent when this lands: the bake puts unreachable walkable islands on top of the Final Room's
     central obstacle (y=2.083) and both benches (y=0.48). No gameplay effect today; wants a NavMeshModifier
     if the room ever gains ledge traversal.
"""

if data.count(old) != 1:
    print('ABORT: anchor found %d times' % data.count(old))
    raise SystemExit(1)

io.open(path, 'w', encoding='utf-8', newline='').write(data.replace(old, new))
print('state file updated')
