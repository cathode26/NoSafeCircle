using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    // NSC-049 downstream integration regression: inspect the exact committed room source
    // scenes without saving them. Builder-only tests cannot prove that those serialized
    // artifacts remain admissible to RoomSceneComposer or that shared anchors pair.
    public class CommittedRoomSourceSceneConformanceTests
    {
        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [Test]
        public void FiveCommittedRoomScenes_AreComposableWithPairedDoorAnchors()
        {
            var rooms = RoomSceneCatalog.CreateCanonicalRooms();
            var doors = RoomSceneCatalog.CreateCanonicalDoors();
            var bytesBefore = rooms.ToDictionary(room => room.SceneAssetPath, room => File.ReadAllBytes(room.SceneAssetPath));
            var openedScenes = new List<Scene>();
            var results = new Dictionary<RoomId, RoomSceneComposer.RoomValidationResult>();

            try
            {
                foreach (var room in rooms)
                {
                    var scene = EditorSceneManager.OpenScene(room.SceneAssetPath, OpenSceneMode.Additive);
                    openedScenes.Add(scene);

                    var result = RoomSceneComposer.ValidateOpenRoomScene(room.RoomId, scene, room, doors);
                    Assert.IsTrue(result.IsValid,
                        $"Committed source scene '{room.SceneAssetPath}' is not composable:\n" +
                        string.Join("\n", result.Errors));
                    results.Add(room.RoomId, result);
                }

                foreach (var door in doors.Where(candidate => !candidate.IsFinal))
                {
                    var exitAnchor = results[door.ExitRoom].DoorAnchors.Single(
                        anchor => anchor.DoorId == door.DoorId && anchor.Role == DoorAnchorRole.Exit);
                    var entryAnchor = results[door.EntryRoom].DoorAnchors.Single(
                        anchor => anchor.DoorId == door.DoorId && anchor.Role == DoorAnchorRole.Entry);

                    Assert.IsTrue(RoomSceneComposer.ValidateAnchorPairing(exitAnchor, entryAnchor, out var error), error);
                }
            }
            finally
            {
                for (var index = openedScenes.Count - 1; index >= 0; index--)
                {
                    var scene = openedScenes[index];
                    if (scene.IsValid() && scene.isLoaded)
                    {
                        EditorSceneManager.CloseScene(scene, true);
                    }
                }

                foreach (var room in rooms)
                {
                    CollectionAssert.AreEqual(bytesBefore[room.SceneAssetPath], File.ReadAllBytes(room.SceneAssetPath),
                        $"Committed-scene conformance inspection changed '{room.SceneAssetPath}'.");
                }
            }
        }
    }
}
