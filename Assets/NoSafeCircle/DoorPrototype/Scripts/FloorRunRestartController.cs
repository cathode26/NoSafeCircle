using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// AC-001/AC-002: staged Floor Run/Restart Orchestrator. Subscribes to Player Health's
    /// owner-exposed zero-health/death transition and, on trigger, invokes the owner-controlled
    /// reset entry point of every currently-existing run-persistent owner (Player Health, Player
    /// Mana, Player Movement, Player Interaction, and every currently active door). It never polls
    /// CurrentHealth or writes another owner's internal state directly (AC-003). GDD "Floor-run
    /// restart ownership": early implementation validates only against currently-existing
    /// persistent owners; later owners join this orchestrator without redesigning the contract.
    public class FloorRunRestartController : MonoBehaviour
    {
        [SerializeField] private PlayerHealth playerHealth;
        [SerializeField] private PlayerMana playerMana;
        [SerializeField] private PlayerMovement playerMovement;
        [SerializeField] private PlayerInteractionController playerInteractionController;

        private void OnEnable()
        {
            if (playerHealth != null) playerHealth.Died += HandlePlayerDied;
        }

        private void OnDisable()
        {
            if (playerHealth != null) playerHealth.Died -= HandlePlayerDied;
        }

        private void HandlePlayerDied()
        {
            RestartFloor();
        }

        /// Invokes every currently-existing run-persistent owner's exposed reset entry point.
        /// Doors are reset through the static active-door registry rather than a serialized
        /// reference list, since DoorInteractable already owns that registry (AC-002).
        private void RestartFloor()
        {
            playerHealth?.ResetHealth();
            playerMana?.ResetMana();
            playerMovement?.ResetMovement();
            playerInteractionController?.ResetInteraction();

            var activeDoors = DoorInteractable.ActiveDoors;
            for (var i = 0; i < activeDoors.Count; i++)
            {
                activeDoors[i].ResetDoor();
            }
        }
    }
}
