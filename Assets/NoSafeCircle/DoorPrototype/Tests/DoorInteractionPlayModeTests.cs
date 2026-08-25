using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class DoorInteractionPlayModeTests
    {
        private GameObject doorObject;
        private GameObject playerObject;
        private DoorInteractable door;
        private PlayerInteractionController controller;
        private PlayerHealth health;

        [SetUp]
        public void SetUp()
        {
            doorObject = new GameObject("TestDoor");
            door = doorObject.AddComponent<DoorInteractable>();

            playerObject = new GameObject("TestPlayer");
            health = playerObject.AddComponent<PlayerHealth>();
            controller = playerObject.AddComponent<PlayerInteractionController>();

            controller.NotifyDoorInRange(door);
        }

        [TearDown]
        public void TearDown()
        {
            Object.Destroy(playerObject);
            Object.Destroy(doorObject);
        }

        [UnityTest]
        public IEnumerator Completion_OpensDoor_AfterFullDuration()
        {
            controller.BeginInteraction();

            AdvanceDoorTime(door, door.Duration + 0.1f);

            yield return null;

            Assert.AreEqual(1f, door.Progress, 0.001f);
            Assert.IsTrue(door.IsOpen);
        }

        [UnityTest]
        public IEnumerator Progress_IsApproximatelyHalf_AtHalfDuration()
        {
            controller.BeginInteraction();

            AdvanceDoorTime(door, door.Duration * 0.5f);

            yield return null;

            Assert.AreEqual(0.5f, door.Progress, 0.05f);
            Assert.IsFalse(door.IsOpen);
        }

        [UnityTest]
        public IEnumerator ReleasingInteraction_CancelsAttempt()
        {
            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration * 0.4f);

            controller.EndInteraction();

            yield return null;

            Assert.AreEqual(0f, door.Progress);
            Assert.IsFalse(door.IsOpen);
        }

        [UnityTest]
        public IEnumerator PlayerMovement_CancelsAttempt()
        {
            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration * 0.4f);

            controller.OnPlayerMoved();

            yield return null;

            Assert.AreEqual(0f, door.Progress);
            Assert.IsFalse(door.IsOpen);
        }

        [UnityTest]
        public IEnumerator PlayerDamage_CancelsAttempt()
        {
            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration * 0.4f);

            health.TakeDamage(10f);

            yield return null;

            Assert.AreEqual(0f, door.Progress);
            Assert.IsFalse(door.IsOpen);
        }

        // AC-001: a click-to-approach request using a ground point inside the door's selection
        // area selects that door and (once the wizard is already confirmed in range, as here)
        // starts the automatic opening timer with no sustained hold.
        [UnityTest]
        public IEnumerator TryBeginDoorApproach_PointWithinSelectionArea_SelectsDoorAndStartsTimer()
        {
            var selected = controller.TryBeginDoorApproach(door.SelectionPoint);

            yield return null;

            Assert.IsTrue(selected);
            Assert.AreSame(door, controller.PendingDoor);
            Assert.IsTrue(controller.HasLockedDoorInteraction);
            Assert.IsTrue(controller.IsInteracting,
                "The wizard is already confirmed in range in this test's SetUp, so selecting the door " +
                "should start the automatic opening timer immediately.");
        }

        // AC-001: a ground point outside every door's selection area does not select anything.
        [UnityTest]
        public IEnumerator TryBeginDoorApproach_PointOutsideSelectionArea_DoesNotSelectDoor()
        {
            var selected = controller.TryBeginDoorApproach(new Vector3(50f, 0f, 50f));

            yield return null;

            Assert.IsFalse(selected);
            Assert.IsNull(controller.PendingDoor);
            Assert.IsFalse(controller.HasLockedDoorInteraction);
        }

        // AC-004: issuing another command that replaces the door interaction (selecting a
        // different door) resets the previously selected door's progress to zero.
        [UnityTest]
        public IEnumerator TryBeginDoorApproach_SelectingDifferentDoor_ResetsPreviousDoorProgress()
        {
            var secondDoorObject = new GameObject("SecondTestDoor");
            secondDoorObject.transform.position = new Vector3(10f, 0f, 10f);
            var secondDoor = secondDoorObject.AddComponent<DoorInteractable>();

            try
            {
                Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
                AdvanceDoorTime(door, door.Duration * 0.4f);
                yield return null;

                Assert.Greater(door.Progress, 0f, "Test setup must actually build progress on the first door.");

                Assert.IsTrue(controller.TryBeginDoorApproach(secondDoor.SelectionPoint));

                yield return null;

                Assert.AreEqual(0f, door.Progress,
                    "Selecting a different door is a replacing command and must reset the previous door's " +
                    "progress to zero.");
                Assert.IsFalse(door.IsInteracting);
                Assert.AreSame(secondDoor, controller.PendingDoor);
            }
            finally
            {
                Object.Destroy(secondDoorObject);
            }
        }

        // AC-008/human-review item 3: after the door completes its automatic timer and opens,
        // PlayerInteractionController must release its pending selection instead of continuing
        // to report a locked door interaction that would keep suppressing held-cursor
        // destination updates.
        [UnityTest]
        public IEnumerator DoorOpening_ClearsPendingDoorSelection()
        {
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            Assert.IsTrue(controller.HasLockedDoorInteraction);

            AdvanceDoorTime(door, door.Duration + 0.1f);

            yield return null;

            Assert.IsTrue(door.IsOpen);
            Assert.IsFalse(controller.HasLockedDoorInteraction,
                "Once the door completes and opens, the pending selection must be released.");
            Assert.IsFalse(controller.IsInteracting);
            Assert.IsNull(controller.PendingDoor);
        }

        // AC-006: the owner-controlled suspend interface immediately cancels an in-progress
        // door interaction and rejects new door-selection commands until re-enabled.
        [UnityTest]
        public IEnumerator SuspendGameplayInput_CancelsInProgressInteraction_AndRejectsNewSelection()
        {
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            AdvanceDoorTime(door, door.Duration * 0.3f);
            yield return null;

            Assert.Greater(door.Progress, 0f, "Test setup must actually build progress before suspending.");

            controller.SuspendGameplayInput();

            yield return null;

            Assert.AreEqual(0f, door.Progress,
                "Suspending gameplay input must immediately cancel any in-progress door opening timer.");
            Assert.IsFalse(controller.IsInteracting);
            Assert.IsFalse(controller.IsGameplayEnabled);

            var selectedWhileSuspended = controller.TryBeginDoorApproach(door.SelectionPoint);

            yield return null;

            Assert.IsFalse(selectedWhileSuspended,
                "A new door-selection command must be rejected while gameplay input is suspended.");
            Assert.IsNull(controller.PendingDoor);

            controller.EnableGameplayInput();

            yield return null;

            Assert.IsTrue(controller.IsGameplayEnabled);
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint),
                "Door selection must be accepted again once gameplay input is re-enabled through the " +
                "authorized EnableGameplayInput entry point.");
        }

        // AC-007: the owner-controlled reset entry point returns owned interaction state to
        // floor-initial values, including re-enabling gameplay input after a suspension.
        [UnityTest]
        public IEnumerator ResetInteraction_ReturnsOwnedStateToFloorInitialValues()
        {
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            AdvanceDoorTime(door, door.Duration * 0.3f);
            controller.SuspendGameplayInput();

            yield return null;

            controller.ResetInteraction();

            yield return null;

            Assert.IsFalse(controller.IsInteracting);
            Assert.IsNull(controller.PendingDoor);
            Assert.IsFalse(controller.HasLockedDoorInteraction);
            Assert.IsFalse(controller.IsInRange,
                "Reset must also clear CurrentDoor back to its floor-initial (not-in-range) value.");
            Assert.IsTrue(controller.IsGameplayEnabled,
                "Reset must return gameplay input to its floor-initial enabled state.");
        }

        // AC-007: DoorInteractable's owner-controlled reset entry point returns progress,
        // interacting state, open state, and doorway-blocker enablement to floor-initial values.
        [UnityTest]
        public IEnumerator ResetDoor_ReturnsDoorStateToFloorInitialValues()
        {
            var doorVisual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            var doorwayBlocker = doorVisual.GetComponent<Collider>();
            SetPrivateField(door, "doorVisual", doorVisual);
            SetPrivateField(door, "doorwayBlocker", doorwayBlocker);

            try
            {
                controller.BeginInteraction();
                AdvanceDoorTime(door, door.Duration + 0.1f);
                yield return null;

                Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before reset.");
                Assert.IsFalse(doorVisual.activeSelf);
                Assert.IsFalse(doorwayBlocker.enabled);

                door.ResetDoor();

                yield return null;

                Assert.AreEqual(0f, door.Progress);
                Assert.IsFalse(door.IsInteracting);
                Assert.IsFalse(door.IsOpen);
                Assert.IsTrue(doorVisual.activeSelf,
                    "Reset must restore doorway-blocker/visual enablement to its floor-initial state.");
                Assert.IsTrue(doorwayBlocker.enabled);
            }
            finally
            {
                Object.Destroy(doorVisual);
            }
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

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }
    }

    // Human-review regression (item 1): with the production doorway trigger and destination
    // geometry, the wizard's own automatic approach movement - driven by a real
    // CharacterController and the real OnTriggerEnter path, not a direct NotifyDoorInRange call
    // made after already being within 0.1 of the door - must not self-cancel the automatic
    // opening timer it just started on arrival.
    public class DoorArrivalPhysicsPlayModeTests
    {
        // Keep this real-physics fixture away from the canonical DoorPrototype scene.
        // The generated scene owns a real player and door at the same coordinates this
        // fixture historically used, so overlapping colliders can block the fixture and
        // turn this regression into a scene-state/order test.
        private static readonly Vector3 TestWorldOrigin = new Vector3(1000f, 0f, 1000f);

        private GameObject doorObject;
        private GameObject playerObject;
        private DoorInteractable door;
        private PlayerMovement movement;
        private PlayerInteractionController controller;
        private PlayerHealth health;

        [SetUp]
        public void SetUp()
        {
            doorObject = new GameObject("PhysicsTestDoor");
            doorObject.transform.position = TestWorldOrigin;

            // Mirrors DoorPrototypeSceneBuilder.BuildDoor's arm's-reach trigger geometry.
            var rangeTrigger = doorObject.AddComponent<BoxCollider>();
            rangeTrigger.isTrigger = true;
            rangeTrigger.size = new Vector3(3f, 3f, 3f);
            rangeTrigger.center = new Vector3(0f, 1.5f, 0f);

            door = doorObject.AddComponent<DoorInteractable>();
            SetPrivateField(door, "duration", 0.3f);

            playerObject = new GameObject("PhysicsTestPlayer");
            playerObject.SetActive(false);
            playerObject.transform.position =
                TestWorldOrigin + new Vector3(0f, 1f, -4f);

            var characterController = playerObject.AddComponent<CharacterController>();
            characterController.center = new Vector3(0f, 1f, 0f);
            characterController.height = 2f;
            characterController.radius = 0.5f;

            health = playerObject.AddComponent<PlayerHealth>();
            controller = playerObject.AddComponent<PlayerInteractionController>();
            movement = playerObject.AddComponent<PlayerMovement>();

            // Activating after every component exists guarantees each component's Awake-time
            // GetComponent fallback wiring (PlayerMovement<->PlayerInteractionController) finds
            // its counterpart regardless of AddComponent order.
            playerObject.SetActive(true);
        }

        [TearDown]
        public void TearDown()
        {
            if (playerObject != null) Object.Destroy(playerObject);
            if (doorObject != null) Object.Destroy(doorObject);
        }

        [UnityTest]
        [Timeout(30000)]
        public IEnumerator AutomaticApproach_ArrivesAndStartsTimer_WithoutSelfCancellingViaRealPhysicsTrigger()
        {
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            Assert.IsTrue(movement.HasActiveDestination);

            // Drive PlayerMovement's public deterministic test seam with a normal gameplay-sized
            // delta while still using the real CharacterController.Move/trigger path. Uncapped
            // batchmode frames can have such tiny Time.deltaTime values that CharacterController's
            // minimum movement threshold discards every automatic Update step.
            movement.enabled = false;
            const float simulationStepSeconds = 1f / 60f;
            const float maxElapsedSeconds = 3f;
            var elapsedSeconds = 0f;
            var frames = 0;
            while (movement.HasActiveDestination && elapsedSeconds < maxElapsedSeconds)
            {
                movement.Tick(simulationStepSeconds);
                yield return null;
                elapsedSeconds += simulationStepSeconds;
                frames++;
            }

            Assert.IsFalse(movement.HasActiveDestination,
                "The wizard must actually arrive at the door's interaction position via real " +
                $"CharacterController movement within {maxElapsedSeconds:F1} seconds of simulated " +
                $"game time (elapsed={elapsedSeconds:F3}s, renderedFrames={frames}).");
            Assert.IsTrue(controller.IsInteracting,
                "Arriving via real physics-driven approach movement (through the actual trigger " +
                "OnTriggerEnter path) must start the automatic opening timer.");
            Assert.IsTrue(door.IsInteracting);

            var lastProgress = door.Progress;
            var sawProgressIncrease = false;
            for (var i = 0; i < 30 && !door.IsOpen; i++)
            {
                yield return null;

                Assert.GreaterOrEqual(door.Progress, lastProgress,
                    "Progress must never reset back toward zero once the automatic timer has started.");
                if (door.Progress > lastProgress) sawProgressIncrease = true;
                lastProgress = door.Progress;

                // The door may legitimately finish on this same frame (Opened clears
                // IsInteracting as designed - see the separate PendingDoor-clearing regression).
                // Only the still-in-progress case must prove no self-cancellation occurred.
                if (!door.IsOpen)
                {
                    Assert.IsTrue(controller.IsInteracting,
                        "The wizard's own settled approach movement must not self-cancel the automatic " +
                        "opening timer after arrival.");
                }
            }

            Assert.IsTrue(sawProgressIncrease || door.IsOpen,
                "Expected the opening timer to make real progress after arrival.");
        }

        // Human-review regression (second pass, item 1): suspending gameplay input while the
        // wizard is still automatically walking toward the door - before arrival ever starts the
        // opening timer - must clear the pending selection AND stop PlayerMovement from
        // continuing to execute the door-issued approach destination. AC-006.
        [UnityTest]
        [Timeout(30000)]
        public IEnumerator SuspendGameplayInput_DuringApproach_CancelsApproachDestination_AndRejectsNewCommands()
        {
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            Assert.IsTrue(movement.HasActiveDestination);

            // A couple of real frames of physics-driven approach movement, still well short of
            // arrival at the door (~3 units away at 4 units/sec).
            yield return null;
            yield return null;

            Assert.IsTrue(movement.HasActiveDestination,
                "Test setup must still be mid-approach (not yet arrived) when suspending.");
            Assert.IsFalse(controller.IsInteracting,
                "The opening timer must not have started yet while the wizard is still approaching.");

            controller.SuspendGameplayInput();

            yield return null;

            Assert.IsFalse(controller.HasLockedDoorInteraction,
                "Suspending during the approach must clear the pending door selection.");
            Assert.IsFalse(movement.HasActiveDestination,
                "Suspending during the approach must cancel the door-issued destination PlayerMovement was " +
                "walking toward, not merely the door's own interaction/timer state.");

            var positionAtSuspend = movement.transform.position;

            for (var i = 0; i < 10; i++)
            {
                yield return null;
            }

            Assert.Less(HorizontalOffset(movement.transform.position, positionAtSuspend), 0.05f,
                "The wizard must not continue walking toward the cancelled door-approach destination after " +
                "suspension.");

            Assert.IsFalse(controller.TryBeginDoorApproach(door.SelectionPoint),
                "New door-selection commands must remain rejected while gameplay input is suspended.");
        }

        // Human-review regression (second pass, item 2): taking damage while the wizard is still
        // automatically walking toward the door - before the opening timer has started - must
        // reset the pending approach attempt, not merely be ignored because IsInteracting is
        // still false. AC-004.
        [UnityTest]
        [Timeout(30000)]
        public IEnumerator TakeDamage_DuringApproach_CancelsPendingApproach_AndStopsDestinationMovement()
        {
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            Assert.IsTrue(movement.HasActiveDestination);

            yield return null;
            yield return null;

            Assert.IsTrue(movement.HasActiveDestination,
                "Test setup must still be mid-approach (not yet arrived) when damage occurs.");
            Assert.IsFalse(controller.IsInteracting,
                "The opening timer must not have started yet while the wizard is still approaching.");

            health.TakeDamage(10f);

            yield return null;

            Assert.IsFalse(controller.HasLockedDoorInteraction,
                "Damage during the automatic approach must clear the pending door selection, even though the " +
                "opening timer had not started yet.");
            Assert.IsNull(controller.PendingDoor);
            Assert.IsFalse(controller.IsInteracting);
            Assert.AreEqual(0f, door.Progress);
            Assert.IsFalse(movement.HasActiveDestination,
                "Damage during the automatic approach must cancel the door-issued approach destination so the " +
                "wizard does not continue the same attempt.");

            var positionAtDamage = movement.transform.position;

            for (var i = 0; i < 10; i++)
            {
                yield return null;
            }

            Assert.Less(HorizontalOffset(movement.transform.position, positionAtDamage), 0.05f,
                "The wizard must not continue walking toward the door after the approach was cancelled by " +
                "damage.");
        }

        private static float HorizontalOffset(Vector3 position, Vector3 target)
        {
            var offset = new Vector3(position.x - target.x, 0f, position.z - target.z);
            return offset.magnitude;
        }

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }
    }
}
