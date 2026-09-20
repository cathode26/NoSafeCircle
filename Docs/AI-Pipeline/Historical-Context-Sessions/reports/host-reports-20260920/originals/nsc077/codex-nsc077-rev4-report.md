codex
Implemented NSC-077 revision 4. The branch is clean and was not pushed.

1. Commits

- `76d9b656331076aba1df29aad622b94f044819cf` — applies 64 PPU, uniform enemy Visual transforms, fixed camera rotation, and runtime rotation restoration.
- `a19eb8fa9a5384060933d5cf57cc5828fcde03ba` — adds revision-4 Edit Mode and Play Mode assertions.

2. Revision-4 changes

- Change 1: [EnemyAnimationAssetBuilder.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Editor/World/EnemyAnimationAssetBuilder.cs:16) now uses the single `EnemyPixelsPerUnit = 64f` constant. Point filtering and disabled mipmaps remain explicit. [EnemyArtIntegrationTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/Editor/EnemyArtIntegrationTests.cs:64) asserts 64 once and audits all 112 importers against the shared constant.
- Change 2: [DoorPrototypeGlobalSceneBuilder.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs:417) passes `Vector2.one` and the isometric rotation to both enemy Visuals. [EnemyAnimationController.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyAnimationController.cs:17) restores world rotation during runtime. Repository inspection found no Lantern Wraith root-rotation behavior; melee roots can rotate through `NavMeshAgent`.
- Change 3: [EnemyArtIntegrationTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/Editor/EnemyArtIntegrationTests.cs:407) checks uniform scale one, camera-facing world rotation within `0.01°`, sorting, and editor/runtime rotation agreement.
- Change 4: [EnemyAnimationPlayModeTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/EnemyAnimationPlayModeTests.cs:194) moves and rotates both enemy root types, calls `Tick`, and verifies the Visual returns to the camera rotation.
- Change 5: no wisp art, sprite, effect, or gameplay change. The teal orb stand-in and its existing tests remain unchanged.
- Change 6: no code added for VAL-008; it remains Vincent’s in-game size/lean review.

3. Runtime rotation

`EnemyAnimationController.LateUpdate` calls `Tick` after the NavMeshAgent engine update has applied movement and root rotation. `Tick` then assigns the Visual’s world rotation, so parent rotation cannot lean or turn the sprite edge-on.

`EnemyAnimationController.IsometricCameraEulerAngles` is the runtime source of truth. The editor builder’s `IsometricCameraEulerAngles` property forwards to it, and the Edit Mode test guards their agreement.

4. Builder and expected output

Exact Unity menu command: `No Safe Circle/Build Door Prototype Scene`  
Exact batch entry point: `NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build`

Revision-4-specific materialized differences are:

- 112 existing `.png.meta` files imported at 64 PPU, Point filtering, and no mipmaps.
- `Assets/Scenes/DoorPrototype.unity` enemy Visuals serialized with local scale `(1,1,1)` and camera-facing rotation.

Because neither earlier pass ran Unity, the first materialization also creates the 32 `.anim` clips, two Animator controllers and their metas, creates `LanternWraithSprite.asset`, and removes `FireCasterEnemySprite.asset`. A second identical build must produce no changes.

5. Unity test filters

Edit Mode:  
`NoSafeCircle.DoorPrototype.Tests.Editor.EnemyArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.Editor.WizardArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests`

Play Mode:  
`NoSafeCircle.DoorPrototype.Tests.EnemyAnimationPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyLanternWispCasterPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyPursuitPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyPursuitDoorCrossingPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyTargetKnowledgePlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyHealthPlayModeTests;NoSafeCircle.DoorPrototype.Tests.ActiveEnemyRegistryPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyLockedDoorAttackPlayModeTests;NoSafeCircle.DoorPrototype.Tests.DoorEnemyPassabilityPlayModeTests;NoSafeCircle.DoorPrototype.Tests.WizardAnimationPlayModeTests`

6. Validation boundary

- `taskcontrol.py validate`: PASS.
- `git diff --check`: PASS.
- HEAD: `a19eb8fa9a5384060933d5cf57cc5828fcde03ba`; tree: `0a9f0e669a39b354e35ac72235d3843aa5a07a68`.
- Unity was unavailable, so the builder, compilation, Unity tests, XML results, and VAL-008 were not run.
- No out-of-bounds test asserts the old enemy Visual scale or rotation.
- No instruction/contract conflict was found. VAL-008 still says “open pixel-density decision” despite revision 4 selecting decision B; I treated that stale wording as a human-review note with no implementation effect.
- No generated/serialized Unity file, source art, gameplay setting, or out-of-scope file was edited.
