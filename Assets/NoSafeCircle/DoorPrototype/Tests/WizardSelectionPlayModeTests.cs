using System.Collections;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class WizardSelectionPlayModeTests
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

        // NSC-067 AC-003/AC-005 and VAL-002: Start Game opens selection with no default,
        // confirmation is guarded, and all gameplay input owners remain suspended.
        [UnityTest]
        public IEnumerator StartGame_OpensSelectionWithoutDefaultAndKeepsGameplayInputInactive()
        {
            yield return SceneManager.LoadSceneAsync("DoorPrototype", LoadSceneMode.Single);
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            Assert.IsTrue(scene.IsValid() && scene.isLoaded);

            GameObject canvas = FindRoot(scene, "Canvas");
            GameObject player = FindRoot(scene, "Player");
            TitleScreenController titleController = canvas.GetComponent<TitleScreenController>();
            WizardSelectionController selectionController =
                canvas.GetComponent<WizardSelectionController>();
            Button startButton = canvas.transform
                .Find("TitleScreen/TitleCard/StartGameButton")?.GetComponent<Button>();
            Button confirmButton = canvas.transform
                .Find("WizardSelectionScreen/ConfirmSelectionButton")?.GetComponent<Button>();

            Assert.IsNotNull(titleController);
            Assert.IsNotNull(selectionController);
            Assert.IsNotNull(startButton);
            Assert.IsNotNull(confirmButton);

            startButton.onClick.Invoke();

            Assert.IsTrue(selectionController.IsSelectionVisible);
            Assert.AreEqual(4, selectionController.OptionCount);
            Assert.AreEqual(-1, selectionController.SelectedOptionIndex);
            Assert.IsFalse(selectionController.IsConfirmationAvailable);
            Assert.IsFalse(selectionController.ConfirmedSelection.HasValue);
            Assert.AreEqual(0, SelectedOptionCount(selectionController));

            confirmButton.onClick.Invoke();
            Assert.IsFalse(selectionController.ConfirmedSelection.HasValue,
                "Confirmation must not create an unselected fallback wizard.");

            Assert.IsFalse(player.GetComponent<PlayerMovement>().IsGameplayEnabled);
            Assert.IsFalse(player.GetComponent<PlayerInteractionController>().IsGameplayEnabled);
            Assert.IsFalse(player.GetComponent<DebugDamageControl>().enabled);
            Assert.IsFalse(player.GetComponent<DebugManaSpendControl>().enabled);
        }

        // NSC-067 AC-003/AC-004/AC-005 and VAL-002/VAL-003: each card produces one exact
        // NSC-068 handoff while leaving the existing Player and its NSC-062 visual untouched.
        [UnityTest]
        public IEnumerator EachOption_ConfirmsOneMatchingHandoffWithoutChangingPlayer()
        {
            for (var optionIndex = 0; optionIndex < ExpectedPresentations.Length; optionIndex++)
            {
                yield return SceneManager.LoadSceneAsync("DoorPrototype", LoadSceneMode.Single);
                Scene scene = SceneManager.GetSceneByName("DoorPrototype");
                Assert.IsTrue(scene.IsValid() && scene.isLoaded);

                GameObject canvas = FindRoot(scene, "Canvas");
                GameObject player = FindRoot(scene, "Player");
                TitleScreenController titleController = canvas.GetComponent<TitleScreenController>();
                WizardSelectionController selectionController =
                    canvas.GetComponent<WizardSelectionController>();
                WizardGameEntryController gameEntryController =
                    canvas.GetComponent<WizardGameEntryController>();
                Button startButton = canvas.transform
                    .Find("TitleScreen/TitleCard/StartGameButton")?.GetComponent<Button>();
                Button confirmButton = canvas.transform
                    .Find("WizardSelectionScreen/ConfirmSelectionButton")?.GetComponent<Button>();
                WizardAnimationController playerWizard = player.GetComponent<WizardAnimationController>();
                Sprite originalPlayerSprite = player.transform.Find("Visual")?.GetComponent<SpriteRenderer>()?.sprite;
                Vector3 originalPlayerPosition = player.transform.position;
                Quaternion originalPlayerRotation = player.transform.rotation;
                bool originalPlayerActive = player.activeSelf;

                Assert.IsNotNull(titleController);
                Assert.IsNotNull(selectionController);
                Assert.IsNotNull(gameEntryController);
                Assert.IsNotNull(startButton);
                Assert.IsNotNull(confirmButton);
                Assert.IsNotNull(playerWizard);
                Assert.IsNotNull(originalPlayerSprite);

                // This NSC-067 test isolates the producer contract. NSC-068's focused tests
                // cover the installed downstream consumer and its Player mutation separately.
                gameEntryController.enabled = false;

                var handoffCount = 0;
                ConfirmedWizardSelection? observedHandoff = null;
                selectionController.WizardSelectionConfirmed += handoff =>
                {
                    handoffCount++;
                    observedHandoff = handoff;
                };

                startButton.onClick.Invoke();
                selectionController.GetOption(optionIndex).Button.onClick.Invoke();

                Assert.AreEqual(optionIndex, selectionController.SelectedOptionIndex);
                Assert.AreEqual(1, SelectedOptionCount(selectionController));
                Assert.IsTrue(selectionController.GetOption(optionIndex).IsSelected);
                Assert.IsTrue(selectionController.IsConfirmationAvailable);

                confirmButton.onClick.Invoke();
                confirmButton.onClick.Invoke();
                selectionController.ConfirmSelection();

                Assert.AreEqual(1, handoffCount);
                Assert.IsTrue(observedHandoff.HasValue);
                Assert.AreEqual(ExpectedPresentations[optionIndex], observedHandoff.Value.Presentation);
                Assert.AreEqual(ExpectedSkins[optionIndex], observedHandoff.Value.Skin);
                Assert.AreEqual(observedHandoff, selectionController.ConfirmedSelection);
                Assert.IsFalse(selectionController.IsSelectionVisible);
                Assert.IsFalse(selectionController.IsConfirmationAvailable);

                Assert.AreSame(player, FindRoot(scene, "Player"));
                Assert.AreEqual(1, scene.GetRootGameObjects().Count(root => root.name == "Player"));
                Assert.AreEqual(originalPlayerActive, player.activeSelf);
                Assert.AreEqual(originalPlayerPosition, player.transform.position);
                Assert.AreEqual(originalPlayerRotation, player.transform.rotation);
                Assert.AreSame(originalPlayerSprite,
                    player.transform.Find("Visual").GetComponent<SpriteRenderer>().sprite);
                Assert.AreEqual(WizardPresentation.Masculine, playerWizard.Presentation);
                Assert.AreEqual(WizardSkin.White, playerWizard.Skin);
                Assert.IsFalse(player.GetComponent<PlayerMovement>().IsGameplayEnabled);
                Assert.IsFalse(player.GetComponent<PlayerInteractionController>().IsGameplayEnabled);
            }
        }

        [UnityTearDown]
        public IEnumerator UnloadCanonicalSceneWithoutSaving()
        {
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            Scene cleanupScene = SceneManager.CreateScene("WizardSelectionTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }

        private static GameObject FindRoot(Scene scene, string name)
        {
            GameObject result = scene.GetRootGameObjects().SingleOrDefault(root => root.name == name);
            Assert.IsNotNull(result, $"Expected one '{name}' root in {scene.path}.");
            return result;
        }

        private static int SelectedOptionCount(WizardSelectionController controller)
        {
            return Enumerable.Range(0, controller.OptionCount)
                .Count(index => controller.GetOption(index).IsSelected);
        }
    }
}
