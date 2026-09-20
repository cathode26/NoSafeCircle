Implemented NSC-077 revision 3. Working tree is clean, branch is two commits ahead, and nothing was pushed.

## Commits

- `cc4ff88994d99b7779fba9c79c451442b65ff9d8` — runtime animation controller, enemy asset builder, scene-builder wiring, Lantern Wraith rename, teal wisp, preserved script GUID.
- `139e37795bc098fae73c388afcaa679a6bf125cf` — focused Edit Mode and Play Mode fixtures.

## Contract coverage

| ID | Implementation and test coverage | Remaining gate |
|---|---|---|
| AC-001 | [DoorPrototypeGlobalSceneBuilder.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs), `SavedSceneEnemiesUseGeneratedArtControllersAndExistingGameplaySetup` | Game Agent builds scene and runs Unity tests |
| AC-002 | [EnemyAnimationAssetBuilder.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Editor/World/EnemyAnimationAssetBuilder.cs), `ApprovedEnemySourcesHaveExactInventoryImportSettingsAndGroundPivots` | Game Agent runs builder/import audit |
| AC-003 | `EnemyPixelsPerUnit = 128`, same Edit Mode import audit | Vincent confirms size in VAL-008 |
| AC-004 | `BuildController`/`EnsureClip`, `GeneratedEnemyControllersHaveExactStateClipAndSpriteMappings` | Game Agent materializes assets |
| AC-005 | [EnemyAnimationController.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyAnimationController.cs), five `Tick_*` direction/speed tests | Game Agent runs Play Mode |
| AC-006 | `EnemyAnimationController.ResolveFacingTarget`, `EnemyLanternWispCaster.FacingTarget`, stopped-melee/wraith tests | Game Agent runs Play Mode |
| AC-007 | [EnemyLanternWispCaster.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyLanternWispCaster.cs), `EnemyLanternWispCasterPlayModeTests` | Game Agent runs tests; Vincent reviews wisp |
| AC-008 | Global builder attaches south idle sprites, Animators and controllers; Edit/Play saved-scene tests | Double-build and saved-scene materialization pending |
| VAL-001 | `ApprovedEnemySourcesHaveExactInventoryImportSettingsAndGroundPivots` | Game Agent |
| VAL-002 | `GeneratedEnemyControllersHaveExactStateClipAndSpriteMappings` | Game Agent |
| VAL-003 | `SavedSceneEnemiesUseGeneratedArtControllersAndExistingGameplaySetup` | Game Agent |
| VAL-004 | [EnemyAnimationPlayModeTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/EnemyAnimationPlayModeTests.cs), component-facing tests | Game Agent |
| VAL-005 | [EnemyLanternWispCasterPlayModeTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/EnemyLanternWispCasterPlayModeTests.cs) | Game Agent |
| VAL-006 | `SavedSceneEnemiesUseProductionAnimationAndLanternWisp` | Game Agent |
| VAL-007 | Builder twice, compile, focused and regression fixtures | Game Agent |
| VAL-008 | In-game eight-direction, pivot, sorting, size and wisp review | Vincent |

## Builder commands

Menu:

`No Safe Circle → Build Door Prototype Scene`

Batchmode, run twice from the clone root:

```text
Unity.exe -batchmode -quit -projectPath . -executeMethod NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build -logFile -
Unity.exe -batchmode -quit -projectPath . -executeMethod NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build -logFile -
```

Expected first-run output:

- `Art/Enemies/Generated.meta`
- `MeleeEnemyAnimator.controller` and `LanternWraithAnimator.controller`, with metas
- 32 clips and metas: `{MeleeEnemy|LanternWraith}_{idle|walk}_{eight directions}.anim`
- Import-setting changes to exactly 112 enemy `.png.meta` files
- `LanternWraithSprite.asset` and meta
- Removal of `FireCasterEnemySprite.asset` and meta
- Updated `Assets/Scenes/DoorPrototype.unity`

The second run must introduce no further file-content changes.

## Unity test filters

Edit Mode:

```text
NoSafeCircle.DoorPrototype.Tests.Editor.EnemyArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.Editor.WizardArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests
```

Play Mode:

```text
NoSafeCircle.DoorPrototype.Tests.EnemyAnimationPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyLanternWispCasterPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyPursuitPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyPursuitDoorCrossingPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyTargetKnowledgePlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyHealthPlayModeTests;NoSafeCircle.DoorPrototype.Tests.ActiveEnemyRegistryPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyLockedDoorAttackPlayModeTests;NoSafeCircle.DoorPrototype.Tests.DoorEnemyPassabilityPlayModeTests;NoSafeCircle.DoorPrototype.Tests.WizardAnimationPlayModeTests
```

## Unverified and intentionally not done

- Unity was unavailable, so nothing was compiled, materialized, or executed in Unity.
- No generated/serialized Unity asset or scene was hand-edited.
- Source PNGs, inventory and art documentation were untouched.
- `EnemyLanternWispCaster.cs.meta` retains GUID `73b9fddab19c3f34e878119acd894458`.
- Python confirmed 16 idle PNGs, 96 walk PNGs, correct dimensions, 96 unique inventory entries, and ground line 132.
- `taskcontrol validate` passed.
- No contract conflict was found. The 128 PPU value remains the contract’s temporary choice pending Vincent’s visual decision.
- No push was performed.