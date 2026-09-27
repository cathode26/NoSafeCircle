using System;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// <summary>Hides gameplay HUD graphics while the title owns the screen.</summary>
    [DisallowMultipleComponent]
    public sealed class TitleScreenGameplayHudVisibility : MonoBehaviour
    {
        [SerializeField] private TitleScreenController titleScreen;
        [SerializeField] private CanvasGroup[] gameplayGroups;

        private VisualState[] previousStates;
        private bool isHidden;

        public void Configure(TitleScreenController controller, CanvasGroup[] groups)
        {
            if (controller == null) throw new ArgumentNullException(nameof(controller));
            if (groups == null || groups.Length == 0)
                throw new ArgumentException("At least one gameplay HUD group is required.", nameof(groups));
            foreach (CanvasGroup group in groups)
            {
                if (group == null)
                    throw new ArgumentException("Gameplay HUD groups cannot contain null.", nameof(groups));
            }

            Restore();
            Unsubscribe();
            titleScreen = controller;
            gameplayGroups = groups;
            ApplyTitleState();
        }

        private void Awake()
        {
            ApplyTitleState();
        }

        private void OnEnable()
        {
            ApplyTitleState();
        }

        private void OnDisable()
        {
            Unsubscribe();
        }

        private void ApplyTitleState()
        {
            if (titleScreen == null || gameplayGroups == null) return;
            Unsubscribe();
            titleScreen.WizardSelectionRequested += OnWizardSelectionRequested;
            if (titleScreen.IsTitleScreenVisible) Hide();
            else Restore();
        }

        private void Hide()
        {
            if (isHidden) return;
            previousStates = new VisualState[gameplayGroups.Length];
            for (int index = 0; index < gameplayGroups.Length; index++)
            {
                CanvasGroup group = gameplayGroups[index];
                previousStates[index] = new VisualState(group);
                group.alpha = 0f;
                group.interactable = false;
                group.blocksRaycasts = false;
            }
            isHidden = true;
        }

        private void OnWizardSelectionRequested()
        {
            Restore();
            Unsubscribe();
        }

        private void Restore()
        {
            if (!isHidden) return;
            for (int index = 0; index < gameplayGroups.Length; index++)
            {
                previousStates[index].Restore(gameplayGroups[index]);
            }
            previousStates = null;
            isHidden = false;
        }

        private void Unsubscribe()
        {
            if (titleScreen != null)
                titleScreen.WizardSelectionRequested -= OnWizardSelectionRequested;
        }

        private readonly struct VisualState
        {
            private readonly float alpha;
            private readonly bool interactable;
            private readonly bool blocksRaycasts;

            public VisualState(CanvasGroup group)
            {
                alpha = group.alpha;
                interactable = group.interactable;
                blocksRaycasts = group.blocksRaycasts;
            }

            public void Restore(CanvasGroup group)
            {
                group.alpha = alpha;
                group.interactable = interactable;
                group.blocksRaycasts = blocksRaycasts;
            }
        }
    }
}
