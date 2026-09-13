using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    public class DoorInteractionUI : MonoBehaviour
    {
        [SerializeField] private PlayerInteractionController interactionController;

        // Retained as a fallback for older scenes that predate the player-owned selection
        // model. Current scenes resolve the interaction controller and use its selected door.
        [SerializeField] private DoorInteractable door;
        [SerializeField] private GameObject promptRoot;
        [SerializeField] private Image progressFillImage;

        private void Awake()
        {
            ResolveInteractionController();
        }

        private void Update()
        {
            ResolveInteractionController();

            var promptDoor = interactionController != null
                ? interactionController.CurrentDoor
                : door;
            var trackedDoor = TrackedDoor();

            if (promptRoot != null)
            {
                promptRoot.SetActive(promptDoor != null && promptDoor.IsPlayerInRange && !promptDoor.IsOpen);
            }

            if (progressFillImage != null)
            {
                var progress = trackedDoor != null ? trackedDoor.Progress : 0f;
                progressFillImage.fillAmount = progress;
                progressFillImage.enabled = progress > 0f;
            }
        }

        private DoorInteractable TrackedDoor()
        {
            if (interactionController == null)
            {
                return door != null && !door.IsOpen ? door : null;
            }

            var selectedDoor = interactionController.PendingDoor;
            if (selectedDoor != null && !selectedDoor.IsOpen) return selectedDoor;

            var currentDoor = interactionController.CurrentDoor;
            return currentDoor != null && !currentDoor.IsOpen ? currentDoor : null;
        }

        private void ResolveInteractionController()
        {
            if (interactionController == null)
            {
                interactionController = FindFirstObjectByType<PlayerInteractionController>();
            }
        }
    }
}
