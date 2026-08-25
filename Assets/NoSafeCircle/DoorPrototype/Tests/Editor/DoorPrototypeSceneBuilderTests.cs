using System.Collections.Generic;
using System.IO;
using System.Reflection;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.TestTools;
using UnityEngine.Tilemaps;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public class DoorPrototypeSceneBuilderTests
    {
        private const string CanonicalScenePath = "Assets/Scenes/DoorPrototype.unity";
        private string temporaryArchitecturalTileAssetFolder;

        [SetUp]
        public void SetUp()
        {
            temporaryArchitecturalTileAssetFolder =
                "Assets/__DoorPrototypeSceneBuilderTests_" + System.Guid.NewGuid().ToString("N");
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            if (!string.IsNullOrEmpty(temporaryArchitecturalTileAssetFolder) &&
                AssetDatabase.IsValidFolder(temporaryArchitecturalTileAssetFolder))
            {
                AssetDatabase.DeleteAsset(temporaryArchitecturalTileAssetFolder);
            }
        }

        [Test]
        public void Build_ProgressFillImage_HasSpriteAssignedSoFillAmountIsVisible()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var fillImage = GameObject.Find("Canvas/ProgressFill/Fill")?.GetComponent<Image>();

            Assert.IsNotNull(fillImage, "Expected a 'Fill' Image under Canvas/ProgressFill after building the scene.");
            Assert.IsNotNull(fillImage.sprite,
                "Progress fill Image has no sprite. A Filled Image with no sprite renders as a static full rect and ignores fillAmount.");
            Assert.AreEqual(Image.Type.Filled, fillImage.type);
            Assert.AreEqual(Image.FillMethod.Horizontal, fillImage.fillMethod);
        }

        [Test]
        public void Build_RunTwice_DoesNotDuplicateProgressFillHierarchy()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var canvas = GameObject.Find("Canvas");
            var progressFillCount = 0;
            foreach (Transform child in canvas.transform)
            {
                if (child.name == "ProgressFill") progressFillCount++;
            }

            Assert.AreEqual(1, progressFillCount,
                "Re-running the scene builder must not duplicate the ProgressFill UI element.");
        }

        // AC-003: continuous player-facing health indicator must actually be wired into the
        // canonical scene builder output, mirroring the door's ProgressFill visibility fix.
        [Test]
        public void Build_HealthFillImage_HasSpriteAssignedSoFillAmountIsVisible()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var fillImage = GameObject.Find("Canvas/HealthFill/Fill")?.GetComponent<Image>();

            Assert.IsNotNull(fillImage, "Expected a 'Fill' Image under Canvas/HealthFill after building the scene.");
            Assert.IsNotNull(fillImage.sprite,
                "Health fill Image has no sprite. A Filled Image with no sprite renders as a static full rect and ignores fillAmount.");
            Assert.AreEqual(Image.Type.Filled, fillImage.type);
            Assert.AreEqual(Image.FillMethod.Horizontal, fillImage.fillMethod);
        }

        // AC-003: the health indicator must be bound to the same PlayerHealth instance carried
        // by the generated Player, not a stray/unwired component, so it reflects real state.
        [Test]
        public void Build_PlayerHealthUI_WiredToPlayerHealthAndFillImage()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var healthUi = GameObject.Find("Canvas")?.GetComponent<PlayerHealthUI>();
            Assert.IsNotNull(healthUi, "Expected a PlayerHealthUI component on the generated Canvas.");

            var playerHealth = GameObject.Find("Player")?.GetComponent<PlayerHealth>();
            Assert.IsNotNull(playerHealth, "Expected a PlayerHealth component on the generated Player.");

            var fillImage = GameObject.Find("Canvas/HealthFill/Fill")?.GetComponent<Image>();
            Assert.IsNotNull(fillImage, "Expected a 'Fill' Image under Canvas/HealthFill after building the scene.");

            var serializedUi = new SerializedObject(healthUi);
            Assert.AreEqual(playerHealth, serializedUi.FindProperty("health").objectReferenceValue,
                "PlayerHealthUI must be wired to the same PlayerHealth instance carried by the generated Player.");
            Assert.AreEqual(fillImage, serializedUi.FindProperty("fillImage").objectReferenceValue,
                "PlayerHealthUI must be wired to the generated HealthFill/Fill Image.");
        }

        [Test]
        public void Build_RunTwice_DoesNotDuplicateHealthFillHierarchy()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var canvas = GameObject.Find("Canvas");
            var healthFillCount = 0;
            foreach (Transform child in canvas.transform)
            {
                if (child.name == "HealthFill") healthFillCount++;
            }

            Assert.AreEqual(1, healthFillCount,
                "Re-running the scene builder must not duplicate the HealthFill UI element.");

            var healthUiComponents = canvas.GetComponents<PlayerHealthUI>();
            Assert.AreEqual(1, healthUiComponents.Length,
                "Re-running the scene builder must not duplicate the PlayerHealthUI binding.");
        }
        // AC-003: the health indicator must stay visible/readable at all times. Give it a
        // dedicated center-screen vertical lane above the interaction prompt rather than
        // merely requiring a numerically different anchor from the other bars.
        [Test]
        public void Build_HealthFill_UsesDedicatedVerticalLaneAboveInteractionPrompt()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var healthRect = GameObject.Find("Canvas/HealthFill")?.GetComponent<RectTransform>();
            var promptRect = GameObject.Find("Canvas/InteractPrompt")?.GetComponent<RectTransform>();
            var progressRect = GameObject.Find("Canvas/ProgressFill")?.GetComponent<RectTransform>();
            var manaRect = GameObject.Find("Canvas/ManaFill")?.GetComponent<RectTransform>();

            Assert.IsNotNull(healthRect, "Expected a 'HealthFill' RectTransform directly under Canvas.");
            Assert.IsNotNull(promptRect, "Expected an 'InteractPrompt' RectTransform directly under Canvas.");
            Assert.IsNotNull(progressRect, "Expected a 'ProgressFill' RectTransform directly under Canvas.");
            Assert.IsNotNull(manaRect, "Expected a 'ManaFill' RectTransform directly under Canvas.");

            Assert.GreaterOrEqual(
                healthRect.anchorMin.y - promptRect.anchorMax.y,
                0.049f,
                "Health indicator must have a dedicated normalized vertical lane above the interaction prompt.");

            Assert.Greater(healthRect.anchorMin.y, progressRect.anchorMin.y,
                "Health indicator must remain above the door progress bar.");
            Assert.Greater(healthRect.anchorMin.y, manaRect.anchorMin.y,
                "Health indicator must remain above the mana indicator.");
        }
[Test]
        public void Build_ControlsHud_ExistsSeparateFromPromptAndProgressIndicator()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var hud = GameObject.Find("Canvas/ControlsHud");
            Assert.IsNotNull(hud, "Expected a 'ControlsHud' object directly under Canvas.");

            var prompt = GameObject.Find("Canvas/InteractPrompt");
            var progress = GameObject.Find("Canvas/ProgressFill");
            Assert.AreNotEqual(hud, prompt, "Controls HUD must be a separate object from the interaction prompt.");
            Assert.AreNotEqual(hud, progress, "Controls HUD must be a separate object from the progress indicator.");
        }

        [Test]
        public void Build_ControlsHud_TextMatchesActualImplementedControls()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var hudText = GameObject.Find("Canvas/ControlsHud/Text")?.GetComponent<Text>();
            Assert.IsNotNull(hudText, "Expected a 'Text' element under Canvas/ControlsHud.");
            StringAssert.Contains("Click/Hold Left Mouse", hudText.text);
            StringAssert.Contains("Move", hudText.text);
            // AC-001/AC-002: door interaction is click-to-approach with an automatic timer, not
            // a sustained key hold; the HUD text must reflect that current interaction model.
            StringAssert.Contains("Click Sealed Door", hudText.text);
            StringAssert.DoesNotContain("Hold E", hudText.text,
                "HUD text must not describe the superseded sustained-hold interaction model.");
            StringAssert.Contains("cancels the opening attempt", hudText.text);

            var debugControl = GameObject.Find("Player")?.GetComponent<DebugDamageControl>();
            Assert.IsNotNull(debugControl, "Expected a DebugDamageControl on the generated Player.");
            var damageKey = (Key)new SerializedObject(debugControl).FindProperty("damageKey").enumValueIndex;
            StringAssert.Contains(damageKey.ToString(), hudText.text,
                "Displayed debug key must match the actual implemented damage-test key binding.");
            StringAssert.Contains("Debug", hudText.text,
                "The damage-test key must be clearly labeled as debug/test, not a normal gameplay ability.");
        }

        [Test]
        public void Build_RunTwice_DoesNotDuplicateControlsHud()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var canvas = GameObject.Find("Canvas");
            var hudCount = 0;
            foreach (Transform child in canvas.transform)
            {
                if (child.name == "ControlsHud") hudCount++;
            }

            Assert.AreEqual(1, hudCount, "Re-running the scene builder must not duplicate the ControlsHud panel.");
        }

        [Test]
        public void Build_MainCamera_IsFixedOrthographicIsometric()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();
            Assert.IsNotNull(camera, "Expected a 'Main Camera' with a Camera component.");

            Assert.IsTrue(camera.orthographic,
                "Camera must be orthographic for the GDD's fixed 2.5D isometric presentation, not perspective.");
            Assert.Greater(camera.orthographicSize, 0f);

            var expectedRotation = Quaternion.Euler(30f, -45f, 0f);
            Assert.Less(Quaternion.Angle(expectedRotation, camera.transform.rotation), 0.01f,
                "Camera rotation must match the fixed isometric angle and not the old perspective test angle.");

            var noRotationComponents = camera.GetComponentsInParent<Behaviour>();
            foreach (var behaviour in noRotationComponents)
            {
                Assert.IsFalse(behaviour.GetType().Name.Contains("Rotate") || behaviour.GetType().Name.Contains("Orbit"),
                    "Main Camera must not have any free-rotation/orbit component attached; the isometric view is fixed.");
            }
        }

        [Test]
        public void Build_RunTwice_MainCameraStaysSingleAndFixed()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var cameras = Object.FindObjectsByType<Camera>(FindObjectsSortMode.None);
            Assert.AreEqual(1, cameras.Length, "Re-running the scene builder must not duplicate the Main Camera.");
            Assert.IsTrue(cameras[0].orthographic);
        }

        [Test]
        public void Build_MainCamera_FramesPlayerAndStartingDoorInView()
        {
            // Camera.forward pointing exactly at the player is not itself a meaningful framing
            // check - a camera can satisfy that and still be positioned on the wrong side, or
            // frame the gameplay space badly. What actually matters is that the player and the
            // starting door both land comfortably inside the camera's viewport.
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();
            var player = GameObject.Find("Player");
            var door = GameObject.Find("DoorRoot");
            Assert.IsNotNull(camera);
            Assert.IsNotNull(player);
            Assert.IsNotNull(door);

            var playerViewport = camera.WorldToViewportPoint(player.transform.position);
            var doorViewport = camera.WorldToViewportPoint(door.transform.position);

            Assert.IsTrue(playerViewport.x > 0.1f && playerViewport.x < 0.9f
                          && playerViewport.y > 0.1f && playerViewport.y < 0.9f && playerViewport.z > 0f,
                $"Player must be comfortably inside the camera view at scene start, was viewport {playerViewport}.");
            Assert.IsTrue(doorViewport.x > 0.1f && doorViewport.x < 0.9f
                          && doorViewport.y > 0.1f && doorViewport.y < 0.9f && doorViewport.z > 0f,
                $"Starting door must be comfortably inside the camera view at scene start, was viewport {doorViewport}.");
        }

        [Test]
        public void Build_MainCamera_HasFollowComponentTargetingPlayer()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var camera = GameObject.Find("Main Camera");
            var follow = camera?.GetComponent<IsometricCameraFollow>();
            Assert.IsNotNull(follow,
                "Expected an IsometricCameraFollow component on the Main Camera so it tracks the player instead of staying static.");

            var target = new SerializedObject(follow).FindProperty("target").objectReferenceValue as Transform;
            Assert.IsNotNull(target, "IsometricCameraFollow.target must be wired up by the scene builder.");
            Assert.AreEqual("Player", target.name);
        }

        [Test]
        public void Build_MainCamera_TranslatesWithPlayerButRotationStaysFixed()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var cameraObject = GameObject.Find("Main Camera");
            var player = GameObject.Find("Player");
            var follow = cameraObject.GetComponent<IsometricCameraFollow>();

            var rotationBefore = cameraObject.transform.rotation;
            var offsetBefore = cameraObject.transform.position - player.transform.position;

            player.transform.position += new Vector3(5f, 0f, 3f);

            var lateUpdate = typeof(IsometricCameraFollow).GetMethod("LateUpdate",
                BindingFlags.NonPublic | BindingFlags.Instance);
            lateUpdate.Invoke(follow, null);

            Assert.AreEqual(offsetBefore, cameraObject.transform.position - player.transform.position,
                "Camera must keep the same relative offset while translating to follow the player, so the " +
                "gameplay area stays framed as the player moves.");
            Assert.AreEqual(rotationBefore, cameraObject.transform.rotation,
                "Camera rotation must never change while following the player - the isometric orientation is " +
                "fixed and there is no free player-controlled rotation.");
        }

        [Test]
        public void BuildCamera_NullFollowTarget_LogsWarningInsteadOfSilentlyMisframing()
        {
            // BuildCamera's initial placement depends on Build() calling BuildPlayer() first so a
            // real follow target exists. This locks in the fallback: if that ordering is ever
            // broken, BuildCamera must warn rather than silently place the camera at the world
            // origin with no indication the framing requirement was violated.
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var buildCamera = typeof(DoorPrototypeSceneBuilder).GetMethod("BuildCamera",
                BindingFlags.NonPublic | BindingFlags.Static);
            Assert.IsNotNull(buildCamera, "Expected a private static BuildCamera(Transform) method.");

            // Isolate from any "Main Camera" left over by other tests in this run, since this
            // test invokes BuildCamera directly rather than through Build()'s scene clearing.
            var existingCamera = GameObject.Find("Main Camera");
            if (existingCamera != null) Object.DestroyImmediate(existingCamera);

            LogAssert.Expect(LogType.Warning, new System.Text.RegularExpressions.Regex("null follow target"));

            buildCamera.Invoke(null, new object[] { null });

            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();
            Assert.IsNotNull(camera, "BuildCamera must still create a Main Camera even without a follow target.");
            Assert.IsTrue(camera.orthographic);
        }

        // NSC-038 AC-001: floors, walls, and repeatable architectural art are distinct
        // visual-only layers on an isometric Tilemap grid.
        [Test]
        public void Build_IsometricVisualLayer_HasFloorWallAndRepeatableArchitectureTilemaps()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            var grid = GameObject.Find("IsometricVisualGrid")?.GetComponent<Grid>();
            Assert.IsNotNull(grid, "Expected the generated isometric visual Grid.");
            Assert.AreEqual(GridLayout.CellLayout.IsometricZAsY, grid.cellLayout);
            Assert.That(grid.cellSize.x / grid.cellSize.y, Is.EqualTo(2f).Within(0.0001f));

            var floorTilemap = GetVisualTilemap(grid, "FloorTilemap");
            var wallTilemap = GetVisualTilemap(grid, "WallTilemap");
            var architecturalTilemap = GetVisualTilemap(grid, "ArchitecturalTilemap");

            Assert.Greater(CountOccupiedCells(floorTilemap), 1);
            Assert.AreEqual(2, CountOccupiedCells(wallTilemap));
            Assert.Greater(CountOccupiedCells(architecturalTilemap), 1);

            AssertVisualLayerHierarchyHasNoGameplayOwnership(grid);
            AssertVisualOnly(floorTilemap);
            AssertVisualOnly(wallTilemap);
            AssertVisualOnly(architecturalTilemap);
        }

        // NSC-038 AC-001: reusable architectural Tile assets remain visual data and own their
        // generated Sprite and Texture subassets in the caller-owned temporary folder.
        [Test]
        public void Build_PersistentArchitecturalTiles_AreTemporaryReusableVisualOnlyAssets()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            var grid = GameObject.Find("IsometricVisualGrid")?.GetComponent<Grid>();
            Assert.IsNotNull(grid);

            var tiles = new[]
            {
                GetFirstTile(GetVisualTilemap(grid, "FloorTilemap")),
                GetFirstTile(GetVisualTilemap(grid, "WallTilemap")),
                GetFirstTile(GetVisualTilemap(grid, "ArchitecturalTilemap"))
            };

            CollectionAssert.AllItemsAreNotNull(tiles);
            CollectionAssert.AllItemsAreUnique(tiles);

            foreach (var tile in tiles)
            {
                Assert.AreEqual(Tile.ColliderType.None, tile.colliderType);
                Assert.IsTrue(AssetDatabase.Contains(tile));
                StringAssert.StartsWith(temporaryArchitecturalTileAssetFolder + "/",
                    AssetDatabase.GetAssetPath(tile));
                Assert.IsNotNull(tile.sprite);
                Assert.IsNotNull(tile.sprite.texture);
                Assert.AreEqual(AssetDatabase.GetAssetPath(tile), AssetDatabase.GetAssetPath(tile.sprite));
                Assert.AreEqual(AssetDatabase.GetAssetPath(tile), AssetDatabase.GetAssetPath(tile.sprite.texture));
            }
        }

        // NSC-038 VAL-001: compare the effective floor visual in world space to the separately
        // authored gameplay Plane, covering coordinate, footprint, offset, and orientation.
        [Test]
        public void Build_FloorTilemapVisual_AlignsWithIndependentGameplayFloorInWorldSpace()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);
            Physics.SyncTransforms();

            var floorCollider = GameObject.Find("Floor")?.GetComponent<Collider>();
            var floorTilemap = GameObject.Find("IsometricVisualGrid/FloorTilemap")?.GetComponent<Tilemap>();
            Assert.IsNotNull(floorCollider);
            Assert.IsNotNull(floorTilemap);

            var visualBounds = CalculateEffectiveWorldVisualBounds(floorTilemap);
            var gameplayBounds = floorCollider.bounds;

            Assert.That(visualBounds.center.x, Is.EqualTo(gameplayBounds.center.x).Within(0.001f));
            Assert.That(visualBounds.center.z, Is.EqualTo(gameplayBounds.center.z).Within(0.001f));
            Assert.That(visualBounds.size.x, Is.EqualTo(gameplayBounds.size.x).Within(0.001f));
            Assert.That(visualBounds.size.z, Is.EqualTo(gameplayBounds.size.z).Within(0.001f));
            Assert.That(visualBounds.center.y - gameplayBounds.max.y, Is.EqualTo(0.01f).Within(0.0001f));
            Assert.That(Vector3.Angle(floorTilemap.transform.TransformDirection(Vector3.forward), Vector3.up),
                Is.LessThan(0.01f));
        }

        // NSC-038 VAL-001: validate each wall independently so symmetric drift cannot be hidden
        // by a combined bound.
        [Test]
        public void Build_WallTilemapVisuals_AlignWithIndependentGameplayWallsInWorldSpace()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);
            Physics.SyncTransforms();

            var wallTilemap = GameObject.Find("IsometricVisualGrid/WallTilemap")?.GetComponent<Tilemap>();
            var leftWall = GameObject.Find("Walls/WallLeft")?.GetComponent<Collider>();
            var rightWall = GameObject.Find("Walls/WallRight")?.GetComponent<Collider>();
            Assert.IsNotNull(wallTilemap);
            Assert.IsNotNull(leftWall);
            Assert.IsNotNull(rightWall);

            var visualBounds = CalculateEffectiveWorldVisualBoundsByCell(wallTilemap);
            Assert.AreEqual(2, visualBounds.Count);
            visualBounds.Sort((first, second) => first.center.x.CompareTo(second.center.x));

            AssertWallVisualAlignsWithGameplayWall(visualBounds[0], leftWall.bounds, "left");
            AssertWallVisualAlignsWithGameplayWall(visualBounds[1], rightWall.bounds, "right");
            Assert.That(Vector3.Angle(wallTilemap.transform.TransformDirection(Vector3.forward), Vector3.forward),
                Is.LessThan(0.01f));
        }

        // NSC-038 regression-only invariant: repairing generated Tiles must save only those
        // assets, leaving unrelated dirty project assets untouched.
        [Test]
        public void Build_PersistentArchitecturalTiles_DoesNotSaveUnrelatedDirtyAsset()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            var floorTilePath = temporaryArchitecturalTileAssetFolder + "/FloorTile.asset";
            var floorTile = AssetDatabase.LoadAssetAtPath<Tile>(floorTilePath);
            Assert.IsNotNull(floorTile);
            floorTile.colliderType = Tile.ColliderType.Grid;
            EditorUtility.SetDirty(floorTile);

            var unrelatedPath = temporaryArchitecturalTileAssetFolder + "/UnrelatedTile.asset";
            var unrelatedTile = ScriptableObject.CreateInstance<Tile>();
            AssetDatabase.CreateAsset(unrelatedTile, unrelatedPath);
            AssetDatabase.SaveAssetIfDirty(unrelatedTile);
            unrelatedTile.colliderType = Tile.ColliderType.Sprite;
            EditorUtility.SetDirty(unrelatedTile);

            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            Assert.AreEqual(Tile.ColliderType.None, floorTile.colliderType);
            Assert.IsFalse(EditorUtility.IsDirty(floorTile),
                "The repaired existing architectural Tile must be saved asset-specifically.");
            Assert.IsTrue(EditorUtility.IsDirty(unrelatedTile),
                "The builder must not globally save an unrelated dirty asset.");
        }

        // NSC-038 regression-only invariant: rebuilding the parameterless seam destroys the
        // exact transient Tile/Sprite/Texture instances owned by the prior build.
        [Test]
        public void BuildInMemory_TransientArchitecturalObjects_AreDestroyedOnRebuild()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            var oldTiles = GetArchitecturalTilesFromActiveGrid();
            var oldSprites = new Sprite[oldTiles.Length];
            var oldTextures = new Texture2D[oldTiles.Length];
            for (var i = 0; i < oldTiles.Length; i++)
            {
                oldSprites[i] = oldTiles[i].sprite;
                oldTextures[i] = oldSprites[i].texture;
            }

            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            for (var i = 0; i < oldTiles.Length; i++)
            {
                Assert.IsTrue(oldTiles[i] == null,
                    $"Previous transient Tile {i} must be destroyed before rebuilding.");
                Assert.IsTrue(oldSprites[i] == null,
                    $"Previous transient Sprite {i} must be destroyed before rebuilding.");
                Assert.IsTrue(oldTextures[i] == null,
                    $"Previous transient Texture {i} must be destroyed before rebuilding.");
            }

            foreach (var replacementTile in GetArchitecturalTilesFromActiveGrid())
            {
                Assert.IsNotNull(replacementTile);
                Assert.IsFalse(AssetDatabase.Contains(replacementTile));
            }
        }

        // NSC-038 regression-only invariant: closing/replacing the in-memory test scene cleans
        // the final transient build even when no subsequent builder invocation occurs.
        [Test]
        public void BuildInMemory_TransientArchitecturalObjects_AreDestroyedOnSceneReplacement()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            var tiles = GetArchitecturalTilesFromActiveGrid();
            var sprites = new Sprite[tiles.Length];
            var textures = new Texture2D[tiles.Length];
            for (var i = 0; i < tiles.Length; i++)
            {
                sprites[i] = tiles[i].sprite;
                textures[i] = sprites[i].texture;
            }

            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            for (var i = 0; i < tiles.Length; i++)
            {
                Assert.IsTrue(tiles[i] == null,
                    $"Transient Tile {i} must be destroyed when its test scene closes.");
                Assert.IsTrue(sprites[i] == null,
                    $"Transient Sprite {i} must be destroyed when its test scene closes.");
                Assert.IsTrue(textures[i] == null,
                    $"Transient Texture {i} must be destroyed when its test scene closes.");
            }
        }

        [Test]
        public void BuildInMemory_CanonicalSceneBytesRemainUnchanged()
        {
            var bytesBefore = File.ReadAllBytes(CanonicalScenePath);

            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            CollectionAssert.AreEqual(bytesBefore, File.ReadAllBytes(CanonicalScenePath));
            Assert.IsEmpty(UnityEngine.SceneManagement.SceneManager.GetActiveScene().path);
        }

        private static Tilemap GetVisualTilemap(Grid grid, string childName)
        {
            Assert.IsNotNull(grid);
            var child = grid.transform.Find(childName);
            Assert.IsNotNull(child, $"Expected visual layer '{childName}' directly under the isometric Grid.");

            var tilemap = child.GetComponent<Tilemap>();
            Assert.IsNotNull(tilemap);
            Assert.IsNotNull(child.GetComponent<TilemapRenderer>());
            return tilemap;
        }

        private static int CountOccupiedCells(Tilemap tilemap)
        {
            var count = 0;
            foreach (var position in tilemap.cellBounds.allPositionsWithin)
            {
                if (tilemap.HasTile(position)) count++;
            }

            return count;
        }

        private static Tile GetFirstTile(Tilemap tilemap)
        {
            foreach (var position in tilemap.cellBounds.allPositionsWithin)
            {
                var tile = tilemap.GetTile<Tile>(position);
                if (tile != null) return tile;
            }

            return null;
        }

        private static Tile[] GetArchitecturalTilesFromActiveGrid()
        {
            var grid = GameObject.Find("IsometricVisualGrid")?.GetComponent<Grid>();
            Assert.IsNotNull(grid);
            return new[]
            {
                GetFirstTile(GetVisualTilemap(grid, "FloorTilemap")),
                GetFirstTile(GetVisualTilemap(grid, "WallTilemap")),
                GetFirstTile(GetVisualTilemap(grid, "ArchitecturalTilemap"))
            };
        }

        private static void AssertVisualOnly(Tilemap tilemap)
        {
            Assert.IsNull(tilemap.GetComponent<Collider>());
            Assert.IsNull(tilemap.GetComponent<Collider2D>());
            Assert.IsEmpty(tilemap.GetComponents<MonoBehaviour>());

            foreach (var position in tilemap.cellBounds.allPositionsWithin)
            {
                var tile = tilemap.GetTile<Tile>(position);
                if (tile != null)
                {
                    Assert.AreEqual(Tile.ColliderType.None, tile.colliderType);
                }
            }
        }

        private static void AssertVisualLayerHierarchyHasNoGameplayOwnership(Grid grid)
        {
            Assert.IsEmpty(grid.GetComponentsInChildren<Collider>(true));
            Assert.IsEmpty(grid.GetComponentsInChildren<Collider2D>(true));
            Assert.IsEmpty(grid.GetComponentsInChildren<MonoBehaviour>(true));
        }

        private static Bounds CalculateEffectiveWorldVisualBounds(Tilemap tilemap)
        {
            var cellBounds = CalculateEffectiveWorldVisualBoundsByCell(tilemap);
            Assert.IsNotEmpty(cellBounds);

            var result = cellBounds[0];
            for (var i = 1; i < cellBounds.Count; i++)
            {
                result.Encapsulate(cellBounds[i]);
            }

            return result;
        }

        private static List<Bounds> CalculateEffectiveWorldVisualBoundsByCell(Tilemap tilemap)
        {
            var result = new List<Bounds>();

            foreach (var position in tilemap.cellBounds.allPositionsWithin)
            {
                var tile = tilemap.GetTile<Tile>(position);
                if (tile == null || tile.sprite == null) continue;

                var spriteBounds = tile.sprite.bounds;
                var tileTransform = tilemap.GetTransformMatrix(position);
                var tileAnchorWorld = tilemap.GetCellCenterWorld(position);
                var hasPoint = false;
                var cellVisualBounds = new Bounds();

                for (var xSign = -1; xSign <= 1; xSign += 2)
                {
                    for (var ySign = -1; ySign <= 1; ySign += 2)
                    {
                        var spritePoint = spriteBounds.center + new Vector3(
                            spriteBounds.extents.x * xSign,
                            spriteBounds.extents.y * ySign,
                            0f);
                        var tileLocalPoint = tileTransform.MultiplyPoint3x4(spritePoint);
                        var worldPoint = tileAnchorWorld + tilemap.transform.TransformVector(tileLocalPoint);

                        if (!hasPoint)
                        {
                            cellVisualBounds = new Bounds(worldPoint, Vector3.zero);
                            hasPoint = true;
                        }
                        else
                        {
                            cellVisualBounds.Encapsulate(worldPoint);
                        }
                    }
                }

                Assert.IsTrue(hasPoint);
                result.Add(cellVisualBounds);
            }

            return result;
        }

        private static void AssertWallVisualAlignsWithGameplayWall(
            Bounds visualBounds,
            Bounds gameplayBounds,
            string wallLabel)
        {
            Assert.That(visualBounds.center.x, Is.EqualTo(gameplayBounds.center.x).Within(0.001f), wallLabel);
            Assert.That(visualBounds.center.y, Is.EqualTo(gameplayBounds.center.y).Within(0.001f), wallLabel);
            Assert.That(visualBounds.size.x, Is.EqualTo(gameplayBounds.size.x).Within(0.001f), wallLabel);
            Assert.That(visualBounds.size.y, Is.EqualTo(gameplayBounds.size.y).Within(0.001f), wallLabel);
            Assert.That(visualBounds.center.z - gameplayBounds.min.z,
                Is.EqualTo(-0.001f).Within(0.0001f), wallLabel);
        }
    }

    // Human-review regression (item 2): the previous door-selection tests aimed at
    // WorldToScreenPoint(door.transform.position) - the ground anchor, not the visible door -
    // which does not represent an actual player click on the sealed door under the production
    // fixed isometric camera. This builds the real scene, clicks through the built DoorVisual's
    // world center under the real built Main Camera, drives that click through a live
    // PlayerMovement instance so the ground point is produced by the same shared projection
    // consumers rely on (AC-001), and proves the door is selected through
    // PlayerInteractionController.TryBeginDoorApproach.
    public class DoorPrototypeSceneBuilderClickSelectionTests : InputTestFixture
    {
        private Mouse mouseDevice;
        private RenderTexture testRenderTexture;

        public override void Setup()
        {
            base.Setup();
            mouseDevice = InputSystem.AddDevice<Mouse>();
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        public override void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                Object.Destroy(testRenderTexture);
                testRenderTexture = null;
            }

            mouseDevice = null;
            base.TearDown();
        }

        [Test]
        public void Build_ClickingVisibleDoorCenterUnderProductionCamera_SelectsDoorThroughSharedPointerTarget()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var playerObject = GameObject.Find("Player");
            var movement = playerObject != null ? playerObject.GetComponent<PlayerMovement>() : null;
            var interactionController =
                playerObject != null ? playerObject.GetComponent<PlayerInteractionController>() : null;
            var door = GameObject.Find("DoorRoot")?.GetComponent<DoorInteractable>();
            var doorVisual = GameObject.Find("DoorRoot/DoorVisual");
            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();

            Assert.IsNotNull(movement, "Expected a PlayerMovement on the generated Player.");
            Assert.IsNotNull(interactionController,
                "Expected a PlayerInteractionController on the generated Player.");
            Assert.IsNotNull(door, "Expected a DoorInteractable on the generated DoorRoot.");
            Assert.IsNotNull(doorVisual, "Expected a DoorVisual child under DoorRoot.");
            Assert.IsNotNull(camera, "Expected a Camera on the generated Main Camera.");

            // Batch mode has no interactive Game View; give the built camera a fixed pixel
            // surface so WorldToScreenPoint/ScreenPointToRay are deterministic here too.
            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
            camera.targetTexture = testRenderTexture;

            // EditMode tests do not invoke MonoBehaviour Awake/OnEnable automatically; invoke
            // them explicitly so the built components are wired the same way they would be at
            // runtime before driving a real click through them. Unity's engine does not track
            // these as "live" components in Edit Mode (they were never enabled through the
            // normal engine path), so OnEnable's InputAction.Enable() calls must be matched with
            // an explicit OnDisable in this test rather than relying on scene teardown to release
            // them from the real, session-shared project InputActionAsset.
            InvokePrivate(movement, "Awake");
            InvokePrivate(movement, "OnEnable");
            InvokePrivate(interactionController, "Awake");
            InvokePrivate(interactionController, "OnEnable");
            InvokePrivate(door, "OnEnable");

            try
            {
                var screenPoint = camera.WorldToScreenPoint(doorVisual.transform.position);
                SetMouse(screenPoint, true);

                movement.Tick(0.02f);

                Assert.IsTrue(movement.HasPointerWorldTarget,
                    "Expected PlayerMovement to have produced a shared world-space pointer target for this " +
                    "click.");
                Assert.IsTrue(interactionController.HasLockedDoorInteraction,
                    "Clicking through the visible door's visual center under the production camera must " +
                    "select the sealed door via the shared PlayerMovement pointer target, not merely near " +
                    "its ground anchor.");
                Assert.AreSame(door, interactionController.PendingDoor);
            }
            finally
            {
                InvokePrivate(door, "OnDisable");
                InvokePrivate(movement, "OnDisable");
            }
        }

        private void SetMouse(Vector2 screenPosition, bool leftButtonPressed)
        {
            InputSystem.QueueStateEvent(mouseDevice, new MouseState
            {
                position = screenPosition,
                buttons = leftButtonPressed ? (ushort)(1 << (int)MouseButton.Left) : (ushort)0
            });
            InputSystem.Update();
        }

        private static void InvokePrivate(object target, string methodName)
        {
            var method = target.GetType().GetMethod(methodName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(method, $"Expected a private method named '{methodName}' on {target.GetType().Name}.");
            method.Invoke(target, null);
        }
    }
}
