using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using NoSafeCircle.DoorPrototype.Editor.Rooms;
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

        [Test] // AC-001: D2 is offset, so the north wall segments must straddle X=+6.
        public void Builder_OffsetsNorthOpeningToD2()
        {
            BoneArchiveSceneBuilder.BuildInMemoryForTests();

            try
            {
                GameObject west = GameObject.Find("NorthWallWest");
                GameObject east = GameObject.Find("NorthWallEast");

                Assert.That(west, Is.Not.Null);
                Assert.That(east, Is.Not.Null);
                Assert.That(west.transform.position.x, Is.EqualTo(-3f).Within(0.001f));
                Assert.That(west.transform.localScale.x, Is.EqualTo(14f).Within(0.001f));
                Assert.That(east.transform.position.x, Is.EqualTo(8.5f).Within(0.001f));
                Assert.That(east.transform.localScale.x, Is.EqualTo(3f).Within(0.001f));
            }
            finally
            {
                SceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }
    }
}
