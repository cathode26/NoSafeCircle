using System;
using System.Collections.Generic;
using System.IO;
using NoSafeCircle.DoorPrototype;
using NoSafeCircle.DoorPrototype.Editor.World;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>Photographs the composed floor, one shot centred on each catalog room.</summary>
    /// <remarks>
    /// Four rooms were real on main for a whole night and nobody had seen the floor they
    /// make together. The per-room capture fixtures only exist for two rooms and each is
    /// hardcoded to its own scene, so none of them can answer "what does the composed
    /// game look like". This one takes the scene from an environment variable and derives
    /// its shot positions from RoomSceneCatalog, so it follows the catalog rather than a
    /// hardcoded list and keeps working when a room moves.
    /// <para>
    /// Explicit and env-gated, exactly like the NSC-082/NSC-044 captures: it writes PNGs
    /// outside the repository and must never run as part of an ordinary suite.
    /// </para>
    /// </remarks>
    public sealed class ComposedFloorCaptureTests
    {
        private const int ShotWidth = 800;
        private const int ShotHeight = 600;

        // Derive the camera offset from the rotation instead of writing a vector down.
        // The offset MUST be antiparallel to the camera forward or the room does not sit in
        // the middle of the frame: the hand-written (30, 30, -30) was 4.79 units off that
        // axis, which on an orthographic camera with orthographicSize 22 put every room
        // 21.7% of half-height low. Nothing clipped, so no capture ever looked broken -- it
        // just read as art sitting low, which is exactly the misreading this avoids.
        // Built this way the offset cannot drift when the rotation changes.
        private static readonly Quaternion CameraRotation = Quaternion.Euler(30f, -45f, 0f);
        private const float CameraDistance = 51.96f;
        private static readonly Vector3 CameraOffset =
            CameraRotation * Vector3.back * CameraDistance;

        [Explicit("Set NSC_FLOOR_CAPTURE_OUTPUT and NSC_FLOOR_CAPTURE_SCENE to photograph a scene.")]
        [Test]
        public void CaptureComposedFloor()
        {
            string output = Environment.GetEnvironmentVariable("NSC_FLOOR_CAPTURE_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC_FLOOR_CAPTURE_OUTPUT to run the explicit floor capture.");
            }

            string scenePath = Environment.GetEnvironmentVariable("NSC_FLOOR_CAPTURE_SCENE");
            if (string.IsNullOrWhiteSpace(scenePath))
            {
                scenePath = "Assets/Scenes/DoorPrototype.unity";
            }

            string outputFull = Path.GetFullPath(output);
            string repository = Path.GetFullPath(Directory.GetCurrentDirectory())
                .TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            Assert.IsFalse(outputFull.StartsWith(repository, StringComparison.OrdinalIgnoreCase),
                "Write capture output OUTSIDE the repository so a run cannot dirty it.");
            Directory.CreateDirectory(outputFull);

            Scene scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
            Assert.IsTrue(scene.IsValid(), "Could not open " + scenePath);

            var names = new List<string>();
            var positions = new List<Vector3>();
            foreach (RoomSceneCatalog.RoomCatalogEntry room in RoomSceneCatalog.CreateCanonicalRooms())
            {
                names.Add(room.RoomId.ToString());
                positions.Add(new Vector3(
                    (room.Bounds.MinX + room.Bounds.MaxX) * 0.5f,
                    0f,
                    (room.Bounds.MinZ + room.Bounds.MaxZ) * 0.5f));
            }
            Assert.Greater(names.Count, 0, "The catalog listed no rooms to photograph.");

            GameObject cameraObject = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();
            try
            {
                cameraObject = new GameObject("FloorCaptureCamera", typeof(Camera));
                Camera camera = cameraObject.GetComponent<Camera>();
                camera.orthographic = true;
                // Wide enough to take a whole room in one frame: the largest is 36 units
                // across, against the 16 used for the per-room gameplay reviews.
                camera.orthographicSize = 22f;
                camera.transparencySortMode = TransparencySortMode.CustomAxis;
                camera.transparencySortAxis = IsometricCameraFollow.IsometricTransparencySortAxis;
                cameraObject.transform.rotation = CameraRotation;
                target = new RenderTexture(ShotWidth, ShotHeight, 24);
                target.Create();
                camera.targetTexture = target;

                for (int index = 0; index < names.Count; index++)
                {
                    cameraObject.transform.position = positions[index] + CameraOffset;
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
                // memory that reads as a frame. Require the grid to fill exactly.
                int columns = 2;
                int rows = (names.Count + columns - 1) / columns;
                Texture2D contact = new Texture2D(
                    columns * ShotWidth, rows * ShotHeight, TextureFormat.RGBA32, false);
                shots.Add(contact);
                var blank = new Color32[ShotWidth * ShotHeight];
                for (int index = 0; index < columns * rows; index++)
                {
                    Color32[] pixels = index < names.Count ? shots[index].GetPixels32() : blank;
                    int originX = (index % columns) * ShotWidth;
                    int originY = (rows - 1 - (index / columns)) * ShotHeight;
                    contact.SetPixels32(originX, originY, ShotWidth, ShotHeight, pixels);
                }
                contact.Apply(false, false);
                File.WriteAllBytes(
                    Path.Combine(outputFull, "contact-sheet.png"), contact.EncodeToPNG());

                File.WriteAllText(Path.Combine(outputFull, "capture-source.txt"),
                    scenePath + Environment.NewLine +
                    names.Count + " rooms from RoomSceneCatalog" + Environment.NewLine);
            }
            finally
            {
                RenderTexture.active = null;
                if (cameraObject != null) Object.DestroyImmediate(cameraObject);
                foreach (Texture2D shot in shots) Object.DestroyImmediate(shot);
                if (target != null)
                {
                    target.Release();
                    Object.DestroyImmediate(target);
                }
            }
        }
    }
}
