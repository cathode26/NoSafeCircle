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
        private const string FloorTileName = "ChapelOfAshFloorTile";
        private const string FloorTilePath = ArchitecturalTileFolder + "/" + FloorTileName + ".asset";
        private const string FarWallTileName = "ChapelOfAshFarWallTile";
        private const string CutawayWallTileName = "ChapelOfAshCutawayWallTile";
        private const string WallAccentsRootName = "WallAccents";

        // NSC-109 AC-001/AC-002/AC-004: the committed art this room and the shared full/low wall
        // modules are applied from, instead of the procedurally generated masonry textures this
        // builder used before.
        private const string FloorSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_ChapelOfAsh.png";
        private const string FarWallSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_straight.png";
        private const string CutawayWallSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_broken_stub.png";

        // NSC-046 AC-004: the committed RuinedEntrySceneBuilder inward visual offset every wall
        // Tilemap is inset from its RoomBounds line by, so wall sprites never extend past their
        // gameplay collider face into walkable floor.
        private const float WallVisualOffset = 0.151f;

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

            // Opening the old scene can unload a newly created Tile sub-asset. Resolve all Tiles
            // only after the destination scene is active so the references survive materialization.
            Tile floorTile = LoadOrCreateFloorTile(ArchitecturalTileFolder);
            Tile farWallTile = LoadOrCreateFarWallTile(ArchitecturalTileFolder);
            Tile cutawayWallTile = LoadOrCreateCutawayWallTile(ArchitecturalTileFolder);
            RebuildSceneContents(scene, floorTile, farWallTile, cutawayWallTile);

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.Refresh();

            Debug.Log($"Chapel of Ash scene built at {ScenePath}");
        }

        public static void BuildInMemoryForTests()
        {
            CleanupTransientTiles();
            Tile floorTile = AssetDatabase.LoadAssetAtPath<Tile>(FloorTilePath);
            if (floorTile == null)
            {
                floorTile = CreateTransientTile(FloorTileName, FloorSpriteSourcePath);
            }

            Tile farWallTile = AssetDatabase.LoadAssetAtPath<Tile>(
                ArchitecturalTileFolder + "/" + FarWallTileName + ".asset");
            if (farWallTile == null)
            {
                farWallTile = CreateTransientTile(FarWallTileName, FarWallSpriteSourcePath);
            }

            Tile cutawayWallTile = AssetDatabase.LoadAssetAtPath<Tile>(
                ArchitecturalTileFolder + "/" + CutawayWallTileName + ".asset");
            if (cutawayWallTile == null)
            {
                cutawayWallTile = CreateTransientTile(CutawayWallTileName, CutawayWallSpriteSourcePath);
            }

            RebuildSceneContents(SceneManager.GetActiveScene(), floorTile, farWallTile, cutawayWallTile);
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

        private static void RebuildSceneContents(Scene scene, Tile floorTile, Tile farWallTile, Tile cutawayWallTile)
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

            BuildVisuals(visuals, floorTile, farWallTile, cutawayWallTile);
            BuildWallAccents(visuals);
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
        // committed wall sprites.
        private static void BuildVisuals(Transform visuals, Tile floorTile, Tile farWallTile, Tile cutawayWallTile)
        {
            GameObject gridObject = new GameObject(IsometricGridName, typeof(Grid));
            gridObject.transform.SetParent(visuals, false);
            Grid grid = gridObject.GetComponent<Grid>();
            grid.cellSize = new Vector3(1f, 0.5f, 1f);
            grid.cellSwizzle = GridLayout.CellSwizzle.XYZ;

            Tilemap floor = CreateVisualTilemap(gridObject.transform, "FloorTilemap",
                new Vector3(0f, 0.01f, 0f), Quaternion.Euler(-90f, 0f, 0f),
                DoorPrototypeSceneBuilder.BackgroundGroundSortingOrder);
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

        // NSC-126 AC-001/AC-003/AC-004: places the corner/jamb/end-cap accents NSC-120 delivered,
        // from this room's own committed RoomBounds, floor Y and D2/D3 door openings -- no new
        // door coordinates or bounds are introduced here. Nested under Visuals rather than as a
        // direct child of the room root because RoomSceneComposer.ValidateContentCategories
        // requires every direct room-root child to carry a RoomContentMarker for one of its four
        // categories; the whole room is rebuilt from scratch on every call, so this is idempotent
        // for free.
        private static void BuildWallAccents(Transform visuals)
        {
            Bounds roomBounds = ChapelOfAshLayout.RoomBounds;
            var doorOpenings = new List<WallAccentDoorOpening>
            {
                new WallAccentDoorOpening(WallSide.South, ChapelOfAshLayout.D2.x, ChapelOfAshLayout.DoorWidth),
                new WallAccentDoorOpening(WallSide.North, ChapelOfAshLayout.D3.x, ChapelOfAshLayout.DoorWidth)
            };
            WallAccentRoomGeometry geometry = ArchitecturalWallAccentPlacement.BuildRectangularRoomGeometry(
                roomBounds, roomBounds.center.y, doorOpenings);

            GameObject accentsRoot = new GameObject(WallAccentsRootName);
            accentsRoot.transform.SetParent(visuals, false);
            ArchitecturalWallAccentPlacement.Place(accentsRoot.transform, geometry);
        }

        // AC-003: paints every cell whose center lies inside the wall-collider interior faces.
        // The loop range is intentionally wider than the painted area; GetCellCenterWorld decides
        // membership, so the exact cell indices never need to be hand-derived.
        // NSC-109 wall-floor gap: paint every cell whose FULL FOOTPRINT lies inside the room
        // bounds, which is the convention FinalRoomSceneBuilder and BoneArchiveSceneBuilder
        // already use and the only two rooms with no visible gap. Testing the anchor against
        // the wall-collider INNER faces stopped the floor short of the wall's visual plane,
        // which sits at MaximumX - WallVisualOffset (0.151) rather than at the collider face.
        // The overshoot is hidden: walls render at sortingOrder 0 over the floor's -100.
        public static bool FloorCellIsInsideRoom(Vector3 cellCorner, Vector3 cellSize)
        {
            const float tolerance = 0.001f;
            return cellCorner.x >= ChapelOfAshLayout.MinimumX - tolerance
                && cellCorner.x + cellSize.x <= ChapelOfAshLayout.MaximumX + tolerance
                && cellCorner.z - cellSize.y >= ChapelOfAshLayout.MinimumZ - tolerance
                && cellCorner.z <= ChapelOfAshLayout.MaximumZ + tolerance;
        }

        private static void PaintFloor(Tilemap tilemap, TileBase floorTile)
        {
            for (int x = -20; x <= 20; x++)
            {
                for (int row = -120; row <= -30; row++)
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

        // NSC-109 AC-001/AC-002: this room's own floor Tile, bound to the committed
        // floor_ChapelOfAsh sprite rather than a procedurally generated texture.
        public static Tile LoadOrCreateFloorTile(string assetFolder)
        {
            return LoadOrCreateSpriteTile(assetFolder, FloorTileName, FloorSpriteSourcePath);
        }

        // NSC-109 AC-001/AC-002: generates and reconciles the two Chapel-specific wall Tile
        // assets, now bound to the committed wall_straight and wall_broken_stub sprites instead
        // of procedurally generated masonry textures.
        public static Tile LoadOrCreateFarWallTile(string assetFolder)
        {
            return LoadOrCreateSpriteTile(assetFolder, FarWallTileName, FarWallSpriteSourcePath);
        }

        public static Tile LoadOrCreateCutawayWallTile(string assetFolder)
        {
            return LoadOrCreateSpriteTile(assetFolder, CutawayWallTileName, CutawayWallSpriteSourcePath);
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
                    $"Chapel of Ash requires the committed sprite at '{sourceSpritePath}'.");
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
                    $"Chapel of Ash requires the committed sprite at '{sourceSpritePath}'.");
            }

            Tile tile = ScriptableObject.CreateInstance<Tile>();
            tile.name = tileName;
            tile.colliderType = Tile.ColliderType.None;
            tile.hideFlags = HideFlags.HideAndDontSave;
            tile.sprite = sourceSprite;
            TransientTileObjects.Add(tile);
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
