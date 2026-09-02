using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.UI;
using UnityEngine.SceneManagement;
using UnityEngine.Tilemaps;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor
{
    public static class DoorPrototypeSceneBuilder
    {
        private const string SceneFolder = "Assets/Scenes";
        private const string ScenePath = SceneFolder + "/DoorPrototype.unity";
        private const string InputActionsAssetPath = "Assets/InputSystem_Actions.inputactions";
        private const string ArchitecturalTileAssetFolder =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";

        private const string IsometricVisualGridName = "IsometricVisualGrid";
        private const string FloorTilemapName = "FloorTilemap";
        private const string WallTilemapName = "WallTilemap";
        private const string ArchitecturalTilemapName = "ArchitecturalTilemap";

        private static readonly Vector3 IsometricCellSize = new Vector3(1f, 0.5f, 1f);
        private static readonly Quaternion FloorTilemapRotation = Quaternion.Euler(-90f, 0f, 0f);

        private const float FloorVisualOffset = 0.01f;
        private const float WallVisualOffset = -0.151f;

        // NSC-039 AC-001/VAL-001: isometric sorting convention shared by the Tilemap visual
        // layer and every world-space SpriteRenderer object. There are two distinct bands:
        //
        // 1. Background band (large fixed negative sortingOrder, forced behind everything).
        //    Floor and the flat decorative architectural border tile lie flush on the ground
        //    plane; nothing standing on top of them should ever be able to render behind them,
        //    so they are intentionally excluded from positional depth sorting.
        // 2. Interactive/occluding band (one shared sortingLayer + sortingOrder). Walls are
        //    vertical geometry that can genuinely occlude, or be occluded by, a world sprite
        //    depending on isometric position (e.g. the wizard walking behind vs. in front of a
        //    wall segment), so walls share this exact band with the wizard, doors, and later
        //    enemies/props/obstacles instead of being forced behind by sortingOrder. Relative
        //    depth within this band is resolved purely by the camera's orthographic
        //    transparency sort (configured in BuildCamera), which orders same-band renderers by
        //    world position along the camera's fixed view direction.
        //
        // Every world sprite is additionally anchored at a consistent ground-contact (feet)
        // origin - see EnsureWorldSpritePrefab/CreateWorldSpriteVisual below - so sprite height
        // or center elevation never arbitrarily shifts an object's isometric depth.
        private const string WorldSpriteSortingLayerName = "Default";
        private const int WorldSpriteSortingOrder = 0;
        private const int BackgroundGroundSortingOrder = -100;
        private const int BackgroundArchitecturalBorderSortingOrder = -90;

        // Unity Isometric Z-as-Y Individual Tilemap sorting axis. X intentionally
        // contributes no depth so moving along a horizontal wall cannot flip occlusion.
        private static readonly Vector3 IsometricTransparencySortAxis = new Vector3(0f, 1f, -0.26f);

        private const int WorldSpriteTextureSize = 128;
        private const int WorldSpriteBorderThicknessPx = 6;

        // Subfolder name only, not an absolute path: the shared world-sprite Prefab asset is
        // always saved under whichever AssetDatabase folder the caller owns (the real
        // ArchitecturalTileAssetFolder for Build(), or a caller-owned temporary folder for
        // tests), mirroring the existing caller-owned-folder pattern already used for
        // architectural Tile/Sprite/Texture assets below. This guarantees the persistence-aware
        // test seam never writes to the exact same AssetDatabase path Build() uses.
        private const string WorldSpritePrefabAssetFolderName = "WorldSprites";
        private const string WorldSpritePrefabAssetName = "WorldSpriteVisual.prefab";

        // Placeholder colors only (GDD: placeholder character/prop sprites are acceptable).
        private static readonly Color32 WizardSpriteFillColor = new Color32(88, 64, 145, 255);
        private static readonly Color32 WizardSpriteBorderColor = new Color32(40, 28, 66, 255);
        private static readonly Color32 DoorSpriteFillColor = new Color32(90, 62, 38, 255);
        private static readonly Color32 DoorSpriteBorderColor = new Color32(46, 30, 16, 255);

        // This list is the ownership boundary for non-persistent architectural objects made by
        // the parameterless test seam. Persistent AssetDatabase objects are never added here.
        private static readonly List<Object> OwnedTransientArchitecturalObjects = new List<Object>();
        private static Scene ownedTransientArchitecturalScene;

        // Classic 2:1 dimetric isometric camera angle (rotate -45 degrees around Y to face
        // a corner, then tilt 30 degrees down) matching Diablo 1 / Ultima Online-style
        // fixed isometric presentation.
        private static readonly Vector3 IsometricCameraEulerAngles = new Vector3(30f, -45f, 0f);

        // Fixed, hand-picked world-space offset from the follow target to the camera. This is
        // a plain constant - NOT derived by rotating a local vector through the camera's own
        // rotation - so the camera's framing is decoupled from its orientation. Paired with
        // IsometricCameraEulerAngles above, it keeps the player and the starting door in view
        // from the intended side rather than merely pointing camera.forward at the player.
        private static readonly Vector3 IsometricCameraOffset = new Vector3(10f, 10f, -10f);

        private const float IsometricOrthographicSize = 8f;

        private static readonly string[] KnownRootNames =
        {
            "Directional Light",
            "Main Camera",
            IsometricVisualGridName,
            "Floor",
            "Walls",
            "DoorRoot",
            "Player",
            "Canvas",
            "EventSystem"
        };

        static DoorPrototypeSceneBuilder()
        {
            EditorSceneManager.sceneClosing += OnSceneClosing;
            AssemblyReloadEvents.beforeAssemblyReload += CleanupTransientArchitecturalObjects;
            EditorApplication.quitting += CleanupTransientArchitecturalObjects;
        }

        [MenuItem("No Safe Circle/Build Door Prototype Scene")]
        public static void Build()
        {
            EnsureFolder(SceneFolder);
            EnsureFolder(ArchitecturalTileAssetFolder);

            var scene = File.Exists(ScenePath)
                ? EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single)
                : EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            RebuildSceneContents(scene, ArchitecturalTileAssetFolder);

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.Refresh();

            Debug.Log($"Door Prototype scene built at {ScenePath}");
        }

        // Legacy non-persistent test seam retained for existing component tests. Architectural
        // objects created through this overload are explicitly owned and destroyed by this builder.
        public static void BuildInMemoryForTests()
        {
            RebuildSceneContents(SceneManager.GetActiveScene(), null);
        }

        // Narrow persistence-aware test seam. The caller owns the supplied temporary
        // AssetDatabase folder and its cleanup. This does not open or save the canonical scene.
        public static void BuildInMemoryForTests(string temporaryArchitecturalTileAssetFolder)
        {
            ValidateArchitecturalTileAssetFolder(temporaryArchitecturalTileAssetFolder);
            EnsureFolder(temporaryArchitecturalTileAssetFolder);
            RebuildSceneContents(SceneManager.GetActiveScene(), temporaryArchitecturalTileAssetFolder);
        }

        private static void RebuildSceneContents(Scene scene, string architecturalTileAssetFolder)
        {
            CleanupTransientArchitecturalObjects();
            ClearExistingObjects(scene);

            BuildLighting();
            BuildFloor();

            var doorRoot = BuildDoor(out var door, architecturalTileAssetFolder);
            BuildWalls(doorRoot.transform.position);
            if (string.IsNullOrEmpty(architecturalTileAssetFolder))
            {
                ownedTransientArchitecturalScene = scene;
            }
            BuildIsometricVisualLayer(doorRoot.transform.position, architecturalTileAssetFolder);

            BuildPlayer(out var movement, out var interactionController, out var health, out var debugControl,
                out var mana, out var debugManaControl, architecturalTileAssetFolder);
            SetPrivateField(movement, "interactionController", interactionController);

            var doorFeedback = door.GetComponent<DoorInteractionFeedback>();
            SetPrivateField(doorFeedback, "playerMovement", movement);
            SetPrivateField(doorFeedback, "interactionController", interactionController);

            var inputActions = AssetDatabase.LoadAssetAtPath<InputActionAsset>(InputActionsAssetPath);
            if (inputActions == null)
            {
                Debug.LogWarning($"DoorPrototypeSceneBuilder could not load an InputActionAsset at " +
                    $"'{InputActionsAssetPath}'; PlayerMovement will have no input actions asset assigned.");
            }
            SetPrivateField(movement, "inputActions", inputActions);

            // BuildCamera reads followTarget.position immediately (not as a live reference)
            // to place the camera at its initial isometric framing, so BuildPlayer must run
            // first. If this ordering is ever changed, BuildCamera's null-target warning below
            // will fire rather than silently producing an unframed camera at the world origin.
            BuildCamera(movement.transform);

            BuildUI(door, debugControl, health, mana, debugManaControl);
        }

        private static void ValidateArchitecturalTileAssetFolder(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                throw new System.ArgumentException(
                    "A caller-owned temporary AssetDatabase folder is required.", nameof(path));
            }

            if (path == "Assets" || !path.StartsWith("Assets/", System.StringComparison.Ordinal) ||
                path.Contains("..") || path.Contains("\\"))
            {
                throw new System.ArgumentException(
                    "The temporary architectural Tile asset folder must be a normalized child path under Assets.",
                    nameof(path));
            }
        }

        private static void OnSceneClosing(Scene scene, bool removingScene)
        {
            if (OwnedTransientArchitecturalObjects.Count > 0 && scene == ownedTransientArchitecturalScene)
            {
                CleanupTransientArchitecturalObjects();
            }
        }

        private static void CleanupTransientArchitecturalObjects()
        {
            for (var i = OwnedTransientArchitecturalObjects.Count - 1; i >= 0; i--)
            {
                var transientObject = OwnedTransientArchitecturalObjects[i];
                if (transientObject != null && !AssetDatabase.Contains(transientObject))
                {
                    Object.DestroyImmediate(transientObject);
                }
            }

            OwnedTransientArchitecturalObjects.Clear();
            ownedTransientArchitecturalScene = default(Scene);
        }

        private static T OwnTransientArchitecturalObject<T>(T transientObject) where T : Object
        {
            OwnedTransientArchitecturalObjects.Add(transientObject);
            return transientObject;
        }

        private static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;

            var parts = path.Split('/');
            var current = parts[0];
            for (var i = 1; i < parts.Length; i++)
            {
                var next = current + "/" + parts[i];
                if (!AssetDatabase.IsValidFolder(next))
                {
                    AssetDatabase.CreateFolder(current, parts[i]);
                }
                current = next;
            }
        }

        private static void ClearExistingObjects(Scene scene)
        {
            foreach (var root in scene.GetRootGameObjects())
            {
                if (System.Array.IndexOf(KnownRootNames, root.name) >= 0)
                {
                    Object.DestroyImmediate(root);
                }
            }
        }

        private static void BuildLighting()
        {
            var light = new GameObject("Directional Light");
            var lightComponent = light.AddComponent<Light>();
            lightComponent.type = LightType.Directional;
            lightComponent.intensity = 1f;
            light.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
        }

        // Fixed 2.5D isometric presentation per the GDD (Diablo 1 / Ultima Online-style):
        // orthographic projection, no free rotation, at the classic 30/45 dimetric angle
        // used by Unity's isometric ("Z as Y") authoring conventions. The camera's position
        // is the follow target plus a fixed, hand-picked world-space offset - it is
        // deliberately NOT computed by rotating a local vector through the camera's own
        // rotation, since that couples the position to the rotation and produces a camera
        // whose forward axis always points exactly at the target regardless of whether that
        // actually frames the gameplay space well. An IsometricCameraFollow component then
        // translates the camera by that same fixed offset every frame while its rotation is
        // never touched again, so the fixed isometric orientation is preserved and the
        // gameplay area (including the starting door) stays in view as the player moves.
        private static void BuildCamera(Transform followTarget)
        {
            var cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            var camera = cameraObject.AddComponent<Camera>();
            cameraObject.AddComponent<AudioListener>();

            camera.orthographic = true;
            camera.orthographicSize = IsometricOrthographicSize;

            // NSC-039 AC-001: makes the established isometric sorting convention an explicit,
            // intentional part of the fixed camera setup rather than an unstated implicit
            // default. With an orthographic camera this already sorts transparent renderers
            // that share a sortingLayer/sortingOrder (world-space SpriteRenderer prefabs and
            // the Isometric Tilemap layers) by distance along the camera's fixed view
            // direction, so world sprites at different isometric positions order correctly
            // relative to one another without any per-object runtime sorting script.
            camera.transparencySortMode = TransparencySortMode.CustomAxis;
            camera.transparencySortAxis = IsometricTransparencySortAxis;

            cameraObject.transform.rotation = Quaternion.Euler(IsometricCameraEulerAngles);

            if (followTarget == null)
            {
                Debug.LogWarning("DoorPrototypeSceneBuilder.BuildCamera called with a null follow target; " +
                    "the camera will be placed at the world origin plus its isometric offset instead of " +
                    "framing the player, which will fail the fixed isometric framing requirement.");
            }

            var targetPosition = followTarget != null ? followTarget.position : Vector3.zero;
            cameraObject.transform.position = targetPosition + IsometricCameraOffset;

            var follow = cameraObject.AddComponent<IsometricCameraFollow>();
            follow.Initialize(followTarget);
        }

        private static void BuildFloor()
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
            floor.name = "Floor";
            floor.transform.position = Vector3.zero;
            floor.transform.localScale = new Vector3(2f, 1f, 2f);
            // Gameplay collision remains on this Plane, but the Tilemap owns floor visuals.
            // Leaving both renderers visible causes coplanar depth flicker / z-fighting.
            floor.GetComponent<MeshRenderer>().enabled = false;
        }

        private static void BuildIsometricVisualLayer(Vector3 doorPosition, string architecturalTileAssetFolder)
        {
            var tiles = CreateArchitecturalTileSet(architecturalTileAssetFolder);

            var gridObject = new GameObject(IsometricVisualGridName);
            var grid = gridObject.AddComponent<Grid>();
            grid.cellLayout = GridLayout.CellLayout.IsometricZAsY;
            grid.cellSize = IsometricCellSize;
            grid.cellSwizzle = GridLayout.CellSwizzle.XYZ;

            var floorTilemap = CreateVisualOnlyTilemap(
                gridObject.transform,
                FloorTilemapName,
                new Vector3(0f, FloorVisualOffset, 0f),
                FloorTilemapRotation,
                BackgroundGroundSortingOrder);
            PaintFloorTiles(floorTilemap, tiles.Floor);

            // Walls are vertical, interleavable occluding geometry: they share the same
            // sortingLayer/sortingOrder band as world-space SpriteRenderer objects (see the
            // sorting-convention comment above) so the camera's custom-axis transparency sort
            // - not a fixed sortingOrder - decides whether a wall renders in front of or behind
            // the wizard, a door, or another world sprite at a given isometric position.
            var wallTilemap = CreateVisualOnlyTilemap(
                gridObject.transform,
                WallTilemapName,
                doorPosition + new Vector3(-2.5f, 0f, WallVisualOffset),
                Quaternion.identity,
                WorldSpriteSortingOrder);
            // NSC-042 AC-001/AC-002/AC-003: each gameplay wall is painted as a run of one-cell
            // visual segments through the shared PaintWallRun helper below. Individual Tilemap
            // sorting still gets multiple ground-contact sort positions along the wall
            // (NSC-039), and every segment reuses the same tiles.Wall asset - the two
            // three-cell runs here and a future much longer wall both scale without authoring
            // additional Sprite/Tile assets. CreateWallPixels' brick pattern repeats on a
            // period that evenly divides the tile texture's width, so adjacent segments join
            // without a visible seam or pattern restart.
            PaintWallRun(wallTilemap, new Vector3Int(-1, 1, 0), 3, tiles.Wall);
            PaintWallRun(wallTilemap, new Vector3Int(4, -4, 0), 3, tiles.Wall);

            var architecturalTilemap = CreateVisualOnlyTilemap(
                gridObject.transform,
                ArchitecturalTilemapName,
                new Vector3(0f, FloorVisualOffset * 2f, 0f),
                FloorTilemapRotation,
                BackgroundArchitecturalBorderSortingOrder);
            PaintArchitecturalBorder(architecturalTilemap, tiles.Architectural);
        }

        private static Tilemap CreateVisualOnlyTilemap(
            Transform parent,
            string name,
            Vector3 worldPosition,
            Quaternion worldRotation,
            int sortingOrder)
        {
            var tilemapObject = new GameObject(name);
            tilemapObject.transform.SetParent(parent, false);
            tilemapObject.transform.SetPositionAndRotation(worldPosition, worldRotation);

            var tilemap = tilemapObject.AddComponent<Tilemap>();
            tilemap.tileAnchor = Vector3.zero;
            tilemap.orientation = Tilemap.Orientation.XY;

            var renderer = tilemapObject.AddComponent<TilemapRenderer>();
            renderer.mode = TilemapRenderer.Mode.Individual;
            renderer.sortOrder = TilemapRenderer.SortOrder.TopRight;
            // Explicitly shares the same named sorting layer as world-space SpriteRenderer
            // objects (rather than relying on both defaulting to "Default") so the
            // background/interactive sortingOrder bands above compare correctly regardless of
            // the project's configured sorting layers.
            renderer.sortingLayerName = WorldSpriteSortingLayerName;
            renderer.sortingOrder = sortingOrder;

            return tilemap;
        }

        // NSC-042 AC-001/AC-002/AC-003: reusable convention for painting a straight run of
        // one-cell wall visual segments. Every cell reuses the same wallTile asset instead of
        // authoring a unique Sprite/Tile per cell, so a run scales from a few cells to
        // approximately one hundred without asset-count growth, while each cell remains an
        // independently sortable Individual Tilemap tile per NSC-039's positional sorting
        // convention. Cells step diagonally (+1 X, -1 Y per segment) to trace a straight
        // world-space wall under this Grid's IsometricZAsY cell swizzle.
        private static void PaintWallRun(Tilemap wallTilemap, Vector3Int startCell, int cellCount, TileBase wallTile)
        {
            for (var i = 0; i < cellCount; i++)
            {
                wallTilemap.SetTile(new Vector3Int(startCell.x + i, startCell.y - i, 0), wallTile);
            }
        }

        private static void PaintFloorTiles(Tilemap tilemap, TileBase floorTile)
        {
            for (var x = -30; x <= 30; x++)
            {
                for (var y = -30; y <= 30; y++)
                {
                    var cell = new Vector3Int(x, y, 0);
                    var center = tilemap.GetCellCenterLocal(cell);
                    if (Mathf.Abs(center.x) <= 9.75f && Mathf.Abs(center.y) <= 9.75f)
                    {
                        tilemap.SetTile(cell, floorTile);
                    }
                }
            }
        }

        private static void PaintArchitecturalBorder(Tilemap tilemap, TileBase architecturalTile)
        {
            for (var x = -30; x <= 30; x++)
            {
                for (var y = -30; y <= 30; y++)
                {
                    var cell = new Vector3Int(x, y, 0);
                    var center = tilemap.GetCellCenterLocal(cell);
                    var onHorizontalEdge = Mathf.Abs(center.x) <= 9.75f &&
                                           Mathf.Abs(Mathf.Abs(center.y) - 9.75f) <= 0.26f;
                    var onVerticalEdge = Mathf.Abs(center.y) <= 9.75f &&
                                         Mathf.Abs(Mathf.Abs(center.x) - 9.75f) <= 0.26f;
                    if (onHorizontalEdge || onVerticalEdge)
                    {
                        tilemap.SetTile(cell, architecturalTile);
                    }
                }
            }
        }

        private static ArchitecturalTileSet CreateArchitecturalTileSet(string assetFolder)
        {
            return new ArchitecturalTileSet(
                LoadOrCreateArchitecturalTile(
                    assetFolder,
                    "FloorTile.asset",
                    "FloorTile",
                    64,
                    32,
                    64f,
                    CreateDiamondPixels(
                        64,
                        32,
                        new Color32(80, 76, 70, 255),
                        new Color32(49, 46, 43, 255))),
                LoadOrCreateArchitecturalTile(
                    assetFolder,
                    "WallTile.asset",
                    "WallTile",
                    64,
                    160,
                    64f,
                    new Vector2(0.5f, 0f),
                    CreateWallPixels(64, 160)),
                LoadOrCreateArchitecturalTile(
                    assetFolder,
                    "ArchitecturalBorderTile.asset",
                    "ArchitecturalBorderTile",
                    64,
                    32,
                    64f,
                    CreateDiamondPixels(
                        64,
                        32,
                        new Color32(121, 105, 72, 255),
                        new Color32(65, 56, 40, 255))));
        }
        private static Tile LoadOrCreateArchitecturalTile(
            string assetFolder,
            string assetFileName,
            string tileName,
            int textureWidth,
            int textureHeight,
            float pixelsPerUnit,
            Color32[] pixels)
        {
            return LoadOrCreateArchitecturalTile(
                assetFolder,
                assetFileName,
                tileName,
                textureWidth,
                textureHeight,
                pixelsPerUnit,
                new Vector2(0.5f, 0.5f),
                pixels);
        }

        private static Tile LoadOrCreateArchitecturalTile(
            string assetFolder,
            string assetFileName,
            string tileName,
            int textureWidth,
            int textureHeight,
            float pixelsPerUnit,
            Vector2 spritePivot,
            Color32[] pixels)
        {
            if (!string.IsNullOrEmpty(assetFolder))
            {
                var assetPath = assetFolder + "/" + assetFileName;
                var existing = AssetDatabase.LoadAssetAtPath<Tile>(assetPath);

                if (existing != null)
                {
                    existing.colliderType = Tile.ColliderType.None;

                    if (!ArchitecturalTileVisualMatches(
                            existing,
                            textureWidth,
                            textureHeight,
                            pixelsPerUnit,
                            spritePivot,
                            pixels))
                    {
                        ReplaceArchitecturalTileVisual(
                            existing,
                            tileName,
                            textureWidth,
                            textureHeight,
                            pixelsPerUnit,
                            spritePivot,
                            pixels);
                    }

                    EditorUtility.SetDirty(existing);
                    AssetDatabase.SaveAssetIfDirty(existing);
                    return existing;
                }

                var persistentTile = ScriptableObject.CreateInstance<Tile>();
                persistentTile.name = tileName;
                persistentTile.colliderType = Tile.ColliderType.None;

                AssetDatabase.CreateAsset(
                    persistentTile,
                    assetPath);

                var persistentTexture = CreateTileTexture(
                    tileName + "Texture",
                    textureWidth,
                    textureHeight,
                    pixels);

                AssetDatabase.AddObjectToAsset(
                    persistentTexture,
                    persistentTile);

                var persistentSprite = Sprite.Create(
                    persistentTexture,
                    new Rect(0f, 0f, textureWidth, textureHeight),
                    spritePivot,
                    pixelsPerUnit);

                persistentSprite.name = tileName + "Sprite";

                AssetDatabase.AddObjectToAsset(
                    persistentSprite,
                    persistentTile);

                persistentTile.sprite = persistentSprite;

                EditorUtility.SetDirty(persistentTexture);
                EditorUtility.SetDirty(persistentSprite);
                EditorUtility.SetDirty(persistentTile);

                AssetDatabase.SaveAssetIfDirty(persistentTile);

                return persistentTile;
            }

            var inMemoryTile =
                OwnTransientArchitecturalObject(
                    ScriptableObject.CreateInstance<Tile>());

            inMemoryTile.name = tileName;
            inMemoryTile.colliderType = Tile.ColliderType.None;
            inMemoryTile.hideFlags = HideFlags.HideAndDontSave;

            var inMemoryTexture =
                OwnTransientArchitecturalObject(
                    CreateTileTexture(
                        tileName + "Texture",
                        textureWidth,
                        textureHeight,
                        pixels));

            inMemoryTexture.hideFlags = HideFlags.HideAndDontSave;

            var inMemorySprite =
                OwnTransientArchitecturalObject(
                    Sprite.Create(
                        inMemoryTexture,
                        new Rect(0f, 0f, textureWidth, textureHeight),
                        spritePivot,
                        pixelsPerUnit));

            inMemorySprite.name = tileName + "Sprite";
            inMemorySprite.hideFlags = HideFlags.HideAndDontSave;

            inMemoryTile.sprite = inMemorySprite;

            return inMemoryTile;
        }

        private static bool ArchitecturalTileVisualMatches(
            Tile tile,
            int textureWidth,
            int textureHeight,
            float pixelsPerUnit,
            Vector2 spritePivot,
            Color32[] expectedPixels)
        {
            var sprite = tile.sprite;

            if (sprite == null || sprite.texture == null)
            {
                return false;
            }

            var expectedPivotPixels = new Vector2(
                textureWidth * spritePivot.x,
                textureHeight * spritePivot.y);

            var structuralMatch =
                sprite.texture.width == textureWidth &&
                sprite.texture.height == textureHeight &&
                Mathf.Approximately(sprite.rect.width, textureWidth) &&
                Mathf.Approximately(sprite.rect.height, textureHeight) &&
                Mathf.Approximately(sprite.pixelsPerUnit, pixelsPerUnit) &&
                Vector2.Distance(
                    sprite.pivot,
                    expectedPivotPixels) < 0.01f;

            if (!structuralMatch)
            {
                return false;
            }

            // NSC-042: two tiles can share dimensions/pivot but carry stale pixel content once
            // procedural art (e.g. CreateWallPixels) is revised - such as fixing a brick repeat
            // that did not tile seamlessly. Comparing actual pixel content, not just structural
            // metadata, is what lets re-running Build() reconcile stale visual output instead of
            // silently leaving outdated art on disk (ENGINEERING_STANDARDS.md 12: avoid stale
            // editor-tool output).
            var actualPixels = sprite.texture.GetPixels32();
            if (actualPixels.Length != expectedPixels.Length)
            {
                return false;
            }

            for (var i = 0; i < actualPixels.Length; i++)
            {
                if (!actualPixels[i].Equals(expectedPixels[i]))
                {
                    return false;
                }
            }

            return true;
        }

        private static void ReplaceArchitecturalTileVisual(
            Tile tile,
            string tileName,
            int textureWidth,
            int textureHeight,
            float pixelsPerUnit,
            Vector2 spritePivot,
            Color32[] pixels)
        {
            var oldSprite = tile.sprite;
            var oldTexture =
                oldSprite != null ? oldSprite.texture : null;

            tile.sprite = null;
            EditorUtility.SetDirty(tile);

            if (oldSprite != null && AssetDatabase.Contains(oldSprite))
            {
                Object.DestroyImmediate(oldSprite, true);
            }

            if (oldTexture != null && AssetDatabase.Contains(oldTexture))
            {
                Object.DestroyImmediate(oldTexture, true);
            }

            var replacementTexture = CreateTileTexture(
                tileName + "Texture",
                textureWidth,
                textureHeight,
                pixels);

            AssetDatabase.AddObjectToAsset(
                replacementTexture,
                tile);

            var replacementSprite = Sprite.Create(
                replacementTexture,
                new Rect(0f, 0f, textureWidth, textureHeight),
                spritePivot,
                pixelsPerUnit);

            replacementSprite.name = tileName + "Sprite";

            AssetDatabase.AddObjectToAsset(
                replacementSprite,
                tile);

            tile.sprite = replacementSprite;

            EditorUtility.SetDirty(replacementTexture);
            EditorUtility.SetDirty(replacementSprite);
            EditorUtility.SetDirty(tile);

            AssetDatabase.SaveAssetIfDirty(tile);
        }
        private static Texture2D CreateTileTexture(string name, int width, int height, Color32[] pixels)
        {
            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false)
            {
                name = name,
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Clamp
            };
            texture.SetPixels32(pixels);
            texture.Apply(false, false);
            return texture;
        }

        private static Color32[] CreateDiamondPixels(int width, int height, Color32 fill, Color32 border)
        {
            var pixels = new Color32[width * height];
            var transparent = new Color32(0, 0, 0, 0);
            for (var y = 0; y < height; y++)
            {
                for (var x = 0; x < width; x++)
                {
                    var normalizedX = Mathf.Abs((x + 0.5f - width * 0.5f) / (width * 0.5f));
                    var normalizedY = Mathf.Abs((y + 0.5f - height * 0.5f) / (height * 0.5f));
                    var diamondDistance = normalizedX + normalizedY;
                    pixels[y * width + x] = diamondDistance > 1f
                        ? transparent
                        : diamondDistance > 0.89f ? border : fill;
                }
            }

            return pixels;
        }

        private static Color32[] CreateWallPixels(int width, int height)
        {
            var pixels = new Color32[width * height];
            var stone = new Color32(74, 71, 68, 255);
            var alternateStone = new Color32(86, 82, 77, 255);
            var mortar = new Color32(39, 37, 36, 255);
            const int courseHeight = 32;
            // NSC-042 AC-001: must evenly divide width (64) so the brick pattern has the same
            // period as the tile texture itself. PaintWallRun repeats this exact texture across
            // adjacent one-cell segments (see BuildIsometricVisualLayer); a block width that
            // does not divide the texture width evenly cuts a block off mid-pattern at the tile
            // edge, and because every segment restarts from the same texture, the next segment
            // begins a fresh block instead of continuing it - the "pattern-phase reset" seam
            // human runtime validation observed. The previous value (48) did not divide 64.
            const int blockWidth = 32;

            for (var y = 0; y < height; y++)
            {
                var course = y / courseHeight;
                var horizontalMortar = y % courseHeight < 2;
                for (var x = 0; x < width; x++)
                {
                    var staggeredX = x + (course % 2) * (blockWidth / 2);
                    var verticalMortar = staggeredX % blockWidth < 2;
                    pixels[y * width + x] = horizontalMortar || verticalMortar
                        ? mortar
                        : ((staggeredX / blockWidth + course) % 2 == 0 ? stone : alternateStone);
                }
            }

            return pixels;
        }

        private sealed class ArchitecturalTileSet
        {
            public readonly Tile Floor;
            public readonly Tile Wall;
            public readonly Tile Architectural;

            public ArchitecturalTileSet(Tile floor, Tile wall, Tile architectural)
            {
                Floor = floor;
                Wall = wall;
                Architectural = architectural;
            }
        }

        // NSC-039 AC-001: the actual reusable Prefab asset every independently sorted or
        // interactive world object (the wizard, doors, and later enemies/props/obstacles) is
        // instantiated from, rather than each caller hand-assembling its own SpriteRenderer.
        // The template carries only the shared, non-negotiable parts of the convention - the
        // sorting layer/order established above - so callers can never accidentally diverge
        // from it; they only ever customize sprite artwork and footprint size.
        private static GameObject EnsureWorldSpritePrefab(string architecturalTileAssetFolder)
        {
            if (string.IsNullOrEmpty(architecturalTileAssetFolder))
            {
                // Parameterless in-memory test seam: an equivalent transient, owned template
                // instead of a saved AssetDatabase Prefab, mirroring the existing Tile/Sprite
                // transient-object split used elsewhere in this builder.
                var transientTemplate = OwnTransientArchitecturalObject(BuildWorldSpritePrefabTemplate());
                transientTemplate.hideFlags = HideFlags.HideAndDontSave;
                return transientTemplate;
            }

            var worldSpritePrefabAssetFolder =
                architecturalTileAssetFolder + "/" + WorldSpritePrefabAssetFolderName;
            EnsureFolder(worldSpritePrefabAssetFolder);
            var prefabAssetPath = worldSpritePrefabAssetFolder + "/" + WorldSpritePrefabAssetName;
            var existingPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabAssetPath);
            if (existingPrefab != null)
            {
                // A previously saved prefab asset may predate the current shared convention
                // (for example an older asset saved before spriteSortPoint was pinned to
                // Pivot). Repair it in place rather than trusting that whatever is already on
                // disk still matches the convention this method is supposed to guarantee.
                if (RepairWorldSpritePrefabConvention(existingPrefab))
                {
                    EditorUtility.SetDirty(existingPrefab);
                    AssetDatabase.SaveAssetIfDirty(existingPrefab);
                }
                return existingPrefab;
            }

            var template = BuildWorldSpritePrefabTemplate();
            var savedPrefab = PrefabUtility.SaveAsPrefabAsset(template, prefabAssetPath);
            Object.DestroyImmediate(template);
            return savedPrefab;
        }

        private static GameObject BuildWorldSpritePrefabTemplate()
        {
            var template = new GameObject("WorldSpriteVisual");
            var renderer = template.AddComponent<SpriteRenderer>();
            ApplyWorldSpriteRendererConvention(renderer);
            return template;
        }

        // Shared by both the freshly-created template and the existing-prefab repair path so
        // the two can never drift apart into two different definitions of "the convention".
        private static void ApplyWorldSpriteRendererConvention(SpriteRenderer renderer)
        {
            renderer.sortingLayerName = WorldSpriteSortingLayerName;
            renderer.sortingOrder = WorldSpriteSortingOrder;
            // Ground-contact sorting only actually takes effect if the renderer sorts by its
            // pivot (the bottom-anchored GroundContactSpritePivot below) rather than Unity's
            // default Center sort point; otherwise a taller sprite's center - not its feet -
            // would determine its camera transparency sort depth.
            renderer.spriteSortPoint = SpriteSortPoint.Pivot;
        }

        private static bool RepairWorldSpritePrefabConvention(GameObject prefabAsset)
        {
            var renderer = prefabAsset.GetComponent<SpriteRenderer>();
            if (renderer == null) return false;

            var changed = renderer.sortingLayerName != WorldSpriteSortingLayerName ||
                          renderer.sortingOrder != WorldSpriteSortingOrder ||
                          renderer.spriteSortPoint != SpriteSortPoint.Pivot;
            if (!changed) return false;

            ApplyWorldSpriteRendererConvention(renderer);
            return true;
        }

        // Every world sprite instance is built the same way from the shared prefab above: a
        // ground-contact (feet) local position combined with a bottom-anchored sprite pivot, so
        // artwork extends upward from that ground point instead of being centered on it. This
        // keeps the Transform position that the camera's custom-axis transparency sort orders
        // by consistently anchored at each object's true isometric ground position, regardless
        // of how tall the sprite is - a tall door or prop never appears at a different depth
        // than a short one merely because its silhouette is taller. Gameplay collision is kept
        // on separate, independently sized colliders (the same separation already used between
        // the Tilemap visual layer and the gameplay Floor/Walls colliders).
        private static readonly Vector2 GroundContactSpritePivot = new Vector2(0.5f, 0f);

        private static SpriteRenderer CreateWorldSpriteVisual(
            string name,
            string persistentAssetKey,
            Transform parent,
            Vector3 groundContactLocalPosition,
            Quaternion localRotation,
            Vector2 worldSize,
            Color32[] spritePixels,
            string architecturalTileAssetFolder)
        {
            var prefab = EnsureWorldSpritePrefab(architecturalTileAssetFolder);
            var spriteObject = string.IsNullOrEmpty(architecturalTileAssetFolder)
                ? Object.Instantiate(prefab)
                : (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            spriteObject.name = name;
            spriteObject.transform.SetParent(parent, false);
            spriteObject.transform.localPosition = groundContactLocalPosition;
            // NSC-039 human runtime correction: the shared prefab convention owns reusable
            // SpriteRenderer/sorting/pivot behavior only. It must never force one non-zero
            // billboard/tilt rotation onto every consumer - authored orientation (e.g. the
            // door's human-validated zero/identity rotation) stays a per-instance decision
            // made by each call site instead.
            spriteObject.transform.localRotation = localRotation;
            spriteObject.transform.localScale = new Vector3(worldSize.x, worldSize.y, 1f);

            var renderer = spriteObject.GetComponent<SpriteRenderer>();
            // persistentAssetKey is the on-disk asset identity and is intentionally separate
            // from the scene hierarchy object name above: multiple different world objects
            // (e.g. future enemies/props) can reasonably share a generic hierarchy child name
            // such as "Visual" without colliding on the same persisted sprite artwork.
            renderer.sprite = LoadOrCreateWorldSprite(
                architecturalTileAssetFolder,
                persistentAssetKey + ".asset",
                persistentAssetKey,
                WorldSpriteTextureSize,
                WorldSpriteTextureSize,
                WorldSpriteTextureSize,
                GroundContactSpritePivot,
                spritePixels);
            return renderer;
        }

        // Mirrors LoadOrCreateArchitecturalTile's persistence split: a real AssetDatabase
        // Sprite/Texture pair when a caller-owned folder is supplied (required for the sprite
        // reference to survive the saved/reopened canonical scene), or a HideAndDontSave
        // transient pair owned by the parameterless in-memory test seam otherwise.
        private static Sprite LoadOrCreateWorldSprite(
            string assetFolder,
            string assetFileName,
            string spriteName,
            int textureWidth,
            int textureHeight,
            float pixelsPerUnit,
            Vector2 pivot,
            Color32[] pixels)
        {
            if (!string.IsNullOrEmpty(assetFolder))
            {
                var assetPath = assetFolder + "/" + assetFileName;
                var existingTexture = AssetDatabase.LoadAssetAtPath<Texture2D>(assetPath);
                if (existingTexture != null)
                {
                    foreach (var subAsset in AssetDatabase.LoadAllAssetsAtPath(assetPath))
                    {
                        if (subAsset is Sprite existingSprite) return existingSprite;
                    }
                }

                var persistentTexture = CreateTileTexture(spriteName + "Texture", textureWidth, textureHeight, pixels);
                AssetDatabase.CreateAsset(persistentTexture, assetPath);

                var persistentSprite = Sprite.Create(
                    persistentTexture,
                    new Rect(0f, 0f, textureWidth, textureHeight),
                    pivot,
                    pixelsPerUnit);
                persistentSprite.name = spriteName;
                AssetDatabase.AddObjectToAsset(persistentSprite, persistentTexture);

                EditorUtility.SetDirty(persistentTexture);
                EditorUtility.SetDirty(persistentSprite);
                AssetDatabase.SaveAssetIfDirty(persistentTexture);
                return persistentSprite;
            }

            var inMemoryTexture = OwnTransientArchitecturalObject(
                CreateTileTexture(spriteName + "Texture", textureWidth, textureHeight, pixels));
            inMemoryTexture.hideFlags = HideFlags.HideAndDontSave;

            var inMemorySprite = OwnTransientArchitecturalObject(Sprite.Create(
                inMemoryTexture,
                new Rect(0f, 0f, textureWidth, textureHeight),
                pivot,
                pixelsPerUnit));
            inMemorySprite.name = spriteName;
            inMemorySprite.hideFlags = HideFlags.HideAndDontSave;
            return inMemorySprite;
        }

        private static Color32[] CreateBorderedRectPixels(
            int width, int height, Color32 fill, Color32 border, int borderThicknessPx)
        {
            var pixels = new Color32[width * height];
            for (var y = 0; y < height; y++)
            {
                for (var x = 0; x < width; x++)
                {
                    var onBorder = x < borderThicknessPx || y < borderThicknessPx ||
                                   x >= width - borderThicknessPx || y >= height - borderThicknessPx;
                    pixels[y * width + x] = onBorder ? border : fill;
                }
            }

            return pixels;
        }

        // NSC-039 human runtime correction: a readable placeholder wizard silhouette (a
        // round head over a tapered robe) instead of an undifferentiated solid/bordered
        // square, so isometric sorting/occlusion against Tilemap walls and the door is
        // actually visible during validation. This remains placeholder-quality art only;
        // no final character art is implied.
        private static Color32[] CreateWizardSilhouettePixels(int width, int height, Color32 fill, Color32 border)
        {
            var pixels = new Color32[width * height];
            var transparent = new Color32(0, 0, 0, 0);

            var headCenterX = width * 0.5f;
            var headCenterY = height * 0.78f;
            var headRadius = width * 0.16f;
            const float headBorderThicknessPx = 1.5f;

            var robeTopY = height * 0.62f;
            var robeBottomY = height * 0.04f;
            var robeTopHalfWidth = width * 0.14f;
            var robeBottomHalfWidth = width * 0.32f;
            const float robeBorderThicknessPx = 1.5f;

            for (var y = 0; y < height; y++)
            {
                for (var x = 0; x < width; x++)
                {
                    var pixelCenterX = x + 0.5f;
                    var pixelCenterY = y + 0.5f;

                    var headOffsetX = pixelCenterX - headCenterX;
                    var headOffsetY = pixelCenterY - headCenterY;
                    var headDistance = Mathf.Sqrt(headOffsetX * headOffsetX + headOffsetY * headOffsetY);
                    var inHead = headDistance <= headRadius;
                    var onHeadBorder = inHead && headDistance >= headRadius - headBorderThicknessPx;

                    var inRobe = false;
                    var onRobeBorder = false;
                    if (pixelCenterY <= robeTopY && pixelCenterY >= robeBottomY)
                    {
                        var robeHeightFraction = (robeTopY - pixelCenterY) / (robeTopY - robeBottomY);
                        var robeHalfWidth = Mathf.Lerp(robeTopHalfWidth, robeBottomHalfWidth, robeHeightFraction);
                        var robeOffsetX = Mathf.Abs(pixelCenterX - headCenterX);
                        inRobe = robeOffsetX <= robeHalfWidth;
                        onRobeBorder = inRobe && robeOffsetX >= robeHalfWidth - robeBorderThicknessPx;
                    }

                    pixels[y * width + x] = inHead || inRobe
                        ? (onHeadBorder || onRobeBorder ? border : fill)
                        : transparent;
                }
            }

            return pixels;
        }

        private static GameObject BuildDoor(out DoorInteractable door, string architecturalTileAssetFolder)
        {
            var doorRoot = new GameObject("DoorRoot");
            doorRoot.transform.position = Vector3.zero;

            var rangeTrigger = doorRoot.AddComponent<BoxCollider>();
            rangeTrigger.isTrigger = true;
            rangeTrigger.size = new Vector3(3f, 3f, 3f);
            rangeTrigger.center = new Vector3(0f, 1.5f, 0f);

            const float visualLocalHeight = 1.25f;
            var visual = new GameObject("DoorVisual");
            visual.transform.SetParent(doorRoot.transform, false);
            visual.transform.localPosition = new Vector3(0f, visualLocalHeight, 0f);

            // Gameplay collision (the doorway blocker) stays a plain BoxCollider sized to the
            // door's footprint, kept separate from the SpriteRenderer visual child below so the
            // visual can hold its own authored orientation and non-uniform scale without
            // shearing the collider.
            var doorwayBlocker = visual.AddComponent<BoxCollider>();
            doorwayBlocker.size = new Vector3(2f, 2.5f, 0.3f);

            // DoorVisual itself stays elevated (visualLocalHeight) for the doorway-blocker
            // collider and ComputeGroundSelectionOffset's click math below, but the sprite's own
            // local position cancels that elevation back down to doorRoot's ground-contact
            // point, per the shared ground-contact sorting convention above. The bottom-anchored
            // prefab pivot then rebuilds the identical [0, 2.5] visual footprint from there.
            // Human-validated correction: the authored DoorSprite orientation is identity
            // (inspector 0,0,0), not a camera-facing billboard/tilt.
            CreateWorldSpriteVisual(
                "DoorSprite",
                "DoorSprite",
                visual.transform,
                new Vector3(0f, -visualLocalHeight, 0f),
                Quaternion.identity,
                new Vector2(2f, 2.5f),
                CreateBorderedRectPixels(
                    WorldSpriteTextureSize, WorldSpriteTextureSize, DoorSpriteFillColor, DoorSpriteBorderColor,
                    WorldSpriteBorderThicknessPx),
                architecturalTileAssetFolder);

            door = doorRoot.AddComponent<DoorInteractable>();
            SetPrivateField(door, "doorVisual", visual);
            SetPrivateField(door, "doorwayBlocker", doorwayBlocker);
            SetPrivateFieldValue(door, "groundSelectionOffset", ComputeGroundSelectionOffset(visualLocalHeight));

            // AC-001/AC-002/AC-003: gives the sealed door a base appearance distinguishable
            // from the plain-primitive walls plus hover/selected/opening feedback. The
            // player-side references (playerMovement/interactionController) are wired once
            // BuildPlayer creates them later in RebuildSceneContents.
            var feedback = doorRoot.AddComponent<DoorInteractionFeedback>();
            SetPrivateField(feedback, "door", door);
            SetPrivateField(feedback, "doorRenderer", visual.GetComponentInChildren<Renderer>());

            return doorRoot;
        }

        // The visible door's silhouette is centered above the ground (at visualLocalHeight), not
        // on it. Under the fixed isometric camera's orthographic (parallel) projection, a screen
        // click through that visual center lands on the ground plane offset horizontally from
        // the door's own ground position, purely because of that height difference. This computes
        // that offset analytically from the camera's fixed rotation and the visual's height - it
        // does not use Camera/ScreenPointToRay, so it is not an independent screen-to-world
        // projection; it is a one-time authored value DoorInteractable's ground-space selection
        // test consumes at runtime instead of independently projecting screen coordinates.
        private static Vector3 ComputeGroundSelectionOffset(float visualLocalHeight)
        {
            var forward = Quaternion.Euler(IsometricCameraEulerAngles) * Vector3.forward;
            if (Mathf.Approximately(forward.y, 0f)) return Vector3.zero;

            var t = -visualLocalHeight / forward.y;
            return new Vector3(forward.x * t, 0f, forward.z * t);
        }

        private static void BuildWalls(Vector3 doorPosition)
        {
            var walls = new GameObject("Walls");

            var left = GameObject.CreatePrimitive(PrimitiveType.Cube);
            left.name = "WallLeft";
            left.transform.SetParent(walls.transform, false);
            left.transform.position = doorPosition + new Vector3(-2.5f, 1.25f, 0f);
            left.transform.localScale = new Vector3(3f, 2.5f, 0.3f);

            var right = GameObject.CreatePrimitive(PrimitiveType.Cube);
            right.name = "WallRight";
            right.transform.SetParent(walls.transform, false);
            right.transform.position = doorPosition + new Vector3(2.5f, 1.25f, 0f);
            right.transform.localScale = new Vector3(3f, 2.5f, 0.3f);
        }

        private static void BuildPlayer(
            out PlayerMovement movement,
            out PlayerInteractionController interactionController,
            out PlayerHealth health,
            out DebugDamageControl debugControl,
            out PlayerMana mana,
            out DebugManaSpendControl debugManaControl,
            string architecturalTileAssetFolder)
        {
            var player = new GameObject("Player");
            player.transform.position = new Vector3(0f, 0f, -4f);

            var characterController = player.AddComponent<CharacterController>();
            characterController.center = new Vector3(0f, 1f, 0f);
            characterController.height = 2f;
            characterController.radius = 0.5f;

            // CharacterController collision keeps the capsule approximately one skinWidth
            // above the collision surface. Spawn at that already-grounded root height so
            // Play Mode does not begin with the wizard visibly falling onto the floor.
            player.transform.position =
                new Vector3(0f, characterController.skinWidth, -4f);

            // Placeholder wizard sprite (GDD: placeholder character sprites are acceptable),
            // instantiated from the same reusable world-space SpriteRenderer prefab as the
            // door. Already at the ground-contact convention's neutral local position, so the
            // sprite's feet sit exactly at the player's own transform position. The hierarchy
            // child keeps the existing "Visual" name other code/tests depend on, while
            // "WizardSprite" is the persistent asset identity so a future enemy/prop that also
            // names its child "Visual" cannot silently reuse the wizard's sprite asset.
            CreateWorldSpriteVisual(
                "Visual",
                "WizardSprite",
                player.transform,
                Vector3.zero,
                Quaternion.identity,
                new Vector2(1f, 2f),
                CreateWizardSilhouettePixels(
                    WorldSpriteTextureSize, WorldSpriteTextureSize, WizardSpriteFillColor, WizardSpriteBorderColor),
                architecturalTileAssetFolder);

            health = player.AddComponent<PlayerHealth>();
            interactionController = player.AddComponent<PlayerInteractionController>();
            movement = player.AddComponent<PlayerMovement>();
            debugControl = player.AddComponent<DebugDamageControl>();
            mana = player.AddComponent<PlayerMana>();
            debugManaControl = player.AddComponent<DebugManaSpendControl>();

            SetPrivateField(interactionController, "playerHealth", health);
            SetPrivateField(debugControl, "target", health);
            SetPrivateField(debugManaControl, "target", mana);
        }

        private static void BuildUI(DoorInteractable door, DebugDamageControl debugControl,
            PlayerHealth health, PlayerMana mana, DebugManaSpendControl debugManaControl)
        {
            var canvasObject = new GameObject("Canvas");
            var canvas = canvasObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvasObject.AddComponent<CanvasScaler>();
            canvasObject.AddComponent<GraphicRaycaster>();

            var eventSystemObject = new GameObject("EventSystem");
            eventSystemObject.AddComponent<EventSystem>();
            eventSystemObject.AddComponent<InputSystemUIInputModule>();

            var promptRoot = new GameObject("InteractPrompt");
            promptRoot.transform.SetParent(canvasObject.transform, false);
            var promptRect = promptRoot.AddComponent<RectTransform>();
            promptRect.anchorMin = new Vector2(0.5f, 0.2f);
            promptRect.anchorMax = new Vector2(0.5f, 0.2f);
            promptRect.sizeDelta = new Vector2(400f, 40f);
            var promptText = promptRoot.AddComponent<Text>();
            promptText.text = "Sealed Door - Click to Open";
            promptText.alignment = TextAnchor.MiddleCenter;
            promptText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            promptText.color = Color.white;

            var progressObject = new GameObject("ProgressFill");
            progressObject.transform.SetParent(canvasObject.transform, false);
            var progressRect = progressObject.AddComponent<RectTransform>();
            progressRect.anchorMin = new Vector2(0.5f, 0.12f);
            progressRect.anchorMax = new Vector2(0.5f, 0.12f);
            progressRect.sizeDelta = new Vector2(300f, 20f);
            var progressBackgroundImage = progressObject.AddComponent<Image>();
            progressBackgroundImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            progressBackgroundImage.type = Image.Type.Sliced;
            progressBackgroundImage.color = new Color(0.15f, 0.15f, 0.15f, 0.85f);

            var progressFillObject = new GameObject("Fill");
            progressFillObject.transform.SetParent(progressObject.transform, false);
            var progressFillRect = progressFillObject.AddComponent<RectTransform>();
            progressFillRect.anchorMin = Vector2.zero;
            progressFillRect.anchorMax = Vector2.one;
            progressFillRect.offsetMin = Vector2.zero;
            progressFillRect.offsetMax = Vector2.zero;
            var progressFill = progressFillObject.AddComponent<Image>();
            // A Filled Image with no sprite bypasses fill geometry and always renders as a full
            // solid rect, so fillAmount visibly does nothing without a sprite assigned here.
            progressFill.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
            progressFill.type = Image.Type.Filled;
            progressFill.fillMethod = Image.FillMethod.Horizontal;
            progressFill.fillOrigin = (int)Image.OriginHorizontal.Left;
            progressFill.fillAmount = 0f;
            progressFill.color = Color.green;

            var uiBinding = canvasObject.AddComponent<DoorInteractionUI>();
            SetPrivateField(uiBinding, "door", door);
            SetPrivateField(uiBinding, "promptRoot", promptRoot);
            SetPrivateField(uiBinding, "progressFillImage", progressFill);

            var buttonObject = new GameObject("DebugDamageButton");
            buttonObject.transform.SetParent(canvasObject.transform, false);
            var buttonRect = buttonObject.AddComponent<RectTransform>();
            buttonRect.anchorMin = new Vector2(0.02f, 0.02f);
            buttonRect.anchorMax = new Vector2(0.02f, 0.02f);
            buttonRect.pivot = Vector2.zero;
            buttonRect.sizeDelta = new Vector2(260f, 40f);
            var buttonImage = buttonObject.AddComponent<Image>();
            buttonImage.color = new Color(0.6f, 0.1f, 0.1f);
            var damageButton = buttonObject.AddComponent<Button>();
            damageButton.targetGraphic = buttonImage;

            var buttonTextObject = new GameObject("Text");
            buttonTextObject.transform.SetParent(buttonObject.transform, false);
            var buttonTextRect = buttonTextObject.AddComponent<RectTransform>();
            buttonTextRect.anchorMin = Vector2.zero;
            buttonTextRect.anchorMax = Vector2.one;
            buttonTextRect.sizeDelta = Vector2.zero;
            var buttonText = buttonTextObject.AddComponent<Text>();
            buttonText.text = "DEBUG: Take Damage (K)";
            buttonText.alignment = TextAnchor.MiddleCenter;
            buttonText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            buttonText.color = Color.white;
            buttonText.fontSize = 14;

            UnityEventTools.AddPersistentListener(damageButton.onClick, debugControl.TriggerDebugDamage);

            BuildHealthUI(canvasObject, health);
            BuildManaUI(canvasObject, mana, debugManaControl);

            BuildControlsHud(canvasObject.transform);
        }

        /// Mirrors the door's ProgressFill pattern: a background bar with a Filled child
        /// Image whose fillAmount tracks CurrentHealth/MaxHealth. Positioned above the door
        /// progress bar so it never overlaps the door or mana indicators.
        private static void BuildHealthUI(GameObject canvasObject, PlayerHealth health)
        {
            var healthBarObject = new GameObject("HealthFill");
            healthBarObject.transform.SetParent(canvasObject.transform, false);
            var healthBarRect = healthBarObject.AddComponent<RectTransform>();
            // Keep health in its own center-screen vertical lane above the interaction
            // prompt. This leaves clear separation from the prompt, progress bar, and mana bar.
            healthBarRect.anchorMin = new Vector2(0.5f, 0.25f);
            healthBarRect.anchorMax = new Vector2(0.5f, 0.25f);
            healthBarRect.sizeDelta = new Vector2(300f, 20f);
            var healthBarBackgroundImage = healthBarObject.AddComponent<Image>();
            healthBarBackgroundImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            healthBarBackgroundImage.type = Image.Type.Sliced;
            healthBarBackgroundImage.color = new Color(0.15f, 0.15f, 0.15f, 0.85f);

            var healthFillObject = new GameObject("Fill");
            healthFillObject.transform.SetParent(healthBarObject.transform, false);
            var healthFillRect = healthFillObject.AddComponent<RectTransform>();
            healthFillRect.anchorMin = Vector2.zero;
            healthFillRect.anchorMax = Vector2.one;
            healthFillRect.offsetMin = Vector2.zero;
            healthFillRect.offsetMax = Vector2.zero;
            var healthFill = healthFillObject.AddComponent<Image>();
            healthFill.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
            healthFill.type = Image.Type.Filled;
            healthFill.fillMethod = Image.FillMethod.Horizontal;
            healthFill.fillOrigin = (int)Image.OriginHorizontal.Left;
            healthFill.fillAmount = 1f;
            healthFill.color = Color.red;

            var healthUiBinding = canvasObject.AddComponent<PlayerHealthUI>();
            SetPrivateField(healthUiBinding, "health", health);
            SetPrivateField(healthUiBinding, "fillImage", healthFill);
        }

        /// Mirrors the door's ProgressFill pattern: a background bar with a Filled child
        /// Image whose fillAmount tracks CurrentMana/MaxMana. Positioned below the door
        /// progress bar so the two never overlap.
        private static void BuildManaUI(GameObject canvasObject, PlayerMana mana, DebugManaSpendControl debugManaControl)
        {
            var manaBarObject = new GameObject("ManaFill");
            manaBarObject.transform.SetParent(canvasObject.transform, false);
            var manaBarRect = manaBarObject.AddComponent<RectTransform>();
            manaBarRect.anchorMin = new Vector2(0.5f, 0.06f);
            manaBarRect.anchorMax = new Vector2(0.5f, 0.06f);
            manaBarRect.sizeDelta = new Vector2(300f, 20f);
            var manaBarBackgroundImage = manaBarObject.AddComponent<Image>();
            manaBarBackgroundImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            manaBarBackgroundImage.type = Image.Type.Sliced;
            manaBarBackgroundImage.color = new Color(0.15f, 0.15f, 0.15f, 0.85f);

            var manaFillObject = new GameObject("Fill");
            manaFillObject.transform.SetParent(manaBarObject.transform, false);
            var manaFillRect = manaFillObject.AddComponent<RectTransform>();
            manaFillRect.anchorMin = Vector2.zero;
            manaFillRect.anchorMax = Vector2.one;
            manaFillRect.offsetMin = Vector2.zero;
            manaFillRect.offsetMax = Vector2.zero;
            var manaFill = manaFillObject.AddComponent<Image>();
            manaFill.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
            manaFill.type = Image.Type.Filled;
            manaFill.fillMethod = Image.FillMethod.Horizontal;
            manaFill.fillOrigin = (int)Image.OriginHorizontal.Left;
            manaFill.fillAmount = 1f;
            manaFill.color = Color.blue;

            var manaUiBinding = canvasObject.AddComponent<PlayerManaUI>();
            SetPrivateField(manaUiBinding, "mana", mana);
            SetPrivateField(manaUiBinding, "fillImage", manaFill);

            var manaButtonObject = new GameObject("DebugManaSpendButton");
            manaButtonObject.transform.SetParent(canvasObject.transform, false);
            var manaButtonRect = manaButtonObject.AddComponent<RectTransform>();
            manaButtonRect.anchorMin = new Vector2(0.02f, 0.02f);
            manaButtonRect.anchorMax = new Vector2(0.02f, 0.02f);
            manaButtonRect.pivot = Vector2.zero;
            manaButtonRect.anchoredPosition = new Vector2(0f, 44f);
            manaButtonRect.sizeDelta = new Vector2(260f, 40f);
            var manaButtonImage = manaButtonObject.AddComponent<Image>();
            manaButtonImage.color = new Color(0.1f, 0.1f, 0.6f);
            var manaButton = manaButtonObject.AddComponent<Button>();
            manaButton.targetGraphic = manaButtonImage;

            var manaButtonTextObject = new GameObject("Text");
            manaButtonTextObject.transform.SetParent(manaButtonObject.transform, false);
            var manaButtonTextRect = manaButtonTextObject.AddComponent<RectTransform>();
            manaButtonTextRect.anchorMin = Vector2.zero;
            manaButtonTextRect.anchorMax = Vector2.one;
            manaButtonTextRect.sizeDelta = Vector2.zero;
            var manaButtonText = manaButtonTextObject.AddComponent<Text>();
            manaButtonText.text = "DEBUG: Spend Mana (L)";
            manaButtonText.alignment = TextAnchor.MiddleCenter;
            manaButtonText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            manaButtonText.color = Color.white;
            manaButtonText.fontSize = 14;

            UnityEventTools.AddPersistentListener(manaButton.onClick, debugManaControl.TriggerDebugSpend);
        }

        /// Compact, always-visible controls panel. Kept as a sibling of, not merged
        /// into, the interaction prompt and progress-fill objects, and positioned in
        /// the top-left so it never overlaps them or the bottom-left debug button.
        private static void BuildControlsHud(Transform canvasTransform)
        {
            var hudRoot = new GameObject("ControlsHud");
            hudRoot.transform.SetParent(canvasTransform, false);
            var hudRect = hudRoot.AddComponent<RectTransform>();
            hudRect.anchorMin = new Vector2(0f, 1f);
            hudRect.anchorMax = new Vector2(0f, 1f);
            hudRect.pivot = new Vector2(0f, 1f);
            hudRect.anchoredPosition = new Vector2(16f, -16f);
            hudRect.sizeDelta = new Vector2(300f, 130f);

            var hudBackground = hudRoot.AddComponent<Image>();
            hudBackground.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            hudBackground.type = Image.Type.Sliced;
            hudBackground.color = new Color(0f, 0f, 0f, 0.6f);

            var hudTextObject = new GameObject("Text");
            hudTextObject.transform.SetParent(hudRoot.transform, false);
            var hudTextRect = hudTextObject.AddComponent<RectTransform>();
            hudTextRect.anchorMin = Vector2.zero;
            hudTextRect.anchorMax = Vector2.one;
            hudTextRect.offsetMin = new Vector2(10f, 8f);
            hudTextRect.offsetMax = new Vector2(-10f, -8f);
            var hudText = hudTextObject.AddComponent<Text>();
            hudText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            hudText.fontSize = 14;
            hudText.alignment = TextAnchor.UpperLeft;
            hudText.color = Color.white;
            hudText.horizontalOverflow = HorizontalWrapMode.Wrap;
            hudText.verticalOverflow = VerticalWrapMode.Overflow;
            hudText.text =
                "Click/Hold Left Mouse - Move\n" +
                "Click Sealed Door - Approach and Open\n" +
                "Taking damage or moving away once opening starts\ncancels the opening attempt\n" +
                "[Debug/Test] K - Take Damage\n" +
                "[Debug/Test] L - Spend Mana";
        }

        private static void SetPrivateField(Object target, string fieldName, Object value)
        {
            var serializedObject = new SerializedObject(target);
            var property = serializedObject.FindProperty(fieldName);
            if (property == null)
            {
                Debug.LogWarning($"Field '{fieldName}' not found on {target.GetType().Name}.");
                return;
            }

            property.objectReferenceValue = value;
            serializedObject.ApplyModifiedPropertiesWithoutUndo();
        }

        // SerializedProperty has no generic value-type setter, so plain-data fields (Vector3,
        // float, etc.) are assigned directly through reflection instead.
        private static void SetPrivateFieldValue(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName,
                System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
            if (field == null)
            {
                Debug.LogWarning($"Field '{fieldName}' not found on {target.GetType().Name}.");
                return;
            }

            field.SetValue(target, value);
        }
    }
}
