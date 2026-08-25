using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class EncounterAdmissionControllerPlayModeTests
    {
        private readonly List<GameObject> spawnedObjects = new List<GameObject>();
        private ActiveEnemyRegistry registry;
        private EncounterAdmissionController controller;

        [SetUp]
        public void SetUp()
        {
            var registryObject = CreateGameObject("TestActiveEnemyRegistry");
            registry = registryObject.AddComponent<ActiveEnemyRegistry>();

            var controllerObject = CreateGameObject("TestEncounterAdmissionController");
            controller = controllerObject.AddComponent<EncounterAdmissionController>();
            controller.Initialize(registry);
        }

        [TearDown]
        public void TearDown()
        {
            for (var i = spawnedObjects.Count - 1; i >= 0; i--)
            {
                if (spawnedObjects[i] != null)
                {
                    Object.DestroyImmediate(spawnedObjects[i]);
                }
            }

            spawnedObjects.Clear();
        }

        // AC-001, AC-002, AC-003, VAL-001: admission consumes the shared registry's
        // remaining capacity, preserves carry-forward pursuers, and delays only the
        // excess newly requested enemies.
        [Test]
        public void RequestAdmission_PersistentPursuersConsumeCapacity_OnlyNewExcessRemainsPending()
        {
            var persistentPursuers = CreateAndRegisterPersistentEnemies(13, "Persistent");
            var requestedEnemies = CreateEnemies(4, "Requested", false);

            var newlyAdmitted = controller.RequestAdmission(requestedEnemies);

            Assert.That(controller.Registry, Is.SameAs(registry));
            Assert.That(newlyAdmitted, Is.EqualTo(2));
            Assert.That(registry.ActiveCount, Is.EqualTo(ActiveEnemyRegistry.MaxActiveEnemies));
            Assert.That(registry.RemainingCapacity, Is.Zero);
            Assert.That(CountActiveEnemies(persistentPursuers, requestedEnemies),
                Is.EqualTo(ActiveEnemyRegistry.MaxActiveEnemies));
            Assert.That(persistentPursuers.All(enemy => enemy.activeInHierarchy), Is.True);

            Assert.That(controller.RequestedBatchCount, Is.EqualTo(1));
            Assert.That(controller.PendingBatchCount, Is.EqualTo(1));
            Assert.That(controller.AdmittedBatchCount, Is.EqualTo(1));
            Assert.That(controller.PendingEnemyCount, Is.EqualTo(2));
            Assert.That(controller.AdmittedEnemyCount, Is.EqualTo(2));

            var batch = controller.AdmissionBatches[0];
            CollectionAssert.AreEqual(requestedEnemies.Take(2), batch.AdmittedEnemies);
            CollectionAssert.AreEqual(requestedEnemies.Skip(2), batch.PendingEnemies);
            Assert.That(requestedEnemies[0].activeInHierarchy, Is.True);
            Assert.That(requestedEnemies[1].activeInHierarchy, Is.True);
            Assert.That(requestedEnemies[2].activeInHierarchy, Is.False);
            Assert.That(requestedEnemies[3].activeInHierarchy, Is.False);

            // Removing the original pursuers through the registry owner's interface
            // leaves both admitted encounter enemies counted, proving admission did not
            // deregister existing members to create capacity.
            foreach (var pursuer in persistentPursuers)
            {
                SimulateDefeat(pursuer);
            }

            Assert.That(registry.ActiveCount, Is.EqualTo(2));
            Assert.That(CountActiveEnemies(persistentPursuers, requestedEnemies), Is.EqualTo(2));
        }

        // AC-001, AC-002, AC-003, VAL-002: repeated processing cannot exceed the cap.
        // The simulated defeat transition removes a pursuer from active play as well as
        // unregistering it, so registry count and actual active population stay aligned.
        [Test]
        public void ProcessPendingAdmissions_AfterSimulatedDefeats_NeverExceedsCapOrActivePopulation()
        {
            var persistentPursuers = CreateAndRegisterPersistentEnemies(14, "Persistent");
            var requestedEnemies = CreateEnemies(3, "Requested", false);

            Assert.That(controller.RequestAdmission(requestedEnemies), Is.EqualTo(1));
            AssertPopulationMatchesRegistry(persistentPursuers, requestedEnemies, 15);
            Assert.That(controller.PendingEnemyCount, Is.EqualTo(2));

            Assert.That(controller.ProcessPendingAdmissions(), Is.Zero);
            AssertPopulationMatchesRegistry(persistentPursuers, requestedEnemies, 15);
            Assert.That(controller.PendingEnemyCount, Is.EqualTo(2));

            SimulateDefeat(persistentPursuers[0]);
            AssertPopulationMatchesRegistry(persistentPursuers, requestedEnemies, 14);

            Assert.That(controller.ProcessPendingAdmissions(), Is.EqualTo(1));
            AssertPopulationMatchesRegistry(persistentPursuers, requestedEnemies, 15);
            Assert.That(controller.PendingEnemyCount, Is.EqualTo(1));
            Assert.That(requestedEnemies[1].activeInHierarchy, Is.True);
            Assert.That(requestedEnemies[2].activeInHierarchy, Is.False);

            Assert.That(controller.ProcessPendingAdmissions(), Is.Zero);
            AssertPopulationMatchesRegistry(persistentPursuers, requestedEnemies, 15);

            SimulateDefeat(persistentPursuers[1]);
            AssertPopulationMatchesRegistry(persistentPursuers, requestedEnemies, 14);

            Assert.That(controller.ProcessPendingAdmissions(), Is.EqualTo(1));
            AssertPopulationMatchesRegistry(persistentPursuers, requestedEnemies, 15);
            Assert.That(controller.PendingEnemyCount, Is.Zero);
            Assert.That(controller.PendingBatchCount, Is.Zero);
            Assert.That(requestedEnemies.All(enemy => enemy.activeInHierarchy), Is.True);
        }

        // AC-002, AC-004, VAL-001, VAL-002: distinct encounter requests retain FIFO
        // identity. The earlier batch remains first while partial, then the later batch
        // becomes partial only after the earlier batch is complete.
        [Test]
        public void TwoRequestedBatches_CapacityIsAllocatedInRequestOrder_AndPartialStateTracksEachBatch()
        {
            var persistentPursuers = CreateAndRegisterPersistentEnemies(14, "Persistent");
            var firstRequest = CreateEnemies(2, "FirstRequest", false);
            var secondRequest = CreateEnemies(2, "SecondRequest", false);

            Assert.That(controller.RequestAdmission(firstRequest), Is.EqualTo(1));
            Assert.That(controller.RequestAdmission(secondRequest), Is.Zero);

            var firstBatch = controller.AdmissionBatches[0];
            var secondBatch = controller.AdmissionBatches[1];
            Assert.That(firstBatch.RequestOrder, Is.EqualTo(0));
            Assert.That(secondBatch.RequestOrder, Is.EqualTo(1));
            CollectionAssert.AreEqual(firstRequest, firstBatch.RequestedEnemies);
            CollectionAssert.AreEqual(secondRequest, secondBatch.RequestedEnemies);
            Assert.That(firstBatch.AdmittedEnemyCount, Is.EqualTo(1));
            Assert.That(firstBatch.PendingEnemyCount, Is.EqualTo(1));
            Assert.That(secondBatch.AdmittedEnemyCount, Is.Zero);
            Assert.That(secondBatch.PendingEnemyCount, Is.EqualTo(2));
            CollectionAssert.AreEqual(new[] { firstBatch, secondBatch }, controller.PendingBatches);
            CollectionAssert.AreEqual(new[] { firstBatch }, controller.AdmittedBatches);
            Assert.That(controller.PendingBatchCount, Is.EqualTo(2));
            Assert.That(controller.AdmittedBatchCount, Is.EqualTo(1));
            Assert.That(controller.PendingEnemyCount, Is.EqualTo(3));
            Assert.That(controller.AdmittedEnemyCount, Is.EqualTo(1));
            Assert.That(firstRequest[0].activeInHierarchy, Is.True);
            Assert.That(firstRequest[1].activeInHierarchy, Is.False);
            Assert.That(secondRequest.All(enemy => !enemy.activeInHierarchy), Is.True);
            AssertPopulationMatchesRegistry(persistentPursuers, firstRequest, secondRequest, 15);

            SimulateDefeat(persistentPursuers[0]);
            SimulateDefeat(persistentPursuers[1]);

            Assert.That(controller.ProcessPendingAdmissions(), Is.EqualTo(2));

            Assert.That(firstBatch.AdmittedEnemyCount, Is.EqualTo(2));
            Assert.That(firstBatch.PendingEnemyCount, Is.Zero);
            Assert.That(secondBatch.AdmittedEnemyCount, Is.EqualTo(1));
            Assert.That(secondBatch.PendingEnemyCount, Is.EqualTo(1));
            CollectionAssert.AreEqual(new[] { secondBatch }, controller.PendingBatches);
            CollectionAssert.AreEqual(new[] { firstBatch, secondBatch }, controller.AdmittedBatches);
            Assert.That(controller.PendingBatchCount, Is.EqualTo(1));
            Assert.That(controller.AdmittedBatchCount, Is.EqualTo(2));
            Assert.That(controller.PendingEnemyCount, Is.EqualTo(1));
            Assert.That(controller.AdmittedEnemyCount, Is.EqualTo(3));
            Assert.That(firstRequest.All(enemy => enemy.activeInHierarchy), Is.True);
            Assert.That(secondRequest[0].activeInHierarchy, Is.True);
            Assert.That(secondRequest[1].activeInHierarchy, Is.False);
            AssertPopulationMatchesRegistry(persistentPursuers, firstRequest, secondRequest, 15);
        }

        // AC-004, AC-005, VAL-003: encounter reset clears requested, pending, reduced,
        // and admitted batch bookkeeping for multiple requests, while leaving separately
        // owned enemy activity and registry membership untouched.
        [Test]
        public void ResetAdmissionState_TwoBatches_ClearsAllBookkeepingWithoutChangingEnemiesOrRegistry()
        {
            var persistentPursuers = CreateAndRegisterPersistentEnemies(14, "Persistent");
            var firstRequest = CreateEnemies(2, "FirstRequest", false);
            var secondRequest = CreateEnemies(2, "SecondRequest", false);

            controller.RequestAdmission(firstRequest);
            controller.RequestAdmission(secondRequest);

            var firstBatch = controller.AdmissionBatches[0];
            var secondBatch = controller.AdmissionBatches[1];
            Assert.That(controller.RequestedBatchCount, Is.EqualTo(2));
            Assert.That(controller.PendingBatchCount, Is.EqualTo(2));
            Assert.That(controller.AdmittedBatchCount, Is.EqualTo(1));
            Assert.That(controller.PendingEnemyCount, Is.EqualTo(3));
            Assert.That(controller.AdmittedEnemyCount, Is.EqualTo(1));
            Assert.That(firstBatch.PendingEnemyCount, Is.EqualTo(1));
            Assert.That(firstBatch.AdmittedEnemyCount, Is.EqualTo(1));
            Assert.That(secondBatch.PendingEnemyCount, Is.EqualTo(2));
            Assert.That(secondBatch.AdmittedEnemyCount, Is.Zero);
            AssertPopulationMatchesRegistry(persistentPursuers, firstRequest, secondRequest, 15);

            controller.ResetAdmissionState();

            Assert.That(controller.RequestedBatchCount, Is.Zero);
            Assert.That(controller.PendingBatchCount, Is.Zero);
            Assert.That(controller.AdmittedBatchCount, Is.Zero);
            Assert.That(controller.PendingEnemyCount, Is.Zero);
            Assert.That(controller.AdmittedEnemyCount, Is.Zero);
            Assert.That(controller.AdmissionBatches, Is.Empty);
            Assert.That(controller.PendingBatches, Is.Empty);
            Assert.That(controller.AdmittedBatches, Is.Empty);

            Assert.That(controller.Registry, Is.SameAs(registry));
            AssertPopulationMatchesRegistry(persistentPursuers, firstRequest, secondRequest, 15);
            Assert.That(persistentPursuers.All(enemy => enemy.activeInHierarchy), Is.True);
            Assert.That(firstRequest[0].activeInHierarchy, Is.True);
            Assert.That(firstRequest[1].activeInHierarchy, Is.False);
            Assert.That(secondRequest.All(enemy => !enemy.activeInHierarchy), Is.True);

            // Identity-sensitive membership check: all fourteen original pursuers plus
            // the one admitted enemy can still be removed after admission reset.
            foreach (var pursuer in persistentPursuers)
            {
                SimulateDefeat(pursuer);
            }

            SimulateDefeat(firstRequest[0]);
            Assert.That(registry.ActiveCount, Is.Zero);
            Assert.That(CountActiveEnemies(persistentPursuers, firstRequest, secondRequest), Is.Zero);
        }

        private GameObject CreateGameObject(string name)
        {
            var gameObject = new GameObject(name);
            spawnedObjects.Add(gameObject);
            return gameObject;
        }

        private List<GameObject> CreateEnemies(int count, string namePrefix, bool active)
        {
            var enemies = new List<GameObject>(count);
            for (var i = 0; i < count; i++)
            {
                var enemy = CreateGameObject($"{namePrefix}{i}");
                enemy.SetActive(active);
                enemies.Add(enemy);
            }

            return enemies;
        }

        private List<GameObject> CreateAndRegisterPersistentEnemies(int count, string namePrefix)
        {
            var enemies = CreateEnemies(count, namePrefix, true);
            foreach (var enemy in enemies)
            {
                registry.Register(enemy);
            }

            return enemies;
        }

        private void SimulateDefeat(GameObject enemy)
        {
            enemy.SetActive(false);
            registry.Unregister(enemy);
        }

        private static int CountActiveEnemies(params IEnumerable<GameObject>[] enemyGroups)
        {
            return enemyGroups.SelectMany(group => group).Count(enemy => enemy.activeInHierarchy);
        }

        private void AssertPopulationMatchesRegistry(
            IEnumerable<GameObject> firstGroup,
            IEnumerable<GameObject> secondGroup,
            int expectedCount)
        {
            AssertPopulationMatchesRegistry(new[] { firstGroup, secondGroup }, expectedCount);
        }

        private void AssertPopulationMatchesRegistry(
            IEnumerable<GameObject> firstGroup,
            IEnumerable<GameObject> secondGroup,
            IEnumerable<GameObject> thirdGroup,
            int expectedCount)
        {
            AssertPopulationMatchesRegistry(new[] { firstGroup, secondGroup, thirdGroup }, expectedCount);
        }

        private void AssertPopulationMatchesRegistry(
            IEnumerable<GameObject>[] enemyGroups,
            int expectedCount)
        {
            Assert.That(expectedCount, Is.LessThanOrEqualTo(ActiveEnemyRegistry.MaxActiveEnemies));
            Assert.That(CountActiveEnemies(enemyGroups), Is.EqualTo(expectedCount));
            Assert.That(registry.ActiveCount, Is.EqualTo(expectedCount));
            Assert.That(registry.ActiveCount, Is.LessThanOrEqualTo(ActiveEnemyRegistry.MaxActiveEnemies));
        }
    }
}
