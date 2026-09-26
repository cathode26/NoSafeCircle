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

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    // NSC-048 VAL-001/VAL-002: focused Edit Mode tests for the Final Room layout, its Tilemap
    // visuals, and its independently authored gameplay collision. AC-006's exhaustive cross-room
    // catalog comparison is owned by NSC-101's RoomSceneCatalogGeometryTests.cs; the room-specific
    // check here only fails if FinalRoom's own catalog entry stops matching this room's authoring.
    public sealed class FinalRoomSceneTests
    {
        private static readonly HashSet<string> PerimeterWallColliderNames = new HashSet<string>
        {
            "WestWallCollision", "EastWallCollision",
            "SouthWallWestCollision", "SouthWallEastCollision",
            "NorthWallWestCollision", "NorthWallEastCollision"
        };

        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            FinalRoomSceneBuilder.BuildInMemoryForTests();
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        // AC-001: approved shell, both doors, and FR-1's revised X[-3.5,3.5] Z[87,94] footprint.
        [Test]
        public void Layout_UsesApprovedShellDoorsAndCentralObstacle()
        {
            Assert.AreEqual(new Vector3(-15f, 0f, 76f), FinalRoomLayout.RoomBounds.min);
            Assert.AreEqual(new Vector3(15f, 0f, 104f), FinalRoomLayout.RoomBounds.max);
            Assert.AreEqual(new Vector3(4f, 0f, 76f), FinalRoomLayout.D4);
            Assert.AreEqual(new Vector3(0f, 0f, 104f), FinalRoomLayout.D5);
            Assert.AreEqual(3f, FinalRoomLayout.DoorOpeningWidth);

            Assert.AreEqual(new Vector3(-3.5f, 0f, 87f), FinalRoomLayout.FR1Bounds.min);
            Assert.AreEqual(new Vector3(3.5f, 2f, 94f), FinalRoomLayout.FR1Bounds.max);

            // A separate constant from any rendered wall height so the visual cutaway scale
            // cannot silently change gameplay collision.
            Assert.AreEqual(2.5f, FinalRoomLayout.GameplayWallColliderHeight);
        }

        // AC-002: the published NSC-083 handoff Bounds, including the hazard frame's isolation
        // from RoomBounds, every catalog room, and D4.
        [Test]
        public void Layout_PublishesNSC083HandoffBoundsAndIsolatesHazardFrame()
        {
            Assert.AreEqual(new Vector3(-8f, 0f, 98f), FinalRoomLayout.D5StagingBounds.min);
            Assert.AreEqual(new Vector3(8f, 0f, 103f), FinalRoomLayout.D5StagingBounds.max);

            Assert.AreEqual(new Vector3(-14.75f, 0f, 79f), FinalRoomLayout.WestSupportClusterBounds.min);
            Assert.AreEqual(new Vector3(-10f, 0f, 84f), FinalRoomLayout.WestSupportClusterBounds.max);
            Assert.AreEqual(new Vector3(10f, 0f, 93f), FinalRoomLayout.EastSupportClusterBounds.min);
            Assert.AreEqual(new Vector3(14.75f, 0f, 98f), FinalRoomLayout.EastSupportClusterBounds.max);

            Assert.AreEqual(new Vector3(-10f, 0f, 85.25f), FinalRoomLayout.WestProtectedFlankBounds.min);
            Assert.AreEqual(new Vector3(-5.25f, 0f, 95.75f), FinalRoomLayout.WestProtectedFlankBounds.max);
            Assert.AreEqual(new Vector3(5.25f, 0f, 85.25f), FinalRoomLayout.EastProtectedFlankBounds.min);
            Assert.AreEqual(new Vector3(10f, 0f, 95.75f), FinalRoomLayout.EastProtectedFlankBounds.max);

            Bounds hazard = FinalRoomLayout.EastExteriorHazardFrameBounds;
            Assert.AreEqual(new Vector3(15.25f, 0f, 84f), hazard.min);
            Assert.AreEqual(new Vector3(17.25f, 0f, 96f), hazard.max);
            Assert.IsFalse(hazard.Intersects(FinalRoomLayout.RoomBounds));
            Assert.Greater(hazard.min.z, FinalRoomLayout.D4Z, "The hazard frame must not cross D4.");

            foreach (RoomSceneCatalog.RoomCatalogEntry room in RoomSceneCatalog.CreateCanonicalRooms())
            {
                bool overlapsX = hazard.min.x < room.Bounds.MaxX && hazard.max.x > room.Bounds.MinX;
                bool overlapsZ = hazard.min.z < room.Bounds.MaxZ && hazard.max.z > room.Bounds.MinZ;
                Assert.IsFalse(overlapsX && overlapsZ,
                    $"The hazard frame must stay outside {room.RoomId}'s catalog bounds.");
            }

            GameObject geometry = GameObject.Find("Room_FinalRoom/GameplayGeometry");
            foreach (BoxCollider collider in geometry.GetComponentsInChildren<BoxCollider>())
            {
                // Bounds.Intersects is inclusive, so a collider whose face is FLUSH with the
                // hazard frame counts as intersecting it. AC-002 fixes the frame at X [15.25,17.25]
                // and AC-004's east wall collider is WallThickness (0.5) wide centred on
                // MaximumX (15), putting its outer face at exactly 15.25 - so a contract-conformant
                // room can NEVER satisfy the inclusive form. Use the same strict-overlap test this
                // file already applies to the catalog bounds above: shared surface, no shared volume.
                Assert.IsFalse(SharesGroundVolume(collider.bounds, hazard),
                    $"'{collider.name}' must not give the hazard frame a gameplay collider.");
            }
        }

        // AC-006: this room's own catalog entry only; the full cross-room comparison belongs to
        // NSC-101's RoomSceneCatalogGeometryTests.cs.
        [Test]
        public void Layout_MatchesCanonicalCatalogEntryForFinalRoom()
        {
            RoomSceneCatalog.RoomCatalogEntry[] rooms = RoomSceneCatalog.CreateCanonicalRooms();
            Assert.AreEqual(5, rooms.Length);
            RoomSceneCatalog.RoomCatalogEntry finalRoom = rooms[4];
            Assert.AreEqual(RoomId.FinalRoom, finalRoom.RoomId);
            Assert.AreEqual(FinalRoomSceneBuilder.ScenePath, finalRoom.SceneAssetPath);
            Assert.AreEqual(FinalRoomLayout.MinimumX, finalRoom.Bounds.MinX);
            Assert.AreEqual(FinalRoomLayout.MaximumX, finalRoom.Bounds.MaxX);
            Assert.AreEqual(FinalRoomLayout.MinimumZ, finalRoom.Bounds.MinZ);
            Assert.AreEqual(FinalRoomLayout.MaximumZ, finalRoom.Bounds.MaxZ);

            RoomSceneCatalog.DoorSequenceEntry[] doors = RoomSceneCatalog.CreateCanonicalDoors();
            Assert.AreEqual(5, doors.Length);
            RoomSceneCatalog.DoorSequenceEntry d4 = doors[3];
            Assert.AreEqual(DoorId.D4, d4.DoorId);
            Assert.AreEqual(RoomId.LowerVault, d4.ExitRoom);
            Assert.AreEqual(RoomId.FinalRoom, d4.EntryRoom);
            Assert.IsFalse(d4.IsFinal);
            Assert.AreEqual(new Vector2(FinalRoomLayout.D4X, FinalRoomLayout.D4Z), d4.ExpectedGroundCenter);
            Assert.AreEqual(FinalRoomLayout.DoorOpeningWidth, d4.OpeningWidth);

            RoomSceneCatalog.DoorSequenceEntry d5 = doors[4];
            Assert.AreEqual(DoorId.D5, d5.DoorId);
            Assert.AreEqual(RoomId.FinalRoom, d5.ExitRoom);
            Assert.IsTrue(d5.IsFinal);
            Assert.AreEqual(new Vector2(FinalRoomLayout.D5X, FinalRoomLayout.D5Z), d5.ExpectedGroundCenter);
            Assert.AreEqual(FinalRoomLayout.DoorOpeningWidth, d5.OpeningWidth);
            Assert.AreEqual(1, doors.Count(door => door.IsFinal), "D5 must remain the only final door.");
        }

        // VAL-002: representative 3-, 10- and 100-cell calls, including an even count.
        [Test]
        public void PaintStraightWallRun_ReusesOneTileWithoutGapsAtThreeScales()
        {
            GameObject wallObject = new GameObject("FinalRoomWallRunTest", typeof(Tilemap), typeof(TilemapRenderer));
            Tile tile = ScriptableObject.CreateInstance<Tile>();
            try
            {
                Tilemap tilemap = wallObject.GetComponent<Tilemap>();
                foreach (int count in new[] { 3, 10, 100 })
                {
                    tilemap.ClearAllTiles();
                    FinalRoomSceneBuilder.PaintStraightWallRun(tilemap, tile, 0, count);
                    int first = -count / 2;
                    int painted = 0;
                    for (int index = 0; index < count; index++)
                    {
                        Assert.AreSame(tile, tilemap.GetTile(new Vector3Int(first + index, 0, 0)));
                    }
                    foreach (Vector3Int cell in tilemap.cellBounds.allPositionsWithin)
                    {
                        if (tilemap.HasTile(cell)) painted++;
                    }
                    Assert.AreEqual(count, painted, $"PaintStraightWallRun({count}) must paint exactly {count} contiguous cells.");
                }
            }
            finally
            {
                Object.DestroyImmediate(tile);
                Object.DestroyImmediate(wallObject);
            }
        }

        [Test]
        public void InMemoryVisuals_UseIsometricGridFloorAndFourWallTilemaps()
        {
            AssertTilemapVisuals(SceneManager.GetActiveScene());
        }

        [Test]
        public void CommittedVisuals_UseIsometricGridFloorAndFourWallTilemaps()
        {
            AssertCommittedSceneUnchanged(scene => AssertTilemapVisuals(scene));
        }

        [Test]
        public void InMemoryGeometry_MatchesApprovedRoomAndPreservesBothRoutes()
        {
            AssertRoomGeometry(SceneManager.GetActiveScene());
        }

        [Test]
        public void CommittedGeometry_MatchesApprovedRoomAndPreservesBothRoutes()
        {
            AssertCommittedSceneUnchanged(scene => AssertRoomGeometry(scene));
        }


        // NSC-083: the FR-1 mass shipped as a flat saturated INDIGO box - the same class of
        // defect as the Ruined Entry white cubes, where a blockout proxy reads as a rendering
        // fault rather than as a placeholder. The Art Director's pick was to reuse the tone
        // already approved for the rubble rather than authoring a fourth placeholder colour.
        [Test]
        public void Build_TintsTheCentralObstacleInsteadOfLeavingItIndigo()
        {
            AssertObstacleTint(SceneManager.GetActiveScene());
        }

        [Test]
        public void CommittedScene_CentralObstacleCarriesTheApprovedTint()
        {
            AssertCommittedSceneUnchanged(scene => AssertObstacleTint(scene));
        }

        private static void AssertObstacleTint(Scene scene)
        {
            // The approved blockout tone, written out DELIBERATELY rather than read from
            // RoomPlaceholderVisuals: a test that sources its expectation from the constant it
            // guards agrees with any value that constant ever takes, including a wrong one.
            Color32 expected = new Color32(96, 88, 80, 255);
            Color32 rejected = new Color32(41, 20, 51, 255);

            Transform obstacle = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<Transform>(true))
                .FirstOrDefault(candidate => candidate.name == "FR-1Visual");
            Assert.IsNotNull(obstacle, "FR-1Visual is missing from the Final Room.");

            Renderer renderer = obstacle.GetComponent<Renderer>();
            Assert.IsNotNull(renderer, "FR-1Visual has no Renderer.");
            Assert.IsNotNull(renderer.sharedMaterial, "FR-1Visual has no material.");

            Color actual = renderer.sharedMaterial.color;
            Color32 actual32 = actual;

            Assert.Greater(
                Mathf.Abs(actual.r - rejected.r / 255f) + Mathf.Abs(actual.b - rejected.b / 255f),
                4f / 255f,
                "FR-1Visual is still the saturated indigo " + rejected + ". That is the defect: a " +
                "blockout mass in a colour no finished surface uses reads as a rendering fault.");

            // Tolerance rather than Color32 equality: the colour makes a byte -> float -> byte
            // round trip through the material and a one-unit rounding difference is a flake.
            Assert.AreEqual(expected.r / 255f, actual.r, 1.5f / 255f,
                "FR-1Visual red: expected " + expected + " but was " + actual32);
            Assert.AreEqual(expected.g / 255f, actual.g, 1.5f / 255f,
                "FR-1Visual green: expected " + expected + " but was " + actual32);
            Assert.AreEqual(expected.b / 255f, actual.b, 1.5f / 255f,
                "FR-1Visual blue: expected " + expected + " but was " + actual32);
            Assert.AreEqual(expected.a / 255f, actual.a, 1.5f / 255f,
                "FR-1Visual alpha: expected " + expected + " but was " + actual32);

            // FR-1 MUST DRAW BEFORE THE DRESSING, AND THIS ASSERTION USED TO SAY THE OPPOSITE.
            // It required renderQueue == Transparent, to prove the alpha was not silently
            // dropped. That is the right assertion for the Ruined Entry rubble and the WRONG one
            // here, and it PASSED on the regression it should have caught: giving FR-1 alpha 230
            // moved its material to the Transparent queue (3000), where the dressing
            // SpriteRenderers already live, so the mass stopped drawing before them and overdrew
            // about 4% of the bone throne and skeleton rows against its silhouette. Caught by
            // measuring a rendered panel, not by this suite.
            //
            // Asserted as a RELATION rather than as the literal 2000, so any opaque-range queue
            // satisfies it: the mass must be drawn before anything at Transparent.
            Assert.Less(renderer.sharedMaterial.renderQueue,
                (int)UnityEngine.Rendering.RenderQueue.Transparent,
                "FR-1Visual renders at or after the transparent queue, so it draws over the " +
                "dressing props that sit against it instead of behind them.");
        }

        private static void AssertCommittedSceneUnchanged(System.Action<Scene> body)
        {
            byte[] before = File.ReadAllBytes(FinalRoomSceneBuilder.ScenePath);
            Scene scene = EditorSceneManager.OpenScene(FinalRoomSceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                body(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
            byte[] after = File.ReadAllBytes(FinalRoomSceneBuilder.ScenePath);
            CollectionAssert.AreEqual(before, after,
                "Opening FinalRoom.unity for conformance inspection must not change it.");
        }

        // AC-003/VAL-002: the single Grid, its five Tilemaps, their transforms, cell sets, cell
        // transforms, and sprite-to-collider extent matching.
        private static void AssertTilemapVisuals(Scene scene)
        {
            GameObject root = scene.GetRootGameObjects().Single(candidate => candidate.name == "Room_FinalRoom");
            Transform visuals = root.transform.Find("Visuals");
            Transform gridRoot = visuals.Find("IsometricZAsY");
            Assert.IsNotNull(gridRoot);
            Assert.AreEqual(Vector3.zero, gridRoot.localPosition);
            Assert.AreEqual(Quaternion.identity, gridRoot.localRotation);
            Assert.AreEqual(1, visuals.GetComponentsInChildren<Grid>().Length);
            Grid grid = gridRoot.GetComponent<Grid>();
            Assert.AreEqual(new Vector3(1f, 0.5f, 1f), grid.cellSize);
            Assert.AreEqual(GridLayout.CellSwizzle.XYZ, grid.cellSwizzle);
            Assert.AreEqual(GridLayout.CellLayout.Rectangle, grid.cellLayout);

            Tilemap floor = RequiredTilemap(gridRoot, "FloorTilemap", Quaternion.Euler(-90f, 0f, 0f), -100);
            Tilemap north = RequiredTilemap(gridRoot, "NorthFullWallTilemap", Quaternion.identity, 0);
            Tilemap south = RequiredTilemap(gridRoot, "SouthLowWallTilemap", Quaternion.identity, 0);
            Tilemap west = RequiredTilemap(gridRoot, "WestFullWallTilemap", Quaternion.Euler(0f, 90f, 0f), 0);
            Tilemap east = RequiredTilemap(gridRoot, "EastLowWallTilemap", Quaternion.Euler(0f, 90f, 0f), 0);
            Assert.AreEqual(5, visuals.GetComponentsInChildren<Tilemap>().Length);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<TilemapCollider2D>().Length);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<Collider>().Length);

            Assert.That(floor.transform.localPosition, Is.EqualTo(new Vector3(0f, 0.01f, 0f)));
            Assert.That(north.transform.localPosition.z, Is.EqualTo(103.849f).Within(0.001f));
            Assert.That(south.transform.localPosition.z, Is.EqualTo(76.151f).Within(0.001f));
            Assert.That(west.transform.localPosition.x, Is.EqualTo(-14.849f).Within(0.001f));
            Assert.That(east.transform.localPosition.x, Is.EqualTo(14.849f).Within(0.001f));

            // Read the floor Tile off a painted cell rather than assuming the room's own
            // generated Tile asset is already persisted: BuildInMemoryForTests() falls back to an
            // equivalent transient Tile when no persisted asset exists yet.
            Tile floorTile = null;
            foreach (Vector3Int candidate in floor.cellBounds.allPositionsWithin)
            {
                if (!floor.HasTile(candidate)) continue;
                floorTile = floor.GetTile(candidate) as Tile;
                break;
            }
            Tile wallTile = AssetDatabase.LoadAssetAtPath<Tile>(
                "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/WallTile.asset");
            Assert.IsNotNull(floorTile);
            Assert.IsNotNull(wallTile);
            Assert.That(wallTile.sprite.bounds.size.y, Is.EqualTo(2.5f).Within(0.01f),
                "Full-height wall cells render at 2.5 units.");
            Assert.That(wallTile.sprite.bounds.size.y * 0.2f, Is.EqualTo(0.5f).Within(0.05f),
                "Cutaway cells render at 0.5 units via the 0.2 cell transform.");

            // NSC-109 AC-001/VAL-001: the painted floor Tile must resolve to the committed
            // floor_FinalRoom sprite rather than a procedurally generated texture.
            Assert.AreEqual(
                "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_FinalRoom.png",
                AssetDatabase.GetAssetPath(floorTile.sprite));

            AssertFloorCoversRoomBounds(floor);

            IEnumerable<int> northCells = Enumerable.Range(-15, 13).Concat(Enumerable.Range(2, 13));
            IEnumerable<int> southCells = Enumerable.Range(-15, 17).Concat(Enumerable.Range(6, 9));
            IEnumerable<int> westCells = Enumerable.Range(-104, 28);
            IEnumerable<int> eastCells = Enumerable.Range(-104, 28);

            AssertWallCells(north, wallTile, northCells, lowWall: false);
            AssertWallCells(south, wallTile, southCells, lowWall: true);
            AssertWallCells(west, wallTile, westCells, lowWall: false);
            AssertWallCells(east, wallTile, eastCells, lowWall: true);

            // D4's X[2,6] and D5's X[-2,2] clear intervals must hold no wall cell (revised GER
            // room decision 2: no full-height jamb, the door instance frames the opening).
            for (int cell = 2; cell <= 5; cell++)
            {
                Assert.IsFalse(south.HasTile(new Vector3Int(cell, 0, 0)), $"South wall cell {cell} overlaps D4.");
            }
            for (int cell = -2; cell <= 1; cell++)
            {
                Assert.IsFalse(north.HasTile(new Vector3Int(cell, 0, 0)), $"North wall cell {cell} overlaps D5.");
            }

            Transform geometry = root.transform.Find("GameplayGeometry");
            AssertRunMatchesCollider(north, -15, -3, RequiredCollider(geometry, "NorthWallWestCollision").bounds, alongX: true);
            AssertRunMatchesCollider(north, 2, 14, RequiredCollider(geometry, "NorthWallEastCollision").bounds, alongX: true);
            AssertRunMatchesCollider(south, -15, 1, RequiredCollider(geometry, "SouthWallWestCollision").bounds, alongX: true);
            AssertRunMatchesCollider(south, 6, 14, RequiredCollider(geometry, "SouthWallEastCollision").bounds, alongX: true);
            AssertRunMatchesCollider(west, -104, -77, RequiredCollider(geometry, "WestWallCollision").bounds, alongX: false);
            AssertRunMatchesCollider(east, -104, -77, RequiredCollider(geometry, "EastWallCollision").bounds, alongX: false);
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
            // Assert the RELATION, not the value. This constant currently EQUALS "Default",
            // so the literal passed for the wrong reason and would keep passing after NSC-100
            // repoints it, while the room sorted wrongly against every world sprite.
            Assert.AreEqual(
                NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName,
                renderer.sortingLayerName);
            Assert.AreEqual(sortingOrder, renderer.sortingOrder);
            return tilemap;
        }

        private static void AssertWallCells(Tilemap tilemap, TileBase tile, IEnumerable<int> expectedCells, bool lowWall)
        {
            HashSet<int> expectedSet = new HashSet<int>(expectedCells);
            Matrix4x4 expectedTransform = lowWall
                ? Matrix4x4.Scale(NoSafeCircle.DoorPrototype.Editor.Rooms.FinalRoomSceneBuilder.LowWallCellScale)
                : Matrix4x4.identity;

            for (int cell = -110; cell <= 20; cell++)
            {
                Vector3Int position = new Vector3Int(cell, 0, 0);
                bool shouldHaveTile = expectedSet.Contains(cell);
                Assert.AreEqual(shouldHaveTile, tilemap.HasTile(position),
                    $"{tilemap.name} cell {cell} painted-state mismatch.");
                if (!shouldHaveTile) continue;

                Assert.AreSame(tile, tilemap.GetTile(position));
                Assert.AreEqual(expectedTransform, tilemap.GetTransformMatrix(position),
                    $"{tilemap.name} cell {cell} has an unexpected cell transform.");
            }
        }

        private static void AssertRunMatchesCollider(Tilemap tilemap, int firstCell, int lastCell, Bounds collider, bool alongX)
        {
            float first = alongX
                ? tilemap.CellToWorld(new Vector3Int(firstCell, 0, 0)).x
                : tilemap.CellToWorld(new Vector3Int(firstCell, 0, 0)).z;
            float last = alongX
                ? tilemap.CellToWorld(new Vector3Int(lastCell, 0, 0)).x
                : tilemap.CellToWorld(new Vector3Int(lastCell, 0, 0)).z;
            float visualMin = Mathf.Min(first, last) - 0.5f;
            float visualMax = Mathf.Max(first, last) + 0.5f;
            float colliderMin = alongX ? collider.min.x : collider.min.z;
            float colliderMax = alongX ? collider.max.x : collider.max.z;
            Assert.LessOrEqual(Mathf.Abs(visualMin - colliderMin), 0.5f,
                $"{tilemap.name} run start does not match its gameplay wall collider within 0.5 units.");
            Assert.LessOrEqual(Mathf.Abs(visualMax - colliderMax), 0.5f,
                $"{tilemap.name} run end does not match its gameplay wall collider within 0.5 units.");
        }

        private static void AssertFloorCoversRoomBounds(Tilemap floor)
        {
            float minX = FinalRoomLayout.MinimumX;
            float maxX = FinalRoomLayout.MaximumX;
            float minZ = FinalRoomLayout.MinimumZ;
            float maxZ = FinalRoomLayout.MaximumZ;

            Vector3Int cornerA = floor.WorldToCell(new Vector3(minX - 2f, 0f, minZ - 2f));
            Vector3Int cornerB = floor.WorldToCell(new Vector3(maxX + 2f, 0f, maxZ + 2f));
            int minCellX = Mathf.Min(cornerA.x, cornerB.x);
            int maxCellX = Mathf.Max(cornerA.x, cornerB.x);
            int minRow = Mathf.Min(cornerA.y, cornerB.y);
            int maxRow = Mathf.Max(cornerA.y, cornerB.y);

            for (int x = minCellX; x <= maxCellX; x++)
            {
                for (int row = minRow; row <= maxRow; row++)
                {
                    Vector3Int cell = new Vector3Int(x, row, 0);
                    Vector3 center = floor.GetCellCenterWorld(cell);
                    bool shouldPaint = FinalRoomSceneBuilder.FloorCellIsInsideRoom(center, floor.layoutGrid.cellSize);
                    Assert.AreEqual(shouldPaint, floor.HasTile(cell), $"Floor cell {cell} at world {center} violates RoomBounds.");
                }
            }

            // Sample STRICTLY inside RoomBounds, which is what this comment always claimed and
            // what the loop did not do: it started ON minX/minZ. A sample sitting exactly on a
            // room boundary is on the wall centerline, not in the interior, and which cell it
            // resolves to is decided by float residue in the tilemap's inverse transform -- the
            // measured run showed that residue changing SIGN with position. A test must not ask
            // a question whose answer is rounding. Every point strictly inside must have floor.
            const float step = 0.25f;
            for (float x = minX + step; x < maxX; x += step)
            {
                for (float z = minZ + step; z < maxZ; z += step)
                {
                    // The floor Tilemap's plane sits at world y = 0.01, so a sample taken at
                    // y = 0 lands at tilemap-local z = -0.01 and floors to cell z = -1, where no
                    // tile is ever painted. Sample the floor's own plane so the cell is the one
                    // the point actually stands on.
                    // The tilemap plane is at world y = 0.01, which is not exactly representable,
                    // so inverting the transform leaves a tiny residue and WorldToCell floors the
                    // z index to -1 -- measured as cell=(-15, -193, -1). Tiles only ever exist on
                    // plane 0, so take the cell there.
                    Vector3Int sampled = floor.WorldToCell(new Vector3(x, floor.transform.position.y, z));
                    Vector3Int cell = new Vector3Int(sampled.x, sampled.y, 0);
                    Assert.IsTrue(floor.HasTile(cell),
                        $"FloorTilemap has no tile under sample point ({x},{z}). " +
                        $"cell={cell} cellCenter={floor.GetCellCenterWorld(cell)} " +
                        $"floorY={floor.transform.position.y} origin={floor.origin} size={floor.size}");
                }
            }
        }

        // AC-004/AC-005/VAL-001: gameplay collision inventory, low-furniture limits, circulation,
        // D5 staging emptiness, both 3.5-unit-clearance FR-1 routes, door anchors, and composer
        // validation, all read from the scene's saved colliders rather than layout constants alone.
        // Strict overlap on the ground plane: shared VOLUME, never a shared SURFACE.
        // Bounds.Intersects is inclusive and reports a flush face as an intersection.
        private static bool SharesGroundVolume(Bounds a, Bounds b)
        {
            return a.min.x < b.max.x && a.max.x > b.min.x
                && a.min.z < b.max.z && a.max.z > b.min.z;
        }

        // Breaks the guard on purpose. Replacing Bounds.Intersects with a strict test is only
        // legitimate if the gate still CATCHES a real overlap; a predicate nobody has tried to
        // break is a claim, not evidence. Pure geometry, no scene.
        [Test]
        public void HazardFrameGate_AcceptsAFlushFaceAndStillCatchesRealOverlap()
        {
            Bounds hazard = FinalRoomLayout.EastExteriorHazardFrameBounds;
            float centerZ = FinalRoomLayout.RoomBounds.center.z;

            // What AC-004 actually ships: 0.5 wide on MaximumX 15, so its outer face is 15.25,
            // exactly the frame's min.x. Shares a plane, shares no volume.
            Bounds flush = new Bounds(
                new Vector3(FinalRoomLayout.MaximumX, 0f, centerZ),
                new Vector3(FinalRoomLayout.WallThickness, 0f, 28f));
            Assert.AreEqual(hazard.min.x, flush.max.x, 0.0001f,
                "This test is only meaningful while the shipped collider is flush with the frame.");
            Assert.IsFalse(SharesGroundVolume(flush, hazard),
                "A flush face gives the hazard frame no collision and must pass.");
            Assert.IsTrue(flush.Intersects(hazard),
                "Bounds.Intersects counts that same flush face as an intersection - the defect.");

            // Widen the wall by 0.1 and its face reaches 15.3, genuinely inside the frame.
            Bounds overlapping = new Bounds(
                new Vector3(FinalRoomLayout.MaximumX, 0f, centerZ),
                new Vector3(FinalRoomLayout.WallThickness + 0.1f, 0f, 28f));
            Assert.IsTrue(SharesGroundVolume(overlapping, hazard),
                "A collider reaching past the frame's min.x MUST still be caught.");
        }

        private static void AssertRoomGeometry(Scene scene)
        {
            GameObject root = scene.GetRootGameObjects().Single(candidate => candidate.name == "Room_FinalRoom");
            Transform visuals = root.transform.Find("Visuals");
            Transform geometry = root.transform.Find("GameplayGeometry");
            Transform anchors = root.transform.Find("DoorAnchors");
            Assert.IsNotNull(visuals);
            Assert.IsNotNull(geometry);
            Assert.IsNotNull(anchors);

            Assert.Greater(visuals.GetComponentsInChildren<Renderer>().Length, 0);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<Collider>().Length);
            Assert.AreEqual(0, geometry.GetComponentsInChildren<Renderer>().Length);
            Assert.Greater(geometry.GetComponentsInChildren<BoxCollider>().Length, 0);

            HashSet<string> expectedColliderNames = new HashSet<string>(PerimeterWallColliderNames)
            {
                "FloorCollision", "FR-1Collision", "WestBenchCollision", "EastBenchCollision"
            };
            HashSet<string> actualColliderNames = new HashSet<string>(
                geometry.GetComponentsInChildren<BoxCollider>().Select(collider => collider.name));
            CollectionAssert.AreEquivalent(expectedColliderNames, actualColliderNames,
                "GameplayGeometry must contain exactly the approved colliders and no unspecified interior solid.");

            BoxCollider floor = RequiredCollider(geometry, "FloorCollision");
            Assert.That(floor.bounds.min, Is.EqualTo(new Vector3(-15f, floor.bounds.min.y, 76f)).Using(Vector3Comparer));
            Assert.That(floor.bounds.max, Is.EqualTo(new Vector3(15f, floor.bounds.max.y, 104f)).Using(Vector3Comparer));

            BoxCollider west = RequiredCollider(geometry, "WestWallCollision");
            BoxCollider east = RequiredCollider(geometry, "EastWallCollision");
            BoxCollider southWest = RequiredCollider(geometry, "SouthWallWestCollision");
            BoxCollider southEast = RequiredCollider(geometry, "SouthWallEastCollision");
            BoxCollider northWest = RequiredCollider(geometry, "NorthWallWestCollision");
            BoxCollider northEast = RequiredCollider(geometry, "NorthWallEastCollision");
            foreach (BoxCollider wall in new[] { west, east, southWest, southEast, northWest, northEast })
            {
                Assert.That(wall.bounds.size.y, Is.EqualTo(2.5f).Within(0.01f));
                Assert.That(Mathf.Min(wall.bounds.size.x, wall.bounds.size.z), Is.EqualTo(0.5f).Within(0.001f));
            }
            Assert.That(west.bounds.center.x, Is.EqualTo(FinalRoomLayout.MinimumX).Within(0.01f));
            Assert.That(east.bounds.center.x, Is.EqualTo(FinalRoomLayout.MaximumX).Within(0.01f));
            Assert.That(southWest.bounds.center.z, Is.EqualTo(FinalRoomLayout.MinimumZ).Within(0.01f));
            Assert.That(southEast.bounds.center.z, Is.EqualTo(FinalRoomLayout.MinimumZ).Within(0.01f));
            Assert.That(northWest.bounds.center.z, Is.EqualTo(FinalRoomLayout.MaximumZ).Within(0.01f));
            Assert.That(northEast.bounds.center.z, Is.EqualTo(FinalRoomLayout.MaximumZ).Within(0.01f));

            float d4Clear = southEast.bounds.min.x - southWest.bounds.max.x;
            float d5Clear = northEast.bounds.min.x - northWest.bounds.max.x;
            Assert.That(d4Clear, Is.EqualTo(FinalRoomLayout.DoorOpeningWidth).Within(0.001f));
            Assert.That(d5Clear, Is.EqualTo(FinalRoomLayout.DoorOpeningWidth).Within(0.001f));

            BoxCollider fr1 = RequiredCollider(geometry, "FR-1Collision");
            Assert.That(fr1.bounds.min, Is.EqualTo(FinalRoomLayout.FR1Bounds.min).Using(Vector3Comparer));
            Assert.That(fr1.bounds.max, Is.EqualTo(FinalRoomLayout.FR1Bounds.max).Using(Vector3Comparer));

            BoxCollider westBench = RequiredCollider(geometry, "WestBenchCollision");
            BoxCollider eastBench = RequiredCollider(geometry, "EastBenchCollision");
            Assert.That(westBench.bounds.min, Is.EqualTo(FinalRoomLayout.WestBenchBounds.min).Using(Vector3Comparer));
            Assert.That(westBench.bounds.max, Is.EqualTo(FinalRoomLayout.WestBenchBounds.max).Using(Vector3Comparer));
            Assert.That(eastBench.bounds.min, Is.EqualTo(FinalRoomLayout.EastBenchBounds.min).Using(Vector3Comparer));
            Assert.That(eastBench.bounds.max, Is.EqualTo(FinalRoomLayout.EastBenchBounds.max).Using(Vector3Comparer));
            Assert.That(westBench.bounds.min.x, Is.EqualTo(west.bounds.max.x).Within(0.001f),
                "WestBenchCollision must sit flush against the west wall collider's inner face.");
            Assert.That(eastBench.bounds.max.x, Is.EqualTo(east.bounds.min.x).Within(0.001f),
                "EastBenchCollision must sit flush against the east wall collider's inner face.");

            AssertLowFurnitureLimitAndFR1IsOnlyMajorSolid(fr1, westBench, eastBench);
            AssertCirculationClearances(fr1, west, east, southWest, northWest);
            AssertD5StagingIsFreeOfInteriorSolids(geometry);
            AssertBothFR1RoutesHaveClearance(geometry);

            DoorAnchorMarker d4Anchor = anchors.Find("D4Anchor")?.GetComponent<DoorAnchorMarker>();
            DoorAnchorMarker d5Anchor = anchors.Find("D5Anchor")?.GetComponent<DoorAnchorMarker>();
            Assert.IsNotNull(d4Anchor);
            Assert.IsNotNull(d5Anchor);
            Assert.AreEqual(DoorAnchorRole.Entry, d4Anchor.Role);
            Assert.AreEqual(FinalRoomLayout.D4, d4Anchor.transform.position);
            Assert.AreEqual(DoorAnchorRole.Exit, d5Anchor.Role);
            Assert.AreEqual(FinalRoomLayout.D5, d5Anchor.transform.position);

            RoomSceneComposer.RoomValidationResult validation = RoomSceneComposer.ValidateOpenRoomScene(
                RoomId.FinalRoom, scene, FindRoomEntry(RoomId.FinalRoom), RoomSceneCatalog.CreateCanonicalDoors());
            CollectionAssert.IsEmpty(validation.Errors, string.Join("\n", validation.Errors));
            Assert.That(validation.DoorAnchors, Has.Count.EqualTo(2));

            AssertOnlyApprovedMeshRenderersRemain(visuals);
        }

        private static void AssertLowFurnitureLimitAndFR1IsOnlyMajorSolid(
            BoxCollider fr1, BoxCollider westBench, BoxCollider eastBench)
        {
            foreach (BoxCollider bench in new[] { westBench, eastBench })
            {
                float area = bench.bounds.size.x * bench.bounds.size.z;
                Assert.LessOrEqual(bench.bounds.size.y, 0.75f, $"{bench.name} exceeds the low-furniture height limit.");
                Assert.LessOrEqual(area, 1.5f, $"{bench.name} exceeds the low-furniture footprint limit.");
            }

            float fr1Area = fr1.bounds.size.x * fr1.bounds.size.z;
            Assert.IsTrue(fr1.bounds.size.y > 0.75f || fr1Area > 1.5f,
                "FR-1 must be the room's major interior solid.");
        }

        private static void AssertCirculationClearances(
            BoxCollider fr1, BoxCollider west, BoxCollider east, BoxCollider southWest, BoxCollider northWest)
        {
            float westCirculation = fr1.bounds.min.x - west.bounds.max.x;
            float eastCirculation = east.bounds.min.x - fr1.bounds.max.x;
            float southCirculation = fr1.bounds.min.z - southWest.bounds.max.z;
            float northCirculation = northWest.bounds.min.z - fr1.bounds.max.z;

            Assert.That(westCirculation, Is.EqualTo(11.25f).Within(0.01f));
            Assert.That(eastCirculation, Is.EqualTo(11.25f).Within(0.01f));
            Assert.That(southCirculation, Is.EqualTo(10.75f).Within(0.01f));
            Assert.That(northCirculation, Is.EqualTo(9.75f).Within(0.01f));

            foreach (float circulation in new[] { westCirculation, eastCirculation, southCirculation, northCirculation })
            {
                Assert.GreaterOrEqual(circulation, 4f);
            }
        }

        private static void AssertD5StagingIsFreeOfInteriorSolids(Transform geometry)
        {
            Bounds staging = FinalRoomLayout.D5StagingBounds;
            foreach (BoxCollider collider in geometry.GetComponentsInChildren<BoxCollider>())
            {
                if (collider.name == "FloorCollision" || PerimeterWallColliderNames.Contains(collider.name)) continue;
                Assert.IsFalse(collider.bounds.Intersects(staging),
                    $"'{collider.name}' intrudes into the D5 staging rectangle.");
            }
        }

        // AC-005/VAL-001: search the saved collider layout on a 0.25-unit grid after inflating
        // every solid footprint by 1.75 units, proving one route passes west of FR-1 and a second
        // passes east, each with at least 3.5 units of clearance. D4/D5 throats are excluded by
        // construction: the approach points already sit past the inflated wall zone at each door.
        private static void AssertBothFR1RoutesHaveClearance(Transform geometry)
        {
            var obstacles = new List<Bounds>();
            foreach (BoxCollider collider in geometry.GetComponentsInChildren<BoxCollider>())
            {
                if (collider.name == "FloorCollision") continue;
                obstacles.Add(InflateXZ(collider.bounds, 1.75f));
            }

            Vector2 d4Approach = new Vector2(4f, 78.5f);
            Vector2 d5Approach = new Vector2(0f, 101.5f);

            Assert.IsTrue(RouteExists(obstacles, d4Approach, d5Approach, forceWestOfFR1: true),
                "No route with 3.5-unit clearance passes west of FR-1 from the D4 approach to the D5 approach.");
            Assert.IsTrue(RouteExists(obstacles, d4Approach, d5Approach, forceWestOfFR1: false),
                "No route with 3.5-unit clearance passes east of FR-1 from the D4 approach to the D5 approach.");
        }

        private static Bounds InflateXZ(Bounds bounds, float amount)
        {
            Vector3 min = bounds.min;
            Vector3 max = bounds.max;
            min.x -= amount;
            min.z -= amount;
            max.x += amount;
            max.z += amount;
            Bounds inflated = new Bounds();
            inflated.SetMinMax(min, max);
            return inflated;
        }

        private static bool RouteExists(List<Bounds> obstacles, Vector2 start, Vector2 goal, bool forceWestOfFR1)
        {
            const float step = 0.25f;
            float fr1MinZ = FinalRoomLayout.FR1Bounds.min.z;
            float fr1MaxZ = FinalRoomLayout.FR1Bounds.max.z;

            bool IsBlocked(Vector2Int cell)
            {
                float x = cell.x * step;
                float z = cell.y * step;
                if (x < FinalRoomLayout.MinimumX || x > FinalRoomLayout.MaximumX ||
                    z < FinalRoomLayout.MinimumZ || z > FinalRoomLayout.MaximumZ)
                {
                    return true;
                }

                foreach (Bounds obstacle in obstacles)
                {
                    if (x >= obstacle.min.x && x <= obstacle.max.x && z >= obstacle.min.z && z <= obstacle.max.z)
                    {
                        return true;
                    }
                }

                if (z >= fr1MinZ && z <= fr1MaxZ)
                {
                    if (forceWestOfFR1 && x >= 0f) return true;
                    if (!forceWestOfFR1 && x <= 0f) return true;
                }

                return false;
            }

            Vector2Int ToCell(Vector2 point) =>
                new Vector2Int(Mathf.RoundToInt(point.x / step), Mathf.RoundToInt(point.y / step));

            Vector2Int startCell = ToCell(start);
            Vector2Int goalCell = ToCell(goal);
            Assert.IsFalse(IsBlocked(startCell), "The approach point must not itself be blocked.");

            var visited = new HashSet<Vector2Int> { startCell };
            var queue = new Queue<Vector2Int>();
            queue.Enqueue(startCell);
            Vector2Int[] directions = { Vector2Int.up, Vector2Int.down, Vector2Int.left, Vector2Int.right };
            while (queue.Count > 0)
            {
                Vector2Int current = queue.Dequeue();
                if (current == goalCell) return true;
                foreach (Vector2Int direction in directions)
                {
                    Vector2Int next = current + direction;
                    if (visited.Contains(next) || IsBlocked(next)) continue;
                    visited.Add(next);
                    queue.Enqueue(next);
                }
            }

            return visited.Contains(goalCell);
        }

        private static void AssertOnlyApprovedMeshRenderersRemain(Transform visuals)
        {
            HashSet<string> expectedPaths = new HashSet<string>
            {
                "FR-1Visual",
                "FittingRoomDressing/WestBench",
                "FittingRoomDressing/EastBench",
                "FittingRoomDressing/Candle1/Wax",
                "FittingRoomDressing/Candle1/Flame"
            };

            var actualPaths = new HashSet<string>();
            foreach (MeshRenderer renderer in visuals.GetComponentsInChildren<MeshRenderer>(true))
            {
                var segments = new List<string>();
                Transform current = renderer.transform;
                while (current != null && current != visuals)
                {
                    segments.Insert(0, current.name);
                    current = current.parent;
                }
                actualPaths.Add(string.Join("/", segments));
            }

            CollectionAssert.AreEquivalent(expectedPaths, actualPaths,
                "Only FR-1Visual, WestBench, EastBench, and Candle1's Wax/Flame children may carry MeshRenderers.");
        }

        private static BoxCollider RequiredCollider(Transform geometry, string name)
        {
            BoxCollider collider = geometry.Find(name)?.GetComponent<BoxCollider>();
            Assert.IsNotNull(collider, $"Expected GameplayGeometry/{name} BoxCollider.");
            return collider;
        }

        private static RoomSceneCatalog.RoomCatalogEntry FindRoomEntry(RoomId roomId)
        {
            foreach (RoomSceneCatalog.RoomCatalogEntry entry in RoomSceneCatalog.CreateCanonicalRooms())
            {
                if (entry.RoomId == roomId) return entry;
            }

            Assert.Fail($"Missing canonical catalog entry for {roomId}.");
            return null;
        }

        private static readonly Vector3ApproximateComparer Vector3Comparer = new Vector3ApproximateComparer();

        private sealed class Vector3ApproximateComparer : IEqualityComparer<Vector3>
        {
            public bool Equals(Vector3 a, Vector3 b) => Vector3.Distance(a, b) < 0.001f;
            public int GetHashCode(Vector3 v) => 0;
        }
    }
}
