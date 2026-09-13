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

            Assert.AreEqual(new Vector3(0f, 0f, 0f), doors[0].transform.position);
            Assert.AreEqual(new Vector3(6f, 0f, 20f), doors[1].transform.position);
            Assert.AreEqual(new Vector3(-6f, 0f, 42f), doors[2].transform.position);
            Assert.AreEqual(new Vector3(4f, 0f, 64f), doors[3].transform.position);
            Assert.AreEqual(new Vector3(0f, 0f, 86f), doors[4].transform.position);
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
