using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.InputSystem;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    [RequireComponent(typeof(CharacterController))]
    public class PlayerMovement : MonoBehaviour
    {
        private const float MovementThreshold = 0.001f;
        private const float ArrivalThreshold = 0.05f;
        private const float VerticalGroundingOffset = -0.1f;

        // A clicked destination can still be unreachable even with NavMesh steering - either
        // because no baked NavMesh covers this scene at all (RecomputeNavMeshPath falls back to
        // the pre-pathfinding direct-line behaviour below), or because the residual stretch past
        // the end of a PathPartial route runs into geometry the CharacterController itself has to
        // resolve. Do not keep an unreachable destination alive forever: after a short period of
        // side-collision with negligible progress toward the target, settle the movement state as
        // stopped. This is now a backstop rather than the only defence against a blocked route.
        private const float BlockedDestinationTimeout = 0.2f;
        private const float MinimumForwardProgressFraction = 0.05f;
        private const float MinimumForwardProgressDistance = 0.001f;

        // Tolerance used to snap a raw world point (the player's own position, or a clicked
        // destination) onto the baked NavMesh. Generous enough to reliably find real NavMesh data
        // when a GameplayNavigationSurface has actually baked one, but irrelevant to scenes with
        // no baked NavMesh at all (e.g. isolated component tests) since NavMesh.SamplePosition
        // fails there regardless of tolerance - there is no triangulated data to find.
        private const float NavMeshSampleTolerance = 1f;

        // How close to the current path corner counts as "reached" before advancing to the next
        // one. Slightly looser than ArrivalThreshold so the wizard starts turning toward the next
        // corner a little before exactly touching this one, rather than clipping the turn.
        private const float CornerAdvanceThreshold = 0.15f;

        [SerializeField] private float moveSpeed = 4f;
        [SerializeField] private float gameplayPlaneHeight = 0f;
        [SerializeField] private InputActionAsset inputActions;
        [SerializeField] private PlayerInteractionController interactionController;

        private CharacterController controller;
        private Camera mainCamera;
        private InputAction pointerPositionAction;
        private InputAction moveToCursorAction;
        private InputAction holdPositionAction;

        private Vector3 initialPosition;
        private Quaternion initialRotation;

        private bool hasDestination;
        private Vector3 destination;
        private int movementRestrictionCount;
        private float blockedDestinationTime;
        private bool wasMoveToCursorPressed;
        private bool isHoldingPositionRestriction;
        private bool mousePressStartedOverUi;
        private bool ignoreMouseUntilRelease;
        public bool UseMobileWorldInput { get; private set; }
        public void SetMobileWorldInputEnabled(bool enabled) => UseMobileWorldInput = enabled;
        public event Action MobileFireHoldsCleared;
        public bool IsMobileFireHeld(MobileFireMode mode) => mode == MobileFireMode.StandAndFire
            ? standingFirePointers.Count > 0 : mode == MobileFireMode.FireWhileMoving && movingFirePointers.Count > 0;
        private readonly HashSet<int> movingFirePointers = new HashSet<int>();
        private readonly HashSet<int> standingFirePointers = new HashSet<int>();
        private readonly List<RaycastResult> uiHits = new List<RaycastResult>();

        public MobileFireMode CurrentMobileFireMode => standingFirePointers.Count > 0
            ? MobileFireMode.StandAndFire
            : movingFirePointers.Count > 0 ? MobileFireMode.FireWhileMoving : MobileFireMode.None;

        /// <summary>A world tap while a mobile fire modifier is held; the bound spell owner casts it.</summary>
        public event Action<Vector3> WorldFireRequested;

        public void SetMobileFireHeld(MobileFireMode mode, int pointerId, bool held)
        {
            if (mode == MobileFireMode.None || (held && !IsGameplayEnabled)) return;
            HashSet<int> pointers = mode == MobileFireMode.StandAndFire
                ? standingFirePointers : movingFirePointers;
            if (!held)
            {
                if (pointers.Remove(pointerId) && CurrentMobileFireMode == MobileFireMode.None
                    && moveToCursorAction != null && moveToCursorAction.IsPressed())
                    ignoreMouseUntilRelease = true;
                return;
            }
            if (!pointers.Add(pointerId)) return;
            if (mode == MobileFireMode.StandAndFire)
            {
                // Cancel, rather than pause: neither the path nor a pending door timer can resume.
                interactionController?.CancelDoorCommand();
                ClearDestination();
                ignoreMouseUntilRelease = moveToCursorAction != null && moveToCursorAction.IsPressed();
            }
        }

        public void ClearMobileFireHolds()
        {
            if (CurrentMobileFireMode != MobileFireMode.None)
                ignoreMouseUntilRelease = moveToCursorAction != null && moveToCursorAction.IsPressed();
            movingFirePointers.Clear();
            standingFirePointers.Clear();
            MobileFireHoldsCleared?.Invoke();
        }

        /// <summary>One fresh UI world pointer, with its own aim position (never the held button finger).</summary>
        public void HandleWorldTap(Vector2 screenPosition)
        {
            if (!IsGameplayEnabled || !TryProjectPointer(screenPosition, out Vector3 target)) return;
            PointerWorldTarget = target;
            HasPointerWorldTarget = true;
            if (CurrentMobileFireMode != MobileFireMode.None)
            {
                WorldFireRequested?.Invoke(target);
                return;
            }
            if (IsHoldPositionHeld) return;
            if (interactionController != null && interactionController.TryBeginDoorApproach(target)) return;
            SetDestination(target);
        }

        public bool TryProjectPointer(Vector2 screenPosition, out Vector3 target)
        {
            target = default;
            if (mainCamera == null) mainCamera = Camera.main;
            if (mainCamera == null) return false;
            Ray ray = mainCamera.ScreenPointToRay(screenPosition);
            var plane = new Plane(Vector3.up, new Vector3(0f, gameplayPlaneHeight, 0f));
            if (!plane.Raycast(ray, out float distance)) return false;
            target = ray.GetPoint(distance);
            return true;
        }

        /// <summary>Raycast this pointer directly; EventSystem's cached/any-pointer query is unsuitable for multitouch.</summary>
        public bool IsPointerOverGameplayUi(Vector2 screenPosition)
        {
            EventSystem events = EventSystem.current;
            if (events == null) return false;
            uiHits.Clear();
            events.RaycastAll(new PointerEventData(events) { position = screenPosition }, uiHits);
            foreach (RaycastResult hit in uiHits)
                if (hit.module is GraphicRaycaster) return true;
            return false;
        }

        private void OnApplicationFocus(bool focused)
        {
            if (!focused) ClearMobileFireHolds();
        }

        private void OnApplicationPause(bool paused)
        {
            if (paused) ClearMobileFireHolds();
        }

        // AC (this fix): follows a baked NavMesh route around obstacles to the requested
        // destination via NavMesh.CalculatePath, walked with the existing CharacterController -
        // deliberately not a NavMeshAgent (see PlayerMovement.cs's exclusive_resources owners
        // NSC-019/NSC-128, whose public surface below this component depends on collision
        // response staying CharacterController-driven). hasNavMeshPath is false whenever no
        // baked NavMesh is found near the player at all, which is the normal state for isolated
        // component tests (PlayerMovementPlayModeTests and friends never bake one) and exactly
        // reproduces the pre-pathfinding direct-line behaviour for them.
        private NavMeshPath navMeshPath;
        private Vector3[] pathCorners = Array.Empty<Vector3>();
        private int pathCornerIndex;
        private bool hasNavMeshPath;

        /// Shared world-space pointer target (AC-002), produced by projecting the cursor
        /// onto the gameplay plane. Consumers (cursor-aimed spells, Door/Interaction) read
        /// this instead of independently projecting screen coordinates.
        public Vector3 PointerWorldTarget { get; private set; }
        public bool HasPointerWorldTarget { get; private set; }

        public bool IsMovementRestricted => movementRestrictionCount > 0
            || CurrentMobileFireMode == MobileFireMode.StandAndFire;
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
            holdPositionAction = playerMap.FindAction("HoldPosition", false);

            if (pointerPositionAction == null || moveToCursorAction == null)
            {
                Debug.LogWarning("PlayerMovement could not find the 'PointerPosition' and/or 'MoveToCursor' " +
                    "actions on the Player action map.");
            }

            if (holdPositionAction == null)
            {
                Debug.LogWarning("PlayerMovement could not find the 'HoldPosition' action on the Player action " +
                    "map; holding Z to suppress movement will be unavailable.");
            }
        }

        private void OnEnable()
        {
            pointerPositionAction?.Enable();
            moveToCursorAction?.Enable();
            holdPositionAction?.Enable();
        }

        private void OnDisable()
        {
            ClearMobileFireHolds();
            pointerPositionAction?.Disable();
            moveToCursorAction?.Disable();
            holdPositionAction?.Disable();
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

            HandleHoldPositionInput();
            HandleMoveToCursorInput();
            TickDestinationMovement(deltaTime);
        }

        /// AC-001/AC-002: reads only the 'HoldPosition' action (no hardware polling). True for
        /// exactly as long as the Z key is held.
        private bool IsHoldPositionHeld => holdPositionAction != null && holdPositionAction.IsPressed();

        /// AC-002/AC-003: holds/releases the existing reference-counted movement restriction for
        /// exactly as long as the action is held, so a Fireball charge held across the same
        /// press/release composes with this one instead of fighting it.
        private void HandleHoldPositionInput()
        {
            var isPressed = IsHoldPositionHeld;

            if (isPressed && !isHoldingPositionRestriction)
            {
                RequestMovementRestriction();
                isHoldingPositionRestriction = true;
            }
            else if (!isPressed && isHoldingPositionRestriction)
            {
                ReleaseMovementRestriction();
                isHoldingPositionRestriction = false;
            }
        }

        private void UpdatePointerWorldTarget()
        {
            HasPointerWorldTarget = false;

            if (pointerPositionAction == null) return;

            if (TryProjectPointer(pointerPositionAction.ReadValue<Vector2>(), out Vector3 target))
            {
                PointerWorldTarget = target;
                HasPointerWorldTarget = true;
            }
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
            if (!isPressed)
            {
                mousePressStartedOverUi = false;
                ignoreMouseUntilRelease = false;
            }
            // Touch UI owns all mobile world gestures; compatibility mouse events must not replay them.
            if (UseMobileWorldInput || Application.isMobilePlatform || Touchscreen.current != null) return;
            if (isFreshPress)
                mousePressStartedOverUi = IsPointerOverGameplayUi(pointerPositionAction.ReadValue<Vector2>());
            if (mousePressStartedOverUi || ignoreMouseUntilRelease) return;
            // Mobile world taps arrive through the UI surface, once per pointer-down.
            if (CurrentMobileFireMode != MobileFireMode.None) return;

            // AC-005: while Z is held, a fresh press starts no destination and no door
            // approach. wasMoveToCursorPressed above is still updated while held, so a press
            // held across Z's release is not replayed/queued as a fresh press once Z
            // comes back up.
            if (IsHoldPositionHeld) return;

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
                RecomputeNavMeshPath(worldPosition);
            }

            hasDestination = true;
            destination = worldPosition;
        }

        // Computes a NavMesh route from the player's current position to the requested
        // destination, snapping both endpoints onto the baked NavMesh within
        // NavMeshSampleTolerance. Leaves hasNavMeshPath false (falling back to the original
        // direct-line steering in TickDestinationMovement) whenever there is nothing useful to
        // route with: no baked NavMesh near the player at all, the destination too far off any
        // NavMesh to snap onto, or a degenerate/invalid CalculatePath result. A PathPartial result
        // is still accepted - TickDestinationMovement walks its reachable corners and then falls
        // through to the same direct-line behaviour for whatever residual stretch remains, so an
        // unreachable click still eventually settles via BlockedDestinationTimeout exactly as it
        // did before this method existed.
        private void RecomputeNavMeshPath(Vector3 target)
        {
            hasNavMeshPath = false;
            pathCornerIndex = 0;

            if (!NavMesh.SamplePosition(transform.position, out var startHit, NavMeshSampleTolerance,
                    NavMesh.AllAreas))
            {
                return;
            }

            if (!NavMesh.SamplePosition(target, out var endHit, NavMeshSampleTolerance, NavMesh.AllAreas))
            {
                return;
            }

            if (navMeshPath == null) navMeshPath = new NavMeshPath();

            if (!NavMesh.CalculatePath(startHit.position, endHit.position, NavMesh.AllAreas, navMeshPath) ||
                navMeshPath.status == NavMeshPathStatus.PathInvalid ||
                navMeshPath.corners.Length < 2)
            {
                return;
            }

            // corners[0] is the sampled START position (already reached); steer toward corners[1]
            // onward. Once pathCornerIndex reaches corners.Length, TickDestinationMovement's
            // steering target naturally falls back to the raw `destination` for the final
            // stretch/residual - see AdvancePathCornersIfReached and TickDestinationMovement.
            pathCorners = navMeshPath.corners;
            pathCornerIndex = 1;
            hasNavMeshPath = true;
        }

        // Advances past any path corners already within CornerAdvanceThreshold of the player's
        // current position, so a corner reached mid-tick does not stall steering until next tick.
        private void AdvancePathCornersIfReached()
        {
            if (!hasNavMeshPath) return;

            while (pathCornerIndex < pathCorners.Length)
            {
                var toCorner = pathCorners[pathCornerIndex] - transform.position;
                toCorner.y = 0f;
                if (toCorner.sqrMagnitude > CornerAdvanceThreshold * CornerAdvanceThreshold) break;
                pathCornerIndex++;
            }
        }

        /// Narrow owner-controlled destination-request extension consumed by Door/Interaction to
        /// issue the combined approach-and-interact request (AC-001/AC-002) without independently
        /// projecting screen coordinates or polling pointer hardware.
        public void RequestDestination(Vector3 worldPosition)
        {
            if (!IsGameplayEnabled || CurrentMobileFireMode == MobileFireMode.StandAndFire) return;

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
                AdvancePathCornersIfReached();

                // Arrival is always measured against the real requested destination, never an
                // intermediate path corner, so DestinationReached keeps firing on exactly the
                // same condition it always did (AC-002's "genuinely arrived at" contract, which
                // NSC-019's click-to-approach timer depends on).
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

                    // Steer toward the current NavMesh path corner when one is available;
                    // otherwise (no baked NavMesh near the player, an off-mesh click beyond
                    // NavMeshSampleTolerance, or the path's corners already exhausted - including
                    // the residual stretch past the end of a PathPartial route) steer straight at
                    // the real destination exactly as before pathfinding existed.
                    var steeringTarget = (hasNavMeshPath && pathCornerIndex < pathCorners.Length)
                        ? pathCorners[pathCornerIndex]
                        : destination;
                    var toSteeringTarget = steeringTarget - transform.position;
                    toSteeringTarget.y = 0f;

                    if (toSteeringTarget.sqrMagnitude <= expectedHorizontalStep * expectedHorizontalStep)
                    {
                        horizontal = deltaTime > 0f ? toSteeringTarget / deltaTime : Vector3.zero;
                    }
                    else
                    {
                        horizontal = toSteeringTarget.normalized * moveSpeed;
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
            hasNavMeshPath = false;
            pathCornerIndex = 0;
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
            ClearMobileFireHolds();
            ClearDestination();
            movementRestrictionCount = 0;
            isHoldingPositionRestriction = false;
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
            ClearMobileFireHolds();
            ClearDestination();

            // AC-003: a title-screen transition mid-hold must not strand this restriction;
            // release it here rather than waiting for a Z release that may never come
            // while gameplay input is suspended.
            if (isHoldingPositionRestriction)
            {
                ReleaseMovementRestriction();
                isHoldingPositionRestriction = false;
            }
        }

        public void EnableGameplayInput()
        {
            IsGameplayEnabled = true;
        }
    }
}
