using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Editor.World;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NoSafeCircle.DoorPrototype.World;
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
                GameObject west = GameObject.Find("NorthWallWestVisual");
                GameObject east = GameObject.Find("NorthWallEastVisual");

                Assert.That(west, Is.Not.Null);
                Assert.That(east, Is.Not.Null);
                Assert.That(west.transform.position.x, Is.EqualTo(-2.75f).Within(0.001f));
                Assert.That(west.transform.localScale.x, Is.EqualTo(14.5f).Within(0.001f));
                Assert.That(east.transform.position.x, Is.EqualTo(8.75f).Within(0.001f));
                Assert.That(east.transform.localScale.x, Is.EqualTo(2.5f).Within(0.001f));
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }

        [Test] // VAL-001: visible blockouts and gameplay colliders are separate twins.
        public void Builder_SeparatesApprovedVisualAndGameplayFootprints()
        {
            BoneArchiveSceneBuilder.BuildInMemoryForTests();

            try
            {
                GameObject visuals = GameObject.Find("Room_BoneArchive/Visuals");
                GameObject gameplay = GameObject.Find("Room_BoneArchive/GameplayGeometry");

                Assert.That(visuals, Is.Not.Null);
                Assert.That(gameplay, Is.Not.Null);
                Assert.That(visuals.GetComponentsInChildren<Renderer>(), Has.Length.GreaterThan(0));
                Assert.That(visuals.GetComponentsInChildren<Collider>(), Is.Empty);
                Assert.That(gameplay.GetComponentsInChildren<Renderer>(), Is.Empty);
                Assert.That(gameplay.GetComponentsInChildren<BoxCollider>(), Has.Length.EqualTo(11));
                AssertBounds("Shelf A", BoneArchiveLayout.ShelfA);
                AssertBounds("Shelf B", BoneArchiveLayout.ShelfB);
                AssertBounds("Shelf C", BoneArchiveLayout.ShelfC);
                AssertBounds("Collapsed Furniture BA-1", BoneArchiveLayout.CollapsedFurnitureBA1);
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }

        [Test] // Downstream composition gate: the committed source scene satisfies RoomSceneComposer.
        public void CommittedScene_ValidatesForComposition()
        {
            Scene scene = EditorSceneManager.OpenScene(BoneArchiveSceneBuilder.ScenePath, OpenSceneMode.Single);

            try
            {
                RoomSceneComposer.RoomValidationResult result = RoomSceneComposer.ValidateOpenRoomScene(
                    RoomId.BoneArchive,
                    scene,
                    FindRoomEntry(RoomId.BoneArchive),
                    RoomSceneCatalog.CreateCanonicalDoors());

                CollectionAssert.IsEmpty(result.Errors, string.Join("\n", result.Errors));
                Assert.That(result.DoorAnchors, Has.Count.EqualTo(2));
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }

        private static void AssertBounds(string baseName, Bounds expected)
        {
            GameObject visual = GameObject.Find(baseName + "Visual");
            GameObject collision = GameObject.Find(baseName + "Collision");
            Assert.That(visual, Is.Not.Null);
            Assert.That(collision, Is.Not.Null);
            Assert.That(new Bounds(visual.transform.position, visual.transform.localScale), Is.EqualTo(expected));
            Assert.That(collision.GetComponent<BoxCollider>().bounds, Is.EqualTo(expected));
        }

        private static RoomSceneCatalog.RoomCatalogEntry FindRoomEntry(RoomId roomId)
        {
            foreach (RoomSceneCatalog.RoomCatalogEntry entry in RoomSceneCatalog.CreateCanonicalRooms())
            {
                if (entry.RoomId == roomId)
                {
                    return entry;
                }
            }

            Assert.Fail($"Missing canonical catalog entry for {roomId}.");
            return null;
        }
    }
}
