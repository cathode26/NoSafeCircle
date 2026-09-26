using System;
using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.Content;
using NoSafeCircle.DoorPrototype.Enemies.Pooling;
using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    /// <summary>
    /// One spawn's worth of enemies: the two pools, the checkout-wire-admit sequence, the return
    /// of each defeated enemy to its pool, and the re-arm when the player dies. A plain class
    /// created and disposed by <see cref="EnemySpawner"/> (standards 5.5 keeps creation and
    /// lifetime in the composition root); no scene object, no Awake, nothing to find.
    /// </summary>
    /// <remarks>
    /// <para>
    /// IT NEVER ACTIVATES AN ENEMY. Instances come out of the pool INACTIVE and go to
    /// <see cref="EncounterAdmissionController"/> as one batch, which activates and registers each
    /// in request order while the registry has capacity (NSC-011). Nine against a cap of 15 all
    /// get in; a longer table leaves the rest inactive and pending by that design.
    /// </para>
    /// <para>
    /// TWO POOLS, TWO POLICIES. Melee instances recycle: every component has a public reset. The
    /// wraith destroys on return, because <c>EnemyLanternWispCaster</c> keeps its wisps as
    /// non-children with no public clear (only its OnDestroy removes them) and has no reset for
    /// its mana or cooldown. A <c>ClearProjectiles()</c> seam there flips <c>recycleOnReturn</c>
    /// to true with no other change here.
    /// </para>
    /// </remarks>
    public sealed class EnemyEncounter : IDisposable
    {
        private readonly EnemySpawnTable table;
        private readonly ActiveEnemyRegistry registry;
        private readonly EncounterAdmissionController admission;
        private readonly Transform player;
        private readonly PlayerHealth playerHealth;

        // The Defeated subscriptions this class owns; exactly the instances still out (2.3).
        private readonly Dictionary<EnemyHealth, Action> defeatedHandlers =
            new Dictionary<EnemyHealth, Action>();

        private bool released;

        public EnemyEncounter(EnemySpawnTable table, GameObject meleePrefab, GameObject wraithPrefab,
            Transform root, ActiveEnemyRegistry registry, EncounterAdmissionController admission,
            Transform player, PlayerHealth playerHealth)
        {
            this.table = table;
            this.registry = registry;
            this.admission = admission;
            this.player = player;
            this.playerHealth = playerHealth;

            // Unmanaged leases today (Resources). When the bootstrap preloads through Addressables
            // it hands real leases in; the pools never load anything themselves.
            MeleePool = new EnemyPrefabPool("MeleeEnemy",
                AssetLease<GameObject>.Unmanaged(meleePrefab, "Enemies/MeleeEnemy"),
                SlotsOf(EnemyKind.Melee), root, recycleOnReturn: true);
            WraithPool = new EnemyPrefabPool("LanternWraith",
                AssetLease<GameObject>.Unmanaged(wraithPrefab, "Enemies/LanternWraith"),
                SlotsOf(EnemyKind.LanternWraith), root, recycleOnReturn: false);

            admission.Initialize(registry);
            AdmittedCount = Populate();

            // The restart re-arms the enemies without touching FloorRunRestartController.
            if (playerHealth != null) playerHealth.Died += HandlePlayerDied;
        }

        public EnemyPrefabPool MeleePool { get; }

        public EnemyPrefabPool WraithPool { get; }

        /// <summary>What admission activated when this encounter was created.</summary>
        public int AdmittedCount { get; }

        /// <summary>Orderly end: every instance returned and reset, then both pools disposed.</summary>
        public void Dispose() => Release(returnFirst: true);

        /// <summary>Scene-teardown end: the instances may already be destroyed, so nothing is
        /// returned (each would count as an external destruction); the pools are disposed.</summary>
        public void Abandon() => Release(returnFirst: false);

        private List<(string id, Pose pose)> SlotsOf(EnemyKind kind)
        {
            var slots = new List<(string id, Pose pose)>();
            foreach (EnemySpawnEntry entry in table.Entries)
            {
                if (entry.Kind == kind) slots.Add((entry.Id, new Pose(entry.Position, Quaternion.identity)));
            }

            return slots;
        }

        /// Checks every table entry out of its pool, wires it to the player and the registry,
        /// submits the batch to admission, then warps the admitted agents. Returns what admission
        /// activated.
        private int Populate()
        {
            var batch = new List<GameObject>();
            var placed = new List<(GameObject instance, EnemySpawnEntry entry)>();

            foreach (EnemySpawnEntry entry in table.Entries)
            {
                EnemyPrefabPool pool = PoolFor(entry.Kind);
                GameObject instance = pool?.Checkout(entry.Id);
                if (instance == null) continue; // the pool already said why

                EnemyHealth health = instance.GetComponent<EnemyHealth>();
                if (health == null)
                {
                    Debug.LogError($"{nameof(EnemyEncounter)}: '{entry.Id}' has no EnemyHealth, so it "
                        + "can neither register nor be defeated. Returned to its pool.");
                    pool.Return(instance);
                    continue;
                }

                instance.GetComponent<EnemyTargetKnowledge>()?.Initialize(player);
                instance.GetComponent<EnemyLanternWispCaster>()?.Initialize(player);
                health.Initialize(registry);

                Action onDefeated = () => Return(instance);
                defeatedHandlers[health] = onDefeated;
                health.Defeated += onDefeated;

                batch.Add(instance);
                placed.Add((instance, entry));
            }

            int admitted = admission.RequestAdmission(batch);

            foreach ((GameObject instance, EnemySpawnEntry entry) in placed)
            {
                NavMeshAgent agent = instance.GetComponent<NavMeshAgent>();
                if (agent == null || !instance.activeInHierarchy) continue;

                // Warp needs an enabled agent, hence after admission. AC-006 pins every point to
                // sample onto the navmesh within 0.1; an agent that does not land on it says so.
                if (!agent.Warp(entry.Position) || !agent.isOnNavMesh)
                {
                    Debug.LogError($"{nameof(EnemyEncounter)}: '{entry.Id}' at {entry.Position} is not "
                        + "on the navmesh (AC-006). Navigation must bake before Enemies, and the "
                        + "point must lie on walkable floor.");
                }
            }

            return admitted;
        }

        private void HandlePlayerDied()
        {
            ReturnAll();
            registry.ResetRegistry();
            admission.ResetAdmissionState();
            admission.Initialize(registry);
            Populate();
        }

        private void Return(GameObject instance)
        {
            EnemyHealth health = instance != null ? instance.GetComponent<EnemyHealth>() : null;
            if (health != null && defeatedHandlers.TryGetValue(health, out Action handler))
            {
                health.Defeated -= handler;
                defeatedHandlers.Remove(health);
            }

            registry.Unregister(instance); // a no-op after a defeat, which already unregistered
            PoolFor(instance).Return(instance);
        }

        private void ReturnAll()
        {
            // The handler table is exactly the set of instances still out; Return prunes it.
            var outstanding = new List<EnemyHealth>(defeatedHandlers.Keys);
            foreach (EnemyHealth health in outstanding)
            {
                if (health != null) Return(health.gameObject);
                else defeatedHandlers.Remove(health);
            }

            MeleePool.ReturnAll();
            WraithPool.ReturnAll();
        }

        private EnemyPrefabPool PoolFor(EnemyKind kind)
        {
            switch (kind)
            {
                case EnemyKind.Melee: return MeleePool;
                case EnemyKind.LanternWraith: return WraithPool;
                default:
                    Debug.LogError($"{nameof(EnemyEncounter)}: no pool for enemy kind '{kind}'.");
                    return null;
            }
        }

        private EnemyPrefabPool PoolFor(GameObject instance) =>
            WraithPool.Owns(instance) ? WraithPool : MeleePool;

        private void Release(bool returnFirst)
        {
            if (released) return;
            released = true;

            if (playerHealth != null) playerHealth.Died -= HandlePlayerDied;
            if (returnFirst) ReturnAll();

            foreach (KeyValuePair<EnemyHealth, Action> pair in defeatedHandlers)
            {
                if (pair.Key != null) pair.Key.Defeated -= pair.Value;
            }

            defeatedHandlers.Clear();

            // Each pool destroys its instances, counts what was still out, then releases its lease.
            MeleePool.Dispose();
            WraithPool.Dispose();
        }
    }
}
