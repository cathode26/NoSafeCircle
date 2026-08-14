using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

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
    }
}
