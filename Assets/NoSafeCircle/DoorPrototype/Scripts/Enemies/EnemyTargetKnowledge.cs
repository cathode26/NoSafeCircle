using System;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    /// Pursuit/search phase owned by EnemyTargetKnowledge. Movement consumes this to
    /// decide navigation without EnemyTargetKnowledge ever choosing a destination itself.
    public enum EnemyTargetKnowledgeState
    {
        Idle,
        Pursuing,
        SearchingLastKnownPosition,
        Wandering
    }

    /// Owns one enemy's target identity, last-known-position, and bounded search/wander
    /// state per the GDD's Enemy Detection, Pursuit, and Target Loss rules. This component
    /// never sets a NavMeshAgent destination, chooses a wander point, or moves the enemy
    /// Transform; movement consumes its read-only state and calls its movement-facing
    /// transition/reset methods through a one-way dependency.
    public class EnemyTargetKnowledge : MonoBehaviour
    {
        [SerializeField] private Transform wizardTransform;
        [SerializeField] private float detectionDistance = 6f;
        [SerializeField] private float loseTargetDistance = 10f;
        [SerializeField] private float searchDuration = 5f;

        private float searchTimeRemaining;

        public float DetectionDistance => detectionDistance;
        public float LoseTargetDistance => loseTargetDistance;
        public float SearchDuration => searchDuration;

        public EnemyTargetKnowledgeState State { get; private set; } = EnemyTargetKnowledgeState.Idle;
        public Transform CurrentTarget { get; private set; }
        public bool HasTarget => CurrentTarget != null;
        public Vector3 LastKnownPosition { get; private set; }
        public float SearchTimeRemaining => searchTimeRemaining;

        private void Awake()
        {
            ValidateDistances(detectionDistance, loseTargetDistance);

            // startPosition/hasStartPosition are deliberately not serialized, so the leash must
            // anchor itself here rather than relying on IsBeyondPursuitLeash being reached. The
            // sight test is evaluated first in the acquisition chain, so a lazy anchor would
            // never initialize while sight is blocked - and would then measure distance from
            // world origin, which for an enemy at Z 53 exceeds any leash and silently prevents
            // it from ever acquiring the wizard.
            startPosition = transform.position;
            hasStartPosition = true;
        }

        private void OnValidate()
        {
            if (loseTargetDistance <= detectionDistance)
            {
                loseTargetDistance = detectionDistance + 0.01f;
            }
        }

        /// Wires the wizard Transform this enemy checks distance against. Movement or a
        /// test fixture supplies this independently of the inspector-assigned field.
        public void Initialize(Transform wizard)
        {
            wizardTransform = wizard;
        }

        /// Owner-controlled configuration entry point that enforces the GDD's strict
        /// Detection Distance &lt; Lose Target Distance relationship. Throws rather than
        /// silently accepting an authoring value that would cause acquire/lose flicker.
        public void ConfigureDistances(float newDetectionDistance, float newLoseTargetDistance)
        {
            ValidateDistances(newDetectionDistance, newLoseTargetDistance);

            detectionDistance = newDetectionDistance;
            loseTargetDistance = newLoseTargetDistance;
        }

        private static void ValidateDistances(float candidateDetectionDistance, float candidateLoseTargetDistance)
        {
            if (candidateDetectionDistance >= candidateLoseTargetDistance)
            {
                throw new ArgumentException(
                    "Detection Distance must be strictly smaller than Lose Target Distance.");
            }
        }

        /// Movement-facing per-tick evaluation. Movement calls this every frame it advances
        /// (or a test drives it directly) so target acquisition, distance-only target loss,
        /// and bounded search expiry stay solely a function of distance and elapsed time.
        /// The wander/search interval is time-bounded on its own: it keeps counting down and
        /// still expires even if the wired wizard Transform is destroyed or unbound mid-search.
        public void UpdateTargetKnowledge(float deltaTime)
        {
            if (wizardTransform != null)
            {
                var distanceToWizard = Vector3.Distance(transform.position, wizardTransform.position);

                if (State != EnemyTargetKnowledgeState.Pursuing
                    && distanceToWizard <= detectionDistance
                    && HasUnobstructedViewOfWizard()
                    && !IsBeyondPursuitLeash())
                {
                    AcquireTarget();
                    return;
                }

                // Dragged too far from its post: give up and head back rather than following
                // the wizard onto a doorway.
                if (State == EnemyTargetKnowledgeState.Pursuing && IsBeyondPursuitLeash())
                {
                    LastKnownPosition = startPosition;
                    State = EnemyTargetKnowledgeState.SearchingLastKnownPosition;
                    searchTimeRemaining = 0f;
                    return;
                }

                if (State == EnemyTargetKnowledgeState.Pursuing && distanceToWizard > loseTargetDistance)
                {
                    LastKnownPosition = wizardTransform.position;
                    State = EnemyTargetKnowledgeState.SearchingLastKnownPosition;
                    searchTimeRemaining = 0f;
                    return;
                }
            }

            if (State == EnemyTargetKnowledgeState.Wandering)
            {
                searchTimeRemaining -= deltaTime;

                if (searchTimeRemaining <= 0f)
                {
                    ClearTarget();
                }
            }
        }

        /// Demo-scoped sight rule. Off by default so existing component tests keep the
        /// distance-only acquisition contract they assert; the scene builder turns it on for
        /// the enemies it authors so a closed door actually hides the wizard. Solid gameplay
        /// colliders (wall boxes, a door's enabled doorwayBlocker) block the view; triggers
        /// such as the door's own range volume are ignored.
        [SerializeField] private bool requiresLineOfSight;

        /// Demo-scoped leash. Zero means unlimited, which is the behavior every existing test
        /// asserts. When set, the enemy gives up once it has been dragged this far from where
        /// it started, so it can never follow the wizard onto a doorway and camp the threshold
        /// the wizard is about to walk through.
        [SerializeField, Min(0f)] private float maximumPursuitDistanceFromStart;

        private Vector3 startPosition;
        private bool hasStartPosition;

        public void SetRequiresLineOfSight(bool required)
        {
            requiresLineOfSight = required;
        }

        public void SetMaximumPursuitDistanceFromStart(float distance)
        {
            maximumPursuitDistanceFromStart = Mathf.Max(0f, distance);
            startPosition = transform.position;
            hasStartPosition = true;
        }

        private bool IsBeyondPursuitLeash()
        {
            if (maximumPursuitDistanceFromStart <= 0f) return false;

            if (!hasStartPosition)
            {
                startPosition = transform.position;
                hasStartPosition = true;
            }

            var fromStart = transform.position - startPosition;
            fromStart.y = 0f;
            return fromStart.magnitude > maximumPursuitDistanceFromStart;
        }

        private bool HasUnobstructedViewOfWizard()
        {
            if (!requiresLineOfSight || wizardTransform == null) return true;

            // Sample at chest height so the ground plane itself never counts as an occluder.
            var eye = transform.position + Vector3.up;
            var target = wizardTransform.position + Vector3.up;
            var toTarget = target - eye;
            var distance = toTarget.magnitude;
            if (distance <= 0.01f) return true;

            if (!Physics.Raycast(eye, toTarget / distance, out RaycastHit hit, distance,
                    Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore))
            {
                return true;
            }

            // The wizard's own CharacterController sits at the end of this ray, so hitting it
            // means the view is clear. Anything else in the way is a real occluder.
            return hit.transform == wizardTransform || hit.transform.IsChildOf(wizardTransform);
        }

        private void AcquireTarget()
        {
            CurrentTarget = wizardTransform;
            State = EnemyTargetKnowledgeState.Pursuing;
            searchTimeRemaining = 0f;
        }

        /// Movement-facing transition entry point: movement calls this once its owned
        /// arrival check reports the enemy reached the recorded last known position, which
        /// starts the bounded wander/search interval.
        public void ReportArrivedAtLastKnownPosition()
        {
            if (State != EnemyTargetKnowledgeState.SearchingLastKnownPosition) return;

            State = EnemyTargetKnowledgeState.Wandering;
            searchTimeRemaining = searchDuration;
        }

        private void ClearTarget()
        {
            State = EnemyTargetKnowledgeState.Idle;
            CurrentTarget = null;
            LastKnownPosition = Vector3.zero;
            searchTimeRemaining = 0f;
        }

        /// Restores the floor-initial target-knowledge state (idle, no target, no
        /// last-known position, no search timer), for use by owner-controlled floor-restart
        /// orchestration. Never destroys, disables, or replaces the enemy GameObject.
        public void ResetTargetKnowledge()
        {
            ClearTarget();
        }
    }
}
