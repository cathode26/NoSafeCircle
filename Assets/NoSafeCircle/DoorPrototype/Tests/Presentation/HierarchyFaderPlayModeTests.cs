using System.Collections;
using DG.Tweening;
using NoSafeCircle.DoorPrototype.Presentation;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests.Presentation
{
    // NSC-058 VAL-002: in-memory owner lifecycle, no saved scene or prefab.
    public sealed class HierarchyFaderPlayModeTests
    {
        [UnityTest]
        public IEnumerator ReplacementCancelAndTemporaryCompletionOwnOneTween()
        {
            var root = new GameObject("Fader replacement owner");
            SpriteRenderer sprite = root.AddComponent<SpriteRenderer>();
            sprite.color = new Color(0.2f, 0.4f, 0.6f, 0.8f);
            HierarchyFader fader = root.AddComponent<HierarchyFader>();

            Tween first = fader.FadeTo(0f, 2f);
            first.Goto(1f, false);
            Assert.That(sprite.color.a, Is.EqualTo(0.4f).Within(0.001f));
            Tween second = fader.FadeTo(1f, 2f);
            Assert.That(first.IsActive(), Is.False);
            Assert.That(second.IsActive(), Is.True);
            Assert.That(sprite.color.a, Is.EqualTo(0.4f).Within(0.001f));

            fader.Cancel(false);
            Assert.That(second.IsActive(), Is.False);
            Assert.That(fader.HasOwnedTween, Is.False);
            Assert.That(sprite.color.a, Is.EqualTo(0.4f).Within(0.001f));

            Tween temporary = fader.FadeTo(0f, 1f, restoreOnComplete: true);
            temporary.Complete();
            Assert.That(fader.HasOwnedTween, Is.False);
            Assert.That(DOTween.IsTweening(fader), Is.False);
            Assert.That(sprite.color.a, Is.EqualTo(0.8f).Within(0.001f));

            Object.Destroy(root);
            yield return null;
        }

        [UnityTest]
        public IEnumerator DisableAndDestroyKillOwnedTweensAndRestoreSprite()
        {
            var root = new GameObject("Fader owner");
            SpriteRenderer sprite = root.AddComponent<SpriteRenderer>();
            sprite.color = new Color(0.2f, 0.4f, 0.6f, 0.8f);
            HierarchyFader fader = root.AddComponent<HierarchyFader>();
            Tween first = fader.FadeTo(0f, 10f);
            yield return null;

            fader.enabled = false;
            Assert.That(first.IsActive(), Is.False);
            Assert.That(sprite.color.a, Is.EqualTo(0.8f).Within(0.001f));
            Assert.That(fader.HasOwnedTween, Is.False);

            fader.enabled = true;
            Tween second = fader.FadeTo(0f, 10f);
            Object.Destroy(root);
            yield return null;
            Assert.That(second.IsActive(), Is.False);
        }
    }
}
