using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// AC-002: binds the approved bonestone door sprites to the door state DoorInteractable's
    /// own public events express, rather than to sprite filenames or a state model of its own.
    /// DoorInteractable.Complete() deactivates doorVisual before raising Opened, so
    /// HandleOpened re-enables it before assigning the open sprite - otherwise the door would
    /// render the correct sprite on a hidden object and simply vanish when opened. doorVisual
    /// and the doorwayBlocker collider are the SAME GameObject (see
    /// DoorPrototypeSceneBuilder.BuildDoor), so this class only ever changes GameObject
    /// activity and the sprite, never collider state - re-enabling the collider alongside the
    /// visual would make an open door block the wizard and stop projectiles again.
    [DisallowMultipleComponent]
    public sealed class DoorStateSpriteBinder : MonoBehaviour
    {
        [SerializeField] private DoorInteractable door;
        [SerializeField] private GameObject doorVisual;
        [SerializeField] private SpriteRenderer spriteRenderer;

        [SerializeField] private Sprite sealedSprite;
        [SerializeField] private Sprite lockedSprite;
        [SerializeField] private Sprite openSprite;

        // AC-002: not a DoorPassabilityState - a closed-leaf skin selected by
        // DoorInteractable.IsFinalDoor, used only while the door is closed (sealed or locked).
        // An open final door renders openSprite like every other door.
        [SerializeField] private Sprite finalSprite;

        private void Awake()
        {
            if (door == null) door = GetComponent<DoorInteractable>();
        }

        private void OnEnable()
        {
            if (door == null) return;

            door.Opened += HandleOpened;
            door.Locked += HandleLocked;
            door.ResetCompleted += HandleResetCompleted;

            // AC-002: a door that has not yet transitioned state at runtime (e.g. a sealed,
            // never-opened final door composed by DoorSequenceBuilder cloning an already-built
            // door and only setting isFinalDoor afterward) never raises Opened/Locked/
            // ResetCompleted, so relying on those events alone would leave it showing whatever
            // sprite construction-time assigned instead of the sprite its actual current state
            // requires. Reading door.IsOpen/IsLocked/IsFinalDoor directly here makes the very
            // first frame correct without waiting for a future event.
            SyncToCurrentState();
        }

        private void SyncToCurrentState()
        {
            // LOCKED WINS OVER OPEN, AND THE ORDER IS THE WHOLE POINT: the two flags are not
            // mutually exclusive. DoorInteractable.CloseAndLock sets IsLocked while LEAVING
            // IsOpen true, so testing IsOpen first makes a door that was locked after being
            // crossed render the open sprite for a passage that is shut - visible on any door
            // re-enabled in that state, and not caught by the event handlers because locking
            // raises Locked exactly once, before the object is ever disabled.
            if (door.IsLocked)
            {
                HandleLocked();
                return;
            }

            if (door.IsOpen)
            {
                HandleOpened();
                return;
            }

            SetSprite(door.IsFinalDoor ? finalSprite : sealedSprite);
        }

        private void OnDisable()
        {
            if (door == null) return;

            door.Opened -= HandleOpened;
            door.Locked -= HandleLocked;
            door.ResetCompleted -= HandleResetCompleted;
        }

        private void HandleOpened()
        {
            // DoorInteractable.Complete() already deactivated doorVisual before raising this
            // event; re-enable it before the open sprite can be seen. doorwayBlocker shares this
            // GameObject and stays disabled - only its collider's own `enabled` flag governs
            // passability, and this method never touches it.
            if (doorVisual != null) doorVisual.SetActive(true);
            SetSprite(openSprite);
        }

        private void HandleLocked()
        {
            SetSprite(door.IsFinalDoor ? finalSprite : lockedSprite);
        }

        private void HandleResetCompleted()
        {
            SetSprite(door.IsFinalDoor ? finalSprite : sealedSprite);
        }

        private void SetSprite(Sprite sprite)
        {
            if (spriteRenderer != null) spriteRenderer.sprite = sprite;
        }
    }
}
