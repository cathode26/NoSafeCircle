using System;
using System.Collections.Generic;
using System.IO;
using NoSafeCircle.DoorPrototype.Editor;
using NoSafeCircle.DoorPrototype.Editor.Generation;
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
        private const string WallAccentsRootName = "WallAccents";
        private const string ArchitecturalTileFolder =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";
        private const string FloorTileName = "RuinedEntryFloorTile";
        private const string FloorTilePath = ArchitecturalTileFolder + "/" + FloorTileName + ".asset";
        private const string LowWallTileName = "RuinedEntryLowWallTile";
        private const string LowWallTilePath = ArchitecturalTileFolder + "/" + LowWallTileName + ".asset";
        private const string FullWallTilePath = ArchitecturalTileFolder + "/WallTile.asset";
        private const float WallVisualOffset = 0.151f;
        private static readonly List<Object> TransientTileObjects = new List<Object>();

        // NSC-109 AC-001/AC-004: the committed art the Art Director delivered for this room and
        // for the shared low/broken-wall module. Applied as-authored; no local pixel edits.
        private const string FloorSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_RuinedEntry.png";
        private const string LowWallSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_broken_stub.png";

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
            Tile floorTile = LoadOrCreateRuinedEntryFloorTile(ArchitecturalTileFolder);
            Tile lowWallTile = LoadOrCreateRuinedEntryLowWallTile(ArchitecturalTileFolder);
            RebuildSceneContents(scene, floorTile, lowWallTile);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.Refresh();

            Debug.Log($"Ruined Entry scene built at {ScenePath}");
        }

        public static void BuildInMemoryForTests()
        {
            CleanupTransientTiles();
            Tile floorTile = AssetDatabase.LoadAssetAtPath<Tile>(FloorTilePath);
            if (floorTile == null)
            {
                floorTile = CreateTransientTile(FloorTileName, FloorSpriteSourcePath);
            }

            Tile lowWallTile = AssetDatabase.LoadAssetAtPath<Tile>(LowWallTilePath);
            if (lowWallTile == null)
            {
                lowWallTile = CreateTransientTile(LowWallTileName, LowWallSpriteSourcePath);
            }
            RebuildSceneContents(SceneManager.GetActiveScene(), floorTile, lowWallTile);
        }

        private static void RebuildSceneContents(Scene scene, Tile floorTile, Tile lowWallTile)
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

            BuildVisibleBlockout(visibleRoot, floorTile, lowWallTile);
            BuildWallAccents(visibleRoot);
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

        private static void BuildVisibleBlockout(Transform parent, Tile floorTile, Tile lowWallTile)
        {
            Tile fullWallTile = AssetDatabase.LoadAssetAtPath<Tile>(FullWallTilePath);
            if (fullWallTile == null)
            {
                throw new InvalidOperationException("Ruined Entry requires the existing WallTile asset.");
            }

            GameObject gridObject = new GameObject("IsometricZAsY", typeof(Grid));
            gridObject.transform.SetParent(parent, false);
            Grid grid = gridObject.GetComponent<Grid>();
            grid.cellSize = new Vector3(1f, 0.5f, 1f);
            grid.cellSwizzle = GridLayout.CellSwizzle.XYZ;

            Tilemap floor = CreateVisualTilemap(gridObject.transform, "FloorTilemap",
                new Vector3(0f, 0.01f, 0f), Quaternion.Euler(-90f, 0f, 0f),
                WorldSpriteConvention.BackgroundGroundSortingOrder);
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
                RaisedSize(RuinedEntryLayout.RubbleABounds, RuinedEntryLayout.RubbleHeight),
                RubblePlaceholderColor);
            CreateVisualBox(parent, "RubbleBVisual", RaisedCenter(RuinedEntryLayout.RubbleBBounds,
                    RuinedEntryLayout.RubbleHeight),
                RaisedSize(RuinedEntryLayout.RubbleBBounds, RuinedEntryLayout.RubbleHeight),
                RubblePlaceholderColor);
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
            renderer.sortingLayerName = WorldSpriteConvention.SortingLayerName;
            renderer.sortingOrder = sortingOrder;
            return tilemap;
        }

        // NSC-126 AC-001/AC-003/AC-004: places the corner/jamb/end-cap accents NSC-120 delivered,
        // from this room's own committed RoomBounds, floor Y and D1 door opening -- no new door
        // coordinates or bounds are introduced here. Nested under Visuals rather than as a direct
        // child of the room root because RoomSceneComposer.ValidateContentCategories requires
        // every direct room-root child to carry a RoomContentMarker for one of its four
        // categories; the whole room is rebuilt from scratch on every call, so this is idempotent
        // for free.
        private static void BuildWallAccents(Transform visuals)
        {
            Bounds roomBounds = RuinedEntryLayout.RoomBounds;
            var doorOpenings = new List<WallAccentDoorOpening>
            {
                new WallAccentDoorOpening(
                    WallSide.North, RuinedEntryLayout.DoorCenterX, RuinedEntryLayout.DoorOpeningWidth)
            };
            WallAccentRoomGeometry geometry = ArchitecturalWallAccentPlacement.BuildRectangularRoomGeometry(
                roomBounds, roomBounds.center.y, doorOpenings);

            GameObject accentsRoot = new GameObject(WallAccentsRootName);
            accentsRoot.transform.SetParent(visuals, false);
            ArchitecturalWallAccentPlacement.Place(accentsRoot.transform, geometry);
        }

        // NSC-109 wall-floor gap: paint every cell whose FULL FOOTPRINT lies inside the room
        // bounds, which is the convention FinalRoomSceneBuilder and BoneArchiveSceneBuilder
        // already use and the only two rooms with no visible gap. Testing the anchor against
        // the wall-collider INNER faces stopped the floor short of the wall's visual plane,
        // which sits at MaximumX - WallVisualOffset (0.151) rather than at the collider face.
        // The overshoot is hidden: walls render at sortingOrder 0 over the floor's -100.
        public static bool FloorCellIsInsideRoom(Vector3 cellCorner, Vector3 cellSize)
        {
            const float tolerance = 0.001f;
            return cellCorner.x >= RuinedEntryLayout.MinimumX - tolerance
                && cellCorner.x + cellSize.x <= RuinedEntryLayout.MaximumX + tolerance
                && cellCorner.z - cellSize.y >= RuinedEntryLayout.MinimumZ - tolerance
                && cellCorner.z <= RuinedEntryLayout.MaximumZ + tolerance;
        }

        private static void PaintFloor(Tilemap tilemap, TileBase floorTile)
        {
            for (int x = -16; x <= 15; x++)
            {
                for (int row = -3; row <= 54; row++)
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

        // NSC-109 AC-001/AC-002: this room's own floor Tile, bound to the committed
        // floor_RuinedEntry sprite rather than a procedurally generated diamond texture.
        // Generation logic moved to Editor/Generation/ArchitecturalTileGenerator.cs
        // (ArchitecturalTileGenerator.RuinedEntry.LoadOrCreateSpriteTile); this stays as the
        // public entry point tests and Build() call.
        public static Tile LoadOrCreateRuinedEntryFloorTile(string assetFolder)
        {
            return ArchitecturalTileGenerator.RuinedEntry.LoadOrCreateSpriteTile(
                assetFolder, FloorTileName, FloorSpriteSourcePath);
        }

        // NSC-109 AC-001/AC-002: bound to the committed wall_broken_stub sprite rather than a
        // procedurally generated masonry-course texture. Generation logic moved to
        // Editor/Generation/ArchitecturalTileGenerator.cs.
        public static Tile LoadOrCreateRuinedEntryLowWallTile(string assetFolder)
        {
            return ArchitecturalTileGenerator.RuinedEntry.LoadOrCreateSpriteTile(
                assetFolder, LowWallTileName, LowWallSpriteSourcePath);
        }

        // internal (was private): ArchitecturalTileGenerator.RuinedEntry.LoadOrCreateSpriteTile
        // calls this from Editor/Generation/ArchitecturalTileGenerator.cs. No behaviour change.
        internal static void EnsureFolder(string folder)
        {
            if (string.IsNullOrWhiteSpace(folder) || AssetDatabase.IsValidFolder(folder))
            {
                return;
            }

            Directory.CreateDirectory(folder);
            AssetDatabase.Refresh();
        }

        private static Tile CreateTransientTile(string tileName, string sourceSpritePath)
        {
            Sprite sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourceSpritePath);
            if (sourceSprite == null)
            {
                throw new InvalidOperationException(
                    $"Ruined Entry requires the committed sprite at '{sourceSpritePath}'.");
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

        /// <summary>The Art Director's tint for the two rubble blockers.</summary>
        /// <remarks>
        /// NOT A CHOICE MADE HERE. Recorded by the Art Director in
        /// C:/nscrev/reports/handoffs/ART-20260924-composed-world-review.md: inside the stone
        /// value range the room already uses, slightly warmer than the wall so the blocker
        /// separates from the backdrop, and semi-transparent so it still reads as a PLACEHOLDER.
        /// <para>
        /// THIS IS A STOPGAP AND IS MEANT TO BE DELETED, not kept. The real fix is the rubble
        /// props NSC-079's dressing places in these two footprints. They are in the composed
        /// scene already and they do NOT hide the blockers -- the props sit on top of the white
        /// slabs -- which is why the tint is still worth having. When the blockers stop being
        /// drawn at all, this colour and CreateMaterial go with them.
        /// </para>
        /// </remarks>
        // The approved blockout tone now lives in one place; see RoomPlaceholderVisuals.
        private static readonly Color32 RubblePlaceholderColor =
            RoomPlaceholderVisuals.BlockoutPlaceholder;

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

        private static void CreateVisualBox(
            Transform parent, string name, Vector3 position, Vector3 size, Color32 color)
        {
            GameObject box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            box.transform.localScale = size;
            Object.DestroyImmediate(box.GetComponent<Collider>());

            // A primitive keeps Unity's DEFAULT material, which is bright white. Every other
            // room assigns one; Ruined Entry was simply left out, so its two blockers rendered
            // as white slabs in the middle of a grey stone room -- the most visible defect in
            // the composed world. THE COLOUR IS A REQUIRED ARGUMENT rather than a default: a
            // future visual box must choose one instead of silently inheriting white again.
            box.GetComponent<Renderer>().sharedMaterial = CreateMaterial(color);
        }

        /// <summary>A Standard material that actually honours the alpha it is given.</summary>
        /// <remarks>
        /// SETTING <c>material.color</c> ALONE IS NOT ENOUGH AND FAILS SILENTLY. The Standard
        /// shader ignores alpha while its rendering mode is Opaque, so a colour carrying alpha
        /// 230 renders fully opaque while the code still reads as though the transparency had
        /// been applied. The blocker is meant to read as a PLACEHOLDER rather than as finished
        /// art, which is the whole point of the alpha, so fade mode is configured explicitly
        /// instead of assumed.
        /// </remarks>
        // Delegates rather than repeating the fade setup: a second copy of this is exactly
        // how the Final Room ended up with a CreateMaterial that drops alpha silently.
        private static Material CreateMaterial(Color32 color)
        {
            return RoomPlaceholderVisuals.CreateStandardMaterial(color);
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
    }
}
