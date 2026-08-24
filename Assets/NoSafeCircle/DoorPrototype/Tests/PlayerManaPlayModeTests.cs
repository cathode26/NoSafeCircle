using System.Collections;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class PlayerManaPlayModeTests
    {
        private GameObject manaObject;
        private PlayerMana mana;

        [SetUp]
        public void SetUp()
        {
            manaObject = new GameObject("TestMana");
            mana = manaObject.AddComponent<PlayerMana>();
        }

        [TearDown]
        public void TearDown()
        {
            Object.Destroy(manaObject);
        }

        [UnityTest]
        public IEnumerator Spend_ReducesCurrentMana_WhenSufficient()
        {
            var before = mana.CurrentMana;

            var success = mana.Spend(20f);

            yield return null;

            Assert.IsTrue(success);
            Assert.AreEqual(before - 20f, mana.CurrentMana, 0.001f);
        }

        [UnityTest]
        public IEnumerator Spend_Fails_WhenAmountExceedsCurrentMana()
        {
            var before = mana.CurrentMana;

            var success = mana.Spend(before + 1f);

            yield return null;

            Assert.IsFalse(success);
            Assert.AreEqual(before, mana.CurrentMana, 0.001f);
        }

        [UnityTest]
        public IEnumerator Mana_DoesNotRegenerate_DuringPostCastDelay()
        {
            mana.Spend(30f);
            var afterSpend = mana.CurrentMana;

            AdvanceManaTime(mana, mana.PostCastRegenDelay * 0.5f);

            yield return null;

            Assert.AreEqual(afterSpend, mana.CurrentMana, 0.001f);
        }

        [UnityTest]
        public IEnumerator Mana_Regenerates_AfterPostCastDelayElapses()
        {
            mana.Spend(30f);
            var afterSpend = mana.CurrentMana;

            AdvanceManaTime(mana, mana.PostCastRegenDelay + 0.5f);

            yield return null;

            Assert.Greater(mana.CurrentMana, afterSpend);
        }

        [UnityTest]
        public IEnumerator Spend_DuringRegen_ResetsPostCastDelay()
        {
            mana.Spend(10f);
            AdvanceManaTime(mana, mana.PostCastRegenDelay + 0.5f);
            var regeneratedMana = mana.CurrentMana;

            mana.Spend(10f);
            var afterSecondSpend = mana.CurrentMana;
            AdvanceManaTime(mana, mana.PostCastRegenDelay * 0.5f);

            yield return null;

            Assert.Less(afterSecondSpend, regeneratedMana);
            Assert.AreEqual(afterSecondSpend, mana.CurrentMana, 0.001f);
        }

        private static void AdvanceManaTime(PlayerMana target, float totalSeconds)
        {
            const float step = 0.05f;
            var elapsed = 0f;
            while (elapsed < totalSeconds)
            {
                var dt = Mathf.Min(step, totalSeconds - elapsed);
                target.Tick(dt);
                elapsed += dt;
            }
        }

        // AC-001: ResetMana restores current mana to full for floor-restart orchestration.
        [UnityTest]
        public IEnumerator ResetMana_RestoresCurrentManaToFull_AfterPartialSpend()
        {
            mana.Spend(40f);
            Assert.Less(mana.CurrentMana, mana.MaxMana);

            mana.ResetMana();

            yield return null;

            Assert.AreEqual(mana.MaxMana, mana.CurrentMana, 0.001f);
        }

        // AC-001: ResetMana restores current mana to full even when the pool was fully spent.
        [UnityTest]
        public IEnumerator ResetMana_RestoresCurrentManaToFull_AfterManaFullySpent()
        {
            mana.Spend(mana.MaxMana);
            Assert.AreEqual(0f, mana.CurrentMana, 0.001f);

            mana.ResetMana();

            yield return null;

            Assert.AreEqual(mana.MaxMana, mana.CurrentMana, 0.001f);
        }

        // AC-001: ResetMana clears the post-cast regen-delay timer state. CurrentMana is
        // always driven to MaxMana by ResetMana, and Tick() short-circuits whenever
        // CurrentMana >= MaxMana, so the timer it clears has no observable effect through
        // the public Spend/Tick/CurrentMana surface alone. Reading the private timer field
        // directly is the only way to prove this half of AC-001, using the same
        // reflection-based private-member technique already established in this project's
        // Editor tests (see DoorPrototypeSceneBuilderTests / CommittedSceneCameraConformanceTests).
        [UnityTest]
        public IEnumerator ResetMana_ClearsPostCastRegenDelayTimerState()
        {
            mana.Spend(30f);
            AdvanceManaTime(mana, mana.PostCastRegenDelay * 0.25f);

            mana.ResetMana();

            yield return null;

            var timerField = typeof(PlayerMana).GetField("timeSinceLastSpend",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(timerField, "Expected a private timeSinceLastSpend field on PlayerMana.");
            var timerValue = (float)timerField.GetValue(mana);

            Assert.GreaterOrEqual(timerValue, mana.PostCastRegenDelay,
                "ResetMana must clear the post-cast regen-delay timer to an already-elapsed state.");
        }

        // AC-002: CastDenied fires when a cast is refused for insufficient mana, distinct
        // from a successful spend.
        [UnityTest]
        public IEnumerator Spend_RaisesCastDenied_WhenAmountExceedsCurrentMana()
        {
            float? deniedAmount = null;
            mana.CastDenied += amount => deniedAmount = amount;

            var requested = mana.CurrentMana + 10f;
            var success = mana.Spend(requested);

            yield return null;

            Assert.IsFalse(success);
            Assert.IsTrue(deniedAmount.HasValue,
                "Expected CastDenied to fire when a cast is refused for insufficient mana.");
            Assert.AreEqual(requested, deniedAmount.Value, 0.001f);
        }

        // AC-002: A successful spend must not also raise CastDenied.
        [UnityTest]
        public IEnumerator Spend_DoesNotRaiseCastDenied_WhenSpendSucceeds()
        {
            var deniedRaised = false;
            var spentRaised = false;
            mana.CastDenied += _ => deniedRaised = true;
            mana.ManaSpent += _ => spentRaised = true;

            var success = mana.Spend(20f);

            yield return null;

            Assert.IsTrue(success);
            Assert.IsTrue(spentRaised, "Expected ManaSpent to fire on a successful spend.");
            Assert.IsFalse(deniedRaised,
                "CastDenied must be distinct from a successful spend and must not fire when the cast succeeds.");
        }

        // Regression-only: a non-positive amount is a separate no-op path from an
        // insufficient-mana refusal and must not raise CastDenied.
        [UnityTest]
        public IEnumerator Spend_ZeroOrNegativeAmount_DoesNotRaiseCastDenied()
        {
            var deniedRaised = false;
            mana.CastDenied += _ => deniedRaised = true;

            var successZero = mana.Spend(0f);
            var successNegative = mana.Spend(-5f);

            yield return null;

            Assert.IsFalse(successZero);
            Assert.IsFalse(successNegative);
            Assert.IsFalse(deniedRaised,
                "CastDenied signals refusal specifically due to insufficient mana; a non-positive amount " +
                "request is a separate no-op path and must not raise it.");
        }

        // VAL-002/VAL-003: low-mana failure must be readable through the existing mana
        // indicator. PlayerManaUI's private mana/fillImage/deniedFlashDuration fields are
        // wired via reflection since they are intentionally not exposed publicly; the
        // component is then disabled/re-enabled so OnEnable re-subscribes to CastDenied
        // using the reflection-assigned mana reference (OnEnable already ran once with a
        // null mana field when AddComponent triggered the initial Awake/OnEnable pass).
        [UnityTest]
        public IEnumerator PlayerManaUI_FlashesDeniedColor_OnCastDenied_ThenRevertsAfterDuration()
        {
            var uiObject = new GameObject("TestManaUI");
            try
            {
                var image = uiObject.AddComponent<Image>();
                var ui = uiObject.AddComponent<PlayerManaUI>();

                SetPrivateField(ui, "mana", mana);
                SetPrivateField(ui, "fillImage", image);
                SetPrivateField(ui, "deniedFlashDuration", 0.05f);
                ui.enabled = false;
                ui.enabled = true;

                var normalColor = (Color)GetPrivateField(ui, "normalColor");
                var deniedColor = (Color)GetPrivateField(ui, "deniedColor");

                yield return null;

                Assert.AreEqual(normalColor, image.color,
                    "Expected the mana indicator to start in its normal color.");

                mana.Spend(mana.CurrentMana + 10f);

                yield return null;

                Assert.AreEqual(deniedColor, image.color,
                    "Failure caused by low mana must be readable through the mana indicator flashing a " +
                    "denied color.");

                yield return new WaitForSeconds(0.1f);
                yield return null;

                Assert.AreEqual(normalColor, image.color,
                    "Expected the denied flash to revert to the normal color after its duration.");
            }
            finally
            {
                Object.Destroy(uiObject);
            }
        }

        // Regression-only: a successful spend must not trigger the denied-cast flash.
        [UnityTest]
        public IEnumerator PlayerManaUI_DoesNotFlash_OnSuccessfulSpend()
        {
            var uiObject = new GameObject("TestManaUI");
            try
            {
                var image = uiObject.AddComponent<Image>();
                var ui = uiObject.AddComponent<PlayerManaUI>();

                SetPrivateField(ui, "mana", mana);
                SetPrivateField(ui, "fillImage", image);
                ui.enabled = false;
                ui.enabled = true;

                var normalColor = (Color)GetPrivateField(ui, "normalColor");

                yield return null;

                mana.Spend(10f);

                yield return null;

                Assert.AreEqual(normalColor, image.color,
                    "A successful spend must not trigger the denied-cast flash feedback.");
            }
            finally
            {
                Object.Destroy(uiObject);
            }
        }

        // VAL-002/VAL-003 (regression-only): the denied-flash revert must restore the fill
        // Image's actual pre-existing color (e.g. a scene-authored blue tint), not a
        // hardcoded C# field-initializer default. This specifically targets a prior
        // regression where a fresh AddComponent<Image>() default (white) happened to match
        // the field initializer and masked the mismatch against a non-white scene color.
        [UnityTest]
        public IEnumerator PlayerManaUI_RevertsToActualFillImageColor_NotHardcodedDefault()
        {
            var uiObject = new GameObject("TestManaUI");
            try
            {
                var image = uiObject.AddComponent<Image>();
                var sceneAuthoredColor = new Color(0f, 0f, 1f, 1f);
                image.color = sceneAuthoredColor;
                var ui = uiObject.AddComponent<PlayerManaUI>();

                SetPrivateField(ui, "mana", mana);
                SetPrivateField(ui, "fillImage", image);
                SetPrivateField(ui, "deniedFlashDuration", 0.05f);
                ui.enabled = false;
                ui.enabled = true;

                yield return null;

                Assert.AreEqual(sceneAuthoredColor, image.color,
                    "Expected the mana indicator to retain its scene-authored color before any denied flash.");

                mana.Spend(mana.CurrentMana + 10f);

                yield return null;

                Assert.AreEqual((Color)GetPrivateField(ui, "deniedColor"), image.color,
                    "Expected the denied-cast flash color to apply.");

                yield return new WaitForSeconds(0.1f);
                yield return null;

                Assert.AreEqual(sceneAuthoredColor, image.color,
                    "Expected the denied flash to revert to the fill Image's actual scene-authored color, " +
                    "not a hardcoded field-initializer default.");
            }
            finally
            {
                Object.Destroy(uiObject);
            }
        }

        // AC-003 (regression-only ownership-boundary invariant): PlayerMana continues to
        // own only current mana and post-cast regen-delay state and must not absorb
        // spell-local cooldown/charge/cast/placement/active-field state. This locks the
        // public API surface to the current mana-only member set so that ownership creep
        // would fail this test; it does not by itself prove no private spell-local state
        // was added.
        [Test]
        public void PlayerMana_PublicApiSurface_OnlyOwnsManaAndRegenDelayState()
        {
            const BindingFlags flags = BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly;

            var propertyNames = typeof(PlayerMana).GetProperties(flags).Select(p => p.Name);
            var eventNames = typeof(PlayerMana).GetEvents(flags).Select(e => e.Name);
            var methodNames = typeof(PlayerMana).GetMethods(flags).Where(m => !m.IsSpecialName).Select(m => m.Name);

            var declaredPublicMembers = propertyNames.Concat(eventNames).Concat(methodNames)
                .Distinct().OrderBy(n => n).ToArray();

            var expected = new[]
            {
                "CastDenied", "CurrentMana", "ManaSpent", "MaxMana", "PostCastRegenDelay", "ResetMana", "Spend", "Tick"
            };

            CollectionAssert.AreEquivalent(expected, declaredPublicMembers,
                "PlayerMana's public surface must stay limited to current mana and post-cast regen-delay " +
                "state; it must not grow to include spell-local cooldown/charge/cast/placement/active-field " +
                "members owned by Fireball/Frost Field/Force Wave.");
        }

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }

        private static object GetPrivateField(object target, string fieldName)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            return field.GetValue(target);
        }
    }
}
