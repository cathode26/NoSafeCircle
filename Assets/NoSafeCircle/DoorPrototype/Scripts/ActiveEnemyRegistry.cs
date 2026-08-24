using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    public class ActiveEnemyRegistry : MonoBehaviour
    {
        public const int MaxActiveEnemies = 15;

        private readonly HashSet<GameObject> activeEnemies = new HashSet<GameObject>();

        public int ActiveCount => activeEnemies.Count;
        public int RemainingCapacity => MaxActiveEnemies - activeEnemies.Count;

        /// Owner-controlled registration entry point for enemy activation. Duplicate
        /// or null registration attempts do not alter the active set.
        public void Register(GameObject enemy)
        {
            if (enemy == null) return;

            activeEnemies.Add(enemy);
        }

        /// Owner-controlled removal entry point for explicit defeat-removal. Unknown
        /// or null unregister attempts do not alter the active set.
        public void Unregister(GameObject enemy)
        {
            if (enemy == null) return;

            activeEnemies.Remove(enemy);
        }

        /// Returns bookkeeping to the floor's initial empty state, for use by
        /// owner-controlled floor-restart orchestration.
        public void ResetRegistry()
        {
            activeEnemies.Clear();
        }
    }
}
