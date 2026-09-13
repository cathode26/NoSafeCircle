using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    public sealed class FinalRoomSceneTests
    {
        [SetUp]
        public void SetUp() => FinalRoomSceneBuilder.BuildInMemoryForTests();

        [TearDown]
        public void TearDown() => EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        [Test]
        public void Layout_UsesApprovedShellDoorsAndSingleCentralObstacle()
        {
            Assert.That(FinalRoomLayout.RoomBounds.min, Is.EqualTo(new Vector3(-12f, 0f, 64f)));
            Assert.That(FinalRoomLayout.RoomBounds.max, Is.EqualTo(new Vector3(12f, 0f, 86f)));
            Assert.That(FinalRoomLayout.D4, Is.EqualTo(new Vector3(4f, 0f, 64f)));
            Assert.That(FinalRoomLayout.D5, Is.EqualTo(new Vector3(0f, 0f, 86f)));
            Assert.That(FinalRoomLayout.FinalObstacleBounds.size, Is.EqualTo(new Vector3(5f, 2f, 5f)));
        }

        [Test]
        public void Build_SeparatesVisualsAndGameplayGeometry()
        {
            GameObject visuals = GameObject.Find("Room_FinalRoom/Visuals");
            GameObject geometry = GameObject.Find("Room_FinalRoom/GameplayGeometry");
            Assert.IsNotNull(visuals);
            Assert.IsNotNull(geometry);
            Assert.Greater(visuals.GetComponentsInChildren<Renderer>().Length, 0);
            Assert.AreEqual(0, visuals.GetComponentsInChildren<Collider>().Length);
            Assert.AreEqual(0, geometry.GetComponentsInChildren<Renderer>().Length);
            Assert.Greater(geometry.GetComponentsInChildren<BoxCollider>().Length, 0);
        }

        [Test]
        public void Build_PreservesDoorOpeningsAndFourUnitCirculation()
        {
            AssertOpening("SouthWall", FinalRoomLayout.D4X);
            AssertOpening("NorthWall", FinalRoomLayout.D5X);
            Assert.That(FinalRoomLayout.WestCirculationWidth, Is.GreaterThanOrEqualTo(4f));
            Assert.That(FinalRoomLayout.EastCirculationWidth, Is.GreaterThanOrEqualTo(4f));
            Assert.IsFalse(FinalRoomLayout.NorthStagingBounds.Intersects(FinalRoomLayout.FinalObstacleBounds));
        }

        [Test]
        public void Build_ProvidesD4AndD5AnchorsAndBothSideRoutes()
        {
            Assert.IsNotNull(GameObject.Find("Room_FinalRoom/DoorAnchors/D4Anchor"));
            Assert.IsNotNull(GameObject.Find("Room_FinalRoom/DoorAnchors/D5Anchor"));
            Assert.That(FinalRoomLayout.FinalObstacleBounds.min.x, Is.GreaterThan(FinalRoomLayout.MinimumX));
            Assert.That(FinalRoomLayout.FinalObstacleBounds.max.x, Is.LessThan(FinalRoomLayout.MaximumX));
            Assert.That(FinalRoomLayout.FinalObstacleBounds.max.z, Is.LessThan(80f));
        }

        [Test]
        public void Build_BenchesHaveMatchingGameplayCollisionAndCandlesAreRecognizableDressing()
        {
            BoxCollider westBench = FindCollider("Room_FinalRoom/GameplayGeometry/WestBenchCollision");
            BoxCollider eastBench = FindCollider("Room_FinalRoom/GameplayGeometry/EastBenchCollision");
            Assert.That(westBench.bounds, Is.EqualTo(FinalRoomLayout.WestBenchBounds));
            Assert.That(eastBench.bounds, Is.EqualTo(FinalRoomLayout.EastBenchBounds));

            for (int index = 1; index <= 5; index++)
            {
                GameObject candle = GameObject.Find($"Room_FinalRoom/Visuals/FittingRoomDressing/Candle{index}");
                Assert.IsNotNull(candle);
                Assert.IsNotNull(candle.transform.Find("Wax")?.GetComponent<MeshRenderer>());
                Assert.IsNotNull(candle.transform.Find("Flame")?.GetComponent<MeshRenderer>());
                Assert.IsEmpty(candle.GetComponentsInChildren<Collider>());
            }
        }

        [Test]
        public void CommittedScene_ValidatesForComposition()
        {
            Scene scene = EditorSceneManager.OpenScene(FinalRoomSceneBuilder.ScenePath, OpenSceneMode.Single);

            RoomSceneComposer.RoomValidationResult result = RoomSceneComposer.ValidateOpenRoomScene(
                RoomId.FinalRoom,
                scene,
                FindRoomEntry(RoomId.FinalRoom),
                RoomSceneCatalog.CreateCanonicalDoors());

            CollectionAssert.IsEmpty(result.Errors, string.Join("\n", result.Errors));
            Assert.That(result.DoorAnchors, Has.Count.EqualTo(2));
        }

        private static BoxCollider FindCollider(string path)
        {
            var found = GameObject.Find(path);
            Assert.IsNotNull(found, $"Expected {path}.");
            var collider = found.GetComponent<BoxCollider>();
            Assert.IsNotNull(collider, $"Expected {path} to carry gameplay collision.");
            return collider;
        }

        private static void AssertOpening(string wallName, float centerX)
        {
            float halfWidth = FinalRoomLayout.DoorOpeningWidth * 0.5f;
            BoxCollider west = FindCollider($"Room_FinalRoom/GameplayGeometry/{wallName}WestCollision");
            BoxCollider east = FindCollider($"Room_FinalRoom/GameplayGeometry/{wallName}EastCollision");
            Assert.That(west.bounds.max.x, Is.EqualTo(centerX - halfWidth).Within(0.001f));
            Assert.That(east.bounds.min.x, Is.EqualTo(centerX + halfWidth).Within(0.001f));

            Renderer westVisual = FindRenderer($"Room_FinalRoom/Visuals/{wallName}WestVisual");
            Renderer eastVisual = FindRenderer($"Room_FinalRoom/Visuals/{wallName}EastVisual");
            Assert.That(westVisual.bounds.max.x, Is.EqualTo(centerX - halfWidth).Within(0.001f));
            Assert.That(eastVisual.bounds.min.x, Is.EqualTo(centerX + halfWidth).Within(0.001f));
        }

        private static Renderer FindRenderer(string path)
        {
            var found = GameObject.Find(path);
            Assert.IsNotNull(found, $"Expected {path}.");
            var renderer = found.GetComponent<Renderer>();
            Assert.IsNotNull(renderer, $"Expected {path} to carry visible geometry.");
            return renderer;
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
