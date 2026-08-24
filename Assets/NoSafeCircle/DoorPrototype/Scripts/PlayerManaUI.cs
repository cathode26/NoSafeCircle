using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    public class PlayerManaUI : MonoBehaviour
    {
        [SerializeField] private PlayerMana mana;
        [SerializeField] private Image fillImage;
        [SerializeField] private Color normalColor = Color.white;
        [SerializeField] private Color deniedColor = Color.red;
        [SerializeField] private float deniedFlashDuration = 0.25f;

        private float deniedFlashTimeRemaining;

        private void OnEnable()
        {
            if (mana != null) mana.CastDenied += HandleCastDenied;
            if (fillImage != null) normalColor = fillImage.color;
        }

        private void OnDisable()
        {
            if (mana != null) mana.CastDenied -= HandleCastDenied;
        }

        private void Update()
        {
            if (mana == null || fillImage == null) return;

            fillImage.fillAmount = mana.MaxMana > 0f ? mana.CurrentMana / mana.MaxMana : 0f;

            if (deniedFlashTimeRemaining > 0f)
            {
                deniedFlashTimeRemaining -= Time.deltaTime;
                fillImage.color = deniedFlashTimeRemaining > 0f ? deniedColor : normalColor;
            }
        }

        /// Presents readable low-mana feedback on the existing mana indicator
        /// when a cast is denied due to insufficient mana.
        private void HandleCastDenied(float requestedAmount)
        {
            deniedFlashTimeRemaining = deniedFlashDuration;
        }
    }
}
