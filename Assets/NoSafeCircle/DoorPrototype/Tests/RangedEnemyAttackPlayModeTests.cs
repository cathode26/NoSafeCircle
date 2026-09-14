using System;
using System.Collections.Generic;
using System.Reflection;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Play Mode behavior fixture: temporary objects, no canonical scene or prefab mutation.
    public sealed class RangedEnemyAttackPlayModeTests
    {
        private readonly List<GameObject> objects = new List<GameObject>();
        private GameObject enemy;
        private GameObject wizard;
        private GameObject feedback;
        private EnemyTargetKnowledge knowledge;
        private RangedEnemyAttack attack;
        private RangedEnemyProjectile template;
        private PlayerHealth health;

        [SetUp]
        public void SetUp()
        {
            enemy = MakeObject("Ranged Enemy", Vector3.zero);
            knowledge = enemy.AddComponent<EnemyTargetKnowledge>();
            wizard = MakeObject("Wizard", new Vector3(4f, 0.8f, 0f));
            health = wizard.AddComponent<PlayerHealth>();
            BoxCollider playerCollider = wizard.AddComponent<BoxCollider>();
            playerCollider.size = new Vector3(0.5f, 2f, 0.5f);
            knowledge.Initialize(wizard.transform);
            knowledge.ConfigureDistances(6f, 10f);

            GameObject origin = MakeObject("Projectile Origin", new Vector3(0f, 0.8f, 0f));
            origin.transform.SetParent(enemy.transform, true);
            feedback = MakePrimitive("Wind-up feedback", new Vector3(0f, 1.2f, 0f));
            feedback.transform.SetParent(enemy.transform, true);
            UnityEngine.Object.DestroyImmediate(feedback.GetComponent<Collider>());
            feedback.SetActive(false);

            GameObject templateObject = MakePrimitive("Projectile template", new Vector3(100f, 100f, 100f));
            templateObject.transform.localScale = Vector3.one * 0.1f;
            UnityEngine.Object.DestroyImmediate(templateObject.GetComponent<Collider>());
            template = templateObject.AddComponent<RangedEnemyProjectile>();
            SetSerialized(template, "speed", 3f);
            SetSerialized(template, "lifetimeSeconds", 5f);
            SetSerialized(template, "damage", 10f);
            templateObject.SetActive(false);

            attack = enemy.AddComponent<RangedEnemyAttack>();
            SetSerialized(attack, "targetKnowledge", knowledge);
            SetSerialized(attack, "projectileTemplate", template);
            SetSerialized(attack, "projectileOrigin", origin.transform);
            SetSerialized(attack, "windUpFeedback", feedback);
            SetSerialized(attack, "windUpSeconds", 0.4f);
            SetSerialized(attack, "cooldownSeconds", 1f);
        }

        [TearDown]
        public void TearDown()
        {
            foreach (RangedEnemyProjectile projectile in
                UnityEngine.Object.FindObjectsByType<RangedEnemyProjectile>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (projectile != null) UnityEngine.Object.DestroyImmediate(projectile.gameObject);
            }
            for (int index = objects.Count - 1; index >= 0; index--)
            {
                if (objects[index] != null) UnityEngine.Object.DestroyImmediate(objects[index]);
            }
            objects.Clear();
        }

        private GameObject MakeObject(string name, Vector3 position)
        {
            GameObject value = new GameObject(name);
            value.transform.position = position;
            objects.Add(value);
            return value;
        }

        private GameObject MakePrimitive(string name, Vector3 position)
        {
            GameObject value = GameObject.CreatePrimitive(PrimitiveType.Cube);
            value.name = name;
            value.transform.position = position;
            objects.Add(value);
            return value;
        }

        private static void SetSerialized(object component, string name, object value)
        {
            FieldInfo field = component.GetType().GetField(name, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.That(field, Is.Not.Null, $"Serialized field {name} must exist");
            field.SetValue(component, value);
        }

        private void Step(float seconds)
        {
            knowledge.UpdateTargetKnowledge(seconds);
            attack.Tick(seconds);
        }

        private RangedEnemyProjectile Launch()
        {
            Step(0.2f);
            Assert.That(attack.IsWindingUp, Is.True);
            Step(0.2f);
            RangedEnemyProjectile projectile = ActiveProjectile();
            Assert.That(projectile, Is.Not.Null);
            return projectile;
        }

        private RangedEnemyProjectile ActiveProjectile()
        {
            foreach (RangedEnemyProjectile projectile in
                UnityEngine.Object.FindObjectsByType<RangedEnemyProjectile>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (projectile != template && projectile.IsFlying) return projectile;
            }
            return null;
        }

        private static BoxCollider MakeCover(GameObject value, float top, bool isTrigger)
        {
            BoxCollider collider = value.AddComponent<BoxCollider>();
            collider.size = new Vector3(0.3f, top, 1f);
            collider.isTrigger = isTrigger;
            return collider;
        }

        // VAL-001, VAL-005: acquired target, visible wind-up, multi-step flight, exact health contact.
        [Test]
        public void AcquiredWizard_WindsUpThenProjectileMovesAndDamagesOnce()
        {
            int damageCalls = 0;
            health.Damaged += _ => damageCalls++;

            Step(0.2f);
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(attack.IsWindingUp, Is.True);
            Assert.That(feedback.activeSelf, Is.True);
            Assert.That(feedback.GetComponent<Renderer>().enabled, Is.True);
            Assert.That(ActiveProjectile(), Is.Null);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));

            Step(0.2f);
            RangedEnemyProjectile projectile = ActiveProjectile();
            Assert.That(projectile, Is.Not.Null);
            Assert.That(projectile.GetComponent<Renderer>().enabled, Is.True);
            Assert.That(attack.IsWindingUp, Is.False);
            Assert.That(feedback.activeSelf, Is.False);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));

            float firstX = projectile.transform.position.x;
            projectile.Tick(0.1f);
            Assert.That(projectile.transform.position.x, Is.GreaterThan(firstX));
            float secondX = projectile.transform.position.x;
            projectile.Tick(0.1f);
            Assert.That(projectile.transform.position.x, Is.GreaterThan(secondX));
            projectile.Tick(2f);
            Assert.That(projectile.IsFlying, Is.False);
            Assert.That(damageCalls, Is.EqualTo(1));
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth - 10f));
            projectile.Tick(2f);
            Assert.That(damageCalls, Is.EqualTo(1));
        }

        // VAL-002, VAL-006: a short pew blocks a full large step without clearing pursuit.
        [Test]
        public void PewCover_BlocksProjectileButNotPursuit_ThenNextShotCanHit()
        {
            GameObject cover = MakeObject("Pew cover", new Vector3(2f, 0.625f, 0f));
            MakeCover(cover, 1.25f, false);
            RangedEnemyProjectile first = Launch();
            first.Tick(2f);
            Assert.That(first.IsFlying, Is.False);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(knowledge.CurrentTarget, Is.SameAs(wizard.transform));

            UnityEngine.Object.DestroyImmediate(cover);
            Step(1f);
            RangedEnemyProjectile second = Launch();
            second.Tick(2f);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth - 10f));
        }

        // VAL-002: trigger volumes are ignored by the whole-segment collision query.
        [Test]
        public void TriggerCover_DoesNotStopProjectile()
        {
            GameObject trigger = MakeObject("Trigger", new Vector3(2f, 0.625f, 0f));
            MakeCover(trigger, 1.25f, true);
            RangedEnemyProjectile projectile = Launch();
            projectile.Tick(0.8f);
            Assert.That(projectile.IsFlying, Is.True);
            Assert.That(projectile.transform.position.x, Is.GreaterThan(2f));
            projectile.Tick(1f);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth - 10f));
        }

        // AC-003: only the exact GameObject carrying PlayerHealth can receive damage.
        [Test]
        public void ChildColliderOfPlayer_IsNeitherDamageTargetNorCover()
        {
            wizard.GetComponent<BoxCollider>().enabled = false;
            GameObject child = MakeObject("Player child collider", new Vector3(4f, 0.8f, 0f));
            child.transform.SetParent(wizard.transform, true);
            MakeCover(child, 1f, false);
            RangedEnemyProjectile projectile = Launch();
            projectile.Tick(2f);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
        }

        // AC-003: another enemy body is not cover and cannot take friendly fire.
        [Test]
        public void OtherEnemyCollider_IsIgnored()
        {
            GameObject otherEnemy = MakeObject("Other enemy", new Vector3(2f, 0.8f, 0f));
            otherEnemy.AddComponent<EnemyTargetKnowledge>();
            MakeCover(otherEnemy, 1f, false);
            RangedEnemyProjectile projectile = Launch();
            projectile.Tick(2f);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth - 10f));
        }

        // AC-002: a collider moved between two ticks in one frame must be swept on the next tick.
        [Test]
        public void ConsecutiveTicks_DetectNewCoverWithoutPhysicsFrame()
        {
            RangedEnemyProjectile projectile = Launch();
            projectile.Tick(0.4f);
            GameObject cover = MakeObject("Moved pew", new Vector3(10f, 0.625f, 0f));
            MakeCover(cover, 1.25f, false);
            cover.transform.position = new Vector3(projectile.transform.position.x, 0.625f, 0f);
            projectile.Tick(0.4f);
            Assert.That(projectile.IsFlying, Is.False);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
        }

        // VAL-007: launch direction is a snapshot, so lateral movement avoids a slow shot.
        [Test]
        public void PlayerSidestepsAfterLaunch_ProjectileDoesNotHome()
        {
            RangedEnemyProjectile projectile = Launch();
            wizard.transform.position += new Vector3(0f, 0f, 2f);
            projectile.Tick(2f);
            Assert.That(projectile.transform.position.z, Is.EqualTo(0f).Within(0.001f));
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
        }

        // VAL-008: target knowledge alone decides loss and later reacquisition.
        [Test]
        public void TargetLostDuringWindUp_CancelsWithoutChangingSearchState()
        {
            Step(0.2f);
            wizard.transform.position = new Vector3(11f, 0.8f, 0f);
            Step(0.2f);
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
            Assert.That(attack.IsWindingUp, Is.False);
            Assert.That(feedback.activeSelf, Is.False);
            Assert.That(ActiveProjectile(), Is.Null);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
            wizard.transform.position = new Vector3(4f, 0.8f, 0f);
            Step(0.2f);
            Assert.That(knowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(attack.IsWindingUp, Is.True);
        }

        // AC-001: an unwired attack never starts or damages, even if knowledge exists elsewhere.
        [Test]
        public void MissingTargetKnowledge_DoesNotStartAttack()
        {
            SetSerialized(attack, "targetKnowledge", null);
            Step(1f);
            Assert.That(attack.IsWindingUp, Is.False);
            Assert.That(feedback.activeSelf, Is.False);
            Assert.That(ActiveProjectile(), Is.Null);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
        }

        // VAL-004: reset removes pending and already launched damage, then restores initial timing.
        [Test]
        public void ResetDuringWindUpAndFlight_CancelsAndRestartsAtInitialTiming()
        {
            Step(0.2f);
            attack.ResetAttack();
            Assert.That(attack.IsWindingUp, Is.False);
            Assert.That(feedback.activeSelf, Is.False);
            Step(0.2f);
            Assert.That(attack.IsWindingUp, Is.True);
            Assert.That(ActiveProjectile(), Is.Null);
            Step(0.2f);
            RangedEnemyProjectile projectile = ActiveProjectile();
            Assert.That(projectile, Is.Not.Null);
            attack.ResetAttack();
            Assert.That(projectile.IsFlying, Is.False);
            projectile.Tick(2f);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
            Step(0.2f);
            Assert.That(attack.IsWindingUp, Is.True);
            Assert.That(ActiveProjectile(), Is.Null);
        }

        // VAL-009: disabling or destroying the owner invalidates all in-flight shots.
        [Test]
        public void DisableAndDestroyOwner_RemoveFeedbackAndOwnedProjectiles()
        {
            Step(0.2f);
            attack.enabled = false;
            Assert.That(attack.IsWindingUp, Is.False);
            Assert.That(feedback.activeSelf, Is.False);
            Step(1f);
            Assert.That(ActiveProjectile(), Is.Null);

            attack.enabled = true;
            RangedEnemyProjectile projectile = Launch();
            attack.enabled = false;
            Assert.That(projectile.IsFlying, Is.False);
            projectile.Tick(2f);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));

            attack.enabled = true;
            RangedEnemyProjectile next = Launch();
            UnityEngine.Object.DestroyImmediate(enemy);
            Assert.That(next.IsFlying, Is.False);
            next.Tick(2f);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
        }

        // VAL-003: Frost changes NavMeshAgent speed, not attack or projectile clocks.
        [Test]
        public void FrostSlowdown_LeavesWindUpCooldownSpeedAndLifetimeUnchanged()
        {
            NavMeshAgent agent = enemy.AddComponent<NavMeshAgent>();
            float baselineSpeed = agent.speed;
            EnemyStatusEffectMovement frost = enemy.AddComponent<EnemyStatusEffectMovement>();
            RangedEnemyProjectile normal = Launch();
            normal.Tick(0.2f);
            float normalDistance = normal.transform.position.x;
            wizard.transform.position += new Vector3(0f, 0f, 2f);
            normal.Tick(4.8f);
            Assert.That(normal.IsFlying, Is.False);

            wizard.transform.position -= new Vector3(0f, 0f, 2f);
            Step(0.5f);
            Assert.That(attack.IsWindingUp, Is.False);
            Step(0.5f);
            Assert.That(attack.IsWindingUp, Is.False);
            Step(0.1f);
            Assert.That(attack.IsWindingUp, Is.True);

            attack.ResetAttack();
            frost.ApplyFrostSlowdown(0.5f, 20f);
            Assert.That(agent.speed, Is.EqualTo(baselineSpeed * 0.5f).Within(0.001f));
            RangedEnemyProjectile slowed = Launch();
            slowed.Tick(0.2f);
            Assert.That(slowed.transform.position.x, Is.EqualTo(normalDistance).Within(0.001f));
            wizard.transform.position += new Vector3(0f, 0f, 2f);
            slowed.Tick(4.8f);
            Assert.That(slowed.IsFlying, Is.False);
            wizard.transform.position -= new Vector3(0f, 0f, 2f);
            Step(0.5f);
            Assert.That(attack.IsWindingUp, Is.False);
            Step(0.5f);
            Assert.That(attack.IsWindingUp, Is.False);
            Step(0.1f);
            Assert.That(attack.IsWindingUp, Is.True);
            Assert.That(frost.IsFrostSlowdownActive, Is.True);
        }

        // AC-002/AC-003: explicit Launch rejects an unowned shot.
        [Test]
        public void ProjectileLaunch_RequiresOwner()
        {
            Assert.Throws<ArgumentNullException>(() => template.Launch(Vector3.zero, Vector3.right, null));
        }

        // INT-001/AC-006: a room test may call Launch directly; reset still owns that shot.
        [Test]
        public void DirectLaunch_IsRegisteredWithOwnerAndResetRemovesIt()
        {
            GameObject projectileObject = MakePrimitive("Direct room-test shot", Vector3.zero);
            UnityEngine.Object.DestroyImmediate(projectileObject.GetComponent<Collider>());
            RangedEnemyProjectile projectile = projectileObject.AddComponent<RangedEnemyProjectile>();
            projectile.Launch(new Vector3(0f, 0.8f, 0f), Vector3.right, attack);
            Assert.That(projectile.IsFlying, Is.True);
            attack.ResetAttack();
            Assert.That(projectile.IsFlying, Is.False);
            projectile.Tick(2f);
            Assert.That(health.CurrentHealth, Is.EqualTo(health.MaxHealth));
        }
    }
}
