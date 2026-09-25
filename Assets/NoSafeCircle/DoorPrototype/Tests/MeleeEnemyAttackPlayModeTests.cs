using System.Reflection;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.World;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-124 VAL-001/VAL-002: proves MeleeEnemyAttack's integrated behavior against the
    // production NavMeshAgent, EnemyTargetKnowledge (NSC-091), EnemyPursuitMovement (NSC-092),
    // EnemyHealth (NSC-012), and PlayerHealth (NSC-004) on a temporary NavMesh baked by
    // GameplayNavigationSurface (NSC-089). Every object here is created and destroyed by this
    // fixture; nothing here opens, saves, or otherwise touches the committed
    // Assets/Scenes/DoorPrototype.unity scene.
    public sealed class MeleeEnemyAttackPlayModeTests
    {
        private const float DetectionDistance = 6f;
        private const float LoseTargetDistance = 10f;
        private const float AttackRange = 1.5f;
        private const float WindUpSeconds = 0.4f;
        private const float CooldownSeconds = 1f;
        private const float AttackDamage = 12f;

        private static readonly Vector3 EnemySpawnPoint = Vector3.zero;
        private static readonly Vector3 WizardInRangePoint = new Vector3(1f, 0f, 0f);
        private static readonly Vector3 WizardOutOfRangePoint = new Vector3(3f, 0f, 0f);
        private static readonly Vector3 WizardBeyondLoseDistancePoint = new Vector3(20f, 0f, 0f);

        private GameObject root;
        private GameplayNavigationSurface surfaceOwner;
        private GameObject wizardObject;
        private Transform wizardTransform;
        private PlayerHealth health;
        private GameObject enemyObject;
        private NavMeshAgent agent;
        private EnemyTargetKnowledge targetKnowledge;
        private EnemyPursuitMovement pursuitMovement;
        private EnemyHealth enemyHealth;
        private MeleeEnemyAttack attack;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("MeleeEnemyAttackTestRoot");
            BuildOpenFloor();

            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(root.transform, false);
            surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surfaceOwner.ConfigureAndBuild();

            wizardObject = new GameObject("TestWizard");
            wizardObject.transform.SetParent(root.transform, false);
            wizardTransform = wizardObject.transform;
            health = wizardObject.AddComponent<PlayerHealth>();

            Assert.IsTrue(NavMesh.SamplePosition(EnemySpawnPoint, out var spawnHit, 2f, NavMesh.AllAreas),
                "Expected the enemy spawn point to sample onto the baked open test floor.");

            enemyObject = new GameObject("TestMeleeEnemy");
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

            enemyHealth = enemyObject.AddComponent<EnemyHealth>();
            pursuitMovement = enemyObject.AddComponent<EnemyPursuitMovement>();

            attack = enemyObject.AddComponent<MeleeEnemyAttack>();
            SetSerialized(attack, "attackRange", AttackRange);
            SetSerialized(attack, "windUpSeconds", WindUpSeconds);
            SetSerialized(attack, "cooldownSeconds", CooldownSeconds);
            SetSerialized(attack, "attackDamage", AttackDamage);
        }

        [TearDown]
        public void TearDown()
        {
            if (surfaceOwner != null) surfaceOwner.ClearBakedData();
            if (root != null) Object.DestroyImmediate(root);
        }

        private void BuildOpenFloor()
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.name = "TestGameplayFloor";
            floor.transform.SetParent(root.transform, false);
            floor.transform.position = Vector3.zero;
            floor.transform.localScale = new Vector3(24f, 0.1f, 24f);
        }

        private static void SetSerialized(object component, string name, object value)
        {
            FieldInfo field = component.GetType().GetField(name, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.That(field, Is.Not.Null, $"Serialized field {name} must exist");
            field.SetValue(component, value);
        }

        private void Step(float seconds)
        {
            pursuitMovement.Tick(seconds);
            attack.Tick(seconds);
        }

        // AC-001, VAL-001: a pursued target outside the close attack range never starts a wind-up
        // and never receives damage.
        [Test]
        public void OutOfRange_WhilePursuing_NeverStartsWindUpOrDamages()
        {
            int damageCalls = 0;
            health.Damaged += _ => damageCalls++;
            wizardTransform.position = WizardOutOfRangePoint;

            Step(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Idle));

            Step(WindUpSeconds + CooldownSeconds + 1f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Idle));
            Assert.That(damageCalls, Is.EqualTo(0));
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
        }

        // AC-001, AC-002, VAL-001: a valid close-range target winds up, then impacts exactly
        // once with the configured damage, with no further per-frame contact damage during the
        // ensuing cooldown.
        [Test]
        public void ValidImpact_AppliesConfiguredDamageExactlyOnce_ThenCooldownAppliesNoFurtherDamage()
        {
            int damageCalls = 0;
            health.Damaged += _ => damageCalls++;
            wizardTransform.position = WizardInRangePoint;

            Step(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));

            Step(WindUpSeconds);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Cooldown));
            Assert.That(damageCalls, Is.EqualTo(1));
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth - AttackDamage));

            Step(CooldownSeconds * 0.5f);
            Assert.That(damageCalls, Is.EqualTo(1));
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth - AttackDamage));

            Step(CooldownSeconds * 0.5f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Idle));
            Assert.That(damageCalls, Is.EqualTo(1));
        }

        // AC-001, VAL-001: the target leaving the attack range mid wind-up cancels the cycle
        // without damage, and a later valid cycle can still begin normally.
        [Test]
        public void TargetLeavesRangeDuringWindUp_CancelsWithoutDamage_ThenLaterCycleCanComplete()
        {
            int damageCalls = 0;
            health.Damaged += _ => damageCalls++;
            wizardTransform.position = WizardInRangePoint;

            Step(0f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));

            wizardTransform.position = WizardOutOfRangePoint;
            Step(WindUpSeconds);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Idle));
            Assert.That(damageCalls, Is.EqualTo(0));

            wizardTransform.position = WizardInRangePoint;
            Step(0f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));
            Step(WindUpSeconds);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Cooldown));
            Assert.That(damageCalls, Is.EqualTo(1));
        }

        // AC-001, VAL-001: losing the Pursuing state (target beyond Lose Target Distance) mid
        // wind-up cancels the cycle without damage.
        [Test]
        public void PursuitLostDuringWindUp_CancelsWithoutDamage()
        {
            int damageCalls = 0;
            health.Damaged += _ => damageCalls++;
            wizardTransform.position = WizardInRangePoint;

            Step(0f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));

            wizardTransform.position = WizardBeyondLoseDistancePoint;
            Step(WindUpSeconds);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Idle));
            Assert.That(damageCalls, Is.EqualTo(0));
        }

        // AC-001, VAL-001: a defeated melee enemy never starts a wind-up, and one that is
        // defeated mid wind-up cancels the cycle without damage.
        [Test]
        public void EnemyHealthDefeated_NeverStartsAttack_AndCancelsAnInFlightWindUpWithoutDamage()
        {
            int damageCalls = 0;
            health.Damaged += _ => damageCalls++;
            wizardTransform.position = WizardInRangePoint;

            enemyHealth.TakeDamage(enemyHealth.MaxHealth);
            Assert.That(enemyHealth.IsDefeated, Is.True);

            Step(WindUpSeconds + CooldownSeconds + 1f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Idle));
            Assert.That(damageCalls, Is.EqualTo(0));

            enemyHealth.ResetHealth();
            Step(0f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));

            enemyHealth.TakeDamage(enemyHealth.MaxHealth);
            Step(WindUpSeconds);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Idle));
            Assert.That(damageCalls, Is.EqualTo(0));
        }

        // AC-001: impact rechecks that the target at wind-up start is still the current target;
        // a target swapped mid wind-up through EnemyTargetKnowledge's own production redirect
        // entry point completes the swipe without damage.
        [Test]
        public void CurrentTargetRedirectedDuringWindUp_ImpactRechecksSameTargetAndSkipsDamage()
        {
            int damageCalls = 0;
            health.Damaged += _ => damageCalls++;
            wizardTransform.position = WizardInRangePoint;

            GameObject decoy = new GameObject("Decoy");
            decoy.transform.SetParent(root.transform, false);
            decoy.transform.position = WizardInRangePoint;

            Step(0f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));

            Assert.IsTrue(targetKnowledge.TryRedirectToSpectralDecoy(decoy.transform));
            Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(decoy.transform));

            Step(WindUpSeconds);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Cooldown));
            Assert.That(damageCalls, Is.EqualTo(0));
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
        }

        // AC-002: a close current target without PlayerHealth (e.g. a Spectral Decoy) remains
        // active and unchanged, and completing a swipe against it produces no exception or
        // damage.
        [Test]
        public void CloseCurrentTargetWithoutPlayerHealth_RemainsUnchangedAndProducesNoDamage()
        {
            Object.DestroyImmediate(health);
            health = null;
            wizardTransform.position = WizardInRangePoint;
            int originalInstanceId = wizardObject.GetInstanceID();

            Assert.DoesNotThrow(() => Step(0f));
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));
            Assert.DoesNotThrow(() => Step(WindUpSeconds));
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Cooldown));

            Assert.That(wizardObject, Is.Not.Null);
            Assert.That(wizardObject.GetInstanceID(), Is.EqualTo(originalInstanceId));
            Assert.That(wizardObject.activeInHierarchy, Is.True);
            Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(wizardTransform));
        }

        // AC-003, VAL-002: ResetAttack during early wind-up returns to idle, prevents the
        // cancelled cycle's delayed damage, and permits a later valid cycle to complete normally.
        [Test]
        public void ResetAttack_DuringEarlyWindUp_ReturnsToIdleAndLaterCycleCompletes()
        {
            int damageCalls = 0;
            health.Damaged += _ => damageCalls++;
            wizardTransform.position = WizardInRangePoint;

            Step(0.1f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));

            attack.ResetAttack();
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Idle));

            // The reset cancels the pending cycle, so a fresh one restarts at the full
            // windUpSeconds; this partial step proves no delayed damage arrives from the
            // cancelled cycle before the later cycle it starts has a chance to complete.
            Step(0.2f);
            Assert.That(damageCalls, Is.EqualTo(0),
                "Expected no delayed damage from the cancelled wind-up.");
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));

            Step(0.2f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Cooldown));
            Assert.That(damageCalls, Is.EqualTo(1));
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth - AttackDamage));
        }

        // AC-003, VAL-002: ResetAttack called immediately before the scheduled impact cancels
        // the pending impact, prevents delayed damage, and a later valid cycle still completes.
        [Test]
        public void ResetAttack_ImmediatelyBeforeScheduledImpact_PreventsPendingDamage_ThenLaterCycleCompletes()
        {
            int damageCalls = 0;
            health.Damaged += _ => damageCalls++;
            wizardTransform.position = WizardInRangePoint;

            Step(0.3f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp),
                "Expected the wind-up to still be pending, immediately before its scheduled impact.");

            attack.ResetAttack();
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Idle));

            // The reset cancels the pending impact, so a fresh cycle restarts at the full
            // windUpSeconds; this partial step proves the cancelled cycle's impact never fires
            // before the later cycle it starts has a chance to complete.
            Step(0.2f);
            Assert.That(damageCalls, Is.EqualTo(0),
                "Expected no delayed damage from the impact pending at reset time.");
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));

            Step(0.2f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Cooldown));
            Assert.That(damageCalls, Is.EqualTo(1));
        }

        // AC-003, VAL-002: ResetAttack during cooldown clears the cooldown and idles
        // immediately, allowing a new valid cycle to begin without waiting out the original
        // cooldown.
        [Test]
        public void ResetAttack_DuringCooldown_ClearsCooldownAndAllowsImmediateNewCycle()
        {
            int damageCalls = 0;
            health.Damaged += _ => damageCalls++;
            wizardTransform.position = WizardInRangePoint;

            Step(0f);
            Step(WindUpSeconds);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Cooldown));
            Assert.That(damageCalls, Is.EqualTo(1));

            attack.ResetAttack();
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Idle));

            Step(0f);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.WindingUp));
            Step(WindUpSeconds);
            Assert.That(attack.Phase, Is.EqualTo(MeleeAttackPhase.Cooldown));
            Assert.That(damageCalls, Is.EqualTo(2));
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth - (AttackDamage * 2f)));
        }
    }
}
