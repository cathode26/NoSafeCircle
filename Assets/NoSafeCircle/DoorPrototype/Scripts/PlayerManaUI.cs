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

        private PlayerMana subscribedMana;
        private Image feedbackImage;
        private float deniedFlashTimeRemaining;
        private bool normalColorCaptured;

        private void OnEnable()
        {
            RefreshBindings();
        }

        private void OnDisable()
        {
            Unsubscribe();

            if (feedbackImage != null && normalColorCaptured)
            {
                feedbackImage.color = normalColor;
            }

            deniedFlashTimeRemaining = 0f;
        }

        private void Update()
        {
            // The scene builder adds this component before assigning its serialized
            // references. Refreshing here makes that late wiring safe without requiring
            // an artificial disable/re-enable cycle.
            RefreshBindings();

            if (mana == null || fillImage == null) return;

            fillImage.fillAmount = mana.MaxMana > 0f ? mana.CurrentMana / mana.MaxMana : 0f;

            if (feedbackImage == null || deniedFlashTimeRemaining <= 0f) return;

            deniedFlashTimeRemaining -= Time.deltaTime;
            feedbackImage.color = deniedFlashTimeRemaining > 0f ? deniedColor : normalColor;
        }

        private void RefreshBindings()
        {
            if (subscribedMana != mana)
            {
                Unsubscribe();

                subscribedMana = mana;
                if (subscribedMana != null)
                {
                    subscribedMana.CastDenied += HandleCastDenied;
                }
            }

            var resolvedFeedbackImage = ResolveFeedbackImage();
            if (resolvedFeedbackImage == feedbackImage) return;

            feedbackImage = resolvedFeedbackImage;
            normalColorCaptured = false;

            if (feedbackImage != null)
            {
                normalColor = feedbackImage.color;
                normalColorCaptured = true;
            }
        }

        private Image ResolveFeedbackImage()
        {
            if (fillImage == null) return null;

            // Prefer the visible mana-bar background. At zero mana the filled Image has
            // fillAmount == 0 and cannot visibly communicate a denied cast.
            if (fillImage.transform.parent != null)
            {
                var parentImage = fillImage.transform.parent.GetComponent<Image>();
                if (parentImage != null)
                {
                    return parentImage;
                }
            }

            // Preserve compatibility with isolated/test usages that have only a fill Image.
            return fillImage;
        }

        private void Unsubscribe()
        {
            if (subscribedMana != null)
            {
                subscribedMana.CastDenied -= HandleCastDenied;
                subscribedMana = null;
            }
        }

        /// Presents readable low-mana feedback on the mana indicator
        /// when a cast is denied due to insufficient mana.
        private void HandleCastDenied(float requestedAmount)
        {
            RefreshBindings();
            deniedFlashTimeRemaining = deniedFlashDuration;

            if (feedbackImage != null)
            {
                feedbackImage.color = deniedColor;
            }
        }
    }
}
