using System.Linq;
using NoSafeCircle.DoorPrototype.Editor;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public sealed class WizardSelectionSceneBuilderTests
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

        private static readonly string[] ExpectedLabels =
        {
            "Ember Wizard",
            "Ash Wizard",
            "Frost Wizard",
            "Dusk Wizard"
        };

        private static readonly string[] ExpectedPreviewPaths =
        {
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png",
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-dark/selected/standing/south-east.png",
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-light/selected/standing/south-east.png",
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/standing/south-east.png"
        };

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

        // NSC-067 AC-001/AC-002 and VAL-001: every card uses one distinct NSC-062
        // presentation/skin pair and its exact integrated south-east standing Sprite.
        [Test]
        public void Build_OptionsResolveToFourDistinctCompleteNsc062Presentations()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            WizardSelectionController controller =
                GameObject.Find("Canvas")?.GetComponent<WizardSelectionController>();
            Assert.IsNotNull(controller);
            Assert.IsTrue(controller.HasValidOptionCatalog);
            Assert.AreEqual(4, controller.OptionCount);

            for (var index = 0; index < controller.OptionCount; index++)
            {
                WizardSelectionOptionBinding option = controller.GetOption(index);
                Assert.IsTrue(option.IsComplete, $"Option {index} must have all UI and art bindings.");
                Assert.AreEqual(ExpectedPresentations[index], option.Presentation);
                Assert.AreEqual(ExpectedSkins[index], option.Skin);
                Assert.AreEqual(ExpectedLabels[index], option.Label);
                Assert.AreEqual(ExpectedPreviewPaths[index], AssetDatabase.GetAssetPath(option.PreviewSprite));
                Assert.IsFalse(option.IsSelected);
            }

            Assert.AreEqual(
                4,
                Enumerable.Range(0, controller.OptionCount)
                    .Select(index => new
                    {
                        controller.GetOption(index).Presentation,
                        controller.GetOption(index).Skin
                    })
                    .Distinct()
                    .Count());
        }

        // NSC-067 AC-005/AC-006 and VAL-004: rebuilding twice leaves one complete menu path,
        // one Player root, and exactly one persistent action on each generated Button.
        [Test]
        public void Build_RunTwice_LeavesOneSelectionControllerFourOptionsAndOnePlayer()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            Scene scene = SceneManager.GetActiveScene();
            GameObject[] roots = scene.GetRootGameObjects();
            Assert.AreEqual(1, roots.Count(root => root.name == "Canvas"));
            Assert.AreEqual(1, roots.Count(root => root.name == "Player"));

            WizardSelectionController[] controllers =
                Resources.FindObjectsOfTypeAll<WizardSelectionController>()
                    .Where(candidate => candidate.gameObject.scene == scene)
                    .ToArray();
            Assert.AreEqual(1, controllers.Length);

            Transform canvas = roots.Single(root => root.name == "Canvas").transform;
            Transform[] panels = canvas.Cast<Transform>()
                .Where(child => child.name == "WizardSelectionScreen")
                .ToArray();
            Assert.AreEqual(1, panels.Length);
            Assert.IsFalse(panels[0].gameObject.activeSelf);

            WizardSelectionController controller = controllers[0];
            Assert.AreEqual(4, controller.OptionCount);
            for (var index = 0; index < controller.OptionCount; index++)
            {
                Button button = controller.GetOption(index).Button;
                Assert.AreEqual(1, button.onClick.GetPersistentEventCount());
                Assert.AreSame(controller, button.onClick.GetPersistentTarget(0));
                Assert.AreEqual(
                    nameof(WizardSelectionController.SelectOption),
                    button.onClick.GetPersistentMethodName(0));
            }

            Button confirmButton = panels[0].Find("ConfirmSelectionButton")?.GetComponent<Button>();
            Assert.IsNotNull(confirmButton);
            Assert.IsFalse(confirmButton.interactable);
            Assert.AreEqual(1, confirmButton.onClick.GetPersistentEventCount());
            Assert.AreSame(controller, confirmButton.onClick.GetPersistentTarget(0));
            Assert.AreEqual(
                nameof(WizardSelectionController.ConfirmSelection),
                confirmButton.onClick.GetPersistentMethodName(0));

            SerializedObject serializedController = new SerializedObject(controller);
            Assert.AreSame(
                canvas.GetComponent<TitleScreenController>(),
                serializedController.FindProperty("titleScreenController").objectReferenceValue);
        }
    }
}
