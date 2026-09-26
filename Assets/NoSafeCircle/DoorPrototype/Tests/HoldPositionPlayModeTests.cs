using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Play Mode behavior fixture: temporary objects only, no canonical scene or prefab
    // mutation. Drives the real 'HoldPosition' action (constructed here by name, exactly as
    // PlayerMovementPlayModeTests constructs 'MoveToCursor'/'PointerPosition') rather than a
    // simulated flag, per NSC-128 AC-001's point that a binding present only in the asset
    // proves nothing about behaviour.
    public class HoldPositionPlayModeTests : InputTestFixture
    {
        private GameObject playerObject;
        private GameObject cameraObject;
        private GameObject shotObject;
        private PlayerMovement movement;
        private PlayerMana mana;
        private Camera testCamera;
        private RenderTexture testRenderTexture;

        private InputActionAsset testInputActions;
        private Mouse mouseDevice;
        private Keyboard keyboardDevice;

        public override void Setup()
        {
            base.Setup();

            mouseDevice = InputSystem.AddDevice<Mouse>();
            keyboardDevice = InputSystem.AddDevice<Keyboard>();

            cameraObject = new GameObject("TestCamera");
            cameraObject.tag = "MainCamera";
            testCamera = cameraObject.AddComponent<Camera>();
            testCamera.transform.SetPositionAndRotation(new Vector3(0f, 10f, -10f), Quaternion.identity);
            testCamera.transform.LookAt(Vector3.zero);

            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
            testCamera.targetTexture = testRenderTexture;

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

            // AC-001: the same action name PlayerMovement.Awake looks up via FindAction,
            // bound to both physical Shift keys, matching the committed
            // InputSystem_Actions.inputactions Keyboard&Mouse bindings.
            var holdPositionAction = playerMap.AddAction("HoldPosition", InputActionType.Button);
            holdPositionAction.AddBinding("<Keyboard>/leftShift");
            holdPositionAction.AddBinding("<Keyboard>/rightShift");

            playerMap.devices = new InputDevice[] { mouseDevice, keyboardDevice };

            playerObject = new GameObject("TestPlayer");
            playerObject.SetActive(false);

            playerObject.AddComponent<CharacterController>();
            movement = playerObject.AddComponent<PlayerMovement>();
            mana = playerObject.AddComponent<PlayerMana>();

            SetPrivateField(movement, "inputActions", testInputActions);

            playerObject.SetActive(true);
        }

        public override void TearDown()
        {
            if (shotObject != null) Object.Destroy(shotObject);
            if (playerObject != null) Object.Destroy(playerObject);
            if (cameraObject != null) Object.Destroy(cameraObject);

            if (testInputActions != null)
            {
                testInputActions.Disable();
                Object.Destroy(testInputActions);
            }

            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                Object.Destroy(testRenderTexture);
            }

            shotObject = null;
            playerObject = null;
            cameraObject = null;
            movement = null;
            mana = null;
            testCamera = null;
            testInputActions = null;
            testRenderTexture = null;
            mouseDevice = null;
            keyboardDevice = null;

            base.TearDown();
        }

        // AC-002/VAL-001: a fresh pointer press while HoldPosition is held leaves the wizard's
        // world position unchanged over a fixed number of fixed steps, while the same press
        // with the action released moves it. The two runs are compared against each other
        // (not against hard-coded coordinates), as VAL-001 requires.
        [UnityTest]
        public IEnumerator FreshPointerPress_WhileHeld_MovesNegligibly_ComparedToSamePressReleased()
        {
            var target = new Vector3(3f, 0f, 0f);
            var screenPoint = testCamera.WorldToScreenPoint(target);

            Press(keyboardDevice.leftShiftKey);
            SetMouse(screenPoint, true);
            movement.Tick(0.02f);

            var startHeld = movement.transform.position;
            AdvanceMovementTime(movement, 2f);
            var heldDisplacement = HorizontalOffset(movement.transform.position, startHeld);

            SetMouse(screenPoint, false);
            Release(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);
            movement.ResetMovement();

            SetMouse(screenPoint, true);
            movement.Tick(0.02f);

            var startReleased = movement.transform.position;
            AdvanceMovementTime(movement, 2f);
            var releasedDisplacement = HorizontalOffset(movement.transform.position, startReleased);

            yield return null;

            Assert.Greater(releasedDisplacement, 0.5f,
                "Test setup must actually move the wizard once the action is released, or the comparison below " +
                "is meaningless.");
            Assert.Less(heldDisplacement, releasedDisplacement * 0.1f,
                "A fresh pointer press while HoldPosition is held must move the wizard negligibly compared to " +
                "the same press with the action released.");
        }

        // AC-002/VAL-001: releasing HoldPosition restores movement toward a pointer press that
        // remains held across the release, matching the same continuous-hold steering
        // PlayerMovementPlayModeTests already proves for MoveToCursor.
        [UnityTest]
        public IEnumerator ReleasingHoldPosition_RestoresMovement_WhilePointerPressRemainsHeld()
        {
            var target = new Vector3(3f, 0f, 0f);
            var screenPoint = testCamera.WorldToScreenPoint(target);

            Press(keyboardDevice.leftShiftKey);
            SetMouse(screenPoint, true);
            movement.Tick(0.02f);

            Assert.IsFalse(movement.HasActiveDestination,
                "A fresh press while HoldPosition is held must not set a destination.");

            Release(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            AdvanceMovementTime(movement, 2f);

            yield return null;

            Assert.Less(HorizontalOffset(movement.transform.position, target), 0.1f,
                "Releasing HoldPosition must restore movement toward the still-held pointer target.");
        }

        // AC-002: the modifier is held, not toggled. A press-and-release leaves no lasting
        // suppression state, and the restriction count returns to its starting value.
        [UnityTest]
        public IEnumerator PressAndReleaseCycle_LeavesNoLastingRestriction_AndRestrictionCountReturnsToBaseline()
        {
            var baselineCount = GetPrivateField<int>(movement, "movementRestrictionCount");

            Press(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);

            Assert.IsTrue(movement.IsMovementRestricted,
                "Test setup must actually restrict movement while the action is held.");

            Release(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);

            yield return null;

            Assert.IsFalse(movement.IsMovementRestricted,
                "A press-and-release must leave no lasting suppression state (hold, not toggle).");
            Assert.AreEqual(baselineCount, GetPrivateField<int>(movement, "movementRestrictionCount"),
                "The restriction count must return to its starting value after a press-release cycle.");
        }

        // AC-001: the action responds to either physical Shift key.
        [UnityTest]
        public IEnumerator HoldPosition_RespondsToEitherPhysicalShiftKey()
        {
            Press(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);
            Assert.IsTrue(movement.IsMovementRestricted, "The left Shift key must suppress movement.");
            Release(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);
            Assert.IsFalse(movement.IsMovementRestricted);

            yield return null;

            Press(keyboardDevice.rightShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);
            Assert.IsTrue(movement.IsMovementRestricted, "The right Shift key must also suppress movement.");
            Release(keyboardDevice.rightShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);
            Assert.IsFalse(movement.IsMovementRestricted);
        }

        // AC-003: suppression uses the existing reference-counted movement restriction and
        // composes with a concurrently held restriction (e.g. a Fireball charge) instead of
        // fighting it - one release must not prematurely free a restriction another requester
        // still needs, and the count returns to baseline once every requester has released.
        [UnityTest]
        public IEnumerator HoldPosition_ComposesWithConcurrentRestriction_WithoutPrematureFreezeOrRelease()
        {
            var baselineCount = GetPrivateField<int>(movement, "movementRestrictionCount");

            movement.RequestMovementRestriction();
            Assert.IsTrue(movement.IsMovementRestricted,
                "Test setup must actually hold a concurrent (e.g. Fireball charge) restriction first.");

            Press(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);

            Assert.AreEqual(baselineCount + 2, GetPrivateField<int>(movement, "movementRestrictionCount"),
                "Holding the action while another restriction is already active must add exactly one more " +
                "restriction, not replace or duplicate the existing one.");

            Release(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);

            yield return null;

            Assert.AreEqual(baselineCount + 1, GetPrivateField<int>(movement, "movementRestrictionCount"),
                "Releasing the action must release exactly one restriction.");
            Assert.IsTrue(movement.IsMovementRestricted,
                "The pre-existing (e.g. Fireball charge) restriction must not be prematurely freed by the " +
                "action's release.");

            movement.ReleaseMovementRestriction();

            Assert.AreEqual(baselineCount, GetPrivateField<int>(movement, "movementRestrictionCount"));
            Assert.IsFalse(movement.IsMovementRestricted);
        }

        // AC-003/VAL-001: the restriction is released when gameplay input is suspended, so a
        // title-screen transition mid-hold cannot strand it - the count returns to baseline
        // even though the action is never released.
        [UnityTest]
        public IEnumerator SuspendGameplayInput_MidHold_ReleasesStrandedRestriction_RestrictionCountReturnsToBaseline()
        {
            var baselineCount = GetPrivateField<int>(movement, "movementRestrictionCount");

            Press(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);

            Assert.IsTrue(movement.IsMovementRestricted,
                "Test setup must actually hold the restriction before suspending gameplay input.");

            movement.SuspendGameplayInput();

            yield return null;

            Assert.AreEqual(baselineCount, GetPrivateField<int>(movement, "movementRestrictionCount"),
                "Suspending gameplay input mid-hold must not strand the restriction, even though the action " +
                "itself is never released.");
            Assert.IsFalse(movement.IsMovementRestricted);
        }

        // AC-004: this task touches no spell component, cast path, mana cost or cooldown. A
        // cast performed while HoldPosition is held still spends mana and produces its
        // projectile, driven directly through the untouched PlayerMana/FireballProjectile
        // components rather than a test-only simulation of them.
        [UnityTest]
        public IEnumerator CastPerformedWhileHeld_StillSpendsMana_AndProducesProjectile()
        {
            Press(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);

            Assert.IsTrue(movement.IsMovementRestricted,
                "Test setup must actually hold movement-suppression before exercising the cast path.");

            var manaBeforeCast = mana.CurrentMana;
            var spent = mana.Spend(20f);

            Assert.IsTrue(spent, "A cast performed while HoldPosition is held must still be able to spend mana.");
            Assert.Less(mana.CurrentMana, manaBeforeCast,
                "Mana must actually decrease from a cast performed while HoldPosition is held.");

            shotObject = new GameObject("TestShot");
            var shot = shotObject.AddComponent<FireballProjectile>();
            var startPosition = movement.transform.position;
            shot.Launch(
                startPosition,
                Vector3.forward,
                10f,
                3f,
                0.5f,
                25f,
                0f,
                playerObject.GetComponent<CharacterController>());

            Assert.IsTrue(shot.IsFlying,
                "A cast performed while HoldPosition is held must still produce a flying projectile.");

            shot.Tick(0.1f);

            yield return null;

            Assert.Greater(Vector3.Distance(shot.transform.position, startPosition), 0.01f,
                "The projectile produced by a cast while HoldPosition is held must actually fly.");
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

        private static T GetPrivateField<T>(object target, string fieldName)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            return (T)field.GetValue(target);
        }
    }

    // AC-005/INT-001: while HoldPosition is held, a fresh pointer press issues no destination,
    // so click-to-approach-a-door is also suppressed for as long as it is held. Releasing the
    // action restores approach for a new press. Mirrors
    // PlayerMovementDoorApproachIntegrationPlayModeTests' setup.
    public class HoldPositionDoorApproachPlayModeTests : InputTestFixture
    {
        private GameObject playerObject;
        private GameObject cameraObject;
        private GameObject doorObject;
        private PlayerMovement movement;
        private PlayerInteractionController interactionController;
        private DoorInteractable door;
        private Camera testCamera;
        private RenderTexture testRenderTexture;
        private InputActionAsset testInputActions;
        private Mouse mouseDevice;
        private Keyboard keyboardDevice;

        public override void Setup()
        {
            base.Setup();

            mouseDevice = InputSystem.AddDevice<Mouse>();
            keyboardDevice = InputSystem.AddDevice<Keyboard>();

            cameraObject = new GameObject("TestCamera");
            cameraObject.tag = "MainCamera";
            testCamera = cameraObject.AddComponent<Camera>();
            testCamera.transform.SetPositionAndRotation(new Vector3(0f, 10f, -10f), Quaternion.identity);
            testCamera.transform.LookAt(Vector3.zero);

            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
            testCamera.targetTexture = testRenderTexture;

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
            var holdPositionAction = playerMap.AddAction("HoldPosition", InputActionType.Button);
            holdPositionAction.AddBinding("<Keyboard>/leftShift");
            holdPositionAction.AddBinding("<Keyboard>/rightShift");
            playerMap.devices = new InputDevice[] { mouseDevice, keyboardDevice };

            doorObject = new GameObject("TestDoor");
            doorObject.transform.position = new Vector3(2f, 0f, 2f);
            door = doorObject.AddComponent<DoorInteractable>();

            playerObject = new GameObject("TestPlayer");
            playerObject.SetActive(false);

            playerObject.AddComponent<CharacterController>();
            playerObject.AddComponent<PlayerHealth>();
            interactionController = playerObject.AddComponent<PlayerInteractionController>();
            movement = playerObject.AddComponent<PlayerMovement>();

            SetPrivateField(movement, "inputActions", testInputActions);
            SetPrivateField(movement, "interactionController", interactionController);

            playerObject.SetActive(true);
        }

        public override void TearDown()
        {
            if (playerObject != null) Object.Destroy(playerObject);
            if (cameraObject != null) Object.Destroy(cameraObject);
            if (doorObject != null) Object.Destroy(doorObject);

            if (testInputActions != null)
            {
                testInputActions.Disable();
                Object.Destroy(testInputActions);
            }

            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                Object.Destroy(testRenderTexture);
            }

            playerObject = null;
            cameraObject = null;
            doorObject = null;
            movement = null;
            interactionController = null;
            door = null;
            testCamera = null;
            testInputActions = null;
            testRenderTexture = null;
            mouseDevice = null;
            keyboardDevice = null;

            base.TearDown();
        }

        [UnityTest]
        public IEnumerator FreshPressOnDoor_WhileHeld_DoesNotBeginApproach_ButWorksOnceReleased()
        {
            var doorScreenPoint = testCamera.WorldToScreenPoint(door.SelectionPoint);

            Press(keyboardDevice.leftShiftKey);
            SetMouse(doorScreenPoint, true);
            movement.Tick(0.02f);

            Assert.IsFalse(interactionController.HasLockedDoorInteraction,
                "A fresh press on the door while HoldPosition is held must not begin approach.");
            Assert.IsFalse(movement.HasActiveDestination);

            SetMouse(doorScreenPoint, false);
            movement.Tick(0.02f);
            Release(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);

            yield return null;

            SetMouse(doorScreenPoint, true);
            movement.Tick(0.02f);

            Assert.IsTrue(interactionController.HasLockedDoorInteraction,
                "Releasing HoldPosition must restore door click-to-approach for a new press.");
        }

        // AC-005: "a press made while held is NOT replayed or queued on release" - a pointer
        // press on the door that remains held across HoldPosition's release must not
        // retroactively begin the door approach once the action comes back up.
        [UnityTest]
        public IEnumerator PressHeldAcrossRelease_DoesNotRetroactivelyBeginDoorApproach()
        {
            var doorScreenPoint = testCamera.WorldToScreenPoint(door.SelectionPoint);

            Press(keyboardDevice.leftShiftKey);
            SetMouse(doorScreenPoint, true);
            movement.Tick(0.02f);

            Assert.IsFalse(interactionController.HasLockedDoorInteraction,
                "Test setup must actually suppress the door approach while HoldPosition is held.");

            Release(keyboardDevice.leftShiftKey);
            InputSystem.Update();
            movement.Tick(0.02f);

            yield return null;

            Assert.IsFalse(interactionController.HasLockedDoorInteraction,
                "A pointer press held across HoldPosition's release must not be replayed/queued into a door " +
                "approach once the action comes back up.");
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

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }
    }
}
