using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Tilemaps;
using UnityEngine.UI;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.World;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor
{
    public static class DoorPrototypeSceneBuilder
    {
        private const string SceneFolder = "Assets/Scenes";
        private const string ScenePath = SceneFolder + "/DoorPrototype.unity";
        private const string ArchitecturalTileAssetFolder =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";

        private const string GameplayNavigationRootName = "GameplayNavigation";
        private const string FloorRunRestartControllerName = "FloorRunRestartController";

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
        // PUBLIC so the Editor test assembly can assert the RELATION rather than the current
        // value. It was internal, and NoSafeCircle.DoorPrototype.Tests.Editor is a separate
        // assembly, so every room test asserted the literal "Default" instead -- which keeps
        // passing after this constant is repointed while the room's floor and walls sort
        // wrongly against every world sprite. Reaching this constant across that boundary is
        // also what left NSC-045's candidate unable to compile.
        public const string WorldSpriteSortingLayerName = "Default";
        private const int WorldSpriteSortingOrder = 0;
        private const int BackgroundGroundSortingOrder = -100;
        private const int BackgroundArchitecturalBorderSortingOrder = -90;

        internal const int WorldSpriteTextureSize = 128;

        // Subfolder name only, not an absolute path: the shared world-sprite Prefab asset is
        // always saved under whichever AssetDatabase folder the caller owns (the real
        // ArchitecturalTileAssetFolder for Build(), or a caller-owned temporary folder for
        // tests), mirroring the existing caller-owned-folder pattern already used for
        // architectural Tile/Sprite/Texture assets below. This guarantees the persistence-aware
        // test seam never writes to the exact same AssetDatabase path Build() uses.
        private const string WorldSpritePrefabAssetFolderName = "WorldSprites";
        private const string WorldSpritePrefabAssetName = "WorldSpriteVisual.prefab";

        // This list is the ownership boundary for non-persistent architectural objects made by
        // the parameterless test seam. Persistent AssetDatabase objects are never added here.
        private static readonly List<Object> OwnedTransientArchitecturalObjects = new List<Object>();
        private static Scene ownedTransientArchitecturalScene;

        // AC-005: this facade only owns and clears the environment roots it directly builds
        // (floor, walls, door, isometric visuals). DoorPrototypeGlobalSceneBuilder owns and
        // clears its own global root names (camera, lighting, Player, UI, input) so each root
        // is cleared by the class that actually builds it instead of one shared implicit list.
        private static readonly string[] EnvironmentRootNames =
        {
            IsometricVisualGridName,
            "Floor",
            "Walls",
            "DoorRoot",
            FloorRunRestartControllerName,
            // Both are created fresh by every rebuild, so they must be cleared first or each
            // Build() leaves another copy behind - a second enemy squad dealing contact damage,
            // and two run-flow objects drawing the same overlay twice.
            DoorPrototypeGlobalSceneBuilder.EnemiesRootName,
            "DemoRunFlow",
            // Legacy root-level enemies from builds that predate the Enemies root. Without
            // these two names an earlier build's stale enemy survives every rebuild, keeps its
            // old spawn point, and has no wizard wired - the one that sat two units past D1.
            "MeleeEnemy",
            "FireCasterEnemy"
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
            DoorPrototypeGlobalSceneBuilder.ClearOwnedRoots(scene);

            DoorPrototypeGlobalSceneBuilder.BuildLighting();
            BuildFloor();

            var doorRoot = BuildDoor(out var door, architecturalTileAssetFolder);
            BuildWalls(doorRoot.transform.position);
            if (string.IsNullOrEmpty(architecturalTileAssetFolder))
            {
                ownedTransientArchitecturalScene = scene;
            }
            BuildIsometricVisualLayer(doorRoot.transform.position, architecturalTileAssetFolder);
            DoorSequenceBuilder.BuildCanonical(scene, doorRoot);

            // AC-001: the walkable NavMesh must bake from the composed gameplay collision
            // geometry (room FloorCollision/obstacle colliders), so this only runs once
            // DoorSequenceBuilder.BuildCanonical has actually materialized that composed
            // geometry into the canonical scene - the same path guard BuildCanonical itself
            // uses - rather than on every lightweight in-memory test scene this builder also
            // supports.
            if (scene.path == DoorSequenceBuilder.CanonicalScenePath)
            {
                BuildGameplayNavigation(scene);
            }

            DoorPrototypeGlobalSceneBuilder.BuildPlayer(
                out var movement,
                out var interactionController,
                out var health,
                out var debugControl,
                out var mana,
                out var debugManaControl,
                out var wizardAnimationController,
                out Transform playerSpawn,
                architecturalTileAssetFolder);

            DoorPrototypeGlobalSceneBuilder.BuildChaseEnemies(movement.transform, architecturalTileAssetFolder);

            var demoRunFlow = new GameObject("DemoRunFlow");
            demoRunFlow.AddComponent<DemoRunFlow>();

            // AC-002/VAL-006: DoorSequenceBuilder.BuildCanonical clones D2-D5 from this D1
            // instance before Player exists, so each clone's own DoorInteractionFeedback.Awake
            // ran with no PlayerMovement/PlayerInteractionController to find yet. Wire every
            // door's feedback component now that both exist, not only the original D1 door.
            foreach (var doorFeedback in Object.FindObjectsByType<DoorInteractionFeedback>(FindObjectsSortMode.None))
            {
                SetPrivateField(doorFeedback, "playerMovement", movement);
                SetPrivateField(doorFeedback, "interactionController", interactionController);
            }

            BuildFloorRunRestartController(health, mana, movement, interactionController);

            // BuildCamera reads followTarget.position immediately (not as a live reference)
            // to place the camera at its initial isometric framing, so BuildPlayer must run
            // first. If this ordering is ever changed, BuildCamera's null-target warning below
            // will fire rather than silently producing an unframed camera at the world origin.
            DoorPrototypeGlobalSceneBuilder.BuildCamera(movement.transform);

            DoorPrototypeGlobalSceneBuilder.BuildUI(
                door,
                debugControl,
                health,
                mana,
                debugManaControl,
                movement,
                interactionController,
                wizardAnimationController,
                playerSpawn);
        }

        private static void BuildFloorRunRestartController(
            PlayerHealth health,
            PlayerMana mana,
            PlayerMovement movement,
            PlayerInteractionController interactionController)
        {
            var restartObject = new GameObject(FloorRunRestartControllerName);
            restartObject.SetActive(false);
            var restartController = restartObject.AddComponent<FloorRunRestartController>();
            SetPrivateField(restartController, "playerHealth", health);
            SetPrivateField(restartController, "playerMana", mana);
            SetPrivateField(restartController, "playerMovement", movement);
            SetPrivateField(restartController, "playerInteractionController", interactionController);
            restartObject.SetActive(true);
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
                if (System.Array.IndexOf(EnvironmentRootNames, root.name) >= 0)
                {
                    Object.DestroyImmediate(root);
                }
            }
        }

        // Retained as the existing reflection-based test seam while the global facade owns
        // the camera root and its complete construction behavior.
        private static void BuildCamera(Transform followTarget)
        {
            DoorPrototypeGlobalSceneBuilder.BuildCamera(followTarget);
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

        // AC-001: creates the persistent builder-owned GameplayNavigation GameObject and bakes
        // its walkable NavMesh from the just-composed gameplay collision geometry. Rebuilding the
        // scene removes and recreates this exact GameObject deterministically rather than baking
        // onto a stale surviving instance from a prior Build().
        private static void BuildGameplayNavigation(Scene scene)
        {
            RemoveExistingGameplayNavigation(scene);

            var navigationRoot = new GameObject(GameplayNavigationRootName);
            SceneManager.MoveGameObjectToScene(navigationRoot, scene);

            // NSC-049 VAL-007/NSC-017 INT-003. Sealed is every door's construction-time state, so
            // this bake used to run with each door's solid DoorVisual collider and its doorway
            // blocker standing in the opening. That writes a PERMANENT hole across every doorway:
            // measured at D1, the doorway centre carried no walkable surface at all (nearest
            // 0.67 units away) and a BROKEN door still yielded only PathPartial, with its
            // NavMeshObstacle correctly not carving.
            //
            // It contradicts the design DoorEnemyPassability documents and that
            // DoorEnemyPassabilityPlayModeTests already proves green: bake ONE continuous
            // surface, then let the obstacle CARVE the hole at runtime while the door is sealed
            // or locked. That fixture builds its door AFTER its bake, which is the order this
            // builder cannot use because DoorSequenceBuilder clones D2-D5 from D1 during
            // composition. Suppressing the door's own blocking colliders for the duration of the
            // bake is the same thing without reordering composition.
            //
            // Sealed doors keep blocking enemies - that is the carving, not the bake, and it is
            // what the four SetDoorState_* passability tests assert.
            var suppressed = SuppressDoorBlockingColliders(scene);
            try
            {
                navigationRoot.AddComponent<GameplayNavigationSurface>().ConfigureAndBuild();
            }
            finally
            {
                foreach (var collider in suppressed)
                {
                    collider.enabled = true;
                }
            }
        }

        // Disables every enabled non-trigger collider owned by a door, returning exactly those it
        // changed so the caller restores the same set. Triggers are left alone: the arm's-reach
        // and forward-crossing volumes carry no navigation geometry and disabling them would
        // change door behaviour rather than the bake.
        private static List<Collider> SuppressDoorBlockingColliders(Scene scene)
        {
            var suppressed = new List<Collider>();

            foreach (var root in scene.GetRootGameObjects())
            {
                foreach (var door in root.GetComponentsInChildren<DoorInteractable>(true))
                {
                    foreach (var collider in door.GetComponentsInChildren<Collider>(true))
                    {
                        if (!collider.enabled || collider.isTrigger) continue;

                        collider.enabled = false;
                        suppressed.Add(collider);
                    }
                }
            }

            return suppressed;
        }

        private static void RemoveExistingGameplayNavigation(Scene scene)
        {
            foreach (var root in scene.GetRootGameObjects())
            {
                if (root.name != GameplayNavigationRootName) continue;

                var existingSurface = root.GetComponent<GameplayNavigationSurface>();
                if (existingSurface != null)
                {
                    existingSurface.ClearBakedData();
                }

                Object.DestroyImmediate(root);
            }
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
            // NSC-042 AC-001/AC-003: each gameplay wall spans three world units and is
            // painted as a repeated run of the same reusable one-cell wall Tile rather than
            // one long renderer or a uniquely authored asset per cell. PaintStraightWallRun
            // is the single place that repeats this convention, so a longer straight wall
            // (e.g. approximately 100 cells) is authored by widening wallRunCellCount, never
            // by adding more Tile/Sprite assets.
            const int wallRunCellCount = 3;
            PaintStraightWallRun(wallTilemap, tiles.Wall, 0, wallRunCellCount);
            PaintStraightWallRun(wallTilemap, tiles.Wall, 5, wallRunCellCount);

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

        // NSC-042 AC-001/AC-003: paints an odd-length run of one-cell wall segments centered
        // on centerCell along the existing x = -y wall diagonal, reusing the single supplied
        // wallTile for every cell. This is the one reusable convention both current doorway
        // walls call, so scaling straight-wall authoring to a much longer wall (tens or
        // approximately a hundred cells) means calling this with a larger cellCount instead of
        // hand-authoring more Tile/Sprite assets or duplicating the painting loop.
        private static void PaintStraightWallRun(
            Tilemap wallTilemap, TileBase wallTile, int centerCell, int cellCount)
        {
            var halfSpan = cellCount / 2;
            for (var offset = -halfSpan; offset <= halfSpan; offset++)
            {
                var cell = centerCell + offset;
                wallTilemap.SetTile(new Vector3Int(cell, -cell, 0), wallTile);
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

        // NSC-109 AC-001/AC-004: the committed art this generic demo layer's floor, wall and
        // architectural-border Tiles are bound to, instead of the procedurally generated diamond
        // and masonry textures this builder used before. The demo layer sits at D1's door, so it
        // reuses Ruined Entry's own committed floor and the shared full/low wall modules; it never
        // persists in the canonical scene (DoorSequenceBuilder.RemoveLegacyEnvironmentRoots
        // deletes it once the five real rooms are composed).
        private const string ArchitecturalFloorSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_RuinedEntry.png";
        private const string ArchitecturalWallSpriteSourcePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/wall_straight.png";

        private static ArchitecturalTileSet CreateArchitecturalTileSet(string assetFolder)
        {
            return new ArchitecturalTileSet(
                LoadOrCreateArchitecturalTile(
                    assetFolder, "FloorTile.asset", "FloorTile", ArchitecturalFloorSpriteSourcePath),
                LoadOrCreateArchitecturalTile(
                    assetFolder, "WallTile.asset", "WallTile", ArchitecturalWallSpriteSourcePath),
                LoadOrCreateArchitecturalTile(
                    assetFolder, "ArchitecturalBorderTile.asset", "ArchitecturalBorderTile",
                    ArchitecturalFloorSpriteSourcePath));
        }

        private static Tile LoadOrCreateArchitecturalTile(
            string assetFolder, string assetFileName, string tileName, string sourceSpritePath)
        {
            var sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourceSpritePath);
            if (sourceSprite == null)
            {
                throw new System.InvalidOperationException(
                    $"The Door Prototype scene requires the committed sprite at '{sourceSpritePath}'.");
            }

            if (!string.IsNullOrEmpty(assetFolder))
            {
                var assetPath = assetFolder + "/" + assetFileName;
                var existing = AssetDatabase.LoadAssetAtPath<Tile>(assetPath);

                if (existing != null)
                {
                    if (existing.sprite != sourceSprite || existing.colliderType != Tile.ColliderType.None)
                    {
                        existing.sprite = sourceSprite;
                        existing.colliderType = Tile.ColliderType.None;
                        EditorUtility.SetDirty(existing);
                        AssetDatabase.SaveAssetIfDirty(existing);
                    }
                    return existing;
                }

                var persistentTile = ScriptableObject.CreateInstance<Tile>();
                persistentTile.name = tileName;
                persistentTile.colliderType = Tile.ColliderType.None;
                persistentTile.sprite = sourceSprite;

                AssetDatabase.CreateAsset(persistentTile, assetPath);
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
            inMemoryTile.sprite = sourceSprite;

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

        internal static SpriteRenderer CreateWorldSpriteVisual(
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

        private static GameObject BuildDoor(out DoorInteractable door, string architecturalTileAssetFolder)
        {
            var doorRoot = new GameObject("DoorRoot");
            doorRoot.transform.position = Vector3.zero;

            var rangeTrigger = doorRoot.AddComponent<BoxCollider>();
            rangeTrigger.isTrigger = true;
            rangeTrigger.size = new Vector3(3f, 3f, 3f);
            rangeTrigger.center = new Vector3(0f, 1.5f, 0f);

            // AC-001: the doorway blocker's width is read back from this exact door's own
            // DoorEnemyPassability obstacle instead of being authored a second time. That
            // component already carries the authored opening width this doorway uses to carve
            // enemy NavMesh traversal, so deriving from it here means a later change to the
            // authored opening cannot silently reopen the jamb gap this task exists to close
            // (measured at HEAD: wall collision begins at +/-1.5 either side of centre while the
            // old hard-coded 2-unit blocker only reached +/-1.0, leaving open sightlines at both
            // jambs of every door).
            var doorEnemyPassability = doorRoot.AddComponent<DoorEnemyPassability>();
            var doorwayOpeningWidth = ResolveDoorwayOpeningWidth(doorEnemyPassability);

            const float visualLocalHeight = 1.25f;
            var visual = new GameObject("DoorVisual");
            visual.transform.SetParent(doorRoot.transform, false);
            visual.transform.localPosition = new Vector3(0f, visualLocalHeight, 0f);

            // Gameplay collision (the doorway blocker) stays a plain BoxCollider spanning the
            // full authored opening width - both jambs, not the door leaf's own art footprint -
            // kept separate from the SpriteRenderer visual child below so the visual can hold its
            // own authored orientation and non-uniform scale without shearing the collider.
            var doorwayBlocker = visual.AddComponent<BoxCollider>();
            doorwayBlocker.size = new Vector3(doorwayOpeningWidth, 2.5f, 0.3f);

            // DoorVisual itself stays elevated (visualLocalHeight) for the doorway-blocker
            // collider and ComputeGroundSelectionOffset's click math below, but the sprite's own
            // local position cancels that elevation back down to doorRoot's ground-contact
            // point, per the shared ground-contact sorting convention above.
            // Human-validated correction: the authored DoorSprite orientation is identity
            // (inspector 0,0,0), not a camera-facing billboard/tilt.
            var doorSprite = CreateDoorSpriteVisual(
                visual.transform,
                new Vector3(0f, -visualLocalHeight, 0f),
                architecturalTileAssetFolder,
                out var sealedSprite,
                out var lockedSprite,
                out var openSprite,
                out var finalSprite);

            door = doorRoot.AddComponent<DoorInteractable>();
            SetPrivateField(door, "doorVisual", visual);
            SetPrivateField(door, "doorwayBlocker", doorwayBlocker);
            SetPrivateFieldValue(door, "groundSelectionOffset", ComputeGroundSelectionOffset(visualLocalHeight));
            // The crossing volume starts clear of the doorway rather than on it, so entering it
            // means the wizard is already through. A volume that began at the doorway plane
            // locked the door while the wizard still stood in the opening.
            //
            // THE PREVIOUS VALUE (1.5, near face 1.0) FIXED THAT GROSS CASE BUT NOT THE
            // CAPSULE'S OWN DEPTH, and the comment above used to claim entering the volume
            // meant the wizard was already through. Measured at main b6cb952f2, it was not:
            //
            //     blocker forward face   +0.15   DoorVisual local Z 0, BoxCollider size.z 0.3
            //     player capsule radius   0.5    DoorPrototypeGlobalSceneBuilder.cs:257
            //     VAL-001 requires        1.15   blockerFace + 2 * radius
            //     near face was           1.0    SHORT BY 0.15
            //
            // At the old value the capsule spanned door-local Z [0.0, 1.0] when
            // CrossedForward fired while the blocker occupied [-0.15, +0.15], so CloseAndLock
            // re-enabled the blocker INSIDE the wizard. 1.75 puts the near face at 1.25.
            // Trigger depth stays 1.0, so no tunneling margin is given up to buy the
            // clearance. Keep this in step with DoorInteractable's own default.
            SetPrivateFieldValue(door, "forwardCrossingOffset", new Vector3(0f, 0f, 1.75f));
            SetPrivateFieldValue(door, "forwardCrossingTriggerSize", new Vector3(3f, 3f, 1f));
            door.BindEnemyPassability(doorEnemyPassability);

            // AC-001/AC-002/AC-003: gives the sealed door a base appearance distinguishable
            // from the plain-primitive walls plus hover/selected/opening feedback. The
            // player-side references (playerMovement/interactionController) are wired once
            // BuildPlayer creates them later in RebuildSceneContents.
            var feedback = doorRoot.AddComponent<DoorInteractionFeedback>();
            SetPrivateField(feedback, "door", door);
            SetPrivateField(feedback, "doorRenderer", visual.GetComponentInChildren<Renderer>());

            // AC-002: binds the approved bonestone door sprites to the state DoorInteractable's
            // own events express. Lives on doorRoot rather than visual, which DoorInteractable
            // deactivates while the door is open, so it keeps receiving Opened/Locked/
            // ResetCompleted and can re-enable visual before showing the open sprite.
            var doorSpriteBinder = doorRoot.AddComponent<DoorStateSpriteBinder>();
            SetPrivateField(doorSpriteBinder, "door", door);
            SetPrivateField(doorSpriteBinder, "doorVisual", visual);
            SetPrivateField(doorSpriteBinder, "spriteRenderer", doorSprite);
            SetPrivateField(doorSpriteBinder, "sealedSprite", sealedSprite);
            SetPrivateField(doorSpriteBinder, "lockedSprite", lockedSprite);
            SetPrivateField(doorSpriteBinder, "openSprite", openSprite);
            SetPrivateField(doorSpriteBinder, "finalSprite", finalSprite);

            BuildBreachFeedback(doorRoot, door, visual, doorSprite.transform);

            return doorRoot;
        }

        private static float ResolveDoorwayOpeningWidth(DoorEnemyPassability passability)
        {
            var field = typeof(DoorEnemyPassability).GetField(
                "obstacleSize", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
            return ((Vector3)field.GetValue(passability)).x;
        }

        // AC-002: the four DoorPassabilityState-reachable bonestone sprites, resolved by asset
        // path per Docs/Art/Doors/APPROVAL.md's bind list rather than any other naming rule.
        // damaged/opening/broken are deliberately not loaded here: no code path can reach them
        // yet (Docs/Art/Doors/APPROVAL.md).
        private const string DoorArtSourceFolder = "Assets/NoSafeCircle/DoorPrototype/Art/Doors/Source";
        private const string DoorSealedSpriteAssetName = "door_bonestone_sealed_S_000.png";
        private const string DoorLockedSpriteAssetName = "door_bonestone_locked_S_000.png";
        private const string DoorOpenSpriteAssetName = "door_bonestone_open_S_000.png";
        private const string DoorFinalSpriteAssetName = "door_bonestone_final_S_000.png";

        // AC-003: Vincent's approval 2026-09-17 (Docs/Art/Doors/APPROVAL.md) scales the existing
        // approved art rather than re-authoring it. The Art Director measured the sealed/open
        // sprites' painted opening at 1.00 x 1.30 world units against a 1.64-unit wizard; this
        // uniform scale lifts that opening to roughly 2.0 units, clearing the wizard with margin,
        // for zero additional PixelLab generations. GER Agent decision: if the resulting
        // proportion is later rejected, the remedy is a revision of AC-003, not a rebuild of this
        // binding.
        private const float DoorArtScale = 1.54f;

        private static SpriteRenderer CreateDoorSpriteVisual(
            Transform parent,
            Vector3 groundContactLocalPosition,
            string architecturalTileAssetFolder,
            out Sprite sealedSprite,
            out Sprite lockedSprite,
            out Sprite openSprite,
            out Sprite finalSprite)
        {
            var prefab = EnsureWorldSpritePrefab(architecturalTileAssetFolder);
            var spriteObject = string.IsNullOrEmpty(architecturalTileAssetFolder)
                ? Object.Instantiate(prefab)
                : (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            spriteObject.name = "DoorSprite";
            spriteObject.transform.SetParent(parent, false);
            spriteObject.transform.localPosition = groundContactLocalPosition;
            spriteObject.transform.localRotation = Quaternion.identity;
            spriteObject.transform.localScale = Vector3.one * DoorArtScale;

            sealedSprite = LoadDoorSprite(DoorSealedSpriteAssetName);
            lockedSprite = LoadDoorSprite(DoorLockedSpriteAssetName);
            openSprite = LoadDoorSprite(DoorOpenSpriteAssetName);
            finalSprite = LoadDoorSprite(DoorFinalSpriteAssetName);

            var renderer = spriteObject.GetComponent<SpriteRenderer>();
            // Sealed is every door's construction-time state - DoorSequenceBuilder assigns
            // isFinalDoor afterward, so the final-door skin is applied once this door actually
            // reaches a closed state through DoorStateSpriteBinder's Locked/ResetCompleted
            // handlers instead of being guessed here.
            renderer.sprite = sealedSprite;
            return renderer;
        }

        private static Sprite LoadDoorSprite(string assetFileName)
        {
            var path = DoorArtSourceFolder + "/" + assetFileName;
            var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
            if (sprite == null)
            {
                Debug.LogWarning($"Door sprite not found or not imported as a Sprite at '{path}'.");
            }
            return sprite;
        }

        private static void BuildBreachFeedback(GameObject doorRoot, DoorInteractable door, GameObject visual,
            Transform shakeTarget)
        {
            var root = new GameObject("DoorBreachFeedback");
            root.transform.SetParent(doorRoot.transform, false);
            var component = root.AddComponent<DoorBreachFeedback>();
            var bangAudio = root.AddComponent<AudioSource>();
            bangAudio.playOnAwake = false;
            bangAudio.spatialBlend = 0.8f;
            bangAudio.volume = 0.85f;

            var canvasObject = new GameObject("DurabilityIndicator", typeof(RectTransform), typeof(Canvas),
                typeof(CanvasScaler), typeof(GraphicRaycaster));
            canvasObject.transform.SetParent(root.transform, false);
            var canvas = canvasObject.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            canvas.sortingOrder = 10;
            canvasObject.transform.localPosition = new Vector3(0f, 2.8f, -0.2f);
            canvasObject.transform.localScale = Vector3.one * 0.01f;
            var canvasRect = canvasObject.GetComponent<RectTransform>();
            canvasRect.sizeDelta = new Vector2(220f, 24f);

            var backgroundObject = new GameObject("Background", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            backgroundObject.transform.SetParent(canvasObject.transform, false);
            var backgroundRect = backgroundObject.GetComponent<RectTransform>();
            backgroundRect.sizeDelta = canvasRect.sizeDelta;
            var background = backgroundObject.GetComponent<Image>();
            background.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            background.type = Image.Type.Sliced;
            background.color = new Color(0.08f, 0.03f, 0.03f, 0.9f);

            var fillObject = new GameObject("Fill", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            fillObject.transform.SetParent(backgroundObject.transform, false);
            var fillRect = fillObject.GetComponent<RectTransform>();
            fillRect.anchorMin = Vector2.zero;
            fillRect.anchorMax = Vector2.one;
            fillRect.offsetMin = new Vector2(3f, 3f);
            fillRect.offsetMax = new Vector2(-3f, -3f);
            var fill = fillObject.GetComponent<Image>();
            fill.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
            fill.type = Image.Type.Filled;
            fill.fillMethod = Image.FillMethod.Horizontal;
            fill.fillOrigin = (int)Image.OriginHorizontal.Left;
            fill.color = new Color(0.85f, 0.16f, 0.08f, 1f);

            var cracks = new GameObject[3];
            for (var i = 0; i < cracks.Length; i++)
            {
                var crack = GameObject.CreatePrimitive(PrimitiveType.Cube);
                crack.name = "CrackStage" + (i + 1);
                crack.transform.SetParent(visual.transform, false);
                crack.transform.localPosition = new Vector3(-0.45f + i * 0.45f, 0.15f + i * 0.2f, -0.18f);
                crack.transform.localRotation = Quaternion.Euler(0f, 0f, i % 2 == 0 ? 35f : -35f);
                crack.transform.localScale = new Vector3(0.06f, 0.55f, 0.03f);
                // Keep the authored world placement, then attach each crack to the
                // collider-free sprite so shaking never moves DoorVisual's blocker.
                crack.transform.SetParent(shakeTarget, true);
                var renderer = crack.GetComponent<Renderer>();
                renderer.sharedMaterial = new Material(Shader.Find("Standard")) { color = new Color(0.1f, 0.01f, 0.01f) };
                Object.DestroyImmediate(crack.GetComponent<Collider>());
                crack.SetActive(false);
                cracks[i] = crack;
            }

            // AddComponent invokes OnEnable before generated references are assigned, so use the
            // public binding seam to install event subscriptions and initialize the indicator.
            component.Bind(door, shakeTarget, fill, cracks, bangAudio, canvasObject);
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
            var forward = Quaternion.Euler(DoorPrototypeGlobalSceneBuilder.IsometricCameraEulerAngles) * Vector3.forward;
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

        internal static void SetPrivateField(Object target, string fieldName, Object value)
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
        internal static void SetPrivateFieldValue(object target, string fieldName, object value)
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
