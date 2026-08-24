using UnityEngine;
using UnityEngine.InputSystem;

namespace NoSafeCircle.DoorPrototype
{
    [RequireComponent(typeof(CharacterController))]
    public class PlayerMovement : MonoBehaviour
    {
        private const float MovementThreshold = 0.001f;
        private const float ArrivalThreshold = 0.05f;
        private const float VerticalGroundingOffset = -0.1f;

        [SerializeField] private float moveSpeed = 4f;
        [SerializeField] private float gameplayPlaneHeight = 0f;
        [SerializeField] private InputActionAsset inputActions;
        [SerializeField] private PlayerInteractionController interactionController;

        private CharacterController controller;
        private Camera mainCamera;
        private InputAction pointerPositionAction;
        private InputAction moveToCursorAction;

        private Vector3 initialPosition;
        private Quaternion initialRotation;

        private bool hasDestination;
        private Vector3 destination;
        private int movementRestrictionCount;

        /// Shared world-space pointer target (AC-002), produced by projecting the cursor
        /// onto the gameplay plane. Consumers (cursor-aimed spells, Door/Interaction) read
        /// this instead of independently projecting screen coordinates.
        public Vector3 PointerWorldTarget { get; private set; }
        public bool HasPointerWorldTarget { get; private set; }

        public bool IsMovementRestricted => movementRestrictionCount > 0;
        public bool IsGameplayEnabled { get; private set; } = true;
        public bool HasActiveDestination => hasDestination;

        private void Awake()
        {
            controller = GetComponent<CharacterController>();
            if (interactionController == null) interactionController = GetComponent<PlayerInteractionController>();

            initialPosition = transform.position;
            initialRotation = transform.rotation;

            var playerMap = inputActions != null ? inputActions.FindActionMap("Player", false) : null;
            if (playerMap == null)
            {
                Debug.LogWarning("PlayerMovement has no 'Player' action map assigned/found; mouse-directed " +
                    "movement and the shared pointer projection will be unavailable.");
                return;
            }

            pointerPositionAction = playerMap.FindAction("PointerPosition", false);
            moveToCursorAction = playerMap.FindAction("MoveToCursor", false);

            if (pointerPositionAction == null || moveToCursorAction == null)
            {
                Debug.LogWarning("PlayerMovement could not find the 'PointerPosition' and/or 'MoveToCursor' " +
                    "actions on the Player action map.");
            }
        }

        private void OnEnable()
        {
            pointerPositionAction?.Enable();
            moveToCursorAction?.Enable();
        }

        private void OnDisable()
        {
            pointerPositionAction?.Disable();
            moveToCursorAction?.Disable();
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// Advances movement/pointer-projection state by deltaTime. Public so Play Mode
        /// tests can drive it deterministically, mirroring DoorInteractable.Tick/PlayerMana.Tick.
        public void Tick(float deltaTime)
        {
            UpdatePointerWorldTarget();

            if (!IsGameplayEnabled)
            {
                ApplyGrounding(deltaTime);
                return;
            }

            HandleMoveToCursorInput();
            TickDestinationMovement(deltaTime);
        }

        private void UpdatePointerWorldTarget()
        {
            HasPointerWorldTarget = false;

            if (pointerPositionAction == null) return;

            if (mainCamera == null) mainCamera = Camera.main;
            if (mainCamera == null) return;

            var screenPosition = pointerPositionAction.ReadValue<Vector2>();
            var ray = mainCamera.ScreenPointToRay(screenPosition);
            var plane = new Plane(Vector3.up, new Vector3(0f, gameplayPlaneHeight, 0f));

            if (!plane.Raycast(ray, out var distance)) return;

            PointerWorldTarget = ray.GetPoint(distance);
            HasPointerWorldTarget = true;
        }

        private void HandleMoveToCursorInput()
        {
            if (moveToCursorAction == null || !HasPointerWorldTarget) return;
            if (!moveToCursorAction.IsPressed()) return;

            hasDestination = true;
            destination = PointerWorldTarget;
        }

        private void TickDestinationMovement(float deltaTime)
        {
            var horizontal = Vector3.zero;

            if (hasDestination && !IsMovementRestricted)
            {
                var toDestination = destination - transform.position;
                toDestination.y = 0f;

                if (toDestination.sqrMagnitude <= ArrivalThreshold * ArrivalThreshold)
                {
                    hasDestination = false;
                }
                else
                {
                    var maxHorizontalStep = moveSpeed * Mathf.Max(0f, deltaTime);
                    if (toDestination.sqrMagnitude <= maxHorizontalStep * maxHorizontalStep)
                    {
                        horizontal = deltaTime > 0f ? toDestination / deltaTime : Vector3.zero;
                        hasDestination = false;
                    }
                    else
                    {
                        horizontal = toDestination.normalized * moveSpeed;
                    }
                }
            }

            var move = new Vector3(horizontal.x, VerticalGroundingOffset, horizontal.z);
            controller.Move(move * deltaTime);

            if (horizontal.sqrMagnitude > MovementThreshold)
            {
                interactionController?.OnPlayerMoved();
            }
        }

        private void ApplyGrounding(float deltaTime)
        {
            controller.Move(new Vector3(0f, VerticalGroundingOffset, 0f) * deltaTime);
        }

        /// AC-003: owner-controlled movement-restriction interface consumed by Charged
        /// Fireball while charging. Reference-counted so overlapping requests don't let one
        /// release prematurely clear a restriction another requester still needs.
        public void RequestMovementRestriction()
        {
            movementRestrictionCount++;
        }

        public void ReleaseMovementRestriction()
        {
            if (movementRestrictionCount <= 0) return;
            movementRestrictionCount--;
        }

        /// AC-004: owner-controlled reset entry point consumed by the Floor Run/Restart
        /// Orchestrator. Restores position/rotation to the floor's initial state and clears
        /// all owned movement state, including re-enabling gameplay input.
        public void ResetMovement()
        {
            hasDestination = false;
            movementRestrictionCount = 0;
            IsGameplayEnabled = true;

            controller.enabled = false;
            transform.SetPositionAndRotation(initialPosition, initialRotation);
            controller.enabled = true;
        }

        /// AC-005: owner-controlled gameplay-enable/suspend interface consumed by the
        /// Game Flow/Victory capability. Immediately cancels any in-progress click-to-
        /// destination approach and causes further movement input to be ignored until an
        /// authorized reset/re-enable call is made.
        public void SuspendGameplayInput()
        {
            IsGameplayEnabled = false;
            hasDestination = false;
        }

        public void EnableGameplayInput()
        {
            IsGameplayEnabled = true;
        }
    }
}
