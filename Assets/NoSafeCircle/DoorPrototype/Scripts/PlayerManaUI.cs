using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    public class PlayerManaUI : MonoBehaviour
    {
        [SerializeField] private PlayerMana mana;
        [SerializeField] private Image fillImage;

        private void Update()
        {
            if (mana == null || fillImage == null) return;

            fillImage.fillAmount = mana.MaxMana > 0f ? mana.CurrentMana / mana.MaxMana : 0f;
        }
    }
}
