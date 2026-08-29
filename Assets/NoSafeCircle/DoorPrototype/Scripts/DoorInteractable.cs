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

        // AC-001: local-space offset (relative to this door) for the trigger volume that detects
        // the wizard actually reaching this door's forward side. Mirrors interactionPositionOffset
        // on the opposite (far) side of the doorway. DoorPrototypeSceneBuilder may override this
        // per door instance to match authored room geometry; this default assumes the door faces
        // +Z, matching interactionPositionOffset's -Z approach-side default.
        [SerializeField] private Vector3 forwardCrossingOffset = new Vector3(0f, 0f, 1f);
        [SerializeField] private Vector3 forwardCrossingTriggerSize = new Vector3(3f, 3f, 2f);

        private static readonly List<DoorInteractable> activeDoors = new List<DoorInteractable>();

        private PlayerInteractionController playerInRange;

        public float Duration => duration;
        public float Progress { get; private set; }
        public bool IsOpen { get; private set; }
        public bool IsInteracting { get; private set; }
        public bool IsPlayerInRange => playerInRange != null;

        /// AC-001/AC-002: the single owner-side doorway-crossing state. Only ever set true while
        /// this door is open and the wizard has physically reached the forward-side crossing
        /// trigger; opening the door by itself never sets this. Door close/lock and final-escape
        /// victory consume this property (and the CrossedForward event below) instead of each
        /// implementing their own forward-side detection.
        public bool HasCrossedForward { get; private set; }

        /// AC-008: fires when this door completes its five-second opening timer and transitions
        /// from sealed to open. PlayerInteractionController consumes this to release its pending
        /// selection instead of independently polling IsOpen every frame.
        public event System.Action Opened;

        /// AC-002: fires exactly once, the moment HasCrossedForward becomes true. Owner-side
        /// consumers (door close/lock, final-escape victory) subscribe here instead of polling.
        public event System.Action CrossedForward;

        public static IReadOnlyList<DoorInteractable> ActiveDoors => activeDoors;

        public Vector3 SelectionPoint => transform.position + new Vector3(groundSelectionOffset.x, 0f, groundSelectionOffset.z);

        public Vector3 InteractionPosition => transform.position + interactionPositionOffset;

        private void Awake()
        {
            // AC-001: the forward-crossing trigger lives on its own child GameObject (rather than
            // this door's own collider set) so it can be told apart from the arm's-reach
            // interaction-range trigger, which already relies on this component's own
            // OnTriggerEnter/OnTriggerExit below.
            var crossingObject = new GameObject("ForwardCrossingTrigger");
            crossingObject.transform.SetParent(transform, false);
            crossingObject.transform.localPosition = forwardCrossingOffset;

            var crossingTrigger = crossingObject.AddComponent<BoxCollider>();
            crossingTrigger.isTrigger = true;
            crossingTrigger.size = forwardCrossingTriggerSize;

            var relay = crossingObject.AddComponent<ForwardCrossingRelay>();
            relay.Owner = this;
        }

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

        /// AC-003/AC-007: owner-controlled reset entry point consumed by the Floor Run/Restart
        /// Orchestrator. Returns progress, interacting state, open state, doorway-crossing state,
        /// and doorway-blocker enablement to their floor-initial values.
        public void ResetDoor()
        {
            IsInteracting = false;
            IsOpen = false;
            Progress = 0f;
            HasCrossedForward = false;
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

        /// AC-001: called by the forward-crossing trigger's relay when the wizard's collider
        /// enters it. Only counts as crossing while this door is actually open, so opening the
        /// door alone never sets HasCrossedForward.
        private void HandleForwardCrossingTriggerEnter(Collider other)
        {
            if (!IsOpen || HasCrossedForward) return;

            var controller = other.GetComponentInParent<PlayerInteractionController>();
            if (controller == null) return;

            HasCrossedForward = true;
            CrossedForward?.Invoke();
        }

        // AC-001: relays trigger events from the child forward-crossing GameObject back to the
        // owning door. Kept as a private nested MonoBehaviour so the forward-crossing trigger can
        // be created and wired entirely from this script without any additional scene/prefab
        // authoring.
        private class ForwardCrossingRelay : MonoBehaviour
        {
            public DoorInteractable Owner;

            private void OnTriggerEnter(Collider other)
            {
                Owner?.HandleForwardCrossingTriggerEnter(other);
            }
        }
    }
}
