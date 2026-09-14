using NoSafeCircle.DoorPrototype.Presentation;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Presentation
{
    // NSC-058 VAL-001/002: in-memory visual targets, no saved scene or prefab.
    public sealed class HierarchyFaderEditModeTests
    {
        private GameObject root;
        private Material testMaterial;

        [SetUp]
        public void SetUp() => root = new GameObject("HierarchyFader test root");

        [TearDown]
        public void TearDown()
        {
            if (root != null) Object.DestroyImmediate(root);
            if (testMaterial != null) Object.DestroyImmediate(testMaterial);
        }

        [Test]
        public void BuiltInTargetsFadeAndRestoreTheirOriginalState()
        {
            var groupObject = new GameObject("Canvas group", typeof(RectTransform), typeof(CanvasGroup));
            groupObject.transform.SetParent(root.transform);
            CanvasGroup group = groupObject.GetComponent<CanvasGroup>();
            group.alpha = 0.8f;
            Image groupedImage = AddImage(groupObject.transform, "Image in group");
            groupedImage.color = new Color(0.2f, 0.3f, 0.4f, 0.6f);
            var nestedObject = new GameObject("Nested canvas group", typeof(RectTransform), typeof(CanvasGroup));
            nestedObject.transform.SetParent(groupObject.transform);
            CanvasGroup nestedGroup = nestedObject.GetComponent<CanvasGroup>();
            nestedGroup.alpha = 0.5f;

            Image independentImage = AddImage(root.transform, "Independent image");
            Color originalImageColor = new Color(0.4f, 0.5f, 0.6f, 0.7f);
            independentImage.color = originalImageColor;

            SpriteRenderer sprite = new GameObject("Sprite").AddComponent<SpriteRenderer>();
            sprite.transform.SetParent(root.transform);
            Color originalSpriteColor = new Color(0.7f, 0.6f, 0.5f, 0.4f);
            sprite.color = originalSpriteColor;

            HierarchyFader fader = root.AddComponent<HierarchyFader>();
            fader.FadeTo(0.5f, 0f);

            Assert.That(group.alpha, Is.EqualTo(0.4f).Within(0.001f));
            Assert.That(nestedGroup.alpha, Is.EqualTo(0.5f).Within(0.001f),
                "The outer CanvasGroup already fades its nested group.");
            Assert.That(groupedImage.color.a, Is.EqualTo(0.6f).Within(0.001f),
                "The CanvasGroup already fades its child Graphic; do not square its alpha.");
            Assert.That(independentImage.color.a, Is.EqualTo(0.35f).Within(0.001f));
            Assert.That(sprite.color.a, Is.EqualTo(0.2f).Within(0.001f));

            fader.Restore();
            Assert.That(fader.HasOwnedTween, Is.False);
            Assert.That(group.alpha, Is.EqualTo(0.8f));
            Assert.That(nestedGroup.alpha, Is.EqualTo(0.5f));
            AssertColorNear(groupedImage.color, new Color(0.2f, 0.3f, 0.4f, 0.6f));
            AssertColorNear(independentImage.color, originalImageColor);
            AssertColorNear(sprite.color, originalSpriteColor);
        }

        [Test]
        public void RendererUsesPropertyBlockAndRestoresPreviousOverrides()
        {
            Shader shader = Shader.Find("Sprites/Default");
            Assert.That(shader, Is.Not.Null);
            testMaterial = new Material(shader);
            var rendererObject = new GameObject("Generic renderer");
            rendererObject.transform.SetParent(root.transform);
            MeshRenderer renderer = rendererObject.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = testMaterial;
            int colorId = testMaterial.HasProperty("_BaseColor")
                ? Shader.PropertyToID("_BaseColor") : Shader.PropertyToID("_Color");
            Assert.That(testMaterial.HasProperty(colorId), Is.True);
            Color materialColor = testMaterial.GetColor(colorId);
            Color originalOverride = new Color(0.3f, 0.4f, 0.5f, 0.8f);
            int markerId = Shader.PropertyToID("_NSC_FaderTestMarker");
            var originalBlock = new MaterialPropertyBlock();
            originalBlock.SetColor(colorId, originalOverride);
            originalBlock.SetFloat(markerId, 0.42f);
            renderer.SetPropertyBlock(originalBlock);

            HierarchyFader fader = root.AddComponent<HierarchyFader>();
            fader.FadeTo(0.25f, 0f);
            var during = new MaterialPropertyBlock();
            renderer.GetPropertyBlock(during);
            Assert.That(during.GetColor(colorId).a, Is.EqualTo(0.2f).Within(0.001f));
            Assert.That(during.GetFloat(markerId), Is.EqualTo(0.42f).Within(0.001f));
            Assert.That(renderer.sharedMaterial, Is.SameAs(testMaterial));
            AssertColorNear(testMaterial.GetColor(colorId), materialColor);

            fader.Restore();
            var restored = new MaterialPropertyBlock();
            renderer.GetPropertyBlock(restored);
            AssertColorNear(restored.GetColor(colorId), originalOverride);
            Assert.That(restored.GetFloat(markerId), Is.EqualTo(0.42f).Within(0.001f));
            Assert.That(renderer.sharedMaterial, Is.SameAs(testMaterial));
        }

        [Test]
        public void CustomTargetCancellationAndTemporaryInstantFadeRestore()
        {
            var custom = new RecordingTarget { Value = 0.8f };
            HierarchyFader fader = root.AddComponent<HierarchyFader>();
            fader.RegisterTarget(custom);
            fader.FadeTo(0.5f, 0f);
            Assert.That(custom.Value, Is.EqualTo(0.4f).Within(0.001f));
            fader.Cancel(false);
            Assert.That(fader.HasOwnedTween, Is.False);
            Assert.That(custom.Value, Is.EqualTo(0.4f).Within(0.001f));

            fader.FadeTo(0f, 0f, restoreOnComplete: true);
            Assert.That(fader.HasOwnedTween, Is.False);
            Assert.That(custom.Value, Is.EqualTo(0.8f).Within(0.001f));
            Assert.That(custom.CaptureCount, Is.EqualTo(1));
            Assert.That(custom.RestoreCount, Is.EqualTo(1));
        }

        [Test]
        public void TimedFadeRequiresPlayMode()
        {
            HierarchyFader fader = root.AddComponent<HierarchyFader>();
            Assert.Throws<System.InvalidOperationException>(() => fader.FadeTo(0f, 1f));
            Assert.That(fader.HasOwnedTween, Is.False);
        }

        private static Image AddImage(Transform parent, string name)
        {
            var gameObject = new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            gameObject.transform.SetParent(parent);
            return gameObject.GetComponent<Image>();
        }

        private static void AssertColorNear(Color actual, Color expected)
        {
            Assert.That(Vector4.Distance(actual, expected), Is.LessThan(0.0001f));
        }

        private sealed class RecordingTarget : IFadeTarget
        {
            private float original;
            public float Value;
            public int CaptureCount;
            public int RestoreCount;
            public bool IsValid => true;
            public void CaptureOriginalState() { original = Value; CaptureCount++; }
            public void ApplyOpacity(float normalizedOpacity) => Value = original * normalizedOpacity;
            public void RestoreOriginalState() { Value = original; RestoreCount++; }
        }
    }
}
