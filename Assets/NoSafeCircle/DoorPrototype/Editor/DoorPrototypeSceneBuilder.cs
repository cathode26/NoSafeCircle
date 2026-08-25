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

            var doorRoot = BuildDoor(out var door);
            BuildWalls(doorRoot.transform.position);
            if (string.IsNullOrEmpty(architecturalTileAssetFolder))
            {
                ownedTransientArchitecturalScene = scene;
            }
            BuildIsometricVisualLayer(doorRoot.transform.position, architecturalTileAssetFolder);

            BuildPlayer(out var movement, out var interactionController, out var health, out var debugControl,
                out var mana, out var debugManaControl);
            SetPrivateField(movement, "interactionController", interactionController);

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
                -100);
            PaintFloorTiles(floorTilemap, tiles.Floor);

            var wallTilemap = CreateVisualOnlyTilemap(
                gridObject.transform,
                WallTilemapName,
                doorPosition + new Vector3(-2.5f, 1.25f, WallVisualOffset),
                Quaternion.identity,
                -50);
            wallTilemap.SetTile(Vector3Int.zero, tiles.Wall);
            wallTilemap.SetTile(new Vector3Int(5, -5, 0), tiles.Wall);

            var architecturalTilemap = CreateVisualOnlyTilemap(
                gridObject.transform,
                ArchitecturalTilemapName,
                new Vector3(0f, FloorVisualOffset * 2f, 0f),
                FloorTilemapRotation,
                -90);
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
            renderer.sortingOrder = sortingOrder;

            return tilemap;
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
                    CreateDiamondPixels(64, 32, new Color32(80, 76, 70, 255), new Color32(49, 46, 43, 255))),
                LoadOrCreateArchitecturalTile(
                    assetFolder,
                    "WallTile.asset",
                    "WallTile",
                    192,
                    160,
                    64f,
                    CreateWallPixels(192, 160)),
                LoadOrCreateArchitecturalTile(
                    assetFolder,
                    "ArchitecturalBorderTile.asset",
                    "ArchitecturalBorderTile",
                    64,
                    32,
                    64f,
                    CreateDiamondPixels(64, 32, new Color32(121, 105, 72, 255), new Color32(65, 56, 40, 255))));
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
            if (!string.IsNullOrEmpty(assetFolder))
            {
                var assetPath = assetFolder + "/" + assetFileName;
                var existing = AssetDatabase.LoadAssetAtPath<Tile>(assetPath);
                if (existing != null)
                {
                    existing.colliderType = Tile.ColliderType.None;
                    EditorUtility.SetDirty(existing);
                    AssetDatabase.SaveAssetIfDirty(existing);
                    return existing;
                }

                var persistentTile = ScriptableObject.CreateInstance<Tile>();
                persistentTile.name = tileName;
                persistentTile.colliderType = Tile.ColliderType.None;
                AssetDatabase.CreateAsset(persistentTile, assetPath);

                var persistentTexture = CreateTileTexture(tileName + "Texture", textureWidth, textureHeight, pixels);
                AssetDatabase.AddObjectToAsset(persistentTexture, persistentTile);

                var persistentSprite = Sprite.Create(
                    persistentTexture,
                    new Rect(0f, 0f, textureWidth, textureHeight),
                    new Vector2(0.5f, 0.5f),
                    pixelsPerUnit);
                persistentSprite.name = tileName + "Sprite";
                AssetDatabase.AddObjectToAsset(persistentSprite, persistentTile);

                persistentTile.sprite = persistentSprite;
                EditorUtility.SetDirty(persistentTexture);
                EditorUtility.SetDirty(persistentSprite);
                EditorUtility.SetDirty(persistentTile);
                AssetDatabase.SaveAssetIfDirty(persistentTile);
                return persistentTile;
            }

            var inMemoryTile = OwnTransientArchitecturalObject(ScriptableObject.CreateInstance<Tile>());
            inMemoryTile.name = tileName;
            inMemoryTile.colliderType = Tile.ColliderType.None;
            inMemoryTile.hideFlags = HideFlags.HideAndDontSave;

            var inMemoryTexture = OwnTransientArchitecturalObject(
                CreateTileTexture(tileName + "Texture", textureWidth, textureHeight, pixels));
            inMemoryTexture.hideFlags = HideFlags.HideAndDontSave;

            var inMemorySprite = OwnTransientArchitecturalObject(Sprite.Create(
                inMemoryTexture,
                new Rect(0f, 0f, textureWidth, textureHeight),
                new Vector2(0.5f, 0.5f),
                pixelsPerUnit));
            inMemorySprite.name = tileName + "Sprite";
            inMemorySprite.hideFlags = HideFlags.HideAndDontSave;
            inMemoryTile.sprite = inMemorySprite;
            return inMemoryTile;
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
            const int blockWidth = 48;

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

        private static GameObject BuildDoor(out DoorInteractable door)
        {
            var doorRoot = new GameObject("DoorRoot");
            doorRoot.transform.position = Vector3.zero;

            var rangeTrigger = doorRoot.AddComponent<BoxCollider>();
            rangeTrigger.isTrigger = true;
            rangeTrigger.size = new Vector3(3f, 3f, 3f);
            rangeTrigger.center = new Vector3(0f, 1.5f, 0f);

            var visual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            visual.name = "DoorVisual";
            visual.transform.SetParent(doorRoot.transform, false);
            visual.transform.localPosition = new Vector3(0f, 1.25f, 0f);
            visual.transform.localScale = new Vector3(2f, 2.5f, 0.3f);

            door = doorRoot.AddComponent<DoorInteractable>();
            SetPrivateField(door, "doorVisual", visual);
            SetPrivateField(door, "doorwayBlocker", visual.GetComponent<Collider>());

            return doorRoot;
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
            out DebugManaSpendControl debugManaControl)
        {
            var player = new GameObject("Player");
            player.transform.position = new Vector3(0f, 1f, -4f);

            var characterController = player.AddComponent<CharacterController>();
            characterController.center = new Vector3(0f, 1f, 0f);
            characterController.height = 2f;
            characterController.radius = 0.5f;

            var visual = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            visual.name = "Visual";
            visual.transform.SetParent(player.transform, false);
            visual.transform.localPosition = new Vector3(0f, 1f, 0f);
            Object.DestroyImmediate(visual.GetComponent<Collider>());

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
            promptText.text = "Hold E to Open";
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
                "Hold E - Open Door\n" +
                "Moving or taking damage\ncancels the opening attempt\n" +
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
    }
}
