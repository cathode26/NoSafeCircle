using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class EnemyHealthPlayModeTests
    {
        private GameObject enemyObject;
        private EnemyHealth enemyHealth;
        private GameObject registryObject;
        private ActiveEnemyRegistry registry;

        [SetUp]
        public void SetUp()
        {
            enemyObject = new GameObject("TestEnemy");
            enemyHealth = enemyObject.AddComponent<EnemyHealth>();

            registryObject = new GameObject("TestActiveEnemyRegistry");
            registry = registryObject.AddComponent<ActiveEnemyRegistry>();
        }

        [TearDown]
        public void TearDown()
        {
            if (enemyObject != null)
            {
                UnityEngine.Object.DestroyImmediate(enemyObject);
            }

            if (registryObject != null)
            {
                UnityEngine.Object.DestroyImmediate(registryObject);
            }
        }

        // AC-001, VAL-001: initial state starts at full authored health, undefeated.
        [Test]
        public void InitialState_CurrentHealthEqualsMaxHealth_AndNotDefeated()
        {
            Assert.That(enemyHealth.CurrentHealth, Is.EqualTo(enemyHealth.MaxHealth));
            Assert.That(enemyHealth.IsDefeated, Is.False);
        }

        // AC-001, VAL-001: the owner-controlled damage interface reduces health.
        [Test]
        public void TakeDamage_PartialAmount_ReducesCurrentHealthByThatAmount()
        {
            var maxHealth = enemyHealth.MaxHealth;

            enemyHealth.TakeDamage(maxHealth * 0.25f);

            Assert.That(enemyHealth.CurrentHealth, Is.EqualTo(maxHealth * 0.75f).Within(0.001f));
            Assert.That(enemyHealth.IsDefeated, Is.False);
        }

        // AC-001, VAL-001: the Damaged event reports the amount applied through the interface.
        [Test]
        public void TakeDamage_PositiveAmount_RaisesDamagedEventWithThatAmount()
        {
            var reportedAmount = 0f;
            var eventCount = 0;
            enemyHealth.Damaged += amount =>
            {
                reportedAmount = amount;
                eventCount++;
            };

            enemyHealth.TakeDamage(10f);

            Assert.That(eventCount, Is.EqualTo(1));
            Assert.That(reportedAmount, Is.EqualTo(10f).Within(0.001f));
        }

        // AC-001, VAL-001: non-positive damage requests do not mutate health or notify.
        [Test]
        public void TakeDamage_ZeroOrNegativeAmount_DoesNotChangeHealthOrRaiseEvent()
        {
            var maxHealth = enemyHealth.MaxHealth;
            var eventCount = 0;
            enemyHealth.Damaged += _ => eventCount++;

            enemyHealth.TakeDamage(0f);
            enemyHealth.TakeDamage(-5f);

            Assert.That(enemyHealth.CurrentHealth, Is.EqualTo(maxHealth));
            Assert.That(eventCount, Is.EqualTo(0));
        }

        // AC-001, VAL-001: health does not fall below zero even when overkill damage is applied.
        [Test]
        public void TakeDamage_ExceedingCurrentHealth_ClampsCurrentHealthToZero()
        {
            var maxHealth = enemyHealth.MaxHealth;

            enemyHealth.TakeDamage(maxHealth * 2f);

            Assert.That(enemyHealth.CurrentHealth, Is.EqualTo(0f));
        }

        // AC-002, VAL-001: reaching zero health triggers the defeat transition.
        [Test]
        public void TakeDamage_ReducingHealthToZero_TriggersDefeatTransition()
        {
            enemyHealth.TakeDamage(enemyHealth.MaxHealth);

            Assert.That(enemyHealth.IsDefeated, Is.True);
        }

        // AC-002, VAL-001: the Defeated event fires exactly once for the persistent enemy object.
        [Test]
        public void TakeDamage_ReducingHealthToZero_RaisesDefeatedEventExactlyOnce()
        {
            var defeatCount = 0;
            enemyHealth.Defeated += () => defeatCount++;

            enemyHealth.TakeDamage(enemyHealth.MaxHealth);

            Assert.That(defeatCount, Is.EqualTo(1));
        }

        // AC-002, VAL-001: further lethal damage requests after defeat do not refire the
        // defeat transition or continue reducing health for the same persistent object.
        [Test]
        public void TakeDamage_AfterDefeat_DoesNotRaiseDefeatedAgain_AndHealthStaysAtZero()
        {
            var defeatCount = 0;
            enemyHealth.Defeated += () => defeatCount++;

            enemyHealth.TakeDamage(enemyHealth.MaxHealth);
            enemyHealth.TakeDamage(enemyHealth.MaxHealth);
            enemyHealth.TakeDamage(10f);

            Assert.That(defeatCount, Is.EqualTo(1));
            Assert.That(enemyHealth.CurrentHealth, Is.EqualTo(0f));
        }

        // AC-002, VAL-001: damage applied after defeat is also not reported through Damaged,
        // so no system can keep writing this enemy's health once it has been defeated.
        [Test]
        public void TakeDamage_AfterDefeat_DoesNotRaiseDamagedEvent()
        {
            enemyHealth.TakeDamage(enemyHealth.MaxHealth);

            var eventCount = 0;
            enemyHealth.Damaged += _ => eventCount++;

            enemyHealth.TakeDamage(10f);

            Assert.That(eventCount, Is.EqualTo(0));
        }

        // AC-003, VAL-002: defeat reports removal through the registry's owner-controlled
        // unregister interface rather than the registry double-counting or Enemy Health
        // maintaining a separate count.
        [Test]
        public void TakeDamage_ReducingHealthToZero_UnregistersFromActiveEnemyRegistry()
        {
            registry.Register(enemyObject);
            enemyHealth.Initialize(registry);
            Assert.That(registry.ActiveCount, Is.EqualTo(1));

            enemyHealth.TakeDamage(enemyHealth.MaxHealth);

            Assert.That(registry.ActiveCount, Is.EqualTo(0));
        }

        // AC-003, VAL-002: repeated lethal damage after defeat does not call Unregister again,
        // so the registry cannot be double-decremented for one defeated persistent object.
        [Test]
        public void TakeDamage_AfterDefeat_DoesNotUnregisterFromRegistryAgain()
        {
            var otherEnemy = new GameObject("OtherEnemy");
            try
            {
                registry.Register(enemyObject);
                registry.Register(otherEnemy);
                enemyHealth.Initialize(registry);

                enemyHealth.TakeDamage(enemyHealth.MaxHealth);
                Assert.That(registry.ActiveCount, Is.EqualTo(1));

                enemyHealth.TakeDamage(enemyHealth.MaxHealth);

                Assert.That(registry.ActiveCount, Is.EqualTo(1));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(otherEnemy);
            }
        }

        // AC-003, VAL-002: without a wired registry, defeat still transitions locally without
        // throwing, so damage sources cannot be blocked by registry wiring order.
        [Test]
        public void TakeDamage_ReducingHealthToZero_WithoutRegistryWired_StillDefeatsLocally()
        {
            Assert.DoesNotThrow(() => enemyHealth.TakeDamage(enemyHealth.MaxHealth));

            Assert.That(enemyHealth.IsDefeated, Is.True);
        }

        // AC-004, VAL-003: the owner-controlled reset entry point restores full health and
        // clears the defeat transition for a previously-damaged persistent enemy.
        [Test]
        public void ResetHealth_AfterPartialDamage_RestoresFullHealth()
        {
            var maxHealth = enemyHealth.MaxHealth;
            enemyHealth.TakeDamage(maxHealth * 0.6f);

            enemyHealth.ResetHealth();

            Assert.That(enemyHealth.CurrentHealth, Is.EqualTo(maxHealth));
            Assert.That(enemyHealth.IsDefeated, Is.False);
        }

        // AC-004, VAL-003: reset restores a previously-defeated enemy's health and clears
        // IsDefeated, matching floor-restart's owner-controlled reset contract.
        [Test]
        public void ResetHealth_AfterDefeat_RestoresFullHealth_AndClearsDefeatState()
        {
            enemyHealth.TakeDamage(enemyHealth.MaxHealth);
            Assert.That(enemyHealth.IsDefeated, Is.True);

            enemyHealth.ResetHealth();

            Assert.That(enemyHealth.CurrentHealth, Is.EqualTo(enemyHealth.MaxHealth));
            Assert.That(enemyHealth.IsDefeated, Is.False);
        }

        // AC-004, VAL-003: after reset, the same persistent enemy object can be damaged and
        // defeated again through the owner-controlled damage interface.
        [Test]
        public void ResetHealth_ThenTakeDamage_CanReachDefeatTransitionAgain()
        {
            enemyHealth.TakeDamage(enemyHealth.MaxHealth);
            var defeatCount = 0;
            enemyHealth.Defeated += () => defeatCount++;

            enemyHealth.ResetHealth();
            enemyHealth.TakeDamage(enemyHealth.MaxHealth);

            Assert.That(defeatCount, Is.EqualTo(1));
            Assert.That(enemyHealth.IsDefeated, Is.True);
        }
    }
}
