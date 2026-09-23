using System;
using System.Collections.Generic;
using System.IO;
using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    /// <summary>Photographs the Bone Archive for NSC-045's VAL-004 developer visual review.</summary>
    /// <remarks>
    /// NSC-045's pipeline route is dead at five separate guards, so this gate was never going to be
    /// cleared through the controller. The room itself is real now -- its builder was the stub and
    /// was given a tiled floor and walls, taking the scene from 2,896 to 11,541 lines -- so there
    /// is finally something to shoot.
    /// <para>
    /// SEVEN SHOTS, NOT FOUR. The gate names seven grounded wizard positions and every one of them
    /// answers a different question it asks: D1 entry for the doorway read, the two bypasses and
    /// the A-to-B lane for route choice, BA-1 for the pinch, the north crossover for the reliquary
    /// focal, and D2 staging for the exit. A shorter sheet would look complete and leave the gate
    /// unanswerable on whichever question got dropped.
    /// </para>
    /// <para>
    /// The gate also asks for a review light, so one is created rather than relying on whatever
    /// ambient lighting the scene happens to carry.
    /// </para>
    /// </remarks>
    public sealed class BoneArchiveCameraReviewTests
    {
        // NSC-045 VAL-004 states the rig: orthographic size 8, Euler (30,-45,0), offset (10,10,-10).
        // It states no aspect ratio; 16:9 is the shipping aspect, not a gate requirement.
        private const int ShotWidth = 1280;
        private const int ShotHeight = 720;
        private const float ReviewOrthographicSize = 8f;
        private static readonly Vector3 ReviewCameraEuler = new Vector3(30f, -45f, 0f);
        private static readonly Vector3 ReviewCameraOffset = new Vector3(10f, 10f, -10f);

        private const string WizardSpritePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png";

        [Explicit("Requires an external NSC045_CAMERA_REVIEW_OUTPUT directory for Vincent's visual review.")]
        [Test]
        public void CaptureGameplayCameraReview()
        {
            string output = Environment.GetEnvironmentVariable("NSC045_CAMERA_REVIEW_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC045_CAMERA_REVIEW_OUTPUT to run the explicit visual capture.");
            }

            string outputFull = RoomCameraReview.RequireDirectoryOutsideRepository(output);

            // The gate's own seven XZ positions, in its own order, each named for the question it
            // is there to answer.
            var names = new List<string>
            {
                "1-d1-entry", "2-west-bypass", "3-a-to-b-lane", "4-ba1-b-to-c",
                "5-east-bypass", "6-north-crossover-reliquary", "7-d2-staging"
            };
            var positions = new List<Vector3>
            {
                new Vector3(0f, 0f, 2f),
                new Vector3(-9f, 0f, 10f),
                new Vector3(-4.25f, 0f, 9f),
                new Vector3(1.25f, 0f, 10f),
                new Vector3(5.5f, 0f, 10f),
                new Vector3(0f, 0f, 17.5f),
                new Vector3(6f, 0f, 18f)
            };
            Assert.AreEqual(names.Count, positions.Count);
            Assert.AreEqual(7, positions.Count, "VAL-004 names seven capture positions.");

            RoomCameraReview.EnsureFreshOutput(outputFull, names);

            string scenePath = Path.GetFullPath(BoneArchiveSceneBuilder.ScenePath);
            long bytesBefore = new FileInfo(scenePath).Length;

            Scene source = default;
            Scene staging = default;
            GameObject wizard = null;
            GameObject cameraObject = null;
            GameObject light = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();
            RenderTexture previousActive = RenderTexture.active;
            try
            {
                source = EditorSceneManager.OpenScene(BoneArchiveSceneBuilder.ScenePath, OpenSceneMode.Single);
                Assert.IsTrue(source.IsValid(), "Could not open " + BoneArchiveSceneBuilder.ScenePath);
                staging = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
                SceneManager.SetActiveScene(staging);

                // VAL-004 names a review-light object explicitly.
                light = new GameObject("NSC045ReviewLight", typeof(Light));
                Light reviewLight = light.GetComponent<Light>();
                reviewLight.type = LightType.Directional;
                reviewLight.intensity = 1f;
                light.transform.rotation = Quaternion.Euler(50f, -30f, 0f);

                wizard = RoomCameraReview.CreateWizard("NSC045WizardReviewTarget", WizardSpritePath);
                cameraObject = RoomCameraReview.CreateCamera(
                    "NSC045ReviewCamera", ReviewOrthographicSize, ReviewCameraEuler,
                    ShotWidth, ShotHeight, out Camera camera, out target);

                for (int index = 0; index < names.Count; index++)
                {
                    shots.Add(RoomCameraReview.Shoot(
                        camera, cameraObject, wizard, target, positions[index], ReviewCameraOffset,
                        ShotWidth, ShotHeight, Path.Combine(outputFull, names[index] + ".png")));
                }

                shots.Add(RoomCameraReview.WriteContactSheet(
                    outputFull, shots, names.Count, ShotWidth, ShotHeight));

                File.WriteAllText(Path.Combine(outputFull, "capture-source.txt"),
                    BoneArchiveSceneBuilder.ScenePath + Environment.NewLine +
                    "NSC-045 VAL-004 rig: orthographic size 8, rotation (30,-45,0), offset (10,10,-10), " +
                    "IsometricCameraFollow enabled, directional review light" + Environment.NewLine +
                    string.Join(", ", names) + Environment.NewLine +
                    "NOTE: the readable D1 frame comes from NSC-049's door instance, not from this " +
                    "scene, so judge the D1 opening as a gap rather than as a framed doorway."
                    + Environment.NewLine);
            }
            finally
            {
                RenderTexture.active = previousActive;
                foreach (Texture2D shot in shots) Object.DestroyImmediate(shot);
                if (cameraObject != null) Object.DestroyImmediate(cameraObject);
                if (wizard != null) Object.DestroyImmediate(wizard);
                if (light != null) Object.DestroyImmediate(light);
                if (target != null)
                {
                    target.Release();
                    Object.DestroyImmediate(target);
                }
                if (staging.IsValid() && staging.isLoaded) EditorSceneManager.CloseScene(staging, true);
                if (source.IsValid() && source.isLoaded) EditorSceneManager.CloseScene(source, true);
            }

            Assert.AreEqual(bytesBefore, new FileInfo(scenePath).Length,
                "VAL-004 requires the committed room scene to be unchanged by the review capture.");
        }
    }
}
