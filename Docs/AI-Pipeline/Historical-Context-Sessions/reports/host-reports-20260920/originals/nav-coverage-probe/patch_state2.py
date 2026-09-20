"""Mark the leash fix verified in the Game Agent state file."""
import io

path = r'C:\NSC\agent-state\game-agent.md'
data = io.open(path, 'r', encoding='utf-8', newline='').read()

old = """   - NEXT:
     1. Edit Mode rerun (EnemySpawnPlacementTests;DoorPrototypeSceneBuilderTests;NavMeshAgentConfigurationTests);
     2. Play Mode `EnemyPursuitPlayModeTests` (runner: `run_playmode.ps1` in that folder);
     3. commit the test fix, point the branch ref at the new tip, restore the whitespace churn;
     4. Vincent's go and in-game check. NOTE: the release-pause exception does NOT cover merges.
"""

new = """   - **VERIFIED AND READY FOR VINCENT'S GO (2026-09-17).** Authoritative tip:
     `fix/melee-leash-and-spawns-20260917` @ **`68cd3aeee`** in `C:\\nscrev\\branch-verify`, tree clean,
     churn restored. The stale ref in `cj-melee-leash-spawns` (`13c16bf2d`) must NOT be used.
     - Build: exit 0, 0 compile errors.
     - Edit Mode 63/63 (EnemySpawnPlacementTests, DoorPrototypeSceneBuilderTests, NavMeshAgentConfigurationTests).
     - Play Mode 8/8 (EnemyPursuitPlayModeTests), including
       `SavedSceneMeleeEnemy_PursuesRetreatingWizardWithoutTheOldDemoLeash` - the committed scene,
       not just the code, no longer carries the leash.
     - Results: `editmode-results.xml`, `playmode-results.xml` in `C:\\nscrev\\reports\\nav-coverage-probe\\`.
   - **Identity leak found and fixed here.** `f8d13155b` and `618cb6af1` carried
     `Vincent.J.Liguori@outlook.com` as committer despite this clone's `.invalid` config - the leak
     travelled with the commits from an earlier rebase elsewhere. The chain was replayed with
     plumbing (trees, messages, author identities and both dates preserved), `git diff` old vs new
     tip empty, and the pre-rewrite tip archived at
     `refs/archive/fix-melee-leash-and-spawns-20260917-pre-identity-rewrite`. Every author and
     committer on the branch is now `.invalid`.
   - Audited the rest of the queue for the same leak: `nsc095-wizard-128-art` clean,
     `art-rejects/NSC-095` clean, `fix/retired-auditor-test-debt` clean, `fix/worker-final-write`
     clean (its clone's `main` is stale at `95492e43d`, so the dirty commits in `main..HEAD` are the
     known already-merged 11, verified with `merge-base --is-ancestor` against canonical).
   - NEXT: Vincent's go, then merge and his in-game check. The release-pause exception does NOT
     cover merges.
"""

if data.count(old) != 1:
    print('ABORT: anchor found %d times' % data.count(old))
    raise SystemExit(1)

io.open(path, 'w', encoding='utf-8', newline='').write(data.replace(old, new))
print('state file updated')
