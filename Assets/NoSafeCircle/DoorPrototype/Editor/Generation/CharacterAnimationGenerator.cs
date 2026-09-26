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
    // and controller names, same frame ordering, same import settings as before.
    //
    // The enemy equivalent (melee + lantern wraith) was already its own file before this move -
    // World/EnemyAnimationAssetBuilder.cs - and is left where it is.
    internal static class CharacterAnimationGenerator
    {
        // Also read by DoorPrototypeGlobalSceneBuilder.LoadWizardSelectionPreview, for the wizard
        // selection screen's preview art, which is why these two stay internal instead of private.
        internal const string WizardSourceRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab";
        internal const string WizardCanonicalInitialDirection = "south-east";

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
            EnsureFolder("Assets/NoSafeCircle/DoorPrototype/Art");
            EnsureFolder("Assets/NoSafeCircle/DoorPrototype/Art/Wizard");
            EnsureFolder(WizardGeneratedRoot);
            var controllerPath = WizardGeneratedRoot + "/WizardAnimator.controller";
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
            if (controller == null) controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);

            var stateMachine = controller.layers[0].stateMachine;
            Sprite defaultIdle = null;
            foreach (var variant in WizardVariants)
            {
                var sourceVariant = variant.Replace("_White", "-light").Replace("_Black", "-dark")
                    .Replace("Masculine", "masculine").Replace("Feminine", "feminine");
                foreach (var standingDirection in WizardStandingDirections)
                {
                    ImportWizardSprite(WizardSourceRoot + "/" + sourceVariant + "/selected/standing/" + standingDirection + ".png");
                }
                foreach (var direction in WizardDirections)
                {
                    var standingPath = WizardSourceRoot + "/" + sourceVariant + "/selected/standing/" + direction + ".png";
                    var idle = ImportWizardSprite(standingPath);
                    var idleName = "Wizard_" + variant + "_idle_" + direction;
                    EnsureWizardState(stateMachine, idleName, EnsureWizardClip(idleName, new[] { idle }, 1));
                    if (variant == "Masculine_White" && direction == WizardCanonicalInitialDirection)
                        defaultIdle = idle;

                    var walk = new Sprite[6];
                    for (var frame = 0; frame < walk.Length; frame++)
                    {
                        var walkPath = WizardSourceRoot + "/" + sourceVariant + "/selected/walk/" + direction + "/frame_00" + frame + ".png";
                        walk[frame] = ImportWizardSprite(walkPath);
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
                WizardSourceRoot + "/masculine-light/selected/standing/south-east.png");
            return new WizardAnimationAssets(controller, defaultIdle);
        }

        private static Sprite ImportWizardSprite(string path)
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
            importer.spritePixelsPerUnit = 180f;
            var textureSettings = new TextureImporterSettings();
            importer.ReadTextureSettings(textureSettings);
            textureSettings.spriteAlignment = (int)SpriteAlignment.Custom;
            textureSettings.spritePivot = new Vector2(0.5f, 0f);
            importer.SetTextureSettings(textureSettings);
            ClearCookieImportDefaults(importer);
            importer.SaveAndReimport();
            var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
            if (sprite == null) throw new InvalidDataException("Wizard source did not import as a Sprite: " + path);
            return sprite;
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
