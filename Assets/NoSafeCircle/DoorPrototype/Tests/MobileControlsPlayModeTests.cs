using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using NoSafeCircle.DoorPrototype.Hud;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.InputSystem.UI;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Candidate for Vincent's 2026-09-27 mobile controls rules, not TaskGraph delivery proof.
    // Play Mode component tests plus one read-only prefab/UI-input integration test.
    // Everything instantiated here belongs to a fresh in-memory scene; no assets are saved.
    public sealed class MobileControlsPlayModeTests : InputTestFixture
    {
        private Scene previousScene;
        private Scene testScene;
        private PlayerMovement movement;
        private PlayerInteractionController interaction;
        private PlayerMana mana;
        private Camera testCamera;
        private RenderTexture testRenderTexture;
        private InputActionAsset testInputActions;
        private Mouse mouseDevice;
        private readonly List<Vector3> fireTargets = new List<Vector3>();

        public override void Setup()
        {
            base.Setup();
            previousScene = SceneManager.GetActiveScene();
            testScene = SceneManager.CreateScene("MobileControlsTest-" + System.Guid.NewGuid().ToString("N"));
            SceneManager.SetActiveScene(testScene);
            fireTargets.Clear();

            mouseDevice = InputSystem.AddDevice<Mouse>();
            Keyboard keyboardDevice = InputSystem.AddDevice<Keyboard>();
            GameObject cameraObject = new GameObject("MobileControlsTestCamera");
            cameraObject.tag = "MainCamera";
            testCamera = cameraObject.AddComponent<Camera>();
            testCamera.transform.position = new Vector3(0f, 10f, -10f);
            testCamera.transform.LookAt(Vector3.zero);
            SetCameraPixelSurface(800, 600);

            testInputActions = ScriptableObject.CreateInstance<InputActionAsset>();
            InputActionMap playerMap = testInputActions.AddActionMap("Player");
            playerMap.AddAction("PointerPosition", InputActionType.Value, "<Mouse>/position",
                expectedControlLayout: "Vector2");
            playerMap.AddAction("MoveToCursor", InputActionType.Button, "<Mouse>/leftButton");
            playerMap.AddAction("HoldPosition", InputActionType.Button, "<Keyboard>/z");
            playerMap.devices = new InputDevice[] { mouseDevice, keyboardDevice };

            GameObject playerObject = new GameObject("MobileControlsTestPlayer");
            playerObject.SetActive(false);
            playerObject.AddComponent<CharacterController>();
            playerObject.AddComponent<PlayerHealth>();
            mana = playerObject.AddComponent<PlayerMana>();
            interaction = playerObject.AddComponent<PlayerInteractionController>();
            movement = playerObject.AddComponent<PlayerMovement>();
            SetSerializedField(movement, "inputActions", testInputActions);
            SetSerializedField(movement, "interactionController", interaction);
            playerObject.SetActive(true);
            movement.WorldFireRequested += RecordFireTarget;
        }

        public override void TearDown()
        {
            if (movement != null) movement.WorldFireRequested -= RecordFireTarget;
            if (testCamera != null) testCamera.targetTexture = null;
            // Scoped cleanup includes DemoRunFlow's unparented projectile visuals and UI module.
            if (testScene.IsValid() && testScene.isLoaded)
                foreach (GameObject root in testScene.GetRootGameObjects())
                    UnityEngine.Object.DestroyImmediate(root);
            if (testInputActions != null)
            {
                testInputActions.Disable();
                UnityEngine.Object.DestroyImmediate(testInputActions);
            }
            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                UnityEngine.Object.DestroyImmediate(testRenderTexture);
            }
            testInputActions = null;
            testRenderTexture = null;
            movement = null;
            interaction = null;
            mana = null;
            testCamera = null;
            mouseDevice = null;
            base.TearDown();
        }

        [UnityTearDown]
        public IEnumerator UnloadOwnedTestSceneWithoutSaving()
        {
            if (!testScene.IsValid() || !testScene.isLoaded) yield break;
            Scene restoreScene = previousScene;
            if (!restoreScene.IsValid() || !restoreScene.isLoaded || restoreScene == testScene)
                restoreScene = SceneManager.CreateScene("MobileControlsTestCleanup");
            SceneManager.SetActiveScene(restoreScene);
            yield return SceneManager.UnloadSceneAsync(testScene);
            testScene = default;
        }

        // Regression: the lower held button changes tap meaning while retaining the old route.
        [UnityTest]
        public IEnumerator FireWhileMoving_RoutesTapToFire_AndKeepsOriginalDestination()
        {
            Vector3 walkTarget = new Vector3(3f, 0f, 0f);
            Vector3 aimTarget = new Vector3(-3f, 0f, 3f);
            movement.RequestDestination(walkTarget);
            movement.Tick(0.05f);
            Assert.IsTrue(movement.HasActiveDestination);

            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, 11, true);
            Assert.AreEqual(MobileFireMode.FireWhileMoving, movement.CurrentMobileFireMode);
            Assert.IsFalse(movement.IsMovementRestricted);
            movement.HandleWorldTap(ScreenPoint(aimTarget));
            Assert.AreEqual(1, fireTargets.Count);
            Assert.Less(HorizontalDistance(fireTargets[0], aimTarget), 0.02f);
            Assert.IsTrue(movement.HasActiveDestination);

            AdvanceMovement(1f);
            Assert.Less(HorizontalDistance(movement.transform.position, walkTarget), 0.1f,
                "Firing must retain the existing route rather than walk toward the aim point.");
            Assert.Greater(HorizontalDistance(movement.transform.position, aimTarget), 1f);
            yield return null;
        }

        // Regression: Stand erases the route, including mouse movement commands during the hold.
        [UnityTest]
        public IEnumerator StandAndFire_CancelsImmediately_AndReleaseRequiresAFreshWalkCommand()
        {
            Vector3 oldTarget = new Vector3(5f, 0f, 0f);
            Vector3 newTarget = new Vector3(-3f, 0f, 2f);
            movement.RequestDestination(oldTarget);
            movement.Tick(0.1f);
            Assert.IsTrue(movement.HasActiveDestination);
            Vector3 stoppedPosition = movement.transform.position;

            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 12, true);
            Assert.IsFalse(movement.HasActiveDestination,
                "Stand must cancel synchronously, before the next movement tick.");
            Assert.IsTrue(movement.IsMovementRestricted);
            movement.HandleWorldTap(ScreenPoint(newTarget));
            Assert.AreEqual(1, fireTargets.Count);
            SetMouse(ScreenPoint(newTarget), true);
            AdvanceMovement(0.5f);
            Assert.IsFalse(movement.HasActiveDestination);
            Assert.Less(HorizontalDistance(movement.transform.position, stoppedPosition), 0.001f);
            SetMouse(ScreenPoint(newTarget), false);
            movement.Tick(0.02f);

            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 12, false);
            AdvanceMovement(0.5f);
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode);
            Assert.IsFalse(movement.HasActiveDestination,
                "Releasing Stand must never restore the canceled route.");
            Assert.Less(HorizontalDistance(movement.transform.position, stoppedPosition), 0.001f);

            movement.HandleWorldTap(ScreenPoint(newTarget));
            Assert.IsTrue(movement.HasActiveDestination);
            AdvanceMovement(2f);
            Assert.Less(HorizontalDistance(movement.transform.position, newTarget), 0.1f);
            Assert.AreEqual(1, fireTargets.Count, "The fresh ordinary tap should walk, not fire.");
            yield return null;
        }

        // Regression: each button owns its pointer set; Stand wins in either press order.
        [UnityTest]
        public IEnumerator StandPriorityAndMultiplePointers_OnlyEndWhenTheirOwnHoldsEnd()
        {
            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, 21, true);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 22, true);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 23, true);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 23, true);
            Assert.AreEqual(MobileFireMode.StandAndFire, movement.CurrentMobileFireMode);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 22, false);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 999, false);
            Assert.AreEqual(MobileFireMode.StandAndFire, movement.CurrentMobileFireMode,
                "One release cannot free another finger's Stand hold.");
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 23, false);
            Assert.AreEqual(MobileFireMode.FireWhileMoving, movement.CurrentMobileFireMode);
            Assert.IsFalse(movement.IsMovementRestricted);
            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, 21, false);
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode);

            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 24, true);
            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, 25, true);
            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, 26, true);
            Assert.AreEqual(MobileFireMode.StandAndFire, movement.CurrentMobileFireMode);
            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, 25, false);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 24, false);
            Assert.AreEqual(MobileFireMode.FireWhileMoving, movement.CurrentMobileFireMode);
            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, 26, false);
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode);
            yield return null;
        }

        // Regression: suspension/reset clears mobile state while preserving another owner's
        // reference-counted restriction during suspension (reset intentionally resets all).
        [UnityTest]
        public IEnumerator SuspendAndReset_ClearMobileHolds_WithoutReplayingOldInput()
        {
            movement.RequestDestination(new Vector3(5f, 0f, 0f));
            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, 31, true);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 32, true);
            movement.RequestMovementRestriction();
            movement.SuspendGameplayInput();
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode);
            Assert.IsFalse(movement.HasActiveDestination);
            Assert.IsTrue(movement.IsMovementRestricted,
                "Suspension must not release another owner's movement restriction.");
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 33, true);
            movement.HandleWorldTap(ScreenPoint(new Vector3(3f, 0f, 0f)));
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode);
            Assert.AreEqual(0, fireTargets.Count);
            movement.EnableGameplayInput();
            movement.ReleaseMovementRestriction();
            Assert.IsFalse(movement.IsMovementRestricted);
            Assert.IsFalse(movement.HasActiveDestination);

            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, 34, true);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 35, true);
            movement.ResetMovement();
            Assert.IsTrue(movement.IsGameplayEnabled);
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode);
            Assert.IsFalse(movement.IsMovementRestricted);
            Assert.IsFalse(movement.HasActiveDestination);
            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, 36, true);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 35, false);
            Assert.AreEqual(MobileFireMode.FireWhileMoving, movement.CurrentMobileFireMode,
                "A stale release must not clear a different fresh pointer hold.");
            movement.ClearMobileFireHolds();
            movement.ClearMobileFireHolds();
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode);
            yield return null;
        }

        // Regression: a stop command must also cancel the selected door, not strand its lock.
        [UnityTest]
        public IEnumerator StandCancelsPendingDoor_AndCancelDoorCommandResetsOpeningProgress()
        {
            GameObject doorObject = new GameObject("MobileControlsTestDoor");
            doorObject.transform.position = new Vector3(5f, 0f, 0f);
            DoorInteractable door = doorObject.AddComponent<DoorInteractable>();
            Assert.IsTrue(interaction.TryBeginDoorApproach(door.SelectionPoint));
            Assert.IsTrue(interaction.HasLockedDoorInteraction);
            Assert.IsTrue(movement.HasActiveDestination);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 41, true);
            Assert.IsFalse(interaction.HasLockedDoorInteraction);
            Assert.IsFalse(interaction.IsInteracting);
            Assert.IsFalse(movement.HasActiveDestination);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, 41, false);

            interaction.NotifyDoorInRange(door);
            interaction.BeginInteraction();
            Assert.IsTrue(interaction.IsInteracting);
            door.Tick(0.1f);
            Assert.Greater(door.Progress, 0f, "The test must exercise a running opening timer.");
            interaction.CancelDoorCommand();
            Assert.IsFalse(interaction.IsInteracting);
            Assert.IsNull(interaction.PendingDoor);
            Assert.AreEqual(0f, door.Progress);
            Assert.IsFalse(movement.HasActiveDestination);
            yield return null;
        }

        // Regression: suppress the complete mouse gesture that began over UI, not just the
        // frame in which its current screen position overlaps UI.
        [UnityTest]
        public IEnumerator UiOriginMousePress_DraggedIntoWorld_DoesNotStartMovement()
        {
            CreateEventSystem();
            GameObject canvasObject = new GameObject("MobileControlsMouseGuardCanvas",
                typeof(RectTransform), typeof(Canvas), typeof(GraphicRaycaster));
            canvasObject.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            GameObject blocker = new GameObject("MouseUiBlocker", typeof(RectTransform), typeof(Image));
            blocker.transform.SetParent(canvasObject.transform, false);
            RectTransform rect = blocker.GetComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.zero;
            rect.pivot = Vector2.zero;
            rect.anchoredPosition = new Vector2(20f, 20f);
            rect.sizeDelta = new Vector2(120f, 120f);
            blocker.GetComponent<Image>().raycastTarget = true;
            Canvas.ForceUpdateCanvases();
            Vector2 uiPoint = RectTransformUtility.WorldToScreenPoint(null, rect.TransformPoint(rect.rect.center));
            Vector3 worldTarget = new Vector3(3f, 0f, 3f);

            SetMouse(uiPoint, true);
            movement.Tick(0.02f);
            Assert.IsFalse(movement.HasActiveDestination);
            SetMouse(ScreenPoint(worldTarget), true);
            Vector3 stoppedPosition = movement.transform.position;
            AdvanceMovement(0.5f);
            Assert.IsFalse(movement.HasActiveDestination);
            Assert.Less(HorizontalDistance(movement.transform.position, stoppedPosition), 0.001f);

            SetMouse(ScreenPoint(worldTarget), false);
            movement.Tick(0.02f);
            SetMouse(ScreenPoint(worldTarget), true);
            movement.Tick(0.02f);
            Assert.IsTrue(movement.HasActiveDestination,
                "A genuinely new world-origin mouse press must still work.");
            yield return null;
        }

        // Regression: the real cast owner validates gameplay/aim before mana consumption,
        // emits a projectile, and applies cooldown equally for touch-triggered calls.
        [UnityTest]
        public IEnumerator DemoCastApi_GatesSuspensionAndInvalidAim_AndSpendsManaOnceForOneProjectile()
        {
            DemoRunFlow flow = new GameObject("MobileControlsTestRunFlow").AddComponent<DemoRunFlow>();
            flow.BindToPlayer(movement);
            Assert.IsFalse(flow.HasEnded);
            Vector3 aimTarget = new Vector3(4f, 0f, 0f);
            float initialMana = mana.CurrentMana;

            movement.SuspendGameplayInput();
            Assert.IsFalse(flow.TryCastFireball(aimTarget));
            Assert.AreEqual(initialMana, mana.CurrentMana);
            Assert.AreEqual(0, CountNamedObjects("Fireball"));
            movement.EnableGameplayInput();
            Assert.IsFalse(flow.TryCastFireball(movement.transform.position));
            Assert.AreEqual(initialMana, mana.CurrentMana);
            Assert.AreEqual(0, CountNamedObjects("Fireball"));

            Assert.IsTrue(flow.TryCastFireball(aimTarget));
            float manaAfterCast = mana.CurrentMana;
            Assert.Less(manaAfterCast, initialMana);
            Assert.AreEqual(1, CountNamedObjects("Fireball"));
            Assert.IsFalse(flow.TryCastFireball(aimTarget), "Cooldown must reject an immediate duplicate cast.");
            Assert.AreEqual(manaAfterCast, mana.CurrentMana);
            Assert.AreEqual(1, CountNamedObjects("Fireball"));
            yield return null;
        }

        // Read-only prefab and real Input System UI regression. Requires a landscape runner.
        // A held UI finger must not block a second world finger or turn either drag into taps.
        [UnityTest]
        public IEnumerator RealTwoTouchUi_HoldsStand_CastsOnceWithSecondFinger_AndClearsAcrossSuspension()
        {
            Assert.Greater(Screen.width, Screen.height, "Run this mobile UI case in landscape.");
            SetCameraPixelSurface(Screen.width, Screen.height);
            Touchscreen touchscreen = InputSystem.AddDevice<Touchscreen>();
            CreateEventSystem();
            GameObject template = Resources.Load<GameObject>("Hud/MobileControls");
            Assert.IsNotNull(template);
            GameObject canvasObject = new GameObject("MobileControlsTouchTestCanvas",
                typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            canvasObject.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            CanvasScaler scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.matchWidthOrHeight = 0.5f;
            GameObject controlsObject = UnityEngine.Object.Instantiate(template, canvasObject.transform, false);
            MobileGameplayControls controls = controlsObject.GetComponentInChildren<MobileGameplayControls>(true);
            Assert.IsNotNull(controls);
            controls.Bind(movement, null);
            yield return null;
            Canvas.ForceUpdateCanvases();

            RectTransform standButton = FindNamed(controlsObject, "StandFireButton").GetComponent<RectTransform>();
            RectTransform moveButton = FindNamed(controlsObject, "MoveFireButton").GetComponent<RectTransform>();
            Assert.IsTrue(standButton.gameObject.activeInHierarchy);
            Assert.IsTrue(moveButton.gameObject.activeInHierarchy);
            Vector2 standPoint = UiCenter(standButton);
            Vector2 movePoint = UiCenter(moveButton);
            Assert.Greater(standPoint.y, movePoint.y, "Stand must be the upper button in the stack.");
            Assert.AreEqual(standPoint.x, movePoint.x, 2f, "The buttons must form one vertical stack.");
            Assert.Less(standPoint.x, Screen.width * 0.5f, "The stack must remain on the left.");
            Assert.Less(standPoint.y, Screen.height * 0.5f, "The stack must remain near the bottom.");

            BeginTouch(51, standPoint, screen: touchscreen);
            yield return null;
            Assert.AreEqual(MobileFireMode.StandAndFire, movement.CurrentMobileFireMode);
            Assert.AreEqual(0, fireTargets.Count, "The UI finger itself must never fire or walk.");
            Assert.IsFalse(movement.HasActiveDestination);

            Vector2 worldPoint = new Vector2(Screen.width * 0.8f, Screen.height * 0.55f);
            BeginTouch(52, worldPoint, screen: touchscreen);
            yield return null;
            Assert.AreEqual(1, fireTargets.Count,
                "A second finger in the world must fire even while the first remains over UI.");
            MoveTouch(52, worldPoint + new Vector2(-20f, 20f), screen: touchscreen);
            yield return null;
            yield return null;
            Assert.AreEqual(1, fireTargets.Count, "A held or dragged world finger must not repeat the tap.");

            movement.SuspendGameplayInput();
            yield return null;
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode);
            movement.EnableGameplayInput();
            yield return null;
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode,
                "Returning to gameplay cannot replay the still-down UI finger.");
            Assert.AreEqual(1, fireTargets.Count);
            Assert.IsFalse(movement.HasActiveDestination);
            MoveTouch(51, worldPoint, screen: touchscreen);
            yield return null;
            Assert.AreEqual(1, fireTargets.Count, "Dragging a UI-origin finger into the world is not a new tap.");
            Assert.IsFalse(movement.HasActiveDestination);
            EndTouch(52, worldPoint + new Vector2(-20f, 20f), screen: touchscreen);
            EndTouch(51, worldPoint, screen: touchscreen);
            yield return null;
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode);

            // Also exercise the lower button's serialized mode through real pointer events.
            movement.RequestDestination(new Vector3(20f, 0f, 0f));
            BeginTouch(53, movePoint, screen: touchscreen);
            yield return null;
            Assert.AreEqual(MobileFireMode.FireWhileMoving, movement.CurrentMobileFireMode);
            Assert.IsTrue(movement.HasActiveDestination,
                "The lower button must retain the active route.");
            BeginTouch(54, worldPoint, screen: touchscreen);
            yield return null;
            Assert.AreEqual(2, fireTargets.Count);
            Assert.IsTrue(movement.HasActiveDestination);
            EndTouch(54, worldPoint, screen: touchscreen);
            EndTouch(53, movePoint, screen: touchscreen);
            yield return null;
            Assert.AreEqual(MobileFireMode.None, movement.CurrentMobileFireMode);
        }

        private void RecordFireTarget(Vector3 target) => fireTargets.Add(target);

        private Vector2 ScreenPoint(Vector3 point) => testCamera.WorldToScreenPoint(point);

        private void AdvanceMovement(float seconds)
        {
            for (float elapsed = 0f; elapsed < seconds; elapsed += 0.02f) movement.Tick(0.02f);
        }

        private void SetMouse(Vector2 position, bool pressed)
        {
            InputSystem.QueueStateEvent(mouseDevice, new MouseState
            {
                position = position,
                buttons = pressed ? (ushort)(1 << (int)MouseButton.Left) : (ushort)0
            });
            InputSystem.Update();
        }

        private void SetCameraPixelSurface(int width, int height)
        {
            if (testRenderTexture != null)
            {
                testCamera.targetTexture = null;
                testRenderTexture.Release();
                UnityEngine.Object.DestroyImmediate(testRenderTexture);
            }
            testRenderTexture = new RenderTexture(width, height, 24);
            testRenderTexture.Create();
            testCamera.targetTexture = testRenderTexture;
        }

        private static void CreateEventSystem()
        {
            GameObject root = new GameObject("MobileControlsTestEventSystem",
                typeof(EventSystem), typeof(InputSystemUIInputModule));
            root.GetComponent<InputSystemUIInputModule>().AssignDefaultActions();
        }

        private static Vector2 UiCenter(RectTransform rect)
        {
            Canvas canvas = rect.GetComponentInParent<Canvas>();
            Camera camera = canvas.renderMode == RenderMode.ScreenSpaceOverlay ? null : canvas.worldCamera;
            return RectTransformUtility.WorldToScreenPoint(camera, rect.TransformPoint(rect.rect.center));
        }

        private static Transform FindNamed(GameObject root, string name)
        {
            foreach (Transform child in root.GetComponentsInChildren<Transform>(true))
                if (child.name == name) return child;
            Assert.Fail("The mobile controls prefab has no " + name + ".");
            return null;
        }

        private int CountNamedObjects(string name)
        {
            int count = 0;
            foreach (GameObject root in testScene.GetRootGameObjects())
                foreach (Transform child in root.GetComponentsInChildren<Transform>(true))
                    if (child.name == name) count++;
            return count;
        }

        private static float HorizontalDistance(Vector3 first, Vector3 second)
        {
            Vector3 offset = first - second;
            offset.y = 0f;
            return offset.magnitude;
        }

        private static void SetSerializedField(object target, string name, object value)
        {
            FieldInfo field = target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.IsNotNull(field, "Missing serialized dependency: " + name);
            field.SetValue(target, value);
        }
    }
}
