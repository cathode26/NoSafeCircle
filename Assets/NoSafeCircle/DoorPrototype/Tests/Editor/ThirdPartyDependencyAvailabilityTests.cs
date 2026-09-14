using NUnit.Framework;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    // NSC-057 AC-003: compile and assembly-reference proof for the two tools.
    public sealed class ThirdPartyDependencyAvailabilityTests
    {
        [Test]
        public void SignalsApiResolvesFromItsPluginAssembly()
        {
            Assert.That(typeof(deVoid.Utils.Signals).Assembly.GetName().Name,
                Is.EqualTo("deVoid.Signals"));
        }

        [Test]
        public void DOTweenApiResolvesFromItsStandardPluginAssembly()
        {
            Assert.That(typeof(DG.Tweening.DOTween).Assembly.GetName().Name,
                Is.EqualTo("DOTween"));
        }
    }
}
