using System.Collections;
using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.World;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    /// <summary>
    /// Pressing Play builds the world from prefabs, with nothing baked.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THIS IS THE TEST THAT MATTERS, because it is the only one that exercises the claim the whole
    /// architecture rests on: an empty scene plus one manager object produces a populated world at
    /// runtime. Everything else - the prefabs importing, the scene being a stub, the map parsing -
    /// is a precondition for this and proves nothing on its own.
    /// </para>
    /// <para>
    /// IT BUILDS THE HIERARCHY IN CODE RATHER THAN LOADING RuntimeWorld.unity. Loading the committed
    /// scene would test the scene file; building it here tests the MECHANISM, and the two fail for
    /// different reasons. SceneStubTests already opens the committed scene and asserts it holds a
    /// connected GameManagers prefab instance carrying this component, so between the two fixtures
    /// both halves are covered without either one depending on the other's subject.
    /// </para>
    /// </remarks>
    public sealed class GameBootstrapPlayModeTests
    {
        private GameObject managers;

        [TearDown]
        public void TearDown()
        {
            if (managers != null)
            {
                Object.Destroy(managers);
                managers = null;
            }
        }

        private GameBootstrap CreateBootstrap()
        {
            managers = new GameObject("GameManagersUnderTest");
            GameBootstrap bootstrap = managers.AddComponent<GameBootstrap>();
            return bootstrap;
        }

        [UnityTest]
        public IEnumerator BuildWorldInstantiatesTheSpawnerPrefabsFromTheFolder()
        {
            // THE FOLDER IS THE REGISTRY. Nothing is dragged in and nothing is serialized: the
            // bootstrap finds every spawner prefab by looking, which is what lets a lane ship one
            // file that no other branch contains.
            GameBootstrap bootstrap = CreateBootstrap();
            Assert.IsEmpty(bootstrap.CollectSpawnersInPhaseOrder(),
                "A fresh GameManagers should carry no spawners until it instantiates them.");

            bootstrap.InstantiateSpawnerPrefabs();
            yield return null;

            List<ISpawner> spawners = bootstrap.CollectSpawnersInPhaseOrder();
            Assert.IsNotEmpty(spawners,
                "GameBootstrap instantiated no spawners. Resources/"
                + GameBootstrap.SpawnerResourceFolder + " is empty or its prefabs carry no ISpawner.");

            bool foundProps = false;
            foreach (ISpawner spawner in spawners)
            {
                if (spawner.Phase == SpawnPhase.Props)
                {
                    foundProps = true;
                }
            }

            Assert.IsTrue(foundProps,
                "No spawner declared SpawnPhase.Props, so the 45 authored prop prefabs would never "
                + "be placed.");
        }

        [UnityTest]
        public IEnumerator InstantiatingTwiceDoesNotDuplicateASpawner()
        {
            // A DUPLICATE SPAWNER WOULD DOUBLE THE WORLD SILENTLY, and it would look like a
            // placement bug rather than a lifecycle bug - the same failure the five editor dressing
            // builders had, where every re-bake appended instead of replacing.
            GameBootstrap bootstrap = CreateBootstrap();

            bootstrap.InstantiateSpawnerPrefabs();
            yield return null;
            int afterFirst = bootstrap.CollectSpawnersInPhaseOrder().Count;

            bootstrap.InstantiateSpawnerPrefabs();
            yield return null;
            int afterSecond = bootstrap.CollectSpawnersInPhaseOrder().Count;

            Assert.AreEqual(afterFirst, afterSecond,
                "A second InstantiateSpawnerPrefabs added " + (afterSecond - afterFirst)
                + " more spawner(s). Every family would then be placed twice.");
        }

        [UnityTest]
        public IEnumerator SpawnersRunInPhaseOrderRegardlessOfHierarchyOrder()
        {
            // THE ORDER IS THE CONTRACT BETWEEN SEVEN LANES, so it must not be an accident of which
            // component was added first. Two probes are added in DELIBERATELY REVERSED phase order
            // and the bootstrap must still run them low phase first.
            GameBootstrap bootstrap = CreateBootstrap();

            var late = managers.AddComponent<PhaseProbe>();
            late.Configure(SpawnPhase.Hud);
            var early = managers.AddComponent<PhaseProbe>();
            early.Configure(SpawnPhase.Rooms);

            yield return null;

            List<ISpawner> ordered = bootstrap.CollectSpawnersInPhaseOrder();
            var phases = new List<SpawnPhase>();
            foreach (ISpawner spawner in ordered)
            {
                phases.Add(spawner.Phase);
            }

            for (int i = 1; i < phases.Count; i++)
            {
                Assert.LessOrEqual((int)phases[i - 1], (int)phases[i],
                    "Spawner " + i + " (" + phases[i] + ") runs after " + phases[i - 1]
                    + ", which is out of phase order. Built order was: "
                    + string.Join(", ", phases));
            }

            Assert.AreEqual(SpawnPhase.Rooms, phases[0],
                "Rooms must run first even though its component was added last.");
        }

        [UnityTest]
        public IEnumerator BuildWorldReportsWhatItCreatedAndIsSafeToRunAgain()
        {
            GameBootstrap bootstrap = CreateBootstrap();
            Assert.AreEqual(-1, bootstrap.SpawnedCount,
                "SpawnedCount before a build must be -1, which is distinguishable from a build that "
                + "created nothing.");
            Assert.IsFalse(bootstrap.HasBuilt);

            int first = bootstrap.BuildWorld();
            yield return null;

            Assert.IsTrue(bootstrap.HasBuilt, "BuildWorld did not record that it ran.");
            Assert.AreEqual(first, bootstrap.SpawnedCount,
                "BuildWorld returned " + first + " but recorded " + bootstrap.SpawnedCount + ".");
            Assert.Greater(first, 0,
                "BuildWorld created nothing. With the authored prop catalogs present this should "
                + "place the Art Director's dressing.");

            int second = bootstrap.BuildWorld();
            yield return null;

            // EQUAL, NOT DOUBLED. Each spawner clears its own previous output, so a rebuild is
            // idempotent in COUNT even though every object is a new instance.
            Assert.AreEqual(first, second,
                "A second BuildWorld produced " + second + " objects against " + first
                + " the first time. A spawner is appending instead of replacing.");
        }

        /// <summary>A spawner that creates nothing and only declares a phase, so the ordering test
        /// measures ordering and not placement.</summary>
        private sealed class PhaseProbe : MonoBehaviour, ISpawner
        {
            private SpawnPhase phase;

            public void Configure(SpawnPhase value) => phase = value;

            public SpawnPhase Phase => phase;

            public int Spawn() => 0;
        }
    }
}
