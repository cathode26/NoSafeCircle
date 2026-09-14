using System;
using System.Collections.Generic;
using System.IO;
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
    public static class RuinedEntrySceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/Rooms/RuinedEntry.unity";

        private const string RoomRootName = "Room_RuinedEntry";
        private const string VisualRootName = "Visuals";
        private const string GameplayRootName = "GameplayGeometry";
        private const string DoorMarkerName = "D1Opening";
        private const string ArchitecturalTileFolder =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";
        private const string LowWallTileName = "RuinedEntryLowWallTile";
        private const string LowWallTilePath = ArchitecturalTileFolder + "/" + LowWallTileName + ".asset";
        private const string FloorTilePath = ArchitecturalTileFolder + "/FloorTile.asset";
        private const string FullWallTilePath = ArchitecturalTileFolder + "/WallTile.asset";
        private const float WallVisualOffset = 0.151f;
        private static readonly List<Object> TransientTileObjects = new List<Object>();

        [MenuItem("No Safe Circle/Rooms/Build Ruined Entry")]
        public static void Build()
        {
            EnsureFolder(Path.GetDirectoryName(ScenePath)?.Replace('\\', '/'));
            EnsureFolder(ArchitecturalTileFolder);
            Scene scene = File.Exists(ScenePath)
                ? EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single)
                : EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // Opening the old scene can unload a newly created Tile sub-asset. Resolve it only
            // after the destination scene is active so the reference survives materialization.
            Tile lowWallTile = LoadOrCreateRuinedEntryLowWallTile(ArchitecturalTileFolder);
            RebuildSceneContents(scene, lowWallTile);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.Refresh();

            Debug.Log($"Ruined Entry scene built at {ScenePath}");
        }

        public static void BuildInMemoryForTests()
        {
            CleanupTransientTiles();
            Tile lowWallTile = AssetDatabase.LoadAssetAtPath<Tile>(LowWallTilePath);
            if (lowWallTile == null)
            {
                lowWallTile = CreateTransientLowWallTile();
            }
            RebuildSceneContents(SceneManager.GetActiveScene(), lowWallTile);
        }

        private static void RebuildSceneContents(Scene scene, Tile lowWallTile)
        {
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                Object.DestroyImmediate(root);
            }

            GameObject roomRoot = new GameObject(RoomRootName);
            roomRoot.AddComponent<RuinedEntryLayout>();

            Transform visibleRoot = CreateContentRoot(
                roomRoot.transform, VisualRootName, RoomContentCategory.Visuals);
            Transform gameplayRoot = CreateContentRoot(
                roomRoot.transform, GameplayRootName, RoomContentCategory.GameplayGeometry);
            Transform anchorsRoot = CreateContentRoot(
                roomRoot.transform, "DoorAnchors", RoomContentCategory.DoorAnchors);
            Transform authoringRoot = CreateContentRoot(
                roomRoot.transform, "Authoring", RoomContentCategory.Authoring);

            BuildVisibleBlockout(visibleRoot, lowWallTile);
            BuildGameplayGeometry(gameplayRoot);
            CreateDoorAnchor(
                anchorsRoot,
                DoorMarkerName,
                DoorId.D1,
                DoorAnchorRole.Exit,
                new Vector3(RuinedEntryLayout.DoorCenterX, 0f, RuinedEntryLayout.DoorCenterZ),
                Quaternion.LookRotation(Vector3.forward));
            CreateMarker(authoringRoot, "D1StagingArea", RuinedEntryLayout.DoorStagingBounds.center);
            CreateMarker(authoringRoot, "PlayerStart", RuinedEntryLayout.PlayerStart);
        }

        private static void BuildVisibleBlockout(Transform parent, Tile lowWallTile)
        {
            Tile floorTile = AssetDatabase.LoadAssetAtPath<Tile>(FloorTilePath);
            Tile fullWallTile = AssetDatabase.LoadAssetAtPath<Tile>(FullWallTilePath);
            if (floorTile == null || fullWallTile == null)
            {
                throw new InvalidOperationException("Ruined Entry requires the existing FloorTile and WallTile assets.");
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
                new Vector3(0.5f, 0f, RuinedEntryLayout.MaximumZ - WallVisualOffset),
                Quaternion.identity, 0);
            PaintStraightWallRun(north, fullWallTile, -8, 12);
            PaintStraightWallRun(north, fullWallTile, 8, 12);

            Tilemap west = CreateVisualTilemap(gridObject.transform, "WestFullWallTilemap",
                new Vector3(RuinedEntryLayout.MinimumX + WallVisualOffset, 0f, -0.5f),
                Quaternion.Euler(0f, 90f, 0f), 0);
            PaintStraightWallRun(west, fullWallTile, 13, 26);

            Tilemap south = CreateVisualTilemap(gridObject.transform, "SouthLowWallTilemap",
                new Vector3(0.5f, 0f, RuinedEntryLayout.MinimumZ + WallVisualOffset),
                Quaternion.identity, 0);
            PaintStraightWallRun(south, lowWallTile, 0, 28);

            Tilemap east = CreateVisualTilemap(gridObject.transform, "EastLowWallTilemap",
                new Vector3(RuinedEntryLayout.MaximumX - WallVisualOffset, 0f, -0.5f),
                Quaternion.Euler(0f, 90f, 0f), 0);
            PaintStraightWallRun(east, lowWallTile, 13, 26);

            CreateVisualBox(parent, "RubbleAVisual", RaisedCenter(RuinedEntryLayout.RubbleABounds,
                    RuinedEntryLayout.RubbleHeight),
                RaisedSize(RuinedEntryLayout.RubbleABounds, RuinedEntryLayout.RubbleHeight));
            CreateVisualBox(parent, "RubbleBVisual", RaisedCenter(RuinedEntryLayout.RubbleBBounds,
                    RuinedEntryLayout.RubbleHeight),
                RaisedSize(RuinedEntryLayout.RubbleBBounds, RuinedEntryLayout.RubbleHeight));
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
            renderer.sortingLayerName = "Default";
            renderer.sortingOrder = sortingOrder;
            return tilemap;
        }

        private static void PaintFloor(Tilemap tilemap, TileBase floorTile)
        {
            float innerMinimumX = RuinedEntryLayout.MinimumX + RuinedEntryLayout.WallThickness * 0.5f;
            float innerMaximumX = RuinedEntryLayout.MaximumX - RuinedEntryLayout.WallThickness * 0.5f;
            float innerMinimumZ = RuinedEntryLayout.MinimumZ + RuinedEntryLayout.WallThickness * 0.5f;
            float innerMaximumZ = RuinedEntryLayout.MaximumZ - RuinedEntryLayout.WallThickness * 0.5f;

            for (int x = -15; x <= 14; x++)
            {
                for (int row = -2; row <= 53; row++)
                {
                    Vector3Int cell = new Vector3Int(x, row, 0);
                    Vector3 center = tilemap.GetCellCenterWorld(cell);
                    if (center.x >= innerMinimumX && center.x <= innerMaximumX &&
                        center.z >= innerMinimumZ && center.z <= innerMaximumZ)
                    {
                        tilemap.SetTile(cell, floorTile);
                    }
                }
            }
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

        private static void BuildGameplayGeometry(Transform parent)
        {
            CreateGameplayBox(parent, "FloorCollision",
                RuinedEntryLayout.RoomBounds.center + Vector3.down * 0.05f,
                new Vector3(RuinedEntryLayout.RoomBounds.size.x, 0.1f, RuinedEntryLayout.RoomBounds.size.z));

            CreateShellBoxes(parent, "Collision", CreateGameplayBox);
            CreateGameplayBox(parent, "RubbleACollision",
                RaisedCenter(RuinedEntryLayout.RubbleABounds, RuinedEntryLayout.RubbleHeight),
                RaisedSize(RuinedEntryLayout.RubbleABounds, RuinedEntryLayout.RubbleHeight));
            CreateGameplayBox(parent, "RubbleBCollision",
                RaisedCenter(RuinedEntryLayout.RubbleBBounds, RuinedEntryLayout.RubbleHeight),
                RaisedSize(RuinedEntryLayout.RubbleBBounds, RuinedEntryLayout.RubbleHeight));
        }

        private static void CreateShellBoxes(
            Transform parent,
            string suffix,
            System.Action<Transform, string, Vector3, Vector3> createBox)
        {
            float centerY = RuinedEntryLayout.WallHeight * 0.5f;
            float roomWidth = RuinedEntryLayout.MaximumX - RuinedEntryLayout.MinimumX;
            float roomDepth = RuinedEntryLayout.MaximumZ - RuinedEntryLayout.MinimumZ;

            createBox(parent, "WestWall" + suffix,
                new Vector3(RuinedEntryLayout.MinimumX, centerY, RuinedEntryLayout.RoomBounds.center.z),
                new Vector3(RuinedEntryLayout.WallThickness, RuinedEntryLayout.WallHeight, roomDepth));
            createBox(parent, "EastWall" + suffix,
                new Vector3(RuinedEntryLayout.MaximumX, centerY, RuinedEntryLayout.RoomBounds.center.z),
                new Vector3(RuinedEntryLayout.WallThickness, RuinedEntryLayout.WallHeight, roomDepth));
            createBox(parent, "SouthWall" + suffix,
                new Vector3(RuinedEntryLayout.RoomBounds.center.x, centerY, RuinedEntryLayout.MinimumZ),
                new Vector3(roomWidth, RuinedEntryLayout.WallHeight, RuinedEntryLayout.WallThickness));

            float northSegmentWidth = (roomWidth - RuinedEntryLayout.DoorOpeningWidth) * 0.5f;
            float northOffset = (RuinedEntryLayout.DoorOpeningWidth + northSegmentWidth) * 0.5f;
            createBox(parent, "NorthWallWest" + suffix,
                new Vector3(-northOffset, centerY, RuinedEntryLayout.MaximumZ),
                new Vector3(northSegmentWidth, RuinedEntryLayout.WallHeight, RuinedEntryLayout.WallThickness));
            createBox(parent, "NorthWallEast" + suffix,
                new Vector3(northOffset, centerY, RuinedEntryLayout.MaximumZ),
                new Vector3(northSegmentWidth, RuinedEntryLayout.WallHeight, RuinedEntryLayout.WallThickness));
        }

        public static Tile LoadOrCreateRuinedEntryLowWallTile(string assetFolder)
        {
            if (string.IsNullOrWhiteSpace(assetFolder) || !assetFolder.StartsWith("Assets/", StringComparison.Ordinal))
            {
                throw new ArgumentException("The low-wall Tile asset folder must be under Assets.", nameof(assetFolder));
            }

            EnsureFolder(assetFolder);
            string assetPath = assetFolder + "/" + LowWallTileName + ".asset";
            Color32[] pixels = CreateLowWallPixels();
            Tile tile = AssetDatabase.LoadAssetAtPath<Tile>(assetPath);
            if (tile == null)
            {
                tile = ScriptableObject.CreateInstance<Tile>();
                tile.name = LowWallTileName;
                tile.colliderType = Tile.ColliderType.None;
                AssetDatabase.CreateAsset(tile, assetPath);
                ReplaceLowWallVisual(tile, pixels);
            }
            else if (!LowWallVisualMatches(tile, pixels))
            {
                ReplaceLowWallVisual(tile, pixels);
            }
            else if (tile.colliderType != Tile.ColliderType.None)
            {
                tile.colliderType = Tile.ColliderType.None;
                EditorUtility.SetDirty(tile);
                AssetDatabase.SaveAssetIfDirty(tile);
            }

            return tile;
        }

        private static Tile CreateTransientLowWallTile()
        {
            Tile tile = ScriptableObject.CreateInstance<Tile>();
            tile.name = LowWallTileName;
            tile.colliderType = Tile.ColliderType.None;
            tile.hideFlags = HideFlags.HideAndDontSave;
            Texture2D texture = CreateLowWallTexture(CreateLowWallPixels());
            texture.hideFlags = HideFlags.HideAndDontSave;
            Sprite sprite = Sprite.Create(texture, new Rect(0f, 0f, 64f, 32f), new Vector2(0.5f, 0f), 64f);
            sprite.name = LowWallTileName + "Sprite";
            sprite.hideFlags = HideFlags.HideAndDontSave;
            tile.sprite = sprite;
            TransientTileObjects.Add(tile);
            TransientTileObjects.Add(texture);
            TransientTileObjects.Add(sprite);
            return tile;
        }

        private static void CleanupTransientTiles()
        {
            for (int index = TransientTileObjects.Count - 1; index >= 0; index--)
            {
                if (TransientTileObjects[index] != null)
                {
                    Object.DestroyImmediate(TransientTileObjects[index]);
                }
            }
            TransientTileObjects.Clear();
        }

        private static Color32[] CreateLowWallPixels()
        {
            const int width = 64;
            const int height = 32;
            const int repeatPeriod = 32;
            Color32[] pixels = new Color32[width * height];
            Color32 stone = new Color32(77, 70, 67, 255);
            Color32 alternate = new Color32(88, 79, 73, 255);
            Color32 mortar = new Color32(39, 35, 35, 255);
            for (int y = 0; y < height; y++)
            {
                int course = y / 16;
                for (int x = 0; x < width; x++)
                {
                    int phase = (x + course * 16) % repeatPeriod;
                    bool isMortar = y % 16 < 2 || phase < 2;
                    pixels[y * width + x] = isMortar ? mortar : (course == 0 ? stone : alternate);
                }
            }
            return pixels;
        }

        private static Texture2D CreateLowWallTexture(Color32[] pixels)
        {
            Texture2D texture = new Texture2D(64, 32, TextureFormat.RGBA32, false)
            {
                name = LowWallTileName + "Texture",
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Repeat
            };
            texture.SetPixels32(pixels);
            texture.Apply(false, false);
            return texture;
        }

        private static bool LowWallVisualMatches(Tile tile, Color32[] pixels)
        {
            Sprite sprite = tile.sprite;
            if (sprite == null || sprite.texture == null || sprite.texture.width != 64 || sprite.texture.height != 32 ||
                !Mathf.Approximately(sprite.pixelsPerUnit, 64f) ||
                Vector2.Distance(sprite.pivot, new Vector2(32f, 0f)) > 0.01f)
            {
                return false;
            }

            try
            {
                Color32[] persisted = sprite.texture.GetPixels32();
                if (persisted.Length != pixels.Length) return false;
                for (int index = 0; index < pixels.Length; index++)
                {
                    if (!persisted[index].Equals(pixels[index])) return false;
                }
                return true;
            }
            catch (UnityException)
            {
                return false;
            }
        }

        private static void ReplaceLowWallVisual(Tile tile, Color32[] pixels)
        {
            Sprite previousSprite = tile.sprite;
            Texture2D previousTexture = previousSprite != null ? previousSprite.texture : null;
            tile.sprite = null;
            if (previousSprite != null && AssetDatabase.Contains(previousSprite)) Object.DestroyImmediate(previousSprite, true);
            if (previousTexture != null && AssetDatabase.Contains(previousTexture)) Object.DestroyImmediate(previousTexture, true);

            Texture2D texture = CreateLowWallTexture(pixels);
            AssetDatabase.AddObjectToAsset(texture, tile);
            Sprite sprite = Sprite.Create(texture, new Rect(0f, 0f, 64f, 32f), new Vector2(0.5f, 0f), 64f);
            sprite.name = LowWallTileName + "Sprite";
            AssetDatabase.AddObjectToAsset(sprite, tile);
            tile.sprite = sprite;
            tile.colliderType = Tile.ColliderType.None;
            EditorUtility.SetDirty(texture);
            EditorUtility.SetDirty(sprite);
            EditorUtility.SetDirty(tile);
            AssetDatabase.SaveAssetIfDirty(tile);
        }

        private static Transform CreateContentRoot(
            Transform parent,
            string name,
            RoomContentCategory category)
        {
            GameObject child = new GameObject(name);
            child.transform.SetParent(parent, false);

            RoomContentMarker marker = child.AddComponent<RoomContentMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.RuinedEntry;
            serialized.FindProperty("category").enumValueIndex = (int)category;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            return child.transform;
        }

        private static void CreateVisualBox(Transform parent, string name, Vector3 position, Vector3 size)
        {
            GameObject box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            box.transform.localScale = size;
            Object.DestroyImmediate(box.GetComponent<Collider>());
        }

        private static void CreateGameplayBox(Transform parent, string name, Vector3 position, Vector3 size)
        {
            GameObject box = new GameObject(name);
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            BoxCollider collider = box.AddComponent<BoxCollider>();
            collider.size = size;
        }

        private static void CreateMarker(Transform parent, string name, Vector3 position)
        {
            GameObject marker = new GameObject(name);
            marker.transform.SetParent(parent, false);
            marker.transform.position = position;
        }

        private static void CreateDoorAnchor(
            Transform parent,
            string name,
            DoorId doorId,
            DoorAnchorRole role,
            Vector3 position,
            Quaternion rotation)
        {
            GameObject anchor = new GameObject(name);
            anchor.transform.SetParent(parent, false);
            anchor.transform.SetPositionAndRotation(position, rotation);

            DoorAnchorMarker marker = anchor.AddComponent<DoorAnchorMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.RuinedEntry;
            serialized.FindProperty("doorId").enumValueIndex = (int)doorId;
            serialized.FindProperty("role").enumValueIndex = (int)role;
            serialized.FindProperty("openingWidth").floatValue = 3f;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static Vector3 RaisedCenter(Bounds bounds, float height)
        {
            return new Vector3(bounds.center.x, height * 0.5f, bounds.center.z);
        }

        private static Vector3 RaisedSize(Bounds bounds, float height)
        {
            return new Vector3(bounds.size.x, height, bounds.size.z);
        }

        private static void EnsureFolder(string folder)
        {
            if (string.IsNullOrWhiteSpace(folder) || AssetDatabase.IsValidFolder(folder))
            {
                return;
            }

            Directory.CreateDirectory(folder);
            AssetDatabase.Refresh();
        }
    }
}
