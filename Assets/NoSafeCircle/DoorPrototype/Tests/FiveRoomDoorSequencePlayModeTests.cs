using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using NoSafeCircle.DoorPrototype;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-049 AC-002/VAL-002: runtime checks for the ordered, interaction-owned D1-D5 instances.
    public sealed class FiveRoomDoorSequencePlayModeTests
    {
        // Bounds the wait for the door's arm's-reach trigger to fire after a teleport. One fixed
        // step is enough in practice; this only stops a fixture defect from hanging the run.
        private const int MaxTriggerSettleFixedSteps = 10;

        // The new world does not exist until GameBootstrap runs: the wait is not optional. See
        // e82bd6f23 (TitleScreenPlayModeTests) for why two frames plus HasBuilt, not a frame count.
        private static IEnumerator WaitForWorldBuilt()
        {
            yield return null;
            GameObject managers = GameObject.Find("GameManagers");
            Assert.IsNotNull(managers,
                "RuntimeWorld.unity carries no GameManagers object, so nothing builds the world.");
            var bootstrap = managers.GetComponent<World.GameBootstrap>();
            Assert.IsNotNull(bootstrap, "GameManagers carries no GameBootstrap.");

            yield return null;
            yield return null;

            Assert.IsTrue(bootstrap.HasBuilt,
                "GameBootstrap had not built after three frames, so every assertion below would "
                + "fail on an empty world rather than on the thing under test. SpawnedCount = "
                + bootstrap.SpawnedCount + ".");
        }

        // NOT root-scoped: RuntimeWorld nests every spawned object under its spawner
        // (GameManagers -> <Family>Spawner -> the object), never at the scene root, unlike the
        // old committed scene the previous scene.GetRootGameObjects().Single(...) calls here
        // were written against. Recurses the whole loaded scene and keeps the original
        // "expect exactly one" guarantee.
        private static GameObject FindInScene(Scene scene, string name)
        {
            var matches = new System.Collections.Generic.List<GameObject>();
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                CollectByName(root.transform, name, matches);
            }
            Assert.AreEqual(1, matches.Count,
                $"Expected exactly one '{name}' object in loaded scene {scene.path}, found {matches.Count}.");
            return matches[0];
        }

        private static void CollectByName(Transform node, string name, System.Collections.Generic.List<GameObject> matches)
        {
            if (node.name == name) matches.Add(node.gameObject);
            for (int i = 0; i < node.childCount; i++)
            {
                CollectByName(node.GetChild(i), name, matches);
            }
        }

        [UnityTest]
        public IEnumerator CanonicalScene_HasOrderedDoors_AndD5IsTheOnlyFinalDoor()
        {
            yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName("RuntimeWorld");
            var doors = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<DoorInteractable>(true))
                .OrderBy(door => door.DoorId)
                .ToArray();

            Assert.AreEqual(5, doors.Length);
            for (var index = 0; index < doors.Length; index++)
            {
                Assert.AreEqual((DoorId)index, doors[index].DoorId);
                Assert.IsFalse(doors[index].IsOpen, $"{doors[index].DoorId} must start sealed.");
                Assert.IsFalse(doors[index].HasCrossedForward,
                    $"{doors[index].DoorId} must not count opening as crossing.");
                Assert.AreEqual(index == 4, doors[index].IsFinalDoor);
            }

            // THESE ARE THE CATALOG'S POSITIONS, AND THE CATALOG IS AUTHORITATIVE.
            // D3, D4 and D5 moved in fb36f012f ("NSC-101: one catalog to write, five rooms to
            // read it"), which lists the moves as deliberate contract work. This fixture last
            // changed 2026-09-13, BEFORE that commit, so it kept asserting the pre-NSC-101
            // layout. D1 and D2 were not moved and are unchanged here - they are the control
            // that shows this is three stale expectations rather than a broken composition.
            //
            // Verified against RoomSceneCatalog.asset rather than taken on inference:
            // doorId 2 {x: -8, y: 54}, doorId 3 {x: 4, y: 76}, doorId 4 {x: 0, y: 104}.
            // doorId 2's value was also measured directly from a failing run before this fix.
            //
            // THE ASSERTS ARE SEQUENTIAL, so a stale expectation here hides every later one:
            // only D3 had ever been seen to fail, because the run stopped there.
            Assert.AreEqual(new Vector3(0f, 0f, 0f), doors[0].transform.position);
            Assert.AreEqual(new Vector3(6f, 0f, 20f), doors[1].transform.position);
            Assert.AreEqual(new Vector3(-8f, 0f, 54f), doors[2].transform.position);
            Assert.AreEqual(new Vector3(4f, 0f, 76f), doors[3].transform.position);
            Assert.AreEqual(new Vector3(0f, 0f, 104f), doors[4].transform.position);
        }

        // NSC-049 VAL-006: drives each composed door's existing DoorInteractionFeedback
        // component against its NSC-065 textured door Renderer, consuming only
        // DoorInteractable's own selection test and PlayerInteractionController's own
        // pending-door/IsInteracting state - no second selection or feedback path. The shared
        // pointer target is set directly through PlayerMovement's own property setters rather
        // than simulating screen-space mouse input: DoorInteractionFeedbackHoverPlayModeTests
        // already proves hover against real mouse/camera projection, so this only needs to
        // prove feedback against DoorInteractable's production TryGetSelectionDistance test on
        // each of the composed scene's actual D1-D5 instances.
        [UnityTest]
        public IEnumerator ComposedScene_DoorFeedback_TracksHoverSelectedAndOpeningPerDoor()
        {
            yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName("RuntimeWorld");

            // THE COMPOSED SCENE STARTS AT THE TITLE SCREEN WITH GAMEPLAY INPUT SUSPENDED.
            // TitleScreenController.Awake calls SuspendGameplayInput on PlayerInteractionController,
            // and DoorInteractionFeedback gates IsHovered on exactly that flag - it reads
            // `gameplayEnabled = interactionController == null || interactionController
            // .IsGameplayEnabled` before hover can ever become true. So hover feedback cannot
            // activate in a freshly loaded scene no matter how the pointer is set, and this test
            // failed on D1 for that reason alone rather than for anything wrong with the feedback.
            // Entering gameplay the way a player does is what makes the assertion meaningful.
            yield return EnterGameplayThroughRunEntry();

            var player = FindInScene(scene, "Player");
            var movement = player.GetComponent<PlayerMovement>();
            var interactionController = player.GetComponent<PlayerInteractionController>();

            // PlayerMovement.Update already calls Tick, so leaving the component enabled would
            // advance movement on rendered frames as well as on this fixture's explicit
            // Tick(0.02f) calls. Disabling it makes those explicit calls the only clock that
            // moves the wizard, which is what the per-phase assertions below assume.
            movement.enabled = false;

            var doorRootNames = new[] { "DoorRoot", "D2", "D3", "D4", "D5" };

            foreach (var doorRootName in doorRootNames)
            {
                var doorRoot = FindInScene(scene, doorRootName);
                var door = doorRoot.GetComponent<DoorInteractable>();
                var feedback = doorRoot.GetComponent<DoorInteractionFeedback>();
                var doorRenderer = doorRoot.transform.Find("DoorVisual").Find("DoorSprite").GetComponent<SpriteRenderer>();

                Assert.IsNotNull(doorRenderer.sprite,
                    $"{door.DoorId}: expected the NSC-065 textured door Renderer to have an assigned sprite, " +
                    "not a placeholder Renderer.");

                feedback.ResetFeedback();
                var sealedColor = ReadRendererColor(doorRenderer);

                // Hover: the shared pointer target falls within this door's own accepted
                // selection area and no stronger state is active yet.
                SetPointerWorldTarget(movement, door.SelectionPoint, true);
                feedback.Tick(0.02f);

                Assert.IsTrue(door.TryGetSelectionDistance(door.SelectionPoint, out _),
                    $"{door.DoorId}: test setup point must actually fall within DoorInteractable's own " +
                    "selection area.");
                Assert.IsTrue(feedback.IsHovered, $"{door.DoorId}: VAL-006 hover feedback must activate.");
                Assert.IsFalse(feedback.IsSelected);
                Assert.IsFalse(feedback.IsOpening);
                Assert.AreNotEqual(sealedColor, ReadRendererColor(doorRenderer),
                    $"{door.DoorId}: VAL-006 hover feedback must apply the hover tint.");

                // Selected: TryBeginDoorApproach makes this door the pending door, but arrival
                // has not happened yet (movement still has an active destination), so
                // IsInteracting must not have started.
                //
                // THE WIZARD MUST BE INSIDE THIS DOOR'S ARM'S-REACH TRIGGER FIRST, AND THAT
                // TRIGGER IS DISPATCHED BY THE PHYSICS STEP RATHER THAN BY A RENDERED FRAME.
                // DoorInteractable.OnTriggerEnter is the only thing that calls NotifyDoorInRange,
                // which is the only thing that sets PlayerInteractionController.CurrentDoor - and
                // TryStartPendingDoorInteraction returns early while PendingDoor != CurrentDoor.
                // A teleport followed only by Tick calls never runs a physics step, so CurrentDoor
                // stayed null for every one of D1-D5 and the opening timer could never start. That
                // was a fixture defect rather than missing feedback: the production path reaches
                // this state by walking the wizard into the trigger, which steps physics on the way.
                yield return TeleportIntoDoorRange(player, interactionController, door);

                Assert.IsTrue(interactionController.TryBeginDoorApproach(door.SelectionPoint),
                    $"{door.DoorId}: test setup must actually select the door.");
                feedback.Tick(0.02f);

                Assert.IsTrue(feedback.IsSelected, $"{door.DoorId}: VAL-006 selected feedback must activate.");
                Assert.IsFalse(feedback.IsOpening,
                    $"{door.DoorId}: opening feedback must not activate before DoorInteractable.IsInteracting " +
                    "is actually running.");
                Assert.AreNotEqual(sealedColor, ReadRendererColor(doorRenderer),
                    $"{door.DoorId}: VAL-006 selected feedback must apply the selected tint.");

                // Opening: arrival (no active destination remaining) starts the automatic
                // timer, which is DoorInteractable.IsInteracting actually running.
                movement.Tick(0.02f);
                feedback.Tick(0.02f);

                Assert.IsTrue(door.IsInteracting, $"{door.DoorId}: test setup must actually start the opening timer.");
                Assert.IsTrue(feedback.IsOpening, $"{door.DoorId}: VAL-006 opening feedback must activate.");
                Assert.AreNotEqual(sealedColor, ReadRendererColor(doorRenderer),
                    $"{door.DoorId}: VAL-006 opening feedback must apply the opening tint.");

                interactionController.EndInteraction();
                feedback.Tick(0.02f);
                yield return null;
            }
        }

        // NSC-049 VAL-007/NSC-017 INT-003: locks a composed door through its production
        // crossing path (open, then the same forward-crossing setup seam DoorLockDurabilityPlayModeTests
        // already uses), breaks it through DoorInteractable.TakeDamage, waits for
        // DoorEnemyPassability's stationary NavMeshObstacle carving to settle, and verifies a
        // test-owned NavMeshAgent using the project agent type finds a complete path from the
        // door's approach side to its forward side.
        [UnityTest]
        public IEnumerator ComposedScene_BrokenDoor_NavMeshPathReconnectsAcrossDoorway()
        {
            yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName("RuntimeWorld");

            var doorRoot = FindInScene(scene, "DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var player = FindInScene(scene, "Player");
            var playerCollider = player.GetComponent<CharacterController>();

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            yield return null;
            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before locking it.");

            InvokeForwardCrossingTriggerEnter(door, playerCollider);
            yield return null;
            Assert.IsTrue(door.IsLocked, "Test setup must actually lock the door before breaking it.");

            door.TakeDamage(door.MaxDurability);
            yield return null;
            Assert.IsTrue(door.IsBroken, "Test setup must actually break the door before checking passability.");

            for (var frame = 0; frame < 10; frame++) yield return null;
            Physics.SyncTransforms();

            var doorPosition = doorRoot.transform.position;
            var approachPoint = doorPosition + new Vector3(0f, 0f, -2f);
            var forwardPoint = doorPosition + new Vector3(0f, 0f, 2f);

            Assert.IsTrue(NavMesh.SamplePosition(approachPoint, out var approachHit, 1.5f, NavMesh.AllAreas),
                "Expected the door's approach side to be on the baked gameplay NavMesh.");
            Assert.IsTrue(NavMesh.SamplePosition(forwardPoint, out var forwardHit, 1.5f, NavMesh.AllAreas),
                "Expected the door's forward side to be on the baked gameplay NavMesh.");

            var agentObject = new GameObject("VAL007TestNavMeshAgent");
            try
            {
                agentObject.transform.position = approachHit.position;
                var agent = agentObject.AddComponent<NavMeshAgent>();
                var navigationSettings = NavMesh.GetSettingsByIndex(0);
                agent.agentTypeID = navigationSettings.agentTypeID;
                agent.radius = navigationSettings.agentRadius;
                agent.height = navigationSettings.agentHeight;

                var path = new NavMeshPath();
                var found = agent.CalculatePath(forwardHit.position, path);

                // "CalculatePath returned false" and "it returned a PARTIAL path" have opposite
                // causes - the first is no navmesh under an endpoint, the second is a blocked
                // corridor between two reachable endpoints - and the bare assertion could not
                // tell them apart. The doorway sample is the discriminator the contract points
                // at: VAL-007 targets "the builder's door-before-bake order", so a doorway with
                // NO navmesh at all means the hole was BAKED IN and no runtime carving change
                // can reopen it, while a carved hole means the obstacle is still carving.
                var doorwayOnNavMesh = NavMesh.SamplePosition(doorPosition, out var doorwayHit, 1.5f, NavMesh.AllAreas);
                var obstacle = doorRoot.GetComponentInChildren<NavMeshObstacle>(true);
                var blockers = doorRoot.GetComponentsInChildren<Collider>(true)
                    .Where(c => c.enabled && !c.isTrigger)
                    .Select(c => $"{c.name}[y {c.bounds.min.y:F2}..{c.bounds.max.y:F2}]")
                    .ToArray();

                Assert.IsTrue(found && path.status == NavMeshPathStatus.PathComplete,
                    "VAL-007/NSC-017 INT-003: a test-owned NavMeshAgent using the project agent type must " +
                    "find a complete path from the broken door's approach side to its forward side once " +
                    "DoorEnemyPassability carving has settled." +
                    $" CalculatePath returned {found}, status {path.status}, {path.corners.Length} corner(s)." +
                    $" Approach {approachHit.position} -> forward {forwardHit.position}." +
                    $" Doorway {doorPosition} on navmesh: {doorwayOnNavMesh}" +
                    (doorwayOnNavMesh ? $" at {doorwayHit.position}." : " (NO walkable surface in the doorway).") +
                    $" IsBroken {door.IsBroken}, obstacle " +
                    (obstacle == null
                        ? "absent."
                        : $"enabled {obstacle.enabled} carving {obstacle.carving}.") +
                    $" Enabled non-trigger colliders still under the door: {string.Join(", ", blockers)}.");
            }
            finally
            {
                Object.Destroy(agentObject);
            }
        }

        // The four-room table and RoomOf lookup used to be a local function/array inside
        // ComposedScene_FixedSquadSpawns_MatchApprovedDistributionAndOracles below. Promoted to
        // shared static state so FixedSquadSpawnPositionTests (the per-position AC-006 cases
        // split out below) can compute the same room membership without duplicating the table.
        private static readonly (string Name, float MinX, float MaxX, float MinZ, float MaxZ)[] Rooms =
        {
            ("BoneArchive", -12f, 12f, 0f, 20f),
            ("ChapelOfAsh", -18f, 18f, 20f, 54f),
            ("LowerVault", -20f, 20f, 54f, 76f),
            ("FinalRoom", -15f, 15f, 76f, 104f),
        };

        private static string RoomOf(Vector3 position)
        {
            foreach (var room in Rooms)
            {
                if (position.x >= room.MinX && position.x <= room.MaxX &&
                    position.z >= room.MinZ && position.z <= room.MaxZ)
                {
                    return room.Name;
                }
            }
            return null;
        }

        private static System.Type ResolveBuilderType()
        {
            var builderType = System.Type.GetType(
                "NoSafeCircle.DoorPrototype.Editor.World.DoorPrototypeGlobalSceneBuilder, " +
                "NoSafeCircle.DoorPrototype.Editor");
            Assert.IsNotNull(builderType,
                "VAL-008: expected to reflect DoorPrototypeGlobalSceneBuilder from the Editor assembly.");
            return builderType;
        }

        // NSC-049 VAL-008/AC-005: reads DoorPrototypeGlobalSceneBuilder's fixed melee/ranged
        // squad arrays by reflection (this Play Mode test can reach the baked gameplay NavMesh,
        // unlike the Edit Mode composition tests) and asserts the counts, the AC-005 per-room
        // distribution and the placement-intent oracles that compare positions WITHIN a room to
        // each other - relations a single per-position case cannot express.
        //
        // AC-006 clearance (wall inset, NavMesh sample, CheckSphere) and the general AC-005
        // "falls within an approved room" membership check moved to FixedSquadSpawnPositionTests
        // below: those are independent per spawn, and this method's single [UnityTest] used to
        // throw on the FIRST failing one and hide the rest. Splitting them means N spawn defects
        // now report as N failing cases instead of 1 - see NSC's game-fixer brief for
        // fix/spawn-test-split. NOT a coordinate fix: no position value changed by this split.
        [UnityTest]
        public IEnumerator ComposedScene_FixedSquadSpawns_MatchApprovedDistributionAndOracles()
        {
            yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            Physics.SyncTransforms();

            var builderType = ResolveBuilderType();
            var meleePositions = GetPrivateStaticVector3Array(builderType, "EnemySpawnPositions");
            var rangedPositions = GetPrivateStaticVector3Array(builderType, "LanternWraithSpawnPositions");

            Assert.AreEqual(5, meleePositions.Length, "AC-005: exactly 5 melee entries.");
            Assert.AreEqual(4, rangedPositions.Length, "AC-005: exactly 4 ranged entries.");

            var meleeByRoom = meleePositions.GroupBy(RoomOf).ToDictionary(g => g.Key, g => g.ToList());
            var rangedByRoom = rangedPositions.GroupBy(RoomOf).ToDictionary(g => g.Key, g => g.ToList());

            List<Vector3> RoomList(Dictionary<string, List<Vector3>> dict, string room) =>
                dict.TryGetValue(room, out var list) ? list : new List<Vector3>();

            Assert.AreEqual(1, RoomList(meleeByRoom, "BoneArchive").Count, "AC-005: Bone Archive melee count.");
            Assert.AreEqual(1, RoomList(meleeByRoom, "ChapelOfAsh").Count, "AC-005: Chapel of Ash melee count.");
            Assert.AreEqual(1, RoomList(meleeByRoom, "LowerVault").Count, "AC-005: Lower Vault melee count.");
            Assert.AreEqual(2, RoomList(meleeByRoom, "FinalRoom").Count, "AC-005: Final Room melee count.");

            Assert.AreEqual(1, RoomList(rangedByRoom, "BoneArchive").Count, "AC-005: Bone Archive ranged count.");
            Assert.AreEqual(1, RoomList(rangedByRoom, "ChapelOfAsh").Count, "AC-005: Chapel of Ash ranged count.");
            Assert.AreEqual(1, RoomList(rangedByRoom, "LowerVault").Count, "AC-005: Lower Vault ranged count.");
            Assert.AreEqual(1, RoomList(rangedByRoom, "FinalRoom").Count, "AC-005: Final Room ranged count.");

            // Door-line oracles (a)/(c): Bone Archive, Chapel of Ash, Lower Vault.
            AssertSingleMeleeRoomOracles("BoneArchive",
                RoomList(meleeByRoom, "BoneArchive")[0], RoomList(rangedByRoom, "BoneArchive")[0],
                entry: new Vector2(0f, 0f), exit: new Vector2(6f, 20f),
                approachA: new Vector2(0f, 1.5f), approachB: new Vector2(6f, 18.5f));
            AssertSingleMeleeRoomOracles("ChapelOfAsh",
                RoomList(meleeByRoom, "ChapelOfAsh")[0], RoomList(rangedByRoom, "ChapelOfAsh")[0],
                entry: new Vector2(6f, 20f), exit: new Vector2(-8f, 54f),
                approachA: new Vector2(6f, 21.5f), approachB: new Vector2(-8f, 52.5f));
            AssertSingleMeleeRoomOracles("LowerVault",
                RoomList(meleeByRoom, "LowerVault")[0], RoomList(rangedByRoom, "LowerVault")[0],
                entry: new Vector2(-8f, 54f), exit: new Vector2(4f, 76f),
                approachA: new Vector2(-8f, 55.5f), approachB: new Vector2(4f, 74.5f));

            // Oracle (b): Final Room's two melee spawns.
            var finalMelee = RoomList(meleeByRoom, "FinalRoom");
            var d4 = new Vector2(4f, 76f);
            var d5 = new Vector2(0f, 104f);
            var finalMidpoint = (d4 + d5) * 0.5f;
            var lineDirection = d5 - d4;
            foreach (var spawn in finalMelee)
            {
                var flat = new Vector2(spawn.x, spawn.z);
                Assert.LessOrEqual(Vector2.Distance(flat, finalMidpoint), 6.0f,
                    $"AC-005(b): Final Room melee spawn {spawn} must lie within 6 units of the D4-D5 midpoint.");
            }
            var side0 = Cross(lineDirection, new Vector2(finalMelee[0].x, finalMelee[0].z) - d4);
            var side1 = Cross(lineDirection, new Vector2(finalMelee[1].x, finalMelee[1].z) - d4);
            Assert.Less(side0 * side1, 0f,
                "AC-005(b): Final Room's two melee spawns must lie on opposite sides of the D4-D5 line.");

            // Oracle (d): Final Room ranged spawn.
            var finalRanged = RoomList(rangedByRoom, "FinalRoom")[0];
            Assert.LessOrEqual(Vector2.Distance(new Vector2(finalRanged.x, finalRanged.z), d4), 12.0f,
                "AC-005(d): Final Room ranged spawn must lie within 12 units of D4.");
            Assert.IsTrue(HasClearLinecast(finalRanged, new Vector2(4f, 77.5f)),
                "AC-005(d): Final Room ranged spawn must have a clear Linecast to the D4 approach point.");
        }

        // NSC-049 AC-005 (general membership)/AC-006: one case per fixed spawn (9 total: 5 melee +
        // 4 ranged), split out of ComposedScene_FixedSquadSpawns_MatchApprovedDistributionAndOracles
        // above so N independent spawn defects report as N failing cases instead of NUnit's single
        // [UnityTest] throwing on the first Assert and hiding the rest. Every check here is about
        // ONE position in isolation (room membership, wall inset, NavMesh sample, clearance) -
        // never a relation between two spawns, which is what stayed in the method above.
        //
        // MEASURED, NOT ASSUMED: [UnityTest]+[TestCaseSource] was tried first (case names built by
        // reflecting the builder's arrays at NUnit collection time, which DID work - all 9 names
        // resolved correctly before any scene loaded). But every generated case then reported
        // result="Failed", runstate="NotRunnable", reason "Method has non-void return value, but
        // no result is expected" - this project's com.unity.test-framework@7056e7f856e9 does not
        // run a [TestCaseSource]-parameterized IEnumerator as a coroutine the way a parameterless
        // [UnityTest] is. Confirmed by running this exact fixture (see fix/spawn-test-split run
        // log): 9/9 cases NotRunnable with that message, none of the AC-006 assertions ever
        // executed. Falling back to 9 separately named, parameterless [UnityTest] methods, as
        // this brief allows when TestCaseSource proves unreliable.
        //
        // Room/role -> position is still resolved once by reflection (NamedSpawnPosition), so a
        // change to the builder's spawn ARRAY SIZE surfaces as an assertion failure here (a named
        // case whose position goes missing) as well as in the count asserts kept in
        // ComposedScene_FixedSquadSpawns_MatchApprovedDistributionAndOracles above - but adding a
        // 10th spawn would need a 10th named method here; nothing generates one automatically.
        //
        // UNSHARED BY MEASUREMENT, NOT BY DEFAULT: a first version loaded RuntimeWorld ONCE for
        // all 9 cases (a static s_WorldBuilt guard in UnitySetUp) and unloaded it once in
        // [OneTimeTearDown] after the last case ran. That teardown is SYNCHRONOUS by NUnit's own
        // contract, so it could not `yield return SceneManager.UnloadSceneAsync(...)` the way
        // every other teardown in this file does - it fired the unload and returned immediately,
        // leaving no active scene and an in-flight unload that landed asynchronously inside
        // whichever fixture ran next. The full NoSafeCircle-filtered suite caught this as two
        // fixtures nothing here touches going red for reasons that were never their own
        // (HoldPositionPlayModeTests x2, HudSpawnerPlayModeTests x1) - see
        // PlayModeSceneCleanupConventionTests.cs remarks for the 2026-09-23 precedent of the same
        // shape, and note its own guard only checks for the literal "UnloadSceneAsync" appearing
        // in source, so it cannot tell an awaited call from a fired-and-forgotten one.
        //
        // So each case here loads and unloads RuntimeWorld itself, exactly like every other test
        // in the outer class, via the SAME awaited UnloadRuntimeWorldSceneWithoutSaving() helper.
        // Measured cost of the shared version was 0.334s total (9 cases) against roughly 2.9s
        // unshared (9 x this fixture's ~0.32s single-scene cost) - about 2.5s. That is worth
        // paying to remove a correctness race across fixtures that do not know about each other.
        [TestFixture]
        public sealed class FixedSquadSpawnPositionTests
        {
            [UnitySetUp]
            public IEnumerator SetUp()
            {
                yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);
                yield return WaitForWorldBuilt();
                Physics.SyncTransforms();
            }

            [UnityTearDown]
            public IEnumerator TearDown()
            {
                yield return UnloadRuntimeWorldSceneWithoutSaving();
            }

            // Resolved by name rather than cached once: the reflection cost is two FieldInfo
            // reads and is negligible next to the NavMesh/Physics queries below, and recomputing
            // it per case avoids any dependency on static-field init order.
            private static Vector3 NamedSpawnPosition(string caseName)
            {
                var builderType = ResolveBuilderType();
                var meleePositions = GetPrivateStaticVector3Array(builderType, "EnemySpawnPositions");
                var rangedPositions = GetPrivateStaticVector3Array(builderType, "LanternWraithSpawnPositions");

                var roleCounts = new Dictionary<string, int>();
                var tagged = meleePositions.Select(p => (Position: p, Role: "Melee"))
                    .Concat(rangedPositions.Select(p => (Position: p, Role: "Ranged")));

                foreach (var entry in tagged)
                {
                    var roomName = RoomOf(entry.Position) ?? "UnknownRoom";
                    var key = roomName + "_" + entry.Role;
                    roleCounts.TryGetValue(key, out var count);
                    count++;
                    roleCounts[key] = count;
                    if ($"{roomName}_{entry.Role}_{count}" == caseName) return entry.Position;
                }

                Assert.Fail($"Expected a fixed spawn position named '{caseName}' among the builder's " +
                    "current melee/ranged arrays, but none matched - the array contents or size " +
                    "changed under this hard-coded case name.");
                return default;
            }

            private static void AssertClearsWallInsetNavMeshAndCollision(Vector3 position, string roomNameForMessage)
            {
                var roomName = RoomOf(position);
                Assert.IsNotNull(roomName,
                    $"AC-005: fixed spawn {position} must fall within one of the four approved " +
                    "enemy-bearing rooms.");
                var room = Rooms.Single(r => r.Name == roomName);

                Assert.GreaterOrEqual(position.x, room.MinX + 1.5f,
                    $"AC-006: {position} must lie at least 1.5 units inside {room.Name}'s west wall.");
                Assert.LessOrEqual(position.x, room.MaxX - 1.5f,
                    $"AC-006: {position} must lie at least 1.5 units inside {room.Name}'s east wall.");
                Assert.GreaterOrEqual(position.z, room.MinZ + 1.5f,
                    $"AC-006: {position} must lie at least 1.5 units inside {room.Name}'s south wall.");
                Assert.LessOrEqual(position.z, room.MaxZ - 1.5f,
                    $"AC-006: {position} must lie at least 1.5 units inside {room.Name}'s north wall.");

                // The 0.1 maxDistance is the contract's own number (AC-006 and VAL-008 both state
                // it), so it is asserted exactly as written. The wide probe before it exists only
                // to say HOW FAR the nearest walkable point actually is when this fails - a bare
                // "sampled false" cannot tell a missing bake apart from a surface a few
                // centimetres above the authored spawn height.
                var nearestFound = NavMesh.SamplePosition(position, out var nearest, 5f, NavMesh.AllAreas);
                var nearestDetail = nearestFound
                    ? $" Nearest walkable point is {nearest.position}, {Vector3.Distance(position, nearest.position):F4} away " +
                      $"(dY {nearest.position.y - position.y:F4})."
                    : " No walkable point within 5 units, so this is a bake gap rather than a height offset.";

                Assert.IsTrue(NavMesh.SamplePosition(position, out _, 0.1f, NavMesh.AllAreas),
                    $"AC-006: {position} in {roomNameForMessage} must sample the baked gameplay NavMesh within 0.1 units." +
                    nearestDetail);

                var checkPoint = position + Vector3.up;
                Assert.IsFalse(Physics.CheckSphere(checkPoint, 0.5f, Physics.AllLayers, QueryTriggerInteraction.Ignore),
                    $"AC-006: {position} must be clear of non-trigger colliders.");
            }

            [UnityTest]
            public IEnumerator BoneArchive_Melee_1()
            {
                AssertClearsWallInsetNavMeshAndCollision(NamedSpawnPosition("BoneArchive_Melee_1"), "BoneArchive");
                yield break;
            }

            [UnityTest]
            public IEnumerator BoneArchive_Ranged_1()
            {
                AssertClearsWallInsetNavMeshAndCollision(NamedSpawnPosition("BoneArchive_Ranged_1"), "BoneArchive");
                yield break;
            }

            [UnityTest]
            public IEnumerator ChapelOfAsh_Melee_1()
            {
                AssertClearsWallInsetNavMeshAndCollision(NamedSpawnPosition("ChapelOfAsh_Melee_1"), "ChapelOfAsh");
                yield break;
            }

            [UnityTest]
            public IEnumerator ChapelOfAsh_Ranged_1()
            {
                AssertClearsWallInsetNavMeshAndCollision(NamedSpawnPosition("ChapelOfAsh_Ranged_1"), "ChapelOfAsh");
                yield break;
            }

            [UnityTest]
            public IEnumerator LowerVault_Melee_1()
            {
                AssertClearsWallInsetNavMeshAndCollision(NamedSpawnPosition("LowerVault_Melee_1"), "LowerVault");
                yield break;
            }

            [UnityTest]
            public IEnumerator LowerVault_Ranged_1()
            {
                AssertClearsWallInsetNavMeshAndCollision(NamedSpawnPosition("LowerVault_Ranged_1"), "LowerVault");
                yield break;
            }

            [UnityTest]
            public IEnumerator FinalRoom_Melee_1()
            {
                AssertClearsWallInsetNavMeshAndCollision(NamedSpawnPosition("FinalRoom_Melee_1"), "FinalRoom");
                yield break;
            }

            [UnityTest]
            public IEnumerator FinalRoom_Melee_2()
            {
                AssertClearsWallInsetNavMeshAndCollision(NamedSpawnPosition("FinalRoom_Melee_2"), "FinalRoom");
                yield break;
            }

            [UnityTest]
            public IEnumerator FinalRoom_Ranged_1()
            {
                AssertClearsWallInsetNavMeshAndCollision(NamedSpawnPosition("FinalRoom_Ranged_1"), "FinalRoom");
                yield break;
            }
        }

        private static void AssertSingleMeleeRoomOracles(
            string roomName, Vector3 melee, Vector3 ranged, Vector2 entry, Vector2 exit,
            Vector2 approachA, Vector2 approachB)
        {
            var midpoint = (entry + exit) * 0.5f;
            var meleeFlat = new Vector2(melee.x, melee.z);
            var rangedFlat = new Vector2(ranged.x, ranged.z);

            Assert.LessOrEqual(Vector2.Distance(meleeFlat, midpoint), 4.0f,
                $"AC-005(a): {roomName}'s melee spawn must lie within 4 units of its door-line midpoint.");

            var lineDirection = exit - entry;
            var meleeSide = Cross(lineDirection, meleeFlat - entry);
            var rangedSide = Cross(lineDirection, rangedFlat - entry);
            Assert.Less(meleeSide * rangedSide, 0f,
                $"AC-005(c): {roomName}'s ranged spawn must lie on the opposite side of the door line from " +
                "its melee spawn.");
            Assert.GreaterOrEqual(Vector2.Distance(meleeFlat, rangedFlat), 6.0f,
                $"AC-005(c): {roomName}'s ranged spawn must lie at least 6 units from its melee spawn.");

            var clearToA = HasClearLinecast(ranged, approachA);
            var clearToB = HasClearLinecast(ranged, approachB);
            Assert.IsTrue(clearToA || clearToB,
                $"AC-005(c): {roomName}'s ranged spawn must have a clear Linecast to at least one door " +
                "approach point.");
        }

        private static bool HasClearLinecast(Vector3 from, Vector2 toFlat)
        {
            var start = new Vector3(from.x, 1.0f, from.z);
            var end = new Vector3(toFlat.x, 1.0f, toFlat.y);
            return !Physics.Linecast(start, end, out _,
                SightOcclusionLayers.ExcludeLowDressing(Physics.AllLayers), QueryTriggerInteraction.Ignore);
        }

        private static float Cross(Vector2 a, Vector2 b) => a.x * b.y - a.y * b.x;

        private static Vector3[] GetPrivateStaticVector3Array(System.Type type, string fieldName)
        {
            var field = type.GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Static);
            Assert.IsNotNull(field, $"Expected a private static Vector3[] field named '{fieldName}' on {type.Name}.");
            return (Vector3[])field.GetValue(null);
        }

        private static void SetPointerWorldTarget(PlayerMovement movement, Vector3 target, bool hasTarget)
        {
            var pointerProperty = typeof(PlayerMovement).GetProperty(nameof(PlayerMovement.PointerWorldTarget));
            pointerProperty.GetSetMethod(true).Invoke(movement, new object[] { target });
            var hasProperty = typeof(PlayerMovement).GetProperty(nameof(PlayerMovement.HasPointerWorldTarget));
            hasProperty.GetSetMethod(true).Invoke(movement, new object[] { hasTarget });
        }

        private static void TeleportPlayer(GameObject player, Vector3 position)
        {
            var controller = player.GetComponent<CharacterController>();
            controller.enabled = false;
            player.transform.position = position;
            controller.enabled = true;
        }

        // A physics step, not a rendered frame, is what dispatches the door's arm's-reach trigger
        // and so what sets PlayerInteractionController.CurrentDoor. Teleporting is a discrete
        // position change, so the overlap is only recomputed on the next FixedUpdate; this waits
        // for the door to actually report the wizard in range and fails naming CurrentDoor if it
        // never does, rather than letting a later feedback assertion inherit the blame.
        private static IEnumerator TeleportIntoDoorRange(
            GameObject player, PlayerInteractionController interactionController, DoorInteractable door)
        {
            TeleportPlayer(player, door.InteractionPosition);
            Physics.SyncTransforms();

            for (var step = 0; step < MaxTriggerSettleFixedSteps && interactionController.CurrentDoor != door; step++)
            {
                yield return new WaitForFixedUpdate();
            }

            Assert.AreSame(door, interactionController.CurrentDoor,
                $"{door.DoorId}: test setup must put the wizard inside this door's arm's-reach trigger at " +
                $"its InteractionPosition {door.InteractionPosition}. PlayerInteractionController.CurrentDoor " +
                "is what TryStartPendingDoorInteraction gates the opening timer on, and it is set only by " +
                "DoorInteractable.OnTriggerEnter.");
        }

        // Walks the committed scene from its title screen into gameplay exactly as a player does:
        // StartGame raises WizardSelectionRequested, WizardSelectionController shows its panel, and
        // SelectOption plus ConfirmSelection hand a confirmed selection to WizardGameEntryController,
        // which spawns the wizard and re-enables gameplay input on both player controllers.
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

        private static Color ReadRendererColor(Renderer renderer)
        {
            var block = new MaterialPropertyBlock();
            renderer.GetPropertyBlock(block);
            return block.GetColor(Shader.PropertyToID("_Color"));
        }

        private static void InvokeForwardCrossingTriggerEnter(DoorInteractable target, Collider other)
        {
            var method = target.GetType().GetMethod("HandleForwardCrossingTriggerEnter",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(method,
                "Expected a private HandleForwardCrossingTriggerEnter(Collider) method on DoorInteractable.");
            method.Invoke(target, new object[] { other });
        }

        [UnityTearDown]
        public IEnumerator UnloadCanonicalSceneWithoutSaving()
        {
            yield return UnloadRuntimeWorldSceneWithoutSaving();
        }

        // Shared by this class's own UnityTearDown above and by
        // FixedSquadSpawnPositionTests.TearDown below, so both stay byte-for-byte identical to
        // the ORIGINAL pattern rather than risking drift between two hand-copies of it.
        //
        // MUST be awaited (yield return), never fired-and-forgotten from a synchronous
        // OneTimeTearDown: an unawaited SceneManager.UnloadSceneAsync lands its unload
        // asynchronously inside whichever fixture runs NEXT, and leaves no active scene behind
        // in the meantime. See PlayModeSceneCleanupConventionTests.cs remarks (2026-09-23): a
        // Single-loaded scene left behind this way took down two unrelated fixtures
        // (HoldPositionPlayModeTests, HudSpawnerPlayModeTests) with nothing wrong in either one -
        // exactly what a first version of FixedSquadSpawnPositionTests here did with a
        // fire-and-forget [OneTimeTearDown], caught by the full NoSafeCircle-filtered suite
        // (440/429/6/5) even though the fixture's own filtered run looked clean (11/13 passed,
        // both failures the two already-known-bad spawn coordinates).
        private static IEnumerator UnloadRuntimeWorldSceneWithoutSaving()
        {
            var scene = SceneManager.GetSceneByName("RuntimeWorld");
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            var cleanupScene = SceneManager.CreateScene("FiveRoomDoorSequenceTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }
    }
}
