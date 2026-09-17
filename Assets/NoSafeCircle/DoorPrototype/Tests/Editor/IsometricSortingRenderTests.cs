using System.IO;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    // Regression guard for the 2026-09-17 camera-sort-axis fix: Vincent reported the D1 door
    // sprite drawing over the wizard's upper body. IsometricCameraFollow.OnEnable reapplies the
    // shared transparencySortAxis every time this committed scene loads (it is [ExecuteAlways]),
    // so opening the scene here exercises the exact path that reintroduced the bug at runtime
    // even though DoorPrototypeGlobalSceneBuilder's authored axis was correct. This test FAILS
    // against a negative Z coefficient and PASSES against the corrected positive one.
    public class IsometricSortingRenderTests
    {
        private const string CanonicalScenePath = "Assets/Scenes/DoorPrototype.unity";
        private const int RenderWidth = 800;
        private const int RenderHeight = 600;
        private const byte OpaqueAlphaThreshold = 250;
        private const byte ColorMatchTolerance = 2;

        // Not read from DoorPrototypeGlobalSceneBuilder's private IsometricCameraOffset - this is
        // just a convenient, door-centered vantage point for capturing the overlap region below,
        // not a claim about the production camera's exact framing.
        private static readonly Vector3 CameraOffsetFromDoor = new Vector3(10f, 10f, -10f);

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
        public void ClosedD1DoorNeverDrawsOverWizardStandingSouthOfIt()
        {
            byte[] bytesBefore = File.ReadAllBytes(CanonicalScenePath);
            Scene openedScene = default;
            RenderTexture target = null;
            Texture2D doorOnly = null;
            Texture2D wizardOnly = null;
            Texture2D both = null;
            RenderTexture previousActive = RenderTexture.active;
            Camera camera = null;
            RenderTexture previousCameraTarget = null;
            SpriteRenderer doorRenderer = null;
            SpriteRenderer wizardRenderer = null;
            bool doorRendererEnabledBefore = true;
            bool wizardRendererEnabledBefore = true;
            CameraClearFlags previousClearFlags = CameraClearFlags.SolidColor;
            Color previousBackgroundColor = Color.black;

            try
            {
                openedScene = EditorSceneManager.OpenScene(CanonicalScenePath, OpenSceneMode.Additive);
                GameObject doorRoot = FindInSceneRoots(openedScene, "DoorRoot");
                GameObject player = FindInSceneRoots(openedScene, "Player");
                GameObject cameraObject = FindInSceneRoots(openedScene, "Main Camera");

                Assert.IsNotNull(doorRoot, "Expected DoorRoot (D1) in the committed scene.");
                Assert.IsNotNull(player, "Expected Player in the committed scene.");
                Assert.IsNotNull(cameraObject, "Expected Main Camera in the committed scene.");

                var doorInteractable = doorRoot.GetComponent<DoorInteractable>();
                Assert.IsNotNull(doorInteractable, "Expected DoorInteractable on DoorRoot.");
                Assert.IsFalse(doorInteractable.IsOpen,
                    "D1 must start closed for this regression check to be meaningful.");

                doorRenderer = doorRoot.transform.Find("DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>();
                wizardRenderer = player.transform.Find("Visual")?.GetComponent<SpriteRenderer>();
                camera = cameraObject.GetComponent<Camera>();

                Assert.IsNotNull(doorRenderer, "Expected DoorRoot/DoorVisual/DoorSprite in the committed scene.");
                Assert.IsNotNull(wizardRenderer, "Expected Player/Visual in the committed scene.");
                Assert.IsNotNull(camera, "Expected a Camera component on Main Camera.");

                doorRendererEnabledBefore = doorRenderer.enabled;
                wizardRendererEnabledBefore = wizardRenderer.enabled;
                previousCameraTarget = camera.targetTexture;

                // Ground-contact convention: DoorSprite's local position cancels DoorVisual's
                // elevation back down to DoorRoot's own ground pivot (see
                // DoorPrototypeSceneBuilder.BuildDoor), so DoorRoot's own position is the door's
                // sorting-relevant ground position.
                Vector3 doorGroundPosition = doorRoot.transform.position;

                // Stand the wizard just south (smaller world Z, camera side) of the closed D1
                // door - close enough that the wizard's (1x2) and the door's (2x2.5) world-sprite
                // footprints overlap on screen, reproducing "a door in front of a wizard standing
                // south of it" from the fix comment.
                player.transform.position = new Vector3(
                    doorGroundPosition.x,
                    player.transform.position.y,
                    doorGroundPosition.z - 0.5f);

                cameraObject.transform.position = doorGroundPosition + CameraOffsetFromDoor;

                target = new RenderTexture(RenderWidth, RenderHeight, 24) { antiAliasing = 1 };
                target.Create();
                camera.targetTexture = target;

                // Clear to transparent black so alpha marks sprite coverage. With the scene
                // camera's own opaque clear, every pixel reads as opaque in both single renders,
                // the contested set becomes the whole frame, and the door legitimately showing
                // beside the wizard counts as a regression.
                previousClearFlags = camera.clearFlags;
                previousBackgroundColor = camera.backgroundColor;
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0f, 0f, 0f, 0f);

                wizardRenderer.enabled = false;
                doorRenderer.enabled = true;
                camera.Render();
                doorOnly = CapturePixels(target);

                doorRenderer.enabled = false;
                wizardRenderer.enabled = true;
                camera.Render();
                wizardOnly = CapturePixels(target);

                doorRenderer.enabled = true;
                wizardRenderer.enabled = true;
                camera.Render();
                both = CapturePixels(target);

                Color32[] doorPixels = doorOnly.GetPixels32();
                Color32[] wizardPixels = wizardOnly.GetPixels32();
                Color32[] combinedPixels = both.GetPixels32();

                int contestedPixelCount = 0;
                int doorWonCount = 0;
                for (int i = 0; i < combinedPixels.Length; i++)
                {
                    if (doorPixels[i].a < OpaqueAlphaThreshold || wizardPixels[i].a < OpaqueAlphaThreshold)
                    {
                        continue;
                    }

                    contestedPixelCount++;
                    if (!ColorsApproximatelyEqual(combinedPixels[i], wizardPixels[i]))
                    {
                        doorWonCount++;
                    }
                }

                Assert.Greater(contestedPixelCount, 0,
                    "The wizard and the closed D1 door sprite never overlapped on screen; the " +
                    "test positions did not produce a contested region to check.");

                // The regression guard: wherever both the door and the wizard are opaque, the
                // wizard (standing in front, at a smaller world Z) must win the combined render.
                Assert.AreEqual(0, doorWonCount,
                    $"{doorWonCount} of {contestedPixelCount} contested pixels rendered as the " +
                    "door instead of the wizard standing in front of it (transparencySortAxis regression).");
            }
            finally
            {
                if (doorRenderer != null) doorRenderer.enabled = doorRendererEnabledBefore;
                if (wizardRenderer != null) wizardRenderer.enabled = wizardRendererEnabledBefore;
                if (camera != null)
                {
                    camera.targetTexture = previousCameraTarget;
                    camera.clearFlags = previousClearFlags;
                    camera.backgroundColor = previousBackgroundColor;
                }

                RenderTexture.active = previousActive;

                if (doorOnly != null) Object.DestroyImmediate(doorOnly);
                if (wizardOnly != null) Object.DestroyImmediate(wizardOnly);
                if (both != null) Object.DestroyImmediate(both);
                if (target != null)
                {
                    target.Release();
                    Object.DestroyImmediate(target);
                }

                if (openedScene.IsValid() && openedScene.isLoaded)
                {
                    EditorSceneManager.CloseScene(openedScene, true);
                }

                CollectionAssert.AreEqual(bytesBefore, File.ReadAllBytes(CanonicalScenePath),
                    "This regression check must not change canonical scene bytes.");
            }
        }

        private static Texture2D CapturePixels(RenderTexture source)
        {
            RenderTexture.active = source;
            var texture = new Texture2D(source.width, source.height, TextureFormat.RGBA32, false);
            texture.ReadPixels(new Rect(0f, 0f, source.width, source.height), 0, 0);
            texture.Apply(false, false);
            return texture;
        }

        private static bool ColorsApproximatelyEqual(Color32 a, Color32 b)
        {
            return Mathf.Abs(a.r - b.r) <= ColorMatchTolerance &&
                   Mathf.Abs(a.g - b.g) <= ColorMatchTolerance &&
                   Mathf.Abs(a.b - b.b) <= ColorMatchTolerance &&
                   Mathf.Abs(a.a - b.a) <= ColorMatchTolerance;
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
