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
    // NSC-053 AC-001..AC-008: temporary production NavMesh behavior; no saved assets.
    public sealed class RangedEnemyKeepDistanceMovementPlayModeTests
    {
        private GameObject root;
        private GameplayNavigationSurface surface;
        private GameObject wizard;
        private GameObject enemy;
        private NavMeshAgent agent;
        private EnemyTargetKnowledge knowledge;
        private EnemyPursuitMovement pursuit;
        private RangedEnemyKeepDistanceMovement keepDistance;
        private EnemyStatusEffectMovement status;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("NSC053Fixture");
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.name = "WalkableFloor";
            floor.transform.SetParent(root.transform);
            floor.transform.position = new Vector3(0f, -0.05f, 0f);
            var testName = TestContext.CurrentContext.Test.Name;
            floor.transform.localScale = testName.Contains("CorneredNoRoute")
                ? new Vector3(3f, 0.1f, 3f)
                : new Vector3(24f, 0.1f, 24f);
            if (testName.Contains("BlockedDirectRetreat"))
                CreateWall("DirectRetreatWall", new Vector3(-6f, 1.5f, 0f), new Vector3(0.5f, 3f, 1f));
            if (testName.Contains("CorneredNoRoute"))
            {
                CreateWall("WestFence", new Vector3(-1.5f, 1.5f, 0f), new Vector3(0.2f, 3f, 3f));
                CreateWall("EastFence", new Vector3(1.5f, 1.5f, 0f), new Vector3(0.2f, 3f, 3f));
                CreateWall("NorthFence", new Vector3(0f, 1.5f, 1.5f), new Vector3(3f, 3f, 0.2f));
                CreateWall("SouthFence", new Vector3(0f, 1.5f, -1.5f), new Vector3(3f, 3f, 0.2f));
            }
            var navRoot = new GameObject("GameplayNavigation");
            navRoot.transform.SetParent(root.transform);
            surface = navRoot.AddComponent<GameplayNavigationSurface>();
            surface.ConfigureAndBuild();

            wizard = new GameObject("Wizard");
            wizard.transform.SetParent(root.transform);
            wizard.transform.position = Vector3.zero;
            enemy = new GameObject("RangedEnemy");
            enemy.transform.SetParent(root.transform);
            var spawnPoint = testName.Contains("CorneredNoRoute") ? Vector3.zero : new Vector3(-5f, 0f, 0f);
            Assert.IsTrue(NavMesh.SamplePosition(spawnPoint, out var spawn, 2f, NavMesh.AllAreas));
            enemy.transform.position = spawn.position;
            agent = enemy.AddComponent<NavMeshAgent>();
            var settings = NavMesh.GetSettingsByIndex(0);
            agent.agentTypeID = settings.agentTypeID;
            agent.radius = settings.agentRadius;
            agent.height = settings.agentHeight;
            agent.Warp(spawn.position);
            knowledge = enemy.AddComponent<EnemyTargetKnowledge>();
            knowledge.Initialize(wizard.transform);
            knowledge.ConfigureDistances(8f, 12f);
            pursuit = enemy.AddComponent<EnemyPursuitMovement>();
            status = enemy.AddComponent<EnemyStatusEffectMovement>();
            keepDistance = enemy.AddComponent<RangedEnemyKeepDistanceMovement>();
            keepDistance.ConfigureDistances(2f, 3.5f);
        }

        private void CreateWall(string name, Vector3 position, Vector3 scale)
        {
            var wall = GameObject.CreatePrimitive(PrimitiveType.Cube);
            wall.name = name;
            wall.transform.SetParent(root.transform);
            wall.transform.position = position;
            wall.transform.localScale = scale;
        }

        [TearDown]
        public void TearDown()
        {
            if (surface != null) surface.ClearBakedData();
            if (root != null) Object.Destroy(root);
        }

        // AC-002, VAL-005: public configuration rejects invalid bands and later loss-range changes hold.
        [UnityTest]
        public IEnumerator InvalidBand_Throws_AndLaterLossRangeChangeClearsPath()
        {
            Assert.Throws<ArgumentException>(() => keepDistance.ConfigureDistances(0f, 3f));
            Assert.Throws<ArgumentException>(() => keepDistance.ConfigureDistances(3f, 3f));
            Assert.Throws<ArgumentException>(() => keepDistance.ConfigureDistances(2f, 12f));
            knowledge.UpdateTargetKnowledge(0f);
            wizard.transform.position = enemy.transform.position + Vector3.right;
            knowledge.ConfigureDistances(1f, 3f);
            yield return null;
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.IsFalse(agent.hasPath, "Invalid keep-distance band must not leave a targetward path.");
            knowledge.ConfigureDistances(8f, 12f);
            yield return null;
            Assert.IsTrue(agent.isOnNavMesh);
        }

        // AC-001/003/004, VAL-001: no melee companion is present; pursue, hold, then retreat.
        [UnityTest]
        public IEnumerator AcquiredWizard_Approaches_HoldsInBand_ThenRetreatsWhenClose()
        {
            Assert.That(root.transform.childCount, Is.EqualTo(4), "Fixture contains only floor, navigation, wizard, and ranged enemy.");
            var initialDistance = Vector3.Distance(enemy.transform.position, wizard.transform.position);
            var deadline = Time.time + 6f;
            while (Time.time < deadline && Vector3.Distance(enemy.transform.position, wizard.transform.position) > 3.3f)
                yield return null;
            Assert.That(Vector3.Distance(enemy.transform.position, wizard.transform.position), Is.LessThan(initialDistance - 1f));
            Assert.AreSame(wizard.transform, knowledge.CurrentTarget);
            for (var i = 0; i < 60; i++)
            {
                yield return null;
                Assert.IsFalse(agent.hasPath, "A stationary wizard inside the band must not cause chase jitter.");
            }
            wizard.transform.position = enemy.transform.position + Vector3.right * 0.6f;
            var closeSeparation = Vector3.Distance(enemy.transform.position, wizard.transform.position);
            deadline = Time.time + 4f;
            while (Time.time < deadline && Vector3.Distance(enemy.transform.position, wizard.transform.position) < closeSeparation + 0.6f)
                yield return null;
            Assert.That(Vector3.Distance(enemy.transform.position, wizard.transform.position), Is.GreaterThan(closeSeparation + 0.6f));
            Assert.AreSame(wizard.transform, knowledge.CurrentTarget);
        }

        // AC-007, VAL-006: disabling hands destination authority back to live pursuit.
        [UnityTest]
        public IEnumerator DisableDuringRetreat_ClearsPath_AndPursuitResumesTargetward()
        {
            wizard.transform.position = enemy.transform.position + Vector3.right * 0.6f;
            for (var i = 0; i < 15 && !agent.hasPath; i++) yield return null;
            Assert.IsTrue(agent.hasPath);
            keepDistance.enabled = false;
            Assert.IsFalse(agent.hasPath);
            yield return null;
            Assert.IsTrue(pursuit.enabled);
            Assert.IsTrue(agent.enabled);
            Assert.That(Vector3.Distance(agent.destination, wizard.transform.position), Is.LessThan(0.8f));
            wizard.transform.position = new Vector3(8f, 0f, 0f);
            yield return null;
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
        }

        // AC-001/007, VAL-006: RequireComponent works even if this component is added first.
        [Test]
        public void AddOnlyKeepDistance_ProvidesAndResolvesCompanions()
        {
            var orderProbe = new GameObject("AddOrderProbe");
            orderProbe.transform.SetParent(root.transform);
            var added = orderProbe.AddComponent<RangedEnemyKeepDistanceMovement>();
            Assert.IsNotNull(orderProbe.GetComponent<NavMeshAgent>());
            Assert.IsNotNull(orderProbe.GetComponent<EnemyTargetKnowledge>());
            Assert.IsNotNull(orderProbe.GetComponent<EnemyPursuitMovement>());
            Assert.DoesNotThrow(() => added.ConfigureDistances(1f, 2f));
        }

        // AC-006, VAL-004: loss and search remain exclusively owned by pursuit/knowledge.
        [UnityTest]
        public IEnumerator TargetLoss_LeavesLastKnownMovementToPursuit_ThenReacquires()
        {
            yield return null;
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            wizard.transform.position = new Vector3(8f, 0f, 0f);
            yield return null;
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
            Assert.That(Vector3.Distance(agent.destination, knowledge.LastKnownPosition), Is.LessThan(0.8f));
            wizard.transform.position = new Vector3(30f, 0f, 0f);
            var searchDeadline = Time.time + 8f;
            while (Time.time < searchDeadline && knowledge.State != EnemyTargetKnowledgeState.Wandering)
                yield return null;
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Wandering),
                "Pursuit must reach the recorded last-known position and begin bounded search.");
            wizard.transform.position = enemy.transform.position + Vector3.right * 0.5f;
            // Reacquisition and a newly calculated retreat path can span separate
            // NavMeshAgent simulation frames after the last-known destination is cleared.
            for (var i = 0; i < 15 &&
                 (knowledge.State != EnemyTargetKnowledgeState.Pursuing ||
                  Vector3.Distance(agent.destination, wizard.transform.position) < 0.8f); i++)
                yield return null;
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.AreSame(wizard.transform, knowledge.CurrentTarget);
            Assert.That(Vector3.Distance(agent.destination, wizard.transform.position), Is.GreaterThan(0.8f),
                "After reacquisition inside close range, keep-distance must replace targetward pursuit.");
        }

        // AC-005, VAL-002: Frost owns speed, while this component continues to select paths.
        [UnityTest]
        public IEnumerator Frost_ReducesRealApproachAndRetreatDisplacement()
        {
            knowledge.ConfigureDistances(10f, 14f);
            var approachStart = new Vector3(-8f, 0f, 0f);
            Assert.IsTrue(agent.Warp(approachStart));
            wizard.transform.position = Vector3.zero;
            yield return null;
            float controlApproach = 0f;
            yield return MeasureDisplacement(0.6f, value => controlApproach = value);
            Assert.IsTrue(agent.Warp(approachStart));
            keepDistance.ResetKeepDistanceMovement();
            status.ApplyFrostSlowdown(0.3f, 3f);
            yield return null;
            float frostedApproach = 0f;
            yield return MeasureDisplacement(0.6f, value => frostedApproach = value);
            Assert.That(frostedApproach, Is.LessThan(controlApproach - 0.1f));
            Assert.AreSame(wizard.transform, knowledge.CurrentTarget);
            Assert.IsTrue(agent.isOnNavMesh);

            status.ResetStatusEffects();
            var retreatStart = new Vector3(-5f, 0f, 0f);
            Assert.IsTrue(agent.Warp(retreatStart));
            keepDistance.ResetKeepDistanceMovement();
            wizard.transform.position = new Vector3(-4.4f, 0f, 0f);
            yield return null;
            float controlRetreat = 0f;
            yield return MeasureDisplacement(0.6f, value => controlRetreat = value);
            Assert.IsTrue(agent.Warp(retreatStart));
            keepDistance.ResetKeepDistanceMovement();
            status.ApplyFrostSlowdown(0.3f, 3f);
            yield return null;
            float frostedRetreat = 0f;
            yield return MeasureDisplacement(0.6f, value => frostedRetreat = value);
            Assert.That(frostedRetreat, Is.LessThan(controlRetreat - 0.1f));
            Assert.AreSame(wizard.transform, knowledge.CurrentTarget);
            Assert.IsTrue(agent.isOnNavMesh);
        }

        // AC-003, VAL-003: all geometry is present before the initial bake and before
        // the live NavMeshAgent exists. A blocked straight ray must choose a stable side.
        [UnityTest]
        public IEnumerator BlockedDirectRetreat_UsesStableCompleteSidePath()
        {
            wizard.transform.position = enemy.transform.position + Vector3.right * 0.6f;
            Assert.IsTrue(agent.isOnNavMesh);
            Assert.IsTrue(NavMesh.Raycast(enemy.transform.position,
                enemy.transform.position + Vector3.left * 2f, out _, NavMesh.AllAreas),
                "Fixture must block the direct retreat ray on its stable bake.");
            for (var i = 0; i < 30 && (!agent.hasPath || Mathf.Abs(agent.destination.z) < 1f); i++)
                yield return null;
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.IsTrue(agent.isOnNavMesh);
            Assert.That(Mathf.Abs(agent.destination.z), Is.GreaterThan(1f),
                $"Expected a side destination, got {agent.destination} from {enemy.transform.position}.");
            var sideDestination = agent.destination;
            var path = new NavMeshPath();
            Assert.IsTrue(NavMesh.CalculatePath(enemy.transform.position, sideDestination, NavMesh.AllAreas, path));
            Assert.That(path.status, Is.EqualTo(NavMeshPathStatus.PathComplete));
            Assert.That(Vector3.Distance(sideDestination, wizard.transform.position),
                Is.GreaterThan(Vector3.Distance(enemy.transform.position, wizard.transform.position)));
            var initialSeparation = Vector3.Distance(enemy.transform.position, wizard.transform.position);
            var sideDeadline = Time.time + 3f;
            while (Time.time < sideDeadline &&
                   Vector3.Distance(enemy.transform.position, wizard.transform.position) < initialSeparation + 0.3f)
            {
                yield return null;
                Assert.IsTrue(agent.isOnNavMesh);
                Assert.That(Vector3.Distance(agent.destination, sideDestination), Is.LessThan(0.2f),
                    "Side destination must stay fixed while the agent begins moving.");
            }
            Assert.That(Vector3.Distance(enemy.transform.position, wizard.transform.position),
                Is.GreaterThan(initialSeparation + 0.3f), "The enemy must actually increase separation.");
            for (var i = 0; i < 5; i++)
            {
                yield return null;
                Assert.That(Vector3.Distance(agent.destination, sideDestination), Is.LessThan(0.2f));
            }
        }

        // AC-003, VAL-003: a small enclosed walkable pocket has no complete candidate
        // at the component's retreat stride; never chase into the stationary wizard.
        [UnityTest]
        public IEnumerator CorneredNoRoute_HoldsWithoutTargetwardPath()
        {
            Assert.IsTrue(agent.isOnNavMesh);
            wizard.transform.position = enemy.transform.position + Vector3.right * 0.4f;
            var start = enemy.transform.position;
            var initialSeparation = Vector3.Distance(start, wizard.transform.position);
            var deadline = Time.time + 1.1f;
            while (Time.time < deadline)
            {
                yield return null;
                Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
                Assert.IsTrue(agent.isOnNavMesh);
                Assert.IsFalse(agent.hasPath, "A cornered enemy must clear pursuit's targetward request.");
                Assert.That(Vector3.Distance(enemy.transform.position, wizard.transform.position),
                    Is.GreaterThanOrEqualTo(initialSeparation - 0.1f));
                Assert.That(Vector3.Distance(enemy.transform.position, start), Is.LessThan(0.1f));
            }
        }


        private IEnumerator MeasureDisplacement(float duration, Action<float> record)
        {
            var start = enemy.transform.position;
            var end = Time.time + duration;
            while (Time.time < end) yield return null;
            record(Vector3.Distance(start, enemy.transform.position));
        }
    }
}
