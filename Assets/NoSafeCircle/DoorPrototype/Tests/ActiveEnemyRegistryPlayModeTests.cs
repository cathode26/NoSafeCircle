using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class ActiveEnemyRegistryPlayModeTests
    {
        private GameObject registryObject;
        private ActiveEnemyRegistry registry;
        private readonly List<GameObject> spawnedEnemies = new List<GameObject>();

        [SetUp]
        public void SetUp()
        {
            registryObject = new GameObject("TestActiveEnemyRegistry");
            registry = registryObject.AddComponent<ActiveEnemyRegistry>();
        }

        [TearDown]
        public void TearDown()
        {
            if (registryObject != null)
            {
                UnityEngine.Object.DestroyImmediate(registryObject);
            }

            foreach (var enemy in spawnedEnemies)
            {
                if (enemy != null)
                {
                    UnityEngine.Object.DestroyImmediate(enemy);
                }
            }

            spawnedEnemies.Clear();
        }

        private GameObject CreateEnemy(string name)
        {
            var enemy = new GameObject(name);
            spawnedEnemies.Add(enemy);
            return enemy;
        }

        private List<GameObject> CreateEnemies(int count)
        {
            var enemies = new List<GameObject>(count);
            for (var i = 0; i < count; i++)
            {
                enemies.Add(CreateEnemy($"Enemy{i}"));
            }

            return enemies;
        }

        // AC-001, VAL-001: registry starts at floor-initial empty bookkeeping.
        [Test]
        public void InitialState_ActiveCountIsZero_AndRemainingCapacityIsFifteen()
        {
            Assert.That(registry.ActiveCount, Is.EqualTo(0));
            Assert.That(registry.RemainingCapacity, Is.EqualTo(ActiveEnemyRegistry.MaxActiveEnemies));
            Assert.That(ActiveEnemyRegistry.MaxActiveEnemies, Is.EqualTo(15));
        }

        // AC-001, VAL-001: count/capacity stay accurate up to exactly the hard cap.
        [Test]
        public void Register_UpToFifteenEnemies_ReportsExactCountAndZeroRemainingCapacity()
        {
            var enemies = CreateEnemies(15);
            foreach (var enemy in enemies)
            {
                registry.Register(enemy);
            }

            Assert.That(registry.ActiveCount, Is.EqualTo(15));
            Assert.That(registry.RemainingCapacity, Is.EqualTo(0));
        }

        // AC-001, VAL-001: unregistering restores remaining capacity.
        [Test]
        public void Unregister_OneOfFifteen_RestoresOneUnitOfCapacity()
        {
            var enemies = CreateEnemies(15);
            foreach (var enemy in enemies)
            {
                registry.Register(enemy);
            }

            registry.Unregister(enemies[0]);

            Assert.That(registry.ActiveCount, Is.EqualTo(14));
            Assert.That(registry.RemainingCapacity, Is.EqualTo(1));
        }

        // AC-001, VAL-001: unregistering several restores matching capacity.
        [Test]
        public void Unregister_MultipleEnemies_RestoresMatchingCapacity()
        {
            var enemies = CreateEnemies(15);
            foreach (var enemy in enemies)
            {
                registry.Register(enemy);
            }

            registry.Unregister(enemies[0]);
            registry.Unregister(enemies[1]);
            registry.Unregister(enemies[2]);

            Assert.That(registry.ActiveCount, Is.EqualTo(12));
            Assert.That(registry.RemainingCapacity, Is.EqualTo(3));
        }

        // AC-002, VAL-002: registering a persistent enemy adds it to the active set once.
        [Test]
        public void Register_SingleEnemy_AddsToActiveSetOnce()
        {
            var enemy = CreateEnemy("SoloEnemy");

            registry.Register(enemy);

            Assert.That(registry.ActiveCount, Is.EqualTo(1));
        }

        // AC-002, VAL-002: duplicate registration does not double-count.
        [Test]
        public void Register_SameEnemyTwice_DoesNotDoubleCount()
        {
            var enemy = CreateEnemy("DuplicateEnemy");

            registry.Register(enemy);
            registry.Register(enemy);
            registry.Register(enemy);

            Assert.That(registry.ActiveCount, Is.EqualTo(1));
        }

        // AC-002, VAL-002: explicit defeat-removal through Unregister removes the enemy once.
        [Test]
        public void Unregister_RegisteredEnemy_RemovesFromActiveSet()
        {
            var enemy = CreateEnemy("DefeatedEnemy");
            registry.Register(enemy);

            registry.Unregister(enemy);

            Assert.That(registry.ActiveCount, Is.EqualTo(0));
            Assert.That(registry.RemainingCapacity, Is.EqualTo(ActiveEnemyRegistry.MaxActiveEnemies));
        }

        // AC-002, VAL-002: repeated unregister of the same enemy does not corrupt the count.
        [Test]
        public void Unregister_SameEnemyTwice_DoesNotCorruptCount()
        {
            var enemy = CreateEnemy("DefeatedEnemy");
            registry.Register(enemy);

            registry.Unregister(enemy);
            registry.Unregister(enemy);

            Assert.That(registry.ActiveCount, Is.EqualTo(0));
        }

        // AC-002, VAL-002: unregistering an enemy that was never registered does not alter the count.
        [Test]
        public void Unregister_UnknownEnemy_DoesNotAlterActiveCount()
        {
            var registeredEnemy = CreateEnemy("RegisteredEnemy");
            var unknownEnemy = CreateEnemy("UnknownEnemy");
            registry.Register(registeredEnemy);

            registry.Unregister(unknownEnemy);

            Assert.That(registry.ActiveCount, Is.EqualTo(1));
        }

        // AC-002, VAL-002: null register/unregister calls do not corrupt the active count.
        [Test]
        public void RegisterAndUnregister_NullEnemy_DoesNotAlterActiveCount()
        {
            var enemy = CreateEnemy("RegisteredEnemy");
            registry.Register(enemy);

            registry.Register(null);
            registry.Unregister(null);

            Assert.That(registry.ActiveCount, Is.EqualTo(1));
        }

        // AC-003, VAL-002: no autonomous removal path exists; a registered surviving enemy
        // remains counted absent explicit unregister or reset, including across simulated
        // target-loss/search/room-crossing/door-wait scenarios that must not touch the registry.
        [Test]
        public void RegisteredEnemy_RemainsCountedWithoutExplicitUnregisterOrReset()
        {
            var enemy = CreateEnemy("SurvivingPursuer");
            registry.Register(enemy);

            // Simulate the enemy surviving target loss, search, a room crossing, and
            // waiting behind a locked door: none of those events call Unregister, so
            // the registry has nothing to invoke here except the passage of state.
            Assert.That(registry.ActiveCount, Is.EqualTo(1));
            Assert.That(registry.RemainingCapacity, Is.EqualTo(ActiveEnemyRegistry.MaxActiveEnemies - 1));
        }

        // AC-004, VAL-003: owner-controlled reset returns bookkeeping to floor-initial empty state.
        [Test]
        public void ResetRegistry_ReturnsActiveCountToZero_AndRemainingCapacityToFifteen()
        {
            var enemies = CreateEnemies(5);
            foreach (var enemy in enemies)
            {
                registry.Register(enemy);
            }

            registry.ResetRegistry();

            Assert.That(registry.ActiveCount, Is.EqualTo(0));
            Assert.That(registry.RemainingCapacity, Is.EqualTo(ActiveEnemyRegistry.MaxActiveEnemies));
        }

        // AC-005, VAL-003: after reset, the same persistent enemy objects can re-register
        // through the normal registration path, and reported count/capacity reflect exactly
        // the re-registered set rather than any restart-side count adjustment.
        [Test]
        public void ResetRegistry_ThenReRegisterSameEnemies_ReflectsExactlyReRegisteredSet()
        {
            var enemies = CreateEnemies(4);
            foreach (var enemy in enemies)
            {
                registry.Register(enemy);
            }

            registry.ResetRegistry();

            registry.Register(enemies[0]);
            registry.Register(enemies[1]);
            registry.Register(enemies[2]);

            Assert.That(registry.ActiveCount, Is.EqualTo(3));
            Assert.That(registry.RemainingCapacity, Is.EqualTo(ActiveEnemyRegistry.MaxActiveEnemies - 3));
        }

        // AC-005, VAL-003: re-registering only a subset of the pre-reset survivors after
        // reset produces a count matching exactly that subset, not the pre-reset total.
        [Test]
        public void ResetRegistry_ThenReRegisterSubset_DoesNotReflectPreResetCount()
        {
            var enemies = CreateEnemies(6);
            foreach (var enemy in enemies)
            {
                registry.Register(enemy);
            }

            Assert.That(registry.ActiveCount, Is.EqualTo(6));

            registry.ResetRegistry();
            registry.Register(enemies[0]);

            Assert.That(registry.ActiveCount, Is.EqualTo(1));
            Assert.That(registry.RemainingCapacity, Is.EqualTo(ActiveEnemyRegistry.MaxActiveEnemies - 1));
        }
    }
}
