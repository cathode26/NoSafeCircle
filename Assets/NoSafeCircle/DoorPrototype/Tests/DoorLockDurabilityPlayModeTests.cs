using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class DoorLockDurabilityPlayModeTests
    {
        private GameObject doorObject;
        private GameObject doorVisual;
        private Collider doorwayBlocker;
        private GameObject playerObject;
        private DoorInteractable door;
        private PlayerInteractionController controller;
        private PlayerHealth health;
        private BoxCollider playerCollider;

        [SetUp]
        public void SetUp()
        {
            doorObject = new GameObject("TestDoor");
            door = doorObject.AddComponent<DoorInteractable>();

            doorVisual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            doorwayBlocker = doorVisual.GetComponent<Collider>();
            SetPrivateField(door, "doorVisual", doorVisual);
            SetPrivateField(door, "doorwayBlocker", doorwayBlocker);

            playerObject = new GameObject("TestPlayer");
            health = playerObject.AddComponent<PlayerHealth>();
            controller = playerObject.AddComponent<PlayerInteractionController>();
            playerCollider = playerObject.AddComponent<BoxCollider>();

            controller.NotifyDoorInRange(door);
        }

        [TearDown]
        public void TearDown()
        {
            Object.Destroy(playerObject);
            Object.Destroy(doorVisual);
            Object.Destroy(doorObject);
        }

        // AC-004: damage requested while the door is still sealed (never locked) must be
        // rejected and must not reduce durability or break the door.
        [UnityTest]
        public IEnumerator TakeDamage_WhileSealed_IsRejected()
        {
            Assert.IsFalse(door.IsLocked, "Test setup must keep the door sealed before this assertion.");

            door.TakeDamage(10f);

            yield return null;

            Assert.AreEqual(door.MaxDurability, door.CurrentDurability, 0.001f,
                "Damage requested while the door is sealed must not reduce durability.");
            Assert.IsFalse(door.IsBroken);
        }

        // AC-004: damage requested while the door is open but has not yet auto-locked (the
        // wizard has not yet crossed to the forward side) must also be rejected.
        [UnityTest]
        public IEnumerator TakeDamage_WhileOpenButNotLocked_IsRejected()
        {
            OpenDoor();
            yield return null;

            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before this assertion.");
            Assert.IsFalse(door.IsLocked);

            door.TakeDamage(10f);

            yield return null;

            Assert.AreEqual(door.MaxDurability, door.CurrentDurability, 0.001f,
                "Damage requested before automatic locking must not reduce durability.");
            Assert.IsFalse(door.IsBroken);
        }

        // AC-001/AC-003: forward-side crossing automatically closes and locks the door without
        // any second player input, re-enabling the doorway blocker so it prevents backward
        // player movement.
        [UnityTest]
        public IEnumerator ForwardCrossing_AutomaticallyLocksDoor_WithoutSecondInput()
        {
            OpenDoor();
            yield return null;

            var lockedFireCount = 0;
            door.Locked += () => lockedFireCount++;

            CrossForward();

            yield return null;

            Assert.IsTrue(door.IsLocked,
                "Reaching the forward-crossing trigger on an open door must automatically close and lock it.");
            Assert.AreEqual(1, lockedFireCount, "Locked must fire exactly once.");
            Assert.IsTrue(doorVisual.activeSelf, "The door must be visibly closed once locked.");
            Assert.IsTrue(doorwayBlocker.enabled,
                "The doorway blocker must be re-enabled so it prevents backward player movement.");
        }

        // AC-002: completing the automatic close-and-lock requests the configured fixed recovery
        // amount through Player Health's own owner-controlled Restore method rather than editing
        // Player Health fields directly.
        [UnityTest]
        public IEnumerator ForwardCrossing_RestoresPlayerHealth_ThroughOwnerControlledRestore()
        {
            var maxHealth = health.MaxHealth;
            health.TakeDamage(maxHealth * 0.5f);
            var damagedHealth = health.CurrentHealth;
            var expectedRestoreAmount = GetPrivateFloat(door, "healthRestoreAmount");

            OpenDoor();
            yield return null;

            CrossForward();

            yield return null;

            Assert.AreEqual(Mathf.Min(maxHealth, damagedHealth + expectedRestoreAmount), health.CurrentHealth, 0.001f,
                "Locking must request exactly the configured fixed recovery amount through Player Health's " +
                "Restore method.");
        }

        // AC-003: the player cannot reopen or unlock a door that has already automatically
        // locked; a repeated interaction attempt is rejected because the door still reports
        // itself open.
        [UnityTest]
        public IEnumerator StartInteraction_AfterLocked_DoesNotReopenDoor()
        {
            OpenDoor();
            yield return null;
            CrossForward();
            yield return null;

            Assert.IsTrue(door.IsLocked, "Test setup must actually lock the door before this assertion.");

            door.StartInteraction();

            yield return null;

            Assert.IsFalse(door.IsInteracting,
                "A locked door must reject a repeated interaction attempt; the player cannot reopen or unlock it.");
            Assert.IsTrue(door.IsLocked);
        }

        // AC-004: while locked, accepted damage reduces current durability but does not yet
        // break the door while durability remains above zero.
        [UnityTest]
        public IEnumerator TakeDamage_WhileLocked_ReducesDurability()
        {
            OpenDoor();
            yield return null;
            CrossForward();
            yield return null;

            var maxDurability = door.MaxDurability;
            var damage = maxDurability * 0.3f;

            door.TakeDamage(damage);

            yield return null;

            Assert.AreEqual(maxDurability - damage, door.CurrentDurability, 0.001f,
                "Accepted damage while locked must reduce current durability by the requested amount.");
            Assert.IsFalse(door.IsBroken);
            Assert.IsTrue(door.IsLocked);
        }

        // AC-004/AC-005: repeated accepted damage that reduces durability to zero breaks the
        // door, transitioning it from locked to broken exactly once.
        [UnityTest]
        public IEnumerator TakeDamage_ReducingDurabilityToZero_BreaksDoor()
        {
            OpenDoor();
            yield return null;
            CrossForward();
            yield return null;

            var brokenFireCount = 0;
            door.Broken += () => brokenFireCount++;

            var perHit = door.MaxDurability / 4f;
            for (var i = 0; i < 4; i++)
            {
                door.TakeDamage(perHit);
                yield return null;
            }

            Assert.AreEqual(0f, door.CurrentDurability, 0.001f);
            Assert.IsTrue(door.IsBroken, "Durability reaching zero must break the door.");
            Assert.IsFalse(door.IsLocked, "A broken door is no longer locked.");
            Assert.AreEqual(1, brokenFireCount, "Broken must fire exactly once.");
        }

        // AC-004: damage requested against an already-broken door is rejected and does not
        // change durability further or fire another state transition.
        [UnityTest]
        public IEnumerator TakeDamage_AfterBroken_IsRejected()
        {
            OpenDoor();
            yield return null;
            CrossForward();
            yield return null;

            door.TakeDamage(door.MaxDurability);
            yield return null;

            Assert.IsTrue(door.IsBroken, "Test setup must actually break the door before this assertion.");

            var brokenFireCount = 0;
            door.Broken += () => brokenFireCount++;

            door.TakeDamage(10f);

            yield return null;

            Assert.AreEqual(0f, door.CurrentDurability, 0.001f,
                "Damage requested against an already-broken door must not change durability further.");
            Assert.AreEqual(0, brokenFireCount, "Broken must not fire again for an already-broken door.");
        }

        // AC-005: a broken door remains broken/open and its blocker continues preventing
        // backward player travel; it cannot return to locked or an earlier semantic state
        // during this run.
        [UnityTest]
        public IEnumerator BrokenDoor_RemainsBroken_AndBlockerContinuesPreventingBackwardTravel()
        {
            OpenDoor();
            yield return null;
            CrossForward();
            yield return null;

            door.TakeDamage(door.MaxDurability);
            yield return null;

            Assert.IsTrue(door.IsBroken, "Test setup must actually break the door before this assertion.");
            Assert.IsTrue(doorwayBlocker.enabled,
                "The doorway blocker must continue preventing backward player travel after the door breaks.");

            InvokeCloseAndLock(door, null);

            yield return null;

            Assert.IsFalse(door.IsLocked, "A broken door must never become locked again during the current run.");
            Assert.IsTrue(door.IsBroken);
        }

        // AC-006/AC-007: the owner-controlled reset entry point restores locked/broken state
        // and current durability to the serialized maximum, alongside sealed geometry and the
        // doorway blocker.
        [UnityTest]
        public IEnumerator ResetDoor_RestoresLockBrokenAndDurabilityState()
        {
            OpenDoor();
            yield return null;
            CrossForward();
            yield return null;

            door.TakeDamage(door.MaxDurability);
            yield return null;

            Assert.IsTrue(door.IsBroken, "Test setup must actually break the door before reset.");

            door.ResetDoor();

            yield return null;

            Assert.IsFalse(door.IsLocked);
            Assert.IsFalse(door.IsBroken);
            Assert.AreEqual(door.MaxDurability, door.CurrentDurability, 0.001f,
                "Reset must restore current durability to the serialized maximum.");
            Assert.IsFalse(door.IsOpen);
            Assert.IsTrue(doorVisual.activeSelf);
            Assert.IsTrue(doorwayBlocker.enabled);
        }

        // AC-007: DoorInteractable exposes a serialized per-door maximum durability that level
        // authoring can configure; current durability follows that configured maximum.
        [UnityTest]
        public IEnumerator MaxDurability_IsPerDoorConfigurable_AndCurrentDurabilityFollowsIt()
        {
            SetPrivateField(door, "maxDurability", 250f);

            door.ResetDoor();

            yield return null;

            Assert.AreEqual(250f, door.MaxDurability, 0.001f);
            Assert.AreEqual(250f, door.CurrentDurability, 0.001f,
                "Current durability must follow the serialized per-door maximum after reset.");
        }

        // VAL-001: damage calls made before the door locks are rejected; crossing an open door
        // then automatically locks it and blocks backward player movement; repeated accepted
        // damage eventually breaks the door; further damage calls are then rejected; and the
        // player still cannot move backward through the resulting broken doorway.
        [UnityTest]
        public IEnumerator DoorLockDurabilityFlow_MatchesFullBreachGate()
        {
            door.TakeDamage(10f);
            yield return null;
            Assert.AreEqual(door.MaxDurability, door.CurrentDurability, 0.001f,
                "Damage before the door ever locks must be rejected.");

            OpenDoor();
            yield return null;
            CrossForward();
            yield return null;

            Assert.IsTrue(door.IsLocked, "Crossing an open door must automatically lock it.");
            Assert.IsTrue(doorwayBlocker.enabled,
                "The locked door's blocker must prevent backward player movement.");

            var perHit = door.MaxDurability / 4f;
            for (var i = 0; i < 4; i++)
            {
                door.TakeDamage(perHit);
                yield return null;
            }

            Assert.IsTrue(door.IsBroken, "Repeated accepted damage must break the door.");

            door.TakeDamage(10f);
            yield return null;

            Assert.AreEqual(0f, door.CurrentDurability, 0.001f,
                "Further damage calls against a broken door must be rejected.");
            Assert.IsTrue(doorwayBlocker.enabled,
                "The player still cannot move backward through the broken doorway.");
        }

        // VAL-002: forward-side crossing visibly closes and locks the door with no second
        // input, and the resulting player blocker makes forward progress final (the door
        // cannot be reopened afterward).
        [UnityTest]
        public IEnumerator ForwardCrossing_ClosesAndLocksVisibly_AndMakesForwardProgressFinal()
        {
            OpenDoor();
            yield return null;

            Assert.IsFalse(doorwayBlocker.enabled, "Test setup must actually open the door first.");

            CrossForward();

            yield return null;

            Assert.IsTrue(door.IsLocked,
                "Forward-side crossing must automatically close and lock the door without a second input.");
            Assert.IsTrue(doorVisual.activeSelf);
            Assert.IsTrue(doorwayBlocker.enabled);

            door.StartInteraction();
            yield return null;

            Assert.IsFalse(door.IsInteracting,
                "The player blocker makes forward progress final: the door cannot be reopened afterward.");
        }

        private void OpenDoor()
        {
            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration + 0.1f);
        }

        private void CrossForward()
        {
            InvokeForwardCrossingTriggerEnter(door, playerCollider);
        }

        private static void AdvanceDoorTime(DoorInteractable target, float totalSeconds)
        {
            const float step = 0.05f;
            var elapsed = 0f;
            while (elapsed < totalSeconds)
            {
                var dt = Mathf.Min(step, totalSeconds - elapsed);
                target.Tick(dt);
                elapsed += dt;
            }
        }

        private static void InvokeForwardCrossingTriggerEnter(DoorInteractable target, Collider other)
        {
            var method = target.GetType().GetMethod("HandleForwardCrossingTriggerEnter",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(method,
                "Expected a private HandleForwardCrossingTriggerEnter(Collider) method on DoorInteractable.");
            method.Invoke(target, new object[] { other });
        }

        private static void InvokeCloseAndLock(DoorInteractable target, PlayerHealth crossedPlayerHealth)
        {
            var method = target.GetType().GetMethod("CloseAndLock",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(method, "Expected a private CloseAndLock(PlayerHealth) method on DoorInteractable.");
            method.Invoke(target, new object[] { crossedPlayerHealth });
        }

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }

        private static float GetPrivateFloat(object target, string fieldName)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            return (float)field.GetValue(target);
        }
    }
}
