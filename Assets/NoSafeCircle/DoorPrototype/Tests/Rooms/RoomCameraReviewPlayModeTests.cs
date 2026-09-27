using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using NoSafeCircle.DoorPrototype;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Rooms
{
    /// <summary>PlayMode port of the five rooms' developer gameplay-camera review captures.</summary>
    /// <remarks>
    /// <para>
    /// PORTED FROM, ROOM BY ROOM: Tests/Editor/Rooms/BoneArchiveCameraReviewTests.cs (NSC-045
    /// VAL-004), Tests/Editor/Rooms/ChapelOfAshCameraReviewTests.cs (NSC-046 VAL-003),
    /// Tests/Editor/Rooms/FinalRoomCameraReviewTests.cs (NSC-048 VAL-004), and the
    /// CaptureGameplayCameraReview methods that lived inside Tests/Editor/Rooms/
    /// LowerVaultSceneTests.cs (NSC-082 VAL-002) and RuinedEntrySceneTests.cs (NSC-044), both
    /// removed at 04e7abc6 ahead of the committed room-scene deletion, recovered here from
    /// e2359186:Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms/{LowerVault,RuinedEntry}
    /// SceneTests.cs. The three Edit-mode files above are NOT deleted by this port; that deletion
    /// belongs to the room-scene-deletion commit, not to this one.
    /// </para>
    /// <para>
    /// WHY A NEW FIXTURE RATHER THAN A REPAIR OF THE OLD ONES. The old per-room authoring scenes
    /// (BoneArchive.unity, ChapelOfAsh.unity, FinalRoom.unity, LowerVault.unity, RuinedEntry.unity)
    /// and DoorPrototype.unity are dying; Vincent's PropSpawner/GameBootstrap world instead builds
    /// everything at Play from prefabs and JSON catalogs, and the only committed scene left is
    /// Assets/Scenes/RuntimeWorld.unity - a near-empty bootstrap scene carrying just GameManagers.
    /// So every capture below loads THAT scene, waits for GameBootstrap to build the combined
    /// five-room world, and photographs the built world rather than a scene this port does not
    /// save and a later commit deletes.
    /// </para>
    /// <para>
    /// THE STATIONS ARE WORLD COORDINATES, NOT ROOM-LOCAL, AND THIS WAS VERIFIED ROOM BY ROOM
    /// BEFORE THIS FILE WAS WRITTEN. Every *Layout.cs under Scripts/World/Rooms/ declares its
    /// MinimumZ/MaximumZ in the SAME shared axis and they are contiguous: RuinedEntry -26..0,
    /// BoneArchive 0..~18 (consistent because its room starts at the origin), ChapelOfAsh 20..54,
    /// LowerVault 54..76, FinalRoom's MinimumZ = LowerVaultLayout.MaximumZ (76) .. 104. No room
    /// offset is applied anywhere when the combined world is built, so a station authored against
    /// one room's layout constants is already positioned correctly in the composed world and
    /// must NOT be re-translated here.
    /// </para>
    /// <para>
    /// THE SYNTHETIC WIZARD IS KEPT, DELIBERATELY, RATHER THAN USING THE SPAWNED PLAYER. Every
    /// gate's rig is stated against a temporary unsaved review target using existing project art
    /// plus IsometricCameraFollow - the wizard is the AIMING MECHANISM the stations are framed
    /// against, not a prop the shot happens to contain, and the real spawned player is wherever
    /// PlayerSpawner and the navmesh leave it, not at any of the named stations.
    /// </para>
    /// </remarks>
    public sealed class RoomCameraReviewPlayModeTests
    {
        private const string SceneName = "RuntimeWorld";
        private const string ScenePath = "Assets/Scenes/RuntimeWorld.unity";

        // The synthetic wizard's art can no longer be loaded with
        // AssetDatabase.LoadAssetAtPath<Sprite>(...): this assembly (NoSafeCircle.DoorPrototype.
        // Tests, Tests/, not Tests/Editor/) has no UnityEditor reference - confirmed by
        // FiveRoomDoorSequencePlayModeTests.cs reaching DoorPrototypeGlobalSceneBuilder through
        // reflection rather than a direct call, which only makes sense if this assembly cannot
        // see Editor types. So the sprite is read at RUNTIME off Resources/Player/Player.prefab,
        // which is loaded as an ASSET (not instantiated - no player is ever spawned, per the
        // remark above) purely to read its SpriteRenderer's serialized sprite reference.
        // VERIFIED SAME ASSET, NOT MERELY THE SAME LOOK: Player.prefab's SpriteRenderer serializes
        // {fileID: 21300000, guid: ba32e804c3c549e43aa53b4a61cad7be}; the Edit-mode helper's own
        // WizardSpritePath ("Art/Wizard/Source/PixelLab/masculine-light/selected/standing/
        // south-east.png") carries the identical guid in its own .meta. Same guid, same fileID
        // (21300000 is the default single-sprite fileID) - one asset, two routes to it.
        private const string PlayerPrefabResourcePath = "Player/Player";

        // Carries the pre-capture scene bytes from the test body to UnityTearDown, which is the
        // only hook NUnit guarantees runs even when an Assert inside the test throws partway.
        // Null means "never read" (Assert.Ignore fired before any read, or the repository-output
        // guard failed first), and in both cases there is nothing to compare.
        private byte[] _sceneBytesBeforeCapture;

        // Byte-for-byte identical in intent to FiveRoomDoorSequencePlayModeTests.WaitForWorldBuilt
        // and RuntimeWorldLandmarkCapturePlayModeTests.WaitForWorldBuilt - duplicated rather than
        // shared, matching both of those files' own stated convention, so this fixture carries no
        // compile-time dependency on either class's private members.
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
                "GameBootstrap had not built after three frames, so every capture below would "
                + "photograph an empty world and report success. SpawnedCount = "
                + bootstrap.SpawnedCount + ".");
        }

        private static string RequireDirectoryOutsideRepository(string output)
        {
            Assert.IsTrue(Path.IsPathRooted(output), "The review output directory must be absolute.");
            string outputFull = Path.GetFullPath(output);
            string repository = Path.GetFullPath(Directory.GetCurrentDirectory())
                .TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            Assert.IsFalse(
                outputFull.TrimEnd(Path.DirectorySeparatorChar).Equals(
                    repository.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase)
                || outputFull.StartsWith(repository, StringComparison.OrdinalIgnoreCase),
                "Camera review PNGs must be written outside the repository.");
            Directory.CreateDirectory(outputFull);
            return outputFull;
        }

        private static void EnsureFreshOutput(string outputFull, IEnumerable<string> names)
        {
            foreach (string name in names)
            {
                Assert.IsFalse(File.Exists(Path.Combine(outputFull, name + ".png")),
                    "Use a fresh output directory so earlier visual evidence is preserved.");
            }
            Assert.IsFalse(File.Exists(Path.Combine(outputFull, "contact-sheet.png")));
        }

        private static GameObject CreateWizard(string name)
        {
            GameObject playerPrefabAsset = Resources.Load<GameObject>(PlayerPrefabResourcePath);
            Assert.IsNotNull(playerPrefabAsset,
                "Resources/" + PlayerPrefabResourcePath + " did not load, so there is no existing "
                + "project art to read the review wizard's sprite from.");
            SpriteRenderer sourceRenderer = playerPrefabAsset.GetComponentInChildren<SpriteRenderer>(true);
            Assert.IsNotNull(sourceRenderer, "Player.prefab has no SpriteRenderer to read art from.");
            Sprite sprite = sourceRenderer.sprite;
            Assert.IsNotNull(sprite, "Player.prefab's SpriteRenderer has no sprite assigned.");

            var wizard = new GameObject(name, typeof(SpriteRenderer));
            wizard.transform.localScale = new Vector3(1f, 2f, 1f);
            SpriteRenderer renderer = wizard.GetComponent<SpriteRenderer>();
            renderer.sprite = sprite;
            // The durable relation, not the value it currently has - same reasoning as the
            // Edit-mode helper this is ported from.
            renderer.sortingLayerName = WorldSpriteConvention.SortingLayerName;
            renderer.sortingOrder = 0;
            return wizard;
        }

        private static GameObject CreateCamera(
            string name, float orthographicSize, Vector3 eulerAngles,
            int width, int height, out Camera camera, out RenderTexture target)
        {
            var cameraObject = new GameObject(name, typeof(Camera), typeof(IsometricCameraFollow));
            camera = cameraObject.GetComponent<Camera>();
            camera.orthographic = true;
            camera.orthographicSize = orthographicSize;
            camera.transparencySortMode = TransparencySortMode.CustomAxis;
            camera.transparencySortAxis = IsometricCameraFollow.IsometricTransparencySortAxis;
            cameraObject.transform.rotation = Quaternion.Euler(eulerAngles);
            target = new RenderTexture(width, height, 24);
            target.Create();
            camera.targetTexture = target;
            return cameraObject;
        }

        private static Texture2D Shoot(
            Camera camera, GameObject cameraObject, GameObject wizard, RenderTexture target,
            Vector3 groundPosition, Vector3 cameraOffset, int width, int height, string pngPath)
        {
            wizard.transform.position = groundPosition;
            cameraObject.transform.position = groundPosition + cameraOffset;
            cameraObject.GetComponent<IsometricCameraFollow>().Initialize(wizard.transform);
            camera.Render();
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = target;
            var shot = new Texture2D(width, height, TextureFormat.RGBA32, false);
            shot.ReadPixels(new Rect(0f, 0f, width, height), 0, 0);
            shot.Apply(false, false);
            RenderTexture.active = previous;
            File.WriteAllBytes(pngPath, shot.EncodeToPNG());
            return shot;
        }

        private static Texture2D WriteContactSheet(
            string outputFull, IReadOnlyList<Texture2D> shots, int shotCount, int width, int height)
        {
            const int columns = 2;
            int rows = (shotCount + columns - 1) / columns;
            var contact = new Texture2D(columns * width, rows * height, TextureFormat.RGBA32, false);
            var blank = new Color32[width * height];
            for (int index = 0; index < columns * rows; index++)
            {
                Color32[] pixels = index < shotCount ? shots[index].GetPixels32() : blank;
                int originX = (index % columns) * width;
                int originY = (rows - 1 - (index / columns)) * height;
                contact.SetPixels32(originX, originY, width, height, pixels);
            }
            contact.Apply(false, false);
            File.WriteAllBytes(Path.Combine(outputFull, "contact-sheet.png"), contact.EncodeToPNG());
            return contact;
        }

        // ------------------------------------------------------------------
        // BoneArchive - NSC-045 VAL-004
        // ------------------------------------------------------------------

        [Explicit("Set NSC045_CAMERA_REVIEW_OUTPUT to shoot the NSC-045 VAL-004 review panels.")]
        [UnityTest]
        public IEnumerator CaptureBoneArchiveGameplayCameraReview()
        {
            string output = Environment.GetEnvironmentVariable("NSC045_CAMERA_REVIEW_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC045_CAMERA_REVIEW_OUTPUT to run the explicit visual capture.");
            }
            string outputFull = RequireDirectoryOutsideRepository(output);

            // VAL-004's own seven XZ positions, in its own order, unchanged from the Edit-mode
            // fixture and NOT re-translated (see the world-coordinates remark above).
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
            EnsureFreshOutput(outputFull, names);

            _sceneBytesBeforeCapture = File.ReadAllBytes(ScenePath);
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();

            GameObject wizard = null;
            GameObject cameraObject = null;
            GameObject light = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();
            try
            {
                // VAL-004 names a review-light object explicitly.
                light = new GameObject("NSC045ReviewLight", typeof(Light));
                Light reviewLight = light.GetComponent<Light>();
                reviewLight.type = LightType.Directional;
                reviewLight.intensity = 1f;
                light.transform.rotation = Quaternion.Euler(50f, -30f, 0f);

                wizard = CreateWizard("NSC045WizardReviewTarget");
                cameraObject = CreateCamera(
                    "NSC045ReviewCamera", 8f, new Vector3(30f, -45f, 0f),
                    1280, 720, out Camera camera, out target);

                for (int index = 0; index < names.Count; index++)
                {
                    shots.Add(Shoot(
                        camera, cameraObject, wizard, target, positions[index],
                        new Vector3(10f, 10f, -10f), 1280, 720,
                        Path.Combine(outputFull, names[index] + ".png")));
                }
                shots.Add(WriteContactSheet(outputFull, shots, names.Count, 1280, 720));

                File.WriteAllText(Path.Combine(outputFull, "capture-source.txt"),
                    "PlayMode port, RuntimeWorld not BoneArchive.unity" + Environment.NewLine +
                    "NSC-045 VAL-004 rig: orthographic size 8, rotation (30,-45,0), offset (10,10,-10), "
                    + "IsometricCameraFollow enabled, directional review light" + Environment.NewLine +
                    string.Join(", ", names) + Environment.NewLine);
            }
            finally
            {
                foreach (Texture2D shot in shots) Object.Destroy(shot);
                if (cameraObject != null) Object.Destroy(cameraObject);
                if (wizard != null) Object.Destroy(wizard);
                if (light != null) Object.Destroy(light);
                if (target != null) { target.Release(); Object.Destroy(target); }
            }
        }

        // ------------------------------------------------------------------
        // ChapelOfAsh - NSC-046 VAL-003
        // ------------------------------------------------------------------

        [Explicit("Set NSC046_CAMERA_REVIEW_OUTPUT to shoot the NSC-046 VAL-003 review panels.")]
        [UnityTest]
        public IEnumerator CaptureChapelOfAshGameplayCameraReview()
        {
            string output = Environment.GetEnvironmentVariable("NSC046_CAMERA_REVIEW_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC046_CAMERA_REVIEW_OUTPUT to run the explicit visual capture.");
            }
            string outputFull = RequireDirectoryOutsideRepository(output);

            // NOT TRANSCRIBED: read from ChapelOfAshLayout.GameplayCameraReviewStations, the same
            // public array the Edit-mode fixture (and its menu-item precedent) reads, confirmed
            // world-space above. A station that moves there moves here too.
            Vector3[] stations = ChapelOfAshLayout.GameplayCameraReviewStations;
            Assert.AreEqual(4, stations.Length,
                "VAL-003 names four public stations; the shared array no longer holds four.");

            var names = new List<string>
            {
                "station-1-south", "station-2-west", "station-3-east", "station-4-north"
            };
            var positions = new List<Vector3>(stations);
            EnsureFreshOutput(outputFull, names);

            _sceneBytesBeforeCapture = File.ReadAllBytes(ScenePath);
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();

            GameObject wizard = null;
            GameObject cameraObject = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();
            try
            {
                wizard = CreateWizard("NSC046ReviewWizard");
                cameraObject = CreateCamera(
                    "NSC046ReviewCamera", 8f, new Vector3(30f, -45f, 0f),
                    1280, 720, out Camera camera, out target);

                for (int index = 0; index < names.Count; index++)
                {
                    shots.Add(Shoot(
                        camera, cameraObject, wizard, target, positions[index],
                        new Vector3(10f, 10f, -10f), 1280, 720,
                        Path.Combine(outputFull, names[index] + ".png")));
                }
                shots.Add(WriteContactSheet(outputFull, shots, names.Count, 1280, 720));

                File.WriteAllText(Path.Combine(outputFull, "capture-source.txt"),
                    "PlayMode port, RuntimeWorld not ChapelOfAsh.unity" + Environment.NewLine +
                    "NSC-046 VAL-003 rig: orthographic size 8, rotation (30,-45,0), offset (10,10,-10)"
                    + Environment.NewLine +
                    "stations from ChapelOfAshLayout.GameplayCameraReviewStations: " +
                    string.Join(", ", Array.ConvertAll(stations, s => s.ToString())) + Environment.NewLine +
                    "NOT PORTED: the Edit-mode fixture's fifth 'station-4-north-wall-disabled' shot, "
                    + "which toggled the authored scene's NorthFullWallTilemap GameObject off for one "
                    + "frame. The runtime world has no equivalent single object: WallSpawner.cs "
                    + "builds walls as many individually-named per-piece GameObjects "
                    + "(WallSpawner.cs Place(): 'prefab.name x,z'), not one continuous Tilemap per "
                    + "wall, so there is nothing to find and disable by name. Reported rather than "
                    + "dropped silently; this is an EXTRA comparison shot beyond VAL-003's stated "
                    + "four stations, not one of the three fidelity requirements this port was "
                    + "briefed to preserve." + Environment.NewLine +
                    "ALSO NOT COVERED (same as the Edit-mode fixture): the wizard near/far pew, C4 "
                    + "sorting checks are interactive and no fixture, old or new, is a substitute "
                    + "for them." + Environment.NewLine);
            }
            finally
            {
                foreach (Texture2D shot in shots) Object.Destroy(shot);
                if (cameraObject != null) Object.Destroy(cameraObject);
                if (wizard != null) Object.Destroy(wizard);
                if (target != null) { target.Release(); Object.Destroy(target); }
            }
        }

        // ------------------------------------------------------------------
        // FinalRoom - NSC-048 VAL-004
        // ------------------------------------------------------------------

        [Explicit("Set NSC048_CAMERA_REVIEW_OUTPUT to shoot the NSC-048 VAL-004 review panels.")]
        [UnityTest]
        public IEnumerator CaptureFinalRoomGameplayCameraReview()
        {
            string output = Environment.GetEnvironmentVariable("NSC048_CAMERA_REVIEW_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC048_CAMERA_REVIEW_OUTPUT to run the explicit visual capture.");
            }
            string outputFull = RequireDirectoryOutsideRepository(output);

            // VAL-004's own five review positions, in its own order, unchanged and NOT re-translated.
            var names = new List<string>
                { "d4-arrival", "west-flank", "east-flank", "d5-staging", "northwest-coverage" };
            var positions = new List<Vector3>
            {
                new Vector3(4f, 0f, 80f),
                new Vector3(-9f, 0f, 91f),
                new Vector3(9f, 0f, 93f),
                new Vector3(0f, 0f, 101f),
                new Vector3(-12f, 0f, 100f)
            };
            EnsureFreshOutput(outputFull, names);

            _sceneBytesBeforeCapture = File.ReadAllBytes(ScenePath);
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();

            GameObject wizard = null;
            GameObject cameraObject = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();
            try
            {
                wizard = CreateWizard("NSC048ReviewWizard");
                cameraObject = CreateCamera(
                    "NSC048ReviewCamera", 8f, new Vector3(30f, -45f, 0f),
                    1280, 720, out Camera camera, out target);

                for (int index = 0; index < names.Count; index++)
                {
                    shots.Add(Shoot(
                        camera, cameraObject, wizard, target, positions[index],
                        new Vector3(10f, 10f, -10f), 1280, 720,
                        Path.Combine(outputFull, names[index] + ".png")));
                }
                shots.Add(WriteContactSheet(outputFull, shots, names.Count, 1280, 720));

                File.WriteAllText(Path.Combine(outputFull, "capture-source.txt"),
                    "PlayMode port, RuntimeWorld not FinalRoom.unity" + Environment.NewLine +
                    "NSC-048 VAL-004 rig: 16:9, orthographic size 8, rotation (30,-45,0), "
                    + "follow offset (10,10,-10), IsometricCameraFollow enabled" + Environment.NewLine +
                    string.Join(", ", names) + Environment.NewLine);
            }
            finally
            {
                foreach (Texture2D shot in shots) Object.Destroy(shot);
                if (cameraObject != null) Object.Destroy(cameraObject);
                if (wizard != null) Object.Destroy(wizard);
                if (target != null) { target.Release(); Object.Destroy(target); }
            }
        }

        // ------------------------------------------------------------------
        // LowerVault - NSC-082 VAL-002 (recreated; the Edit-mode fixture was deleted at 04e7abc6)
        // ------------------------------------------------------------------

        [Explicit("Set NSC082_CAMERA_REVIEW_OUTPUT to shoot the NSC-082 VAL-002 review panels.")]
        [UnityTest]
        public IEnumerator CaptureLowerVaultGameplayCameraReview()
        {
            string output = Environment.GetEnvironmentVariable("NSC082_CAMERA_REVIEW_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC082_CAMERA_REVIEW_OUTPUT to run the explicit visual capture.");
            }
            string outputFull = RequireDirectoryOutsideRepository(output);

            // Eight positions, recovered from e2359186:.../LowerVaultSceneTests.cs
            // (CaptureGameplayCameraReview, deleted at 04e7abc6). Same reasoning the deleted
            // fixture recorded: the original four all sat on the D3->centre->D4 spine, leaving
            // LV-N1 and two of the three LV-H1 hazard spans outside every frame.
            var names = new List<string>
            {
                "d3-apron", "c1-west-lane", "c1-east-lane", "east-storage",
                "hall-west", "hall-east", "nw-collapse", "d4-apron"
            };
            var positions = new List<Vector3>
            {
                LowerVaultLayout.D3Apron.center,
                new Vector3(-6f, 0f, 62f),
                new Vector3(4.5f, 0f, 62f),
                LowerVaultLayout.EastStoragePile.center,
                LowerVaultLayout.HallWestSpan.center,
                LowerVaultLayout.HallEastSpan.center,
                LowerVaultLayout.NorthWestStorageBar.center,
                LowerVaultLayout.D4Apron.center
            };
            EnsureFreshOutput(outputFull, names);

            _sceneBytesBeforeCapture = File.ReadAllBytes(ScenePath);
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();

            GameObject wizard = null;
            GameObject cameraObject = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();
            try
            {
                // The deleted fixture conditionally staged LowerVaultDressing.prefab because it
                // opened the bare committed blockout scene in isolation. The runtime world has no
                // such gap: GameBootstrap's PropSpawner has already placed every room's dressing
                // catalog by the time WaitForWorldBuilt() returns, so this capture is always of
                // the DRESSED room. Recorded rather than silently changing what gets judged.
                File.WriteAllText(Path.Combine(outputFull, "dressing-state.txt"),
                    "STAGED (unconditionally, via GameBootstrap/PropSpawner in the runtime world - "
                    + "the deleted Edit-mode fixture's conditional dressingPrefab != null branch has "
                    + "no equivalent here because dressing is not optional in this world)"
                    + Environment.NewLine);

                wizard = CreateWizard("NSC082ReviewWizard");
                cameraObject = CreateCamera(
                    "NSC082ReviewCamera", 8f, new Vector3(30f, -45f, 0f),
                    800, 600, out Camera camera, out target);

                for (int index = 0; index < names.Count; index++)
                {
                    shots.Add(Shoot(
                        camera, cameraObject, wizard, target, positions[index],
                        new Vector3(10f, 10f, -10f), 800, 600,
                        Path.Combine(outputFull, names[index] + ".png")));
                }
                shots.Add(WriteContactSheet(outputFull, shots, names.Count, 800, 600));

                File.WriteAllText(Path.Combine(outputFull, "capture-source.txt"),
                    "PlayMode port, RuntimeWorld not LowerVault.unity" + Environment.NewLine +
                    "NSC-082 VAL-002 rig: orthographic size 8, rotation (30,-45,0), offset (10,10,-10)"
                    + Environment.NewLine + string.Join(", ", names) + Environment.NewLine);
            }
            finally
            {
                foreach (Texture2D shot in shots) Object.Destroy(shot);
                if (cameraObject != null) Object.Destroy(cameraObject);
                if (wizard != null) Object.Destroy(wizard);
                if (target != null) { target.Release(); Object.Destroy(target); }
            }
        }

        // ------------------------------------------------------------------
        // RuinedEntry - NSC-044 (recreated; the Edit-mode fixture was deleted at 04e7abc6)
        // ------------------------------------------------------------------

        [Explicit("Set NSC044_CAMERA_REVIEW_OUTPUT to shoot the NSC-044 review panels.")]
        [UnityTest]
        public IEnumerator CaptureRuinedEntryGameplayCameraReview()
        {
            string output = Environment.GetEnvironmentVariable("NSC044_CAMERA_REVIEW_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC044_CAMERA_REVIEW_OUTPUT to run the explicit visual capture.");
            }
            string outputFull = RequireDirectoryOutsideRepository(output);

            // Recovered from e2359186:.../RuinedEntrySceneTests.cs (CaptureGameplayCameraReview,
            // deleted at 04e7abc6).
            var names = new List<string> { "player-start", "west-loop", "east-lane", "d1-staging" };
            var positions = new List<Vector3>
            {
                RuinedEntryLayout.PlayerStart,
                new Vector3(-7f, 0f, -13f),
                new Vector3(10.875f, 0f, -11.75f),
                new Vector3(0f, 0f, -2.75f)
            };
            EnsureFreshOutput(outputFull, names);

            _sceneBytesBeforeCapture = File.ReadAllBytes(ScenePath);
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();

            GameObject wizard = null;
            GameObject cameraObject = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();
            try
            {
                wizard = CreateWizard("NSC044ReviewWizard");
                cameraObject = CreateCamera(
                    "NSC044ReviewCamera", 8f, new Vector3(30f, -45f, 0f),
                    800, 600, out Camera camera, out target);

                for (int index = 0; index < names.Count; index++)
                {
                    shots.Add(Shoot(
                        camera, cameraObject, wizard, target, positions[index],
                        new Vector3(10f, 10f, -10f), 800, 600,
                        Path.Combine(outputFull, names[index] + ".png")));
                }
                shots.Add(WriteContactSheet(outputFull, shots, names.Count, 800, 600));

                File.WriteAllText(Path.Combine(outputFull, "capture-source.txt"),
                    "PlayMode port, RuntimeWorld not RuinedEntry.unity" + Environment.NewLine +
                    "NSC-044 rig: orthographic size 8, rotation (30,-45,0), offset (10,10,-10)"
                    + Environment.NewLine + string.Join(", ", names) + Environment.NewLine);
            }
            finally
            {
                foreach (Texture2D shot in shots) Object.Destroy(shot);
                if (cameraObject != null) Object.Destroy(cameraObject);
                if (wizard != null) Object.Destroy(wizard);
                if (target != null) { target.Release(); Object.Destroy(target); }
            }
        }

        // ------------------------------------------------------------------
        // Shared teardown: unload without saving, then check RuntimeWorld.unity's committed bytes.
        // ------------------------------------------------------------------

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            yield return UnloadRuntimeWorldSceneWithoutSaving();

            if (_sceneBytesBeforeCapture != null)
            {
                // PROPERTY 3, THE BYTE-IDENTITY ASSERTION - SUBSTITUTED, NOT DROPPED.
                //
                // The Edit-mode sources this ports from close BoneArchive.unity/ChapelOfAsh.unity/
                // FinalRoom.unity via EditorSceneManager.OpenScene/CloseScene(saveChanges:false)
                // and then assert the room-scene file's bytes are unchanged - the fleet's
                // never-dirty-the-repository rule encoded as an assertion. (The LowerVault and
                // RuinedEntry originals never had this assertion at all; it is added here for all
                // five rooms uniformly rather than reproducing that asymmetry, since the check
                // costs nothing and guards a real risk in every one of them.)
                //
                // PlayMode never opens a committed scene for editing: SceneManager.LoadSceneAsync
                // loads RuntimeWorld.unity for SIMULATION, Unity does not write Play-mode state
                // back to the scene asset on disk, and the unload above never saves. So the exact
                // OpenScene/CloseScene risk the sources guarded against does not exist on this
                // path, and the gate clause requiring it is inapplicable in its original form.
                //
                // THE SUBSTITUTION, matching the one already landed and reviewed in
                // RuntimeWorldLandmarkCapturePlayModeTests.cs: RuntimeWorld.unity is the scene
                // PlayMode actually loads for every capture above, so its on-disk bytes are read
                // before the load (in each test body) and compared here, after the unload. This
                // guards a DIFFERENT risk than the original - not OpenScene/CloseScene, which
                // never runs here, but an editor autosave, a domain reload, or a future change
                // that opens this scene for editing mid-capture.
                CollectionAssert.AreEqual(_sceneBytesBeforeCapture, File.ReadAllBytes(ScenePath),
                    "Photographing the runtime world must not modify the committed RuntimeWorld "
                    + "scene on disk.");
                _sceneBytesBeforeCapture = null;
            }
        }

        // Byte-for-byte identical in intent to FiveRoomDoorSequencePlayModeTests.
        // UnloadRuntimeWorldSceneWithoutSaving and RuntimeWorldLandmarkCapturePlayModeTests'
        // method of the same name - duplicated rather than shared, per those files' own stated
        // convention. MUST be awaited: an unawaited SceneManager.UnloadSceneAsync lands its
        // unload asynchronously inside whichever fixture runs next.
        private static IEnumerator UnloadRuntimeWorldSceneWithoutSaving()
        {
            Scene scene = SceneManager.GetSceneByName(SceneName);
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            Scene cleanupScene = SceneManager.CreateScene("RoomCameraReviewPlayModeTestsCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }
    }
}
