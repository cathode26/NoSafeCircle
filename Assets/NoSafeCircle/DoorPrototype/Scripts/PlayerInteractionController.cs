using UnityEngine;
using UnityEngine.InputSystem;

namespace NoSafeCircle.DoorPrototype
{
    public class PlayerInteractionController : MonoBehaviour
    {
        [SerializeField] private PlayerHealth playerHealth;
        [SerializeField] private Key interactKey = Key.E;

        public DoorInteractable CurrentDoor { get; private set; }
        public bool IsInRange => CurrentDoor != null;
        public bool IsInteracting { get; private set; }

        private void Awake()
        {
            if (playerHealth == null) playerHealth = GetComponent<PlayerHealth>();
        }

        private void OnEnable()
        {
            if (playerHealth != null) playerHealth.Damaged += HandleDamaged;
        }

        private void OnDisable()
        {
            if (playerHealth != null) playerHealth.Damaged -= HandleDamaged;
        }

        private void Update()
        {
            var keyboard = Keyboard.current;
            if (keyboard == null) return;

            var key = keyboard[interactKey];
            if (key.wasPressedThisFrame)
            {
                BeginInteraction();
            }
            else if (key.wasReleasedThisFrame)
            {
                EndInteraction();
            }
        }

        /// Called by DoorInteractable when the player enters its trigger zone.
        public void NotifyDoorInRange(DoorInteractable door)
        {
            CurrentDoor = door;
        }

        /// Called by DoorInteractable when the player leaves its trigger zone.
        public void NotifyDoorOutOfRange(DoorInteractable door)
        {
            if (CurrentDoor != door) return;

            EndInteraction();
            CurrentDoor = null;
        }

        public void BeginInteraction()
        {
            if (CurrentDoor == null || CurrentDoor.IsOpen) return;

            IsInteracting = true;
            CurrentDoor.StartInteraction();
        }

        public void EndInteraction()
        {
            if (!IsInteracting) return;

            IsInteracting = false;
            CurrentDoor?.CancelInteraction();
        }

        /// Public entry point for movement-triggered cancellation, called by PlayerMovement.
        public void OnPlayerMoved()
        {
            if (!IsInteracting) return;
            EndInteraction();
        }

        private void HandleDamaged(float amount)
        {
            if (!IsInteracting) return;
            EndInteraction();
        }
    }
}
