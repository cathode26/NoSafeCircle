using System.Collections;
using System.Reflection;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.TestTools;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-017 VAL-001..VAL-006: temporary collision and NavMesh only. The floor is baked
    // before the door exists, so these tests measure runtime obstacle carving and never
    // open or save the canonical DoorPrototype scene.
    public sealed class EnemyLockedDoorAttackPlayModeTests
    {
        private const float Step = 0.05f;
        private const float DoorZ = 0f;
        private static readonly Vector3 EnemyStart = new Vector3(0f, 0f, -6f);
        private static readonly Vector3 WizardForward = new Vector3(1f, 0f, 6f);

        private GameObject root;
        private GameplayNavigationSurface navigation;
        private DoorInteractable door;
        private DoorEnemyPassability passability;
        private GameObject wizard;
        private GameObject enemy;
        private NavMeshAgent agent;
        private EnemyTargetKnowledge knowledge;
        private EnemyPursuitMovement pursuit;
        private EnemyLockedDoorAttack attack;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("NSC017TemporaryNavigationRoot");
            CreateCollider("Floor", new Vector3(0f, -0.05f, 0f), new Vector3(20f, 0.1f, 20f));
            CreateCollider("DoorwayWallWest", new Vector3(-5.75f, 1f, DoorZ),
                new Vector3(8.5f, 2f, 0.5f));
            CreateCollider("DoorwayWallEast", new Vector3(5.75f, 1f, DoorZ),
                new Vector3(8.5f, 2f, 0.5f));

            var navigationObject = new GameObject("GameplayNavigation");
            navigationObject.transform.SetParent(root.transform, false);
            navigation = navigationObject.AddComponent<GameplayNavigationSurface>();
            navigation.ConfigureAndBuild();

            Assert.IsTrue(NavMesh.SamplePosition(EnemyStart, out var enemyHit, 1f, NavMesh.AllAreas));
            Assert.IsTrue(NavMesh.SamplePosition(WizardForward, out var wizardHit, 1f, NavMesh.AllAreas));

            wizard = new GameObject("Wizard");
            wizard.transform.SetParent(root.transform, false);
            wizard.transform.position = wizardHit.position;
            wizard.AddComponent<PlayerHealth>();
            var playerController = wizard.AddComponent<PlayerInteractionController>();
            var playerCollider = wizard.AddComponent<BoxCollider>();

            enemy = new GameObject("PursuingEnemy");
            enemy.transform.SetParent(root.transform, false);
            enemy.transform.position = enemyHit.position;
            agent = enemy.AddComponent<NavMeshAgent>();
            var settings = NavMesh.GetSettingsByIndex(0);
            agent.agentTypeID = settings.agentTypeID;
            agent.radius = settings.agentRadius;
            agent.height = settings.agentHeight;
            agent.speed = 5f;
            agent.Warp(enemyHit.position);
            knowledge = enemy.AddComponent<EnemyTargetKnowledge>();
            knowledge.Initialize(wizard.transform);
            knowledge.ConfigureDistances(15f, 20f);
            pursuit = enemy.AddComponent<EnemyPursuitMovement>();
            attack = enemy.AddComponent<EnemyLockedDoorAttack>();
            pursuit.enabled = false;
            attack.enabled = false;

            var doorObject = new GameObject("LockedDoor");
            doorObject.transform.SetParent(root.transform, false);
            doorObject.transform.position = new Vector3(0f, 0f, DoorZ);
            passability = doorObject.AddComponent<DoorEnemyPassability>();
            door = doorObject.AddComponent<DoorInteractable>();
            door.BindEnemyPassability(passability);
            playerController.NotifyDoorInRange(door);
            playerController.BeginInteraction();
            door.Tick(door.Duration + 0.01f);
            Assert.IsTrue(door.IsOpen, "Fixture must open through PlayerInteractionController.");
            var callback = typeof(DoorInteractable).GetMethod("HandleForwardCrossingTriggerEnter",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.IsNotNull(callback);
            callback.Invoke(door, new object[] { playerCollider });
            Assert.IsTrue(door.IsLocked, "Reflection is fixture lock setup, not NSC-017 proof.");
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            if (navigation != null) navigation.ClearBakedData();
            if (root != null) Object.Destroy(root);
            // Destroy is deferred in Play Mode; let the old obstacle/agent leave the
            // NavMesh before the next fixture bakes its temporary surface.
            yield return null;
        }

        [UnityTest]
        public IEnumerator LockedDoor_RoutesToApproach_HitsBreaksAndResumesPursuit()
        {
            yield return SettleCarving();
            var path = new NavMeshPath();
            Assert.IsTrue(agent.CalculatePath(wizard.transform.position, path));
            Assert.AreEqual(NavMeshPathStatus.PathPartial, path.status,
                "The locked door must interrupt the route to the sideways-offset wizard.");
            pursuit.Tick(0f);
            Assert.AreSame(door, pursuit.BlockingLockedDoor);
            Assert.IsTrue(agent.CalculatePath(pursuit.BlockingDoorApproachPoint, path) &&
                path.status == NavMeshPathStatus.PathComplete,
                "The door approach must have a complete route from this enemy.");

            var initialDurability = door.CurrentDurability;
            for (var index = 0; index < 8; index++)
            {
                Drive(Step);
                yield return new WaitForFixedUpdate();
            }
            Assert.AreEqual(initialDurability, door.CurrentDurability, 0.001f,
                "An enemy still outside attack reach must not damage the door.");

            yield return UntilFirstHit(400);
            Assert.Less(door.CurrentDurability, initialDurability);
            yield return UntilBroken(400);
            Assert.IsTrue(door.IsBroken);
            Assert.AreEqual(DoorPassabilityState.Broken, passability.CurrentState);
            Assert.IsNull(attack.PendingDoor);
            yield return SettleCarving();
            pursuit.Tick(0f);
            Assert.IsNull(pursuit.BlockingLockedDoor);
            Assert.AreEqual(EnemyTargetKnowledgeState.Pursuing, knowledge.State);

            var crossed = false;
            for (var index = 0; index < 400; index++)
            {
                Drive(Step);
                if (enemy.transform.position.z > DoorZ + 0.5f)
                {
                    crossed = true;
                    break;
                }
                yield return new WaitForFixedUpdate();
            }
            Assert.IsTrue(crossed, "The same enemy must move through the broken doorway. " + Diagnostics());
            Assert.AreEqual(EnemyTargetKnowledgeState.Pursuing, knowledge.State);
        }

        [UnityTest]
        public IEnumerator SameRoomTargetAndOpenOrBrokenDoor_DoNotProduceAnAttackTarget()
        {
            yield return SettleCarving();
            wizard.transform.position = new Vector3(1f, 0f, -4f);
            pursuit.Tick(0f);
            attack.Tick(2f);
            Assert.IsNull(pursuit.BlockingLockedDoor,
                "A nearby locked door is not between an enemy and a same-room wizard.");
            Assert.AreEqual(door.MaxDurability, door.CurrentDurability, 0.001f);

            wizard.transform.position = WizardForward;
            door.TakeDamage(door.MaxDurability);
            yield return SettleCarving();
            pursuit.Tick(0f);
            attack.Tick(2f);
            Assert.IsTrue(door.IsBroken);
            Assert.IsNull(pursuit.BlockingLockedDoor);
            Assert.IsNull(attack.PendingDoor);
        }

        [UnityTest]
        public IEnumerator UnreachableDoorApproach_DoesNotSelectNearbyLockedDoor()
        {
            // The door remains a possible bridge to the wizard, but a second full-width
            // carve isolates its approach side from this enemy's walkable region.
            var blocker = new GameObject("UnreachableApproachBlocker");
            blocker.transform.SetParent(root.transform, false);
            blocker.transform.position = new Vector3(0f, 1f, -3f);
            var obstacle = blocker.AddComponent<NavMeshObstacle>();
            obstacle.shape = NavMeshObstacleShape.Box;
            obstacle.size = new Vector3(22f, 2f, 0.8f);
            obstacle.carving = true;
            yield return SettleCarving();

            pursuit.Tick(0f);
            attack.Tick(2f);
            var path = new NavMeshPath();
            Assert.IsFalse(agent.CalculatePath(door.InteractionPosition, path) &&
                path.status == NavMeshPathStatus.PathComplete,
                "The second carve must make the door approach unreachable in this fixture.");
            Assert.IsNull(pursuit.BlockingLockedDoor);
            Assert.AreEqual(door.MaxDurability, door.CurrentDurability, 0.001f);
        }

        [UnityTest]
        public IEnumerator ForcedDisplacement_CancelsHitAndPursuitReturnsForFullNewInterval()
        {
            yield return SettleCarving();
            yield return WalkToAttackReach(400);
            var initial = door.CurrentDurability;
            attack.Tick(0.4f);
            Assert.AreSame(door, attack.PendingDoor);
            Assert.AreEqual(initial, door.CurrentDurability, 0.001f);

            var status = enemy.AddComponent<EnemyStatusEffectMovement>();
            status.RequestDisplacement(Vector3.back, 3f);
            Assert.Greater(HorizontalDistance(enemy.transform.position, pursuit.BlockingDoorApproachPoint), 1f,
                "EnemyStatusEffectMovement must actually displace the enemy out of attack reach.");
            pursuit.Tick(0f);
            attack.Tick(2f);
            Assert.IsNull(attack.PendingDoor);
            Assert.AreEqual(initial, door.CurrentDurability, 0.001f);

            yield return WalkToAttackReach(400);
            attack.Tick(0.79f);
            Assert.AreEqual(initial, door.CurrentDurability, 0.001f);
            attack.Tick(0.01f);
            Assert.AreEqual(initial - 10f, door.CurrentDurability, 0.001f);
        }

        [UnityTest]
        public IEnumerator TwoInReachEnemies_ContributeIndependentHitsAndBothCrossAfterBreak()
        {
            yield return SettleCarving();
            Assert.IsTrue(agent.Warp(new Vector3(-0.3f, 0f, -1.8f)));
            var other = CreateOtherEnemy(new Vector3(0.3f, 0f, -1.8f));
            pursuit.Tick(0f);
            other.Pursuit.Tick(0f);
            Assert.AreSame(door, pursuit.BlockingLockedDoor);
            Assert.AreSame(door, other.Pursuit.BlockingLockedDoor);
            Assert.Less(HorizontalDistance(enemy.transform.position, pursuit.BlockingDoorApproachPoint), 1f);
            Assert.Less(HorizontalDistance(other.Root.transform.position,
                other.Pursuit.BlockingDoorApproachPoint), 1f);

            var initial = door.CurrentDurability;
            attack.Tick(0.8f);
            other.Attack.Tick(0.8f);
            Assert.AreEqual(initial - 20f, door.CurrentDurability, 0.001f,
                "Each pursuing enemy must contribute exactly one accepted damage request.");
            for (var index = 0; index < 4; index++)
            {
                attack.Tick(0.8f);
                other.Attack.Tick(0.8f);
            }
            Assert.IsTrue(door.IsBroken);
            Assert.IsNull(attack.PendingDoor);
            Assert.IsNull(other.Attack.PendingDoor);
            yield return SettleCarving();

            var bothCrossed = false;
            for (var index = 0; index < 400; index++)
            {
                pursuit.Tick(0f);
                other.Pursuit.Tick(0f);
                bothCrossed = enemy.transform.position.z > 0.5f &&
                    other.Root.transform.position.z > 0.5f;
                if (bothCrossed) break;
                yield return new WaitForFixedUpdate();
            }
            Assert.IsTrue(bothCrossed, "Both enemies should continue through the broken door. " + Diagnostics());
            Assert.AreEqual(EnemyTargetKnowledgeState.Pursuing, knowledge.State);
            Assert.AreEqual(EnemyTargetKnowledgeState.Pursuing, other.Knowledge.State);
        }

        [UnityTest]
        public IEnumerator DistantSecondEnemy_DoesNotContributeUntilItsOwnFullInReachInterval()
        {
            yield return SettleCarving();
            Assert.IsTrue(agent.Warp(new Vector3(0f, 0f, -1.8f)));
            var distant = CreateOtherEnemy(EnemyStart + Vector3.left);
            pursuit.Tick(0f);
            distant.Pursuit.Tick(0f);
            Assert.AreSame(door, distant.Pursuit.BlockingLockedDoor);
            Assert.Greater(HorizontalDistance(distant.Root.transform.position,
                distant.Pursuit.BlockingDoorApproachPoint), 1f);

            var initial = door.CurrentDurability;
            attack.Tick(0.8f);
            distant.Attack.Tick(0.8f);
            Assert.AreEqual(initial - 10f, door.CurrentDurability, 0.001f,
                "The in-reach enemy alone must supply the first hit.");

            for (var index = 0; index < 400; index++)
            {
                distant.Pursuit.Tick(0f);
                distant.Attack.Tick(0f);
                if (HorizontalDistance(distant.Root.transform.position,
                    distant.Pursuit.BlockingDoorApproachPoint) <= 1f) break;
                yield return new WaitForFixedUpdate();
            }
            Assert.LessOrEqual(HorizontalDistance(distant.Root.transform.position,
                distant.Pursuit.BlockingDoorApproachPoint), 1f);
            Assert.AreEqual(initial - 10f, door.CurrentDurability, 0.001f);
            distant.Attack.Tick(0.79f);
            Assert.AreEqual(initial - 10f, door.CurrentDurability, 0.001f);
            distant.Attack.Tick(0.01f);
            Assert.AreEqual(initial - 20f, door.CurrentDurability, 0.001f);
        }

        [UnityTest]
        public IEnumerator LosingTargetAndResettingEnemy_CancelPendingDoorHit()
        {
            yield return SettleCarving();
            agent.Warp(new Vector3(0f, 0f, -1.8f));
            pursuit.Tick(0f);
            attack.Tick(0.4f);
            Assert.AreSame(door, attack.PendingDoor);
            var before = door.CurrentDurability;

            wizard.transform.position = new Vector3(1f, 0f, 19f);
            pursuit.Tick(0f);
            attack.Tick(2f);
            Assert.AreEqual(EnemyTargetKnowledgeState.SearchingLastKnownPosition, knowledge.State);
            Assert.IsNull(attack.PendingDoor);
            Assert.IsNull(pursuit.BlockingLockedDoor);
            Assert.AreEqual(before, door.CurrentDurability, 0.001f);

            attack.ResetAttack();
            pursuit.ResetPursuit();
            Assert.IsNull(attack.PendingDoor);
            Assert.IsNull(pursuit.BlockingLockedDoor);
            Assert.AreEqual(EnemyTargetKnowledgeState.Idle, knowledge.State);
            Assert.Less(Vector3.Distance(enemy.transform.position, EnemyStart), 0.5f);
            attack.Tick(2f);
            Assert.AreEqual(before, door.CurrentDurability, 0.001f);

            wizard.transform.position = WizardForward;
            yield return WalkToAttackReach(400);
            attack.Tick(0.79f);
            Assert.AreEqual(before, door.CurrentDurability, 0.001f,
                "Reacquisition after restart must not inherit the old partial interval.");
            attack.Tick(0.01f);
            Assert.AreEqual(before - 10f, door.CurrentDurability, 0.001f);
        }

        [UnityTest]
        public IEnumerator SearchArrivalAndExpiry_NearLockedDoorNeverCauseDamage()
        {
            door.TakeDamage(door.MaxDurability);
            yield return SettleCarving();
            knowledge.ConfigureDistances(2f, 4f);
            wizard.transform.position = new Vector3(0f, 0f, -4.2f);
            pursuit.Tick(0f);
            Assert.AreEqual(EnemyTargetKnowledgeState.Pursuing, knowledge.State);
            wizard.transform.position = new Vector3(0f, 0f, 2f);
            pursuit.Tick(0f);
            Assert.AreEqual(EnemyTargetKnowledgeState.SearchingLastKnownPosition, knowledge.State);
            wizard.transform.position = new Vector3(0f, 0f, 19f);

            var reachedWander = false;
            for (var index = 0; index < 400; index++)
            {
                Drive(0f);
                reachedWander = knowledge.State == EnemyTargetKnowledgeState.Wandering;
                if (reachedWander) break;
                yield return new WaitForFixedUpdate();
            }
            Assert.IsTrue(reachedWander, "Search must reach the unobstructed last-known point.");
            attack.Tick(knowledge.SearchDuration + 0.1f);
            pursuit.Tick(knowledge.SearchDuration + 0.1f);
            Assert.AreEqual(EnemyTargetKnowledgeState.Idle, knowledge.State);
            Assert.IsNull(pursuit.BlockingLockedDoor);
            Assert.AreEqual(0f, door.CurrentDurability, 0.001f);
        }

        [UnityTest]
        public IEnumerator DoorAttack_DrivesBoundBreachFeedback_OnlyWhileInReach()
        {
            yield return SettleCarving();
            var feedbackObject = new GameObject("BreachFeedback");
            feedbackObject.transform.SetParent(door.transform, false);
            var feedback = feedbackObject.AddComponent<DoorBreachFeedback>();
            var audio = feedbackObject.AddComponent<AudioSource>();
            audio.playOnAwake = false;
            var indicator = new GameObject("Indicator", typeof(RectTransform));
            indicator.transform.SetParent(feedbackObject.transform, false);
            var fillObject = new GameObject("Fill", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            fillObject.transform.SetParent(indicator.transform, false);
            var fill = fillObject.GetComponent<Image>();
            var cracks = new[] { new GameObject("Crack1"), new GameObject("Crack2") };
            foreach (var crack in cracks)
            {
                crack.transform.SetParent(feedbackObject.transform, false);
                crack.SetActive(false);
            }
            feedback.Bind(door, feedbackObject.transform, fill, cracks, audio, indicator);

            pursuit.Tick(0f);
            attack.Tick(2f);
            Assert.AreEqual(1f, feedback.DurabilityRatio, 0.001f);
            Assert.IsFalse(cracks[0].activeSelf);
            Assert.IsFalse(feedback.IsShaking);

            agent.Warp(new Vector3(0f, 0f, -1.8f));
            pursuit.Tick(0f);
            attack.Tick(0.8f);
            Assert.Less(feedback.DurabilityRatio, 1f);
            Assert.IsTrue(feedback.IsShaking);
            Assert.IsTrue(cracks[0].activeSelf);
        }

        private void Drive(float deltaTime)
        {
            pursuit.Tick(deltaTime);
            attack.Tick(deltaTime);
        }

        private IEnumerator WalkToAttackReach(int maxFrames)
        {
            for (var index = 0; index < maxFrames; index++)
            {
                pursuit.Tick(0f);
                if (pursuit.BlockingLockedDoor == door &&
                    HorizontalDistance(enemy.transform.position, pursuit.BlockingDoorApproachPoint) <= 1f)
                    break;
                yield return new WaitForFixedUpdate();
            }
            Assert.AreSame(door, pursuit.BlockingLockedDoor);
            Assert.LessOrEqual(HorizontalDistance(enemy.transform.position,
                pursuit.BlockingDoorApproachPoint), 1f, "Enemy did not reach the locked door. " + Diagnostics());
        }

        private static float HorizontalDistance(Vector3 first, Vector3 second)
        {
            var offset = first - second;
            offset.y = 0f;
            return offset.magnitude;
        }

        private struct OtherEnemy
        {
            public GameObject Root;
            public EnemyTargetKnowledge Knowledge;
            public EnemyPursuitMovement Pursuit;
            public EnemyLockedDoorAttack Attack;
        }

        private OtherEnemy CreateOtherEnemy(Vector3 position)
        {
            Assert.IsTrue(NavMesh.SamplePosition(position, out var hit, 1f, NavMesh.AllAreas));
            var other = new OtherEnemy();
            other.Root = new GameObject("SecondPursuingEnemy");
            other.Root.transform.SetParent(root.transform, false);
            other.Root.transform.position = hit.position;
            var otherAgent = other.Root.AddComponent<NavMeshAgent>();
            var settings = NavMesh.GetSettingsByIndex(0);
            otherAgent.agentTypeID = settings.agentTypeID;
            otherAgent.radius = settings.agentRadius;
            otherAgent.height = settings.agentHeight;
            otherAgent.speed = 5f;
            Assert.IsTrue(otherAgent.Warp(hit.position));
            other.Knowledge = other.Root.AddComponent<EnemyTargetKnowledge>();
            other.Knowledge.Initialize(wizard.transform);
            other.Knowledge.ConfigureDistances(15f, 20f);
            other.Pursuit = other.Root.AddComponent<EnemyPursuitMovement>();
            other.Attack = other.Root.AddComponent<EnemyLockedDoorAttack>();
            other.Pursuit.enabled = false;
            other.Attack.enabled = false;
            return other;
        }

        private IEnumerator SettleCarving()
        {
            for (var index = 0; index < 10; index++)
                yield return new WaitForFixedUpdate();
        }

        private IEnumerator UntilFirstHit(int maxFrames)
        {
            var initial = door.CurrentDurability;
            for (var index = 0; index < maxFrames && door.CurrentDurability >= initial; index++)
            {
                Drive(Step);
                yield return new WaitForFixedUpdate();
            }
            Assert.Less(door.CurrentDurability, initial, "Enemy never reached and attacked the door. " + Diagnostics());
        }

        private IEnumerator UntilBroken(int maxFrames)
        {
            for (var index = 0; index < maxFrames && !door.IsBroken; index++)
            {
                Drive(Step);
                yield return new WaitForFixedUpdate();
            }
            Assert.IsTrue(door.IsBroken, "Enemy never completed the breach. " + Diagnostics());
        }

        private string Diagnostics()
        {
            return "enemy=" + enemy.transform.position + ", destination=" + agent.destination +
                ", velocity=" + agent.velocity + ", remaining=" + agent.remainingDistance +
                ", pending=" + agent.pathPending + ", stopped=" + agent.isStopped +
                ", onMesh=" + agent.isOnNavMesh + ", path=" + agent.pathStatus +
                ", knowledge=" + knowledge.State +
                ", blockingDoor=" + (pursuit.BlockingLockedDoor == null ? "null" : pursuit.BlockingLockedDoor.name);
        }

        private void CreateCollider(string name, Vector3 position, Vector3 size)
        {
            var gameObject = new GameObject(name);
            gameObject.transform.SetParent(root.transform, false);
            gameObject.transform.position = position;
            gameObject.AddComponent<BoxCollider>().size = size;
        }
    }
}
