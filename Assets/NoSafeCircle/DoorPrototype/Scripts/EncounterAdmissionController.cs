using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    public class EncounterAdmissionController : MonoBehaviour
    {
        public sealed class AdmissionBatch
        {
            private readonly List<GameObject> requestedEnemies;
            private readonly List<GameObject> pendingEnemies;
            private readonly List<GameObject> admittedEnemies = new List<GameObject>();

            internal AdmissionBatch(int requestOrder, List<GameObject> enemies)
            {
                RequestOrder = requestOrder;
                requestedEnemies = new List<GameObject>(enemies);
                pendingEnemies = new List<GameObject>(enemies);
            }

            public int RequestOrder { get; }
            public int RequestedEnemyCount => requestedEnemies.Count;
            public int PendingEnemyCount => pendingEnemies.Count;
            public int AdmittedEnemyCount => admittedEnemies.Count;
            public IReadOnlyList<GameObject> RequestedEnemies => requestedEnemies;
            public IReadOnlyList<GameObject> PendingEnemies => pendingEnemies;
            public IReadOnlyList<GameObject> AdmittedEnemies => admittedEnemies;

            internal bool HasPendingEnemies => pendingEnemies.Count > 0;
            internal bool HasAdmittedEnemies => admittedEnemies.Count > 0;

            internal GameObject PeekPendingEnemy()
            {
                return pendingEnemies[0];
            }

            internal void RemoveInvalidPendingEnemy()
            {
                pendingEnemies.RemoveAt(0);
            }

            internal void AdmitNextEnemy()
            {
                var enemy = pendingEnemies[0];
                pendingEnemies.RemoveAt(0);
                admittedEnemies.Add(enemy);
            }
        }

        [SerializeField] private ActiveEnemyRegistry activeEnemyRegistry;

        private readonly List<AdmissionBatch> admissionBatches = new List<AdmissionBatch>();
        private readonly Queue<AdmissionBatch> pendingBatches = new Queue<AdmissionBatch>();
        private readonly List<AdmissionBatch> admittedBatches = new List<AdmissionBatch>();
        private readonly HashSet<GameObject> requestedEnemies = new HashSet<GameObject>();
        private int pendingEnemyCount;
        private int admittedEnemyCount;

        public ActiveEnemyRegistry Registry => activeEnemyRegistry;
        public int RequestedBatchCount => admissionBatches.Count;
        public int PendingBatchCount => pendingBatches.Count;
        public int AdmittedBatchCount => admittedBatches.Count;
        public int PendingEnemyCount => pendingEnemyCount;
        public int AdmittedEnemyCount => admittedEnemyCount;

        // Compatibility aliases for consumers interested in aggregate enemy counts.
        public int PendingCount => PendingEnemyCount;
        public int AdmittedCount => AdmittedEnemyCount;

        public IReadOnlyList<AdmissionBatch> AdmissionBatches => admissionBatches;
        public IEnumerable<AdmissionBatch> PendingBatches => pendingBatches;
        public IReadOnlyList<AdmissionBatch> AdmittedBatches => admittedBatches;

        /// Wires the shared registry owner consumed by encounter-admission policy.
        public void Initialize(ActiveEnemyRegistry registry)
        {
            activeEnemyRegistry = registry;
        }

        /// Records one distinct encounter request and immediately attempts to admit it
        /// behind all earlier pending requests. Returns the number admitted by this call.
        public int RequestAdmission(IEnumerable<GameObject> enemies)
        {
            if (enemies == null)
            {
                return 0;
            }

            var batchEnemies = new List<GameObject>();
            foreach (var enemy in enemies)
            {
                if (enemy == null || !requestedEnemies.Add(enemy))
                {
                    continue;
                }

                batchEnemies.Add(enemy);
            }

            var batch = new AdmissionBatch(admissionBatches.Count, batchEnemies);
            admissionBatches.Add(batch);

            if (batch.HasPendingEnemies)
            {
                pendingBatches.Enqueue(batch);
                pendingEnemyCount += batch.PendingEnemyCount;
            }

            return ProcessPendingAdmissions();
        }

        /// Reprocesses delayed requests in original request order. A partially admitted
        /// batch remains first in line until it is complete, so later encounters cannot
        /// bypass it when registry capacity becomes available.
        public int ProcessPendingAdmissions()
        {
            if (activeEnemyRegistry == null)
            {
                return 0;
            }

            var newlyAdmittedCount = 0;

            while (pendingBatches.Count > 0)
            {
                var batch = pendingBatches.Peek();

                while (batch.HasPendingEnemies)
                {
                    var enemy = batch.PeekPendingEnemy();
                    if (enemy == null)
                    {
                        batch.RemoveInvalidPendingEnemy();
                        pendingEnemyCount--;
                        continue;
                    }

                    // Both values come from the registry owner. This controller never
                    // maintains or infers a duplicate floor-wide active-enemy count.
                    var activeCount = activeEnemyRegistry.ActiveCount;
                    var remainingCapacity = activeEnemyRegistry.RemainingCapacity;
                    if (activeCount >= ActiveEnemyRegistry.MaxActiveEnemies || remainingCapacity <= 0)
                    {
                        return newlyAdmittedCount;
                    }

                    var isFirstAdmissionForBatch = !batch.HasAdmittedEnemies;
                    enemy.SetActive(true);
                    activeEnemyRegistry.Register(enemy);
                    batch.AdmitNextEnemy();

                    pendingEnemyCount--;
                    admittedEnemyCount++;
                    newlyAdmittedCount++;

                    if (isFirstAdmissionForBatch)
                    {
                        admittedBatches.Add(batch);
                    }
                }

                pendingBatches.Dequeue();
            }

            return newlyAdmittedCount;
        }

        /// Clears encounter-admission-owned history and queues for a fresh floor run.
        /// Enemy active state and registry membership belong to their separate owners
        /// and are deliberately left untouched for coordinated restart orchestration.
        public void ResetAdmissionState()
        {
            admissionBatches.Clear();
            pendingBatches.Clear();
            admittedBatches.Clear();
            requestedEnemies.Clear();
            pendingEnemyCount = 0;
            admittedEnemyCount = 0;
        }
    }
}
