using System;
using System.Collections.Generic;
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
    /// <summary>Builds only the Final Room authoring scene; it never touches the canonical scene.</summary>
    public static class FinalRoomSceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/Rooms/FinalRoom.unity";

        private const string ArchitecturalTileFolder =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";
        private const string WallTilePath = ArchitecturalTileFolder + "/WallTile.asset";
        private const float WallVisualOffset = 0.151f;
        private static readonly Vector3 LowWallCellScale = new Vector3(1f, 0.2f, 1f);

        // NSC-109 AC-001/AC-002: this room's own floor Tile, owned and materialized here rather
        // than borrowed from a room-agnostic shared asset, so it can be bound to this room's own
        // committed floor sprite.
        private const string FloorTileName = "FinalRoomFloorTile";
        private const string FloorTilePath = ArchitecturalTileFolder + "/" + FloorTileName + ".asset";
        private const string FloorSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_FinalRoom.png";
        private const string WallAccentsRootName = "WallAccents";

        [MenuItem("No Safe Circle/Rooms/Build Final Room Authoring Scene")]
        public static void BuildAndSave()
        {
            BuildInMemoryForTests();
            EditorSceneManager.SaveScene(SceneManager.GetActiveScene(), ScenePath);
            AssetDatabase.SaveAssets();
        }

        public static void BuildInMemoryForTests()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var root = new GameObject("Room_FinalRoom");
            Transform visuals = CreateCategory(root.transform, "Visuals", RoomContentCategory.Visuals);
            Transform geometry = CreateCategory(root.transform, "GameplayGeometry", RoomContentCategory.GameplayGeometry);
            Transform anchors = CreateCategory(root.transform, "DoorAnchors", RoomContentCategory.DoorAnchors);
            Transform authoring = CreateCategory(root.transform, "Authoring", RoomContentCategory.Authoring);
            GameObject dressingObject = new GameObject("FittingRoomDressing");
            dressingObject.transform.SetParent(visuals, false);
            Transform dressing = dressingObject.transform;

            BuildTilemapVisuals(visuals);
            BuildWallAccents(visuals);

            CreateBox("FloorCollision", geometry,
                FinalRoomLayout.RoomBounds.center + Vector3.down * 0.05f,
                new Vector3(FinalRoomLayout.RoomBounds.size.x, 0.1f, FinalRoomLayout.RoomBounds.size.z),
                Color.clear, true);
            CreateGameplayPerimeter(geometry);
            CreateObstacle(visuals, false);
            CreateObstacle(geometry, true);
            CreateFittingRoomDressing(dressing, geometry);

            CreateAnchor("D4Anchor", anchors, FinalRoomLayout.D4, Vector3.back, DoorId.D4, DoorAnchorRole.Entry);
            CreateAnchor("D5Anchor", anchors, FinalRoomLayout.D5, Vector3.forward, DoorId.D5, DoorAnchorRole.Exit);
            GameObject staging = new GameObject("D5Staging");
            staging.transform.SetParent(authoring, false);
            staging.transform.position = FinalRoomLayout.D5StagingBounds.center;
            SceneManager.SetActiveScene(scene);
        }

        private static void BuildTilemapVisuals(Transform parent)
        {
            Tile floorTile = LoadOrCreateFloorTile(ArchitecturalTileFolder);
            Tile wallTile = AssetDatabase.LoadAssetAtPath<Tile>(WallTilePath);
            if (wallTile == null)
            {
                Debug.LogError($"Final Room requires the existing {WallTilePath} Tile asset.");
                return;
            }

            GameObject gridObject = new GameObject("IsometricZAsY", typeof(Grid));
            gridObject.transform.SetParent(parent, false);
            Grid grid = gridObject.GetComponent<Grid>();
            grid.cellSize = new Vector3(1f, 0.5f, 1f);
            grid.cellSwizzle = GridLayout.CellSwizzle.XYZ;

            Tilemap floor = CreateVisualTilemap(gridObject.transform, "FloorTilemap",
                new Vector3(0f, 0.01f, 0f), Quaternion.Euler(-90f, 0f, 0f), -100);
            PaintFloor(floor, floorTile);

            Tilemap north = CreateVisualTilemap(gridObject.transform, "NorthFullWallTilemap",
                new Vector3(0.5f, 0f, FinalRoomLayout.MaximumZ - WallVisualOffset), Quaternion.identity, 0);
            PaintStraightWallRun(north, wallTile, -9, 13);
            PaintStraightWallRun(north, wallTile, 8, 13);

            Tilemap south = CreateVisualTilemap(gridObject.transform, "SouthLowWallTilemap",
                new Vector3(0.5f, 0f, FinalRoomLayout.MinimumZ + WallVisualOffset), Quaternion.identity, 0);
            PaintLowWallRun(south, wallTile, -7, 17);
            PaintLowWallRun(south, wallTile, 10, 9);

            Tilemap west = CreateVisualTilemap(gridObject.transform, "WestFullWallTilemap",
                new Vector3(FinalRoomLayout.MinimumX + WallVisualOffset, 0f, -0.5f),
                Quaternion.Euler(0f, 90f, 0f), 0);
            PaintStraightWallRun(west, wallTile, -90, 28);

            Tilemap east = CreateVisualTilemap(gridObject.transform, "EastLowWallTilemap",
                new Vector3(FinalRoomLayout.MaximumX - WallVisualOffset, 0f, -0.5f),
                Quaternion.Euler(0f, 90f, 0f), 0);
            PaintLowWallRun(east, wallTile, -90, 28);
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

        // tileAnchor is zero, so Tilemap.GetCellCenterWorld returns the cell's ORIGIN CORNER,
        // not its centre. A cell therefore covers [corner.x, corner.x + cellSize.x) in world x,
        // and because the -90 degree tilemap rotation negates z, (corner.z - cellSize.y, corner.z]
        // in world z. Testing the corner alone -- which is what this builder used to do -- paints
        // a band offset by one cell: a full column past MaximumX, half a row short of MaximumZ.
        // Test the cell's COVERED INTERVAL so the painted floor is exactly the room.
        // Shared with FinalRoomSceneTests so the builder and its check cannot drift apart; the
        // test that actually proves COVERAGE is the world-point sampling loop, not this.
        public static bool FloorCellIsInsideRoom(Vector3 cellCorner, Vector3 cellSize)
        {
            const float tolerance = 0.001f;
            return cellCorner.x >= FinalRoomLayout.MinimumX - tolerance
                && cellCorner.x + cellSize.x <= FinalRoomLayout.MaximumX + tolerance
                && cellCorner.z - cellSize.y >= FinalRoomLayout.MinimumZ - tolerance
                && cellCorner.z <= FinalRoomLayout.MaximumZ + tolerance;
        }

        private static void PaintFloor(Tilemap tilemap, TileBase floorTile)
        {
            float minimumX = FinalRoomLayout.MinimumX;
            float maximumX = FinalRoomLayout.MaximumX;
            float minimumZ = FinalRoomLayout.MinimumZ;
            float maximumZ = FinalRoomLayout.MaximumZ;

            Vector3Int cornerA = tilemap.WorldToCell(new Vector3(minimumX - 1f, 0f, minimumZ - 1f));
            Vector3Int cornerB = tilemap.WorldToCell(new Vector3(maximumX + 1f, 0f, maximumZ + 1f));

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

        // NSC-126 AC-001/AC-003/AC-004: places the corner/jamb/end-cap accents NSC-120 delivered,
        // from this room's own committed RoomBounds, floor Y and D4/D5 door openings -- no new
        // door coordinates or bounds are introduced here. Nested under Visuals rather than as a
        // direct child of the room root because RoomSceneComposer.ValidateContentCategories
        // requires every direct room-root child to carry a RoomContentMarker for one of its four
        // categories; the whole room is rebuilt from scratch on every call, so this is idempotent
        // for free.
        private static void BuildWallAccents(Transform visuals)
        {
            Bounds roomBounds = FinalRoomLayout.RoomBounds;
            var doorOpenings = new List<WallAccentDoorOpening>
            {
                new WallAccentDoorOpening(WallSide.South, FinalRoomLayout.D4X, FinalRoomLayout.DoorOpeningWidth),
                new WallAccentDoorOpening(WallSide.North, FinalRoomLayout.D5X, FinalRoomLayout.DoorOpeningWidth)
            };
            WallAccentRoomGeometry geometry = ArchitecturalWallAccentPlacement.BuildRectangularRoomGeometry(
                roomBounds, roomBounds.center.y, doorOpenings);

            GameObject accentsRoot = new GameObject(WallAccentsRootName);
            accentsRoot.transform.SetParent(visuals, false);
            ArchitecturalWallAccentPlacement.Place(accentsRoot.transform, geometry);
        }

        public static void PaintStraightWallRun(Tilemap wallTilemap, TileBase wallTile, int centerCell, int cellCount)
        {
            if (wallTilemap == null) throw new ArgumentNullException(nameof(wallTilemap));
            if (wallTile == null) throw new ArgumentNullException(nameof(wallTile));
            if (cellCount <= 0) throw new ArgumentOutOfRangeException(nameof(cellCount));

            int firstCell = centerCell - cellCount / 2;
            for (int index = 0; index < cellCount; index++)
            {
                wallTilemap.SetTile(new Vector3Int(firstCell + index, 0, 0), wallTile);
            }
        }

        private static void PaintLowWallRun(Tilemap wallTilemap, TileBase wallTile, int centerCell, int cellCount)
        {
            PaintStraightWallRun(wallTilemap, wallTile, centerCell, cellCount);
            int firstCell = centerCell - cellCount / 2;
            Matrix4x4 lowCellTransform = Matrix4x4.Scale(LowWallCellScale);
            for (int index = 0; index < cellCount; index++)
            {
                wallTilemap.SetTransformMatrix(new Vector3Int(firstCell + index, 0, 0), lowCellTransform);
            }
        }

        private static void CreateGameplayPerimeter(Transform parent)
        {
            float centerY = FinalRoomLayout.GameplayWallColliderHeight * 0.5f;
            float roomDepth = FinalRoomLayout.MaximumZ - FinalRoomLayout.MinimumZ;

            CreateBox("WestWallCollision", parent,
                new Vector3(FinalRoomLayout.MinimumX, centerY, FinalRoomLayout.RoomBounds.center.z),
                new Vector3(FinalRoomLayout.WallThickness, FinalRoomLayout.GameplayWallColliderHeight, roomDepth),
                Color.clear, true);
            CreateBox("EastWallCollision", parent,
                new Vector3(FinalRoomLayout.MaximumX, centerY, FinalRoomLayout.RoomBounds.center.z),
                new Vector3(FinalRoomLayout.WallThickness, FinalRoomLayout.GameplayWallColliderHeight, roomDepth),
                Color.clear, true);

            CreateSplitWallCollision(parent, "SouthWall", FinalRoomLayout.D4X, FinalRoomLayout.MinimumZ, centerY);
            CreateSplitWallCollision(parent, "NorthWall", FinalRoomLayout.D5X, FinalRoomLayout.MaximumZ, centerY);
        }

        private static void CreateSplitWallCollision(
            Transform parent, string prefix, float openingCenter, float z, float centerY)
        {
            float halfOpening = FinalRoomLayout.DoorOpeningWidth * 0.5f;
            float westLength = openingCenter - halfOpening - FinalRoomLayout.MinimumX;
            float eastLength = FinalRoomLayout.MaximumX - openingCenter - halfOpening;
            CreateBox(prefix + "WestCollision", parent,
                new Vector3(FinalRoomLayout.MinimumX + westLength * 0.5f, centerY, z),
                new Vector3(westLength, FinalRoomLayout.GameplayWallColliderHeight, FinalRoomLayout.WallThickness),
                Color.clear, true);
            CreateBox(prefix + "EastCollision", parent,
                new Vector3(FinalRoomLayout.MaximumX - eastLength * 0.5f, centerY, z),
                new Vector3(eastLength, FinalRoomLayout.GameplayWallColliderHeight, FinalRoomLayout.WallThickness),
                Color.clear, true);
        }

        private static void CreateObstacle(Transform parent, bool collision)
        {
            CreateBox("FR-1" + Suffix(collision), parent,
                FinalRoomLayout.FR1Bounds.center,
                FinalRoomLayout.FR1Bounds.size,
                RoomPlaceholderVisuals.Opaque(RoomPlaceholderVisuals.BlockoutPlaceholder), collision);
        }

        private static void CreateFittingRoomDressing(Transform parent, Transform gameplay)
        {
            CreateBox("WestBench", parent, FinalRoomLayout.WestBenchBounds.center, FinalRoomLayout.WestBenchBounds.size, new Color(0.23f, 0.12f, 0.16f), false);
            CreateBox("EastBench", parent, FinalRoomLayout.EastBenchBounds.center, FinalRoomLayout.EastBenchBounds.size, new Color(0.23f, 0.12f, 0.16f), false);
            CreateBox("WestBenchCollision", gameplay, FinalRoomLayout.WestBenchBounds.center, FinalRoomLayout.WestBenchBounds.size, Color.clear, true);
            CreateBox("EastBenchCollision", gameplay, FinalRoomLayout.EastBenchBounds.center, FinalRoomLayout.EastBenchBounds.size, Color.clear, true);
            CreateCandle("Candle1", parent, new Vector3(-12f, 0f, 82.5f));
        }

        private static void CreateCandle(string name, Transform parent, Vector3 groundPosition)
        {
            GameObject root = new GameObject(name);
            root.transform.SetParent(parent, false);
            root.transform.position = groundPosition;

            GameObject wax = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            wax.name = "Wax";
            wax.transform.SetParent(root.transform, false);
            wax.transform.localPosition = new Vector3(0f, 0.16f, 0f);
            wax.transform.localScale = new Vector3(0.12f, 0.16f, 0.12f);
            wax.GetComponent<Renderer>().sharedMaterial = CreateMaterial(new Color(0.72f, 0.55f, 0.32f));
            Object.DestroyImmediate(wax.GetComponent<Collider>());

            GameObject flame = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            flame.name = "Flame";
            flame.transform.SetParent(root.transform, false);
            flame.transform.localPosition = new Vector3(0f, 0.38f, 0f);
            flame.transform.localScale = new Vector3(0.09f, 0.15f, 0.09f);
            flame.GetComponent<Renderer>().sharedMaterial = CreateMaterial(new Color(1f, 0.35f, 0.05f));
            Object.DestroyImmediate(flame.GetComponent<Collider>());
        }

        private static GameObject CreateBox(string name, Transform parent, Vector3 position, Vector3 size, Color color, bool collision)
        {
            GameObject box = collision ? new GameObject(name) : GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            box.transform.localScale = collision ? Vector3.one : size;
            if (collision)
            {
                BoxCollider collider = box.AddComponent<BoxCollider>();
                collider.size = size;
            }
            else
            {
                box.GetComponent<Renderer>().sharedMaterial = CreateMaterial(color);
                Object.DestroyImmediate(box.GetComponent<Collider>());
            }
            return box;
        }

        private static void CreateAnchor(
            string name, Transform parent, Vector3 position, Vector3 forward, DoorId doorId, DoorAnchorRole role)
        {
            GameObject anchor = new GameObject(name);
            anchor.transform.SetParent(parent, false);
            anchor.transform.position = position;
            anchor.transform.forward = forward;
            DoorAnchorMarker marker = anchor.AddComponent<DoorAnchorMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.FinalRoom;
            serialized.FindProperty("doorId").enumValueIndex = (int)doorId;
            serialized.FindProperty("role").enumValueIndex = (int)role;
            serialized.FindProperty("openingWidth").floatValue = FinalRoomLayout.DoorOpeningWidth;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static Transform CreateCategory(Transform parent, string name, RoomContentCategory category)
        {
            GameObject child = new GameObject(name);
            child.transform.SetParent(parent, false);
            RoomContentMarker marker = child.AddComponent<RoomContentMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.FinalRoom;
            serialized.FindProperty("category").enumValueIndex = (int)category;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            return child.transform;
        }

        private static string Suffix(bool collision) => collision ? "Collision" : "Visual";

        // NSC-109 AC-001/AC-002: this room's own floor Tile, bound to the committed
        // floor_FinalRoom sprite rather than a procedurally generated texture.
        private static Tile LoadOrCreateFloorTile(string assetFolder)
        {
            Sprite sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(FloorSpriteSourcePath);
            if (sourceSprite == null)
            {
                throw new InvalidOperationException(
                    $"Final Room requires the committed sprite at '{FloorSpriteSourcePath}'.");
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

        // WAS: new Material(Standard); material.color = color; return material; - which drops
        // any alpha below 255 SILENTLY, because the Standard shader ships in Opaque mode and
        // never consults the channel. The assignment succeeded and the colour read back
        // correctly the whole time, which is why nobody caught it by inspection.
        private static Material CreateMaterial(Color color)
        {
            return RoomPlaceholderVisuals.CreateStandardMaterial(color);
        }

    }

}
