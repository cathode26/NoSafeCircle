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
        public event Action<float> CastDenied;

        private void Awake()
        {
            CurrentMana = maxMana;
            timeSinceLastSpend = postCastRegenDelay;
        }

        /// Restores current mana to full and clears post-cast regen-delay timer
        /// state, for use by owner-controlled floor-restart orchestration.
        public void ResetMana()
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
        /// Raises CastDenied when the refusal is specifically due to insufficient mana,
        /// so a consuming spell/UI can present readable low-mana feedback.
        public bool Spend(float amount)
        {
            if (amount <= 0f) return false;

            if (amount > CurrentMana)
            {
                CastDenied?.Invoke(amount);
                return false;
            }

            CurrentMana -= amount;
            timeSinceLastSpend = 0f;
            ManaSpent?.Invoke(amount);
            return true;
        }
    }
}
