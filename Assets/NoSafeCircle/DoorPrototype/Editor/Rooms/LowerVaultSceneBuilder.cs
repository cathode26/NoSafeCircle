using System;
using System.Collections.Generic;
using System.IO;
using NoSafeCircle.DoorPrototype.Editor.World;
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
    /// <summary>Builds the Lower Vault authoring scene without touching the canonical gameplay scene.</summary>
    public static class LowerVaultSceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/Rooms/LowerVault.unity";

        private const string ArchitecturalTileFolder =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";
        private const string FullWallTilePath = ArchitecturalTileFolder + "/WallTile.asset";
        private const string WorldSpriteVisualPrefabPath =
            ArchitecturalTileFolder + "/WorldSprites/WorldSpriteVisual.prefab";

        // NSC-109 AC-001/AC-002: this room's own floor Tile, owned and materialized here rather
        // than borrowed from a room-agnostic shared asset, so it can be bound to this room's own
        // committed floor sprite.
        private const string FloorTileName = "LowerVaultFloorTile";
        private const string FloorTilePath = ArchitecturalTileFolder + "/" + FloorTileName + ".asset";
        private const string FloorSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_LowerVault.png";

        private const string NearWallStubTileName = "LowerVaultNearWallStubTile";
        private const string NearWallStubTilePath = ArchitecturalTileFolder + "/" + NearWallStubTileName + ".asset";
        private const string NearWallStubSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_broken_stub.png";

        private const string BlockoutProxySpriteName = "LowerVaultBlockoutProxySprite";
        private const string BlockoutProxySpritePath = ArchitecturalTileFolder + "/" + BlockoutProxySpriteName + ".asset";
        private const int BlockoutProxyTextureSize = 64;
        private const float BlockoutProxyPixelsPerUnit = 64f;
        private static readonly Vector2 BlockoutProxyPivot = new Vector2(0.5f, 0f);
        private const string WallAccentsRootName = "WallAccents";

        // RuinedEntrySceneBuilder.WallVisualOffset: every wall Tilemap stands this far inside its
        // RoomBounds line so its bottom-pivot sprites never extend past the gameplay wall collider.
        private const float WallVisualOffset = 0.151f;

        private const string WizardReviewSpritePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south.png";

        private static readonly List<Object> TransientArchitecturalObjects = new List<Object>();

        [MenuItem("No Safe Circle/Rooms/Build Lower Vault Authoring Scene")]
        public static void BuildAndSave()
        {
            EnsureFolder(Path.GetDirectoryName(ScenePath)?.Replace('\\', '/'));
            EnsureFolder(ArchitecturalTileFolder);
            Scene scene = File.Exists(ScenePath)
                ? EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single)
                : EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // Opening the old scene can unload a newly created Tile/Sprite sub-asset. Resolve them
            // only after the destination scene is active so the references survive materialization.
            Tile floorTile = LoadOrCreateFloorTile(ArchitecturalTileFolder);
            Tile nearWallStubTile = LoadOrCreateNearWallStubTile(ArchitecturalTileFolder);
            Sprite blockoutProxySprite = LoadOrCreateBlockoutProxySprite(ArchitecturalTileFolder);
            RebuildSceneContents(scene, floorTile, nearWallStubTile, blockoutProxySprite);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
        }

        public static void BuildInMemoryForTests()
        {
            CleanupTransientArchitecturalObjects();

            Tile floorTile = AssetDatabase.LoadAssetAtPath<Tile>(FloorTilePath);
            if (floorTile == null)
            {
                floorTile = CreateTransientTile(FloorTileName, FloorSpriteSourcePath);
            }

            Tile nearWallStubTile = AssetDatabase.LoadAssetAtPath<Tile>(NearWallStubTilePath);
            if (nearWallStubTile == null)
            {
                nearWallStubTile = CreateTransientTile(NearWallStubTileName, NearWallStubSpriteSourcePath);
            }

            Sprite blockoutProxySprite = LoadPersistedBlockoutProxySprite();
            if (blockoutProxySprite == null)
            {
                blockoutProxySprite = CreateTransientBlockoutProxySprite();
            }

            RebuildSceneContents(SceneManager.GetActiveScene(), floorTile, nearWallStubTile, blockoutProxySprite);
        }

        // AC-005/GAME_TASK_LESSONS_LEARNED: a non-destructive staging tool. It never saves the
        // untitled staging Scene, never saves LowerVault.unity (opened additively), and never
        // writes to any tracked asset; closing it afterward leaves the repository untouched.
        [MenuItem("No Safe Circle/Rooms/Stage Lower Vault Camera Review")]
        public static void StageCameraReview()
        {
            Scene stagingScene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Additive);
            SceneManager.SetActiveScene(stagingScene);

            GameObject standIn = new GameObject("WizardReviewStandIn");
            SpriteRenderer standInRenderer = standIn.AddComponent<SpriteRenderer>();
            standInRenderer.sprite = AssetDatabase.LoadAssetAtPath<Sprite>(WizardReviewSpritePath);
            standInRenderer.sortingLayerName = DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName;
            standInRenderer.spriteSortPoint = SpriteSortPoint.Pivot;

            DoorPrototypeGlobalSceneBuilder.BuildCamera(standIn.transform);

            CreateReviewMarker("D3ApronMarker", -8f, 57f);
            CreateReviewMarker("C1LeftLaneMarker", -6f, 62f);
            CreateReviewMarker("C1RightLaneMarker", 4.5f, 62f);
            CreateReviewMarker("NorthMergeWestMarker", -2.5f, 66f);
            CreateReviewMarker("NorthMergeEastMarker", 3.5f, 66f);
            CreateReviewMarker("WestStoragePocketMarker", -16f, 64f);
            CreateReviewMarker("EastStoragePocketMarker", 16f, 63f);
            CreateReviewMarker("PrimaryCrossingMarker", 9.5f, 69f);
            CreateReviewMarker("D4ApronMarker", 4f, 73f);
        }

        private static void CreateReviewMarker(string name, float x, float z)
        {
            GameObject marker = new GameObject(name);
            marker.transform.position = new Vector3(x, 0f, z);
        }

        private static void RebuildSceneContents(
            Scene scene, Tile floorTile, Tile nearWallStubTile, Sprite blockoutProxySprite)
        {
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                Object.DestroyImmediate(root);
            }

            GameObject roomRoot = new GameObject("Room_LowerVault");
            Transform visibleRoot = CreateContentRoot(
                roomRoot.transform, "Visuals", RoomContentCategory.Visuals);
            Transform gameplayRoot = CreateContentRoot(
                roomRoot.transform, "GameplayGeometry", RoomContentCategory.GameplayGeometry);
            Transform anchorsRoot = CreateContentRoot(
                roomRoot.transform, "DoorAnchors", RoomContentCategory.DoorAnchors);
            Transform authoringRoot = CreateContentRoot(
                roomRoot.transform, "Authoring", RoomContentCategory.Authoring);

            BuildWallsAndFloor(visibleRoot, floorTile, nearWallStubTile);
            BuildBlockoutObstacleProxies(visibleRoot, blockoutProxySprite);
            BuildWallAccents(visibleRoot);
            BuildGameplayGeometry(gameplayRoot);

            CreateDoorAnchor(
                anchorsRoot, "D3Opening", DoorId.D3, DoorAnchorRole.Entry,
                LowerVaultLayout.D3, Quaternion.LookRotation(Vector3.back));
            CreateDoorAnchor(
                anchorsRoot, "D4Opening", DoorId.D4, DoorAnchorRole.Exit,
                LowerVaultLayout.D4, Quaternion.LookRotation(Vector3.forward));

            CreateMarker(authoringRoot, "D3StagingArea", LowerVaultLayout.D3Apron.center);
            CreateMarker(authoringRoot, "D4StagingArea", LowerVaultLayout.D4Apron.center);

            SceneManager.SetActiveScene(scene);
        }

        // ------------------------------------------------------------------
        // Visuals: IsometricZAsY Grid (floor + four straight-run wall Tilemaps)
        // ------------------------------------------------------------------

        private static void BuildWallsAndFloor(Transform parent, Tile floorTile, Tile nearWallStubTile)
        {
            Tile fullWallTile = AssetDatabase.LoadAssetAtPath<Tile>(FullWallTilePath);
            if (fullWallTile == null)
            {
                throw new InvalidOperationException("Lower Vault requires the existing WallTile asset.");
            }

            GameObject gridObject = new GameObject("IsometricZAsY", typeof(Grid));
            gridObject.transform.SetParent(parent, false);
            Grid grid = gridObject.GetComponent<Grid>();
            grid.cellSize = new Vector3(1f, 0.5f, 1f);
            grid.cellSwizzle = GridLayout.CellSwizzle.XYZ;

            Tilemap floor = CreateVisualTilemap(gridObject.transform, "FloorTilemap",
                new Vector3(0f, 0.01f, 0f), Quaternion.Euler(-90f, 0f, 0f),
                DoorPrototypeSceneBuilder.BackgroundGroundSortingOrder);
            PaintFloor(floor, floorTile);

            // North and west walls are full height.
            Tilemap north = CreateVisualTilemap(gridObject.transform, "NorthFullWallTilemap",
                new Vector3(0.5f, 0f, LowerVaultLayout.MaximumZ - WallVisualOffset), Quaternion.identity, 0);
            PaintStraightWallRun(north, fullWallTile, -9, 22); // X [-20,+2]
            PaintStraightWallRun(north, fullWallTile, 13, 14); // X [+6,+20], leaves the D4 gap X [+2,+6]

            Tilemap west = CreateVisualTilemap(gridObject.transform, "WestFullWallTilemap",
                new Vector3(LowerVaultLayout.MinimumX + WallVisualOffset, 0f, -0.5f),
                Quaternion.Euler(0f, 90f, 0f), 0);
            PaintStraightWallRun(west, fullWallTile, -65, 22); // Z [54,76]

            // South and east walls are cutaway walls that stop at their door opening.
            Tilemap south = CreateVisualTilemap(gridObject.transform, "SouthLowWallTilemap",
                new Vector3(0.5f, 0f, LowerVaultLayout.MinimumZ + WallVisualOffset), Quaternion.identity, 0);
            PaintStraightWallRun(south, nearWallStubTile, -15, 10); // X [-20,-10]
            PaintStraightWallRun(south, nearWallStubTile, 7, 26);   // X [-6,+20], leaves the D3 gap X [-10,-6]

            Tilemap east = CreateVisualTilemap(gridObject.transform, "EastLowWallTilemap",
                new Vector3(LowerVaultLayout.MaximumX - WallVisualOffset, 0f, -0.5f),
                Quaternion.Euler(0f, 90f, 0f), 0);
            PaintStraightWallRun(east, nearWallStubTile, -65, 22); // Z [54,76]
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

        // Paints FloorTile in every cell whose GetCellCenterWorld lies inside the wall-collider
        // inner faces. Bounds are resolved through WorldToCell so the loop range is correct
        // regardless of the Tilemap's own rotation.
        // NSC-109 wall-floor gap: paint every cell whose FULL FOOTPRINT lies inside the room
        // bounds, which is the convention FinalRoomSceneBuilder and BoneArchiveSceneBuilder
        // already use and the only two rooms with no visible gap. Testing the anchor against
        // the wall-collider INNER faces stopped the floor short of the wall's visual plane,
        // which sits at MaximumX - WallVisualOffset (0.151) rather than at the collider face.
        // The overshoot is hidden: walls render at sortingOrder 0 over the floor's -100.
        public static bool FloorCellIsInsideRoom(Vector3 cellCorner, Vector3 cellSize)
        {
            const float tolerance = 0.001f;
            return cellCorner.x >= LowerVaultLayout.MinimumX - tolerance
                && cellCorner.x + cellSize.x <= LowerVaultLayout.MaximumX + tolerance
                && cellCorner.z - cellSize.y >= LowerVaultLayout.MinimumZ - tolerance
                && cellCorner.z <= LowerVaultLayout.MaximumZ + tolerance;
        }

        private static void PaintFloor(Tilemap tilemap, TileBase floorTile)
        {
            Vector3Int cornerA = tilemap.WorldToCell(new Vector3(LowerVaultLayout.MinimumX, 0f, LowerVaultLayout.MinimumZ));
            Vector3Int cornerB = tilemap.WorldToCell(new Vector3(LowerVaultLayout.MaximumX, 0f, LowerVaultLayout.MaximumZ));
            Vector3Int cornerC = tilemap.WorldToCell(new Vector3(LowerVaultLayout.MinimumX, 0f, LowerVaultLayout.MaximumZ));
            Vector3Int cornerD = tilemap.WorldToCell(new Vector3(LowerVaultLayout.MaximumX, 0f, LowerVaultLayout.MinimumZ));

            int minCellX = Mathf.Min(Mathf.Min(cornerA.x, cornerB.x), Mathf.Min(cornerC.x, cornerD.x)) - 1;
            int maxCellX = Mathf.Max(Mathf.Max(cornerA.x, cornerB.x), Mathf.Max(cornerC.x, cornerD.x)) + 1;
            int minCellY = Mathf.Min(Mathf.Min(cornerA.y, cornerB.y), Mathf.Min(cornerC.y, cornerD.y)) - 1;
            int maxCellY = Mathf.Max(Mathf.Max(cornerA.y, cornerB.y), Mathf.Max(cornerC.y, cornerD.y)) + 1;

            for (int x = minCellX; x <= maxCellX; x++)
            {
                for (int y = minCellY; y <= maxCellY; y++)
                {
                    Vector3Int cell = new Vector3Int(x, y, 0);
                    Vector3 corner = tilemap.GetCellCenterWorld(cell);
                    if (FloorCellIsInsideRoom(corner, tilemap.layoutGrid.cellSize))
                    {
                        tilemap.SetTile(cell, floorTile);
                    }
                }
            }
        }

        // Behaves exactly like RuinedEntrySceneBuilder.PaintStraightWallRun: the only repeated-
        // cell loop the walls use, painting cellCount contiguous cells with one shared Tile.
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

        // ------------------------------------------------------------------
        // Visuals: collider-free blockout obstacle proxies
        // ------------------------------------------------------------------

        private static void BuildBlockoutObstacleProxies(Transform parent, Sprite proxySprite)
        {
            GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(WorldSpriteVisualPrefabPath);
            if (prefab == null)
            {
                throw new InvalidOperationException("Lower Vault requires the existing WorldSpriteVisual prefab.");
            }

            GameObject proxiesRoot = new GameObject("BlockoutObstacleProxies");
            proxiesRoot.transform.SetParent(parent, false);

            CreateBlockoutProxy(proxiesRoot.transform, prefab, "LV-C1Proxy", LowerVaultLayout.CentralColumnCluster, proxySprite);
            CreateBlockoutProxy(proxiesRoot.transform, prefab, "LV-W1Proxy", LowerVaultLayout.WestStoragePile, proxySprite);
            CreateBlockoutProxy(proxiesRoot.transform, prefab, "LV-E1Proxy", LowerVaultLayout.EastStoragePile, proxySprite);
            CreateBlockoutProxy(proxiesRoot.transform, prefab, "LV-N1Proxy", LowerVaultLayout.NorthWestStorageBar, proxySprite);
            CreateBlockoutProxy(proxiesRoot.transform, prefab, "LV-H1-WestProxy", LowerVaultLayout.HallWestSpan, proxySprite);
            CreateBlockoutProxy(proxiesRoot.transform, prefab, "LV-H1-CenterProxy", LowerVaultLayout.HallCenterSpan, proxySprite);
            CreateBlockoutProxy(proxiesRoot.transform, prefab, "LV-H1-EastProxy", LowerVaultLayout.HallEastSpan, proxySprite);
        }

        private static void CreateBlockoutProxy(
            Transform parent, GameObject prefab, string name, Bounds footprint, Sprite proxySprite)
        {
            GameObject instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            instance.name = name;
            instance.transform.SetParent(parent, false);
            instance.transform.localPosition = new Vector3(footprint.center.x, 0f, footprint.center.z);
            instance.transform.localRotation = Quaternion.identity;
            instance.transform.localScale = new Vector3(footprint.size.x, footprint.size.y, 1f);

            SpriteRenderer renderer = instance.GetComponent<SpriteRenderer>();
            renderer.sprite = proxySprite;
            renderer.sortingLayerName = DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName;
            renderer.sortingOrder = 0;
        }

        // NSC-126 AC-001/AC-003/AC-004: places the corner/jamb/end-cap accents NSC-120 delivered,
        // from this room's own committed RoomBounds, floor Y and D3/D4 door openings -- no new
        // door coordinates or bounds are introduced here. Nested under Visuals rather than as a
        // direct child of the room root because RoomSceneComposer.ValidateContentCategories
        // requires every direct room-root child to carry a RoomContentMarker for one of its four
        // categories; the whole room is rebuilt from scratch on every call, so this is idempotent
        // for free.
        private static void BuildWallAccents(Transform visuals)
        {
            Bounds roomBounds = LowerVaultLayout.RoomBounds;
            var doorOpenings = new List<WallAccentDoorOpening>
            {
                new WallAccentDoorOpening(WallSide.South, LowerVaultLayout.D3.x, LowerVaultLayout.DoorWidth),
                new WallAccentDoorOpening(WallSide.North, LowerVaultLayout.D4.x, LowerVaultLayout.DoorWidth)
            };
            WallAccentRoomGeometry geometry = ArchitecturalWallAccentPlacement.BuildRectangularRoomGeometry(
                roomBounds, roomBounds.center.y, doorOpenings);

            GameObject accentsRoot = new GameObject(WallAccentsRootName);
            accentsRoot.transform.SetParent(visuals, false);
            ArchitecturalWallAccentPlacement.Place(accentsRoot.transform, geometry);
        }

        // ------------------------------------------------------------------
        // GameplayGeometry: floor + wall + obstacle colliders
        // ------------------------------------------------------------------

        private static void BuildGameplayGeometry(Transform parent)
        {
            CreateGameplayBox(parent, "FloorCollision",
                LowerVaultLayout.RoomBounds.center + Vector3.down * 0.05f,
                new Vector3(LowerVaultLayout.RoomBounds.size.x, 0.1f, LowerVaultLayout.RoomBounds.size.z));

            CreateShellBoxes(parent);

            CreateGameplayObstacle(parent, "LV-C1Collision", LowerVaultLayout.CentralColumnCluster);
            CreateGameplayObstacle(parent, "LV-W1Collision", LowerVaultLayout.WestStoragePile);
            CreateGameplayObstacle(parent, "LV-E1Collision", LowerVaultLayout.EastStoragePile);
            CreateGameplayObstacle(parent, "LV-N1Collision", LowerVaultLayout.NorthWestStorageBar);

            CreateGameplayObstacle(parent, "LV-H1-WestCollision", LowerVaultLayout.HallWestSpan);
            CreateGameplayObstacle(parent, "LV-H1-CenterCollision", LowerVaultLayout.HallCenterSpan);
            CreateGameplayObstacle(parent, "LV-H1-EastCollision", LowerVaultLayout.HallEastSpan);
        }

        private static void CreateShellBoxes(Transform parent)
        {
            float centerY = LowerVaultLayout.WallHeight * 0.5f;
            float roomDepth = LowerVaultLayout.MaximumZ - LowerVaultLayout.MinimumZ;

            CreateGameplayBox(parent, "WestWallCollision",
                new Vector3(LowerVaultLayout.MinimumX, centerY, LowerVaultLayout.RoomBounds.center.z),
                new Vector3(LowerVaultLayout.WallThickness, LowerVaultLayout.WallHeight, roomDepth));
            CreateGameplayBox(parent, "EastWallCollision",
                new Vector3(LowerVaultLayout.MaximumX, centerY, LowerVaultLayout.RoomBounds.center.z),
                new Vector3(LowerVaultLayout.WallThickness, LowerVaultLayout.WallHeight, roomDepth));

            CreateOpeningWallCollision(parent, "SouthWall", LowerVaultLayout.D3.x, LowerVaultLayout.MinimumZ);
            CreateOpeningWallCollision(parent, "NorthWall", LowerVaultLayout.D4.x, LowerVaultLayout.MaximumZ);
        }

        private static void CreateOpeningWallCollision(Transform parent, string name, float openingCenter, float z)
        {
            float halfOpening = LowerVaultLayout.DoorWidth * 0.5f;
            float westLength = openingCenter - halfOpening - LowerVaultLayout.MinimumX;
            float eastLength = LowerVaultLayout.MaximumX - openingCenter - halfOpening;
            float centerY = LowerVaultLayout.WallHeight * 0.5f;

            CreateGameplayBox(parent, name + "WestCollision",
                new Vector3(LowerVaultLayout.MinimumX + westLength * 0.5f, centerY, z),
                new Vector3(westLength, LowerVaultLayout.WallHeight, LowerVaultLayout.WallThickness));
            CreateGameplayBox(parent, name + "EastCollision",
                new Vector3(LowerVaultLayout.MaximumX - eastLength * 0.5f, centerY, z),
                new Vector3(eastLength, LowerVaultLayout.WallHeight, LowerVaultLayout.WallThickness));
        }

        private static void CreateGameplayObstacle(Transform parent, string name, Bounds bounds)
        {
            CreateGameplayBox(parent, name, bounds.center, bounds.size);
        }

        private static void CreateGameplayBox(Transform parent, string name, Vector3 position, Vector3 size)
        {
            GameObject box = new GameObject(name);
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            BoxCollider collider = box.AddComponent<BoxCollider>();
            collider.size = size;
        }

        // ------------------------------------------------------------------
        // DoorAnchors / Authoring
        // ------------------------------------------------------------------

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
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.LowerVault;
            serialized.FindProperty("doorId").enumValueIndex = (int)doorId;
            serialized.FindProperty("role").enumValueIndex = (int)role;
            serialized.FindProperty("openingWidth").floatValue = LowerVaultLayout.DoorWidth;
            serialized.ApplyModifiedPropertiesWithoutUndo();
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
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.LowerVault;
            serialized.FindProperty("category").enumValueIndex = (int)category;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            return child.transform;
        }

        // ------------------------------------------------------------------
        // NSC-109 AC-001/AC-002: LowerVaultFloorTile.asset and LowerVaultNearWallStubTile.asset,
        // now bound to the committed floor_LowerVault and wall_broken_stub sprites instead of
        // procedurally generated textures.
        // ------------------------------------------------------------------

        public static Tile LoadOrCreateFloorTile(string assetFolder)
        {
            return LoadOrCreateSpriteTile(assetFolder, FloorTileName, FloorSpriteSourcePath);
        }

        public static Tile LoadOrCreateNearWallStubTile(string assetFolder)
        {
            return LoadOrCreateSpriteTile(assetFolder, NearWallStubTileName, NearWallStubSpriteSourcePath);
        }

        private static Tile LoadOrCreateSpriteTile(string assetFolder, string tileName, string sourceSpritePath)
        {
            if (string.IsNullOrWhiteSpace(assetFolder) || !assetFolder.StartsWith("Assets/", StringComparison.Ordinal))
            {
                throw new ArgumentException("The Tile asset folder must be under Assets.", nameof(assetFolder));
            }

            Sprite sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourceSpritePath);
            if (sourceSprite == null)
            {
                throw new InvalidOperationException(
                    $"Lower Vault requires the committed sprite at '{sourceSpritePath}'.");
            }

            EnsureFolder(assetFolder);
            string assetPath = assetFolder + "/" + tileName + ".asset";
            Tile tile = AssetDatabase.LoadAssetAtPath<Tile>(assetPath);
            if (tile == null)
            {
                tile = ScriptableObject.CreateInstance<Tile>();
                tile.name = tileName;
                tile.colliderType = Tile.ColliderType.None;
                tile.sprite = sourceSprite;
                AssetDatabase.CreateAsset(tile, assetPath);
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

        private static Tile CreateTransientTile(string tileName, string sourceSpritePath)
        {
            Sprite sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourceSpritePath);
            if (sourceSprite == null)
            {
                throw new InvalidOperationException(
                    $"Lower Vault requires the committed sprite at '{sourceSpritePath}'.");
            }

            Tile tile = ScriptableObject.CreateInstance<Tile>();
            tile.name = tileName;
            tile.colliderType = Tile.ColliderType.None;
            tile.hideFlags = HideFlags.HideAndDontSave;
            tile.sprite = sourceSprite;
            TransientArchitecturalObjects.Add(tile);
            return tile;
        }

        // ------------------------------------------------------------------
        // LowerVaultBlockoutProxySprite.asset: shared original proxy Sprite
        // ------------------------------------------------------------------

        public static Sprite LoadOrCreateBlockoutProxySprite(string assetFolder)
        {
            if (string.IsNullOrWhiteSpace(assetFolder) || !assetFolder.StartsWith("Assets/", StringComparison.Ordinal))
            {
                throw new ArgumentException("The blockout proxy Sprite asset folder must be under Assets.", nameof(assetFolder));
            }

            EnsureFolder(assetFolder);
            string assetPath = assetFolder + "/" + BlockoutProxySpriteName + ".asset";
            Color32[] pixels = CreateBlockoutProxyPixels();

            Texture2D existingTexture = AssetDatabase.LoadAssetAtPath<Texture2D>(assetPath);
            if (existingTexture != null)
            {
                if (!BlockoutProxyPixelsMatch(existingTexture, pixels))
                {
                    ReplaceBlockoutProxyPixels(existingTexture, pixels);
                }

                foreach (Object subAsset in AssetDatabase.LoadAllAssetsAtPath(assetPath))
                {
                    if (subAsset is Sprite existingSprite) return existingSprite;
                }
            }

            Texture2D texture = CreateProxyTexture(pixels);
            AssetDatabase.CreateAsset(texture, assetPath);
            Sprite sprite = Sprite.Create(
                texture,
                new Rect(0f, 0f, BlockoutProxyTextureSize, BlockoutProxyTextureSize),
                BlockoutProxyPivot,
                BlockoutProxyPixelsPerUnit);
            sprite.name = BlockoutProxySpriteName;
            AssetDatabase.AddObjectToAsset(sprite, texture);
            EditorUtility.SetDirty(texture);
            EditorUtility.SetDirty(sprite);
            AssetDatabase.SaveAssetIfDirty(texture);
            return sprite;
        }

        private static Sprite LoadPersistedBlockoutProxySprite()
        {
            Texture2D existingTexture = AssetDatabase.LoadAssetAtPath<Texture2D>(BlockoutProxySpritePath);
            if (existingTexture == null) return null;

            foreach (Object subAsset in AssetDatabase.LoadAllAssetsAtPath(BlockoutProxySpritePath))
            {
                if (subAsset is Sprite sprite) return sprite;
            }
            return null;
        }

        private static Sprite CreateTransientBlockoutProxySprite()
        {
            Texture2D texture = CreateProxyTexture(CreateBlockoutProxyPixels());
            texture.hideFlags = HideFlags.HideAndDontSave;
            Sprite sprite = Sprite.Create(
                texture,
                new Rect(0f, 0f, BlockoutProxyTextureSize, BlockoutProxyTextureSize),
                BlockoutProxyPivot,
                BlockoutProxyPixelsPerUnit);
            sprite.name = BlockoutProxySpriteName;
            sprite.hideFlags = HideFlags.HideAndDontSave;
            TransientArchitecturalObjects.Add(texture);
            TransientArchitecturalObjects.Add(sprite);
            return sprite;
        }

        private static Texture2D CreateProxyTexture(Color32[] pixels)
        {
            Texture2D texture = new Texture2D(BlockoutProxyTextureSize, BlockoutProxyTextureSize, TextureFormat.RGBA32, false)
            {
                name = BlockoutProxySpriteName + "Texture",
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Clamp
            };
            texture.SetPixels32(pixels);
            texture.Apply(false, false);
            return texture;
        }

        // Original bordered-marker fill; distinct from every other architectural tile's palette
        // so a blockout proxy is never mistaken for finished dressing.
        private static Color32[] CreateBlockoutProxyPixels()
        {
            const int width = BlockoutProxyTextureSize;
            const int height = BlockoutProxyTextureSize;
            const int borderThicknessPx = 4;
            // WAS magenta (96,46,74) with a (198,132,165) edge, which read as a rendering
            // fault rather than as a blockout. The edge ratio is KEPT - the original drew
            // its border at roughly 2x the fill's channels to mark the proxy's extent, so
            // repointing the fill preserves that relationship instead of inventing a tone.
            Color32 fill = RoomPlaceholderVisuals.BlockoutPlaceholder;
            Color32 border = RoomPlaceholderVisuals.EdgeFrom(fill, 2.06f);
            Color32[] pixels = new Color32[width * height];
            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    bool onBorder = x < borderThicknessPx || y < borderThicknessPx ||
                        x >= width - borderThicknessPx || y >= height - borderThicknessPx;
                    pixels[y * width + x] = onBorder ? border : fill;
                }
            }
            return pixels;
        }

        private static bool BlockoutProxyPixelsMatch(Texture2D texture, Color32[] pixels)
        {
            if (texture.width != BlockoutProxyTextureSize || texture.height != BlockoutProxyTextureSize)
            {
                return false;
            }

            try
            {
                Color32[] persisted = texture.GetPixels32();
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

        private static void ReplaceBlockoutProxyPixels(Texture2D texture, Color32[] pixels)
        {
            if (texture.width != BlockoutProxyTextureSize || texture.height != BlockoutProxyTextureSize)
            {
                texture.Reinitialize(BlockoutProxyTextureSize, BlockoutProxyTextureSize, TextureFormat.RGBA32, false);
            }
            texture.SetPixels32(pixels);
            texture.Apply(false, false);
            EditorUtility.SetDirty(texture);
            AssetDatabase.SaveAssetIfDirty(texture);
        }

        // ------------------------------------------------------------------
        // Shared transient-object ownership (parameterless in-memory test seam only)
        // ------------------------------------------------------------------

        private static void CleanupTransientArchitecturalObjects()
        {
            for (int index = TransientArchitecturalObjects.Count - 1; index >= 0; index--)
            {
                if (TransientArchitecturalObjects[index] != null)
                {
                    Object.DestroyImmediate(TransientArchitecturalObjects[index]);
                }
            }
            TransientArchitecturalObjects.Clear();
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
