using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// <summary>
    /// Consumes the confirmed wizard choice and hands control to the existing Player.
    /// </summary>
    public sealed class WizardGameEntryController : MonoBehaviour
    {
        [SerializeField] private WizardSelectionController wizardSelectionController;
        [SerializeField] private WizardAnimationController wizardAnimationController;
        [SerializeField] private Transform player;
        [SerializeField] private Transform worldSpawn;
        [SerializeField] private PlayerMovement playerMovement;
        [SerializeField] private PlayerInteractionController playerInteractionController;
        [SerializeField] private GameObject[] menuUiRoots;

        private bool isSubscribed;

        public bool HasEnteredGameplay { get; private set; }
        public int GameplayEntryCount { get; private set; }
        public ConfirmedWizardSelection? AppliedSelection { get; private set; }

        private void OnEnable()
        {
            SubscribeToSelection();
        }

        private void OnDisable()
        {
            UnsubscribeFromSelection();
        }

        private void SubscribeToSelection()
        {
            if (HasEnteredGameplay || isSubscribed || wizardSelectionController == null) return;

            wizardSelectionController.WizardSelectionConfirmed += EnterWorld;
            isSubscribed = true;
        }

        private void UnsubscribeFromSelection()
        {
            if (!isSubscribed) return;

            if (wizardSelectionController != null)
            {
                wizardSelectionController.WizardSelectionConfirmed -= EnterWorld;
            }

            isSubscribed = false;
        }

        /// <summary>
        /// Applies one confirmed selection, places the existing Player, and enables its input owners.
        /// Repeated callbacks are ignored after the first completed entry.
        /// </summary>
        public void EnterWorld(ConfirmedWizardSelection selection)
        {
            if (HasEnteredGameplay) return;
            if (!HasValidReferences())
            {
                Debug.LogError(
                    "WizardGameEntryController requires one selection source, one existing Player with " +
                    "its wizard, movement, and interaction owners, one world spawn, and complete menu roots.",
                    this);
                return;
            }

            wizardAnimationController.ApplyPresentation(selection.Presentation, selection.Skin);
            player.SetPositionAndRotation(worldSpawn.position, worldSpawn.rotation);

            foreach (GameObject menuUiRoot in menuUiRoots)
            {
                menuUiRoot.SetActive(false);
            }

            AppliedSelection = selection;
            HasEnteredGameplay = true;
            GameplayEntryCount++;
            UnsubscribeFromSelection();

            playerMovement.EnableGameplayInput();
            playerInteractionController.EnableGameplayInput();
        }

        private bool HasValidReferences()
        {
            if (wizardSelectionController == null || wizardAnimationController == null ||
                player == null || worldSpawn == null || playerMovement == null ||
                playerInteractionController == null || menuUiRoots == null || menuUiRoots.Length == 0)
            {
                return false;
            }

            if (wizardAnimationController.transform != player || playerMovement.transform != player ||
                playerInteractionController.transform != player)
            {
                return false;
            }

            foreach (GameObject menuUiRoot in menuUiRoots)
            {
                if (menuUiRoot == null) return false;
            }

            return true;
        }
    }
}
