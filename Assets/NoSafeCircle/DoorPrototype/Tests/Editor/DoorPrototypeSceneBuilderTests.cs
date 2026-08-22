using System.IO;
using System.Reflection;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public class DoorPrototypeSceneBuilderTests
    {
        private const string CanonicalScenePath =
            "Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity";

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
            StringAssert.Contains("WASD", hudText.text);
            StringAssert.Contains("Move", hudText.text);
            StringAssert.Contains("Hold E", hudText.text);
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
}
