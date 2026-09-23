using System;
using System.Collections.Generic;
using System.IO;
using NoSafeCircle.DoorPrototype;
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
    /// <summary>Builds the Chapel of Ash authoring scene with separate visual and gameplay layers.</summary>
    public static class ChapelOfAshSceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/Rooms/ChapelOfAsh.unity";

        private const string RoomRootName = "Room_ChapelOfAsh";
        private const string VisualRootName = "Visuals";
        private const string GameplayRootName = "GameplayGeometry";
        private const string AnchorsRootName = "DoorAnchors";
        private const string AuthoringRootName = "Authoring";
        private const string IsometricGridName = "IsometricZAsY";

        private const string ArchitecturalTileFolder =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";
        private const string FloorTilePath = ArchitecturalTileFolder + "/FloorTile.asset";
        private const string FarWallTileName = "ChapelOfAshFarWallTile";
        private const string CutawayWallTileName = "ChapelOfAshCutawayWallTile";
        private const int FarWallTileWidth = 64;
        private const int FarWallTileHeight = 160;
        private const int CutawayWallTileWidth = 64;
        private const int CutawayWallTileHeight = 32;

        // NSC-046 AC-004: the committed RuinedEntrySceneBuilder inward visual offset every wall
        // Tilemap is inset from its RoomBounds line by, so wall sprites never extend past their
        // gameplay collider face into walkable floor.
        private const float WallVisualOffset = 0.151f;

        private const int WallCoursePixelHeight = 32;
        private const int WallBlockPixelWidth = 32;

        private const float RitualFocusReserveHeight = 3.5f;

        private static readonly Color PewTintA = new Color(0.36f, 0.24f, 0.20f, 1f);
        private static readonly Color PewTintB = new Color(0.42f, 0.28f, 0.22f, 1f);
        private static readonly Color ColumnTint = new Color(0.55f, 0.53f, 0.56f, 1f);
        private static readonly Color RitualFocusTint = new Color(0.68f, 0.42f, 0.24f, 1f);

        private const string PreviewWizardSpritePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png";
        private static readonly Vector3 PreviewCameraOffset = new Vector3(10f, 10f, -10f);
        private static readonly Vector3 PreviewCameraEulerAngles = new Vector3(30f, -45f, 0f);
        private const float PreviewOrthographicSize = 8f;

        private static readonly List<Object> TransientTileObjects = new List<Object>();

        [MenuItem("No Safe Circle/Rooms/Build Chapel of Ash Authoring Scene")]
        public static void BuildAndSave()
        {
            EnsureFolder(Path.GetDirectoryName(ScenePath)?.Replace('\\', '/'));
            EnsureFolder(ArchitecturalTileFolder);

            Scene scene = File.Exists(ScenePath)
                ? EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single)
                : EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // Opening the old scene can unload a newly created Tile sub-asset. Resolve both Tiles
            // only after the destination scene is active so the references survive materialization.
            Tile farWallTile = LoadOrCreateFarWallTile(ArchitecturalTileFolder);
            Tile cutawayWallTile = LoadOrCreateCutawayWallTile(ArchitecturalTileFolder);
            RebuildSceneContents(scene, farWallTile, cutawayWallTile);

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.Refresh();

            Debug.Log($"Chapel of Ash scene built at {ScenePath}");
        }

        public static void BuildInMemoryForTests()
        {
            CleanupTransientTiles();
            Tile farWallTile = AssetDatabase.LoadAssetAtPath<Tile>(
                ArchitecturalTileFolder + "/" + FarWallTileName + ".asset");
            if (farWallTile == null)
            {
                farWallTile = CreateTransientFarWallTile();
            }

            Tile cutawayWallTile = AssetDatabase.LoadAssetAtPath<Tile>(
                ArchitecturalTileFolder + "/" + CutawayWallTileName + ".asset");
            if (cutawayWallTile == null)
            {
                cutawayWallTile = CreateTransientCutawayWallTile();
            }

            RebuildSceneContents(SceneManager.GetActiveScene(), farWallTile, cutawayWallTile);
        }

        [MenuItem("No Safe Circle/Rooms/Preview Chapel of Ash Gameplay Camera")]
        public static void PreviewGameplayCamera()
        {
            EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            Scene previewScene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);

            Sprite wizardSprite = AssetDatabase.LoadAssetAtPath<Sprite>(PreviewWizardSpritePath);
            if (wizardSprite == null)
            {
                throw new InvalidOperationException(
                    $"Chapel of Ash gameplay-camera preview requires the wizard Sprite at '{PreviewWizardSpritePath}'.");
            }

            GameObject wizard = new GameObject("PreviewWizard");
            SceneManager.MoveGameObjectToScene(wizard, previewScene);
            wizard.transform.position = ChapelOfAshLayout.GameplayCameraReviewStations[0];

            SpriteRenderer wizardRenderer = wizard.AddComponent<SpriteRenderer>();
            wizardRenderer.sprite = wizardSprite;
            wizardRenderer.sortingLayerName = DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName;
            wizardRenderer.spriteSortPoint = SpriteSortPoint.Pivot;

            GameObject cameraObject = new GameObject("PreviewGameplayCamera");
            SceneManager.MoveGameObjectToScene(cameraObject, previewScene);
            Camera camera = cameraObject.AddComponent<Camera>();
            camera.orthographic = true;
            camera.orthographicSize = PreviewOrthographicSize;
            cameraObject.transform.rotation = Quaternion.Euler(PreviewCameraEulerAngles);
            cameraObject.transform.position = wizard.transform.position + PreviewCameraOffset;

            IsometricCameraFollow follow = cameraObject.AddComponent<IsometricCameraFollow>();
            follow.Initialize(wizard.transform);

            SceneManager.SetActiveScene(previewScene);
        }

        private static void RebuildSceneContents(Scene scene, Tile farWallTile, Tile cutawayWallTile)
        {
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                Object.DestroyImmediate(root);
            }

            GameObject roomRoot = new GameObject(RoomRootName);
            Transform visuals = CreateContentRoot(roomRoot.transform, VisualRootName, RoomContentCategory.Visuals);
            Transform gameplay = CreateContentRoot(roomRoot.transform, GameplayRootName, RoomContentCategory.GameplayGeometry);
            Transform anchors = CreateContentRoot(roomRoot.transform, AnchorsRootName, RoomContentCategory.DoorAnchors);
            Transform authoring = CreateContentRoot(roomRoot.transform, AuthoringRootName, RoomContentCategory.Authoring);

            BuildVisuals(visuals, farWallTile, cutawayWallTile);
            BuildGameplayGeometry(gameplay);

            CreateAnchor(anchors, "D2Anchor", ChapelOfAshLayout.D2, Vector3.back, DoorId.D2, DoorAnchorRole.Entry);
            CreateAnchor(anchors, "D3Anchor", ChapelOfAshLayout.D3, Vector3.forward, DoorId.D3, DoorAnchorRole.Exit);

            CreateMarker(authoring, "CA-W", ChapelOfAshLayout.CoverPocketWest, Vector3.right);
            CreateMarker(authoring, "CA-E", ChapelOfAshLayout.CoverPocketEast, Vector3.left);
            CreateMarker(authoring, "WestRemembranceClusterReserve", ChapelOfAshLayout.WestRemembranceClusterReserveBounds.center);
            CreateMarker(authoring, "EastVestryClusterReserve", ChapelOfAshLayout.EastVestryClusterReserveBounds.center);

            SceneManager.SetActiveScene(scene);
        }

        // NSC-046 AC-003/AC-004: one room-owned Grid with five Tilemaps (Floor, North, South,
        // West, East) painted with the committed RuinedEntrySceneBuilder cell mapping, plus the
        // sprite-blockout pews, columns, and ritual-focus placeholder that reuse the same
        // generated wall Tile sprites.
        private static void BuildVisuals(Transform visuals, Tile farWallTile, Tile cutawayWallTile)
        {
            Tile floorTile = AssetDatabase.LoadAssetAtPath<Tile>(FloorTilePath);
            if (floorTile == null)
            {
                throw new InvalidOperationException("Chapel of Ash requires the existing FloorTile asset.");
            }

            GameObject gridObject = new GameObject(IsometricGridName, typeof(Grid));
            gridObject.transform.SetParent(visuals, false);
            Grid grid = gridObject.GetComponent<Grid>();
            grid.cellSize = new Vector3(1f, 0.5f, 1f);
            grid.cellSwizzle = GridLayout.CellSwizzle.XYZ;

            Tilemap floor = CreateVisualTilemap(gridObject.transform, "FloorTilemap",
                new Vector3(0f, 0.01f, 0f), Quaternion.Euler(-90f, 0f, 0f), -100);
            PaintFloor(floor, floorTile);

            Tilemap north = CreateVisualTilemap(gridObject.transform, "NorthFullWallTilemap",
                new Vector3(0.5f, 0f, ChapelOfAshLayout.MaximumZ - WallVisualOffset), Quaternion.identity, 0);
            PaintStraightWallRun(north, farWallTile, -14, 8);
            PaintStraightWallRun(north, farWallTile, 6, 24);

            Tilemap south = CreateVisualTilemap(gridObject.transform, "SouthLowWallTilemap",
                new Vector3(0.5f, 0f, ChapelOfAshLayout.MinimumZ + WallVisualOffset), Quaternion.identity, 0);
            PaintStraightWallRun(south, cutawayWallTile, -7, 22);
            PaintStraightWallRun(south, cutawayWallTile, 13, 10);

            Tilemap west = CreateVisualTilemap(gridObject.transform, "WestFullWallTilemap",
                new Vector3(ChapelOfAshLayout.MinimumX + WallVisualOffset, 0f, -0.5f), Quaternion.Euler(0f, 90f, 0f), 0);
            PaintStraightWallRun(west, farWallTile, -37, 34);

            Tilemap east = CreateVisualTilemap(gridObject.transform, "EastLowWallTilemap",
                new Vector3(ChapelOfAshLayout.MaximumX - WallVisualOffset, 0f, -0.5f), Quaternion.Euler(0f, 90f, 0f), 0);
            PaintStraightWallRun(east, cutawayWallTile, -37, 34);

            BuildPewVisuals(visuals, cutawayWallTile);
            BuildColumnVisuals(visuals, farWallTile);
            BuildRitualFocusVisual(visuals, farWallTile);
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

        // AC-003: paints every cell whose center lies inside the wall-collider interior faces.
        // The loop range is intentionally wider than the painted area; GetCellCenterWorld decides
        // membership, so the exact cell indices never need to be hand-derived.
        private static void PaintFloor(Tilemap tilemap, TileBase floorTile)
        {
            float innerMinimumX = ChapelOfAshLayout.MinimumX + ChapelOfAshLayout.WallThickness * 0.5f;
            float innerMaximumX = ChapelOfAshLayout.MaximumX - ChapelOfAshLayout.WallThickness * 0.5f;
            float innerMinimumZ = ChapelOfAshLayout.MinimumZ + ChapelOfAshLayout.WallThickness * 0.5f;
            float innerMaximumZ = ChapelOfAshLayout.MaximumZ - ChapelOfAshLayout.WallThickness * 0.5f;

            for (int x = -20; x <= 20; x++)
            {
                for (int row = -120; row <= -30; row++)
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

        // NSC-046 AC-004: behaves exactly like RuinedEntrySceneBuilder.PaintStraightWallRun - the
        // only repeated-cell loop the walls use.
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

        private static void BuildPewVisuals(Transform visuals, Tile cutawayWallTile)
        {
            Sprite pewSprite = cutawayWallTile.sprite;
            for (int index = 0; index < ChapelOfAshLayout.PewFootprints.Length; index++)
            {
                Bounds bounds = ChapelOfAshLayout.PewFootprints[index];
                Color tint = index % 2 == 0 ? PewTintA : PewTintB;
                CreateBlockoutSprite(
                    visuals,
                    "Pew" + (index + 1) + "Visual",
                    pewSprite,
                    new Vector3(bounds.center.x, 0f, bounds.center.z),
                    bounds.size.x,
                    ChapelOfAshLayout.PewHeight,
                    tint);
            }
        }

        private static void BuildColumnVisuals(Transform visuals, Tile farWallTile)
        {
            Sprite columnSprite = farWallTile.sprite;
            for (int index = 0; index < ChapelOfAshLayout.ColumnCenters.Length; index++)
            {
                Vector3 center = ChapelOfAshLayout.ColumnCenters[index];
                CreateBlockoutSprite(
                    visuals,
                    "Column" + (index + 1) + "Visual",
                    columnSprite,
                    new Vector3(center.x, 0f, center.z),
                    ChapelOfAshLayout.ColumnSize,
                    ChapelOfAshLayout.ColumnHeight,
                    ColumnTint);
            }
        }

        // AC-005: a vertical, non-colliding placeholder reserving the north ritual landmark for
        // NSC-081. It reuses the far-wall sprite so no new production prop art is authored here.
        private static void BuildRitualFocusVisual(Transform visuals, Tile farWallTile)
        {
            Bounds reserve = ChapelOfAshLayout.RitualFocusReserveBounds;
            CreateBlockoutSprite(
                visuals,
                "RitualFocusReserveVisual",
                farWallTile.sprite,
                new Vector3(reserve.center.x, 0f, reserve.center.z),
                reserve.size.x,
                RitualFocusReserveHeight,
                RitualFocusTint);
        }

        private static void CreateBlockoutSprite(
            Transform parent, string name, Sprite sprite, Vector3 groundPosition, float footprintWidth, float height, Color tint)
        {
            GameObject spriteObject = new GameObject(name);
            spriteObject.transform.SetParent(parent, false);
            spriteObject.transform.localPosition = groundPosition;

            SpriteRenderer renderer = spriteObject.AddComponent<SpriteRenderer>();
            renderer.sprite = sprite;
            renderer.color = tint;
            renderer.sortingLayerName = DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName;
            renderer.sortingOrder = 0;
            renderer.spriteSortPoint = SpriteSortPoint.Pivot;

            float nativeWidth = sprite.rect.width / sprite.pixelsPerUnit;
            float nativeHeight = sprite.rect.height / sprite.pixelsPerUnit;
            spriteObject.transform.localScale = new Vector3(footprintWidth / nativeWidth, height / nativeHeight, 1f);
        }

        // AC-003: separate 2.5-unit gameplay colliders under GameplayGeometry, split by name
        // around the D2/D3 openings so NSC-049 can find and remove wall pieces by name.
        private static void BuildGameplayGeometry(Transform gameplay)
        {
            CreateGameplayBox(gameplay, "FloorCollision",
                ChapelOfAshLayout.RoomBounds.center + Vector3.down * 0.05f,
                new Vector3(ChapelOfAshLayout.RoomBounds.size.x, 0.1f, ChapelOfAshLayout.RoomBounds.size.z));

            BuildWallColliders(gameplay);
            BuildPewColliders(gameplay);
            BuildColumnColliders(gameplay);
        }

        private static void BuildWallColliders(Transform gameplay)
        {
            float centerY = ChapelOfAshLayout.WallHeight * 0.5f;
            float roomCenterZ = ChapelOfAshLayout.RoomBounds.center.z;
            float roomDepth = ChapelOfAshLayout.MaximumZ - ChapelOfAshLayout.MinimumZ;

            CreateGameplayBox(gameplay, "WestWallCollision",
                new Vector3(ChapelOfAshLayout.MinimumX, centerY, roomCenterZ),
                new Vector3(ChapelOfAshLayout.WallThickness, ChapelOfAshLayout.WallHeight, roomDepth));
            CreateGameplayBox(gameplay, "EastWallCollision",
                new Vector3(ChapelOfAshLayout.MaximumX, centerY, roomCenterZ),
                new Vector3(ChapelOfAshLayout.WallThickness, ChapelOfAshLayout.WallHeight, roomDepth));

            CreateSplitWallColliders(gameplay, "SouthWallWestCollision", "SouthWallEastCollision",
                ChapelOfAshLayout.MinimumZ, centerY, ChapelOfAshLayout.D2.x);
            CreateSplitWallColliders(gameplay, "NorthWallWestCollision", "NorthWallEastCollision",
                ChapelOfAshLayout.MaximumZ, centerY, ChapelOfAshLayout.D3.x);
        }

        private static void CreateSplitWallColliders(
            Transform gameplay, string westName, string eastName, float z, float centerY, float doorCenterX)
        {
            float openingHalfWidth = ChapelOfAshLayout.DoorWidth * 0.5f;
            float westLength = doorCenterX - openingHalfWidth - ChapelOfAshLayout.MinimumX;
            float eastLength = ChapelOfAshLayout.MaximumX - doorCenterX - openingHalfWidth;
            Vector3 westCenter = new Vector3(ChapelOfAshLayout.MinimumX + westLength * 0.5f, centerY, z);
            Vector3 eastCenter = new Vector3(ChapelOfAshLayout.MaximumX - eastLength * 0.5f, centerY, z);
            Vector3 westSize = new Vector3(westLength, ChapelOfAshLayout.WallHeight, ChapelOfAshLayout.WallThickness);
            Vector3 eastSize = new Vector3(eastLength, ChapelOfAshLayout.WallHeight, ChapelOfAshLayout.WallThickness);
            CreateGameplayBox(gameplay, westName, westCenter, westSize);
            CreateGameplayBox(gameplay, eastName, eastCenter, eastSize);
        }

        private static void BuildPewColliders(Transform gameplay)
        {
            for (int index = 0; index < ChapelOfAshLayout.PewFootprints.Length; index++)
            {
                Bounds bounds = ChapelOfAshLayout.PewFootprints[index];
                CreateGameplayBox(gameplay, "Pew" + (index + 1) + "Collision", bounds.center, bounds.size);
            }
        }

        private static void BuildColumnColliders(Transform gameplay)
        {
            for (int index = 0; index < ChapelOfAshLayout.ColumnCenters.Length; index++)
            {
                Bounds bounds = ChapelOfAshLayout.ColumnBounds(ChapelOfAshLayout.ColumnCenters[index]);
                CreateGameplayBox(gameplay, "Column" + (index + 1) + "Collision", bounds.center, bounds.size);
            }
        }

        private static Transform CreateContentRoot(Transform parent, string name, RoomContentCategory category)
        {
            GameObject child = new GameObject(name);
            child.transform.SetParent(parent, false);
            RoomContentMarker marker = child.AddComponent<RoomContentMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.ChapelOfAsh;
            serialized.FindProperty("category").enumValueIndex = (int)category;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            return child.transform;
        }

        private static void CreateAnchor(
            Transform parent, string name, Vector3 position, Vector3 forward, DoorId doorId, DoorAnchorRole role)
        {
            GameObject anchor = new GameObject(name);
            anchor.transform.SetParent(parent, false);
            anchor.transform.position = position;
            anchor.transform.forward = forward;
            DoorAnchorMarker marker = anchor.AddComponent<DoorAnchorMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.ChapelOfAsh;
            serialized.FindProperty("doorId").enumValueIndex = (int)doorId;
            serialized.FindProperty("role").enumValueIndex = (int)role;
            serialized.FindProperty("openingWidth").floatValue = ChapelOfAshLayout.DoorWidth;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static void CreateMarker(Transform parent, string name, Vector3 position, Vector3 forward)
        {
            GameObject marker = new GameObject(name);
            marker.transform.SetParent(parent, false);
            marker.transform.position = position;
            marker.transform.forward = forward;
        }

        private static void CreateMarker(Transform parent, string name, Vector3 position)
        {
            GameObject marker = new GameObject(name);
            marker.transform.SetParent(parent, false);
            marker.transform.position = position;
        }

        private static GameObject CreateGameplayBox(Transform parent, string name, Vector3 position, Vector3 size)
        {
            GameObject box = new GameObject(name);
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            BoxCollider collider = box.AddComponent<BoxCollider>();
            collider.size = size;
            return box;
        }

        // NSC-046 AC-003: generates and reconciles the two Chapel-specific wall Tile assets using
        // the same load/create/replace convention as RuinedEntrySceneBuilder.LoadOrCreateRuinedEntryLowWallTile.
        public static Tile LoadOrCreateFarWallTile(string assetFolder)
        {
            return LoadOrCreateWallTile(assetFolder, FarWallTileName, FarWallTileWidth, FarWallTileHeight, CreateFarWallPixels());
        }

        public static Tile LoadOrCreateCutawayWallTile(string assetFolder)
        {
            return LoadOrCreateWallTile(assetFolder, CutawayWallTileName, CutawayWallTileWidth, CutawayWallTileHeight, CreateCutawayPixels());
        }

        private static Tile LoadOrCreateWallTile(string assetFolder, string tileName, int width, int height, Color32[] pixels)
        {
            if (string.IsNullOrWhiteSpace(assetFolder) || !assetFolder.StartsWith("Assets/", StringComparison.Ordinal))
            {
                throw new ArgumentException("The wall Tile asset folder must be under Assets.", nameof(assetFolder));
            }

            EnsureFolder(assetFolder);
            string assetPath = assetFolder + "/" + tileName + ".asset";
            Tile tile = AssetDatabase.LoadAssetAtPath<Tile>(assetPath);
            if (tile == null)
            {
                tile = ScriptableObject.CreateInstance<Tile>();
                tile.name = tileName;
                tile.colliderType = Tile.ColliderType.None;
                AssetDatabase.CreateAsset(tile, assetPath);
                ReplaceWallVisual(tile, tileName, width, height, pixels);
            }
            else if (!WallVisualMatches(tile, width, height, pixels))
            {
                ReplaceWallVisual(tile, tileName, width, height, pixels);
            }
            else if (tile.colliderType != Tile.ColliderType.None)
            {
                tile.colliderType = Tile.ColliderType.None;
                EditorUtility.SetDirty(tile);
                AssetDatabase.SaveAssetIfDirty(tile);
            }

            return tile;
        }

        private static Tile CreateTransientFarWallTile()
        {
            return CreateTransientWallTile(FarWallTileName, FarWallTileWidth, FarWallTileHeight, CreateFarWallPixels());
        }

        private static Tile CreateTransientCutawayWallTile()
        {
            return CreateTransientWallTile(CutawayWallTileName, CutawayWallTileWidth, CutawayWallTileHeight, CreateCutawayPixels());
        }

        private static Tile CreateTransientWallTile(string tileName, int width, int height, Color32[] pixels)
        {
            Tile tile = ScriptableObject.CreateInstance<Tile>();
            tile.name = tileName;
            tile.colliderType = Tile.ColliderType.None;
            tile.hideFlags = HideFlags.HideAndDontSave;
            Texture2D texture = CreateWallTexture(tileName, width, height, pixels);
            texture.hideFlags = HideFlags.HideAndDontSave;
            Sprite sprite = Sprite.Create(texture, new Rect(0f, 0f, width, height), new Vector2(0.5f, 0f), 64f);
            sprite.name = tileName + "Sprite";
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

        private static bool WallVisualMatches(Tile tile, int width, int height, Color32[] pixels)
        {
            Sprite sprite = tile.sprite;
            if (sprite == null || sprite.texture == null || sprite.texture.width != width || sprite.texture.height != height ||
                !Mathf.Approximately(sprite.pixelsPerUnit, 64f) ||
                Vector2.Distance(sprite.pivot, new Vector2(width * 0.5f, 0f)) > 0.01f)
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

        private static void ReplaceWallVisual(Tile tile, string tileName, int width, int height, Color32[] pixels)
        {
            Sprite previousSprite = tile.sprite;
            Texture2D previousTexture = previousSprite != null ? previousSprite.texture : null;
            tile.sprite = null;
            if (previousSprite != null && AssetDatabase.Contains(previousSprite)) Object.DestroyImmediate(previousSprite, true);
            if (previousTexture != null && AssetDatabase.Contains(previousTexture)) Object.DestroyImmediate(previousTexture, true);

            Texture2D texture = CreateWallTexture(tileName, width, height, pixels);
            AssetDatabase.AddObjectToAsset(texture, tile);
            Sprite sprite = Sprite.Create(texture, new Rect(0f, 0f, width, height), new Vector2(0.5f, 0f), 64f);
            sprite.name = tileName + "Sprite";
            AssetDatabase.AddObjectToAsset(sprite, tile);
            tile.sprite = sprite;
            tile.colliderType = Tile.ColliderType.None;
            EditorUtility.SetDirty(texture);
            EditorUtility.SetDirty(sprite);
            EditorUtility.SetDirty(tile);
            AssetDatabase.SaveAssetIfDirty(tile);
        }

        private static Texture2D CreateWallTexture(string tileName, int width, int height, Color32[] pixels)
        {
            Texture2D texture = new Texture2D(width, height, TextureFormat.RGBA32, false)
            {
                name = tileName + "Texture",
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Repeat
            };
            texture.SetPixels32(pixels);
            texture.Apply(false, false);
            return texture;
        }

        private static Color32[] CreateFarWallPixels()
        {
            return CreateWallPixels(FarWallTileWidth, FarWallTileHeight);
        }

        private static Color32[] CreateCutawayPixels()
        {
            return CreateWallPixels(CutawayWallTileWidth, CutawayWallTileHeight);
        }

        // NSC-046 AC-003/WALL_TILING_IMPLEMENTATION_GUIDE: a horizontally periodic 32-pixel block
        // pattern that divides both 64-pixel-wide Tile textures exactly, so the pattern never
        // truncates or restarts across a painted wall run.
        private static Color32[] CreateWallPixels(int width, int height)
        {
            Color32[] pixels = new Color32[width * height];
            Color32 stone = new Color32(94, 82, 70, 255);
            Color32 alternateStone = new Color32(108, 94, 79, 255);
            Color32 mortar = new Color32(46, 39, 34, 255);

            for (int y = 0; y < height; y++)
            {
                int course = y / WallCoursePixelHeight;
                bool horizontalMortar = y % WallCoursePixelHeight < 2;
                int staggerOffset = (course % 2) * (WallBlockPixelWidth / 2);
                for (int x = 0; x < width; x++)
                {
                    int staggeredX = (x + staggerOffset) % WallBlockPixelWidth;
                    bool verticalMortar = staggeredX < 2;
                    // The shade must NOT depend on the horizontal block index. (x + stagger)
                    // / WallBlockPixelWidth climbs with x instead of wrapping, so adjacent
                    // 32px blocks alternated and the texture repeated every 64px, not 32 --
                    // measured at row 2: x=2 gave stone and x=34 gave alternateStone.
                    // LowerVaultSceneBuilder.CreateNearWallStubPixels, which passes this same
                    // assertion, varies shade by COURSE alone. Match it.
                    pixels[y * width + x] = horizontalMortar || verticalMortar
                        ? mortar
                        : (course % 2 == 0 ? stone : alternateStone);
                }
            }

            return pixels;
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
