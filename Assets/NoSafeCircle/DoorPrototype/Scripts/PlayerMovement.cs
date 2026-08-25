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

        // A clicked destination can be unreachable because CharacterController collision
        // prevents the wizard from making forward progress. Do not keep an unreachable
        // destination alive forever: after a short period of side-collision with negligible
        // progress toward the target, settle the movement state as stopped.
        private const float BlockedDestinationTimeout = 0.2f;
        private const float MinimumForwardProgressFraction = 0.05f;
        private const float MinimumForwardProgressDistance = 0.001f;

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
        private float blockedDestinationTime;
        private bool wasMoveToCursorPressed;

        /// Shared world-space pointer target (AC-002), produced by projecting the cursor
        /// onto the gameplay plane. Consumers (cursor-aimed spells, Door/Interaction) read
        /// this instead of independently projecting screen coordinates.
        public Vector3 PointerWorldTarget { get; private set; }
        public bool HasPointerWorldTarget { get; private set; }

        public bool IsMovementRestricted => movementRestrictionCount > 0;
        public bool IsGameplayEnabled { get; private set; } = true;
        public bool HasActiveDestination => hasDestination;

        /// AC-002: fires when an active destination is genuinely arrived at (not when an
        /// unreachable destination is cancelled after sustained blocked progress). Door and
        /// Interaction consumes this to know when its click-to-approach request has actually
        /// completed, instead of relying on arm's-reach trigger timing alone.
        public event System.Action DestinationReached;

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

            var isPressed = moveToCursorAction.IsPressed();
            // Tracked against this component's own Tick cadence (one call per simulated/real
            // frame) rather than the Input System's internal update-step counter, so a fresh
            // press is detected exactly once regardless of how many Tick calls a caller makes
            // between two distinct input samples.
            var isFreshPress = isPressed && !wasMoveToCursorPressed;
            wasMoveToCursorPressed = isPressed;

            // AC-001: a fresh press is offered to Door/Interaction first, using the shared
            // pointer target this method already computed. If it hit a sealed door, Door and
            // Interaction has issued its own combined approach-and-interact destination request
            // and this click must not also be treated as a plain move-to-point click.
            if (isFreshPress &&
                interactionController != null && interactionController.TryBeginDoorApproach(PointerWorldTarget))
            {
                return;
            }

            // AC-003: while a door approach/interaction is pending, held-cursor drift must not
            // redirect the wizard away from the selected door.
            if (interactionController != null && interactionController.HasLockedDoorInteraction) return;

            if (!isPressed) return;

            SetDestination(PointerWorldTarget);
        }

        private void SetDestination(Vector3 worldPosition)
        {
            if (!hasDestination || HorizontalDistance(destination, worldPosition) > ArrivalThreshold)
            {
                blockedDestinationTime = 0f;
            }

            hasDestination = true;
            destination = worldPosition;
        }

        /// Narrow owner-controlled destination-request extension consumed by Door/Interaction to
        /// issue the combined approach-and-interact request (AC-001/AC-002) without independently
        /// projecting screen coordinates or polling pointer hardware.
        public void RequestDestination(Vector3 worldPosition)
        {
            if (!IsGameplayEnabled) return;

            SetDestination(worldPosition);
        }

        /// AC-004/AC-006: owner-controlled cancellation counterpart to RequestDestination.
        /// Consumed by Door/Interaction when it cancels a pending or in-progress door
        /// interaction (on suspend, on damage, or when replaced by another command) so a
        /// stale door-approach destination does not keep driving movement after the door
        /// request itself has already been cancelled.
        public void CancelRequestedDestination()
        {
            ClearDestination();
        }

        private void TickDestinationMovement(float deltaTime)
        {
            var horizontal = Vector3.zero;
            var attemptedDestinationMovement = false;
            var distanceBeforeMove = 0f;
            var expectedHorizontalStep = 0f;

            if (hasDestination && !IsMovementRestricted)
            {
                var toDestination = destination - transform.position;
                toDestination.y = 0f;

                if (toDestination.sqrMagnitude <= ArrivalThreshold * ArrivalThreshold)
                {
                    ClearDestination();
                    DestinationReached?.Invoke();
                }
                else
                {
                    attemptedDestinationMovement = true;
                    distanceBeforeMove = toDestination.magnitude;
                    expectedHorizontalStep = moveSpeed * Mathf.Max(0f, deltaTime);

                    if (toDestination.sqrMagnitude <= expectedHorizontalStep * expectedHorizontalStep)
                    {
                        horizontal = deltaTime > 0f ? toDestination / deltaTime : Vector3.zero;
                    }
                    else
                    {
                        horizontal = toDestination.normalized * moveSpeed;
                    }
                }
            }

            var positionBeforeMove = transform.position;
            var move = new Vector3(horizontal.x, VerticalGroundingOffset, horizontal.z);
            var collisionFlags = controller.Move(move * deltaTime);

            // Interaction cancellation must reflect what the CharacterController actually
            // moved, not what movement wanted to do. A blocked wall push is not real player
            // movement just because the requested velocity was non-zero.
            var actualHorizontalDisplacement = transform.position - positionBeforeMove;
            actualHorizontalDisplacement.y = 0f;
            if (actualHorizontalDisplacement.sqrMagnitude > MovementThreshold * MovementThreshold)
            {
                interactionController?.OnPlayerMoved();
            }

            if (!attemptedDestinationMovement || !hasDestination)
            {
                blockedDestinationTime = 0f;
                return;
            }

            var distanceAfterMove = HorizontalDistance(transform.position, destination);
            if (distanceAfterMove <= ArrivalThreshold)
            {
                // This frame's own approach movement (handled above via OnPlayerMoved) must not
                // be treated as the interaction-cancelling "moved away" case just because arrival
                // and displacement land in the same frame: DestinationReached fires only after
                // hasDestination has already been cleared, so Door/Interaction starts its timer
                // from a state where no further approach movement is pending.
                ClearDestination();
                DestinationReached?.Invoke();
                return;
            }

            var forwardProgress = Mathf.Max(0f, distanceBeforeMove - distanceAfterMove);
            var minimumExpectedProgress = Mathf.Max(
                MinimumForwardProgressDistance,
                expectedHorizontalStep * MinimumForwardProgressFraction);
            var blockedBySideCollision = (collisionFlags & CollisionFlags.Sides) != 0;

            if (blockedBySideCollision && forwardProgress < minimumExpectedProgress)
            {
                blockedDestinationTime += Mathf.Max(0f, deltaTime);
                if (blockedDestinationTime >= BlockedDestinationTimeout)
                {
                    ClearDestination();
                }
            }
            else
            {
                blockedDestinationTime = 0f;
            }
        }

        private static float HorizontalDistance(Vector3 a, Vector3 b)
        {
            var offset = a - b;
            offset.y = 0f;
            return offset.magnitude;
        }

        private void ClearDestination()
        {
            hasDestination = false;
            blockedDestinationTime = 0f;
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
            ClearDestination();
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
            ClearDestination();
        }

        public void EnableGameplayInput()
        {
            IsGameplayEnabled = true;
        }
    }
}
