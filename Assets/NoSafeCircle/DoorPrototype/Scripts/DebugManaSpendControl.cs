using UnityEngine;
using UnityEngine.InputSystem;

namespace NoSafeCircle.DoorPrototype
{
    /// Testing/demo affordance only, not a spell-casting system: lets a developer trigger
    /// mana spend to demonstrate the pool's spend/post-cast-delay/regen behavior standalone,
    /// ahead of the real spells that will consume it.
    public class DebugManaSpendControl : MonoBehaviour
    {
        [SerializeField] private PlayerMana target;
        [SerializeField] private Key spendKey = Key.L;
        [SerializeField] private float spendAmount = 25f;

        private void Awake()
        {
            if (target == null) target = GetComponent<PlayerMana>();
        }

        private void Update()
        {
            var keyboard = Keyboard.current;
            if (keyboard != null && keyboard[spendKey].wasPressedThisFrame)
            {
                TriggerDebugSpend();
            }
        }

        public void TriggerDebugSpend()
        {
            target?.Spend(spendAmount);
        }
    }
}
