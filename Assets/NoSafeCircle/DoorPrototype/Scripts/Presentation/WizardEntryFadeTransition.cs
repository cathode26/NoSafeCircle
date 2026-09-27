using DG.Tweening;
using NoSafeCircle.DoorPrototype.Presentation;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    /// <summary>Fades the screen across the cutscene actor-to-player handoff.</summary>
    [DisallowMultipleComponent]
    public sealed class WizardEntryFadeTransition : MonoBehaviour
    {
        private const float BlackoutSeconds = 0.25f;
        private const float RevealSeconds = 0.35f;

        private TitleScreenChaseBackdrop chase;
        private WizardGameEntryController entry;
        private GameObject overlay;
        private HierarchyFader fader;
        private EntryChamberCutsceneOcclusion chamberOcclusion;
        private bool blackoutStarted;
        private bool blackoutReached;
        private bool entryReady;
        private bool revealing;

        public bool IsTransitioning => blackoutStarted && !revealing;

        public void Configure(TitleScreenChaseBackdrop chaseOwner,
            WizardGameEntryController entryOwner)
        {
            Cancel();
            Canvas canvas = GetComponentInParent<Canvas>();
            if (canvas == null || chaseOwner == null || entryOwner == null)
                return;

            chase = chaseOwner;
            entry = entryOwner;
            overlay = new GameObject("WizardEntryFade", typeof(RectTransform),
                typeof(Image), typeof(HierarchyFader));
            overlay.transform.SetParent(canvas.transform, false);
            overlay.transform.SetAsLastSibling();

            RectTransform rect = overlay.GetComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;

            Image image = overlay.GetComponent<Image>();
            image.color = new Color(0.045f, 0.035f, 0.075f, 1f);
            image.raycastTarget = false;

            fader = overlay.GetComponent<HierarchyFader>();
            fader.FadeTo(0f, 0f);
            chamberOcclusion = GetComponent<EntryChamberCutsceneOcclusion>();
            if (chamberOcclusion == null)
                chamberOcclusion = gameObject.AddComponent<EntryChamberCutsceneOcclusion>();
            chamberOcclusion.Begin();
            chase.EntryChaseEnding += OnChaseEnding;
            entry.EntryCutsceneReadyForGameplay += OnEntryReady;
        }

        public void Cancel()
        {
            if (chase != null) chase.EntryChaseEnding -= OnChaseEnding;
            if (entry != null) entry.EntryCutsceneReadyForGameplay -= OnEntryReady;
            if (chamberOcclusion != null) chamberOcclusion.Restore();
            chase = null;
            entry = null;
            chamberOcclusion = null;
            if (overlay != null)
            {
                overlay.SetActive(false);
                Destroy(overlay);
            }
            overlay = null;
            fader = null;
            blackoutStarted = false;
            blackoutReached = false;
            entryReady = false;
            revealing = false;
        }

        private void OnDisable() => Cancel();
        private void OnDestroy() => Cancel();

        private void OnChaseEnding()
        {
            if (fader == null || blackoutStarted) return;
            blackoutStarted = true;
            Tween tween = fader.FadeTo(1f, BlackoutSeconds);
            if (tween == null) OnBlackoutReached();
            else tween.OnComplete(OnBlackoutReached);
        }

        private void OnEntryReady()
        {
            if (fader == null || entry == null) return;
            entryReady = true;
            if (!blackoutStarted)
            {
                blackoutStarted = true;
                fader.FadeTo(1f, 0f);
                OnBlackoutReached();
            }
            else if (blackoutReached)
            {
                BeginReveal();
            }
        }

        private void OnBlackoutReached()
        {
            // Restore the authored wall art while the overlay is fully opaque.
            if (chamberOcclusion != null) chamberOcclusion.Restore();
            blackoutReached = true;
            if (entryReady) BeginReveal();
        }

        private void BeginReveal()
        {
            if (revealing || fader == null || entry == null) return;
            revealing = true;
            entry.RevealGameplayPresentation();
            Tween tween = fader.FadeTo(0f, RevealSeconds);
            if (tween == null) FinishReveal();
            else tween.OnComplete(FinishReveal);
        }

        private void FinishReveal()
        {
            WizardGameEntryController controller = entry;
            Cancel();
            if (controller != null) controller.CompleteEntryAfterCutscene();
        }
    }
}
