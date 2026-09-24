using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Editor.World;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    /// <summary>The dressing is actually IN the committed composed scene -- the one Play opens.</summary>
    /// <remarks>
    /// WHY THIS FIXTURE EXISTS. Five dressing prefabs were built and instantiated into
    /// Assets/Scenes/DoorPrototype.unity, and the only evidence that the art was there was A
    /// RENDERED IMAGE SOMEBODY LOOKED AT. Every suite in the project would have stayed green with
    /// that scene emptied of every prop, because nothing asserted the join's output. That is the
    /// exact shape this project keeps meeting: a green result that is not evidence of the thing.
    /// <para>
    /// THE EXPECTATIONS COME FROM THE AUTHORED CATALOGS, NOT FROM THE PREFABS AND NOT FROM THE
    /// SCENE. Each room's placement count and instance ids are read from its committed
    /// &lt;Room&gt;DressingCatalog.json -- the Art Director's authored art, which is upstream of
    /// both the prefab and the scene. A fixture that counted the scene's children against the
    /// prefab's children would agree with itself however far both had drifted from what was
    /// authored.
    /// </para>
    /// <para>
    /// THE ROOT NAME IS RESTATED HERE AS A LITERAL ON PURPOSE. DoorSequenceBuilder.DressingRootName
    /// is internal to the Editor assembly, but even if it were reachable this fixture would not use
    /// it: asserting against the constant the builder writes with means a rename changes both sides
    /// at once and the assertion can never fail. A rename should cost a deliberate edit in two
    /// places.
    /// </para>
    /// <para>
    /// THE IDENTITY ASSERTIONS ARE NOT COSMETIC. Catalog placements are WORLD coordinates, so the
    /// dressing root and every room instance under it must sit at identity. A transform anywhere on
    /// that chain silently double-offsets every prop in the room -- the props still exist, the
    /// counts still match, and the furniture renders in the wrong place or outside the walls.
    /// Counting cannot see that, so position, rotation and scale are all asserted.
    /// </para>
    /// </remarks>
    public sealed class ComposedSceneDressingTests
    {
        private const string ScenePath = "Assets/Scenes/DoorPrototype.unity";
        private const string DressingRootName = "RoomDressing";
        private const string DressingDirectory =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/RoomDressing/";

        [Test]
        public void CommittedScene_ContainsEveryRoomsAuthoredDressing()
        {
            var rooms = RoomSceneCatalog.CreateCanonicalRooms();
            var authored = rooms.ToDictionary(
                room => room.RoomId.ToString(),
                room => ReadAuthoredPlacements(room.RoomId.ToString()));

            byte[] sceneBefore = File.ReadAllBytes(ScenePath);
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            try
            {
                var dressingRoot = scene.GetRootGameObjects()
                    .SingleOrDefault(root => root.name == DressingRootName);
                Assert.IsNotNull(dressingRoot,
                    "The committed composed scene has no '" + DressingRootName + "' root. The art " +
                    "is not in the scene the player opens, whatever the prefabs on disk contain.");

                // The root carries world-coordinate placements, so it must not transform them.
                AssertAtIdentity(dressingRoot.transform, DressingRootName);

                Assert.AreEqual(rooms.Length, dressingRoot.transform.childCount,
                    "The dressing root must hold exactly one dressed room per composed room.");

                foreach (var room in rooms)
                {
                    string roomId = room.RoomId.ToString();
                    string instanceName = roomId + "Dressing";

                    var dressed = dressingRoot.transform.Find(instanceName);
                    Assert.IsNotNull(dressed,
                        roomId + " has no dressing in the committed scene (expected a child named '" +
                        instanceName + "').");

                    AssertAtIdentity(dressed, instanceName);

                    string[] expectedIds = authored[roomId];
                    Assert.AreEqual(expectedIds.Length, dressed.childCount,
                        instanceName + " holds " + dressed.childCount + " props but its authored " +
                        "catalog declares " + expectedIds.Length + ". The scene has drifted from " +
                        "the art.");

                    var builtIds = new List<string>();
                    foreach (Transform placement in dressed)
                    {
                        builtIds.Add(placement.name);

                        var renderer = placement.GetComponent<SpriteRenderer>();
                        Assert.IsNotNull(renderer,
                            instanceName + "/" + placement.name + " has no SpriteRenderer, so it " +
                            "draws nothing.");
                        Assert.IsNotNull(renderer.sprite,
                            instanceName + "/" + placement.name + " has a SpriteRenderer with no " +
                            "sprite. The prop is present in the hierarchy and INVISIBLE in the room.");
                    }

                    CollectionAssert.AreEquivalent(expectedIds, builtIds,
                        instanceName + " does not place the props its catalog authored. A matching " +
                        "count with different ids is the right number of the wrong things.");
                }
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, false);
                CollectionAssert.AreEqual(sceneBefore, File.ReadAllBytes(ScenePath),
                    "Reading the composed scene must not modify it.");
            }
        }

        [Test]
        public void CommittedScene_DressingIsLinkedToTheCommittedPrefabs()
        {
            // Linkage is the difference between art that can be re-authored and art that has been
            // copied into the scene by hand. As prefab INSTANCES, rebuilding a dressing prefab
            // updates the composed scene; as loose copies, the catalog and the scene drift apart
            // silently and only a screenshot would ever show it.
            var rooms = RoomSceneCatalog.CreateCanonicalRooms();

            byte[] sceneBefore = File.ReadAllBytes(ScenePath);
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            try
            {
                var dressingRoot = scene.GetRootGameObjects()
                    .SingleOrDefault(root => root.name == DressingRootName);
                Assert.IsNotNull(dressingRoot, "The composed scene has no dressing root.");

                foreach (var room in rooms)
                {
                    string roomId = room.RoomId.ToString();
                    var dressed = dressingRoot.transform.Find(roomId + "Dressing");
                    Assert.IsNotNull(dressed, roomId + " has no dressing in the committed scene.");

                    Assert.IsTrue(PrefabUtility.IsPartOfPrefabInstance(dressed.gameObject),
                        roomId + "'s dressing is not a prefab instance. It was copied into the " +
                        "scene rather than instantiated, so rebuilding the prefab will not update it.");

                    string expectedPrefab = DressingDirectory + roomId + "Dressing.prefab";
                    string actualPrefab =
                        PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(dressed.gameObject);
                    Assert.AreEqual(expectedPrefab, actualPrefab,
                        roomId + "'s dressing comes from a different prefab than the one its " +
                        "builder writes.");
                }
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, false);
                CollectionAssert.AreEqual(sceneBefore, File.ReadAllBytes(ScenePath),
                    "Reading the composed scene must not modify it.");
            }
        }

        private static void AssertAtIdentity(Transform transform, string label)
        {
            Assert.AreEqual(Vector3.zero, transform.localPosition,
                label + " must sit at the origin: catalog placements are WORLD coordinates, so any " +
                "offset here moves every prop in the room.");
            Assert.AreEqual(Quaternion.identity, transform.localRotation,
                label + " must be unrotated, for the same reason.");
            Assert.AreEqual(Vector3.one, transform.localScale,
                label + " must be unscaled, for the same reason.");
        }

        /// <summary>The authored instance ids for a room, read from the committed catalog.</summary>
        /// <remarks>
        /// From disk, not through the AssetDatabase: the dressing catalogs carry no .meta on main,
        /// so Unity has never imported them and LoadAssetAtPath returns null for a file that plainly
        /// exists. JsonUtility also returns null on a leading byte-order mark, which reads exactly
        /// like a missing file, so the BOM is stripped here rather than misdiagnosed later.
        /// </remarks>
        private static string[] ReadAuthoredPlacements(string roomId)
        {
            string path = DressingDirectory + roomId + "DressingCatalog.json";
            Assert.IsTrue(File.Exists(path),
                path + " is missing. The authored catalog is what this fixture measures the scene " +
                "against; without it there is no independent expectation.");

            string json = File.ReadAllText(path);
            if (json.Length > 0 && json[0] == '﻿') json = json.Substring(1);

            var catalog = JsonUtility.FromJson<DressingCatalogFile>(json);
            Assert.IsNotNull(catalog?.props, path + " parsed to no placements.");
            Assert.Greater(catalog.props.Length, 0, path + " declares no placements.");

            return catalog.props.Select(placement => placement.instance_id).ToArray();
        }

        [Serializable]
        private sealed class DressingCatalogFile
        {
            public DressingPlacement[] props;
        }

        [Serializable]
        private sealed class DressingPlacement
        {
            public string instance_id;
        }
    }
}
