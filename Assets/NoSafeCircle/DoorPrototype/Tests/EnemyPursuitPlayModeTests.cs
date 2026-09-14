using System;
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
    // NSC-092 VAL-001: proves EnemyPursuitMovement's integrated behavior against the production
    // EnemyTargetKnowledge (NSC-091) and a temporary NavMesh baked by GameplayNavigationSurface
    // (NSC-089). Every object here - floor, navigation, wizard, and enemy - is created and
    // destroyed by this fixture. Nothing here opens, saves, or otherwise touches the committed
    // Assets/Scenes/DoorPrototype.unity scene.
    public sealed class EnemyPursuitPlayModeTests
    {
        private const float DetectionDistance = 3f;
        private const float LoseTargetDistance = 6f;
        private const float FloorSize = 24f;

        private static readonly Vector3 EnemySpawnPoint = new Vector3(-4f, 0f, 0f);
        private static readonly Vector3 WizardNearPoint = new Vector3(-2f, 0f, 0f);
        private static readonly Vector3 WizardFarPoint = new Vector3(4f, 0f, 0f);

        private GameObject root;
        private GameplayNavigationSurface surfaceOwner;
        private GameObject wizardObject;
        private Transform wizardTransform;
        private GameObject enemyObject;
        private NavMeshAgent agent;
        private EnemyTargetKnowledge targetKnowledge;
        private EnemyPursuitMovement pursuitMovement;
        private Vector3 spawnPosition;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("EnemyPursuitMovementTestRoot");
            BuildOpenFloor();

            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(root.transform, false);
            surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surfaceOwner.ConfigureAndBuild();

            wizardObject = new GameObject("TestWizard");
            wizardObject.transform.SetParent(root.transform, false);
            wizardTransform = wizardObject.transform;

            Assert.IsTrue(NavMesh.SamplePosition(EnemySpawnPoint, out var spawnHit, 2f, NavMesh.AllAreas),
                "Expected the enemy spawn point to sample onto the baked open test floor.");

            enemyObject = new GameObject("TestEnemy");
            enemyObject.transform.SetParent(root.transform, false);
            enemyObject.transform.position = spawnHit.position;

            var settings = NavMesh.GetSettingsByIndex(0);
            agent = enemyObject.AddComponent<NavMeshAgent>();
            agent.agentTypeID = settings.agentTypeID;
            agent.radius = settings.agentRadius;
            agent.height = settings.agentHeight;
            agent.Warp(spawnHit.position);

            targetKnowledge = enemyObject.AddComponent<EnemyTargetKnowledge>();
            targetKnowledge.Initialize(wizardTransform);
            targetKnowledge.ConfigureDistances(DetectionDistance, LoseTargetDistance);

            pursuitMovement = enemyObject.AddComponent<EnemyPursuitMovement>();

            spawnPosition = enemyObject.transform.position;
        }

        [TearDown]
        public void TearDown()
        {
            if (surfaceOwner != null) surfaceOwner.ClearBakedData();
            if (root != null) Object.Destroy(root);
        }

        // AC-001, VAL-001: acquiring the wizard sets the NavMeshAgent destination to its
        // position, and the enemy actually moves closer over subsequent frames.
        [UnityTest]
        public IEnumerator Pursuing_AcquiredTarget_SetsAgentDestinationTowardTarget_AndAgentMovesCloser()
        {
            wizardTransform.position = WizardNearPoint;
            var initialDistance = Vector3.Distance(enemyObject.transform.position, wizardTransform.position);

            pursuitMovement.Tick(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(Vector3.Distance(agent.destination, wizardTransform.position), Is.LessThan(0.6f),
                "Expected the NavMeshAgent destination to be set to the acquired wizard target's position.");

            yield return WaitUntilOrTimeout(
                () => Vector3.Distance(enemyObject.transform.position, wizardTransform.position) <
                      initialDistance - 0.5f,
                5f,
                "Expected the pursuing enemy to actually move closer to the acquired wizard target.");
        }

        // AC-002, VAL-001: exceeding Lose Target Distance while pursuing sets the NavMeshAgent
        // destination to the recorded last known position; physically reaching it reports
        // arrival back to EnemyTargetKnowledge, entering the bounded wander/search state with a
        // valid on-NavMesh wander point.
        [UnityTest]
        public IEnumerator SearchingLastKnownPosition_ReachesRecordedPosition_ReportsArrival_AndEntersWanderingWithValidNavMeshPoint()
        {
            wizardTransform.position = WizardNearPoint;
            pursuitMovement.Tick(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));

            wizardTransform.position = WizardFarPoint;
            pursuitMovement.Tick(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
            var lastKnownPosition = targetKnowledge.LastKnownPosition;
            Assert.That(Vector3.Distance(lastKnownPosition, WizardFarPoint), Is.LessThan(0.6f));
            Assert.That(Vector3.Distance(agent.destination, lastKnownPosition), Is.LessThan(0.6f),
                "Expected the NavMeshAgent destination to be set to the recorded last known position.");

            // Keep the recorded position fixed while the wizard leaves the search area.
            // Otherwise the enemy correctly reacquires the wizard before reaching it.
            wizardTransform.position = new Vector3(100f, 0f, 0f);

            yield return WaitUntilOrTimeout(
                () => targetKnowledge.State == EnemyTargetKnowledgeState.Wandering,
                8f,
                "Expected the searching enemy to physically reach the last known position, report arrival, " +
                "and enter the bounded wander/search state.");

            Assert.That(targetKnowledge.SearchTimeRemaining, Is.EqualTo(targetKnowledge.SearchDuration));

            var wanderDestination = agent.destination;
            Assert.That(Vector3.Distance(wanderDestination, lastKnownPosition), Is.LessThan(10f),
                "Expected the chosen wander point to stay within a short, bounded distance of the last " +
                "known position.");

            Assert.IsTrue(NavMesh.SamplePosition(wanderDestination, out var wanderHit, 0.1f, NavMesh.AllAreas));
            Assert.That(Vector3.Distance(wanderHit.position, wanderDestination), Is.LessThan(0.15f),
                "Expected the chosen wander point to be valid on the configured NavMesh.");
        }

        // AC-003, VAL-001: once the wandering enemy physically reaches its chosen point, it
        // selects a new controlled-random, bounded, on-NavMesh point rather than stopping.
        [UnityTest]
        public IEnumerator Wandering_AfterReachingChosenPoint_SelectsANewBoundedNavMeshPoint()
        {
            yield return EnterWanderingState();

            var firstDestination = agent.destination;

            yield return WaitUntilOrTimeout(
                () => Vector3.Distance(enemyObject.transform.position, firstDestination) < 0.6f,
                6f,
                "Expected the wandering enemy to physically reach its first chosen wander point.");

            yield return WaitUntilOrTimeout(
                () => Vector3.Distance(agent.destination, firstDestination) > 0.05f,
                3f,
                "Expected the wandering enemy to select a new bounded wander point after reaching the first.");

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Wandering));
            var secondDestination = agent.destination;
            Assert.IsTrue(NavMesh.SamplePosition(secondDestination, out var hit, 0.1f, NavMesh.AllAreas));
            Assert.That(Vector3.Distance(hit.position, secondDestination), Is.LessThan(0.15f),
                "Expected the newly chosen wander point to also be valid on the configured NavMesh.");
        }

        // AC-004, VAL-001: the wizard re-entering Detection Distance during the wander/search
        // state reacquires it, and pursuit destinations resume targeting the wizard rather than
        // a stale wander point.
        [UnityTest]
        public IEnumerator Wandering_WizardReentersDetectionDistance_ReacquiresAndResumesPursuing()
        {
            yield return EnterWanderingState();

            wizardTransform.position = enemyObject.transform.position;

            yield return WaitUntilOrTimeout(
                () => targetKnowledge.State == EnemyTargetKnowledgeState.Pursuing,
                3f,
                "Expected the wandering enemy to reacquire the wizard once it re-enters Detection Distance.");

            Assert.That(Vector3.Distance(agent.destination, wizardTransform.position), Is.LessThan(0.6f),
                "Expected pursuit destinations to resume targeting the reacquired wizard rather than a " +
                "stale wander point.");
        }

        // AC-004, VAL-001: the bounded wander/search interval completing without reacquisition
        // clears the target (owned by EnemyTargetKnowledge) and stops the agent's pursuit/search
        // path, returning control to local idle/wander movement without destroying, disabling,
        // replacing, or reinitializing the enemy GameObject.
        [UnityTest]
        public IEnumerator SearchExpiresWithoutReacquisition_ClearsTargetAndStopsAgentPath()
        {
            yield return EnterWanderingState();

            var originalInstanceId = enemyObject.GetInstanceID();

            pursuitMovement.Tick(targetKnowledge.SearchDuration + 1f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(targetKnowledge.HasTarget, Is.False);
            Assert.IsFalse(agent.hasPath,
                "Expected the agent's pursuit/search path to be cleared once the enemy returns to idle.");
            Assert.That(enemyObject, Is.Not.Null);
            Assert.That(enemyObject.GetInstanceID(), Is.EqualTo(originalInstanceId));
            Assert.That(enemyObject.activeInHierarchy, Is.True);

            yield return null;
        }

        // AC-007, VAL-001: ResetPursuit clears EnemyTargetKnowledge's owned state through its
        // own reset method, stops and clears the agent's path, and returns the enemy Transform
        // to its authored spawn position.
        [UnityTest]
        public IEnumerator ResetPursuit_WhilePursuing_ClearsKnowledgeStopsAgentAndReturnsToSpawnPosition()
        {
            wizardTransform.position = WizardNearPoint;
            pursuitMovement.Tick(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));

            yield return WaitUntilOrTimeout(
                () => Vector3.Distance(enemyObject.transform.position, spawnPosition) > 0.5f,
                3f,
                "Expected the pursuing enemy to have moved away from its spawn point before reset.");

            pursuitMovement.ResetPursuit();

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(targetKnowledge.HasTarget, Is.False);
            Assert.IsFalse(agent.hasPath, "Expected ResetPursuit to clear the agent's current path.");
            Assert.That(Vector3.Distance(enemyObject.transform.position, spawnPosition), Is.LessThan(0.05f),
                "Expected ResetPursuit to return the enemy Transform to its authored spawn position.");

            yield return null;
        }

        // AC-007, VAL-001: after a complete reset, the same persistent enemy can acquire and
        // pursue again, matching floor-restart reuse.
        [UnityTest]
        public IEnumerator ResetPursuit_ThenWizardReentersDetectionDistance_CanPursueAgain()
        {
            wizardTransform.position = WizardNearPoint;
            pursuitMovement.Tick(0f);

            pursuitMovement.ResetPursuit();

            wizardTransform.position = enemyObject.transform.position + new Vector3(1f, 0f, 0f);

            yield return WaitUntilOrTimeout(
                () => targetKnowledge.State == EnemyTargetKnowledgeState.Pursuing,
                3f,
                "Expected the enemy to be able to reacquire and pursue again after ResetPursuit.");

            Assert.That(enemyObject, Is.Not.Null);
            Assert.That(enemyObject.activeInHierarchy, Is.True);
        }

        // Drives the fixture's enemy/wizard into the Wandering state deterministically: acquire,
        // then instantly move the wizard beyond Lose Target Distance before any frame elapses so
        // the recorded last known position is deterministic, then wait for the enemy to
        // physically arrive and EnemyPursuitMovement to report that arrival.
        private IEnumerator EnterWanderingState()
        {
            wizardTransform.position = WizardNearPoint;
            pursuitMovement.Tick(0f);

            wizardTransform.position = WizardFarPoint;
            pursuitMovement.Tick(0f);

            // The wizard must leave the last-known location so search can reach arrival
            // without the target-knowledge owner correctly reacquiring it first.
            wizardTransform.position = new Vector3(100f, 0f, 0f);

            yield return WaitUntilOrTimeout(
                () => targetKnowledge.State == EnemyTargetKnowledgeState.Wandering,
                8f,
                "Expected the enemy to reach the last known position and enter the wander/search state.");
        }

        private static IEnumerator WaitUntilOrTimeout(Func<bool> condition, float timeoutSeconds,
            string timeoutMessage)
        {
            var elapsed = 0f;
            while (!condition())
            {
                if (elapsed >= timeoutSeconds)
                {
                    Assert.Fail(timeoutMessage);
                }

                yield return null;
                elapsed += Time.deltaTime;
            }
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
}
