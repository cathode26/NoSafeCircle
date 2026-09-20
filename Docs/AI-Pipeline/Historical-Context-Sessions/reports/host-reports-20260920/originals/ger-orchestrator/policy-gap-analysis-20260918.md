# Authoritative-validation-policy gap analysis — NSC-032, 040, 050, 051, 060, 067

- **Repo:** `C:\NSC\NSC\NoSafeCircle`
- **Commit analysed:** `ca9060cdabdae4142ae63ce12ff2b7294d860e43` (HEAD)
- **Method:** committed blobs only (`git show HEAD:<path>`, `git cat-file -e HEAD:<path>`, `git grep … HEAD`). The working tree was never opened. No Unity run, no edits, no commits.
- **Date:** 2026-09-18 (report name as requested; host clock reads 2026-09-17)

---

## 0. Confirmation of the premise

`Pipeline/TaskReviewAgent/authoritative_validation_policy.json` at HEAD contains entries for exactly these task ids:

NSC-007, 017, 020, 029, 042, 044, 045, 046, 047, 048, 049, 052, 053, 055, 062, 068, 069, 070, 071, 072, 073, 074, 075, 077, 078, 079, 080, 081, 082, 083, 084, 086, 087, 089, 090, 091, 092, 095, 096.

**None of NSC-032, NSC-040, NSC-050, NSC-051, NSC-060, NSC-067 appear.** The premise holds: nothing can be bound and any candidate parks unvalidated.

### Test-fixture inventory used throughout

Every committed NUnit fixture under `Assets/**/Tests/**` was enumerated by grepping *file contents* at HEAD for `class <Name>` (never filenames). The assembly split is:

- `Assets/NoSafeCircle/DoorPrototype/Tests/NoSafeCircle.DoorPrototype.Tests.asmdef` → **PlayMode**
- `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/NoSafeCircle.DoorPrototype.Tests.Editor.asmdef` → **EditMode**

So "under `Tests/Editor/`" = EditMode; everything else under `Tests/` = PlayMode. Note `Tests/Presentation/HierarchyFaderPlayModeTests.cs` is PlayMode despite the sub-folder, and `Tests/Editor/Presentation/HierarchyFaderEditModeTests.cs` is EditMode.

Only one fixture in the whole tree is declared `partial`: `NoSafeCircle.DoorPrototype.Tests.Editor.World.RoomSceneCompositionFoundationTests`, split across `Tests/Editor/World/RoomSceneComposerTests.cs` (line 21, 20 attributes) and `Tests/Editor/World/RoomSceneContractTests.cs` (line 16, 6 attributes) — 26 attributes total. Every other fixture named below is non-partial.

---

## NSC-032 — Floor Run/Restart Bootstrap (Current-Owner Stage)

### 1. Contract

- `contract_revision`: **2**
- `title`: **Floor Run/Restart Bootstrap (Current-Owner Stage)**
- `depends_on`: `["NSC-004", "NSC-005", "NSC-003", "NSC-019"]`
- `completion_gates` (verbatim):
  - **VAL-001** — reference *Floor-run restart ownership*: "Play Mode check: reducing Player Health to zero triggers a fresh floor attempt exactly once per zero-health transition."
  - **VAL-002** — reference *Floor-run restart ownership*: "Play Mode check: after restart, Player Health, Player Mana, player position, and door-open-interaction state (progress/open/blocker) are all back to their floor-initial values."

### 2. `exclusive_resources` at HEAD

| Claim | Status |
|---|---|
| `logical:floor-run-restart-orchestrator` | not a path — not checkable |
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` | **present** |
| `unity-scene:Assets/Scenes/DoorPrototype.unity` | **present** |

Missing: none. (The orchestrator implementation itself is `Assets/NoSafeCircle/DoorPrototype/Scripts/FloorRunRestartController.cs`, **present** at HEAD, though the contract does not claim it as an exclusive resource.)

### 3. Candidate fixtures (content grep for `FloorRunRestartController`, `DoorPrototypeSceneBuilder`)

Only four files at HEAD mention `FloorRunRestartController`: the builder, the controller, `Tests/Editor/DoorPrototypeSceneBuilderTests.cs`, and `Tests/FloorRunRestartPlayModeTests.cs`.

| Fixture (namespace-qualified) | File | `partial`? | Attributes | Platform |
|---|---|---|---|---|
| `NoSafeCircle.DoorPrototype.Tests.FloorRunRestartPlayModeTests` | `Tests/FloorRunRestartPlayModeTests.cs:16` | no | 4 (3 `[UnityTest]`, 1 `[Test]`) | **PlayMode** |
| `NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests` | `Tests/Editor/DoorPrototypeSceneBuilderTests.cs:18` | no | 58 attribute lines (55 `[Test]` + 3 `[TestCase]` on one method) | EditMode |

### 4. Classification — **REUSABLE**

`NoSafeCircle.DoorPrototype.Tests.FloorRunRestartPlayModeTests` genuinely validates both gates; its own comments cite NSC-032 by gate id.

- VAL-001 ("exactly once per zero-health transition") ← `PlayerDied_TriggersFreshRestart_ExactlyOncePerZeroHealthTransition` drives two independent zero-health transitions, asserts `diedCount == 1` then `== 2`, and asserts a fresh restart after each. `NonFatalDamage_DoesNotTriggerRestart` rules out polling/threshold triggering.
- VAL-002 ("Player Health, Player Mana, player position, and door-open-interaction state (progress/open/blocker) are all back to their floor-initial values") ← `PlayerDied_RestartsAllCurrentlyExistingOwners_ToFloorInitialState` asserts, after the kill: `health.CurrentHealth == MaxHealth`, `mana.CurrentMana == MaxMana`, x/z back to `initialPosition`, `!door.IsOpen`, `door.Progress == 0f`, `doorVisual.activeSelf`, `doorVisual.GetComponent<Collider>().enabled` (the blocker), plus the same for a second door and the `PlayerInteractionController` pending/locked state.

**Minimal contract revision:** none to the gate text. Add a policy entry only:

```json
"NSC-032": {
  "task_contract_sha256": "<sha256 of the committed LF blob of Tasks/NSC-032.yaml>",
  "required_test_platforms": ["PlayMode"],
  "test_filters": { "PlayMode": "NoSafeCircle.DoorPrototype.Tests.FloorRunRestartPlayModeTests" },
  "authority": "committed_task_specific_authoritative_validation_policy"
}
```

### 5. Confidence and gaps

High. Not determined: whether the fixture passes (no Unity run was permitted), and whether the contract hash must be rebound (a policy entry binds `task_contract_sha256`, so the entry must be committed in the same revision as any contract edit).

---

## NSC-040 — Visual/Simulation Separation and Continuous-Scene Integration

### 1. Contract

- `contract_revision`: **1**
- `title`: **Visual/Simulation Separation and Continuous-Scene Integration**
- `depends_on`: `["NSC-038", "NSC-039"]`
- `completion_gates` (verbatim):
  - **VAL-001** — reference *GDD - Unity Validation Agent role (Section 4)*: "Integrated Unity validation checks representative Tilemap and SpriteRenderer visuals against separately owned collision and walkability geometry and detects visual/simulation desynchronization."
  - **VAL-002** — reference *GDD - Runtime Implementation*: "Unity validation confirms the foundation extends within the canonical continuous gameplay scene and introduces no room-transition scene-loading or cross-scene state-transfer dependency."

### 2. `exclusive_resources` at HEAD

| Claim | Status |
|---|---|
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` | **present** |
| `unity-scene:Assets/Scenes/DoorPrototype.unity` | **present** |

Missing: none.

### 3. Candidate fixtures

The only type name available from `exclusive_resources` is `DoorPrototypeSceneBuilder`. Nine test files reference it by content; the ones whose content also exercises visual-vs-simulation separation or continuous-scene structure are:

| Fixture (namespace-qualified) | File | `partial`? | Attributes | Platform |
|---|---|---|---|---|
| `NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests` | `Tests/Editor/DoorPrototypeSceneBuilderTests.cs:18` | no | 58 (55 `[Test]` + 3 `[TestCase]`) | EditMode |
| `NoSafeCircle.DoorPrototype.Tests.Editor.World.FiveRoomCompositionTests` | `Tests/Editor/World/FiveRoomCompositionTests.cs:14` | no | 1 `[Test]` | EditMode |
| `NoSafeCircle.DoorPrototype.Tests.Editor.World.RoomSceneCompositionFoundationTests` | `Tests/Editor/World/RoomSceneComposerTests.cs:21` **and** `Tests/Editor/World/RoomSceneContractTests.cs:16` | **yes, `partial`** | 26 `[Test]` (20 + 6) | EditMode |
| `NoSafeCircle.DoorPrototype.Tests.Editor.NavMeshAgentConfigurationTests` | `Tests/Editor/NavMeshAgentConfigurationTests.cs:20` | no | 2 `[Test]` | EditMode |
| `NoSafeCircle.DoorPrototype.Tests.Editor.WindowsBuildSceneRegistrationTests` | `Tests/Editor/WindowsBuildSceneRegistrationTests.cs:10` | no | 4 `[Test]` | EditMode |
| `NoSafeCircle.DoorPrototype.Tests.Editor.IsometricSortingRenderTests` | `Tests/Editor/IsometricSortingRenderTests.cs:17` | no | 1 `[Test]` | EditMode |
| `NoSafeCircle.DoorPrototype.Tests.Editor.CommittedSceneCameraConformanceTests` | `Tests/Editor/CommittedSceneCameraConformanceTests.cs:11` | no | 2 `[Test]` | EditMode |
| (also, but for the other two builder classes in the same file) `…Tests.Editor.DoorPrototypeSceneBuilderClickSelectionTests` (line 2355, 1 attr) and `…Tests.Editor.DoorPrototypeSceneBuilderHoverFeedbackTests` (line 2470, 1 attr) | same file | no | 1 each | EditMode |

### 4. Classification — **REUSABLE**, with a caveat that must be read before binding

Existing coverage for VAL-001 ("representative Tilemap and SpriteRenderer visuals against separately owned collision and walkability geometry … detects visual/simulation desynchronization"):

- `DoorPrototypeSceneBuilderTests.Build_GameplayFloor_KeepsCollisionButDisablesMeshRendererBehindTilemap` — gameplay `Floor` exists independently of the visual `Tilemap`; its `MeshRenderer` stays disabled.
- `…Build_IsometricVisualLayer_HasFloorWallAndRepeatableArchitectureTilemaps` plus the private helper `AssertVisualOnly(Tilemap)` — the visual Tilemaps carry no collision.
- `…Build_FloorTilemapVisual_AlignsWithIndependentGameplayFloorInWorldSpace` and `…Build_WallTilemapVisuals_AlignWithIndependentGameplayWallsInWorldSpace` — these are the actual desynchronization detectors: visual bounds are compared against the independently-owned gameplay colliders.
- `…Build_RepresentativeWorldSprite_CanSortOnEitherSideOfRealWallTilemapGeometry` — the SpriteRenderer half of the gate.
- `NavMeshAgentConfigurationTests` asserts, in its own words, "GameplayNavigationSurface must bake from physics colliders (gameplay truth), never Tilemap renderers" — this is the *walkability* half of VAL-001, which the builder fixture does not cover.

Existing coverage for VAL-002 ("extends within the canonical continuous gameplay scene and introduces no room-transition scene-loading or cross-scene state-transfer dependency"):

- `FiveRoomCompositionTests.CanonicalScene_ContainsAllRoomsAtApprovedBounds_AndKeepsSimulationSeparate` opens the committed `Assets/Scenes/DoorPrototype.unity` and asserts exactly five rooms under one `World/ComposedRooms` root, each with **separate** `Visuals` and `GameplayGeometry` children — five spaces in one scene, visuals separate from simulation.
- `RoomSceneCompositionFoundationTests.AreRoomScenesExcludedFromBuild_CatalogRoomPaths_AreNotRegisteredInBuildSettings` and `WindowsBuildSceneRegistrationTests.CanonicalGameplayScene_IsRegisteredAndEnabledInBuildSettings` / `NonCanonicalSampleScene_IsNotRegisteredInBuildSettings` together prove no room scene is loadable at runtime — the strongest available "no room-transition scene-loading" evidence.

**Caveat (important, and the reason this task should not be bound blindly):** the visual foundation the NSC-040 contract describes — `IsometricVisualGrid` with `FloorTilemap` / `WallTilemap` / `ArchitecturalTilemap` — is still built by `DoorPrototypeSceneBuilder` (`DoorPrototypeSceneBuilder.cs:26, 88, 358`), but on the canonical-scene path it is **destroyed again** by `DoorSequenceBuilder.BuildCanonical` (`Editor/World/DoorSequenceBuilder.cs:72,76` lists `"Floor", "Walls", "IsometricVisualGrid", "D2".."D5"` and `DestroyImmediate`s them). `FiveRoomCompositionTests` asserts positively that `IsometricVisualGrid` is **absent** from the committed scene. So the `DoorPrototypeSceneBuilderTests` Tilemap assertions run only against the in-memory `BuildInMemoryForTests()` seam, where the path guard leaves the legacy grid alive. Binding VAL-001 to the builder fixture would therefore validate a legacy prototype grid that no longer ships in the canonical scene.

**Minimal contract revision (recommended):** keep the gate intent, retarget the wording at the composed-room foundation that actually exists at HEAD, then bind three EditMode fixtures:

- VAL-001 → "Editor validation confirms each composed room's `Visuals` subtree carries no collision, that its visuals align with the independently owned `GameplayGeometry` colliders, and that navigation bakes from those colliders rather than from Tilemap renderers."
- VAL-002 → "Editor validation confirms all five rooms coexist under one `World/ComposedRooms` root in `Assets/Scenes/DoorPrototype.unity` and that no room source scene is registered in build settings."

```json
"NSC-040": {
  "required_test_platforms": ["EditMode"],
  "test_filters": {
    "EditMode": "NoSafeCircle.DoorPrototype.Tests.Editor.World.FiveRoomCompositionTests|NoSafeCircle.DoorPrototype.Tests.Editor.NavMeshAgentConfigurationTests|NoSafeCircle.DoorPrototype.Tests.Editor.WindowsBuildSceneRegistrationTests"
  }
}
```

Confirm the policy loader's filter syntax supports multiple classes before writing this — every existing entry names exactly one class per platform, so a multi-class filter is **unverified** here. If only one class is allowed, `FiveRoomCompositionTests` is the single best choice and the VAL-001 walkability clause should be moved into a new test inside it.

### 5. Confidence and gaps

Medium. The fixture-to-gate mapping is solid; the *retargeting* judgement is mine and worth a second opinion. Not determined: whether the policy schema accepts a `|`-joined filter; whether NSC-038/NSC-039 (the two dependencies) are themselves delivered; whether `FiveRoomCompositionTests` — already bound to NSC-049 — may be shared (precedent exists: `WizardArtIntegrationTests` is bound to NSC-062, NSC-070 and NSC-073).

---

## NSC-050 — DoorInteractable Auto-Lock, Durability, Breaking, and Floor Reset

### 1. Contract

- `contract_revision`: **1**
- `title`: **DoorInteractable Auto-Lock, Durability, Breaking, and Floor Reset**
- `depends_on`: `["NSC-020", "NSC-004"]`
- `completion_gates` (verbatim):
  - **VAL-001** — reference *NSC-021 VAL-002; GDD §3 Door and Pursuit Rules*: "In a Play Mode test, verify that damage calls made before the door locks are rejected. Then cross an open test door, verify automatic locking and backward-player blocking, apply repeated accepted damage until the door breaks, verify further damage calls are rejected, and verify the player still cannot move backward through the broken doorway."
  - **VAL-002** — reference *NSC-021 VAL-004; GDD §3 Player Experience Success Criteria*: "In Play Mode, verify that forward-side crossing visibly closes and locks the door without a second input and that the resulting player blocker makes forward progress final."

### 2. `exclusive_resources` at HEAD

| Claim | Status |
|---|---|
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs` | **present** |
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` | **present** |
| `unity-scene:Assets/Scenes/DoorPrototype.unity` | **present** |

Missing: none.

### 3. Candidate fixtures (content grep for `DoorInteractable`)

| Fixture (namespace-qualified) | File | `partial`? | Attributes | Platform |
|---|---|---|---|---|
| `NoSafeCircle.DoorPrototype.Tests.DoorLockDurabilityPlayModeTests` | `Tests/DoorLockDurabilityPlayModeTests.cs:9` | no | 13 `[UnityTest]` | **PlayMode** |
| `NoSafeCircle.DoorPrototype.Tests.DoorInteractionPlayModeTests` | `Tests/DoorInteractionPlayModeTests.cs:10` | no | 20 `[UnityTest]` | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.DoorArrivalPhysicsPlayModeTests` | same file, line 572 | no | 3 `[UnityTest]` | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.EnemyLockedDoorAttackPlayModeTests` | `Tests/EnemyLockedDoorAttackPlayModeTests.cs:17` | no | 9 | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.DoorBreachFeedbackPlayModeTests` | `Tests/DoorBreachFeedbackPlayModeTests.cs:12` | no | 6 | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.DoorPassabilityConnectionPlayModeTests` | `Tests/DoorPassabilityConnectionPlayModeTests.cs:15` | no | 1 `[UnityTest]` | PlayMode |

### 4. Classification — **REUSABLE**

`NoSafeCircle.DoorPrototype.Tests.DoorLockDurabilityPlayModeTests` covers both gates, method-for-clause:

- VAL-001: `TakeDamage_WhileSealed_IsRejected` + `TakeDamage_WhileOpenButNotLocked_IsRejected` ("damage calls made before the door locks are rejected"); `ForwardCrossing_AutomaticallyLocksDoor_WithoutSecondInput` ("cross an open test door, verify automatic locking"); `TakeDamage_WhileLocked_ReducesDurability` → `TakeDamage_ReducingDurabilityToZero_BreaksDoor` ("repeated accepted damage until the door breaks"); `TakeDamage_AfterBroken_IsRejected` ("further damage calls are rejected"); `BrokenDoor_RemainsBroken_AndBlockerContinuesPreventingBackwardTravel` ("the player still cannot move backward through the broken doorway"). `DoorLockDurabilityFlow_MatchesFullBreachGate` runs the whole sequence end-to-end in one test — its name is an explicit reference to this gate.
- VAL-002: `ForwardCrossing_ClosesAndLocksVisibly_AndMakesForwardProgressFinal` matches the gate text nearly word for word.

Note: `DoorLockDurabilityFlow_MatchesFullBreachGate` is a **method**, not a fixture — do not put it in a `test_filters` value expecting a class. Bind the class.

Also covered but outside this task's gates: AC-006's reset method is exercised by `ResetDoor_RestoresLockBrokenAndDurabilityState`, and AC-007's serialized maximum by `MaxDurability_IsPerDoorConfigurable_AndCurrentDurabilityFollowsIt`.

**Minimal contract revision:** none. Policy entry only:

```json
"NSC-050": {
  "required_test_platforms": ["PlayMode"],
  "test_filters": { "PlayMode": "NoSafeCircle.DoorPrototype.Tests.DoorLockDurabilityPlayModeTests" }
}
```

### 5. Confidence and gaps

High — this is the cleanest of the six. Not determined: pass/fail (no Unity run).

---

## NSC-051 — DoorInteractable State Connection to Enemy Door Passability

### 1. Contract

- `contract_revision`: **2**
- `title`: **DoorInteractable State Connection to Enemy Door Passability**
- `depends_on`: `["NSC-090", "NSC-050"]`
- `completion_gates` (verbatim):
  - **VAL-001** — reference *NSC-021 AC-006; GDD §3 Door passability contract*: "Using a test-owned door and the NSC-025 navigation interface, verify that sealed, open, locked, broken, and reset-to-sealed transitions produce the required enemy-walkability result without DoorInteractable manipulating navigation internals."

  (single gate; there is no VAL-002.)

  There is also one `downstream_integration_obligation`, **INT-001**, deferring the real NSC-017 locked-door-attack-then-resume-pursuit validation. It is an obligation, not a completion gate, and must not be bound here.

### 2. `exclusive_resources` at HEAD

| Claim | Status |
|---|---|
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs` | **present** |
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` | **present** |
| `unity-scene:Assets/Scenes/DoorPrototype.unity` | **present** |
| `logical:gameplay-walkability-surface` | not a path — not checkable |

Missing: none. (The backing implementations `Scripts/World/DoorEnemyPassability.cs` and `Scripts/World/GameplayNavigationSurface.cs` are both **present**, though neither is claimed as an exclusive resource.)

### 3. Candidate fixtures (content grep for `DoorEnemyPassability` / `GameplayNavigationSurface`)

| Fixture (namespace-qualified) | File | `partial`? | Attributes | Platform |
|---|---|---|---|---|
| `NoSafeCircle.DoorPrototype.Tests.DoorPassabilityConnectionPlayModeTests` | `Tests/DoorPassabilityConnectionPlayModeTests.cs:15` | no | 1 `[UnityTest]` | **PlayMode** |
| `NoSafeCircle.DoorPrototype.Tests.DoorEnemyPassabilityPlayModeTests` | `Tests/DoorEnemyPassabilityPlayModeTests.cs:16` | no | 5 `[UnityTest]` | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.Editor.NavMeshAgentConfigurationTests` | `Tests/Editor/NavMeshAgentConfigurationTests.cs:20` | no | 2 `[Test]` | EditMode |
| `NoSafeCircle.DoorPrototype.Tests.EnemyLockedDoorAttackPlayModeTests` | `Tests/EnemyLockedDoorAttackPlayModeTests.cs:17` | no | 9 | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.EnemyPursuitDoorCrossingPlayModeTests` | `Tests/EnemyPursuitDoorCrossingPlayModeTests.cs:21` | no | 3 | PlayMode |
| (also `EnemyPursuitPlayModeTests`, `EnemyStatusEffectMovementPlayModeTests`, `RangedEnemyKeepDistanceMovementPlayModeTests`, `Editor/DoorPrototypeSceneBuilderTests` reference these types incidentally) | | | | |

### 4. Classification — **REUSABLE**

`NoSafeCircle.DoorPrototype.Tests.DoorPassabilityConnectionPlayModeTests` was written to this gate. Its single test `DoorTransitions_PublishEnemyWalkabilityThroughPassabilityOwner` walks exactly the five states VAL-001 names — `Sealed` → `Open` → `Locked` → `Broken` → `ResetDoor()` back to `Sealed` — and after each transition asserts `passability.CurrentState`, `obstacle.carving`, and an actual `NavMeshAgent.CalculatePath` result against a forward target.

The "without DoorInteractable manipulating navigation internals" clause is enforced structurally rather than by assertion: the fixture's own header states "The test never calls `SetDoorState` after binding: each navigation result must come from the door's own open, crossing, break, or reset path," and the body drives only `player.BeginInteraction()`, `door.Tick`, the private `HandleForwardCrossingTriggerEnter`, `door.TakeDamage`, `door.ResetDoor()`. That is the honest reading of the clause; it is not a direct assertion that no NavMesh API was touched.

The distinction between the two passability fixtures matters: `DoorEnemyPassabilityPlayModeTests` drives `SetDoorState` **directly** (its five tests are named `SetDoorState_Sealed_…` etc.), which is NSC-090's side of the boundary. Binding NSC-051 to it would validate the navigation owner, not the door→navigation connection this task delivers. Bind `DoorPassabilityConnectionPlayModeTests`.

**Minimal contract revision:** none. Policy entry only:

```json
"NSC-051": {
  "required_test_platforms": ["PlayMode"],
  "test_filters": { "PlayMode": "NoSafeCircle.DoorPrototype.Tests.DoorPassabilityConnectionPlayModeTests" }
}
```

### 5. Confidence and gaps

High for the mapping. Not determined: whether a one-test fixture clears whatever minimum the review agent applies; whether the gate's "NSC-025 navigation interface" wording should be updated — the contract's `depends_on` says NSC-090 while the gate text still says NSC-025, and the code it exercises is `DoorEnemyPassability` / `GameplayNavigationSurface`. That is a wording inconsistency inside the contract, not a blocker.

---

## NSC-060 — Player Resource Feedback Modernization

### 1. Contract

- `contract_revision`: **2**
- `title`: **Player Resource Feedback Modernization**
- `depends_on`: `["NSC-004", "NSC-005", "NSC-057"]`
- `completion_gates` (verbatim):
  - **VAL-001** — reference *Regression coverage*: "Existing Player Health, Player Mana, and door-damage interruption behavior remains covered and passes after the refactor."
  - **VAL-002** — reference *New event-lifecycle coverage*: "Automated coverage proves the health-changed notification updates UI after damage, restore, and reset and does not leave duplicate subscriptions after enable/disable cycles."
  - **VAL-003** — reference *New DOTween lifecycle coverage*: "Automated coverage proves repeated denied casts restart/replace the owned feedback tween safely and disabling the UI kills the tween and restores the expected normal color."
  - **VAL-004** — reference *Human Play Mode inspection*: "Developer verifies health fill, mana regeneration fill, and insufficient-mana feedback remain readable and behaviorally unchanged in Play Mode."

### 2. `exclusive_resources` at HEAD

| Claim | Status |
|---|---|
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerHealth.cs` | **present** |
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerHealthUI.cs` | **present** |
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerManaUI.cs` | **present** |

Missing: none.

**The refactor itself is already at HEAD.** `PlayerHealth.cs:13` declares `public event Action<float> HealthChanged;` alongside `Damaged` and `Died`. `PlayerHealthUI.cs` has `OnEnable`/`OnDisable` (lines 13, 18) with symmetric `HealthChanged += / -= HandleHealthChanged` (lines 31, 41) and no `Update`. `PlayerManaUI.cs` imports `DG.Tweening` (line 3), holds `private Tween deniedFlashTween` (line 18), builds a `DOTween.Sequence()` with `.OnComplete(() => deniedFlashTween = null)` (lines 124–130), and kills it on rebind/disable (105, 120). `deniedFlashTimeRemaining` no longer exists.

### 3. Candidate fixtures (content grep for `PlayerHealth`, `PlayerHealthUI`, `PlayerManaUI`)

| Fixture (namespace-qualified) | File | `partial`? | Attributes | Platform |
|---|---|---|---|---|
| `NoSafeCircle.DoorPrototype.Tests.PlayerHealthPlayModeTests` | `Tests/PlayerHealthPlayModeTests.cs:11` | no | 5 (4 `[Test]`, 1 `[UnityTest]`) | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.PlayerManaPlayModeTests` | `Tests/PlayerManaPlayModeTests.cs:11` | no | 19 (18 `[UnityTest]`, 1 `[Test]`) | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.DoorInteractionPlayModeTests` | `Tests/DoorInteractionPlayModeTests.cs:10` | no | 20 `[UnityTest]` | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests` | `Tests/Editor/DoorPrototypeSceneBuilderTests.cs:18` | no | 58 | EditMode |

Only two files in the whole tree mention `PlayerHealthUI` by content: `DoorPrototypeSceneBuilderTests.cs` (lines 175–213, wiring + no-duplicate-component on rebuild) and `PlayerHealthPlayModeTests.cs` (lines 110, 121).

### 4. Classification — **NEEDS_FIXTURE**

Three of the four gates are already covered; **VAL-002 is not**, and that is the gate this task exists for.

Already covered:
- VAL-001 ← `PlayerHealthPlayModeTests` (`Restore_HealsThroughOwnerControlledEntryPoint_AndClampsToMaximum`, `Died_EventFiresExactlyOnce_WhenHealthTransitionsToZero`, `ResetHealth_RestoresFloorInitialHealth`, `Health_DoesNotPassivelyRegenerate`), `PlayerManaPlayModeTests` (spend/regen/post-cast-delay/reset/denied-cast), and — for "door-damage interruption" — `DoorInteractionPlayModeTests.PlayerDamage_CancelsAttempt` and `…TakeDamage_DuringApproach_CancelsPendingApproach_AndStopsDestinationMovement`.
- VAL-003 ← `PlayerManaPlayModeTests.PlayerManaUI_RepeatedDeniedCast_RestartsFlashAndDisableRestoresColor` matches the gate clause for clause, supported by `PlayerManaUI_RevertsToActualFillImageColor_NotHardcodedDefault`, `PlayerManaUI_RebindDuringFlash_RestoresPreviousImage`, `PlayerManaUI_LateWiring_SubscribesWithoutDisableReenable` (which is also AC-005's evidence) and `PlayerManaUI_DeniedFeedback_RemainsVisibleWhenManaFillIsZero`.
- VAL-004 is human inspection and cannot be automated (see the NSC-067 VAL-005 note below for how to handle it).

**Not covered — what a new fixture (or new tests inside `PlayerHealthPlayModeTests`) must assert for VAL-002:**

- With a `PlayerHealthUI` bound to a `PlayerHealth` and a fill `Image`, calling `TakeDamage`, then `Restore`, then `ResetHealth` each drives the fill to the new `CurrentHealth / MaxHealth` **without any frame advancing** — proving the change arrives via the `HealthChanged` notification and not via polling.
- After N `OnDisable`/`OnEnable` cycles on the UI object, one `TakeDamage` produces exactly one handler invocation (count invocations via a spy subscriber on `PlayerHealth.HealthChanged`, or assert the `Delegate.GetInvocationList().Length` of the backing field) — the "no duplicate subscriptions" clause.
- After `OnDisable`, a `TakeDamage` leaves the fill unchanged, and the following `OnEnable` re-syncs it to the current value — proving unsubscribe actually happened and rebind is not stale.
- `PlayerHealthUI` exposes no `Update` method (reflection assertion), pinning AC-001's "no longer requires per-frame polling" the way `PlayerManaPlayModeTests.PlayerMana_PublicApiSurface_OnlyOwnsManaAndRegenDelayState` pins its own surface.

The existing `PlayerHealthUI_ContinuouslyReflectsCurrentHealthFraction` does **not** satisfy VAL-002: it damages first, then calls `ui.Bind(health, fillImage)`, then asserts `fillAmount == 0.75f` once. It never exercises restore, reset, or an enable/disable cycle, and it would still pass against a polling implementation.

**Minimal contract revision:** none to the gate text — VAL-002 is well specified and simply lacks a test. The work is: add the four assertions above to `PlayerHealthPlayModeTests` (cheapest — it already has the `PlayerHealth` fixture scaffolding), then bind:

```json
"NSC-060": {
  "required_test_platforms": ["PlayMode"],
  "test_filters": { "PlayMode": "NoSafeCircle.DoorPrototype.Tests.PlayerHealthPlayModeTests" }
}
```

If VAL-001's door-damage clause must also be bound, the same multi-class filter question raised under NSC-040 applies. Consider instead dropping VAL-001 to a note (it is a regression restatement, not new work) so a single-class filter suffices; that would be a one-line contract revision.

VAL-004 is human-only and must be marked as such in whatever field the schema provides, or the policy entry will claim automated authority it does not have.

### 5. Confidence and gaps

High that VAL-002 is uncovered — I read every one of the two files that mention `PlayerHealthUI`. Not determined: whether the review agent treats a partially-human gate set as bindable at all; whether `PlayerHealthUI` exposes a public accessor for its subscription state (I did not read the whole file — only the lines matching the lifecycle grep), which affects how the duplicate-subscription assertion is written.

---

## NSC-067 — Four-Wizard Selection Screen

### 1. Contract

- `contract_revision`: **2**
- `title`: **Four-Wizard Selection Screen**
- `depends_on`: `["NSC-062", "NSC-066"]`
- `completion_gates` (verbatim):
  - **VAL-001** — reference *Editor wizard-option validation*: "Automated Editor coverage proves all four selection entries resolve to distinct, complete NSC-062 presentation bindings and that no option is missing, duplicated, or mapped to the wrong presentation/skin combination."
  - **VAL-002** — reference *Play Mode selection validation*: "Play Mode coverage proves Start Game opens selection, gameplay input stays inactive, confirmation is unavailable without a choice, each of the four choices can be selected, and confirmation records exactly one matching selection for NSC-068."
  - **VAL-003** — reference *Selection ownership validation*: "Automated coverage confirms the selection screen does not instantiate or modify the world Player, and its confirmed-selection handoff distinguishes all four options without a default or stale prior choice."
  - **VAL-004** — reference *Builder regression validation*: "Repeated DoorPrototypeSceneBuilder.Build runs preserve one complete title-to-selection-to-gameplay path and do not duplicate selection entries, controllers, listeners, or Player objects."
  - **VAL-005** — reference *Developer visual approval*: "Vincent opens Assets/Scenes/DoorPrototype.unity in Play Mode, checks the title-to-selection flow, selects all four wizard options in separate runs, and approves readability, option identity, respectful presentation, and selected-state feedback. World placement and gameplay entry are reviewed under NSC-068."

### 2. `exclusive_resources` at HEAD

| Claim | Status |
|---|---|
| `logical:game-entry-menu-flow` | not a path — not checkable |
| `logical:wizard-presentation-selection` | not a path — not checkable |
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/WizardSelectionController.cs` | **present** |
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` | **present** |
| `repo-file:Assets/NoSafeCircle/DoorPrototype/Tests/WizardSelectionPlayModeTests.cs` | **present** |
| `unity-scene:Assets/Scenes/DoorPrototype.unity` | **present** |

Missing: none. This is the only one of the six whose `exclusive_resources` already claims its own test file. (`Scripts/WizardSelection.cs`, which carries `WizardPresentation` / `WizardSkin` / `ConfirmedWizardSelection`, is also present but unclaimed.)

### 3. Candidate fixtures (content grep for `WizardSelectionController` / `WizardSelection`)

| Fixture (namespace-qualified) | File | `partial`? | Attributes | Platform |
|---|---|---|---|---|
| `NoSafeCircle.DoorPrototype.Tests.WizardSelectionPlayModeTests` | `Tests/WizardSelectionPlayModeTests.cs:11` | no | 2 `[UnityTest]` | **PlayMode** |
| `NoSafeCircle.DoorPrototype.Tests.Editor.WizardSelectionSceneBuilderTests` | `Tests/Editor/WizardSelectionSceneBuilderTests.cs:12` | no | 2 `[Test]` | **EditMode** |
| `NoSafeCircle.DoorPrototype.Tests.WizardGameEntryPlayModeTests` | `Tests/WizardGameEntryPlayModeTests.cs:14` | no | 3 | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.Editor.WizardGameEntrySceneBuilderTests` | `Tests/Editor/WizardGameEntrySceneBuilderTests.cs:12` | no | 1 | EditMode |
| `NoSafeCircle.DoorPrototype.Tests.TitleScreenPlayModeTests` | `Tests/TitleScreenPlayModeTests.cs:12` | no | 3 across the file (2 classes) | PlayMode |
| `NoSafeCircle.DoorPrototype.Tests.WizardAnimationPlayModeTests` | `Tests/WizardAnimationPlayModeTests.cs:15` | no | 15 | PlayMode |

### 4. Classification — **REUSABLE** (VAL-001..VAL-004); VAL-005 is human-only

Both fixtures carry explicit `// NSC-067 …VAL-xxx` headers.

- VAL-001 ← `WizardSelectionSceneBuilderTests.Build_OptionsResolveToFourDistinctCompleteNsc062Presentations`: asserts `OptionCount == 4`, `option.IsComplete` for each, the exact `Presentation`/`Skin`/`Label` per index, the exact NSC-062 source sprite path per index (`…/masculine-light|masculine-dark|feminine-light|feminine-dark/selected/standing/south-east.png`), and `Distinct().Count() == 4` over the (presentation, skin) pairs — i.e. "no option missing, duplicated, or mapped to the wrong combination", clause by clause.
- VAL-002 ← `WizardSelectionPlayModeTests.StartGame_OpensSelectionWithoutDefaultAndKeepsGameplayInputInactive` (Start Game opens selection; `SelectedOptionIndex == -1`; `IsConfirmationAvailable == false`; a click on the confirm button produces no `ConfirmedSelection`; `PlayerMovement.IsGameplayEnabled` and `PlayerInteractionController.IsGameplayEnabled` both false and both debug controls disabled) plus `EachOption_ConfirmsOneMatchingHandoffWithoutChangingPlayer`, which loops all four indices in separate scene loads and asserts `handoffCount == 1` with the matching presentation/skin even after two confirm clicks and a direct `ConfirmSelection()` call.
- VAL-003 ← the same `EachOption_…` test: `AreSame(player, FindRoot(scene,"Player"))`, exactly one `Player` root, unchanged `activeSelf` / position / rotation / `Visual` sprite, and `playerWizard.Presentation/Skin` still the scene default — "does not instantiate or modify the world Player". "Without a default or stale prior choice" is covered by the fresh `LoadSceneAsync` per iteration plus the `SelectedOptionIndex == -1` assertion in the first test.
- VAL-004 ← `WizardSelectionSceneBuilderTests.Build_RunTwice_LeavesOneSelectionControllerFourOptionsAndOnePlayer`: one `Canvas`, one `Player`, one controller, one `WizardSelectionScreen` panel, and `GetPersistentEventCount() == 1` on each option button and on the confirm button — "do not duplicate selection entries, controllers, listeners, or Player objects", clause by clause.

  One honest caveat: this test drives `DoorPrototypeSceneBuilder.BuildInMemoryForTests()`, not `DoorPrototypeSceneBuilder.Build()` as VAL-004's text says. `Build()` opens and saves the canonical scene, so it is not runnable from a test. If the gate is meant to be literal about `Build`, that is a one-word contract revision (`Build` → "the scene builder's repeatable build path"); otherwise the coverage is genuine.

- VAL-005 is Vincent's own Play Mode inspection. No automated gate is honest for it.

**Minimal contract revision:** none required for VAL-001..004 (optionally the `Build` wording above). Mark VAL-005 as human-only so the entry does not overclaim, then:

```json
"NSC-067": {
  "required_test_platforms": ["EditMode", "PlayMode"],
  "test_filters": {
    "EditMode": "NoSafeCircle.DoorPrototype.Tests.Editor.WizardSelectionSceneBuilderTests",
    "PlayMode": "NoSafeCircle.DoorPrototype.Tests.WizardSelectionPlayModeTests"
  }
}
```

This is the same two-platform shape already used for NSC-049, NSC-062 and NSC-070, so it needs no schema question answered.

### 5. Confidence and gaps

High. Not determined: whether VAL-005 blocks the policy entry (the schema has no visible human-gate field — NSC-049's entry binds two automated filters and says nothing about its human gate, which suggests human gates are simply omitted); pass/fail of either fixture; whether `WizardSelectionPlayModeTests`, which loads the committed `DoorPrototype` scene five times, is stable in a batch run.

---

## Summary

| Task | Rev | Missing exclusive-resource paths | Classification | Fixture to bind | Contract revision needed? |
|---|---|---|---|---|---|
| NSC-032 | 2 | none | **REUSABLE** | `…Tests.FloorRunRestartPlayModeTests` (PlayMode) | no |
| NSC-040 | 1 | none | **REUSABLE** (retarget advised) | `…Tests.Editor.World.FiveRoomCompositionTests` (+ `NavMeshAgentConfigurationTests`, `WindowsBuildSceneRegistrationTests`) | yes — gate text still describes the deleted `IsometricVisualGrid` |
| NSC-050 | 1 | none | **REUSABLE** | `…Tests.DoorLockDurabilityPlayModeTests` (PlayMode) | no |
| NSC-051 | 2 | none | **REUSABLE** | `…Tests.DoorPassabilityConnectionPlayModeTests` (PlayMode) | no (optional NSC-025 → NSC-090 wording fix) |
| NSC-060 | 2 | none | **NEEDS_FIXTURE** | `…Tests.PlayerHealthPlayModeTests` after adding VAL-002 tests | no (gate text is fine; the test is missing) |
| NSC-067 | 2 | none | **REUSABLE** | `…Tests.Editor.WizardSelectionSceneBuilderTests` + `…Tests.WizardSelectionPlayModeTests` | no (optional `Build` wording fix) |

No task in this set is **NOT_BUILT** — every claimed `repo-file:` and `unity-scene:` path exists at HEAD. No task is wholly **HUMAN_ONLY**, though NSC-060 VAL-004 and NSC-067 VAL-005 are individually human gates inside otherwise automatable sets.

### Cross-cutting items to settle before writing any entry

1. **Does `test_filters` accept more than one class per platform?** Every one of the 39 committed entries names exactly one. NSC-040 and NSC-060 VAL-001 would benefit from several. Until this is answered, plan on one class per platform.
2. **Hash binding.** A policy entry carries `task_contract_sha256`. Per the standing rule, compute it from the committed LF blob (`git show <commit>:Tasks/NSC-0xx.yaml | sha256sum`), not the CRLF worktree file, and commit the policy entry in the same revision as any contract edit.
3. **Fixture sharing is precedented** — `WizardArtIntegrationTests` is bound by NSC-062, NSC-070 and NSC-073 — so NSC-040 reusing NSC-049's `FiveRoomCompositionTests` is not novel.
4. **Partial-class hazard.** Only `RoomSceneCompositionFoundationTests` is partial, and it is already bound (NSC-069). None of the six recommended filters names a partial class. No filter below names a method: `DoorLockDurabilityFlow_MatchesFullBreachGate` and `AreRoomScenesExcludedFromBuild_…` are **methods**, not fixtures, and appear in this report only as evidence.

### What this report could not determine

- **Nothing was executed.** No Unity run, so every "covered" claim is a reading of committed source, not a passing result. Each recommended filter should be run once before the entry is committed — a filter naming a class that compiles but selects zero tests fails silently.
- The policy schema's fields beyond the five seen in existing entries (`task_contract_sha256`, `required_test_platforms`, `test_filters`, `authority`) — in particular whether a human-only gate can be declared.
- Delivery state of the dependencies (`NSC-038`, `NSC-039` for NSC-040; `NSC-090` for NSC-051; `NSC-057` for NSC-060; `NSC-066` for NSC-067). A bound gate on a task whose dependencies are `not_delivered` still parks.
- Whether `PlayerHealthUI` exposes a subscription-state accessor (only its lifecycle lines were read).
