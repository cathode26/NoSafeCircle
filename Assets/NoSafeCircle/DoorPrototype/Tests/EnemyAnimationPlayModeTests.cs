using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class EnemyAnimationPlayModeTests
    {
        private static readonly DirectionSample[] MovementDirections =
        {
            new DirectionSample("north", new Vector3(-1f, 0f, 1f)),
            new DirectionSample("north-east", new Vector3(0f, 0f, 1f)),
            new DirectionSample("east", new Vector3(1f, 0f, 1f)),
            new DirectionSample("south-east", new Vector3(1f, 0f, 0f)),
            new DirectionSample("south", new Vector3(1f, 0f, -1f)),
            new DirectionSample("south-west", new Vector3(0f, 0f, -1f)),
            new DirectionSample("west", new Vector3(-1f, 0f, -1f)),
            new DirectionSample("north-west", new Vector3(-1f, 0f, 0f))
        };

        [UnityTearDown]
        public IEnumerator UnloadCommittedSceneWithoutSaving()
        {
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            Scene cleanupScene = SceneManager.CreateScene("EnemyAnimationTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }

        // NSC-077 AC-005 and VAL-004: both generated state families use the specified fixed-camera
        // mapping for all eight world movement directions.
        [Test]
        public void Tick_SelectsAllEightWalkDirectionsForBothEnemyTypes()
        {
            foreach (EnemyAnimationKind kind in Enum.GetValues(typeof(EnemyAnimationKind)))
            {
                foreach (DirectionSample direction in MovementDirections)
                {
                    GameObject enemy = CreateAnimationEnemy(kind, out EnemyAnimationController animation);
                    try
                    {
                        MoveAndTick(enemy, animation, direction.WorldMovement, 0.1f);
                        Assert.AreEqual(kind + "_walk_" + direction.Name, animation.CurrentState);
                        Assert.AreEqual(direction.Name, animation.LastDirection);
                    }
                    finally
                    {
                        UnityEngine.Object.DestroyImmediate(enemy);
                    }
                }
            }
        }

        // NSC-077 AC-005 and VAL-004: angular hysteresis retains every prior direction while
        // deterministic sideways noise alternates across its sector boundary.
        [Test]
        public void Tick_HeldBoundaryNoiseDoesNotChangeFacingForEitherEnemyType()
        {
            foreach (EnemyAnimationKind kind in Enum.GetValues(typeof(EnemyAnimationKind)))
            {
                foreach (DirectionSample priorDirection in MovementDirections)
                {
                    GameObject enemy = CreateAnimationEnemy(kind, out EnemyAnimationController animation);
                    try
                    {
                        MoveAndTick(enemy, animation, priorDirection.WorldMovement, 0.1f);
                        Assert.AreEqual(priorDirection.Name, animation.LastDirection);

                        for (int sample = 0; sample < 6; sample++)
                        {
                            float offset = sample % 2 == 0 ? -0.05f : 0.05f;
                            MoveAndTick(
                                enemy,
                                animation,
                                BoundaryMovementFor(priorDirection.Name, offset) * 0.1f,
                                0.1f);
                            Assert.AreEqual(priorDirection.Name, animation.LastDirection,
                                kind + " changed at the " + priorDirection.Name + " boundary.");
                        }
                    }
                    finally
                    {
                        UnityEngine.Object.DestroyImmediate(enemy);
                    }
                }
            }
        }

        // NSC-077 AC-005 and VAL-004: start/stop speed hysteresis prevents a speed between the
        // two thresholds from alternating idle and walk.
        [Test]
        public void Tick_SpeedHysteresisDoesNotAlternateIdleAndWalk()
        {
            foreach (EnemyAnimationKind kind in Enum.GetValues(typeof(EnemyAnimationKind)))
            {
                GameObject enemy = CreateAnimationEnemy(kind, out EnemyAnimationController animation);
                try
                {
                    MoveAtSpeedAndTick(enemy, animation, Vector3.forward, 0.11f, 0.1f);
                    Assert.That(animation.CurrentState, Does.Contain("_walk_"));

                    MoveAtSpeedAndTick(enemy, animation, Vector3.forward, 0.075f, 0.1f);
                    Assert.That(animation.CurrentState, Does.Contain("_walk_"));

                    MoveAtSpeedAndTick(enemy, animation, Vector3.forward, 0.04f, 0.1f);
                    Assert.That(animation.CurrentState, Does.Contain("_idle_"));

                    MoveAtSpeedAndTick(enemy, animation, Vector3.forward, 0.075f, 0.1f);
                    Assert.That(animation.CurrentState, Does.Contain("_idle_"));
                }
                finally
                {
                    UnityEngine.Object.DestroyImmediate(enemy);
                }
            }
        }

        // NSC-077 AC-005 and VAL-004: stopping retains the last movement facing, and equal
        // velocity at different frame times selects the same state.
        [Test]
        public void Tick_StoppingRetainsFacingAndFrameTimeDoesNotChangeState()
        {
            foreach (EnemyAnimationKind kind in Enum.GetValues(typeof(EnemyAnimationKind)))
            {
                GameObject fastFrameEnemy = CreateAnimationEnemy(
                    kind, out EnemyAnimationController fastFrameAnimation);
                GameObject slowFrameEnemy = CreateAnimationEnemy(
                    kind, out EnemyAnimationController slowFrameAnimation);
                try
                {
                    MoveAtSpeedAndTick(
                        fastFrameEnemy, fastFrameAnimation, Vector3.right, 2f, 0.02f);
                    MoveAtSpeedAndTick(
                        slowFrameEnemy, slowFrameAnimation, Vector3.right, 2f, 0.2f);
                    Assert.AreEqual(fastFrameAnimation.CurrentState, slowFrameAnimation.CurrentState);
                    Assert.AreEqual("south-east", fastFrameAnimation.LastDirection);

                    fastFrameAnimation.Tick(0.02f);
                    Assert.AreEqual(kind + "_idle_south-east", fastFrameAnimation.CurrentState);
                    Assert.AreEqual("south-east", fastFrameAnimation.LastDirection);
                }
                finally
                {
                    UnityEngine.Object.DestroyImmediate(fastFrameEnemy);
                    UnityEngine.Object.DestroyImmediate(slowFrameEnemy);
                }
            }
        }

        // NSC-077 INT-001 regression: encounter admission can deactivate and reactivate an
        // enemy, so the cached state must be cleared and replayed after re-enabling.
        [Test]
        public void OnEnable_ClearsCachedStateBeforeReapplyingTheRetainedFacing()
        {
            foreach (EnemyAnimationKind kind in Enum.GetValues(typeof(EnemyAnimationKind)))
            {
                GameObject enemy = CreateAnimationEnemy(
                    kind, out EnemyAnimationController animation);
                try
                {
                    MoveAndTick(enemy, animation, Vector3.right, 0.1f);
                    animation.Tick(0.1f);
                    Assert.AreEqual(kind + "_idle_south-east", animation.CurrentState);

                    enemy.SetActive(false);
                    enemy.SetActive(true);

                    Assert.IsNull(
                        animation.CurrentState,
                        kind + " retained a stale animation-state cache after re-enabling.");
                    animation.Tick(0.1f);
                    Assert.AreEqual(kind + "_idle_south-east", animation.CurrentState);
                }
                finally
                {
                    UnityEngine.Object.DestroyImmediate(enemy);
                }
            }
        }

        // NSC-077 AC-005 and VAL-004: the enemy classifier matches the corrected wizard
        // classifier for the same eight displacements.
        [Test]
        public void Tick_FacingMatchesWizardForTheSameDisplacements()
        {
            MethodInfo wizardUpdate = typeof(WizardAnimationController).GetMethod(
                "Update", BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.IsNotNull(wizardUpdate);

            foreach (EnemyAnimationKind kind in Enum.GetValues(typeof(EnemyAnimationKind)))
            {
                foreach (DirectionSample direction in MovementDirections)
                {
                    var wizardObject = new GameObject("WizardDirectionReference");
                    wizardObject.AddComponent<Animator>();
                    WizardAnimationController wizard =
                        wizardObject.AddComponent<WizardAnimationController>();
                    GameObject enemy = CreateAnimationEnemy(
                        kind, out EnemyAnimationController animation);
                    try
                    {
                        wizardObject.transform.position += direction.WorldMovement;
                        wizardUpdate.Invoke(wizard, null);
                        MoveAndTick(enemy, animation, direction.WorldMovement, 0.1f);

                        Assert.AreEqual(
                            wizard.LastDirection,
                            animation.LastDirection,
                            kind + " " + direction.Name);
                    }
                    finally
                    {
                        UnityEngine.Object.DestroyImmediate(wizardObject);
                        UnityEngine.Object.DestroyImmediate(enemy);
                    }
                }
            }
        }

        // NSC-077 AC-003 and VAL-004: NavMeshAgent can rotate an enemy root while moving, but
        // both enemy SpriteRenderers must retain the fixed camera-facing world rotation.
        [Test]
        public void Tick_RestoresCameraFacingVisualAfterEnemyRootRotates()
        {
            Quaternion expectedRotation = Quaternion.Euler(30f, -45f, 0f);
            foreach (EnemyAnimationKind kind in Enum.GetValues(typeof(EnemyAnimationKind)))
            {
                GameObject enemy = CreateAnimationEnemy(
                    kind, out EnemyAnimationController animation);
                try
                {
                    Transform visual = enemy.transform.Find("Visual");
                    enemy.transform.position += Vector3.right;
                    enemy.transform.rotation = Quaternion.Euler(0f, 90f, 0f);
                    Assert.That(Quaternion.Angle(expectedRotation, visual.rotation),
                        Is.GreaterThan(1f), kind + " test setup did not rotate the Visual.");

                    animation.Tick(0.1f);

                    Assert.That(animation.CurrentState, Does.Contain("_walk_"), kind.ToString());
                    Assert.That(Quaternion.Angle(expectedRotation, visual.rotation),
                        Is.LessThan(0.01f), kind + " Visual did not return to camera rotation.");
                }
                finally
                {
                    UnityEngine.Object.DestroyImmediate(enemy);
                }
            }
        }

        // NSC-077 AC-006 and VAL-004: a stopped MeleeEnemy faces only a current knowledge
        // target; without one it retains its prior direction.
        [Test]
        public void Tick_StoppedMeleeFacesCurrentTargetAndRetainsFacingWithoutTarget()
        {
            var enemy = new GameObject("MeleeEnemy");
            enemy.AddComponent<Animator>();
            EnemyTargetKnowledge knowledge = enemy.AddComponent<EnemyTargetKnowledge>();
            EnemyAnimationController animation = enemy.AddComponent<EnemyAnimationController>();
            var wizard = new GameObject("Wizard");
            try
            {
                animation.Initialize(enemy.GetComponent<Animator>(), EnemyAnimationKind.MeleeEnemy);
                MoveAndTick(enemy, animation, Vector3.back, 0.1f);
                animation.Tick(0.1f);
                Assert.AreEqual("south-west", animation.LastDirection);

                wizard.transform.position = enemy.transform.position + new Vector3(-1f, 0f, 1f);
                knowledge.Initialize(wizard.transform);
                knowledge.UpdateTargetKnowledge(0f);
                Assert.IsTrue(knowledge.HasTarget);
                animation.Tick(0.1f);
                Assert.AreEqual("MeleeEnemy_idle_north", animation.CurrentState);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(enemy);
                UnityEngine.Object.DestroyImmediate(wizard);
            }
        }

        // NSC-077 AC-006 and VAL-004: movement owns facing while walking even when the current
        // target occupies a different screen sector.
        [Test]
        public void Tick_WalkingMeleeFacesMovementInsteadOfCurrentTarget()
        {
            var enemy = new GameObject("MeleeEnemy");
            enemy.AddComponent<Animator>();
            EnemyTargetKnowledge knowledge = enemy.AddComponent<EnemyTargetKnowledge>();
            EnemyAnimationController animation = enemy.AddComponent<EnemyAnimationController>();
            var wizard = new GameObject("Wizard");
            try
            {
                wizard.transform.position = new Vector3(0f, 0f, 3f);
                knowledge.Initialize(wizard.transform);
                knowledge.UpdateTargetKnowledge(0f);
                Assert.IsTrue(knowledge.HasTarget);
                animation.Initialize(enemy.GetComponent<Animator>(), EnemyAnimationKind.MeleeEnemy);

                MoveAndTick(enemy, animation, Vector3.right, 0.1f);

                Assert.AreEqual("south-east", animation.LastDirection);
                Assert.AreEqual("MeleeEnemy_walk_south-east", animation.CurrentState);
                Assert.AreNotEqual(
                    animation.LastDirection,
                    DirectionFor(wizard.transform.position - enemy.transform.position),
                    "Test setup must put the current target outside the movement-facing sector.");
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(enemy);
                UnityEngine.Object.DestroyImmediate(wizard);
            }
        }

        // NSC-077 AC-006 and VAL-004: a stopped Lantern Wraith faces a wizard in cast range
        // with clear sight, but retains its facing out of range or behind a solid wall.
        [Test]
        public void Tick_StoppedWraithFacesOnlyWizardInRangeWithClearView()
        {
            var wraith = new GameObject("LanternWraith");
            wraith.AddComponent<Animator>();
            EnemyLanternWispCaster caster = wraith.AddComponent<EnemyLanternWispCaster>();
            EnemyAnimationController animation = wraith.AddComponent<EnemyAnimationController>();
            var wizard = new GameObject("Wizard");
            wizard.AddComponent<CharacterController>();
            GameObject wall = null;
            try
            {
                caster.Initialize(wizard.transform);
                animation.Initialize(wraith.GetComponent<Animator>(), EnemyAnimationKind.LanternWraith);

                wizard.transform.position = new Vector3(3f, 0f, 0f);
                Physics.SyncTransforms();
                Assert.AreSame(wizard.transform, caster.FacingTarget);
                animation.Tick(0.1f);
                Assert.AreEqual("LanternWraith_idle_south-east", animation.CurrentState);

                wizard.transform.position = new Vector3(0f, 0f, 20f);
                Physics.SyncTransforms();
                Assert.IsNull(caster.FacingTarget);
                Assert.AreEqual("north-east", DirectionFor(wizard.transform.position));
                animation.Tick(0.1f);
                Assert.AreEqual("south-east", animation.LastDirection);

                wizard.transform.position = new Vector3(0f, 0f, 3f);
                wall = GameObject.CreatePrimitive(PrimitiveType.Cube);
                wall.name = "SightBlockingWall";
                wall.transform.position = new Vector3(0f, 1f, 1.5f);
                wall.transform.localScale = new Vector3(2f, 2f, 0.25f);
                Physics.SyncTransforms();
                Assert.IsNull(caster.FacingTarget);
                animation.Tick(0.1f);
                Assert.AreEqual("south-east", animation.LastDirection);
            }
            finally
            {
                if (wall != null) UnityEngine.Object.DestroyImmediate(wall);
                UnityEngine.Object.DestroyImmediate(wraith);
                UnityEngine.Object.DestroyImmediate(wizard);
            }
        }

        // NSC-077 AC-001/AC-006/AC-008 and VAL-006: production scene enemies animate their
        // actual movement/targets, the stationary wraith casts, and no placeholder/fire object remains.
        [UnityTest]
        public IEnumerator SavedSceneEnemiesUseProductionAnimationAndLanternWisp()
        {
            yield return SceneManager.LoadSceneAsync("DoorPrototype", LoadSceneMode.Single);
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            Assert.IsTrue(scene.IsValid() && scene.isLoaded);

            GameObject player = FindRoot(scene, "Player");
            GameObject enemiesRoot = FindRoot(scene, "Enemies");
            GameObject melee = FindEnemyAtSpawn(
                enemiesRoot,
                "MeleeEnemy",
                new Vector3(7f, 0f, 31f));
            GameObject wraith = FindEnemyAtSpawn(
                enemiesRoot,
                "LanternWraith",
                new Vector3(7f, 0f, 13f));

            CharacterController playerController = player.GetComponent<CharacterController>();
            EnemyAnimationController meleeAnimation = melee.GetComponent<EnemyAnimationController>();
            EnemyTargetKnowledge knowledge = melee.GetComponent<EnemyTargetKnowledge>();
            NavMeshAgent agent = melee.GetComponent<NavMeshAgent>();

            yield return WaitForCondition(
                () => agent.isOnNavMesh,
                5f,
                "Chapel of Ash MeleeEnemy at (7, 0, 31) did not join the baked NavMesh.");

            TeleportPlayer(player, playerController, new Vector3(9f, 0f, 31f));
            yield return WaitForCondition(
                () => knowledge.HasTarget,
                5f,
                "Chapel of Ash MeleeEnemy did not acquire the wizard across the clear pew-row gap.");

            Vector3 meleeStart = melee.transform.position;
            Vector3 previousMeleePosition = meleeStart;
            Vector3 latestMeleeDisplacement = Vector3.zero;
            yield return WaitForCondition(
                () =>
                {
                    latestMeleeDisplacement = melee.transform.position - previousMeleePosition;
                    previousMeleePosition = melee.transform.position;
                    latestMeleeDisplacement.y = 0f;
                    return latestMeleeDisplacement.sqrMagnitude > 0.000001f &&
                        meleeAnimation.CurrentState != null &&
                        meleeAnimation.CurrentState.StartsWith("MeleeEnemy_walk_");
                },
                5f,
                "Chapel of Ash MeleeEnemy acquired the wizard but did not begin moving on the NavMesh.");

            Assert.That(
                (melee.transform.position - meleeStart).sqrMagnitude,
                Is.GreaterThan(0.000001f));
            Assert.That(meleeAnimation.CurrentState, Does.StartWith("MeleeEnemy_walk_"));
            string walkingDirection = DirectionFor(latestMeleeDisplacement);
            Assert.AreEqual(walkingDirection, meleeAnimation.LastDirection);

            EnemyPursuitMovement pursuit = melee.GetComponent<EnemyPursuitMovement>();
            pursuit.enabled = false;
            Assert.IsTrue(
                agent.isOnNavMesh,
                "Chapel of Ash MeleeEnemy left the baked NavMesh before the stop-facing check.");
            agent.isStopped = true;
            agent.ResetPath();
            yield return null;

            TeleportPlayer(
                player,
                playerController,
                melee.transform.position + Vector3.left * 2f);
            string stoppedTargetDirection =
                DirectionFor(player.transform.position - melee.transform.position);
            Assert.AreNotEqual(
                walkingDirection,
                stoppedTargetDirection,
                "VAL-006 setup must distinguish target-facing idle from retained movement facing.");
            meleeAnimation.Tick(0.1f);
            Assert.That(meleeAnimation.CurrentState, Does.StartWith("MeleeEnemy_idle_"));
            Assert.AreEqual(stoppedTargetDirection, meleeAnimation.LastDirection);

            TeleportPlayer(player, playerController, new Vector3(9f, 0f, 13f));
            EnemyLanternWispCaster caster = wraith.GetComponent<EnemyLanternWispCaster>();
            yield return WaitForCondition(
                () => caster.FacingTarget == player.transform,
                5f,
                "Bone Archive LanternWraith at (7, 0, 13) did not get a clear view of the wizard.");

            EnemyAnimationController wraithAnimation = wraith.GetComponent<EnemyAnimationController>();
            yield return WaitForCondition(
                () => FindNamedObject(scene, "LanternWisp") != null,
                5f,
                "Bone Archive LanternWraith saw the wizard but did not cast a LanternWisp.");

            Assert.AreEqual("LanternWraith_idle_south-east", wraithAnimation.CurrentState);
            Assert.That(wraithAnimation.CurrentState, Does.Not.Contain("_walk_"));
            Assert.IsNotNull(FindNamedObject(scene, "LanternWisp"));

            foreach (GameObject enemy in DirectChildren(enemiesRoot))
            {
                SpriteRenderer renderer = enemy.transform.Find("Visual")?.GetComponent<SpriteRenderer>();
                Assert.IsNotNull(renderer, enemy.name);
                Assert.IsNotNull(renderer.sprite, enemy.name);
                Assert.That(renderer.sprite.name, Does.StartWith("enemy_"), enemy.name);
            }

            Transform[] allTransforms = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<Transform>(true))
                .ToArray();
            Assert.IsFalse(allTransforms.Any(item => item.name == "FireCasterEnemy"));
            Assert.IsFalse(allTransforms.Any(item => item.name == "EnemyFireball"));
        }

        private static IEnumerator WaitForCondition(
            Func<bool> condition,
            float timeoutSeconds,
            string failureMessage)
        {
            float deadline = Time.realtimeSinceStartup + timeoutSeconds;
            bool satisfied = condition();
            while (!satisfied && Time.realtimeSinceStartup < deadline)
            {
                yield return null;
                satisfied = condition();
            }

            Assert.IsTrue(satisfied, failureMessage);
        }

        private static void TeleportPlayer(
            GameObject player,
            CharacterController controller,
            Vector3 position)
        {
            controller.enabled = false;
            player.transform.position = position;
            controller.enabled = true;
            Physics.SyncTransforms();
        }

        private static GameObject FindEnemyAtSpawn(
            GameObject enemiesRoot,
            string enemyName,
            Vector3 spawnPosition)
        {
            GameObject enemy = DirectChildren(enemiesRoot).SingleOrDefault(candidate =>
                candidate.name == enemyName &&
                (candidate.transform.position - spawnPosition).sqrMagnitude < 0.0001f);
            Assert.IsNotNull(
                enemy,
                "Expected " + enemyName + " at builder spawn " + spawnPosition + ".");
            return enemy;
        }

        private static GameObject CreateAnimationEnemy(
            EnemyAnimationKind kind,
            out EnemyAnimationController animation)
        {
            var enemy = new GameObject(kind.ToString());
            var visual = new GameObject("Visual", typeof(SpriteRenderer));
            visual.transform.SetParent(enemy.transform, false);
            visual.transform.rotation = Quaternion.Euler(30f, -45f, 0f);
            Animator animator = enemy.AddComponent<Animator>();
            animation = enemy.AddComponent<EnemyAnimationController>();
            animation.Initialize(animator, kind);
            return enemy;
        }

        private static void MoveAndTick(GameObject enemy, EnemyAnimationController animation,
            Vector3 displacement, float deltaTime)
        {
            enemy.transform.position += displacement;
            animation.Tick(deltaTime);
        }

        private static void MoveAtSpeedAndTick(GameObject enemy, EnemyAnimationController animation,
            Vector3 direction, float speed, float deltaTime)
        {
            MoveAndTick(enemy, animation, direction.normalized * (speed * deltaTime), deltaTime);
        }

        private static Vector3 BoundaryMovementFor(string direction, float offset)
        {
            float angle;
            switch (direction)
            {
                case "north-east": angle = 22.5f; break;
                case "east": angle = -22.5f; break;
                case "south-east": angle = -67.5f; break;
                case "south": angle = -112.5f; break;
                case "south-west": angle = -157.5f; break;
                case "west": angle = 157.5f; break;
                case "north-west": angle = 112.5f; break;
                case "north": angle = 67.5f; break;
                default: throw new ArgumentOutOfRangeException(nameof(direction));
            }

            float radians = (angle + offset) * Mathf.Deg2Rad;
            float screenX = Mathf.Cos(radians);
            float screenY = Mathf.Sin(radians);
            return new Vector3((screenX - screenY) * 0.5f, 0f,
                (screenX + screenY) * 0.5f);
        }

        private static string DirectionFor(Vector3 movement)
        {
            Vector2 screen = new Vector2(movement.x + movement.z, movement.z - movement.x);
            float angle = Mathf.Atan2(screen.y, screen.x) * Mathf.Rad2Deg;
            if (angle < -157.5f || angle >= 157.5f) return "west";
            if (angle < -112.5f) return "south-west";
            if (angle < -67.5f) return "south";
            if (angle < -22.5f) return "south-east";
            if (angle < 22.5f) return "east";
            if (angle < 67.5f) return "north-east";
            if (angle < 112.5f) return "north";
            return "north-west";
        }

        private static GameObject FindRoot(Scene scene, string name)
        {
            GameObject result = scene.GetRootGameObjects().SingleOrDefault(root => root.name == name);
            Assert.IsNotNull(result, "Expected one " + name + " root in " + scene.path);
            return result;
        }

        private static GameObject[] DirectChildren(GameObject parent)
        {
            return Enumerable.Range(0, parent.transform.childCount)
                .Select(index => parent.transform.GetChild(index).gameObject)
                .ToArray();
        }

        private static GameObject FindNamedObject(Scene scene, string name)
        {
            return scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<Transform>(true))
                .FirstOrDefault(item => item.name == name)?.gameObject;
        }

        private readonly struct DirectionSample
        {
            public readonly string Name;
            public readonly Vector3 WorldMovement;

            public DirectionSample(string name, Vector3 worldMovement)
            {
                Name = name;
                WorldMovement = worldMovement;
            }
        }
    }
}
