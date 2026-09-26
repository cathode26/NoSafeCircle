using System.Collections;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Proves the DOORS lane end to end, AT RUNTIME, with no bake and no scene: the shipped
    // Resources/Spawners/DoorSpawner.prefab instantiates the shipped Resources/Doors/Door.prefab
    // five times, each clone lands on its layout line with the right identity and name, carries
    // the anatomy DoorPrototypeSceneBuilder.BuildDoor used to assemble in code, carves the navmesh
    // that was baked one phase earlier, and can be spawned again without doubling.
    //
    // EVERY EXPECTED VALUE COMES FROM SOMEWHERE OTHER THAN THE SPAWNER OR THE PREFAB: door centres
    // from the ENTRY room's copy of each shared door (the spawner reads the exit room's), the
    // opening width from RuinedEntryLayout, sorting from WorldSpriteConvention, the count from the
    // DoorId enum, and the passability behaviour from DoorEnemyPassability's own documented
    // contract. Literals that cannot be reached from this assembly (the builder's collider sizes,
    // the player radius) are cited to the line they come from.
    //
    // THE FIXTURE GEOMETRY IS DoorEnemyPassabilityPlayModeTests' (its constants and BuildFloor /
    // BuildDoorwayWalls, :22-29 and :174-203), whose DoorZ = 0 already puts the doorway on D1's
    // line, so nothing here is re-centred. Navigation is baked by a helper rather than in SetUp so
    // that ONE test can deliberately spawn before baking and show why the phase order exists.
    public sealed class DoorSpawnerPlayModeTests
    {
        private const string SpawnerResourcePath = "Spawners/DoorSpawner";

        private const float WallThickness = 0.5f;
        private const float WallHeight = 2f;
        private const float DoorOpeningWidth = 3f;
        private const float RoomMinX = -10f;
        private const float RoomMaxX = 10f;
        private const float ApproachMinZ = -10f;
        private const float DoorZ = 0f;
        private const float ForwardMaxZ = 10f;

        private static readonly Vector3 ApproachSamplePoint = new Vector3(0f, 0f, -8f);
        private static readonly Vector3 ForwardSamplePoint = new Vector3(0f, 0f, 8f);

        // One door per DoorId is the design's count, not the spawner's. A spawner that created
        // four, or six, must fail against a number it did not supply.
        private static int ExpectedDoorCount => System.Enum.GetValues(typeof(DoorId)).Length;

        private GameObject root;
        private GameplayNavigationSurface surfaceOwner;
        private bool baked;
        private GameObject spawnerObject;
        private DoorSpawner spawner;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("DoorSpawnerTestRoot");
            BuildFloor();
            BuildDoorwayWalls();

            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(root.transform, false);
            surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
        }

        [TearDown]
        public void TearDown()
        {
            if (baked && surfaceOwner != null) surfaceOwner.ClearBakedData();

            // Immediate, not deferred: a deferred Destroy leaves this fixture's doors in
            // DoorInteractable.ActiveDoors until the end of the frame, where the next test's
            // registry counts would see them.
            if (root != null) Object.DestroyImmediate(root);
            root = null;
            spawnerObject = null;
            spawner = null;
            baked = false;
        }

        [UnityTest]
        public IEnumerator Spawn_CreatesTheFiveDoorsAtTheEntryRoomsCentresWithTheirIdsAndNames()
        {
            BakeNavigation();
            int returned = SpawnDoors();
            yield return null;

            // THE ENTRY ROOM'S COPY OF EACH SHARED LINE, which the spawner never reads: D1 from
            // Bone Archive, D2 from Chapel of Ash, D3 from Lower Vault, D4 from the Final Room. D5
            // has no entry room; DoorPrefabTests adds the editor catalog as its witness.
            var expected = new[]
            {
                (id: DoorId.D1, name: "DoorRoot", centre: BoneArchiveLayout.D1, isFinal: false),
                (id: DoorId.D2, name: "D2", centre: ChapelOfAshLayout.D2, isFinal: false),
                (id: DoorId.D3, name: "D3", centre: LowerVaultLayout.D3, isFinal: false),
                (id: DoorId.D4, name: "D4",
                    centre: new Vector3(FinalRoomLayout.D4X, 0f, FinalRoomLayout.D4Z), isFinal: false),
                (id: DoorId.D5, name: "D5",
                    centre: new Vector3(FinalRoomLayout.D5X, 0f, FinalRoomLayout.D5Z), isFinal: true)
            };
            Assert.AreEqual(ExpectedDoorCount, expected.Length, "This fixture's own table is incomplete.");

            Assert.AreEqual(ExpectedDoorCount, returned, "Spawn() returned a different count.");
            Assert.AreEqual(ExpectedDoorCount, spawner.SpawnedCount, "SpawnedCount disagrees with the return value.");

            DoorInteractable[] doors = SpawnedDoors();
            Assert.AreEqual(ExpectedDoorCount, doors.Length, "The hierarchy holds a different number of doors.");
            Assert.AreEqual(ExpectedDoorCount, RegisteredUnder(spawnerObject.transform),
                "DoorInteractable.ActiveDoors - the registry every consumer finds doors through - "
                + "does not hold the spawned doors. OnEnable never ran, or ran on the wrong object.");

            for (int i = 0; i < expected.Length; i++)
            {
                DoorInteractable door = doors[i];
                var (id, name, centre, isFinal) = expected[i];
                Vector3 position = door.transform.position;

                Assert.AreEqual(id, door.DoorId, "Door " + i + " has the wrong DoorId.");
                Assert.AreEqual(name, door.name, id + " is named '" + door.name + "'. NSC-052 and NSC-075 "
                    + "pin DoorRoot/DoorVisual/DoorSprite in prose and six fixtures look the names up.");
                Assert.AreEqual(centre.x, position.x, 0.001f, id + " x");
                Assert.AreEqual(0f, position.y, 0.001f, id + " must stand on the ground line; y is forced to zero.");
                Assert.AreEqual(centre.z, position.z, 0.001f, id + " z");
                Assert.Less(Quaternion.Angle(door.transform.rotation, Quaternion.identity), 0.01f,
                    id + " is rotated. Every door faces +Z; the prefab's orientation is the only one.");
                Assert.AreEqual(isFinal, door.IsFinalDoor, id + " IsFinalDoor");
                Assert.AreEqual(Vector3.one, door.transform.localScale,
                    id + " root is scaled. The 1.54 art scale lives on DoorSprite, never on the root.");
            }
        }

        [UnityTest]
        public IEnumerator EveryDoorCarriesTheBuilderAnatomy()
        {
            BakeNavigation();
            SpawnDoors();
            yield return null;

            FieldInfo obstacleSizeField = typeof(DoorEnemyPassability).GetField(
                "obstacleSize", BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(obstacleSizeField, "Expected a private 'obstacleSize' field on DoorEnemyPassability.");

            foreach (DoorInteractable door in SpawnedDoors())
            {
                string who = door.name;

                // The arm's-reach range trigger: DoorPrototypeSceneBuilder.BuildDoor, the four lines
                // after `var rangeTrigger = doorRoot.AddComponent<BoxCollider>()`. Restated as
                // literals because the Editor assembly is unreachable from PlayMode.
                var rangeTrigger = door.GetComponent<BoxCollider>();
                Assert.IsNotNull(rangeTrigger, who + " has no range trigger on its root.");
                Assert.IsTrue(rangeTrigger.isTrigger, who + " range collider is solid; it must be a trigger.");
                Assert.AreEqual(new Vector3(3f, 3f, 3f), rangeTrigger.size, who + " range trigger size");
                Assert.AreEqual(new Vector3(0f, 1.5f, 0f), rangeTrigger.center, who + " range trigger centre");

                Assert.IsNotNull(door.GetComponent<NavMeshObstacle>(), who + " has no NavMeshObstacle to carve with.");
                var passability = door.GetComponent<DoorEnemyPassability>();
                Assert.IsNotNull(passability, who + " has no DoorEnemyPassability.");
                float openingWidth = ((Vector3)obstacleSizeField.GetValue(passability)).x;
                Assert.AreEqual(RuinedEntryLayout.DoorOpeningWidth, openingWidth, 0.001f,
                    who + ": the obstacle's width is not the layouts' opening width.");

                Transform visual = door.transform.Find("DoorVisual");
                Assert.IsNotNull(visual, who + " has no DoorVisual child.");
                AssertVector(new Vector3(0f, 1.25f, 0f), visual.localPosition, who + " DoorVisual localPosition");
                var blocker = visual.GetComponent<BoxCollider>();
                Assert.IsNotNull(blocker, who + " DoorVisual carries no doorway blocker.");
                Assert.IsFalse(blocker.isTrigger, who + " doorway blocker is a trigger and would stop nothing.");
                Assert.AreEqual(openingWidth, blocker.size.x, 0.001f,
                    who + ": the blocker must span the authored opening (DoorwayOpeningSealTests' rule).");
                Assert.AreEqual(2.5f, blocker.size.y, 0.001f, who + " blocker height");
                Assert.AreEqual(0.3f, blocker.size.z, 0.001f, who + " blocker depth");

                Transform sprite = visual.Find("DoorSprite");
                Assert.IsNotNull(sprite, who + " has no DoorVisual/DoorSprite.");
                AssertVector(new Vector3(0f, -1.25f, 0f), sprite.localPosition, who + " DoorSprite localPosition");
                AssertVector(new Vector3(1.54f, 1.54f, 1.54f), sprite.localScale,
                    who + " DoorSprite scale. Docs/Art/Doors/APPROVAL.md: 'x1.54', Vincent's 2026-09-17 approval.");

                var renderer = sprite.GetComponent<SpriteRenderer>();
                Assert.IsNotNull(renderer, who + " DoorSprite has no SpriteRenderer.");
                Assert.AreEqual(WorldSpriteConvention.SortingLayerName, renderer.sortingLayerName, who + " sorting layer");
                Assert.AreEqual(WorldSpriteConvention.SortingOrder, renderer.sortingOrder, who + " sorting order");
                Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint, who + " sort point");
                Assert.IsNotNull(renderer.sprite, who + " renders no sprite.");

                // THE MEASUREMENT THAT PROVES Configure RAN BEFORE OnEnable: DoorStateSpriteBinder
                // picks the closed-leaf skin from IsFinalDoor when it enables. Five sealed sprites
                // would mean identity arrived too late; five final ones would mean it never varied.
                string expectedSprite = door.IsFinalDoor ? "door_bonestone_final_S_000" : "door_bonestone_sealed_S_000";
                Assert.AreEqual(expectedSprite, renderer.sprite.name,
                    who + " renders '" + renderer.sprite.name + "'. The binder syncs to IsFinalDoor in "
                    + "OnEnable, so this is wrong only if identity was configured after activation.");

                // Awake ran exactly once: DoorInteractable creates this child itself.
                Transform[] crossings = door.transform.Cast<Transform>()
                    .Where(t => t.name == "ForwardCrossingTrigger").ToArray();
                Assert.AreEqual(1, crossings.Length, who + " has " + crossings.Length
                    + " ForwardCrossingTrigger children; Awake creates exactly one, and a prefab copy would double it.");
                Transform crossing = crossings[0];
                AssertVector(new Vector3(0f, 0f, 1.75f), crossing.localPosition, who + " crossing trigger offset");
                var crossingBox = crossing.GetComponent<BoxCollider>();
                Assert.IsNotNull(crossingBox, who + " crossing trigger has no collider.");
                Assert.IsTrue(crossingBox.isTrigger, who + " crossing collider must be a trigger.");
                AssertVector(new Vector3(3f, 3f, 1f), crossingBox.size, who + " crossing trigger size");

                // VAL-001's clearance rule as a RELATION between the parts that actually exist:
                // nearFace >= blockerForwardFace + 2 * playerRadius (DoorInteractable's own comment).
                // The radius 0.5 is DoorPrototypeGlobalSceneBuilder.cs:263, restated as a literal.
                const float playerRadius = 0.5f;
                float nearFace = crossing.localPosition.z - crossingBox.size.z * 0.5f;
                float blockerForwardFace = visual.localPosition.z + blocker.size.z * 0.5f;
                Assert.GreaterOrEqual(nearFace, blockerForwardFace + 2f * playerRadius,
                    who + ": the crossing volume's near face (" + nearFace + ") does not clear the blocker "
                    + "face plus a capsule (" + (blockerForwardFace + 2f * playerRadius) + ").");

                // The cracks start hidden. This is also the check on component activation order:
                // DoorBreachFeedback.OnEnable reads CurrentDurability, which DoorInteractable.Awake
                // sets - if the child enabled before the root woke, stage 3 would show on a sealed door.
                for (int stage = 1; stage <= 3; stage++)
                {
                    Transform crack = sprite.Find("CrackStage" + stage);
                    Assert.IsNotNull(crack, who + " has no CrackStage" + stage + " under DoorSprite.");
                    Assert.IsFalse(crack.gameObject.activeSelf, who + " CrackStage" + stage
                        + " is visible on a sealed door.");
                    Assert.AreEqual(0, crack.GetComponentsInChildren<Collider>(true).Length,
                        who + " CrackStage" + stage + " carries a collider (NSC-052: none on the shake target's descendants).");
                }
            }
        }

        [UnityTest]
        public IEnumerator SealedDoorsCarveTheNavMeshAndBlockRays_OpenedDoorsDoNeither()
        {
            BakeNavigation();

            // CONTROL, sampled before any door exists: the baked surface crosses the doorway line,
            // so a blocked path below is the door's doing and not the bake's.
            Assert.IsTrue(NavMesh.SamplePosition(ApproachSamplePoint, out NavMeshHit start, 2f, NavMesh.AllAreas),
                "Expected a walkable NavMesh point on the approach side of the test doorway.");
            Assert.IsTrue(NavMesh.SamplePosition(ForwardSamplePoint, out NavMeshHit end, 2f, NavMesh.AllAreas),
                "Expected a walkable NavMesh point on the forward side of the test doorway.");
            Assert.AreEqual(NavMeshPathStatus.PathComplete, PathBetween(start.position, end.position).status,
                "Control failed: with no door, the doorway must already be walkable.");

            SpawnDoors();
            yield return SettleCarving();

            DoorInteractable d1 = FindDoor("DoorRoot");

            // SEALED: the obstacle carves (DoorEnemyPassability's contract) and the blocker stops a
            // chest-height ray fired the way FireballProjectile fires, triggers ignored.
            Assert.AreNotEqual(NavMeshPathStatus.PathComplete, PathBetween(start.position, end.position).status,
                "A sealed D1 did not carve the doorway: enemies could path straight through it.");
            Physics.SyncTransforms();
            Assert.IsTrue(Physics.Raycast(new Vector3(0f, 1f, -1f), Vector3.forward, out RaycastHit hit, 2f,
                    Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore),
                "A ray through a sealed D1 hit nothing; the doorway blocker is missing or a trigger.");
            Assert.IsTrue(hit.collider.transform.IsChildOf(d1.transform),
                "The ray was stopped by '" + hit.collider.name + "', which is not part of DoorRoot.");

            // OPENED through the door's own public entry points, as a player would.
            d1.StartInteraction();
            d1.Tick(d1.Duration + 0.1f);
            Assert.IsTrue(d1.IsOpen, "Setup: D1 must be open after its full duration.");
            yield return SettleCarving();
            Physics.SyncTransforms();

            Assert.AreEqual(NavMeshPathStatus.PathComplete, PathBetween(start.position, end.position).status,
                "An open D1 still blocks the doorway. Either the obstacle kept carving or the bake had a "
                + "hole under the door (see ADoorSpawnedBeforeNavigationLeavesAPermanentHole).");
            Assert.IsFalse(Physics.Raycast(new Vector3(0f, 1f, -1f), Vector3.forward, 2f,
                    Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore),
                "The same ray still hits something through an open D1.");
        }

        [UnityTest]
        public IEnumerator SpawningTwiceLeavesExactlyFiveDoorsRegistered()
        {
            BakeNavigation();
            int first = SpawnDoors();
            yield return null;
            int second = spawner.Spawn();
            yield return null;

            Assert.AreEqual(ExpectedDoorCount, first, "First Spawn() count");
            Assert.AreEqual(ExpectedDoorCount, second, "Second Spawn() count");
            Assert.AreEqual(ExpectedDoorCount, spawner.SpawnedCount, "SpawnedCount after the second run");
            Assert.AreEqual(ExpectedDoorCount, SpawnedDoors().Length, "DoorInteractable count after two runs");

            // THE REGISTRY IS THE INDEPENDENT OBSERVER: OnEnable and OnDisable maintain it, not the
            // spawner. A door the spawner destroyed but that never left the registry shows up here
            // as a null entry; a door it forgot to destroy shows up as a sixth live one.
            Assert.AreEqual(ExpectedDoorCount, RegisteredUnder(spawnerObject.transform),
                "The registry holds a different number of this spawner's doors after two Spawn() calls.");
            Assert.IsFalse(DoorInteractable.ActiveDoors.Any(door => door == null),
                "A destroyed door is still registered in DoorInteractable.ActiveDoors.");

            Assert.AreEqual(ExpectedDoorCount, spawnerObject.GetComponentsInChildren<Transform>(true)
                    .Count(t => t.name == "ForwardCrossingTrigger"),
                "ForwardCrossingTrigger count after two runs (Awake ran on the wrong number of doors).");
            Assert.AreEqual(ExpectedDoorCount, spawnerObject.GetComponentsInChildren<NavMeshObstacle>(true).Length,
                "NavMeshObstacle count after two runs.");
        }

        // THE WRONG ORDER, ON PURPOSE. This is the only test that says WHY Navigation runs before
        // Doors: a door standing in the opening at bake time is baked AROUND, and the hole it
        // leaves survives the door opening. The legacy builder measured exactly this at D1 ("no
        // walkable surface at the doorway centre, nearest 0.67 units away") and had to suppress
        // every door collider around its bake; the phase order makes that hack unnecessary.
        [UnityTest]
        public IEnumerator ADoorSpawnedBeforeNavigationLeavesAPermanentHole()
        {
            SpawnDoors();
            yield return null;

            BakeNavigation();

            // Open D1 so neither its carving obstacle nor its blocker can be what is missing.
            DoorInteractable d1 = FindDoor("DoorRoot");
            d1.StartInteraction();
            d1.Tick(d1.Duration + 0.1f);
            Assert.IsTrue(d1.IsOpen, "Setup: D1 must be open.");
            yield return SettleCarving();

            Assert.IsFalse(NavMesh.SamplePosition(d1.transform.position, out _, 0.5f, NavMesh.AllAreas),
                "A door baked into the navmesh left NO permanent hole. That would be good news, and it "
                + "would mean the Navigation-before-Doors ordering no longer carries the reason recorded "
                + "here; measure before removing either.");
        }

        private void BakeNavigation()
        {
            surfaceOwner.ConfigureAndBuild();
            baked = true;
        }

        private int SpawnDoors()
        {
            // THE SHIPPED PREFABS, loaded the way GameBootstrap loads them, so the serialized
            // doorPrefab reference and the prefab's saved state are what is under test.
            var prefab = Resources.Load<GameObject>(SpawnerResourcePath);
            Assert.IsNotNull(prefab, "Resources/" + SpawnerResourcePath + ".prefab did not load.");

            spawnerObject = Object.Instantiate(prefab, root.transform);
            spawnerObject.name = prefab.name;
            spawner = spawnerObject.GetComponent<DoorSpawner>();
            Assert.IsNotNull(spawner, "The spawner prefab carries no DoorSpawner.");
            Assert.AreEqual(-1, spawner.SpawnedCount, "The spawner prefab spawned on its own before Spawn() was called.");

            return spawner.Spawn();
        }

        private DoorInteractable[] SpawnedDoors()
        {
            return spawnerObject.GetComponentsInChildren<DoorInteractable>(true)
                .OrderBy(door => door.DoorId)
                .ToArray();
        }

        private DoorInteractable FindDoor(string objectName)
        {
            DoorInteractable door = SpawnedDoors().SingleOrDefault(candidate => candidate.name == objectName);
            Assert.IsNotNull(door, "No spawned door named '" + objectName + "'.");
            return door;
        }

        private static int RegisteredUnder(Transform parent)
        {
            return DoorInteractable.ActiveDoors.Count(door => door != null && door.transform.IsChildOf(parent));
        }

        // NavMeshObstacle carving is applied by Unity's navigation update, not synchronously, so a
        // freshly toggled carve needs a few fixed steps before a path request is meaningful
        // (DoorEnemyPassabilityPlayModeTests.SetStateAndSettle).
        private static IEnumerator SettleCarving()
        {
            for (int i = 0; i < 10; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static NavMeshPath PathBetween(Vector3 from, Vector3 to)
        {
            var path = new NavMeshPath();
            NavMesh.CalculatePath(from, to, NavMesh.AllAreas, path);
            return path;
        }

        private static void AssertVector(Vector3 expected, Vector3 actual, string what)
        {
            Assert.AreEqual(expected.x, actual.x, 0.0001f, what + " x");
            Assert.AreEqual(expected.y, actual.y, 0.0001f, what + " y");
            Assert.AreEqual(expected.z, actual.z, 0.0001f, what + " z");
        }

        private void BuildFloor()
        {
            var floor = new GameObject("TestFloorCollision");
            floor.transform.SetParent(root.transform, false);
            floor.transform.position = new Vector3(0f, -0.05f, (ApproachMinZ + ForwardMaxZ) * 0.5f);
            var collider = floor.AddComponent<BoxCollider>();
            collider.size = new Vector3(RoomMaxX - RoomMinX, 0.1f, ForwardMaxZ - ApproachMinZ);
        }

        private void BuildDoorwayWalls()
        {
            var centerY = WallHeight * 0.5f;
            var roomWidth = RoomMaxX - RoomMinX;
            var segmentWidth = (roomWidth - DoorOpeningWidth) * 0.5f;
            var segmentOffset = (DoorOpeningWidth + segmentWidth) * 0.5f;

            CreateWall("TestDoorWallWest", new Vector3(-segmentOffset, centerY, DoorZ),
                new Vector3(segmentWidth, WallHeight, WallThickness));
            CreateWall("TestDoorWallEast", new Vector3(segmentOffset, centerY, DoorZ),
                new Vector3(segmentWidth, WallHeight, WallThickness));
        }

        private void CreateWall(string name, Vector3 position, Vector3 size)
        {
            var wall = new GameObject(name);
            wall.transform.SetParent(root.transform, false);
            wall.transform.position = position;
            var collider = wall.AddComponent<BoxCollider>();
            collider.size = size;
        }
    }

    // THE PLAYER ARRIVES AFTER THE DOORS. Under GameBootstrap the Doors phase runs before the
    // Player phase inside one synchronous BuildWorld, so every door's DoorInteractionFeedback wakes
    // with no PlayerMovement to find. This fixture spawns the doors, THEN builds a player exactly
    // as DoorInteractionFeedbackHoverPlayModeTests builds its own (real camera, real InputSystem,
    // input asset set by reflection - PlayerMovement's pointer target has no other seam), and
    // requires hover on D1. Fails at 3fbac01c4 (playerMovement stays null, IsHovered false) and
    // passes with DoorInteractionFeedback's lazy resolve.
    public sealed class DoorSpawnerFeedbackPlayModeTests : InputTestFixture
    {
        private const string SpawnerResourcePath = "Spawners/DoorSpawner";

        private Mouse mouseDevice;
        private GameObject cameraObject;
        private Camera testCamera;
        private RenderTexture testRenderTexture;
        private InputActionAsset inputActionsAsset;
        private GameObject root;
        private GameObject playerObject;
        private PlayerMovement movement;

        public override void Setup()
        {
            base.Setup();
            mouseDevice = InputSystem.AddDevice<Mouse>();

            cameraObject = new GameObject("TestMainCamera");
            cameraObject.tag = "MainCamera";
            testCamera = cameraObject.AddComponent<Camera>();
            testCamera.orthographic = true;
            testCamera.orthographicSize = 10f;
            cameraObject.transform.SetPositionAndRotation(new Vector3(0f, 10f, 0f), Quaternion.Euler(90f, 0f, 0f));

            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
            testCamera.targetTexture = testRenderTexture;

            root = new GameObject("DoorSpawnerFeedbackTestRoot");
        }

        public override void TearDown()
        {
            if (playerObject != null) Object.DestroyImmediate(playerObject);
            if (root != null) Object.DestroyImmediate(root);
            if (cameraObject != null) Object.DestroyImmediate(cameraObject);
            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                Object.Destroy(testRenderTexture);
                testRenderTexture = null;
            }
            if (inputActionsAsset != null) Object.Destroy(inputActionsAsset);

            mouseDevice = null;
            base.TearDown();
        }

        [UnityTest]
        public IEnumerator DoorFeedbackFindsAPlayerThatArrivesAfterTheDoors()
        {
            // Phase Doors: no player exists, so the Awake-time lookup returns null on every door.
            Assert.IsNull(Object.FindFirstObjectByType<PlayerMovement>(),
                "Precondition: a PlayerMovement already exists, so this fixture would not be testing the late arrival.");
            var prefab = Resources.Load<GameObject>(SpawnerResourcePath);
            Assert.IsNotNull(prefab, "Resources/" + SpawnerResourcePath + ".prefab did not load.");
            GameObject spawnerObject = Object.Instantiate(prefab, root.transform);
            var spawner = spawnerObject.GetComponent<DoorSpawner>();
            Assert.AreEqual(System.Enum.GetValues(typeof(DoorId)).Length, spawner.Spawn(), "Spawn() count");
            yield return null;

            // Phase Player, one frame later, the way the hover fixture builds it (:280-288).
            playerObject = new GameObject("TestPlayer");
            playerObject.SetActive(false);
            playerObject.transform.position = new Vector3(5f, 1f, 5f);
            playerObject.AddComponent<CharacterController>();
            playerObject.AddComponent<PlayerHealth>();
            playerObject.AddComponent<PlayerInteractionController>();
            movement = playerObject.AddComponent<PlayerMovement>();
            inputActionsAsset = BuildInputActionsAsset();
            SetPrivateField(movement, "inputActions", inputActionsAsset);
            playerObject.SetActive(true);
            yield return null;

            DoorInteractable d1 = spawnerObject.GetComponentsInChildren<DoorInteractable>()
                .Single(door => door.DoorId == DoorId.D1);
            var feedback = d1.GetComponent<DoorInteractionFeedback>();
            Assert.IsNotNull(feedback, "D1 carries no DoorInteractionFeedback.");

            SetMouse(testCamera.WorldToScreenPoint(d1.SelectionPoint), false);
            movement.Tick(0.02f);
            Assert.IsTrue(movement.HasPointerWorldTarget,
                "Setup must produce a shared pointer world target through the real camera projection.");
            Assert.IsTrue(d1.TryGetSelectionDistance(movement.PointerWorldTarget, out _),
                "Setup: the pointer target must fall inside D1's own selection area.");

            feedback.Tick(0.02f);

            Assert.IsTrue(feedback.IsHovered,
                "D1 shows no hover with the pointer over its selection point. The feedback never found "
                + "the player that arrived after the doors did (DoorInteractionFeedback resolves the "
                + "player at Awake only), so no spawned door would ever highlight.");
            Assert.IsFalse(feedback.IsSelected, "Nothing selected the door; hover must not read as selection.");
        }

        private static InputActionAsset BuildInputActionsAsset()
        {
            var asset = ScriptableObject.CreateInstance<InputActionAsset>();
            var playerMap = asset.AddActionMap("Player");
            playerMap.AddAction("PointerPosition", InputActionType.Value, binding: "<Mouse>/position");
            playerMap.AddAction("MoveToCursor", InputActionType.Button, binding: "<Mouse>/leftButton");
            return asset;
        }

        private void SetMouse(Vector2 screenPosition, bool leftButtonPressed)
        {
            InputSystem.QueueStateEvent(mouseDevice, new MouseState
            {
                position = screenPosition,
                buttons = leftButtonPressed ? (ushort)(1 << (int)MouseButton.Left) : (ushort)0
            });
            InputSystem.Update();
        }

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            FieldInfo field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, "Expected a private field named '" + fieldName + "' on " + target.GetType().Name + ".");
            field.SetValue(target, value);
        }
    }
}
