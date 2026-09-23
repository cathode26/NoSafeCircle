using System;
using System.Collections;
using System.Globalization;
using System.IO;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace NoSafeCircle.DoorPrototype.Diagnostics
{
    /// <summary>
    /// Records a walkthrough: a numbered PNG every couple of seconds plus a
    /// <c>session.json</c> saying where the player was for each one, so a reviewer who
    /// was not holding the controller can agree on how the game looks and point at a
    /// bug by position instead of by guess.
    /// </summary>
    /// <remarks>
    /// It creates itself. F9 starts and stops a session, F10 marks the frame on screen
    /// as interesting, and both actions are public methods so tests drive them without
    /// input.
    /// <para>
    /// Deliberately NOT placed on a GameObject in a scene. Adding a component to a room
    /// scene and saving edits that scene, and the room contracts forbid touching the
    /// blockout -- keeping it untouched is what the room tasks paid for. Walking five
    /// rooms would otherwise mean five edited scenes, or re-adding the object by hand
    /// every session and losing it on every Play mode exit. Creating itself also means
    /// it SURVIVES scene changes, which the manifest needs anyway because it records a
    /// scene name per frame.
    /// </para>
    /// <para>
    /// Frames are written outside the project. Unity imports everything under
    /// <c>Assets/</c> and generates a <c>.meta</c> for each file, so a ten-minute
    /// walkthrough would add roughly six hundred tracked files, and a dirty repository
    /// blocks merges for everyone.
    /// </para>
    /// <para>
    /// The capture reads the composed framebuffer through
    /// <see cref="ScreenCapture.CaptureScreenshotIntoRenderTexture"/>. It deliberately
    /// does not blit some other texture believed to hold the game, which is a
    /// substitution that writes perfectly convincing files of nothing; see
    /// <see cref="WalkthroughFrameCheck"/> for why that failure has to be shouted about.
    /// </para>
    /// </remarks>
    public sealed class WalkthroughCapture : MonoBehaviour
    {
        // DELIBERATELY OUTSIDE the #if !UNITY_WEBGL gate below. This is pure logic
        // with no platform dependency, and WalkthroughOverlayTests calls it. The
        // Editor test assembly is includePlatforms [Editor] with NO excludePlatforms,
        // and UNITY_WEBGL is defined in the EDITOR whenever WebGL is the active build
        // target, so gating it broke the entire test assembly with CS0117 the moment
        // WebGL was selected -- which is exactly what the Release Agent publishes.
        /// <summary>Whether the on-screen readout may draw on this frame.</summary>
        /// <remarks>
        /// Pure, so the rule can be proven by a truth table rather than by looking at a
        /// screenshot. THE SUPPRESSION TERM IS THE LOAD-BEARING ONE.
        /// <see cref="ScreenCapture.CaptureScreenshotIntoRenderTexture"/> grabs the
        /// COMPOSED SCREEN, so anything drawn during a captured frame is burned into the
        /// PNG -- layer culling cannot help, because it is not a camera render. That
        /// failure is silent and expensive: it yields three hundred usable-looking frames
        /// with a debug counter stamped across the room somebody is judging, and the
        /// whole point of this tool is that those frames are evidence.
        /// </remarks>
        public static bool ShouldDrawOverlay(
            bool isCapturing, bool summaryVisible, bool suppressedForCapture)
        {
            return (isCapturing || summaryVisible) && !suppressedForCapture;
        }

#if !UNITY_WEBGL

        /// <summary>
        /// Whether the readback needs flipping. Graphics APIs disagree about the
        /// origin, so <see cref="Auto"/> follows the device and the explicit values
        /// exist because an upside-down walkthrough should be fixable in the Inspector
        /// rather than by a rebuild.
        /// </summary>
        public enum VerticalFlip
        {
            Auto,
            Always,
            Never
        }

        /// <summary>
        /// Create the capture for this play session, once, without touching a scene.
        /// </summary>
        /// <remarks>
        /// It only exists and waits for the hotkey; nothing is captured and no directory
        /// is created until someone presses F9. The guard means a deliberately placed
        /// instance, which a test may add, still wins rather than being duplicated.
        /// </remarks>
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void CreateForPlaySession()
        {
            if (FindFirstObjectByType<WalkthroughCapture>() != null)
            {
                return;
            }

            var host = new GameObject(nameof(WalkthroughCapture));
            host.AddComponent<WalkthroughCapture>();
            DontDestroyOnLoad(host);
        }

        private const string ManifestFileName = "session.json";
        private const float SummarySeconds = 12f;
        private const string BuildCommitResourceName = "BuildCommit";
        private const float MinimumFramesPerSecond = 0.05f;

        [Tooltip("Frames per second. 0.5 is one frame every two seconds.")]
        [SerializeField, Min(MinimumFramesPerSecond)] private float framesPerSecond = 0.5f;

        [Tooltip("Fraction of screen resolution to store. Half size still shows a missing prop.")]
        [SerializeField, Range(0.1f, 1f)] private float scale = 0.75f;

        [Tooltip("Where sessions are written. Must be outside the Unity project.")]
        [SerializeField] private string captureRoot = "C:/nscrev/walkthroughs";

        [SerializeField] private Key toggleKey = Key.F9;
        [SerializeField] private Key markKey = Key.F10;

        [Tooltip("Frames the background writer may hold before refusing more.")]
        [SerializeField, Min(1)] private int maximumQueuedFrames = 24;

        [SerializeField] private VerticalFlip verticalFlip = VerticalFlip.Auto;

        [Tooltip("How long a stop waits for queued frames to reach disk.")]
        [SerializeField, Min(0.5f)] private float drainTimeoutSeconds = 15f;

        private WalkthroughFrameWriter writer;
        private WalkthroughSessionManifest manifest;
        private Coroutine captureLoop;
        private Transform playerTransform;
        private Camera captureCamera;
        private string sessionDirectory;
        private int frameIndex;
        private bool capturing;
        private bool frameContentConfirmed;
        private bool uniformFrameReported;
        private bool overlaySuppressedForCapture;
        private float summaryHideTime;
        private GUIStyle overlayStyle;

        /// <summary>True while a session is running.</summary>
        public bool IsCapturing => capturing;

        /// <summary>Directory of the current or most recent session; null before the first.</summary>
        public string SessionDirectory => sessionDirectory;

        /// <summary>Frames accepted so far in the current session.</summary>
        public int FrameCount => frameIndex;

        /// <summary>Marks recorded so far in the current session.</summary>
        public int MarkCount => manifest != null ? manifest.marks.Count : 0;

        /// <summary>True while a capture owns the frame currently being composed.</summary>
        public bool OverlaySuppressedForCapture => overlaySuppressedForCapture;

        /// <summary>
        /// Redirect output before a session starts. Tests use this so a capture run
        /// never writes into the repository.
        /// </summary>
        public void SetCaptureRoot(string root)
        {
            if (capturing)
            {
                throw new InvalidOperationException("The capture root cannot change during a session.");
            }

            if (string.IsNullOrWhiteSpace(root))
            {
                throw new ArgumentException("A capture root is required.", nameof(root));
            }

            captureRoot = root;
        }

        /// <summary>Set the capture rate before a session starts.</summary>
        public void SetFramesPerSecond(float rate)
        {
            if (capturing)
            {
                throw new InvalidOperationException("The capture rate cannot change during a session.");
            }

            framesPerSecond = Mathf.Max(MinimumFramesPerSecond, rate);
        }

        /// <summary>Start a session if one is not running, otherwise stop it.</summary>
        public void ToggleCapture()
        {
            if (capturing)
            {
                StopCapture();
            }
            else
            {
                StartCapture();
            }
        }

        /// <summary>
        /// Begin a session. Returns false when no session directory could be created,
        /// in which case nothing is started.
        /// </summary>
        public bool StartCapture()
        {
            if (capturing)
            {
                Debug.LogWarning("Walkthrough capture is already running.");
                return false;
            }

            DateTime startedUtc = DateTime.UtcNow;

            if (!TryCreateSessionDirectory(out string directory))
            {
                return false;
            }

            sessionDirectory = directory;
            writer = new WalkthroughFrameWriter(maximumQueuedFrames);
            manifest = BuildManifest(startedUtc);
            frameIndex = 0;
            frameContentConfirmed = false;
            uniformFrameReported = false;
            capturing = true;
            captureLoop = StartCoroutine(CaptureLoop());

            Debug.Log("Walkthrough capture STARTED. Frames and " + ManifestFileName + " go to: " + sessionDirectory);
            return true;
        }

        /// <summary>Stop the session, drain queued frames and write the manifest.</summary>
        public void StopCapture()
        {
            if (!capturing)
            {
                return;
            }

            capturing = false;
            // Leave the final count and the folder on screen long enough to read and
            // retype, so the path does not have to be hunted for afterwards.
            summaryHideTime = Time.unscaledTime + SummarySeconds;

            if (captureLoop != null)
            {
                StopCoroutine(captureLoop);
                captureLoop = null;
            }

            // StopCoroutine abandons the iterator rather than disposing it, so the finally
            // in CaptureOneFrame does NOT run when a stop lands mid-capture. Left alone the
            // flag would stay set for the rest of the session and the summary would never
            // draw -- pressing F9 to stop would show nothing, which is precisely the thing
            // this readout exists to prevent.
            overlaySuppressedForCapture = false;

            FinishSession();
        }

        /// <summary>
        /// Flag the frame currently on screen. A mark with no note is still the
        /// strongest signal in the artifact, because it says which frame to look at.
        /// </summary>
        public void Mark(string note)
        {
            if (!capturing || manifest == null)
            {
                Debug.LogWarning("Walkthrough MARK ignored: no session is running.");
                return;
            }

            manifest.marks.Add(new WalkthroughSessionManifest.Mark
            {
                frameIndex = frameIndex,
                markedUtc = UtcNow(),
                note = note ?? string.Empty
            });

            Debug.Log("Walkthrough MARK recorded at frame " + frameIndex + ".");
        }

        private void Update()
        {
            Keyboard keyboard = Keyboard.current;

            if (keyboard == null)
            {
                return;
            }

            if (keyboard[toggleKey].wasPressedThisFrame)
            {
                ToggleCapture();
            }

            if (keyboard[markKey].wasPressedThisFrame)
            {
                Mark(null);
            }
        }

        /// <summary>Draw the recording readout, except on a frame being captured.</summary>
        private void OnGUI()
        {
            bool summaryVisible = !capturing
                                  && summaryHideTime > 0f
                                  && Time.unscaledTime < summaryHideTime;

            if (!ShouldDrawOverlay(capturing, summaryVisible, overlaySuppressedForCapture))
            {
                return;
            }

            if (overlayStyle == null)
            {
                overlayStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 18,
                    alignment = TextAnchor.UpperLeft,
                    wordWrap = false
                };
            }

            string text = capturing
                ? "RECORDING   frames " + frameIndex + "   marks " + MarkCount + "\n"
                  + "F9 stop     F10 mark"
                : "WALKTHROUGH SAVED   " + frameIndex + " frames\n" + sessionDirectory;

            overlayStyle.normal.textColor = capturing
                ? new Color(1f, 0.35f, 0.35f)
                : Color.white;

            var box = new Rect(12f, 12f, 620f, 62f);
            Color previous = GUI.color;
            GUI.color = new Color(0f, 0f, 0f, 0.65f);
            GUI.DrawTexture(box, Texture2D.whiteTexture);
            GUI.color = previous;

            GUI.Label(
                new Rect(box.x + 10f, box.y + 7f, box.width - 20f, box.height - 14f),
                text,
                overlayStyle);
        }

        private void OnDestroy()
        {
            // Play mode can end mid-session. Without this the PNGs survive and the
            // manifest that explains them does not, which is the artifact we need.
            if (!capturing && writer == null)
            {
                return;
            }

            capturing = false;
            captureLoop = null;
            FinishSession();
        }

        private IEnumerator CaptureLoop()
        {
            var interval = new WaitForSeconds(1f / Mathf.Max(MinimumFramesPerSecond, framesPerSecond));

            while (capturing)
            {
                yield return CaptureOneFrame();
                yield return interval;
            }
        }

        private IEnumerator CaptureOneFrame()
        {
            // Set BEFORE this frame renders. Coroutines resume after Update and BEFORE
            // OnGUI, so the readout sees this flag and skips drawing for exactly the frame
            // ScreenCapture composes. Suppressing after WaitForEndOfFrame would be too
            // late -- by then the overlay is already in the buffer.
            overlaySuppressedForCapture = true;
            try
            {
                yield return CaptureComposedFrame();
            }
            finally
            {
                overlaySuppressedForCapture = false;
            }
        }

        private IEnumerator CaptureComposedFrame()
        {
            yield return new WaitForEndOfFrame();

            int sourceWidth = Screen.width;
            int sourceHeight = Screen.height;

            if (sourceWidth <= 0 || sourceHeight <= 0)
            {
                yield break;
            }

            int targetWidth = Mathf.Max(1, Mathf.RoundToInt(sourceWidth * scale));
            int targetHeight = Mathf.Max(1, Mathf.RoundToInt(sourceHeight * scale));

            RenderTexture composed = RenderTexture.GetTemporary(
                sourceWidth, sourceHeight, 0, RenderTextureFormat.ARGB32);
            RenderTexture resized = RenderTexture.GetTemporary(
                targetWidth, targetHeight, 0, RenderTextureFormat.ARGB32);

            try
            {
                ScreenCapture.CaptureScreenshotIntoRenderTexture(composed);

                // Resize and, where the device needs it, flip -- one GPU blit, rather
                // than a per-row managed pixel copy for every frame.
                if (ShouldFlip())
                {
                    Graphics.Blit(composed, resized, new Vector2(1f, -1f), new Vector2(0f, 1f));
                }
                else
                {
                    Graphics.Blit(composed, resized);
                }

                RenderTexture.ReleaseTemporary(composed);
                composed = null;

                byte[] pixels;

                if (SystemInfo.supportsAsyncGPUReadback)
                {
                    AsyncGPUReadbackRequest request = AsyncGPUReadback.Request(resized, 0, TextureFormat.RGB24);
                    yield return new WaitUntil(() => request.done);

                    if (request.hasError)
                    {
                        Debug.LogError("Walkthrough readback failed; frame skipped.");
                        yield break;
                    }

                    // The returned NativeArray is only valid until the next readback,
                    // so it is copied here and never held across another yield.
                    pixels = request.GetData<byte>().ToArray();
                }
                else
                {
                    pixels = ReadBackOnMainThread(resized, targetWidth, targetHeight);
                }

                RecordAndQueue(pixels, targetWidth, targetHeight);
            }
            finally
            {
                if (composed != null)
                {
                    RenderTexture.ReleaseTemporary(composed);
                }

                RenderTexture.ReleaseTemporary(resized);
            }
        }

        private static byte[] ReadBackOnMainThread(RenderTexture source, int width, int height)
        {
            RenderTexture previous = RenderTexture.active;
            var scratch = new Texture2D(width, height, TextureFormat.RGB24, false, false);

            try
            {
                RenderTexture.active = source;
                scratch.ReadPixels(new Rect(0f, 0f, width, height), 0, 0);
                scratch.Apply(false);

                // The non-generic overload returns a managed copy. The generic one
                // returns a view into texture memory, which Destroy below would
                // invalidate underneath the background writer.
                return scratch.GetRawTextureData();
            }
            finally
            {
                RenderTexture.active = previous;
                Destroy(scratch);
            }
        }

        private void RecordAndQueue(byte[] pixels, int width, int height)
        {
            if (pixels == null || pixels.Length == 0 || writer == null || manifest == null)
            {
                return;
            }

            ReportIfFrameIsEmpty(pixels, width, height);

            int candidateIndex = frameIndex + 1;
            string path = Path.Combine(
                sessionDirectory,
                "Screenshot" + candidateIndex.ToString("D6", CultureInfo.InvariantCulture) + ".png");

            if (!writer.TryEnqueue(pixels, width, height, path))
            {
                // Refused by back pressure. The index is not consumed, so filenames
                // and manifest entries stay in step with the PNGs that exist.
                manifest.framesDroppedByBackPressure = writer.DroppedCount;
                return;
            }

            frameIndex = candidateIndex;
            manifest.framesCaptured = frameIndex;
            manifest.frames.Add(BuildFrameRecord(candidateIndex));
        }

        private void ReportIfFrameIsEmpty(byte[] pixels, int width, int height)
        {
            if (frameContentConfirmed)
            {
                return;
            }

            if (!WalkthroughFrameCheck.IsUniform(pixels, width, height))
            {
                frameContentConfirmed = true;
                return;
            }

            if (uniformFrameReported)
            {
                return;
            }

            uniformFrameReported = true;
            Debug.LogError(
                "Walkthrough capture produced a UNIFORM frame: every pixel is the same colour, " +
                "so these images show nothing. The files are still being written and their " +
                "sizes look normal, so do not read this session as evidence until a frame " +
                "with content appears. Check that the game is actually rendering to the screen.");
        }

        private WalkthroughSessionManifest BuildManifest(DateTime startedUtc)
        {
            TextAsset buildStamp = Resources.Load<TextAsset>(BuildCommitResourceName);

            return new WalkthroughSessionManifest
            {
                startedUtc = startedUtc.ToString("o", CultureInfo.InvariantCulture),
                unityVersion = Application.unityVersion,
                applicationVersion = Application.version,
                buildCommit = buildStamp != null ? buildStamp.text.Trim() : string.Empty,
                startSceneName = SceneManager.GetActiveScene().name,
                framesPerSecond = framesPerSecond,
                scale = scale,
                frameWidth = Mathf.Max(1, Mathf.RoundToInt(Screen.width * scale)),
                frameHeight = Mathf.Max(1, Mathf.RoundToInt(Screen.height * scale))
            };
        }

        private WalkthroughSessionManifest.FrameRecord BuildFrameRecord(int index)
        {
            Transform player = ResolvePlayer();
            Camera camera = ResolveCamera();

            return new WalkthroughSessionManifest.FrameRecord
            {
                index = index,
                capturedUtc = UtcNow(),
                sceneName = SceneManager.GetActiveScene().name,
                playerResolved = player != null,
                playerPosition = player != null ? player.position : Vector3.zero,
                cameraResolved = camera != null,
                cameraPosition = camera != null ? camera.transform.position : Vector3.zero,
                cameraOrthographicSize = camera != null ? camera.orthographicSize : 0f
            };
        }

        private Transform ResolvePlayer()
        {
            // Cached, and re-resolved only while missing: a scene change destroys the
            // old player, and at a frame every couple of seconds this search is not
            // on any hot path.
            if (playerTransform != null)
            {
                return playerTransform;
            }

            PlayerMovement movement = FindFirstObjectByType<PlayerMovement>();
            playerTransform = movement != null ? movement.transform : null;
            return playerTransform;
        }

        private Camera ResolveCamera()
        {
            if (captureCamera != null)
            {
                return captureCamera;
            }

            captureCamera = Camera.main;
            return captureCamera;
        }

        private bool ShouldFlip()
        {
            switch (verticalFlip)
            {
                case VerticalFlip.Always:
                    return true;
                case VerticalFlip.Never:
                    return false;
                default:
                    return SystemInfo.graphicsUVStartsAtTop;
            }
        }

        private void FinishSession()
        {
            if (manifest != null)
            {
                manifest.endedUtc = UtcNow();
            }

            if (writer != null)
            {
                int unwritten = writer.CompleteWriting(TimeSpan.FromSeconds(drainTimeoutSeconds));

                if (manifest != null)
                {
                    manifest.framesDroppedByBackPressure = writer.DroppedCount;
                    manifest.framesUnwrittenAtShutdown = unwritten;
                    manifest.framesFailedToWrite = writer.FailedCount;
                }

                writer.Dispose();
                writer = null;
            }

            WriteManifest();

            if (manifest != null)
            {
                Debug.Log("Walkthrough capture STOPPED after " + manifest.framesCaptured +
                          " frame(s): " + sessionDirectory);
            }

            manifest = null;
        }

        private void WriteManifest()
        {
            if (manifest == null || string.IsNullOrEmpty(sessionDirectory))
            {
                return;
            }

            try
            {
                File.WriteAllText(
                    Path.Combine(sessionDirectory, ManifestFileName),
                    JsonUtility.ToJson(manifest, true));
            }
            catch (Exception exception)
            {
                Debug.LogError("Walkthrough manifest was not written to " + sessionDirectory + ": " + exception);
            }
        }

        private bool TryCreateSessionDirectory(out string directory)
        {
            DateTime now = DateTime.Now;
            string day = now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            string stamp = now.ToString("HH_mm_ss", CultureInfo.InvariantCulture);

            // The stamp resolves to the SECOND, and Directory.CreateDirectory SUCCEEDS
            // SILENTLY on a directory that already exists. Two stop/start cycles inside
            // one second therefore landed in the SAME directory: frame numbering restarted
            // at 000001 and overwrote the previous session PNGs and its manifest in place,
            // so pressing the hotkey twice quickly destroyed the first walkthrough without
            // saying anything. A session that silently eats the previous one is worse than
            // one that refuses to start. Never accept a directory that already exists.
            if (TryCreateFreshDirectory(captureRoot, day, stamp, out directory))
            {
                return true;
            }

            // A session that lands somewhere nobody looks is the same as no session,
            // so the fallback is reported as an error rather than taken quietly.
            string fallbackRoot = Path.Combine(Application.persistentDataPath, "walkthroughs");
            Debug.LogError("Walkthrough capture could not write under '" + captureRoot +
                           "'. Falling back to '" + fallbackRoot + "'.");

            if (TryCreateFreshDirectory(fallbackRoot, day, stamp, out directory))
            {
                return true;
            }

            Debug.LogError("Walkthrough capture could not create a session directory under '" +
                           captureRoot + "' or '" + fallbackRoot + "'. Capture NOT started.");
            return false;
        }

        /// <summary>Allocate a session directory that did not already exist.</summary>
        /// <remarks>
        /// Suffixes the second-resolution stamp until a free name is found, so a capture
        /// started inside the same second as the previous one gets its own directory
        /// instead of overwriting it. Directory.Exists is checked before each create
        /// because CreateDirectory reports success for a directory that is already there.
        /// </remarks>
        // PUBLIC so the data-loss rule can be proven by a test rather than trusted.
        // Overwriting a previous walkthrough is silent and unrecoverable, so this one
        // gets a guard that fails if the allocator ever hands out the same path twice.
        public static bool TryCreateFreshDirectory(
            string root, string day, string stamp, out string created)
        {
            for (int attempt = 1; attempt <= 100; attempt++)
            {
                string leaf = attempt == 1
                    ? stamp
                    : stamp + "-" + attempt.ToString(CultureInfo.InvariantCulture);
                string candidate = Path.Combine(root, day, leaf);

                try
                {
                    if (Directory.Exists(candidate))
                    {
                        continue;
                    }
                }
                catch (Exception exception)
                {
                    Debug.LogWarning("Walkthrough capture could not inspect a session path: " +
                                     exception.Message);
                    created = null;
                    return false;
                }

                if (TryCreateDirectory(candidate, out created))
                {
                    return true;
                }
            }

            Debug.LogError("Walkthrough capture found no free session directory after 100 attempts.");
            created = null;
            return false;
        }

        private static bool TryCreateDirectory(string path, out string created)
        {
            try
            {
                Directory.CreateDirectory(path);
                created = path;
                return true;
            }
            catch (Exception exception)
            {
                Debug.LogWarning("Walkthrough capture could not create '" + path + "': " + exception.Message);
                created = null;
                return false;
            }
        }

        private static string UtcNow()
        {
            return DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture);
        }

#endif
    }
}
