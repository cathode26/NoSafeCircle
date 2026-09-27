using System;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype
{
    /// <summary>Hides gameplay UI, the stationary player, and the chase floor at the title.</summary>
    [DisallowMultipleComponent]
    public sealed class TitleScreenGameplayHudVisibility : MonoBehaviour
    {
        [SerializeField] private TitleScreenController titleScreen;
        [SerializeField] private CanvasGroup[] gameplayGroups;

        private VisualState[] previousStates;
        private bool isHidden;
        private SpriteRenderer gameplayPlayerVisual;
        private bool previousPlayerVisualEnabled;
        private bool isPlayerVisualHidden;
        private TilemapRenderer approachVisual;
        private bool previousApproachVisualEnabled;
        private bool isApproachVisualHidden;

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

            RestoreHud();
            RestorePlayerVisual();
            if (titleScreen != null)
                titleScreen.WizardSelectionRequested -= RestoreApproachVisual;
            RestoreApproachVisual();
            titleScreen = controller;
            gameplayGroups = groups;
            if (approachVisual != null)
                titleScreen.WizardSelectionRequested += RestoreApproachVisual;
            ApplyTitleState();
        }

        /// <summary>Connects the spawned player's visual without disabling its root, camera, or input components.</summary>
        public void BindPlayerVisual(SpriteRenderer visual)
        {
            if (visual == null) throw new ArgumentNullException(nameof(visual));

            RestorePlayerVisual();
            gameplayPlayerVisual = visual;
            if (titleScreen != null && titleScreen.IsTitleScreenVisible)
                HidePlayerVisual();
        }

        /// <summary>Shows the exterior chase tiles only after Start Game leaves the title.</summary>
        public void BindApproachVisual(TilemapRenderer visual)
        {
            if (visual == null) throw new ArgumentNullException(nameof(visual));

            if (titleScreen != null)
                titleScreen.WizardSelectionRequested -= RestoreApproachVisual;
            RestoreApproachVisual();
            approachVisual = visual;
            if (titleScreen == null) return;
            titleScreen.WizardSelectionRequested += RestoreApproachVisual;
            if (titleScreen.IsTitleScreenVisible)
                HideApproachVisual();
        }

        /// <summary>Reveals the HUD and player sprite when entry hands control back to gameplay.</summary>
        public void RestoreGameplayPresentation()
        {
            RestoreHud();
            RestorePlayerVisual();
            RestoreApproachVisual();
        }

        private void Awake()
        {
            ApplyTitleState();
        }

        private void OnEnable()
        {
            ApplyTitleState();
        }

        private void OnDestroy()
        {
            // A HUD re-spawn destroys this owner before binding a replacement. Do not leave the
            // surviving gameplay player invisible if entry never reached its handoff.
            RestorePlayerVisual();
            if (titleScreen != null)
                titleScreen.WizardSelectionRequested -= RestoreApproachVisual;
            RestoreApproachVisual();
        }

        private void ApplyTitleState()
        {
            if (titleScreen == null || gameplayGroups == null) return;
            if (titleScreen.IsTitleScreenVisible) Hide();
        }

        private void Hide()
        {
            if (!isHidden)
            {
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
            HidePlayerVisual();
            HideApproachVisual();
        }

        private void RestoreHud()
        {
            if (isHidden)
            {
                for (int index = 0; index < gameplayGroups.Length; index++)
                    previousStates[index].Restore(gameplayGroups[index]);
                previousStates = null;
                isHidden = false;
            }
        }

        private void HidePlayerVisual()
        {
            if (gameplayPlayerVisual == null || isPlayerVisualHidden) return;
            previousPlayerVisualEnabled = gameplayPlayerVisual.enabled;
            gameplayPlayerVisual.enabled = false;
            isPlayerVisualHidden = true;
        }

        private void RestorePlayerVisual()
        {
            if (!isPlayerVisualHidden) return;
            if (gameplayPlayerVisual != null)
                gameplayPlayerVisual.enabled = previousPlayerVisualEnabled;
            isPlayerVisualHidden = false;
        }

        private void HideApproachVisual()
        {
            if (approachVisual == null || isApproachVisualHidden) return;
            previousApproachVisualEnabled = approachVisual.enabled;
            approachVisual.enabled = false;
            isApproachVisualHidden = true;
        }

        private void RestoreApproachVisual()
        {
            if (!isApproachVisualHidden) return;
            if (approachVisual != null)
                approachVisual.enabled = previousApproachVisualEnabled;
            isApproachVisualHidden = false;
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
