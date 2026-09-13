using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    public sealed class RuinedEntrySceneTests
    {
        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            RuinedEntrySceneBuilder.BuildInMemoryForTests();
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [Test]
        public void Layout_UsesApprovedBoundsDoorAndTouchingRubbleFootprints()
        {
            Assert.AreEqual(new Vector3(0f, 0f, -9f), RuinedEntryLayout.RoomBounds.center);
            Assert.AreEqual(new Vector3(20f, 0f, 18f), RuinedEntryLayout.RoomBounds.size);
            Assert.AreEqual(3f, RuinedEntryLayout.DoorOpeningWidth);

            Assert.AreEqual(new Vector3(4f, 0f, -10f), RuinedEntryLayout.RubbleABounds.center);
            Assert.AreEqual(new Vector3(4f, 0f, 4f), RuinedEntryLayout.RubbleABounds.size);
            Assert.AreEqual(new Vector3(5.5f, 0f, -7f), RuinedEntryLayout.RubbleBBounds.center);
            Assert.AreEqual(new Vector3(3f, 0f, 2f), RuinedEntryLayout.RubbleBBounds.size);
            Assert.AreEqual(RuinedEntryLayout.RubbleAMaximumZ, RuinedEntryLayout.RubbleBMinimumZ,
                "Rubble A and B must touch to preserve the approved L-shaped hard-geometry footprint.");
        }

        [Test]
        public void Build_SeparatesVisibleBlockoutFromGameplayCollision()
        {
            GameObject visible = GameObject.Find("RuinedEntry/VisibleBlockout");
            GameObject gameplay = GameObject.Find("RuinedEntry/GameplayGeometry");

            Assert.IsNotNull(visible);
            Assert.IsNotNull(gameplay);
            Assert.Greater(visible.GetComponentsInChildren<Renderer>().Length, 0);
            Assert.AreEqual(0, visible.GetComponentsInChildren<Collider>().Length,
                "Visible room blockout must not own gameplay collision.");
            Assert.Greater(gameplay.GetComponentsInChildren<BoxCollider>().Length, 0);
            Assert.AreEqual(0, gameplay.GetComponentsInChildren<Renderer>().Length,
                "Gameplay geometry must remain independently replaceable from room visuals.");
        }

        [Test]
        public void Build_PreservesDoorOpeningAndApprovedRoutes()
        {
            BoxCollider westDoorWall = FindCollider("RuinedEntry/GameplayGeometry/NorthWallWestCollision");
            BoxCollider eastDoorWall = FindCollider("RuinedEntry/GameplayGeometry/NorthWallEastCollision");

            float westOpeningEdge = westDoorWall.bounds.max.x;
            float eastOpeningEdge = eastDoorWall.bounds.min.x;
            Assert.AreEqual(-1.5f, westOpeningEdge, 0.001f);
            Assert.AreEqual(1.5f, eastOpeningEdge, 0.001f);
            Assert.AreEqual(RuinedEntryLayout.DoorOpeningWidth, eastOpeningEdge - westOpeningEdge, 0.001f);

            Assert.GreaterOrEqual(RuinedEntryLayout.WestRouteWidth, 6f);
            Assert.GreaterOrEqual(RuinedEntryLayout.EastRouteWidth, 2.5f);
            Assert.IsFalse(RuinedEntryLayout.DoorStagingBounds.Intersects(RuinedEntryLayout.RubbleABounds));
            Assert.IsFalse(RuinedEntryLayout.DoorStagingBounds.Intersects(RuinedEntryLayout.RubbleBBounds));
        }

        [Test]
        public void Build_LeavesD1ReachableFromBothSidesOfRubble()
        {
            Transform door = GameObject.Find("RuinedEntry/D1Opening")?.transform;
            Transform staging = GameObject.Find("RuinedEntry/D1StagingArea")?.transform;

            Assert.IsNotNull(door);
            Assert.IsNotNull(staging);
            Assert.AreEqual(new Vector3(0f, 0f, 0f), door.position);
            Assert.AreEqual(new Vector3(0f, 0f, -2.5f), staging.position);
            Assert.Less(RuinedEntryLayout.RubbleABounds.min.x, RuinedEntryLayout.RubbleBBounds.min.x);
            Assert.Greater(RuinedEntryLayout.RubbleABounds.min.x, door.position.x,
                "The west route must remain open from the staging area to D1.");
            Assert.Less(RuinedEntryLayout.RubbleBBounds.max.z, staging.position.z,
                "The rubble must remain south of the final D1 approach.");
        }

        private static BoxCollider FindCollider(string path)
        {
            GameObject found = GameObject.Find(path);
            Assert.IsNotNull(found, $"Expected {path}.");
            BoxCollider collider = found.GetComponent<BoxCollider>();
            Assert.IsNotNull(collider, $"Expected {path} to carry gameplay collision.");
            return collider;
        }
    }
}
