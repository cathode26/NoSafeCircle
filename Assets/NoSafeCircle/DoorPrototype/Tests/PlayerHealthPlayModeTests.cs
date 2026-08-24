using System;
using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class PlayerHealthPlayModeTests
    {
        private GameObject playerObject;
        private PlayerHealth health;

        [SetUp]
        public void SetUp()
        {
            playerObject = new GameObject("TestPlayer");
            health = playerObject.AddComponent<PlayerHealth>();
        }

        [TearDown]
        public void TearDown()
        {
            if (playerObject != null)
            {
                UnityEngine.Object.DestroyImmediate(playerObject);
            }
        }

        // AC-001: owner-controlled restoration, clamped to max health.
        [Test]
        public void Restore_HealsThroughOwnerControlledEntryPoint_AndClampsToMaximum()
        {
            var maxHealth = ReadMaxHealth();
            health.TakeDamage(maxHealth * 0.75f);

            InvokeRequiredMethod("Restore", maxHealth * 2f);

            Assert.That(
                health.CurrentHealth,
                Is.EqualTo(maxHealth).Within(0.001f),
                "Restore must heal through PlayerHealth and clamp CurrentHealth to MaxHealth.");
        }

        // AC-002: observable zero-health transition exactly once.
        [Test]
        public void Died_EventFiresExactlyOnce_WhenHealthTransitionsToZero()
        {
            var eventInfo = typeof(PlayerHealth).GetEvent("Died", BindingFlags.Instance | BindingFlags.Public);
            Assert.That(
                eventInfo,
                Is.Not.Null,
                "PlayerHealth must expose a public Died event so restart/game-flow code can observe the zero-health transition.");

            var deathCount = 0;
            Action handler = () => deathCount++;
            eventInfo.AddEventHandler(health, handler);

            var maxHealth = ReadMaxHealth();
            health.TakeDamage(maxHealth);
            health.TakeDamage(maxHealth);

            Assert.That(health.CurrentHealth, Is.EqualTo(0f).Within(0.001f));
            Assert.That(
                deathCount,
                Is.EqualTo(1),
                "The death transition must be emitted exactly once when health first reaches zero.");
        }

        // AC-004: floor restart goes through the state owner's reset API.
        [Test]
        public void ResetHealth_RestoresFloorInitialHealth()
        {
            var maxHealth = ReadMaxHealth();
            health.TakeDamage(maxHealth * 0.5f);

            InvokeRequiredMethod("ResetHealth");

            Assert.That(
                health.CurrentHealth,
                Is.EqualTo(maxHealth).Within(0.001f),
                "ResetHealth must restore the floor-initial health state.");
        }

        // AC-005: health does not passively regenerate.
        [UnityTest]
        public IEnumerator Health_DoesNotPassivelyRegenerate()
        {
            var maxHealth = ReadMaxHealth();
            health.TakeDamage(maxHealth * 0.4f);
            var damagedHealth = health.CurrentHealth;

            // Advance real Play Mode frames so any accidental Update-based passive
            // regeneration would have an opportunity to modify health.
            for (var i = 0; i < 30; i++)
            {
                yield return null;
            }

            Assert.That(
                health.CurrentHealth,
                Is.EqualTo(damagedHealth).Within(0.001f),
                "Health must not passively regenerate during or between rooms.");
        }

        // AC-003 + VAL-001/VAL-002 support: continuous player-facing health indicator.
        [Test]
        public void PlayerHealthUI_ContinuouslyReflectsCurrentHealthFraction()
        {
            var maxHealth = ReadMaxHealth();
            health.TakeDamage(maxHealth * 0.25f);

            var canvasObject = new GameObject("Canvas", typeof(Canvas));
            var fillObject = new GameObject("HealthFill", typeof(RectTransform), typeof(Image));
            fillObject.transform.SetParent(canvasObject.transform, false);
            var fillImage = fillObject.GetComponent<Image>();

            var uiObject = new GameObject("HealthUI");
            var uiType = typeof(PlayerHealthUI);
            var ui = uiObject.AddComponent(uiType);

            try
            {
                SetRequiredField(ui, "health", health);
                SetRequiredField(ui, "fillImage", fillImage);

                InvokeRequiredInstanceMethod(ui, "Update");

                Assert.That(
                    fillImage.fillAmount,
                    Is.EqualTo(0.75f).Within(0.001f),
                    "The health indicator must continuously reflect CurrentHealth / MaxHealth.");
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(uiObject);
                UnityEngine.Object.DestroyImmediate(canvasObject);
            }
        }

        private float ReadMaxHealth()
        {
            var property = typeof(PlayerHealth).GetProperty(
                "MaxHealth",
                BindingFlags.Instance | BindingFlags.Public);

            Assert.That(
                property,
                Is.Not.Null,
                "PlayerHealth must expose MaxHealth so the continuous health indicator can represent current/maximum health.");

            var value = property.GetValue(health);
            Assert.That(value, Is.TypeOf<float>());
            return (float)value;
        }

        private void InvokeRequiredMethod(string methodName, params object[] arguments)
        {
            var method = typeof(PlayerHealth).GetMethod(
                methodName,
                BindingFlags.Instance | BindingFlags.Public);

            Assert.That(
                method,
                Is.Not.Null,
                $"PlayerHealth must expose the owner-controlled {methodName} entry point.");

            method.Invoke(health, arguments);
        }

        private static void SetRequiredField(Component target, string fieldName, UnityEngine.Object value)
        {
            var field = target.GetType().GetField(
                fieldName,
                BindingFlags.Instance | BindingFlags.NonPublic);

            Assert.That(
                field,
                Is.Not.Null,
                $"{target.GetType().Name} must contain serialized field '{fieldName}'.");

            field.SetValue(target, value);
        }

        private static void InvokeRequiredInstanceMethod(Component target, string methodName)
        {
            var method = target.GetType().GetMethod(
                methodName,
                BindingFlags.Instance | BindingFlags.NonPublic);

            Assert.That(
                method,
                Is.Not.Null,
                $"{target.GetType().Name} must implement {methodName}().");

            method.Invoke(target, null);
        }
    }
}
