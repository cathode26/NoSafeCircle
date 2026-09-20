# GER Orchestrator handoff: NSC-077 rev 3 (enemy art on the existing moving enemies)

From the game developer / integration steward session, 2026-09-16. Vincent assigned this contract revision to the GER Orchestrator. The implementation comes back to the game developer afterwards.

## Vincent's direction

> "So 77 needs to be changed. We have moving enemies. We need to integrate the art into the already created enemies that have no art."

## Why the current contracts no longer fit

- **`Tasks/NSC-077.yaml`** (rev 2, "Stationary Enemy Sprite Integration and Room Placement") places presentation-only stationary enemies. Its AC-004 forbids movement, navigation and attacks.
- **`Tasks/NSC-094.yaml`** (rev 1, "Enemy Eight-Direction Walk Animation Integration") animates presentation fixtures only, and depends on NSC-077.
- **Local main already has moving gameplay enemies**, built by `Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs`:
  - a melee chaser (`BuildChaseEnemy`);
  - a ranged fire caster.
  - Both are drawn as generated placeholder silhouettes: the `MeleeEnemySprite` / `FireCasterEnemySprite` assets, filled with `EnemySpriteFillColor`.
  - Runtime scripts are in `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/`: EnemyPursuitMovement, RangedEnemyKeepDistanceMovement, RangedEnemyAttack, EnemyFireballCaster, EnemyLockedDoorAttack, EnemyStatusEffectMovement, EnemyTargetKnowledge and RangedEnemyProjectile.
- **The old stationary NSC-077 branches** stay unmerged (Vincent's rule: never delete NSC branches). Their sprite import code may be reusable.
  - `codex/nsc077-stationary-enemies-20260914` has 70 files: StationaryEnemy scripts, prefabs and tests.
  - Its import code predates the facing fix below, so check its direction mapping.

## Proposal from the game developer (yours to confirm or change)

1. **Scope:** revise NSC-077 to rev 3, "Enemy Art Integration for the Existing Moving Enemies", absorbing NSC-094's walk scope. Mark NSC-094 superseded by NSC-077 if the schema allows it.
2. **Art mapping:**
   - Melee Enemy art goes on the melee chaser.
   - Ranged Enemy art (the lantern wraith caster) goes on the fire caster.
   - Include any other gameplay enemy instances found on main.
3. **Inputs:**
   - 16 NSC-063 idle PNGs: `Art/Enemies/Source/`, 128x128.
   - 96 NSC-093 six-frame walk PNGs: `Art/Enemies/Source/Walk/`, 176x176, feet normalized; see `inventory.json` and `Docs/Art/Enemies/PIXELLAB_WALK_GENERATION.md`.
   - Their metas are Unity-generated default textures, so the builder must set sprite import: Sprite, single mode, **Texture2D shape**, point filter, uncompressed, no mips, feet pivot, and a pixels-per-unit calibrated against the wizard.
   - The melee north-east idle and walk were just corrected to a single cleaver on branch `assistant/nsc063-nsc093-ne-single-cleaver-20260916` (same paths and GUIDs), which is awaiting Vincent's pick. Do not bind exact pixel hashes.
4. **Behaviour:**
   - The walk clip plays while the enemy actually moves; the idle plays when stopped.
   - Facing is the eight-way screen direction of movement, and the last facing is kept when stopped.
   - **Use the corrected NSC-075 camera mapping:** camera (30, -45, 0), screen right = X+Z, screen up = Z-X, with hysteresis. NSC-075 shipped with the vertical axis inverted until Vincent caught it in Unity (fix `7fc15c528`), so require an in-game facing check, not just tests.
   - Facing the target while attacking is a possible follow-up, not part of this scope.
5. **Boundaries:**
   - No changes to pursuit, keep-distance, navigation, attacks, projectiles, damage, health, registry or encounters.
   - Remove the placeholder silhouettes.
   - The builder generates the 32 clips (2 archetypes x 8 directions x idle/walk), the Animator controller(s), and the prefab and scene changes through `DoorPrototypeSceneBuilder.Build`, idempotently. The worker edits source and tests only.
6. **Gates:**
   - Edit Mode mapping and import audits.
   - Play Mode tests: each archetype through eight directions, idle and walk states, last facing kept.
   - The existing enemy behaviour fixtures still pass.
   - Final gate: Vincent's in-game visual check of both enemies in all eight directions.
7. **Likely `depends_on`:** NSC-063, NSC-093 and NSC-075, plus the tasks that own the enemy behaviours (verify: NSC-017, NSC-053, NSC-054 and the owner of the chaser and fire caster added by the playable-build commit `9a3d22c56`, which may have no task).

## Lessons that belong in the contract

- GUID-only stub metas import as cubemap cookies in Unity 6000.1. See NSC-075 fixes `0d28b0bf5` and `bf97d116c`.
- Scenes are binary here. Rebuild them from builders; never merge scene files.
- Unity test filters are separated by semicolons.

## Available workspace

Worktree `C:\nscrev\nsc077-rev3` on branch `assistant/nsc077-rev3-moving-enemy-art-20260916` sits at main `7fc15c528` with no changes. A drafting attempt was stopped before writing anything. Use it or ignore it.
