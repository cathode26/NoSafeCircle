using System.Collections;
using System.Linq;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class EnemyLanternWispCasterPlayModeTests
    {
        private GameObject wraithObject;
        private EnemyLanternWispCaster caster;
        private GameObject wizardObject;
        private PlayerHealth wizardHealth;

        [SetUp]
        public void SetUp()
        {
            wraithObject = new GameObject("LanternWraith");
            caster = wraithObject.AddComponent<EnemyLanternWispCaster>();
            caster.enabled = false;

            wizardObject = new GameObject("Wizard");
            wizardHealth = wizardObject.AddComponent<PlayerHealth>();
            caster.Initialize(wizardObject.transform);
        }

        [TearDown]
        public void TearDown()
        {
            foreach (GameObject wisp in AllWisps())
            {
                if (wisp != null) Object.DestroyImmediate(wisp);
            }

            if (wraithObject != null) Object.DestroyImmediate(wraithObject);
            if (wizardObject != null) Object.DestroyImmediate(wizardObject);
        }

        // NSC-077 AC-006/AC-007 and VAL-005: range and view are shared by casting and the
        // public read-only facing target, independently of mana/cooldown.
        [Test]
        public void Tick_CastsImmediatelyOnlyWithinRangeAndClearView()
        {
            wizardObject.transform.position = new Vector3(14f, 0f, 0f);
            Physics.SyncTransforms();
            Assert.IsTrue(caster.HasFacingTarget);
            Assert.AreSame(wizardObject.transform, caster.FacingTarget);

            caster.Tick(0f);

            Assert.AreEqual(50f, caster.CurrentMana);
            Assert.AreEqual(1, AllWisps().Length);

            DestroyAllWisps();
            wizardObject.transform.position = new Vector3(14.1f, 0f, 0f);
            Physics.SyncTransforms();
            Assert.IsFalse(caster.HasFacingTarget);
            Assert.IsNull(caster.FacingTarget);
            caster.Tick(2f);
            Assert.AreEqual(50f, caster.CurrentMana);
            Assert.AreEqual(0, AllWisps().Length);
        }

        [Test]
        public void Tick_WallBlocksCastingAndFacingTarget()
        {
            wizardObject.transform.position = new Vector3(6f, 0f, 0f);
            GameObject wall = GameObject.CreatePrimitive(PrimitiveType.Cube);
            wall.name = "CastBlockingWall";
            wall.transform.position = new Vector3(3f, 1f, 0f);
            wall.transform.localScale = new Vector3(0.25f, 2f, 2f);
            try
            {
                Physics.SyncTransforms();
                Assert.IsFalse(caster.HasFacingTarget);
                Assert.IsNull(caster.FacingTarget);

                caster.Tick(0f);

                Assert.AreEqual(60f, caster.CurrentMana);
                Assert.AreEqual(0, AllWisps().Length);
            }
            finally
            {
                Object.DestroyImmediate(wall);
            }
        }

        // NSC-077 AC-007 and VAL-005: unchanged one-second cadence spends six 10-mana casts
        // from 60 mana, then stops.
        [Test]
        public void Tick_CastsOncePerSecondAndStopsAfterSixCasts()
        {
            wizardObject.transform.position = new Vector3(10f, 0f, 0f);
            Physics.SyncTransforms();

            caster.Tick(0f);
            Assert.AreEqual(50f, caster.CurrentMana);
            Assert.AreEqual(1, AllWisps().Length);

            DestroyAllWisps();
            caster.Tick(0.99f);
            Assert.AreEqual(50f, caster.CurrentMana);
            Assert.AreEqual(0, AllWisps().Length);
            caster.Tick(0.02f);
            Assert.AreEqual(40f, caster.CurrentMana);
            Assert.AreEqual(1, AllWisps().Length);

            for (int cast = 0; cast < 4; cast++)
            {
                DestroyAllWisps();
                caster.Tick(1f);
                Assert.AreEqual(
                    1,
                    AllWisps().Length,
                    "Exactly one LanternWisp must be cast at each one-second interval.");
            }

            Assert.AreEqual(0f, caster.CurrentMana);
            Assert.IsTrue(caster.IsOutOfMana);
            DestroyAllWisps();
            caster.Tick(10f);
            Assert.AreEqual(0f, caster.CurrentMana);
            Assert.AreEqual(0, AllWisps().Length, "No cast is allowed after all 60 mana is spent.");
        }

        // NSC-077 AC-007 and VAL-005: each projectile keeps the existing size/speed/lifetime
        // while presenting only the approved teal ghost-light color.
        [UnityTest]
        public IEnumerator LanternWisp_HasTealLookMovesEightUnitsPerSecondAndExpiresAtFourSeconds()
        {
            wizardObject.transform.position = new Vector3(10f, 0f, 0f);
            Physics.SyncTransforms();
            caster.Tick(0f);

            GameObject wisp = AllWisps().Single();
            Assert.AreEqual("LanternWisp", wisp.name);
            Assert.AreEqual(Vector3.one * 0.45f, wisp.transform.localScale);
            Renderer renderer = wisp.GetComponent<Renderer>();
            Assert.IsNotNull(renderer);
            Color expectedTeal = new Color32(0x30, 0xe0, 0xcb, 0xff);
            Assert.That(renderer.material.color.r, Is.EqualTo(expectedTeal.r).Within(0.001f));
            Assert.That(renderer.material.color.g, Is.EqualTo(expectedTeal.g).Within(0.001f));
            Assert.That(renderer.material.color.b, Is.EqualTo(expectedTeal.b).Within(0.001f));

            float startX = wisp.transform.position.x;
            wizardObject.transform.position = new Vector3(30f, 0f, 0f);
            Physics.SyncTransforms();
            caster.Tick(0.25f);
            Assert.That(wisp.transform.position.x - startX, Is.EqualTo(2f).Within(0.001f));

            caster.Tick(3.74f);
            yield return null;
            Assert.IsTrue(wisp != null, "The wisp must live until its four-second lifetime.");
            caster.Tick(0.02f);
            yield return null;
            Assert.IsTrue(wisp == null, "The wisp must be destroyed after four seconds.");
        }

        // NSC-077 AC-007 and VAL-005: the existing hit radius delivers exactly five damage
        // through PlayerHealth.TakeDamage.
        [Test]
        public void LanternWisp_HitsWithinPointEightUnitsAndDealsFiveDamage()
        {
            wizardObject.transform.position = new Vector3(3.79f, 0f, 0f);
            Physics.SyncTransforms();
            float startingHealth = wizardHealth.CurrentHealth;

            caster.Tick(0f);
            caster.Tick(0.25f);

            Assert.That(wizardHealth.CurrentHealth, Is.EqualTo(startingHealth - 5f).Within(0.001f));
        }

        [Test]
        public void LanternWisp_DoesNotHitOutsidePointEightUnits()
        {
            wizardObject.transform.position = new Vector3(3.81f, 0f, 0f);
            Physics.SyncTransforms();
            float startingHealth = wizardHealth.CurrentHealth;

            caster.Tick(0f);
            caster.Tick(0.25f);

            Assert.That(wizardHealth.CurrentHealth, Is.EqualTo(startingHealth).Within(0.001f));
            Assert.AreEqual(1, AllWisps().Length);
        }

        private static GameObject[] AllWisps()
        {
            return Object.FindObjectsByType<GameObject>(
                    FindObjectsInactive.Include, FindObjectsSortMode.None)
                .Where(candidate => candidate.name == "LanternWisp")
                .ToArray();
        }

        private static void DestroyAllWisps()
        {
            foreach (GameObject wisp in AllWisps())
            {
                Object.DestroyImmediate(wisp);
            }
        }
    }
}
