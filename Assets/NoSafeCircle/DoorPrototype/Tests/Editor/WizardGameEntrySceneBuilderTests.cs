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
    public sealed class WizardGameEntrySceneBuilderTests
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

        // NSC-068 AC-002/AC-006 and VAL-004: repeated builds preserve one complete
        // title-to-selection-to-world path and one marker for the established Player spawn.
        [Test]
        public void Build_RunTwice_WiresOneEntryCoordinatorToExistingPlayerAndSpawn()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            Scene scene = SceneManager.GetActiveScene();
            GameObject[] roots = scene.GetRootGameObjects();
            GameObject player = roots.Single(root => root.name == "Player");
            GameObject playerSpawn = roots.Single(root => root.name == "PlayerSpawn");
            GameObject canvas = roots.Single(root => root.name == "Canvas");

            Assert.AreEqual(1, roots.Count(root => root.name == "Player"));
            Assert.AreEqual(1, roots.Count(root => root.name == "PlayerSpawn"));
            Assert.AreEqual(player.transform.position, playerSpawn.transform.position);
            Assert.AreEqual(player.transform.rotation, playerSpawn.transform.rotation);

            WizardGameEntryController[] entryControllers =
                Resources.FindObjectsOfTypeAll<WizardGameEntryController>()
                    .Where(candidate => candidate.gameObject.scene == scene)
                    .ToArray();
            Assert.AreEqual(1, entryControllers.Length);
            Assert.AreSame(canvas, entryControllers[0].gameObject);

            WizardSelectionController selection = canvas.GetComponent<WizardSelectionController>();
            WizardAnimationController wizard = player.GetComponent<WizardAnimationController>();
            PlayerMovement movement = player.GetComponent<PlayerMovement>();
            PlayerInteractionController interaction = player.GetComponent<PlayerInteractionController>();
            Assert.IsNotNull(selection);
            Assert.IsNotNull(wizard);
            Assert.IsNotNull(movement);
            Assert.IsNotNull(interaction);

            var serializedEntry = new SerializedObject(entryControllers[0]);
            Assert.AreSame(
                selection,
                serializedEntry.FindProperty("wizardSelectionController").objectReferenceValue);
            Assert.AreSame(
                wizard,
                serializedEntry.FindProperty("wizardAnimationController").objectReferenceValue);
            Assert.AreSame(player.transform, serializedEntry.FindProperty("player").objectReferenceValue);
            Assert.AreSame(playerSpawn.transform, serializedEntry.FindProperty("worldSpawn").objectReferenceValue);
            Assert.AreSame(movement, serializedEntry.FindProperty("playerMovement").objectReferenceValue);
            Assert.AreSame(
                interaction,
                serializedEntry.FindProperty("playerInteractionController").objectReferenceValue);

            SerializedProperty menuRoots = serializedEntry.FindProperty("menuUiRoots");
            Assert.AreEqual(2, menuRoots.arraySize);
            Assert.AreSame(
                canvas.transform.Find("TitleScreen").gameObject,
                menuRoots.GetArrayElementAtIndex(0).objectReferenceValue);
            Assert.AreSame(
                canvas.transform.Find("WizardSelectionScreen").gameObject,
                menuRoots.GetArrayElementAtIndex(1).objectReferenceValue);

            Button startButton = canvas.transform
                .Find("TitleScreen/TitleCard/StartGameButton")?.GetComponent<Button>();
            Button confirmButton = canvas.transform
                .Find("WizardSelectionScreen/ConfirmSelectionButton")?.GetComponent<Button>();
            Assert.IsNotNull(startButton);
            Assert.IsNotNull(confirmButton);
            Assert.AreEqual(1, startButton.onClick.GetPersistentEventCount());
            Assert.AreEqual(1, confirmButton.onClick.GetPersistentEventCount());
        }
    }
}
