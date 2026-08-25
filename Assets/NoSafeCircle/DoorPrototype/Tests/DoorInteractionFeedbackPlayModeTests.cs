using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // State-machine coverage for DoorInteractionFeedback that does not require pointer
    // simulation: AC-003 (selected/opening feedback and its transition), AC-004 (clearing on
    // cancel/interrupt/completion/suspend/reset), and AC-001 (distinguishable per-state
    // appearance actually applied to the renderer). Mirrors DoorInteractionPlayModeTests'
    // lightweight SetUp (no PlayerMovement involved) since none of these behaviors depend on
    // the shared pointer target.
    public class DoorInteractionFeedbackPlayModeTests
    {
        private GameObject doorObject;
        private GameObject doorVisualObject;
        private GameObject playerObject;
        private DoorInteractable door;
        private Renderer doorRenderer;
        private PlayerInteractionController controller;
        private PlayerHealth health;
        private DoorInteractionFeedback feedback;

        [SetUp]
        public void SetUp()
        {
            doorObject = new GameObject("TestDoor");
            door = doorObject.AddComponent<DoorInteractable>();

            doorVisualObject = GameObject.CreatePrimitive(PrimitiveType.Cube);
            doorVisualObject.transform.SetParent(doorObject.transform, false);
            doorRenderer = doorVisualObject.GetComponent<Renderer>();

            playerObject = new GameObject("TestPlayer");
            health = playerObject.AddComponent<PlayerHealth>();
            controller = playerObject.AddComponent<PlayerInteractionController>();

            feedback = doorObject.AddComponent<DoorInteractionFeedback>();
            SetPrivateField(feedback, "door", door);
            SetPrivateField(feedback, "interactionController", controller);
            SetPrivateField(feedback, "doorRenderer", doorRenderer);
            feedback.enabled = false;
        }

        [TearDown]
        public void TearDown()
        {
            Object.Destroy(playerObject);
            Object.Destroy(doorObject);
        }

        // AC-003: while the wizard is still automatically approaching the selected door (before
        // arrival starts the timer) feedback reports "selected" but not yet "opening"; once
        // arrival starts the automatic timer, feedback transitions to "opening".
        [UnityTest]
        public IEnumerator SelectedFeedback_TransitionsToOpening_WhenAutomaticTimerStarts()
        {
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            feedback.Tick(0.02f);
            yield return null;

            Assert.IsTrue(feedback.IsSelected,
                "A pending door approach must show accepted-selection feedback before arrival.");
            Assert.IsFalse(feedback.IsOpening,
                "The automatic opening timer has not started yet, so feedback must not show opening yet.");
            Assert.IsFalse(door.IsInteracting, "Test setup must not have started the timer yet.");

            controller.NotifyDoorInRange(door);
            feedback.Tick(0.02f);
            yield return null;

            Assert.IsTrue(door.IsInteracting, "Test setup must actually start the automatic timer on arrival.");
            Assert.IsTrue(feedback.IsSelected);
            Assert.IsTrue(feedback.IsOpening,
                "AC-003: feedback must transition to the opening state once automatic timing begins.");
        }

        // AC-004: taking damage while the door attempt is pending/in-progress resets it, and
        // feedback must clear along with the cancelled interaction.
        [UnityTest]
        public IEnumerator Feedback_Clears_WhenDamageCancelsInteraction()
        {
            controller.NotifyDoorInRange(door);
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            feedback.Tick(0.02f);
            Assert.IsTrue(feedback.IsOpening, "Test setup must actually start the opening timer.");

            health.TakeDamage(10f);
            feedback.Tick(0.02f);
            yield return null;

            Assert.IsFalse(door.IsInteracting);
            Assert.IsFalse(feedback.IsSelected, "AC-004: damage must clear selected feedback.");
            Assert.IsFalse(feedback.IsOpening, "AC-004: damage must clear opening feedback.");
        }

        // AC-004: moving away resets an in-progress attempt through the same production hook
        // PlayerMovement calls on real displacement (OnPlayerMoved).
        [UnityTest]
        public IEnumerator Feedback_Clears_WhenPlayerMovesAway()
        {
            controller.NotifyDoorInRange(door);
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            feedback.Tick(0.02f);
            Assert.IsTrue(feedback.IsOpening, "Test setup must actually start the opening timer.");

            controller.OnPlayerMoved();
            feedback.Tick(0.02f);
            yield return null;

            Assert.IsFalse(feedback.IsSelected, "AC-004: moving away must clear selected feedback.");
            Assert.IsFalse(feedback.IsOpening, "AC-004: moving away must clear opening feedback.");
        }

        // AC-003/AC-004: once the door actually completes and opens, feedback must return to its
        // base (non-selected/non-opening/non-hovered) state rather than continuing to show
        // opening feedback for an already-open door.
        [UnityTest]
        public IEnumerator Feedback_ReturnsToBaseState_WhenDoorCompletesAndOpens()
        {
            controller.NotifyDoorInRange(door);
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            feedback.Tick(0.02f);
            Assert.IsTrue(feedback.IsOpening, "Test setup must actually start the opening timer.");

            AdvanceDoorTime(door, door.Duration + 0.1f);
            feedback.Tick(0.02f);
            yield return null;

            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door.");
            Assert.IsFalse(feedback.IsSelected);
            Assert.IsFalse(feedback.IsOpening);
            Assert.IsFalse(feedback.IsHovered);
        }

        // AC-004: the owner-controlled gameplay-suspend interface must clear any in-progress
        // selected/opening feedback.
        [UnityTest]
        public IEnumerator Feedback_Clears_WhenGameplaySuspended()
        {
            controller.NotifyDoorInRange(door);
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            feedback.Tick(0.02f);
            Assert.IsTrue(feedback.IsOpening, "Test setup must actually start the opening timer.");

            controller.SuspendGameplayInput();
            feedback.Tick(0.02f);
            yield return null;

            Assert.IsFalse(feedback.IsSelected, "AC-004: suspending gameplay input must clear selected feedback.");
            Assert.IsFalse(feedback.IsOpening, "AC-004: suspending gameplay input must clear opening feedback.");
        }

        // AC-004: the owner-controlled reset entry point returns feedback to its floor-initial
        // (non-hovered/non-selected/non-opening) state, for use alongside DoorInteractable's and
        // PlayerInteractionController's own reset entry points during a floor restart.
        [UnityTest]
        public IEnumerator ResetFeedback_ReturnsToFloorInitialState()
        {
            controller.NotifyDoorInRange(door);
            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            feedback.Tick(0.02f);
            Assert.IsTrue(feedback.IsOpening, "Test setup must actually start the opening timer.");

            feedback.ResetFeedback();
            yield return null;

            Assert.IsFalse(feedback.IsHovered);
            Assert.IsFalse(feedback.IsSelected);
            Assert.IsFalse(feedback.IsOpening);
        }

        // AC-001/AC-003: base, selected, and opening states must actually apply visually
        // distinguishable colors to the door's renderer, not merely toggle internal booleans.
        [UnityTest]
        public IEnumerator Appearance_UsesDistinctColors_ForBaseSelectedAndOpeningStates()
        {
            feedback.ResetFeedback();
            yield return null;
            var baseColor = ReadRendererColor(doorRenderer);

            Assert.IsTrue(controller.TryBeginDoorApproach(door.SelectionPoint));
            feedback.Tick(0.02f);
            yield return null;
            Assert.IsFalse(feedback.IsOpening, "Test setup must isolate the selected-only state first.");
            var selectedColor = ReadRendererColor(doorRenderer);

            controller.NotifyDoorInRange(door);
            feedback.Tick(0.02f);
            yield return null;
            Assert.IsTrue(feedback.IsOpening, "Test setup must actually reach the opening state.");
            var openingColor = ReadRendererColor(doorRenderer);

            Assert.AreNotEqual(baseColor, selectedColor,
                "AC-001/AC-003: selected feedback must render a color distinct from the base sealed-door color.");
            Assert.AreNotEqual(selectedColor, openingColor,
                "AC-003: opening feedback must render a color distinct from selected feedback.");
            Assert.AreNotEqual(baseColor, openingColor,
                "AC-001/AC-003: opening feedback must render a color distinct from the base sealed-door color.");
        }

        private static Color ReadRendererColor(Renderer renderer)
        {
            var block = new MaterialPropertyBlock();
            renderer.GetPropertyBlock(block);
            return block.GetColor(Shader.PropertyToID("_Color"));
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

    // Pointer-driven coverage for DoorInteractionFeedback's hover behavior: AC-002 (hover
    // agrees with the door's own accepted-click region and clears on leaving it or when a
    // stronger selected state is active), AC-004 (hover clears while suspended), and AC-005
    // (hover consumes DoorInteractable's own selection test against PlayerMovement's shared
    // pointer target instead of an independent screen-to-world projection). Mirrors
    // DoorPrototypeSceneBuilderClickSelectionTests' real-camera/real-InputSystem pattern.
    public class DoorInteractionFeedbackHoverPlayModeTests : InputTestFixture
    {
        private Mouse mouseDevice;
        private GameObject cameraObject;
        private Camera testCamera;
        private RenderTexture testRenderTexture;
        private InputActionAsset inputActionsAsset;

        private GameObject doorObject;
        private GameObject doorVisualObject;
        private DoorInteractable door;
        private Renderer doorRenderer;

        private GameObject playerObject;
        private PlayerInteractionController interactionController;
        private PlayerMovement movement;

        private DoorInteractionFeedback feedback;

        public override void Setup()
        {
            base.Setup();
            mouseDevice = InputSystem.AddDevice<Mouse>();

            cameraObject = new GameObject("TestMainCamera");
            cameraObject.tag = "MainCamera";
            testCamera = cameraObject.AddComponent<Camera>();
            testCamera.orthographic = true;
            testCamera.orthographicSize = 10f;
            cameraObject.transform.SetPositionAndRotation(new Vector3(0f, 10f, 0f), Quaternion.Euler(90f, 0f, 0f));

            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
            testCamera.targetTexture = testRenderTexture;

            doorObject = new GameObject("TestDoor");
            door = doorObject.AddComponent<DoorInteractable>();
            doorVisualObject = GameObject.CreatePrimitive(PrimitiveType.Cube);
            doorVisualObject.transform.SetParent(doorObject.transform, false);
            doorRenderer = doorVisualObject.GetComponent<Renderer>();

            playerObject = new GameObject("TestPlayer");
            playerObject.SetActive(false);
            playerObject.transform.position = new Vector3(5f, 1f, 5f);
            playerObject.AddComponent<CharacterController>();
            playerObject.AddComponent<PlayerHealth>();
            interactionController = playerObject.AddComponent<PlayerInteractionController>();
            movement = playerObject.AddComponent<PlayerMovement>();
            inputActionsAsset = BuildInputActionsAsset();
            SetPrivateField(movement, "inputActions", inputActionsAsset);
            playerObject.SetActive(true);

            // Human-review correction: PlayerMovement.OnDisable() disables the InputAction-backed
            // pointerPositionAction/moveToCursorAction it reads from. Keep movement enabled so
            // those actions stay enabled while this fixture manually drives Tick() with simulated
            // mouse input, mirroring DoorPrototypeSceneBuilderClickSelectionTests' established
            // pattern. Each test sets the mouse position immediately before its own manual Tick()
            // call and asserts on that same call, so an incidental automatic Update() during
            // "yield return null" reads the same still-current mouse state and cannot change the
            // intended sample.

            feedback = doorObject.AddComponent<DoorInteractionFeedback>();
            SetPrivateField(feedback, "door", door);
            SetPrivateField(feedback, "playerMovement", movement);
            SetPrivateField(feedback, "interactionController", interactionController);
            SetPrivateField(feedback, "doorRenderer", doorRenderer);
            feedback.enabled = false;
        }

        public override void TearDown()
        {
            if (playerObject != null) Object.Destroy(playerObject);
            if (doorObject != null) Object.Destroy(doorObject);
            if (cameraObject != null) Object.Destroy(cameraObject);
            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                Object.Destroy(testRenderTexture);
                testRenderTexture = null;
            }
            if (inputActionsAsset != null) Object.Destroy(inputActionsAsset);

            mouseDevice = null;
            base.TearDown();
        }

        // AC-002: hovering the pointer over the door's own accepted click region shows hover
        // feedback, and the door is not otherwise selected.
        [UnityTest]
        public IEnumerator IsHovered_WhenPointerOverDoorsSelectionArea_SetsIsHoveredTrue()
        {
            var screenPoint = testCamera.WorldToScreenPoint(door.SelectionPoint);
            SetMouse(screenPoint, false);
            movement.Tick(0.02f);
            feedback.Tick(0.02f);

            yield return null;

            Assert.IsTrue(movement.HasPointerWorldTarget,
                "Test setup must actually produce a shared pointer world target via the real camera projection.");
            Assert.IsTrue(feedback.IsHovered,
                "AC-002: hovering the door's own accepted click region must show hover feedback.");
            Assert.IsFalse(feedback.IsSelected);
        }

        // AC-002: leaving the door's clickable region removes hover feedback.
        [UnityTest]
        public IEnumerator IsHovered_WhenPointerLeavesSelectionArea_ClearsIsHovered()
        {
            var overDoor = testCamera.WorldToScreenPoint(door.SelectionPoint);
            SetMouse(overDoor, false);
            movement.Tick(0.02f);
            feedback.Tick(0.02f);
            Assert.IsTrue(feedback.IsHovered, "Test setup must actually hover the door first.");

            var farAway = testCamera.WorldToScreenPoint(door.SelectionPoint + new Vector3(20f, 0f, 20f));
            SetMouse(farAway, false);
            movement.Tick(0.02f);
            feedback.Tick(0.02f);

            yield return null;

            Assert.IsFalse(feedback.IsHovered,
                "AC-002: leaving the door's clickable region must remove hover feedback.");
        }

        // AC-002: a stronger selected/approach state suppresses hover, even while the pointer
        // remains over the door.
        [UnityTest]
        public IEnumerator IsHovered_DoesNotActivate_WhenDoorIsSelected()
        {
            Assert.IsTrue(interactionController.TryBeginDoorApproach(door.SelectionPoint),
                "Test setup must actually select the door.");

            var overDoor = testCamera.WorldToScreenPoint(door.SelectionPoint);
            SetMouse(overDoor, false);
            movement.Tick(0.02f);
            feedback.Tick(0.02f);

            yield return null;

            Assert.IsTrue(feedback.IsSelected);
            Assert.IsFalse(feedback.IsHovered,
                "AC-002: a stronger selected/approach state must suppress hover feedback even while the " +
                "pointer remains over the door.");
        }

        // AC-005/VAL-002: hover feedback must exactly agree with DoorInteractable's own
        // production selection test evaluated against PlayerMovement's shared pointer target,
        // across points inside, at the edge of, and outside the door's accepted click region -
        // proving feedback does not implement a second independent screen-to-world projection.
        [UnityTest]
        public IEnumerator IsHovered_MatchesDoorsOwnSelectionTest_ForSharedPointerTarget()
        {
            var candidatePoints = new[]
            {
                door.SelectionPoint,
                door.SelectionPoint + new Vector3(1f, 0f, 0f),
                door.SelectionPoint + new Vector3(5f, 0f, 5f)
            };

            foreach (var candidate in candidatePoints)
            {
                var screenPoint = testCamera.WorldToScreenPoint(candidate);
                SetMouse(screenPoint, false);
                movement.Tick(0.02f);
                feedback.Tick(0.02f);

                yield return null;

                Assert.IsTrue(movement.HasPointerWorldTarget);
                var expectedHover = door.TryGetSelectionDistance(movement.PointerWorldTarget, out _);

                Assert.AreEqual(expectedHover, feedback.IsHovered,
                    $"AC-002/AC-005/VAL-002: hover feedback must exactly agree with DoorInteractable's own " +
                    $"production selection test against the shared PlayerMovement pointer target, for " +
                    $"candidate {candidate}.");
            }
        }

        // AC-004: hover feedback clears while gameplay input is suspended.
        [UnityTest]
        public IEnumerator IsHovered_ClearsWhenGameplaySuspended()
        {
            var overDoor = testCamera.WorldToScreenPoint(door.SelectionPoint);
            SetMouse(overDoor, false);
            movement.Tick(0.02f);
            feedback.Tick(0.02f);
            Assert.IsTrue(feedback.IsHovered, "Test setup must actually hover the door first.");

            interactionController.SuspendGameplayInput();
            movement.Tick(0.02f);
            feedback.Tick(0.02f);

            yield return null;

            Assert.IsFalse(feedback.IsHovered,
                "AC-004: hover feedback must clear while gameplay input is suspended.");
        }

        private static InputActionAsset BuildInputActionsAsset()
        {
            var asset = ScriptableObject.CreateInstance<InputActionAsset>();
            var playerMap = asset.AddActionMap("Player");
            playerMap.AddAction("PointerPosition", InputActionType.Value, binding: "<Mouse>/position");
            playerMap.AddAction("MoveToCursor", InputActionType.Button, binding: "<Mouse>/leftButton");
            return asset;
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
