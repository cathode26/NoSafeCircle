using System;
using System.Collections.Generic;
using System.IO;
using NoSafeCircle.DoorPrototype.Editor;
using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NoSafeCircle.DoorPrototype.Editor.World;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    /// <summary>Photographs the Final Room for NSC-048's VAL-004 developer visual review.</summary>
    /// <remarks>
    /// NSC-048 VAL-004 is the one gate on this task that no agent can clear: it is Vincent's own
    /// eyes. Until this fixture existed there was no way to SHOW him the room -- LowerVault and
    /// RuinedEntry each have a capture fixture and the Final Room had none -- so the gate was not
    /// merely unmet, it was unreachable, and the task could not become conformant no matter how
    /// much evidence anything else produced.
    /// <para>
    /// The rig is not a design choice. VAL-004 SPECIFIES it: open FinalRoom.unity additively,
    /// stage the existing wizard visual, a 16:9 view, orthographic size 8, rotation (30,-45,0),
    /// follow offset (10,10,-10), and an enabled IsometricCameraFollow so transparencySortMode is
    /// CustomAxis on the project sort axis. The five shot positions are the contract's own. A
    /// picture taken with a different rig does not satisfy a gate that names the rig, which is why
    /// ComposedFloorCaptureTests -- orthographicSize 22, no wizard -- is not a substitute.
    /// </para>
    /// <para>
    /// Explicit and env-gated, like the NSC-044 and NSC-082 captures: it writes PNGs outside the
    /// repository and must never run as part of an ordinary suite.
    /// </para>
    /// </remarks>
    public sealed class FinalRoomCameraReviewTests
    {
        // 16:9, as VAL-004 requires. The NSC-044 fixture renders 800x600, which is 4:3; copying
        // its size would have quietly failed the one framing requirement this gate states.
        private const int ShotWidth = 1280;
        private const int ShotHeight = 720;

        private const string WizardSpritePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png";

        [Explicit("Requires an external NSC048_CAMERA_REVIEW_OUTPUT directory for Vincent's visual review.")]
        [Test]
        public void CaptureGameplayCameraReview()
        {
            string output = Environment.GetEnvironmentVariable("NSC048_CAMERA_REVIEW_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC048_CAMERA_REVIEW_OUTPUT to run the explicit visual capture.");
            }

            Assert.IsTrue(Path.IsPathRooted(output), "NSC048_CAMERA_REVIEW_OUTPUT must be absolute.");
            string outputFull = Path.GetFullPath(output);
            string repository = Path.GetFullPath(Directory.GetCurrentDirectory())
                .TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            Assert.IsFalse(
                outputFull.TrimEnd(Path.DirectorySeparatorChar).Equals(
                    repository.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase)
                || outputFull.StartsWith(repository, StringComparison.OrdinalIgnoreCase),
                "Camera review PNGs must be written outside the repository.");

            // The contract's own five review positions, in its own order.
            string[] names = { "d4-arrival", "west-flank", "east-flank", "d5-staging", "northwest-coverage" };
            Vector3[] positions =
            {
                new Vector3(4f, 0f, 80f),
                new Vector3(-9f, 0f, 91f),
                new Vector3(9f, 0f, 93f),
                new Vector3(0f, 0f, 101f),
                new Vector3(-12f, 0f, 100f)
            };
            Assert.AreEqual(names.Length, positions.Length);

            Directory.CreateDirectory(outputFull);
            foreach (string name in names)
            {
                Assert.IsFalse(File.Exists(Path.Combine(outputFull, name + ".png")),
                    "Use a fresh output directory so earlier visual evidence is preserved.");
            }
            Assert.IsFalse(File.Exists(Path.Combine(outputFull, "contact-sheet.png")));

            // VAL-004 requires the committed scene to be unchanged afterwards. Measure it before
            // and after rather than asserting that nothing was saved: "I closed without saving"
            // is a claim about intent, and the file length is a fact.
            string scenePath = Path.GetFullPath(FinalRoomSceneBuilder.ScenePath);
            long bytesBefore = new FileInfo(scenePath).Length;

            Scene source = default;
            Scene staging = default;
            GameObject wizard = null;
            GameObject cameraObject = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();
            RenderTexture previousActive = RenderTexture.active;
            try
            {
                source = EditorSceneManager.OpenScene(FinalRoomSceneBuilder.ScenePath, OpenSceneMode.Single);
                Assert.IsTrue(source.IsValid(), "Could not open " + FinalRoomSceneBuilder.ScenePath);
                staging = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
                SceneManager.SetActiveScene(staging);

                Sprite wizardSprite = AssetDatabase.LoadAssetAtPath<Sprite>(WizardSpritePath);
                Assert.IsNotNull(wizardSprite, WizardSpritePath);
                wizard = new GameObject("NSC048ReviewWizard", typeof(SpriteRenderer));
                wizard.transform.localScale = new Vector3(1f, 2f, 1f);
                SpriteRenderer wizardRenderer = wizard.GetComponent<SpriteRenderer>();
                wizardRenderer.sprite = wizardSprite;
                // The durable relation, not the value it currently happens to have. A literal
                // "Default" passes today only because the constant equals it, and would keep
                // passing while the wizard sorted wrongly against every world sprite.
                wizardRenderer.sortingLayerName = WorldSpriteConvention.SortingLayerName;
                wizardRenderer.sortingOrder = 0;

                cameraObject = new GameObject(
                    "NSC048ReviewCamera", typeof(Camera), typeof(IsometricCameraFollow));
                Camera camera = cameraObject.GetComponent<Camera>();
                camera.orthographic = true;
                camera.orthographicSize = 8f;
                camera.transparencySortMode = TransparencySortMode.CustomAxis;
                camera.transparencySortAxis = IsometricCameraFollow.IsometricTransparencySortAxis;
                cameraObject.transform.rotation = Quaternion.Euler(30f, -45f, 0f);
                target = new RenderTexture(ShotWidth, ShotHeight, 24);
                target.Create();
                camera.targetTexture = target;

                for (int index = 0; index < names.Length; index++)
                {
                    wizard.transform.position = positions[index];
                    cameraObject.transform.position = positions[index] + new Vector3(10f, 10f, -10f);
                    cameraObject.GetComponent<IsometricCameraFollow>().Initialize(wizard.transform);
                    camera.Render();
                    RenderTexture.active = target;
                    Texture2D shot = new Texture2D(ShotWidth, ShotHeight, TextureFormat.RGBA32, false);
                    shot.ReadPixels(new Rect(0f, 0f, ShotWidth, ShotHeight), 0, 0);
                    shot.Apply(false, false);
                    shots.Add(shot);
                    File.WriteAllBytes(
                        Path.Combine(outputFull, names[index] + ".png"), shot.EncodeToPNG());
                }

                // A fresh Texture2D is NOT cleared, so an unfilled cell carries uninitialised
                // memory that reads as a plausible frame. Five shots in a 2x3 grid leave one
                // cell over; fill it deliberately.
                const int columns = 2;
                int rows = (names.Length + columns - 1) / columns;
                Texture2D contact = new Texture2D(
                    columns * ShotWidth, rows * ShotHeight, TextureFormat.RGBA32, false);
                shots.Add(contact);
                var blank = new Color32[ShotWidth * ShotHeight];
                for (int index = 0; index < columns * rows; index++)
                {
                    Color32[] pixels = index < names.Length ? shots[index].GetPixels32() : blank;
                    int originX = (index % columns) * ShotWidth;
                    int originY = (rows - 1 - (index / columns)) * ShotHeight;
                    contact.SetPixels32(originX, originY, ShotWidth, ShotHeight, pixels);
                }
                contact.Apply(false, false);
                File.WriteAllBytes(Path.Combine(outputFull, "contact-sheet.png"), contact.EncodeToPNG());

                File.WriteAllText(Path.Combine(outputFull, "capture-source.txt"),
                    FinalRoomSceneBuilder.ScenePath + Environment.NewLine +
                    "NSC-048 VAL-004 rig: 16:9, orthographic size 8, rotation (30,-45,0), " +
                    "follow offset (10,10,-10), IsometricCameraFollow enabled" + Environment.NewLine +
                    string.Join(", ", names) + Environment.NewLine);
            }
            finally
            {
                RenderTexture.active = previousActive;
                foreach (Texture2D shot in shots) Object.DestroyImmediate(shot);
                if (cameraObject != null) Object.DestroyImmediate(cameraObject);
                if (wizard != null) Object.DestroyImmediate(wizard);
                if (target != null)
                {
                    target.Release();
                    Object.DestroyImmediate(target);
                }
                if (staging.IsValid() && staging.isLoaded) EditorSceneManager.CloseScene(staging, true);
                if (source.IsValid() && source.isLoaded) EditorSceneManager.CloseScene(source, true);
            }

            Assert.AreEqual(bytesBefore, new FileInfo(scenePath).Length,
                "VAL-004 requires FinalRoom.unity to be unchanged by the review capture.");
        }
    }
}
