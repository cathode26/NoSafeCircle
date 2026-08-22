using System.IO;
using System.Reflection;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public class CommittedSceneCameraConformanceTests
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
        public void CommittedScene_MainCamera_IsFixedOrthographicIsometric()
        {
            var bytesBefore = File.ReadAllBytes(CanonicalScenePath);
            Scene openedScene = default;

            try
            {
                openedScene = EditorSceneManager.OpenScene(CanonicalScenePath, OpenSceneMode.Additive);
                var cameraObject = FindInSceneRoots(openedScene, "Main Camera");
                var player = FindInSceneRoots(openedScene, "Player");

                Assert.IsNotNull(cameraObject, "Expected Main Camera in the committed scene.");
                Assert.IsNotNull(player, "Expected Player in the committed scene.");

                var camera = cameraObject.GetComponent<Camera>();
                Assert.IsNotNull(camera, "Expected a Camera component on Main Camera.");
                Assert.IsTrue(camera.orthographic, "The committed camera must be orthographic.");
                Assert.Less(Quaternion.Angle(Quaternion.Euler(30f, -45f, 0f), camera.transform.rotation), 0.01f,
                    "The committed camera must use the approved fixed isometric rotation.");

                var follow = cameraObject.GetComponent<IsometricCameraFollow>();
                Assert.IsNotNull(follow, "Expected IsometricCameraFollow on the committed Main Camera.");
                var target = new SerializedObject(follow).FindProperty("target").objectReferenceValue as Transform;
                Assert.AreSame(player.transform, target,
                    "The follow target must be the Player from the same committed scene.");

                foreach (var behaviour in cameraObject.GetComponents<Behaviour>())
                {
                    var componentName = behaviour.GetType().Name;
                    Assert.IsFalse(componentName.Contains("Rotate") || componentName.Contains("Orbit"),
                        $"Main Camera must not have a free-rotation component; found {componentName}.");
                }
            }
            finally
            {
                if (openedScene.IsValid() && openedScene.isLoaded)
                {
                    EditorSceneManager.CloseScene(openedScene, true);
                }

                CollectionAssert.AreEqual(bytesBefore, File.ReadAllBytes(CanonicalScenePath),
                    "Committed-scene conformance inspection must not change canonical scene bytes.");
            }
        }

        [Test]
        public void CommittedScene_MainCamera_TranslatesWithPlayerWithoutRotating()
        {
            var bytesBefore = File.ReadAllBytes(CanonicalScenePath);
            Scene openedScene = default;

            try
            {
                openedScene = EditorSceneManager.OpenScene(CanonicalScenePath, OpenSceneMode.Additive);
                var cameraObject = FindInSceneRoots(openedScene, "Main Camera");
                var player = FindInSceneRoots(openedScene, "Player");

                Assert.IsNotNull(cameraObject, "Expected Main Camera in the committed scene.");
                Assert.IsNotNull(player, "Expected Player in the committed scene.");
                var follow = cameraObject.GetComponent<IsometricCameraFollow>();
                Assert.IsNotNull(follow, "Expected IsometricCameraFollow on the committed Main Camera.");

                var rotationBefore = cameraObject.transform.rotation;
                var offsetBefore = cameraObject.transform.position - player.transform.position;
                player.transform.position += new Vector3(5f, 0f, 3f);

                var lateUpdate = typeof(IsometricCameraFollow).GetMethod("LateUpdate",
                    BindingFlags.NonPublic | BindingFlags.Instance);
                Assert.IsNotNull(lateUpdate, "Expected the established private LateUpdate follow hook.");
                lateUpdate.Invoke(follow, null);

                Assert.AreEqual(offsetBefore, cameraObject.transform.position - player.transform.position,
                    "Camera must preserve its camera-to-player offset while following.");
                Assert.AreEqual(rotationBefore, cameraObject.transform.rotation,
                    "Camera rotation must remain fixed while following the Player.");
            }
            finally
            {
                if (openedScene.IsValid() && openedScene.isLoaded)
                {
                    EditorSceneManager.CloseScene(openedScene, true);
                }

                CollectionAssert.AreEqual(bytesBefore, File.ReadAllBytes(CanonicalScenePath),
                    "Committed-scene conformance inspection must not change canonical scene bytes.");
            }
        }

        private static GameObject FindInSceneRoots(Scene scene, string objectName)
        {
            foreach (var root in scene.GetRootGameObjects())
            {
                if (root.name == objectName) return root;

                var transforms = root.GetComponentsInChildren<Transform>(true);
                foreach (var candidate in transforms)
                {
                    if (candidate.name == objectName) return candidate.gameObject;
                }
            }

            return null;
        }
    }
}
