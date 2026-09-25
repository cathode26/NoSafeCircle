using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class DoorInteractionPlayModeTests
    {
        private GameObject doorObject;
        private GameObject playerObject;
        private DoorInteractable door;
        private PlayerInteractionController controller;
        private PlayerHealth health;
        private GameObject interactionUiObject;

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
            if (interactionUiObject != null) Object.Destroy(interactionUiObject);
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

        [UnityTest]
        public IEnumerator DoorInteractionUI_CancelledAttempt_ResetsAndHidesProgressFill()
        {
            var progressFill = CreateInteractionUi(out var ui, out var promptRoot);

            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration * 0.4f);
            RefreshInteractionUi(ui);

            Assert.AreEqual(door.Progress, progressFill.fillAmount, 0.001f);
            Assert.IsTrue(progressFill.enabled,
                "An active opening attempt must show the selected door's progress.");
            Assert.IsTrue(promptRoot.activeSelf,
                "The existing sealed-door prompt must remain visible while the player is in range.");

            controller.EndInteraction();
            RefreshInteractionUi(ui);

            Assert.AreEqual(0f, progressFill.fillAmount, 0.001f,
                "Cancelling the selected door must reset the shared HUD fill.");
            Assert.IsFalse(progressFill.enabled,
                "A cancelled attempt must hide the empty fill instead of leaving stale progress visible.");

            yield return null;
        }

        [UnityTest]
        public IEnumerator DoorInteractionUI_SuccessfulOpen_ResetsAndHidesProgressFill()
        {
            var progressFill = CreateInteractionUi(out var ui, out var promptRoot);

            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration + 0.1f);
            RefreshInteractionUi(ui);

            Assert.IsTrue(door.IsOpen);
            Assert.AreEqual(1f, door.Progress, 0.001f,
                "The door may retain its completed progress as model history.");
            Assert.IsNull(controller.PendingDoor,
                "Opening releases the player-owned selection that drives the shared HUD.");
            Assert.AreEqual(0f, progressFill.fillAmount, 0.001f,
                "The shared HUD must reset after the selected door opens even though that door retains Progress=1.");
            Assert.IsFalse(progressFill.enabled,
                "The completed door's stale full fill must be hidden.");
            Assert.IsFalse(promptRoot.activeSelf,
                "The sealed-door prompt must be hidden after the in-range door opens.");

            yield return null;
        }

        [UnityTest]
        public IEnumerator DoorInteractionUI_SelectingAnotherDoor_TracksNewSelection()
        {
            var secondDoorObject = new GameObject("SecondUiTestDoor");
            secondDoorObject.transform.position = new Vector3(10f, 0f, 10f);
            var secondDoor = secondDoorObject.AddComponent<DoorInteractable>();
            var progressFill = CreateInteractionUi(out var ui, out _);

            try
            {
                controller.BeginInteraction();
                AdvanceDoorTime(door, door.Duration * 0.4f);
                RefreshInteractionUi(ui);
                Assert.AreEqual(door.Progress, progressFill.fillAmount, 0.001f);

                Assert.IsTrue(controller.TryBeginDoorApproach(secondDoor.SelectionPoint));
                controller.NotifyDoorInRange(secondDoor);
                AdvanceDoorTime(secondDoor, secondDoor.Duration * 0.65f);
                RefreshInteractionUi(ui);

                Assert.AreEqual(0f, door.Progress, 0.001f,
                    "Replacing the first selection must reset its model progress.");
                Assert.AreSame(secondDoor, controller.PendingDoor);
                Assert.AreEqual(secondDoor.Progress, progressFill.fillAmount, 0.001f,
                    "The shared HUD must follow the player controller's new selected door, not its legacy static door reference.");
                Assert.IsTrue(progressFill.enabled);
            }
            finally
            {
                Object.Destroy(secondDoorObject);
            }

            yield return null;
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

        // VAL-001/AC-001: opening the door via the automatic timer alone must not set the shared
        // doorway-crossing state; only actually reaching the forward-side crossing trigger does.
        [UnityTest]
        public IEnumerator Completion_OpensDoor_DoesNotSetCrossingState()
        {
            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration + 0.1f);

            yield return null;

            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door.");
            Assert.IsFalse(door.HasCrossedForward,
                "Completing the automatic opening timer must not by itself set the shared doorway-crossing " +
                "state.");
        }

        // AC-001: the forward-crossing trigger must not set crossing state while the door is
        // still sealed, even if the wizard's collider reaches it (for example while still
        // approaching before the door has finished opening).
        [UnityTest]
        public IEnumerator ForwardCrossingTrigger_WhileDoorSealed_DoesNotSetCrossingState()
        {
            var playerCollider = playerObject.AddComponent<BoxCollider>();

            Assert.IsFalse(door.IsOpen, "Test setup must keep the door sealed.");

            InvokeForwardCrossingTriggerEnter(door, playerCollider);

            yield return null;

            Assert.IsFalse(door.HasCrossedForward,
                "Reaching the forward-crossing trigger while the door is still sealed must not set crossing " +
                "state.");
        }

        // AC-001/AC-002: once the door is open, the wizard's collider reaching the
        // forward-crossing trigger sets the shared HasCrossedForward state and fires the
        // CrossedForward event exactly once, so door close/lock and final-escape victory can
        // consume a stable owner-side interface instead of implementing their own crossing
        // detector.
        [UnityTest]
        public IEnumerator ForwardCrossingTrigger_AfterDoorOpen_SetsCrossingStateAndFiresEventOnce()
        {
            var playerCollider = playerObject.AddComponent<BoxCollider>();

            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration + 0.1f);
            yield return null;

            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before crossing.");

            var crossedForwardFireCount = 0;
            door.CrossedForward += () => crossedForwardFireCount++;

            InvokeForwardCrossingTriggerEnter(door, playerCollider);
            InvokeForwardCrossingTriggerEnter(door, playerCollider);

            yield return null;

            Assert.IsTrue(door.HasCrossedForward,
                "Reaching the forward-crossing trigger on an open door must set the shared doorway-crossing " +
                "state.");
            Assert.AreEqual(1, crossedForwardFireCount,
                "CrossedForward must fire exactly once even if the trigger reports entry more than once.");
        }

        // AC-001: the forward-crossing trigger must ignore colliders that do not belong to the
        // wizard, so an unrelated collider cannot falsely set the shared crossing state.
        [UnityTest]
        public IEnumerator ForwardCrossingTrigger_IgnoresNonPlayerCollider()
        {
            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration + 0.1f);
            yield return null;

            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before crossing.");

            var nonPlayerObject = new GameObject("NonPlayerCollider");
            var nonPlayerCollider = nonPlayerObject.AddComponent<BoxCollider>();

            try
            {
                InvokeForwardCrossingTriggerEnter(door, nonPlayerCollider);

                yield return null;

                Assert.IsFalse(door.HasCrossedForward,
                    "A collider without a PlayerInteractionController ancestor must not set the shared " +
                    "crossing state.");
            }
            finally
            {
                Object.Destroy(nonPlayerObject);
            }
        }

        // AC-003: DoorInteractable's owner-controlled reset entry point also returns the shared
        // doorway-crossing state to its floor-initial (not-crossed) value, consumed by the Floor
        // Run/Restart Orchestrator.
        [UnityTest]
        public IEnumerator ResetDoor_ResetsCrossingState()
        {
            var playerCollider = playerObject.AddComponent<BoxCollider>();

            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration + 0.1f);
            yield return null;

            InvokeForwardCrossingTriggerEnter(door, playerCollider);
            yield return null;

            Assert.IsTrue(door.HasCrossedForward, "Test setup must actually set crossing state before reset.");

            door.ResetDoor();

            yield return null;

            Assert.IsFalse(door.HasCrossedForward,
                "ResetDoor must return the shared doorway-crossing state to its floor-initial (not-crossed) " +
                "value.");
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

        private Image CreateInteractionUi(out DoorInteractionUI ui, out GameObject promptRoot)
        {
            interactionUiObject = new GameObject("DoorInteractionUiTestRoot");
            // SetUp calls the controller notification directly; mirror the other half of the
            // real trigger handshake so IsPlayerInRange and the prompt are also authentic.
            SetPrivateField(door, "playerInRange", controller);

            promptRoot = new GameObject("PromptRoot");
            promptRoot.transform.SetParent(interactionUiObject.transform, false);

            var progressObject = new GameObject("ProgressFill", typeof(RectTransform),
                typeof(CanvasRenderer), typeof(Image));
            progressObject.transform.SetParent(interactionUiObject.transform, false);
            var progressFill = progressObject.GetComponent<Image>();
            progressFill.type = Image.Type.Filled;
            progressFill.fillAmount = 0f;

            ui = interactionUiObject.AddComponent<DoorInteractionUI>();
            SetPrivateField(ui, "interactionController", controller);
            SetPrivateField(ui, "door", door);
            SetPrivateField(ui, "promptRoot", promptRoot);
            SetPrivateField(ui, "progressFillImage", progressFill);
            RefreshInteractionUi(ui);

            return progressFill;
        }

        private static void RefreshInteractionUi(DoorInteractionUI ui)
        {
            var method = typeof(DoorInteractionUI).GetMethod("Update",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(method, "Expected DoorInteractionUI.Update for deterministic HUD refresh.");
            method.Invoke(ui, null);
        }

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }

        // AC-001: invokes DoorInteractable's private forward-crossing trigger handler directly so
        // this component test can prove HasCrossedForward/CrossedForward semantics without
        // depending on real physics trigger delivery, which is already covered separately by the
        // real-physics arrival regression fixture below.
        private static void InvokeForwardCrossingTriggerEnter(DoorInteractable target, Collider other)
        {
            var method = target.GetType().GetMethod("HandleForwardCrossingTriggerEnter",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(method,
                "Expected a private HandleForwardCrossingTriggerEnter(Collider) method on DoorInteractable.");
            method.Invoke(target, new object[] { other });
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

            // CharacterController.Move can settle the destination before Unity's next physics
            // step dispatches the real OnTriggerEnter callback. Wait for a small, bounded number
            // of physics steps rather than requiring trigger delivery in the same rendered frame.
            const int maxTriggerPhysicsSteps = 3;
            var triggerPhysicsSteps = 0;
            while (!controller.IsInteracting && triggerPhysicsSteps < maxTriggerPhysicsSteps)
            {
                yield return new WaitForFixedUpdate();
                triggerPhysicsSteps++;
            }

            Assert.IsTrue(controller.IsInteracting,
                "Arriving via real physics-driven approach movement must start the automatic " +
                "opening timer through the actual trigger OnTriggerEnter path. " +
                $"fixedStepsWaited={triggerPhysicsSteps}, " +
                $"currentDoor={(controller.CurrentDoor != null ? controller.CurrentDoor.name : "<null>")}, " +
                $"pendingDoor={(controller.PendingDoor != null ? controller.PendingDoor.name : "<null>")}, " +
                $"doorReportsPlayerInRange={door.IsPlayerInRange}.");
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

#if UNITY_EDITOR
    // NSC-020 AC-005 / VAL-001: a READ-ONLY committed-scene conformance check. It opens the
    // committed Assets/Scenes/DoorPrototype.unity in Play Mode, never saves it, and asserts the
    // corrected forward-crossing geometry on the production D1-D5 rather than on a fixture.
    //
    // WHY THE ASSERTION IS WHAT IT IS. HandleForwardCrossingTriggerEnter performs no geometry
    // test at all - it checks IsOpen, HasCrossedForward and PlayerInteractionController, then
    // records the crossing. So AC-001 "capsule geometrically clear of the doorwayBlocker" lives
    // entirely in where the trigger volume sits, and only a placement check can defend it.
    // OnTriggerEnter fires when the capsule LEADING edge reaches the volume near face, which
    // leaves the capsule TRAILING edge 2r behind it, so clearing the blocker needs
    //
    //     nearFace >= blockerForwardFace + 2 * playerRadius
    //
    // which is VAL-001 verbatim. This is a RELATION, not a literal: it keeps holding if the
    // offset, the blocker depth or the capsule radius is ever re-authored, and it fails the
    // moment any of them drifts apart.
    public sealed class DoorCrossingCommittedSceneConformanceTests
    {
        private const string CommittedScenePath = "Assets/Scenes/DoorPrototype.unity";

        private const string CommittedSceneName = "DoorPrototype";

        // Fixed simulation step for the public PlayerMovement.Tick seam, and the bounds that
        // keep every wait in this fixture finite. Uncapped batchmode frames give deltaTime
        // values small enough that CharacterController discards the move outright, which is why
        // the step is fixed rather than taken from Time.deltaTime.
        private const float SimulationStepSeconds = 1f / 60f;

        private const int MaxDriveFrames = 1200;

        private const int MaxOpenFrames = 4000;

        private const int TriggerSettleFixedSteps = 3;

        // PlayModeSceneCleanupConventionTests caught this fixture the moment it was written, and
        // the guard was right: loading in LoadSceneMode.Single without restoring leaves the
        // committed five-room scene loaded for every fixture that runs AFTER this one, and the
        // only symptom is unrelated tests failing somewhere else. Same shape as the incident that
        // test records - one missing unload turned seven innocent tests red.
        //
        // A cleanup scene is made active first because Unity refuses to unload the last loaded
        // scene. Nothing is ever saved: the committed scene is opened read-only and discarded.
        [UnityTearDown]
        public IEnumerator UnloadCommittedSceneWithoutSaving()
        {
            UnityEngine.SceneManagement.Scene scene =
                UnityEngine.SceneManagement.SceneManager.GetSceneByName(CommittedSceneName);
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            UnityEngine.SceneManagement.Scene cleanupScene =
                UnityEngine.SceneManagement.SceneManager.CreateScene(
                    "DoorCrossingConformanceCleanup");
            UnityEngine.SceneManagement.SceneManager.SetActiveScene(cleanupScene);
            yield return UnityEngine.SceneManagement.SceneManager.UnloadSceneAsync(scene);
        }


        // VAL-001 requires the blocker extent to come from the BoxCollider own center, size and
        // Transform rather than Collider.bounds, because the blocker GameObject is INACTIVE
        // while a door is open and bounds on an inactive collider is not meaningful.
        private static float BlockerForwardFaceInDoorLocalZ(Transform door, BoxCollider blocker)
        {
            Transform t = blocker.transform;
            Vector3 centreWorld = t.TransformPoint(blocker.center);
            float halfDepthWorld = blocker.size.z * 0.5f * t.lossyScale.z;
            return door.InverseTransformPoint(centreWorld).z + halfDepthWorld;
        }

        private static float TriggerNearFaceInDoorLocalZ(Transform door, BoxCollider trigger)
        {
            Transform t = trigger.transform;
            Vector3 centreWorld = t.TransformPoint(trigger.center);
            float halfDepthWorld = trigger.size.z * 0.5f * t.lossyScale.z;
            return door.InverseTransformPoint(centreWorld).z - halfDepthWorld;
        }

        private static IEnumerator LoadCommittedSceneReadOnly()
        {
            UnityEditor.SceneManagement.EditorSceneManager.LoadSceneInPlayMode(
                CommittedScenePath,
                new UnityEngine.SceneManagement.LoadSceneParameters(
                    UnityEngine.SceneManagement.LoadSceneMode.Single));

            // One frame so the loaded scene Awake calls run: ForwardCrossingTrigger is created at
            // runtime by DoorInteractable.Awake and is not serialized in the scene at all.
            yield return null;
        }

        [UnityTest]
        public IEnumerator CommittedScene_EveryDoorCrossingTriggerClearsItsBlockerByTwoPlayerRadii()
        {
            yield return LoadCommittedSceneReadOnly();

            DoorInteractable[] doors =
                Object.FindObjectsByType<DoorInteractable>(FindObjectsSortMode.None);
            Assert.AreEqual(5, doors.Length,
                "The committed scene must compose exactly five doors, D1 through D5.");

            CharacterController capsule = Object.FindFirstObjectByType<CharacterController>();
            Assert.IsNotNull(capsule,
                "The committed scene must hold the Player CharacterController; the clearance rule "
                + "is expressed in terms of its radius.");
            float radius = capsule.radius * Mathf.Max(
                capsule.transform.lossyScale.x, capsule.transform.lossyScale.z);

            foreach (DoorInteractable door in doors)
            {
                Transform doorTransform = door.transform;

                Transform triggerTransform = doorTransform.Find("ForwardCrossingTrigger");
                Assert.IsNotNull(triggerTransform,
                    door.DoorId + " must own a runtime-created ForwardCrossingTrigger child.");
                var trigger = triggerTransform.GetComponent<BoxCollider>();
                Assert.IsNotNull(trigger,
                    door.DoorId + " crossing trigger must be a BoxCollider.");
                Assert.IsTrue(trigger.isTrigger,
                    door.DoorId + " crossing volume must be a trigger, not solid collision.");

                // Found by hierarchy rather than by reflecting the private doorwayBlocker field,
                // so this reaches the same object the builder wired without depending on a
                // private name and without reflection.
                Transform visual = doorTransform.Find("DoorVisual");
                Assert.IsNotNull(visual, door.DoorId + " must own its DoorVisual child.");
                var blocker = visual.GetComponent<BoxCollider>();
                Assert.IsNotNull(blocker,
                    door.DoorId + " doorway blocker must be a BoxCollider on DoorVisual.");

                float nearFace = TriggerNearFaceInDoorLocalZ(doorTransform, trigger);
                float blockerFace = BlockerForwardFaceInDoorLocalZ(doorTransform, blocker);
                float required = blockerFace + (2f * radius);

                Assert.GreaterOrEqual(nearFace, required - 0.001f,
                    door.DoorId + ": the crossing trigger near face sits at door-local Z "
                    + nearFace.ToString("F3") + ", but the wizard capsule is only clear of the "
                    + "blocker from " + required.ToString("F3") + " onward (blocker forward face "
                    + blockerFace.ToString("F3") + " plus twice the " + radius.ToString("F3")
                    + " capsule radius). Crossing would be recorded while the capsule still "
                    + "overlaps the blocker, and CloseAndLock re-enables that blocker inside the "
                    + "wizard.");
            }
        }

        // VAL-001: each door local +Z must point toward the next room, and D5 toward the escape
        // side. Asserted as an ordering relation against the next door own position rather than
        // against copied rotation literals, so re-authoring the layout cannot leave this check
        // passing on stale numbers.
        [UnityTest]
        public IEnumerator CommittedScene_EveryDoorForwardAxisPointsAtTheRoomItLeadsTo()
        {
            yield return LoadCommittedSceneReadOnly();

            DoorInteractable[] doors =
                Object.FindObjectsByType<DoorInteractable>(FindObjectsSortMode.None);
            Assert.AreEqual(5, doors.Length);

            System.Array.Sort(doors, (a, b) => a.DoorId.CompareTo(b.DoorId));

            for (int i = 0; i < doors.Length; i++)
            {
                // D5 has no successor, so its escape direction is taken as the direction the
                // sequence was already travelling when it arrived.
                Vector3 onward = i < doors.Length - 1
                    ? doors[i + 1].transform.position - doors[i].transform.position
                    : doors[i].transform.position - doors[i - 1].transform.position;
                onward.y = 0f;

                Assert.Greater(onward.sqrMagnitude, 0.0001f,
                    doors[i].DoorId + " and its neighbour must not share a position.");

                Vector3 forward = doors[i].transform.forward;
                forward.y = 0f;

                Assert.Greater(Vector3.Dot(forward.normalized, onward.normalized), 0f,
                    doors[i].DoorId + " local +Z must point toward the room it leads to (for D5, "
                    + "the escape side), because forward-crossing is recorded on the +Z side and "
                    + "a reversed door would record the approach as a crossing.");
            }
        }

        // NSC-020 VAL-001, FINAL CLAUSE. Every other check in this gate runs in a TEMPORARY
        // fixture. This one is explicit that it runs "against the committed DoorPrototype scene's
        // production D1 rather than a temporary fixture", under real physics, and that after a
        // FloorRunRestartController restart the repeated crossing fires "exactly one
        // CrossedForward event for that run".
        //
        // THE RESTART IS NOT DRIVEN BY POKING THE CONTROLLER. Player Health is driven to zero,
        // PlayerHealth raises Died, and FloorRunRestartController's own OnEnable subscription
        // performs the owner-controlled restart - ResetHealth, ResetMana, ResetMovement,
        // ResetInteraction, and ResetDoor on every door in the active-door registry. That is the
        // production wiring the gate names, so this exercises it instead of simulating it.
        // FloorRunRestartController exposes no public member at all, which is the point: there is
        // no other way in, and a test that found one would not be testing the shipped path.
        //
        // WHY movement.enabled IS TURNED OFF: PlayerMovement.Update already calls Tick, so a test
        // that also calls Tick would advance movement twice per rendered frame. Driving the public
        // Tick seam with a fixed step is the pattern DoorArrivalPhysicsPlayModeTests established,
        // and it exists because uncapped batchmode frames produce deltaTime values small enough
        // that CharacterController discards the step entirely. THE DOOR IS DELIBERATELY LEFT
        // ENABLED: its own Update drives the opening timer, and disabling it would also stop the
        // trigger callbacks this test depends on.
        [UnityTest]
        [Timeout(180000)]
        public IEnumerator CommittedD1_RealPhysics_SurvivesFloorRunRestartAndFiresOneCrossingPerRun()
        {
            yield return LoadCommittedSceneReadOnly();

            DoorInteractable d1 = null;
            foreach (DoorInteractable candidate in
                     Object.FindObjectsByType<DoorInteractable>(FindObjectsSortMode.None))
            {
                if (candidate.DoorId == World.DoorId.D1) d1 = candidate;
            }
            Assert.IsNotNull(d1, "The committed scene must hold the production D1.");

            var movement = Object.FindFirstObjectByType<PlayerMovement>();
            var playerHealth = Object.FindFirstObjectByType<PlayerHealth>();
            var interaction = Object.FindFirstObjectByType<PlayerInteractionController>();
            var capsule = Object.FindFirstObjectByType<CharacterController>();
            var restartController = Object.FindFirstObjectByType<FloorRunRestartController>();
            Assert.IsNotNull(movement, "The committed scene must hold PlayerMovement.");
            Assert.IsNotNull(playerHealth, "The committed scene must hold PlayerHealth.");
            Assert.IsNotNull(interaction,
                "The committed scene must hold PlayerInteractionController; the crossing handler "
                + "identifies the wizard by finding it on the entering collider's parent.");
            Assert.IsNotNull(capsule, "The committed scene must hold the Player CharacterController.");
            Assert.IsNotNull(restartController,
                "The committed scene must hold FloorRunRestartController. This clause is about the "
                + "restart that component owns, so its absence is a failure of the scene rather "
                + "than a reason to skip.");

            // THE COMMITTED SCENE STARTS AT THE TITLE SCREEN WITH GAMEPLAY INPUT SUSPENDED.
            // TitleScreenController.Awake calls SuspendGameplayInput on both PlayerMovement and
            // PlayerInteractionController, so a fixture that drove the wizard straight out of a
            // freshly loaded scene would be driving suspended controllers, and every approach
            // click would be refused by the IsGameplayEnabled guard at the top of
            // TryBeginDoorApproach. That is not a bug in the scene - it is the title screen doing
            // its job, and it is invisible until something tries to play the scene.
            //
            // So this enters gameplay the way a player does: start the game, pick a wizard,
            // confirm, and let WizardGameEntryController spawn the wizard and re-enable input.
            // Writing the flag directly would be shorter and would let this test pass against a
            // committed scene no player could actually get moving in.
            yield return EnterGameplayThroughRunEntry();

            Assert.IsTrue(movement.IsGameplayEnabled,
                "PlayerMovement gameplay input must be enabled once the production run-entry flow "
                + "has completed; the committed scene starts it suspended behind the title screen.");
            Assert.IsTrue(interaction.IsGameplayEnabled,
                "PlayerInteractionController gameplay input must be enabled once the production "
                + "run-entry flow has completed.");

            Transform doorTransform = d1.transform;

            Transform triggerTransform = doorTransform.Find("ForwardCrossingTrigger");
            Assert.IsNotNull(triggerTransform,
                "D1 must own a runtime-created ForwardCrossingTrigger child.");
            var trigger = triggerTransform.GetComponent<BoxCollider>();
            Assert.IsNotNull(trigger, "D1 crossing trigger must be a BoxCollider.");

            Transform visual = doorTransform.Find("DoorVisual");
            Assert.IsNotNull(visual, "D1 must own its DoorVisual child.");
            var blocker = visual.GetComponent<BoxCollider>();
            Assert.IsNotNull(blocker, "D1 doorway blocker must be a BoxCollider on DoorVisual.");

            float radius = capsule.radius * Mathf.Max(
                capsule.transform.lossyScale.x, capsule.transform.lossyScale.z);
            float blockerFace = BlockerForwardFaceInDoorLocalZ(doorTransform, blocker);
            float nearFace = TriggerNearFaceInDoorLocalZ(doorTransform, trigger);

            // Every position is DERIVED from the blocker and the capsule rather than written as a
            // literal, so re-authoring the doorway depth, the trigger offset or the capsule radius
            // keeps these meaningful instead of leaving the test passing on stale numbers.
            //
            // thresholdLocalZ is the gate's threshold: the capsule leading edge at the blocker
            // forward face while the capsule CENTRE is still at door-local Z below zero. The
            // sealed blocker is solid, so real physics will usually stop the wizard short of this
            // point - which is the behaviour under test, not an obstacle to it, and is why
            // arrival is never asserted here.
            float thresholdLocalZ = Mathf.Min(blockerFace - radius, -0.05f);
            float approachLocalZ = thresholdLocalZ - 2f;
            float throughLocalZ = nearFace + radius + 1f;

            movement.enabled = false;

            int crossings = 0;
            System.Action countCrossing = () => crossings++;
            d1.CrossedForward += countCrossing;

            try
            {
                yield return DriveToDoorLocalZ(movement, doorTransform, approachLocalZ);

                // Step to the threshold and retreat: no crossing, no lock.
                yield return DriveToDoorLocalZ(movement, doorTransform, thresholdLocalZ);
                Assert.IsFalse(d1.HasCrossedForward,
                    "Reaching the sealed D1 threshold with the capsule centre still on the "
                    + "approach side must not record a forward crossing.");
                Assert.IsFalse(d1.IsLocked, "Reaching the sealed D1 threshold must not lock D1.");
                Assert.AreEqual(0, crossings,
                    "No CrossedForward event may fire at the threshold of a sealed D1.");

                yield return DriveToDoorLocalZ(movement, doorTransform, approachLocalZ);
                Assert.IsFalse(d1.HasCrossedForward,
                    "Retreating to the approach side must not record a forward crossing.");
                Assert.IsFalse(d1.IsLocked, "Retreating to the approach side must not lock D1.");

                // Open D1 through the production ground-click approach path.
                yield return OpenDoorThroughApproach(movement, interaction, d1);
                Assert.IsTrue(d1.IsOpen,
                    "D1 must open through the production approach-and-timer path before the "
                    + "crossing can be attempted.");

                // Walk fully through under real physics.
                float beforeLocalZ = doorTransform.InverseTransformPoint(
                    capsule.transform.position).z;
                yield return DriveToDoorLocalZ(movement, doorTransform, throughLocalZ);

                Assert.IsTrue(d1.HasCrossedForward,
                    "Walking the wizard fully through an open D1 under real physics must record "
                    + "the forward crossing.");
                Assert.AreEqual(1, crossings,
                    "Crossing D1 once must raise CrossedForward exactly once.");
                Assert.IsTrue(d1.IsLocked,
                    "D1 must close and lock behind the freely moving wizard once it has crossed.");

                float afterLocalZ = doorTransform.InverseTransformPoint(
                    capsule.transform.position).z;
                Assert.Greater(afterLocalZ, beforeLocalZ,
                    "The wizard must actually have advanced in door-local Z while crossing D1; "
                    + "an unmoved wizard would make the crossing assertions above vacuous.");

                // Forward movement must remain possible after the door locks behind.
                yield return DriveToDoorLocalZ(
                    movement, doorTransform, throughLocalZ + (4f * radius));
                float advancedLocalZ = doorTransform.InverseTransformPoint(
                    capsule.transform.position).z;
                Assert.Greater(advancedLocalZ, afterLocalZ + 0.05f,
                    "Forward movement must remain possible after D1 locks behind the wizard. The "
                    + "lock seals the way back, not the way on.");

                // Drive Player Health to zero. PlayerHealth raises Died synchronously, so
                // FloorRunRestartController has already performed the whole restart by the time
                // TakeDamage returns.
                crossings = 0;
                playerHealth.TakeDamage(playerHealth.CurrentHealth);
                yield return null;
                yield return new WaitForFixedUpdate();

                Assert.IsFalse(d1.IsLocked,
                    "The FloorRunRestartController restart must clear D1's lock; a floor that "
                    + "restarts behind a still-locked first door cannot be replayed.");
                Assert.IsFalse(d1.HasCrossedForward,
                    "The restart must clear D1's crossing state rather than leaving the floor "
                    + "half-run.");
                Assert.AreEqual(0, crossings,
                    "The restart itself must not raise CrossedForward.");

                // Repeat the full crossing and verify exactly one event FOR THAT RUN.
                yield return DriveToDoorLocalZ(movement, doorTransform, approachLocalZ);
                yield return OpenDoorThroughApproach(movement, interaction, d1);
                Assert.IsTrue(d1.IsOpen, "D1 must be openable again after the restart.");

                yield return DriveToDoorLocalZ(movement, doorTransform, throughLocalZ);

                Assert.IsTrue(d1.HasCrossedForward,
                    "The post-restart crossing of D1 must be recorded.");
                Assert.AreEqual(1, crossings,
                    "After the FloorRunRestartController restart, repeating the full crossing must "
                    + "raise CrossedForward exactly once for that run. A count above one means "
                    + "run state leaked across the restart.");
            }
            finally
            {
                d1.CrossedForward -= countCrossing;
            }
        }


        // Walks the committed scene from its title screen into gameplay exactly as a player does.
        // TitleScreenController.StartGame raises WizardSelectionRequested, WizardSelectionController
        // shows its panel in response, and SelectOption plus ConfirmSelection hand a confirmed
        // selection to WizardGameEntryController, which applies the presentation, spawns the wizard
        // at the world spawn point and re-enables gameplay input on both player controllers.
        //
        // Tolerant of a scene with no title screen on purpose: such a scene is already in gameplay,
        // and the CALLER asserts the end state either way, so this can never pass vacuously.
        private static IEnumerator EnterGameplayThroughRunEntry()
        {
            var title = Object.FindFirstObjectByType<TitleScreenController>();
            if (title == null) yield break;

            title.StartGame();
            yield return null;

            var selection = Object.FindFirstObjectByType<WizardSelectionController>();
            Assert.IsNotNull(selection,
                "The committed scene shows a title screen, so it must also hold the "
                + "WizardSelectionController that the title screen hands off to.");
            Assert.IsTrue(selection.IsSelectionVisible,
                "Starting the game must show the wizard selection panel; without it no wizard can "
                + "be confirmed and gameplay input is never re-enabled.");

            selection.SelectOption(0);
            Assert.IsTrue(selection.IsConfirmationAvailable,
                "Selecting a wizard option must make confirmation available.");

            selection.ConfirmSelection();

            // One frame for WizardGameEntryController to receive WizardSelectionConfirmed, move the
            // wizard to the world spawn and re-enable input before anything drives movement.
            yield return null;
        }

        // Drives the wizard to a point expressed in DOOR-LOCAL Z through PlayerMovement's public
        // deterministic Tick seam under real CharacterController physics, never by writing the
        // transform. Bounded by a frame count, and arrival is deliberately NOT asserted: while D1
        // is sealed the doorway blocker is supposed to stop the wizard short, so a drive that does
        // not complete is frequently the correct outcome. Callers assert crossing state, which is
        // what the gate is about.
        private static IEnumerator DriveToDoorLocalZ(
            PlayerMovement movement, Transform door, float localZ)
        {
            movement.RequestDestination(door.TransformPoint(new Vector3(0f, 0f, localZ)));

            for (int frame = 0; frame < MaxDriveFrames && movement.HasActiveDestination; frame++)
            {
                movement.Tick(SimulationStepSeconds);
                yield return null;
            }

            // CharacterController.Move can settle a destination before Unity's next physics step
            // dispatches the real OnTriggerEnter, so allow a small BOUNDED number of fixed steps
            // for the crossing trigger to be delivered rather than demanding it in the same
            // rendered frame.
            for (int step = 0; step < TriggerSettleFixedSteps; step++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        // Opens the door the way the shipped game does: a ground click at the door's own selection
        // point issues the approach destination, arrival fires the real arm's-reach range trigger,
        // and that trigger starts the automatic opening timer. No BeginInteraction call, no
        // reflection, no writing IsOpen.
        //
        // The wait is bounded by the DOOR'S OWN clock - DoorInteractable.Update ticks the timer
        // with Time.deltaTime, so accumulating Time.deltaTime tracks exactly the quantity the door
        // is counting. A wall-clock deadline would instead be a race against batchmode frame rate.
        private static IEnumerator OpenDoorThroughApproach(
            PlayerMovement movement,
            PlayerInteractionController interaction,
            DoorInteractable door)
        {
            if (door.IsOpen) yield break;

            Assert.IsTrue(interaction.TryBeginDoorApproach(door.SelectionPoint),
                door.DoorId + " must accept a ground-click approach at its own SelectionPoint; "
                + "that is the production path this gate opens the door through.");

            // BOUND BY FRAMES, NOT BY A CLOCK. The wizard walks on the fixed simulation step this
            // fixture supplies, while the door timer runs on Time.deltaTime from its own Update -
            // two different clocks. An earlier version bounded this loop by accumulated
            // Time.deltaTime against Duration, which expired while the wizard was still walking
            // and reported "the door did not open" for a journey that had not finished.
            int frames = 0;
            for (; frames < MaxOpenFrames && !door.IsOpen; frames++)
            {
                movement.Tick(SimulationStepSeconds);
                yield return null;
            }

            // Asserted HERE rather than only in the caller so a failure names which half of the
            // production path stalled: the approach (the wizard never arrived, so the timer never
            // started) or the opening timer itself.
            float playerLocalZ =
                door.transform.InverseTransformPoint(movement.transform.position).z;
            float interactionLocalZ =
                door.transform.InverseTransformPoint(door.InteractionPosition).z;

            Assert.IsTrue(door.IsOpen,
                door.DoorId + " must open through the production approach-and-timer path. After "
                + frames + " frames: progress=" + door.Progress.ToString("F3")
                + " duration=" + door.Duration.ToString("F3")
                + " doorInteracting=" + door.IsInteracting
                + " playerInRange=" + door.IsPlayerInRange
                + " controllerInteracting=" + interaction.IsInteracting
                + " pendingDoor=" + (interaction.PendingDoor != null
                    ? interaction.PendingDoor.DoorId.ToString() : "<null>")
                + " currentDoor=" + (interaction.CurrentDoor != null
                    ? interaction.CurrentDoor.DoorId.ToString() : "<null>")
                + " hasActiveDestination=" + movement.HasActiveDestination
                + " movementRestricted=" + movement.IsMovementRestricted
                + " gameplayEnabled=" + movement.IsGameplayEnabled
                + " playerDoorLocalZ=" + playerLocalZ.ToString("F3")
                + " interactionDoorLocalZ=" + interactionLocalZ.ToString("F3"));
        }
    }
#endif
}
