using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies.Pooling
{
    /// <summary>
    /// ENGINEERING_STANDARDS 9.4 counters for one <see cref="EnemyPrefabPool"/>. The pool writes
    /// them, anyone reads them. In development every fault also logs an error naming the pool and
    /// the slot; in a release build they only count.
    /// </summary>
    /// <remarks>
    /// Named EnemyPoolDiagnostics rather than PoolDiagnostics for the same reason as
    /// <see cref="IEnemyPoolable"/>: the Content lane ships a
    /// <c>NoSafeCircle.DoorPrototype.Content.PoolDiagnostics</c> and the two must never be
    /// ambiguous in a file that imports both namespaces.
    /// </remarks>
    public sealed class EnemyPoolDiagnostics
    {
        /// <summary>An instance returned while it was not checked out.</summary>
        public int DoubleReturn { get; internal set; }

        /// <summary>An object returned that this pool never created.</summary>
        public int ForeignReturn { get; internal set; }

        /// <summary>A slot requested while its instance was already out.</summary>
        public int DoubleCheckout { get; internal set; }

        /// <summary>Instances still checked out (and alive) when the pool was disposed.</summary>
        public int ActiveAtDisposal { get; internal set; }

        /// <summary>
        /// Always 0 for this pool. Capacity is the slot count and a slot is a spawn point, so
        /// there is nowhere to create an extra instance. The counter exists so the report states
        /// the policy rather than leaving 9.4's item silently unaddressed.
        /// </summary>
        public int CapacityExpansion { get; internal set; }

        /// <summary>A checkout refused: unknown slot id, or the pool was already disposed.</summary>
        public int Rejected { get; internal set; }

        /// <summary>An instance destroyed by something other than this pool. DemoRunFlow does
        /// this to a defeated enemy today; the pool re-creates the instance at its slot.</summary>
        public int DestroyedExternally { get; internal set; }

        /// <summary>The most instances ever out at once.</summary>
        public int PeakActive { get; internal set; }

        /// <summary>Instances out right now.</summary>
        public int ActiveNow { get; internal set; }

        /// <summary>True if any fault counter is non-zero. Peak and active-now are not faults.</summary>
        public bool HasFault =>
            DoubleReturn + ForeignReturn + DoubleCheckout + ActiveAtDisposal
            + CapacityExpansion + Rejected + DestroyedExternally > 0;

        /// <summary>The editor and development builds: where faults log as well as count.</summary>
        public static bool IsDevelopment => Application.isEditor || Debug.isDebugBuild;

        public string Report(string poolName) =>
            $"[{poolName}] active {ActiveNow}, peak {PeakActive}, doubleReturn {DoubleReturn}, "
            + $"foreignReturn {ForeignReturn}, doubleCheckout {DoubleCheckout}, rejected {Rejected}, "
            + $"destroyedExternally {DestroyedExternally}, activeAtDisposal {ActiveAtDisposal}, "
            + $"capacityExpansion {CapacityExpansion}";
    }
}
