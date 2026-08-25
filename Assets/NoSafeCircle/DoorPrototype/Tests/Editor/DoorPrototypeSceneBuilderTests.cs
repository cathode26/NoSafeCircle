using System.IO;
using System.Reflection;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public class DoorPrototypeSceneBuilderTests
    {
        private const string CanonicalScenePath = "Assets/Scenes/DoorPrototype.unity";

        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [Test]
        public void Build_ProgressFillImage_HasSpriteAssignedSoFillAmountIsVisible()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var fillImage = GameObject.Find("Canvas/ProgressFill/Fill")?.GetComponent<Image>();

            Assert.IsNotNull(fillImage, "Expected a 'Fill' Image under Canvas/ProgressFill after building the scene.");
            Assert.IsNotNull(fillImage.sprite,
                "Progress fill Image has no sprite. A Filled Image with no sprite renders as a static full rect and ignores fillAmount.");
            Assert.AreEqual(Image.Type.Filled, fillImage.type);
            Assert.AreEqual(Image.FillMethod.Horizontal, fillImage.fillMethod);
        }

        [Test]
        public void Build_RunTwice_DoesNotDuplicateProgressFillHierarchy()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var canvas = GameObject.Find("Canvas");
            var progressFillCount = 0;
            foreach (Transform child in canvas.transform)
            {
                if (child.name == "ProgressFill") progressFillCount++;
            }

            Assert.AreEqual(1, progressFillCount,
                "Re-running the scene builder must not duplicate the ProgressFill UI element.");
        }

        // AC-003: continuous player-facing health indicator must actually be wired into the
        // canonical scene builder output, mirroring the door's ProgressFill visibility fix.
        [Test]
        public void Build_HealthFillImage_HasSpriteAssignedSoFillAmountIsVisible()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var fillImage = GameObject.Find("Canvas/HealthFill/Fill")?.GetComponent<Image>();

            Assert.IsNotNull(fillImage, "Expected a 'Fill' Image under Canvas/HealthFill after building the scene.");
            Assert.IsNotNull(fillImage.sprite,
                "Health fill Image has no sprite. A Filled Image with no sprite renders as a static full rect and ignores fillAmount.");
            Assert.AreEqual(Image.Type.Filled, fillImage.type);
            Assert.AreEqual(Image.FillMethod.Horizontal, fillImage.fillMethod);
        }

        // AC-003: the health indicator must be bound to the same PlayerHealth instance carried
        // by the generated Player, not a stray/unwired component, so it reflects real state.
        [Test]
        public void Build_PlayerHealthUI_WiredToPlayerHealthAndFillImage()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var healthUi = GameObject.Find("Canvas")?.GetComponent<PlayerHealthUI>();
            Assert.IsNotNull(healthUi, "Expected a PlayerHealthUI component on the generated Canvas.");

            var playerHealth = GameObject.Find("Player")?.GetComponent<PlayerHealth>();
            Assert.IsNotNull(playerHealth, "Expected a PlayerHealth component on the generated Player.");

            var fillImage = GameObject.Find("Canvas/HealthFill/Fill")?.GetComponent<Image>();
            Assert.IsNotNull(fillImage, "Expected a 'Fill' Image under Canvas/HealthFill after building the scene.");

            var serializedUi = new SerializedObject(healthUi);
            Assert.AreEqual(playerHealth, serializedUi.FindProperty("health").objectReferenceValue,
                "PlayerHealthUI must be wired to the same PlayerHealth instance carried by the generated Player.");
            Assert.AreEqual(fillImage, serializedUi.FindProperty("fillImage").objectReferenceValue,
                "PlayerHealthUI must be wired to the generated HealthFill/Fill Image.");
        }

        [Test]
        public void Build_RunTwice_DoesNotDuplicateHealthFillHierarchy()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var canvas = GameObject.Find("Canvas");
            var healthFillCount = 0;
            foreach (Transform child in canvas.transform)
            {
                if (child.name == "HealthFill") healthFillCount++;
            }

            Assert.AreEqual(1, healthFillCount,
                "Re-running the scene builder must not duplicate the HealthFill UI element.");

            var healthUiComponents = canvas.GetComponents<PlayerHealthUI>();
            Assert.AreEqual(1, healthUiComponents.Length,
                "Re-running the scene builder must not duplicate the PlayerHealthUI binding.");
        }
        // AC-003: the health indicator must stay visible/readable at all times. Give it a
        // dedicated center-screen vertical lane above the interaction prompt rather than
        // merely requiring a numerically different anchor from the other bars.
        [Test]
        public void Build_HealthFill_UsesDedicatedVerticalLaneAboveInteractionPrompt()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var healthRect = GameObject.Find("Canvas/HealthFill")?.GetComponent<RectTransform>();
            var promptRect = GameObject.Find("Canvas/InteractPrompt")?.GetComponent<RectTransform>();
            var progressRect = GameObject.Find("Canvas/ProgressFill")?.GetComponent<RectTransform>();
            var manaRect = GameObject.Find("Canvas/ManaFill")?.GetComponent<RectTransform>();

            Assert.IsNotNull(healthRect, "Expected a 'HealthFill' RectTransform directly under Canvas.");
            Assert.IsNotNull(promptRect, "Expected an 'InteractPrompt' RectTransform directly under Canvas.");
            Assert.IsNotNull(progressRect, "Expected a 'ProgressFill' RectTransform directly under Canvas.");
            Assert.IsNotNull(manaRect, "Expected a 'ManaFill' RectTransform directly under Canvas.");

            Assert.GreaterOrEqual(
                healthRect.anchorMin.y - promptRect.anchorMax.y,
                0.049f,
                "Health indicator must have a dedicated normalized vertical lane above the interaction prompt.");

            Assert.Greater(healthRect.anchorMin.y, progressRect.anchorMin.y,
                "Health indicator must remain above the door progress bar.");
            Assert.Greater(healthRect.anchorMin.y, manaRect.anchorMin.y,
                "Health indicator must remain above the mana indicator.");
        }
[Test]
        public void Build_ControlsHud_ExistsSeparateFromPromptAndProgressIndicator()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var hud = GameObject.Find("Canvas/ControlsHud");
            Assert.IsNotNull(hud, "Expected a 'ControlsHud' object directly under Canvas.");

            var prompt = GameObject.Find("Canvas/InteractPrompt");
            var progress = GameObject.Find("Canvas/ProgressFill");
            Assert.AreNotEqual(hud, prompt, "Controls HUD must be a separate object from the interaction prompt.");
            Assert.AreNotEqual(hud, progress, "Controls HUD must be a separate object from the progress indicator.");
        }

        [Test]
        public void Build_ControlsHud_TextMatchesActualImplementedControls()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var hudText = GameObject.Find("Canvas/ControlsHud/Text")?.GetComponent<Text>();
            Assert.IsNotNull(hudText, "Expected a 'Text' element under Canvas/ControlsHud.");
            StringAssert.Contains("Click/Hold Left Mouse", hudText.text);
            StringAssert.Contains("Move", hudText.text);
            // AC-001/AC-002: door interaction is click-to-approach with an automatic timer, not
            // a sustained key hold; the HUD text must reflect that current interaction model.
            StringAssert.Contains("Click Sealed Door", hudText.text);
            StringAssert.DoesNotContain("Hold E", hudText.text,
                "HUD text must not describe the superseded sustained-hold interaction model.");
            StringAssert.Contains("cancels the opening attempt", hudText.text);

            var debugControl = GameObject.Find("Player")?.GetComponent<DebugDamageControl>();
            Assert.IsNotNull(debugControl, "Expected a DebugDamageControl on the generated Player.");
            var damageKey = (Key)new SerializedObject(debugControl).FindProperty("damageKey").enumValueIndex;
            StringAssert.Contains(damageKey.ToString(), hudText.text,
                "Displayed debug key must match the actual implemented damage-test key binding.");
            StringAssert.Contains("Debug", hudText.text,
                "The damage-test key must be clearly labeled as debug/test, not a normal gameplay ability.");
        }

        [Test]
        public void Build_RunTwice_DoesNotDuplicateControlsHud()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var canvas = GameObject.Find("Canvas");
            var hudCount = 0;
            foreach (Transform child in canvas.transform)
            {
                if (child.name == "ControlsHud") hudCount++;
            }

            Assert.AreEqual(1, hudCount, "Re-running the scene builder must not duplicate the ControlsHud panel.");
        }

        [Test]
        public void Build_MainCamera_IsFixedOrthographicIsometric()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();
            Assert.IsNotNull(camera, "Expected a 'Main Camera' with a Camera component.");

            Assert.IsTrue(camera.orthographic,
                "Camera must be orthographic for the GDD's fixed 2.5D isometric presentation, not perspective.");
            Assert.Greater(camera.orthographicSize, 0f);

            var expectedRotation = Quaternion.Euler(30f, -45f, 0f);
            Assert.Less(Quaternion.Angle(expectedRotation, camera.transform.rotation), 0.01f,
                "Camera rotation must match the fixed isometric angle and not the old perspective test angle.");

            var noRotationComponents = camera.GetComponentsInParent<Behaviour>();
            foreach (var behaviour in noRotationComponents)
            {
                Assert.IsFalse(behaviour.GetType().Name.Contains("Rotate") || behaviour.GetType().Name.Contains("Orbit"),
                    "Main Camera must not have any free-rotation/orbit component attached; the isometric view is fixed.");
            }
        }

        [Test]
        public void Build_RunTwice_MainCameraStaysSingleAndFixed()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var cameras = Object.FindObjectsByType<Camera>(FindObjectsSortMode.None);
            Assert.AreEqual(1, cameras.Length, "Re-running the scene builder must not duplicate the Main Camera.");
            Assert.IsTrue(cameras[0].orthographic);
        }

        [Test]
        public void Build_MainCamera_FramesPlayerAndStartingDoorInView()
        {
            // Camera.forward pointing exactly at the player is not itself a meaningful framing
            // check - a camera can satisfy that and still be positioned on the wrong side, or
            // frame the gameplay space badly. What actually matters is that the player and the
            // starting door both land comfortably inside the camera's viewport.
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();
            var player = GameObject.Find("Player");
            var door = GameObject.Find("DoorRoot");
            Assert.IsNotNull(camera);
            Assert.IsNotNull(player);
            Assert.IsNotNull(door);

            var playerViewport = camera.WorldToViewportPoint(player.transform.position);
            var doorViewport = camera.WorldToViewportPoint(door.transform.position);

            Assert.IsTrue(playerViewport.x > 0.1f && playerViewport.x < 0.9f
                          && playerViewport.y > 0.1f && playerViewport.y < 0.9f && playerViewport.z > 0f,
                $"Player must be comfortably inside the camera view at scene start, was viewport {playerViewport}.");
            Assert.IsTrue(doorViewport.x > 0.1f && doorViewport.x < 0.9f
                          && doorViewport.y > 0.1f && doorViewport.y < 0.9f && doorViewport.z > 0f,
                $"Starting door must be comfortably inside the camera view at scene start, was viewport {doorViewport}.");
        }

        [Test]
        public void Build_MainCamera_HasFollowComponentTargetingPlayer()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var camera = GameObject.Find("Main Camera");
            var follow = camera?.GetComponent<IsometricCameraFollow>();
            Assert.IsNotNull(follow,
                "Expected an IsometricCameraFollow component on the Main Camera so it tracks the player instead of staying static.");

            var target = new SerializedObject(follow).FindProperty("target").objectReferenceValue as Transform;
            Assert.IsNotNull(target, "IsometricCameraFollow.target must be wired up by the scene builder.");
            Assert.AreEqual("Player", target.name);
        }

        [Test]
        public void Build_MainCamera_TranslatesWithPlayerButRotationStaysFixed()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var cameraObject = GameObject.Find("Main Camera");
            var player = GameObject.Find("Player");
            var follow = cameraObject.GetComponent<IsometricCameraFollow>();

            var rotationBefore = cameraObject.transform.rotation;
            var offsetBefore = cameraObject.transform.position - player.transform.position;

            player.transform.position += new Vector3(5f, 0f, 3f);

            var lateUpdate = typeof(IsometricCameraFollow).GetMethod("LateUpdate",
                BindingFlags.NonPublic | BindingFlags.Instance);
            lateUpdate.Invoke(follow, null);

            Assert.AreEqual(offsetBefore, cameraObject.transform.position - player.transform.position,
                "Camera must keep the same relative offset while translating to follow the player, so the " +
                "gameplay area stays framed as the player moves.");
            Assert.AreEqual(rotationBefore, cameraObject.transform.rotation,
                "Camera rotation must never change while following the player - the isometric orientation is " +
                "fixed and there is no free player-controlled rotation.");
        }

        [Test]
        public void BuildCamera_NullFollowTarget_LogsWarningInsteadOfSilentlyMisframing()
        {
            // BuildCamera's initial placement depends on Build() calling BuildPlayer() first so a
            // real follow target exists. This locks in the fallback: if that ordering is ever
            // broken, BuildCamera must warn rather than silently place the camera at the world
            // origin with no indication the framing requirement was violated.
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var buildCamera = typeof(DoorPrototypeSceneBuilder).GetMethod("BuildCamera",
                BindingFlags.NonPublic | BindingFlags.Static);
            Assert.IsNotNull(buildCamera, "Expected a private static BuildCamera(Transform) method.");

            // Isolate from any "Main Camera" left over by other tests in this run, since this
            // test invokes BuildCamera directly rather than through Build()'s scene clearing.
            var existingCamera = GameObject.Find("Main Camera");
            if (existingCamera != null) Object.DestroyImmediate(existingCamera);

            LogAssert.Expect(LogType.Warning, new System.Text.RegularExpressions.Regex("null follow target"));

            buildCamera.Invoke(null, new object[] { null });

            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();
            Assert.IsNotNull(camera, "BuildCamera must still create a Main Camera even without a follow target.");
            Assert.IsTrue(camera.orthographic);
        }

        [Test]
        public void BuildInMemory_CanonicalSceneBytesRemainUnchanged()
        {
            var bytesBefore = File.ReadAllBytes(CanonicalScenePath);

            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            CollectionAssert.AreEqual(bytesBefore, File.ReadAllBytes(CanonicalScenePath),
                "The in-memory builder must never rewrite the canonical DoorPrototype scene.");
        }
    }

    // Human-review regression (item 2): the previous door-selection tests aimed at
    // WorldToScreenPoint(door.transform.position) - the ground anchor, not the visible door -
    // which does not represent an actual player click on the sealed door under the production
    // fixed isometric camera. This builds the real scene, clicks through the built DoorVisual's
    // world center under the real built Main Camera, drives that click through a live
    // PlayerMovement instance so the ground point is produced by the same shared projection
    // consumers rely on (AC-001), and proves the door is selected through
    // PlayerInteractionController.TryBeginDoorApproach.
    public class DoorPrototypeSceneBuilderClickSelectionTests : InputTestFixture
    {
        private Mouse mouseDevice;
        private RenderTexture testRenderTexture;

        public override void Setup()
        {
            base.Setup();
            mouseDevice = InputSystem.AddDevice<Mouse>();
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        public override void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                Object.Destroy(testRenderTexture);
                testRenderTexture = null;
            }

            mouseDevice = null;
            base.TearDown();
        }

        [Test]
        public void Build_ClickingVisibleDoorCenterUnderProductionCamera_SelectsDoorThroughSharedPointerTarget()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var playerObject = GameObject.Find("Player");
            var movement = playerObject != null ? playerObject.GetComponent<PlayerMovement>() : null;
            var interactionController =
                playerObject != null ? playerObject.GetComponent<PlayerInteractionController>() : null;
            var door = GameObject.Find("DoorRoot")?.GetComponent<DoorInteractable>();
            var doorVisual = GameObject.Find("DoorRoot/DoorVisual");
            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();

            Assert.IsNotNull(movement, "Expected a PlayerMovement on the generated Player.");
            Assert.IsNotNull(interactionController,
                "Expected a PlayerInteractionController on the generated Player.");
            Assert.IsNotNull(door, "Expected a DoorInteractable on the generated DoorRoot.");
            Assert.IsNotNull(doorVisual, "Expected a DoorVisual child under DoorRoot.");
            Assert.IsNotNull(camera, "Expected a Camera on the generated Main Camera.");

            // Batch mode has no interactive Game View; give the built camera a fixed pixel
            // surface so WorldToScreenPoint/ScreenPointToRay are deterministic here too.
            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
            camera.targetTexture = testRenderTexture;

            // EditMode tests do not invoke MonoBehaviour Awake/OnEnable automatically; invoke
            // them explicitly so the built components are wired the same way they would be at
            // runtime before driving a real click through them. Unity's engine does not track
            // these as "live" components in Edit Mode (they were never enabled through the
            // normal engine path), so OnEnable's InputAction.Enable() calls must be matched with
            // an explicit OnDisable in this test rather than relying on scene teardown to release
            // them from the real, session-shared project InputActionAsset.
            InvokePrivate(movement, "Awake");
            InvokePrivate(movement, "OnEnable");
            InvokePrivate(interactionController, "Awake");
            InvokePrivate(interactionController, "OnEnable");
            InvokePrivate(door, "OnEnable");

            try
            {
                var screenPoint = camera.WorldToScreenPoint(doorVisual.transform.position);
                SetMouse(screenPoint, true);

                movement.Tick(0.02f);

                Assert.IsTrue(movement.HasPointerWorldTarget,
                    "Expected PlayerMovement to have produced a shared world-space pointer target for this " +
                    "click.");
                Assert.IsTrue(interactionController.HasLockedDoorInteraction,
                    "Clicking through the visible door's visual center under the production camera must " +
                    "select the sealed door via the shared PlayerMovement pointer target, not merely near " +
                    "its ground anchor.");
                Assert.AreSame(door, interactionController.PendingDoor);
            }
            finally
            {
                InvokePrivate(door, "OnDisable");
                InvokePrivate(movement, "OnDisable");
            }
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

        private static void InvokePrivate(object target, string methodName)
        {
            var method = target.GetType().GetMethod(methodName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(method, $"Expected a private method named '{methodName}' on {target.GetType().Name}.");
            method.Invoke(target, null);
        }
    }
}
