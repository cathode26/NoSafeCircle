using System;
using NoSafeCircle.DoorPrototype.Hud;
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor.World
{
    /// <summary>Applies the title layout to the HUD used by RuntimeWorld.</summary>
    public static class TitleScreenHudPrefabBuilder
    {
        private const string HudPath = "Assets/NoSafeCircle/DoorPrototype/Resources/Hud/Hud.prefab";
        private const string WizardControllerPath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/WizardAnimator.controller";
        private const string MeleeControllerPath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Generated/MeleeEnemyAnimator.controller";
        private const string WraithControllerPath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Generated/LanternWraithAnimator.controller";

        [MenuItem("No Safe Circle/Build/Title Screen HUD Prefab")]
        public static void Build()
        {
            GameObject root = PrefabUtility.LoadPrefabContents(HudPath);
            try
            {
                Transform panel = Required(root.transform, "TitleScreen");
                Image panelImage = RequiredComponent<Image>(panel);
                panelImage.color = new Color(panelImage.color.r, panelImage.color.g,
                    panelImage.color.b, 0f);
                panelImage.raycastTarget = true;

                Transform card = Required(panel, "TitleCard");
                RemoveIfPresent<Outline>(card.gameObject);
                RemoveIfPresent<Image>(card.gameObject);
                RemoveIfPresent<CanvasRenderer>(card.gameObject);
                RectTransform cardRect = RequiredComponent<RectTransform>(card);
                cardRect.anchorMin = new Vector2(0f, 0.5f);
                cardRect.anchorMax = new Vector2(0f, 0.5f);
                cardRect.pivot = new Vector2(0f, 0.5f);
                cardRect.anchoredPosition = new Vector2(96f, 0f);
                cardRect.sizeDelta = new Vector2(740f, 620f);

                RectTransform accent = RequiredComponent<RectTransform>(Required(card, "Accent"));
                accent.anchorMin = new Vector2(0f, 1f);
                accent.anchorMax = new Vector2(0f, 1f);
                accent.pivot = new Vector2(0f, 1f);
                accent.anchoredPosition = new Vector2(0f, -34f);

                AlignText(Required(card, "Eyebrow"));
                AlignText(Required(card, "Title"));
                AlignText(Required(card, "Tagline"));

                RectTransform button = RequiredComponent<RectTransform>(Required(card, "StartGameButton"));
                button.anchorMin = new Vector2(0f, 0.22f);
                button.anchorMax = new Vector2(0f, 0.22f);
                button.pivot = new Vector2(0f, 0.5f);
                button.anchoredPosition = Vector2.zero;
                button.sizeDelta = new Vector2(380f, 82f);

                Transform footer = card.Find("Footer");
                if (footer != null)
                {
                    Object.DestroyImmediate(footer.gameObject);
                }

                TitleScreenChaseBackdrop chase = root.GetComponent<TitleScreenChaseBackdrop>();
                if (chase == null)
                {
                    chase = root.AddComponent<TitleScreenChaseBackdrop>();
                }

                HudBindings bindings = root.GetComponent<HudBindings>();
                if (bindings == null)
                {
                    throw new InvalidOperationException("Hud.prefab is missing HudBindings.");
                }

                SerializedObject serialized = new SerializedObject(bindings);
                Assign(serialized, "titleChase", chase);
                RuntimeAnimatorController wizard = RequiredController(WizardControllerPath);
                RuntimeAnimatorController melee = RequiredController(MeleeControllerPath);
                RuntimeAnimatorController wraith = RequiredController(WraithControllerPath);
                Assign(serialized, "wizardChaseAnimator", wizard);
                Assign(serialized, "meleeChaseAnimator", melee);
                Assign(serialized, "wraithChaseAnimator", wraith);
                serialized.ApplyModifiedPropertiesWithoutUndo();

                SerializedObject chaseSerialized = new SerializedObject(chase);
                Assign(chaseSerialized, "titleScreen", root.GetComponent<TitleScreenController>());
                Assign(chaseSerialized, "wizardAnimatorController", wizard);
                Assign(chaseSerialized, "meleeAnimatorController", melee);
                Assign(chaseSerialized, "wraithAnimatorController", wraith);
                AssignFloat(chaseSerialized, "wizardVisualScale", 1f);
                AssignFloat(chaseSerialized, "pursuerVisualScale", 1f);
                chaseSerialized.ApplyModifiedPropertiesWithoutUndo();

                string[] gameplayNames =
                {
                    "InteractPrompt", "ProgressFill", "HealthFill", "ManaFill",
                    "DebugDamageButton", "DebugManaSpendButton", "ControlsHud"
                };
                var gameplayGroups = new CanvasGroup[gameplayNames.Length];
                for (int index = 0; index < gameplayNames.Length; index++)
                {
                    GameObject visual = Required(root.transform, gameplayNames[index]).gameObject;
                    gameplayGroups[index] = visual.GetComponent<CanvasGroup>();
                    if (gameplayGroups[index] == null)
                        gameplayGroups[index] = visual.AddComponent<CanvasGroup>();
                }

                TitleScreenGameplayHudVisibility visibility =
                    root.GetComponent<TitleScreenGameplayHudVisibility>();
                if (visibility == null)
                    visibility = root.AddComponent<TitleScreenGameplayHudVisibility>();
                SerializedObject visibilitySerialized = new SerializedObject(visibility);
                Assign(visibilitySerialized, "titleScreen", root.GetComponent<TitleScreenController>());
                SerializedProperty groups = visibilitySerialized.FindProperty("gameplayGroups");
                if (groups == null)
                    throw new InvalidOperationException("Title HUD visibility is missing gameplayGroups.");
                groups.arraySize = gameplayGroups.Length;
                for (int index = 0; index < gameplayGroups.Length; index++)
                    groups.GetArrayElementAtIndex(index).objectReferenceValue = gameplayGroups[index];
                visibilitySerialized.ApplyModifiedPropertiesWithoutUndo();

                GameObject saved = PrefabUtility.SaveAsPrefabAsset(root, HudPath);
                if (saved == null)
                {
                    throw new InvalidOperationException("Unity could not save Hud.prefab.");
                }
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(root);
            }

            AssetDatabase.SaveAssets();
        }

        private static void AlignText(Transform transform)
        {
            RectTransform rect = RequiredComponent<RectTransform>(transform);
            rect.anchorMin = new Vector2(0f, rect.anchorMin.y);
            rect.anchorMax = new Vector2(0f, rect.anchorMax.y);
            rect.pivot = new Vector2(0f, 0.5f);
            rect.anchoredPosition = new Vector2(0f, rect.anchoredPosition.y);
            rect.sizeDelta = new Vector2(700f, rect.sizeDelta.y);
            RequiredComponent<Text>(transform).alignment = TextAnchor.MiddleLeft;
        }

        private static T RequiredComponent<T>(Transform transform) where T : Component
        {
            T component = transform.GetComponent<T>();
            if (component == null)
            {
                throw new InvalidOperationException($"{transform.name} is missing {typeof(T).Name}.");
            }
            return component;
        }

        private static Transform Required(Transform parent, string path)
        {
            Transform child = parent.Find(path);
            if (child == null)
            {
                throw new InvalidOperationException($"Hud.prefab is missing {path} under {parent.name}.");
            }
            return child;
        }

        private static RuntimeAnimatorController RequiredController(string path)
        {
            RuntimeAnimatorController controller = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(path);
            if (controller == null)
            {
                throw new InvalidOperationException($"Animator controller is missing: {path}");
            }
            return controller;
        }

        private static void Assign(SerializedObject serialized, string name, Object value)
        {
            SerializedProperty property = serialized.FindProperty(name);
            if (property == null)
            {
                throw new InvalidOperationException($"HudBindings is missing serialized field {name}.");
            }
            property.objectReferenceValue = value;
        }

        private static void RemoveIfPresent<T>(GameObject gameObject) where T : Component
        {
            T component = gameObject.GetComponent<T>();
            if (component != null)
            {
                Object.DestroyImmediate(component);
            }
        }

        private static void AssignFloat(SerializedObject serialized, string name, float value)
        {
            SerializedProperty property = serialized.FindProperty(name);
            if (property == null)
            {
                throw new InvalidOperationException($"TitleScreenChaseBackdrop is missing {name}.");
            }
            property.floatValue = value;
        }
    }
}
