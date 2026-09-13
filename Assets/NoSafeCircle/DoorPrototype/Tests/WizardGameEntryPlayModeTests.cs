using System.Collections;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class WizardGameEntryPlayModeTests : InputTestFixture
    {
        private static readonly WizardPresentation[] ExpectedPresentations =
        {
            WizardPresentation.Masculine,
            WizardPresentation.Masculine,
            WizardPresentation.Feminine,
            WizardPresentation.Feminine
        };

        private static readonly WizardSkin[] ExpectedSkins =
        {
            WizardSkin.White,
            WizardSkin.Black,
            WizardSkin.White,
            WizardSkin.Black
        };

        private Mouse mouseDevice;
        private RenderTexture testRenderTexture;
        private Camera renderCamera;

        public override void Setup()
        {
            base.Setup();
            mouseDevice = InputSystem.AddDevice<Mouse>();
        }

        public override void TearDown()
        {
            DetachTestRenderTexture();
            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                Object.Destroy(testRenderTexture);
            }

            testRenderTexture = null;
            renderCamera = null;
            mouseDevice = null;
            base.TearDown();
        }

        // NSC-068 AC-001/AC-002/AC-003/AC-005 and VAL-001/VAL-003: every confirmed
        // option updates the same complete Player at the established spawn and stays selected
        // while that Player moves with its existing collision, animation, and sorting setup.
        [UnityTest]
        public IEnumerator EachConfirmedOption_EntersWithExactPresentationOnSamePlayer()
        {
            for (var optionIndex = 0; optionIndex < ExpectedPresentations.Length; optionIndex++)
            {
                yield return LoadDoorPrototypeScene();

                Scene scene = SceneManager.GetSceneByName("DoorPrototype");
                GameObject player = FindRoot(scene, "Player");
                GameObject playerSpawn = FindRoot(scene, "PlayerSpawn");
                GameObject canvas = FindRoot(scene, "Canvas");
                WizardSelectionController selection = canvas.GetComponent<WizardSelectionController>();
                WizardGameEntryController entry = canvas.GetComponent<WizardGameEntryController>();
                WizardAnimationController wizard = player.GetComponent<WizardAnimationController>();
                PlayerMovement movement = player.GetComponent<PlayerMovement>();
                PlayerInteractionController interaction = player.GetComponent<PlayerInteractionController>();
                CharacterController characterController = player.GetComponent<CharacterController>();
                SpriteRenderer renderer = player.transform.Find("Visual")?.GetComponent<SpriteRenderer>();

                Assert.IsNotNull(selection);
                Assert.IsNotNull(entry);
                Assert.IsNotNull(wizard);
                Assert.IsNotNull(movement);
                Assert.IsNotNull(interaction);
                Assert.IsNotNull(characterController);
                Assert.IsNotNull(renderer);

                Component[] originalComponents = player.GetComponents<Component>();
                Collider[] originalColliders = player.GetComponents<Collider>();
                Vector3 originalScale = player.transform.localScale;
                Vector3 originalVisualLocalPosition = renderer.transform.localPosition;
                string originalSortingLayer = renderer.sortingLayerName;
                int originalSortingOrder = renderer.sortingOrder;
                SpriteSortPoint originalSortPoint = renderer.spriteSortPoint;
                Sprite expectedIdleSprite = selection.GetOption(optionIndex).PreviewSprite;

                player.transform.position = playerSpawn.transform.position + new Vector3(2f, 0f, -1f);
                Assert.AreNotEqual(playerSpawn.transform.position, player.transform.position);

                BeginSelection(canvas);
                selection.GetOption(optionIndex).Button.onClick.Invoke();
                ConfirmSelection(canvas);

                var expectedSelection = new ConfirmedWizardSelection(
                    ExpectedPresentations[optionIndex], ExpectedSkins[optionIndex]);
                Assert.IsTrue(entry.HasEnteredGameplay);
                Assert.AreEqual(1, entry.GameplayEntryCount);
                Assert.AreEqual(expectedSelection, entry.AppliedSelection);
                Assert.AreEqual(expectedSelection, selection.ConfirmedSelection);
                Assert.AreEqual(ExpectedPresentations[optionIndex], wizard.Presentation);
                Assert.AreEqual(ExpectedSkins[optionIndex], wizard.Skin);
                Assert.AreEqual(playerSpawn.transform.position, player.transform.position);
                Assert.AreEqual(playerSpawn.transform.rotation, player.transform.rotation);
                Assert.AreSame(expectedIdleSprite, renderer.sprite,
                    "The world entry must display the confirmed option's integrated idle Sprite immediately.");
                Assert.IsFalse(canvas.transform.Find("TitleScreen").gameObject.activeSelf);
                Assert.IsFalse(canvas.transform.Find("WizardSelectionScreen").gameObject.activeSelf);
                Assert.IsTrue(movement.IsGameplayEnabled);
                Assert.IsTrue(interaction.IsGameplayEnabled);

                Assert.AreSame(player, FindRoot(scene, "Player"));
                Assert.AreEqual(1, scene.GetRootGameObjects().Count(root => root.name == "Player"));
                CollectionAssert.AreEqual(originalComponents, player.GetComponents<Component>());
                CollectionAssert.AreEqual(originalColliders, player.GetComponents<Collider>());
                Assert.AreEqual(originalScale, player.transform.localScale);
                Assert.AreEqual(originalVisualLocalPosition, renderer.transform.localPosition);
                Assert.AreEqual(originalSortingLayer, renderer.sortingLayerName);
                Assert.AreEqual(originalSortingOrder, renderer.sortingOrder);
                Assert.AreEqual(originalSortPoint, renderer.spriteSortPoint);
                Assert.IsTrue(characterController.enabled);

                yield return null;
                movement.RequestDestination(playerSpawn.transform.position + new Vector3(1f, 0f, -1f));
                movement.Tick(0.1f);
                yield return null;

                string expectedWalkState =
                    $"Wizard_{ExpectedPresentations[optionIndex]}_{ExpectedSkins[optionIndex]}_walk_south-east";
                Assert.AreEqual(expectedWalkState, wizard.CurrentState);
                Assert.AreEqual(ExpectedPresentations[optionIndex], wizard.Presentation);
                Assert.AreEqual(ExpectedSkins[optionIndex], wizard.Skin);
                Assert.AreSame(player, FindRoot(scene, "Player"));

                movement.SuspendGameplayInput();
                interaction.SuspendGameplayInput();
                entry.EnterWorld(expectedSelection);
                selection.ConfirmSelection();

                Assert.AreEqual(1, entry.GameplayEntryCount,
                    "Repeated entry callbacks must be ignored after the one completed handoff.");
                Assert.IsFalse(movement.IsGameplayEnabled,
                    "A duplicate callback would reveal an extra movement EnableGameplayInput call here.");
                Assert.IsFalse(interaction.IsGameplayEnabled,
                    "A duplicate callback would reveal an extra interaction EnableGameplayInput call here.");
                Assert.AreEqual(1, scene.GetRootGameObjects().Count(root => root.name == "Player"));
            }
        }

        // NSC-068 AC-004 and VAL-002: Start Game alone cannot bypass the required selection.
        [UnityTest]
        public IEnumerator StartWithoutSelection_LeavesGameplaySuspendedAndPlayerUnchanged()
        {
            yield return LoadDoorPrototypeScene();

            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            GameObject player = FindRoot(scene, "Player");
            GameObject canvas = FindRoot(scene, "Canvas");
            WizardSelectionController selection = canvas.GetComponent<WizardSelectionController>();
            WizardGameEntryController entry = canvas.GetComponent<WizardGameEntryController>();
            PlayerMovement movement = player.GetComponent<PlayerMovement>();
            PlayerInteractionController interaction = player.GetComponent<PlayerInteractionController>();

            BeginSelection(canvas);
            ConfirmSelection(canvas);

            Assert.IsFalse(selection.ConfirmedSelection.HasValue);
            Assert.IsFalse(entry.HasEnteredGameplay);
            Assert.AreEqual(0, entry.GameplayEntryCount);
            Assert.IsFalse(movement.IsGameplayEnabled);
            Assert.IsFalse(interaction.IsGameplayEnabled);
            Assert.AreEqual(1, scene.GetRootGameObjects().Count(root => root.name == "Player"));
        }

        // Vincent's reported regression path: the real title and selection buttons hand off
        // to both input owners, then the scene's real mouse actions move the selected Player.
        [UnityTest]
        public IEnumerator StartChooseConfirm_EnablesOwnersAndMouseMovementAndDoorSelection()
        {
            yield return LoadDoorPrototypeScene();

            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            GameObject player = FindRoot(scene, "Player");
            GameObject playerSpawn = FindRoot(scene, "PlayerSpawn");
            GameObject canvas = FindRoot(scene, "Canvas");
            Camera camera = FindRoot(scene, "Main Camera").GetComponent<Camera>();
            PlayerMovement movement = player.GetComponent<PlayerMovement>();
            PlayerInteractionController interaction = player.GetComponent<PlayerInteractionController>();
            WizardSelectionController selection = canvas.GetComponent<WizardSelectionController>();
            WizardGameEntryController entry = canvas.GetComponent<WizardGameEntryController>();
            DoorInteractable door = FindRoot(scene, "DoorRoot").GetComponent<DoorInteractable>();

            Assert.IsNotNull(camera);
            Assert.IsNotNull(door);
            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
            camera.targetTexture = testRenderTexture;
            renderCamera = camera;

            BeginSelection(canvas);
            selection.GetOption(3).Button.onClick.Invoke();
            ConfirmSelection(canvas);

            Assert.IsTrue(entry.HasEnteredGameplay);
            Assert.IsTrue(movement.IsGameplayEnabled);
            Assert.IsTrue(interaction.IsGameplayEnabled);

            yield return null;
            Vector3 startPosition = player.transform.position;
            Vector3 target = playerSpawn.transform.position + new Vector3(-1.5f, 0f, -1.5f);
            SetMouse(camera.WorldToScreenPoint(target), true);
            movement.Tick(0.02f);
            SetMouse(camera.WorldToScreenPoint(target), false);
            movement.Tick(0.02f);

            Assert.IsTrue(movement.HasActiveDestination,
                "The post-confirmation mouse press must reach the scene's PlayerMovement owner.");
            AdvanceMovementTime(movement, 1f);
            yield return null;

            Assert.Greater(HorizontalDistance(startPosition, player.transform.position), 0.5f);
            Assert.Less(HorizontalDistance(target, player.transform.position), 0.2f);

            movement.CancelRequestedDestination();
            Assert.IsTrue(interaction.TryBeginDoorApproach(door.SelectionPoint),
                "The same confirmed flow must also enable the scene's door-selection owner.");
            Assert.AreSame(door, interaction.PendingDoor);
            Assert.AreEqual(1, scene.GetRootGameObjects().Count(root => root.name == "Player"));
        }

        [UnityTearDown]
        public IEnumerator UnloadCanonicalSceneWithoutSaving()
        {
            DetachTestRenderTexture();
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            Scene cleanupScene = SceneManager.CreateScene("WizardGameEntryTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }

        private void DetachTestRenderTexture()
        {
            if (renderCamera != null && renderCamera.targetTexture == testRenderTexture)
            {
                renderCamera.targetTexture = null;
            }
        }

        private static IEnumerator LoadDoorPrototypeScene()
        {
            yield return SceneManager.LoadSceneAsync("DoorPrototype", LoadSceneMode.Single);
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            Assert.IsTrue(scene.IsValid() && scene.isLoaded);
        }

        private static GameObject FindRoot(Scene scene, string name)
        {
            GameObject result = scene.GetRootGameObjects().SingleOrDefault(root => root.name == name);
            Assert.IsNotNull(result, $"Expected one '{name}' root in {scene.path}.");
            return result;
        }

        private static void BeginSelection(GameObject canvas)
        {
            Button startButton = canvas.transform
                .Find("TitleScreen/TitleCard/StartGameButton")?.GetComponent<Button>();
            Assert.IsNotNull(startButton);
            startButton.onClick.Invoke();
        }

        private static void ConfirmSelection(GameObject canvas)
        {
            Button confirmButton = canvas.transform
                .Find("WizardSelectionScreen/ConfirmSelectionButton")?.GetComponent<Button>();
            Assert.IsNotNull(confirmButton);
            confirmButton.onClick.Invoke();
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

        private static void AdvanceMovementTime(PlayerMovement movement, float totalSeconds)
        {
            const float step = 0.05f;
            var elapsed = 0f;
            while (elapsed < totalSeconds)
            {
                float deltaTime = Mathf.Min(step, totalSeconds - elapsed);
                movement.Tick(deltaTime);
                elapsed += deltaTime;
            }
        }

        private static float HorizontalDistance(Vector3 from, Vector3 to)
        {
            Vector3 offset = to - from;
            offset.y = 0f;
            return offset.magnitude;
        }
    }
}
