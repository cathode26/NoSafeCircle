using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Editor.Generation
{
    // port/extract-animation-generation (2026-09-26): extracted verbatim from
    // World/DoorPrototypeGlobalSceneBuilder.cs, whose BuildPlayer either loads these committed
    // assets or (when handed a temp architecturalTileAssetFolder) regenerates them here instead.
    // The old scenes and their builders are going away; this is the wizard's only asset producer
    // and has to survive that delete so the 64 committed .anim files plus WizardAnimator.controller
    // under Art/Wizard/Generated/ can still be regenerated. Pure move: same asset paths, same clip
    // and controller names and frame ordering. NSC-096 switches the source and import geometry.
    //
    // The enemy equivalent (melee + lantern wraith) was already its own file before this move -
    // World/EnemyAnimationAssetBuilder.cs - and is left where it is.
    internal static class CharacterAnimationGenerator
    {
        // Keep the original source archive intact when one variant uses a newer source canvas.
        internal const string WizardSourceRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128";
        internal const string WizardCanonicalInitialDirection = "south-east";

        private const string FeminineLightWizardSourceRoot =
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab256/feminine-light";
        private const string WizardGeneratedRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated";

        private static readonly string[] WizardVariants =
        {
            "Masculine_White",
            "Masculine_Black",
            "Feminine_White",
            "Feminine_Black"
        };

        private static readonly string[] WizardDirections =
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

        private static readonly string[] WizardStandingDirections = WizardDirections;

        internal readonly struct WizardAnimationAssets
        {
            public readonly RuntimeAnimatorController controller;
            public readonly Sprite defaultIdle;

            public WizardAnimationAssets(RuntimeAnimatorController controller, Sprite defaultIdle)
            {
                this.controller = controller;
                this.defaultIdle = defaultIdle;
            }
        }

        internal static WizardAnimationAssets BuildWizardAnimationAssets()
        {
            return BuildWizardAnimationAssets(null);
        }

        /// <summary>Regenerates only the replacement Frost wizard's sprites and existing clips.</summary>
        public static void BuildFeminineLightWizardAnimationAssets()
        {
            BuildWizardAnimationAssets("Feminine_White");
        }

        private static WizardAnimationAssets BuildWizardAnimationAssets(string onlyVariant)
        {
            Dictionary<string, WizardSpriteSourceSettings> sourceSettings = ReadWizardSourceSettings(onlyVariant);
            EnsureFolder("Assets/NoSafeCircle/DoorPrototype/Art");
            EnsureFolder("Assets/NoSafeCircle/DoorPrototype/Art/Wizard");
            EnsureFolder(WizardGeneratedRoot);
            var controllerPath = WizardGeneratedRoot + "/WizardAnimator.controller";
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
            if (controller == null && onlyVariant != null)
                throw new InvalidDataException("A single-wizard regeneration requires the existing controller: " + controllerPath);
            if (controller == null) controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);

            var stateMachine = controller.layers[0].stateMachine;
            Sprite defaultIdle = AssetDatabase.LoadAssetAtPath<Sprite>(
                GetWizardStandingSourcePath("masculine-light", WizardCanonicalInitialDirection));
            foreach (var variant in WizardVariants)
            {
                if (onlyVariant != null && variant != onlyVariant) continue;
                var sourceVariant = variant.Replace("_White", "-light").Replace("_Black", "-dark")
                    .Replace("Masculine", "masculine").Replace("Feminine", "feminine");
                WizardSpriteSourceSettings settings = sourceSettings[sourceVariant];
                foreach (var standingDirection in WizardStandingDirections)
                {
                    ImportWizardSprite(GetWizardStandingSourcePath(sourceVariant, standingDirection),
                        settings.PivotFor(standingDirection), settings.PixelsPerUnit);
                }
                foreach (var direction in WizardDirections)
                {
                    Vector2 sourcePivot = settings.PivotFor(direction);
                    var standingPath = GetWizardStandingSourcePath(sourceVariant, direction);
                    var idle = ImportWizardSprite(standingPath, sourcePivot, settings.PixelsPerUnit);
                    var idleName = "Wizard_" + variant + "_idle_" + direction;
                    EnsureWizardState(stateMachine, idleName, EnsureWizardClip(idleName, new[] { idle }, 1));
                    if (variant == "Masculine_White" && direction == WizardCanonicalInitialDirection)
                        defaultIdle = idle;

                    var walk = new Sprite[6];
                    for (var frame = 0; frame < walk.Length; frame++)
                    {
                        var walkPath = GetWizardWalkSourcePath(sourceVariant, direction, frame);
                        walk[frame] = ImportWizardSprite(walkPath, sourcePivot, settings.PixelsPerUnit);
                    }
                    var walkName = "Wizard_" + variant + "_walk_" + direction;
                    EnsureWizardState(stateMachine, walkName, EnsureWizardClip(walkName, walk, 12));
                }
            }
            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssetIfDirty(controller);
            return new WizardAnimationAssets(controller, defaultIdle);
        }

        internal static WizardAnimationAssets LoadWizardAnimationAssets()
        {
            var controller = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(
                WizardGeneratedRoot + "/WizardAnimator.controller");
            var defaultIdle = AssetDatabase.LoadAssetAtPath<Sprite>(
                GetWizardStandingSourcePath("masculine-light", WizardCanonicalInitialDirection));
            return new WizardAnimationAssets(controller, defaultIdle);
        }

        internal static string GetWizardStandingSourcePath(string sourceVariant, string direction)
        {
            ValidateWizardDirection(direction);
            return GetWizardVariantSourceRoot(sourceVariant) + "/selected/standing/" + direction + ".png";
        }

        internal static string GetWizardWalkSourcePath(string sourceVariant, string direction, int frame)
        {
            ValidateWizardDirection(direction);
            if (frame < 0 || frame >= 6) throw new ArgumentOutOfRangeException(nameof(frame));
            return GetWizardVariantSourceRoot(sourceVariant) + "/selected/walk/" + direction +
                "/frame_" + frame.ToString("000") + ".png";
        }

        private static string GetWizardVariantSourceRoot(string sourceVariant)
        {
            switch (sourceVariant)
            {
                case "feminine-light": return FeminineLightWizardSourceRoot;
                case "masculine-light":
                case "masculine-dark":
                case "feminine-dark": return WizardSourceRoot + "/" + sourceVariant;
                default: throw new ArgumentOutOfRangeException(nameof(sourceVariant));
            }
        }

        private static void ValidateWizardDirection(string direction)
        {
            if (Array.IndexOf(WizardDirections, direction) < 0)
                throw new ArgumentOutOfRangeException(nameof(direction));
        }

        private static Sprite ImportWizardSprite(string path, Vector2 sourcePivot, float pixelsPerUnit)
        {
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null) throw new FileNotFoundException("Wizard source is not a texture", path);
            importer.textureType = TextureImporterType.Sprite;
            importer.textureShape = TextureImporterShape.Texture2D;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.filterMode = FilterMode.Point;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.mipmapEnabled = false;
            importer.spritePixelsPerUnit = pixelsPerUnit;
            var textureSettings = new TextureImporterSettings();
            importer.ReadTextureSettings(textureSettings);
            textureSettings.spriteAlignment = (int)SpriteAlignment.Custom;
            textureSettings.spritePivot = sourcePivot;
            importer.SetTextureSettings(textureSettings);
            ClearCookieImportDefaults(importer);
            importer.SaveAndReimport();
            var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
            if (sprite == null) throw new InvalidDataException("Wizard source did not import as a Sprite: " + path);
            return sprite;
        }

        private static Dictionary<string, WizardSpriteSourceSettings> ReadWizardSourceSettings(string onlyVariant)
        {
            if (onlyVariant == "Feminine_White")
            {
                return new Dictionary<string, WizardSpriteSourceSettings>
                {
                    { "feminine-light", ReadFeminineLightSourceSettings() }
                };
            }

            string inventoryPath = WizardSourceRoot + "/source-inventory.json";
            if (!File.Exists(inventoryPath))
                throw new FileNotFoundException("Wizard source inventory is missing", inventoryPath);

            // JsonUtility has no dictionary support. Only the four property names are changed;
            // source file paths and provenance records keep their committed PixelLab spelling.
            string json = File.ReadAllText(inventoryPath);
            foreach (string variant in new[]
            {
                "masculine-light", "masculine-dark", "feminine-light", "feminine-dark"
            })
                json = json.Replace("\"" + variant + "\":", "\"" + variant.Replace('-', '_') + "\":");

            WizardSourceInventory inventory = JsonUtility.FromJson<WizardSourceInventory>(json);
            if (inventory == null || inventory.canvas == null || inventory.canvas.Length != 2 ||
                inventory.canvas[0] != 128 || inventory.canvas[1] != 128 || inventory.wizards == null)
                throw new InvalidDataException("Wizard source inventory must describe a 128 x 128 canvas and four wizards: " + inventoryPath);

            return new Dictionary<string, WizardSpriteSourceSettings>
            {
                { "masculine-light", LegacySourceSettings(inventory.wizards.masculine_light, "masculine-light") },
                { "masculine-dark", LegacySourceSettings(inventory.wizards.masculine_dark, "masculine-dark") },
                { "feminine-light", ReadFeminineLightSourceSettings() },
                { "feminine-dark", LegacySourceSettings(inventory.wizards.feminine_dark, "feminine-dark") }
            };
        }

        private static WizardSpriteSourceSettings LegacySourceSettings(WizardSourceWizard wizard, string variant)
        {
            Vector2 pivot = GroundLinePivot(wizard, variant);
            var directionPivots = new Dictionary<string, Vector2>();
            foreach (string direction in WizardDirections) directionPivots.Add(direction, pivot);
            return new WizardSpriteSourceSettings(64f, directionPivots);
        }

        private static WizardSpriteSourceSettings ReadFeminineLightSourceSettings()
        {
            string inventoryPath = FeminineLightWizardSourceRoot + "/source-inventory.json";
            if (!File.Exists(inventoryPath))
                throw new FileNotFoundException("Frost wizard source inventory is missing", inventoryPath);
            WizardVariantSourceInventory inventory = JsonUtility.FromJson<WizardVariantSourceInventory>(
                File.ReadAllText(inventoryPath));
            if (inventory == null || inventory.canvas == null || inventory.canvas.Length != 2 ||
                inventory.canvas[0] != 256 || inventory.canvas[1] != 256 ||
                inventory.pixels_per_unit <= 0f || float.IsNaN(inventory.pixels_per_unit) ||
                float.IsInfinity(inventory.pixels_per_unit) || inventory.directions == null ||
                inventory.directions.Length != WizardDirections.Length)
                throw new InvalidDataException("Frost wizard inventory requires a 256 x 256 canvas, positive pixels_per_unit and eight direction ground lines: " + inventoryPath);

            var directionPivots = new Dictionary<string, Vector2>();
            foreach (WizardDirectionGroundLine direction in inventory.directions)
            {
                if (direction == null || Array.IndexOf(WizardDirections, direction.id) < 0 ||
                    directionPivots.ContainsKey(direction.id) || direction.ground_line_y_from_top < 1 ||
                    direction.ground_line_y_from_top > inventory.canvas[1])
                    throw new InvalidDataException("Frost wizard inventory has an invalid or duplicate direction ground line: " + inventoryPath);
                // Keep one foot pivot for idle and the whole walk loop; do not erase gait drift.
                directionPivots.Add(direction.id, new Vector2(0.5f,
                    (inventory.canvas[1] - direction.ground_line_y_from_top) / (float)inventory.canvas[1]));
            }
            return new WizardSpriteSourceSettings(inventory.pixels_per_unit, directionPivots);
        }

        private static Vector2 GroundLinePivot(WizardSourceWizard wizard, string variant)
        {
            if (wizard == null || wizard.ground_line_y_from_top < 1 ||
                wizard.ground_line_y_from_top > 128)
                throw new InvalidDataException("Wizard source inventory has no valid ground line for " + variant);
            return new Vector2(0.5f, (128f - wizard.ground_line_y_from_top) / 128f);
        }

        [Serializable]
        private sealed class WizardSourceInventory
        {
            public int[] canvas;
            public WizardSourceWizards wizards;
        }

        [Serializable]
        private sealed class WizardSourceWizards
        {
            public WizardSourceWizard masculine_light;
            public WizardSourceWizard masculine_dark;
            public WizardSourceWizard feminine_light;
            public WizardSourceWizard feminine_dark;
        }

        [Serializable]
        private sealed class WizardSourceWizard
        {
            public int ground_line_y_from_top;
        }

        [Serializable]
        private sealed class WizardVariantSourceInventory
        {
            public int[] canvas;
            public float pixels_per_unit;
            public WizardDirectionGroundLine[] directions;
        }

        [Serializable]
        private sealed class WizardDirectionGroundLine
        {
            public string id;
            public int ground_line_y_from_top;
        }

        private sealed class WizardSpriteSourceSettings
        {
            private readonly Dictionary<string, Vector2> directionPivots;

            public WizardSpriteSourceSettings(float pixelsPerUnit, Dictionary<string, Vector2> directionPivots)
            {
                PixelsPerUnit = pixelsPerUnit;
                this.directionPivots = directionPivots;
            }

            public float PixelsPerUnit { get; }

            public Vector2 PivotFor(string direction)
            {
                return directionPivots[direction];
            }
        }

        // A GUID-only .meta imports with point-light cookie defaults; reset them to match every other wizard source.
        private static void ClearCookieImportDefaults(TextureImporter importer)
        {
            var serializedImporter = new SerializedObject(importer);
            foreach (var propertyName in new[] { "m_ApplyGammaDecoding", "m_CookieLightType" })
            {
                var property = serializedImporter.FindProperty(propertyName);
                if (property == null) throw new InvalidDataException("TextureImporter has no serialized property " + propertyName);
                if (property.propertyType == SerializedPropertyType.Boolean) property.boolValue = false;
                else property.intValue = 0;
            }

            serializedImporter.ApplyModifiedPropertiesWithoutUndo();
        }

        private static AnimationClip EnsureWizardClip(string name, Sprite[] sprites, int frameRate)
        {
            var path = WizardGeneratedRoot + "/" + name + ".anim";
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            if (clip == null)
            {
                clip = new AnimationClip { name = name };
                AssetDatabase.CreateAsset(clip, path);
            }
            clip.frameRate = frameRate;
            var keys = new ObjectReferenceKeyframe[sprites.Length];
            for (var i = 0; i < sprites.Length; i++)
                keys[i] = new ObjectReferenceKeyframe { time = i / (float)frameRate, value = sprites[i] };
            AnimationUtility.SetObjectReferenceCurve(clip,
                EditorCurveBinding.PPtrCurve("", typeof(SpriteRenderer), "m_Sprite"), null);
            AnimationUtility.SetObjectReferenceCurve(clip,
                EditorCurveBinding.PPtrCurve("Visual", typeof(SpriteRenderer), "m_Sprite"), keys);
            var settings = AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime = true;
            AnimationUtility.SetAnimationClipSettings(clip, settings);
            EditorUtility.SetDirty(clip);
            AssetDatabase.SaveAssetIfDirty(clip);
            return clip;
        }

        private static void EnsureWizardState(AnimatorStateMachine stateMachine, string name, AnimationClip clip)
        {
            foreach (var child in stateMachine.states)
            {
                if (child.state.name != name) continue;
                child.state.motion = clip;
                return;
            }
            stateMachine.AddState(name).motion = clip;
        }

        private static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;

            string[] parts = path.Split('/');
            string current = parts[0];
            for (var index = 1; index < parts.Length; index++)
            {
                string next = current + "/" + parts[index];
                if (!AssetDatabase.IsValidFolder(next))
                {
                    AssetDatabase.CreateFolder(current, parts[index]);
                }

                current = next;
            }
        }
    }
}
