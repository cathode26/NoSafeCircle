using System.Linq;
using NoSafeCircle.DoorPrototype.Editor;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.SceneManagement;
using UnityEngine.Tilemaps;
using UnityEngine.UI;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public class TitleScreenSceneBuilderTests
    {
        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        // NSC-066 AC-005/VAL-002: the non-saving builder seam is run twice in one scene and
        // must still leave one title hierarchy and one persistent Start Game listener path.
        [Test]
        public void Build_RunTwice_LeavesOneTitleScreenAndOneStartListener()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            Scene scene = SceneManager.GetActiveScene();
            GameObject[] roots = scene.GetRootGameObjects();
            Assert.AreEqual(1, roots.Count(root => root.name == "Canvas"));
            Assert.AreEqual(1, roots.Count(root => root.name == "EventSystem"));

            TitleScreenController[] controllers = Resources.FindObjectsOfTypeAll<TitleScreenController>()
                .Where(controller => controller.gameObject.scene == scene)
                .ToArray();
            Assert.AreEqual(1, controllers.Length);
            Assert.AreEqual(1, Resources.FindObjectsOfTypeAll<TitleScreenChaseBackdrop>()
                .Count(backdrop => backdrop.gameObject.scene == scene));
            Assert.AreEqual(1, Resources.FindObjectsOfTypeAll<TitleScreenGameplayHudVisibility>()
                .Count(visibility => visibility.gameObject.scene == scene));

            Transform canvas = roots.Single(root => root.name == "Canvas").transform;
            Transform[] titlePanels = canvas.Cast<Transform>()
                .Where(child => child.name == "TitleScreen")
                .ToArray();
            Assert.AreEqual(1, titlePanels.Length);

            Button[] startButtons = titlePanels[0].GetComponentsInChildren<Button>(true)
                .Where(button => button.name == "StartGameButton")
                .ToArray();
            Assert.AreEqual(1, startButtons.Length);
            Assert.AreEqual(1, startButtons[0].onClick.GetPersistentEventCount());
            Assert.AreSame(controllers[0], startButtons[0].onClick.GetPersistentTarget(0));
            Assert.AreEqual(
                nameof(TitleScreenController.StartGame),
                startButtons[0].onClick.GetPersistentMethodName(0));
        }

        // The title remains interactive while the live world and chase remain visible behind it.
        [Test]
        public void Build_TitleScreen_IsTransparentAndLeftStacked()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            GameObject canvasObject = GameObject.Find("Canvas");
            Assert.IsNotNull(canvasObject);

            CanvasScaler scaler = canvasObject.GetComponent<CanvasScaler>();
            Assert.IsNotNull(scaler);
            Assert.AreEqual(CanvasScaler.ScaleMode.ScaleWithScreenSize, scaler.uiScaleMode);
            Assert.AreEqual(new Vector2(1920f, 1080f), scaler.referenceResolution);

            Transform titlePanel = canvasObject.transform.Find("TitleScreen");
            Assert.IsNotNull(titlePanel);
            RectTransform panelRect = titlePanel.GetComponent<RectTransform>();
            Assert.AreEqual(Vector2.zero, panelRect.anchorMin);
            Assert.AreEqual(Vector2.one, panelRect.anchorMax);

            Image panelImage = titlePanel.GetComponent<Image>();
            Assert.IsNotNull(panelImage);
            Assert.AreEqual(0f, panelImage.color.a, 0.001f);
            Assert.IsTrue(panelImage.raycastTarget);

            Transform card = titlePanel.Find("TitleCard");
            Assert.IsNotNull(card);
            Assert.LessOrEqual(card.GetComponent<RectTransform>().anchorMax.x, 0.5f);
            Assert.IsNull(card.GetComponent<Image>());
            Assert.IsNull(card.GetComponent<Outline>());

            Text eyebrow = card.Find("Eyebrow")?.GetComponent<Text>();
            Text title = card.Find("Title")?.GetComponent<Text>();
            Text tagline = card.Find("Tagline")?.GetComponent<Text>();
            Assert.IsNotNull(eyebrow);
            Assert.IsNotNull(title);
            Assert.IsNotNull(tagline);
            Assert.AreEqual("WELCOME, TINY WIZARD", eyebrow.text);
            Assert.AreEqual("NO SAFE CIRCLE", title.text);
            Assert.AreEqual("Cute wizards. Terrible odds.", tagline.text);
            foreach (Text saying in new[] { eyebrow, title, tagline })
            {
                Assert.LessOrEqual(saying.rectTransform.anchorMax.x, 0.5f);
                Assert.AreEqual(TextAnchor.MiddleLeft, saying.alignment);
            }

            Button button = titlePanel.Find("TitleCard/StartGameButton")?.GetComponent<Button>();
            Text buttonText = titlePanel.Find("TitleCard/StartGameButton/Text")?.GetComponent<Text>();
            Assert.IsNotNull(button);
            Assert.IsNotNull(buttonText);
            Assert.AreEqual("START GAME", buttonText.text);
            Assert.GreaterOrEqual(button.GetComponent<RectTransform>().rect.width, 300f);
            Assert.LessOrEqual(button.GetComponent<RectTransform>().anchorMax.x, 0.5f);
            Assert.AreEqual((Color)new Color32(152, 65, 119, 255), button.targetGraphic.color);
            Assert.AreEqual((Color)new Color32(255, 211, 225, 255), button.colors.highlightedColor);
            Assert.AreEqual((Color)new Color32(205, 145, 178, 255), button.colors.pressedColor);

            EventSystem eventSystem = Object.FindFirstObjectByType<EventSystem>();
            Assert.IsNotNull(eventSystem);
            Assert.IsNotNull(eventSystem.GetComponent<InputSystemUIInputModule>());

            SerializedObject controller = new SerializedObject(canvasObject.GetComponent<TitleScreenController>());
            Assert.AreSame(
                GameObject.Find("Player").GetComponent<PlayerMovement>(),
                controller.FindProperty("playerMovement").objectReferenceValue);
            Assert.AreSame(
                GameObject.Find("Player").GetComponent<PlayerInteractionController>(),
                controller.FindProperty("playerInteractionController").objectReferenceValue);
            Assert.AreEqual(2, controller.FindProperty("gameplayInputBehaviours").arraySize);
        }

        [Test]
        public void Build_ChaseHasAssetsAndFloorLineThroughViewCentre()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            Camera camera = GameObject.Find("Main Camera").GetComponent<Camera>();
            GameObject canvas = GameObject.Find("Canvas");
            TitleScreenChaseBackdrop backdrop = canvas.GetComponent<TitleScreenChaseBackdrop>();
            Assert.IsNotNull(backdrop);

            SerializedObject serialized = new SerializedObject(backdrop);
            Assert.AreSame(canvas.GetComponent<TitleScreenController>(),
                serialized.FindProperty("titleScreen").objectReferenceValue);
            Assert.AreSame(camera, serialized.FindProperty("chaseCamera").objectReferenceValue);
            Assert.IsNotNull(serialized.FindProperty("wizardAnimatorController").objectReferenceValue);
            Assert.IsNotNull(serialized.FindProperty("meleeAnimatorController").objectReferenceValue);
            Assert.IsNotNull(serialized.FindProperty("wraithAnimatorController").objectReferenceValue);
            Assert.AreEqual(4, serialized.FindProperty("wizardChoices").arraySize);
            Assert.AreEqual(1f, serialized.FindProperty("wizardVisualScale").floatValue);
            Assert.AreEqual(2f, serialized.FindProperty("pursuerVisualScale").floatValue);

            Vector3 start = serialized.FindProperty("floorSegmentStart").vector3Value;
            Vector3 end = serialized.FindProperty("floorSegmentEnd").vector3Value;
            foreach (Vector3 endpoint in new[] { start, end })
            {
                Assert.That(endpoint.x, Is.InRange(-12.5f, 12.5f));
                Assert.That(endpoint.z, Is.InRange(-24.5f, -1.5f));
                Assert.AreEqual(0f, endpoint.y, 0.001f);
                Assert.AreEqual(0.5f, camera.WorldToViewportPoint(endpoint).y, 0.001f);
            }
            Assert.Greater(Vector3.Distance(start, end), 6f);
            Assert.That(Vector3.Dot((end - start).normalized, new Vector3(1f, 0f, 1f).normalized),
                Is.EqualTo(1f).Within(0.001f));
        }

        [Test]
        public void Build_GameplayHudIsHiddenUntilStartGame()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            GameObject canvas = GameObject.Find("Canvas");
            Assert.IsNotNull(canvas.GetComponent<TitleScreenGameplayHudVisibility>());
            string[] gameplayNames =
            {
                "InteractPrompt", "ProgressFill", "HealthFill", "ManaFill",
                "DebugDamageButton", "DebugManaSpendButton", "ControlsHud"
            };
            foreach (string name in gameplayNames)
            {
                CanvasGroup group = canvas.transform.Find(name)?.GetComponent<CanvasGroup>();
                Assert.IsNotNull(group, name);
                Assert.AreEqual(0f, group.alpha, name);
                Assert.IsFalse(group.blocksRaycasts, name);
            }

            canvas.GetComponent<TitleScreenController>().StartGame();
            foreach (string name in gameplayNames)
            {
                CanvasGroup group = canvas.transform.Find(name).GetComponent<CanvasGroup>();
                Assert.AreEqual(1f, group.alpha, name);
                Assert.IsTrue(group.blocksRaycasts, name);
            }
        }

        // NSC-039 regression-only: adding the Canvas title flow must leave the established
        // camera-axis and renderer-band sorting convention intact.
        [Test]
        public void Build_TitleScreenPreservesExistingIsometricSortingConvention()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            Camera camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();
            Assert.IsNotNull(camera);
            Assert.AreEqual(TransparencySortMode.CustomAxis, camera.transparencySortMode);
            Assert.That(
                Vector3.Distance(IsometricCameraFollow.IsometricTransparencySortAxis, camera.transparencySortAxis),
                Is.LessThan(0.0001f));

            TilemapRenderer floor = GameObject.Find("IsometricVisualGrid/FloorTilemap")
                ?.GetComponent<TilemapRenderer>();
            TilemapRenderer border = GameObject.Find("IsometricVisualGrid/ArchitecturalTilemap")
                ?.GetComponent<TilemapRenderer>();
            TilemapRenderer walls = GameObject.Find("IsometricVisualGrid/WallTilemap")
                ?.GetComponent<TilemapRenderer>();
            SpriteRenderer player = GameObject.Find("Player/Visual")?.GetComponent<SpriteRenderer>();

            Assert.IsNotNull(floor);
            Assert.IsNotNull(border);
            Assert.IsNotNull(walls);
            Assert.IsNotNull(player);
            // These read the shared constants rather than the literals they held, which makes
            // this a WIRING check and nothing more: it proves the prototype scene floor and
            // border ARE the band, and it deliberately cannot judge whether the band VALUE is
            // right, because its expectation now comes from the thing under test. The value is
            // BackgroundSortingBandTests job, computed from the catalogs. The literals that
            // used to be here passed for the wrong reason and would have kept passing while
            // 189 authored props sat underneath the floor.
            Assert.AreEqual(WorldSpriteConvention.BackgroundGroundSortingOrder, floor.sortingOrder);
            Assert.AreEqual(
                WorldSpriteConvention.BackgroundArchitecturalBorderSortingOrder, border.sortingOrder);
            Assert.AreEqual(0, walls.sortingOrder);
            Assert.AreEqual(0, player.sortingOrder);
            Assert.AreEqual(WorldSpriteConvention.SortingLayerName, walls.sortingLayerName);
            Assert.AreEqual(walls.sortingLayerName, player.sortingLayerName);
        }
    }
}
