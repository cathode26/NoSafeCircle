using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Regression guard for the 2026-09-17 camera-sort-axis fix: Vincent reported the D1 door
    // sprite drawing over the wizard's upper body. IsometricCameraFollow.OnEnable reapplies the
    // shared transparencySortAxis whenever its GameObject is enabled (it is [ExecuteAlways]), and
    // this test FAILS against a negative Z coefficient and PASSES against the corrected positive
    // one - exactly as the Edit Mode original did.
    //
    // PORTED FROM Tests/Editor/IsometricSortingRenderTests.cs, which opened the committed
    // Assets/Scenes/DoorPrototype.unity - one of the scenes being retired now that GameBootstrap
    // builds the world procedurally at Play. A PATH SWAP ALONE WOULD NOT HAVE WORKED: the
    // committed RuntimeWorld.unity carries no room content at all (GameBootstrap builds
    // everything from prefabs at runtime), so an Edit Mode OpenScene of it photographs an empty
    // room. This loads RuntimeWorld and waits for GameBootstrap to actually build the world
    // before finding anything, per FiveRoomDoorSequencePlayModeTests.WaitForWorldBuilt.
    //
    // NOTHING ELSE ASSERTS THIS REGRESSION. A sweep of every PlayMode test for
    // transparencySortAxis, doorWonCount, CapturePixels and ContestedPixel found nothing besides
    // the Edit Mode original this replaces, so the per-pixel comparison below is preserved with
    // the same threshold and the same contested-region logic, not weakened into a property check.
    public sealed class IsometricSortingRenderPlayModeTests
    {
        private const int RenderWidth = 800;
        private const int RenderHeight = 600;
        private const byte OpaqueAlphaThreshold = 250;
        private const byte ColorMatchTolerance = 2;

        // Same convenient, door-centered vantage point as the Edit Mode original - not a claim
        // about the production camera's exact framing, and it happens to share the production
        // rig's own fixed rotation (Euler 30, -45, 0; see IsometricCameraFollow), so this offset
        // still produces an isometric view rather than an arbitrary one.
        private static readonly Vector3 CameraOffsetFromDoor = new Vector3(10f, 10f, -10f);

        // Copied from FiveRoomDoorSequencePlayModeTests.WaitForWorldBuilt (see e82bd6f23 /
        // TitleScreenPlayModeTests for why two frames plus HasBuilt, not a frame count): the new
        // world does not exist until GameBootstrap runs, so the wait is not optional.
        private static IEnumerator WaitForWorldBuilt()
        {
            yield return null;
            GameObject managers = GameObject.Find("GameManagers");
            Assert.IsNotNull(managers,
                "RuntimeWorld.unity carries no GameManagers object, so nothing builds the world.");
            var bootstrap = managers.GetComponent<GameBootstrap>();
            Assert.IsNotNull(bootstrap, "GameManagers carries no GameBootstrap.");

            yield return null;
            yield return null;

            Assert.IsTrue(bootstrap.HasBuilt,
                "GameBootstrap had not built after three frames, so every assertion below would "
                + "fail on an empty world rather than on the thing under test. SpawnedCount = "
                + bootstrap.SpawnedCount + ".");
        }

        // NOT root-scoped: RuntimeWorld nests every spawned object under its spawner
        // (GameManagers -> <Family>Spawner -> the object), never at the scene root, unlike the
        // committed DoorPrototype.unity the Edit Mode original read. Recurses the whole loaded
        // scene and keeps the original "expect exactly one" guarantee.
        private static GameObject FindInScene(Scene scene, string name)
        {
            var matches = new List<GameObject>();
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                CollectByName(root.transform, name, matches);
            }
            Assert.AreEqual(1, matches.Count,
                $"Expected exactly one '{name}' object in loaded scene {scene.path}, found {matches.Count}.");
            return matches[0];
        }

        private static void CollectByName(Transform node, string name, List<GameObject> matches)
        {
            if (node.name == name) matches.Add(node.gameObject);
            for (int i = 0; i < node.childCount; i++)
            {
                CollectByName(node.GetChild(i), name, matches);
            }
        }

        // REQUIRED BY PlayModeSceneCleanupConventionTests: a fixture that loads a scene
        // LoadSceneMode.Single must restore one afterward, or it leaves RuntimeWorld loaded for
        // every fixture that runs after it in the same PlayMode session. Copied from
        // FiveRoomDoorSequencePlayModeTests.UnloadRuntimeWorldSceneWithoutSaving, which the
        // convention test's own failure message points at by name.
        [UnityTearDown]
        public IEnumerator TearDown()
        {
            yield return UnloadRuntimeWorldSceneWithoutSaving();
        }

        private static IEnumerator UnloadRuntimeWorldSceneWithoutSaving()
        {
            var scene = SceneManager.GetSceneByName("RuntimeWorld");
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            var cleanupScene = SceneManager.CreateScene("IsometricSortingRenderTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }

        [UnityTest]
        public IEnumerator ClosedD1DoorNeverDrawsOverWizardStandingSouthOfIt()
        {
            yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);
            yield return WaitForWorldBuilt();

            var scene = SceneManager.GetSceneByName("RuntimeWorld");

            // D1 is spawned as "DoorRoot" - DoorSpawner.CanonicalDoors: "D1 is named 'DoorRoot'
            // because NSC-052 and NSC-075 pin the path DoorRoot/DoorVisual/DoorSprite ... the
            // names are not negotiable here."
            GameObject doorRoot = FindInScene(scene, "DoorRoot");
            GameObject player = FindInScene(scene, "Player");

            var doorInteractable = doorRoot.GetComponent<DoorInteractable>();
            Assert.IsNotNull(doorInteractable, "Expected a DoorInteractable on the spawned DoorRoot (D1).");
            Assert.IsFalse(doorInteractable.IsOpen,
                "D1 must start closed for this regression check to be meaningful.");

            SpriteRenderer doorRenderer = doorRoot.transform.Find("DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>();
            SpriteRenderer wizardRenderer = player.transform.Find("Visual")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(doorRenderer, "Expected DoorRoot/DoorVisual/DoorSprite in the spawned world.");
            Assert.IsNotNull(wizardRenderer, "Expected Player/Visual in the spawned world.");

            // Camera.main, never a name lookup: PlayerSpawner.RetirePlaceholderCameras disables
            // the scene's placeholder "Main Camera" rather than removing it, so TWO GameObjects
            // share that name once Play has run. Camera.main resolves only the enabled one - the
            // real IsometricCamera prefab instance PlayerSpawner just spawned, carrying the same
            // IsometricCameraFollow component (and the same OnEnable-applied
            // transparencySortAxis) the Edit Mode original exercised through the committed
            // scene's own Main Camera at OpenScene. This is the camera rig that makes the pixel
            // comparison below mean anything: it is the production path, not a stand-in built by
            // this test.
            Camera camera = Camera.main;
            Assert.IsNotNull(camera, "Camera.main did not resolve the spawned isometric camera.");

            var movement = player.GetComponent<PlayerMovement>();
            var controller = player.GetComponent<CharacterController>();

            bool doorRendererEnabledBefore = doorRenderer.enabled;
            bool wizardRendererEnabledBefore = wizardRenderer.enabled;
            bool movementEnabledBefore = movement != null && movement.enabled;
            RenderTexture previousCameraTarget = camera.targetTexture;
            CameraClearFlags previousClearFlags = camera.clearFlags;
            Color previousBackgroundColor = camera.backgroundColor;
            Vector3 previousCameraPosition = camera.transform.position;
            RenderTexture previousActive = RenderTexture.active;

            RenderTexture target = null;
            Texture2D doorOnly = null;
            Texture2D wizardOnly = null;
            Texture2D both = null;
            var silencedRenderers = new List<Renderer>();

            try
            {
                // PlayerMovement.Update ticks every frame the player loop advances; disabling it
                // is the same guard the VAL-006 fixture uses so nothing but this test's own
                // explicit positioning below can move the wizard between here and the renders.
                if (movement != null) movement.enabled = false;

                // Ground-contact convention, unchanged from the Edit Mode original: DoorSprite's
                // local position cancels DoorVisual's elevation back down to DoorRoot's own
                // ground pivot (Resources/Doors/Door.prefab: DoorVisual y=1.25, DoorSprite
                // y=-1.25 - confirmed in the committed prefab), so DoorRoot's own position is
                // the door's sorting-relevant ground position.
                Vector3 doorGroundPosition = doorRoot.transform.position;

                // Stand the wizard just south (smaller world Z, camera side) of the closed D1
                // door - close enough that the wizard's and the door's world-sprite footprints
                // overlap on screen, exactly as the Edit Mode original did. Disable the
                // CharacterController for the teleport (TeleportPlayer's pattern in
                // FiveRoomDoorSequencePlayModeTests) so it cannot fight the position write.
                if (controller != null) controller.enabled = false;
                player.transform.position = new Vector3(
                    doorGroundPosition.x,
                    player.transform.position.y,
                    doorGroundPosition.z - 0.5f);
                if (controller != null) controller.enabled = true;

                // No yield happens between this and the three Render() calls below, so nothing
                // else in the player loop (LateUpdate included) runs and reasserts a different
                // camera position in between.
                camera.transform.position = doorGroundPosition + CameraOffsetFromDoor;

                target = new RenderTexture(RenderWidth, RenderHeight, 24) { antiAliasing = 1 };
                target.Create();
                camera.targetTexture = target;

                // Clear to transparent black so alpha marks sprite coverage. With the camera's
                // own opaque clear, every pixel reads as opaque in both single renders, the
                // contested set becomes the whole frame, and the door legitimately showing
                // beside the wizard would count as a regression.
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0f, 0f, 0f, 0f);

                // Silence every other renderer in the spawned world. Otherwise the floor and
                // walls are opaque in all three captures, the contested set becomes most of the
                // frame, and the door drawing over the FLOOR beside the wizard would count as a
                // regression.
                foreach (GameObject root in scene.GetRootGameObjects())
                {
                    foreach (Renderer sceneRenderer in root.GetComponentsInChildren<Renderer>(true))
                    {
                        if (sceneRenderer == doorRenderer || sceneRenderer == wizardRenderer || !sceneRenderer.enabled)
                        {
                            continue;
                        }

                        sceneRenderer.enabled = false;
                        silencedRenderers.Add(sceneRenderer);
                    }
                }

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
                doorRenderer.enabled = doorRendererEnabledBefore;
                wizardRenderer.enabled = wizardRendererEnabledBefore;

                foreach (Renderer silenced in silencedRenderers)
                {
                    if (silenced != null) silenced.enabled = true;
                }

                camera.targetTexture = previousCameraTarget;
                camera.clearFlags = previousClearFlags;
                camera.backgroundColor = previousBackgroundColor;
                camera.transform.position = previousCameraPosition;

                RenderTexture.active = previousActive;

                if (doorOnly != null) Object.DestroyImmediate(doorOnly);
                if (wizardOnly != null) Object.DestroyImmediate(wizardOnly);
                if (both != null) Object.DestroyImmediate(both);
                if (target != null)
                {
                    target.Release();
                    Object.DestroyImmediate(target);
                }

                if (movement != null) movement.enabled = movementEnabledBefore;
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
    }
}
