using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    /// <summary>
    /// Photographs the world the bootstrap builds at Play, one shot per room.
    /// </summary>
    /// <remarks>
    /// <para>
    /// WHY IT HAS TO BE PLAY MODE, and this is the whole reason it is a new fixture rather than a
    /// parameter on an old one. Every existing capture in this repository is an EDIT MODE test that
    /// opens a committed scene and photographs what is already in it. Under the new architecture
    /// there IS nothing in the scene - the world does not exist until GameBootstrap runs. An edit
    /// mode capture of RuntimeWorld.unity would photograph an empty room and report success.
    /// </para>
    /// <para>
    /// AND WHY IT EXISTS AT ALL: "FOR ART, DIMENSIONS ARE NOT THE ARTEFACT. RENDER IT AND LOOK."
    /// Three agents once reasoned about one wall sprite from its numbers and a render refuted all
    /// three. Test counts prove the machinery ran; only a picture shows whether the game looks like
    /// anything. Vincent's own standing rule is that art is never sent for review without the art
    /// attached, and this is what produces the attachment.
    /// </para>
    /// <para>
    /// EXPLICIT AND ENVIRONMENT-GATED, exactly like the NSC-044 and NSC-082 captures: it writes PNGs
    /// outside the repository and must never run inside an ordinary suite. Set
    /// NSC_RUNTIME_CAPTURE_OUTPUT to a folder to take the shots.
    /// </para>
    /// <para>
    /// IT BUILDS THE WORLD FROM THE PREFAB RATHER THAN LOADING THE SCENE. A Play Mode test cannot
    /// open a scene that is not in the build settings, and adding one there is a shared-file edit
    /// that every lane owner would then be touching. Instantiating GameManagers from Resources
    /// exercises the same object the scene holds, so the picture is honest.
    /// </para>
    /// </remarks>
    public sealed class RuntimeWorldCaptureTests
    {
        private const int ShotWidth = 800;
        private const int ShotHeight = 600;

        // The game's own angle: rotate -45 around Y to face a corner, then tilt 30 down.
        private static readonly Quaternion CameraRotation = Quaternion.Euler(30f, -45f, 0f);

        // DERIVED FROM THE ROTATION, NEVER WRITTEN DOWN, and the reason is recorded in
        // ComposedFloorCaptureTests: a hand-written (30, 30, -30) offset was 4.79 units off the
        // camera's own back axis, which put every room 21.7% of half-height low. Nothing clipped,
        // so no capture ever looked broken - it just read as art sitting low, which is exactly the
        // misreading a capture is supposed to prevent.
        private const float CameraDistance = 51.96f;
        private static readonly Vector3 CameraOffset = CameraRotation * Vector3.back * CameraDistance;

        // Wide enough that the largest room - Lower Vault at 40 units across - fits in one frame.
        private const float OrthographicSize = 22f;

        [UnityTest]
        [Explicit("Set NSC_RUNTIME_CAPTURE_OUTPUT to photograph the world the bootstrap builds.")]
        public IEnumerator CaptureRuntimeWorld()
        {
            string output = Environment.GetEnvironmentVariable("NSC_RUNTIME_CAPTURE_OUTPUT");
            Assert.IsFalse(string.IsNullOrWhiteSpace(output),
                "NSC_RUNTIME_CAPTURE_OUTPUT is not set. This test writes PNGs outside the "
                + "repository and refuses to guess where.");

            string outputFull = Path.GetFullPath(output);
            Directory.CreateDirectory(outputFull);

            var prefab = Resources.Load<GameObject>("GameManagers");
            Assert.IsNotNull(prefab,
                "Resources/GameManagers.prefab did not load. That prefab IS the runtime scene's "
                + "only content, so nothing would build.");

            GameObject managers = Object.Instantiate(prefab);
            var bootstrap = managers.GetComponent<GameBootstrap>();
            Assert.IsNotNull(bootstrap, "GameManagers carries no GameBootstrap.");

            // Start() runs on the next frame; wait for it rather than calling BuildWorld directly,
            // so what is photographed is what pressing Play produces and not a path only a test
            // takes.
            yield return null;
            yield return null;

            Assert.IsTrue(bootstrap.HasBuilt,
                "GameBootstrap had not built after two frames. The capture would photograph an "
                + "empty world and look like an art problem.");

            var names = new List<string>();
            var centres = new List<Vector3>();
            foreach (var room in RoomCentres())
            {
                names.Add(room.Key);
                centres.Add(room.Value);
            }

            GameObject cameraObject = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();

            try
            {
                cameraObject = new GameObject("RuntimeCaptureCamera", typeof(Camera));
                Camera camera = cameraObject.GetComponent<Camera>();
                camera.orthographic = true;
                camera.orthographicSize = OrthographicSize;

                // The isometric sorting convention, applied here too. Without it this camera would
                // sort world sprites by distance and the photograph would show an ordering the game
                // never produces - a capture that lies in the direction of looking broken.
                camera.transparencySortMode = TransparencySortMode.CustomAxis;
                camera.transparencySortAxis = IsometricCameraFollow.IsometricTransparencySortAxis;
                cameraObject.transform.rotation = CameraRotation;

                target = new RenderTexture(ShotWidth, ShotHeight, 24);
                target.Create();
                camera.targetTexture = target;

                for (int index = 0; index < names.Count; index++)
                {
                    cameraObject.transform.position = centres[index] + CameraOffset;
                    camera.Render();
                    RenderTexture.active = target;

                    var shot = new Texture2D(ShotWidth, ShotHeight, TextureFormat.RGBA32, false);
                    shot.ReadPixels(new Rect(0f, 0f, ShotWidth, ShotHeight), 0, 0);
                    shot.Apply(false, false);
                    shots.Add(shot);

                    File.WriteAllBytes(Path.Combine(outputFull, names[index] + ".png"),
                        shot.EncodeToPNG());
                }

                WriteContactSheet(outputFull, names, shots);

                // THE CAPTURE SOURCE FILE IS NOT BOOKKEEPING. A frame with no manifest is a picture
                // nobody can act on: it cannot be re-taken, and a later reader cannot tell whether
                // it shows the build they are asking about. It records what was photographed and
                // what the world contained when it was.
                File.WriteAllText(Path.Combine(outputFull, "capture-source.txt"),
                    "Resources/GameManagers.prefab instantiated at Play" + Environment.NewLine
                    + "GameBootstrap.SpawnedCount = " + bootstrap.SpawnedCount + Environment.NewLine
                    + names.Count + " rooms, centres from Scripts/World/Rooms/*Layout.cs"
                    + Environment.NewLine
                    + "orthographicSize " + OrthographicSize + ", rotation "
                    + CameraRotation.eulerAngles + ", distance " + CameraDistance
                    + Environment.NewLine);
            }
            finally
            {
                RenderTexture.active = null;
                if (cameraObject != null)
                {
                    Object.DestroyImmediate(cameraObject);
                }

                foreach (Texture2D shot in shots)
                {
                    Object.DestroyImmediate(shot);
                }

                if (target != null)
                {
                    target.Release();
                    Object.DestroyImmediate(target);
                }

                if (managers != null)
                {
                    Object.DestroyImmediate(managers);
                }
            }
        }

        /// <summary>
        /// Each room's ground centre, from the layout constants rather than from a written list, so
        /// a room that moves is photographed where it moved to.
        /// </summary>
        private static IEnumerable<KeyValuePair<string, Vector3>> RoomCentres()
        {
            yield return Centre("RuinedEntry", RuinedEntryLayout.RoomBounds);
            yield return Centre("BoneArchive", BoneArchiveLayout.RoomBounds);
            yield return Centre("ChapelOfAsh", ChapelOfAshLayout.RoomBounds);
            yield return Centre("LowerVault", LowerVaultLayout.RoomBounds);
            yield return Centre("FinalRoom", FinalRoomLayout.RoomBounds);
        }

        private static KeyValuePair<string, Vector3> Centre(string name, Bounds bounds) =>
            new KeyValuePair<string, Vector3>(name, new Vector3(bounds.center.x, 0f, bounds.center.z));

        private static void WriteContactSheet(string outputFull, List<string> names,
            List<Texture2D> shots)
        {
            const int Columns = 2;
            int rows = (names.Count + Columns - 1) / Columns;
            var contact = new Texture2D(Columns * ShotWidth, rows * ShotHeight,
                TextureFormat.RGBA32, false);

            // A FRESH Texture2D IS NOT CLEARED, so an unfilled cell carries uninitialised memory
            // that reads as a frame of noise - and noise in a contact sheet looks like a rendering
            // fault rather than an empty slot. Fill every cell explicitly.
            var blank = new Color32[ShotWidth * ShotHeight];
            for (int index = 0; index < Columns * rows; index++)
            {
                Color32[] pixels = index < names.Count ? shots[index].GetPixels32() : blank;
                int originX = (index % Columns) * ShotWidth;
                int originY = (rows - 1 - (index / Columns)) * ShotHeight;
                contact.SetPixels32(originX, originY, ShotWidth, ShotHeight, pixels);
            }

            contact.Apply(false, false);
            File.WriteAllBytes(Path.Combine(outputFull, "contact-sheet.png"), contact.EncodeToPNG());
            Object.DestroyImmediate(contact);
        }
    }
}
