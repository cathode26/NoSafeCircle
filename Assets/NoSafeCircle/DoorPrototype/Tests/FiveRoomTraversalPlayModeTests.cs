using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using NoSafeCircle.DoorPrototype;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-110 (Tasks/NSC-110.yaml, contract_revision 1, parent NSC-018): the missing Play Mode
    // proof that the player can traverse the composed five-room floor - Ruined Entry, Bone
    // Archive, Chapel of Ash, Lower Vault, Final Room - through D1-D5, IN THE RUNTIME-BUILT
    // WORLD. Vincent deleted every committed room scene 2026-09-27 (fe4c95ad, "we have a new way
    // to work. The scene was a bottleneck"); Assets/Scenes/ now holds only RuntimeWorld.unity (a
    // light, a camera, one object) and SampleScene. The whole floor is built AT PLAY by eight
    // spawners under Resources/Spawners/, driven by GameManagers.prefab -> GameBootstrap. This
    // fixture spawns that real world (mirrors PropSightOcclusionPlayModeTests' own
    // SceneManager.LoadSceneAsync("RuntimeWorld", ...) + GameBootstrap.HasBuilt wait) rather than
    // opening any composed scene, because none exists to open any more.
    //
    // AC-002: MOVEMENT IS DRIVEN ONLY THROUGH PlayerMovement's PRODUCTION PUBLIC SURFACE -
    // RequestDestination, HasActiveDestination, DestinationReached, CancelRequestedDestination,
    // IsMovementRestricted - the same NavMesh.CalculatePath + CharacterController.Move path
    // MoveToCursor itself drives through SetDestination. WASD is bound in the input asset but read
    // by nothing (PlayerMovement.cs's own header), so a WASD-driven fixture would fail for a
    // reason that has nothing to do with traversal - exactly the 2026-09-23 confusion AC-002
    // exists to prevent. movement.enabled is set false below so this fixture's own explicit
    // Tick(dt) calls are the only clock advancing movement (the same technique
    // FiveRoomDoorSequencePlayModeTests.ComposedScene_DoorFeedback...  already uses), instead of
    // depending on real per-frame Time.deltaTime in a batched test run.
    //
    // OPENING EACH DOOR: via DoorInteractable.StartInteraction()/Tick(Duration + 0.1f) directly -
    // the same production API FiveRoomDoorSequencePlayModeTests.ComposedScene_BrokenDoor_...
    // already uses to set up door state before its own NavMesh check. AC-002 constrains PLAYER
    // MOVEMENT only; the click-to-select-and-approach UX that normally triggers StartInteraction()
    // is NSC-049 VAL-006/VAL-007's own coverage, not this task's (see NSC-110's own execution_reason
    // and AC-003: "this task adds the missing proof ... does not fix what it finds"). Opening the
    // door directly keeps this fixture's evidence about the thing NSC-110 exists to prove -
    // CharacterController/NavMesh movement across five rooms - rather than re-testing door
    // selection that already has coverage elsewhere.
    //
    // WHY A DOOR NEEDS SEVERAL FRAMES TO SETTLE AFTER OPENING: DoorEnemyPassability owns a
    // NavMeshObstacle that CARVES a hole across the doorway while sealed/locked and stops carving
    // once open/broken (DoorEnemyPassability.SetDoorState); the runtime carve toggle needs Unity
    // frames to propagate into the baked NavMesh's runtime data before NavMesh.CalculatePath/
    // SamplePosition see the opening open up, mirroring the 10-frame + Physics.SyncTransforms()
    // wait FiveRoomDoorSequencePlayModeTests.ComposedScene_BrokenDoor_NavMeshPathReconnectsAcrossDoorway
    // already measured necessary for exactly this transition.
    //
    // "REACHING A ROOM IS ASSERTED FROM THE PLAYER'S OWN RESULTING WORLD POSITION AGAINST THAT
    // ROOM'S COMMITTED RoomBounds, NOT FROM A DOOR EVENT ALONE" (AC-001): every room-bounds check
    // below reads the relevant *Layout.cs's own RoomBounds directly rather than restating a
    // literal, and reads it against a GROUND-PROJECTED player position (world Y forced to the
    // bounds' own center.y, which every *Layout.cs's RoomBounds sets to exactly 0) rather than the
    // player's raw transform.position.y, because every *Layout.cs RoomBounds has a ZERO-HEIGHT Y
    // EXTENT and Bounds.Contains would otherwise go false on ordinary CharacterController grounding
    // jitter that a real room-reached check must not be sensitive to.
    //
    // DoorInteractable.HasCrossedForward is read as CORROBORATION alongside the position check for
    // D1-D4 (never as a substitute for it, per AC-001's own text), and is the PRIMARY signal only
    // for D5, whose forward side is not one of this task's five rooms (D5 sits at
    // FinalRoomLayout.MaximumZ, the room's own far wall, not a sixth room) - there the position
    // check is instead against the same live forward-crossing-trigger geometry DoorInteractable
    // itself places (read by reflection, never a hardcoded literal), so "through D1, D2, D3, D4 and
    // D5 in order" (AC-001) is satisfied for every one of the five doors, not just the first four.
    public sealed class FiveRoomTraversalPlayModeTests
    {
        private const float TickDeltaTime = 0.05f;
        private const int DoorSettleFrames = 10;

        // Multiplies the geometrically-expected tick count (leg distance / measured moveSpeed /
        // TickDeltaTime) so that a REAL stall (a blocked route, a doorway NavMesh never opened)
        // is what exhausts a leg's budget, not this project's own authored obstacles (shelves,
        // pews, columns - see BoneArchiveLayout/ChapelOfAshLayout/LowerVaultLayout's own obstacle
        // bounds) forcing a longer, curved NavMesh corner path than the straight-line distance.
        private const float TickBudgetSafetyFactor = 6f;
        private const int TickBudgetFloor = 200;

        // One unit past the far face of a door's own forward-crossing trigger: enough for the
        // CharacterController capsule (radius 0.5, matching the baked NavMesh agent radius quoted
        // in this task's brief) to have fully cleared the trigger volume, without steering deep
        // into whatever lies beyond the NEXT doorway.
        private const float PastCrossingMargin = 1f;

        // The new world does not exist until GameBootstrap runs: the wait is not optional. Copied
        // from FiveRoomDoorSequencePlayModeTests/PropSightOcclusionPlayModeTests (not shared -
        // those files are other in-flight work on this branch and are not in this task's
        // allowed_files) rather than invented fresh.
        private static IEnumerator WaitForWorldBuilt()
        {
            yield return null;
            GameObject managers = GameObject.Find("GameManagers");
            Assert.IsNotNull(managers,
                "RuntimeWorld.unity carries no GameManagers object, so nothing builds the world.");
            var bootstrap = managers.GetComponent<GameBootstrap>();
            Assert.IsNotNull(bootstrap, "GameManagers carries no GameBootstrap.");

            yield return null;
            yield return null;

            Assert.IsTrue(bootstrap.HasBuilt,
                "GameBootstrap had not built after three frames, so every assertion below would "
                + "fail on an empty world rather than on the thing under test. SpawnedCount="
                + bootstrap.SpawnedCount + ".");
        }

        // NOT root-scoped: RuntimeWorld nests every spawned object under its spawner
        // (GameManagers -> <Family>Spawner -> the object), never at the scene root. Copied from
        // FiveRoomDoorSequencePlayModeTests for the same not-shared reason above.
        private static GameObject FindInScene(Scene scene, string name)
        {
            var matches = new List<GameObject>();
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                CollectByName(root.transform, name, matches);
            }
            Assert.AreEqual(1, matches.Count,
                $"Expected exactly one '{name}' object in loaded scene {scene.path}, found {matches.Count}.");
            return matches[0];
        }

        private static void CollectByName(Transform node, string name, List<GameObject> matches)
        {
            if (node.name == name) matches.Add(node.gameObject);
            for (int i = 0; i < node.childCount; i++)
            {
                CollectByName(node.GetChild(i), name, matches);
            }
        }

        // Walks the composed world from its title screen into gameplay exactly as a player does
        // (copied from FiveRoomDoorSequencePlayModeTests for the same not-shared reason above):
        // StartGame raises WizardSelectionRequested, WizardSelectionController shows its panel,
        // SelectOption/ConfirmSelection hand a confirmed selection to WizardGameEntryController,
        // which calls EnableGameplayInput() on PlayerMovement. TitleScreenController.Awake had
        // already called SuspendGameplayInput() on it, and PlayerMovement.RequestDestination is a
        // silent no-op while IsGameplayEnabled is false - so skipping this would fail every leg
        // below for a reason that has nothing to do with traversal.
        private static IEnumerator EnterGameplayThroughRunEntry()
        {
            var title = Object.FindFirstObjectByType<TitleScreenController>();
            if (title == null) yield break;

            title.StartGame();
            yield return null;

            var selection = Object.FindFirstObjectByType<WizardSelectionController>();
            if (selection != null && selection.IsSelectionVisible)
            {
                selection.SelectOption(0);
                selection.ConfirmSelection();
            }

            yield return null;
        }

        // Ground level (the bounds' own center.y, which every *Layout.cs RoomBounds sets to
        // exactly 0), not the player's raw transform.position.y - see the class header.
        private static Vector3 GroundPoint(Vector3 worldPosition, Bounds roomBounds) =>
            new Vector3(worldPosition.x, roomBounds.center.y, worldPosition.z);

        // Diagnostic only (never the assertion itself, per AC-001's "not from a door event alone"
        // and the sibling requirement that room-reaching be position-based): a real
        // PathPartial/PathInvalid result is worth reporting on failure, exactly as this project's
        // own VAL-007 fixture (ComposedScene_BrokenDoor_NavMeshPathReconnectsAcrossDoorway)
        // already does with its own test-owned NavMeshAgent.
        private static string DiagnoseNavMesh(Vector3 from, Vector3 to)
        {
            bool startSampled = NavMesh.SamplePosition(from, out var startHit, 1.5f, NavMesh.AllAreas);
            bool endSampled = NavMesh.SamplePosition(to, out var endHit, 1.5f, NavMesh.AllAreas);
            var path = new NavMeshPath();
            bool calculated = startSampled && endSampled
                && NavMesh.CalculatePath(startHit.position, endHit.position, NavMesh.AllAreas, path);

            return $"NavMesh diagnostic {from} -> {to}: startSampled={startSampled}"
                + (startSampled ? $" ({startHit.position})" : "")
                + $", endSampled={endSampled}" + (endSampled ? $" ({endHit.position})" : "")
                + $", calculated={calculated}"
                + (calculated ? $", status={path.status}, corners={path.corners.Length}" : "") + ".";
        }

        // Reads DoorInteractable's own private forwardCrossingOffset/forwardCrossingTriggerSize
        // fields (the exact geometry DoorInteractable.Awake() uses to build its
        // "ForwardCrossingTrigger" child collider) rather than restating a literal, so the
        // position check below is derived from the SAME production geometry that decides
        // HasCrossedForward, never an independently guessed number.
        private static float ForwardCrossingFarFaceZ(DoorInteractable door)
        {
            var offsetField = typeof(DoorInteractable).GetField("forwardCrossingOffset",
                BindingFlags.NonPublic | BindingFlags.Instance);
            var sizeField = typeof(DoorInteractable).GetField("forwardCrossingTriggerSize",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(offsetField, "Expected DoorInteractable to still declare forwardCrossingOffset.");
            Assert.IsNotNull(sizeField, "Expected DoorInteractable to still declare forwardCrossingTriggerSize.");

            var offset = (Vector3)offsetField.GetValue(door);
            var size = (Vector3)sizeField.GetValue(door);
            return door.transform.position.z + offset.z + size.z * 0.5f;
        }

        private static float ForwardCrossingMargin(DoorInteractable door)
        {
            return (ForwardCrossingFarFaceZ(door) - door.transform.position.z) + PastCrossingMargin;
        }

        // AC-002: PlayerMovement.moveSpeed, read once by reflection so this leg's tick budget is
        // derived from the same value driving TickDestinationMovement, never a hardcoded guess.
        private static float ReadMoveSpeed(PlayerMovement movement)
        {
            var field = typeof(PlayerMovement).GetField("moveSpeed",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, "Expected PlayerMovement to still declare moveSpeed.");
            return (float)field.GetValue(movement);
        }

        // Opens the given door via its own production timer (see the class header for why this,
        // not a click, is in scope here), waits for DoorEnemyPassability's carve toggle to
        // propagate, then drives the wizard toward target through PlayerMovement's public
        // RequestDestination/Tick/HasActiveDestination/DestinationReached surface until arrival, a
        // real BlockedDestinationTimeout give-up, or this leg's own tick budget running out -
        // whichever happens first, every outcome reported rather than any of them silently retried
        // or hidden (AC-003: this task records the answer, it does not engineer one).
        private static IEnumerator DriveDoorAndLeg(
            PlayerMovement movement, DoorInteractable door, Vector3 startPosition, Vector3 target,
            float moveSpeed, StringBuilder log)
        {
            Assert.IsFalse(door.IsOpen,
                $"{door.DoorId}: test setup expected this door still sealed before opening it for "
                + "this leg.");

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            Assert.IsTrue(door.IsOpen,
                $"{door.DoorId}: test setup must actually open the door before attempting to walk "
                + "the player through it.");

            for (var frame = 0; frame < DoorSettleFrames; frame++) yield return null;
            Physics.SyncTransforms();

            log.AppendLine($"[NSC-110] {door.DoorId} opened at {door.transform.position}. "
                + DiagnoseNavMesh(startPosition, target));

            var reached = false;
            void OnReached() => reached = true;
            movement.DestinationReached += OnReached;

            movement.RequestDestination(target);

            var distance = Vector3.Distance(startPosition, target);
            var expectedTicks = Mathf.CeilToInt(distance / moveSpeed / TickDeltaTime);
            var maxTicks = Mathf.Max(TickBudgetFloor, Mathf.CeilToInt(expectedTicks * TickBudgetSafetyFactor));

            var ticks = 0;
            while (movement.HasActiveDestination && ticks < maxTicks)
            {
                movement.Tick(TickDeltaTime);
                ticks++;
                yield return null;
            }

            movement.DestinationReached -= OnReached;

            var finalPosition = movement.transform.position;
            log.AppendLine($"[NSC-110] {door.DoorId} leg: distance={distance:F2}, "
                + $"budget={maxTicks} ticks, used={ticks} ticks, reached={reached}, "
                + $"finalPosition={finalPosition}, HasActiveDestination={movement.HasActiveDestination}, "
                + $"HasCrossedForward={door.HasCrossedForward}.");

            if (movement.HasActiveDestination)
            {
                Assert.Fail(
                    $"{door.DoorId}: the player still had an active destination toward {target} "
                    + $"after this leg's full {maxTicks}-tick budget (distance {distance:F2}, "
                    + $"moveSpeed {moveSpeed}) - it did not settle either way. Final position "
                    + $"{finalPosition}. " + DiagnoseNavMesh(finalPosition, target));
            }

            Assert.IsTrue(reached,
                $"{door.DoorId}: PlayerMovement gave up on destination {target} without "
                + "DestinationReached ever firing - a real BlockedDestinationTimeout give-up "
                + "(a blocked-side-collision route), or the destination could not be resolved onto "
                + $"the baked NavMesh at all. Final position {finalPosition}. "
                + DiagnoseNavMesh(finalPosition, target));
        }

        [UnityTest]
        public IEnumerator PlayerTraversesRuinedEntryThroughFinalRoom_ViaProductionMovementAndDoors()
        {
            yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName("RuntimeWorld");

            yield return EnterGameplayThroughRunEntry();

            var player = FindInScene(scene, "Player");
            var movement = player.GetComponent<PlayerMovement>();
            Assert.IsNotNull(movement, "Expected the spawned Player to carry a PlayerMovement component.");
            Assert.IsTrue(movement.IsGameplayEnabled,
                "Expected gameplay input to be enabled after entering the run through the title "
                + "screen; RequestDestination is a silent no-op while IsGameplayEnabled is false.");

            // AC-002: from here on, this fixture's own Tick(dt) calls are the only clock advancing
            // movement - see the class header.
            movement.enabled = false;

            var doors = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<DoorInteractable>(true))
                .OrderBy(d => d.DoorId)
                .ToArray();
            Assert.AreEqual(5, doors.Length,
                $"Expected exactly five doors (D1-D5) in the built world, found {doors.Length}.");
            for (var i = 0; i < doors.Length; i++)
            {
                Assert.AreEqual((DoorId)i, doors[i].DoorId,
                    $"Doors must be ordered D1..D5; index {i} was {doors[i].DoorId}.");
                Assert.IsFalse(doors[i].IsOpen,
                    $"{doors[i].DoorId} must start sealed - this task's traversal proof is "
                    + "meaningless if the doors do not need opening to pass.");
            }

            var moveSpeed = ReadMoveSpeed(movement);
            Assert.Greater(moveSpeed, 0f,
                "PlayerMovement.moveSpeed must be positive or no distance/tick budget below means "
                + "anything.");

            var log = new StringBuilder();

            // NSC-049 AC-003: the player's own spawn point (RuinedEntryLayout.PlayerStart, via
            // PlayerSpawner.Spawn()) - read live from the spawned object, never restated as a
            // literal here.
            var startPosition = player.transform.position;
            log.AppendLine($"[NSC-110] Player spawned at {startPosition}.");

            // AC-001, room 1 of 5 (Ruined Entry): the spawn point itself must already fall within
            // its own room's committed bounds.
            Assert.IsTrue(
                RuinedEntryLayout.RoomBounds.Contains(GroundPoint(startPosition, RuinedEntryLayout.RoomBounds)),
                $"AC-001: the player's spawn position {startPosition} must fall within Ruined "
                + $"Entry's own RoomBounds {RuinedEntryLayout.RoomBounds} - this is the first of "
                + "the five rooms and the traversal proof starts from it.");

            // --- D1: Ruined Entry -> Bone Archive ---
            var d1Target = doors[0].transform.position + new Vector3(0f, 0f, ForwardCrossingMargin(doors[0]));
            yield return DriveDoorAndLeg(movement, doors[0], startPosition, d1Target, moveSpeed, log);
            var positionAfterD1 = player.transform.position;
            // AC-001, room 2 of 5 (Bone Archive): position-based, not from HasCrossedForward alone.
            Assert.IsTrue(
                BoneArchiveLayout.RoomBounds.Contains(GroundPoint(positionAfterD1, BoneArchiveLayout.RoomBounds)),
                $"AC-001: after crossing D1 the player's position {positionAfterD1} must fall "
                + $"within Bone Archive's RoomBounds {BoneArchiveLayout.RoomBounds}.\n{log}");
            Assert.IsTrue(doors[0].HasCrossedForward,
                "D1: HasCrossedForward must be true (corroborating, not substituting for, the "
                + "position check above) once the player has physically crossed it.");

            // --- D2: Bone Archive -> Chapel of Ash ---
            var d2Target = doors[1].transform.position + new Vector3(0f, 0f, ForwardCrossingMargin(doors[1]));
            yield return DriveDoorAndLeg(movement, doors[1], positionAfterD1, d2Target, moveSpeed, log);
            var positionAfterD2 = player.transform.position;
            // AC-001, room 3 of 5 (Chapel of Ash).
            Assert.IsTrue(
                ChapelOfAshLayout.RoomBounds.Contains(GroundPoint(positionAfterD2, ChapelOfAshLayout.RoomBounds)),
                $"AC-001: after crossing D2 the player's position {positionAfterD2} must fall "
                + $"within Chapel of Ash's RoomBounds {ChapelOfAshLayout.RoomBounds}.\n{log}");
            Assert.IsTrue(doors[1].HasCrossedForward,
                "D2: HasCrossedForward must be true once the player has physically crossed it.");

            // --- D3: Chapel of Ash -> Lower Vault ---
            var d3Target = doors[2].transform.position + new Vector3(0f, 0f, ForwardCrossingMargin(doors[2]));
            yield return DriveDoorAndLeg(movement, doors[2], positionAfterD2, d3Target, moveSpeed, log);
            var positionAfterD3 = player.transform.position;
            // AC-001, room 4 of 5 (Lower Vault).
            Assert.IsTrue(
                LowerVaultLayout.RoomBounds.Contains(GroundPoint(positionAfterD3, LowerVaultLayout.RoomBounds)),
                $"AC-001: after crossing D3 the player's position {positionAfterD3} must fall "
                + $"within Lower Vault's RoomBounds {LowerVaultLayout.RoomBounds}.\n{log}");
            Assert.IsTrue(doors[2].HasCrossedForward,
                "D3: HasCrossedForward must be true once the player has physically crossed it.");

            // --- D4: Lower Vault -> Final Room ---
            var d4Target = doors[3].transform.position + new Vector3(0f, 0f, ForwardCrossingMargin(doors[3]));
            yield return DriveDoorAndLeg(movement, doors[3], positionAfterD3, d4Target, moveSpeed, log);
            var positionAfterD4 = player.transform.position;
            // AC-001, room 5 of 5 (Final Room) - "into the Final Room" is this task's stated goal.
            Assert.IsTrue(
                FinalRoomLayout.RoomBounds.Contains(GroundPoint(positionAfterD4, FinalRoomLayout.RoomBounds)),
                $"AC-001: after crossing D4 the player's position {positionAfterD4} must fall "
                + $"within Final Room's RoomBounds {FinalRoomLayout.RoomBounds}.\n{log}");
            Assert.IsTrue(doors[3].HasCrossedForward,
                "D4: HasCrossedForward must be true once the player has physically crossed it.");

            // --- D5: crossed as the fifth ordered door (AC-001 "through D1, D2, D3, D4 and D5 in
            // order"). D5 sits at FinalRoomLayout.MaximumZ, the room's own far wall - not a sixth
            // room - so no RoomBounds check applies to its far side. Asserted instead against the
            // same live forward-crossing-trigger geometry DoorInteractable itself uses to decide
            // HasCrossedForward (read by reflection above, never a hardcoded literal), so this is
            // still a position-derived proof and not a bare door event.
            var d5Target = doors[4].transform.position + new Vector3(0f, 0f, ForwardCrossingMargin(doors[4]));
            yield return DriveDoorAndLeg(movement, doors[4], positionAfterD4, d5Target, moveSpeed, log);
            var positionAfterD5 = player.transform.position;
            var d5FarFaceZ = ForwardCrossingFarFaceZ(doors[4]);
            Assert.Greater(positionAfterD5.z, d5FarFaceZ,
                $"AC-001: after crossing D5 the player's position {positionAfterD5} must lie past "
                + $"D5's own forward-crossing trigger far face (z > {d5FarFaceZ:F2}) - the same "
                + $"production geometry DoorInteractable places its own crossing detector at.\n{log}");
            Assert.IsTrue(doors[4].HasCrossedForward,
                "D5: HasCrossedForward must be true - the fifth and final door in order.");
            Assert.IsTrue(doors[4].IsFinalDoor,
                "D5 must be the door DoorSpawner marks IsFinalDoor - sanity check that this is "
                + "really the last door in the sequence.");

            Debug.Log(log.ToString());
        }

        // MUST be awaited (yield return), never fired-and-forgotten: an unawaited
        // SceneManager.UnloadSceneAsync lands its unload asynchronously inside whichever fixture
        // runs NEXT, corrupting an unrelated test - see
        // FiveRoomDoorSequencePlayModeTests.UnloadRuntimeWorldSceneWithoutSaving's own remarks for
        // the 2026-09-23 precedent this mirrors exactly (not shared, for the same reason above).
        private static IEnumerator UnloadRuntimeWorldSceneWithoutSaving()
        {
            var scene = SceneManager.GetSceneByName("RuntimeWorld");
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            var cleanupScene = SceneManager.CreateScene("FiveRoomTraversalTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            yield return UnloadRuntimeWorldSceneWithoutSaving();
        }
    }
}
