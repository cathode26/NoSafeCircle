using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    [DisallowMultipleComponent]
    public class DoorInteractable : MonoBehaviour
    {
        [SerializeField] private float duration = 5f;
        [SerializeField] private GameObject doorVisual;
        [SerializeField] private Collider doorwayBlocker;

        private PlayerInteractionController playerInRange;

        public float Duration => duration;
        public float Progress { get; private set; }
        public bool IsOpen { get; private set; }
        public bool IsInteracting { get; private set; }
        public bool IsPlayerInRange => playerInRange != null;

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// Advances the interaction timer by deltaTime. Public so Play Mode tests
        /// can drive the timer deterministically without waiting on real frames.
        public void Tick(float deltaTime)
        {
            if (!IsInteracting || IsOpen) return;

            Progress = Mathf.Clamp01(Progress + deltaTime / duration);

            if (Progress >= 1f)
            {
                Complete();
            }
        }

        public void StartInteraction()
        {
            if (IsOpen) return;
            IsInteracting = true;
        }

        public void CancelInteraction()
        {
            IsInteracting = false;
            Progress = 0f;
        }

        private void Complete()
        {
            IsInteracting = false;
            IsOpen = true;
            Progress = 1f;

            if (doorVisual != null) doorVisual.SetActive(false);
            if (doorwayBlocker != null) doorwayBlocker.enabled = false;
        }

        private void OnTriggerEnter(Collider other)
        {
            var controller = other.GetComponentInParent<PlayerInteractionController>();
            if (controller == null) return;

            playerInRange = controller;
            controller.NotifyDoorInRange(this);
        }

        private void OnTriggerExit(Collider other)
        {
            var controller = other.GetComponentInParent<PlayerInteractionController>();
            if (controller == null || controller != playerInRange) return;

            playerInRange = null;
            controller.NotifyDoorOutOfRange(this);
        }
    }
}
