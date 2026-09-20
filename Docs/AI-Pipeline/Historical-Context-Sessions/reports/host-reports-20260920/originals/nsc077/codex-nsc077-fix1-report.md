codex
Implemented and committed one fix round. Working tree is clean; nothing was pushed.

### Commits

- `9a50113e8856d3b54cf5a132ae90c21900b1e74e` — independent camera constant, allocation-free animation states, re-enable reset, exact asset-error paths.
- `7f2d4ef18a8a4c75a93b4585251f2070e5c5ddde` — revision-7 Edit/Play Mode validation fixes.

### Findings 1–11

1. Fixed camera constant and tests in [DoorPrototypeGlobalSceneBuilder.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs:88), [EnemyArtIntegrationTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/Editor/EnemyArtIntegrationTests.cs:115), and [EnemyAnimationPlayModeTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/EnemyAnimationPlayModeTests.cs:232). Reflection uses `GetField`; vectors are compared component-by-component; Play Mode uses literal Euler angles.
2. Fixed VAL-006 in [EnemyAnimationPlayModeTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/EnemyAnimationPlayModeTests.cs:376). The CharacterController is re-enabled in the teleport frame, and NavMesh, acquisition, movement, sight, and casting use five-second condition deadlines.
3. Fixed. The stopped wizard moves two units west of the melee enemy, with an assertion that idle target-facing differs from walking facing. A separate test proves movement facing wins over a target in another sector.
4. Fixed. The out-of-range wraith target is now world `+Z`, a different sector from the in-range `+X` target.
5. Fixed in [EnemyLanternWispCasterPlayModeTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/EnemyLanternWispCasterPlayModeTests.cs:94): 8 units/second, alive at 3.99 seconds and destroyed after 4.01, hit at 0.79 and miss at 0.81, five damage, six ten-mana casts from 60 mana, one-second cadence, and no seventh cast.
6. Fixed. Wizard-facing parity now runs for both `MeleeEnemy` and `LanternWraith`.
7. Fixed in [EnemyAnimationAssetBuilder.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Editor/World/EnemyAnimationAssetBuilder.cs): missing, invalid, wrong-size, inventory, importer, and idle/walk source failures name the exact file.
8. Fixed in [EnemyAnimationController.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyAnimationController.cs): state names and hashes are precomputed, `Animator.Play` uses hashes, and a missing `Visual` lookup is not repeated every frame.
9. Fixed. `OnEnable` resets position and cached state; a focused Play Mode test covers deactivate/reactivate for both enemy types.
10. Fixed in [EnemyArtIntegrationTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/Editor/EnemyArtIntegrationTests.cs:211). Every GameObject in the saved scene is checked with `GameObjectUtility.GetMonoBehavioursWithMissingScriptCount`.
11. Fixed/verified. `EnemyLanternWispCaster.cs.meta` retains GUID `73b9fddab19c3f34e878119acd894458`. No legacy `.cs` or `.meta` exists. No legacy caster reference remains in code, tests, `Docs`, or text Unity assets. Only authoritative task contracts NSC-007, NSC-009, and NSC-077 retain historical/rename references.

### VAL-006 placement evidence

- Melee: `(7,0,31)`; wizard: `(9,0,31)`. Chapel east pews end at Z `29.5` and restart at `32`, leaving a 2.5-unit corridor at Z `31`; columns are at Z `27` and `35`. The configured agent radius is `0.5`. See [ChapelOfAshLayout.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/ChapelOfAshLayout.cs:22) and [NavMeshAreas.asset](/workspace/ProjectSettings/NavMeshAreas.asset:73).
- Wraith: `(7,0,13)`; wizard: `(9,0,13)`. Bone Archive Shelf C ends at X `5`, while the room extends to X `10`, leaving this sight line clear. See [BoneArchiveLayout.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/BoneArchiveLayout.cs:14).
- Confirmed the rejected Bone melee is inside Shelf A, and the rejected Chapel wraith is inside Column1.

### Validation and remaining work

`python3 -B Pipeline/TaskGraph/taskcontrol.py validate` passed, both commits pass `git diff --check`, and the tree is clean. Revision 6’s 64-PPU decision was already implemented; revision 7’s remaining changes concern GUID preservation and exact-candidate validation procedure.

Unity was unavailable, so nothing was compiled or run here. The Game Agent should run the builder twice, the authoritative revision-7 Edit/Play Mode filters, verify scene semantic stability and no missing scripts, and watch the new Chapel NavMesh/Bone sight-line timeout messages. VAL-008 still requires Vincent’s visual approval.
