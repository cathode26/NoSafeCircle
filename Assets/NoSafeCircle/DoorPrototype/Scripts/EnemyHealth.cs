using System;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    public class EnemyHealth : MonoBehaviour
    {
        [SerializeField] private float maxHealth = 50f;
        [SerializeField] private ActiveEnemyRegistry activeEnemyRegistry;

        public float MaxHealth => maxHealth;
        public float CurrentHealth { get; private set; }
        public bool IsDefeated { get; private set; }
        public event Action<float> Damaged;
        public event Action Defeated;

        private void Awake()
        {
            CurrentHealth = maxHealth;
        }

        /// Wires the shared registry owner consumed by defeat-removal reporting.
        public void Initialize(ActiveEnemyRegistry registry)
        {
            activeEnemyRegistry = registry;
        }

        /// Owner-controlled damage-intake entry point. Canon-required damage sources
        /// (e.g. Fireball) request damage here rather than writing enemy health directly.
        public void TakeDamage(float amount)
        {
            if (amount <= 0f || IsDefeated) return;

            CurrentHealth = Mathf.Max(0f, CurrentHealth - amount);
            Damaged?.Invoke(amount);

            if (CurrentHealth <= 0f)
            {
                Defeat();
            }
        }

        private void Defeat()
        {
            if (IsDefeated) return;

            IsDefeated = true;
            activeEnemyRegistry?.Unregister(gameObject);
            Defeated?.Invoke();
        }

        /// Restores the floor-initial health/defeat state, for use by owner-controlled
        /// floor-restart orchestration.
        public void ResetHealth()
        {
            CurrentHealth = maxHealth;
            IsDefeated = false;
        }
    }
}
