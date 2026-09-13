using System;
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
            GameObject visible = GameObject.Find("Room_RuinedEntry/Visuals");
            GameObject gameplay = GameObject.Find("Room_RuinedEntry/GameplayGeometry");

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
            BoxCollider westDoorWall = FindCollider("Room_RuinedEntry/GameplayGeometry/NorthWallWestCollision");
            BoxCollider eastDoorWall = FindCollider("Room_RuinedEntry/GameplayGeometry/NorthWallEastCollision");

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
            Transform door = GameObject.Find("Room_RuinedEntry/DoorAnchors/D1Opening")?.transform;
            Transform staging = GameObject.Find("Room_RuinedEntry/Authoring/D1StagingArea")?.transform;

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

        [Test]
        public void Build_CreatesComposerReadyHierarchyAndD1ExitAnchor()
        {
            Scene scene = SceneManager.GetActiveScene();

            AssertComposerReadyScene(scene);
        }

        [Test]
        public void CommittedScene_ValidatesThroughRoomSceneComposer()
        {
            Scene scene = EditorSceneManager.OpenScene(RuinedEntrySceneBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                AssertComposerReadyScene(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        private static void AssertComposerReadyScene(Scene scene)
        {
            RoomSceneCatalog.RoomCatalogEntry roomEntry = Array.Find(
                RoomSceneCatalog.CreateCanonicalRooms(), entry => entry.RoomId == RoomId.RuinedEntry);
            RoomSceneComposer.RoomValidationResult validation = RoomSceneComposer.ValidateOpenRoomScene(
                RoomId.RuinedEntry, scene, roomEntry, RoomSceneCatalog.CreateCanonicalDoors());

            CollectionAssert.IsEmpty(validation.Errors, string.Join("\n", validation.Errors));
            Assert.IsTrue(validation.IsValid);

            GameObject[] roots = scene.GetRootGameObjects();
            Assert.AreEqual(1, roots.Length);
            GameObject roomRoot = roots[0];
            Assert.AreEqual("Room_RuinedEntry", roomRoot.name);
            Assert.AreEqual(Vector3.zero, roomRoot.transform.localPosition);
            Assert.AreEqual(Quaternion.identity, roomRoot.transform.localRotation);
            Assert.AreEqual(Vector3.one, roomRoot.transform.localScale);
            Assert.AreEqual(4, roomRoot.transform.childCount);

            AssertContentMarker(roomRoot.transform, "Visuals", RoomId.RuinedEntry, RoomContentCategory.Visuals);
            AssertContentMarker(
                roomRoot.transform, "GameplayGeometry", RoomId.RuinedEntry, RoomContentCategory.GameplayGeometry);
            Transform anchors = AssertContentMarker(
                roomRoot.transform, "DoorAnchors", RoomId.RuinedEntry, RoomContentCategory.DoorAnchors);
            AssertContentMarker(roomRoot.transform, "Authoring", RoomId.RuinedEntry, RoomContentCategory.Authoring);

            DoorAnchorMarker anchor = anchors.GetComponentInChildren<DoorAnchorMarker>(true);
            Assert.IsNotNull(anchor);
            Assert.AreEqual(DoorId.D1, anchor.DoorId);
            Assert.AreEqual(DoorAnchorRole.Exit, anchor.Role);
            Assert.AreEqual(3f, anchor.OpeningWidth);
            Assert.AreEqual(new Vector3(0f, 0f, 0f), anchor.transform.position);
            Assert.AreEqual(Vector3.forward, anchor.transform.forward);
        }

        private static Transform AssertContentMarker(
            Transform roomRoot,
            string name,
            RoomId roomId,
            RoomContentCategory category)
        {
            Transform child = roomRoot.Find(name);
            Assert.IsNotNull(child, $"Expected direct child {name}.");
            RoomContentMarker marker = child.GetComponent<RoomContentMarker>();
            Assert.IsNotNull(marker, $"Expected {name} to carry RoomContentMarker.");
            Assert.AreEqual(roomId, marker.RoomId);
            Assert.AreEqual(category, marker.Category);
            return child;
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
