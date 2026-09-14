using System.Collections;
using System.Reflection;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Exercises the real DoorInteractable transitions. The test never calls SetDoorState after
    // binding: each navigation result must come from the door's own open, crossing, break, or
    // reset path. All scene objects and NavMesh data belong to this fixture.
    public sealed class DoorPassabilityConnectionPlayModeTests
    {
        private GameObject root;
        private GameplayNavigationSurface surface;
        private DoorInteractable door;
        private DoorEnemyPassability passability;
        private NavMeshObstacle obstacle;
        private PlayerInteractionController player;
        private Collider playerCollider;
        private NavMeshAgent agent;
        private Vector3 forwardTarget;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("DoorPassabilityConnectionTest");
            CreateCollider("Floor", new Vector3(0f, -0.05f, 0f), new Vector3(20f, 0.1f, 20f));
            CreateCollider("WestWall", new Vector3(-5.75f, 1f, 0f), new Vector3(8.5f, 2f, 0.5f));
            CreateCollider("EastWall", new Vector3(5.75f, 1f, 0f), new Vector3(8.5f, 2f, 0.5f));

            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(root.transform, false);
            surface = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surface.ConfigureAndBuild();

            Assert.IsTrue(NavMesh.SamplePosition(new Vector3(0f, 0f, -8f), out var start, 2f, NavMesh.AllAreas));
            Assert.IsTrue(NavMesh.SamplePosition(new Vector3(0f, 0f, 8f), out var forward, 2f, NavMesh.AllAreas));
            forwardTarget = forward.position;

            var doorRoot = new GameObject("DoorRoot");
            doorRoot.transform.SetParent(root.transform, false);
            door = doorRoot.AddComponent<DoorInteractable>();
            var visual = CreateCollider("DoorVisual", new Vector3(0f, 1f, 0f), new Vector3(2f, 2f, 0.3f), doorRoot.transform);
            SetPrivateField(door, "doorVisual", visual.gameObject);
            SetPrivateField(door, "doorwayBlocker", visual);
            passability = doorRoot.AddComponent<DoorEnemyPassability>();
            obstacle = doorRoot.GetComponent<NavMeshObstacle>();
            door.BindEnemyPassability(passability);

            var playerRoot = new GameObject("Player");
            playerRoot.transform.SetParent(root.transform, false);
            player = playerRoot.AddComponent<PlayerInteractionController>();
            playerCollider = playerRoot.AddComponent<BoxCollider>();
            player.NotifyDoorInRange(door);

            var agentRoot = new GameObject("EnemyNavMeshAgent");
            agentRoot.transform.SetParent(root.transform, false);
            agentRoot.transform.position = start.position;
            var settings = NavMesh.GetSettingsByIndex(0);
            agent = agentRoot.AddComponent<NavMeshAgent>();
            agent.agentTypeID = settings.agentTypeID;
            agent.radius = settings.agentRadius;
            agent.height = settings.agentHeight;
            agent.Warp(start.position);
        }

        [TearDown]
        public void TearDown()
        {
            if (surface != null) surface.ClearBakedData();
            if (root != null) Object.Destroy(root);
        }

        [UnityTest]
        public IEnumerator DoorTransitions_PublishEnemyWalkabilityThroughPassabilityOwner()
        {
            yield return SettleCarving();
            AssertDoorState(DoorPassabilityState.Sealed, true, false);

            player.BeginInteraction();
            door.Tick(door.Duration + 0.1f);
            yield return SettleCarving();
            AssertDoorState(DoorPassabilityState.Open, false, true);

            var crossing = typeof(DoorInteractable).GetMethod("HandleForwardCrossingTriggerEnter",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.IsNotNull(crossing);
            crossing.Invoke(door, new object[] { playerCollider });
            yield return SettleCarving();
            AssertDoorState(DoorPassabilityState.Locked, true, false);

            door.TakeDamage(door.MaxDurability);
            yield return SettleCarving();
            AssertDoorState(DoorPassabilityState.Broken, false, true);

            door.ResetDoor();
            yield return SettleCarving();
            AssertDoorState(DoorPassabilityState.Sealed, true, false);
        }

        private void AssertDoorState(DoorPassabilityState expectedState, bool expectedCarving, bool expectedPath)
        {
            Assert.AreEqual(expectedState, passability.CurrentState);
            Assert.AreEqual(expectedCarving, obstacle.carving);
            var path = new NavMeshPath();
            var found = agent.CalculatePath(forwardTarget, path);
            Assert.AreEqual(expectedPath, found && path.status == NavMeshPathStatus.PathComplete,
                $"Door state {expectedState} published the wrong enemy path result.");
        }

        private static IEnumerator SettleCarving()
        {
            for (var i = 0; i < 10; i++) yield return new WaitForFixedUpdate();
        }

        private BoxCollider CreateCollider(string name, Vector3 position, Vector3 size, Transform parent = null)
        {
            var child = new GameObject(name);
            child.transform.SetParent(parent == null ? root.transform : parent, false);
            child.transform.position = position;
            var collider = child.AddComponent<BoxCollider>();
            collider.size = size;
            return collider;
        }

        private static void SetPrivateField(object target, string name, object value)
        {
            typeof(DoorInteractable).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)
                .SetValue(target, value);
        }
    }
}
