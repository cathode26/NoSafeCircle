using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using NoSafeCircle.DoorPrototype.World.Rooms;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class BoneArchiveNavigationPlayModeTests
    {
        [UnityTest] // VAL-001: geometry exposes the required pinch to the configured navigation layer.
        public IEnumerator ApprovedPinchIsNotNarrowerThanNavigationMinimum()
        {
            yield return null;
            Assert.That(BoneArchiveLayout.ShelfC.min.x - BoneArchiveLayout.CollapsedFurnitureBA1.max.x,
                Is.GreaterThanOrEqualTo(BoneArchiveLayout.MinLaneWidth));
        }
    }
}
