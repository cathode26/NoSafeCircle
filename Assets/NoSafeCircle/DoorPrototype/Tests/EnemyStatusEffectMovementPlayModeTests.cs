using System;
using System.Collections;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-013: proves EnemyStatusEffectMovement's Frost Field slowdown apply/restore
    // (AC-001/AC-002, VAL-001), ability-requested forced displacement warp/identity-preservation
    // and pursuit hand-back (AC-003/AC-004, VAL-002), and the owner-controlled reset entry point
    // (AC-005, VAL-004) against a temporary NavMesh baked by GameplayNavigationSurface (NSC-089)
    // and the production EnemyTargetKnowledge (NSC-091) / EnemyPursuitMovement (NSC-092)
    // components, read-only. Every object here is created and destroyed by this fixture; nothing
    // here opens, saves, or otherwise touches the committed Assets/Scenes/DoorPrototype.unity
    // scene.
    //
    // VAL-003 (a Ranged Enemy continuing its telegraphed attack on schedule while frosted) is not
    // exercised here: a repository-wide search of Assets/ found no ranged-enemy attack/telegraph
    // component to attach this effect to, so no attack-timing double is fabricated. That check is
    // deferred as an integration obligation to NSC-054 (Ranged Enemy Projectile Attack, Cover
    // Collision, and Reset), whose own AC-005/VAL-003 require its attack wind-up/cooldown/
    // projectile speed and lifetime to stay unchanged under this component's Frost slowdown. The
    // available evidence here until NSC-054 exists is structural: ApplyFrostSlowdown only ever
    // writes NavMeshAgent.speed and never references any other component.
    public sealed class EnemyStatusEffectMovementPlayModeTests
    {
        private const float DetectionDistance = 3f;
        private const float LoseTargetDistance = 6f;
        private const float FloorSize = 24f;

        private static readonly Vector3 EnemySpawnPoint = new Vector3(-4f, 0f, 0f);
        private static readonly Vector3 WizardNearPoint = new Vector3(-2f, 0f, 0f);

        private GameObject root;
        private GameplayNavigationSurface surfaceOwner;
        private GameObject wizardObject;
        private Transform wizardTransform;
        private GameObject enemyObject;
        private NavMeshAgent agent;
        private EnemyTargetKnowledge targetKnowledge;
        private EnemyPursuitMovement pursuitMovement;
        private EnemyStatusEffectMovement statusEffectMovement;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("EnemyStatusEffectMovementTestRoot");
            BuildOpenFloor();

            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(root.transform, false);
            surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surfaceOwner.ConfigureAndBuild();

            wizardObject = new GameObject("TestWizard");
            wizardObject.transform.SetParent(root.transform, false);
            wizardTransform = wizardObject.transform;

            Assert.IsTrue(NavMesh.SamplePosition(EnemySpawnPoint, out var spawnHit, 2f, NavMesh.AllAreas),
                "Expected the enemy spawn point to sample onto the baked open test floor.");

            enemyObject = new GameObject("TestEnemy");
            enemyObject.transform.SetParent(root.transform, false);
            enemyObject.transform.position = spawnHit.position;

            var settings = NavMesh.GetSettingsByIndex(0);
            agent = enemyObject.AddComponent<NavMeshAgent>();
            agent.agentTypeID = settings.agentTypeID;
            agent.radius = settings.agentRadius;
            agent.height = settings.agentHeight;
            agent.Warp(spawnHit.position);

            targetKnowledge = enemyObject.AddComponent<EnemyTargetKnowledge>();
            targetKnowledge.Initialize(wizardTransform);
            targetKnowledge.ConfigureDistances(DetectionDistance, LoseTargetDistance);

            pursuitMovement = enemyObject.AddComponent<EnemyPursuitMovement>();
            statusEffectMovement = enemyObject.AddComponent<EnemyStatusEffectMovement>();
        }

        [TearDown]
        public void TearDown()
        {
            if (surfaceOwner != null) surfaceOwner.ClearBakedData();
            if (root != null) Object.Destroy(root);
        }

        // AC-001/AC-002, VAL-001: applying Frost slows the NavMeshAgent to the requested fraction
        // of its baseline, and the slowdown fully restores once the effect's duration elapses.
        [UnityTest]
        public IEnumerator ApplyFrostSlowdown_ReducesAgentSpeed_AndRestoresBaselineWhenDurationElapses()
        {
            var baselineSpeed = statusEffectMovement.BaselineSpeed;

            statusEffectMovement.ApplyFrostSlowdown(0.4f, 2f);

            Assert.That(agent.speed, Is.EqualTo(baselineSpeed * 0.4f).Within(0.001f));
            Assert.IsTrue(statusEffectMovement.IsFrostSlowdownActive);

            statusEffectMovement.Tick(2.1f);

            Assert.That(agent.speed, Is.EqualTo(baselineSpeed).Within(0.001f),
                "Expected NavMeshAgent speed to be fully restored once Frost slowdown ends, " +
                "with no permanent slowdown remaining.");
            Assert.IsFalse(statusEffectMovement.IsFrostSlowdownActive);

            yield return null;
        }

        // AC-001, VAL-001: a multiplier above 1 would speed the enemy up rather than slow it, so
        // it is clamped to the baseline instead of being honored literally.
        [Test]
        public void ApplyFrostSlowdown_MultiplierAboveOne_ClampsToBaselineSpeedWithoutIncrease()
        {
            var baselineSpeed = statusEffectMovement.BaselineSpeed;

            statusEffectMovement.ApplyFrostSlowdown(2f, 1f);

            Assert.That(agent.speed, Is.EqualTo(baselineSpeed).Within(0.001f));
        }

        // AC-001, VAL-001: a negative multiplier is clamped to a full stop rather than being
        // honored literally.
        [Test]
        public void ApplyFrostSlowdown_NegativeMultiplier_ClampsToFullStop()
        {
            statusEffectMovement.ApplyFrostSlowdown(-1f, 1f);

            Assert.That(agent.speed, Is.EqualTo(0f).Within(0.001f));
        }

        // AC-001/AC-002, VAL-001: reapplying Frost before the previous application expires
        // overwrites the multiplier and refreshes the duration rather than stacking timers.
        [Test]
        public void ApplyFrostSlowdown_ReappliedBeforeExpiry_OverwritesMultiplierAndRefreshesDuration()
        {
            var baselineSpeed = statusEffectMovement.BaselineSpeed;

            statusEffectMovement.ApplyFrostSlowdown(0.5f, 1f);
            statusEffectMovement.Tick(0.9f);

            statusEffectMovement.ApplyFrostSlowdown(0.2f, 1f);

            Assert.That(statusEffectMovement.FrostTimeRemaining, Is.EqualTo(1f).Within(0.001f));
            Assert.That(agent.speed, Is.EqualTo(baselineSpeed * 0.2f).Within(0.001f));
        }

        // Defensive: a non-positive duration is ignored rather than silently ending an
        // in-progress effect or leaving the agent at zero speed.
        [Test]
        public void ApplyFrostSlowdown_NonPositiveDuration_DoesNotApplyEffect()
        {
            var baselineSpeed = statusEffectMovement.BaselineSpeed;

            statusEffectMovement.ApplyFrostSlowdown(0.3f, 0f);

            Assert.IsFalse(statusEffectMovement.IsFrostSlowdownActive);
            Assert.That(agent.speed, Is.EqualTo(baselineSpeed).Within(0.001f));
        }

        // AC-003, VAL-002: a requested displacement warps the enemy to a valid NavMesh position
        // along the requested direction while preserving its identity as the same persistent
        // GameObject/component.
        [Test]
        public void RequestDisplacement_ValidDirection_WarpsToValidNavMeshPositionAndPreservesIdentity()
        {
            var originalInstanceId = enemyObject.GetInstanceID();
            var positionBeforeDisplacement = enemyObject.transform.position;

            statusEffectMovement.RequestDisplacement(Vector3.right, 3f);

            Assert.That(enemyObject.GetInstanceID(), Is.EqualTo(originalInstanceId));
            Assert.That(enemyObject.activeInHierarchy, Is.True);
            Assert.IsTrue(agent.isOnNavMesh, "Expected the displaced enemy to remain on a valid NavMesh position.");

            Assert.IsTrue(
                NavMesh.SamplePosition(enemyObject.transform.position, out var hit, 0.1f, NavMesh.AllAreas));
            Assert.That(Vector3.Distance(hit.position, enemyObject.transform.position), Is.LessThan(0.15f),
                "Expected the displaced position to be valid on the configured NavMesh.");

            Assert.That(Vector3.Distance(enemyObject.transform.position, positionBeforeDisplacement),
                Is.GreaterThan(0.5f), "Expected the requested displacement to actually move the enemy.");
        }

        // AC-003, VAL-002: a knockback whose only nearby NavMesh sample lies on a separate,
        // walkably-disconnected region across a wall (for example a bakeable NavMesh island the
        // enemy could never actually walk to) must not be warped into. This builds its own
        // isolated two-room fixture, spatially far from the shared open-floor fixture above, so
        // the two bakes never touch: a small Room A holds the enemy, a solid wall plus a real
        // floor gap makes Room B unreachable on foot, and Room B's own floor still exists (so a
        // naive distance-only NavMesh.SamplePosition would find it) purely to prove the rejection
        // is based on path connectivity, not merely "is there NavMesh nearby."
        [Test]
        public void RequestDisplacement_SampledPointDisconnectedAcrossWall_RejectsItAndStaysPathConnected()
        {
            var isolationRoot = new GameObject("DisconnectedRoomsTestRoot");

            try
            {
                var roomOrigin = new Vector3(200f, 0f, 0f);
                BuildDisconnectedRoomsFloor(isolationRoot.transform, roomOrigin);

                var navigationRoot = new GameObject("DisconnectedRoomsNavigation");
                navigationRoot.transform.SetParent(isolationRoot.transform, false);
                var isolatedSurface = navigationRoot.AddComponent<GameplayNavigationSurface>();
                isolatedSurface.ConfigureAndBuild();

                try
                {
                    Assert.IsTrue(NavMesh.SamplePosition(roomOrigin, out var spawnHit, 2f, NavMesh.AllAreas),
                        "Expected the isolated Room A spawn point to sample onto its own baked floor.");

                    var isolatedEnemyObject = new GameObject("DisconnectedRoomsEnemy");
                    isolatedEnemyObject.transform.SetParent(isolationRoot.transform, false);
                    isolatedEnemyObject.transform.position = spawnHit.position;

                    var settings = NavMesh.GetSettingsByIndex(0);
                    var isolatedAgent = isolatedEnemyObject.AddComponent<NavMeshAgent>();
                    isolatedAgent.agentTypeID = settings.agentTypeID;
                    isolatedAgent.radius = settings.agentRadius;
                    isolatedAgent.height = settings.agentHeight;
                    isolatedAgent.Warp(spawnHit.position);

                    var isolatedStatusEffect = isolatedEnemyObject.AddComponent<EnemyStatusEffectMovement>();

                    // Room B (the disconnected island) spans roomOrigin.z + 8..16; a knockback of
                    // 32 forward first samples well past Room B (no NavMesh nearby), then lands
                    // directly inside Room B at 16 and 8, and only succeeds - within Room A - at
                    // the shortest, 4-unit fallback distance.
                    var originalInstanceId = isolatedEnemyObject.GetInstanceID();
                    var positionBeforeDisplacement = isolatedEnemyObject.transform.position;

                    isolatedStatusEffect.RequestDisplacement(Vector3.forward, 32f);

                    var positionAfterDisplacement = isolatedEnemyObject.transform.position;

                    Assert.That(isolatedEnemyObject.GetInstanceID(), Is.EqualTo(originalInstanceId));
                    Assert.That(positionAfterDisplacement.z - roomOrigin.z, Is.LessThan(8f),
                        "Expected RequestDisplacement to reject the sampled NavMesh point on the far side " +
                        "of the wall, which is not reachable by an actual walkable path.");

                    var verificationPath = new NavMeshPath();
                    Assert.IsTrue(
                        NavMesh.CalculatePath(positionBeforeDisplacement, positionAfterDisplacement,
                            NavMesh.AllAreas, verificationPath),
                        "Expected the enemy's final position after a rejected displacement to still be " +
                        "path-reachable from where it started.");
                    Assert.That(verificationPath.status, Is.EqualTo(NavMeshPathStatus.PathComplete),
                        "Expected the enemy's final position after a rejected displacement to remain fully " +
                        "walkable-connected rather than landing in a disconnected pocket.");
                }
                finally
                {
                    isolatedSurface.ClearBakedData();
                }
            }
            finally
            {
                Object.DestroyImmediate(isolationRoot);
            }
        }

        // AC-003: a zero knockback direction (e.g. an ability that failed to compute a radial
        // direction) still resolves to a deterministic displacement instead of leaving the enemy
        // stuck or throwing.
        [Test]
        public void RequestDisplacement_ZeroDirection_FallsBackToForwardDirectionAndStillDisplaces()
        {
            var positionBeforeDisplacement = enemyObject.transform.position;

            Assert.DoesNotThrow(() => statusEffectMovement.RequestDisplacement(Vector3.zero, 2f));

            Assert.That(Vector3.Distance(enemyObject.transform.position, positionBeforeDisplacement),
                Is.GreaterThan(0.5f));
            Assert.IsTrue(agent.isOnNavMesh);
        }

        // Defensive: a non-positive distance is a no-op rather than an unintended warp.
        [Test]
        public void RequestDisplacement_NonPositiveDistance_DoesNotMoveAgent()
        {
            var positionBeforeDisplacement = enemyObject.transform.position;

            statusEffectMovement.RequestDisplacement(Vector3.right, 0f);

            Assert.That(Vector3.Distance(enemyObject.transform.position, positionBeforeDisplacement),
                Is.LessThan(0.01f));
        }

        // AC-003/AC-004, VAL-002: a displacement requested while the enemy is actively pursuing
        // preserves valid navigation state and does not require this component to drive pursuit
        // itself - EnemyPursuitMovement's existing per-frame destination refresh resumes closing
        // the distance to the target on its own once the displaced enemy's next Update runs.
        [UnityTest]
        public IEnumerator RequestDisplacement_WhilePursuing_PreservesNavigationAndPursuitResumesTowardTarget()
        {
            wizardTransform.position = WizardNearPoint;
            pursuitMovement.Tick(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));

            var awayFromWizard = (enemyObject.transform.position - wizardTransform.position);
            awayFromWizard.y = 0f;
            if (awayFromWizard.sqrMagnitude < 0.0001f) awayFromWizard = Vector3.left;

            var positionBeforeDisplacement = enemyObject.transform.position;
            var distanceBeforeDisplacement = Vector3.Distance(positionBeforeDisplacement, wizardTransform.position);
            var originalInstanceId = enemyObject.GetInstanceID();

            statusEffectMovement.RequestDisplacement(awayFromWizard, 3f);

            Assert.That(enemyObject.GetInstanceID(), Is.EqualTo(originalInstanceId));
            Assert.IsTrue(agent.isOnNavMesh, "Expected the displaced enemy to remain on a valid NavMesh position.");
            var distanceAfterDisplacement = Vector3.Distance(enemyObject.transform.position, wizardTransform.position);
            Assert.That(distanceAfterDisplacement, Is.GreaterThan(distanceBeforeDisplacement),
                "Expected the requested displacement to actually push the enemy away from its target.");

            yield return WaitUntilOrTimeout(
                () => Vector3.Distance(enemyObject.transform.position, wizardTransform.position) <
                      distanceAfterDisplacement - 0.5f,
                5f,
                "Expected pursuit movement to resume closing the distance to the target after displacement.");

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
        }

        // AC-005, VAL-004: the owner-controlled reset entry point clears an active Frost
        // slowdown and restores baseline NavMeshAgent speed for floor restart.
        [Test]
        public void ResetStatusEffects_WhileFrostActive_ClearsSlowdownAndRestoresBaselineSpeed()
        {
            var baselineSpeed = statusEffectMovement.BaselineSpeed;
            statusEffectMovement.ApplyFrostSlowdown(0.3f, 5f);
            Assert.IsTrue(statusEffectMovement.IsFrostSlowdownActive);

            statusEffectMovement.ResetStatusEffects();

            Assert.IsFalse(statusEffectMovement.IsFrostSlowdownActive);
            Assert.That(statusEffectMovement.FrostTimeRemaining, Is.EqualTo(0f));
            Assert.That(agent.speed, Is.EqualTo(baselineSpeed).Within(0.001f));
        }

        // Defensive, VAL-004: resetting with no active effects does not throw and leaves the
        // agent at its authored baseline speed, matching a floor restart that clears every
        // enemy's status-effect state regardless of whether it was active.
        [Test]
        public void ResetStatusEffects_WithNoActiveEffects_DoesNotThrowAndLeavesBaselineSpeed()
        {
            var baselineSpeed = statusEffectMovement.BaselineSpeed;

            Assert.DoesNotThrow(() => statusEffectMovement.ResetStatusEffects());

            Assert.That(agent.speed, Is.EqualTo(baselineSpeed).Within(0.001f));
        }

        // AC-005, VAL-004: after reset, Frost can be applied again normally, matching
        // floor-restart reuse of the same persistent enemy.
        [Test]
        public void ResetStatusEffects_ThenFrostAppliedAgain_AppliesNormally()
        {
            var baselineSpeed = statusEffectMovement.BaselineSpeed;
            statusEffectMovement.ApplyFrostSlowdown(0.3f, 5f);
            statusEffectMovement.ResetStatusEffects();

            statusEffectMovement.ApplyFrostSlowdown(0.6f, 2f);

            Assert.IsTrue(statusEffectMovement.IsFrostSlowdownActive);
            Assert.That(agent.speed, Is.EqualTo(baselineSpeed * 0.6f).Within(0.001f));
        }

        private static IEnumerator WaitUntilOrTimeout(Func<bool> condition, float timeoutSeconds,
            string timeoutMessage)
        {
            var elapsed = 0f;
            while (!condition())
            {
                if (elapsed >= timeoutSeconds)
                {
                    Assert.Fail(timeoutMessage);
                }

                yield return null;
                elapsed += Time.deltaTime;
            }
        }

        private void BuildOpenFloor()
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.name = "TestGameplayFloor";
            floor.transform.SetParent(root.transform, false);
            floor.transform.position = Vector3.zero;
            floor.transform.localScale = new Vector3(FloorSize, 0.1f, FloorSize);
        }

        // Builds a small Room A (holds the enemy), a solid wall, a real floor gap, and a
        // separate Room B floor beyond the wall - all offset by roomOrigin so this isolated bake
        // never touches the shared open-floor fixture built by BuildOpenFloor. Room B's floor
        // still exists so NavMesh.SamplePosition can find it; only the missing floor gap plus the
        // wall between z 4 and 8 (relative to roomOrigin) make it walkably unreachable from
        // Room A, proving RequestDisplacement's rejection is path-based rather than distance-only.
        private static void BuildDisconnectedRoomsFloor(Transform parent, Vector3 roomOrigin)
        {
            var roomA = GameObject.CreatePrimitive(PrimitiveType.Cube);
            roomA.name = "DisconnectedRoomA";
            roomA.transform.SetParent(parent, false);
            roomA.transform.position = roomOrigin;
            roomA.transform.localScale = new Vector3(8f, 0.1f, 8f);

            var wall = GameObject.CreatePrimitive(PrimitiveType.Cube);
            wall.name = "DisconnectedRoomsWall";
            wall.transform.SetParent(parent, false);
            wall.transform.position = roomOrigin + new Vector3(0f, 1.5f, 6f);
            wall.transform.localScale = new Vector3(10f, 3f, 0.5f);

            var roomB = GameObject.CreatePrimitive(PrimitiveType.Cube);
            roomB.name = "DisconnectedRoomB";
            roomB.transform.SetParent(parent, false);
            roomB.transform.position = roomOrigin + new Vector3(0f, 0f, 12f);
            roomB.transform.localScale = new Vector3(8f, 0.1f, 8f);
        }
    }
}
