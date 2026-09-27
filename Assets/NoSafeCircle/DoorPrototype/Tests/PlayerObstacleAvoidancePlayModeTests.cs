using System.Collections;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Vincent's defect, verbatim: "The path finding for the player doesnt consider the room
    // obstacles and walk around". Confirms the precondition the brief for this fix asked to be
    // checked first: that the 41 prop BoxColliders just reshaped from full-sprite-height square
    // prisms to base-height boxes with real depth (e02d54e9d, already an ancestor of this
    // checkout's base) still let GameplayNavigationSurface carve a real detour around a prop,
    // rather than only around a synthetic test cube. Uses the ACTUAL reshaped collider on
    // ca_landmark_cracked_bell_frame_x (BoxCollider size 2.031 x 1.306 x 0.772, base-height per
    // the reshape), not a stand-in shape.
    //
    // Every object here - floor, prop, navigation - is created and destroyed by this fixture.
    // Nothing here opens, saves, or otherwise touches the committed
    // Assets/Scenes/DoorPrototype.unity scene, matching the convention already set by
    // EnemyPursuitPlayModeTests and the other GameplayNavigationSurface-baking fixtures.
    public sealed class PlayerPathAroundRealPropSanityCheckPlayModeTests
    {
        private const string PropResourcePath = "Props/ca_landmark_cracked_bell_frame_x";
        private const float FloorSize = 24f;

        private static readonly Vector3 StartPoint = new Vector3(-3f, 0f, 0f);
        private static readonly Vector3 TargetPoint = new Vector3(3f, 0f, 0f);

        private GameObject root;
        private GameplayNavigationSurface surfaceOwner;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("PlayerPathAroundRealPropSanityCheckTestRoot");
            BuildOpenFloor();

            var prefab = Resources.Load<GameObject>(PropResourcePath);
            Assert.IsNotNull(prefab, "Expected a prefab at Resources/" + PropResourcePath +
                " - if this prop was renamed or removed, swap in another reshaped prop from " +
                "e02d54e9d rather than deleting this check.");
            var prop = Object.Instantiate(prefab, Vector3.zero, Quaternion.identity, root.transform);
            prop.name = "TestProp";

            var propCollider = prop.GetComponentInChildren<BoxCollider>();
            Assert.IsNotNull(propCollider, "Expected the reshaped prop to still carry a BoxCollider.");

            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(root.transform, false);
            surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surfaceOwner.ConfigureAndBuild();
        }

        [TearDown]
        public void TearDown()
        {
            if (surfaceOwner != null) surfaceOwner.ClearBakedData();
            if (root != null) Object.Destroy(root);
        }

        [UnityTest]
        public IEnumerator BakedNavMesh_HasACompletePathAroundTheRealProp_WithMoreThanTwoCorners()
        {
            yield return null;

            Assert.IsTrue(NavMesh.SamplePosition(StartPoint, out var startHit, 2f, NavMesh.AllAreas),
                "Expected the start point to sample onto the baked floor.");
            Assert.IsTrue(NavMesh.SamplePosition(TargetPoint, out var endHit, 2f, NavMesh.AllAreas),
                "Expected the target point to sample onto the baked floor.");

            var path = new NavMeshPath();
            var found = NavMesh.CalculatePath(startHit.position, endHit.position, NavMesh.AllAreas, path);

            Assert.IsTrue(found, "Expected NavMesh.CalculatePath to succeed around the reshaped prop.");
            Assert.AreEqual(NavMeshPathStatus.PathComplete, path.status,
                "Expected a complete path around the prop, not merely a partial one - if this is " +
                "PathPartial or the call fails, the collider reshape broke carving and that is a " +
                "more important finding than this feature.");
            Assert.Greater(path.corners.Length, 2,
                "A straight, unobstructed line is exactly two corners (start, end); a real detour " +
                "around the prop needs at least one intermediate corner.");
        }

        private void BuildOpenFloor()
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.name = "TestGameplayFloor";
            floor.transform.SetParent(root.transform, false);
            floor.transform.position = Vector3.zero;
            floor.transform.localScale = new Vector3(FloorSize, 0.1f, FloorSize);
        }
    }

    // THE FAILING-BEFORE TEST FOR VINCENT'S DEFECT. On unmodified PlayerMovement (straight-line
    // CharacterController steering with no NavMesh awareness at all - PlayerMovement.cs contains
    // the string "NavMesh" zero times) this FAILS: the wizard walks dead-on into the obstacle,
    // makes zero forward progress, and BlockedDestinationTimeout (0.2s) cancels the destination
    // without ever arriving. After the fix, PlayerMovement follows the baked NavMesh path around
    // the obstacle and arrives.
    //
    // Uses a synthetic obstacle rather than the real prop above so the assertions describe a
    // durable relation (arrival + a path that actually left the direct line) instead of a
    // hardcoded coordinate tied to one prop's footprint. Drives movement through
    // PlayerMovement.RequestDestination - the same owner-controlled entry point
    // Door/Interaction (NSC-019) uses - rather than simulated mouse/camera input, so this stays
    // scoped to the pathfinding/steering defect and does not re-exercise the click/input plumbing
    // PlayerMovementPlayModeTests already covers.
    //
    // Every object here - floor, obstacle, navigation, wizard - is created and destroyed by this
    // fixture. Nothing here opens, saves, or otherwise touches the committed
    // Assets/Scenes/DoorPrototype.unity scene.
    public sealed class PlayerObstacleAvoidancePlayModeTests
    {
        private const float FloorSize = 24f;
        private const float ArrivalCheckTolerance = 0.2f;
        private const float SimulationStep = 0.05f;
        private const float SimulationTimeoutSeconds = 12f;

        private static readonly Vector3 StartPoint = new Vector3(-5f, 0f, 0f);
        private static readonly Vector3 TargetPoint = new Vector3(5f, 0f, 0f);

        // Spans the direct line from StartPoint to TargetPoint (both at Z=0) but leaves open
        // floor to either side (room floor is 24 wide) so a route around exists. The obstacle's
        // wide face is perpendicular to the direct line of travel, so the old straight-line
        // steering hits it dead-on and makes zero lateral progress on its own - this is what
        // makes the failing-before result deterministic rather than an accidental slide-around.
        private static readonly Vector3 ObstacleCenter = Vector3.zero;
        private static readonly Vector3 ObstacleSize = new Vector3(4f, 2f, 1.5f);

        private GameObject root;
        private GameplayNavigationSurface surfaceOwner;
        private GameObject playerObject;
        private PlayerMovement movement;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("PlayerObstacleAvoidanceTestRoot");
            BuildOpenFloor();
            BuildObstacle();

            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(root.transform, false);
            surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surfaceOwner.ConfigureAndBuild();

            playerObject = new GameObject("TestPlayer");
            playerObject.transform.SetParent(root.transform, false);
            playerObject.transform.position = StartPoint;
            playerObject.AddComponent<CharacterController>();
            movement = playerObject.AddComponent<PlayerMovement>();
        }

        [TearDown]
        public void TearDown()
        {
            if (surfaceOwner != null) surfaceOwner.ClearBakedData();
            if (root != null) Object.Destroy(root);
        }

        [UnityTest]
        public IEnumerator ClickBeyondObstacle_WalksAroundIt_AndArrives()
        {
            yield return null;

            movement.RequestDestination(TargetPoint);
            Assert.IsTrue(movement.HasActiveDestination,
                "Test setup must actually issue a destination request before simulating movement.");

            var maxLateralDeviation = 0f;
            var elapsed = 0f;
            while (elapsed < SimulationTimeoutSeconds && movement.HasActiveDestination)
            {
                movement.Tick(SimulationStep);
                elapsed += SimulationStep;

                // The direct line from StartPoint to TargetPoint runs along Z=0; a genuine detour
                // around the obstacle must leave that line by more than the obstacle's own
                // half-depth at some point along the way.
                var lateralOffset = Mathf.Abs(playerObject.transform.position.z);
                if (lateralOffset > maxLateralDeviation) maxLateralDeviation = lateralOffset;
            }

            var finalOffset = HorizontalDistance(playerObject.transform.position, TargetPoint);
            Assert.Less(finalOffset, ArrivalCheckTolerance,
                "Expected the wizard to arrive at the clicked destination on the far side of the " +
                "obstacle by routing around it, instead of stalling against it. Final position " +
                playerObject.transform.position + " after " + elapsed +
                "s, max lateral deviation from the direct line " + maxLateralDeviation + ".");
            Assert.Greater(maxLateralDeviation, ObstacleSize.z * 0.5f,
                "Expected the wizard's path to actually deviate around the obstacle (a straight " +
                "line never leaves Z=0), not merely end up near the target by some other means.");
        }

        private void BuildOpenFloor()
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.name = "TestGameplayFloor";
            floor.transform.SetParent(root.transform, false);
            floor.transform.position = Vector3.zero;
            floor.transform.localScale = new Vector3(FloorSize, 0.1f, FloorSize);
        }

        private void BuildObstacle()
        {
            var obstacle = GameObject.CreatePrimitive(PrimitiveType.Cube);
            obstacle.name = "TestObstacle";
            obstacle.transform.SetParent(root.transform, false);
            obstacle.transform.position = ObstacleCenter + new Vector3(0f, ObstacleSize.y * 0.5f, 0f);
            obstacle.transform.localScale = ObstacleSize;
        }

        private static float HorizontalDistance(Vector3 a, Vector3 b)
        {
            var offset = a - b;
            offset.y = 0f;
            return offset.magnitude;
        }
    }
}
