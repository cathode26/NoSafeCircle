using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    // NSC-049 AC-001/VAL-001: committed-scene conformance checks for the single continuous world.
    public sealed class FiveRoomCompositionTests
    {
        private const string ScenePath = "Assets/Scenes/DoorPrototype.unity";

        [Test]
        public void CanonicalScene_ContainsAllRoomsAtApprovedBounds_AndKeepsSimulationSeparate()
        {
            var roomCatalog = RoomSceneCatalog.CreateCanonicalRooms();
            var sourceBytes = roomCatalog.ToDictionary(
                room => room.SceneAssetPath, room => File.ReadAllBytes(room.SceneAssetPath));
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            try
            {
                var world = scene.GetRootGameObjects().SingleOrDefault(root => root.name == RoomSceneComposer.WorldRootName);
                Assert.IsNotNull(world, "Canonical scene must contain the composed World root.");
                var roomsRoot = world.transform.Find(RoomSceneComposer.ComposedRoomsRootName);
                Assert.IsNotNull(roomsRoot, "Canonical scene must contain World/ComposedRooms.");

                foreach (var room in roomCatalog)
                {
                    var roomRoot = roomsRoot.Find("Room_" + room.RoomId);
                    Assert.IsNotNull(roomRoot, $"Missing composed room {room.RoomId}.");
                    Assert.IsNotNull(roomRoot.Find("Visuals"), $"{room.RoomId} is missing Visuals.");
                    Assert.IsNotNull(roomRoot.Find("GameplayGeometry"), $"{room.RoomId} is missing GameplayGeometry.");
                    Assert.IsNotNull(roomRoot.Find("DoorAnchors"), $"{room.RoomId} is missing DoorAnchors.");
                    Assert.IsTrue(roomRoot.Find("Visuals") != roomRoot.Find("GameplayGeometry"));
                }

                Assert.AreEqual(5, roomsRoot.childCount, "The canonical composition must contain exactly five rooms.");
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
                foreach (var pair in sourceBytes)
                {
                    CollectionAssert.AreEqual(pair.Value, File.ReadAllBytes(pair.Key),
                        $"Composition must not modify source scene {pair.Key}.");
                }
            }
        }
    }
}
