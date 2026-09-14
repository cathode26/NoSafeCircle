using System.Collections;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-092 VAL-002 / AC-005: proves that a pursuing or searching enemy driven by the
    // production EnemyPursuitMovement/EnemyTargetKnowledge pair continues following the wizard
    // (or its recorded last known position) through a doorway that NSC-090's
    // DoorEnemyPassability reports as traversable (open or broken), without EnemyTargetKnowledge
    // clearing the target solely because of the crossing. Mirrors the doorway-wall convention
    // from DoorEnemyPassabilityPlayModeTests. Every object here - floor, doorway walls,
    // GameplayNavigationSurface (NSC-089), the door, the wizard, and the enemy - is created and
    // destroyed by this fixture. Nothing here opens, saves, or otherwise touches the committed
    // Assets/Scenes/DoorPrototype.unity scene.
    public sealed class EnemyPursuitDoorCrossingPlayModeTests
    {
        private const float WallThickness = 0.5f;
        private const float WallHeight = 2f;
        private const float DoorOpeningWidth = 3f;
        private const float RoomMinX = -10f;
        private const float RoomMaxX = 10f;
        private const float ApproachMinZ = -10f;
        private const float DoorZ = 0f;
        private const float ForwardMaxZ = 10f;

        private const float DetectionDistance = 20f;
        private const float LoseTargetDistance = 25f;

        private static readonly Vector3 ApproachSamplePoint = new Vector3(0f, 0f, -8f);
        private static readonly Vector3 ForwardSamplePoint = new Vector3(0f, 0f, 8f);

        private GameObject root;
        private GameplayNavigationSurface surfaceOwner;
        private DoorEnemyPassability passability;
        private GameObject wizardObject;
        private Transform wizardTransform;
        private GameObject enemyObject;
        private NavMeshAgent agent;
        private EnemyTargetKnowledge targetKnowledge;
        private EnemyPursuitMovement pursuitMovement;
        private Vector3 approachStartPosition;
        private Vector3 forwardTarget;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("EnemyPursuitDoorCrossingTestRoot");

            BuildFloor();
            BuildDoorwayWalls();

            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(root.transform, false);
            surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surfaceOwner.ConfigureAndBuild();

            Assert.IsTrue(NavMesh.SamplePosition(ApproachSamplePoint, out var startHit, 2f, NavMesh.AllAreas),
                "Expected a walkable NavMesh point on the approach side of the test doorway.");
            Assert.IsTrue(NavMesh.SamplePosition(ForwardSamplePoint, out var forwardHit, 2f, NavMesh.AllAreas),
                "Expected a walkable NavMesh point on the forward side of the test doorway.");
            approachStartPosition = startHit.position;
            forwardTarget = forwardHit.position;

            var doorObject = new GameObject("TestDoorEnemyPassability");
            doorObject.transform.SetParent(root.transform, false);
            doorObject.transform.position = new Vector3(0f, 0f, DoorZ);
            passability = doorObject.AddComponent<DoorEnemyPassability>();

            wizardObject = new GameObject("TestWizard");
            wizardObject.transform.SetParent(root.transform, false);
            wizardTransform = wizardObject.transform;

            enemyObject = new GameObject("TestEnemy");
            enemyObject.transform.SetParent(root.transform, false);
            enemyObject.transform.position = approachStartPosition;

            var settings = NavMesh.GetSettingsByIndex(0);
            agent = enemyObject.AddComponent<NavMeshAgent>();
            agent.agentTypeID = settings.agentTypeID;
            agent.radius = settings.agentRadius;
            agent.height = settings.agentHeight;
            agent.Warp(approachStartPosition);

            targetKnowledge = enemyObject.AddComponent<EnemyTargetKnowledge>();
            targetKnowledge.Initialize(wizardTransform);
            targetKnowledge.ConfigureDistances(DetectionDistance, LoseTargetDistance);

            pursuitMovement = enemyObject.AddComponent<EnemyPursuitMovement>();
        }

        [TearDown]
        public void TearDown()
        {
            if (surfaceOwner != null) surfaceOwner.ClearBakedData();
            if (root != null) Object.Destroy(root);
        }

        // AC-005, VAL-002: an enemy actively pursuing the wizard on the approach side continues
        // following it through an open doorway, without EnemyTargetKnowledge losing the target
        // at any point solely because of the crossing.
        [UnityTest]
        public IEnumerator SetDoorState_Open_PursuingEnemyCrossesDoorway_WithoutLosingTarget()
        {
            yield return SetDoorStateAndSettle(DoorPassabilityState.Open);

            wizardTransform.position = forwardTarget;
            pursuitMovement.Tick(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));

            yield return WaitUntilCrossedOrTimeout();

            Assert.That(targetKnowledge.HasTarget, Is.True,
                "Expected the pursuing enemy to retain its target after crossing the open doorway.");
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
        }

        // AC-005, VAL-002: the same pursuit-through-doorway behavior holds once the door has
        // broken (also permits forward enemy traversal per the door/pursuit rules), matching the
        // GDD's "open or broken" passability requirement.
        [UnityTest]
        public IEnumerator SetDoorState_Broken_PursuingEnemyCrossesDoorway_WithoutLosingTarget()
        {
            yield return SetDoorStateAndSettle(DoorPassabilityState.Broken);

            wizardTransform.position = forwardTarget;
            pursuitMovement.Tick(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));

            yield return WaitUntilCrossedOrTimeout();

            Assert.That(targetKnowledge.HasTarget, Is.True,
                "Expected the pursuing enemy to retain its target after crossing the broken doorway.");
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
        }

        // AC-005, VAL-002: an enemy searching a last known position beyond an open doorway also
        // continues through the doorway toward that recorded position, without the crossing
        // itself clearing target/search state.
        [UnityTest]
        public IEnumerator SetDoorState_Open_SearchingEnemyCrossesDoorwayTowardLastKnownPosition_WithoutLosingTarget()
        {
            yield return SetDoorStateAndSettle(DoorPassabilityState.Open);

            // A smaller Lose Target Distance than the shared fixture default lets a reachable
            // forward-side point (rather than the earlier tests' whole-traversal-spanning
            // distance) exceed it, so the recorded last known position is a real, walkable point
            // beyond the doorway instead of an unreachable off-mesh location.
            targetKnowledge.ConfigureDistances(3f, 12f);

            Assert.IsTrue(NavMesh.SamplePosition(new Vector3(8f, 0f, 8f), out var lastKnownHit, 2f,
                NavMesh.AllAreas), "Expected a walkable forward-side NavMesh point for the last known position.");

            // Acquire on the approach side, then instantly relocate the wizard to that reachable
            // forward-side point (beyond Lose Target Distance) before any frame elapses, so the
            // recorded last known position is deterministic and lies beyond the doorway.
            wizardTransform.position = enemyObject.transform.position + new Vector3(0f, 0f, 2f);
            pursuitMovement.Tick(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));

            wizardTransform.position = lastKnownHit.position;
            pursuitMovement.Tick(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
            Assert.That(targetKnowledge.HasTarget, Is.True);

            var elapsed = 0f;
            var crossed = false;
            while (elapsed < 10f)
            {
                Assert.That(targetKnowledge.HasTarget, Is.True,
                    "Expected the searching enemy to retain its target while crossing the doorway toward the " +
                    "last known position.");

                if (enemyObject.transform.position.z > DoorZ)
                {
                    crossed = true;
                    break;
                }

                yield return null;
                elapsed += Time.deltaTime;
            }

            Assert.IsTrue(crossed,
                "Expected the searching enemy to actually cross to the forward side of the open doorway " +
                "while heading toward its recorded last known position.");
            Assert.That(targetKnowledge.HasTarget, Is.True,
                "Expected the enemy's target/search state to survive the doorway crossing.");
        }

        // AC-001/AC-002 (NSC-090): publishes the requested semantic state through
        // DoorEnemyPassability's only public entry point, then waits a bounded number of fixed
        // updates for the carve toggle to settle before movement/pathing against it is
        // meaningful, matching DoorEnemyPassabilityPlayModeTests.
        private IEnumerator SetDoorStateAndSettle(DoorPassabilityState state)
        {
            passability.SetDoorState(state);

            const int settleSteps = 10;
            for (var i = 0; i < settleSteps; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private IEnumerator WaitUntilCrossedOrTimeout()
        {
            var elapsed = 0f;
            while (enemyObject.transform.position.z <= DoorZ)
            {
                Assert.That(targetKnowledge.HasTarget, Is.True,
                    "Expected the pursuing enemy to retain its target throughout the doorway crossing.");

                if (elapsed >= 10f)
                {
                    Assert.Fail("Expected the pursuing enemy to actually cross to the forward side of the " +
                        "doorway.");
                }

                yield return null;
                elapsed += Time.deltaTime;
            }
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
