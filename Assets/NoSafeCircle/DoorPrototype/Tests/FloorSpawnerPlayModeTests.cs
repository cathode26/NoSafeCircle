using System;
using System.Collections;
using System.IO;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.Tilemaps;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Proves the FLOORS lane end to end AT RUNTIME, with no bake and no scene mutation: the SHIPPED
    // FloorSpawner prefab paints five floors from the committed Tiles and the layouts at Play, they
    // carry the contract-pinned Grid/Tilemap configuration, and each has a physics floor to stand on.
    //
    // EVERY EXPECTED VALUE COMES FROM SOMEWHERE OTHER THAN THE THING UNDER TEST. Extents come from
    // the *Layout.cs classes directly, never from FloorSpawner.TryGetRoomBounds; counts are
    // recomputed from those extents and the Grid's cell size; the configuration is asserted as
    // LITERALS because those literals pin a contract, and reading them from the prefab would agree
    // by construction. A frozen "8,304" would keep passing while the layouts said something else;
    // nothing here freezes it.
    //
    // THE FIXTURE USES THE SHIPPED PREFAB (Resources/Spawners/FloorSpawner.prefab), so the
    // serialized bindings are under test, not a fixture-built copy of them.
    public sealed class FloorSpawnerPlayModeTests
    {
        private const string SpawnerResourcePath = "Spawners/FloorSpawner";
        private const string FloorTilemapName = "FloorTilemap";
        private const string FloorCollisionName = "FloorCollision";
        private const string MapPath = "Assets/NoSafeCircle/DoorPrototype/Content/Levels/floor01.txt";
        private const string TileFolder = "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";
        private const string FloorSpriteFolder = "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors";

        // THE CONTRACT-PINNED CONFIGURATION, AS LITERALS. NSC-046 and NSC-048 AC-003 pin the Grid
        // and FloorTilemap prose per room; these are those numbers, and the five editor builders
        // agree with them line for line. The two SORTING values are NOT from the contract: the
        // contract's "-100" predates NSC-100, and the live values come from
        // WorldSpriteConvention.cs - SortingLayerName ("WorldSprites") and
        // BackgroundGroundSortingOrder (short.MinValue). They are written as literals here for the
        // same reason as the rest, and one assertion checks the convention still says the same, so
        // a drift is reported at its source rather than at each of five renderers.
        private static readonly Vector3 PinnedCellSize = new Vector3(1f, 0.5f, 1f);
        private static readonly Vector3 PinnedTilemapLocalPosition = new Vector3(0f, 0.01f, 0f);
        private static readonly Vector3 PinnedTilemapLocalEuler = new Vector3(-90f, 0f, 0f);
        private const string PinnedSortingLayerName = "WorldSprites";
        private const int PinnedFloorSortingOrder = short.MinValue;

        private static readonly RoomId[] AllRooms = (RoomId[])Enum.GetValues(typeof(RoomId));

        private GameObject spawnerObject;

        [TearDown]
        public void TearDown()
        {
            if (spawnerObject != null)
            {
                Object.Destroy(spawnerObject);
                spawnerObject = null;
            }
        }

        // EXPECTED EXTENTS COME FROM THE LAYOUTS DIRECTLY, never from FloorSpawner.TryGetRoomBounds:
        // an expectation read from the thing under test agrees with it by construction. This switch
        // is the second, independent copy on purpose.
        private static Bounds LayoutBounds(RoomId room)
        {
            switch (room)
            {
                case RoomId.RuinedEntry: return RuinedEntryLayout.RoomBounds;
                case RoomId.BoneArchive: return BoneArchiveLayout.RoomBounds;
                case RoomId.ChapelOfAsh: return ChapelOfAshLayout.RoomBounds;
                case RoomId.LowerVault: return LowerVaultLayout.RoomBounds;
                case RoomId.FinalRoom: return FinalRoomLayout.RoomBounds;
                default:
                    throw new ArgumentOutOfRangeException(nameof(room), room,
                        "No layout for this room. Add it here AND in FloorSpawner.TryGetRoomBounds.");
            }
        }

        private FloorSpawner SpawnShippedPrefab()
        {
            GameObject prefab = Resources.Load<GameObject>(SpawnerResourcePath);
            Assert.IsNotNull(prefab,
                "Resources/" + SpawnerResourcePath + ".prefab did not load. The folder is the "
                + "registry; a spawner that is not there is a family that never appears.");

            spawnerObject = Object.Instantiate(prefab);
            spawnerObject.name = "FloorSpawnerUnderTest";
            var spawner = spawnerObject.GetComponent<FloorSpawner>();
            Assert.IsNotNull(spawner, "The shipped prefab carries no FloorSpawner component.");
            return spawner;
        }

        private Transform RoomFloor(RoomId room)
        {
            Transform floor = spawnerObject.transform.Find(room + "Floor");
            Assert.IsNotNull(floor, "No '" + room + "Floor' was spawned for " + room + ".");
            return floor;
        }

        private Tilemap RoomTilemap(RoomId room)
        {
            Transform tilemapObject = RoomFloor(room).Find(FloorTilemapName);
            Assert.IsNotNull(tilemapObject, room + "Floor has no '" + FloorTilemapName + "' child.");
            var tilemap = tilemapObject.GetComponent<Tilemap>();
            Assert.IsNotNull(tilemap, room + "Floor/" + FloorTilemapName + " carries no Tilemap.");
            return tilemap;
        }

        /// The test's own statement of "the whole cell lies inside the room": the corner is the
        /// cell's ORIGIN corner (tileAnchor zero) and the -90 degree tilemap covers world Z
        /// DOWNWARD from it by cellSize.y. Written here rather than calling
        /// FloorSpawner.CellFootprintIsInside, so the painter and the predicate can drift from THIS
        /// and be caught, instead of drifting together.
        private static bool ExpectedInside(Vector3 corner, Vector3 cellSize, Bounds bounds)
        {
            const float tolerance = 0.001f;
            return corner.x >= bounds.min.x - tolerance
                && corner.x + cellSize.x <= bounds.max.x + tolerance
                && corner.z - cellSize.y >= bounds.min.z - tolerance
                && corner.z <= bounds.max.z + tolerance;
        }

        private static int CountPainted(Tilemap tilemap)
        {
            int painted = 0;
            foreach (Vector3Int cell in tilemap.cellBounds.allPositionsWithin)
            {
                if (tilemap.HasTile(cell))
                {
                    painted++;
                }
            }

            return painted;
        }

        /// WorldToCell on the -90 degree tilemap returns z = -1 for any point at world y = 0,
        /// because the tilemap sits 0.01 above the ground and local z is world y. Tiles live at
        /// z = 0, so a lookup that keeps WorldToCell's z reads an empty layer and a negative control
        /// passes for the wrong reason. Flatten it.
        private static Vector3Int CellUnder(Tilemap tilemap, float worldX, float worldZ)
        {
            Vector3Int cell = tilemap.WorldToCell(new Vector3(worldX, 0f, worldZ));
            return new Vector3Int(cell.x, cell.y, 0);
        }

        private static void AssertVector(Vector3 expected, Vector3 actual, float tolerance, string what)
        {
            Assert.AreEqual(expected.x, actual.x, tolerance, what + " x: expected " + expected + ", got " + actual);
            Assert.AreEqual(expected.y, actual.y, tolerance, what + " y: expected " + expected + ", got " + actual);
            Assert.AreEqual(expected.z, actual.z, tolerance, what + " z: expected " + expected + ", got " + actual);
        }

        [UnityTest]
        public IEnumerator Spawn_PaintsExactlyTheCellsWhoseFootprintLiesInsideEachRoomsLayoutBounds()
        {
            FloorSpawner spawner = SpawnShippedPrefab();
            int spawned = spawner.Spawn();
            yield return null;

            Assert.AreEqual(AllRooms.Length, spawned,
                "FloorSpawner spawned " + spawned + " of " + AllRooms.Length + " room floors. A "
                + "shortfall means a binding is missing or its Tile did not resolve; the console "
                + "errors name the room.");

            int total = 0;
            foreach (RoomId room in AllRooms)
            {
                Tilemap tilemap = RoomTilemap(room);
                Bounds bounds = LayoutBounds(room);
                Vector3 cellSize = tilemap.layoutGrid.cellSize;

                // RECOMPUTED, NOT FROZEN: columns and rows from the layout's extent at the Grid's
                // cell size. cellSize.y divides the Z extent because the tilemap's local y IS
                // world z. First-run check values: 1,456 / 960 / 2,448 / 1,760 / 1,680, sum 8,304.
                int expectedColumns = Mathf.RoundToInt(bounds.size.x / cellSize.x);
                int expectedRows = Mathf.RoundToInt(bounds.size.z / cellSize.y);
                int expected = expectedColumns * expectedRows;
                Assert.Greater(expected, 0, room + ": the layout implies zero cells, so this would pass vacuously.");

                int painted = CountPainted(tilemap);
                Assert.AreEqual(expected, painted,
                    room + ": painted " + painted + " cells; the layout " + bounds.min + ".." + bounds.max
                    + " at cell size " + cellSize + " implies " + expectedColumns + " x " + expectedRows
                    + " = " + expected + ".");

                // THE SET, NOT ONLY THE COUNT. A band painted one cell out of place keeps the
                // count exactly, which is the defect two of the editor builders once had.
                foreach (Vector3Int cell in tilemap.cellBounds.allPositionsWithin)
                {
                    Vector3 corner = tilemap.GetCellCenterWorld(cell);
                    bool shouldPaint = ExpectedInside(corner, cellSize, bounds);
                    Assert.AreEqual(shouldPaint, tilemap.HasTile(cell),
                        room + ": cell " + cell + " at corner " + corner
                        + (shouldPaint ? " lies inside the layout and is not painted."
                                       : " lies outside the layout and is painted."));
                }

                // CONTROLS, from points strictly inside the cells they name so no boundary is
                // read: the cell just west of the north-west corner and the cell just north of it
                // must be empty; the north-west corner cell itself must be painted.
                Vector3Int westOfRoom = CellUnder(tilemap, bounds.min.x - 0.5f * cellSize.x, bounds.max.z - 0.5f * cellSize.y);
                Vector3Int northOfRoom = CellUnder(tilemap, bounds.min.x + 0.5f * cellSize.x, bounds.max.z + 0.5f * cellSize.y);
                Vector3Int northWest = CellUnder(tilemap, bounds.min.x + 0.5f * cellSize.x, bounds.max.z - 0.5f * cellSize.y);
                Assert.IsFalse(tilemap.HasTile(westOfRoom), room + ": the cell west of the room, " + westOfRoom + ", is painted.");
                Assert.IsFalse(tilemap.HasTile(northOfRoom), room + ": the cell north of the room, " + northOfRoom + ", is painted.");
                Assert.IsTrue(tilemap.HasTile(northWest), room + ": the north-west corner cell " + northWest + " is not painted, so the controls prove nothing.");

                total += painted;
            }

            Assert.AreEqual(total, spawner.PaintedCellCount,
                "FloorSpawner reports " + spawner.PaintedCellCount + " painted cells; the tilemaps hold " + total + ".");
        }

#if UNITY_EDITOR
        [UnityTest]
        public IEnumerator Spawn_PaintedCellsAgreeWithTheAsciiMapUnderEachRoomsLayoutRect()
        {
            // THE MAP IS A WITNESS HERE, NOT AN INPUT. FloorSpawner does not read floor01.txt: the
            // layout is the extent, and Floor01AsciiMapTests proves the map's rectangle contains
            // it. This test binds the painted floor to the map's TOPOLOGY anyway - every painted
            // tile cell sits under a non-Outside map cell, and every non-Outside map cell inside a
            // room's layout rectangle has its tile cells painted - so the day a room stops being a
            // rectangle, this is the test that says the floor and the map disagree.
            //
            // THE MAP'S FRAME IS DERIVED FROM THE LAYOUTS, not declared: origin (min X, max Z)
            // over all rooms, and dimensions = extent / AsciiRoomMap.WorldUnitsPerCell.
            // Floor01AsciiMapTests pins the same arithmetic to 20 x 65 at origin (-20, 104).
            FloorSpawner spawner = SpawnShippedPrefab();
            spawner.Spawn();
            yield return null;

            float originX = float.MaxValue, maxX = float.MinValue, originZ = float.MinValue, minZ = float.MaxValue;
            foreach (RoomId room in AllRooms)
            {
                Bounds b = LayoutBounds(room);
                originX = Mathf.Min(originX, b.min.x);
                maxX = Mathf.Max(maxX, b.max.x);
                originZ = Mathf.Max(originZ, b.max.z);
                minZ = Mathf.Min(minZ, b.min.z);
            }

            float unitsPerMapCell = AsciiRoomMap.WorldUnitsPerCell;
            int columns = Mathf.RoundToInt((maxX - originX) / unitsPerMapCell);
            int rows = Mathf.RoundToInt((originZ - minZ) / unitsPerMapCell);

            Assert.IsTrue(File.Exists(MapPath), MapPath + " does not exist; the map witness is missing.");
            Assert.IsTrue(AsciiRoomMap.TryParse(File.ReadAllText(MapPath), columns, rows, out AsciiRoomMap map, out string error),
                MapPath + " did not parse as " + columns + "x" + rows + ": " + error);

            int total = 0;
            foreach (RoomId room in AllRooms)
            {
                Tilemap tilemap = RoomTilemap(room);
                Bounds bounds = LayoutBounds(room);
                Vector3 cellSize = tilemap.layoutGrid.cellSize;

                // ONE MAP CELL IS A BLOCK OF TILE CELLS, AND THE BLOCK'S SHAPE IS DERIVED, NOT
                // ASSUMED. A map cell is AsciiRoomMap.WorldUnitsPerCell (2) world units on each
                // side. A tile cell is cellSize.x (1) world units along X but cellSize.y (0.5)
                // world units along Z, because the -90 degree tilemap lays its local y along
                // world z. So one map cell is 2 / 1 = 2 tile columns by 2 / 0.5 = 4 tile rows: a
                // 2 x 4 block, NOT the 2 x 2 a square tile cell would give. Both divisions must be
                // exact, or "the tiles under a map cell" is not a well-defined set.
                float columnsPerMapCell = unitsPerMapCell / cellSize.x;
                float rowsPerMapCell = unitsPerMapCell / cellSize.y;
                Assert.AreEqual(Mathf.Round(columnsPerMapCell), columnsPerMapCell, 0.0001f,
                    "A map cell is " + columnsPerMapCell + " tile columns wide, not a whole number.");
                Assert.AreEqual(Mathf.Round(rowsPerMapCell), rowsPerMapCell, 0.0001f,
                    "A map cell is " + rowsPerMapCell + " tile rows deep, not a whole number.");

                int expected = 0;
                foreach (Vector3Int cell in tilemap.cellBounds.allPositionsWithin)
                {
                    Vector3 corner = tilemap.GetCellCenterWorld(cell);

                    // The tile cell's CENTRE, so a footprint touching a map-cell boundary reads the
                    // map cell it is actually in rather than its neighbour.
                    AsciiCellIndex at = map.ToCell(corner.x + 0.5f * cellSize.x, corner.z - 0.5f * cellSize.y, originX, originZ);
                    bool inMap = at.Column >= 0 && at.Column < map.Width && at.Row >= 0 && at.Row < map.Height
                        && map[at.Column, at.Row] != AsciiCell.Outside;
                    bool shouldPaint = inMap && ExpectedInside(corner, cellSize, bounds);
                    if (shouldPaint)
                    {
                        expected++;
                    }

                    Assert.AreEqual(shouldPaint, tilemap.HasTile(cell),
                        room + ": cell " + cell + " at corner " + corner + " is under map cell " + at
                        + (inMap ? " (" + map[at.Column, at.Row] + ")" : " (off the map)")
                        + " and " + (shouldPaint ? "should be painted but is not." : "is painted but should not be."));
                }

                Assert.Greater(expected, 0, room + ": the map and the layout together imply zero cells.");
                Assert.AreEqual(expected, CountPainted(tilemap),
                    room + ": the map and the layout imply " + expected + " painted cells; the tilemap holds " + CountPainted(tilemap) + ".");
                total += expected;
            }

            Assert.AreEqual(total, spawner.PaintedCellCount,
                "The map-and-layout recount is " + total + "; FloorSpawner reports " + spawner.PaintedCellCount + ".");
        }
#endif

        [UnityTest]
        public IEnumerator EveryFloorTilemapCarriesTheContractPinnedConfiguration()
        {
            FloorSpawner spawner = SpawnShippedPrefab();
            spawner.Spawn();
            yield return null;

            // The literal pins and the runtime convention must agree, or the pins below would be
            // checking a value the game no longer uses.
            Assert.AreEqual(PinnedSortingLayerName, WorldSpriteConvention.SortingLayerName,
                "WorldSpriteConvention.SortingLayerName moved away from the literal this fixture pins.");
            Assert.AreEqual(PinnedFloorSortingOrder, WorldSpriteConvention.BackgroundGroundSortingOrder,
                "WorldSpriteConvention.BackgroundGroundSortingOrder moved away from the literal this fixture pins.");

            Tilemap[] tilemaps = spawnerObject.GetComponentsInChildren<Tilemap>(true);
            Assert.AreEqual(AllRooms.Length, tilemaps.Length,
                "Expected exactly one floor Tilemap per room (" + AllRooms.Length + "); found " + tilemaps.Length + ".");

            foreach (Tilemap tilemap in tilemaps)
            {
                string who = tilemap.transform.parent.name + "/" + tilemap.name;
                Assert.AreEqual(FloorTilemapName, tilemap.name, who + " is not named " + FloorTilemapName + ".");

                Grid grid = tilemap.layoutGrid;
                Assert.IsNotNull(grid, who + " has no Grid above it.");
                AssertVector(PinnedCellSize, grid.cellSize, 0.0001f, who + " Grid.cellSize");
                Assert.AreEqual(GridLayout.CellSwizzle.XYZ, grid.cellSwizzle, who + " Grid.cellSwizzle");
                Assert.AreEqual(GridLayout.CellLayout.Rectangle, grid.cellLayout,
                    who + " Grid.cellLayout is " + grid.cellLayout + ". The contract leaves it at Rectangle: the "
                    + "isometric projection comes from the camera, and an isometric layout would project it twice.");
                Assert.AreEqual(0f, grid.transform.position.magnitude, 0.0001f,
                    who + ": the Grid is at " + grid.transform.position + ", not the origin, so cell coordinates are not world coordinates.");
                Assert.Less(Quaternion.Angle(Quaternion.identity, grid.transform.rotation), 0.01f,
                    who + ": the Grid is rotated; the floor tilemap's own -90 degrees is the only rotation in the chain.");

                AssertVector(Vector3.zero, tilemap.tileAnchor, 0.0001f, who + " tileAnchor");
                Assert.AreEqual(Tilemap.Orientation.XY, tilemap.orientation, who + " orientation");
                AssertVector(PinnedTilemapLocalPosition, tilemap.transform.localPosition, 0.0001f, who + " localPosition");
                Assert.Less(Quaternion.Angle(Quaternion.Euler(PinnedTilemapLocalEuler), tilemap.transform.localRotation), 0.01f,
                    who + " localRotation is " + tilemap.transform.localRotation.eulerAngles + ", not Euler" + PinnedTilemapLocalEuler + ".");
                AssertVector(Vector3.one, tilemap.transform.localScale, 0.0001f, who + " localScale");

                var renderer = tilemap.GetComponent<TilemapRenderer>();
                Assert.IsNotNull(renderer, who + " has no TilemapRenderer, so the floor is painted and invisible.");
                Assert.AreEqual(TilemapRenderer.Mode.Individual, renderer.mode, who + " renderer.mode");
                Assert.AreEqual(TilemapRenderer.SortOrder.TopRight, renderer.sortOrder, who + " renderer.sortOrder");
                Assert.AreEqual(PinnedSortingLayerName, renderer.sortingLayerName,
                    who + " is on sorting layer '" + renderer.sortingLayerName + "'. The LAYER is compared before "
                    + "the order; a floor on Default draws behind everything whatever number it carries.");
                Assert.AreEqual(PinnedFloorSortingOrder, renderer.sortingOrder,
                    who + " carries sortingOrder " + renderer.sortingOrder + ". The floor sits at the bottom of what "
                    + "Unity can represent so every world sprite - and the architectural border at +10 - draws over it.");
            }

            Assert.AreEqual(0, spawnerObject.GetComponentsInChildren<TilemapCollider2D>(true).Length,
                "A floor carries a TilemapCollider2D. The floor's physics is the FloorCollision box; a 2D "
                + "collider in a 3D world is dead weight that reads as collision.");
        }

        [UnityTest]
        public IEnumerator EachRoomIsPaintedWithItsOwnCommittedTileAndOneTileFillsOneCell()
        {
            FloorSpawner spawner = SpawnShippedPrefab();
            spawner.Spawn();
            yield return null;

            foreach (RoomId room in AllRooms)
            {
                Tilemap tilemap = RoomTilemap(room);
                Vector3 cellSize = tilemap.layoutGrid.cellSize;

                Tile first = null;
                int painted = 0;
                foreach (Vector3Int cell in tilemap.cellBounds.allPositionsWithin)
                {
                    if (!tilemap.HasTile(cell))
                    {
                        continue;
                    }

                    TileBase at = tilemap.GetTile(cell);
                    if (first == null)
                    {
                        first = at as Tile;
                        Assert.IsNotNull(first, room + ": the painted tile is a " + at.GetType().Name + ", not a Tile.");
                    }
                    else
                    {
                        Assert.AreSame(first, at, room + ": cell " + cell + " holds a different tile from the first painted cell.");
                    }

                    painted++;
                }

                Assert.Greater(painted, 0, room + ": nothing painted, so this passes vacuously.");
                Assert.IsNotNull(first.sprite, room + ": the floor Tile has no sprite. It renders nothing.");

#if UNITY_EDITOR
                // THE TILE IS THE COMMITTED ASSET, loaded and never created: it has an asset path,
                // and the path is the room's own. A runtime CreateInstance<Tile>() has no path.
                Assert.AreEqual(TileFolder + "/" + room + "FloorTile.asset", UnityEditor.AssetDatabase.GetAssetPath(first),
                    room + ": the painted Tile is not the committed " + room + "FloorTile.asset. Either a binding "
                    + "points at another room's tile, or something created a tile at runtime.");
                Assert.AreEqual(FloorSpriteFolder + "/floor_" + room + ".png", UnityEditor.AssetDatabase.GetAssetPath(first.sprite),
                    room + ": the Tile's sprite is not the room's committed floor art.");
#endif

                // ONE TILE FILLS ONE CELL WITHOUT SCALING: the sprite's size in world units, from
                // its import settings, equals the Grid's cell. That relation is what makes the floor
                // seamless, and it is a property of the import and the Grid, not of the painter.
                float pixelsPerUnit = first.sprite.pixelsPerUnit;
                Assert.AreEqual(cellSize.x, first.sprite.rect.width / pixelsPerUnit, 0.0001f,
                    room + ": the floor sprite is " + first.sprite.rect.width / pixelsPerUnit + " units wide; a cell is " + cellSize.x + ".");
                Assert.AreEqual(cellSize.y, first.sprite.rect.height / pixelsPerUnit, 0.0001f,
                    room + ": the floor sprite is " + first.sprite.rect.height / pixelsPerUnit + " units tall; a cell is " + cellSize.y + ".");
            }
        }

        [UnityTest]
        public IEnumerator FloorCollisionMatchesLayoutBoundsAndTopsAtTheLayoutsGround()
        {
            FloorSpawner spawner = SpawnShippedPrefab();
            spawner.Spawn();
            yield return null;
            Physics.SyncTransforms();

            Collider[] all = spawnerObject.GetComponentsInChildren<Collider>(true);
            Assert.AreEqual(AllRooms.Length, all.Length,
                "Expected exactly one collider per room (" + AllRooms.Length + ") under the floor spawner; found "
                + all.Length + ". Walls and their colliders belong to the wall lane, not here.");

            foreach (RoomId room in AllRooms)
            {
                Bounds layout = LayoutBounds(room);
                Transform floor = RoomFloor(room);
                Assert.AreEqual(1, floor.GetComponentsInChildren<Collider>(true).Length, room + "Floor carries more than one collider.");

                Transform collisionObject = floor.Find(FloorCollisionName);
                Assert.IsNotNull(collisionObject, room + "Floor has no '" + FloorCollisionName + "' child.");
                var box = collisionObject.GetComponent<BoxCollider>();
                Assert.IsNotNull(box, room + "Floor/" + FloorCollisionName + " carries no BoxCollider.");
                Assert.IsFalse(box.isTrigger, room + ": FloorCollision is a trigger. A CharacterController falls through a trigger.");
                Assert.IsTrue(box.enabled, room + ": FloorCollision is disabled.");

                Bounds world = box.bounds;
                Assert.AreEqual(layout.min.x, world.min.x, 0.001f, room + " FloorCollision west edge");
                Assert.AreEqual(layout.max.x, world.max.x, 0.001f, room + " FloorCollision east edge");
                Assert.AreEqual(layout.min.z, world.min.z, 0.001f, room + " FloorCollision south edge");
                Assert.AreEqual(layout.max.z, world.max.z, 0.001f, room + " FloorCollision north edge");

                // THE INVARIANT: the top face is the layout's ground plane. Derived from the layout
                // (every RoomBounds has zero height at y = 0), not from the collider's own centre
                // and size, so a 0.1-thick box at the wrong height fails and a 0.5-thick box at the
                // right height - Bone Archive's old shape - would pass. The thickness is a detail
                // and is deliberately not pinned.
                Assert.AreEqual(layout.max.y, world.max.y, 0.001f,
                    room + ": the FloorCollision top face is at y " + world.max.y + ", not the layout's ground "
                    + layout.max.y + ". The navmesh bakes onto this face and the wizard stands on it.");
                Assert.Greater(world.size.y, 0f, room + ": FloorCollision has no thickness at all.");

                // A PHYSICS PROOF, ON THIS COLLIDER ALONE so nothing else in the test scene can
                // answer for it: a ray dropped from above the room's centre hits its top face at
                // the ground.
                var ray = new Ray(new Vector3(layout.center.x, layout.max.y + 1f, layout.center.z), Vector3.down);
                Assert.IsTrue(box.Raycast(ray, out RaycastHit hit, 2f),
                    room + ": a ray dropped onto the FloorCollision from one unit above its centre hit nothing.");
                Assert.AreEqual(layout.max.y, hit.point.y, 0.001f,
                    room + ": the ray landed at y " + hit.point.y + ", not on the ground.");
            }
        }

        [UnityTest]
        public IEnumerator SpawningTwiceLeavesFiveTilemapsFiveCollidersAndTheSameCellCount()
        {
            FloorSpawner spawner = SpawnShippedPrefab();
            Assert.AreEqual(-1, spawner.SpawnedCount, "SpawnedCount before Spawn() must be -1, distinguishable from a spawn that created nothing.");
            Assert.AreEqual(-1, spawner.PaintedCellCount, "PaintedCellCount before Spawn() must be -1.");

            int first = spawner.Spawn();
            yield return null;
            int firstCells = spawner.PaintedCellCount;

            // Destroy is deferred to the end of the frame, so the yields are what let the first
            // floors leave before the second set is counted.
            int second = spawner.Spawn();
            yield return null;

            Assert.AreEqual(AllRooms.Length, first, "The first Spawn() created " + first + " room floors, not " + AllRooms.Length + ".");
            Assert.AreEqual(first, second, "A second Spawn() returned " + second + " against " + first + " the first time.");
            Assert.AreEqual(second, spawner.SpawnedCount, "SpawnedCount disagrees with the value Spawn() returned.");
            Assert.AreEqual(firstCells, spawner.PaintedCellCount, "A second Spawn() painted a different number of cells.");

            Tilemap[] tilemaps = spawnerObject.GetComponentsInChildren<Tilemap>(true);
            Assert.AreEqual(AllRooms.Length, tilemaps.Length,
                "After two Spawn() calls the hierarchy holds " + tilemaps.Length + " floor tilemaps rather than "
                + AllRooms.Length + ". A doubled floor reads as a painting bug rather than a lifecycle bug, which is why Spawn() clears first.");
            Assert.AreEqual(AllRooms.Length, spawnerObject.GetComponentsInChildren<BoxCollider>(true).Length,
                "After two Spawn() calls the hierarchy holds the wrong number of FloorCollision boxes.");

            int cells = 0;
            foreach (Tilemap tilemap in tilemaps)
            {
                cells += CountPainted(tilemap);
            }

            Assert.AreEqual(firstCells, cells, "After two Spawn() calls the tilemaps hold " + cells + " painted cells against " + firstCells + " after one.");
        }

        [Test]
        public void PaintRoom_ReturnsWhatItPaintedAndPaintingTwiceDoesNotDouble()
        {
            // A Grid and Tilemap built in code with the pinned values - NOT the prefab - so this
            // exercises the painter alone. Built in the editor builders' order: parent the object
            // under the Grid BEFORE adding the Tilemap, which needs a Grid above it. The tile is
            // transient and exists only here; the spawner never creates one.
            var gridObject = new GameObject("PaintRoomGrid", typeof(Grid));
            var grid = gridObject.GetComponent<Grid>();
            grid.cellSize = PinnedCellSize;
            grid.cellSwizzle = GridLayout.CellSwizzle.XYZ;

            var tilemapObject = new GameObject("PaintRoomTilemap");
            tilemapObject.transform.SetParent(gridObject.transform, false);
            tilemapObject.transform.localPosition = PinnedTilemapLocalPosition;
            tilemapObject.transform.localRotation = Quaternion.Euler(PinnedTilemapLocalEuler);
            var tilemap = tilemapObject.AddComponent<Tilemap>();
            tilemap.tileAnchor = Vector3.zero;
            tilemap.orientation = Tilemap.Orientation.XY;
            tilemapObject.AddComponent<TilemapRenderer>();

            var tile = ScriptableObject.CreateInstance<Tile>();
            try
            {
                Bounds bounds = LayoutBounds(RoomId.RuinedEntry);
                Vector3 cellSize = grid.cellSize;
                int expected = Mathf.RoundToInt(bounds.size.x / cellSize.x) * Mathf.RoundToInt(bounds.size.z / cellSize.y);

                int returned = FloorSpawner.PaintRoom(tilemap, bounds, tile);
                Assert.AreEqual(expected, returned,
                    "PaintRoom returned " + returned + "; the Ruined Entry's " + bounds.size.x + " x " + bounds.size.z
                    + " at cell size " + cellSize + " implies " + expected + ".");
                Assert.AreEqual(returned, CountPainted(tilemap),
                    "PaintRoom's return value and the tiles actually on the Tilemap disagree; the return value cannot be trusted.");

                int again = FloorSpawner.PaintRoom(tilemap, bounds, tile);
                Assert.AreEqual(returned, again, "Painting the same room twice returned a different count.");
                Assert.AreEqual(returned, CountPainted(tilemap),
                    "Painting the same room twice changed the tile count; SetTilesBlock is supposed to overwrite, not append.");
            }
            finally
            {
                Object.DestroyImmediate(tile);
                Object.DestroyImmediate(gridObject);
            }
        }
    }
}
