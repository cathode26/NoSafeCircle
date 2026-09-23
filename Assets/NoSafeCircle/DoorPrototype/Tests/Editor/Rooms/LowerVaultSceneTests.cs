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
    public sealed class LowerVaultSceneTests
    {
        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LowerVaultSceneBuilder.BuildInMemoryForTests();
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [Test] // AC-001: revision-5 shell, D3/D4 openings, and every obstacle footprint size.
        public void Layout_UsesApprovedLowerVaultBlockout()
        {
            Assert.AreEqual(new Vector3(0f, 0f, 65f), LowerVaultLayout.RoomBounds.center);
            Assert.AreEqual(new Vector3(40f, 0f, 22f), LowerVaultLayout.RoomBounds.size);
            Assert.AreEqual(new Vector3(-8f, 0f, 54f), LowerVaultLayout.D3);
            Assert.AreEqual(new Vector3(4f, 0f, 76f), LowerVaultLayout.D4);

            Assert.AreEqual(new Vector3(6f, 2.5f, 5f), LowerVaultLayout.CentralColumnCluster.size);
            Assert.AreEqual(new Vector3(4f, 1.5f, 7f), LowerVaultLayout.WestStoragePile.size);
            Assert.AreEqual(new Vector3(5f, 1.5f, 5f), LowerVaultLayout.EastStoragePile.size);
            Assert.AreEqual(new Vector3(9.75f, 1.5f, 6.25f), LowerVaultLayout.NorthWestStorageBar.size);
            Assert.AreEqual(new Vector3(8.5f, 0.5f, 3f), LowerVaultLayout.HallWestSpan.size);
            Assert.AreEqual(new Vector3(13.5f, 0.5f, 3f), LowerVaultLayout.HallCenterSpan.size);
            Assert.AreEqual(new Vector3(7.75f, 0.5f, 4f), LowerVaultLayout.HallEastSpan.size);

            Assert.AreEqual(new Vector3(5f, 0f, 5f), LowerVaultLayout.D3Apron.size);
            Assert.AreEqual(new Vector3(5f, 0f, 5f), LowerVaultLayout.D4Apron.size);
        }

        [Test] // AC-002: named route widths and corner clearances survive the revised blockout.
        public void Layout_DefinesApprovedRouteWidthsAndCornerClearances()
        {
            Assert.That(
                LowerVaultLayout.CentralColumnCluster.min.x - LowerVaultLayout.WestStoragePile.max.x,
                Is.EqualTo(4f).Within(0.001f), "LV-W1 to LV-C1 lane must stay 4.0 units wide.");
            Assert.That(
                LowerVaultLayout.EastStoragePile.min.x - LowerVaultLayout.CentralColumnCluster.max.x,
                Is.EqualTo(5f).Within(0.001f), "LV-C1 to LV-E1 lane must stay 5.0 units wide.");
            Assert.That(
                LowerVaultLayout.HallCenterSpan.min.z - LowerVaultLayout.CentralColumnCluster.max.z,
                Is.EqualTo(3f).Within(0.001f), "LV-C1 to LV-H1-Center merge must stay 3.0 units.");
            Assert.That(
                LowerVaultLayout.HallEastSpan.min.x - LowerVaultLayout.HallCenterSpan.max.x,
                Is.EqualTo(5f).Within(0.001f), "The single primary crossing must stay 5.0 units wide.");

            Vector2 c1NorthWest = new Vector2(
                LowerVaultLayout.CentralColumnCluster.min.x, LowerVaultLayout.CentralColumnCluster.max.z);
            Vector2 h1WestSouthEast = new Vector2(
                LowerVaultLayout.HallWestSpan.max.x, LowerVaultLayout.HallWestSpan.min.z);
            Assert.That(Vector2.Distance(c1NorthWest, h1WestSouthEast), Is.GreaterThanOrEqualTo(2.999f),
                "LV-C1's north-west corner must stay at least 3.0 units from LV-H1-West's south-east corner.");

            Vector2 e1NorthWest = new Vector2(
                LowerVaultLayout.EastStoragePile.min.x, LowerVaultLayout.EastStoragePile.max.z);
            Vector2 h1CenterSouthEast = new Vector2(
                LowerVaultLayout.HallCenterSpan.max.x, LowerVaultLayout.HallCenterSpan.min.z);
            Assert.That(Vector2.Distance(e1NorthWest, h1CenterSouthEast), Is.EqualTo(3f).Within(0.001f),
                "LV-E1's north-west corner must sit exactly 3.0 units from LV-H1-Center's south-east corner.");

            Assert.That(LowerVaultLayout.D3.z, Is.LessThan(LowerVaultLayout.CentralColumnCluster.min.z));
        }

        [Test] // AC-002/VAL-001: LV-C1 must intersect the straight D3-to-D4 sight line.
        public void Layout_CentralColumnClusterIntersectsD3ToD4SightLine()
        {
            Bounds c1 = LowerVaultLayout.CentralColumnCluster;
            bool intersects = false;
            const int steps = 4000;
            for (int index = 0; index <= steps; index++)
            {
                float t = index / (float)steps;
                float x = Mathf.Lerp(LowerVaultLayout.D3.x, LowerVaultLayout.D4.x, t);
                float z = Mathf.Lerp(LowerVaultLayout.D3.z, LowerVaultLayout.D4.z, t);
                if (x >= c1.min.x && x <= c1.max.x && z >= c1.min.z && z <= c1.max.z)
                {
                    intersects = true;
                    break;
                }
            }
            Assert.IsTrue(intersects, "The straight D3-to-D4 sight line must pass through LV-C1.");
        }

        [Test] // AC-001/AC-002/VAL-001: in-memory blockout matches the approved shell and clearances.
        public void InMemoryGeometry_MatchesApprovedBlockoutAndClearances()
        {
            AssertRoomGeometry(SceneManager.GetActiveScene());
        }

        [Test] // VAL-001: the committed Scene's blockout matches the approved shell and clearances.
        public void CommittedGeometry_MatchesApprovedBlockoutAndClearances()
        {
            Scene scene = EditorSceneManager.OpenScene(LowerVaultSceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                AssertRoomGeometry(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        [Test] // AC-003/AC-004/VAL-002: in-memory visuals use the isometric Grid, wall runs, and proxies.
        public void InMemoryVisuals_UseIsometricFloorAndWallTilemaps()
        {
            AssertTilemapVisuals(SceneManager.GetActiveScene());
        }

        [Test] // VAL-002: the committed Scene's visuals use the isometric Grid, wall runs, and proxies.
        public void CommittedVisuals_UseIsometricFloorAndWallTilemaps()
        {
            Scene scene = EditorSceneManager.OpenScene(LowerVaultSceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                AssertTilemapVisuals(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        [Test] // AC-002/VAL-001: visible dressing carries no collider and gameplay geometry carries no renderer.
        public void Build_SeparatesVaultVisualsFromGameplayGeometry()
        {
            GameObject visible = GameObject.Find("Room_LowerVault/Visuals");
            GameObject gameplay = GameObject.Find("Room_LowerVault/GameplayGeometry");
            Assert.IsNotNull(visible);
            Assert.IsNotNull(gameplay);
            Assert.AreEqual(12, visible.GetComponentsInChildren<Renderer>().Length,
                "Expected 5 wall/floor TilemapRenderers and 7 blockout obstacle proxy SpriteRenderers.");
            Assert.AreEqual(0, visible.GetComponentsInChildren<Collider>().Length);
            Assert.AreEqual(14, gameplay.GetComponentsInChildren<BoxCollider>().Length,
                "Expected floor + 6 wall pieces + 4 named obstacles + 3 LV-H1 spans.");
            Assert.AreEqual(0, gameplay.GetComponentsInChildren<Renderer>().Length);
        }

        [Test] // AC-004: the composer-ready hierarchy and typed D3/D4 anchors exist in-memory.
        public void Build_CreatesComposerReadyHierarchyAndDoorAnchors()
        {
            Scene scene = SceneManager.GetActiveScene();

            AssertComposerReadyScene(scene);
        }

        [Test] // VAL-001/AC-004: the committed Scene validates against RoomSceneComposer with no errors.
        public void CommittedScene_ValidatesThroughRoomSceneComposer()
        {
            Scene scene = EditorSceneManager.OpenScene(LowerVaultSceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                AssertComposerReadyScene(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        [Test] // VAL-001/Unity Testing Policy: opening the committed Scene for validation must not modify it.
        public void CommittedScene_BytesRemainUnchangedAfterValidation()
        {
            string path = LowerVaultSceneBuilder.ScenePath;
            byte[] before = File.ReadAllBytes(path);

            Scene scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Additive);
            RoomSceneCatalog.RoomCatalogEntry roomEntry = RoomSceneCatalog.CreateCanonicalRooms()
                .First(entry => entry.RoomId == RoomId.LowerVault);
            RoomSceneComposer.RoomValidationResult validation = RoomSceneComposer.ValidateOpenRoomScene(
                RoomId.LowerVault, scene, roomEntry, RoomSceneCatalog.CreateCanonicalDoors());
            CollectionAssert.IsEmpty(validation.Errors, string.Join("\n", validation.Errors));
            EditorSceneManager.CloseScene(scene, true);

            byte[] after = File.ReadAllBytes(path);
            CollectionAssert.AreEqual(before, after, "Opening LowerVault.unity for validation must not modify it.");
        }

        [Test] // VAL-001: the D3 apron reaches every named lane, merge, crossing, apron, and pocket sample.
        public void Connectivity_D3ApronReachesAllNamedSamples()
        {
            Scene scene = EditorSceneManager.OpenScene(LowerVaultSceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                GameObject gameplay = RequiredGameplayGeometry(scene);
                HashSet<Vector2> reachable = FloodFillReachableSamples(
                    gameplay, new Vector2(-8f, 57f), null, null);

                Vector2[] required =
                {
                    new Vector2(-6f, 62f),
                    new Vector2(4.5f, 62f),
                    new Vector2(3.5f, 66f),
                    new Vector2(9.5f, 69f),
                    new Vector2(4f, 73f),
                    new Vector2(-16f, 64f),
                    new Vector2(16f, 61f)
                };
                foreach (Vector2 sample in required)
                {
                    Assert.IsTrue(reachable.Contains(sample), $"Expected sample {sample} reachable from the D3 apron.");
                }
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        [Test] // VAL-001: a virtual crossing footprint severs D4 while both storage pockets stay reachable.
        public void Connectivity_VirtualCrossingFootprintSeversD4ButKeepsBothPockets()
        {
            Scene scene = EditorSceneManager.OpenScene(LowerVaultSceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                GameObject gameplay = RequiredGameplayGeometry(scene);
                Bounds virtualFootprint = LowerVaultLayout.BoundsFromRange(7f, 12f, 65.5f, 70.5f, 0f);
                HashSet<Vector2> reachable = FloodFillReachableSamples(
                    gameplay, new Vector2(-8f, 57f), virtualFootprint, null);

                Assert.IsFalse(reachable.Contains(new Vector2(4f, 73f)),
                    "The virtual crossing footprint must sever the D4 apron sample.");
                Assert.IsTrue(reachable.Contains(new Vector2(-16f, 64f)), "The west pocket sample must stay reachable.");
                Assert.IsTrue(reachable.Contains(new Vector2(16f, 61f)), "The east pocket sample must stay reachable.");
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        [Test] // VAL-001: removing only LV-N1 restores a D4 route around the virtual crossing footprint.
        public void Connectivity_RemovingLVN1RestoresD4RouteAroundVirtualFootprint()
        {
            Scene scene = EditorSceneManager.OpenScene(LowerVaultSceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                GameObject gameplay = RequiredGameplayGeometry(scene);
                Bounds virtualFootprint = LowerVaultLayout.BoundsFromRange(7f, 12f, 65.5f, 70.5f, 0f);
                HashSet<Vector2> reachable = FloodFillReachableSamples(
                    gameplay, new Vector2(-8f, 57f), virtualFootprint, "LV-N1Collision");

                Assert.IsTrue(reachable.Contains(new Vector2(4f, 73f)),
                    "Removing LV-N1 must restore a D4 route around the virtual crossing footprint.");
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        [Test] // AC-001: NSC-101's catalog literal and generated asset agree on Lower Vault bounds and D4 center.
        public void CommittedCatalog_RecordsApprovedLowerVaultBoundsAndD4Center()
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
                Assert.AreEqual(expectedDoors[index].ExpectedGroundCenter, catalog.Doors[index].ExpectedGroundCenter);
                Assert.AreEqual(expectedDoors[index].OpeningWidth, catalog.Doors[index].OpeningWidth);
                Assert.AreEqual(index == 4, catalog.Doors[index].IsFinal);
            }

            RoomSceneCatalog.RoomCatalogEntry lowerVault =
                catalog.Rooms.First(entry => entry.RoomId == RoomId.LowerVault);
            Assert.AreEqual(-20f, lowerVault.Bounds.MinX);
            Assert.AreEqual(20f, lowerVault.Bounds.MaxX);
            Assert.AreEqual(54f, lowerVault.Bounds.MinZ);
            Assert.AreEqual(76f, lowerVault.Bounds.MaxZ);

            RoomSceneCatalog.DoorSequenceEntry d4 = catalog.Doors.First(door => door.DoorId == DoorId.D4);
            Assert.AreEqual(new Vector2(4f, 76f), d4.ExpectedGroundCenter);
        }

        [Test] // Unity Testing Policy non-mutation invariant: the in-memory seam never writes generated assets.
        public void InMemoryBuild_DoesNotWriteGeneratedArchitecturalAssets()
        {
            const string nearWallStubPath =
                "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/LowerVaultNearWallStubTile.asset";
            const string proxySpritePath =
                "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/LowerVaultBlockoutProxySprite.asset";

            bool stubExisted = File.Exists(nearWallStubPath);
            bool proxyExisted = File.Exists(proxySpritePath);
            byte[] stubBefore = stubExisted ? File.ReadAllBytes(nearWallStubPath) : null;
            byte[] proxyBefore = proxyExisted ? File.ReadAllBytes(proxySpritePath) : null;

            LowerVaultSceneBuilder.BuildInMemoryForTests();

            Assert.AreEqual(stubExisted, File.Exists(nearWallStubPath));
            Assert.AreEqual(proxyExisted, File.Exists(proxySpritePath));
            if (stubExisted) CollectionAssert.AreEqual(stubBefore, File.ReadAllBytes(nearWallStubPath));
            if (proxyExisted) CollectionAssert.AreEqual(proxyBefore, File.ReadAllBytes(proxySpritePath));
        }

        [Test] // VAL-002: the near-wall stub Tile uses a seamless repeat and repairs stale persisted pixels.
        public void NearWallStubTile_UsesSeamlessRepeatAndRepairsStalePersistedPixels()
        {
            string folderName = "__NSC047NearWallStub_" + Guid.NewGuid().ToString("N");
            string folderPath = "Assets/" + folderName;
            AssetDatabase.CreateFolder("Assets", folderName);
            try
            {
                Tile tile = LowerVaultSceneBuilder.LoadOrCreateNearWallStubTile(folderPath);
                string assetPath = folderPath + "/LowerVaultNearWallStubTile.asset";
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
                            $"Near-wall stub masonry repeat breaks at row {y}, column {x}.");
                    }
                }

                texture.SetPixel(5, 5, Color.red);
                texture.Apply(false, false);
                EditorUtility.SetDirty(texture);
                AssetDatabase.SaveAssetIfDirty(texture);
                Assert.AreNotEqual(original[5 * 64 + 5], texture.GetPixels32()[5 * 64 + 5]);

                Tile repaired = LowerVaultSceneBuilder.LoadOrCreateNearWallStubTile(folderPath);
                Assert.AreSame(tile, repaired);
                Assert.AreEqual(guid, AssetDatabase.AssetPathToGUID(assetPath));
                CollectionAssert.AreEqual(original, repaired.sprite.texture.GetPixels32());
                Sprite correctSprite = repaired.sprite;
                Assert.AreSame(repaired, LowerVaultSceneBuilder.LoadOrCreateNearWallStubTile(folderPath));
                Assert.AreSame(correctSprite, repaired.sprite,
                    "A correct near-wall stub Sprite should be reused on a repeat build.");
            }
            finally
            {
                AssetDatabase.DeleteAsset(folderPath);
            }
        }

        [Test] // VAL-002/AC-004: the blockout proxy Sprite reuses matching pixels and repairs stale pixels.
        public void BlockoutProxySprite_ReplacesStalePixelsAndReusesMatchingPixels()
        {
            string folderName = "__NSC047BlockoutProxy_" + Guid.NewGuid().ToString("N");
            string folderPath = "Assets/" + folderName;
            AssetDatabase.CreateFolder("Assets", folderName);
            try
            {
                Sprite sprite = LowerVaultSceneBuilder.LoadOrCreateBlockoutProxySprite(folderPath);
                string assetPath = folderPath + "/LowerVaultBlockoutProxySprite.asset";
                string guid = AssetDatabase.AssetPathToGUID(assetPath);
                Assert.IsNotEmpty(guid);
                Assert.AreEqual(64, sprite.texture.width);
                Assert.AreEqual(64, sprite.texture.height);
                Assert.That(sprite.pixelsPerUnit, Is.EqualTo(64f).Within(0.001f));
                Assert.That(sprite.pivot.x, Is.EqualTo(32f).Within(0.001f));
                Assert.That(sprite.pivot.y, Is.EqualTo(0f).Within(0.001f));

                Color32[] original = sprite.texture.GetPixels32();

                sprite.texture.SetPixel(5, 5, Color.green);
                sprite.texture.Apply(false, false);
                EditorUtility.SetDirty(sprite.texture);
                AssetDatabase.SaveAssetIfDirty(sprite.texture);
                Assert.AreNotEqual(original[5 * 64 + 5], sprite.texture.GetPixels32()[5 * 64 + 5]);

                Sprite repaired = LowerVaultSceneBuilder.LoadOrCreateBlockoutProxySprite(folderPath);
                Assert.AreSame(sprite, repaired);
                Assert.AreEqual(guid, AssetDatabase.AssetPathToGUID(assetPath));
                CollectionAssert.AreEqual(original, repaired.texture.GetPixels32());

                Assert.AreSame(repaired, LowerVaultSceneBuilder.LoadOrCreateBlockoutProxySprite(folderPath),
                    "A correct proxy Sprite should be reused on a repeat build.");
            }
            finally
            {
                AssetDatabase.DeleteAsset(folderPath);
            }
        }

        [Test] // VAL-002: PaintStraightWallRun paints contiguous cells with one shared Tile at three scales.
        public void PaintStraightWallRun_ReusesOneTileWithoutGapsAtThreeScales()
        {
            GameObject wallObject = new GameObject("LowerVaultWallRunTest", typeof(Tilemap), typeof(TilemapRenderer));
            Tile tile = ScriptableObject.CreateInstance<Tile>();
            try
            {
                Tilemap tilemap = wallObject.GetComponent<Tilemap>();
                foreach (int count in new[] { 3, 10, 100 })
                {
                    tilemap.ClearAllTiles();
                    LowerVaultSceneBuilder.PaintStraightWallRun(tilemap, tile, 0, count);
                    int first = -count / 2;
                    for (int index = 0; index < count; index++)
                    {
                        Assert.AreSame(tile, tilemap.GetTile(new Vector3Int(first + index, 0, 0)));
                    }
                    int painted = 0;
                    foreach (Vector3Int cell in tilemap.cellBounds.allPositionsWithin)
                    {
                        if (tilemap.HasTile(cell)) painted++;
                    }
                    Assert.AreEqual(count, painted);
                }
            }
            finally
            {
                Object.DestroyImmediate(tile);
                Object.DestroyImmediate(wallObject);
            }
        }

        // --------------------------------------------------------------
        // Shared assertion helpers
        // --------------------------------------------------------------

        [Explicit("Requires an external NSC082_CAMERA_REVIEW_OUTPUT directory for the NSC-082 VAL-002 review.")]
        [Test]
        public void CaptureGameplayCameraReview()
        {
            const string dressingPrefabPath =
                "Assets/NoSafeCircle/DoorPrototype/Art/Environment/RoomDressing/LowerVaultDressing.prefab";

            string output = Environment.GetEnvironmentVariable("NSC082_CAMERA_REVIEW_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC082_CAMERA_REVIEW_OUTPUT to run the explicit visual capture.");
            }
            Assert.IsTrue(Path.IsPathRooted(output));
            string outputFull = Path.GetFullPath(output);
            string repository = Path.GetFullPath(Directory.GetCurrentDirectory())
                .TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            Assert.IsFalse(outputFull.TrimEnd(Path.DirectorySeparatorChar)
                    .Equals(repository.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase) ||
                outputFull.StartsWith(repository, StringComparison.OrdinalIgnoreCase),
                "Camera review PNGs must be written outside the repository.");

            string[] names = { "d3-apron", "c1-west-lane", "c1-east-lane", "d4-apron" };
            Vector3[] positions =
            {
                LowerVaultLayout.D3Apron.center,
                new Vector3(-6f, 0f, 62f),
                new Vector3(4.5f, 0f, 62f),
                LowerVaultLayout.D4Apron.center
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
            GameObject dressing = null;
            RenderTexture target = null;
            var shots = new List<Texture2D>();
            RenderTexture previousActive = RenderTexture.active;
            try
            {
                // SetUp authors an unsaved room. Load the committed source additively, then
                // close the fixture scene before creating the separate unsaved review scene.
                // Unity rejects NewScene(Additive) while another untitled scene remains open.
                Scene fixtureScene = SceneManager.GetActiveScene();
                source = EditorSceneManager.OpenScene(LowerVaultSceneBuilder.ScenePath, OpenSceneMode.Additive);
                SceneManager.SetActiveScene(source);
                EditorSceneManager.CloseScene(fixtureScene, true);
                temporary = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
                SceneManager.SetActiveScene(temporary);

                // VAL-002 judges the DRESSING against the committed blockout, and the prefab does
                // not exist until NSC-082 runs. Stage it when present and state which it was: a
                // panel of an undressed room looks exactly like a dressed one to a reviewer who
                // was not told, and that is how a visual gate gets certified on nothing.
                GameObject dressingPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(dressingPrefabPath);
                if (dressingPrefab != null)
                {
                    dressing = (GameObject)PrefabUtility.InstantiatePrefab(dressingPrefab, temporary);
                }
                File.WriteAllText(Path.Combine(outputFull, "dressing-state.txt"),
                    (dressing != null
                        ? "STAGED " + dressingPrefabPath
                        : "ABSENT " + dressingPrefabPath + Environment.NewLine +
                          "These frames show the UNDRESSED committed blockout only.") + Environment.NewLine);

                Sprite wizardSprite = AssetDatabase.LoadAssetAtPath<Sprite>(
                    "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png");
                Assert.IsNotNull(wizardSprite);
                wizard = new GameObject("NSC082ReviewWizard", typeof(SpriteRenderer));
                wizard.transform.localScale = new Vector3(1f, 2f, 1f);
                SpriteRenderer wizardRenderer = wizard.GetComponent<SpriteRenderer>();
                wizardRenderer.sprite = wizardSprite;
                wizardRenderer.sortingLayerName = "Default";
                wizardRenderer.sortingOrder = 0;

                cameraObject = new GameObject("NSC082ReviewCamera", typeof(Camera), typeof(IsometricCameraFollow));
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
                if (dressing != null) Object.DestroyImmediate(dressing);
                if (target != null)
                {
                    target.Release();
                    Object.DestroyImmediate(target);
                }
                if (temporary.IsValid() && temporary.isLoaded) EditorSceneManager.CloseScene(temporary, true);
                if (source.IsValid() && source.isLoaded) EditorSceneManager.CloseScene(source, true);
            }
        }

        private static void AssertRoomGeometry(Scene scene)
        {
            GameObject root = scene.GetRootGameObjects().Single(candidate => candidate.name == "Room_LowerVault");
            Transform geometry = root.transform.Find("GameplayGeometry");
            Transform authoring = root.transform.Find("Authoring");
            Transform anchors = root.transform.Find("DoorAnchors");
            Assert.IsNotNull(geometry);
            Assert.IsNotNull(authoring);
            Assert.IsNotNull(anchors);

            BoxCollider floor = RequiredCollider(geometry, "FloorCollision");
            Assert.That(floor.bounds.min.x, Is.EqualTo(-20f).Within(0.001f));
            Assert.That(floor.bounds.max.x, Is.EqualTo(20f).Within(0.001f));
            Assert.That(floor.bounds.min.z, Is.EqualTo(54f).Within(0.001f));
            Assert.That(floor.bounds.max.z, Is.EqualTo(76f).Within(0.001f));

            BoxCollider west = RequiredCollider(geometry, "WestWallCollision");
            BoxCollider east = RequiredCollider(geometry, "EastWallCollision");
            BoxCollider southWest = RequiredCollider(geometry, "SouthWallWestCollision");
            BoxCollider southEast = RequiredCollider(geometry, "SouthWallEastCollision");
            BoxCollider northWest = RequiredCollider(geometry, "NorthWallWestCollision");
            BoxCollider northEast = RequiredCollider(geometry, "NorthWallEastCollision");
            foreach (BoxCollider wall in new[] { west, east, southWest, southEast, northWest, northEast })
            {
                Assert.That(wall.bounds.size.y, Is.EqualTo(2.5f).Within(0.001f));
                Assert.That(Mathf.Min(wall.bounds.size.x, wall.bounds.size.z), Is.EqualTo(0.5f).Within(0.001f));
                Assert.IsFalse(wall.isTrigger);
            }
            Assert.That(west.bounds.center.x, Is.EqualTo(-20f).Within(0.01f));
            Assert.That(east.bounds.center.x, Is.EqualTo(20f).Within(0.01f));
            Assert.That(southWest.bounds.center.z, Is.EqualTo(54f).Within(0.01f));
            Assert.That(southEast.bounds.center.z, Is.EqualTo(54f).Within(0.01f));
            Assert.That(northWest.bounds.center.z, Is.EqualTo(76f).Within(0.01f));
            Assert.That(northEast.bounds.center.z, Is.EqualTo(76f).Within(0.01f));

            Assert.That(southWest.bounds.max.x, Is.EqualTo(-9.5f).Within(0.001f));
            Assert.That(southEast.bounds.min.x, Is.EqualTo(-6.5f).Within(0.001f));
            Assert.That(southEast.bounds.min.x - southWest.bounds.max.x,
                Is.EqualTo(LowerVaultLayout.DoorWidth).Within(0.001f));
            Assert.That(northWest.bounds.max.x, Is.EqualTo(2.5f).Within(0.001f));
            Assert.That(northEast.bounds.min.x, Is.EqualTo(5.5f).Within(0.001f));
            Assert.That(northEast.bounds.min.x - northWest.bounds.max.x,
                Is.EqualTo(LowerVaultLayout.DoorWidth).Within(0.001f));

            BoxCollider c1 = RequiredCollider(geometry, "LV-C1Collision");
            BoxCollider w1 = RequiredCollider(geometry, "LV-W1Collision");
            BoxCollider e1 = RequiredCollider(geometry, "LV-E1Collision");
            BoxCollider n1 = RequiredCollider(geometry, "LV-N1Collision");
            BoxCollider h1West = RequiredCollider(geometry, "LV-H1-WestCollision");
            BoxCollider h1Center = RequiredCollider(geometry, "LV-H1-CenterCollision");
            BoxCollider h1East = RequiredCollider(geometry, "LV-H1-EastCollision");

            AssertFootprint(c1.bounds, LowerVaultLayout.CentralColumnCluster);
            AssertFootprint(w1.bounds, LowerVaultLayout.WestStoragePile);
            AssertFootprint(e1.bounds, LowerVaultLayout.EastStoragePile);
            AssertFootprint(n1.bounds, LowerVaultLayout.NorthWestStorageBar);
            AssertFootprint(h1West.bounds, LowerVaultLayout.HallWestSpan);
            AssertFootprint(h1Center.bounds, LowerVaultLayout.HallCenterSpan);
            AssertFootprint(h1East.bounds, LowerVaultLayout.HallEastSpan);

            foreach (BoxCollider obstacle in new[] { c1, w1, e1, n1, h1West, h1Center, h1East })
            {
                Assert.IsFalse(obstacle.isTrigger, $"{obstacle.name} must be non-trigger collision.");
                Assert.IsNull(obstacle.GetComponent<Renderer>(), $"{obstacle.name} must not carry a Renderer.");
            }

            BoxCollider[] blockingFootprints = geometry.GetComponentsInChildren<BoxCollider>()
                .Where(collider => collider != floor).ToArray();
            AssertMinimumGap(blockingFootprints);
            AssertApronClear(blockingFootprints, LowerVaultLayout.D3Apron, "D3");
            AssertApronClear(blockingFootprints, LowerVaultLayout.D4Apron, "D4");

            Transform d3 = anchors.Find("D3Opening");
            Transform d4 = anchors.Find("D4Opening");
            Transform d3Staging = authoring.Find("D3StagingArea");
            Transform d4Staging = authoring.Find("D4StagingArea");
            Assert.IsNotNull(d3);
            Assert.IsNotNull(d4);
            Assert.IsNotNull(d3Staging);
            Assert.IsNotNull(d4Staging);
            Assert.AreEqual(LowerVaultLayout.D3, d3.position);
            Assert.AreEqual(LowerVaultLayout.D4, d4.position);
            Assert.AreEqual(LowerVaultLayout.D3Apron.center, d3Staging.position);
            Assert.AreEqual(LowerVaultLayout.D4Apron.center, d4Staging.position);
        }

        private static void AssertFootprint(Bounds actual, Bounds expected)
        {
            Assert.That(actual.min.x, Is.EqualTo(expected.min.x).Within(0.001f));
            Assert.That(actual.max.x, Is.EqualTo(expected.max.x).Within(0.001f));
            Assert.That(actual.min.y, Is.EqualTo(expected.min.y).Within(0.001f));
            Assert.That(actual.max.y, Is.EqualTo(expected.max.y).Within(0.001f));
            Assert.That(actual.min.z, Is.EqualTo(expected.min.z).Within(0.001f));
            Assert.That(actual.max.z, Is.EqualTo(expected.max.z).Within(0.001f));
        }

        // AC-002: apart from touching footprints and the LV-W1/LV-H1-Center corner gap covered by
        // LV-H1-WestCollision, every clear gap between two blocking footprints must be >= 2.5 units.
        private static void AssertMinimumGap(BoxCollider[] colliders)
        {
            for (int i = 0; i < colliders.Length; i++)
            {
                for (int j = i + 1; j < colliders.Length; j++)
                {
                    BoxCollider a = colliders[i];
                    BoxCollider b = colliders[j];
                    bool isNamedException =
                        (a.name == "LV-W1Collision" && b.name == "LV-H1-CenterCollision") ||
                        (a.name == "LV-H1-CenterCollision" && b.name == "LV-W1Collision");
                    if (isNamedException) continue;

                    float gap = GapBetween(a.bounds, b.bounds);
                    if (gap <= 0.001f) continue;
                    Assert.That(gap, Is.GreaterThanOrEqualTo(2.499f),
                        $"{a.name} and {b.name} leave a {gap:F3}-unit gap, narrower than the approved 2.5-unit minimum.");
                }
            }
        }

        private static float GapBetween(Bounds a, Bounds b)
        {
            float dx = Mathf.Max(0f, Mathf.Max(a.min.x - b.max.x, b.min.x - a.max.x));
            float dz = Mathf.Max(0f, Mathf.Max(a.min.z - b.max.z, b.min.z - a.max.z));
            return Mathf.Sqrt(dx * dx + dz * dz);
        }

        private static void AssertApronClear(BoxCollider[] colliders, Bounds apron, string label)
        {
            foreach (BoxCollider collider in colliders)
            {
                bool overlaps = collider.bounds.min.x < apron.max.x && collider.bounds.max.x > apron.min.x &&
                                 collider.bounds.min.z < apron.max.z && collider.bounds.max.z > apron.min.z;
                Assert.IsFalse(overlaps, $"{collider.name} blocks the {label} apron.");
            }
        }

        private static void AssertTilemapVisuals(Scene scene)
        {
            GameObject root = scene.GetRootGameObjects().Single(candidate => candidate.name == "Room_LowerVault");
            Transform visuals = root.transform.Find("Visuals");
            Transform gridRoot = visuals?.Find("IsometricZAsY");
            Assert.IsNotNull(gridRoot);
            Assert.AreEqual(Vector3.zero, gridRoot.localPosition);
            Assert.AreEqual(Quaternion.identity, gridRoot.localRotation);
            Assert.AreEqual(Vector3.one, gridRoot.localScale);
            Grid grid = gridRoot.GetComponent<Grid>();
            Assert.IsNotNull(grid);
            Assert.AreEqual(new Vector3(1f, 0.5f, 1f), grid.cellSize);
            Assert.AreEqual(GridLayout.CellLayout.Rectangle, grid.cellLayout);
            Assert.AreEqual(1, visuals.GetComponentsInChildren<Grid>().Length);

            Tilemap floor = RequiredTilemap(gridRoot, "FloorTilemap", Quaternion.Euler(-90f, 0f, 0f), -100);
            Tilemap north = RequiredTilemap(gridRoot, "NorthFullWallTilemap", Quaternion.identity, 0);
            Tilemap west = RequiredTilemap(gridRoot, "WestFullWallTilemap", Quaternion.Euler(0f, 90f, 0f), 0);
            Tilemap south = RequiredTilemap(gridRoot, "SouthLowWallTilemap", Quaternion.identity, 0);
            Tilemap east = RequiredTilemap(gridRoot, "EastLowWallTilemap", Quaternion.Euler(0f, 90f, 0f), 0);
            Assert.AreEqual(5, visuals.GetComponentsInChildren<Tilemap>().Length);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<TilemapCollider2D>().Length);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<Collider>().Length);

            // Durable form (survives an internal sorting-layer constant repoint): every Lower Vault
            // wall/floor Tilemap and every proxy SpriteRenderer must share one sorting layer.
            string sharedSortingLayer = floor.GetComponent<TilemapRenderer>().sortingLayerName;
            foreach (Tilemap tilemap in new[] { north, west, south, east })
            {
                Assert.AreEqual(sharedSortingLayer, tilemap.GetComponent<TilemapRenderer>().sortingLayerName,
                    "Every Lower Vault wall Tilemap must share the floor's sorting layer.");
            }

            Assert.AreEqual(new Vector3(0f, 0.01f, 0f), floor.transform.localPosition);
            Assert.That(north.transform.localPosition.x, Is.EqualTo(0.5f).Within(0.001f));
            Assert.That(north.transform.localPosition.z, Is.EqualTo(75.849f).Within(0.001f));
            Assert.That(south.transform.localPosition.x, Is.EqualTo(0.5f).Within(0.001f));
            Assert.That(south.transform.localPosition.z, Is.EqualTo(54.151f).Within(0.001f));
            Assert.That(west.transform.localPosition.x, Is.EqualTo(-19.849f).Within(0.001f));
            Assert.That(east.transform.localPosition.x, Is.EqualTo(19.849f).Within(0.001f));

            Tile floorTile = AssetDatabase.LoadAssetAtPath<Tile>(
                "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/FloorTile.asset");
            Tile fullWallTile = AssetDatabase.LoadAssetAtPath<Tile>(
                "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/WallTile.asset");
            Tile nearWallStubTile = south.GetTile(new Vector3Int(-20, 0, 0)) as Tile;
            Assert.IsNotNull(floorTile);
            Assert.IsNotNull(fullWallTile);
            Assert.IsNotNull(nearWallStubTile);
            Assert.That(fullWallTile.sprite.bounds.size.y, Is.EqualTo(2.5f).Within(0.001f));
            Assert.That(nearWallStubTile.sprite.bounds.size.y, Is.EqualTo(0.5f).Within(0.001f));

            if (scene.path == LowerVaultSceneBuilder.ScenePath)
            {
                Tile persisted = AssetDatabase.LoadAssetAtPath<Tile>(
                    "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/LowerVaultNearWallStubTile.asset");
                Assert.AreSame(persisted, nearWallStubTile);
            }

            AssertFloorPainted(floor, floorTile);

            AssertWallCells(north, fullWallTile, -20, 1, 6, 19);
            AssertWallCells(west, fullWallTile, -76, -55);
            AssertWallCells(south, nearWallStubTile, -20, -11, -6, 19);
            AssertWallCells(east, nearWallStubTile, -76, -55);

            for (int cell = -10; cell <= -7; cell++)
            {
                Assert.IsFalse(south.HasTile(new Vector3Int(cell, 0, 0)),
                    "A south-wall Tile overlaps the D3 clear interval.");
            }
            for (int cell = 2; cell <= 5; cell++)
            {
                Assert.IsFalse(north.HasTile(new Vector3Int(cell, 0, 0)),
                    "A north-wall Tile overlaps the D4 clear interval.");
            }

            foreach (Vector3Int cell in south.cellBounds.allPositionsWithin)
            {
                if (south.HasTile(cell))
                {
                    Assert.AreNotSame(fullWallTile, south.GetTile(cell),
                        $"South wall cell {cell} must not carry a full-height WallTile jamb beside D3.");
                }
            }

            // AC-003: each cell's pivot sits at world X k+0.5 (sprite spans X[k,k+1]), so the north
            // wall's cells split exactly at X -15 and X +15 with no single sprite straddling them.
            Assert.That(north.CellToWorld(new Vector3Int(-16, 0, 0)).x, Is.EqualTo(-15.5f).Within(0.001f));
            Assert.That(north.CellToWorld(new Vector3Int(-15, 0, 0)).x, Is.EqualTo(-14.5f).Within(0.001f));
            Assert.That(north.CellToWorld(new Vector3Int(14, 0, 0)).x, Is.EqualTo(14.5f).Within(0.001f));
            Assert.That(north.CellToWorld(new Vector3Int(15, 0, 0)).x, Is.EqualTo(15.5f).Within(0.001f));

            Transform geometry = root.transform.Find("GameplayGeometry");
            AssertRunMatchesCollider(north, -20, 1, RequiredCollider(geometry, "NorthWallWestCollision").bounds, true);
            AssertRunMatchesCollider(north, 6, 19, RequiredCollider(geometry, "NorthWallEastCollision").bounds, true);
            AssertRunMatchesCollider(west, -76, -55, RequiredCollider(geometry, "WestWallCollision").bounds, false);
            AssertRunMatchesCollider(south, -20, -11, RequiredCollider(geometry, "SouthWallWestCollision").bounds, true);
            AssertRunMatchesCollider(south, -6, 19, RequiredCollider(geometry, "SouthWallEastCollision").bounds, true);
            AssertRunMatchesCollider(east, -76, -55, RequiredCollider(geometry, "EastWallCollision").bounds, false);

            // AC-004: collider-free blockout obstacle proxies for LV-C1/W1/E1/N1 and each LV-H1 span.
            Transform proxies = visuals.Find("BlockoutObstacleProxies");
            Assert.IsNotNull(proxies);
            Assert.AreEqual(0, proxies.GetComponentsInChildren<Collider>().Length);
            string[] proxyNames =
            {
                "LV-C1Proxy", "LV-W1Proxy", "LV-E1Proxy", "LV-N1Proxy",
                "LV-H1-WestProxy", "LV-H1-CenterProxy", "LV-H1-EastProxy"
            };
            Assert.AreEqual(proxyNames.Length, proxies.GetComponentsInChildren<SpriteRenderer>().Length);
            foreach (string proxyName in proxyNames)
            {
                Transform proxy = proxies.Find(proxyName);
                Assert.IsNotNull(proxy, $"Expected proxy {proxyName}.");
                SpriteRenderer renderer = proxy.GetComponent<SpriteRenderer>();
                Assert.IsNotNull(renderer);
                Assert.AreEqual(0, renderer.sortingOrder);
                Assert.IsNotNull(renderer.sprite);
                Assert.AreEqual(sharedSortingLayer, renderer.sortingLayerName,
                    "Every blockout obstacle proxy must share the Tilemap sorting layer.");
            }
            Assert.That(proxies.Find("LV-C1Proxy").localScale.y, Is.EqualTo(2.5f).Within(0.001f),
                "The LV-C1 proxy must show its 2.5-unit height.");
        }

        // Mirrors production PaintFloor: paints FloorTile in every cell whose GetCellCenterWorld
        // lies inside the wall-collider inner faces, independent of the production loop range.
        private static void AssertFloorPainted(Tilemap floor, Tile floorTile)
        {
            float innerMinX = LowerVaultLayout.MinimumX + LowerVaultLayout.WallThickness * 0.5f;
            float innerMaxX = LowerVaultLayout.MaximumX - LowerVaultLayout.WallThickness * 0.5f;
            float innerMinZ = LowerVaultLayout.MinimumZ + LowerVaultLayout.WallThickness * 0.5f;
            float innerMaxZ = LowerVaultLayout.MaximumZ - LowerVaultLayout.WallThickness * 0.5f;

            Vector3Int cornerA = floor.WorldToCell(new Vector3(LowerVaultLayout.MinimumX, 0f, LowerVaultLayout.MinimumZ));
            Vector3Int cornerB = floor.WorldToCell(new Vector3(LowerVaultLayout.MaximumX, 0f, LowerVaultLayout.MaximumZ));
            Vector3Int cornerC = floor.WorldToCell(new Vector3(LowerVaultLayout.MinimumX, 0f, LowerVaultLayout.MaximumZ));
            Vector3Int cornerD = floor.WorldToCell(new Vector3(LowerVaultLayout.MaximumX, 0f, LowerVaultLayout.MinimumZ));
            int minCellX = Mathf.Min(Mathf.Min(cornerA.x, cornerB.x), Mathf.Min(cornerC.x, cornerD.x)) - 1;
            int maxCellX = Mathf.Max(Mathf.Max(cornerA.x, cornerB.x), Mathf.Max(cornerC.x, cornerD.x)) + 1;
            int minCellY = Mathf.Min(Mathf.Min(cornerA.y, cornerB.y), Mathf.Min(cornerC.y, cornerD.y)) - 1;
            int maxCellY = Mathf.Max(Mathf.Max(cornerA.y, cornerB.y), Mathf.Max(cornerC.y, cornerD.y)) + 1;

            int floorCount = 0;
            for (int x = minCellX; x <= maxCellX; x++)
            {
                for (int y = minCellY; y <= maxCellY; y++)
                {
                    Vector3Int cell = new Vector3Int(x, y, 0);
                    Vector3 center = floor.GetCellCenterWorld(cell);
                    bool shouldPaint = center.x >= innerMinX && center.x <= innerMaxX &&
                                       center.z >= innerMinZ && center.z <= innerMaxZ;
                    Assert.AreEqual(shouldPaint, floor.HasTile(cell), $"Floor cell {cell} violates the inner wall face.");
                    if (shouldPaint)
                    {
                        Assert.AreSame(floorTile, floor.GetTile(cell));
                        floorCount++;
                    }
                }
            }
            Assert.Greater(floorCount, 800);
        }

        private static Tilemap RequiredTilemap(Transform grid, string name, Quaternion rotation, int sortingOrder)
        {
            Tilemap tilemap = grid.Find(name)?.GetComponent<Tilemap>();
            Assert.IsNotNull(tilemap, $"Expected Visuals/IsometricZAsY/{name}.");
            Assert.That(Quaternion.Angle(tilemap.transform.localRotation, rotation), Is.LessThan(0.001f));
            Assert.AreEqual(Vector3.zero, tilemap.tileAnchor);
            Assert.AreEqual(Tilemap.Orientation.XY, tilemap.orientation);
            TilemapRenderer renderer = tilemap.GetComponent<TilemapRenderer>();
            Assert.IsNotNull(renderer);
            Assert.AreEqual(TilemapRenderer.Mode.Individual, renderer.mode);
            Assert.AreEqual(TilemapRenderer.SortOrder.TopRight, renderer.sortOrder);
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
        }

        private static void AssertComposerReadyScene(Scene scene)
        {
            RoomSceneCatalog.RoomCatalogEntry roomEntry = Array.Find(
                RoomSceneCatalog.CreateCanonicalRooms(), entry => entry.RoomId == RoomId.LowerVault);
            RoomSceneComposer.RoomValidationResult validation = RoomSceneComposer.ValidateOpenRoomScene(
                RoomId.LowerVault, scene, roomEntry, RoomSceneCatalog.CreateCanonicalDoors());

            CollectionAssert.IsEmpty(validation.Errors, string.Join("\n", validation.Errors));
            Assert.IsTrue(validation.IsValid);

            GameObject[] roots = scene.GetRootGameObjects();
            Assert.AreEqual(1, roots.Length);
            GameObject roomRoot = roots[0];
            Assert.AreEqual("Room_LowerVault", roomRoot.name);
            Assert.AreEqual(Vector3.zero, roomRoot.transform.localPosition);
            Assert.AreEqual(Quaternion.identity, roomRoot.transform.localRotation);
            Assert.AreEqual(Vector3.one, roomRoot.transform.localScale);
            Assert.AreEqual(4, roomRoot.transform.childCount);

            AssertContentMarker(roomRoot.transform, "Visuals", RoomId.LowerVault, RoomContentCategory.Visuals);
            AssertContentMarker(
                roomRoot.transform, "GameplayGeometry", RoomId.LowerVault, RoomContentCategory.GameplayGeometry);
            Transform anchors = AssertContentMarker(
                roomRoot.transform, "DoorAnchors", RoomId.LowerVault, RoomContentCategory.DoorAnchors);
            AssertContentMarker(roomRoot.transform, "Authoring", RoomId.LowerVault, RoomContentCategory.Authoring);

            DoorAnchorMarker[] doorAnchors = anchors.GetComponentsInChildren<DoorAnchorMarker>(true);
            Assert.AreEqual(2, doorAnchors.Length);
            AssertDoorAnchor(doorAnchors, DoorId.D3, DoorAnchorRole.Entry, LowerVaultLayout.D3, Vector3.back);
            AssertDoorAnchor(doorAnchors, DoorId.D4, DoorAnchorRole.Exit, LowerVaultLayout.D4, Vector3.forward);
        }

        private static Transform AssertContentMarker(
            Transform roomRoot,
            string name,
            RoomId roomId,
            RoomContentCategory category)
        {
            Transform child = roomRoot.Find(name);
            Assert.IsNotNull(child, "Expected direct child " + name + ".");
            RoomContentMarker marker = child.GetComponent<RoomContentMarker>();
            Assert.IsNotNull(marker, "Expected " + name + " to carry RoomContentMarker.");
            Assert.AreEqual(roomId, marker.RoomId);
            Assert.AreEqual(category, marker.Category);
            return child;
        }

        private static void AssertDoorAnchor(
            DoorAnchorMarker[] anchors,
            DoorId doorId,
            DoorAnchorRole role,
            Vector3 position,
            Vector3 forward)
        {
            DoorAnchorMarker anchor = Array.Find(anchors, candidate => candidate.DoorId == doorId);
            Assert.IsNotNull(anchor, "Expected " + doorId + " anchor.");
            Assert.AreEqual(RoomId.LowerVault, anchor.RoomId);
            Assert.AreEqual(role, anchor.Role);
            Assert.AreEqual(LowerVaultLayout.DoorWidth, anchor.OpeningWidth);
            Assert.AreEqual(position, anchor.transform.position);
            Assert.Greater(Vector3.Dot(forward, anchor.transform.forward), 0.999f);
        }

        private static GameObject RequiredGameplayGeometry(Scene scene)
        {
            GameObject root = scene.GetRootGameObjects().Single(candidate => candidate.name == "Room_LowerVault");
            Transform geometry = root.transform.Find("GameplayGeometry");
            Assert.IsNotNull(geometry);
            return geometry.gameObject;
        }

        private static BoxCollider RequiredCollider(Transform geometry, string name)
        {
            BoxCollider collider = geometry.Find(name)?.GetComponent<BoxCollider>();
            Assert.IsNotNull(collider, "Expected GameplayGeometry/" + name + " BoxCollider.");
            return collider;
        }

        // VAL-001: projects every non-floor BoxCollider footprint (plus an optional virtual one, minus
        // an optional excluded name) onto X/Z, inflates each by 1.45 units, and flood-fills 0.5-unit
        // samples from start, treating a sample as blocked only when it lies strictly inside a footprint.
        private static HashSet<Vector2> FloodFillReachableSamples(
            GameObject gameplayGeometry, Vector2 start, Bounds? extraFootprint, string excludedColliderName)
        {
            var inflated = new List<Rect>();
            foreach (BoxCollider collider in gameplayGeometry.GetComponentsInChildren<BoxCollider>(true))
            {
                if (collider.name == "FloorCollision") continue;
                if (excludedColliderName != null && collider.name == excludedColliderName) continue;
                Bounds b = collider.bounds;
                inflated.Add(Rect.MinMaxRect(b.min.x - 1.45f, b.min.z - 1.45f, b.max.x + 1.45f, b.max.z + 1.45f));
            }
            if (extraFootprint.HasValue)
            {
                Bounds b = extraFootprint.Value;
                inflated.Add(Rect.MinMaxRect(b.min.x - 1.45f, b.min.z - 1.45f, b.max.x + 1.45f, b.max.z + 1.45f));
            }

            bool IsBlocked(Vector2 point)
            {
                foreach (Rect rect in inflated)
                {
                    if (point.x > rect.xMin && point.x < rect.xMax && point.y > rect.yMin && point.y < rect.yMax)
                    {
                        return true;
                    }
                }
                return false;
            }

            var visited = new HashSet<Vector2> { start };
            var queue = new Queue<Vector2>();
            queue.Enqueue(start);
            Vector2[] directions = { Vector2.right, Vector2.left, Vector2.up, Vector2.down };
            while (queue.Count > 0)
            {
                Vector2 current = queue.Dequeue();
                foreach (Vector2 direction in directions)
                {
                    Vector2 next = current + direction * 0.5f;
                    if (next.x < LowerVaultLayout.MinimumX || next.x > LowerVaultLayout.MaximumX ||
                        next.y < LowerVaultLayout.MinimumZ || next.y > LowerVaultLayout.MaximumZ)
                    {
                        continue;
                    }
                    if (visited.Contains(next) || IsBlocked(next)) continue;
                    visited.Add(next);
                    queue.Enqueue(next);
                }
            }
            return visited;
        }
    }
}
