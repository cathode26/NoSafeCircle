using UnityEngine;
using UnityEngine.InputSystem;

namespace NoSafeCircle.DoorPrototype
{
    /// Testing/demo affordance only, not a combat system: lets a developer trigger
    /// player damage to demonstrate that damage cancels an in-progress door interaction.
    public class DebugDamageControl : MonoBehaviour
    {
        [SerializeField] private PlayerHealth target;
        [SerializeField] private Key damageKey = Key.K;
        [SerializeField] private float damageAmount = 25f;

        private void Awake()
        {
            if (target == null) target = GetComponent<PlayerHealth>();
        }

        private void Update()
        {
            var keyboard = Keyboard.current;
            if (keyboard != null && keyboard[damageKey].wasPressedThisFrame)
            {
                TriggerDebugDamage();
            }
        }

        public void TriggerDebugDamage()
        {
            target?.TakeDamage(damageAmount);
        }
    }
}
