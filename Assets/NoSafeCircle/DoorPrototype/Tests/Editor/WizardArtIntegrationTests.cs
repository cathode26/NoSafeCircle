using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using NUnit.Framework;
using System.Linq;
using System.Reflection;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public sealed class WizardArtIntegrationTests
    {
        private const string SourceRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab";
        private const string GeneratedRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated";

        [SetUp]
        public void OpenCandidateScene()
        {
            EditorSceneManager.OpenScene("Assets/Scenes/DoorPrototype.unity", OpenSceneMode.Single);
        }

        [Test]
        public void ApprovedSourceFramesHavePointUncompressedImportAndGroundPivot()
        {
            var guids = AssetDatabase.FindAssets("t:Sprite", new[] { SourceRoot });
            Assert.AreEqual(128, guids.Length);
            foreach (var guid in guids)
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var importer = AssetImporter.GetAtPath(path) as TextureImporter;
                Assert.IsNotNull(importer, path);
                Assert.AreEqual(FilterMode.Point, importer.filterMode, path);
                Assert.AreEqual(TextureImporterCompression.Uncompressed, importer.textureCompression, path);
                Assert.AreEqual(180f, importer.spritePixelsPerUnit, path);
                var textureSettings = new TextureImporterSettings();
                importer.ReadTextureSettings(textureSettings);
                Assert.AreEqual((int)SpriteAlignment.Custom, textureSettings.spriteAlignment, path);
                Assert.That(textureSettings.spritePivot.y, Is.EqualTo(0f).Within(0.001f), path);
                var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
                Assert.IsNotNull(sprite, path);
                Assert.That(sprite.pivot.y, Is.EqualTo(0f).Within(0.001f), path);
            }
        }

        [Test]
        public void GeneratedWizardControllerHasAllFourVariantAnimationSets()
        {
            Assert.IsNotNull(AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(GeneratedRoot + "/WizardAnimator.controller"));
            Assert.AreEqual(32, AssetDatabase.FindAssets("t:AnimationClip", new[] { GeneratedRoot }).Length);
        }

        [Test]
        public void DoorPrototypePlayerUsesWizardPresentationAndWorldSpriteConvention()
        {
            var player = GameObject.Find("Player");
            Assert.IsNotNull(player);
            var wizard = player.GetComponent<WizardAnimationController>();
            Assert.IsNotNull(wizard);
            var renderer = player.transform.Find("Visual")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(renderer);
            Assert.IsNotNull(renderer.sprite);
            var doorRenderer = GameObject.Find("DoorRoot/DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(doorRenderer);
            Assert.AreEqual(doorRenderer.sortingLayerName, renderer.sortingLayerName);
            Assert.AreEqual(doorRenderer.sortingOrder, renderer.sortingOrder);
            Assert.AreEqual(SpriteSortPoint.Pivot, doorRenderer.spriteSortPoint);
            Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint);
            var characterController = player.GetComponent<CharacterController>();
            Assert.IsNotNull(characterController);
            Assert.That(
                renderer.transform.position.y,
                Is.EqualTo(player.transform.position.y - characterController.skinWidth).Within(0.001f));

            var animator = player.GetComponent<Animator>();
            Assert.IsNotNull(animator);
            Assert.IsNotNull(animator.runtimeAnimatorController);
            const string initialState = "Wizard_Masculine_White_idle_south-east";
            Assert.IsTrue(animator.runtimeAnimatorController.animationClips.Any(clip => clip.name == initialState));
            var lastDirection = typeof(WizardAnimationController).GetField(
                "lastDirection", BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.AreEqual("south-east", lastDirection.GetValue(wizard));

            var camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();
            Assert.IsNotNull(camera);
            Assert.AreEqual(TransparencySortMode.CustomAxis, camera.transparencySortMode);
        }
    }

    public sealed class WizardBuilderConfigurationTests
    {
        [Test]
        public void BuilderUsesCanonicalEightDirectionSetForStandingIdleAndWalk()
        {
            var expectedDirections = new[]
            {
                "north",
                "north-east",
                "east",
                "south-east",
                "south",
                "south-west",
                "west",
                "north-west"
            };
            var builderType = typeof(NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder).Assembly.GetType(
                "NoSafeCircle.DoorPrototype.Editor.World.DoorPrototypeGlobalSceneBuilder");
            Assert.IsNotNull(builderType);
            var directions = (string[])builderType.GetField(
                "WizardDirections", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);
            var standingDirections = (string[])builderType.GetField(
                "WizardStandingDirections", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);

            CollectionAssert.AreEqual(expectedDirections, directions);
            CollectionAssert.AreEqual(expectedDirections, standingDirections);
            Assert.AreSame(directions, standingDirections);
        }
    }
}
