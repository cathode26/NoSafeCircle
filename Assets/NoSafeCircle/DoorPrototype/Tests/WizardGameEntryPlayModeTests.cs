using System.Collections;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;

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
        private InputActionAsset testMovementActions;

        public override void Setup()
        {
            base.Setup();
            mouseDevice = InputSystem.AddDevice<Mouse>();
        }

        public override void TearDown()
        {
            if (testMovementActions != null)
            {
                testMovementActions.Disable();
                Object.DestroyImmediate(testMovementActions);
            }

            DetachTestRenderTexture();
            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                Object.Destroy(testRenderTexture);
            }

            testRenderTexture = null;
            renderCamera = null;
            testMovementActions = null;
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
                yield return LoadRuntimeWorldScene();

                Scene scene = SceneManager.GetSceneByName("RuntimeWorld");
                GameObject player = FindInScene(scene, "Player");
                // RuntimeWorld has no "PlayerSpawn" marker object: PlayerSpawner.Spawn() places
                // the wizard directly at RuinedEntryLayout.PlayerStart, one CharacterController
                // skinWidth above the floor (see PlayerSpawner.cs), which is what "the canonical
                // spawn" now means. Computed rather than looked up, from the same public constant
                // and the same field the runtime spawn uses.
                CharacterController playerControllerForSpawn = player.GetComponent<CharacterController>();
                Vector3 playerSpawnPosition = new Vector3(
                    RuinedEntryLayout.PlayerStart.x, playerControllerForSpawn.skinWidth, RuinedEntryLayout.PlayerStart.z);
                Quaternion playerSpawnRotation = Quaternion.identity;
                GameObject canvas = FindInScene(scene, "Canvas");
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

                player.transform.position = playerSpawnPosition + new Vector3(2f, 0f, -1f);
                Assert.AreNotEqual(playerSpawnPosition, player.transform.position);

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
                Assert.AreEqual(playerSpawnPosition, player.transform.position);
                Assert.AreEqual(playerSpawnRotation, player.transform.rotation);
                Assert.AreSame(expectedIdleSprite, renderer.sprite,
                    "The world entry must display the confirmed option's integrated idle Sprite immediately.");
                Assert.IsFalse(canvas.transform.Find("TitleScreen").gameObject.activeSelf);
                Assert.IsFalse(canvas.transform.Find("WizardSelectionScreen").gameObject.activeSelf);
                Assert.IsTrue(movement.IsGameplayEnabled);
                Assert.IsTrue(interaction.IsGameplayEnabled);

                Assert.AreSame(player, FindInScene(scene, "Player"));
                Assert.AreEqual(1, CountInScene(scene, "Player"));
                CollectionAssert.AreEqual(originalComponents, player.GetComponents<Component>());
                CollectionAssert.AreEqual(originalColliders, player.GetComponents<Collider>());
                Assert.AreEqual(originalScale, player.transform.localScale);
                Assert.AreEqual(originalVisualLocalPosition, renderer.transform.localPosition);
                Assert.AreEqual(originalSortingLayer, renderer.sortingLayerName);
                Assert.AreEqual(originalSortingOrder, renderer.sortingOrder);
                Assert.AreEqual(originalSortPoint, renderer.spriteSortPoint);
                Assert.IsTrue(characterController.enabled);

                yield return null;
                movement.RequestDestination(playerSpawnPosition + new Vector3(1f, 0f, -1f));
                movement.Tick(0.1f);
                yield return null;

                string expectedWalkStatePrefix =
                    $"Wizard_{ExpectedPresentations[optionIndex]}_{ExpectedSkins[optionIndex]}_walk_";
                StringAssert.StartsWith(expectedWalkStatePrefix, wizard.CurrentState,
                    "World entry must preserve the selected wizard while its dedicated direction owner chooses facing.");
                Assert.AreEqual(ExpectedPresentations[optionIndex], wizard.Presentation);
                Assert.AreEqual(ExpectedSkins[optionIndex], wizard.Skin);
                Assert.AreSame(player, FindInScene(scene, "Player"));

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
                Assert.AreEqual(1, CountInScene(scene, "Player"));
            }
        }

        // NSC-068 AC-004 and VAL-002: Start Game alone cannot bypass the required selection.
        [UnityTest]
        public IEnumerator StartWithoutSelection_LeavesGameplaySuspendedAndPlayerUnchanged()
        {
            yield return LoadRuntimeWorldScene();

            Scene scene = SceneManager.GetSceneByName("RuntimeWorld");
            GameObject player = FindInScene(scene, "Player");
            GameObject canvas = FindInScene(scene, "Canvas");
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
            Assert.AreEqual(1, CountInScene(scene, "Player"));
        }

        // Vincent's reported regression path: the real title and selection buttons hand off
        // to both input owners, then the scene's real mouse actions move the selected Player.
        [UnityTest]
        public IEnumerator StartChooseConfirm_EnablesOwnersAndMouseMovementAndDoorSelection()
        {
            yield return LoadRuntimeWorldScene();

            Scene scene = SceneManager.GetSceneByName("RuntimeWorld");
            GameObject player = FindInScene(scene, "Player");
            // RuntimeWorld has no "PlayerSpawn" marker object: PlayerSpawner.Spawn() places
            // the wizard directly at RuinedEntryLayout.PlayerStart, one CharacterController
            // skinWidth above the floor (see PlayerSpawner.cs), which is what "the canonical
            // spawn" now means. Computed rather than looked up, from the same public constant
            // and the same field the runtime spawn uses.
            CharacterController playerControllerForSpawn = player.GetComponent<CharacterController>();
            Vector3 playerSpawnPosition = new Vector3(
                RuinedEntryLayout.PlayerStart.x, playerControllerForSpawn.skinWidth, RuinedEntryLayout.PlayerStart.z);
            GameObject canvas = FindInScene(scene, "Canvas");
            Camera camera = Camera.main;
            PlayerMovement movement = player.GetComponent<PlayerMovement>();
            PlayerInteractionController interaction = player.GetComponent<PlayerInteractionController>();
            WizardSelectionController selection = canvas.GetComponent<WizardSelectionController>();
            WizardGameEntryController entry = canvas.GetComponent<WizardGameEntryController>();
            DoorInteractable door = FindInScene(scene, "DoorRoot").GetComponent<DoorInteractable>();

            Assert.IsNotNull(camera);
            Assert.IsNotNull(door);
            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
            camera.targetTexture = testRenderTexture;
            renderCamera = camera;
            SetPrivateField(movement, "mainCamera", camera);
            InputActionAsset sceneMovementActions = GetPrivateField<InputActionAsset>(movement, "inputActions");
            testMovementActions = Object.Instantiate(sceneMovementActions);
            InputActionMap playerMap = testMovementActions.FindActionMap("Player", true);
            playerMap.devices = new InputDevice[] { mouseDevice };
            InputAction pointerPosition = playerMap.FindAction("PointerPosition", true);
            InputAction moveToCursor = playerMap.FindAction("MoveToCursor", true);
            SetPrivateField(movement, "inputActions", testMovementActions);
            SetPrivateField(movement, "pointerPositionAction", pointerPosition);
            SetPrivateField(movement, "moveToCursorAction", moveToCursor);
            playerMap.Enable();

            BeginSelection(canvas);
            selection.GetOption(3).Button.onClick.Invoke();
            ConfirmSelection(canvas);

            Assert.IsTrue(entry.HasEnteredGameplay);
            Assert.IsTrue(movement.IsGameplayEnabled);
            Assert.IsTrue(interaction.IsGameplayEnabled);

            yield return null;
            // InputTestFixture classes earlier in the full PlayMode run may leave a final queued
            // mouse sample until the next InputSystem update. Establish a released baseline so
            // this test observes its own fresh press through the scene's real input actions.
            SetMouse(Vector2.zero, false);
            interaction.ResetInteraction();
            movement.ResetMovement();
            movement.Tick(0.02f);
            Vector3 startPosition = player.transform.position;
            Vector3 target = playerSpawnPosition + new Vector3(-1.5f, 0f, -1.5f);
            SetMouse(camera.WorldToScreenPoint(target), true);
            movement.Tick(0.02f);
            bool hadDestinationAfterPress = movement.HasActiveDestination;
            bool hadPointerTargetAfterPress = movement.HasPointerWorldTarget;
            Vector3 pointerTargetAfterPress = movement.PointerWorldTarget;
            bool hadLockedDoorAfterPress = interaction.HasLockedDoorInteraction;
            SetMouse(camera.WorldToScreenPoint(target), false);
            movement.Tick(0.02f);

            Assert.IsTrue(movement.HasActiveDestination,
                "The post-confirmation mouse press must reach the scene's PlayerMovement owner. " +
                $"AfterPress(destination={hadDestinationAfterPress}, pointer={hadPointerTargetAfterPress}, " +
                $"pointerTarget={pointerTargetAfterPress}, lockedDoor={hadLockedDoorAfterPress}); " +
                $"afterRelease(pointer={movement.HasPointerWorldTarget}, position={player.transform.position}).");
            AdvanceMovementTime(movement, 1f);
            yield return null;

            Assert.Greater(HorizontalDistance(startPosition, player.transform.position), 0.5f);
            Assert.Less(HorizontalDistance(target, player.transform.position), 0.2f);

            movement.CancelRequestedDestination();
            Assert.IsTrue(interaction.TryBeginDoorApproach(door.SelectionPoint),
                "The same confirmed flow must also enable the scene's door-selection owner.");
            Assert.AreSame(door, interaction.PendingDoor);
            Assert.AreEqual(1, CountInScene(scene, "Player"));
        }

        [UnityTearDown]
        public IEnumerator UnloadCanonicalSceneWithoutSaving()
        {
            DetachTestRenderTexture();
            Scene scene = SceneManager.GetSceneByName("RuntimeWorld");
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

        // The old DoorPrototype scene was serialized, so its hierarchy existed one frame after
        // load. RuntimeWorld does not exist until GameBootstrap runs: the wait is not optional.
        // Ported verbatim from FiveRoomDoorSequencePlayModeTests.WaitForWorldBuilt.
        private static IEnumerator WaitForWorldBuilt()
        {
            yield return null;
            GameObject managers = GameObject.Find("GameManagers");
            Assert.IsNotNull(managers,
                "RuntimeWorld.unity carries no GameManagers object, so nothing builds the world.");
            var bootstrap = managers.GetComponent<World.GameBootstrap>();
            Assert.IsNotNull(bootstrap, "GameManagers carries no GameBootstrap.");

            yield return null;
            yield return null;

            Assert.IsTrue(bootstrap.HasBuilt,
                "GameBootstrap had not built after three frames, so every assertion below would "
                + "fail on an empty world rather than on the thing under test. SpawnedCount = "
                + bootstrap.SpawnedCount + ".");
        }

        private static IEnumerator LoadRuntimeWorldScene()
        {
            yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);
            Scene scene = SceneManager.GetSceneByName("RuntimeWorld");
            Assert.IsTrue(scene.IsValid() && scene.isLoaded);
            yield return WaitForWorldBuilt();
        }

        // NOT root-scoped: RuntimeWorld nests every spawned object under its spawner
        // (GameManagers -> <Family>Spawner -> the object), never at the scene root, unlike the
        // old committed DoorPrototype scene the previous FindInScene(scene, name) calls here were
        // written against. Recurses the whole loaded scene and keeps the original "expect exactly
        // one" guarantee. Ported verbatim from FiveRoomDoorSequencePlayModeTests.FindInScene.
        private static GameObject FindInScene(Scene scene, string name)
        {
            var matches = new System.Collections.Generic.List<GameObject>();
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                CollectByName(root.transform, name, matches);
            }
            Assert.AreEqual(1, matches.Count,
                $"Expected exactly one '{name}' object in loaded scene {scene.path}, found {matches.Count}.");
            return matches[0];
        }

        private static void CollectByName(Transform node, string name, System.Collections.Generic.List<GameObject> matches)
        {
            if (node.name == name)
            {
                matches.Add(node.gameObject);
            }

            for (int i = 0; i < node.childCount; i++)
            {
                CollectByName(node.GetChild(i), name, matches);
            }
        }

        // Non-throwing sibling of FindInScene, for a bare count assertion (RuntimeWorld nests
        // every spawned object under its spawner, so this can no longer read
        // scene.GetRootGameObjects().Count(root => root.name == name) as the old committed scene
        // let it).
        private static int CountInScene(Scene scene, string name)
        {
            var matches = new System.Collections.Generic.List<GameObject>();
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                CollectByName(root.transform, name, matches);
            }
            return matches.Count;
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

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            FieldInfo field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }

        private static T GetPrivateField<T>(object target, string fieldName) where T : class
        {
            FieldInfo field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            T value = field.GetValue(target) as T;
            Assert.IsNotNull(value, $"Expected '{fieldName}' on {target.GetType().Name} to contain {typeof(T).Name}.");
            return value;
        }

    }
}
