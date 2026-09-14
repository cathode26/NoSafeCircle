using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-032: the staged Floor Run/Restart Orchestrator subscribes to Player Health's
    // owner-exposed zero-health/death transition and, on trigger, invokes the owner-controlled
    // reset entry point of every currently-existing run-persistent owner. Each owner's own reset
    // entry point is already unit-tested in isolation (PlayerHealthPlayModeTests,
    // PlayerManaPlayModeTests, PlayerMovementPlayModeTests, DoorInteractionPlayModeTests); these
    // tests instead prove the orchestration itself: that the Died transition actually drives all
    // of them together, exactly once per transition, and only non-fatal damage is ignored.
    public class FloorRunRestartPlayModeTests
    {
        private GameObject playerObject;
        private GameObject restartControllerObject;
        private GameObject doorObject;
        private GameObject secondDoorObject;
        private GameObject interactionDoorObject;
        private GameObject doorVisual;

        private PlayerHealth health;
        private PlayerMana mana;
        private PlayerMovement movement;
        private PlayerInteractionController interactionController;
        private DoorInteractable door;
        private DoorInteractable secondDoor;
        private DoorInteractable interactionDoor;

        [SetUp]
        public void SetUp()
        {
            playerObject = new GameObject("TestPlayer");
            playerObject.SetActive(false);
            playerObject.AddComponent<CharacterController>();
            health = playerObject.AddComponent<PlayerHealth>();
            mana = playerObject.AddComponent<PlayerMana>();
            movement = playerObject.AddComponent<PlayerMovement>();
            interactionController = playerObject.AddComponent<PlayerInteractionController>();
            playerObject.SetActive(true);

            doorObject = new GameObject("TestDoor");
            door = doorObject.AddComponent<DoorInteractable>();

            // Positioned well away from the player's test movement path so its real (non-trigger)
            // collider cannot physically interfere with CharacterController movement below.
            doorVisual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            doorVisual.transform.position = new Vector3(50f, 0f, 50f);
            var doorwayBlocker = doorVisual.GetComponent<Collider>();
            SetPrivateField(door, "doorVisual", doorVisual);
            SetPrivateField(door, "doorwayBlocker", doorwayBlocker);

            secondDoorObject = new GameObject("SecondTestDoor");
            secondDoor = secondDoorObject.AddComponent<DoorInteractable>();

            // Positioned far from door/secondDoor's default selection point so click-to-approach
            // selection below deterministically targets only this sealed door.
            interactionDoorObject = new GameObject("InteractionTestDoor");
            interactionDoorObject.transform.position = new Vector3(10f, 0f, 10f);
            interactionDoor = interactionDoorObject.AddComponent<DoorInteractable>();

            // Wire the serialized owner references before OnEnable runs, matching how the scene
            // builder assigns them before the restart controller GameObject is ever active.
            restartControllerObject = new GameObject("TestFloorRunRestartController");
            restartControllerObject.SetActive(false);
            var restartController = restartControllerObject.AddComponent<FloorRunRestartController>();
            SetPrivateField(restartController, "playerHealth", health);
            SetPrivateField(restartController, "playerMana", mana);
            SetPrivateField(restartController, "playerMovement", movement);
            SetPrivateField(restartController, "playerInteractionController", interactionController);
            restartControllerObject.SetActive(true);
        }

        [TearDown]
        public void TearDown()
        {
            if (restartControllerObject != null) Object.Destroy(restartControllerObject);
            if (doorObject != null) Object.Destroy(doorObject);
            if (secondDoorObject != null) Object.Destroy(secondDoorObject);
            if (interactionDoorObject != null) Object.Destroy(interactionDoorObject);
            if (doorVisual != null) Object.Destroy(doorVisual);
            if (playerObject != null) Object.Destroy(playerObject);
        }

        // AC-001/AC-002/VAL-002: the zero-health transition invokes every currently-existing
        // run-persistent owner's exposed reset entry point, returning Player Health, Player
        // Mana, player position, Player Interaction's owned selection/lock state, and every
        // currently active door's open-interaction state (progress/open/blocker) back to their
        // floor-initial values.
        [UnityTest]
        public IEnumerator PlayerDied_RestartsAllCurrentlyExistingOwners_ToFloorInitialState()
        {
            var initialPosition = movement.transform.position;

            health.TakeDamage(health.MaxHealth * 0.5f);
            mana.Spend(mana.MaxMana * 0.5f);
            movement.RequestDestination(initialPosition + new Vector3(3f, 0f, 3f));
            AdvanceMovementTime(movement, 2f);

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            secondDoor.StartInteraction();
            secondDoor.Tick(secondDoor.Duration + 0.1f);

            var selectedPendingDoor = interactionController.TryBeginDoorApproach(interactionDoor.SelectionPoint);

            yield return null;

            Assert.Less(health.CurrentHealth, health.MaxHealth,
                "Test setup must actually damage the player before death.");
            Assert.Less(mana.CurrentMana, mana.MaxMana,
                "Test setup must actually spend mana before death.");
            Assert.Greater(Vector3.Distance(movement.transform.position, initialPosition), 0.5f,
                "Test setup must actually move the player away from its floor-initial position before death.");
            Assert.IsTrue(door.IsOpen, "Test setup must actually open the first door before death.");
            Assert.IsTrue(secondDoor.IsOpen, "Test setup must actually open the second door before death.");
            Assert.IsTrue(selectedPendingDoor,
                "Test setup must actually select a sealed door via click-to-approach before death.");
            Assert.AreSame(interactionDoor, interactionController.PendingDoor,
                "Test setup must actually set a pending door interaction before death.");
            Assert.IsTrue(interactionController.HasLockedDoorInteraction,
                "Test setup must actually lock movement to the pending door interaction before death.");

            health.TakeDamage(health.MaxHealth);

            yield return null;

            Assert.AreEqual(health.MaxHealth, health.CurrentHealth, 0.001f,
                "The zero-health transition must invoke Player Health's owner-controlled reset entry point.");
            Assert.AreEqual(mana.MaxMana, mana.CurrentMana, 0.001f,
                "The zero-health transition must invoke Player Mana's owner-controlled reset entry point.");
            Assert.AreEqual(initialPosition.x, movement.transform.position.x, 0.01f,
                "The zero-health transition must invoke Player Movement's owner-controlled reset entry point.");
            Assert.AreEqual(initialPosition.z, movement.transform.position.z, 0.01f,
                "The zero-health transition must invoke Player Movement's owner-controlled reset entry point.");
            Assert.IsFalse(movement.HasActiveDestination);

            Assert.IsFalse(door.IsOpen,
                "The zero-health transition must invoke the first door's owner-controlled reset entry point.");
            Assert.AreEqual(0f, door.Progress);
            Assert.IsTrue(doorVisual.activeSelf);
            Assert.IsTrue(doorVisual.GetComponent<Collider>().enabled);

            Assert.IsFalse(secondDoor.IsOpen,
                "Every currently active door must be reset, not only a single serialized-reference door.");
            Assert.AreEqual(0f, secondDoor.Progress);

            Assert.IsNull(interactionController.PendingDoor,
                "The zero-health transition must invoke Player Interaction's owner-controlled reset entry point.");
            Assert.IsFalse(interactionController.IsInteracting);
            Assert.IsFalse(interactionController.HasLockedDoorInteraction,
                "Player Interaction's reset entry point must clear any locked door interaction so ordinary " +
                "move-to-click is not left stuck suppressed after a floor restart.");
        }

        // VAL-001: reducing Player Health to zero triggers a fresh floor attempt exactly once
        // per zero-health transition. Proven across two independent transitions so a handler
        // that only fires once (for example one that fails to re-subscribe) would fail here just
        // as a handler that double-restarts a single transition would.
        [UnityTest]
        public IEnumerator PlayerDied_TriggersFreshRestart_ExactlyOncePerZeroHealthTransition()
        {
            var diedCount = 0;
            health.Died += () => diedCount++;

            health.TakeDamage(health.MaxHealth);

            yield return null;

            Assert.AreEqual(1, diedCount, "Test setup must produce exactly one zero-health transition so far.");
            Assert.AreEqual(health.MaxHealth, health.CurrentHealth, 0.001f,
                "The first zero-health transition must trigger exactly one fresh restart.");

            mana.Spend(mana.MaxMana * 0.5f);
            movement.RequestDestination(movement.transform.position + new Vector3(2f, 0f, 2f));
            AdvanceMovementTime(movement, 2f);

            yield return null;

            Assert.Less(mana.CurrentMana, mana.MaxMana,
                "Test setup must actually spend mana again before the second death.");

            health.TakeDamage(health.MaxHealth);

            yield return null;

            Assert.AreEqual(2, diedCount, "A second, independent zero-health transition must fire Died again.");
            Assert.AreEqual(mana.MaxMana, mana.CurrentMana, 0.001f,
                "Each zero-health transition must trigger exactly one fresh restart, including the second one.");
        }

        // AC-001 regression: only the owner-exposed zero-health/death transition triggers a
        // restart. Non-fatal damage must leave every owner's state untouched, ruling out
        // polling-based or threshold-based restart triggering.
        [UnityTest]
        public IEnumerator NonFatalDamage_DoesNotTriggerRestart()
        {
            mana.Spend(mana.MaxMana * 0.5f);
            movement.RequestDestination(movement.transform.position + new Vector3(2f, 0f, 2f));
            AdvanceMovementTime(movement, 2f);

            yield return null;

            var manaBeforeDamage = mana.CurrentMana;
            var positionBeforeDamage = movement.transform.position;

            health.TakeDamage(health.MaxHealth * 0.25f);

            yield return null;

            Assert.Greater(health.CurrentHealth, 0f, "Test setup must keep the player alive after partial damage.");
            Assert.AreEqual(manaBeforeDamage, mana.CurrentMana, 0.001f,
                "Non-fatal damage must not trigger the restart orchestrator's owner resets.");
            Assert.AreEqual(positionBeforeDamage.x, movement.transform.position.x, 0.001f,
                "Non-fatal damage must not trigger the restart orchestrator's owner resets.");
            Assert.AreEqual(positionBeforeDamage.z, movement.transform.position.z, 0.001f,
                "Non-fatal damage must not trigger the restart orchestrator's owner resets.");
        }

        // AC-003 (structural support): the full-restart test above can only reach floor-initial
        // state through each owner's exposed reset entry point because these owners' state is
        // otherwise unsettable from outside the declaring type. This locks the encapsulation
        // that AC-003 ("only calls each owner's exposed reset entry point") depends on.
        [Test]
        public void OwnerState_RemainsUnsettableFromOutsideDeclaringType()
        {
            AssertPropertyHasNoPublicSetter(typeof(PlayerHealth), "CurrentHealth");
            AssertPropertyHasNoPublicSetter(typeof(PlayerMana), "CurrentMana");
            AssertPropertyHasNoPublicSetter(typeof(DoorInteractable), "Progress");
            AssertPropertyHasNoPublicSetter(typeof(DoorInteractable), "IsOpen");
            AssertPropertyHasNoPublicSetter(typeof(PlayerInteractionController), "PendingDoor");
            AssertPropertyHasNoPublicSetter(typeof(PlayerInteractionController), "CurrentDoor");
            AssertPropertyHasNoPublicSetter(typeof(PlayerInteractionController), "IsInteracting");
        }

        private static void AssertPropertyHasNoPublicSetter(System.Type type, string propertyName)
        {
            var property = type.GetProperty(propertyName, BindingFlags.Instance | BindingFlags.Public);
            Assert.IsNotNull(property, $"Expected a public {propertyName} property on {type.Name}.");

            var setter = property.GetSetMethod(true);
            Assert.IsFalse(property.CanWrite && setter != null && setter.IsPublic,
                $"{type.Name}.{propertyName} must remain unsettable from outside its declaring type so a " +
                "consumer like the restart orchestrator can only change it through an owner-exposed reset " +
                "entry point.");
        }

        private static void AdvanceMovementTime(PlayerMovement target, float totalSeconds)
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

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }
    }
}
