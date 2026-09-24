using System.Collections;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-049 AC-002/VAL-002: runtime checks for the ordered, interaction-owned D1-D5 instances.
    public sealed class FiveRoomDoorSequencePlayModeTests
    {
        [UnityTest]
        public IEnumerator CanonicalScene_HasOrderedDoors_AndD5IsTheOnlyFinalDoor()
        {
            yield return SceneManager.LoadSceneAsync("DoorPrototype", LoadSceneMode.Single);
            var scene = SceneManager.GetSceneByName("DoorPrototype");
            var doors = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<DoorInteractable>(true))
                .OrderBy(door => door.DoorId)
                .ToArray();

            Assert.AreEqual(5, doors.Length);
            for (var index = 0; index < doors.Length; index++)
            {
                Assert.AreEqual((DoorId)index, doors[index].DoorId);
                Assert.IsFalse(doors[index].IsOpen, $"{doors[index].DoorId} must start sealed.");
                Assert.IsFalse(doors[index].HasCrossedForward,
                    $"{doors[index].DoorId} must not count opening as crossing.");
                Assert.AreEqual(index == 4, doors[index].IsFinalDoor);
            }

            // THESE ARE THE CATALOG'S POSITIONS, AND THE CATALOG IS AUTHORITATIVE.
            // D3, D4 and D5 moved in fb36f012f ("NSC-101: one catalog to write, five rooms to
            // read it"), which lists the moves as deliberate contract work. This fixture last
            // changed 2026-09-13, BEFORE that commit, so it kept asserting the pre-NSC-101
            // layout. D1 and D2 were not moved and are unchanged here - they are the control
            // that shows this is three stale expectations rather than a broken composition.
            //
            // Verified against RoomSceneCatalog.asset rather than taken on inference:
            // doorId 2 {x: -8, y: 54}, doorId 3 {x: 4, y: 76}, doorId 4 {x: 0, y: 104}.
            // doorId 2's value was also measured directly from a failing run before this fix.
            //
            // THE ASSERTS ARE SEQUENTIAL, so a stale expectation here hides every later one:
            // only D3 had ever been seen to fail, because the run stopped there.
            Assert.AreEqual(new Vector3(0f, 0f, 0f), doors[0].transform.position);
            Assert.AreEqual(new Vector3(6f, 0f, 20f), doors[1].transform.position);
            Assert.AreEqual(new Vector3(-8f, 0f, 54f), doors[2].transform.position);
            Assert.AreEqual(new Vector3(4f, 0f, 76f), doors[3].transform.position);
            Assert.AreEqual(new Vector3(0f, 0f, 104f), doors[4].transform.position);
        }

        [UnityTearDown]
        public IEnumerator UnloadCanonicalSceneWithoutSaving()
        {
            var scene = SceneManager.GetSceneByName("DoorPrototype");
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            var cleanupScene = SceneManager.CreateScene("FiveRoomDoorSequenceTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }
    }
}
