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

                if (State != EnemyTargetKnowledgeState.Pursuing && distanceToWizard <= detectionDistance)
                {
                    AcquireTarget();
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
