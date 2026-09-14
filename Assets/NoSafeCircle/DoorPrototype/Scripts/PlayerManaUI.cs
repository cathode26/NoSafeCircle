using UnityEngine;
using UnityEngine.UI;
using DG.Tweening;

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
        private bool normalColorCaptured;
        private Tween deniedFlashTween;

        private void OnEnable()
        {
            Bind(mana, fillImage);
        }

        private void OnDisable()
        {
            Unsubscribe();
            StopDeniedFlash();
        }

        private void Update()
        {
            if (mana == null || fillImage == null) return;

            fillImage.fillAmount = mana.MaxMana > 0f ? mana.CurrentMana / mana.MaxMana : 0f;

        }

        public void Bind(PlayerMana source, Image target)
        {
            StopDeniedFlash();
            Unsubscribe();
            mana = source;
            fillImage = target;
            RefreshBindings();
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

        private void StopDeniedFlash()
        {
            var wasFlashing = deniedFlashTween != null;
            deniedFlashTween?.Kill();
            deniedFlashTween = null;

            if (wasFlashing && feedbackImage != null && normalColorCaptured)
            {
                feedbackImage.color = normalColor;
            }
        }

        /// Presents readable low-mana feedback on the mana indicator
        /// when a cast is denied due to insufficient mana.
        private void HandleCastDenied(float requestedAmount)
        {
            if (feedbackImage != null)
            {
                deniedFlashTween?.Kill();
                var target = feedbackImage;
                var restoreColor = normalColor;
                target.color = deniedColor;
                deniedFlashTween = DOTween.Sequence()
                    .AppendInterval(deniedFlashDuration)
                    .AppendCallback(() =>
                    {
                        if (target != null) target.color = restoreColor;
                    })
                    .OnComplete(() => deniedFlashTween = null);
            }
        }
    }
}
