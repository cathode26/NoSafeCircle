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
    public sealed class LowerVaultSceneTests
    {
        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LowerVaultSceneBuilder.BuildInMemoryForTests();
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [Test] // AC-001: approved shell, door openings, obstacle footprints, and heights.
        public void Layout_UsesApprovedLowerVaultBlockout()
        {
            Assert.AreEqual(new Vector3(0f, 0f, 53f), LowerVaultLayout.RoomBounds.center);
            Assert.AreEqual(new Vector3(22f, 0f, 22f), LowerVaultLayout.RoomBounds.size);
            Assert.AreEqual(new Vector3(-6f, 0f, 42f), LowerVaultLayout.D3);
            Assert.AreEqual(new Vector3(4f, 0f, 64f), LowerVaultLayout.D4);
            Assert.AreEqual(new Vector3(2f, 2.5f, 4f), LowerVaultLayout.CentralColumnCluster.size);
            Assert.AreEqual(new Vector3(3.5f, 1.5f, 4f), LowerVaultLayout.WestStoragePile.size);
            Assert.AreEqual(new Vector3(3.5f, 1.5f, 3f), LowerVaultLayout.EastStoragePile.size);
            Assert.AreEqual(new Vector3(6.5f, 1.5f, 2f), LowerVaultLayout.NorthWestStorageBar.size);
        }

        [Test] // AC-002 / VAL-001: the blockout retains route choices and a southern D3 connection.
        public void Layout_PreservesClearancesAndOpenD3Connection()
        {
            Assert.GreaterOrEqual(LowerVaultLayout.ClearWidthBetween(LowerVaultLayout.WestStoragePile, LowerVaultLayout.CentralColumnCluster), 3f);
            Assert.GreaterOrEqual(LowerVaultLayout.ClearWidthBetween(LowerVaultLayout.CentralColumnCluster, LowerVaultLayout.EastStoragePile), 3f);
            Assert.GreaterOrEqual(LowerVaultLayout.WestStoragePile.min.x - LowerVaultLayout.RoomBounds.min.x, 3f);
            Assert.GreaterOrEqual(LowerVaultLayout.RoomBounds.max.x - LowerVaultLayout.EastStoragePile.max.x, 3f);
            Assert.IsFalse(LowerVaultLayout.WestStoragePile.Intersects(LowerVaultLayout.NorthWestStorageBar));
            Assert.Less(LowerVaultLayout.D3.z, LowerVaultLayout.CentralColumnCluster.min.z);
        }

        [Test] // AC-001 / VAL-001: both door walls leave exactly the approved opening width.
        public void Build_LeavesD3AndD4Openings()
        {
            AssertOpening("SouthWallWestCollision", "SouthWallEastCollision", -6f);
            AssertOpening("NorthWallWestCollision", "NorthWallEastCollision", 4f);
        }

        [Test] // AC-002: visible dressing is separate from walkable gameplay collision.
        public void Build_SeparatesVaultVisualsFromGameplayGeometry()
        {
            GameObject visible = GameObject.Find("Room_LowerVault/Visuals");
            GameObject gameplay = GameObject.Find("Room_LowerVault/GameplayGeometry");
            Assert.IsNotNull(visible);
            Assert.IsNotNull(gameplay);
            Assert.Greater(visible.GetComponentsInChildren<Renderer>().Length, 10);
            Assert.AreEqual(0, visible.GetComponentsInChildren<Collider>().Length);
            Assert.Greater(gameplay.GetComponentsInChildren<BoxCollider>().Length, 8);
            Assert.AreEqual(0, gameplay.GetComponentsInChildren<Renderer>().Length);
        }

        [Test]
        public void Build_CreatesComposerReadyHierarchyAndDoorAnchors()
        {
            Scene scene = SceneManager.GetActiveScene();

            AssertComposerReadyScene(scene);
        }

        [Test]
        public void CommittedScene_ValidatesThroughRoomSceneComposer()
        {
            Scene scene = EditorSceneManager.OpenScene(LowerVaultSceneBuilder.ScenePath, OpenSceneMode.Additive);
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
                RoomSceneCatalog.CreateCanonicalRooms(), entry => entry.RoomId == RoomId.LowerVault);
            RoomSceneComposer.RoomValidationResult validation = RoomSceneComposer.ValidateOpenRoomScene(
                RoomId.LowerVault, scene, roomEntry, RoomSceneCatalog.CreateCanonicalDoors());

            CollectionAssert.IsEmpty(validation.Errors, string.Join("\n", validation.Errors));
            Assert.IsTrue(validation.IsValid);

            GameObject[] roots = scene.GetRootGameObjects();
            Assert.AreEqual(1, roots.Length);
            GameObject roomRoot = roots[0];
            Assert.AreEqual("Room_LowerVault", roomRoot.name);
            Assert.AreEqual(Vector3.zero, roomRoot.transform.localPosition);
            Assert.AreEqual(Quaternion.identity, roomRoot.transform.localRotation);
            Assert.AreEqual(Vector3.one, roomRoot.transform.localScale);
            Assert.AreEqual(4, roomRoot.transform.childCount);

            AssertContentMarker(roomRoot.transform, "Visuals", RoomId.LowerVault, RoomContentCategory.Visuals);
            AssertContentMarker(
                roomRoot.transform, "GameplayGeometry", RoomId.LowerVault, RoomContentCategory.GameplayGeometry);
            Transform anchors = AssertContentMarker(
                roomRoot.transform, "DoorAnchors", RoomId.LowerVault, RoomContentCategory.DoorAnchors);
            AssertContentMarker(roomRoot.transform, "Authoring", RoomId.LowerVault, RoomContentCategory.Authoring);

            DoorAnchorMarker[] doorAnchors = anchors.GetComponentsInChildren<DoorAnchorMarker>(true);
            Assert.AreEqual(2, doorAnchors.Length);
            AssertDoorAnchor(doorAnchors, DoorId.D3, DoorAnchorRole.Entry, LowerVaultLayout.D3, Vector3.back);
            AssertDoorAnchor(doorAnchors, DoorId.D4, DoorAnchorRole.Exit, LowerVaultLayout.D4, Vector3.forward);
        }

        private static Transform AssertContentMarker(
            Transform roomRoot,
            string name,
            RoomId roomId,
            RoomContentCategory category)
        {
            Transform child = roomRoot.Find(name);
            Assert.IsNotNull(child, "Expected direct child " + name + ".");
            RoomContentMarker marker = child.GetComponent<RoomContentMarker>();
            Assert.IsNotNull(marker, "Expected " + name + " to carry RoomContentMarker.");
            Assert.AreEqual(roomId, marker.RoomId);
            Assert.AreEqual(category, marker.Category);
            return child;
        }

        private static void AssertDoorAnchor(
            DoorAnchorMarker[] anchors,
            DoorId doorId,
            DoorAnchorRole role,
            Vector3 position,
            Vector3 forward)
        {
            DoorAnchorMarker anchor = Array.Find(anchors, candidate => candidate.DoorId == doorId);
            Assert.IsNotNull(anchor, "Expected " + doorId + " anchor.");
            Assert.AreEqual(RoomId.LowerVault, anchor.RoomId);
            Assert.AreEqual(role, anchor.Role);
            Assert.AreEqual(3f, anchor.OpeningWidth);
            Assert.AreEqual(position, anchor.transform.position);
            Assert.Greater(Vector3.Dot(forward, anchor.transform.forward), 0.999f);
        }

        private static void AssertOpening(string westName, string eastName, float centerX)
        {
            BoxCollider west = FindCollider("Room_LowerVault/GameplayGeometry/" + westName);
            BoxCollider east = FindCollider("Room_LowerVault/GameplayGeometry/" + eastName);
            Assert.AreEqual(LowerVaultLayout.DoorWidth, east.bounds.min.x - west.bounds.max.x, 0.001f);
            Assert.AreEqual(centerX, (east.bounds.min.x + west.bounds.max.x) * 0.5f, 0.001f);
        }

        private static BoxCollider FindCollider(string path)
        {
            GameObject found = GameObject.Find(path);
            Assert.IsNotNull(found, "Expected " + path + ".");
            BoxCollider collider = found.GetComponent<BoxCollider>();
            Assert.IsNotNull(collider, "Expected " + path + " to carry gameplay collision.");
            return collider;
        }
    }
}
