using System;
using System.IO;
using NoSafeCircle.DoorPrototype.Editor;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Tilemaps;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor.Rooms
{
    /// <summary>Builds only the Bone Archive authoring scene; it never touches the composed scene.</summary>
    public static class BoneArchiveSceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/Rooms/BoneArchive.unity";

        // The shared full-wall Tile asset every room paints its far walls with. It is not
        // generated here and this builder does not own it.
        private const string ArchitecturalTileFolder =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";
        private const string WallTilePath = ArchitecturalTileFolder + "/WallTile.asset";
        private const float WallVisualOffset = 0.151f;
        private static readonly Vector3 LowWallCellScale = new Vector3(1f, 0.2f, 1f);

        // NSC-109 AC-001/AC-002: this room's own floor Tile, owned and materialized here rather
        // than borrowed from a room-agnostic shared asset, so it can be bound to this room's own
        // committed floor sprite.
        private const string FloorTileName = "BoneArchiveFloorTile";
        private const string FloorTilePath = ArchitecturalTileFolder + "/" + FloorTileName + ".asset";
        private const string FloorSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_BoneArchive.png";

        [MenuItem("No Safe Circle/Rooms/Build Bone Archive Authoring Scene")]
        public static void BuildAndSave()
        {
            BuildInMemoryForTests();
            EditorSceneManager.SaveScene(SceneManager.GetActiveScene(), ScenePath);
            AssetDatabase.SaveAssets();
        }

        public static void BuildInMemoryForTests()
        {
            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            GameObject root = new GameObject("Room_BoneArchive");
            Transform visuals = CreateCategory(root.transform, "Visuals", RoomContentCategory.Visuals);
            Transform geometry = CreateCategory(root.transform, "GameplayGeometry", RoomContentCategory.GameplayGeometry);
            Transform anchors = CreateCategory(root.transform, "DoorAnchors", RoomContentCategory.DoorAnchors);
            CreateCategory(root.transform, "Authoring", RoomContentCategory.Authoring);

            CreateVisualAndCollision("Floor", visuals, geometry, new Vector3(0f, -0.25f, 10f), new Vector3(20f, 0.5f, 20f), Color.gray);
            CreatePerimeter(visuals, geometry);

            // The blockout primitives above stay exactly where they are: BoneArchiveSceneTests
            // asserts on NorthWallWestVisual/NorthWallEastVisual transforms and on an exact
            // count of 11 BoxColliders under GameplayGeometry, so this layer is PURELY
            // ADDITIVE and changes neither. What it changes is what you SEE: when the shared
            // tiles load, the primitives stop rendering and the tilemaps become the visible
            // surface, which is how the other four rooms are built.
            if (BuildTilemapVisuals(visuals))
            {
                HideBlockoutRenderers(visuals);
            }
            CreateVisualAndCollision("Shelf A", visuals, geometry, BoneArchiveLayout.ShelfA.center, BoneArchiveLayout.ShelfA.size, new Color(0.22f, 0.12f, 0.08f));
            CreateVisualAndCollision("Shelf B", visuals, geometry, BoneArchiveLayout.ShelfB.center, BoneArchiveLayout.ShelfB.size, new Color(0.22f, 0.12f, 0.08f));
            CreateVisualAndCollision("Shelf C", visuals, geometry, BoneArchiveLayout.ShelfC.center, BoneArchiveLayout.ShelfC.size, new Color(0.22f, 0.12f, 0.08f));
            CreateVisualAndCollision("Collapsed Furniture BA-1", visuals, geometry, BoneArchiveLayout.CollapsedFurnitureBA1.center, BoneArchiveLayout.CollapsedFurnitureBA1.size, new Color(0.28f, 0.18f, 0.12f));
            CreateAnchor("D1Anchor", anchors, BoneArchiveLayout.D1, Vector3.back, DoorId.D1, DoorAnchorRole.Entry);
            CreateAnchor("D2Anchor", anchors, BoneArchiveLayout.D2, Vector3.forward, DoorId.D2, DoorAnchorRole.Exit);
            SceneManager.SetActiveScene(scene);
        }

        /// <summary>Paints the tiled floor and walls. False when the shared tiles are missing.</summary>
        /// <remarks>
        /// Returning false rather than throwing keeps the room at its blockout instead of
        /// leaving it with no visuals at all. NOT EXERCISED: no test removes the tile assets,
        /// so the degraded path is unverified and is stated here as unverified rather than
        /// described as safe.
        /// </remarks>
        private static bool BuildTilemapVisuals(Transform parent)
        {
            Tile floorTile = LoadOrCreateBoneArchiveFloorTile(ArchitecturalTileFolder);
            Tile wallTile = AssetDatabase.LoadAssetAtPath<Tile>(WallTilePath);
            if (wallTile == null)
            {
                Debug.LogError($"Bone Archive requires the existing {WallTilePath} Tile asset.");
                return false;
            }

            GameObject gridObject = new GameObject("IsometricZAsY", typeof(Grid));
            gridObject.transform.SetParent(parent, false);
            Grid grid = gridObject.GetComponent<Grid>();
            grid.cellSize = new Vector3(1f, 0.5f, 1f);
            grid.cellSwizzle = GridLayout.CellSwizzle.XYZ;

            Tilemap floor = CreateVisualTilemap(gridObject.transform, "FloorTilemap",
                new Vector3(0f, 0.01f, 0f), Quaternion.Euler(-90f, 0f, 0f), -100);
            PaintFloor(floor, floorTile);

            // North and west are the FAR walls under the isometric camera and stay full
            // height; south and east are the NEAR walls and are squashed so the camera can
            // see into the room. Same near/far split as the Final Room.
            float minX = BoneArchiveLayout.RoomBounds.min.x;
            float maxX = BoneArchiveLayout.RoomBounds.max.x;
            float minZ = BoneArchiveLayout.RoomBounds.min.z;
            float maxZ = BoneArchiveLayout.RoomBounds.max.z;

            Tilemap north = CreateVisualTilemap(gridObject.transform, "NorthFullWallTilemap",
                new Vector3(0.5f, 0f, maxZ - WallVisualOffset), Quaternion.identity, 0);
            PaintWallWithOpening(north, wallTile, BoneArchiveLayout.D2.x, false);

            Tilemap south = CreateVisualTilemap(gridObject.transform, "SouthLowWallTilemap",
                new Vector3(0.5f, 0f, minZ + WallVisualOffset), Quaternion.identity, 0);
            PaintWallWithOpening(south, wallTile, BoneArchiveLayout.D1.x, true);

            // The 90-degree yaw makes the run index the NEGATED world z, which is why the
            // side-wall cells are negative. Derived, not copied: first = -ceil(maxZ),
            // last = -floor(minZ) - 1.
            int sideFirstCell = -Mathf.CeilToInt(maxZ);
            int sideCellCount = Mathf.CeilToInt(maxZ) - Mathf.FloorToInt(minZ);

            Tilemap west = CreateVisualTilemap(gridObject.transform, "WestFullWallTilemap",
                new Vector3(minX + WallVisualOffset, 0f, -0.5f), Quaternion.Euler(0f, 90f, 0f), 0);
            PaintRun(west, wallTile, sideFirstCell, sideCellCount, false);

            Tilemap east = CreateVisualTilemap(gridObject.transform, "EastLowWallTilemap",
                new Vector3(maxX - WallVisualOffset, 0f, -0.5f), Quaternion.Euler(0f, 90f, 0f), 0);
            PaintRun(east, wallTile, sideFirstCell, sideCellCount, true);
            return true;
        }

        /// <summary>Stops the blockout primitives rendering once the tiles are the visible surface.</summary>
        /// <remarks>
        /// The GameObjects and their transforms SURVIVE, because that is what the room tests
        /// assert on. Only the Renderer goes. Tilemaps carry their own TilemapRenderer, so
        /// Visuals still has renderers afterwards and VAL-001 still holds.
        /// </remarks>
        private static void HideBlockoutRenderers(Transform visuals)
        {
            foreach (MeshRenderer renderer in visuals.GetComponentsInChildren<MeshRenderer>())
            {
                Object.DestroyImmediate(renderer);
            }
        }

        /// <summary>Paints a wall run along x, leaving a gap for the door opening.</summary>
        /// <remarks>
        /// Cell i covers world x [i, i+1). Every cell whose interval OVERLAPS the opening is
        /// skipped, so a 3-unit door leaves a 4-cell gap. That is deliberate and matches the
        /// Final Room: the collider opening is exactly DoorWidth, and the tiled gap is the
        /// nearest whole number of cells that does not cut into the doorway.
        /// </remarks>
        private static void PaintWallWithOpening(
            Tilemap tilemap, TileBase wallTile, float openingCenter, bool lowWall)
        {
            float halfOpening = BoneArchiveLayout.DoorWidth * 0.5f;
            int firstCell = Mathf.FloorToInt(BoneArchiveLayout.RoomBounds.min.x);
            int lastCell = Mathf.CeilToInt(BoneArchiveLayout.RoomBounds.max.x) - 1;
            int openingFirst = Mathf.FloorToInt(openingCenter - halfOpening);
            int openingLast = Mathf.CeilToInt(openingCenter + halfOpening) - 1;

            PaintRun(tilemap, wallTile, firstCell, openingFirst - firstCell, lowWall);
            PaintRun(tilemap, wallTile, openingLast + 1, lastCell - openingLast, lowWall);
        }

        private static void PaintRun(
            Tilemap tilemap, TileBase wallTile, int firstCell, int cellCount, bool lowWall)
        {
            if (tilemap == null) throw new ArgumentNullException(nameof(tilemap));
            if (wallTile == null) throw new ArgumentNullException(nameof(wallTile));
            if (cellCount <= 0)
            {
                return;
            }

            Matrix4x4 lowCellTransform = Matrix4x4.Scale(LowWallCellScale);
            for (int index = 0; index < cellCount; index++)
            {
                Vector3Int cell = new Vector3Int(firstCell + index, 0, 0);
                tilemap.SetTile(cell, wallTile);
                if (lowWall)
                {
                    tilemap.SetTransformMatrix(cell, lowCellTransform);
                }
            }
        }

        private static Tilemap CreateVisualTilemap(
            Transform parent, string name, Vector3 localPosition, Quaternion localRotation, int sortingOrder)
        {
            GameObject tilemapObject = new GameObject(name);
            tilemapObject.transform.SetParent(parent, false);
            tilemapObject.transform.localPosition = localPosition;
            tilemapObject.transform.localRotation = localRotation;
            Tilemap tilemap = tilemapObject.AddComponent<Tilemap>();
            tilemap.tileAnchor = Vector3.zero;
            tilemap.orientation = Tilemap.Orientation.XY;

            TilemapRenderer renderer = tilemapObject.AddComponent<TilemapRenderer>();
            renderer.mode = TilemapRenderer.Mode.Individual;
            renderer.sortOrder = TilemapRenderer.SortOrder.TopRight;
            renderer.sortingLayerName = DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName;
            renderer.sortingOrder = sortingOrder;
            return tilemap;
        }

        // tileAnchor is zero, so Tilemap.GetCellCenterWorld returns the cell ORIGIN CORNER and
        // not its centre, and the -90 degree rotation negates z. A cell therefore covers
        // [corner.x, corner.x + cellSize.x) and (corner.z - cellSize.y, corner.z]. Testing the
        // corner alone paints a band one cell out of place; test the COVERED INTERVAL. This is
        // the same defect that was fixed in the Final Room, carried here deliberately rather
        // than rediscovered. Public so the room tests can share it instead of restating it.
        public static bool FloorCellIsInsideRoom(Vector3 cellCorner, Vector3 cellSize)
        {
            const float tolerance = 0.001f;
            return cellCorner.x >= BoneArchiveLayout.RoomBounds.min.x - tolerance
                && cellCorner.x + cellSize.x <= BoneArchiveLayout.RoomBounds.max.x + tolerance
                && cellCorner.z - cellSize.y >= BoneArchiveLayout.RoomBounds.min.z - tolerance
                && cellCorner.z <= BoneArchiveLayout.RoomBounds.max.z + tolerance;
        }

        private static void PaintFloor(Tilemap tilemap, TileBase floorTile)
        {
            Bounds room = BoneArchiveLayout.RoomBounds;
            Vector3Int cornerA = tilemap.WorldToCell(new Vector3(room.min.x - 1f, 0f, room.min.z - 1f));
            Vector3Int cornerB = tilemap.WorldToCell(new Vector3(room.max.x + 1f, 0f, room.max.z + 1f));

            int minCellX = Mathf.Min(cornerA.x, cornerB.x);
            int maxCellX = Mathf.Max(cornerA.x, cornerB.x);
            int minRow = Mathf.Min(cornerA.y, cornerB.y);
            int maxRow = Mathf.Max(cornerA.y, cornerB.y);

            for (int x = minCellX; x <= maxCellX; x++)
            {
                for (int row = minRow; row <= maxRow; row++)
                {
                    Vector3Int cell = new Vector3Int(x, row, 0);
                    Vector3 corner = tilemap.GetCellCenterWorld(cell);
                    if (FloorCellIsInsideRoom(corner, tilemap.layoutGrid.cellSize))
                    {
                        tilemap.SetTile(cell, floorTile);
                    }
                }
            }
        }

        private static void CreatePerimeter(Transform visuals, Transform geometry)
        {
            CreateOpeningWall("SouthWall", visuals, geometry, 0f, 0f);
            CreateOpeningWall("NorthWall", visuals, geometry, 6f, 20f);
            CreateVisualAndCollision("WestWall", visuals, geometry, new Vector3(-10.25f, 1.25f, 10f), new Vector3(0.5f, 2.5f, 20f), Color.black);
            CreateVisualAndCollision("EastWall", visuals, geometry, new Vector3(10.25f, 1.25f, 10f), new Vector3(0.5f, 2.5f, 20f), Color.black);
        }

        private static void CreateOpeningWall(string name, Transform visuals, Transform geometry, float openingCenter, float z)
        {
            float roomMinX = BoneArchiveLayout.RoomBounds.min.x;
            float roomMaxX = BoneArchiveLayout.RoomBounds.max.x;
            float openingHalfWidth = BoneArchiveLayout.DoorWidth * 0.5f;
            float westLength = openingCenter - openingHalfWidth - roomMinX;
            float eastLength = roomMaxX - openingCenter - openingHalfWidth;
            float y = BoneArchiveLayout.WallHeight * 0.5f;
            CreateVisualAndCollision(name + "West", visuals, geometry, new Vector3(roomMinX + westLength * 0.5f, y, z), new Vector3(westLength, BoneArchiveLayout.WallHeight, BoneArchiveLayout.WallThickness), Color.black);
            CreateVisualAndCollision(name + "East", visuals, geometry, new Vector3(roomMaxX - eastLength * 0.5f, y, z), new Vector3(eastLength, BoneArchiveLayout.WallHeight, BoneArchiveLayout.WallThickness), Color.black);
        }

        private static void CreateVisualAndCollision(string name, Transform visuals, Transform geometry, Vector3 position, Vector3 size, Color color)
        {
            GameObject visual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            visual.name = name + "Visual";
            visual.transform.SetParent(visuals, false);
            visual.transform.position = position;
            visual.transform.localScale = size;
            visual.GetComponent<Renderer>().sharedMaterial = CreateMaterial(color);
            Object.DestroyImmediate(visual.GetComponent<Collider>());

            GameObject collision = new GameObject(name + "Collision");
            collision.transform.SetParent(geometry, false);
            collision.transform.position = position;
            collision.AddComponent<BoxCollider>().size = size;
        }

        private static Transform CreateCategory(Transform parent, string name, RoomContentCategory category)
        {
            GameObject child = new GameObject(name);
            child.transform.SetParent(parent, false);
            RoomContentMarker marker = child.AddComponent<RoomContentMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.BoneArchive;
            serialized.FindProperty("category").enumValueIndex = (int)category;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            return child.transform;
        }

        private static void CreateAnchor(string name, Transform parent, Vector3 position, Vector3 forward, DoorId doorId, DoorAnchorRole role)
        {
            GameObject anchor = new GameObject(name);
            anchor.transform.SetParent(parent, false);
            anchor.transform.position = position;
            anchor.transform.forward = forward;
            DoorAnchorMarker marker = anchor.AddComponent<DoorAnchorMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.BoneArchive;
            serialized.FindProperty("doorId").enumValueIndex = (int)doorId;
            serialized.FindProperty("role").enumValueIndex = (int)role;
            serialized.FindProperty("openingWidth").floatValue = BoneArchiveLayout.DoorWidth;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static Material CreateMaterial(Color color)
        {
            Material material = new Material(Shader.Find("Standard"));
            material.color = color;
            return material;
        }

        // NSC-109 AC-001/AC-002: binds this room's floor Tile to the committed floor_BoneArchive
        // sprite rather than a procedurally generated texture.
        private static Tile LoadOrCreateBoneArchiveFloorTile(string assetFolder)
        {
            Sprite sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(FloorSpriteSourcePath);
            if (sourceSprite == null)
            {
                throw new InvalidOperationException(
                    $"Bone Archive requires the committed sprite at '{FloorSpriteSourcePath}'.");
            }

            if (!AssetDatabase.IsValidFolder(assetFolder))
            {
                Directory.CreateDirectory(assetFolder);
                AssetDatabase.Refresh();
            }

            Tile tile = AssetDatabase.LoadAssetAtPath<Tile>(FloorTilePath);
            if (tile == null)
            {
                tile = ScriptableObject.CreateInstance<Tile>();
                tile.name = FloorTileName;
                tile.colliderType = Tile.ColliderType.None;
                tile.sprite = sourceSprite;
                AssetDatabase.CreateAsset(tile, FloorTilePath);
                EditorUtility.SetDirty(tile);
                AssetDatabase.SaveAssetIfDirty(tile);
                return tile;
            }

            if (tile.sprite != sourceSprite || tile.colliderType != Tile.ColliderType.None)
            {
                tile.sprite = sourceSprite;
                tile.colliderType = Tile.ColliderType.None;
                EditorUtility.SetDirty(tile);
                AssetDatabase.SaveAssetIfDirty(tile);
            }

            return tile;
        }
    }
}
