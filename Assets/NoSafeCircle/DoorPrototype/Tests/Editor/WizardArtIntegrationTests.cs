using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public sealed class WizardArtIntegrationTests
    {
        private const string SourceRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128";
        private const string InventoryPath = SourceRoot + "/source-inventory.json";
        private const string GeneratedRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated";
        private const int SourceSize = 128;
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

            SourceInventory inventory = LoadInventory();
            foreach (WizardVariant variant in Variants)
            {
                int groundLine = GroundLineFor(inventory, variant.SourceFolder);
                foreach (string direction in Directions)
                {
                    AssertSourceImport(StandingPath(variant.SourceFolder, direction), groundLine);
                    for (int frame = 0; frame < WalkFrameCount; frame++)
                        AssertSourceImport(WalkPath(variant.SourceFolder, direction, frame), groundLine);
                }
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
        public void ShippedPlayerAndHudPrefabsUseThe128PixelStandingSprites()
        {
            const string playerPath = "Assets/NoSafeCircle/DoorPrototype/Resources/Player/Player.prefab";
            const string hudPath = "Assets/NoSafeCircle/DoorPrototype/Resources/Hud/Hud.prefab";
            GameObject player = AssetDatabase.LoadAssetAtPath<GameObject>(playerPath);
            Assert.IsNotNull(player, playerPath);
            Transform visual = player.transform.Find("Visual");
            Assert.IsNotNull(visual, playerPath);
            Assert.AreEqual(Vector3.one, visual.localScale, playerPath + " Visual scale");
            Assert.That(Quaternion.Angle(visual.localRotation, Quaternion.Euler(30f, -45f, 0f)),
                Is.LessThan(0.01f), playerPath + " Visual camera facing");
            SpriteRenderer playerRenderer = visual.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(playerRenderer, playerPath);
            Assert.IsNotNull(playerRenderer.sprite, playerPath);
            Assert.AreEqual(StandingPath("masculine-light", "south-east"),
                AssetDatabase.GetAssetPath(playerRenderer.sprite), playerPath);

            GameObject hud = AssetDatabase.LoadAssetAtPath<GameObject>(hudPath);
            Assert.IsNotNull(hud, hudPath);
            WizardSelectionController selection = hud.GetComponent<WizardSelectionController>();
            Assert.IsNotNull(selection, hudPath);
            Assert.AreEqual(Variants.Length, selection.OptionCount, hudPath);
            for (int index = 0; index < Variants.Length; index++)
            {
                Sprite preview = selection.GetOption(index).PreviewSprite;
                Assert.IsNotNull(preview, hudPath + " option " + index);
                Assert.AreEqual(StandingPath(Variants[index].SourceFolder, "south-east"),
                    AssetDatabase.GetAssetPath(preview), hudPath + " option " + index);
            }
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

        private static void AssertSourceImport(string path, int groundLine)
        {
            Assert.That(groundLine, Is.InRange(1, SourceSize), path);
            float expectedPivotY = (SourceSize - groundLine) / (float)SourceSize;
            TextureImporter importer = AssetImporter.GetAtPath(path) as TextureImporter;
            Assert.IsNotNull(importer, path);
            Assert.AreEqual(TextureImporterType.Sprite, importer.textureType, path);
            Assert.AreEqual(TextureImporterShape.Texture2D, importer.textureShape, path);
            Assert.AreEqual(SpriteImportMode.Single, importer.spriteImportMode, path);
            Assert.AreEqual(FilterMode.Point, importer.filterMode, path);
            Assert.AreEqual(TextureImporterCompression.Uncompressed, importer.textureCompression, path);
            Assert.IsFalse(importer.mipmapEnabled, path);
            Assert.AreEqual(64f, importer.spritePixelsPerUnit, path);
            SerializedObject serializedImporter = new SerializedObject(importer);
            SerializedProperty gamma = serializedImporter.FindProperty("m_ApplyGammaDecoding");
            SerializedProperty cookie = serializedImporter.FindProperty("m_CookieLightType");
            Assert.IsNotNull(gamma, path + " gamma import reset");
            Assert.IsNotNull(cookie, path + " cookie import reset");
            if (gamma.propertyType == SerializedPropertyType.Boolean)
                Assert.IsFalse(gamma.boolValue, path + " gamma import reset");
            else
                Assert.AreEqual(0, gamma.intValue, path + " gamma import reset");
            Assert.AreEqual(0, cookie.intValue, path + " cookie import reset");

            var textureSettings = new TextureImporterSettings();
            importer.ReadTextureSettings(textureSettings);
            Assert.AreEqual((int)SpriteAlignment.Custom, textureSettings.spriteAlignment, path);
            Assert.That(textureSettings.spritePivot.x, Is.EqualTo(0.5f).Within(0.001f), path);
            Assert.That(textureSettings.spritePivot.y, Is.EqualTo(expectedPivotY).Within(0.0001f), path);

            Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
            Assert.IsNotNull(sprite, path);
            Assert.That(sprite.rect.width, Is.EqualTo(SourceSize).Within(0.001f), path);
            Assert.That(sprite.rect.height, Is.EqualTo(SourceSize).Within(0.001f), path);
            Assert.That(sprite.pivot.x, Is.EqualTo(SourceSize * 0.5f).Within(0.001f), path);
            Assert.That(sprite.pivot.y, Is.EqualTo(SourceSize - groundLine).Within(0.001f), path);
            Assert.That(sprite.rect.width / sprite.pixelsPerUnit,
                Is.EqualTo(2f).Within(0.001f), path);
            Assert.That(sprite.rect.height / sprite.pixelsPerUnit,
                Is.EqualTo(2f).Within(0.001f), path);

            var sourceTexture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                Assert.IsTrue(sourceTexture.LoadImage(File.ReadAllBytes(path)), path);
                Assert.AreEqual(SourceSize, sourceTexture.width, path);
                Assert.AreEqual(SourceSize, sourceTexture.height, path);
                Color32[] pixels = sourceTexture.GetPixels32();
                Assert.IsTrue(pixels.Any(pixel => pixel.a == 0), "No transparent pixels: " + path);
                Assert.IsTrue(pixels.Any(pixel => pixel.a > 0), "No visible character pixels: " + path);
                int lowestVisibleRowFromBottom = LowestOpaqueRow(pixels);
                Assert.AreEqual(SourceSize - groundLine, lowestVisibleRowFromBottom,
                    "The imported pivot must sit on this frame's actual planted feet: " + path);
            }
            finally
            {
                Object.DestroyImmediate(sourceTexture);
            }
        }

        private static int LowestOpaqueRow(Color32[] pixels)
        {
            for (int y = 0; y < SourceSize; y++)
            {
                int rowOffset = y * SourceSize;
                for (int x = 0; x < SourceSize; x++)
                {
                    if (pixels[rowOffset + x].a > 0) return y;
                }
            }

            Assert.Fail("A wizard source frame contains no opaque pixels.");
            return -1;
        }

        private static SourceInventory LoadInventory()
        {
            Assert.IsTrue(File.Exists(InventoryPath), InventoryPath);
            string json = File.ReadAllText(InventoryPath)
                .Replace("\"masculine-light\":", "\"masculine_light\":")
                .Replace("\"masculine-dark\":", "\"masculine_dark\":")
                .Replace("\"feminine-light\":", "\"feminine_light\":")
                .Replace("\"feminine-dark\":", "\"feminine_dark\":");
            SourceInventory inventory = JsonUtility.FromJson<SourceInventory>(json);
            Assert.IsNotNull(inventory, InventoryPath);
            Assert.IsNotNull(inventory.wizards, InventoryPath);
            return inventory;
        }

        private static int GroundLineFor(SourceInventory inventory, string variant)
        {
            switch (variant)
            {
                case "masculine-light": return inventory.wizards.masculine_light.ground_line_y_from_top;
                case "masculine-dark": return inventory.wizards.masculine_dark.ground_line_y_from_top;
                case "feminine-light": return inventory.wizards.feminine_light.ground_line_y_from_top;
                case "feminine-dark": return inventory.wizards.feminine_dark.ground_line_y_from_top;
                default: throw new ArgumentOutOfRangeException(nameof(variant));
            }
        }

        [Serializable]
        private sealed class SourceInventory
        {
            public WizardMap wizards;
        }

        [Serializable]
        private sealed class WizardMap
        {
            public WizardGroundLine masculine_light;
            public WizardGroundLine masculine_dark;
            public WizardGroundLine feminine_light;
            public WizardGroundLine feminine_dark;
        }

        [Serializable]
        private sealed class WizardGroundLine
        {
            public int ground_line_y_from_top;
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
            // THE ANCHOR HAS TO SURVIVE TOO, NOT JUST THE TARGET. This typeof only names a class in
            // order to reach its ASSEMBLY, and it used to name DoorPrototypeSceneBuilder - which is
            // being deleted with the old world. Repointing the GetType string at the generator (as
            // c453a5adc did) moved the half that was easy to see and left the half that resolves the
            // assembly pointing at a dying type. ArchitecturalTileGenerator is public, lives in the
            // same assembly, and survives the cutover.
            System.Type builderType = typeof(NoSafeCircle.DoorPrototype.Editor.Generation.ArchitecturalTileGenerator)
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
