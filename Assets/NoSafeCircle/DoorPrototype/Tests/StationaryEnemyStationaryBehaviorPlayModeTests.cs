using System.Collections;
using System.Linq;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class StationaryEnemyStationaryBehaviorPlayModeTests
    {
        [UnityTest]
        public IEnumerator CanonicalScene_ReviewEnemiesRemainStationaryAndPresentationOnly()
        {
            yield return SceneManager.LoadSceneAsync("DoorPrototype", LoadSceneMode.Single);
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            GameObject review = scene.GetRootGameObjects()
                .Single(root => root.name == "StationaryEnemyReview");
            StationaryEnemyPresentation[] enemies = review
                .GetComponentsInChildren<StationaryEnemyPresentation>(true);
            Assert.AreEqual(10, enemies.Length);
            Assert.AreEqual(5, enemies.Count(enemy => enemy.Archetype == StationaryEnemyArchetype.Melee));
            Assert.AreEqual(5, enemies.Count(enemy => enemy.Archetype == StationaryEnemyArchetype.Ranged));

            Vector3[] positions = enemies.Select(enemy => enemy.transform.position).ToArray();
            Quaternion[] rotations = enemies.Select(enemy => enemy.transform.rotation).ToArray();
            Sprite[] sprites = enemies.Select(enemy => enemy.GetComponent<SpriteRenderer>().sprite).ToArray();

            yield return new WaitForSeconds(0.75f);

            Assert.AreEqual(10, review.GetComponentsInChildren<StationaryEnemyPresentation>(true).Length);
            for (int index = 0; index < enemies.Length; index++)
            {
                Assert.AreEqual(positions[index], enemies[index].transform.position);
                Assert.AreEqual(rotations[index], enemies[index].transform.rotation);
                Assert.AreSame(sprites[index], enemies[index].GetComponent<SpriteRenderer>().sprite);
                Assert.AreEqual(0, enemies[index].GetComponentsInChildren<Collider>(true).Length);
                Assert.AreEqual(0, enemies[index].GetComponentsInChildren<Rigidbody>(true).Length);
                Assert.AreEqual(3, enemies[index].GetComponents<Component>().Length,
                    "Presentation-only examples have no attack, projectile, health, or movement component.");
            }
        }

        [UnityTearDown]
        public IEnumerator UnloadCanonicalSceneWithoutSaving()
        {
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            Scene cleanup = SceneManager.CreateScene("StationaryEnemyReviewTestCleanup");
            SceneManager.SetActiveScene(cleanup);
            yield return SceneManager.UnloadSceneAsync(scene);
        }
    }
}
