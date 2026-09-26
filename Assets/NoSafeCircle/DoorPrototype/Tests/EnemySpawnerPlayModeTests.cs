using System.Collections;
using System.Linq;
using System.Text.RegularExpressions;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.Enemies.Pooling;
using NoSafeCircle.DoorPrototype.Navigation;
using NoSafeCircle.DoorPrototype.World;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Proves the Enemies lane end to end at Play, with no scene and no bake: the authored spawner
    // prefab, the authored table and the authored enemy prefabs put nine enemies at the nine
    // pinned points, admit them through a registry that until now NO production code created,
    // return them to their pools on defeat, and re-arm them when the player dies.
    //
    // DEPENDS ON THE NAVIGATION LANE. NavigationSpawner (the real one, as the lane spec requires
    // of every fixture that bakes) and NavMeshRebakeExclusion live on branch lane/navigation-runtime,
    // which the integrator merges before this lane. Until then this file does not compile.
    //
    // Every expected count is derived from the table asset (the INPUT), never restated as a
    // literal; a table with a different number of entries changes every expectation with it.
    public sealed class EnemySpawnerPlayModeTests
    {
        private const string SpawnerResource = "Spawners/EnemySpawner";
        private const string TableResource = "Enemies/EnemySpawnTable";
        private const string MeleeResource = "Enemies/MeleeEnemy";
        private const string WraithResource = "Enemies/LanternWraith";

        // Covers every table position with margin: x [-22, 22], z [-3, 107], top face at y = 0.
        private static readonly Vector3 FloorCenter = new Vector3(0f, -0.25f, 52f);
        private static readonly Vector3 FloorSize = new Vector3(44f, 0.5f, 110f);

        // On the floor, and farther than any detection or cast range from every table point, so
        // nothing acquires the stand-in until a test moves it on purpose.
        private static readonly Vector3 PlayerStandby = new Vector3(-18f, 0f, 0f);

        private GameObject root;
        private NavigationSpawner navigation;
        private GameObject player;
        private PlayerHealth playerHealth;
        private EnemySpawner spawner;
        private EnemySpawnTable table;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("EnemySpawnerTestRoot");

            var floor = new GameObject("Floor").AddComponent<BoxCollider>();
            floor.transform.SetParent(root.transform, false);
            floor.center = FloorCenter;
            floor.size = FloorSize;
            Physics.SyncTransforms();

            var navigationObject = new GameObject("NavigationSpawner");
            navigationObject.transform.SetParent(root.transform, false);
            navigation = navigationObject.AddComponent<NavigationSpawner>();
            Assert.AreEqual(1, navigation.Spawn(),
                "The real NavigationSpawner did not bake, so every navmesh claim below would be vacuous.");

            // A stand-in player: the three components EnemySpawner and the enemies actually touch.
            // PlayerMovement warns about the missing input asset; a warning is not a failure.
            player = new GameObject("Player");
            player.transform.SetParent(root.transform, false);
            player.transform.position = PlayerStandby;
            player.AddComponent<CharacterController>();
            playerHealth = player.AddComponent<PlayerHealth>();
            player.AddComponent<PlayerMovement>();

            table = Resources.Load<EnemySpawnTable>(TableResource);
            Assert.IsNotNull(table, "Resources/" + TableResource + " did not load.");
            Assert.Greater(table.Entries.Count, 0, "The table declares zero entries; every count would be vacuous.");

            GameObject prefab = Resources.Load<GameObject>(SpawnerResource);
            Assert.IsNotNull(prefab, "Resources/" + SpawnerResource + " did not load - the same path GameBootstrap uses.");
            GameObject instance = Object.Instantiate(prefab, root.transform);
            instance.name = prefab.name;
            spawner = instance.GetComponent<EnemySpawner>();
            Assert.IsNotNull(spawner, "the spawner prefab carries no EnemySpawner");
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            if (navigation != null && navigation.Surface != null) navigation.Surface.ClearBakedData();
            if (root != null) Object.Destroy(root);
            yield return null;
        }

        private EnemyPrefabPool PoolFor(EnemySpawnEntry entry) =>
            entry.Kind == EnemyKind.Melee ? spawner.MeleePool : spawner.WraithPool;

        private GameObject InstanceOf(EnemySpawnEntry entry)
        {
            EnemyPrefabPool pool = PoolFor(entry);
            Assert.IsNotNull(pool, entry.Id + ": its pool does not exist, so Spawn() never got that far.");
            Assert.IsTrue(pool.TryGetInstance(entry.Id, out GameObject instance),
                "no live instance in slot '" + entry.Id + "'");
            return instance;
        }

        private static EnemyHealth Defeat(GameObject enemy)
        {
            var health = enemy.GetComponent<EnemyHealth>();
            health.TakeDamage(health.MaxHealth);
            Assert.IsTrue(health.IsDefeated, enemy.name + " survived its own max health in damage");
            return health;
        }

        private void AssertEveryEntryIsActiveAtItsPosition(string when)
        {
            foreach (EnemySpawnEntry entry in table.Entries)
            {
                GameObject instance = InstanceOf(entry);
                Assert.IsTrue(instance.activeInHierarchy, entry.Id + " is not active " + when);
                Vector3 p = instance.transform.position;
                Assert.AreEqual(entry.Position.x, p.x, 0.001f, entry.Id + " x " + when);
                Assert.AreEqual(entry.Position.z, p.z, 0.001f, entry.Id + " z " + when);
            }
        }

        [UnityTest]
        public IEnumerator Spawn_CreatesEveryTableEntryAtItsPositionOnTheNavMesh()
        {
            int expected = table.Entries.Count;

            int spawned = spawner.Spawn();
            yield return null;

            Assert.AreEqual(expected, spawned,
                "Spawn() admitted " + spawned + " of " + expected + " table entries.");
            Assert.AreEqual(expected, spawner.SpawnedCount, "the return value and SpawnedCount disagree");

            Transform enemiesRoot = spawner.transform.Find(EnemySpawner.EnemiesRootName);
            Assert.IsNotNull(enemiesRoot, "no '" + EnemySpawner.EnemiesRootName + "' child was created");
            Assert.IsNotNull(spawner.transform.Find(EnemySpawner.EnemiesRootName + "/MeleeEnemy"),
                "the name Enemies/MeleeEnemy is what scene-loading fixtures look up");
            Assert.IsNotNull(spawner.transform.Find(EnemySpawner.EnemiesRootName + "/LanternWraith"));

            // Count objects, not just the return value: a method can return a number without
            // having created anything.
            Assert.AreEqual(expected, enemiesRoot.GetComponentsInChildren<EnemyHealth>(false).Length,
                "active EnemyHealth instances under Enemies/ differ from the admitted count");

            AssertEveryEntryIsActiveAtItsPosition("after Spawn");
            foreach (EnemySpawnEntry entry in table.Entries)
            {
                GameObject instance = InstanceOf(entry);
                float y = instance.transform.position.y;

                // AC-006's tolerance, on the fixture floor. This proves the sampling gate is
                // satisfiable here, not that the real rooms satisfy it - that is increment C.
                Assert.IsTrue(NavMesh.SamplePosition(entry.Position, out _, 0.1f, NavMesh.AllAreas),
                    entry.Id + " does not sample onto the fixture navmesh within 0.1");
                Assert.LessOrEqual(Mathf.Abs(y), 0.1f,
                    entry.Id + " sits at y " + y + ". The prefab's NavMeshAgent baseOffset is 0 so the "
                    + "root rides on the navmesh, which lies within 0.1 of the authored y 0.");

                var agent = instance.GetComponent<NavMeshAgent>();
                if (entry.Kind == EnemyKind.Melee)
                {
                    Assert.IsNotNull(agent, entry.Id + ": a melee must carry a NavMeshAgent");
                    Assert.IsTrue(agent.isOnNavMesh, entry.Id + " is not on the navmesh after Warp");
                }
                else
                {
                    Assert.IsNull(agent, entry.Id + ": a wraith holds its ground and carries no agent");
                }
            }
        }

        [UnityTest]
        public IEnumerator Spawn_CreatesTheRegistryAndAdmitsEveryEnemyThroughIt()
        {
            int n = table.Entries.Count;
            Assert.LessOrEqual(n, ActiveEnemyRegistry.MaxActiveEnemies,
                "the table exceeds the cap, so full admission could not be expected");

            spawner.Spawn();
            yield return null;

            // THE REGISTRY EXISTS. Before this lane no production code created one, so every
            // EnemyHealth in the game held a null registry and a defeat unregistered nothing.
            ActiveEnemyRegistry registry = Object.FindFirstObjectByType<ActiveEnemyRegistry>();
            Assert.IsNotNull(registry, "no ActiveEnemyRegistry exists in the scene after Spawn()");
            Assert.AreSame(spawner.Registry, registry);
            Assert.AreSame(registry, spawner.Admission.Registry, "admission is not wired to the spawner's registry");
            Assert.AreEqual(n, registry.ActiveCount, "every admitted enemy is registered");
            Assert.AreEqual(n, spawner.Admission.AdmittedCount);
            Assert.AreEqual(0, spawner.Admission.PendingCount);

            // THE WIZARD REFERENCE TOOK. Walk the stand-in into a melee's detection range and it
            // acquires the stand-in. Detection distance is read from the prefab ASSET, not from
            // the instance under test.
            EnemySpawnEntry melee = table.Entries.First(e => e.Kind == EnemyKind.Melee);
            float detection = Resources.Load<GameObject>(MeleeResource)
                .GetComponent<EnemyTargetKnowledge>().DetectionDistance;
            var knowledge = InstanceOf(melee).GetComponent<EnemyTargetKnowledge>();
            Assert.AreEqual(EnemyTargetKnowledgeState.Idle, knowledge.State, "idle before the stand-in approaches");

            player.transform.position = melee.Position + new Vector3(detection * 0.5f, 0f, 0f);
            Physics.SyncTransforms();
            yield return null;
            for (int i = 0; i < 10; i++) knowledge.UpdateTargetKnowledge(0.1f);

            Assert.AreEqual(EnemyTargetKnowledgeState.Pursuing, knowledge.State,
                melee.Id + " did not acquire the stand-in at " + (detection * 0.5f) + " u with a "
                + "clear line of sight, so Initialize(player) did not take.");
            Assert.AreSame(player.transform, knowledge.CurrentTarget);
        }

        [UnityTest]
        public IEnumerator DefeatReturnsTheInstanceToThePoolAndUnregistersIt()
        {
            int n = table.Entries.Count;
            int melees = table.Entries.Count(e => e.Kind == EnemyKind.Melee);
            spawner.Spawn();
            yield return null;

            EnemySpawnEntry entry = table.Entries.First(e => e.Kind == EnemyKind.Melee);
            GameObject instance = InstanceOf(entry);
            Defeat(instance);

            Assert.IsFalse(instance.activeSelf, "a defeated enemy stayed active: the pool did not take it back");
            Assert.AreEqual(n - 1, spawner.Registry.ActiveCount, "the defeat did not unregister");
            Assert.AreEqual(melees - 1, spawner.MeleePool.Diagnostics.ActiveNow);
            Assert.AreEqual(0, spawner.MeleePool.Diagnostics.DoubleReturn,
                "the defeat handler and the registry both fired, but only one return may happen");
            Assert.IsFalse(spawner.MeleePool.Diagnostics.HasFault, spawner.MeleePool.Diagnostics.Report("MeleeEnemy"));
            Assert.IsTrue(spawner.MeleePool.TryGetInstance(entry.Id, out GameObject parked)
                && ReferenceEquals(parked, instance), "a melee recycles: the same object is parked in its slot");
        }

        [UnityTest]
        public IEnumerator PlayerDeathReturnsEverythingAndRespawnsFromTheSamePool()
        {
            int n = table.Entries.Count;
            int melees = table.Entries.Count(e => e.Kind == EnemyKind.Melee);
            spawner.Spawn();
            yield return null;

            var firstIds = table.Entries.ToDictionary(e => e.Id, e => InstanceOf(e).GetInstanceID());
            EnemySpawnEntry melee = table.Entries.First(e => e.Kind == EnemyKind.Melee);
            EnemySpawnEntry wraith = table.Entries.First(e => e.Kind == EnemyKind.LanternWraith);
            Defeat(InstanceOf(melee));
            Defeat(InstanceOf(wraith));
            Assert.AreEqual(n - 2, spawner.Registry.ActiveCount, "two defeats, two unregistered");

            playerHealth.TakeDamage(playerHealth.MaxHealth * 10f);
            yield return null;

            Assert.AreEqual(n, spawner.Registry.ActiveCount, "after the player died every enemy is re-armed");
            Assert.AreEqual(n, spawner.Admission.AdmittedCount);
            AssertEveryEntryIsActiveAtItsPosition("after the restart");

            var reborn = InstanceOf(melee).GetComponent<EnemyHealth>();
            Assert.IsFalse(reborn.IsDefeated, "the defeated melee came back defeated: ResetHealth did not run");
            Assert.AreEqual(reborn.MaxHealth, reborn.CurrentHealth);

            foreach (EnemySpawnEntry entry in table.Entries)
            {
                int nowId = InstanceOf(entry).GetInstanceID();
                if (entry.Kind == EnemyKind.Melee)
                {
                    Assert.AreEqual(firstIds[entry.Id], nowId, entry.Id + " was re-created; a melee recycles");
                }
                else
                {
                    Assert.AreNotEqual(firstIds[entry.Id], nowId,
                        entry.Id + " was recycled, but the wraith pool destroys on return because "
                        + "EnemyLanternWispCaster has no seam that clears its wisps");
                }
            }

            Assert.AreEqual(melees, spawner.MeleePool.Diagnostics.PeakActive);
            Assert.AreEqual(0, spawner.MeleePool.Diagnostics.DestroyedExternally);
            Assert.AreEqual(0, spawner.WraithPool.Diagnostics.DestroyedExternally,
                "the wraith pool's own destroy-on-return must not count as an external destruction");
            Assert.IsFalse(spawner.MeleePool.Diagnostics.HasFault, spawner.MeleePool.Diagnostics.Report("MeleeEnemy"));
            Assert.IsFalse(spawner.WraithPool.Diagnostics.HasFault, spawner.WraithPool.Diagnostics.Report("LanternWraith"));
        }

        [UnityTest]
        public IEnumerator SpawningTwiceLeavesExactlyOneSetOfEnemies()
        {
            int first = spawner.Spawn();
            yield return null;
            int second = spawner.Spawn();
            yield return null;

            Assert.AreEqual(first, second, "a second Spawn() admitted a different count");
            Assert.AreEqual(first, root.GetComponentsInChildren<EnemyHealth>(true).Length,
                "the first pool's instances were leaked rather than destroyed");
            Assert.AreEqual(first, spawner.Registry.ActiveCount, "the registry still counts the first set");
            Assert.AreEqual(1, spawner.transform.childCount, "more than one Enemies root survived");
        }

        [UnityTest]
        public IEnumerator Spawn_WithoutAPlayerCreatesNothingAndLogsAnError()
        {
            // FindFirstObjectByType excludes inactive objects, which is also what makes a
            // same-frame rebuild safe: a deactivated dying player cannot be found either.
            player.SetActive(false);

            LogAssert.Expect(LogType.Error, new Regex("PlayerMovement"));
            int spawned = spawner.Spawn();
            yield return null;

            Assert.AreEqual(0, spawned);
            Assert.AreEqual(0, spawner.SpawnedCount);
            Assert.IsNull(spawner.transform.Find(EnemySpawner.EnemiesRootName), "nothing may be created without a player");
            Assert.IsNull(spawner.MeleePool);
            Assert.IsNull(spawner.WraithPool);
            Assert.AreEqual(0, root.GetComponentsInChildren<EnemyHealth>(true).Length);
        }

        [UnityTest]
        public IEnumerator Spawn_RefusesATableWithARepeatedIdAndLogsAnError()
        {
            EnemySpawnEntry first = table.Entries[0];
            EnemySpawnTable duplicate = EnemySpawnTable.CreateRuntime(new[]
            {
                first,
                new EnemySpawnEntry(first.Id, first.Kind, first.Room, first.Position + Vector3.right)
            });
            spawner.Configure(duplicate, Resources.Load<GameObject>(MeleeResource),
                Resources.Load<GameObject>(WraithResource), spawner.Registry, spawner.Admission);

            LogAssert.Expect(LogType.Error, new Regex("repeated"));
            int spawned = spawner.Spawn();
            yield return null;

            Assert.AreEqual(0, spawned, "a table that fails validation must spawn nothing, not part of itself");
            Assert.IsNull(spawner.transform.Find(EnemySpawner.EnemiesRootName));
            Object.Destroy(duplicate);
        }

        [UnityTest]
        public IEnumerator EverySpawnedEnemyIsExcludedFromANavMeshRebake()
        {
            spawner.Spawn();
            yield return null;
            Transform enemiesRoot = spawner.transform.Find(EnemySpawner.EnemiesRootName);

            // The rule from the navigation lane: a solid collider alive during a re-bake is baked
            // around unless a NavMeshModifier { ignoreFromBuild, applyToChildren } on the ROOT
            // covers it. Today's enemy prefabs carry no collider, so this first check is true but
            // VACUOUS on its own...
            Assert.IsEmpty(NavMeshRebakeExclusion.FindCollected(enemiesRoot),
                "a re-bake would collect an enemy collider as static geometry");

            // ...so give a melee AND a wraith the body collider NSC-125 will add, on the Visual
            // CHILD, where neither the root's NavMeshAgent nor anything but the root's modifier
            // can cover it. Both kinds, because the agent exemption could mask a melee-only check.
            foreach (EnemyKind kind in new[] { EnemyKind.Melee, EnemyKind.LanternWraith })
            {
                GameObject enemy = InstanceOf(table.Entries.First(e => e.Kind == kind));
                Component modifier = enemy.GetComponent("NavMeshModifier");
                Assert.IsNotNull(modifier, enemy.name + " carries no NavMeshModifier on its root");
                Assert.IsTrue((bool)modifier.GetType().GetProperty("ignoreFromBuild").GetValue(modifier));
                Assert.IsTrue((bool)modifier.GetType().GetProperty("applyToChildren").GetValue(modifier));

                BoxCollider body = enemy.transform.Find("Visual").gameObject.AddComponent<BoxCollider>();
                Assert.IsTrue(NavMeshRebakeExclusion.Excludes(body),
                    enemy.name + ": a collider on its Visual child would be baked around");
            }

            Assert.IsEmpty(NavMeshRebakeExclusion.FindCollected(enemiesRoot),
                "with body colliders present, the root modifiers must still cover every one");

            // CONTROL, failing differently: the same collider with no modifier above it IS collected.
            var control = new GameObject("NoModifierControl");
            control.transform.SetParent(root.transform, false);
            var controlCollider = control.AddComponent<BoxCollider>();
            Assert.IsFalse(NavMeshRebakeExclusion.Excludes(controlCollider),
                "the control is excluded too, so the checks above prove nothing");
            Assert.AreEqual(1, NavMeshRebakeExclusion.FindCollected(control.transform).Count);
        }
    }
}
