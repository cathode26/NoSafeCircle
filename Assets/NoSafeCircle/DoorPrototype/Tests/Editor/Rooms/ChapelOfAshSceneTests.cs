using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine;
using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NoSafeCircle.DoorPrototype.World.Rooms;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    public class ChapelOfAshSceneTests
    {
        [Test] // AC-001: approved room shell, doors, aisle, pews, and columns are encoded in layout data.
        public void Layout_ContainsApprovedChapelBlockout()
        {
            Assert.That(ChapelOfAshLayout.RoomBounds.min, Is.EqualTo(new Vector3(-12f, 0f, 20f)));
            Assert.That(ChapelOfAshLayout.RoomBounds.max, Is.EqualTo(new Vector3(12f, 0f, 42f)));
            Assert.That(ChapelOfAshLayout.D2, Is.EqualTo(new Vector3(6f, 0f, 20f)));
            Assert.That(ChapelOfAshLayout.D3, Is.EqualTo(new Vector3(-6f, 0f, 42f)));
            Assert.That(ChapelOfAshLayout.PewFootprints, Has.Length.EqualTo(8));
            Assert.That(ChapelOfAshLayout.ColumnCenters, Has.Length.EqualTo(4));
            Assert.That(ChapelOfAshLayout.CentralAisleWidth, Is.EqualTo(4f));
            Assert.That(ChapelOfAshLayout.PewFootprints[0].size, Is.EqualTo(new Vector3(5.5f, 1.25f, 1.5f)));
            Assert.That(ChapelOfAshLayout.ColumnBounds(ChapelOfAshLayout.ColumnCenters[0]).size, Is.EqualTo(new Vector3(1.5f, 2.5f, 1.5f)));
        }

        [Test] // AC-002: side routes and lateral openings remain available around repeated cover.
        public void Layout_PreservesSideRouteClearanceAndLateralOpenings()
        {
            float westClearance = ChapelOfAshLayout.ColumnCenters[0].x - ChapelOfAshLayout.ColumnBounds(ChapelOfAshLayout.ColumnCenters[0]).size.x * 0.5f - (ChapelOfAshLayout.MinimumX + ChapelOfAshLayout.WallThickness * 0.5f);
            float eastClearance = (ChapelOfAshLayout.MaximumX - ChapelOfAshLayout.WallThickness * 0.5f) - (ChapelOfAshLayout.ColumnCenters[1].x + ChapelOfAshLayout.ColumnBounds(ChapelOfAshLayout.ColumnCenters[1]).size.x * 0.5f);

            Assert.That(westClearance, Is.EqualTo(2.5f).Within(0.001f));
            Assert.That(eastClearance, Is.EqualTo(2.5f).Within(0.001f));
            Assert.That(ChapelOfAshLayout.PewFootprints[1].min.z - ChapelOfAshLayout.PewFootprints[0].max.z, Is.EqualTo(2.5f));
            Assert.That(ChapelOfAshLayout.MinimumSideRouteClearance, Is.EqualTo(2.5f));
        }

        [Test] // VAL-001: the builder keeps visible architecture separate from real gameplay colliders.
        public void Builder_CreatesSeparateVisualAndGameplayGeometryWithCover()
        {
            ChapelOfAshSceneBuilder.BuildInMemoryForTests();

            try
            {
                GameObject visuals = GameObject.Find("VisibleBlockout");
                GameObject gameplay = GameObject.Find("GameplayGeometry");
                GameObject westCover = GameObject.Find("CA-W");
                GameObject eastCover = GameObject.Find("CA-E");
                GameObject pewCollider = GameObject.Find("Pew1Collision");

                Assert.That(visuals, Is.Not.Null);
                Assert.That(gameplay, Is.Not.Null);
                Assert.That(westCover, Is.Not.Null);
                Assert.That(eastCover, Is.Not.Null);
                Assert.That(pewCollider, Is.Not.Null);
                Assert.That(visuals.GetComponentsInChildren<Collider>(), Is.Empty);
                Assert.That(gameplay.GetComponentsInChildren<BoxCollider>(), Has.Length.EqualTo(1 + 8 + 4 + 6));
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }

        [Test] // AC-001: D2 and D3 wall segments leave their approved three-unit openings.
        public void Builder_OffsetsDoorOpeningsAtApprovedCenters()
        {
            ChapelOfAshSceneBuilder.BuildInMemoryForTests();

            try
            {
                GameObject southWest = GameObject.Find("SouthWallWestVisual");
                GameObject southEast = GameObject.Find("SouthWallEastVisual");
                GameObject northWest = GameObject.Find("NorthWallWestVisual");
                GameObject northEast = GameObject.Find("NorthWallEastVisual");

                Assert.That(southWest.transform.localScale.x, Is.EqualTo(16.5f).Within(0.001f));
                Assert.That(southEast.transform.localScale.x, Is.EqualTo(4.5f).Within(0.001f));
                Assert.That(northWest.transform.localScale.x, Is.EqualTo(4.5f).Within(0.001f));
                Assert.That(northEast.transform.localScale.x, Is.EqualTo(16.5f).Within(0.001f));
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }
    }
}
