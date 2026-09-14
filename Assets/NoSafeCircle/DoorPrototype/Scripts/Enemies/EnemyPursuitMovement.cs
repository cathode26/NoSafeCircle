using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    /// Movement/navigation owner for one enemy's locomotion (NSC-092). Consumes
    /// EnemyTargetKnowledge's read-only target/search state and calls its movement-facing
    /// ReportArrivedAtLastKnownPosition/ResetTargetKnowledge entry points; it never
    /// re-implements target-acquisition distance logic or writes EnemyTargetKnowledge's
    /// internal fields directly. All navigation goes through the shared NavMeshAgent/NavMesh
    /// GameplayNavigationSurface (NSC-089) already baked; this component never selects,
    /// instantiates, or configures a different pathfinding technology (AC-006).
    [DisallowMultipleComponent]
    [RequireComponent(typeof(NavMeshAgent))]
    public sealed class EnemyPursuitMovement : MonoBehaviour
    {
        private const int MaxWanderSampleAttempts = 8;

        [SerializeField] private NavMeshAgent agent;
        [SerializeField] private EnemyTargetKnowledge targetKnowledge;

        // Horizontal distance at which a requested destination (last known position or a
        // wander point) counts as reached.
        [SerializeField] private float destinationArrivalDistance = 0.5f;

        // AC-003: bounds how far a controlled-random wander/search point may be chosen from
        // the recorded last known position, keeping the search "short" and "bounded" rather
        // than letting the enemy wander arbitrarily far while searching.
        [SerializeField] private float wanderRadius = 4f;
        [SerializeField] private float wanderSampleMaxDistance = 2f;

        private Vector3 spawnPosition;
        private Quaternion spawnRotation;
        private bool hasWanderDestination;
        private Vector3 wanderDestination;

        private void Awake()
        {
            if (agent == null) agent = GetComponent<NavMeshAgent>();
            if (targetKnowledge == null) targetKnowledge = GetComponent<EnemyTargetKnowledge>();

            // AC-007: this enemy's own authored scene placement is a valid point in its
            // authored encounter/spawn region (the GDD only requires restart to land somewhere
            // valid within that region, not to reproduce a separately authored anchor), so the
            // position/rotation this component first wakes up with is recorded as the
            // floor-initial state to restore on ResetPursuit, mirroring PlayerMovement's own
            // initialPosition/initialRotation floor-restart convention.
            spawnPosition = transform.position;
            spawnRotation = transform.rotation;
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// Advances target knowledge and movement by deltaTime. Public so Play Mode tests can
        /// drive it deterministically without waiting on real frames, mirroring
        /// DoorInteractable.Tick/PlayerMana.Tick.
        public void Tick(float deltaTime)
        {
            if (targetKnowledge == null) return;

            // AC-001/AC-002/AC-003/AC-004: EnemyPursuitMovement is the sole production driver
            // of EnemyTargetKnowledge's per-tick evaluation, since it is the only consumer that
            // needs target/search state to decide navigation.
            targetKnowledge.UpdateTargetKnowledge(deltaTime);

            if (agent == null || !agent.isOnNavMesh) return;

            switch (targetKnowledge.State)
            {
                case EnemyTargetKnowledgeState.Pursuing:
                    HandlePursuing();
                    break;
                case EnemyTargetKnowledgeState.SearchingLastKnownPosition:
                    HandleSearching();
                    break;
                case EnemyTargetKnowledgeState.Wandering:
                    HandleWandering();
                    break;
                case EnemyTargetKnowledgeState.Idle:
                default:
                    HandleIdle();
                    break;
            }
        }

        // AC-001: begins/continues following the acquired wizard target by (re)setting the
        // NavMeshAgent destination to its current position every tick, so pursuit tracks a
        // moving target and automatically routes through any doorway NSC-090's
        // DoorEnemyPassability has made walkable (AC-005) without this component special-casing
        // doorway crossings itself.
        private void HandlePursuing()
        {
            hasWanderDestination = false;

            var target = targetKnowledge.CurrentTarget;
            if (target == null) return;

            agent.SetDestination(target.position);
        }

        // AC-002: heads toward the recorded last known position and reports arrival back to
        // EnemyTargetKnowledge once reached, so the owner-controlled bounded wander/search
        // state can begin.
        private void HandleSearching()
        {
            hasWanderDestination = false;

            var lastKnownPosition = targetKnowledge.LastKnownPosition;
            agent.SetDestination(lastKnownPosition);

            if (HasArrivedAtDestination(lastKnownPosition))
            {
                targetKnowledge.ReportArrivedAtLastKnownPosition();
            }
        }

        // AC-003: while EnemyTargetKnowledge reports the bounded wander/search state, choose a
        // controlled-random nearby point that is valid on the configured NavMesh and move
        // there; once reached, pick another. EnemyTargetKnowledge's own search timer (advanced
        // above in Tick) independently ends this state through reacquisition or expiry.
        private void HandleWandering()
        {
            if (!hasWanderDestination)
            {
                if (TryPickWanderPoint(out wanderDestination))
                {
                    hasWanderDestination = true;
                    agent.SetDestination(wanderDestination);
                }

                return;
            }

            if (HasArrivedAtDestination(wanderDestination))
            {
                hasWanderDestination = false;
            }
        }

        // AC-004: once EnemyTargetKnowledge has cleared the target, stop driving any
        // pursuit/search destination so local idle/wander movement (owned elsewhere) can take
        // over. This never destroys, disables, replaces, or reinitializes the enemy GameObject.
        private void HandleIdle()
        {
            hasWanderDestination = false;

            if (agent.hasPath)
            {
                agent.ResetPath();
            }
        }

        private bool TryPickWanderPoint(out Vector3 point)
        {
            var anchor = targetKnowledge.LastKnownPosition;

            for (var attempt = 0; attempt < MaxWanderSampleAttempts; attempt++)
            {
                var randomOffset = Random.insideUnitCircle * wanderRadius;
                var candidate = anchor + new Vector3(randomOffset.x, 0f, randomOffset.y);

                if (NavMesh.SamplePosition(candidate, out var hit, wanderSampleMaxDistance, NavMesh.AllAreas))
                {
                    point = hit.position;
                    return true;
                }
            }

            point = anchor;
            return false;
        }

        private bool HasArrivedAtDestination(Vector3 destination)
        {
            if (!agent.isOnNavMesh || agent.pathPending) return false;

            var offset = transform.position - destination;
            offset.y = 0f;
            return offset.sqrMagnitude <= destinationArrivalDistance * destinationArrivalDistance;
        }

        /// AC-007: owner-controlled reset entry point for the Floor Run/Restart Orchestrator.
        /// Resets EnemyTargetKnowledge's owned state through its own reset method, stops and
        /// clears this enemy's NavMeshAgent path, and returns the enemy Transform to its
        /// authored encounter/spawn region without directly mutating state owned by another
        /// component.
        public void ResetPursuit()
        {
            hasWanderDestination = false;
            targetKnowledge?.ResetTargetKnowledge();

            if (agent != null && agent.isOnNavMesh)
            {
                agent.ResetPath();
                agent.Warp(spawnPosition);
            }
            else
            {
                transform.position = spawnPosition;
            }

            transform.rotation = spawnRotation;
        }
    }
}
