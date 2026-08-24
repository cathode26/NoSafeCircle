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
        private Image flashTargetImage;

        private void OnEnable()
        {
            if (mana != null) mana.CastDenied += HandleCastDenied;

            flashTargetImage = ResolveFlashTargetImage();
            if (flashTargetImage != null) normalColor = flashTargetImage.color;
        }

        private void OnDisable()
        {
            if (mana != null) mana.CastDenied -= HandleCastDenied;
        }

        private void Update()
        {
            if (mana == null || fillImage == null) return;

            fillImage.fillAmount = mana.MaxMana > 0f ? mana.CurrentMana / mana.MaxMana : 0f;

            if (deniedFlashTimeRemaining > 0f && flashTargetImage != null)
            {
                deniedFlashTimeRemaining -= Time.deltaTime;
                flashTargetImage.color = deniedFlashTimeRemaining > 0f ? deniedColor : normalColor;
            }
        }

        /// A fully-drained fill Image has no rendered fill area, so tinting it is
        /// invisible exactly when denied-cast feedback matters most. Flash the fill's
        /// parent frame/background Image instead when one exists, since that frame
        /// renders regardless of fillAmount; fall back to the fill Image itself
        /// otherwise so the feedback still shows without requiring scene rewiring.
        private Image ResolveFlashTargetImage()
        {
            if (fillImage == null) return null;

            var parentTransform = fillImage.transform.parent;
            if (parentTransform != null)
            {
                var backgroundImage = parentTransform.GetComponent<Image>();
                if (backgroundImage != null) return backgroundImage;
            }

            return fillImage;
        }

        /// Presents readable low-mana feedback on the existing mana indicator
        /// when a cast is denied due to insufficient mana.
        private void HandleCastDenied(float requestedAmount)
        {
            deniedFlashTimeRemaining = deniedFlashDuration;
        }
    }
}
