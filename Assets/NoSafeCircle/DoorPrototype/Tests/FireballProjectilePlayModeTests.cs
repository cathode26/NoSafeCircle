using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Play Mode behavior fixture: temporary objects only, no canonical scene or prefab mutation.
    public sealed class FireballProjectilePlayModeTests
    {
        private readonly List<GameObject> objects = new List<GameObject>();

        [TearDown]
        public void TearDown()
        {
            for (int index = objects.Count - 1; index >= 0; index--)
            {
                if (objects[index] != null) Object.DestroyImmediate(objects[index]);
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

        private FireballProjectile MakeShot(Vector3 position)
        {
            return MakeObject("Shot", position).AddComponent<FireballProjectile>();
        }

        private EnemyHealth MakeEnemy(string name, Vector3 position)
        {
            return MakeObject(name, position).AddComponent<EnemyHealth>();
        }

        private GameObject MakeBlockingCollider(Vector3 center, Vector3 size)
        {
            GameObject value = MakeObject("Blocker", center);
            BoxCollider collider = value.AddComponent<BoxCollider>();
            collider.size = size;
            return value;
        }

        private static void AdvanceTicks(FireballProjectile shot, float totalSeconds, float step = 0.1f)
        {
            float elapsed = 0f;
            while (elapsed < totalSeconds && shot.IsFlying)
            {
                float dt = Mathf.Min(step, totalSeconds - elapsed);
                shot.Tick(dt);
                elapsed += dt;
            }
        }

        private DoorInteractable MakeDoor(Vector3 blockerPosition)
        {
            DoorInteractable door = MakeObject("Door", Vector3.zero).AddComponent<DoorInteractable>();
            GameObject doorVisual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            doorVisual.transform.position = blockerPosition;
            objects.Add(doorVisual);
            SetPrivateField(door, "doorVisual", doorVisual);
            SetPrivateField(door, "doorwayBlocker", doorVisual.GetComponent<Collider>());
            return door;
        }

        private static void OpenDoor(DoorInteractable door)
        {
            door.StartInteraction();
            AdvanceDoorTicks(door, door.Duration + 0.1f);
        }

        private void CrossForward(DoorInteractable door)
        {
            GameObject crossingPlayer = MakeObject("CrossingPlayer", Vector3.zero);
            crossingPlayer.AddComponent<PlayerInteractionController>();
            BoxCollider crossingCollider = crossingPlayer.AddComponent<BoxCollider>();
            InvokeForwardCrossingTriggerEnter(door, crossingCollider);
        }

        private static void AdvanceDoorTicks(DoorInteractable door, float totalSeconds)
        {
            const float step = 0.05f;
            float elapsed = 0f;
            while (elapsed < totalSeconds)
            {
                float dt = Mathf.Min(step, totalSeconds - elapsed);
                door.Tick(dt);
                elapsed += dt;
            }
        }

        private static void InvokeForwardCrossingTriggerEnter(DoorInteractable door, Collider other)
        {
            MethodInfo method = door.GetType().GetMethod(
                "HandleForwardCrossingTriggerEnter", BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.That(method, Is.Not.Null,
                "Expected a private HandleForwardCrossingTriggerEnter(Collider) method on DoorInteractable.");
            method.Invoke(door, new object[] { other });
        }

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            FieldInfo field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.That(field, Is.Not.Null, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }

        // AC-001, VAL-001: Tick advances the shot in bounded steps along one straight
        // gameplay-plane line at the configured speed.
        [Test]
        public void Launch_FollowsStraightLineAtConfiguredSpeed()
        {
            FireballProjectile shot = MakeShot(Vector3.zero);
            Vector3 startPosition = new Vector3(1f, 0.8f, -3f);

            shot.Launch(startPosition, new Vector3(1f, 0f, 0f), 5f, 5f, 0.5f, 10f, 0f, null);

            Assert.That(shot.transform.position, Is.EqualTo(startPosition));

            Vector3 previousPosition = shot.transform.position;
            for (int step = 0; step < 4; step++)
            {
                shot.Tick(0.2f);
                Assert.That(shot.IsFlying, Is.True);
                Vector3 currentPosition = shot.transform.position;
                Assert.That(currentPosition.x - previousPosition.x, Is.EqualTo(1f).Within(0.001f),
                    "5 units/sec at 0.2s per tick must advance exactly 1 unit per tick.");
                Assert.That(currentPosition.y, Is.EqualTo(startPosition.y).Within(0.001f),
                    "The shot must stay on the gameplay plane at its launch height.");
                Assert.That(currentPosition.z, Is.EqualTo(startPosition.z).Within(0.001f),
                    "The shot must travel in a single straight line with no lateral drift.");
                previousPosition = currentPosition;
            }
        }

        // AC-001: an aim direction with a vertical component is projected onto the gameplay
        // plane, so the shot can never be aimed at a cursor or ground point in 3D.
        [Test]
        public void Launch_DirectionWithVerticalComponent_TravelsOnlyOnGameplayPlane()
        {
            FireballProjectile shot = MakeShot(Vector3.zero);
            Vector3 startPosition = new Vector3(0f, 1.2f, 0f);

            shot.Launch(startPosition, new Vector3(1f, 5f, 0f), 4f, 1f, 0.5f, 10f, 0f, null);
            shot.Tick(0.25f);

            Assert.That(shot.transform.position.y, Is.EqualTo(1.2f).Within(0.001f),
                "A launch direction with a vertical component must be projected onto the gameplay plane.");
            Assert.That(shot.transform.position.x, Is.EqualTo(1f).Within(0.001f));
        }

        // AC-001, VAL-001: with no contact, the shot destroys itself in place once the supplied
        // maximum lifetime elapses and deals no damage.
        [UnityTest]
        public IEnumerator Lifetime_ElapsesWithoutContact_DestroysShotInPlace_AndDealsNoDamage()
        {
            GameObject shotObject = MakeObject("Shot", Vector3.zero);
            FireballProjectile shot = shotObject.AddComponent<FireballProjectile>();
            EnemyHealth farEnemy = MakeEnemy("FarEnemy", new Vector3(50f, 0f, 50f));
            int damageCount = 0;
            farEnemy.Damaged += _ => damageCount++;

            shot.Launch(new Vector3(2f, 0.5f, 2f), Vector3.right, 3f, 0.5f, 0.5f, 10f, 0f, null);
            shot.Tick(0.5f);

            Assert.That(shot.IsFlying, Is.False,
                "Reaching the configured maximum lifetime without contact must fizzle the shot.");
            Assert.That(damageCount, Is.EqualTo(0), "A fizzled shot must deal no damage.");

            yield return null;

            Assert.That(shotObject == null, Is.True, "A fizzled shot must destroy itself in place.");
        }

        // AC-002, VAL-002: a wall/prop Collider stops the shot, and nothing beyond it takes damage.
        [Test]
        public void SolidCollider_StopsShot_AndDamagesNothingBeyond()
        {
            FireballProjectile shot = MakeShot(Vector3.zero);
            MakeBlockingCollider(new Vector3(3f, 1f, 0f), new Vector3(0.3f, 2f, 2f));
            EnemyHealth beyondEnemy = MakeEnemy("BeyondEnemy", new Vector3(6f, 0f, 0f));

            shot.Launch(Vector3.zero, Vector3.right, 5f, 5f, 0.5f, 10f, 0f, null);
            AdvanceTicks(shot, 3f);

            Assert.That(shot.IsFlying, Is.False, "A wall/prop Collider must stop the shot on contact.");
            Assert.That(beyondEnemy.CurrentHealth, Is.EqualTo(beyondEnemy.MaxHealth),
                "Nothing beyond a blocking Collider may take damage.");
        }

        // AC-002, VAL-002: the caster's own CharacterController never stops its shot.
        [Test]
        public void CasterCollider_NeverStopsItsOwnShot()
        {
            CharacterController caster = MakeObject("Caster", new Vector3(3f, 0.5f, 0f)).AddComponent<CharacterController>();
            FireballProjectile shot = MakeShot(Vector3.zero);
            EnemyHealth enemy = MakeEnemy("Enemy", new Vector3(6f, 0f, 0f));

            shot.Launch(Vector3.zero, Vector3.right, 5f, 5f, 0.5f, 10f, 0f, caster);
            AdvanceTicks(shot, 3f);

            Assert.That(shot.IsFlying, Is.False, "Contact with the enemy beyond the caster must still detonate the shot.");
            Assert.That(enemy.CurrentHealth, Is.EqualTo(enemy.MaxHealth - 10f).Within(0.001f),
                "The caster's own CharacterController must never stop this shot.");
        }

        // AC-002, VAL-002: a sealed door's enabled doorway blocker stops the shot.
        [Test]
        public void SealedDoorwayBlocker_StopsShot()
        {
            DoorInteractable door = MakeDoor(new Vector3(3f, 1f, 0f));
            Assert.That(door.IsOpen, Is.False, "Test setup must keep the door sealed before this assertion.");

            FireballProjectile shot = MakeShot(Vector3.zero);
            EnemyHealth beyondEnemy = MakeEnemy("BeyondEnemy", new Vector3(6f, 0f, 0f));
            shot.Launch(Vector3.zero, Vector3.right, 5f, 5f, 0.5f, 10f, 0f, null);
            AdvanceTicks(shot, 3f);

            Assert.That(shot.IsFlying, Is.False, "An enabled sealed doorway blocker must stop the shot.");
            Assert.That(beyondEnemy.CurrentHealth, Is.EqualTo(beyondEnemy.MaxHealth));
        }

        // AC-002, VAL-002: a locked door's re-enabled doorway blocker stops the shot.
        [Test]
        public void LockedDoorwayBlocker_StopsShot()
        {
            DoorInteractable door = MakeDoor(new Vector3(3f, 1f, 0f));
            OpenDoor(door);
            CrossForward(door);
            Assert.That(door.IsLocked, Is.True, "Test setup must actually lock the door before this assertion.");

            FireballProjectile shot = MakeShot(Vector3.zero);
            EnemyHealth beyondEnemy = MakeEnemy("BeyondEnemy", new Vector3(6f, 0f, 0f));
            shot.Launch(Vector3.zero, Vector3.right, 5f, 5f, 0.5f, 10f, 0f, null);
            AdvanceTicks(shot, 3f);

            Assert.That(shot.IsFlying, Is.False, "An enabled locked doorway blocker must stop the shot.");
            Assert.That(beyondEnemy.CurrentHealth, Is.EqualTo(beyondEnemy.MaxHealth));
        }

        // AC-002, VAL-002: a broken door's still-enabled doorway blocker stops the shot.
        [Test]
        public void BrokenDoorwayBlocker_StopsShot()
        {
            DoorInteractable door = MakeDoor(new Vector3(3f, 1f, 0f));
            OpenDoor(door);
            CrossForward(door);
            door.TakeDamage(door.MaxDurability);
            Assert.That(door.IsBroken, Is.True, "Test setup must actually break the door before this assertion.");

            FireballProjectile shot = MakeShot(Vector3.zero);
            EnemyHealth beyondEnemy = MakeEnemy("BeyondEnemy", new Vector3(6f, 0f, 0f));
            shot.Launch(Vector3.zero, Vector3.right, 5f, 5f, 0.5f, 10f, 0f, null);
            AdvanceTicks(shot, 3f);

            Assert.That(shot.IsFlying, Is.False, "An enabled broken doorway blocker must stop the shot.");
            Assert.That(beyondEnemy.CurrentHealth, Is.EqualTo(beyondEnemy.MaxHealth));
        }

        // AC-002, VAL-002: an open door the wizard has not crossed does not stop the shot.
        [Test]
        public void OpenUncrossedDoorway_DoesNotStopShot()
        {
            DoorInteractable door = MakeDoor(new Vector3(3f, 1f, 0f));
            OpenDoor(door);
            Assert.That(door.IsOpen, Is.True, "Test setup must actually open the door before this assertion.");
            Assert.That(door.HasCrossedForward, Is.False, "Test setup must keep this doorway uncrossed.");

            FireballProjectile shot = MakeShot(Vector3.zero);
            EnemyHealth beyondEnemy = MakeEnemy("BeyondEnemy", new Vector3(6f, 0f, 0f));
            shot.Launch(Vector3.zero, Vector3.right, 5f, 5f, 0.5f, 10f, 0f, null);
            AdvanceTicks(shot, 3f);

            Assert.That(shot.IsFlying, Is.False, "Contact with the enemy beyond the open doorway must still detonate the shot.");
            Assert.That(beyondEnemy.CurrentHealth, Is.EqualTo(beyondEnemy.MaxHealth - 10f).Within(0.001f),
                "An open door the wizard has not crossed must not stop the shot.");
        }

        // AC-002, VAL-002: a Ranged Enemy carrying a caster Component takes Fireball damage like
        // any other enemy. EnemyFireballCaster does not exist in this repository; EnemyLanternWispCaster
        // is the Ranged Enemy caster Component that does.
        [Test]
        public void EnemyCarryingRangedEnemyCaster_TakesDamageLikeAnyOtherEnemy()
        {
            GameObject enemyObject = MakeObject("RangedEnemy", new Vector3(4f, 0f, 0f));
            EnemyHealth enemyHealth = enemyObject.AddComponent<EnemyHealth>();
            EnemyLanternWispCaster caster = enemyObject.AddComponent<EnemyLanternWispCaster>();
            caster.enabled = false;

            FireballProjectile shot = MakeShot(Vector3.zero);
            shot.Launch(Vector3.zero, Vector3.right, 5f, 5f, 0.5f, 10f, 0f, null);
            AdvanceTicks(shot, 3f);

            Assert.That(enemyHealth.CurrentHealth, Is.EqualTo(enemyHealth.MaxHealth - 10f).Within(0.001f),
                "A Ranged Enemy carrying a caster Component must take Fireball damage like any other enemy.");
        }

        // AC-002, VAL-002: contact is tested as flat horizontal distance, so an enemy 1.5 units
        // above the shot but inside the horizontal contact radius still takes damage.
        [Test]
        public void ContactRadius_IgnoresVerticalOffset_ElevatedTargetInsideRadiusTakesDamage()
        {
            EnemyHealth elevatedEnemy = MakeEnemy("ElevatedEnemy", new Vector3(4f, 1.5f, 0.5f));
            FireballProjectile shot = MakeShot(Vector3.zero);

            shot.Launch(Vector3.zero, Vector3.right, 5f, 5f, 1f, 10f, 0f, null);
            AdvanceTicks(shot, 3f);

            Assert.That(shot.IsFlying, Is.False);
            Assert.That(elevatedEnemy.CurrentHealth, Is.EqualTo(elevatedEnemy.MaxHealth - 10f).Within(0.001f),
                "An enemy 1.5 units above the shot but inside the horizontal contact radius must take damage.");
        }

        // AC-002, VAL-002: splash contact is also tested as flat horizontal distance, so an
        // enemy 1.5 units above the detonation point but inside the horizontal area radius still
        // takes damage exactly once.
        [Test]
        public void AreaRadius_IgnoresVerticalOffset_ElevatedTargetInsideAreaTakesSplashDamage()
        {
            EnemyHealth contactEnemy = MakeEnemy("ContactEnemy", new Vector3(4f, 0f, 0f));
            EnemyHealth elevatedSplashEnemy = MakeEnemy("ElevatedSplashEnemy", new Vector3(6f, 1.5f, 1.5f));
            FireballProjectile shot = MakeShot(Vector3.zero);

            shot.Launch(Vector3.zero, Vector3.right, 5f, 5f, 0.5f, 10f, 3f, null);
            AdvanceTicks(shot, 3f);

            Assert.That(shot.IsFlying, Is.False);
            Assert.That(contactEnemy.CurrentHealth, Is.EqualTo(contactEnemy.MaxHealth - 10f).Within(0.001f));
            Assert.That(elevatedSplashEnemy.CurrentHealth, Is.EqualTo(elevatedSplashEnemy.MaxHealth - 10f).Within(0.001f),
                "An enemy 1.5 units above the detonation point but inside the horizontal area radius must take splash damage.");
        }

        // AC-002, VAL-002: a charged-tier detonation damages every unobstructed enemy in its
        // area exactly once, and damages nothing behind a wall even within the area radius.
        [Test]
        public void ChargedDetonation_DamagesEveryUnobstructedEnemyInAreaExactlyOnce_AndSkipsEnemyBehindWall()
        {
            EnemyHealth contactEnemy = MakeEnemy("ContactEnemy", new Vector3(4f, 0f, 0f));
            int contactDamageCount = 0;
            contactEnemy.Damaged += _ => contactDamageCount++;

            EnemyHealth splashEnemy = MakeEnemy("SplashEnemy", new Vector3(5f, 0f, 2f));
            int splashDamageCount = 0;
            splashEnemy.Damaged += _ => splashDamageCount++;

            EnemyHealth shieldedEnemy = MakeEnemy("ShieldedEnemy", new Vector3(3.5f, 0f, -2f));
            int shieldedDamageCount = 0;
            shieldedEnemy.Damaged += _ => shieldedDamageCount++;
            MakeBlockingCollider(new Vector3(3.75f, 1f, -1f), new Vector3(2f, 2f, 1.5f));

            FireballProjectile shot = MakeShot(Vector3.zero);
            shot.Launch(Vector3.zero, Vector3.right, 5f, 5f, 0.5f, 10f, 3f, null);
            AdvanceTicks(shot, 3f);

            Assert.That(contactDamageCount, Is.EqualTo(1), "The directly contacted enemy must be damaged exactly once.");
            Assert.That(splashDamageCount, Is.EqualTo(1),
                "An unobstructed enemy inside the area radius must be damaged exactly once.");
            Assert.That(shieldedDamageCount, Is.EqualTo(0),
                "Damage must not reach an enemy behind a blocking Collider even within the area radius.");
        }
    }
}
