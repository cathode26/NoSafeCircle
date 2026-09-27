using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NoSafeCircle.DoorPrototype.Editor;
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
    public sealed class ChapelOfAshSceneTests
    {
        private const string ChapelFarWallTileAssetPath =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/ChapelOfAshFarWallTile.asset";
        private const string ChapelCutawayWallTileAssetPath =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/ChapelOfAshCutawayWallTile.asset";

        private const float ProbeStep = 0.25f;
        private const float ProbeRadius = 1.25f;

        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            ChapelOfAshSceneBuilder.BuildInMemoryForTests();
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        // ---- AC-001/AC-002/AC-007: layout data ----

        [Test] // AC-001
        public void Layout_ContainsRevisionSixBoundsDoorsReservesAndReviewStations()
        {
            Assert.That(ChapelOfAshLayout.RoomBounds.min, Is.EqualTo(new Vector3(-18f, 0f, 20f)));
            Assert.That(ChapelOfAshLayout.RoomBounds.max, Is.EqualTo(new Vector3(18f, 0f, 54f)));
            Assert.That(ChapelOfAshLayout.D2, Is.EqualTo(new Vector3(6f, 0f, 20f)));
            Assert.That(ChapelOfAshLayout.D3, Is.EqualTo(new Vector3(-8f, 0f, 54f)));

            AssertBoundsXZ(ChapelOfAshLayout.CentralAisleBounds, -2.5f, 2.5f, 25f, 49f);
            AssertBoundsXZ(ChapelOfAshLayout.D2LandingBounds, 3.5f, 8.5f, 20.25f, 25.25f);
            AssertBoundsXZ(ChapelOfAshLayout.D3StagingBounds, -10.5f, -5.5f, 48.75f, 53.75f);
            AssertBoundsXZ(ChapelOfAshLayout.RitualFocusReserveBounds, -2.5f, 2.5f, 50f, 53f);
            AssertBoundsXZ(ChapelOfAshLayout.WestRemembranceClusterReserveBounds, -16.5f, -13f, 50f, 53.5f);
            AssertBoundsXZ(ChapelOfAshLayout.EastVestryClusterReserveBounds, 8f, 14f, 50f, 53.5f);

            Vector3[] expectedStations =
            {
                new Vector3(6f, 0f, 24f),
                new Vector3(-15.5f, 0f, 37f),
                new Vector3(12f, 0f, 42f),
                new Vector3(-8f, 0f, 51f)
            };
            CollectionAssert.AreEqual(expectedStations, ChapelOfAshLayout.GameplayCameraReviewStations);
        }

        [Test] // AC-002
        public void Layout_ContainsEightPewFootprintsWithFourUnitRowGaps()
        {
            Assert.That(ChapelOfAshLayout.PewFootprints, Has.Length.EqualTo(8));
            float[] rowStartZ = { 27f, 33f, 39f, 45f };
            for (int row = 0; row < 4; row++)
            {
                AssertPewFootprint(ChapelOfAshLayout.PewFootprints[row], -12.5f, -3.5f, rowStartZ[row], rowStartZ[row] + 2f);
                AssertPewFootprint(ChapelOfAshLayout.PewFootprints[row + 4], 3.5f, 12.5f, rowStartZ[row], rowStartZ[row] + 2f);
            }

            Assert.That(ChapelOfAshLayout.PewFootprints[1].min.z - ChapelOfAshLayout.PewFootprints[0].max.z, Is.EqualTo(4f));
            Assert.That(ChapelOfAshLayout.PewFootprints[2].min.z - ChapelOfAshLayout.PewFootprints[1].max.z, Is.EqualTo(4f));
            Assert.That(ChapelOfAshLayout.PewFootprints[3].min.z - ChapelOfAshLayout.PewFootprints[2].max.z, Is.EqualTo(4f));
            Assert.That(ChapelOfAshLayout.PewRowGapWidth, Is.EqualTo(4f));
            Assert.That(ChapelOfAshLayout.MinimumHardGeometryPassage, Is.EqualTo(2.5f));
        }

        [Test] // AC-002
        public void Layout_ColumnsTouchPewRowsAndPreserveApprovedSideRouteClearance()
        {
            Assert.That(ChapelOfAshLayout.ColumnCenters, Has.Length.EqualTo(4));
            Vector3[] expectedCenters =
            {
                new Vector3(-13.25f, 0f, 28f),
                new Vector3(13.25f, 0f, 28f),
                new Vector3(-13.25f, 0f, 40f),
                new Vector3(13.25f, 0f, 40f)
            };
            CollectionAssert.AreEqual(expectedCenters, ChapelOfAshLayout.ColumnCenters);

            Bounds columnWest1 = ChapelOfAshLayout.ColumnBounds(ChapelOfAshLayout.ColumnCenters[0]);
            Bounds columnEast1 = ChapelOfAshLayout.ColumnBounds(ChapelOfAshLayout.ColumnCenters[1]);
            Bounds columnWest3 = ChapelOfAshLayout.ColumnBounds(ChapelOfAshLayout.ColumnCenters[2]);
            Bounds columnEast3 = ChapelOfAshLayout.ColumnBounds(ChapelOfAshLayout.ColumnCenters[3]);

            Assert.That(columnWest1.max.x, Is.EqualTo(ChapelOfAshLayout.PewFootprints[0].min.x).Within(0.001f));
            Assert.That(columnEast1.min.x, Is.EqualTo(ChapelOfAshLayout.PewFootprints[4].max.x).Within(0.001f));
            Assert.That(columnWest3.max.x, Is.EqualTo(ChapelOfAshLayout.PewFootprints[2].min.x).Within(0.001f));
            Assert.That(columnEast3.min.x, Is.EqualTo(ChapelOfAshLayout.PewFootprints[6].max.x).Within(0.001f));

            float innerMinX = ChapelOfAshLayout.MinimumX + ChapelOfAshLayout.WallThickness * 0.5f;
            float innerMaxX = ChapelOfAshLayout.MaximumX - ChapelOfAshLayout.WallThickness * 0.5f;
            float westClearance = columnWest1.min.x - innerMinX;
            float eastClearance = innerMaxX - columnEast1.max.x;
            Assert.That(westClearance, Is.EqualTo(3.75f).Within(0.001f));
            Assert.That(eastClearance, Is.EqualTo(3.75f).Within(0.001f));
            Assert.That(ChapelOfAshLayout.SideRouteColumnClearance, Is.EqualTo(3.75f));
            Assert.That(ChapelOfAshLayout.MinimumSideRouteClearance, Is.EqualTo(3.5f));
            Assert.That(westClearance, Is.GreaterThanOrEqualTo(ChapelOfAshLayout.MinimumSideRouteClearance));

            Assert.That(ChapelOfAshLayout.CoverPocketWest, Is.EqualTo(new Vector3(-15.5f, 0f, 34f)));
            Assert.That(ChapelOfAshLayout.CoverPocketEast, Is.EqualTo(new Vector3(15.5f, 0f, 40f)));
        }

        [Test] // AC-001/AC-007
        public void Layout_KeepsAisleLandingAndStagingFreeOfPewAndColumnFootprints()
        {
            Bounds[] hardGeometry = ChapelOfAshLayout.PewFootprints
                .Concat(ChapelOfAshLayout.ColumnCenters.Select(ChapelOfAshLayout.ColumnBounds))
                .ToArray();

            foreach (Bounds bounds in hardGeometry)
            {
                Assert.IsFalse(OverlapsXZ(bounds, ChapelOfAshLayout.CentralAisleBounds),
                    $"{bounds} obstructs the central aisle.");
                Assert.IsFalse(OverlapsXZ(bounds, ChapelOfAshLayout.D2LandingBounds),
                    $"{bounds} obstructs the D2 landing.");
                Assert.IsFalse(OverlapsXZ(bounds, ChapelOfAshLayout.D3StagingBounds),
                    $"{bounds} obstructs the D3 staging area.");
            }
        }

        // ---- VAL-002 (in-memory scene-builder tests): grid, tilemaps, colliders, blockouts ----

        [Test]
        public void Builder_CreatesTransientTilesWhenNoGeneratedAssetExists()
        {
            // TWO-SIDED, per NSC-046 contract revision 12 (the form NSC-044 AC-005 set).
            // This fixture used to assert the generated Tile assets do NOT exist. But
            // materialization COMMITS them, so that precondition cannot hold once the room
            // is real: the test asserted its own SETUP rather than the builder's behaviour,
            // and became unsatisfiable by construction the moment the room was materialized.
            // Assert what must hold on EITHER side of that line instead.
            bool farWallIsAsset = File.Exists(ChapelFarWallTileAssetPath);
            bool cutawayIsAsset = File.Exists(ChapelCutawayWallTileAssetPath);

            Transform grid = FindGrid(SceneManager.GetActiveScene());
            Tilemap north = RequireTilemap(grid, "NorthFullWallTilemap");
            Tilemap south = RequireTilemap(grid, "SouthLowWallTilemap");
            Tile farWallTile = north.GetTile(new Vector3Int(-18, 0, 0)) as Tile;
            Tile cutawayWallTile = south.GetTile(new Vector3Int(-18, 0, 0)) as Tile;

            Assert.IsNotNull(farWallTile);
            Assert.IsNotNull(cutawayWallTile);
            // Asset-backed: the builder must USE the committed asset, not a transient copy.
            // Transient: every object it fabricates must be HideAndDontSave so none leaks
            // into the scene. Both are real claims; neither guesses at flags not verified.
            if (farWallIsAsset)
            {
                Assert.AreEqual(ChapelFarWallTileAssetPath, AssetDatabase.GetAssetPath(farWallTile),
                    "With the generated far-wall asset present the builder must use it.");
            }
            else
            {
                // The Tile itself is a fabricated transient object, but its sprite is now the
                // shared committed source asset (NSC-109), not a fabricated sub-asset, so only
                // the Tile's own hideFlags are asserted here.
                Assert.AreEqual(HideFlags.HideAndDontSave, farWallTile.hideFlags);
            }

            if (cutawayIsAsset)
            {
                Assert.AreEqual(ChapelCutawayWallTileAssetPath, AssetDatabase.GetAssetPath(cutawayWallTile),
                    "With the generated cutaway-wall asset present the builder must use it.");
            }
            else
            {
                Assert.AreEqual(HideFlags.HideAndDontSave, cutawayWallTile.hideFlags);
            }
            Assert.AreEqual(Tile.ColliderType.None, farWallTile.colliderType);
            Assert.AreEqual(Tile.ColliderType.None, cutawayWallTile.colliderType);
            Assert.That(farWallTile.sprite.bounds.size.y, Is.EqualTo(2.5f).Within(0.001f));
            Assert.That(cutawayWallTile.sprite.bounds.size.y, Is.EqualTo(2.796875f).Within(0.001f));

            // NSC-109 AC-001/VAL-001: both wall Tiles must resolve to their committed source
            // sprites rather than to a procedurally generated texture, whether the persisted
            // asset already exists or the builder fell back to an equivalent transient Tile.
            Assert.AreEqual(
                "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_straight.png",
                AssetDatabase.GetAssetPath(farWallTile.sprite));
            Assert.AreEqual(
                "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_broken_stub.png",
                AssetDatabase.GetAssetPath(cutawayWallTile.sprite));
        }

        [Test]
        public void Builder_CreatesIsometricGridWithFiveConfiguredTilemapsAndNoStrayColliders()
        {
            GameObject roomRoot = FindRoomRoot(SceneManager.GetActiveScene());
            Transform visuals = roomRoot.transform.Find("Visuals");
            Transform gridTransform = visuals.Find("IsometricZAsY");
            Assert.IsNotNull(gridTransform);
            Assert.AreEqual(Vector3.zero, gridTransform.localPosition);
            Assert.AreEqual(Quaternion.identity, gridTransform.localRotation);
            Assert.AreEqual(Vector3.one, gridTransform.localScale);

            Grid grid = gridTransform.GetComponent<Grid>();
            Assert.IsNotNull(grid);
            Assert.AreEqual(new Vector3(1f, 0.5f, 1f), grid.cellSize);
            Assert.AreEqual(GridLayout.CellSwizzle.XYZ, grid.cellSwizzle);
            Assert.AreEqual(GridLayout.CellLayout.Rectangle, grid.cellLayout);
            Assert.AreEqual(1, visuals.GetComponentsInChildren<Grid>().Length);

            RequireTilemapConfiguration(gridTransform, "FloorTilemap", new Vector3(0f, 0.01f, 0f), Quaternion.Euler(-90f, 0f, 0f),
                WorldSpriteConvention.BackgroundGroundSortingOrder);
            RequireTilemapConfiguration(gridTransform, "NorthFullWallTilemap", new Vector3(0.5f, 0f, 53.849f), Quaternion.identity, 0);
            RequireTilemapConfiguration(gridTransform, "SouthLowWallTilemap", new Vector3(0.5f, 0f, 20.151f), Quaternion.identity, 0);
            RequireTilemapConfiguration(gridTransform, "WestFullWallTilemap", new Vector3(-17.849f, 0f, -0.5f), Quaternion.Euler(0f, 90f, 0f), 0);
            RequireTilemapConfiguration(gridTransform, "EastLowWallTilemap", new Vector3(17.849f, 0f, -0.5f), Quaternion.Euler(0f, 90f, 0f), 0);
            Assert.AreEqual(5, visuals.GetComponentsInChildren<Tilemap>().Length);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<TilemapCollider2D>().Length);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<Collider>().Length);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<MeshRenderer>().Length,
                "AC-003: no MeshRenderer may remain under Visuals.");
        }

        [Test] // AC-003
        public void Builder_PaintsFloorTilemapExactlyInsideWallInteriorFaces()
        {
            Transform grid = FindGrid(SceneManager.GetActiveScene());
            Tilemap floor = RequireTilemap(grid, "FloorTilemap");

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
            Assert.IsNotNull(floorTile);

            // NSC-109 AC-001/VAL-001: the painted floor Tile must resolve to the committed
            // floor_ChapelOfAsh sprite rather than a procedurally generated texture.
            Assert.AreEqual(
                "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_ChapelOfAsh.png",
                AssetDatabase.GetAssetPath(floorTile.sprite));

            int paintedCount = 0;
            int minPaintedX = int.MaxValue, maxPaintedX = int.MinValue;
            int minPaintedRow = int.MaxValue, maxPaintedRow = int.MinValue;
            for (int x = -20; x <= 20; x++)
            {
                for (int row = -120; row <= -30; row++)
                {
                    Vector3Int cell = new Vector3Int(x, row, 0);
                    Vector3 corner = floor.GetCellCenterWorld(cell);
                    // NSC-109 wall-floor gap: assert the SAME rule the builder paints by, taken
                    // from the builder rather than restated here, so the two cannot drift. The
                    // literals this replaced encoded the wall-collider inner faces, which left
                    // the floor short of the wall's visual plane in every room that used them.
                    bool shouldPaint = ChapelOfAshSceneBuilder.FloorCellIsInsideRoom(corner, floor.layoutGrid.cellSize);
                    Assert.AreEqual(shouldPaint, floor.HasTile(cell), $"Floor cell {cell} at world {corner} violates RoomBounds.");
                    if (shouldPaint)
                    {
                        Assert.AreSame(floorTile, floor.GetTile(cell));
                        paintedCount++;
                        minPaintedX = Mathf.Min(minPaintedX, x);
                        maxPaintedX = Mathf.Max(maxPaintedX, x);
                        minPaintedRow = Mathf.Min(minPaintedRow, row);
                        maxPaintedRow = Mathf.Max(maxPaintedRow, row);
                    }
                }
            }

            // NSC-109 wall-floor gap: 2,448 = 36 columns x 68 rows, derived INDEPENDENTLY of
            // the loop above so this stays a witness rather than a restatement of it.
            // Columns: corner.x from -18 to 17 inclusive (corner.x + 1 <= MaximumX = 18).
            // Rows: corner.z from 20.5 to 54.0 in 0.5 steps (corner.z - 0.5 >= MinimumZ = 20).
            // Was 2,345 = 35 x 67, one column and one row short, which is the gap.
            Assert.AreEqual(2448, paintedCount, "AC-003 requires every cell whose footprint lies inside RoomBounds.");
            // NSC-109 wall-floor gap: the extent grows on exactly ONE side of each axis, which
            // is what the rule predicts and is worth pinning rather than just the total. The
            // point GetCellCenterWorld returns is the cell's LOW-X / HIGH-Z corner, and the rule
            // is corner.x >= MinimumX with corner.x + cellSize.x <= MaximumX, so the low-x side
            // gains a column (-17 -> -18) and the high-x side cannot. Rows mirror it: the
            // negated-z axis gains one at -108 while -41 is unchanged.
            Assert.AreEqual(-18, minPaintedX);
            Assert.AreEqual(17, maxPaintedX);
            Assert.AreEqual(-108, minPaintedRow);
            Assert.AreEqual(-41, maxPaintedRow);
        }

        [Test] // AC-004
        public void Builder_PaintsApprovedWallCellSetsWithClearDoorAperturesAndCorners()
        {
            Transform grid = FindGrid(SceneManager.GetActiveScene());
            Tilemap north = RequireTilemap(grid, "NorthFullWallTilemap");
            Tilemap south = RequireTilemap(grid, "SouthLowWallTilemap");
            Tilemap west = RequireTilemap(grid, "WestFullWallTilemap");
            Tilemap east = RequireTilemap(grid, "EastLowWallTilemap");

            Tile farWallTile = north.GetTile(new Vector3Int(-18, 0, 0)) as Tile;
            Tile cutawayWallTile = south.GetTile(new Vector3Int(-18, 0, 0)) as Tile;
            Assert.IsNotNull(farWallTile);
            Assert.IsNotNull(cutawayWallTile);
            Assert.AreNotSame(farWallTile, cutawayWallTile);

            AssertWallCellSet(north, farWallTile, -18, -11, -6, 17);
            AssertWallCellSet(south, cutawayWallTile, -18, 3, 8, 17);
            AssertWallCellSet(west, farWallTile, -54, -21);
            AssertWallCellSet(east, cutawayWallTile, -54, -21);

            for (int cell = -10; cell <= -7; cell++)
            {
                Assert.IsFalse(north.HasTile(new Vector3Int(cell, 0, 0)), $"North wall cell {cell} must stay empty over the D3 gap.");
            }
            for (int cell = 4; cell <= 7; cell++)
            {
                Assert.IsFalse(south.HasTile(new Vector3Int(cell, 0, 0)), $"South wall cell {cell} must stay empty over the D2 gap.");
            }

            // Both meeting walls paint each corner cell.
            Assert.IsTrue(north.HasTile(new Vector3Int(-18, 0, 0)));
            Assert.IsTrue(north.HasTile(new Vector3Int(17, 0, 0)));
            Assert.IsTrue(south.HasTile(new Vector3Int(-18, 0, 0)));
            Assert.IsTrue(south.HasTile(new Vector3Int(17, 0, 0)));
            Assert.IsTrue(west.HasTile(new Vector3Int(-54, 0, 0)));
            Assert.IsTrue(west.HasTile(new Vector3Int(-21, 0, 0)));
            Assert.IsTrue(east.HasTile(new Vector3Int(-54, 0, 0)));
            Assert.IsTrue(east.HasTile(new Vector3Int(-21, 0, 0)));

            AssertNoTileInWorldRange(south, 4.5f, 7.5f);
            AssertNoTileInWorldRange(north, -9.5f, -6.5f);
        }

        [Test] // AC-004
        public void Builder_WallVisualExtentMatchesGameplayColliderWithinHalfUnitAndStaysInset()
        {
            GameObject roomRoot = FindRoomRoot(SceneManager.GetActiveScene());
            Transform grid = roomRoot.transform.Find("Visuals/IsometricZAsY");
            Transform geometry = roomRoot.transform.Find("GameplayGeometry");

            Tilemap north = grid.Find("NorthFullWallTilemap").GetComponent<Tilemap>();
            Tilemap south = grid.Find("SouthLowWallTilemap").GetComponent<Tilemap>();
            Tilemap west = grid.Find("WestFullWallTilemap").GetComponent<Tilemap>();
            Tilemap east = grid.Find("EastLowWallTilemap").GetComponent<Tilemap>();

            Assert.That(north.transform.localPosition.z, Is.EqualTo(53.849f).Within(0.001f));
            Assert.That(south.transform.localPosition.z, Is.EqualTo(20.151f).Within(0.001f));
            Assert.That(west.transform.localPosition.x, Is.EqualTo(-17.849f).Within(0.001f));
            Assert.That(east.transform.localPosition.x, Is.EqualTo(17.849f).Within(0.001f));

            BoxCollider westWall = RequireCollider(geometry, "WestWallCollision");
            BoxCollider eastWall = RequireCollider(geometry, "EastWallCollision");
            BoxCollider southWest = RequireCollider(geometry, "SouthWallWestCollision");
            BoxCollider southEast = RequireCollider(geometry, "SouthWallEastCollision");
            BoxCollider northWest = RequireCollider(geometry, "NorthWallWestCollision");
            BoxCollider northEast = RequireCollider(geometry, "NorthWallEastCollision");

            Assert.That(westWall.bounds.center.x, Is.EqualTo(-18f).Within(0.01f));
            Assert.That(eastWall.bounds.center.x, Is.EqualTo(18f).Within(0.01f));
            Assert.That(southWest.bounds.center.z, Is.EqualTo(20f).Within(0.01f));
            Assert.That(southEast.bounds.center.z, Is.EqualTo(20f).Within(0.01f));
            Assert.That(northWest.bounds.center.z, Is.EqualTo(54f).Within(0.01f));
            Assert.That(northEast.bounds.center.z, Is.EqualTo(54f).Within(0.01f));

            AssertRunMatchesCollider(north, -18, -11, northWest.bounds, true);
            AssertRunMatchesCollider(north, -6, 17, northEast.bounds, true);
            AssertRunMatchesCollider(south, -18, 3, southWest.bounds, true);
            AssertRunMatchesCollider(south, 8, 17, southEast.bounds, true);
            AssertRunMatchesCollider(west, -54, -21, westWall.bounds, false);
            AssertRunMatchesCollider(east, -54, -21, eastWall.bounds, false);
        }

        [Test] // AC-003/AC-005
        public void Builder_CreatesBottomPivotSpriteBlockoutsAndSeparateGameplayColliders()
        {
            GameObject roomRoot = FindRoomRoot(SceneManager.GetActiveScene());
            Transform visuals = roomRoot.transform.Find("Visuals");
            Transform gameplay = roomRoot.transform.Find("GameplayGeometry");

            for (int index = 0; index < ChapelOfAshLayout.PewFootprints.Length; index++)
            {
                RequireBlockoutSprite(visuals, "Pew" + (index + 1) + "Visual");
            }
            for (int index = 0; index < ChapelOfAshLayout.ColumnCenters.Length; index++)
            {
                RequireBlockoutSprite(visuals, "Column" + (index + 1) + "Visual");
            }
            RequireBlockoutSprite(visuals, "RitualFocusReserveVisual");

            Assert.AreEqual(0, visuals.GetComponentsInChildren<Collider>().Length);

            BoxCollider[] gameplayColliders = gameplay.GetComponentsInChildren<BoxCollider>();
            Assert.AreEqual(19, gameplayColliders.Length);
            Assert.AreEqual(0, gameplay.GetComponentsInChildren<Renderer>().Length);

            for (int index = 0; index < ChapelOfAshLayout.PewFootprints.Length; index++)
            {
                BoxCollider collider = RequireCollider(gameplay, "Pew" + (index + 1) + "Collision");
                Assert.That(collider.bounds, Is.EqualTo(ChapelOfAshLayout.PewFootprints[index]));
            }
            for (int index = 0; index < ChapelOfAshLayout.ColumnCenters.Length; index++)
            {
                BoxCollider collider = RequireCollider(gameplay, "Column" + (index + 1) + "Collision");
                Assert.That(collider.bounds,
                    Is.EqualTo(ChapelOfAshLayout.ColumnBounds(ChapelOfAshLayout.ColumnCenters[index])));
            }
        }

        [Test]
        public void Builder_DoesNotWriteGeneratedTileAssetsToDisk()
        {
            bool farExisted = File.Exists(ChapelFarWallTileAssetPath);
            bool cutawayExisted = File.Exists(ChapelCutawayWallTileAssetPath);

            ChapelOfAshSceneBuilder.BuildInMemoryForTests();

            Assert.AreEqual(farExisted, File.Exists(ChapelFarWallTileAssetPath));
            Assert.AreEqual(cutawayExisted, File.Exists(ChapelCutawayWallTileAssetPath));
        }

        // ---- VAL-002 (temporary-asset generator tests) ----

        // NSC-109 AC-001/AC-002/VAL-001: both wall Tiles must resolve to their committed source
        // sprites instead of a procedurally generated masonry texture.
        [Test]
        public void WallTiles_ResolveToCommittedSourceSpritesWithNoCollider()
        {
            string folderName = "__NSC109ChapelWall_" + Guid.NewGuid().ToString("N");
            string folderPath = "Assets/" + folderName;
            AssetDatabase.CreateFolder("Assets", folderName);
            try
            {
                Tile farWallTile = ChapelOfAshSceneBuilder.LoadOrCreateFarWallTile(folderPath);
                Tile cutawayWallTile = ChapelOfAshSceneBuilder.LoadOrCreateCutawayWallTile(folderPath);

                Sprite expectedFarWallSprite = AssetDatabase.LoadAssetAtPath<Sprite>(
                    "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_straight.png");
                Sprite expectedCutawaySprite = AssetDatabase.LoadAssetAtPath<Sprite>(
                    "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_broken_stub.png");
                Assert.IsNotNull(expectedFarWallSprite);
                Assert.IsNotNull(expectedCutawaySprite);

                Assert.AreSame(expectedFarWallSprite, farWallTile.sprite);
                Assert.AreSame(expectedCutawaySprite, cutawayWallTile.sprite);
                Assert.AreEqual(Tile.ColliderType.None, farWallTile.colliderType);
                Assert.AreEqual(Tile.ColliderType.None, cutawayWallTile.colliderType);
            }
            finally
            {
                AssetDatabase.DeleteAsset(folderPath);
            }
        }

        // NSC-109 AC-001/VAL-001 (regression-only, supersedes the NSC-046 pixel-content-staleness
        // regression this replaces): a stale sprite reference on an already-persisted wall Tile
        // asset must be repaired back to the committed source sprite on the next build. This never
        // mutates the committed source sprite's own pixel data - only the generated Tile asset's
        // own sprite reference.
        [Test]
        public void WallTile_RepairsAStaleSpriteReferenceAndReusesCorrectAsset()
        {
            string folderName = "__NSC109ChapelWallRepair_" + Guid.NewGuid().ToString("N");
            string folderPath = "Assets/" + folderName;
            AssetDatabase.CreateFolder("Assets", folderName);
            try
            {
                Tile tile = ChapelOfAshSceneBuilder.LoadOrCreateFarWallTile(folderPath);
                string assetPath = folderPath + "/ChapelOfAshFarWallTile.asset";
                string guid = AssetDatabase.AssetPathToGUID(assetPath);
                Assert.IsNotEmpty(guid);

                Sprite expectedSprite = AssetDatabase.LoadAssetAtPath<Sprite>(
                    "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_straight.png");
                Sprite staleSprite = AssetDatabase.LoadAssetAtPath<Sprite>(
                    "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_corner.png");
                Assert.IsNotNull(expectedSprite);
                Assert.IsNotNull(staleSprite);
                Assert.AreSame(expectedSprite, tile.sprite);

                tile.sprite = staleSprite;
                EditorUtility.SetDirty(tile);
                AssetDatabase.SaveAssetIfDirty(tile);

                Tile repaired = ChapelOfAshSceneBuilder.LoadOrCreateFarWallTile(folderPath);
                Assert.AreSame(tile, repaired);
                Assert.AreEqual(guid, AssetDatabase.AssetPathToGUID(assetPath));
                Assert.AreSame(expectedSprite, repaired.sprite,
                    "A stale sprite reference must be repaired back to the committed wall_straight " +
                    "sprite on the next build.");
                Assert.AreSame(repaired, ChapelOfAshSceneBuilder.LoadOrCreateFarWallTile(folderPath));
            }
            finally
            {
                AssetDatabase.DeleteAsset(folderPath);
            }
        }

        [Test] // AC-004
        public void PaintStraightWallRun_ReusesOneTileWithoutGapsAtThreeScales()
        {
            GameObject wallObject = new GameObject("ChapelWallRunTest", typeof(Tilemap), typeof(TilemapRenderer));
            Tile tile = ScriptableObject.CreateInstance<Tile>();
            try
            {
                Tilemap tilemap = wallObject.GetComponent<Tilemap>();
                foreach (int count in new[] { 3, 10, 100 })
                {
                    tilemap.ClearAllTiles();
                    ChapelOfAshSceneBuilder.PaintStraightWallRun(tilemap, tile, 0, count);
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

        // ---- AC-006: catalog verification (this task edits neither representation) ----

        [Test] // AC-006
        public void Catalog_RecordsApprovedChapelBoundsAndDoorsWithoutDisturbingOtherEntries()
        {
            RoomSceneCatalog.RoomCatalogEntry[] sourceRooms = RoomSceneCatalog.CreateCanonicalRooms();
            RoomSceneCatalog.DoorSequenceEntry[] sourceDoors = RoomSceneCatalog.CreateCanonicalDoors();
            RoomSceneCatalog generatedCatalog = AssetDatabase.LoadAssetAtPath<RoomSceneCatalog>(RoomSceneCatalog.AssetPath);
            Assert.IsNotNull(generatedCatalog);

            AssertCatalogMatches(sourceRooms, sourceDoors);
            AssertCatalogMatches(generatedCatalog.Rooms.ToArray(), generatedCatalog.Doors.ToArray());
        }

        // ---- shared helpers ----

        private static GameObject FindRoomRoot(Scene scene)
        {
            return scene.GetRootGameObjects().Single(candidate => candidate.name == "Room_ChapelOfAsh");
        }

        private static Transform FindGrid(Scene scene)
        {
            Transform grid = FindRoomRoot(scene).transform.Find("Visuals/IsometricZAsY");
            Assert.IsNotNull(grid);
            return grid;
        }

        private static Tilemap RequireTilemap(Transform grid, string name)
        {
            Tilemap tilemap = grid.Find(name)?.GetComponent<Tilemap>();
            Assert.IsNotNull(tilemap, $"Expected Visuals/IsometricZAsY/{name}.");
            return tilemap;
        }

        private static Tilemap RequireTilemapConfiguration(
            Transform grid, string name, Vector3 localPosition, Quaternion localRotation, int sortingOrder)
        {
            Tilemap tilemap = RequireTilemap(grid, name);
            Assert.That(Vector3.Distance(tilemap.transform.localPosition, localPosition), Is.LessThan(0.001f),
                $"{name} local position mismatch.");
            Assert.That(Quaternion.Angle(tilemap.transform.localRotation, localRotation), Is.LessThan(0.001f),
                $"{name} local rotation mismatch.");
            Assert.AreEqual(Vector3.zero, tilemap.tileAnchor);
            Assert.AreEqual(Tilemap.Orientation.XY, tilemap.orientation);

            TilemapRenderer renderer = tilemap.GetComponent<TilemapRenderer>();
            Assert.IsNotNull(renderer);
            Assert.AreEqual(TilemapRenderer.Mode.Individual, renderer.mode);
            Assert.AreEqual(TilemapRenderer.SortOrder.TopRight, renderer.sortOrder);
            Assert.AreEqual(WorldSpriteConvention.SortingLayerName, renderer.sortingLayerName);
            Assert.AreEqual(sortingOrder, renderer.sortingOrder);
            return tilemap;
        }

        private static void AssertWallCellSet(Tilemap tilemap, TileBase tile, params int[] ranges)
        {
            int expected = 0;
            for (int index = 0; index < ranges.Length; index += 2)
            {
                for (int cell = ranges[index]; cell <= ranges[index + 1]; cell++)
                {
                    Assert.AreSame(tile, tilemap.GetTile(new Vector3Int(cell, 0, 0)),
                        $"{tilemap.name} is missing its painted cell {cell}.");
                    expected++;
                }
            }

            int actual = 0;
            foreach (Vector3Int cell in tilemap.cellBounds.allPositionsWithin)
            {
                if (tilemap.HasTile(cell)) actual++;
            }
            Assert.AreEqual(expected, actual, $"{tilemap.name} has extra or missing painted cells.");
        }

        private static void AssertNoTileInWorldRange(Tilemap tilemap, float minX, float maxX)
        {
            foreach (Vector3Int cell in tilemap.cellBounds.allPositionsWithin)
            {
                if (!tilemap.HasTile(cell)) continue;
                float pivotX = tilemap.CellToWorld(cell).x;
                float spriteMinX = pivotX - 0.5f;
                float spriteMaxX = pivotX + 0.5f;
                Assert.IsFalse(spriteMinX < maxX && spriteMaxX > minX,
                    $"{tilemap.name} paints a sprite overlapping the clear interval [{minX},{maxX}] at cell {cell}.");
            }
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

        private static void RequireBlockoutSprite(Transform visuals, string name)
        {
            Transform child = visuals.Find(name);
            Assert.IsNotNull(child, $"Expected Visuals/{name}.");
            SpriteRenderer renderer = child.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(renderer, $"Expected {name} to carry a SpriteRenderer.");
            Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint);
            Assert.AreEqual(WorldSpriteConvention.SortingLayerName, renderer.sortingLayerName);
            Assert.AreEqual(0, renderer.sortingOrder);
            Assert.IsNull(child.GetComponent<Collider>());
        }

        private static BoxCollider RequireCollider(Transform parent, string name)
        {
            BoxCollider collider = parent.Find(name)?.GetComponent<BoxCollider>();
            Assert.IsNotNull(collider, $"Expected {parent.name}/{name} BoxCollider.");
            return collider;
        }

        private static void AssertBoundsXZ(Bounds bounds, float minX, float maxX, float minZ, float maxZ)
        {
            Assert.That(bounds.min.x, Is.EqualTo(minX).Within(0.001f));
            Assert.That(bounds.max.x, Is.EqualTo(maxX).Within(0.001f));
            Assert.That(bounds.min.z, Is.EqualTo(minZ).Within(0.001f));
            Assert.That(bounds.max.z, Is.EqualTo(maxZ).Within(0.001f));
        }

        private static bool OverlapsXZ(Bounds a, Bounds b)
        {
            return a.min.x < b.max.x && a.max.x > b.min.x && a.min.z < b.max.z && a.max.z > b.min.z;
        }

        private static void AssertPewFootprint(Bounds pew, float minX, float maxX, float minZ, float maxZ)
        {
            Assert.That(pew.min.x, Is.EqualTo(minX));
            Assert.That(pew.max.x, Is.EqualTo(maxX));
            Assert.That(pew.min.z, Is.EqualTo(minZ));
            Assert.That(pew.max.z, Is.EqualTo(maxZ));
        }

        private static void AssertCatalogMatches(
            RoomSceneCatalog.RoomCatalogEntry[] rooms, RoomSceneCatalog.DoorSequenceEntry[] doors)
        {
            Assert.AreEqual(5, rooms.Length);
            Assert.AreEqual(5, doors.Length);

            RoomId[] expectedRoomIds =
            {
                RoomId.RuinedEntry, RoomId.BoneArchive, RoomId.ChapelOfAsh, RoomId.LowerVault, RoomId.FinalRoom
            };
            string[] expectedPaths =
            {
                "Assets/Scenes/Rooms/RuinedEntry.unity", "Assets/Scenes/Rooms/BoneArchive.unity",
                "Assets/Scenes/Rooms/ChapelOfAsh.unity", "Assets/Scenes/Rooms/LowerVault.unity",
                "Assets/Scenes/Rooms/FinalRoom.unity"
            };
            float[] expectedMinX = { -14f, -12f, -18f, -20f, -15f };
            float[] expectedMaxX = { 14f, 12f, 18f, 20f, 15f };
            float[] expectedMinZ = { -26f, 0f, 20f, 54f, 76f };
            float[] expectedMaxZ = { 0f, 20f, 54f, 76f, 104f };
            for (int index = 0; index < 5; index++)
            {
                Assert.AreEqual(expectedRoomIds[index], rooms[index].RoomId);
                Assert.AreEqual(expectedPaths[index], rooms[index].SceneAssetPath);
                Assert.AreEqual(expectedMinX[index], rooms[index].Bounds.MinX);
                Assert.AreEqual(expectedMaxX[index], rooms[index].Bounds.MaxX);
                Assert.AreEqual(expectedMinZ[index], rooms[index].Bounds.MinZ);
                Assert.AreEqual(expectedMaxZ[index], rooms[index].Bounds.MaxZ);
            }

            DoorId[] expectedDoorIds = { DoorId.D1, DoorId.D2, DoorId.D3, DoorId.D4, DoorId.D5 };
            RoomId[] expectedExitRooms =
            {
                RoomId.RuinedEntry, RoomId.BoneArchive, RoomId.ChapelOfAsh, RoomId.LowerVault, RoomId.FinalRoom
            };
            RoomId[] expectedEntryRooms =
            {
                RoomId.BoneArchive, RoomId.ChapelOfAsh, RoomId.LowerVault, RoomId.FinalRoom, RoomId.FinalRoom
            };
            Vector2[] expectedGroundCenters =
            {
                new Vector2(0f, 0f), new Vector2(6f, 20f), new Vector2(-8f, 54f),
                new Vector2(4f, 76f), new Vector2(0f, 104f)
            };
            for (int index = 0; index < 5; index++)
            {
                Assert.AreEqual(expectedDoorIds[index], doors[index].DoorId);
                Assert.AreEqual(expectedExitRooms[index], doors[index].ExitRoom);
                Assert.AreEqual(expectedEntryRooms[index], doors[index].EntryRoom);
                Assert.AreEqual(expectedGroundCenters[index], doors[index].ExpectedGroundCenter);
                Assert.AreEqual(3f, doors[index].OpeningWidth);
                Assert.AreEqual(index == 4, doors[index].IsFinal);
            }
        }
    }
}
