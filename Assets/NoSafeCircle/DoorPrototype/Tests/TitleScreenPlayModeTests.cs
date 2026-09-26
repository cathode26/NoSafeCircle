using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class TitleScreenPlayModeTests : InputTestFixture
    {
        private GameObject playerObject;
        private GameObject uiObject;
        private GameObject titlePanel;
        private Button startGameButton;
        private Text titleText;
        private PlayerMovement movement;
        private PlayerInteractionController interactionController;
        private DebugDamageControl debugDamageControl;
        private DebugManaSpendControl debugManaControl;
        private PlayerMana mana;
        private TitleScreenController titleScreenController;
        private InputActionAsset inputActions;
        private Keyboard keyboardDevice;

        public override void Setup()
        {
            base.Setup();

            keyboardDevice = InputSystem.AddDevice<Keyboard>();
            inputActions = ScriptableObject.CreateInstance<InputActionAsset>();
            InputActionMap playerMap = inputActions.AddActionMap("Player");
            playerMap.AddAction("PointerPosition", InputActionType.Value);
            playerMap.AddAction("MoveToCursor", InputActionType.Button);

            playerObject = new GameObject("TestPlayer");
            playerObject.SetActive(false);
            playerObject.AddComponent<CharacterController>();
            PlayerHealth health = playerObject.AddComponent<PlayerHealth>();
            interactionController = playerObject.AddComponent<PlayerInteractionController>();
            movement = playerObject.AddComponent<PlayerMovement>();
            debugDamageControl = playerObject.AddComponent<DebugDamageControl>();
            mana = playerObject.AddComponent<PlayerMana>();
            debugManaControl = playerObject.AddComponent<DebugManaSpendControl>();

            SetPrivateField(interactionController, "playerHealth", health);
            SetPrivateField(interactionController, "movement", movement);
            SetPrivateField(movement, "interactionController", interactionController);
            SetPrivateField(movement, "inputActions", inputActions);
            SetPrivateField(debugDamageControl, "target", health);
            SetPrivateField(debugManaControl, "target", mana);

            uiObject = new GameObject("TitleScreenController");
            uiObject.SetActive(false);
            titlePanel = new GameObject("TitleScreen");
            titlePanel.transform.SetParent(uiObject.transform, false);

            var titleTextObject = new GameObject(
                "Title",
                typeof(RectTransform),
                typeof(CanvasRenderer),
                typeof(Text));
            titleTextObject.transform.SetParent(titlePanel.transform, false);
            titleText = titleTextObject.GetComponent<Text>();
            titleText.text = "NO SAFE CIRCLE";

            var buttonObject = new GameObject(
                "StartGameButton",
                typeof(RectTransform),
                typeof(CanvasRenderer),
                typeof(Image),
                typeof(Button));
            buttonObject.transform.SetParent(titlePanel.transform, false);
            startGameButton = buttonObject.GetComponent<Button>();

            titleScreenController = uiObject.AddComponent<TitleScreenController>();
            SetPrivateField(titleScreenController, "titlePanel", titlePanel);
            SetPrivateField(titleScreenController, "startGameButton", startGameButton);
            SetPrivateField(titleScreenController, "playerMovement", movement);
            SetPrivateField(titleScreenController, "playerInteractionController", interactionController);
            SetPrivateField(
                titleScreenController,
                "gameplayInputBehaviours",
                new Behaviour[] { debugDamageControl, debugManaControl });
            startGameButton.onClick.AddListener(titleScreenController.StartGame);

            playerObject.SetActive(true);
            uiObject.SetActive(true);
        }

        public override void TearDown()
        {
            if (uiObject != null) Object.Destroy(uiObject);
            if (playerObject != null) Object.Destroy(playerObject);
            if (inputActions != null)
            {
                inputActions.Disable();
                Object.Destroy(inputActions);
            }

            playerObject = null;
            uiObject = null;
            titlePanel = null;
            startGameButton = null;
            titleText = null;
            movement = null;
            interactionController = null;
            debugDamageControl = null;
            debugManaControl = null;
            mana = null;
            titleScreenController = null;
            inputActions = null;
            keyboardDevice = null;

            base.TearDown();
        }

        // NSC-066 AC-001/AC-002 and VAL-001: entering the title flow shows the named title
        // while movement, door interaction, and the current keyboard-driven mana control are inert.
        [UnityTest]
        public IEnumerator EnteringScene_ShowsTitleAndSuspendsGameplayInput()
        {
            yield return null;

            Assert.IsTrue(titleScreenController.IsTitleScreenVisible);
            Assert.AreEqual("NO SAFE CIRCLE", titleText.text);
            Assert.IsTrue(startGameButton.interactable);
            Assert.IsFalse(movement.IsGameplayEnabled);
            Assert.IsFalse(interactionController.IsGameplayEnabled);
            Assert.IsFalse(debugDamageControl.enabled);
            Assert.IsFalse(debugManaControl.enabled);

            movement.RequestDestination(new Vector3(4f, 0f, 4f));
            Assert.IsFalse(movement.HasActiveDestination,
                "Movement requests must be ignored while the title screen owns the game-entry flow.");

            float manaBeforeInput = mana.CurrentMana;
            Press(keyboardDevice.lKey);
            yield return null;
            Release(keyboardDevice.lKey);
            yield return null;

            Assert.AreEqual(manaBeforeInput, mana.CurrentMana, 0.001f,
                "The current keyboard-driven mana/spell demonstration input must not affect gameplay before Start Game.");
        }

        // NSC-066 AC-003 and VAL-001: every activation path converges on one guarded request.
        // Gameplay stays suspended because NSC-067 owns wizard selection before play begins.
        [UnityTest]
        public IEnumerator StartGame_RepeatedActivation_RequestsWizardSelectionExactlyOnce()
        {
            var requestCount = 0;
            titleScreenController.WizardSelectionRequested += () => requestCount++;

            startGameButton.onClick.Invoke();
            startGameButton.onClick.Invoke();
            titleScreenController.StartGame();
            yield return null;

            Assert.AreEqual(1, requestCount);
            Assert.IsTrue(titleScreenController.HasRequestedWizardSelection);
            Assert.IsFalse(titleScreenController.IsTitleScreenVisible);
            Assert.IsFalse(startGameButton.interactable);
            Assert.IsFalse(movement.IsGameplayEnabled);
            Assert.IsFalse(interactionController.IsGameplayEnabled);
            Assert.IsFalse(debugManaControl.enabled);
        }

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            FieldInfo field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }
    }

    public class TitleScreenCommittedScenePlayModeTests
    {
        /// <summary>Scene 0 of ProjectSettings/EditorBuildSettings.asset - what a build launches.</summary>
        private const string CanonicalSceneName = "RuntimeWorld";


        // NSC-066 AC-001/AC-002/AC-003 and VAL-001: load the registered canonical scene in
        // Play Mode, then exercise its Button listener without saving the scene.
        //
        // THE SCENE NAME CHANGED BECAUSE THE REGISTRATION DID, AND THAT IS THE WHOLE POINT OF THE
        // TEST. It has always meant "whatever scene a build actually launches"; that was
        // DoorPrototype.unity and is now RuntimeWorld.unity, which is scene 0 of
        // ProjectSettings/EditorBuildSettings.asset. Pinning the old name would have kept the test
        // green while it stopped describing the shipped game - the exact failure that let the WebGL
        // player ship the old world for days.
        //
        // AND THE WAIT IS NOT OPTIONAL. The old scene was SERIALIZED, so its hierarchy existed one
        // frame after load. The new world does not exist until GameBootstrap runs: the HUD is
        // spawned from Resources/Hud/Hud.prefab by HudSpawner in phase 6, after the Player it binds
        // to. One frame photographs an empty room. Two frames plus an explicit HasBuilt assertion
        // is the pattern RuntimeWorldCaptureTests already proves, and asserting HasBuilt rather
        // than trusting the frame count is what makes a slow build a loud failure instead of a
        // confusing null.
        [UnityTest]
        public IEnumerator RegisteredCanonicalScene_StartsAtTitleAndEmitsOneWizardSelectionRequest()
        {
            SceneManager.LoadScene(CanonicalSceneName, LoadSceneMode.Single);
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
                + "fail on an empty scene rather than on the title screen. SpawnedCount = "
                + bootstrap.SpawnedCount + ".");

            TitleScreenController controller = Object.FindFirstObjectByType<TitleScreenController>();
            GameObject player = GameObject.Find("Player");
            GameObject canvas = GameObject.Find("Canvas");
            Assert.IsNotNull(controller);
            Assert.IsNotNull(player);
            Assert.IsNotNull(canvas);

            Transform titlePanel = canvas.transform.Find("TitleScreen");
            Text title = titlePanel?.Find("TitleCard/Title")?.GetComponent<Text>();
            Button button = titlePanel?.Find("TitleCard/StartGameButton")?.GetComponent<Button>();
            Assert.IsNotNull(titlePanel);
            Assert.IsNotNull(title);
            Assert.IsNotNull(button);
            Assert.IsTrue(titlePanel.gameObject.activeSelf);
            Assert.AreEqual("NO SAFE CIRCLE", title.text);
            Assert.IsFalse(player.GetComponent<PlayerMovement>().IsGameplayEnabled);
            Assert.IsFalse(player.GetComponent<PlayerInteractionController>().IsGameplayEnabled);
            Assert.IsFalse(player.GetComponent<DebugManaSpendControl>().enabled);

            var requestCount = 0;
            controller.WizardSelectionRequested += () => requestCount++;
            button.onClick.Invoke();
            button.onClick.Invoke();
            yield return null;

            Assert.AreEqual(1, requestCount);
            Assert.IsFalse(titlePanel.gameObject.activeSelf);
            Assert.IsFalse(player.GetComponent<PlayerMovement>().IsGameplayEnabled);
        }

        [UnityTearDown]
        public IEnumerator UnloadCanonicalSceneWithoutSaving()
        {
            // Same constant as the load. A literal here would silently unload nothing once the
            // load moved, leaving the world resident for every fixture that runs afterwards -
            // which is precisely what PlayModeSceneCleanupConventionTests exists to catch.
            Scene scene = SceneManager.GetSceneByName(CanonicalSceneName);
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            Scene cleanupScene = SceneManager.CreateScene("TitleScreenTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }
    }
}
