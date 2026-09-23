using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NoSafeCircle.DoorPrototype.Editor;
using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Tilemaps;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    /// <summary>Photographs the Chapel of Ash for NSC-046's VAL-003 developer visual review.</summary>
    /// <remarks>
    /// VAL-003 asks Vincent to review through the "No Safe Circle/Rooms/Preview Chapel of Ash
    /// Gameplay Camera" menu item at four public stations. That menu item stages an interactive
    /// preview and writes nothing, so there has never been anything to PUT IN FRONT OF HIM without
    /// him opening the editor himself. This renders the same rig to PNGs.
    /// <para>
    /// THE STATIONS ARE NOT TRANSCRIBED. They come from
    /// ChapelOfAshLayout.GameplayCameraReviewStations, the same public array the menu item reads,
    /// so a station that moves moves here too. Transcribing the gate's four coordinates would have
    /// produced a fixture that silently disagrees with the preview it is standing in for.
    /// </para>
    /// <para>
    /// WHAT THIS CANNOT DO, and it is part of the gate: VAL-003 also requires moving the wizard to
    /// the camera-near and camera-far sides of a pew, C4 and the north wall and judging sorting in
    /// both directions. That is an interactive check. The menu item above does it in one click and
    /// this fixture is not a substitute for it -- say so when handing over the sheet rather than
    /// letting five PNGs imply the whole gate was covered.
    /// </para>
    /// </remarks>
    public sealed class ChapelOfAshCameraReviewTests
    {
        // Neither NSC-046 nor NSC-045 states an aspect ratio, unlike NSC-048 which requires 16:9.
        // 16:9 is used here because it is the shipping aspect, not because a gate demands it.
        private const int ShotWidth = 1280;
        private const int ShotHeight = 720;

        // The rig VAL-003's preview uses. These match ChapelOfAshSceneBuilder's private preview
        // constants and the gate text; they are restated because those constants are private.
        private const float ReviewOrthographicSize = 8f;
        private static readonly Vector3 ReviewCameraEuler = new Vector3(30f, -45f, 0f);
        private static readonly Vector3 ReviewCameraOffset = new Vector3(10f, 10f, -10f);

        private const string WizardSpritePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png";

        [Explicit("Requires an external NSC046_CAMERA_REVIEW_OUTPUT directory for Vincent's visual review.")]
        [Test]
        public void CaptureGameplayCameraReview()
        {
            string output = Environment.GetEnvironmentVariable("NSC046_CAMERA_REVIEW_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC046_CAMERA_REVIEW_OUTPUT to run the explicit visual capture.");
            }

            string outputFull = RoomCameraReview.RequireDirectoryOutsideRepository(output);

            Vector3[] stations = ChapelOfAshLayout.GameplayCameraReviewStations;
            Assert.AreEqual(4, stations.Length,
                "VAL-003 names four public stations; the shared array no longer holds four.");

            var names = new List<string>
            {
                "station-1-south", "station-2-west", "station-3-east", "station-4-north"
            };
            var positions = new List<Vector3>(stations);

            // VAL-003 explicitly requires judging the north ritual reservation with
            // NorthFullWallTilemap DISABLED, because INT-006 replaces that wall with Lower Vault's
            // cutaway stub in the composed scene. Without this shot the sheet would answer every
            // part of the gate except the one it calls out by name.
            names.Add("station-4-north-wall-disabled");
            positions.Add(stations[3]);

            RoomCameraReview.EnsureFreshOutput(outputFull, names);

            string scenePath = Path.GetFullPath(ChapelOfAshSceneBuilder.ScenePath);
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
                source = EditorSceneManager.OpenScene(ChapelOfAshSceneBuilder.ScenePath, OpenSceneMode.Single);
                Assert.IsTrue(source.IsValid(), "Could not open " + ChapelOfAshSceneBuilder.ScenePath);
                staging = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
                SceneManager.SetActiveScene(staging);

                wizard = RoomCameraReview.CreateWizard("NSC046ReviewWizard", WizardSpritePath);
                cameraObject = RoomCameraReview.CreateCamera(
                    "NSC046ReviewCamera", ReviewOrthographicSize, ReviewCameraEuler,
                    ShotWidth, ShotHeight, out Camera camera, out target);

                Tilemap northWall = RoomCameraReview.FindTilemap("NorthFullWallTilemap");
                Assert.IsNotNull(northWall,
                    "VAL-003 requires a shot with NorthFullWallTilemap disabled; it was not found.");

                for (int index = 0; index < names.Count; index++)
                {
                    bool wallDisabledShot = names[index].EndsWith("wall-disabled", StringComparison.Ordinal);
                    northWall.gameObject.SetActive(!wallDisabledShot);

                    shots.Add(RoomCameraReview.Shoot(
                        camera, cameraObject, wizard, target, positions[index], ReviewCameraOffset,
                        ShotWidth, ShotHeight, Path.Combine(outputFull, names[index] + ".png")));
                }
                northWall.gameObject.SetActive(true);

                shots.Add(RoomCameraReview.WriteContactSheet(
                    outputFull, shots, names.Count, ShotWidth, ShotHeight));

                File.WriteAllText(Path.Combine(outputFull, "capture-source.txt"),
                    ChapelOfAshSceneBuilder.ScenePath + Environment.NewLine +
                    "NSC-046 VAL-003 rig: orthographic size 8, rotation (30,-45,0), offset (10,10,-10)"
                    + Environment.NewLine +
                    "stations from ChapelOfAshLayout.GameplayCameraReviewStations: " +
                    string.Join(", ", stations.Select(s => s.ToString())) + Environment.NewLine +
                    "NOT COVERED BY THESE SHOTS: the wizard near/far pew, C4 and north-wall sorting " +
                    "checks, which are interactive. Use the Preview Chapel of Ash Gameplay Camera " +
                    "menu item for those." + Environment.NewLine);
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
                "The review capture must leave the committed room scene unchanged.");
        }
    }
}
