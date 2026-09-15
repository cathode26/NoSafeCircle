using System;
using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    // Runs after EnemyPursuitMovement.Update regardless of component order. Pursuit remains
    // the sole target-knowledge driver; this component only replaces its pursuing path.
    [DefaultExecutionOrder(100)]
    [DisallowMultipleComponent]
    [RequireComponent(typeof(NavMeshAgent), typeof(EnemyTargetKnowledge), typeof(EnemyPursuitMovement))]
    public sealed class RangedEnemyKeepDistanceMovement : MonoBehaviour
    {
        private const float ArrivalTolerance = 0.25f;
        private const float SampleRadius = 0.7f;
        private const float MinimumSeparationGain = 0.1f;

        [SerializeField] private float closeDistance = 2f;
        [SerializeField] private float farDistance = 4f;
        [SerializeField] private float repositionDistance = 2f;

        private NavMeshAgent agent;
        private EnemyTargetKnowledge targetKnowledge;
        private EnemyPursuitMovement pursuitMovement;
        private NavMeshPath candidatePath;
        private bool hasRepositionDestination;
        private Vector3 repositionDestination;

        private void Awake()
        {
            ResolveReferences();
            candidatePath = new NavMeshPath();
        }

        private void ResolveReferences()
        {
            if (agent == null) agent = GetComponent<NavMeshAgent>();
            if (targetKnowledge == null) targetKnowledge = GetComponent<EnemyTargetKnowledge>();
            if (pursuitMovement == null) pursuitMovement = GetComponent<EnemyPursuitMovement>();
        }

        public void ConfigureDistances(float close, float far)
        {
            ResolveReferences();
            if (!IsValidBand(close, far))
                throw new ArgumentException("Keep-distance limits require 0 < close < far < LoseTargetDistance.");
            closeDistance = close;
            farDistance = far;
            hasRepositionDestination = false;
        }

        private bool IsValidBand(float close, float far)
        {
            return targetKnowledge != null && close > 0f && close < far && far < targetKnowledge.LoseTargetDistance;
        }

        private void Update()
        {
            ResolveReferences();
            if (agent == null || targetKnowledge == null || pursuitMovement == null || !agent.isOnNavMesh)
                return;

            if (targetKnowledge.State != EnemyTargetKnowledgeState.Pursuing || targetKnowledge.CurrentTarget == null)
            {
                hasRepositionDestination = false;
                return; // Leave search and idle destinations to pursuit.
            }

            if (!IsValidBand(closeDistance, farDistance))
            {
                Hold();
                return;
            }

            var targetPosition = targetKnowledge.CurrentTarget.position;
            var separation = Vector3.Distance(transform.position, targetPosition);
            if (separation > farDistance)
            {
                hasRepositionDestination = false;
                return; // Pursuit's targetward destination remains in effect.
            }

            if (separation >= closeDistance)
            {
                Hold();
                return;
            }

            if (hasRepositionDestination &&
                Vector3.Distance(transform.position, repositionDestination) > ArrivalTolerance &&
                IsCompletePath(repositionDestination))
            {
                if (TrySetRepositionDestination(repositionDestination)) return;
            }

            hasRepositionDestination = false;
            if (TrySelectReposition(targetPosition, separation, out var destination))
            {
                repositionDestination = destination;
                hasRepositionDestination = true;
                if (!TrySetRepositionDestination(destination)) Hold();
            }
            else
            {
                Hold();
            }
        }

        private bool TrySelectReposition(Vector3 targetPosition, float separation, out Vector3 destination)
        {
            var away = transform.position - targetPosition;
            away.y = 0f;
            if (away.sqrMagnitude < 0.0001f) away = transform.forward;
            away.Normalize();

            // Direct retreat first, then deterministic right and left lateral routes.
            var right = new Vector3(away.z, 0f, -away.x);
            var directions = new[] { away, right, -right };
            for (var index = 0; index < directions.Length; index++)
            {
                var desired = transform.position + directions[index] * repositionDistance;
                if (!NavMesh.SamplePosition(desired, out var hit, SampleRadius, NavMesh.AllAreas)) continue;
                if (Vector3.Distance(hit.position, targetPosition) <= separation + MinimumSeparationGain) continue;
                // A path around a wall to the straight-behind point is not a direct
                // retreat. Prefer a reachable lateral route in that case.
                if (index == 0 && NavMesh.Raycast(transform.position, hit.position, out _, NavMesh.AllAreas))
                    continue;
                if (!IsCompletePath(hit.position)) continue;
                destination = hit.position;
                return true;
            }

            destination = default;
            return false;
        }

        private bool IsCompletePath(Vector3 destination)
        {
            if (candidatePath == null) candidatePath = new NavMeshPath();
            return NavMesh.CalculatePath(transform.position, destination, NavMesh.AllAreas, candidatePath) &&
                   candidatePath.status == NavMeshPathStatus.PathComplete;
        }

        // Callers validate the same destination with IsCompletePath immediately before
        // this call, so candidatePath is the complete path to that destination.
        private bool TrySetRepositionDestination(Vector3 destination)
        {
            // EnemyPursuitMovement requests a targetward path every Update while
            // Pursuing. A second SetDestination only queues another request, so the
            // agent still reports the pursuit destination when the frame ends and
            // NSC-053 VAL-003 samples it. Cancel that request and assign the path this
            // component already calculated for the same destination, which applies
            // immediately without waiting for Unity's path queue.
            if (candidatePath == null || candidatePath.status != NavMeshPathStatus.PathComplete)
                return false;
            if (agent.pathPending) agent.ResetPath();
            return agent.SetPath(candidatePath);
        }

        private void Hold()
        {
            hasRepositionDestination = false;
            // Pursuit may have just requested a still-pending path, for which hasPath is
            // false. Reset unconditionally so no targetward request survives this frame.
            if (agent != null && agent.isOnNavMesh) agent.ResetPath();
        }

        public void ResetKeepDistanceMovement()
        {
            Hold();
        }

        private void OnDisable() => ResetKeepDistanceMovement();
        private void OnDestroy() => ResetKeepDistanceMovement();
    }
}
