using System;
using System.Collections.Generic;
using System.Linq;
using NoSafeCircle.DoorPrototype.Content;
using UnityEngine;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Enemies.Pooling
{
    /// <summary>
    /// A fixed-capacity pool of prefab instances, one per authored spawn slot. ENGINEERING_STANDARDS
    /// 9.2 asks every pool to define nine behaviours; each is named here next to where it lives:
    /// </summary>
    /// <remarks>
    /// <code>
    ///   creation method     Create(): Instantiate(prefab, slot pose, activeRoot), name it, SetActive(false)
    ///   initial capacity    slotPoses.Count - every slot is created up front in the constructor
    ///   maximum capacity    slotPoses.Count - never grows; Diagnostics.CapacityExpansion can only read 0
    ///   overflow policy     REJECT: an unknown id or a slot already out returns null, counts, logs in dev
    ///   checkout reset      IEnemyPoolable.OnCheckout(pose) on the still-INACTIVE instance
    ///   return reset        IEnemyPoolable.OnReturn() on the still-ACTIVE instance, then SetActive(false);
    ///                       with recycleOnReturn=false the instance is then destroyed and re-created
    ///                       at its slot on the next checkout
    ///   destruction         Dispose(): every instance deactivated and destroyed, THEN the lease released
    ///   owner/lifetime      whoever constructs it disposes it (EnemySpawner). A plain class: no scene
    ///                       object, no Awake, nothing to find - standards 5.5 keeps creation and
    ///                       lifetime in the composition root
    ///   diagnostics         EnemyPoolDiagnostics (9.4); faults log in development, count in release
    /// </code>
    /// <para>
    /// WHY A SLOT IS A SPAWN POINT. Every instance is created AT its slot's pose, so the enemy
    /// components that record their floor-initial state in Awake (EnemyPursuitMovement's
    /// spawnPosition, EnemyTargetKnowledge's leash anchor) record the right place once and for
    /// all. A pool that created instances at the origin and moved them afterwards would give every
    /// enemy a leash anchored at (0,0,0). It is also why capacity never expands: a tenth melee has
    /// no pose to be created at.
    /// </para>
    /// <para>
    /// THE LEASE OUTLIVES EVERY INSTANCE (standards 8.5 and 9.5). Dispose destroys the instances
    /// first and releases the prefab lease last, and the pool never loads anything itself. Today
    /// the lease is <c>AssetLease.Unmanaged</c> over a Resources prefab; when the bootstrap loads
    /// through Addressables it hands in a real lease and nothing in this class changes.
    /// </para>
    /// <para>
    /// HANDED OUT INACTIVE. Checkout returns an inactive, positioned, reset instance. Activation
    /// belongs to EncounterAdmissionController, which is how the 15-enemy cap and its FIFO queue
    /// keep working: the spawner submits inactive instances and admission activates what fits.
    /// </para>
    /// </remarks>
    public sealed class EnemyPrefabPool : IDisposable
    {
        private sealed class Slot
        {
            public string Id;
            public Pose Pose;
            public GameObject Instance;
            public bool IsOut;

            // True after THIS pool destroyed the instance (a non-recycling return, or a return of
            // an already-dead object), so the next checkout re-creates it without counting a
            // destruction nobody else did.
            public bool Vacated;
        }

        private readonly AssetLease<GameObject> prefab;
        private readonly Transform activeRoot;
        private readonly List<Slot> slots = new List<Slot>();
        private readonly Dictionary<string, Slot> slotsById = new Dictionary<string, Slot>();
        private readonly Dictionary<GameObject, Slot> slotsByInstance = new Dictionary<GameObject, Slot>();

        public EnemyPrefabPool(
            string instanceName,
            AssetLease<GameObject> prefab,
            IReadOnlyList<(string id, Pose pose)> slotPoses,
            Transform activeRoot,
            bool recycleOnReturn)
        {
            if (prefab == null || prefab.Asset == null) throw new ArgumentException("A pool needs a leased prefab with a live asset.", nameof(prefab));
            if (slotPoses == null) throw new ArgumentNullException(nameof(slotPoses));

            Name = instanceName;
            this.prefab = prefab;
            this.activeRoot = activeRoot;
            RecycleOnReturn = recycleOnReturn;

            foreach ((string id, Pose pose) in slotPoses)
            {
                if (string.IsNullOrEmpty(id) || slotsById.ContainsKey(id))
                    throw new ArgumentException($"Pool '{instanceName}': slot id '{id}' is empty or repeated.", nameof(slotPoses));

                var slot = new Slot { Id = id, Pose = pose };
                slots.Add(slot);
                slotsById.Add(id, slot);
                Create(slot);
            }
        }

        /// <summary>The name every instance carries, e.g. "MeleeEnemy".</summary>
        public string Name { get; }

        /// <summary>False means a returned instance is destroyed and re-created on checkout.</summary>
        public bool RecycleOnReturn { get; }

        /// <summary>Initial capacity, maximum capacity, and the number of spawn points. One value.</summary>
        public int Capacity => slots.Count;

        public bool IsDisposed { get; private set; }

        public EnemyPoolDiagnostics Diagnostics { get; } = new EnemyPoolDiagnostics();

        /// <summary>Slots whose instance exists right now, out or parked. Zero once disposed, and
        /// zero BEFORE the lease is released - which is what a lease callback can assert.</summary>
        public int LiveInstanceCount => slots.Count(slot => slot.Instance != null);

        /// <summary>True if this pool created the object (alive or destroyed while out).</summary>
        public bool Owns(GameObject instance) => !(instance is null) && slotsByInstance.ContainsKey(instance);

        /// <summary>The live instance in a slot, out or parked; false for an unknown id or a
        /// slot with no instance right now.</summary>
        public bool TryGetInstance(string id, out GameObject instance)
        {
            instance = id != null && slotsById.TryGetValue(id, out Slot slot) ? slot.Instance : null;
            return instance != null;
        }

        /// <summary>Hands out the slot's instance, inactive, positioned at the slot pose and reset.
        /// Null (counted, logged in development) for an unknown id, a slot already out, or a
        /// disposed pool. Never instantiates past capacity.</summary>
        public GameObject Checkout(string id)
        {
            if (IsDisposed || id == null || !slotsById.TryGetValue(id, out Slot slot))
            {
                Diagnostics.Rejected++;
                Fault($"checkout of '{id}' rejected" + (IsDisposed ? " (pool is disposed)" : " (no such slot)"));
                return null;
            }

            if (slot.IsOut)
            {
                Diagnostics.DoubleCheckout++;
                Fault($"'{id}' is already checked out");
                return null;
            }

            if (slot.Instance == null)
            {
                // NOTE: Destroy is deferred to end of frame, so an instance destroyed by someone
                // else THIS frame still reads non-null here and would be handed out dying. The
                // spawner only checks out at populate time, never mid-frame after a defeat.
                if (!slot.Vacated)
                {
                    Diagnostics.DestroyedExternally++;
                    Fault($"'{id}' was destroyed by something other than this pool; re-creating it at its slot");
                }

                Create(slot);
            }

            slot.Instance.GetComponent<IEnemyPoolable>()?.OnCheckout(slot.Pose);
            slot.IsOut = true;
            Diagnostics.ActiveNow++;
            Diagnostics.PeakActive = Mathf.Max(Diagnostics.PeakActive, Diagnostics.ActiveNow);
            return slot.Instance;
        }

        /// <summary>Takes an instance back: reset, deactivated, and destroyed if not recycling.
        /// False (counted, logged in development) for a foreign object or a double return.</summary>
        public bool Return(GameObject instance)
        {
            // `is null` is the C# null; `== null` further down is Unity's fake null for a
            // destroyed object, which still hashes to its slot and must be treated differently.
            if (instance is null || !slotsByInstance.TryGetValue(instance, out Slot slot))
            {
                Diagnostics.ForeignReturn++;
                Fault($"'{(instance is null ? "null" : instance.name)}' was not created by this pool; ignored");
                return false;
            }

            if (!slot.IsOut)
            {
                Diagnostics.DoubleReturn++;
                Fault($"'{slot.Id}' returned twice; ignored");
                return false;
            }

            if (instance == null)
            {
                Diagnostics.DestroyedExternally++;
                Fault($"'{slot.Id}' was destroyed while checked out; its slot is re-created on the next checkout");
                Forget(slot);
            }
            else
            {
                instance.GetComponent<IEnemyPoolable>()?.OnReturn();
                instance.SetActive(false);
                if (!RecycleOnReturn)
                {
                    Object.Destroy(instance);
                    Forget(slot);
                }
            }

            slot.IsOut = false;
            Diagnostics.ActiveNow--;
            return true;
        }

        /// <summary>Returns every checked-out instance. The restart path.</summary>
        public void ReturnAll()
        {
            foreach (Slot slot in slots)
            {
                if (slot.IsOut) Return(slot.Instance);
            }
        }

        /// <summary>Destroys every instance, records how many were still out, logs the report in
        /// development, and releases the prefab lease LAST. Safe to call twice.</summary>
        public void Dispose()
        {
            if (IsDisposed) return;
            IsDisposed = true;

            foreach (Slot slot in slots)
            {
                if (slot.Instance != null)
                {
                    if (slot.IsOut) Diagnostics.ActiveAtDisposal++;
                    slot.Instance.SetActive(false);
                    Object.Destroy(slot.Instance);
                }

                slot.IsOut = false;
                Forget(slot);
            }

            Diagnostics.ActiveNow = 0;
            if (EnemyPoolDiagnostics.IsDevelopment)
            {
                Debug.Log($"{nameof(EnemyPrefabPool)} disposed: {Diagnostics.Report(Name)}.");
            }

            // LAST. Standards 8.5/9.5: a pool releases its prefab lease only after all instances
            // are gone. LiveInstanceCount is 0 by the time this runs.
            prefab.Dispose();
        }

        private void Create(Slot slot)
        {
            // The position overload, so Awake runs at the slot's pose (see the class remarks).
            slot.Instance = Object.Instantiate(prefab.Asset, slot.Pose.position, slot.Pose.rotation, activeRoot);
            slot.Instance.name = Name;
            slot.Instance.SetActive(false);
            slot.Vacated = false;
            slotsByInstance[slot.Instance] = slot;
        }

        private void Forget(Slot slot)
        {
            if (!(slot.Instance is null)) slotsByInstance.Remove(slot.Instance);
            slot.Instance = null;
            slot.Vacated = true;
        }

        private void Fault(string what)
        {
            if (EnemyPoolDiagnostics.IsDevelopment) Debug.LogError($"{nameof(EnemyPrefabPool)} '{Name}': {what}.");
        }
    }
}
