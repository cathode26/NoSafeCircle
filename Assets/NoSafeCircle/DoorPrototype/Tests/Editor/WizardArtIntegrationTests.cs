using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEditor.Animations;
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
        public void EveryWizardStateUsesItsOwnOrderedSourceSpritesOnVisualRenderer()
        {
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(GeneratedRoot + "/WizardAnimator.controller");
            Assert.IsNotNull(controller);
            Assert.AreEqual(1, controller.layers.Length);
            var states = controller.layers[0].stateMachine.states;
            Assert.AreEqual(32, states.Length, "The controller should contain exactly four variants × four directions × idle/walk.");

            string[] variants = { "Masculine_White", "Masculine_Black", "Feminine_White", "Feminine_Black" };
            string[] directions = { "north-east", "north-west", "south-east", "south-west" };
            foreach (string variant in variants)
            {
                string sourceVariant = variant.Replace("Masculine", "masculine")
                    .Replace("Feminine", "feminine").Replace("_White", "-light")
                    .Replace("_Black", "-dark");
                foreach (string direction in directions)
                {
                    foreach (string motion in new[] { "idle", "walk" })
                    {
                        string name = $"Wizard_{variant}_{motion}_{direction}";
                        var matchingStates = states.Where(child => child.state.name == name).ToArray();
                        Assert.AreEqual(1, matchingStates.Length, name);
                        var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>($"{GeneratedRoot}/{name}.anim");
                        Assert.IsNotNull(clip, name);
                        Assert.AreSame(clip, matchingStates[0].state.motion, name);
                        var bindings = AnimationUtility.GetObjectReferenceCurveBindings(clip);
                        Assert.AreEqual(1, bindings.Length, name);
                        Assert.AreEqual("Visual", bindings[0].path, name);
                        Assert.AreEqual(typeof(SpriteRenderer), bindings[0].type, name);
                        Assert.AreEqual("m_Sprite", bindings[0].propertyName, name);
                        var keys = AnimationUtility.GetObjectReferenceCurve(clip, bindings[0]);
                        int frameCount = motion == "walk" ? 6 : 1;
                        Assert.AreEqual(frameCount, keys.Length, name);
                        for (int frame = 0; frame < frameCount; frame++)
                        {
                            string sourcePath = motion == "walk"
                                ? $"{SourceRoot}/{sourceVariant}/selected/walk/{direction}/frame_{frame:000}.png"
                                : $"{SourceRoot}/{sourceVariant}/selected/standing/{direction}.png";
                            var sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourcePath);
                            Assert.IsNotNull(sourceSprite, sourcePath);
                            Assert.AreSame(sourceSprite, keys[frame].value, $"{name} frame {frame}");
                            Assert.That(keys[frame].time, Is.EqualTo(frame / (motion == "walk" ? 12f : 1f)).Within(0.0001f), name);
                        }
                    }
                }
            }
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
}
