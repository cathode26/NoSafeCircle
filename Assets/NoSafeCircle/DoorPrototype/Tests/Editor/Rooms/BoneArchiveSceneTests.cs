using NUnit.Framework;
using UnityEngine;
using NoSafeCircle.DoorPrototype.World.Rooms;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    public class BoneArchiveSceneTests
    {
        [Test] // AC-001: the authored room measurements match the approved blockout.
        public void Layout_ContainsApprovedShellShelvesAndDoors()
        {
            Assert.That(BoneArchiveLayout.RoomBounds.min, Is.EqualTo(new Vector3(-10f, 0f, 0f)));
            Assert.That(BoneArchiveLayout.RoomBounds.max, Is.EqualTo(new Vector3(10f, 0f, 20f)));
            Assert.That(BoneArchiveLayout.ShelfA.size, Is.EqualTo(new Vector3(1.5f, 2.5f, 12f)));
            Assert.That(BoneArchiveLayout.ShelfB.size, Is.EqualTo(new Vector3(1.5f, 2.5f, 11f)));
            Assert.That(BoneArchiveLayout.ShelfC.size, Is.EqualTo(new Vector3(1.5f, 2.5f, 11f)));
            Assert.That(BoneArchiveLayout.D1, Is.EqualTo(new Vector3(0f, 0f, 0f)));
            Assert.That(BoneArchiveLayout.D2, Is.EqualTo(new Vector3(6f, 0f, 20f)));
        }

        [Test] // AC-002: deliberate pinch and all ordinary lanes remain at or above the minimum.
        public void Layout_PreservesLaneWidthsAndBypasses()
        {
            Assert.That(BoneArchiveLayout.ClearWidthBetween(BoneArchiveLayout.ShelfA, BoneArchiveLayout.ShelfB), Is.EqualTo(3.5f));
            Assert.That(BoneArchiveLayout.ClearWidthBetween(BoneArchiveLayout.ShelfB, BoneArchiveLayout.ShelfC), Is.EqualTo(3.5f));
            Assert.That(BoneArchiveLayout.ShelfA.min.x - (-10f), Is.GreaterThanOrEqualTo(3f));
            Assert.That(10f - BoneArchiveLayout.ShelfC.max.x, Is.GreaterThanOrEqualTo(3f));
            Assert.That(BoneArchiveLayout.ShelfC.min.x - BoneArchiveLayout.CollapsedFurnitureBA1.max.x, Is.EqualTo(2.5f));
            Assert.That(BoneArchiveLayout.MinLaneWidth, Is.EqualTo(2.5f));
        }
    }
}
