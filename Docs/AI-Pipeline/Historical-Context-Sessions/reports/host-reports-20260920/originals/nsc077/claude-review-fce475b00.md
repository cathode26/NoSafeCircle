# NSC-077 candidate fce475b00: adversarial review (Claude)

VERDICT: FIX_FIRST

- **Candidate:** `codex/nsc077-moving-enemy-art-20260917` at `fce475b00` (base `d3bcd4a85`), in the `C:\nscrev\nsc077-codex` clone.
- **Contract:** `Tasks/NSC-077.yaml`, revision 5.
- **Read only.** Nothing was edited, run in Unity, committed or pushed.

## How each claim was checked

- **By reading:** the full diff; all 4 new and renamed C# files, the builder diff, and the 3 test files; the pattern code (`WizardAnimationController`, `ImportWizardSprite`, `CreateWorldSpriteVisual`); the asmdefs; the room scene YAML; the source PNGs, measured with PIL.
- **From the separate Unity run:**
  - The Game Agent materialized the candidate as `3233ac923` in `C:\nscrev\branch-verify`.
  - The 8 code files there have the same git blob IDs as `fce475b00`, checked with `git rev-parse`.
  - I read that commit's generated `.meta`, `.controller` and `.anim` files. I also read `C:\nscrev\reports\nsc077\unity\builder-run1.log` and `failures-phaseC.md`.
  - I only read this evidence. I did not run anything.
- **Suspected** means a runtime outcome I inferred but did not run.

## Findings (ranked)

### BLOCKER 1: the VAL-006 production-path test fails, and the obvious fix will expose a second failure

**Where:** `Assets/NoSafeCircle/DoorPrototype/Tests/EnemyAnimationPlayModeTests.cs`
- lines 312-313: picks the first `MeleeEnemy`
- lines 317-319: disables the player's CharacterController and moves the player
- lines 327-336: waits for movement, then asserts

**Problem (a): error log.** Verified by the Phase C run (`failures-phaseC.md`).
- `playerController.enabled = false` stays off across frames.
- `PlayerMovement.Update` then runs `Tick`, `ApplyGrounding` and `CharacterController.Move` every frame (`PlayerMovement.cs:298`).
- Unity logs `[Error] CharacterController.Move called on inactive controller`, and the Unity Test Framework fails the test on that unhandled error.

**Problem (b): the chosen enemy stands inside a shelf.** Suspected. I verified the geometry by reading; I did not run the outcome.
- `First(MeleeEnemy)` is the Bone Archive enemy spawned at (-6, 0, 10).
- That point is inside `Shelf ACollision` in `Assets/Scenes/Rooms/BoneArchive.unity`: a BoxCollider covering X[-6.5, -5], Y[0, 2.5], Z[4, 16].
- The NavMeshAgent (radius 0.5) should map to the nearest NavMesh edge. That is the west side at about X -7, 1.0 away; the east edge is 1.5 away.
- The builder makes EnemyTargetKnowledge require line of sight (`SetRequiresLineOfSight(true)`). Its ray starts at Y+1.
- The wizard is placed 2 units east, at X -4 or -5. Shelf A sits between the two.

**Failure scenario:**
- Fixing (a) alone makes the test reach line 335 after 120 frames with `HasTarget == false`.
- If the agent cannot map to the NavMesh at all, the enemy never moves and the test fails at line 336.
- Secondary: the 120-frame wait scales with frame rate. Batchmode runs uncapped.

**Fix direction:**
1. Teleport the player in one frame: disable, set position, enable, `Physics.SyncTransforms()`, as `LongWallTraversalPlayModeTests.cs:64-66` does.
2. Select the Chapel of Ash enemy at (7, 0, 31) by position, with the wizard at (9, 0, 31). My collider scan found that ray clear, and no LanternWraith is within 14 units of that spot.
3. Wait for `agent.isOnNavMesh`.
4. Bound the wait by elapsed time, not frame count.

### MAJOR 2: the queued rev 5 builder fix breaks the VAL-003 reflection helper, and the equality check is too loose

**Where:** `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/EnemyArtIntegrationTests.cs:412-419` and `:429-439`. Verified by reading.

**Problem:**
- `EditorCameraEulerAngles()` calls `builderType.GetProperty("IsometricCameraEulerAngles", Static|NonPublic)`.
- The queued fix turns the builder member back into an independent `internal static readonly Vector3` field. `GetProperty` then returns null, and `Assert.IsNotNull(property)` fails for every enemy.
- Reflection is required here: `DoorPrototypeGlobalSceneBuilder` is `internal` and there is no InternalsVisibleTo.
- The "runtime constant equals builder field" check uses `Quaternion.Angle(...) < 0.0001f`. Unity's `Quaternion.Angle` returns 0 whenever the quaternion dot product is above 1 - 1e-6, which is about 0.16°. A drift such as (30, -45.1, 0) would pass.

**Fix direction:**
- Use `GetField(..., BindingFlags.Static | BindingFlags.NonPublic)`.
- Assert that the builder field equals `new Vector3(30f, -45f, 0f)` and equals `EnemyAnimationController.IsometricCameraEulerAngles`, component by component, with exact values or within 1e-5.

### MINOR 3: VAL-006 and AC-006 facing assertions cannot fail

**Where:** `EnemyAnimationPlayModeTests.cs:319` and `:342-354`. Verified by reading.

**Problem:**
- The wizard is placed along the enemy's own movement direction (+X, south-east).
- After stopping, "idle facing the wizard" and "kept the last walking facing" are both south-east, so the test cannot tell them apart.
- No test has a walking enemy whose target is in a different sector. "A walking enemy always faces its movement, never its target" (AC-006) is unproven.

**Failure scenario:** a controller that faces the target while walking, or ignores the target once stopped in the production scene, passes VAL-006.

**Fix direction:**
- After stopping, move the wizard into another sector (for example +Z, north-east) and call SyncTransforms before the Tick.
- Add a VAL-004 case: a MeleeEnemy with HasTarget, target to the north, moving +X, expects `walk_south-east`.

### MINOR 4: the VAL-004 wraith out-of-range facing check is tautological

**Where:** `EnemyAnimationPlayModeTests.cs:277-281`. Verified by reading.

**Problem:** the out-of-range wizard at (20, 0, 0) is in the same south-east sector as the in-range wizard at (3, 0, 0). LastDirection stays south-east even if the controller ignored range. Only `caster.FacingTarget == null` is really proven.

**Fix direction:** put the out-of-range wizard at (0, 0, 20), which is north-east, and assert south-east is kept.

### MINOR 5: VAL-005 does not pin two numbers it claims to prove

**Where:** `EnemyLanternWispCasterPlayModeTests.cs`. Verified by reading.

**Lifetime (lines 142-143):**
- `Assert.IsTrue(wisp != null)` runs right after `caster.Tick(3.74f)`, in the same frame.
- `Destroy` is deferred to the end of the frame, so this assertion cannot fail. A 3-second lifetime passes.
- Fix: `yield return null` before asserting the wisp still exists.

**Hit radius (lines 152-161):**
- The wisp lands exactly on the wizard (distance 0), so any hit radius passes.
- Fix: after `Tick(0)` then `Tick(0.25f)`, the wisp is at x = 3. Put the wizard at x 3.79 (expect 5 damage) and at x 3.81 (expect no damage).

### MINOR 6: VAL-004 "facing equals WizardAnimationController.LastDirection" covers only one enemy type

**Where:** `EnemyAnimationPlayModeTests.cs:162-189`. It only creates `EnemyAnimationKind.MeleeEnemy`.

**Problem:** VAL-004 says "for both enemy types".

**Fix direction:** loop over both kinds.

### MINOR 7: a missing walk frame stops the build with an error that does not name the file (AC-002)

**Where:** `Assets/NoSafeCircle/DoorPrototype/Editor/World/EnemyAnimationAssetBuilder.cs:191`, and the same pattern at `:105`, `:162`, `:260` and `:312`. Verified by reading.

**Problem:**
- These lines throw `new FileNotFoundException(message, path)`.
- Unity logs `Type: Exception.Message` (StackTraceUtility). For this constructor, `Message` excludes the file name.
- A missing `enemy_*_walk_NN.png` logs only "FileNotFoundException: Missing enemy source PNG".
- A missing idle still does name the file, because `File.ReadAllBytes` in `FindIdleGroundLineFromBottom` throws first.

**Fix direction:** put the path in the message text.

### MINOR 8: the runtime animation code allocates every frame (ENGINEERING_STANDARDS sections 6 and 10.1; WebGL is a target)

**Where:** `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyAnimationController.cs:153` and `:131`.

**Problem:**
- Line 153 builds `animationKind + "_" + motion + "_" + lastDirection` in every LateUpdate for every enemy. That is an enum `ToString` plus a string concat.
- Line 131 calls `transform.Find("Visual")` every frame when there is no Visual.

**Fix direction:** precompute the 2x8 state names (or `Animator.StringToHash` values) per kind in `Initialize`/`Awake`, compare indices, and remember a missing Visual instead of searching again.

### MINOR 9 (latent; matters for INT-001 reuse): cached state goes stale after a disable and re-enable

**Where:** `EnemyAnimationController.cs:150-161`.

**Problem:**
- `keepAnimatorStateOnDisable` defaults to false, so a re-enabled Animator restarts at its default state (south idle).
- `currentState` is never cleared, so `ApplyState` skips `Play` when the recomputed state equals the cached one.
- A stopped enemy that faced north shows south idle after re-activation.
- The current scene never deactivates enemies. `Scripts/EncounterAdmissionController.cs:148` does re-activate pending enemies, and INT-001 says prefab tasks reuse this component.

**Fix direction:** in `OnEnable`, set `currentState = null` and `previousPosition = transform.position`.

### MINOR 10: under rev 6 (local main `3eb886805`), VAL-003 does not prove there are no missing scripts

**Where:** `EnemyArtIntegrationTests.cs:257-259`.

**Problem:**
- Rev 6 AC-007 states that VAL-003 proves the rebuilt scene has no missing scripts.
- The test filters null components out (`component != null`), so a missing script would still pass.

**Fix direction:** assert `GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(go) == 0` for each enemy and its Visual.

## Checklist items 1 to 9

1. **PASS.**
   - `EnemyArtIntegrationTests.cs:225-239` checks presence only: `GetComponents<T>().Length == 1` for EnemyTargetKnowledge, EnemyPursuitMovement and EnemyHealth, and a non-null NavMeshAgent (its count is not checked).
   - NavMeshAgent settings match the builder at `d3bcd4a85`: speed 2.2, acceleration 12, angular speed 720, stopping distance 0.6, autoBraking, and agent type, radius and height from settings index 0.
   - There is no exact component-set assertion.
   - The LanternWraith asserts it has no NavMeshAgent.
2. **PASS in code; NEEDS-VINCENT in game.**
   - `EnemyAnimationController.cs:166-167` and `:200-201` use (X+Z, Z-X), identical to `WizardAnimationController.cs:124-125` and `:158-159`.
   - I checked all 8 AC-005 world directions against the code.
   - The Phase C run passed VAL-004. The in-game check is VAL-008.
3. **PASS.**
   - `EnemyAnimationAssetBuilder.cs:315-329` sets every AC-002 importer setting and resets `m_ApplyGammaDecoding` and `m_CookieLightType`.
   - `3233ac923` changes exactly 112 `.png.meta` files under Source and nothing else there.
   - A sampled idle `.meta` has 64 pixels per unit, Point filter, mipmaps off, Texture2D shape and cookieLightType 0. Its pivot y is 0.1484375, which is 19/128 for the melee south idle and matches PIL. A sampled walk `.meta` has pivot y 0.25.
   - The Phase C run passed EnemyArtIntegrationTests.
4. **PASS.** The diff touches 13 files, all within `exclusive_resources`. There are no DoorPrototypeSceneBuilder.cs, WizardAnimationController.cs, `.asmdef` or ProjectSettings changes.
5. **PASS.**
   - The `.meta` is an R100 rename with GUID `73b9fddab19c3f34e878119acd894458` at both base and head.
   - Serialized fields and defaults are identical: 60 mana, 10 per cast, 1 s interval, 14 range, speed 8, hit radius 0.8, lifetime 4, damage 5.
   - The cast, range and sight logic is unchanged; `FacingTarget` wraps the same two private checks.
   - Changes that don't affect gameplay numbers: the projectile is named LanternWisp and is teal with emission; its collider is disabled immediately before `Destroy`; the owned material instance is destroyed.
   - No stale references remain in code, tests or docs.
6. **NEEDS-GER/VINCENT.** The chain of contract checks:
   - The rev 4 check said "revise", which led to rev 5.
   - The rev 5 check said "revise", which led to rev 6, committed on local main as `3eb886805` after this candidate's base.
   - The rev 6 check (`C:\nscrev\codex-jobs\codex-contract-check-NSC-077-rev6-20260917.report.md`) also says "revise":
     - Blocking: a stale `authoritative_validation_policy.json` binding for NSC-077.
     - Major: restore the same-GUID requirement.
   - The candidate keeps the GUID, so it already meets that proposed fix. Rev 6's only code-relevant change is MINOR 10.
   - I did not find the rev 3 retro-check verdict.
7. **PASS in code; NEEDS-VINCENT for VAL-008.**
   - Both Visuals are created through `CreateWorldSpriteVisual` with `Vector2.one` and `Quaternion.Euler(30, -45, 0)` (`DoorPrototypeGlobalSceneBuilder.cs:418-424` and `:469-475`), at local position zero, which keeps ground contact.
   - LateUpdate restores the world rotation (`EnemyAnimationController.cs:67-72` and `:129-136`). NavMeshAgent writes its rotation in PreLateUpdate, before LateUpdate.
   - NavMeshAgent settings are untouched.
   - VAL-003 checks scale one, rotation and sorting.
   - VAL-004 rotates the root and then Ticks.
   - No wisp art was added.
8. **PASS.** No 128 pixels-per-unit value, (1, 2) size or identity Visual rotation remains in code or tests. The only remaining 128 constants are the idle source size.
9. **KNOWN (fix queued), plus MAJOR 2.** The queued fix must also switch `EditorCameraEulerAngles()` to `GetField` and compare exactly.

## Notes (not findings)

- **Compile:** the same code blobs compiled in `C:\nscrev\branch-verify`. `builder-run1.log` shows the Tests and Tests.Editor assemblies built and exit code 0; there were no enemy-related warnings.
- **Phase C results:**
  - Edit Mode: all EnemyArtIntegrationTests passed.
  - Play Mode: 103 of 104 passed; VAL-006 was the only failure.
- **The two failing DoorPrototypeSceneBuilderTests** (camera framing, and the player's grounded height with x = -10) look pre-existing.
  - The diff does not touch BuildPlayer, BuildCamera or PlayerSpawnPosition.
  - `IsometricCameraEulerAngles` keeps its value.
  - The main `32c6223d3` run will confirm.
- **Enemy generated assets did not churn in the Phase C Edit Mode run.** Only wizard clips needed recovery. So the temp-folder test path that calls `EnemyAnimationAssetBuilder.Build()` is byte-stable for enemies.
- **Pre-existing spawn/collider overlaps.** These are out of scope: spawns come from `9a3d22c56`, and NSC-077 forbids moving them. Route them to the GER Agent or the room owner. VAL-008 will show them.
  - Bone Archive MeleeEnemy at (-6, 0, 10) is inside Shelf A.
  - Chapel of Ash LanternWraith at (-9, 0, 27) is inside `Column1Collision`, X[-9.25, -7.75] Z[26.25, 27.75].
  - Lower Vault MeleeEnemy at (-7, 0, 53) sits on the edge of `LV-W1Collision`.
  - For VAL-008, Vincent should lure the Chapel of Ash or Final Room enemies.
- **Generated clips look right.** Walk clips have `m_StopTime` 0.5 (the last frame is held for 1/12 s), bind only `Visual`/`m_Sprite`, and loop. Controllers have 16 states with the default state `*_idle_south`.
