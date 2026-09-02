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

        // NSC-039 AC-001 (human-review correction, item 1 follow-up): the shared world-sprite
        // Prefab asset is saved under the caller-owned folder's own "WorldSprites" subfolder
        // (see DoorPrototypeSceneBuilder.WorldSpritePrefabAssetFolderName), never at a fixed
        // AssetDatabase path shared with the production Build() command. The persistence-aware
        // test seam below therefore only ever writes under temporaryArchitecturalTileAssetFolder,
        // whose own cleanup already covers the prefab subfolder recursively; no separate
        // fixed-path cleanup is required or correct here.
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

        // NSC-041 AC-001/AC-002/AC-003/AC-005: the sealed door's feedback component must
        // actually be wired into the built scene, referencing the same door, door renderer,
        // and player-side references (PlayerMovement's shared pointer target, and
        // PlayerInteractionController's accepted-selection state) it consumes at runtime.
        [Test]
        public void Build_DoorInteractionFeedback_IsWiredToDoorRendererAndPlayerReferences()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var doorRoot = GameObject.Find("DoorRoot");
            var door = doorRoot?.GetComponent<DoorInteractable>();
            var feedback = doorRoot?.GetComponent<DoorInteractionFeedback>();
            var doorVisualRenderer = GameObject.Find("DoorRoot/DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>();
            var movement = GameObject.Find("Player")?.GetComponent<PlayerMovement>();
            var interactionController = GameObject.Find("Player")?.GetComponent<PlayerInteractionController>();

            Assert.IsNotNull(door, "Expected a DoorInteractable on the generated DoorRoot.");
            Assert.IsNotNull(feedback, "Expected a DoorInteractionFeedback on the generated DoorRoot.");
            Assert.IsNotNull(doorVisualRenderer, "Expected a SpriteRenderer on the generated DoorVisual/DoorSprite.");
            Assert.IsNotNull(movement, "Expected a PlayerMovement on the generated Player.");
            Assert.IsNotNull(interactionController, "Expected a PlayerInteractionController on the generated Player.");

            var serializedFeedback = new SerializedObject(feedback);
            Assert.AreEqual(door, serializedFeedback.FindProperty("door").objectReferenceValue,
                "DoorInteractionFeedback must be wired to the same DoorInteractable it decorates.");
            Assert.AreEqual(doorVisualRenderer, serializedFeedback.FindProperty("doorRenderer").objectReferenceValue,
                "DoorInteractionFeedback must be wired to the generated DoorSprite SpriteRenderer.");
            Assert.AreEqual(movement, serializedFeedback.FindProperty("playerMovement").objectReferenceValue,
                "DoorInteractionFeedback must be wired to the generated Player's PlayerMovement so hover " +
                "consumes the shared pointer target instead of an independent projection (AC-005).");
            Assert.AreEqual(interactionController,
                serializedFeedback.FindProperty("interactionController").objectReferenceValue,
                "DoorInteractionFeedback must be wired to the generated Player's PlayerInteractionController " +
                "so selected/opening feedback tracks the real accepted-selection state (AC-003).");
        }

        // NSC-041 regression-only invariant: rebuilding the scene must not duplicate the
        // DoorInteractionFeedback component on DoorRoot.
        [Test]
        public void Build_RunTwice_DoesNotDuplicateDoorInteractionFeedback()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var doorRoot = GameObject.Find("DoorRoot");
            var feedbackComponents = doorRoot.GetComponents<DoorInteractionFeedback>();

            Assert.AreEqual(1, feedbackComponents.Length,
                "Re-running the scene builder must not duplicate the DoorInteractionFeedback component.");
        }

        // NSC-041 AC-001: the door's configured base appearance must actually be distinguishable
        // from the plain wall material, not left indistinguishable from an undifferentiated wall
        // segment as observed in human runtime validation.
        [Test]
        public void Build_DoorInteractionFeedback_BaseColorIsDistinguishableFromWallMaterial()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var feedback = GameObject.Find("DoorRoot")?.GetComponent<DoorInteractionFeedback>();
            var wallRenderer = GameObject.Find("Walls/WallLeft")?.GetComponent<Renderer>();
            Assert.IsNotNull(feedback, "Expected a DoorInteractionFeedback on the generated DoorRoot.");
            Assert.IsNotNull(wallRenderer, "Expected a Renderer on the generated WallLeft.");

            var baseColorProperty = new SerializedObject(feedback).FindProperty("baseColor");
            Assert.IsNotNull(baseColorProperty, "Expected a serialized 'baseColor' field on DoorInteractionFeedback.");

            var baseColor = baseColorProperty.colorValue;
            var wallColor = wallRenderer.sharedMaterial.color;

            Assert.Greater(
                Vector4.Distance(
                    new Vector4(baseColor.r, baseColor.g, baseColor.b, baseColor.a),
                    new Vector4(wallColor.r, wallColor.g, wallColor.b, wallColor.a)),
                0.15f,
                "AC-001: the door's configured base color must be visually distinguishable from the plain " +
                "wall material color so the door does not read as an undifferentiated wall segment.");
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
        public void Build_PlayerStartsAtCharacterControllerGroundedHeight()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var player = GameObject.Find("Player");

            Assert.IsNotNull(player);

            var controller =
                player.GetComponent<CharacterController>();

            Assert.IsNotNull(controller);

            Assert.That(
                controller.skinWidth,
                Is.EqualTo(0.08f).Within(0.0001f),
                "The current prototype CharacterController skin width changed; review the intended grounded spawn height.");

            Assert.That(
                player.transform.position.y,
                Is.EqualTo(controller.skinWidth).Within(0.0001f),
                "The Player must begin at the CharacterController's settled ground-contact height instead of visibly falling onto the floor when Play Mode starts.");

            Assert.That(
                player.transform.position.x,
                Is.EqualTo(0f).Within(0.0001f));

            Assert.That(
                player.transform.position.z,
                Is.EqualTo(-4f).Within(0.0001f));
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
        public void Build_GameplayFloor_KeepsCollisionButDisablesMeshRendererBehindTilemap()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var floor = GameObject.Find("Floor");

            Assert.IsNotNull(
                floor,
                "The gameplay Floor object must still exist independently of the visual Tilemap.");

            var collider = floor.GetComponent<MeshCollider>();
            var renderer = floor.GetComponent<MeshRenderer>();

            Assert.IsNotNull(
                collider,
                "The gameplay Floor must retain its MeshCollider for simulation.");

            Assert.IsNotNull(
                renderer,
                "The primitive Floor may retain its MeshRenderer component so the gameplay object structure remains stable.");

            Assert.IsFalse(
                renderer.enabled,
                "The gameplay Floor MeshRenderer must stay disabled because the Tilemap owns floor presentation; rendering both creates coplanar z-fighting.");

            var floorTilemap =
                GameObject.Find("IsometricVisualGrid/FloorTilemap")
                    ?.GetComponent<Tilemap>();

            Assert.IsNotNull(
                floorTilemap,
                "Disabling the gameplay Floor renderer is only valid while the visual floor Tilemap exists.");
        }
        [Test]
        public void Build_IsometricVisualLayer_HasFloorWallAndRepeatableArchitectureTilemaps()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var gridObject =
                GameObject.Find("IsometricVisualGrid");

            var grid =
                gridObject != null
                    ? gridObject.GetComponent<Grid>()
                    : null;

            var floorTilemap =
                GameObject.Find("IsometricVisualGrid/FloorTilemap")
                    ?.GetComponent<Tilemap>();

            var wallTilemap =
                GameObject.Find("IsometricVisualGrid/WallTilemap")
                    ?.GetComponent<Tilemap>();

            var architecturalTilemap =
                GameObject.Find("IsometricVisualGrid/ArchitecturalTilemap")
                    ?.GetComponent<Tilemap>();

            Assert.IsNotNull(gridObject);
            Assert.IsNotNull(grid);
            Assert.IsNotNull(floorTilemap);
            Assert.IsNotNull(wallTilemap);
            Assert.IsNotNull(architecturalTilemap);

            Assert.AreEqual(
                GridLayout.CellLayout.IsometricZAsY,
                grid.cellLayout,
                "The architectural visual foundation must remain an Isometric Z-as-Y Grid.");

            var floorRenderer =
                floorTilemap.GetComponent<TilemapRenderer>();

            var wallRenderer =
                wallTilemap.GetComponent<TilemapRenderer>();

            var architecturalRenderer =
                architecturalTilemap.GetComponent<TilemapRenderer>();

            Assert.IsNotNull(floorRenderer);
            Assert.IsNotNull(wallRenderer);
            Assert.IsNotNull(architecturalRenderer);

            Assert.AreEqual(
                TilemapRenderer.Mode.Individual,
                floorRenderer.mode);

            Assert.AreEqual(
                TilemapRenderer.Mode.Individual,
                wallRenderer.mode);

            Assert.AreEqual(
                TilemapRenderer.Mode.Individual,
                architecturalRenderer.mode);

            Assert.Less(
                floorRenderer.sortingOrder,
                wallRenderer.sortingOrder,
                "Ground floor visuals must remain in a background sorting band.");

            Assert.Less(
                architecturalRenderer.sortingOrder,
                wallRenderer.sortingOrder,
                "Ground-flush architectural decoration must remain behind the interleavable wall/world-sprite band.");

            var floorCount = 0;
            TileBase firstFloorTile = null;

            foreach (var cell in floorTilemap.cellBounds.allPositionsWithin)
            {
                if (!floorTilemap.HasTile(cell))
                {
                    continue;
                }

                floorCount++;

                var tile = floorTilemap.GetTile(cell);

                if (firstFloorTile == null)
                {
                    firstFloorTile = tile;
                }
                else
                {
                    Assert.AreSame(
                        firstFloorTile,
                        tile,
                        $"Floor cell {cell} must reuse the same architectural floor Tile.");
                }
            }

            Assert.Greater(
                floorCount,
                1,
                "The floor must be repeatably painted across multiple Tilemap cells.");

            var expectedWallCells = new[]
            {
                new Vector3Int(-1, 1, 0),
                new Vector3Int(0, 0, 0),
                new Vector3Int(1, -1, 0),

                new Vector3Int(4, -4, 0),
                new Vector3Int(5, -5, 0),
                new Vector3Int(6, -6, 0)
            };

            var wallCount = 0;
            TileBase firstWallTile = null;

            foreach (var cell in wallTilemap.cellBounds.allPositionsWithin)
            {
                if (!wallTilemap.HasTile(cell))
                {
                    continue;
                }

                wallCount++;

                var tile = wallTilemap.GetTile(cell);

                if (firstWallTile == null)
                {
                    firstWallTile = tile;
                }
                else
                {
                    Assert.AreSame(
                        firstWallTile,
                        tile,
                        $"Wall segment {cell} must reuse the same architectural wall Tile.");
                }
            }

            Assert.AreEqual(
                expectedWallCells.Length,
                wallCount,
                "The two three-unit gameplay walls must be represented by six one-unit visual Tile segments.");

            foreach (var cell in expectedWallCells)
            {
                Assert.IsTrue(
                    wallTilemap.HasTile(cell),
                    $"Expected independently sortable wall segment at {cell}.");
            }

            var architecturalCount = 0;
            TileBase firstArchitecturalTile = null;

            foreach (var cell in architecturalTilemap.cellBounds.allPositionsWithin)
            {
                if (!architecturalTilemap.HasTile(cell))
                {
                    continue;
                }

                architecturalCount++;

                var tile = architecturalTilemap.GetTile(cell);

                if (firstArchitecturalTile == null)
                {
                    firstArchitecturalTile = tile;
                }
                else
                {
                    Assert.AreSame(
                        firstArchitecturalTile,
                        tile,
                        $"Architectural border cell {cell} must reuse the same architectural Tile.");
                }
            }

            Assert.Greater(
                architecturalCount,
                1,
                "Repeatable architectural decoration must contain multiple reused Tile cells.");
        }

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
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            Physics.SyncTransforms();

            var wallTilemap =
                GameObject.Find("IsometricVisualGrid/WallTilemap")
                    ?.GetComponent<Tilemap>();

            var leftWallCollider =
                GameObject.Find("Walls/WallLeft")
                    ?.GetComponent<BoxCollider>();

            var rightWallCollider =
                GameObject.Find("Walls/WallRight")
                    ?.GetComponent<BoxCollider>();

            Assert.IsNotNull(wallTilemap);
            Assert.IsNotNull(leftWallCollider);
            Assert.IsNotNull(rightWallCollider);

            Assert.That(
                Vector3.Distance(
                    wallTilemap.tileAnchor,
                    Vector3.zero),
                Is.LessThan(0.0001f),
                "Wall visual cells must retain the zero Tile Anchor used by the architectural mapping.");

            Assert.That(
                Quaternion.Angle(
                    Quaternion.identity,
                    wallTilemap.transform.rotation),
                Is.LessThan(0.0001f),
                "Wall visual bounds calculations require the wall Tilemap to remain unrotated.");

            Assert.That(
                Vector3.Distance(
                    Vector3.one,
                    wallTilemap.transform.lossyScale),
                Is.LessThan(0.0001f),
                "Wall visual bounds calculations require unit world scale.");

            var leftCells = new[]
            {
                new Vector3Int(-1, 1, 0),
                new Vector3Int(0, 0, 0),
                new Vector3Int(1, -1, 0)
            };

            var rightCells = new[]
            {
                new Vector3Int(4, -4, 0),
                new Vector3Int(5, -5, 0),
                new Vector3Int(6, -6, 0)
            };

            var expectedCells = new[]
            {
                leftCells[0],
                leftCells[1],
                leftCells[2],
                rightCells[0],
                rightCells[1],
                rightCells[2]
            };

            var occupiedCount = 0;

            foreach (var cell in wallTilemap.cellBounds.allPositionsWithin)
            {
                if (wallTilemap.HasTile(cell))
                {
                    occupiedCount++;
                }
            }

            Assert.AreEqual(
                expectedCells.Length,
                occupiedCount,
                "Exactly six visual wall segments should represent the two independent three-unit gameplay walls.");

            foreach (var cell in expectedCells)
            {
                Assert.IsTrue(
                    wallTilemap.HasTile(cell),
                    $"Expected wall visual segment at {cell}.");
            }

            // Independently pin the simulation geometry so the visual alignment
            // assertion cannot become self-fulfilling by deriving gameplay
            // expectations from the Tilemap.
            var expectedGameplayCenters = new[]
            {
                new Vector3(-2.5f, 1.25f, 0f),
                new Vector3(2.5f, 1.25f, 0f)
            };

            var expectedGameplaySize =
                new Vector3(3f, 2.5f, 0.3f);

            var cellGroups = new[]
            {
                leftCells,
                rightCells
            };

            var gameplayColliders = new[]
            {
                leftWallCollider,
                rightWallCollider
            };

            var wallLabels = new[]
            {
                "left",
                "right"
            };

            for (var groupIndex = 0;
                 groupIndex < cellGroups.Length;
                 groupIndex++)
            {
                var cells = cellGroups[groupIndex];
                var gameplayCollider = gameplayColliders[groupIndex];
                var expectedCenter = expectedGameplayCenters[groupIndex];
                var wallLabel = wallLabels[groupIndex];

                Assert.That(
                    gameplayCollider.bounds.center.x,
                    Is.EqualTo(expectedCenter.x).Within(0.001f),
                    $"{wallLabel} gameplay wall X center changed unexpectedly.");

                Assert.That(
                    gameplayCollider.bounds.center.y,
                    Is.EqualTo(expectedCenter.y).Within(0.001f),
                    $"{wallLabel} gameplay wall Y center changed unexpectedly.");

                Assert.That(
                    gameplayCollider.bounds.center.z,
                    Is.EqualTo(expectedCenter.z).Within(0.001f),
                    $"{wallLabel} gameplay wall Z center changed unexpectedly.");

                Assert.That(
                    gameplayCollider.bounds.size.x,
                    Is.EqualTo(expectedGameplaySize.x).Within(0.001f),
                    $"{wallLabel} gameplay wall width changed unexpectedly.");

                Assert.That(
                    gameplayCollider.bounds.size.y,
                    Is.EqualTo(expectedGameplaySize.y).Within(0.001f),
                    $"{wallLabel} gameplay wall height changed unexpectedly.");

                Assert.That(
                    gameplayCollider.bounds.size.z,
                    Is.EqualTo(expectedGameplaySize.z).Within(0.001f),
                    $"{wallLabel} gameplay wall depth changed unexpectedly.");

                var minimumX = float.PositiveInfinity;
                var maximumX = float.NegativeInfinity;
                var minimumY = float.PositiveInfinity;
                var maximumY = float.NegativeInfinity;

                var visualPlaneZ = float.NaN;

                foreach (var cell in cells)
                {
                    var sprite = wallTilemap.GetSprite(cell);

                    Assert.IsNotNull(
                        sprite,
                        $"{wallLabel} wall segment {cell} must resolve to Sprite art.");

                    Assert.That(
                        sprite.bounds.size.x,
                        Is.EqualTo(1f).Within(0.001f),
                        $"{wallLabel} wall segment {cell} must be one world unit wide.");

                    Assert.That(
                        sprite.bounds.size.y,
                        Is.EqualTo(2.5f).Within(0.001f),
                        $"{wallLabel} wall segment {cell} must retain gameplay-wall height.");

                    Assert.That(
                        sprite.pivot.y,
                        Is.EqualTo(0f).Within(0.01f),
                        $"{wallLabel} wall segment {cell} must use its ground-contact pivot.");

                    // With the Tilemap's zero anchor and identity transform,
                    // GetCellCenterWorld is the render/sort pivot used by this
                    // architectural cell. Sprite.bounds is relative to that
                    // bottom-center pivot.
                    var pivot =
                        wallTilemap.GetCellCenterWorld(cell);

                    minimumX =
                        Mathf.Min(
                            minimumX,
                            pivot.x + sprite.bounds.min.x);

                    maximumX =
                        Mathf.Max(
                            maximumX,
                            pivot.x + sprite.bounds.max.x);

                    minimumY =
                        Mathf.Min(
                            minimumY,
                            pivot.y + sprite.bounds.min.y);

                    maximumY =
                        Mathf.Max(
                            maximumY,
                            pivot.y + sprite.bounds.max.y);

                    if (float.IsNaN(visualPlaneZ))
                    {
                        visualPlaneZ = pivot.z;
                    }
                    else
                    {
                        Assert.That(
                            pivot.z,
                            Is.EqualTo(visualPlaneZ).Within(0.0001f),
                            $"{wallLabel} wall segments must remain on one common visual plane.");
                    }
                }

                var visualCenterX =
                    (minimumX + maximumX) * 0.5f;

                var visualCenterY =
                    (minimumY + maximumY) * 0.5f;

                var visualWidth =
                    maximumX - minimumX;

                var visualHeight =
                    maximumY - minimumY;

                Assert.That(
                    visualCenterX,
                    Is.EqualTo(gameplayCollider.bounds.center.x).Within(0.001f),
                    $"The three {wallLabel} visual segments collectively must remain centered on their independent gameplay wall.");

                Assert.That(
                    visualCenterY,
                    Is.EqualTo(gameplayCollider.bounds.center.y).Within(0.001f),
                    $"The three {wallLabel} visual segments collectively must retain the gameplay wall's vertical center.");

                Assert.That(
                    visualWidth,
                    Is.EqualTo(gameplayCollider.bounds.size.x).Within(0.001f),
                    $"The three {wallLabel} visual segments collectively must cover the gameplay wall's full width.");

                Assert.That(
                    visualHeight,
                    Is.EqualTo(gameplayCollider.bounds.size.y).Within(0.001f),
                    $"The {wallLabel} wall visual must retain the gameplay wall's full height.");

                Assert.That(
                    minimumY,
                    Is.EqualTo(gameplayCollider.bounds.min.y).Within(0.001f),
                    $"The {wallLabel} wall visual must begin at the same ground-contact height as gameplay collision.");

                Assert.That(
                    maximumY,
                    Is.EqualTo(gameplayCollider.bounds.max.y).Within(0.001f),
                    $"The {wallLabel} wall visual must terminate at the same height as gameplay collision.");

                // The visual is intentionally a plane immediately adjacent to
                // one face of the 3D gameplay collider rather than a 0.3-unit
                // deep renderer. Verify that offset without requiring a
                // particular front/back sign.
                Assert.That(
                    Mathf.Abs(
                        visualPlaneZ -
                        gameplayCollider.bounds.center.z),
                    Is.EqualTo(gameplayCollider.bounds.extents.z).Within(0.002f),
                    $"The {wallLabel} wall visual plane must remain aligned to a face of its separate gameplay collider.");
            }
        }

        [Test]
        public void Build_DoorSprite_UsesReusableWorldSpaceSpriteRendererConvention()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var doorVisual = GameObject.Find("DoorRoot/DoorVisual");
            Assert.IsNotNull(doorVisual, "Expected a DoorVisual child under DoorRoot.");

            var doorSpriteRenderer = GameObject.Find("DoorRoot/DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(doorSpriteRenderer, "Expected a 'DoorSprite' SpriteRenderer child under DoorVisual.");
            Assert.IsNotNull(doorSpriteRenderer.sprite, "Door world sprite must have a sprite assigned to be visible.");
            Assert.AreEqual("Default", doorSpriteRenderer.sortingLayerName);
            Assert.AreEqual(0, doorSpriteRenderer.sortingOrder);

            Assert.IsNull(doorVisual.GetComponent<MeshRenderer>(),
                "DoorVisual must no longer use a legacy PrimitiveType.Cube mesh visual.");
            Assert.IsNull(doorSpriteRenderer.GetComponent<MeshRenderer>());
        }

        // NSC-039 AC-001 (human-review rejection item 1): the prior review-ready candidate
        // applied an orientation appropriate to a 3D/billboard presentation rather than the
        // authored 2D door sprite. The human manually corrected the door and reports its
        // authored orientation is zero rotation (Quaternion.identity / inspector 0,0,0).
        [Test]
        public void Build_DoorSprite_UsesHumanApprovedIdentityLocalRotation()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var doorSpriteObject = GameObject.Find("DoorRoot/DoorVisual/DoorSprite");
            Assert.IsNotNull(doorSpriteObject, "Expected a 'DoorSprite' child under DoorVisual.");

            Assert.AreEqual(Quaternion.identity, doorSpriteObject.transform.localRotation,
                "Human-review correction (item 1): DoorSprite must be generated with identity/local zero " +
                "rotation (Quaternion.identity / inspector 0,0,0) matching the human-validated correction, not " +
                "a generated tilt/billboard orientation.");
        }

        // NSC-039 AC-001 (human-review rejection item 1): the fix must not merely hard-code the
        // door to identity while secretly still forcing one orientation onto every consumer of
        // the shared world-sprite construction helper. This drives the actual private
        // construction seam directly with a distinct, non-identity rotation and proves the
        // produced instance actually carries that caller-supplied rotation, so authored
        // orientation genuinely remains a per-instance/per-object decision rather than an
        // invariant baked into the reusable prefab convention.
        // Quaternion components can differ by tiny floating-point amounts while
        // representing the same rotation. Compare the rotation itself.
        private static void AssertQuaternionRotationApproximatelyEqual(
            Quaternion expected,
            Quaternion actual,
            string message)
        {
            Assert.Less(
                Quaternion.Angle(expected, actual),
                0.01f,
                message);
        }
        [Test]
        public void CreateWorldSpriteVisual_AppliesCallerSuppliedRotationPerInstanceRatherThanForcingOneOrientation()
        {
            var textureSizeField = typeof(DoorPrototypeSceneBuilder).GetField(
                "WorldSpriteTextureSize", BindingFlags.NonPublic | BindingFlags.Static);
            Assert.IsNotNull(textureSizeField, "Expected a private static WorldSpriteTextureSize field.");
            var textureSize = (int)textureSizeField.GetValue(null);

            var method = typeof(DoorPrototypeSceneBuilder).GetMethod(
                "CreateWorldSpriteVisual", BindingFlags.NonPublic | BindingFlags.Static);
            Assert.IsNotNull(method,
                "Expected a private static CreateWorldSpriteVisual helper accepting a per-call localRotation.");

            var parent = new GameObject("NSC039_TestWorldSpriteParent");
            try
            {
                var distinctRotation = Quaternion.Euler(0f, 90f, 0f);
                var pixels = new Color32[textureSize * textureSize];

                var renderer = (SpriteRenderer)method.Invoke(null, new object[]
                {
                    "TestWorldSprite",
                    "NSC039_TestWorldSpriteAsset",
                    parent.transform,
                    Vector3.zero,
                    distinctRotation,
                    new Vector2(1f, 1f),
                    pixels,
                    null
                });

                Assert.IsNotNull(renderer);
                AssertQuaternionRotationApproximatelyEqual(distinctRotation, renderer.transform.localRotation,
                    "The shared world-sprite construction helper must apply the caller-supplied localRotation " +
                    "to the produced instance rather than forcing one hard-coded orientation onto every " +
                    "consumer.");

                // Explicit isolation: destroy this test's own transient Sprite/Texture pair
                // immediately rather than relying on the builder's lazy next-Build() cleanup, so
                // this test leaves no owned transient objects behind if it happens to run last.
                var producedSprite = renderer.sprite;
                var producedTexture = producedSprite != null ? producedSprite.texture : null;
                if (producedSprite != null) Object.DestroyImmediate(producedSprite);
                if (producedTexture != null) Object.DestroyImmediate(producedTexture);
            }
            finally
            {
                Object.DestroyImmediate(parent);
            }
        }

        // NSC-039 AC-001 (human-review rejection item 2): the prior review-ready candidate's
        // wizard placeholder was a solid brown bordered square, which made visual
        // sorting/occlusion validation unnecessarily difficult even though placeholder art is
        // allowed. The corrected placeholder must be a readable silhouette with real transparent
        // regions (outside a rounded head / tapered robe shape) rather than an undifferentiated
        // rect that fills its whole texture. Compared directly against the door's own bordered
        // rect (which is expected to stay fully opaque at its corners) so this is a genuine
        // observed silhouette difference, not an assumption about texture sampling.
        [Test]
        public void Build_WizardPlaceholderSprite_IsReadableSilhouetteNotSolidBorderedSquare()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var wizardSprite = GameObject.Find("Player/Visual")?.GetComponent<SpriteRenderer>()?.sprite;
            var doorSprite = GameObject.Find("DoorRoot/DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>()?.sprite;
            Assert.IsNotNull(wizardSprite, "Expected a sprite on the Player's Visual child.");
            Assert.IsNotNull(doorSprite, "Expected a sprite on DoorSprite.");

            var wizardTexture = wizardSprite.texture;
            var doorTexture = doorSprite.texture;
            Assert.IsNotNull(wizardTexture);
            Assert.IsNotNull(doorTexture);

            var width = wizardTexture.width;
            var height = wizardTexture.height;

            var wizardCorners = new[]
            {
                wizardTexture.GetPixel(2, 2),
                wizardTexture.GetPixel(width - 3, 2),
                wizardTexture.GetPixel(2, height - 3),
                wizardTexture.GetPixel(width - 3, height - 3)
            };
            foreach (var corner in wizardCorners)
            {
                Assert.AreEqual(0f, corner.a,
                    "Human-review correction (item 2): the wizard placeholder must have real transparent " +
                    "silhouette regions (e.g. outside a rounded head/tapered robe shape) rather than being an " +
                    "undifferentiated solid/bordered square that fills its entire texture.");
            }

            var wizardBodyFill = wizardTexture.GetPixel(width / 2, height / 4);
            Assert.Greater(wizardBodyFill.a, 0f,
                "Expected the wizard silhouette to still have an actual opaque filled region (its robe/body), " +
                "not be fully transparent.");

            var doorCorner = doorTexture.GetPixel(2, 2);
            Assert.Greater(doorCorner.a, 0f,
                "Sanity check: the door's bordered-rect sprite is expected to remain fully opaque at its " +
                "corners, confirming the wizard's transparent corners above reflect a real silhouette " +
                "difference rather than a shared/broken texture-sampling assumption.");
        }

        // NSC-039 AC-001: the wizard's placeholder visual representation must use the same
        // reusable world-space SpriteRenderer convention as the door, per the GDD requirement
        // that the wizard follow the same isometric sorting conventions as other world-space
        // SpriteRenderers, rather than the previous PrimitiveType.Capsule visual.
        [Test]
        public void Build_PlayerVisual_UsesReusableWorldSpaceSpriteRendererConvention()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var playerSpriteObject = GameObject.Find("Player/Visual");
            Assert.IsNotNull(playerSpriteObject, "Expected a 'Visual' child under Player.");

            var playerSpriteRenderer = playerSpriteObject.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(playerSpriteRenderer, "Expected a SpriteRenderer on the Player's Visual child.");
            Assert.IsNotNull(playerSpriteRenderer.sprite, "Wizard placeholder world sprite must have a sprite assigned.");
            Assert.AreEqual("Default", playerSpriteRenderer.sortingLayerName);
            Assert.AreEqual(0, playerSpriteRenderer.sortingOrder);

            Assert.IsNull(playerSpriteObject.GetComponent<Collider>(),
                "The wizard's visual child must stay decoupled from gameplay collision; the CharacterController " +
                "on Player owns collision.");
            Assert.IsNull(playerSpriteObject.GetComponent<MeshRenderer>(),
                "Player Visual must no longer use a legacy PrimitiveType.Capsule mesh visual.");
        }

        // NSC-039 AC-001 / VAL-001 (human-review correction, items 1 and 6): every
        // independently sorted world-space SpriteRenderer must share one sorting layer/order
        // convention. Ground-flush background Tilemap layers (the floor and the flat
        // decorative architectural border) are intentionally forced behind that shared band
        // with a strictly lower static sortingOrder, since nothing standing on the ground
        // plane should ever be able to render behind it. Walls are vertical, interleavable
        // occluding geometry, so unlike the ground-flush layers they intentionally SHARE the
        // exact same sortingOrder as world sprites instead of being forced behind by a lower
        // static order - a prior candidate asserted walls were always strictly behind world
        // sprites, which made a wall unable to occlude/be occluded by a world sprite according
        // to isometric position at all.
        [Test]
        public void Build_WorldSpriteVisuals_ShareInteractiveSortingBandAboveGroundFlushBackgroundLayers()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var doorSprite = GameObject.Find("DoorRoot/DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>();
            var playerSprite = GameObject.Find("Player/Visual")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(doorSprite);
            Assert.IsNotNull(playerSprite);

            Assert.AreEqual(doorSprite.sortingLayerName, playerSprite.sortingLayerName,
                "Every world-space SpriteRenderer must share one sorting layer per the reusable convention.");
            Assert.AreEqual(doorSprite.sortingOrder, playerSprite.sortingOrder,
                "Every world-space SpriteRenderer must share one sortingOrder so relative depth between them is " +
                "resolved by the camera's dynamic transparency sort rather than a static per-object override.");

            var grid = GameObject.Find("IsometricVisualGrid")?.GetComponent<Grid>();
            Assert.IsNotNull(grid);
            var floorRenderer = grid.transform.Find("FloorTilemap")?.GetComponent<TilemapRenderer>();
            var wallRenderer = grid.transform.Find("WallTilemap")?.GetComponent<TilemapRenderer>();
            var architecturalRenderer = grid.transform.Find("ArchitecturalTilemap")?.GetComponent<TilemapRenderer>();
            Assert.IsNotNull(floorRenderer);
            Assert.IsNotNull(wallRenderer);
            Assert.IsNotNull(architecturalRenderer);

            Assert.AreEqual(doorSprite.sortingLayerName, floorRenderer.sortingLayerName,
                "Tilemap architecture must share the same sorting layer as world sprites for sortingOrder " +
                "comparisons between them to be meaningful.");
            Assert.AreEqual(doorSprite.sortingLayerName, wallRenderer.sortingLayerName);
            Assert.AreEqual(doorSprite.sortingLayerName, architecturalRenderer.sortingLayerName);

            Assert.Less(floorRenderer.sortingOrder, doorSprite.sortingOrder,
                "The ground-flush floor layer must always render behind world-space sprites.");
            Assert.Less(architecturalRenderer.sortingOrder, doorSprite.sortingOrder,
                "The ground-flush decorative architectural border layer must always render behind world-space " +
                "sprites.");

            Assert.AreEqual(doorSprite.sortingOrder, wallRenderer.sortingOrder,
                "Walls must share the world-sprite interactive sortingOrder band rather than being forced " +
                "behind by a lower static sortingOrder, so the camera's positional transparency sort can " +
                "genuinely interleave walls with world sprites according to isometric position.");
        }

        // NSC-039 AC-001 (human-review correction, item 3): the reusable "prefab convention"
        // must be a real, reusable Prefab asset that every independently sorted world-space
        // object is instantiated from, not merely a private scene-builder helper method. This
        // uses the persistence-aware test seam because the shared Prefab asset only exists on
        // disk (AssetDatabase.Contains) when instances are created through
        // PrefabUtility.InstantiatePrefab rather than the in-memory Object.Instantiate path.
        [Test]
        public void Build_WorldSpriteVisuals_AreInstancesOfOneSharedReusablePrefabAsset()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            var doorSpriteObject = GameObject.Find("DoorRoot/DoorVisual/DoorSprite");
            var wizardSpriteObject = GameObject.Find("Player/Visual");
            Assert.IsNotNull(doorSpriteObject);
            Assert.IsNotNull(wizardSpriteObject);

            var doorPrefabSource = PrefabUtility.GetCorrespondingObjectFromSource(doorSpriteObject);
            var wizardPrefabSource = PrefabUtility.GetCorrespondingObjectFromSource(wizardSpriteObject);
            Assert.IsNotNull(doorPrefabSource,
                "DoorSprite must be a real Prefab instance connected to a saved Prefab asset, not a " +
                "hand-assembled GameObject.");
            Assert.IsNotNull(wizardPrefabSource,
                "The wizard's Visual sprite must be a real Prefab instance connected to a saved Prefab asset.");

            var doorPrefabAssetPath = AssetDatabase.GetAssetPath(doorPrefabSource);
            var wizardPrefabAssetPath = AssetDatabase.GetAssetPath(wizardPrefabSource);
            Assert.IsNotEmpty(doorPrefabAssetPath);
            Assert.AreEqual(doorPrefabAssetPath, wizardPrefabAssetPath,
                "The door and the wizard must be instantiated from the exact same reusable world-space " +
                "SpriteRenderer Prefab asset, per the shared prefab convention.");
            StringAssert.EndsWith(".prefab", doorPrefabAssetPath,
                "The shared world-space SpriteRenderer convention must be backed by a real .prefab asset.");

            var prefabAsset = AssetDatabase.LoadAssetAtPath<GameObject>(doorPrefabAssetPath);
            Assert.IsNotNull(prefabAsset);
            var prefabRenderer = prefabAsset.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(prefabRenderer,
                "The shared Prefab asset must itself carry the SpriteRenderer sorting convention.");
            Assert.AreEqual("Default", prefabRenderer.sortingLayerName);
            Assert.AreEqual(0, prefabRenderer.sortingOrder);
        }

        // NSC-039 AC-001: rebuilding must reuse, not duplicate, the shared world-space
        // SpriteRenderer Prefab asset - mirroring the existing reuse guarantee already proven
        // for architectural Tiles and for the per-object Sprite/Texture assets.
        //
        // Also covers the validator-blocking regression (item 1): the shared prefab must be
        // saved under the caller-owned temporary folder's own "WorldSprites" subfolder, never at
        // a fixed AssetDatabase path shared with the production Build() command, so the
        // persistence-aware test seam can never collide with a committed canonical prefab.
        [Test]
        public void Build_RunTwiceWithPersistentFolder_ReusesSameSharedWorldSpritePrefabAssetWithoutDuplicating()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);
            var firstDoorSpriteObject = GameObject.Find("DoorRoot/DoorVisual/DoorSprite");
            var firstPrefabAssetPath =
                AssetDatabase.GetAssetPath(PrefabUtility.GetCorrespondingObjectFromSource(firstDoorSpriteObject));

            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);
            var secondDoorSpriteObject = GameObject.Find("DoorRoot/DoorVisual/DoorSprite");
            var secondPrefabAssetPath =
                AssetDatabase.GetAssetPath(PrefabUtility.GetCorrespondingObjectFromSource(secondDoorSpriteObject));

            Assert.IsNotEmpty(firstPrefabAssetPath);
            Assert.AreEqual(firstPrefabAssetPath, secondPrefabAssetPath,
                "Rebuilding must reuse the existing shared world-space SpriteRenderer Prefab asset rather than " +
                "creating a duplicate.");

            var worldSpritePrefabAssetFolder = temporaryArchitecturalTileAssetFolder + "/WorldSprites";
            StringAssert.StartsWith(worldSpritePrefabAssetFolder + "/", firstPrefabAssetPath,
                "The shared world-space SpriteRenderer Prefab asset must be saved under the caller-owned " +
                "temporary folder's own WorldSprites subfolder, not a fixed path shared with the production " +
                "Build() command.");
            Assert.AreEqual(1,
                AssetDatabase.FindAssets("t:GameObject", new[] { worldSpritePrefabAssetFolder }).Length,
                "Only one shared world-space SpriteRenderer Prefab asset should exist after rebuilding.");
        }

        // NSC-039 AC-001 (human-review correction, item 2): tall doors/props/characters must
        // not shift depth merely because their sprite silhouette is taller. Both a taller door
        // sprite (2.5 world units) and a shorter wizard placeholder (2 world units) must anchor
        // their SpriteRenderer's own world position at their object's ground-contact point
        // (not an elevated visual center), using a bottom-anchored sprite pivot so artwork
        // extends upward from that shared ground point.
        [Test]
        public void Build_WorldSpriteVisuals_UseConsistentGroundContactOriginRegardlessOfSpriteHeight()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var doorRoot = GameObject.Find("DoorRoot");
            var doorSprite = GameObject.Find("DoorRoot/DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>();
            var player = GameObject.Find("Player");
            var playerSprite = GameObject.Find("Player/Visual")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(doorRoot);
            Assert.IsNotNull(doorSprite);
            Assert.IsNotNull(player);
            Assert.IsNotNull(playerSprite);

            Assert.That(doorSprite.transform.position.y, Is.EqualTo(doorRoot.transform.position.y).Within(0.001f),
                "DoorSprite's world position must sit at the door's ground-contact point, not the elevated " +
                "DoorVisual center.");
            Assert.That(playerSprite.transform.position.y, Is.EqualTo(player.transform.position.y).Within(0.001f),
                "The wizard sprite's world position must sit at the player's own ground-contact point.");

            AssertSpriteIsBottomAnchored(doorSprite.sprite);
            AssertSpriteIsBottomAnchored(playerSprite.sprite);
        }

        private static void AssertSpriteIsBottomAnchored(Sprite sprite)
        {
            Assert.IsNotNull(sprite);
            Assert.That(sprite.pivot.y, Is.EqualTo(0f).Within(0.01f),
                "World sprite pivot must be bottom-anchored so artwork extends upward from the ground-contact " +
                "position instead of being centered on it.");
            Assert.That(sprite.pivot.x, Is.EqualTo(sprite.rect.width / 2f).Within(0.01f),
                "World sprite pivot must stay horizontally centered.");
        }

        // NSC-039 AC-001/VAL-001 (human-review correction, item 4): a bottom-anchored sprite
        // pivot alone does not make the SpriteRenderer sort by that pivot. Unity's default
        // SpriteRenderer.spriteSortPoint is Center, which would depth-sort by the sprite's
        // visual center and defeat the ground-contact convention even though the pivot itself
        // is correctly bottom-anchored (proven separately by AssertSpriteIsBottomAnchored).
        [Test]
        public void Build_WorldSpriteVisuals_SortByPivotNotCenterSoGroundContactSortingIsReal()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            var doorSprite = GameObject.Find("DoorRoot/DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>();
            var playerSprite = GameObject.Find("Player/Visual")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(doorSprite);
            Assert.IsNotNull(playerSprite);

            Assert.AreEqual(SpriteSortPoint.Pivot, doorSprite.spriteSortPoint,
                "DoorSprite must sort by its bottom-anchored pivot, not the default Center sort point, or the " +
                "ground-contact sorting convention has no actual effect on render order.");
            Assert.AreEqual(SpriteSortPoint.Pivot, playerSprite.spriteSortPoint,
                "The wizard's world sprite must sort by its bottom-anchored pivot, not the default Center sort " +
                "point.");

            var doorSpriteObject = GameObject.Find("DoorRoot/DoorVisual/DoorSprite");
            var prefabSource = PrefabUtility.GetCorrespondingObjectFromSource(doorSpriteObject);
            Assert.IsNotNull(prefabSource);
            var prefabAssetPath = AssetDatabase.GetAssetPath(prefabSource);
            var prefabAsset = AssetDatabase.LoadAssetAtPath<GameObject>(prefabAssetPath);
            var prefabRenderer = prefabAsset.GetComponent<SpriteRenderer>();
            Assert.AreEqual(SpriteSortPoint.Pivot, prefabRenderer.spriteSortPoint,
                "The shared reusable world-space SpriteRenderer Prefab asset itself must carry the Pivot sort " +
                "point convention, not just individual scene instances.");
        }

        // NSC-039 AC-001 (human-review correction, item 6): the persistent sprite asset
        // identity must be a distinct key from the scene hierarchy object name so two different
        // world objects (e.g. the wizard and a future enemy/prop) that both use a generically
        // named "Visual" hierarchy child cannot silently collide on, or reuse, the same
        // persisted sprite artwork.
        [Test]
        public void Build_WizardPersistentSpriteAsset_UsesWizardSpecificAssetIdentityNotGenericHierarchyName()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            var wizardSpriteObject = GameObject.Find("Player/Visual");
            Assert.IsNotNull(wizardSpriteObject, "The wizard's hierarchy child must remain named 'Visual'.");

            var wizardSprite = wizardSpriteObject.GetComponent<SpriteRenderer>().sprite;
            Assert.IsNotNull(wizardSprite);

            var wizardAssetPath = AssetDatabase.GetAssetPath(wizardSprite);
            Assert.IsNotEmpty(wizardAssetPath);
            StringAssert.DoesNotContain("/Visual.asset", wizardAssetPath,
                "The wizard's persistent sprite asset must not be keyed off the generic hierarchy child name " +
                "'Visual', or a future world object that also names its child 'Visual' would silently collide " +
                "with or reuse the wizard's sprite artwork.");
            StringAssert.EndsWith("/WizardSprite.asset", wizardAssetPath,
                "The wizard's persistent sprite asset must use an explicit wizard-specific asset identity while " +
                "its hierarchy object remains Player/Visual.");
        }

        // VAL-001: the shared sortingLayer/sortingOrder convention above only fixes world
        // sprites above Tilemap architecture; correct relative ordering between world sprites at
        // different isometric positions additionally depends on the camera resolving same-order
        // renderers by distance, which requires this explicit orthographic transparency sort mode.
        [Test]
        public void Build_MainCamera_UsesCustomAxisTransparencySortForWorldSpriteDepthOrdering()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var camera =
                GameObject.Find("Main Camera")?.GetComponent<Camera>();

            Assert.IsNotNull(camera);

            Assert.AreEqual(
                TransparencySortMode.CustomAxis,
                camera.transparencySortMode,
                "Isometric Z-as-Y world sprites and Individual Tilemap cells must use CustomAxis sorting.");

            // Unity normalizes Camera.transparencySortAxis when it is assigned.
            // Compare against the normalized form of the authored axis rather
            // than expecting the raw (0, 1, -0.26) components to survive.
            var expectedAxis =
                new Vector3(0f, 1f, -0.26f).normalized;

            Assert.That(
                Vector3.Distance(
                    expectedAxis,
                    camera.transparencySortAxis),
                Is.LessThan(0.0001f),
                "The camera must preserve the intended normalized Isometric Z-as-Y transparency sorting direction.");

            Assert.That(
                camera.transparencySortAxis.magnitude,
                Is.EqualTo(1f).Within(0.0001f),
                "Unity's stored CustomAxis sorting direction should be normalized.");
        }

        [Test]
        public void Build_RepresentativeWorldSprite_CanSortOnEitherSideOfRealWallTilemapGeometry()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();
            var wizardVisual = GameObject.Find("Player/Visual");
            var wallTilemap =
                GameObject.Find("IsometricVisualGrid/WallTilemap")?.GetComponent<Tilemap>();
            var wallRenderer =
                wallTilemap != null ? wallTilemap.GetComponent<TilemapRenderer>() : null;

            Assert.IsNotNull(camera);
            Assert.IsNotNull(wizardVisual);
            Assert.IsNotNull(wallTilemap);
            Assert.IsNotNull(wallRenderer);

            var wizardRenderer = wizardVisual.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(wizardRenderer);

            Assert.AreEqual(TransparencySortMode.CustomAxis, camera.transparencySortMode);
            Assert.AreEqual(TilemapRenderer.Mode.Individual, wallRenderer.mode);

            Assert.AreEqual(wallRenderer.sortingLayerName, wizardRenderer.sortingLayerName);
            Assert.AreEqual(wallRenderer.sortingOrder, wizardRenderer.sortingOrder,
                "Walls and world sprites must remain in the same order band so the custom axis decides occlusion.");

            var sortAxis = camera.transparencySortAxis;
            var wallCenter = wallTilemap.GetCellCenterWorld(Vector3Int.zero);

            // The wall sprite is wider than one unit. Walking along its X length while
            // staying on the same side must not change the positional sort key.
            var firstEnd = wallCenter + Vector3.left;
            var secondEnd = wallCenter + Vector3.right;

            var firstWallKey = Vector3.Dot(firstEnd, sortAxis);
            var secondWallKey = Vector3.Dot(secondEnd, sortAxis);

            Assert.That(
                secondWallKey,
                Is.EqualTo(firstWallKey).Within(0.0001f),
                "Opposite ends of the same long wall must have the same CustomAxis depth; X movement along the wall must not flip front/behind ordering.");

            var groundCrossWallDirection =
                new Vector3(sortAxis.x, 0f, sortAxis.z);

            Assert.Greater(
                groundCrossWallDirection.sqrMagnitude,
                0.0001f,
                "The custom sorting axis must contain a ground-plane component so crossing the wall can change depth.");

            groundCrossWallDirection.Normalize();

            var sameSideOffset = groundCrossWallDirection * 2f;

            wizardVisual.transform.position = firstEnd + sameSideOffset;
            var firstEndSameSideKey =
                Vector3.Dot(wizardVisual.transform.position, sortAxis);

            wizardVisual.transform.position = secondEnd + sameSideOffset;
            var secondEndSameSideKey =
                Vector3.Dot(wizardVisual.transform.position, sortAxis);

            Assert.That(
                secondEndSameSideKey,
                Is.EqualTo(firstEndSameSideKey).Within(0.0001f),
                "Walking from one end of a long wall to the other while remaining on the same side must not reverse the wizard/wall sort relationship.");

            var wallKey = Vector3.Dot(wallCenter, sortAxis);

            var oppositeSideKey =
                Vector3.Dot(firstEnd - sameSideOffset, sortAxis);

            Assert.Less(
                (firstEndSameSideKey - wallKey) *
                (oppositeSideKey - wallKey),
                0f,
                "Moving from one side of the wall to the other must cross the wall's CustomAxis depth so the wizard can legitimately sort on either side.");
        }

        [Test]
        public void Build_WallTilemap_UsesGroundPivotedOneCellSegmentsForStableSorting()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var wallTilemap =
                GameObject.Find("IsometricVisualGrid/WallTilemap")?.GetComponent<Tilemap>();

            Assert.IsNotNull(wallTilemap);

            var wallSprite =
                wallTilemap.GetSprite(Vector3Int.zero);

            Assert.IsNotNull(wallSprite);

            Assert.That(
                wallSprite.bounds.size.x,
                Is.EqualTo(1f).Within(0.001f),
                "Each wall Tile must be one world unit wide so Individual sorting has multiple depth points along a long wall.");

            Assert.That(
                wallSprite.bounds.size.y,
                Is.EqualTo(2.5f).Within(0.001f));

            Assert.That(
                wallSprite.pivot.x,
                Is.EqualTo(wallSprite.rect.width * 0.5f).Within(0.01f));

            Assert.That(
                wallSprite.pivot.y,
                Is.EqualTo(0f).Within(0.01f),
                "Wall visual sorting must originate at the wall/floor contact.");

            Assert.That(
                wallTilemap.transform.position.y,
                Is.EqualTo(0f).Within(0.0001f));

            var expectedCells = new[]
            {
                new Vector3Int(-1, 1, 0),
                new Vector3Int(0, 0, 0),
                new Vector3Int(1, -1, 0),

                new Vector3Int(4, -4, 0),
                new Vector3Int(5, -5, 0),
                new Vector3Int(6, -6, 0)
            };

            foreach (var cell in expectedCells)
            {
                Assert.IsNotNull(
                    wallTilemap.GetTile(cell),
                    $"Expected independently sortable wall segment at {cell}.");
            }
        }

        // NSC-042 AC-001: human runtime validation observed repeated wall segments visibly
        // restarting their brick pattern at each sorting-segment boundary. Every wall segment
        // renders the exact same unshifted WallTile texture side by side (PaintWallRun), so for
        // that repetition to look seamless rather than resetting, the mortar-joint spacing must
        // evenly divide the texture width - otherwise a brick is cut short at the tile's own
        // right edge and the next identical segment restarts a fresh, differently-sized brick
        // instead of continuing it. This proves that directly from the actual produced wall
        // texture pixels (not by re-deriving the algorithm) by treating the texture as tiled
        // end-to-end and confirming every brick run between mortar joints on a representative
        // unstaggered course row has equal length; an unequal run at the wrap boundary is
        // exactly that cut-off-brick / pattern-phase-reset seam.
        [Test]
        public void Build_WallTileTexture_HasUniformBrickRunsSoAdjacentSegmentsTileWithoutASeam()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var wallTilemap = GameObject.Find("IsometricVisualGrid/WallTilemap")?.GetComponent<Tilemap>();
            Assert.IsNotNull(wallTilemap);

            var wallTile = wallTilemap.GetTile<Tile>(Vector3Int.zero);
            Assert.IsNotNull(wallTile, "Expected a Tile at wall cell (0,0,0).");
            var texture = wallTile.sprite != null ? wallTile.sprite.texture : null;
            Assert.IsNotNull(texture, "Expected the wall Tile's sprite to reference a texture.");

            var width = texture.width;
            var pixels = texture.GetPixels32();

            // Course 0 (rows below the courseHeight boundary) is unstaggered, so its brick
            // pattern in X directly reflects the mortar spacing. Row 10 sits inside course 0
            // and below its 2px horizontal mortar band.
            const int representativeRow = 10;
            Assert.Less(representativeRow * width, pixels.Length,
                "Representative row must be within the actual wall texture height.");

            var rowPixels = new Color32[width];
            for (var x = 0; x < width; x++)
            {
                rowPixels[x] = pixels[representativeRow * width + x];
            }

            // Identify the mortar color as the darkest color present in this row rather than
            // hardcoding its authored RGB value, since mortar is always the darkest tone by
            // design; this keeps the test grounded in actual output instead of duplicating
            // implementation constants.
            var mortarColor = rowPixels[0];
            var mortarBrightness = mortarColor.r + mortarColor.g + mortarColor.b;
            foreach (var candidate in rowPixels)
            {
                var brightness = candidate.r + candidate.g + candidate.b;
                if (brightness < mortarBrightness)
                {
                    mortarColor = candidate;
                    mortarBrightness = brightness;
                }
            }

            var isMortar = new bool[width];
            for (var x = 0; x < width; x++)
            {
                isMortar[x] = rowPixels[x].Equals(mortarColor);
            }

            var firstNonMortar = -1;
            for (var x = 0; x < width; x++)
            {
                if (!isMortar[x])
                {
                    firstNonMortar = x;
                    break;
                }
            }

            Assert.GreaterOrEqual(firstNonMortar, 0,
                "Expected at least one non-mortar brick pixel on the representative wall course row.");

            var runLengths = new List<int>();
            var currentRunLength = 0;
            for (var step = 0; step < width; step++)
            {
                var x = (firstNonMortar + step) % width;
                if (!isMortar[x])
                {
                    currentRunLength++;
                }
                else if (currentRunLength > 0)
                {
                    runLengths.Add(currentRunLength);
                    currentRunLength = 0;
                }
            }
            if (currentRunLength > 0) runLengths.Add(currentRunLength);

            Assert.GreaterOrEqual(runLengths.Count, 2,
                "Expected multiple brick runs on the representative wall course row to meaningfully compare " +
                "their lengths.");

            for (var i = 1; i < runLengths.Count; i++)
            {
                Assert.AreEqual(runLengths[0], runLengths[i],
                    "AC-001: every brick run between mortar joints on this wall course must have equal length " +
                    "when the texture is tiled end-to-end, exactly as PaintWallRun repeats this same unshifted " +
                    "wall texture across adjacent one-cell segments; an unequal run at the wrap boundary is the " +
                    "cut-off-brick / pattern-phase-reset seam human runtime validation observed.");
            }
        }

        // NSC-042 AC-003 / VAL-001: a wall of approximately 100 cells must not require ~100
        // uniquely authored Tile assets and must repeat continuously without gaps. This drives
        // the actual reusable PaintWallRun helper directly at representative wall lengths (the
        // completion gate's stated 3/10/100-cell cases) against an in-memory Tilemap/Tile,
        // proving every segment of even a ~100-cell run reuses one shared Tile asset instance
        // and that the run contains no missing cells.
        [TestCase(3)]
        [TestCase(10)]
        [TestCase(100)]
        public void PaintWallRun_PaintsExactCellCountReusingOneSharedTileAssetRegardlessOfWallLength(int cellCount)
        {
            var gridObject = new GameObject("NSC042_TestWallGrid");
            var tile = ScriptableObject.CreateInstance<Tile>();
            try
            {
                var grid = gridObject.AddComponent<Grid>();
                grid.cellLayout = GridLayout.CellLayout.IsometricZAsY;

                var tilemapObject = new GameObject("TestWallTilemap");
                tilemapObject.transform.SetParent(gridObject.transform, false);
                var tilemap = tilemapObject.AddComponent<Tilemap>();
                tilemapObject.AddComponent<TilemapRenderer>();

                var method = typeof(DoorPrototypeSceneBuilder).GetMethod(
                    "PaintWallRun", BindingFlags.NonPublic | BindingFlags.Static);
                Assert.IsNotNull(method,
                    "Expected a private static PaintWallRun(Tilemap, Vector3Int, int, TileBase) helper.");

                method.Invoke(null, new object[] { tilemap, new Vector3Int(0, 0, 0), cellCount, tile });

                var paintedCellCount = 0;
                foreach (var cell in tilemap.cellBounds.allPositionsWithin)
                {
                    if (tilemap.HasTile(cell)) paintedCellCount++;
                }

                Assert.AreEqual(cellCount, paintedCellCount,
                    $"AC-003/VAL-001: a {cellCount}-cell wall run must produce exactly {cellCount} visual " +
                    "segments with no gaps.");

                for (var i = 0; i < cellCount; i++)
                {
                    var expectedCell = new Vector3Int(i, -i, 0);
                    Assert.IsTrue(tilemap.HasTile(expectedCell),
                        $"Expected a continuous segment {i} of the {cellCount}-cell run at {expectedCell}.");
                    Assert.AreSame(tile, tilemap.GetTile(expectedCell),
                        "AC-003: every segment of a wall run - including a ~100-cell wall - must reuse the " +
                        "exact same reusable Tile asset instead of a uniquely authored Tile per cell, so asset " +
                        "count does not grow proportionally to wall length.");
                }
            }
            finally
            {
                Object.DestroyImmediate(tile);
                Object.DestroyImmediate(gridObject);
            }
        }

        // NSC-042: ArchitecturalTileVisualMatches now compares actual pixel content, not just
        // structural metadata (dimensions/pivot/PPU), so a previously-persisted Tile asset whose
        // pixel content predates a procedural-art revision (such as this task's brick-repeat
        // fix) is reconciled on rebuild instead of silently left stale on disk
        // (ENGINEERING_STANDARDS.md 12). Uses the persistence-aware temporary-folder seam so the
        // canonical WallTile.asset is never touched.
        [Test]
        public void Build_ExistingArchitecturalTileWithStalePixelContent_IsRegeneratedToMatchCurrentProceduralArt()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            var wallTilePath = temporaryArchitecturalTileAssetFolder + "/WallTile.asset";
            var wallTile = AssetDatabase.LoadAssetAtPath<Tile>(wallTilePath);
            Assert.IsNotNull(wallTile, "Expected a persisted WallTile.asset after the first build.");

            var texture = wallTile.sprite.texture;
            var freshPixels = texture.GetPixels32();

            // Simulate a previously-persisted tile whose pixel content predates a procedural-art
            // revision even though its structural dimensions/pivot/PPU still match the currently
            // expected values, so only the new pixel-content comparison can detect the drift.
            var stalePixels = new Color32[freshPixels.Length];
            for (var i = 0; i < stalePixels.Length; i++) stalePixels[i] = new Color32(1, 2, 3, 255);
            texture.SetPixels32(stalePixels);
            texture.Apply(false, false);
            EditorUtility.SetDirty(texture);
            AssetDatabase.SaveAssetIfDirty(texture);

            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            var rebuiltWallTile = AssetDatabase.LoadAssetAtPath<Tile>(wallTilePath);
            Assert.IsNotNull(rebuiltWallTile);
            var rebuiltPixels = rebuiltWallTile.sprite.texture.GetPixels32();

            CollectionAssert.AreEqual(freshPixels, rebuiltPixels,
                "A previously-persisted architectural Tile whose pixel content no longer matches the current " +
                "procedural art (with unchanged structural metadata) must be regenerated on rebuild rather than " +
                "left stale on disk.");
        }

        [Test]
        public void Build_DoorwayBlocker_IsSeparateBoxColliderWiredToDoorInteractable()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var doorVisual = GameObject.Find("DoorRoot/DoorVisual");
            var door = GameObject.Find("DoorRoot")?.GetComponent<DoorInteractable>();
            Assert.IsNotNull(doorVisual);
            Assert.IsNotNull(door);

            var boxCollider = doorVisual.GetComponent<BoxCollider>();
            Assert.IsNotNull(boxCollider, "Expected a BoxCollider directly on DoorVisual for gameplay collision.");
            Assert.IsFalse(boxCollider.isTrigger, "The doorway blocker must remain a solid (non-trigger) collider.");

            var serializedDoor = new SerializedObject(door);
            Assert.AreEqual(boxCollider, serializedDoor.FindProperty("doorwayBlocker").objectReferenceValue,
                "DoorInteractable must remain wired to DoorVisual's own BoxCollider as its doorwayBlocker, " +
                "independent from the new SpriteRenderer visual child.");
            Assert.AreEqual(doorVisual, serializedDoor.FindProperty("doorVisual").objectReferenceValue);

            var doorSprite = GameObject.Find("DoorRoot/DoorVisual/DoorSprite");
            Assert.IsNotNull(doorSprite);
            Assert.IsNull(doorSprite.GetComponent<Collider>(),
                "The sprite visual child must not carry gameplay collision; DoorVisual's own BoxCollider owns it.");
        }

        // NSC-039 AC-001, mirrors Build_PersistentArchitecturalTiles_AreTemporaryReusableVisualOnlyAssets:
        // world-space sprite/texture assets follow the same caller-owned-folder persistence
        // split as architectural tiles so their sprite references survive the saved/reopened
        // canonical scene, and rebuilding reuses rather than duplicates them.
        [Test]
        public void Build_PersistentWorldSpriteAssets_AreReusableVisualOnlyAssetsInTemporaryFolder()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            var doorSprite = GameObject.Find("DoorRoot/DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>().sprite;
            var wizardSprite = GameObject.Find("Player/Visual")?.GetComponent<SpriteRenderer>().sprite;
            Assert.IsNotNull(doorSprite);
            Assert.IsNotNull(wizardSprite);

            Assert.IsTrue(AssetDatabase.Contains(doorSprite));
            Assert.IsTrue(AssetDatabase.Contains(wizardSprite));
            StringAssert.StartsWith(temporaryArchitecturalTileAssetFolder + "/", AssetDatabase.GetAssetPath(doorSprite));
            StringAssert.StartsWith(temporaryArchitecturalTileAssetFolder + "/", AssetDatabase.GetAssetPath(wizardSprite));
            Assert.IsNotNull(doorSprite.texture);
            Assert.IsNotNull(wizardSprite.texture);

            DoorPrototypeSceneBuilder.BuildInMemoryForTests(temporaryArchitecturalTileAssetFolder);

            var doorSpriteAfterRebuild = GameObject.Find("DoorRoot/DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>().sprite;
            var wizardSpriteAfterRebuild = GameObject.Find("Player/Visual")?.GetComponent<SpriteRenderer>().sprite;
            Assert.AreEqual(doorSprite, doorSpriteAfterRebuild,
                "Rebuilding with the same temporary folder must reuse the existing DoorSprite asset rather " +
                "than duplicating it.");
            Assert.AreEqual(wizardSprite, wizardSpriteAfterRebuild,
                "Rebuilding with the same temporary folder must reuse the existing Visual sprite asset rather " +
                "than duplicating it.");
        }

        // NSC-039 regression, mirrors BuildInMemory_TransientArchitecturalObjects_AreDestroyedOnRebuild:
        // the parameterless in-memory test seam must destroy the previous build's transient
        // world sprite Sprite/Texture pair before creating the replacement, the same as
        // architectural tiles.
        [Test]
        public void BuildInMemory_TransientWorldSpriteObjects_AreDestroyedOnRebuild()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            var oldDoorSprite = GameObject.Find("DoorRoot/DoorVisual/DoorSprite").GetComponent<SpriteRenderer>().sprite;
            var oldDoorTexture = oldDoorSprite.texture;
            var oldWizardSprite = GameObject.Find("Player/Visual").GetComponent<SpriteRenderer>().sprite;
            var oldWizardTexture = oldWizardSprite.texture;

            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            Assert.IsTrue(oldDoorSprite == null,
                "Previous transient DoorSprite Sprite must be destroyed before rebuilding.");
            Assert.IsTrue(oldDoorTexture == null,
                "Previous transient DoorSprite Texture must be destroyed before rebuilding.");
            Assert.IsTrue(oldWizardSprite == null,
                "Previous transient wizard Sprite must be destroyed before rebuilding.");
            Assert.IsTrue(oldWizardTexture == null,
                "Previous transient wizard Texture must be destroyed before rebuilding.");

            var newDoorSprite = GameObject.Find("DoorRoot/DoorVisual/DoorSprite").GetComponent<SpriteRenderer>().sprite;
            var newWizardSprite = GameObject.Find("Player/Visual").GetComponent<SpriteRenderer>().sprite;
            Assert.IsNotNull(newDoorSprite);
            Assert.IsFalse(AssetDatabase.Contains(newDoorSprite));
            Assert.IsNotNull(newWizardSprite);
            Assert.IsFalse(AssetDatabase.Contains(newWizardSprite));
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

    // NSC-041 VAL-002 (human-review correction): the previous DoorInteractionFeedback hover
    // coverage built its own top-down camera at (0,10,0) with a zero-offset DoorInteractable, so
    // it never exercised the production fixed isometric camera or the production
    // groundSelectionOffset that aligns a visible door click/hover with the ground-plane
    // selection point. This mirrors DoorPrototypeSceneBuilderClickSelectionTests: it builds the
    // real scene, uses the real generated Main Camera and DoorRoot/DoorVisual, and drives
    // DoorInteractionFeedback's hover state through PlayerMovement's shared pointer target
    // produced from simulated mouse input under that real camera.
    public class DoorPrototypeSceneBuilderHoverFeedbackTests : InputTestFixture
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

        // AC-002/AC-005/VAL-002: for representative points on and off the visible door - the
        // visual's own world center (already proven clickable/selectable by
        // DoorPrototypeSceneBuilderClickSelectionTests), the door's real production selection
        // anchor, a point still inside its selection radius, and a point clearly outside it -
        // hover feedback driven through the real built Main Camera must match both the expected
        // on/off result and DoorInteractable's own production selection test against the shared
        // PlayerMovement pointer target, proving feedback does not implement a second independent
        // screen-to-world projection.
        [Test]
        public void Build_HoverFeedback_AgreesWithDoorsOwnSelectionTest_ForRepresentativeVisibleDoorPoints()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var playerObject = GameObject.Find("Player");
            var movement = playerObject != null ? playerObject.GetComponent<PlayerMovement>() : null;
            var interactionController =
                playerObject != null ? playerObject.GetComponent<PlayerInteractionController>() : null;
            var doorRoot = GameObject.Find("DoorRoot");
            var door = doorRoot != null ? doorRoot.GetComponent<DoorInteractable>() : null;
            var feedback = doorRoot != null ? doorRoot.GetComponent<DoorInteractionFeedback>() : null;
            var doorVisual = GameObject.Find("DoorRoot/DoorVisual");
            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();

            Assert.IsNotNull(movement, "Expected a PlayerMovement on the generated Player.");
            Assert.IsNotNull(interactionController,
                "Expected a PlayerInteractionController on the generated Player.");
            Assert.IsNotNull(door, "Expected a DoorInteractable on the generated DoorRoot.");
            Assert.IsNotNull(feedback, "Expected a DoorInteractionFeedback on the generated DoorRoot.");
            Assert.IsNotNull(doorVisual, "Expected a DoorVisual child under DoorRoot.");
            Assert.IsNotNull(camera, "Expected a Camera on the generated Main Camera.");

            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
            camera.targetTexture = testRenderTexture;

            InvokePrivate(movement, "Awake");
            InvokePrivate(movement, "OnEnable");
            InvokePrivate(interactionController, "Awake");
            InvokePrivate(interactionController, "OnEnable");
            InvokePrivate(door, "OnEnable");

            try
            {
                var candidateWorldPoints = new[]
                {
                    doorVisual.transform.position,
                    door.SelectionPoint,
                    door.SelectionPoint + new Vector3(1f, 0f, 0f),
                    door.SelectionPoint + new Vector3(20f, 0f, 20f)
                };
                var candidateExpectedHover = new[] { true, true, true, false };
                var candidateLabels = new[]
                {
                    "visible door visual center",
                    "door's production selection anchor",
                    "inside selection radius",
                    "far outside selection radius"
                };

                for (var i = 0; i < candidateWorldPoints.Length; i++)
                {
                    var screenPoint = camera.WorldToScreenPoint(candidateWorldPoints[i]);
                    SetMouse(screenPoint, false);

                    movement.Tick(0.02f);
                    feedback.Tick(0.02f);

                    Assert.IsTrue(movement.HasPointerWorldTarget,
                        "Expected PlayerMovement to have produced a shared world-space pointer target for " +
                        $"candidate '{candidateLabels[i]}'.");

                    Assert.AreEqual(candidateExpectedHover[i], feedback.IsHovered,
                        $"AC-002/VAL-002: hover feedback did not match the expected on/off result for " +
                        $"candidate '{candidateLabels[i]}' under the production camera.");

                    var expectedFromDoorsOwnTest = door.TryGetSelectionDistance(movement.PointerWorldTarget, out _);
                    Assert.AreEqual(expectedFromDoorsOwnTest, feedback.IsHovered,
                        $"AC-005/VAL-002: hover feedback must exactly agree with DoorInteractable's own " +
                        $"production selection test against the shared pointer target, for candidate " +
                        $"'{candidateLabels[i]}'.");
                }
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
