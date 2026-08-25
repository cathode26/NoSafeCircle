using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    public class PlayerInteractionController : MonoBehaviour
    {
        [SerializeField] private PlayerHealth playerHealth;
        [SerializeField] private PlayerMovement movement;

        private DoorInteractable pendingDoor;

        public DoorInteractable CurrentDoor { get; private set; }
        public bool IsInRange => CurrentDoor != null;
        public bool IsInteracting { get; private set; }
        public bool IsGameplayEnabled { get; private set; } = true;

        /// AC-001/AC-003: the door selection that click-to-approach committed to. While this is
        /// set, PlayerMovement must not let held-cursor drift override the approach destination.
        public DoorInteractable PendingDoor
        {
            get => pendingDoor;
            private set
            {
                if (pendingDoor == value) return;

                if (pendingDoor != null) pendingDoor.Opened -= HandlePendingDoorOpened;
                pendingDoor = value;
                if (pendingDoor != null) pendingDoor.Opened += HandlePendingDoorOpened;
            }
        }

        /// AC-003: consumed by PlayerMovement to suppress held-cursor destination updates while a
        /// door approach/interaction is pending, so cursor drift after the initial click cannot
        /// redirect the wizard away from the selected door.
        public bool HasLockedDoorInteraction => PendingDoor != null;

        private void Awake()
        {
            if (playerHealth == null) playerHealth = GetComponent<PlayerHealth>();
            if (movement == null) movement = GetComponent<PlayerMovement>();
        }

        private void OnEnable()
        {
            if (playerHealth != null) playerHealth.Damaged += HandleDamaged;
            if (movement != null) movement.DestinationReached += HandleDestinationReached;
        }

        private void OnDisable()
        {
            if (playerHealth != null) playerHealth.Damaged -= HandleDamaged;
            if (movement != null) movement.DestinationReached -= HandleDestinationReached;
        }

        /// AC-001/AC-002: called by PlayerMovement on a fresh click/press using the shared
        /// world-space pointer target it already projected. If the click hit a sealed door, this
        /// issues the combined approach-and-interact request and reports the click as consumed so
        /// PlayerMovement does not also treat it as a plain move-to-point click. Any previously
        /// pending/interacting door is cancelled first, since a new click is a replacing command.
        public bool TryBeginDoorApproach(Vector3 groundPoint)
        {
            if (!IsGameplayEnabled) return false;

            var door = FindSelectableDoor(groundPoint);
            if (door == PendingDoor) return door != null;

            CancelCurrentDoorInteraction();

            if (door == null) return false;

            PendingDoor = door;
            if (movement != null) movement.RequestDestination(door.InteractionPosition);
            TryStartPendingDoorInteraction();
            return true;
        }

        /// Called by DoorInteractable when the player enters its trigger zone.
        public void NotifyDoorInRange(DoorInteractable door)
        {
            CurrentDoor = door;
            TryStartPendingDoorInteraction();
        }

        /// Called by DoorInteractable when the player leaves its trigger zone.
        public void NotifyDoorOutOfRange(DoorInteractable door)
        {
            if (CurrentDoor != door) return;

            CurrentDoor = null;

            // AC-004: moving away once timing has begun resets progress.
            if (IsInteracting) CancelCurrentDoorInteraction();
        }

        public void BeginInteraction()
        {
            if (!IsGameplayEnabled) return;
            if (CurrentDoor == null || CurrentDoor.IsOpen) return;

            IsInteracting = true;
            PendingDoor = CurrentDoor;
            CurrentDoor.StartInteraction();
        }

        public void EndInteraction()
        {
            if (!IsInteracting) return;
            CancelCurrentDoorInteraction();
        }

        /// Public entry point for movement-triggered cancellation, called by PlayerMovement.
        public void OnPlayerMoved()
        {
            if (!IsInteracting) return;
            EndInteraction();
        }

        /// AC-006: owner-controlled gameplay-enable/suspend interface consumed by the Game
        /// Flow/Victory capability. Immediately cancels any in-progress door approach/opening
        /// timer and rejects new door-selection/interaction commands until re-enabled.
        public void SuspendGameplayInput()
        {
            IsGameplayEnabled = false;
            CancelCurrentDoorInteraction();
        }

        public void EnableGameplayInput()
        {
            IsGameplayEnabled = true;
        }

        /// AC-007: owner-controlled reset entry point consumed by the Floor Run/Restart
        /// Orchestrator. Returns owned interaction state to floor-initial values.
        public void ResetInteraction()
        {
            CancelCurrentDoorInteraction();
            CurrentDoor = null;
            IsGameplayEnabled = true;
        }

        private void HandleDestinationReached()
        {
            TryStartPendingDoorInteraction();
        }

        /// AC-002: starts the automatic opening timer once the wizard has both arrived (no
        /// active approach destination remaining) and is confirmed within arm's-reach range of
        /// the pending door. Gating on arrival rather than on the arm's-reach trigger alone
        /// avoids starting the timer while the automatic approach is still in motion, which
        /// would otherwise be cancelled by that same approach's own movement.
        private void TryStartPendingDoorInteraction()
        {
            if (!IsGameplayEnabled) return;
            if (PendingDoor == null || PendingDoor.IsOpen || IsInteracting) return;
            if (PendingDoor != CurrentDoor) return;
            if (movement != null && movement.HasActiveDestination) return;

            IsInteracting = true;
            PendingDoor.StartInteraction();
        }

        private void CancelCurrentDoorInteraction()
        {
            IsInteracting = false;
            PendingDoor?.CancelInteraction();
            PendingDoor = null;

            // AC-004/AC-006: a door approach that was still walking toward its interaction
            // position (or a running opening timer) must not continue after the request that
            // owned it has been cancelled - through suspend, damage, or a replacing command.
            movement?.CancelRequestedDestination();
        }

        private void HandlePendingDoorOpened()
        {
            IsInteracting = false;
            PendingDoor = null;
        }

        private DoorInteractable FindSelectableDoor(Vector3 groundPoint)
        {
            DoorInteractable closest = null;
            var closestDistance = float.MaxValue;

            foreach (var candidate in DoorInteractable.ActiveDoors)
            {
                if (candidate == null || candidate.IsOpen) continue;
                if (!candidate.TryGetSelectionDistance(groundPoint, out var distance)) continue;

                if (distance < closestDistance)
                {
                    closestDistance = distance;
                    closest = candidate;
                }
            }

            return closest;
        }

        /// AC-004: damage resets the door attempt whether the wizard is still automatically
        /// approaching the selected door (PendingDoor set, timer not yet started) or is already
        /// running the opening timer. Checking PendingDoor rather than IsInteracting covers both
        /// phases of a single click-to-approach request.
        private void HandleDamaged(float amount)
        {
            if (PendingDoor == null) return;
            CancelCurrentDoorInteraction();
        }
    }
}
