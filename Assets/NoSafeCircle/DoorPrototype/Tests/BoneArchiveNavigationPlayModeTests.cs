using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.TestTools;
using NoSafeCircle.DoorPrototype.World.Rooms;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class BoneArchiveNavigationPlayModeTests
    {
        [UnityTest] // VAL-001: use the configured enemy agent when the navigation implementation is authored.
        public IEnumerator ConfiguredEnemyAgentTraversesEveryIntendedLane()
        {
            yield return null;

            NavMeshAgent agent = Object.FindObjectOfType<NavMeshAgent>();
            if (agent == null)
            {
                Assert.Ignore("VAL-001 unresolved: Bone Archive has no configured enemy NavMeshAgent in this checkout; navigation traversal cannot be claimed.");
            }

            NavMeshPath path = new NavMeshPath();
            Vector3[][] laneSegments =
            {
                new[] { new Vector3(-8f, 0.1f, 1f), new Vector3(-8f, 0.1f, 19f) },
                new[] { new Vector3(-3.25f, 0.1f, 1f), new Vector3(-3.25f, 0.1f, 19f) },
                new[] { new Vector3(2.25f, 0.1f, 1f), new Vector3(2.25f, 0.1f, 8f), new Vector3(2.25f, 0.1f, 12f), new Vector3(2.25f, 0.1f, 19f) },
                new[] { new Vector3(8f, 0.1f, 1f), new Vector3(8f, 0.1f, 19f) },
                new[] { new Vector3(1.75f, 0.1f, 17f), BoneArchiveLayout.D2 + Vector3.up * 0.1f }
            };

            foreach (Vector3[] lane in laneSegments)
            {
                if (!agent.Warp(lane[0]))
                {
                    Assert.Fail("Configured enemy navigation agent could not be placed on the Bone Archive navigation surface at {0}; VAL-001 remains unresolved.", lane[0]);
                }

                for (int index = 1; index < lane.Length; index++)
                {
                    bool canTraverse = agent.CalculatePath(lane[index], path);
                    Assert.That(canTraverse && path.status == NavMeshPathStatus.PathComplete,
                        Is.True, "Configured enemy navigation agent cannot traverse lane segment from {0} to {1}.", lane[index - 1], lane[index]);
                    agent.Warp(lane[index]);
                }
            }
        }
    }
}
