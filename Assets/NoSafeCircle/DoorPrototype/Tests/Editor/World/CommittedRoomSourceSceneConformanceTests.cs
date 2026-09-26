using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;
using UnityEngine;
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

        // THE GAP THAT LET NSC-126 LAND MERGED AND INVISIBLE, and the mirror of the blockout
        // guard in BoneArchiveSceneTests. NSC-126's own RoomWallAccentIntegrationTests build each
        // room into a fresh IN-MEMORY scene, deliberately, so that no canonical asset is touched -
        // which means nothing in the suite ever read a COMMITTED scene for accents.
        //
        // Measured before writing this, with a control: "WallAccent" appears ZERO times in all
        // five *SceneTests.cs, against a "blockout" control of 27/6/3/33/2 in the same files, and
        // RoomWallAccentIntegrationTests contains no OpenScene or ScenePath reference at all. So
        // the accents could disappear from every committed scene with the whole suite still green,
        // which is precisely how they came to be merged and invisible.
        //
        // The 4 is GEOMETRY, re-derived from the scenes rather than assumed: the placer builds a
        // rectangular room and a rectangle has four corners, and all five committed scenes carry
        // exactly 4 CornerAccent today. Jamb counts are NOT frozen - they are two per door opening,
        // so 4 in four rooms and 2 in Ruined Entry, which has one opening. Asserting a grand total
        // here would be the frozen-sum mistake that blocked NSC-126 in LowerVaultSceneTests.
        // Accent objects are named role + "Accent" (ArchitecturalWallAccentPlacement.cs:465).
        [Test]
        public void FiveCommittedRoomScenes_EachCarryTheirWallAccents()
        {
            foreach (var room in RoomSceneCatalog.CreateCanonicalRooms())
            {
                Scene scene = EditorSceneManager.OpenScene(room.SceneAssetPath, OpenSceneMode.Single);

                try
                {
                    Transform accents = scene.GetRootGameObjects()
                        .SelectMany(root => root.GetComponentsInChildren<Transform>(true))
                        .FirstOrDefault(candidate => candidate.name == "WallAccents");

                    Assert.IsNotNull(accents,
                        $"'{room.SceneAssetPath}' carries no WallAccents root. The builder places them, "
                        + "but the composer CLONES this committed scene, so a builder fix alone is "
                        + "invisible - re-bake the room scene and recompose.");

                    var corners = 0;
                    var jambs = 0;

                    foreach (Transform accent in accents)
                    {
                        Assert.IsTrue(accent.name.EndsWith("Accent"),
                            $"'{accent.name}' under WallAccents in {room.RoomId} is not a named accent.");

                        if (accent.name == "CornerAccent") corners++;
                        if (accent.name == "JambAccent") jambs++;

                        SpriteRenderer renderer = accent.GetComponent<SpriteRenderer>();
                        Assert.IsNotNull(renderer, $"{accent.name} in {room.RoomId} has no SpriteRenderer.");
                        Assert.IsNotNull(renderer.sprite,
                            $"{accent.name} in {room.RoomId} resolved no sprite, so it draws nothing.");
                    }

                    Assert.AreEqual(4, corners,
                        $"{room.RoomId} must carry one CornerAccent per corner of its rectangular room.");
                    Assert.GreaterOrEqual(jambs, 2,
                        $"{room.RoomId} must carry two JambAccents per door opening, so at least one "
                        + "opening's worth. This is a family floor, never a frozen total.");
                }
                finally
                {
                    EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                }
            }
        }
    }
}
