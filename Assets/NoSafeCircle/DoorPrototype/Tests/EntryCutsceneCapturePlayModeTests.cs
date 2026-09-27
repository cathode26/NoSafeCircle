using System;
using System.Collections;
using System.IO;
using System.Text;
using NoSafeCircle.DoorPrototype.World;
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
            Assert.IsNotNull(gameCamera);
            Assert.IsNotNull(canvas);
            Assert.IsNotNull(title);
            Assert.IsNotNull(selection);
            Assert.IsNotNull(entry);

            var manifest = new StringBuilder();
            manifest.AppendLine("Unity " + Application.unityVersion);
            manifest.AppendLine("Revision " + Environment.GetEnvironmentVariable("NSC_CAPTURE_REVISION"));
            manifest.AppendLine("Scene RuntimeWorld.unity; selected wizard option 0");
            manifest.AppendLine("Frames are 1920x1080 manual Camera.Render plus UI canvas composition.");

            Capture(output, "00-title", gameCamera, canvas, manifest, entry);
            title.StartGame();
            yield return null;
            Assert.IsTrue(selection.IsSelectionVisible);
            Capture(output, "01-selection", gameCamera, canvas, manifest, entry);

            selection.SelectOption(0);
            Assert.IsTrue(selection.IsConfirmationAvailable);
            selection.ConfirmSelection();
            yield return null;

            // These early samples show the fleeing wizard and backward fireballs without
            // photographing the dark handoff fade near the end of the cutscene.
            float elapsed = 0f;
            float[] chaseTimes = { 0.8f, 1f, 1.2f };
            for (int index = 0; index < chaseTimes.Length; index++)
            {
                float wait = chaseTimes[index] - elapsed;
                yield return new WaitForSeconds(wait);
                elapsed = chaseTimes[index];
                if (!entry.HasEnteredGameplay)
                {
                    Capture(output, "02-chase-" + (int)(elapsed * 1000f) + "ms",
                        gameCamera, canvas, manifest, entry);
                }
            }

            while (!entry.HasEnteredGameplay && elapsed < MaximumEntrySeconds)
            {
                yield return new WaitForSeconds(0.1f);
                elapsed += 0.1f;
            }

            Assert.IsTrue(entry.HasEnteredGameplay,
                "Entry did not hand control to the player within " + MaximumEntrySeconds + " seconds.");
            yield return null;
            Capture(output, "03-door-sealed-player-ready", gameCamera, canvas, manifest, entry);
            File.WriteAllText(Path.Combine(output, "capture-source.txt"), manifest.ToString());
            Debug.Log("Entry cutscene review capture: " + output);
        }

        private static void Capture(string output, string name, Camera gameCamera, Canvas canvas,
            StringBuilder manifest, WizardGameEntryController entry)
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
