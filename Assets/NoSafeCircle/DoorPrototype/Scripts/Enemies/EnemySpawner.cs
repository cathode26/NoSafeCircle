using NoSafeCircle.DoorPrototype.Enemies.Pooling;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    /// <summary>
    /// Phase 5: the enemies, instantiated from authored prefabs at the authored spawn table's
    /// points, through two pools, admitted by the encounter controller, wired to the player.
    /// This class is the seam, the validation and the lifetime; <see cref="EnemyEncounter"/> is
    /// the population it creates and disposes.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THIS PREFAB IS WHERE THE REGISTRY COMES TO EXIST. Before this lane, no production code
    /// created an <see cref="ActiveEnemyRegistry"/> or an <see cref="EncounterAdmissionController"/>
    /// - only tests did - so <c>EnemyHealth.activeEnemyRegistry</c> was null in the game and a
    /// defeat unregistered nothing. Both components ride on
    /// <c>Resources/Spawners/EnemySpawner.prefab</c> next to this one, as serialized references.
    /// </para>
    /// <para>
    /// NOTHING HAPPENS IN Awake. GameBootstrap instantiates every spawner prefab first and only
    /// then runs them in phase order; a spawner that started itself would place its family before
    /// Rooms exist. Spawn() runs when called and clears its previous output first, so a second
    /// BuildWorld yields the same count with no doubling.
    /// </para>
    /// </remarks>
    [DisallowMultipleComponent]
    public sealed class EnemySpawner : MonoBehaviour, ISpawner
    {
        /// <summary>The child every instance lives under, as the editor builder named it.</summary>
        public const string EnemiesRootName = "Enemies";

        [SerializeField] private EnemySpawnTable spawnTable;
        [SerializeField] private GameObject meleePrefab;
        [SerializeField] private GameObject wraithPrefab;
        [SerializeField] private ActiveEnemyRegistry registry;
        [SerializeField] private EncounterAdmissionController admission;

        public SpawnPhase Phase => SpawnPhase.Enemies;

        /// <summary>The population of the last Spawn(); null before one, or after a refused one.</summary>
        public EnemyEncounter Encounter { get; private set; }

        public EnemyPrefabPool MeleePool => Encounter?.MeleePool;

        public EnemyPrefabPool WraithPool => Encounter?.WraithPool;

        public ActiveEnemyRegistry Registry => registry;

        public EncounterAdmissionController Admission => admission;

        /// <summary>Enemies admitted by the last Spawn(); -1 before it has run.</summary>
        public int SpawnedCount { get; private set; } = -1;

        /// <summary>Assigns everything from code, for a fixture that does not load the prefab.
        /// Does NOT spawn: Spawn() runs only when the bootstrap calls it.</summary>
        public void Configure(EnemySpawnTable table, GameObject melee, GameObject wraith,
            ActiveEnemyRegistry enemyRegistry, EncounterAdmissionController admissionController)
        {
            spawnTable = table;
            meleePrefab = melee;
            wraithPrefab = wraith;
            registry = enemyRegistry;
            admission = admissionController;
        }

        private void OnDestroy()
        {
            // Scene teardown: the instances may already be gone, so no orderly returns.
            Encounter?.Abandon();
            Encounter = null;
        }

        public int Spawn()
        {
            Release();

            if (!TryValidate(out string problem))
            {
                Debug.LogError($"{nameof(EnemySpawner)}: {problem}. Nothing spawned.");
                SpawnedCount = 0;
                return 0;
            }

            // Once, at spawn time: the one FindFirstObjectByType this lane ever does. Inactive
            // objects are excluded, which is what makes a same-frame rebuild safe: a Player lane
            // that deactivates its old wizard before Destroy cannot be found here.
            PlayerMovement movement = FindFirstObjectByType<PlayerMovement>();
            if (movement == null)
            {
                Debug.LogError($"{nameof(EnemySpawner)}: no active PlayerMovement exists, so the "
                    + "enemies would have no target. Player (phase 4) must run before Enemies "
                    + "(phase 5). Nothing spawned.");
                SpawnedCount = 0;
                return 0;
            }

            PlayerHealth playerHealth = movement.GetComponent<PlayerHealth>();
            if (playerHealth == null)
            {
                Debug.LogWarning($"{nameof(EnemySpawner)}: the player has no PlayerHealth, so the "
                    + "enemies will not re-arm when the player dies.");
            }

            Transform root = new GameObject(EnemiesRootName).transform;
            root.SetParent(transform, false);

            Encounter = new EnemyEncounter(spawnTable, meleePrefab, wraithPrefab, root, registry,
                admission, movement.transform, playerHealth);
            SpawnedCount = Encounter.AdmittedCount;

            Debug.Log($"{nameof(EnemySpawner)}: admitted {SpawnedCount} of {spawnTable.Entries.Count} enemies.");
            return SpawnedCount;
        }

        private bool TryValidate(out string problem)
        {
            if (spawnTable == null) problem = "spawnTable is not assigned";
            else if (meleePrefab == null) problem = "meleePrefab is not assigned";
            else if (wraithPrefab == null) problem = "wraithPrefab is not assigned";
            else if (registry == null) problem = "registry is not assigned";
            else if (admission == null) problem = "admission is not assigned";
            else if (!spawnTable.TryValidate(out string tableProblem))
                problem = $"spawn table '{spawnTable.name}' is invalid: {tableProblem}";
            else problem = null;
            return problem == null;
        }

        /// Clears the previous spawn: the encounter returns and disposes everything it made, the
        /// Enemies root goes, and the registry and admission return to their floor-initial state.
        private void Release()
        {
            Encounter?.Dispose();
            Encounter = null;

            // Deactivate before Destroy: Destroy is deferred to end of frame, and a same-frame
            // rebuild must not find the dying set by type (section 1 rule 1 of the lane spec).
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                GameObject child = transform.GetChild(i).gameObject;
                child.SetActive(false);
                Destroy(child);
            }

            if (registry != null) registry.ResetRegistry();
            if (admission != null) admission.ResetAdmissionState();
        }
    }
}
