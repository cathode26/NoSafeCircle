using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// AC-001/AC-002/AC-003/AC-004: gives the sealed door a base appearance distinguishable
    /// from the surrounding wall, a hover highlight over the same ground area
    /// DoorInteractable actually accepts a click on, and persistent selected/approach and
    /// opening feedback so cursor drift after a click does not read as an ignored command.
    /// Consumes DoorInteractable's own selection test and PlayerMovement's shared pointer
    /// target instead of independently projecting screen coordinates (AC-005).
    [DisallowMultipleComponent]
    public class DoorInteractionFeedback : MonoBehaviour
    {
        [SerializeField] private DoorInteractable door;
        [SerializeField] private PlayerMovement playerMovement;
        [SerializeField] private PlayerInteractionController interactionController;
        [SerializeField] private Renderer doorRenderer;

        [SerializeField] private Color baseColor = new Color(0.55f, 0.27f, 0.13f);
        [SerializeField] private Color hoverColor = new Color(0.95f, 0.75f, 0.2f);
        [SerializeField] private Color selectedColor = new Color(0.25f, 0.65f, 0.95f);
        [SerializeField] private Color openingColor = new Color(0.3f, 0.85f, 0.35f);

        private static readonly int ColorPropertyId = Shader.PropertyToID("_Color");
        private static readonly int BaseColorPropertyId = Shader.PropertyToID("_BaseColor");

        private MaterialPropertyBlock propertyBlock;

        /// AC-002: true while the shared pointer target falls within this door's own
        /// production selection area and no stronger selected/approach state is active.
        public bool IsHovered { get; private set; }

        /// AC-003: true while this door is the player's currently pending/approach-selected
        /// door, whether or not the automatic opening timer has started yet.
        public bool IsSelected { get; private set; }

        /// AC-003: true once the automatic opening timer has actually started, so feedback
        /// can transition from "command accepted" to "opening in progress".
        public bool IsOpening { get; private set; }

        private void Awake()
        {
            if (door == null) door = GetComponent<DoorInteractable>();
            if (playerMovement == null) playerMovement = FindFirstObjectByType<PlayerMovement>();
            if (interactionController == null) interactionController = FindFirstObjectByType<PlayerInteractionController>();
            if (doorRenderer == null) doorRenderer = GetComponentInChildren<Renderer>();

            propertyBlock = new MaterialPropertyBlock();
        }

        private void OnEnable()
        {
            ResetFeedback();
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// Advances hover/selection feedback for this frame. Public so Play Mode tests can
        /// drive it deterministically, mirroring DoorInteractable.Tick/PlayerMovement.Tick.
        public void Tick(float deltaTime)
        {
            if (door == null) return;

            if (door.IsOpen)
            {
                ResetFeedback();
                return;
            }

            var gameplayEnabled = interactionController == null || interactionController.IsGameplayEnabled;

            IsSelected = gameplayEnabled && interactionController != null && interactionController.PendingDoor == door;
            IsOpening = IsSelected && door.IsInteracting;
            IsHovered = gameplayEnabled && !IsSelected && playerMovement != null && playerMovement.HasPointerWorldTarget &&
                door.TryGetSelectionDistance(playerMovement.PointerWorldTarget, out _);

            ApplyAppearance();
        }

        /// AC-004: owner-controlled reset entry point. Returns hover/selection/opening
        /// feedback to its floor-initial sealed-door appearance, for use alongside
        /// DoorInteractable.ResetDoor() and PlayerInteractionController.ResetInteraction()
        /// when the Floor Run/Restart Orchestrator resets the floor.
        public void ResetFeedback()
        {
            IsHovered = false;
            IsSelected = false;
            IsOpening = false;
            ApplyAppearance();
        }

        private void ApplyAppearance()
        {
            var color = baseColor;
            if (IsOpening) color = openingColor;
            else if (IsSelected) color = selectedColor;
            else if (IsHovered) color = hoverColor;

            SetColor(color);
        }

        private void SetColor(Color color)
        {
            if (doorRenderer == null) return;

            if (propertyBlock == null) propertyBlock = new MaterialPropertyBlock();
            doorRenderer.GetPropertyBlock(propertyBlock);
            propertyBlock.SetColor(ColorPropertyId, color);
            propertyBlock.SetColor(BaseColorPropertyId, color);
            doorRenderer.SetPropertyBlock(propertyBlock);
        }
    }
}
