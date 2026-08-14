using System;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    public class PlayerMana : MonoBehaviour
    {
        [SerializeField] private float maxMana = 100f;
        [SerializeField] private float regenPerSecond = 10f;
        [SerializeField] private float postCastRegenDelay = 2f;

        private float timeSinceLastSpend;

        public float MaxMana => maxMana;
        public float PostCastRegenDelay => postCastRegenDelay;
        public float CurrentMana { get; private set; }
        public event Action<float> ManaSpent;

        private void Awake()
        {
            CurrentMana = maxMana;
            timeSinceLastSpend = postCastRegenDelay;
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// Advances the regen timer by deltaTime. Public so Play Mode tests can drive
        /// it deterministically without waiting on real frames, mirroring DoorInteractable.Tick.
        public void Tick(float deltaTime)
        {
            if (CurrentMana >= maxMana) return;

            timeSinceLastSpend += deltaTime;
            if (timeSinceLastSpend < postCastRegenDelay) return;

            CurrentMana = Mathf.Min(maxMana, CurrentMana + regenPerSecond * deltaTime);
        }

        /// Attempts to spend mana. Returns false and leaves CurrentMana unchanged when
        /// the pool doesn't have enough, so callers (spells) know the cast was refused.
        public bool Spend(float amount)
        {
            if (amount <= 0f || amount > CurrentMana) return false;

            CurrentMana -= amount;
            timeSinceLastSpend = 0f;
            ManaSpent?.Invoke(amount);
            return true;
        }
    }
}
