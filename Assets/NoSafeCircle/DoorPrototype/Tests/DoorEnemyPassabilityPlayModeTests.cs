using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.TestTools;
using NoSafeCircle.DoorPrototype.World;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-090 VAL-001: proves DoorEnemyPassability actually blocks or permits enemy NavMesh
    // traversal through a doorway for each of the four semantic door states. Every object here -
    // floor, doorway walls, GameplayNavigationSurface (NSC-089), the door, and the NavMeshAgent -
    // is created and destroyed by this fixture. Nothing here opens, saves, or otherwise touches
    // the committed Assets/Scenes/DoorPrototype.unity scene.
    public sealed class DoorEnemyPassabilityPlayModeTests
    {
        // Mirrors the production doorway wall convention (see RuinedEntrySceneBuilder): two
        // boundary wall segments separated by a door-opening gap, on top of one continuous floor.
        // This forces the agent to actually route through the doorway gap the owned obstacle
        // carves across, rather than walking around an obstacle placed in an otherwise open floor.
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

        private GameObject root;
        private GameplayNavigationSurface surfaceOwner;
        private DoorEnemyPassability passability;
        private NavMeshAgent agent;
        private Vector3 forwardTarget;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("DoorEnemyPassabilityTestRoot");

            BuildFloor();
            BuildDoorwayWalls();

            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(root.transform, false);
            surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surfaceOwner.ConfigureAndBuild();

            // Sampled before the door/obstacle exists, so both points reflect the open baseline
            // doorway that GameplayNavigationSurface baked from the floor-and-wall geometry above.
            Assert.IsTrue(NavMesh.SamplePosition(ApproachSamplePoint, out var startHit, 2f, NavMesh.AllAreas),
                "Expected a walkable NavMesh point on the approach side of the test doorway.");
            Assert.IsTrue(NavMesh.SamplePosition(ForwardSamplePoint, out var forwardHit, 2f, NavMesh.AllAreas),
                "Expected a walkable NavMesh point on the forward side of the test doorway.");
            forwardTarget = forwardHit.position;

            var doorObject = new GameObject("TestDoorEnemyPassability");
            doorObject.transform.SetParent(root.transform, false);
            doorObject.transform.position = new Vector3(0f, 0f, DoorZ);
            passability = doorObject.AddComponent<DoorEnemyPassability>();

            var agentObject = new GameObject("TestNavMeshAgent");
            agentObject.transform.SetParent(root.transform, false);
            agentObject.transform.position = startHit.position;
            var settings = NavMesh.GetSettingsByIndex(0);
            agent = agentObject.AddComponent<NavMeshAgent>();
            agent.agentTypeID = settings.agentTypeID;
            agent.radius = settings.agentRadius;
            agent.height = settings.agentHeight;
            agent.Warp(startHit.position);
        }

        [TearDown]
        public void TearDown()
        {
            if (surfaceOwner != null) surfaceOwner.ClearBakedData();
            if (root != null) Object.Destroy(root);
        }

        [UnityTest]
        public IEnumerator SetDoorState_Sealed_BlocksCompletePath()
        {
            yield return SetStateAndSettle(DoorPassabilityState.Sealed);

            AssertPathBlocked();
        }

        [UnityTest]
        public IEnumerator SetDoorState_Locked_BlocksCompletePath()
        {
            yield return SetStateAndSettle(DoorPassabilityState.Locked);

            AssertPathBlocked();
        }

        [UnityTest]
        public IEnumerator SetDoorState_Open_AllowsCompletePath()
        {
            yield return SetStateAndSettle(DoorPassabilityState.Open);

            AssertPathComplete();
        }

        [UnityTest]
        public IEnumerator SetDoorState_Broken_AllowsCompletePath()
        {
            yield return SetStateAndSettle(DoorPassabilityState.Broken);

            AssertPathComplete();
        }

        // VAL-001: exercises all four states on one fixture in a mixed order so the owned
        // obstacle also proves it can transition back and forth, not just apply a single state
        // once from a freshly configured default.
        [UnityTest]
        public IEnumerator SetDoorState_AcrossAllFourStatesInSequence_MatchesEachExpectedPassability()
        {
            yield return SetStateAndSettle(DoorPassabilityState.Sealed);
            AssertPathBlocked();

            yield return SetStateAndSettle(DoorPassabilityState.Open);
            AssertPathComplete();

            yield return SetStateAndSettle(DoorPassabilityState.Locked);
            AssertPathBlocked();

            yield return SetStateAndSettle(DoorPassabilityState.Broken);
            AssertPathComplete();
        }

        // AC-001/AC-002: publishes the requested semantic state through the component's only
        // public entry point, then waits a bounded number of fixed updates. NavMeshObstacle
        // carving is applied by Unity's internal navigation update rather than synchronously
        // inside SetDoorState, so a freshly toggled carve needs a few fixed steps to settle
        // before a path request against it is meaningful.
        private IEnumerator SetStateAndSettle(DoorPassabilityState state)
        {
            passability.SetDoorState(state);

            const int settleSteps = 10;
            for (var i = 0; i < settleSteps; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private void AssertPathBlocked()
        {
            var path = new NavMeshPath();
            agent.CalculatePath(forwardTarget, path);

            Assert.AreNotEqual(NavMeshPathStatus.PathComplete, path.status,
                $"DoorEnemyPassability.CurrentState={passability.CurrentState}: expected the doorway obstacle " +
                "to prevent a complete path from the approach side to the forward side.");
        }

        private void AssertPathComplete()
        {
            var path = new NavMeshPath();
            var foundPath = agent.CalculatePath(forwardTarget, path);

            Assert.IsTrue(foundPath,
                $"DoorEnemyPassability.CurrentState={passability.CurrentState}: expected a path to be found " +
                "from the approach side to the forward side.");
            Assert.AreEqual(NavMeshPathStatus.PathComplete, path.status,
                $"DoorEnemyPassability.CurrentState={passability.CurrentState}: expected a complete path from " +
                "the approach side through the open doorway to the forward side.");
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
}
