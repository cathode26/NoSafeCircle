using System;
using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype.World
{
    // Paints each room's floor Tilemap and lays its FloorCollision AT RUNTIME, from the room's
    // committed Tile asset and its *Layout.cs bounds.
    //
    // WHY THIS EXISTS. Vincent, 2026-09-26: "No we must stop this baking thing" / "The scene should
    // just be some objects that create prefabs." Five *SceneBuilder.cs files ran in the editor and
    // BAKED a painted FloorTilemap into five committed scenes: a change to the paint rule was
    // invisible until someone ran Unity, and the output was thousands of tile entries inside an
    // artifact nobody can merge. This component is that paint step, run at Play, once per room,
    // from one prefab nothing bakes into.
    //
    // WHAT IS WHOSE, because the split is the design. The PREFAB (Resources/Floors/RoomFloor.prefab)
    // carries the Grid/Tilemap configuration NSC-046 and NSC-048 AC-003 pin - cellSize (1, 0.5, 1),
    // the tilemap rotated -90 degrees so its local y IS world z, tileAnchor zero, Mode.Individual,
    // SortOrder.TopRight, the WorldSprites layer at WorldSpriteConvention.BackgroundGroundSortingOrder
    // - and holds NO tiles. The TILE is the committed <Room>FloorTile.asset under
    // Generated/ArchitecturalTiles, NSC-109's directory, referenced from the spawner prefab and
    // never loaded by name and never created here. The EXTENT is <Room>Layout.RoomBounds, the same
    // rectangle the wall colliders stand on, so the floor ends on the line the wizard collides
    // with. This component decides none of the three; it applies them.
    //
    // THE FLOOR DOES NOT READ THE ASCII MAP. Floor01AsciiMapTests proves the map's rectangle
    // CONTAINS every room's layout rectangle and differs from it by less than one cell (the Final
    // Room by one unit on each X edge - a property of the 2-unit grid, not of the room), so the
    // layout is the only extent that matters and the map cannot widen a floor. If a room ever
    // stops being a rectangle, the map enters PaintRoom as a second predicate: a new parameter,
    // not a rewrite.
    [DisallowMultipleComponent]
    public sealed class FloorSpawner : MonoBehaviour, ISpawner
    {
        /// <summary>One room's floor art: the room names the layout, the tile names the sprite.</summary>
        [Serializable]
        public struct RoomFloorBinding
        {
            public RoomId room;
            public Tile tile;
        }

        /// <summary>The floor prefab's child that carries the walkable surface. Found by name so
        /// the prefab stays a plain hierarchy anyone can open and edit.</summary>
        public const string FloorCollisionName = "FloorCollision";

        /// <summary>Thickness of the FloorCollision box. Its TOP FACE sits at the layout's ground
        /// (y = 0) whatever this value is, and the top face is the invariant.</summary>
        /// <remarks>
        /// This is CreateGameplayBox's shape in four of the five editor builders: 0.1 thick, centre
        /// 0.05 below the ground. Bone Archive alone used a 0.5-thick box at y -0.25, and the
        /// difference does not matter, because both put the top face at y = 0 - which is the only
        /// thing the navmesh bake (GameplayNavigationSurface: CollectObjects.All, PhysicsColliders)
        /// and the wizard's CharacterController ever stand on. Click-to-move does not need this box
        /// at all (PlayerMovement raycasts a mathematical Plane); the bake does, and without it the
        /// navmesh is empty and the failure surfaces in the Navigation lane, far from its cause.
        /// </remarks>
        public const float FloorCollisionThickness = 0.1f;

        /// <summary>Floors run first: nothing else has anywhere to be until this has run.</summary>
        public SpawnPhase Phase => SpawnPhase.Rooms;

        [Tooltip("Resources/Floors/RoomFloor.prefab: one Grid, one empty FloorTilemap and one "
            + "FloorCollision. A direct reference, so a rename fails at edit time rather than at Play.")]
        [SerializeField] private GameObject roomFloorPrefab;

        [Tooltip("One entry per room: the RoomId and that room's committed floor Tile from "
            + "Generated/ArchitecturalTiles. Dragged in, not loaded by name: those assets are not "
            + "under Resources and must not move.")]
        [SerializeField] private RoomFloorBinding[] rooms = new RoomFloorBinding[0];

        [Tooltip("Parent for the spawned floors. Left empty, floors are parented to this object.")]
        [SerializeField] private Transform floorsRoot;

        /// <summary>Room floors created by the last Spawn(). -1 until Spawn() has run, which is
        /// deliberately distinguishable from a Spawn() that created nothing.</summary>
        public int SpawnedCount { get; private set; } = -1;

        /// <summary>Tile cells painted by the last Spawn(), summed over rooms. -1 until it has run.</summary>
        public int PaintedCellCount { get; private set; } = -1;

        // NO Awake AND NO spawnOnAwake FIELD: GameBootstrap owns the moment. PropSpawner kept that
        // field from its pre-bootstrap life; a lane born under the bootstrap has no such life.

        /// <summary>Assigns the prefab and the bindings from code instead of the inspector, for
        /// tests. Does NOT spawn - call Spawn() when ready.</summary>
        public void Configure(GameObject prefab, IEnumerable<RoomFloorBinding> bindings, Transform root = null)
        {
            roomFloorPrefab = prefab;
            rooms = bindings == null ? new RoomFloorBinding[0] : new List<RoomFloorBinding>(bindings).ToArray();
            floorsRoot = root;
        }

        /// <summary>Instantiates one floor per binding, paints it and sizes its collision. Returns
        /// how many ROOM FLOORS it created - one object per room, as one prop is one object - not
        /// how many cells. Safe to call again: it clears what it previously spawned first.</summary>
        public int Spawn()
        {
            Transform root = floorsRoot != null ? floorsRoot : transform;

            // Clear a previous spawn rather than adding to it. Ten floors would look like a
            // painting bug rather than a lifecycle bug, so make it impossible.
            for (int i = root.childCount - 1; i >= 0; i--)
            {
                Destroy(root.GetChild(i).gameObject);
            }

            SpawnedCount = 0;
            PaintedCellCount = 0;
            if (roomFloorPrefab == null || rooms.Length == 0)
            {
                Debug.LogError($"{nameof(FloorSpawner)}: " + (roomFloorPrefab == null
                        ? "no room floor prefab assigned."
                        : "no room bindings; assign one RoomId and its committed floor Tile per room.")
                    + " No floor exists and the wizard has nothing to stand on.");
                return 0;
            }

            int spawned = 0;
            int painted = 0;
            foreach (RoomFloorBinding binding in rooms)
            {
                if (SpawnRoomFloor(binding, root, out int cells))
                {
                    spawned++;
                    painted += cells;
                }
            }

            SpawnedCount = spawned;
            PaintedCellCount = painted;
            Debug.Log($"{nameof(FloorSpawner)}: spawned {spawned} room floor(s), {painted} cell(s), from {rooms.Length} binding(s).");
            return spawned;
        }

        private bool SpawnRoomFloor(RoomFloorBinding binding, Transform root, out int painted)
        {
            painted = 0;
            if (binding.tile == null)
            {
                // A runtime CreateInstance<Tile>() fallback would hide a missing binding behind a
                // working floor. A null binding is an error and logs as one.
                Debug.LogError($"{nameof(FloorSpawner)}: {binding.room} has no floor Tile bound. "
                    + "Drag in the room's committed <Room>FloorTile.asset; nothing is created here.");
                return false;
            }

            if (!TryGetRoomBounds(binding.room, out Bounds bounds))
            {
                Debug.LogError($"{nameof(FloorSpawner)}: no layout bounds for room '{binding.room}'.");
                return false;
            }

            GameObject floor = Instantiate(roomFloorPrefab, root);
            floor.name = binding.room + "Floor";

            // WORLD origin, unrotated, unscaled. Cell coordinates are world coordinates only while
            // the Grid sits at the origin with identity rotation; GameManagers is at the origin
            // today and this line makes the floor not depend on that.
            floor.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            floor.transform.localScale = Vector3.one;

            var tilemap = floor.GetComponentInChildren<Tilemap>();
            BoxCollider collision = floor.transform.Find(FloorCollisionName) is Transform found ? found.GetComponent<BoxCollider>() : null;
            if (tilemap == null || collision == null)
            {
                Debug.LogError($"{nameof(FloorSpawner)}: '{roomFloorPrefab.name}' lacks "
                    + (tilemap == null ? "a Tilemap" : $"a '{FloorCollisionName}' BoxCollider")
                    + ". The prefab is the artifact to fix.");
                Destroy(floor);
                return false;
            }

            painted = PaintRoom(tilemap, bounds, binding.tile);

            // The walkable surface: top face at the layout's ground, whatever the thickness.
            collision.center = bounds.center + Vector3.down * (FloorCollisionThickness * 0.5f);
            collision.size = new Vector3(bounds.size.x, FloorCollisionThickness, bounds.size.z);
            return true;
        }

        /// <summary>Paints every cell whose FULL FOOTPRINT lies inside the room bounds, in one
        /// SetTilesBlock, and returns how many it painted. Static so a test can drive it on a
        /// Tilemap it built itself.</summary>
        public static int PaintRoom(Tilemap tilemap, Bounds roomBounds, TileBase tile)
        {
            if (tilemap == null) throw new ArgumentNullException(nameof(tilemap));
            if (tile == null) throw new ArgumentNullException(nameof(tile));

            // READ from the Grid the tilemap sits on, never a literal: (1, 0.5, 1) is the
            // contract's number and the contract lives in the prefab.
            Vector3 cell = tilemap.layoutGrid.cellSize;

            // One world unit of padding each side, so the PREDICATE decides the edge and not the
            // range. The -90 degree tilemap maps world z onto cell rows with the sign flipped, so
            // the two corners can come back in either order; min/max sorts them.
            Vector3Int a = tilemap.WorldToCell(new Vector3(roomBounds.min.x - 1f, 0f, roomBounds.min.z - 1f));
            Vector3Int b = tilemap.WorldToCell(new Vector3(roomBounds.max.x + 1f, 0f, roomBounds.max.z + 1f));
            int xMin = Mathf.Min(a.x, b.x);
            int rowMin = Mathf.Min(a.y, b.y);
            var block = new BoundsInt(xMin, rowMin, 0, Mathf.Max(a.x, b.x) - xMin + 1, Mathf.Max(a.y, b.y) - rowMin + 1, 1);

            // SetTilesBlock fills x fastest, then y. A null entry leaves that cell empty.
            var tiles = new TileBase[block.size.x * block.size.y];
            int painted = 0;
            for (int row = 0; row < block.size.y; row++)
            {
                for (int x = 0; x < block.size.x; x++)
                {
                    Vector3 corner = tilemap.GetCellCenterWorld(new Vector3Int(xMin + x, rowMin + row, 0));
                    if (CellFootprintIsInside(corner, cell, roomBounds))
                    {
                        tiles[x + row * block.size.x] = tile;
                        painted++;
                    }
                }
            }

            tilemap.SetTilesBlock(block, tiles);
            return painted;
        }

        /// <summary>True when the whole cell lies inside the room.</summary>
        /// <remarks>
        /// THE TRAP THIS KEEPS: with tileAnchor zero, Tilemap.GetCellCenterWorld returns the cell's
        /// ORIGIN CORNER and not its centre, and the -90 degree rotation maps local +y to world -z,
        /// so cell (x, row) covers world X [x, x + cellSize.x) and Z (corner.z - cellSize.y,
        /// corner.z]. Test the COVERED INTERVAL, never the corner alone: a corner test paints a band
        /// one cell out of place, the defect the Final Room and Bone Archive builders each fixed.
        /// The cellSize.y in the z clause is deliberate - the Tilemap's local y IS world z.
        /// </remarks>
        public static bool CellFootprintIsInside(Vector3 cellCorner, Vector3 cellSize, Bounds roomBounds)
        {
            const float tolerance = 0.001f;
            return cellCorner.x >= roomBounds.min.x - tolerance
                && cellCorner.x + cellSize.x <= roomBounds.max.x + tolerance
                && cellCorner.z - cellSize.y >= roomBounds.min.z - tolerance
                && cellCorner.z <= roomBounds.max.z + tolerance;
        }

        /// <summary>The room's ground rectangle, from its own layout. Five lines, deliberately
        /// repeated in each spawner that needs them rather than shared: a RoomLayouts.cs would be
        /// the one file every lane edits.</summary>
        public static bool TryGetRoomBounds(RoomId room, out Bounds bounds)
        {
            switch (room)
            {
                case RoomId.RuinedEntry: bounds = RuinedEntryLayout.RoomBounds; return true;
                case RoomId.BoneArchive: bounds = BoneArchiveLayout.RoomBounds; return true;
                case RoomId.ChapelOfAsh: bounds = ChapelOfAshLayout.RoomBounds; return true;
                case RoomId.LowerVault: bounds = LowerVaultLayout.RoomBounds; return true;
                case RoomId.FinalRoom: bounds = FinalRoomLayout.RoomBounds; return true;
                default: bounds = default; return false;
            }
        }
    }
}
