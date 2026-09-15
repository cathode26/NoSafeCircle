using System.Collections.Generic;
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
        private const float DoorSideSampleDistance = 0.75f;

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
        private NavMeshPath routePath;

        /// The first locked door on a reachable route to the pursued wizard. A nearby door
        /// outside that route never becomes an attack target.
        public DoorInteractable BlockingLockedDoor { get; private set; }
        public Vector3 BlockingDoorApproachPoint { get; private set; }

        private struct DoorRoute
        {
            public DoorInteractable Door;
            public int FirstSide;
            public int SecondSide;
        }

        private void Awake()
        {
            if (agent == null) agent = GetComponent<NavMeshAgent>();
            if (targetKnowledge == null) targetKnowledge = GetComponent<EnemyTargetKnowledge>();
            routePath = new NavMeshPath();

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
            if (targetKnowledge == null)
            {
                ClearBlockingDoor();
                return;
            }

            // AC-001/AC-002/AC-003/AC-004: EnemyPursuitMovement is the sole production driver
            // of EnemyTargetKnowledge's per-tick evaluation, since it is the only consumer that
            // needs target/search state to decide navigation.
            targetKnowledge.UpdateTargetKnowledge(deltaTime);

            if (agent == null || !agent.isOnNavMesh)
            {
                ClearBlockingDoor();
                return;
            }

            if (targetKnowledge.State != EnemyTargetKnowledgeState.Pursuing)
                ClearBlockingDoor();

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
            if (target == null)
            {
                ClearBlockingDoor();
                return;
            }

            if (TryFindBlockingDoor(target.position, out var door, out var approachPoint))
            {
                BlockingLockedDoor = door;
                BlockingDoorApproachPoint = approachPoint;
                // Door-side sampling is stable while the obstacle is closed. Reissuing the
                // same request every frame can leave the live agent perpetually pending
                // instead of letting it finish the route and reach attack range.
                if ((!agent.hasPath && !agent.pathPending) ||
                    (agent.destination - approachPoint).sqrMagnitude > 0.01f)
                    agent.SetDestination(approachPoint);
                return;
            }

            ClearBlockingDoor();
            agent.SetDestination(target.position);
        }

        // Treat complete NavMesh connections as walkable regions, and locked doors as the only
        // possible bridges between them. This distinguishes a door on the route from a nearby
        // dead-end door and selects the first reachable door when several are locked in series.
        private bool TryFindBlockingDoor(Vector3 targetPosition, out DoorInteractable blockingDoor,
            out Vector3 approachPoint)
        {
            blockingDoor = null;
            approachPoint = Vector3.zero;
            if (agent.CalculatePath(targetPosition, routePath) &&
                routePath.status == NavMeshPathStatus.PathComplete)
                return false;

            var filter = new NavMeshQueryFilter
            {
                agentTypeID = agent.agentTypeID,
                areaMask = agent.areaMask
            };
            if (!NavMesh.SamplePosition(targetPosition, out var targetHit, DoorSideSampleDistance, filter))
                return false;

            var points = new List<Vector3> { agent.nextPosition, targetHit.position };
            var doors = new List<DoorRoute>();
            foreach (var door in DoorInteractable.ActiveDoors)
            {
                if (door == null || !door.isActiveAndEnabled || !door.IsLocked || door.IsBroken)
                    continue;

                var sideOffset = door.InteractionPosition - door.transform.position;
                sideOffset.y = 0f;
                if (sideOffset.sqrMagnitude < 0.01f ||
                    !TrySampleDoorSide(door.transform.position + sideOffset, door.transform.position,
                        sideOffset, filter, out var firstSide) ||
                    !TrySampleDoorSide(door.transform.position - sideOffset, door.transform.position,
                        -sideOffset, filter, out var secondSide))
                    continue;

                doors.Add(new DoorRoute { Door = door, FirstSide = points.Count,
                    SecondSide = points.Count + 1 });
                points.Add(firstSide);
                points.Add(secondSide);
            }
            if (doors.Count == 0) return false;

            var regions = new int[points.Count];
            var representatives = new List<int>();
            for (var index = 0; index < points.Count; index++)
            {
                regions[index] = -1;
                for (var region = 0; region < representatives.Count; region++)
                {
                    if (!HasCompletePath(points[index], points[representatives[region]], filter))
                        continue;
                    regions[index] = region;
                    break;
                }
                if (regions[index] >= 0) continue;
                regions[index] = representatives.Count;
                representatives.Add(index);
            }
            if (regions[0] == regions[1]) return false;

            var doorHopsToTarget = new int[representatives.Count];
            for (var index = 0; index < doorHopsToTarget.Length; index++)
                doorHopsToTarget[index] = -1;
            var queue = new Queue<int>();
            doorHopsToTarget[regions[1]] = 0;
            queue.Enqueue(regions[1]);
            while (queue.Count > 0)
            {
                var region = queue.Dequeue();
                foreach (var door in doors)
                {
                    var first = regions[door.FirstSide];
                    var second = regions[door.SecondSide];
                    var neighbor = first == region ? second : second == region ? first : -1;
                    if (neighbor < 0 || neighbor == region || doorHopsToTarget[neighbor] >= 0)
                        continue;
                    doorHopsToTarget[neighbor] = doorHopsToTarget[region] + 1;
                    queue.Enqueue(neighbor);
                }
            }

            var bestDoorHops = int.MaxValue;
            var bestApproachDistance = float.PositiveInfinity;
            foreach (var door in doors)
            {
                var first = regions[door.FirstSide];
                var second = regions[door.SecondSide];
                var approachIndex = first == regions[0] ? door.FirstSide :
                    second == regions[0] ? door.SecondSide : -1;
                if (approachIndex < 0) continue;
                var farRegion = regions[approachIndex == door.FirstSide ? door.SecondSide : door.FirstSide];
                if (farRegion == regions[0] || doorHopsToTarget[farRegion] < 0) continue;
                var doorHops = doorHopsToTarget[farRegion] + 1;
                var distance = CompletePathLength(points[0], points[approachIndex], filter);
                if (float.IsPositiveInfinity(distance) || doorHops > bestDoorHops ||
                    (doorHops == bestDoorHops && distance >= bestApproachDistance))
                    continue;
                bestDoorHops = doorHops;
                bestApproachDistance = distance;
                blockingDoor = door.Door;
                approachPoint = points[approachIndex];
            }
            return blockingDoor != null;
        }

        private static bool TrySampleDoorSide(Vector3 requested, Vector3 doorPosition,
            Vector3 expectedSide, NavMeshQueryFilter filter, out Vector3 sampled)
        {
            sampled = Vector3.zero;
            if (!NavMesh.SamplePosition(requested, out var hit, DoorSideSampleDistance, filter) ||
                Vector3.Dot(hit.position - doorPosition, expectedSide) <= 0f)
                return false;
            sampled = hit.position;
            return true;
        }

        private bool HasCompletePath(Vector3 start, Vector3 end, NavMeshQueryFilter filter)
        {
            return NavMesh.CalculatePath(start, end, filter, routePath) &&
                   routePath.status == NavMeshPathStatus.PathComplete;
        }

        private float CompletePathLength(Vector3 start, Vector3 end, NavMeshQueryFilter filter)
        {
            if (!HasCompletePath(start, end, filter)) return float.PositiveInfinity;
            var corners = routePath.corners;
            var distance = 0f;
            for (var index = 1; index < corners.Length; index++)
                distance += Vector3.Distance(corners[index - 1], corners[index]);
            return distance;
        }

        private void ClearBlockingDoor()
        {
            BlockingLockedDoor = null;
            BlockingDoorApproachPoint = Vector3.zero;
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
            ClearBlockingDoor();
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
