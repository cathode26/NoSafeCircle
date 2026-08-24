using System;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    public class PlayerHealth : MonoBehaviour
    {
        [SerializeField] private float maxHealth = 100f;

        public float MaxHealth => maxHealth;
        public float CurrentHealth { get; private set; }
        public event Action<float> Damaged;
        public event Action Died;

        private void Awake()
        {
            CurrentHealth = maxHealth;
        }

        public void TakeDamage(float amount)
        {
            if (amount <= 0f) return;

            var previousHealth = CurrentHealth;
            CurrentHealth = Mathf.Max(0f, CurrentHealth - amount);
            Damaged?.Invoke(amount);

            if (CurrentHealth <= 0f && previousHealth > 0f)
            {
                Died?.Invoke();
            }
        }

        /// Owner-controlled restore/heal entry point, clamped to MaxHealth. Requested by
        /// door-lock recovery rather than other systems writing CurrentHealth directly.
        public void Restore(float amount)
        {
            if (amount <= 0f) return;

            CurrentHealth = Mathf.Min(maxHealth, CurrentHealth + amount);
        }

        /// Restores the floor-initial health state, for use by owner-controlled
        /// floor-restart orchestration.
        public void ResetHealth()
        {
            CurrentHealth = maxHealth;
        }
    }
}
