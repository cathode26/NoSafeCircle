using System.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    // NSC-069 VAL-001: this file and RoomSceneComposerTests.cs both contribute tests to the one
    // authoritative NoSafeCircle.DoorPrototype.Tests.Editor.World.RoomSceneCompositionFoundationTests
    // fixture named by the committed EditMode validation filter. This half covers the shared
    // catalog/contract data (AC-001, AC-002, AC-003); RoomSceneComposerTests.cs covers the
    // validation/composition behavior.
    public partial class RoomSceneCompositionFoundationTests
    {
        private const string FixtureHostScenePath =
            "Assets/__RoomSceneCompositionFoundationHost.unity";

        [SetUp]
        public void SetUp()
        {
            if (AssetDatabase.LoadAssetAtPath<SceneAsset>(FixtureHostScenePath) != null)
            {
                AssetDatabase.DeleteAsset(FixtureHostScenePath);
            }

            var hostScene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Assert.IsTrue(EditorSceneManager.SaveScene(hostScene, FixtureHostScenePath),
                "The additive-scene tests require a saved host scene.");
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            if (AssetDatabase.LoadAssetAtPath<SceneAsset>(FixtureHostScenePath) != null)
            {
                AssetDatabase.DeleteAsset(FixtureHostScenePath);
            }
        }

        // AC-001/VAL-001: the catalog's five rooms must appear in the fixed south-to-north
        // forward route order from the approved GDD blockout.
        [Test]
        public void CanonicalRooms_MatchFixedFiveRoomOrder()
        {
            var rooms = RoomSceneCatalog.CreateCanonicalRooms();

            Assert.IsTrue(RoomSceneComposer.ValidateFixedRoomOrder(rooms, out var error), error);
        }

        // AC-001/VAL-002: the catalog records one stable, distinct authoring-scene path per room
        // identity without creating or owning the room-specific scene assets themselves.
        [Test]
        public void CanonicalRooms_RecordDistinctStableScenePaths()
        {
            var rooms = RoomSceneCatalog.CreateCanonicalRooms();

            Assert.AreEqual(5, rooms.Length, "Expected exactly five stable room identities.");
            CollectionAssert.AllItemsAreUnique(rooms.Select(room => room.RoomId).ToArray());
            CollectionAssert.AllItemsAreUnique(rooms.Select(room => room.SceneAssetPath).ToArray());

            foreach (var room in rooms)
            {
                StringAssert.StartsWith("Assets/Scenes/Rooms/", room.SceneAssetPath,
                    $"'{room.RoomId}' must record an authoring-scene path under the shared Rooms folder.");
                StringAssert.EndsWith(".unity", room.SceneAssetPath);
            }
        }

        // AC-003: D1-D4 are the shared boundaries between two adjoining rooms, in the same fixed
        // room order as the catalog, each with the approved 3.0-unit opening width.
        [Test]
        public void CanonicalDoors_D1ToD4PairAdjoiningRoomsInFixedOrder()
        {
            var rooms = RoomSceneCatalog.CreateCanonicalRooms();
            var doors = RoomSceneCatalog.CreateCanonicalDoors();

            var nonFinalDoors = doors.Where(door => !door.IsFinal).OrderBy(door => door.DoorId).ToArray();
            Assert.AreEqual(4, nonFinalDoors.Length, "Expected exactly four non-final door boundaries (D1-D4).");

            for (var i = 0; i < nonFinalDoors.Length; i++)
            {
                Assert.AreEqual(rooms[i].RoomId, nonFinalDoors[i].ExitRoom,
                    $"'{nonFinalDoors[i].DoorId}' must be exited from the room at catalog order index {i}.");
                Assert.AreEqual(rooms[i + 1].RoomId, nonFinalDoors[i].EntryRoom,
                    $"'{nonFinalDoors[i].DoorId}' must be entered into the room at catalog order index {i + 1}.");
                Assert.AreEqual(3f, nonFinalDoors[i].OpeningWidth, 0.001f,
                    $"'{nonFinalDoors[i].DoorId}' must define the approved 3.0-unit opening width.");
            }
        }

        // AC-003: D5 is Final Room's sole Exit marker (the escape boundary), not a shared boundary
        // paired with another room.
        [Test]
        public void CanonicalDoors_D5IsSoleExitMarkerOnFinalRoom()
        {
            var doors = RoomSceneCatalog.CreateCanonicalDoors();
            var finalDoor = doors.Single(door => door.DoorId == DoorId.D5);

            Assert.IsTrue(finalDoor.IsFinal, "D5 must be marked as the final door.");
            Assert.AreEqual(RoomId.FinalRoom, finalDoor.ExitRoom);
            Assert.AreEqual(3f, finalDoor.OpeningWidth, 0.001f);
        }

        // AC-002: RoomContentMarker's RoomId/Category identity must round-trip through the
        // Inspector-facing SerializedObject boundary room authoring content is set through.
        [Test]
        public void RoomContentMarker_ExposesSerializedRoomIdAndCategory()
        {
            var gameObject = new GameObject("RoomContentMarkerFixture");
            var marker = gameObject.AddComponent<RoomContentMarker>();

            var serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.ChapelOfAsh;
            serialized.FindProperty("category").enumValueIndex = (int)RoomContentCategory.GameplayGeometry;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            Assert.AreEqual(RoomId.ChapelOfAsh, marker.RoomId);
            Assert.AreEqual(RoomContentCategory.GameplayGeometry, marker.Category);
        }

        // AC-002/AC-003: DoorAnchorMarker must expose its identity fields and default to the
        // approved 3.0-unit opening width when authoring leaves it unset.
        [Test]
        public void DoorAnchorMarker_ExposesSerializedFieldsAndDefaultOpeningWidth()
        {
            var gameObject = new GameObject("DoorAnchorMarkerFixture");
            var marker = gameObject.AddComponent<DoorAnchorMarker>();

            Assert.AreEqual(3f, marker.OpeningWidth, 0.001f,
                "DoorAnchorMarker must default to the approved 3.0-unit opening width.");

            var serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.LowerVault;
            serialized.FindProperty("doorId").enumValueIndex = (int)DoorId.D4;
            serialized.FindProperty("role").enumValueIndex = (int)DoorAnchorRole.Exit;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            Assert.AreEqual(RoomId.LowerVault, marker.RoomId);
            Assert.AreEqual(DoorId.D4, marker.DoorId);
            Assert.AreEqual(DoorAnchorRole.Exit, marker.Role);
        }
    }
}
