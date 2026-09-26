using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public sealed class WizardArtIntegrationTests
    {
        private const string SourceRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab";
        private const string GeneratedRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated";
        private const int SourceSize = 180;
        private const int WalkFrameCount = 6;

        private static readonly WizardVariant[] Variants =
        {
            new WizardVariant("Masculine_White", "masculine-light"),
            new WizardVariant("Masculine_Black", "masculine-dark"),
            new WizardVariant("Feminine_White", "feminine-light"),
            new WizardVariant("Feminine_Black", "feminine-dark")
        };

        private static readonly string[] Directions =
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

        [SetUp]
        public void OpenCandidateScene()
        {
            EditorSceneManager.OpenScene("Assets/Scenes/DoorPrototype.unity", OpenSceneMode.Single);
        }

        // NSC-075 AC-002/AC-003 and VAL-001: all 224 standing and walk PNGs used by the
        // generated clips share the same Sprite import geometry, transparent canvas, and feet pivot.
        [Test]
        public void ApprovedSourceFramesHaveExactImportGeometryAndGroundPivot()
        {
            string[] expectedPaths = ExpectedSourcePaths().ToArray();
            Assert.AreEqual(224, expectedPaths.Length);
            Assert.AreEqual(expectedPaths.Length, expectedPaths.Distinct().Count());

            string[] importedSpritePaths = AssetDatabase.FindAssets("t:Sprite", new[] { SourceRoot })
                .Select(AssetDatabase.GUIDToAssetPath)
                .OrderBy(path => path)
                .ToArray();
            CollectionAssert.AreEquivalent(expectedPaths, importedSpritePaths);

            foreach (string path in expectedPaths)
            {
                AssertSourceImport(path);
            }
        }

        // NSC-075 AC-002/AC-003 and VAL-001: every one of the 64 Animator states resolves to
        // its exact same-named clip, and every SpriteRenderer curve references only the expected
        // variant, direction, and ordered source frames.
        [Test]
        public void GeneratedWizardControllerHasExactStateClipAndSpriteMappings()
        {
            string controllerPath = GeneratedRoot + "/WizardAnimator.controller";
            AnimatorController controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
            Assert.IsNotNull(controller, controllerPath);
            Assert.AreEqual(1, controller.layers.Length, controllerPath);

            ChildAnimatorState[] childStates = controller.layers[0].stateMachine.states;
            string[] stateNames = childStates.Select(child => child.state.name).ToArray();
            Assert.AreEqual(64, childStates.Length);
            Assert.AreEqual(64, stateNames.Distinct().Count(), "Animator state names must be unique.");
            Dictionary<string, AnimatorState> statesByName = childStates.ToDictionary(
                child => child.state.name, child => child.state);

            var expectedStateNames = new HashSet<string>();
            var expectedClipPaths = new HashSet<string>();
            foreach (WizardVariant variant in Variants)
            {
                foreach (string direction in Directions)
                {
                    string idleName = "Wizard_" + variant.AnimatorName + "_idle_" + direction;
                    string idleSourcePath = StandingPath(variant.SourceFolder, direction);
                    AssertStateAndClip(
                        statesByName,
                        idleName,
                        new[] { idleSourcePath },
                        1,
                        expectedStateNames,
                        expectedClipPaths);

                    string walkName = "Wizard_" + variant.AnimatorName + "_walk_" + direction;
                    string[] walkSourcePaths = Enumerable.Range(0, WalkFrameCount)
                        .Select(frame => WalkPath(variant.SourceFolder, direction, frame))
                        .ToArray();
                    AssertStateAndClip(
                        statesByName,
                        walkName,
                        walkSourcePaths,
                        12,
                        expectedStateNames,
                        expectedClipPaths);
                }
            }

            CollectionAssert.AreEquivalent(expectedStateNames, stateNames);

            string[] generatedClipPaths = AssetDatabase.FindAssets("t:AnimationClip", new[] { GeneratedRoot })
                .Select(AssetDatabase.GUIDToAssetPath)
                .ToArray();
            Assert.AreEqual(64, generatedClipPaths.Length);
            CollectionAssert.AreEquivalent(expectedClipPaths, generatedClipPaths);

            AnimationClip[] controllerClips = controller.animationClips;
            Assert.AreEqual(64, controllerClips.Length);
            Assert.AreEqual(64, controllerClips.Select(clip => clip.name).Distinct().Count());
            CollectionAssert.AreEquivalent(expectedStateNames, controllerClips.Select(clip => clip.name));
        }

        [Test]
        public void DoorPrototypePlayerUsesWizardPresentationAndWorldSpriteConvention()
        {
            GameObject player = GameObject.Find("Player");
            Assert.IsNotNull(player);
            WizardAnimationController wizard = player.GetComponent<WizardAnimationController>();
            Assert.IsNotNull(wizard);
            SpriteRenderer renderer = player.transform.Find("Visual")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(renderer);
            Assert.IsNotNull(renderer.sprite);
            SpriteRenderer doorRenderer =
                GameObject.Find("DoorRoot/DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(doorRenderer);
            Assert.AreEqual(doorRenderer.sortingLayerName, renderer.sortingLayerName);
            Assert.AreEqual(doorRenderer.sortingOrder, renderer.sortingOrder);
            Assert.AreEqual(SpriteSortPoint.Pivot, doorRenderer.spriteSortPoint);
            Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint);
            CharacterController characterController = player.GetComponent<CharacterController>();
            Assert.IsNotNull(characterController);
            Assert.That(
                renderer.transform.position.y,
                Is.EqualTo(player.transform.position.y - characterController.skinWidth).Within(0.001f));

            Animator animator = player.GetComponent<Animator>();
            Assert.IsNotNull(animator);
            Assert.IsNotNull(animator.runtimeAnimatorController);
            const string initialState = "Wizard_Masculine_White_idle_south-east";
            Assert.IsTrue(animator.runtimeAnimatorController.animationClips.Any(clip => clip.name == initialState));
            FieldInfo lastDirection = typeof(WizardAnimationController).GetField(
                "lastDirection", BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.IsNotNull(lastDirection);
            Assert.AreEqual("south-east", lastDirection.GetValue(wizard));

            Camera camera = GameObject.Find("Main Camera")?.GetComponent<Camera>();
            Assert.IsNotNull(camera);
            Assert.AreEqual(TransparencySortMode.CustomAxis, camera.transparencySortMode);
        }

        private static IEnumerable<string> ExpectedSourcePaths()
        {
            foreach (WizardVariant variant in Variants)
            {
                foreach (string direction in Directions)
                {
                    yield return StandingPath(variant.SourceFolder, direction);
                    for (int frame = 0; frame < WalkFrameCount; frame++)
                    {
                        yield return WalkPath(variant.SourceFolder, direction, frame);
                    }
                }
            }
        }

        private static void AssertSourceImport(string path)
        {
            TextureImporter importer = AssetImporter.GetAtPath(path) as TextureImporter;
            Assert.IsNotNull(importer, path);
            Assert.AreEqual(TextureImporterType.Sprite, importer.textureType, path);
            Assert.AreEqual(SpriteImportMode.Single, importer.spriteImportMode, path);
            Assert.AreEqual(FilterMode.Point, importer.filterMode, path);
            Assert.AreEqual(TextureImporterCompression.Uncompressed, importer.textureCompression, path);
            Assert.IsFalse(importer.mipmapEnabled, path);
            Assert.AreEqual(180f, importer.spritePixelsPerUnit, path);

            var textureSettings = new TextureImporterSettings();
            importer.ReadTextureSettings(textureSettings);
            Assert.AreEqual((int)SpriteAlignment.Custom, textureSettings.spriteAlignment, path);
            Assert.That(textureSettings.spritePivot.x, Is.EqualTo(0.5f).Within(0.001f), path);
            Assert.That(textureSettings.spritePivot.y, Is.EqualTo(0f).Within(0.001f), path);

            Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
            Assert.IsNotNull(sprite, path);
            Assert.That(sprite.rect.width, Is.EqualTo(SourceSize).Within(0.001f), path);
            Assert.That(sprite.rect.height, Is.EqualTo(SourceSize).Within(0.001f), path);
            Assert.That(sprite.pivot.x, Is.EqualTo(SourceSize * 0.5f).Within(0.001f), path);
            Assert.That(sprite.pivot.y, Is.EqualTo(0f).Within(0.001f), path);

            var sourceTexture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                Assert.IsTrue(sourceTexture.LoadImage(File.ReadAllBytes(path)), path);
                Assert.AreEqual(SourceSize, sourceTexture.width, path);
                Assert.AreEqual(SourceSize, sourceTexture.height, path);
                Color32[] pixels = sourceTexture.GetPixels32();
                Assert.IsTrue(pixels.Any(pixel => pixel.a == 0), "No transparent pixels: " + path);
                Assert.IsTrue(pixels.Any(pixel => pixel.a > 0), "No visible character pixels: " + path);
            }
            finally
            {
                Object.DestroyImmediate(sourceTexture);
            }
        }

        private static void AssertStateAndClip(
            IReadOnlyDictionary<string, AnimatorState> statesByName,
            string expectedName,
            IReadOnlyList<string> expectedSourcePaths,
            int expectedFrameRate,
            ISet<string> expectedStateNames,
            ISet<string> expectedClipPaths)
        {
            Assert.IsTrue(expectedStateNames.Add(expectedName), expectedName);
            Assert.IsTrue(statesByName.TryGetValue(expectedName, out AnimatorState state), expectedName);

            string clipPath = GeneratedRoot + "/" + expectedName + ".anim";
            Assert.IsTrue(expectedClipPaths.Add(clipPath), clipPath);
            AnimationClip clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
            Assert.IsNotNull(clip, clipPath);
            Assert.AreSame(clip, state.motion, expectedName);
            Assert.AreEqual(expectedName, clip.name, clipPath);
            Assert.AreEqual(expectedFrameRate, clip.frameRate, clipPath);
            Assert.IsTrue(AnimationUtility.GetAnimationClipSettings(clip).loopTime, clipPath);

            EditorCurveBinding[] bindings = AnimationUtility.GetObjectReferenceCurveBindings(clip);
            Assert.AreEqual(1, bindings.Length, clipPath);
            EditorCurveBinding binding = bindings[0];
            Assert.AreEqual("Visual", binding.path, clipPath);
            Assert.AreEqual(typeof(SpriteRenderer), binding.type, clipPath);
            Assert.AreEqual("m_Sprite", binding.propertyName, clipPath);

            ObjectReferenceKeyframe[] keyframes = AnimationUtility.GetObjectReferenceCurve(clip, binding);
            Assert.AreEqual(expectedSourcePaths.Count, keyframes.Length, clipPath);
            for (int frame = 0; frame < expectedSourcePaths.Count; frame++)
            {
                string sourcePath = expectedSourcePaths[frame];
                Sprite expectedSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourcePath);
                Assert.IsNotNull(expectedSprite, sourcePath);
                Assert.That(
                    keyframes[frame].time,
                    Is.EqualTo(frame / (float)expectedFrameRate).Within(0.0001f),
                    clipPath);
                Assert.AreSame(expectedSprite, keyframes[frame].value, clipPath + " frame " + frame);
                Assert.AreEqual(sourcePath, AssetDatabase.GetAssetPath(keyframes[frame].value), clipPath);
            }
        }

        private static string StandingPath(string sourceFolder, string direction)
        {
            return SourceRoot + "/" + sourceFolder + "/selected/standing/" + direction + ".png";
        }

        private static string WalkPath(string sourceFolder, string direction, int frame)
        {
            return SourceRoot + "/" + sourceFolder + "/selected/walk/" + direction +
                "/frame_" + frame.ToString("000") + ".png";
        }

        private readonly struct WizardVariant
        {
            public readonly string AnimatorName;
            public readonly string SourceFolder;

            public WizardVariant(string animatorName, string sourceFolder)
            {
                AnimatorName = animatorName;
                SourceFolder = sourceFolder;
            }
        }
    }

    public sealed class WizardBuilderConfigurationTests
    {
        [Test]
        public void BuilderUsesCanonicalEightDirectionSetForStandingIdleAndWalk()
        {
            string[] expectedDirections =
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
            // REFLECTED BY NAME, SO NO COMPILER CAN SEE THIS COUPLING. These constants moved from
            // DoorPrototypeGlobalSceneBuilder to CharacterAnimationGenerator when the animation
            // generator was extracted so it would survive the deletion of the scene builders. The
            // move was faithful - same names, same values - but this test pinned the old HOME as a
            // STRING, so it broke while compile_check passed 4/4. Reflection is not a compile-time
            // reference; only the test suite could catch it, and this is what it caught.
            //
            // Pointed at the GENERATOR rather than repaired in place on purpose: the generator
            // survives the cutover and the builder does not, so this test now outlives it instead
            // of dying with it.
            //
            // Reflection is still required rather than a direct reference: these members are
            // internal to NoSafeCircle.DoorPrototype.Editor and this fixture is in
            // NoSafeCircle.DoorPrototype.Tests.Editor, a different assembly.
            System.Type builderType = typeof(NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder)
                .Assembly.GetType("NoSafeCircle.DoorPrototype.Editor.Generation.CharacterAnimationGenerator");
            Assert.IsNotNull(builderType,
                "CharacterAnimationGenerator was not found. If it moved again, repoint this at its "
                + "new home rather than deleting the assertion - the canonical eight-direction set "
                + "is the thing under test, not the class that happens to hold it.");
            FieldInfo directionsField = builderType.GetField(
                "WizardDirections", BindingFlags.NonPublic | BindingFlags.Static);
            FieldInfo standingDirectionsField = builderType.GetField(
                "WizardStandingDirections", BindingFlags.NonPublic | BindingFlags.Static);
            Assert.IsNotNull(directionsField);
            Assert.IsNotNull(standingDirectionsField);
            string[] directions = (string[])directionsField.GetValue(null);
            string[] standingDirections = (string[])standingDirectionsField.GetValue(null);

            CollectionAssert.AreEqual(expectedDirections, directions);
            CollectionAssert.AreEqual(expectedDirections, standingDirections);
            Assert.AreSame(directions, standingDirections);
        }
    }
}
