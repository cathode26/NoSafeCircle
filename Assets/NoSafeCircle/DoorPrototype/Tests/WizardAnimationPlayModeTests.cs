using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class WizardAnimationPlayModeTests
    {
        [Test]
        public void PlayerVisualHasOneWizardAnimationDriverAndRetainsGroundContact()
        {
            var player = GameObject.Find("Player");
            Assert.IsNotNull(player);
            Assert.AreEqual(1, player.GetComponents<WizardAnimationController>().Length);
            Assert.IsNotNull(player.GetComponent<Animator>());
            var visual = player.transform.Find("Visual");
            Assert.IsNotNull(visual);
            Assert.That(visual.position.y, Is.EqualTo(player.transform.position.y).Within(0.001f));
        }
    }
}
