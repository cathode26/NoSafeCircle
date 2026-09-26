using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>
    /// The one object in the scene. Instantiates every family's spawner prefab, then builds the
    /// world by running each <see cref="ISpawner"/> in <see cref="SpawnPhase"/> order.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THIS IS THE OBJECT VINCENT ASKED FOR. His words, 2026-09-26: "The scene should just be some
    /// objects that create prefabs." The scene holds one GameManagers prefab instance carrying this
    /// component and nothing else; every wall, prop, door, enemy and pixel of the game is
    /// instantiated here at Play. Nothing is baked, nothing is committed as build output, and the
    /// scene file stops changing - which is the point, because the scene is the one artifact that
    /// cannot be merged.
    /// </para>
    /// <para>
    /// IT DISCOVERS SPAWNERS IN A FOLDER, AND THAT IS THE WHOLE PARALLELISM DECISION. A serialized
    /// array of spawner references - or a list of children on this prefab - would be ONE shared file
    /// that all seven lane owners must edit, which is the single merge hotspot in an otherwise
    /// perfectly partitioned design. With a folder, shipping a lane is shipping ONE prefab nobody
    /// else's branch contains: <c>Resources/Spawners/&lt;Family&gt;Spawner.prefab</c>. Adding a lane
    /// touches zero files anyone else owns. This is the same reasoning that put the 45 prop prefabs
    /// in a folder instead of a registry, applied one level up.
    /// </para>
    /// <para>
    /// TWO PASSES, AND THE SPLIT IS THE DESIGN. Content loading is asynchronous; PLACEMENT is not.
    /// Everything a spawner needs is resident before its phase runs. ENGINEERING_STANDARDS 7.2
    /// forbids blocking the main thread for content, forbids Addressables WaitForCompletion in
    /// WebGL game code, and forbids exposing readiness as a bool that consumers poll - so readiness
    /// is awaited ONCE, here, and no spawner ever asks whether content has arrived. A spawner that
    /// runs has what it needs by construction. Today the load is <c>Resources.LoadAll</c>, which is
    /// synchronous; when Addressables lands, only this class changes and no lane notices.
    /// </para>
    /// <para>
    /// ORDER IS SORTED, NOT INHERITED FROM THE HIERARCHY OR THE FOLDER. <c>Resources.LoadAll</c>
    /// returns an unspecified order and hierarchy order is whatever someone dragged last, so either
    /// would make the build order an accident. Sorting by the declared <see cref="ISpawner.Phase"/>
    /// makes it a property of the phase and nothing else.
    /// </para>
    /// </remarks>
    [DisallowMultipleComponent]
    public sealed class GameBootstrap : MonoBehaviour
    {
        /// <summary>
        /// Every spawner prefab lives here, one per family. A lane ships one file into this folder
        /// and is wired in by existing. The path is relative to any Resources folder.
        /// </summary>
        public const string SpawnerResourceFolder = "Spawners";

        [Tooltip("Build the world on Start. Turn this off for a test that wants to call BuildWorld() "
            + "itself, or for a scene opened for inspection rather than played.")]
        [SerializeField] private bool buildOnStart = true;

        [Tooltip("Log one line per phase with its object count. Cheap, and it is the only place the "
            + "build order is observable at runtime.")]
        [SerializeField] private bool logPhases = true;

        /// <summary>
        /// Objects created by the last <see cref="BuildWorld"/>, or -1 before it has run - which is
        /// deliberately distinguishable from a build that created nothing.
        /// </summary>
        public int SpawnedCount { get; private set; } = -1;

        /// <summary>
        /// True once <see cref="BuildWorld"/> has completed. NOT a readiness flag for consumers to
        /// poll (STANDARDS 7.2 forbids that shape); it exists so a fixture can assert the build ran.
        /// </summary>
        public bool HasBuilt { get; private set; }

        private async void Start()
        {
            if (!buildOnStart)
            {
                return;
            }

            // async void, and this is the ONE place it is allowed: standard 7.2 permits it for a
            // lifecycle entry point that catches and reports its own exceptions, and forbids it
            // everywhere else. An unhandled exception in an async void is lost entirely, so the
            // try/catch is not decoration - it is the whole reason this is permitted.
            try
            {
                await BuildWorldAsync(destroyCancellationToken);
            }
            catch (System.OperationCanceledException)
            {
                // The object was destroyed mid-preload. Not a failure.
            }
            catch (System.Exception error)
            {
                Debug.LogError($"{nameof(GameBootstrap)}: the world failed to build. " + error);
            }
        }

        /// <summary>
        /// The full build: instantiate the spawners, AWAIT every preload, then run the synchronous
        /// placement pass.
        /// </summary>
        /// <remarks>
        /// THE TWO PASSES ARE THE WHOLE DESIGN AND THE PRELOAD HALF WAS MISSING UNTIL AN ADVERSARIAL
        /// REVIEW FOUND IT. Content loading is asynchronous; PLACEMENT is not. Everything a spawner
        /// needs is resident before its phase runs, so <see cref="ISpawner.Spawn"/> can be
        /// synchronous - which is what keeps standard 7.2 satisfiable, because a synchronous Spawn
        /// has no reason to reach for Addressables WaitForCompletion and no way to block the main
        /// thread waiting for content.
        /// </remarks>
        public async Task<int> BuildWorldAsync(CancellationToken cancellationToken)
        {
            InstantiateSpawnerPrefabs();
            await PreloadAllAsync(cancellationToken);
            cancellationToken.ThrowIfCancellationRequested();
            return BuildWorld();
        }

        /// <summary>
        /// Awaits every <see cref="IContentPreloader"/> under this object. They run CONCURRENTLY -
        /// preloading is independent per lane by construction, and serialising seven waits would
        /// make the loading screen as long as their sum instead of their maximum.
        /// </summary>
        public async Task PreloadAllAsync(CancellationToken cancellationToken)
        {
            var preloaders = new List<IContentPreloader>(
                GetComponentsInChildren<IContentPreloader>(true));
            if (preloaders.Count == 0)
            {
                return;
            }

            var pending = new List<Task>(preloaders.Count);
            foreach (IContentPreloader preloader in preloaders)
            {
                pending.Add(preloader.PreloadAsync(cancellationToken));
            }

            await Task.WhenAll(pending);

            if (logPhases)
            {
                Debug.Log($"[{nameof(GameBootstrap)}] preloaded {preloaders.Count} content set(s).");
            }
        }

        /// <summary>
        /// The SYNCHRONOUS placement pass alone: instantiates the spawner prefabs, runs them in
        /// phase order, and returns the total created.
        /// </summary>
        /// <remarks>
        /// THIS DOES NOT PRELOAD. Call <see cref="BuildWorldAsync"/> for the full build. This
        /// overload exists for tests and for a world whose content is already resident - and it is
        /// kept public rather than hidden because the distinction is exactly the thing that was
        /// documented and not implemented once already.
        /// </remarks>
        public int BuildWorld()
        {
            InstantiateSpawnerPrefabs();

            List<ISpawner> spawners = CollectSpawnersInPhaseOrder();
            if (spawners.Count == 0)
            {
                Debug.LogError($"{nameof(GameBootstrap)}: no spawners found. Expected at least one "
                    + $"prefab with an {nameof(ISpawner)} component in a Resources/"
                    + SpawnerResourceFolder + " folder. The world will be empty.");
            }

            int total = 0;
            foreach (ISpawner spawner in spawners)
            {
                int created = spawner.Spawn();
                total += created;

                if (logPhases)
                {
                    Debug.Log($"[{nameof(GameBootstrap)}] {spawner.Phase} "
                        + $"({spawner.GetType().Name}) created {created}.");
                }
            }

            SpawnedCount = total;
            HasBuilt = true;
            return total;
        }

        /// <summary>
        /// Instantiates one child per spawner prefab found in the folder. Prefabs already present as
        /// children are left alone, so a scene or a test may place a spawner by hand and this will
        /// not duplicate it.
        /// </summary>
        /// <remarks>
        /// A SPAWNER PREFAB MUST NOT SPAWN IN Awake. Instantiating an active prefab runs its Awake
        /// immediately, which would place that family before this method has even returned - out of
        /// phase order, and before Rooms exist. PropSpawner's own <c>spawnOnAwake</c> exists for
        /// exactly this and ships false. A lane that self-spawns breaks the order for everyone, so
        /// SceneStubTests asserts the folder's prefabs do not.
        /// </remarks>
        public void InstantiateSpawnerPrefabs()
        {
            GameObject[] prefabs = Resources.LoadAll<GameObject>(SpawnerResourceFolder);
            var alreadyPresent = new HashSet<System.Type>();

            foreach (ISpawner existing in GetComponentsInChildren<ISpawner>(true))
            {
                alreadyPresent.Add(existing.GetType());
            }

            foreach (GameObject prefab in prefabs)
            {
                var template = prefab.GetComponent<ISpawner>();
                if (template == null)
                {
                    // Not an error: the folder is allowed to hold a prefab that is a spawner's
                    // dependency rather than a spawner. Said out loud so a lane owner who dropped a
                    // prefab in and saw nothing happen is not left guessing.
                    Debug.LogWarning($"{nameof(GameBootstrap)}: '{prefab.name}' is in Resources/"
                        + SpawnerResourceFolder + $" but has no {nameof(ISpawner)} component, so it "
                        + "will never run.");
                    continue;
                }

                if (!alreadyPresent.Add(template.GetType()))
                {
                    continue;
                }

                GameObject instance = Instantiate(prefab, transform);
                instance.name = prefab.name;
            }
        }

        /// <summary>
        /// Every spawner under this object, ordered by phase. Exposed so a fixture can assert the
        /// order the world WILL build in without building it, which is the cheap half of the check.
        /// </summary>
        public List<ISpawner> CollectSpawnersInPhaseOrder()
        {
            var found = new List<ISpawner>(GetComponentsInChildren<ISpawner>(true));

            // Insertion sort, deliberately: it is stable, so two spawners sharing a phase keep a
            // predictable relative order, and List.Sort is NOT stable. With at most a dozen
            // spawners the cost is irrelevant and the guarantee is not.
            for (int i = 1; i < found.Count; i++)
            {
                ISpawner current = found[i];
                int j = i - 1;
                while (j >= 0 && found[j].Phase > current.Phase)
                {
                    found[j + 1] = found[j];
                    j--;
                }

                found[j + 1] = current;
            }

            return found;
        }
    }
}
