using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class PlayerMovementPlayModeTests
    {
        private GameObject playerObject;
        private GameObject cameraObject;
        private PlayerMovement movement;
        private Camera testCamera;

        private InputActionAsset testInputActions;
        private Mouse mouseDevice;

        [SetUp]
        public void SetUp()
        {
            mouseDevice = InputSystem.AddDevice<Mouse>();

            cameraObject = new GameObject("TestCamera");
            cameraObject.tag = "MainCamera";
            testCamera = cameraObject.AddComponent<Camera>();
            testCamera.transform.SetPositionAndRotation(new Vector3(0f, 10f, -10f), Quaternion.identity);
            testCamera.transform.LookAt(Vector3.zero);

            testInputActions = ScriptableObject.CreateInstance<InputActionAsset>();
            var playerMap = testInputActions.AddActionMap("Player");
            playerMap.AddAction(
                "PointerPosition",
                InputActionType.Value,
                "<Mouse>/position",
                expectedControlLayout: "Vector2");
            playerMap.AddAction(
                "MoveToCursor",
                InputActionType.Button,
                "<Mouse>/leftButton");

            playerObject = new GameObject("TestPlayer");
            playerObject.SetActive(false);

            playerObject.AddComponent<CharacterController>();
            movement = playerObject.AddComponent<PlayerMovement>();

            // Match normal scene deserialization: serialized dependencies are assigned
            // before PlayerMovement.Awake runs.
            SetPrivateField(movement, "inputActions", testInputActions);

            // Activating the GameObject now runs Awake/OnEnable with the InputActionAsset
            // already available, allowing PlayerMovement to discover and enable its actions.
            playerObject.SetActive(true);
        }

        [TearDown]
        public void TearDown()
        {
            if (playerObject != null) Object.Destroy(playerObject);
            if (cameraObject != null) Object.Destroy(cameraObject);
            if (testInputActions != null)
            {
                testInputActions.Disable();
                Object.Destroy(testInputActions);
            }
            if (mouseDevice != null) InputSystem.RemoveDevice(mouseDevice);
        }

        // AC-002: PointerWorldTarget is the shared world-space pointer target produced by
        // projecting the cursor onto the gameplay plane. Round-trips a chosen world point
        // through the same Camera.main used by production (WorldToScreenPoint -> simulated
        // mouse position -> PointerWorldTarget) so the assertion does not depend on
        // replicating camera/screen-resolution math independently.
        [UnityTest]
        public IEnumerator PointerWorldTarget_ProjectsCursorOntoGameplayPlane_UsingCameraRoundTrip()
        {
            var expectedWorldPoint = new Vector3(3f, 0f, 2f);
            SetMouse(testCamera.WorldToScreenPoint(expectedWorldPoint), false);

            movement.Tick(0.02f);

            yield return null;

            Assert.IsTrue(movement.HasPointerWorldTarget);
            Assert.AreEqual(expectedWorldPoint.x, movement.PointerWorldTarget.x, 0.01f);
            Assert.AreEqual(expectedWorldPoint.z, movement.PointerWorldTarget.z, 0.01f);
        }

        // AC-001/VAL-001: a click sets a destination the wizard walks toward; releasing the
        // button does not cancel the approach.
        [UnityTest]
        public IEnumerator Click_SetsDestination_AndWizardWalksTowardItAfterRelease()
        {
            var target = new Vector3(2f, 0f, 2f);
            var screenPoint = testCamera.WorldToScreenPoint(target);

            SetMouse(screenPoint, true);
            movement.Tick(0.02f);
            SetMouse(screenPoint, false);

            Assert.IsTrue(movement.HasActiveDestination,
                "A single click must set an ongoing destination that persists after the button is released.");

            AdvanceMovementTime(movement, 5f);

            yield return null;

            var horizontalOffset = HorizontalOffset(movement.transform.position, target);
            Assert.Less(horizontalOffset, 0.1f,
                "Expected the wizard to walk toward and arrive at the clicked destination without the button " +
                "held.");
        }

        // AC-001/VAL-001: holding the button continues steering toward the live cursor
        // position, not just the position at the moment of the initial click.
        [UnityTest]
        public IEnumerator HoldingCursor_ContinuesSteeringTowardLiveCursorPosition()
        {
            var firstTarget = new Vector3(1f, 0f, 0f);
            var updatedTarget = new Vector3(-3f, 0f, 4f);

            SetMouse(testCamera.WorldToScreenPoint(firstTarget), true);
            movement.Tick(0.02f);

            Assert.IsTrue(movement.HasActiveDestination);

            SetMouse(testCamera.WorldToScreenPoint(updatedTarget), true);
            AdvanceMovementTime(movement, 5f);

            yield return null;

            var horizontalOffset = HorizontalOffset(movement.transform.position, updatedTarget);
            Assert.Less(horizontalOffset, 0.1f,
                "Expected continued holding to keep steering the wizard toward the live/updated cursor " +
                "position rather than only the position at the moment of the initial click.");
        }

        // AC-003: the owner-controlled movement-restriction interface blocks destination
        // movement while a restriction request is active.
        [UnityTest]
        public IEnumerator RequestMovementRestriction_PreventsDestinationMovement_WhileActive()
        {
            var target = new Vector3(3f, 0f, 0f);
            SetMouse(testCamera.WorldToScreenPoint(target), true);
            movement.Tick(0.02f);
            var positionAfterClick = movement.transform.position;

            movement.RequestMovementRestriction();
            AdvanceMovementTime(movement, 1f);

            yield return null;

            Assert.IsTrue(movement.IsMovementRestricted);
            Assert.AreEqual(positionAfterClick.x, movement.transform.position.x, 0.01f);
            Assert.AreEqual(positionAfterClick.z, movement.transform.position.z, 0.01f);
        }

        // AC-003: the restriction interface is reference-counted so an overlapping request
        // (e.g. from a second requester) is not prematurely cleared by one release, and
        // movement only resumes once every request has been released.
        [UnityTest]
        public IEnumerator ReleaseMovementRestriction_ResumesDestinationMovement_OnlyAfterEveryRequestReleased()
        {
            var target = new Vector3(3f, 0f, 0f);
            SetMouse(testCamera.WorldToScreenPoint(target), true);
            movement.Tick(0.02f);

            movement.RequestMovementRestriction();
            movement.RequestMovementRestriction();
            AdvanceMovementTime(movement, 1f);
            var restrictedPosition = movement.transform.position;

            movement.ReleaseMovementRestriction();
            AdvanceMovementTime(movement, 1f);
            var afterOneReleasePosition = movement.transform.position;

            yield return null;

            Assert.IsTrue(movement.IsMovementRestricted,
                "Overlapping restriction requests must remain active until every request is released.");
            Assert.AreEqual(restrictedPosition.x, afterOneReleasePosition.x, 0.01f,
                "One release must not clear a restriction that another requester still needs.");
            Assert.AreEqual(restrictedPosition.z, afterOneReleasePosition.z, 0.01f,
                "One release must not clear a restriction that another requester still needs.");

            movement.ReleaseMovementRestriction();
            AdvanceMovementTime(movement, 5f);

            yield return null;

            Assert.IsFalse(movement.IsMovementRestricted);
            var horizontalOffset = HorizontalOffset(movement.transform.position, target);
            Assert.Less(horizontalOffset, 0.1f,
                "Expected movement to resume toward the pending destination once fully released.");
        }

        // AC-004: the owner-controlled reset entry point restores position/rotation to the
        // floor's initial state and clears all owned movement state, including re-enabling
        // gameplay input.
        [UnityTest]
        public IEnumerator ResetMovement_RestoresInitialPositionAndClearsOwnedState()
        {
            movement.ResetMovement();
            var initialPosition = movement.transform.position;
            var target = new Vector3(5f, 0f, 5f);
            SetMouse(testCamera.WorldToScreenPoint(target), true);
            AdvanceMovementTime(movement, 0.5f);

            yield return null;

            movement.RequestMovementRestriction();
            movement.SuspendGameplayInput();
            SetMouse(testCamera.WorldToScreenPoint(target), false);

            Assert.AreNotEqual(initialPosition, movement.transform.position,
                "Test setup must actually move the wizard away from its initial position before reset.");

            movement.ResetMovement();

            Assert.AreEqual(initialPosition.x, movement.transform.position.x, 0.001f);
            Assert.AreEqual(initialPosition.y, movement.transform.position.y, 0.001f);
            Assert.AreEqual(initialPosition.z, movement.transform.position.z, 0.001f);
            Assert.IsFalse(movement.HasActiveDestination);
            Assert.IsFalse(movement.IsMovementRestricted);
            Assert.IsTrue(movement.IsGameplayEnabled);
        }

        // AC-005/VAL-002: invoking the suspend interface immediately cancels an
        // in-progress click-to-destination approach.
        [UnityTest]
        public IEnumerator SuspendGameplayInput_ImmediatelyHaltsActiveClickToDestinationApproach()
        {
            var target = new Vector3(5f, 0f, 0f);
            SetMouse(testCamera.WorldToScreenPoint(target), true);
            AdvanceMovementTime(movement, 0.5f);

            Assert.IsTrue(movement.HasActiveDestination);
            var positionAtSuspend = movement.transform.position;

            movement.SuspendGameplayInput();

            yield return null;

            Assert.IsFalse(movement.HasActiveDestination,
                "Suspending gameplay input must immediately cancel any in-progress click-to-destination " +
                "approach.");
            Assert.IsFalse(movement.IsGameplayEnabled);

            AdvanceMovementTime(movement, 1f);

            yield return null;

            Assert.AreEqual(positionAtSuspend.x, movement.transform.position.x, 0.01f,
                "Movement must not continue toward the previously active destination after suspension.");
            Assert.AreEqual(positionAtSuspend.z, movement.transform.position.z, 0.01f,
                "Movement must not continue toward the previously active destination after suspension.");
        }

        // AC-005/VAL-002: while suspended, new movement input is rejected outright, and
        // movement only resumes once the authorized EnableGameplayInput entry point is used.
        [UnityTest]
        public IEnumerator SuspendGameplayInput_RejectsNewMovementCommands_UntilReEnabled()
        {
            movement.SuspendGameplayInput();

            var target = new Vector3(4f, 0f, 4f);
            SetMouse(testCamera.WorldToScreenPoint(target), true);
            AdvanceMovementTime(movement, 1f);

            yield return null;

            Assert.IsFalse(movement.HasActiveDestination,
                "A new click-to-move command must be rejected while gameplay input is suspended.");
            var offsetFromOrigin = HorizontalOffset(movement.transform.position, Vector3.zero);
            Assert.Less(offsetFromOrigin, 0.01f,
                "The wizard must not move toward a new destination while gameplay input is suspended.");

            movement.EnableGameplayInput();
            AdvanceMovementTime(movement, 5f);

            yield return null;

            Assert.IsTrue(movement.IsGameplayEnabled);
            var offsetFromTarget = HorizontalOffset(movement.transform.position, target);
            Assert.Less(offsetFromTarget, 0.1f,
                "Expected movement toward the held cursor target to resume once re-enabled through the " +
                "authorized EnableGameplayInput entry point.");
        }

        // AC-001/VAL-001 regression: a non-step-aligned destination must complete without oscillation.
        [UnityTest]
        public IEnumerator DestinationMovement_ClampsFinalStep_AndCompletesWithoutOvershoot()
        {
            var target = new Vector3(1f, 0f, 0f);
            var screenPoint = testCamera.WorldToScreenPoint(target);

            SetMouse(screenPoint, true);
            movement.Tick(0.02f);
            SetMouse(screenPoint, false);

            AdvanceMovementTime(movement, 1f);

            yield return null;

            Assert.Less(HorizontalOffset(movement.transform.position, target), 0.001f);
            Assert.IsFalse(movement.HasActiveDestination);
        }

        private void SetMouse(Vector2 screenPosition, bool leftButtonPressed)
        {
            InputSystem.QueueStateEvent(mouseDevice, new MouseState
            {
                position = screenPosition,
                buttons = leftButtonPressed ? (ushort)(1 << (int)MouseButton.Left) : (ushort)0
            });
            InputSystem.Update();
        }

        private static float HorizontalOffset(Vector3 position, Vector3 target)
        {
            var offset = new Vector3(position.x - target.x, 0f, position.z - target.z);
            return offset.magnitude;
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
