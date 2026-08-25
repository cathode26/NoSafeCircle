using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    [DisallowMultipleComponent]
    public class DoorInteractable : MonoBehaviour
    {
        [SerializeField] private float duration = 5f;
        [SerializeField] private GameObject doorVisual;
        [SerializeField] private Collider doorwayBlocker;

        // Ground-plane offset from transform.position to the point PlayerInteractionController
        // compares the shared PlayerMovement.PointerWorldTarget against when testing whether the
        // visible door was clicked. The visible door sits above the ground (its visual center is
        // offset vertically), so the ground-plane point "under" a screen click on that visual is
        // offset horizontally from the door's own ground position under the fixed isometric
        // camera. DoorPrototypeSceneBuilder computes and assigns this value analytically at scene
        // build time; DoorInteractable itself never projects screen coordinates.
        [SerializeField] private Vector3 groundSelectionOffset = Vector3.zero;
        [SerializeField] private float selectionRadius = 1.5f;

        // Destination PlayerMovement is asked to walk to for the combined approach-and-interact
        // request. Offset toward the approach side of the door and within the arm's-reach trigger
        // below so that arrival there both (a) is physically reachable while the door is sealed
        // (not blocked by the door's own collider) and (b) already qualifies as arm's-reach range.
        [SerializeField] private Vector3 interactionPositionOffset = new Vector3(0f, 0f, -1f);

        private static readonly List<DoorInteractable> activeDoors = new List<DoorInteractable>();

        private PlayerInteractionController playerInRange;

        public float Duration => duration;
        public float Progress { get; private set; }
        public bool IsOpen { get; private set; }
        public bool IsInteracting { get; private set; }
        public bool IsPlayerInRange => playerInRange != null;

        /// AC-008: fires when this door completes its five-second opening timer and transitions
        /// from sealed to open. PlayerInteractionController consumes this to release its pending
        /// selection instead of independently polling IsOpen every frame.
        public event System.Action Opened;

        public static IReadOnlyList<DoorInteractable> ActiveDoors => activeDoors;

        public Vector3 SelectionPoint => transform.position + new Vector3(groundSelectionOffset.x, 0f, groundSelectionOffset.z);

        public Vector3 InteractionPosition => transform.position + interactionPositionOffset;

        private void OnEnable()
        {
            activeDoors.Add(this);
        }

        private void OnDisable()
        {
            activeDoors.Remove(this);
        }

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

        /// AC-001: tests whether the shared world-space pointer target (already projected onto
        /// the gameplay plane by PlayerMovement) falls within this door's selection area. Consumes
        /// that ground point directly rather than independently projecting screen coordinates.
        public bool TryGetSelectionDistance(Vector3 groundPoint, out float distance)
        {
            var offset = groundPoint - SelectionPoint;
            offset.y = 0f;
            distance = offset.magnitude;
            return distance <= selectionRadius;
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

        /// AC-007: owner-controlled reset entry point consumed by the Floor Run/Restart
        /// Orchestrator. Returns progress, interacting state, open state, and doorway-blocker
        /// enablement to their floor-initial values.
        public void ResetDoor()
        {
            IsInteracting = false;
            IsOpen = false;
            Progress = 0f;
            playerInRange = null;

            if (doorVisual != null) doorVisual.SetActive(true);
            if (doorwayBlocker != null) doorwayBlocker.enabled = true;
        }

        private void Complete()
        {
            IsInteracting = false;
            IsOpen = true;
            Progress = 1f;

            if (doorVisual != null) doorVisual.SetActive(false);
            if (doorwayBlocker != null) doorwayBlocker.enabled = false;

            Opened?.Invoke();
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
