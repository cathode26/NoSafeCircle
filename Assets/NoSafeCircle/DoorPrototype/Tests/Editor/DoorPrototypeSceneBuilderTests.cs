using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Editor;
using UnityEditor;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public class DoorPrototypeSceneBuilderTests
    {
        [Test]
        public void Build_ProgressFillImage_HasSpriteAssignedSoFillAmountIsVisible()
        {
            DoorPrototypeSceneBuilder.Build();

            var fillImage = GameObject.Find("Canvas/ProgressFill/Fill")?.GetComponent<Image>();

            Assert.IsNotNull(fillImage, "Expected a 'Fill' Image under Canvas/ProgressFill after building the scene.");
            Assert.IsNotNull(fillImage.sprite,
                "Progress fill Image has no sprite. A Filled Image with no sprite renders as a static full rect and ignores fillAmount.");
            Assert.AreEqual(Image.Type.Filled, fillImage.type);
            Assert.AreEqual(Image.FillMethod.Horizontal, fillImage.fillMethod);
        }

        [Test]
        public void Build_RunTwice_DoesNotDuplicateProgressFillHierarchy()
        {
            DoorPrototypeSceneBuilder.Build();
            DoorPrototypeSceneBuilder.Build();

            var canvas = GameObject.Find("Canvas");
            var progressFillCount = 0;
            foreach (Transform child in canvas.transform)
            {
                if (child.name == "ProgressFill") progressFillCount++;
            }

            Assert.AreEqual(1, progressFillCount,
                "Re-running the scene builder must not duplicate the ProgressFill UI element.");
        }

        [Test]
        public void Build_ControlsHud_ExistsSeparateFromPromptAndProgressIndicator()
        {
            DoorPrototypeSceneBuilder.Build();

            var hud = GameObject.Find("Canvas/ControlsHud");
            Assert.IsNotNull(hud, "Expected a 'ControlsHud' object directly under Canvas.");

            var prompt = GameObject.Find("Canvas/InteractPrompt");
            var progress = GameObject.Find("Canvas/ProgressFill");
            Assert.AreNotEqual(hud, prompt, "Controls HUD must be a separate object from the interaction prompt.");
            Assert.AreNotEqual(hud, progress, "Controls HUD must be a separate object from the progress indicator.");
        }

        [Test]
        public void Build_ControlsHud_TextMatchesActualImplementedControls()
        {
            DoorPrototypeSceneBuilder.Build();

            var hudText = GameObject.Find("Canvas/ControlsHud/Text")?.GetComponent<Text>();
            Assert.IsNotNull(hudText, "Expected a 'Text' element under Canvas/ControlsHud.");
            StringAssert.Contains("WASD", hudText.text);
            StringAssert.Contains("Move", hudText.text);
            StringAssert.Contains("Hold E", hudText.text);
            StringAssert.Contains("cancels the opening attempt", hudText.text);

            var debugControl = GameObject.Find("Player")?.GetComponent<DebugDamageControl>();
            Assert.IsNotNull(debugControl, "Expected a DebugDamageControl on the generated Player.");
            var damageKey = (Key)new SerializedObject(debugControl).FindProperty("damageKey").enumValueIndex;
            StringAssert.Contains(damageKey.ToString(), hudText.text,
                "Displayed debug key must match the actual implemented damage-test key binding.");
            StringAssert.Contains("Debug", hudText.text,
                "The damage-test key must be clearly labeled as debug/test, not a normal gameplay ability.");
        }

        [Test]
        public void Build_RunTwice_DoesNotDuplicateControlsHud()
        {
            DoorPrototypeSceneBuilder.Build();
            DoorPrototypeSceneBuilder.Build();

            var canvas = GameObject.Find("Canvas");
            var hudCount = 0;
            foreach (Transform child in canvas.transform)
            {
                if (child.name == "ControlsHud") hudCount++;
            }

            Assert.AreEqual(1, hudCount, "Re-running the scene builder must not duplicate the ControlsHud panel.");
        }
    }
}
