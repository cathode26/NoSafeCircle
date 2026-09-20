# NSC-077 candidate — Phase C Unity test failures

Checkout: C:\nscrev\branch-verify @ 3233ac923d2b77a7edd5765e64c7d5f9b43c87ac

## EditMode

Filter: `NoSafeCircle.DoorPrototype.Tests.Editor.EnemyArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.Editor.WizardArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests`
XML: `C:\Users\VincentLiguori\AppData\Local\Temp\NoSafeCircle-UnityTests-3d781a99ca11468ab03552e62aebde16\test-results.xml`
Total 64, passed 62, failed 2, skipped 0.

### NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests.Build_MainCamera_FramesPlayerAndStartingDoorInView

Message:
```
Starting door must be comfortably inside the camera view at scene start, was viewport (1.56, 0.66, 24.64).
  Expected: True
  But was:  False
```

Stack trace:
```
at NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests.Build_MainCamera_FramesPlayerAndStartingDoorInView () [0x000cd] in C:\nscrev\branch-verify\Assets\NoSafeCircle\DoorPrototype\Tests\Editor\DoorPrototypeSceneBuilderTests.cs:573
```

Top stack frame in our code: `Assets\NoSafeCircle\DoorPrototype\Tests\Editor\DoorPrototypeSceneBuilderTests.cs:573`

### NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests.Build_PlayerStartsAtCharacterControllerGroundedHeight

Message:
```
Expected: 0.0f +/- 9.99999975E-05f
  But was:  -10.0f
```

Stack trace:
```
at NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests.Build_PlayerStartsAtCharacterControllerGroundedHeight () [0x0009a] in C:\nscrev\branch-verify\Assets\NoSafeCircle\DoorPrototype\Tests\Editor\DoorPrototypeSceneBuilderTests.cs:617
```

Top stack frame in our code: `Assets\NoSafeCircle\DoorPrototype\Tests\Editor\DoorPrototypeSceneBuilderTests.cs:617`

## PlayMode

Filter: `NoSafeCircle.DoorPrototype.Tests.EnemyAnimationPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyLanternWispCasterPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyPursuitPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyPursuitDoorCrossingPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyTargetKnowledgePlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyHealthPlayModeTests;NoSafeCircle.DoorPrototype.Tests.ActiveEnemyRegistryPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyLockedDoorAttackPlayModeTests;NoSafeCircle.DoorPrototype.Tests.DoorEnemyPassabilityPlayModeTests;NoSafeCircle.DoorPrototype.Tests.WizardAnimationPlayModeTests`
XML: `C:\Users\VincentLiguori\AppData\Local\Temp\NoSafeCircle-UnityTests-686aa18849ee4ffaa15c3912ed92b2f5\test-results.xml`
Total 104, passed 103, failed 1, skipped 0.

### NoSafeCircle.DoorPrototype.Tests.EnemyAnimationPlayModeTests.SavedSceneEnemiesUseProductionAnimationAndLanternWisp

Message:
```
Unhandled log message: '[Error] CharacterController.Move called on inactive controller'. Use UnityEngine.TestTools.LogAssert.Expect
```

Stack trace:
```
UnityEngine.CharacterController:Move (UnityEngine.Vector3)
NoSafeCircle.DoorPrototype.PlayerMovement:ApplyGrounding (single) (at Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs:298)
NoSafeCircle.DoorPrototype.PlayerMovement:Tick (single) (at Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs:107)
NoSafeCircle.DoorPrototype.PlayerMovement:Update () (at Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs:96)
```

Top stack frame in our code: `Assets\NoSafeCircle\DoorPrototype\Scripts\PlayerMovement.cs:298`
