using System;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    public class TitleScreenController : MonoBehaviour
    {
        [SerializeField] private GameObject titlePanel;
        [SerializeField] private Button startGameButton;
        [SerializeField] private PlayerMovement playerMovement;
        [SerializeField] private PlayerInteractionController playerInteractionController;
        [SerializeField] private Behaviour[] gameplayInputBehaviours;

        public bool HasRequestedWizardSelection { get; private set; }
        public bool IsTitleScreenVisible => titlePanel != null && titlePanel.activeSelf;

        /// <summary>
        /// The single NSC-066 boundary consumed by the wizard-selection flow.
        /// </summary>
        public event Action WizardSelectionRequested;

        private void Awake()
        {
            HasRequestedWizardSelection = false;

            if (titlePanel != null)
            {
                titlePanel.SetActive(true);
            }

            if (startGameButton != null)
            {
                startGameButton.interactable = true;
            }

            SuspendGameplayInput();
        }

        public void StartGame()
        {
            if (HasRequestedWizardSelection) return;

            HasRequestedWizardSelection = true;

            if (startGameButton != null)
            {
                startGameButton.interactable = false;
            }

            if (titlePanel != null)
            {
                titlePanel.SetActive(false);
            }

            WizardSelectionRequested?.Invoke();
        }

        private void SuspendGameplayInput()
        {
            playerMovement?.SuspendGameplayInput();
            playerInteractionController?.SuspendGameplayInput();

            if (gameplayInputBehaviours == null) return;

            foreach (Behaviour inputBehaviour in gameplayInputBehaviours)
            {
                if (inputBehaviour != null && inputBehaviour != this)
                {
                    inputBehaviour.enabled = false;
                }
            }
        }
    }
}
