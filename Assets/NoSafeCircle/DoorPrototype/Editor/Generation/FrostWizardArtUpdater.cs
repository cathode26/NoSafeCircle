using System;
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Editor.Generation
{
    internal static class FrostWizardArtUpdater
    {
        private const string HudPath = "Assets/NoSafeCircle/DoorPrototype/Resources/Hud/Hud.prefab";

        [MenuItem("No Safe Circle/Update Strawberry Wizard Artwork")]
        public static void Apply()
        {
            CharacterAnimationGenerator.BuildFeminineLightWizardAnimationAssets();
            string previewPath = CharacterAnimationGenerator.GetWizardStandingSourcePath(
                "feminine-light", CharacterAnimationGenerator.WizardCanonicalInitialDirection);
            Sprite preview = AssetDatabase.LoadAssetAtPath<Sprite>(previewPath);
            if (preview == null) throw new InvalidOperationException("Frost preview sprite is missing: " + previewPath);

            GameObject hud = PrefabUtility.LoadPrefabContents(HudPath);
            try
            {
                WizardSelectionController selection = hud.GetComponent<WizardSelectionController>();
                if (selection == null || selection.OptionCount != 4 ||
                    selection.GetOption(2).Presentation != WizardPresentation.Feminine ||
                    selection.GetOption(2).Skin != WizardSkin.White)
                    throw new InvalidOperationException("HUD option 2 is not the Strawberry Wizard.");

                SerializedObject serializedSelection = new SerializedObject(selection);
                SerializedProperty options = serializedSelection.FindProperty("options");
                Image image = options.GetArrayElementAtIndex(2).FindPropertyRelative("previewImage")
                    .objectReferenceValue as Image;
                if (image == null) throw new InvalidOperationException("Frost preview Image is missing.");
                image.sprite = preview;
                EditorUtility.SetDirty(image);
                PrefabUtility.SaveAsPrefabAsset(hud, HudPath);
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(hud);
            }

            Debug.Log("Strawberry Wizard artwork updated: eight idle directions, eight walk clips, and HUD portrait.");
        }
    }
}
