using NoSafeCircle.DoorPrototype.Hud;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public class TitleScreenHudPrefabTests
    {
        private const string HudPath = "Assets/NoSafeCircle/DoorPrototype/Resources/Hud/Hud.prefab";

        [Test]
        public void RuntimeWorldHud_HasTransparentLeftTitleAndOneWiredChase()
        {
            GameObject hud = AssetDatabase.LoadAssetAtPath<GameObject>(HudPath);
            Assert.IsNotNull(hud);

            Transform panel = hud.transform.Find("TitleScreen");
            Transform card = panel?.Find("TitleCard");
            Assert.IsNotNull(panel);
            Assert.IsNotNull(card);
            Assert.AreEqual(0f, panel.GetComponent<Image>().color.a, 0.001f);
            Assert.IsTrue(panel.GetComponent<Image>().raycastTarget);
            Assert.IsNull(card.GetComponent<Image>());
            Assert.IsNull(card.GetComponent<Outline>());
            Assert.LessOrEqual(card.GetComponent<RectTransform>().anchorMax.x, 0.5f);

            AssertSaying(card, "Eyebrow", "WELCOME, TINY WIZARD");
            AssertSaying(card, "Title", "NO SAFE CIRCLE");
            AssertSaying(card, "Tagline", "Cute wizards. Terrible odds.");

            Button button = card.Find("StartGameButton")?.GetComponent<Button>();
            Assert.IsNotNull(button);
            Assert.LessOrEqual(button.GetComponent<RectTransform>().anchorMax.x, 0.5f);
            Assert.GreaterOrEqual(button.GetComponent<RectTransform>().rect.width, 300f);
            Assert.AreEqual("START GAME", card.Find("StartGameButton/Text").GetComponent<Text>().text);
            Assert.AreEqual(1, button.onClick.GetPersistentEventCount());
            Assert.AreEqual(nameof(TitleScreenController.StartGame),
                button.onClick.GetPersistentMethodName(0));
            AssertColor((Color)new Color32(152, 65, 119, 255), button.targetGraphic.color);
            AssertColor((Color)new Color32(255, 211, 225, 255), button.colors.highlightedColor);
            AssertColor((Color)new Color32(205, 145, 178, 255), button.colors.pressedColor);

            TitleScreenChaseBackdrop[] backdrops = hud.GetComponents<TitleScreenChaseBackdrop>();
            Assert.AreEqual(1, backdrops.Length);
            SerializedObject chase = new SerializedObject(backdrops[0]);
            Assert.AreEqual(1f, chase.FindProperty("wizardVisualScale").floatValue);
            Assert.AreEqual(1f, chase.FindProperty("pursuerVisualScale").floatValue);
            SerializedObject bindings = new SerializedObject(hud.GetComponent<HudBindings>());
            Assert.AreSame(backdrops[0], bindings.FindProperty("titleChase").objectReferenceValue);
            Assert.IsNotNull(bindings.FindProperty("wizardChaseAnimator").objectReferenceValue);
            Assert.IsNotNull(bindings.FindProperty("meleeChaseAnimator").objectReferenceValue);
            Assert.IsNotNull(bindings.FindProperty("wraithChaseAnimator").objectReferenceValue);

            TitleScreenGameplayHudVisibility visibility =
                hud.GetComponent<TitleScreenGameplayHudVisibility>();
            Assert.IsNotNull(visibility);
            SerializedObject visibilitySerialized = new SerializedObject(visibility);
            Assert.AreSame(hud.GetComponent<TitleScreenController>(),
                visibilitySerialized.FindProperty("titleScreen").objectReferenceValue);
            SerializedProperty groups = visibilitySerialized.FindProperty("gameplayGroups");
            string[] gameplayNames =
            {
                "InteractPrompt", "ProgressFill", "HealthFill", "ManaFill",
                "DebugDamageButton", "DebugManaSpendButton", "ControlsHud"
            };
            Assert.AreEqual(gameplayNames.Length, groups.arraySize);
            for (int index = 0; index < gameplayNames.Length; index++)
            {
                CanvasGroup group = hud.transform.Find(gameplayNames[index])?.GetComponent<CanvasGroup>();
                Assert.IsNotNull(group, gameplayNames[index]);
                Assert.AreSame(group, groups.GetArrayElementAtIndex(index).objectReferenceValue);
            }
        }

        private static void AssertSaying(Transform card, string name, string expected)
        {
            Text text = card.Find(name)?.GetComponent<Text>();
            Assert.IsNotNull(text);
            Assert.AreEqual(expected, text.text);
            Assert.LessOrEqual(text.rectTransform.anchorMax.x, 0.5f);
            Assert.AreEqual(TextAnchor.MiddleLeft, text.alignment);
        }

        private static void AssertColor(Color expected, Color actual)
        {
            Assert.That(actual.r, Is.EqualTo(expected.r).Within(0.00001f));
            Assert.That(actual.g, Is.EqualTo(expected.g).Within(0.00001f));
            Assert.That(actual.b, Is.EqualTo(expected.b).Within(0.00001f));
            Assert.That(actual.a, Is.EqualTo(expected.a).Within(0.00001f));
        }
    }
}
