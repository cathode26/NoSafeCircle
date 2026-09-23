#if !UNITY_WEBGL
using System;
using System.Collections;
using System.IO;
using NoSafeCircle.DoorPrototype.Diagnostics;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    /// <summary>
    /// Play Mode coverage for the walkthrough capture path.
    /// </summary>
    /// <remarks>
    /// The load-bearing test here is
    /// <see cref="A_captured_frame_holds_the_rendered_scene_and_is_not_uniform"/>. A
    /// capture path that resolves the wrong source still runs, still writes files of a
    /// plausible size and still logs success, so a test asserting only that a file
    /// exists with non-zero length passes on a folder of blank images. This decodes the
    /// PNG and fails when it shows one flat colour.
    /// <para>
    /// These tests need a real graphics device and a running frame loop, and they say
    /// so rather than passing when they cannot prove anything:
    /// <see cref="WaitForEndOfFrame"/> does not resume under <c>-batchmode</c>, and a
    /// null graphics device renders nothing at all. Both cases are ignored explicitly,
    /// which means a batch run leaves this path UNPROVEN and it must be exercised from
    /// the Editor before the capture is relied on as evidence.
    /// </para>
    /// <para>
    /// Everything written goes to the system temporary directory and is deleted in
    /// teardown, so a run never leaves files in the repository.
    /// </para>
    /// </remarks>
    public class WalkthroughCapturePlayModeTests
    {
        private const float CaptureRatePerSecond = 10f;
        private const float FrameWaitSeconds = 20f;

        private string temporaryRoot;
        private GameObject cameraObject;
        private GameObject canvasObject;
        private GameObject captureObject;

        [SetUp]
        public void SetUp()
        {
            temporaryRoot = Path.Combine(
                Path.GetTempPath(),
                "nsc-walkthrough-playmode",
                Guid.NewGuid().ToString("N"));
        }

        [TearDown]
        public void TearDown()
        {
            DestroyIfPresent(captureObject);
            DestroyIfPresent(canvasObject);
            DestroyIfPresent(cameraObject);

            captureObject = null;
            canvasObject = null;
            cameraObject = null;

            if (temporaryRoot != null && Directory.Exists(temporaryRoot))
            {
                Directory.Delete(temporaryRoot, true);
            }
        }

        private static void DestroyIfPresent(GameObject target)
        {
            if (target != null)
            {
                UnityEngine.Object.DestroyImmediate(target);
            }
        }

        private static void RequireRenderableFrameLoop()
        {
            if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
            {
                Assert.Ignore(
                    "No graphics device, so nothing renders and the capture path CANNOT be " +
                    "proven by this run. Treat the walkthrough capture as unverified until " +
                    "this test is run in the Editor with a display.");
            }

            if (Application.isBatchMode)
            {
                Assert.Ignore(
                    "WaitForEndOfFrame does not resume under -batchmode, so the capture path " +
                    "CANNOT be proven by this run. Treat the walkthrough capture as unverified " +
                    "until this test is run in the Editor.");
            }
        }

        /// <summary>
        /// A black camera background with a white overlay covering part of the screen:
        /// two clearly different colours, so a frame that actually holds the rendered
        /// scene cannot be uniform.
        /// </summary>
        private void BuildTwoColourScene()
        {
            cameraObject = new GameObject("Walkthrough Test Camera");
            Camera camera = cameraObject.AddComponent<Camera>();
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = Color.black;
            camera.orthographic = true;

            canvasObject = new GameObject("Walkthrough Test Canvas");
            Canvas canvas = canvasObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;

            var imageObject = new GameObject("Walkthrough Test Image");
            imageObject.transform.SetParent(canvasObject.transform, false);

            Image image = imageObject.AddComponent<Image>();
            image.color = Color.white;

            RectTransform rect = image.rectTransform;
            rect.anchorMin = new Vector2(0f, 0f);
            rect.anchorMax = new Vector2(1f, 0.5f);
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }

        private WalkthroughCapture BuildCapture()
        {
            captureObject = new GameObject("Walkthrough Capture");
            WalkthroughCapture capture = captureObject.AddComponent<WalkthroughCapture>();
            capture.SetCaptureRoot(temporaryRoot);
            capture.SetFramesPerSecond(CaptureRatePerSecond);
            return capture;
        }

        private static IEnumerator WaitForFrames(WalkthroughCapture capture, int wanted)
        {
            float deadline = Time.realtimeSinceStartup + FrameWaitSeconds;

            while (capture.FrameCount < wanted && Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }

            Assert.GreaterOrEqual(
                capture.FrameCount, wanted,
                "The capture produced no frame within " + FrameWaitSeconds + " seconds.");
        }

        private static string[] CapturedPngs(string directory)
        {
            string[] files = Directory.GetFiles(directory, "Screenshot*.png", SearchOption.AllDirectories);
            Array.Sort(files, StringComparer.Ordinal);
            return files;
        }

        private static byte[] DecodeToRgb24(string path, out int width, out int height)
        {
            var decoded = new Texture2D(2, 2, TextureFormat.RGBA32, false);

            try
            {
                Assert.IsTrue(
                    ImageConversion.LoadImage(decoded, File.ReadAllBytes(path)),
                    "The captured file did not decode as an image: " + path);

                width = decoded.width;
                height = decoded.height;

                Color32[] colours = decoded.GetPixels32();
                var pixels = new byte[colours.Length * WalkthroughFrameCheck.BytesPerPixel];

                for (int index = 0; index < colours.Length; index++)
                {
                    int offset = index * WalkthroughFrameCheck.BytesPerPixel;
                    pixels[offset] = colours[index].r;
                    pixels[offset + 1] = colours[index].g;
                    pixels[offset + 2] = colours[index].b;
                }

                return pixels;
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(decoded);
            }
        }

        [UnityTest]
        public IEnumerator A_captured_frame_holds_the_rendered_scene_and_is_not_uniform()
        {
            RequireRenderableFrameLoop();
            BuildTwoColourScene();

            WalkthroughCapture capture = BuildCapture();
            Assert.IsTrue(capture.StartCapture(), "The session did not start.");

            yield return WaitForFrames(capture, 1);

            string directory = capture.SessionDirectory;
            capture.StopCapture();

            string[] files = CapturedPngs(directory);
            Assert.Greater(files.Length, 0, "No screenshot reached disk.");

            byte[] pixels = DecodeToRgb24(files[0], out int width, out int height);

            Assert.IsFalse(
                WalkthroughFrameCheck.IsUniform(pixels, width, height),
                "The captured frame is a single flat colour. The capture wrote a file of the " +
                "right size that shows nothing, which is the exact silent failure this test " +
                "exists to catch: the frame is not being read from the composed framebuffer.");
        }

        [UnityTest]
        public IEnumerator The_manifest_records_a_frame_for_every_file_and_the_marks_taken()
        {
            RequireRenderableFrameLoop();
            BuildTwoColourScene();

            WalkthroughCapture capture = BuildCapture();
            Assert.IsTrue(capture.StartCapture());

            yield return WaitForFrames(capture, 2);

            capture.Mark("looks wrong here");

            string directory = capture.SessionDirectory;
            capture.StopCapture();

            string manifestPath = Path.Combine(directory, "session.json");
            FileAssert.Exists(manifestPath);

            WalkthroughSessionManifest manifest =
                JsonUtility.FromJson<WalkthroughSessionManifest>(File.ReadAllText(manifestPath));

            Assert.IsNotNull(manifest, "The manifest did not parse.");
            Assert.AreEqual(0, manifest.framesUnwrittenAtShutdown, "Frames were left unwritten.");
            Assert.AreEqual(
                CapturedPngs(directory).Length, manifest.frames.Count,
                "Every written PNG needs a manifest entry and vice versa, or a reader cannot " +
                "tell which frame a position belongs to.");

            Assert.AreEqual(1, manifest.marks.Count, "The mark was not recorded.");
            Assert.AreEqual("looks wrong here", manifest.marks[0].note);
            Assert.Greater(manifest.marks[0].frameIndex, 0, "A mark must name the frame on screen.");
            Assert.IsNotEmpty(manifest.startedUtc);
            Assert.IsNotEmpty(manifest.endedUtc);
        }

        [UnityTest]
        public IEnumerator A_session_writes_nothing_inside_the_unity_project()
        {
            // Unity imports everything under Assets/ and generates a .meta per file,
            // so a walkthrough landing there would add hundreds of tracked files and
            // leave the repository dirty for every other agent.
            RequireRenderableFrameLoop();
            BuildTwoColourScene();

            WalkthroughCapture capture = BuildCapture();
            Assert.IsTrue(capture.StartCapture());

            yield return WaitForFrames(capture, 1);

            string directory = capture.SessionDirectory;
            capture.StopCapture();

            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            string resolved = Path.GetFullPath(directory);

            Assert.IsFalse(
                resolved.StartsWith(projectRoot, StringComparison.OrdinalIgnoreCase),
                "The session wrote inside the Unity project: " + resolved);
        }

        [UnityTest]
        public IEnumerator A_mark_outside_a_session_is_refused_rather_than_recorded()
        {
            RequireRenderableFrameLoop();

            WalkthroughCapture capture = BuildCapture();

            LogAssert.Expect(LogType.Warning, "Walkthrough MARK ignored: no session is running.");
            capture.Mark("nothing is running");

            Assert.IsFalse(capture.IsCapturing);
            yield return null;
        }
    }
}
#endif
