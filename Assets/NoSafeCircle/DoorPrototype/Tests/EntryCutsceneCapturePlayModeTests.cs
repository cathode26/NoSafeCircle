using System;
using System.Collections;
using System.IO;
using System.Text;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    /// <summary>
    /// Explicit, output-gated review capture of the real RuntimeWorld entry flow.
    /// Camera.Render is used because WaitForEndOfFrame does not resume in Unity batch mode.
    /// </summary>
    public sealed class EntryCutsceneCapturePlayModeTests
    {
        private const int Width = 1920;
        private const int Height = 1080;
        private const int TemporaryUiLayer = 31;
        private const float MaximumEntrySeconds = 15f;
        private const float VisualWaitSeconds = 8f;

        [UnityTest]
        [Explicit("Set NSC_ENTRY_CAPTURE_OUTPUT to a new directory outside the project.")]
        public IEnumerator CaptureSelectionChaseAndReadyPlayer()
        {
            string output = Environment.GetEnvironmentVariable("NSC_ENTRY_CAPTURE_OUTPUT");
            Assert.IsFalse(string.IsNullOrWhiteSpace(output),
                "NSC_ENTRY_CAPTURE_OUTPUT must name a new directory outside the project.");
            output = Path.GetFullPath(output);
            Assert.IsFalse(Directory.Exists(output),
                "Refusing to mix new screenshots with a previous capture: " + output);
            Assert.IsFalse(output.StartsWith(Path.GetFullPath(Application.dataPath),
                    StringComparison.OrdinalIgnoreCase),
                "Capture output must be outside the Unity project.");
            Directory.CreateDirectory(output);

            SceneManager.LoadScene("RuntimeWorld", LoadSceneMode.Single);
            yield return null;
            yield return null;
            yield return null;

            GameBootstrap bootstrap = GameObject.Find("GameManagers")?.GetComponent<GameBootstrap>();
            Assert.IsNotNull(bootstrap);
            Assert.IsTrue(bootstrap.HasBuilt, "RuntimeWorld has not finished spawning its content.");

            Camera gameCamera = Camera.main;
            Canvas canvas = GameObject.Find("Canvas")?.GetComponent<Canvas>();
            TitleScreenController title = UnityEngine.Object.FindFirstObjectByType<TitleScreenController>();
            WizardSelectionController selection =
                UnityEngine.Object.FindFirstObjectByType<WizardSelectionController>();
            WizardGameEntryController entry =
                UnityEngine.Object.FindFirstObjectByType<WizardGameEntryController>();
            TitleScreenChaseBackdrop chase =
                UnityEngine.Object.FindFirstObjectByType<TitleScreenChaseBackdrop>();
            EntryChamberStartDoor startDoor =
                UnityEngine.Object.FindFirstObjectByType<EntryChamberStartDoor>();
            Assert.IsNotNull(gameCamera);
            Assert.IsNotNull(canvas);
            Assert.IsNotNull(title);
            Assert.IsNotNull(selection);
            Assert.IsNotNull(entry);
            Assert.IsNotNull(chase, "RuntimeWorld has no entry chase component.");
            Assert.IsNotNull(startDoor, "RuntimeWorld did not spawn the separate entry gate.");
            Assert.IsFalse(startDoor.IsOpen, "The gate should begin sealed on the title screen.");
            float gameplayCameraSize = gameCamera.orthographicSize;

            var manifest = new StringBuilder();
            manifest.AppendLine("Unity " + Application.unityVersion);
            manifest.AppendLine("Revision " + Environment.GetEnvironmentVariable("NSC_CAPTURE_REVISION"));
            manifest.AppendLine("Scene RuntimeWorld.unity; selected wizard option 0");
            manifest.AppendLine("Frames are 1920x1080 manual Camera.Render plus UI canvas composition.");

            Capture(output, "00-title", gameCamera, canvas, manifest, entry, chase, startDoor);
            title.StartGame();
            yield return null;
            Assert.IsTrue(selection.IsSelectionVisible);
            Capture(output, "01-selection", gameCamera, canvas, manifest, entry, chase,
                startDoor);

            selection.SelectOption(0);
            Assert.IsTrue(selection.IsConfirmationAvailable);
            selection.ConfirmSelection();
            yield return null;
            Assert.IsTrue(entry.IsEntryCutsceneRunning,
                "Wizard control began without the selected-wizard chase.");
            Assert.IsTrue(startDoor.IsOpen, "The gate did not open for the wizard's entry.");

            yield return WaitForActiveObject("TitleEntryFireball_0", VisualWaitSeconds);
            EntryChamberCutsceneOcclusion occlusion =
                entry.GetComponent<EntryChamberCutsceneOcclusion>();
            Assert.IsNotNull(occlusion);
            Assert.IsTrue(occlusion.IsActive,
                "The foreground wall art did not soften for the chase.");
            Assert.Greater(occlusion.SouthWallTargetCount, 0);
            Assert.Greater(occlusion.GateFlankTargetCount, 0);
            SpriteRenderer gateFlank = GameObject.Find("EntryChamberGateWall")
                ?.GetComponentInChildren<SpriteRenderer>();
            Assert.IsNotNull(gateFlank);
            Assert.Less(gateFlank.color.a, 0.5f,
                "The gate flank still hides the wizard during fireball shots.");
            Assert.Less(gameCamera.orthographicSize, gameplayCameraSize - 1f,
                "The entry chase camera did not frame the actors closely.");
            Capture(output, "02-first-fireball-miss", gameCamera, canvas, manifest,
                entry, chase, startDoor);
            yield return WaitForActiveObject("TitleEntryFireball_1", VisualWaitSeconds);
            Capture(output, "03-second-fireball-miss", gameCamera, canvas, manifest,
                entry, chase, startDoor);
            yield return WaitForActiveObject("TitleEntryFireball_2", VisualWaitSeconds);
            Capture(output, "04-third-fireball-hit-flight", gameCamera, canvas, manifest,
                entry, chase, startDoor);
            yield return WaitForActiveObject("TitleEntryFireballImpact", VisualWaitSeconds);
            Capture(output, "05-fireball-hit-impact", gameCamera, canvas, manifest,
                entry, chase, startDoor);

            float deadline = Time.realtimeSinceStartup + MaximumEntrySeconds;
            while (startDoor.IsOpen && Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }
            Assert.IsFalse(startDoor.IsOpen, "The start door never sealed behind the wizard.");
            Transform doorVisual = startDoor.transform.Find("DoorVisual");
            Assert.IsNotNull(doorVisual);
            Assert.IsTrue(doorVisual.gameObject.activeSelf,
                "The start door reports closed but its leaf is hidden.");
            Assert.IsFalse(entry.HasEnteredGameplay,
                "The door must visibly seal before control starts.");
            Capture(output, "06-start-door-sealed", gameCamera, canvas, manifest,
                entry, chase, startDoor);

            while (!entry.HasEnteredGameplay && Time.realtimeSinceStartup < deadline)
                yield return null;

            Assert.IsTrue(entry.HasEnteredGameplay,
                "Entry did not hand control to the player within " + MaximumEntrySeconds + " seconds.");
            Assert.IsFalse(startDoor.IsOpen, "The start door reopened before gameplay began.");
            Assert.IsFalse(occlusion.IsActive,
                "The chamber wall art was not restored during the dark handoff.");
            Assert.Greater(gateFlank.color.a, 0.9f,
                "The gate flank stayed translucent after gameplay began.");
            Assert.AreEqual(gameplayCameraSize, gameCamera.orthographicSize, 0.01f,
                "The gameplay camera kept the cutscene zoom after the reveal.");
            Assert.AreEqual(3, chase.FiredEntryShotCount,
                "The wizard did not fire the two misses and final hit.");
            Assert.AreEqual(1, chase.EntryImpactCount,
                "The final fireball did not show its hit effect.");
            GameObject player = GameObject.Find("Player");
            PlayerMovement movement = player?.GetComponent<PlayerMovement>();
            Assert.IsNotNull(movement);
            Assert.IsTrue(movement.IsGameplayEnabled,
                "The player still lacks movement after the room reveal.");
            Assert.Less(Vector3.Distance(player.transform.position,
                    EntryChamberLayout.FirstRoomArrival), 0.1f,
                "The player did not start inside Ruined Entry after the chase.");
            yield return null;
            Capture(output, "07-first-room-player-ready", gameCamera, canvas, manifest,
                entry, chase, startDoor);
            File.WriteAllText(Path.Combine(output, "capture-source.txt"), manifest.ToString());
            Debug.Log("Entry cutscene review capture: " + output);
        }

        private static IEnumerator WaitForActiveObject(string name, float maximumSeconds)
        {
            float deadline = Time.realtimeSinceStartup + maximumSeconds;
            while (GameObject.Find(name) == null && Time.realtimeSinceStartup < deadline)
                yield return null;
            Assert.IsNotNull(GameObject.Find(name),
                "The cutscene did not present " + name + " before the timeout.");
        }

        private static void Capture(string output, string name, Camera gameCamera, Canvas canvas,
            StringBuilder manifest, WizardGameEntryController entry,
            TitleScreenChaseBackdrop chase, EntryChamberStartDoor startDoor)
        {
            RenderTexture previousTarget = gameCamera.targetTexture;
            int previousMask = gameCamera.cullingMask;
            RenderTexture previousActive = RenderTexture.active;
            RenderMode previousMode = canvas.renderMode;
            Camera previousWorldCamera = canvas.worldCamera;
            float previousPlaneDistance = canvas.planeDistance;
            Transform[] uiHierarchy = canvas.GetComponentsInChildren<Transform>(true);
            int[] previousLayers = new int[uiHierarchy.Length];
            RenderTexture worldTarget = null;
            RenderTexture uiTarget = null;
            Texture2D worldPixels = null;
            Texture2D uiPixels = null;
            Texture2D composed = null;
            GameObject uiCameraObject = null;

            try
            {
                for (int index = 0; index < uiHierarchy.Length; index++)
                {
                    previousLayers[index] = uiHierarchy[index].gameObject.layer;
                    uiHierarchy[index].gameObject.layer = TemporaryUiLayer;
                }

                worldTarget = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32);
                uiTarget = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32);
                worldTarget.Create();
                uiTarget.Create();

                gameCamera.targetTexture = worldTarget;
                gameCamera.cullingMask = previousMask & ~(1 << TemporaryUiLayer);
                gameCamera.Render();

                uiCameraObject = new GameObject("EntryCaptureUiCamera", typeof(Camera));
                Camera uiCamera = uiCameraObject.GetComponent<Camera>();
                uiCamera.CopyFrom(gameCamera);
                uiCamera.transform.SetPositionAndRotation(
                    gameCamera.transform.position, gameCamera.transform.rotation);
                uiCamera.clearFlags = CameraClearFlags.SolidColor;
                uiCamera.backgroundColor = Color.clear;
                uiCamera.cullingMask = 1 << TemporaryUiLayer;
                uiCamera.nearClipPlane = 0.01f;
                uiCamera.targetTexture = uiTarget;
                uiCamera.enabled = false;
                canvas.renderMode = RenderMode.ScreenSpaceCamera;
                canvas.worldCamera = uiCamera;
                canvas.planeDistance = 1f;
                Canvas.ForceUpdateCanvases();
                uiCamera.Render();

                worldPixels = ReadPixels(worldTarget, TextureFormat.RGB24);
                uiPixels = ReadPixels(uiTarget, TextureFormat.RGBA32);
                if (Environment.GetEnvironmentVariable("NSC_ENTRY_CAPTURE_DEBUG") == "1")
                {
                    File.WriteAllBytes(Path.Combine(output, name + "-ui-only.png"),
                        uiPixels.EncodeToPNG());
                }
                Color32[] worldColours = worldPixels.GetPixels32();
                Color32[] uiColours = uiPixels.GetPixels32();
                for (int index = 0; index < worldColours.Length; index++)
                {
                    byte alpha = uiColours[index].a;
                    // Unity UI's standard alpha blend writes premultiplied RGB onto clear black.
                    worldColours[index] = new Color32(
                        Blend(uiColours[index].r, worldColours[index].r, alpha),
                        Blend(uiColours[index].g, worldColours[index].g, alpha),
                        Blend(uiColours[index].b, worldColours[index].b, alpha), 255);
                }

                composed = new Texture2D(Width, Height, TextureFormat.RGB24, false);
                composed.SetPixels32(worldColours);
                composed.Apply(false, false);
                string path = Path.Combine(output, name + ".png");
                File.WriteAllBytes(path, composed.EncodeToPNG());
                Assert.Greater(new FileInfo(path).Length, 1000L,
                    "Capture is unexpectedly small: " + name);
                manifest.AppendLine(name + ": enteredGameplay=" + entry.HasEnteredGameplay
                    + ", entryChaseRunning=" + entry.IsEntryCutsceneRunning
                    + ", startDoorOpen=" + startDoor.IsOpen
                    + ", shotsFired=" + chase.FiredEntryShotCount
                    + ", hitsShown=" + chase.EntryImpactCount
                    + ", cameraSize=" + gameCamera.orthographicSize.ToString("0.##")
                    + ", scene=" + SceneManager.GetActiveScene().name);
            }
            finally
            {
                canvas.renderMode = previousMode;
                canvas.worldCamera = previousWorldCamera;
                canvas.planeDistance = previousPlaneDistance;
                gameCamera.targetTexture = previousTarget;
                gameCamera.cullingMask = previousMask;
                RenderTexture.active = previousActive;
                for (int index = 0; index < uiHierarchy.Length; index++)
                    uiHierarchy[index].gameObject.layer = previousLayers[index];
                if (uiCameraObject != null) UnityEngine.Object.DestroyImmediate(uiCameraObject);
                if (worldTarget != null)
                {
                    worldTarget.Release();
                    UnityEngine.Object.DestroyImmediate(worldTarget);
                }
                if (uiTarget != null)
                {
                    uiTarget.Release();
                    UnityEngine.Object.DestroyImmediate(uiTarget);
                }
                if (worldPixels != null) UnityEngine.Object.DestroyImmediate(worldPixels);
                if (uiPixels != null) UnityEngine.Object.DestroyImmediate(uiPixels);
                if (composed != null) UnityEngine.Object.DestroyImmediate(composed);
            }
        }

        private static Texture2D ReadPixels(RenderTexture target, TextureFormat format)
        {
            RenderTexture.active = target;
            var pixels = new Texture2D(Width, Height, format, false);
            pixels.ReadPixels(new Rect(0f, 0f, Width, Height), 0, 0);
            pixels.Apply(false, false);
            return pixels;
        }

        private static byte Blend(byte premultipliedUi, byte background, byte alpha)
        {
            return (byte)Mathf.Clamp(
                premultipliedUi + Mathf.RoundToInt(background * (255 - alpha) / 255f),
                0, 255);
        }
    }
}
