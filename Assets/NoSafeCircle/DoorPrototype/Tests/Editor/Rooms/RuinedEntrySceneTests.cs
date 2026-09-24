using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.World;
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
    public sealed class RuinedEntrySceneTests
    {
        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            RuinedEntrySceneBuilder.BuildInMemoryForTests();
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [Test]
        public void Layout_UsesApprovedBoundsDoorAndTouchingRubbleFootprints()
        {
            Assert.AreEqual(new Vector3(0f, 0f, -13f), RuinedEntryLayout.RoomBounds.center);
            Assert.AreEqual(new Vector3(28f, 0f, 26f), RuinedEntryLayout.RoomBounds.size);
            Assert.AreEqual(3f, RuinedEntryLayout.DoorOpeningWidth);
            Assert.AreEqual(new Vector3(-4f, 0f, -22f), RuinedEntryLayout.PlayerStart);

            Assert.AreEqual(new Vector3(5f, 0f, -13.5f), RuinedEntryLayout.RubbleABounds.center);
            Assert.AreEqual(new Vector3(6f, 0f, 7f), RuinedEntryLayout.RubbleABounds.size);
            Assert.AreEqual(new Vector3(8f, 0f, -8f), RuinedEntryLayout.RubbleBBounds.center);
            Assert.AreEqual(new Vector3(4f, 0f, 4f), RuinedEntryLayout.RubbleBBounds.size);
            Assert.AreEqual(RuinedEntryLayout.RubbleAMaximumZ, RuinedEntryLayout.RubbleBMinimumZ,
                "Rubble A and B must touch to preserve the approved L-shaped hard-geometry footprint.");
        }

        [Test]
        public void InMemoryGeometry_MatchesRevisedRoomAndPreservesBothRoutes()
        {
            AssertRoomGeometry(SceneManager.GetActiveScene());
        }

        [Test]
        public void CommittedGeometry_MatchesRevisedRoomAndPreservesBothRoutes()
        {
            Scene scene = EditorSceneManager.OpenScene(RuinedEntrySceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                AssertRoomGeometry(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        [Test]
        public void PaintStraightWallRun_ReusesOneTileWithoutGapsAtThreeScales()
        {
            GameObject wallObject = new GameObject("WallRunTest", typeof(Tilemap), typeof(TilemapRenderer));
            Tile tile = ScriptableObject.CreateInstance<Tile>();
            try
            {
                Tilemap tilemap = wallObject.GetComponent<Tilemap>();
                foreach (int count in new[] { 3, 10, 100 })
                {
                    tilemap.ClearAllTiles();
                    RuinedEntrySceneBuilder.PaintStraightWallRun(tilemap, tile, 0, count);
                    int first = -count / 2;
                    for (int index = 0; index < count; index++)
                    {
                        Assert.AreSame(tile, tilemap.GetTile(new Vector3Int(first + index, 0, 0)));
                    }
                    Assert.AreEqual(count,
                        tilemap.GetTilesBlock(new BoundsInt(first, 0, 0, count, 1, 1))
                            .Count(occupied => occupied != null));
                }
            }
            finally
            {
                Object.DestroyImmediate(tile);
                Object.DestroyImmediate(wallObject);
            }
        }

        [Test]
        public void LowWallTile_UsesSeamlessRepeatAndRepairsStalePersistedPixels()
        {
            string folderName = "__NSC044LowWall_" + Guid.NewGuid().ToString("N");
            string folderPath = "Assets/" + folderName;
            AssetDatabase.CreateFolder("Assets", folderName);
            try
            {
                Tile tile = RuinedEntrySceneBuilder.LoadOrCreateRuinedEntryLowWallTile(folderPath);
                string assetPath = folderPath + "/RuinedEntryLowWallTile.asset";
                string guid = AssetDatabase.AssetPathToGUID(assetPath);
                Assert.IsNotEmpty(guid);
                Assert.AreEqual(Tile.ColliderType.None, tile.colliderType);
                Assert.That(tile.sprite.bounds.size.y, Is.EqualTo(0.5f).Within(0.001f));
                Assert.That(tile.sprite.pixelsPerUnit, Is.EqualTo(64f).Within(0.001f));
                Assert.That(tile.sprite.pivot.x, Is.EqualTo(32f).Within(0.001f));
                Assert.That(tile.sprite.pivot.y, Is.EqualTo(0f).Within(0.001f));

                Texture2D texture = tile.sprite.texture;
                Assert.AreEqual(64, texture.width);
                Assert.AreEqual(32, texture.height);
                Color32[] original = texture.GetPixels32();
                Assert.AreEqual(0, 64 % 32);
                for (int y = 0; y < 32; y++)
                {
                    for (int x = 0; x < 32; x++)
                    {
                        Assert.AreEqual(original[y * 64 + x], original[y * 64 + x + 32],
                            $"Low wall masonry repeat breaks at row {y}, column {x}.");
                    }
                }

                texture.SetPixel(5, 5, Color.red);
                texture.Apply(false, false);
                EditorUtility.SetDirty(texture);
                AssetDatabase.SaveAssetIfDirty(texture);
                Assert.AreNotEqual(original[5 * 64 + 5], texture.GetPixels32()[5 * 64 + 5]);

                Tile repaired = RuinedEntrySceneBuilder.LoadOrCreateRuinedEntryLowWallTile(folderPath);
                Assert.AreSame(tile, repaired);
                Assert.AreEqual(guid, AssetDatabase.AssetPathToGUID(assetPath));
                CollectionAssert.AreEqual(original, repaired.sprite.texture.GetPixels32());
                Sprite correctSprite = repaired.sprite;
                Assert.AreSame(repaired, RuinedEntrySceneBuilder.LoadOrCreateRuinedEntryLowWallTile(folderPath));
                Assert.AreSame(correctSprite, repaired.sprite,
                    "A correct low-wall Sprite should be reused on a repeat build.");
            }
            finally
            {
                AssetDatabase.DeleteAsset(folderPath);
            }
        }

        [Test]
        public void InMemoryBuild_DoesNotWriteLowWallAsset()
        {
            const string assetPath = "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/RuinedEntryLowWallTile.asset";
            bool existed = File.Exists(assetPath);
            byte[] before = existed ? File.ReadAllBytes(assetPath) : null;
            RuinedEntrySceneBuilder.BuildInMemoryForTests();
            Assert.AreEqual(existed, File.Exists(assetPath));
            if (existed) CollectionAssert.AreEqual(before, File.ReadAllBytes(assetPath));
        }

        [Test]
        public void CommittedCatalog_ChangesOnlyRuinedEntryBoundsAndKeepsDoorOrder()
        {
            RoomSceneCatalog catalog = AssetDatabase.LoadAssetAtPath<RoomSceneCatalog>(RoomSceneCatalog.AssetPath);
            Assert.IsNotNull(catalog);
            Assert.AreEqual(5, catalog.Rooms.Count);
            Assert.AreEqual(5, catalog.Doors.Count);
            RoomSceneCatalog.RoomCatalogEntry[] expectedRooms = RoomSceneCatalog.CreateCanonicalRooms();
            RoomSceneCatalog.DoorSequenceEntry[] expectedDoors = RoomSceneCatalog.CreateCanonicalDoors();
            for (int index = 0; index < 5; index++)
            {
                Assert.AreEqual(expectedRooms[index].RoomId, catalog.Rooms[index].RoomId);
                Assert.AreEqual(expectedRooms[index].SceneAssetPath, catalog.Rooms[index].SceneAssetPath);
                Assert.AreEqual(expectedRooms[index].Bounds.MinX, catalog.Rooms[index].Bounds.MinX);
                Assert.AreEqual(expectedRooms[index].Bounds.MaxX, catalog.Rooms[index].Bounds.MaxX);
                Assert.AreEqual(expectedRooms[index].Bounds.MinZ, catalog.Rooms[index].Bounds.MinZ);
                Assert.AreEqual(expectedRooms[index].Bounds.MaxZ, catalog.Rooms[index].Bounds.MaxZ);
                Assert.AreEqual(expectedDoors[index].DoorId, catalog.Doors[index].DoorId);
                Assert.AreEqual(expectedDoors[index].ExitRoom, catalog.Doors[index].ExitRoom);
                Assert.AreEqual(expectedDoors[index].EntryRoom, catalog.Doors[index].EntryRoom);
                Assert.AreEqual(expectedDoors[index].ExpectedGroundCenter,
                    catalog.Doors[index].ExpectedGroundCenter);
                Assert.AreEqual(expectedDoors[index].OpeningWidth, catalog.Doors[index].OpeningWidth);
                Assert.AreEqual(index == 4, catalog.Doors[index].IsFinal);
            }
            Assert.AreEqual(RoomId.RuinedEntry, catalog.Rooms[0].RoomId);
            Assert.AreEqual(-14f, catalog.Rooms[0].Bounds.MinX);
            Assert.AreEqual(14f, catalog.Rooms[0].Bounds.MaxX);
            Assert.AreEqual(-26f, catalog.Rooms[0].Bounds.MinZ);
            Assert.AreEqual(0f, catalog.Rooms[0].Bounds.MaxZ);
            Assert.AreEqual(Vector2.zero, catalog.Doors[0].ExpectedGroundCenter);
            Assert.AreEqual(3f, catalog.Doors[0].OpeningWidth);
        }

        [Test]
        public void InMemoryVisuals_UseIsometricFloorAndIndividuallySortedWallTiles()
        {
            AssertTilemapVisuals(SceneManager.GetActiveScene());
        }

        [Test]
        public void CommittedVisuals_UseIsometricFloorAndIndividuallySortedWallTiles()
        {
            Scene scene = EditorSceneManager.OpenScene(RuinedEntrySceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                AssertTilemapVisuals(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        [Explicit("Requires an external NSC044_CAMERA_REVIEW_OUTPUT directory for Vincent's visual review.")]
        [Test]
        public void CaptureGameplayCameraReview()
        {
            string output = Environment.GetEnvironmentVariable("NSC044_CAMERA_REVIEW_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC044_CAMERA_REVIEW_OUTPUT to run the explicit visual capture.");
            }
            Assert.IsTrue(Path.IsPathRooted(output));
            string outputFull = Path.GetFullPath(output);
            string repository = Path.GetFullPath(Directory.GetCurrentDirectory())
                .TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            Assert.IsFalse(outputFull.TrimEnd(Path.DirectorySeparatorChar)
                    .Equals(repository.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase) ||
                outputFull.StartsWith(repository, StringComparison.OrdinalIgnoreCase),
                "Camera review PNGs must be written outside the repository.");

            string[] names = { "player-start", "west-loop", "east-lane", "d1-staging" };
            Vector3[] positions =
            {
                RuinedEntryLayout.PlayerStart,
                new Vector3(-7f, 0f, -13f),
                new Vector3(10.875f, 0f, -11.75f),
                new Vector3(0f, 0f, -2.75f)
            };
            Directory.CreateDirectory(outputFull);
            foreach (string name in names)
            {
                Assert.IsFalse(File.Exists(Path.Combine(outputFull, name + ".png")),
                    "Use a fresh output directory so earlier visual evidence is preserved.");
            }
            Assert.IsFalse(File.Exists(Path.Combine(outputFull, "contact-sheet.png")));

            Scene source = default;
            Scene temporary = default;
            GameObject wizard = null;
            GameObject cameraObject = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();
            RenderTexture previousActive = RenderTexture.active;
            try
            {
                // SetUp authors an unsaved room. Load the committed source additively, then
                // close the fixture scene before creating the separate unsaved review scene.
                // Unity rejects NewScene(Additive) while another untitled scene remains open.
                Scene fixtureScene = SceneManager.GetActiveScene();
                source = EditorSceneManager.OpenScene(RuinedEntrySceneBuilder.ScenePath, OpenSceneMode.Additive);
                SceneManager.SetActiveScene(source);
                EditorSceneManager.CloseScene(fixtureScene, true);
                temporary = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
                SceneManager.SetActiveScene(temporary);

                Sprite wizardSprite = AssetDatabase.LoadAssetAtPath<Sprite>(
                    "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png");
                Assert.IsNotNull(wizardSprite);
                wizard = new GameObject("NSC044ReviewWizard", typeof(SpriteRenderer));
                wizard.transform.localScale = new Vector3(1f, 2f, 1f);
                SpriteRenderer wizardRenderer = wizard.GetComponent<SpriteRenderer>();
                wizardRenderer.sprite = wizardSprite;
                wizardRenderer.sortingLayerName = "Default";
                wizardRenderer.sortingOrder = 0;

                cameraObject = new GameObject("NSC044ReviewCamera", typeof(Camera), typeof(IsometricCameraFollow));
                Camera camera = cameraObject.GetComponent<Camera>();
                camera.orthographic = true;
                camera.orthographicSize = 8f;
                camera.transparencySortMode = TransparencySortMode.CustomAxis;
                camera.transparencySortAxis = IsometricCameraFollow.IsometricTransparencySortAxis;
                cameraObject.transform.rotation = Quaternion.Euler(30f, -45f, 0f);
                target = new RenderTexture(800, 600, 24);
                target.Create();
                camera.targetTexture = target;

                for (int index = 0; index < names.Length; index++)
                {
                    wizard.transform.position = positions[index];
                    cameraObject.transform.position = positions[index] + new Vector3(10f, 10f, -10f);
                    cameraObject.GetComponent<IsometricCameraFollow>().Initialize(wizard.transform);
                    camera.Render();
                    RenderTexture.active = target;
                    Texture2D shot = new Texture2D(800, 600, TextureFormat.RGBA32, false);
                    shot.ReadPixels(new Rect(0f, 0f, 800f, 600f), 0, 0);
                    shot.Apply(false, false);
                    shots.Add(shot);
                    File.WriteAllBytes(Path.Combine(outputFull, names[index] + ".png"), shot.EncodeToPNG());
                }

                Texture2D contact = new Texture2D(1600, 1200, TextureFormat.RGBA32, false);
                shots.Add(contact);
                for (int index = 0; index < 4; index++)
                {
                    Color32[] pixels = shots[index].GetPixels32();
                    int originX = (index % 2) * 800;
                    int originY = (1 - index / 2) * 600;
                    for (int row = 0; row < 600; row++)
                    {
                        for (int column = 0; column < 800; column++)
                        {
                            contact.SetPixel(originX + column, originY + row, pixels[row * 800 + column]);
                        }
                    }
                }
                contact.Apply(false, false);
                File.WriteAllBytes(Path.Combine(outputFull, "contact-sheet.png"), contact.EncodeToPNG());
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
                if (temporary.IsValid() && temporary.isLoaded) EditorSceneManager.CloseScene(temporary, true);
                if (source.IsValid() && source.isLoaded) EditorSceneManager.CloseScene(source, true);
            }
        }

        [Test]
        public void Build_SeparatesVisibleBlockoutFromGameplayCollision()
        {
            GameObject visible = GameObject.Find("Room_RuinedEntry/Visuals");
            GameObject gameplay = GameObject.Find("Room_RuinedEntry/GameplayGeometry");

            Assert.IsNotNull(visible);
            Assert.IsNotNull(gameplay);
            Assert.Greater(visible.GetComponentsInChildren<Renderer>().Length, 0);
            Assert.AreEqual(0, visible.GetComponentsInChildren<Collider>().Length,
                "Visible room blockout must not own gameplay collision.");
            Assert.Greater(gameplay.GetComponentsInChildren<BoxCollider>().Length, 0);
            Assert.AreEqual(0, gameplay.GetComponentsInChildren<Renderer>().Length,
                "Gameplay geometry must remain independently replaceable from room visuals.");
        }

        [Test]
        public void Build_PreservesDoorOpeningAndApprovedRoutes()
        {
            BoxCollider westDoorWall = FindCollider("Room_RuinedEntry/GameplayGeometry/NorthWallWestCollision");
            BoxCollider eastDoorWall = FindCollider("Room_RuinedEntry/GameplayGeometry/NorthWallEastCollision");

            float westOpeningEdge = westDoorWall.bounds.max.x;
            float eastOpeningEdge = eastDoorWall.bounds.min.x;
            Assert.AreEqual(-1.5f, westOpeningEdge, 0.001f);
            Assert.AreEqual(1.5f, eastOpeningEdge, 0.001f);
            Assert.AreEqual(RuinedEntryLayout.DoorOpeningWidth, eastOpeningEdge - westOpeningEdge, 0.001f);

            Assert.GreaterOrEqual(RuinedEntryLayout.WestRouteWidth, 15.75f);
            Assert.GreaterOrEqual(RuinedEntryLayout.EastRouteWidth, 3.75f);
            Assert.IsFalse(RuinedEntryLayout.DoorStagingBounds.Intersects(RuinedEntryLayout.RubbleABounds));
            Assert.IsFalse(RuinedEntryLayout.DoorStagingBounds.Intersects(RuinedEntryLayout.RubbleBBounds));
        }

        [Test]
        public void Build_LeavesD1ReachableFromBothSidesOfRubble()
        {
            Transform door = GameObject.Find("Room_RuinedEntry/DoorAnchors/D1Opening")?.transform;
            Transform staging = GameObject.Find("Room_RuinedEntry/Authoring/D1StagingArea")?.transform;

            Assert.IsNotNull(door);
            Assert.IsNotNull(staging);
            Assert.AreEqual(new Vector3(0f, 0f, 0f), door.position);
            Assert.AreEqual(new Vector3(0f, 0f, -2.75f), staging.position);
            Assert.Less(RuinedEntryLayout.RubbleABounds.min.x, RuinedEntryLayout.RubbleBBounds.min.x);
            Assert.Greater(RuinedEntryLayout.RubbleABounds.min.x, door.position.x,
                "The west route must remain open from the staging area to D1.");
            Assert.Less(RuinedEntryLayout.RubbleBBounds.max.z, staging.position.z,
                "The rubble must remain south of the final D1 approach.");
        }

        [Test]
        public void Build_CreatesComposerReadyHierarchyAndD1ExitAnchor()
        {
            Scene scene = SceneManager.GetActiveScene();

            AssertComposerReadyScene(scene);
        }

        [Test]
        public void CommittedScene_ValidatesThroughRoomSceneComposer()
        {
            Scene scene = EditorSceneManager.OpenScene(RuinedEntrySceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                AssertComposerReadyScene(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        /// <summary>NSC-044. The rubble blockers are tinted, not left at Unity's default white.</summary>
        /// <remarks>
        /// THE DEFECT THIS EXISTS TO STOP COMING BACK: GameObject.CreatePrimitive keeps Unity's
        /// default material, which is bright white, and nothing in this fixture used to look at
        /// the blockers' appearance. Two white slabs sat in the middle of a grey stone room --
        /// the most visible thing in the composed world -- while every test stayed green.
        /// <para>
        /// THE EXPECTED COLOUR IS WRITTEN OUT HERE ON PURPOSE. It is the Art Director's call,
        /// recorded in C:/nscrev/reports/handoffs/ART-20260924-composed-world-review.md, and it
        /// is NOT read from the builder: asserting against the constant the builder tints with
        /// would agree with itself no matter what colour that constant later became.
        /// </para>
        /// </remarks>
        [Test]
        public void Build_TintsTheRubbleBlockersInsteadOfLeavingThemDefaultWhite()
        {
            AssertRubbleTint(SceneManager.GetActiveScene());
        }

        /// <summary>The tint is in the COMMITTED scene, not merely in what the builder returns.</summary>
        /// <remarks>
        /// A builder that tints correctly proves nothing about the asset that actually ships if
        /// the scene on disk was never rebuilt. This opens the committed scene for the same
        /// reason the composed-scene dressing fixture does: the artifact is the claim.
        /// </remarks>
        [Test]
        public void CommittedScene_RubbleBlockersCarryTheApprovedTint()
        {
            Scene scene = EditorSceneManager.OpenScene(
                RuinedEntrySceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                AssertRubbleTint(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        private static void AssertRubbleTint(Scene scene)
        {
            // The Art Director's recorded colour. See the class remarks: deliberately not read
            // from RuinedEntrySceneBuilder.
            Color32 expected = new Color32(96, 88, 80, 230);

            GameObject root = scene.GetRootGameObjects()
                .Single(candidate => candidate.name == "Room_RuinedEntry");

            foreach (string blockerName in new[] { "RubbleAVisual", "RubbleBVisual" })
            {
                Transform blocker = root.GetComponentsInChildren<Transform>(true)
                    .FirstOrDefault(candidate => candidate.name == blockerName);
                Assert.IsNotNull(blocker, blockerName + " is missing from the room.");

                Renderer renderer = blocker.GetComponent<Renderer>();
                Assert.IsNotNull(renderer, blockerName + " has no Renderer.");
                Assert.IsNotNull(renderer.sharedMaterial,
                    blockerName + " has no material, so it renders in Unity's default white.");

                Color actual = renderer.sharedMaterial.color;
                Color32 actual32 = actual;

                Assert.AreNotEqual(Color.white, actual,
                    blockerName + " is still Unity's default white. That is the original defect: " +
                    "a primitive that was never given a material.");

                // Compared with a tolerance rather than by Color32 equality: the colour makes a
                // byte -> float -> byte round trip through the material, and a one-unit rounding
                // difference would be a flake rather than a finding.
                Assert.AreEqual(expected.r / 255f, actual.r, 1.5f / 255f,
                    blockerName + " red: expected " + expected + " but was " + actual32);
                Assert.AreEqual(expected.g / 255f, actual.g, 1.5f / 255f,
                    blockerName + " green: expected " + expected + " but was " + actual32);
                Assert.AreEqual(expected.b / 255f, actual.b, 1.5f / 255f,
                    blockerName + " blue: expected " + expected + " but was " + actual32);
                Assert.AreEqual(expected.a / 255f, actual.a, 1.5f / 255f,
                    blockerName + " alpha: expected " + expected + " but was " + actual32);

                // THE ALPHA MUST ACTUALLY DO SOMETHING. The Standard shader ignores alpha while
                // its rendering mode is Opaque, so a material carrying alpha 230 can still render
                // fully opaque -- the transparency would be silently dropped and every colour
                // assertion above would still pass. The blocker is meant to read as a placeholder.
                Assert.AreEqual((int)UnityEngine.Rendering.RenderQueue.Transparent,
                    renderer.sharedMaterial.renderQueue,
                    blockerName + " carries alpha " + expected.a + " but renders on the opaque " +
                    "queue, so the transparency is dropped and it reads as finished art.");
            }
        }
        private static void AssertTilemapVisuals(Scene scene)
        {
            GameObject root = scene.GetRootGameObjects().Single(candidate => candidate.name == "Room_RuinedEntry");
            Transform visuals = root.transform.Find("Visuals");
            Transform gridRoot = visuals?.Find("IsometricZAsY");
            Assert.IsNotNull(gridRoot);
            Assert.AreEqual(Vector3.zero, gridRoot.localPosition);
            Assert.AreEqual(Quaternion.identity, gridRoot.localRotation);
            Assert.AreEqual(Vector3.one, gridRoot.localScale);
            Grid grid = gridRoot.GetComponent<Grid>();
            Assert.IsNotNull(grid);
            Assert.AreEqual(new Vector3(1f, 0.5f, 1f), grid.cellSize);
            Assert.AreEqual(1, visuals.GetComponentsInChildren<Grid>().Length);

            Tilemap floor = RequiredTilemap(gridRoot, "FloorTilemap", Quaternion.Euler(-90f, 0f, 0f), -100);
            Tilemap north = RequiredTilemap(gridRoot, "NorthFullWallTilemap", Quaternion.identity, 0);
            Tilemap west = RequiredTilemap(gridRoot, "WestFullWallTilemap", Quaternion.Euler(0f, 90f, 0f), 0);
            Tilemap south = RequiredTilemap(gridRoot, "SouthLowWallTilemap", Quaternion.identity, 0);
            Tilemap east = RequiredTilemap(gridRoot, "EastLowWallTilemap", Quaternion.Euler(0f, 90f, 0f), 0);
            Assert.AreEqual(5, visuals.GetComponentsInChildren<Tilemap>().Length);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<TilemapCollider2D>().Length);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<Collider>().Length);
            Assert.IsNull(visuals.Find("FloorVisual")?.GetComponent<MeshRenderer>());
            Assert.AreEqual(2, visuals.GetComponentsInChildren<MeshRenderer>().Length,
                "Only the two separate rubble placeholder cubes should retain MeshRenderers.");
            Assert.IsNotNull(visuals.Find("RubbleAVisual")?.GetComponent<MeshRenderer>());
            Assert.IsNotNull(visuals.Find("RubbleBVisual")?.GetComponent<MeshRenderer>());

            Assert.That(north.transform.position.z, Is.EqualTo(-0.151f).Within(0.001f));
            Assert.That(south.transform.position.z, Is.EqualTo(-25.849f).Within(0.001f));
            Assert.That(west.transform.position.x, Is.EqualTo(-13.849f).Within(0.001f));
            Assert.That(east.transform.position.x, Is.EqualTo(13.849f).Within(0.001f));

            Tile floorTile = AssetDatabase.LoadAssetAtPath<Tile>(
                "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/FloorTile.asset");
            Tile fullWallTile = AssetDatabase.LoadAssetAtPath<Tile>(
                "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/WallTile.asset");
            Tile lowWallTile = south.GetTile(new Vector3Int(-14, 0, 0)) as Tile;
            Assert.IsNotNull(floorTile);
            Assert.IsNotNull(fullWallTile);
            Assert.IsNotNull(lowWallTile);
            Assert.That(fullWallTile.sprite.bounds.size.y, Is.EqualTo(2.5f).Within(0.001f));
            Assert.That(lowWallTile.sprite.bounds.size.y, Is.EqualTo(0.5f).Within(0.001f));

            if (scene.path == RuinedEntrySceneBuilder.ScenePath)
            {
                Tile persistedLowWall = AssetDatabase.LoadAssetAtPath<Tile>(
                    "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/RuinedEntryLowWallTile.asset");
                Assert.AreSame(persistedLowWall, lowWallTile);
            }

            int floorCount = 0;
            for (int x = -16; x <= 15; x++)
            {
                for (int row = -3; row <= 54; row++)
                {
                    Vector3Int cell = new Vector3Int(x, row, 0);
                    Vector3 center = floor.GetCellCenterWorld(cell);
                    bool shouldPaint = center.x >= -13.75f && center.x <= 13.75f &&
                                       center.z >= -25.75f && center.z <= -0.25f;
                    Assert.AreEqual(shouldPaint, floor.HasTile(cell), $"Floor cell {cell} violates the inner wall face.");
                    if (shouldPaint)
                    {
                        Assert.AreSame(floorTile, floor.GetTile(cell));
                        floorCount++;
                    }
                }
            }
            Assert.Greater(floorCount, 1000);

            AssertWallCells(north, fullWallTile, -14, -3, 2, 13);
            AssertWallCells(west, fullWallTile, 0, 25);
            AssertWallCells(south, lowWallTile, -14, 13);
            AssertWallCells(east, lowWallTile, 0, 25);
            for (int cell = -2; cell <= 1; cell++)
            {
                Assert.IsFalse(north.HasTile(new Vector3Int(cell, 0, 0)), "A north-wall Tile overlaps D1.");
            }

            Transform geometry = root.transform.Find("GameplayGeometry");
            AssertRunMatchesCollider(north, -14, -3,
                RequiredCollider(geometry, "NorthWallWestCollision").bounds, true);
            AssertRunMatchesCollider(north, 2, 13,
                RequiredCollider(geometry, "NorthWallEastCollision").bounds, true);
            AssertRunMatchesCollider(west, 0, 25,
                RequiredCollider(geometry, "WestWallCollision").bounds, false);
            AssertRunMatchesCollider(south, -14, 13,
                RequiredCollider(geometry, "SouthWallCollision").bounds, true);
            AssertRunMatchesCollider(east, 0, 25,
                RequiredCollider(geometry, "EastWallCollision").bounds, false);
        }

        private static Tilemap RequiredTilemap(Transform grid, string name, Quaternion rotation, int sortingOrder)
        {
            Tilemap tilemap = grid.Find(name)?.GetComponent<Tilemap>();
            Assert.IsNotNull(tilemap, $"Expected Visuals/IsometricZAsY/{name}.");
            Assert.That(Quaternion.Angle(tilemap.transform.localRotation, rotation), Is.LessThan(0.001f));
            TilemapRenderer renderer = tilemap.GetComponent<TilemapRenderer>();
            Assert.IsNotNull(renderer);
            Assert.AreEqual(TilemapRenderer.Mode.Individual, renderer.mode);
            // Assert the RELATION, not the value. This constant currently EQUALS "Default",
            // so the literal passed for the wrong reason and would keep passing after NSC-100
            // repoints it, while the room sorted wrongly against every world sprite.
            Assert.AreEqual(
                NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName,
                renderer.sortingLayerName);
            Assert.AreEqual(sortingOrder, renderer.sortingOrder);
            return tilemap;
        }

        private static void AssertWallCells(Tilemap tilemap, TileBase tile, params int[] ranges)
        {
            int expected = 0;
            for (int index = 0; index < ranges.Length; index += 2)
            {
                for (int cell = ranges[index]; cell <= ranges[index + 1]; cell++)
                {
                    Assert.AreSame(tile, tilemap.GetTile(new Vector3Int(cell, 0, 0)));
                    expected++;
                }
            }
            int actual = 0;
            foreach (Vector3Int cell in tilemap.cellBounds.allPositionsWithin)
            {
                if (tilemap.HasTile(cell)) actual++;
            }
            Assert.AreEqual(expected, actual, "The wall contains extra or missing painted cells.");
        }

        private static void AssertRunMatchesCollider(
            Tilemap tilemap, int firstCell, int lastCell, Bounds collider, bool alongX)
        {
            float first = alongX
                ? tilemap.CellToWorld(new Vector3Int(firstCell, 0, 0)).x
                : tilemap.CellToWorld(new Vector3Int(firstCell, 0, 0)).z;
            float last = alongX
                ? tilemap.CellToWorld(new Vector3Int(lastCell, 0, 0)).x
                : tilemap.CellToWorld(new Vector3Int(lastCell, 0, 0)).z;
            float visualMin = Mathf.Min(first, last) - 0.5f;
            float visualMax = Mathf.Max(first, last) + 0.5f;
            float collisionMin = alongX ? collider.min.x : collider.min.z;
            float collisionMax = alongX ? collider.max.x : collider.max.z;
            Assert.LessOrEqual(Mathf.Abs(visualMin - collisionMin), 0.501f);
            Assert.LessOrEqual(Mathf.Abs(visualMax - collisionMax), 0.501f);
            if (tilemap.name == "NorthFullWallTilemap")
            {
                Assert.IsTrue(visualMax <= -1.5f || visualMin >= 1.5f,
                    "North wall sprites must leave the complete D1 clear interval.");
            }
        }

        private static void AssertRoomGeometry(Scene scene)
        {
            GameObject root = scene.GetRootGameObjects().Single(candidate => candidate.name == "Room_RuinedEntry");
            Transform geometry = root.transform.Find("GameplayGeometry");
            Transform authoring = root.transform.Find("Authoring");
            Transform anchors = root.transform.Find("DoorAnchors");
            Assert.IsNotNull(geometry);
            Assert.IsNotNull(authoring);
            Assert.IsNotNull(anchors);

            BoxCollider floor = RequiredCollider(geometry, "FloorCollision");
            Assert.That(floor.bounds.min.x, Is.EqualTo(-14f).Within(0.001f));
            Assert.That(floor.bounds.max.x, Is.EqualTo(14f).Within(0.001f));
            Assert.That(floor.bounds.min.z, Is.EqualTo(-26f).Within(0.001f));
            Assert.That(floor.bounds.max.z, Is.EqualTo(0f).Within(0.001f));

            BoxCollider west = RequiredCollider(geometry, "WestWallCollision");
            BoxCollider east = RequiredCollider(geometry, "EastWallCollision");
            BoxCollider south = RequiredCollider(geometry, "SouthWallCollision");
            BoxCollider northWest = RequiredCollider(geometry, "NorthWallWestCollision");
            BoxCollider northEast = RequiredCollider(geometry, "NorthWallEastCollision");
            foreach (BoxCollider wall in new[] { west, east, south, northWest, northEast })
            {
                Assert.That(wall.bounds.size.y, Is.EqualTo(2.5f).Within(0.001f));
                Assert.That(Mathf.Min(wall.bounds.size.x, wall.bounds.size.z), Is.EqualTo(0.5f).Within(0.001f));
            }
            Assert.That(west.bounds.max.x, Is.EqualTo(-13.75f).Within(0.001f));
            Assert.That(east.bounds.min.x, Is.EqualTo(13.75f).Within(0.001f));
            Assert.That(south.bounds.max.z, Is.EqualTo(-25.75f).Within(0.001f));
            Assert.That(northWest.bounds.min.z, Is.EqualTo(-0.25f).Within(0.001f));
            Assert.That(northWest.bounds.max.x, Is.EqualTo(-1.5f).Within(0.001f));
            Assert.That(northEast.bounds.min.x, Is.EqualTo(1.5f).Within(0.001f));
            Assert.That(northEast.bounds.min.x - northWest.bounds.max.x, Is.EqualTo(3f).Within(0.001f));

            BoxCollider rubbleA = RequiredCollider(geometry, "RubbleACollision");
            BoxCollider rubbleB = RequiredCollider(geometry, "RubbleBCollision");
            AssertXZ(rubbleA.bounds, 2f, 8f, -17f, -10f);
            AssertXZ(rubbleB.bounds, 6f, 10f, -10f, -6f);
            Assert.That(rubbleA.bounds.max.z, Is.EqualTo(rubbleB.bounds.min.z).Within(0.001f));
            Assert.That(rubbleA.bounds.min.x - west.bounds.max.x, Is.EqualTo(15.75f).Within(0.001f));
            Assert.That(east.bounds.min.x - rubbleA.bounds.max.x, Is.EqualTo(5.75f).Within(0.001f));
            Assert.That(east.bounds.min.x - rubbleB.bounds.max.x, Is.EqualTo(3.75f).Within(0.001f));

            Transform d1 = anchors.Find("D1Opening");
            Transform staging = authoring.Find("D1StagingArea");
            Transform playerStart = authoring.Find("PlayerStart");
            Assert.IsNotNull(d1);
            Assert.IsNotNull(staging);
            Assert.IsNotNull(playerStart);
            Assert.AreEqual(Vector3.zero, d1.position);
            Assert.AreEqual(RuinedEntryLayout.DoorStagingBounds.center, staging.position);
            Assert.AreEqual(RuinedEntryLayout.PlayerStart, playerStart.position);
            Assert.IsFalse(playerStart.GetComponents<MonoBehaviour>()
                .Any(component => component.GetType().Name.StartsWith("Player", StringComparison.Ordinal)));

            BoxCollider[] hardGeometry = geometry.GetComponentsInChildren<BoxCollider>()
                .Where(collider => collider != floor).ToArray();
            AssertSegmentFree(hardGeometry, new Vector2(0f, -20f), new Vector2(11.75f, -20f));
            AssertSegmentFree(hardGeometry, new Vector2(11.75f, -20f), new Vector2(11.75f, -4f));
            AssertSegmentFree(hardGeometry, new Vector2(11.75f, -4f), new Vector2(0f, -4f));
            AssertSegmentFree(hardGeometry, new Vector2(0f, -4f), new Vector2(0f, -20f));
            AssertSegmentFree(hardGeometry, new Vector2(-8f, -20f), new Vector2(-8f, -4f));
            AssertSegmentFree(hardGeometry, new Vector2(0f, -20f), new Vector2(0f, -2.75f));
            AssertTopology(west.bounds.max.x, east.bounds.min.x, south.bounds.max.z,
                northWest.bounds.min.z, rubbleA.bounds, rubbleB.bounds);
        }

        private static BoxCollider RequiredCollider(Transform geometry, string name)
        {
            BoxCollider collider = geometry.Find(name)?.GetComponent<BoxCollider>();
            Assert.IsNotNull(collider, $"Expected GameplayGeometry/{name} BoxCollider.");
            return collider;
        }

        private static void AssertXZ(Bounds bounds, float minX, float maxX, float minZ, float maxZ)
        {
            Assert.That(bounds.min.x, Is.EqualTo(minX).Within(0.001f));
            Assert.That(bounds.max.x, Is.EqualTo(maxX).Within(0.001f));
            Assert.That(bounds.min.z, Is.EqualTo(minZ).Within(0.001f));
            Assert.That(bounds.max.z, Is.EqualTo(maxZ).Within(0.001f));
        }

        private static void AssertSegmentFree(BoxCollider[] colliders, Vector2 start, Vector2 end)
        {
            int steps = Mathf.CeilToInt(Vector2.Distance(start, end) / 0.25f);
            for (int index = 0; index <= steps; index++)
            {
                Vector2 point = Vector2.Lerp(start, end, index / (float)steps);
                Assert.IsFalse(colliders.Any(collider => collider.bounds.Contains(new Vector3(point.x, 0.5f, point.y))),
                    $"Hard geometry blocks required segment {start} -> {end} at {point}.");
            }
        }

        private static void AssertTopology(
            float westInner, float eastInner, float southInner, float northInner,
            Bounds rubbleA, Bounds rubbleB)
        {
            const float step = 0.25f;
            const float playerRadius = 1.25f;
            float minX = westInner + playerRadius;
            float maxX = eastInner - playerRadius;
            float minZ = southInner + playerRadius;
            float maxZ = northInner - playerRadius;

            bool IsBlocked(Vector2Int cell, bool eastBlocker, bool westBlocker)
            {
                float x = cell.x * step;
                float z = cell.y * step;
                if (x < minX || x > maxX || z < minZ || z > maxZ) return true;
                if (InsideExpanded(rubbleA, x, z, playerRadius) ||
                    InsideExpanded(rubbleB, x, z, playerRadius)) return true;
                if (eastBlocker && x >= 8f && x <= 13.75f && z >= -12f && z <= -11.5f) return true;
                if (westBlocker && x >= -13.75f && x <= 2f && z >= -12f && z <= -11.5f) return true;
                return false;
            }

            HashSet<Vector2Int> Flood(bool eastBlocker, bool westBlocker)
            {
                Vector2Int start = new Vector2Int(-16, -88); // PlayerStart (-4,-22) on the 0.25 grid.
                Assert.IsFalse(IsBlocked(start, eastBlocker, westBlocker));
                var visited = new HashSet<Vector2Int> { start };
                var queue = new Queue<Vector2Int>();
                queue.Enqueue(start);
                Vector2Int[] directions =
                {
                    Vector2Int.right, Vector2Int.left, Vector2Int.up, Vector2Int.down
                };
                while (queue.Count > 0)
                {
                    Vector2Int current = queue.Dequeue();
                    foreach (Vector2Int direction in directions)
                    {
                        Vector2Int next = current + direction;
                        if (visited.Contains(next) || IsBlocked(next, eastBlocker, westBlocker)) continue;
                        visited.Add(next);
                        queue.Enqueue(next);
                    }
                }
                return visited;
            }

            Vector2Int staging = new Vector2Int(0, -11); // D1 staging center (0,-2.75).
            Assert.IsTrue(Flood(true, false).Contains(staging),
                "The west teaching field must reach D1 with the east return blocked.");
            Assert.IsTrue(Flood(false, true).Contains(staging),
                "The alternate east return must reach D1 with the west route blocked.");

            HashSet<Vector2Int> reachable = Flood(false, false);
            float rubbleMinX = Mathf.Min(rubbleA.min.x, rubbleB.min.x) - playerRadius;
            float rubbleMaxX = Mathf.Max(rubbleA.max.x, rubbleB.max.x) + playerRadius;
            float rubbleMinZ = Mathf.Min(rubbleA.min.z, rubbleB.min.z) - playerRadius;
            float rubbleMaxZ = Mathf.Max(rubbleA.max.z, rubbleB.max.z) + playerRadius;
            Vector2Int[] rays = { Vector2Int.right, Vector2Int.left, Vector2Int.up, Vector2Int.down };
            foreach (Vector2Int cell in reachable)
            {
                float x = cell.x * step;
                float z = cell.y * step;
                if (x < rubbleMinX || x > rubbleMaxX || z < rubbleMinZ || z > rubbleMaxZ) continue;

                int exits = 0;
                foreach (Vector2Int ray in rays)
                {
                    Vector2Int probe = cell;
                    while (true)
                    {
                        probe += ray;
                        float probeX = probe.x * step;
                        float probeZ = probe.y * step;
                        if (probeX < rubbleMinX || probeX > rubbleMaxX ||
                            probeZ < rubbleMinZ || probeZ > rubbleMaxZ)
                        {
                            exits++;
                            break;
                        }
                        if (IsBlocked(probe, false, false)) break;
                    }
                }
                Assert.GreaterOrEqual(exits, 2,
                    $"Rubble creates a dead-end pocket for player center ({x},{z}).");
            }
        }

        private static bool InsideExpanded(Bounds bounds, float x, float z, float radius)
        {
            return x >= bounds.min.x - radius && x <= bounds.max.x + radius &&
                   z >= bounds.min.z - radius && z <= bounds.max.z + radius;
        }

        private static void AssertComposerReadyScene(Scene scene)
        {
            RoomSceneCatalog.RoomCatalogEntry roomEntry = Array.Find(
                RoomSceneCatalog.CreateCanonicalRooms(), entry => entry.RoomId == RoomId.RuinedEntry);
            RoomSceneComposer.RoomValidationResult validation = RoomSceneComposer.ValidateOpenRoomScene(
                RoomId.RuinedEntry, scene, roomEntry, RoomSceneCatalog.CreateCanonicalDoors());

            CollectionAssert.IsEmpty(validation.Errors, string.Join("\n", validation.Errors));
            Assert.IsTrue(validation.IsValid);

            GameObject[] roots = scene.GetRootGameObjects();
            Assert.AreEqual(1, roots.Length);
            GameObject roomRoot = roots[0];
            Assert.AreEqual("Room_RuinedEntry", roomRoot.name);
            Assert.AreEqual(Vector3.zero, roomRoot.transform.localPosition);
            Assert.AreEqual(Quaternion.identity, roomRoot.transform.localRotation);
            Assert.AreEqual(Vector3.one, roomRoot.transform.localScale);
            Assert.AreEqual(4, roomRoot.transform.childCount);

            AssertContentMarker(roomRoot.transform, "Visuals", RoomId.RuinedEntry, RoomContentCategory.Visuals);
            AssertContentMarker(
                roomRoot.transform, "GameplayGeometry", RoomId.RuinedEntry, RoomContentCategory.GameplayGeometry);
            Transform anchors = AssertContentMarker(
                roomRoot.transform, "DoorAnchors", RoomId.RuinedEntry, RoomContentCategory.DoorAnchors);
            AssertContentMarker(roomRoot.transform, "Authoring", RoomId.RuinedEntry, RoomContentCategory.Authoring);

            DoorAnchorMarker anchor = anchors.GetComponentInChildren<DoorAnchorMarker>(true);
            Assert.IsNotNull(anchor);
            Assert.AreEqual(DoorId.D1, anchor.DoorId);
            Assert.AreEqual(DoorAnchorRole.Exit, anchor.Role);
            Assert.AreEqual(3f, anchor.OpeningWidth);
            Assert.AreEqual(new Vector3(0f, 0f, 0f), anchor.transform.position);
            Assert.AreEqual(Vector3.forward, anchor.transform.forward);
        }

        private static Transform AssertContentMarker(
            Transform roomRoot,
            string name,
            RoomId roomId,
            RoomContentCategory category)
        {
            Transform child = roomRoot.Find(name);
            Assert.IsNotNull(child, $"Expected direct child {name}.");
            RoomContentMarker marker = child.GetComponent<RoomContentMarker>();
            Assert.IsNotNull(marker, $"Expected {name} to carry RoomContentMarker.");
            Assert.AreEqual(roomId, marker.RoomId);
            Assert.AreEqual(category, marker.Category);
            return child;
        }

        private static BoxCollider FindCollider(string path)
        {
            GameObject found = GameObject.Find(path);
            Assert.IsNotNull(found, $"Expected {path}.");
            BoxCollider collider = found.GetComponent<BoxCollider>();
            Assert.IsNotNull(collider, $"Expected {path} to carry gameplay collision.");
            return collider;
        }
    }
}
