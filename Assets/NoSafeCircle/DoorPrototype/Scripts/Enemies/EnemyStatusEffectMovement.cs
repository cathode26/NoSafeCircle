using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    /// Reusable enemy-owned Frost Field slowdown and ability-requested forced displacement
    /// (NSC-013). Modifies only this enemy's NavMeshAgent locomotion speed and position; it
    /// never reads or writes EnemyTargetKnowledge's target/search state or calls into
    /// EnemyPursuitMovement, so pursuit/search movement resumes on its own - through
    /// EnemyPursuitMovement's existing per-frame destination refresh - once Frost ends or a
    /// displacement completes, rather than this component defining a second enemy-state
    /// machine. Frost Field and Force Wave call this component's public entry points; they
    /// never set NavMeshAgent.speed or call NavMeshAgent.Warp directly.
    [DisallowMultipleComponent]
    [RequireComponent(typeof(NavMeshAgent))]
    public sealed class EnemyStatusEffectMovement : MonoBehaviour
    {
        private const int MaxDisplacementSampleAttempts = 4;

        [SerializeField] private NavMeshAgent agent;

        // AC-003: bounds how far a requested displacement's NavMesh landing point may deviate
        // from the sampled candidate position while still counting as a valid sample.
        [SerializeField] private float displacementSampleMaxDistance = 2f;

        private float baselineSpeed;
        private float frostSpeedMultiplier = 1f;
        private float frostTimeRemaining;

        // Reused across RequestDisplacement calls (an infrequent ability-triggered operation,
        // not a per-frame one) to avoid allocating a new NavMeshPath on every request.
        private readonly NavMeshPath displacementPath = new NavMeshPath();

        /// AC-001/AC-002: true while an active Frost Field slowdown is currently reducing this
        /// enemy's NavMeshAgent speed below its authored baseline.
        public bool IsFrostSlowdownActive => frostTimeRemaining > 0f;

        public float FrostSpeedMultiplier => frostSpeedMultiplier;
        public float FrostTimeRemaining => frostTimeRemaining;

        /// The NavMeshAgent speed this component restores once Frost slowdown ends or is reset,
        /// captured once at Awake before any effect can run.
        public float BaselineSpeed => baselineSpeed;

        private void Awake()
        {
            if (agent == null) agent = GetComponent<NavMeshAgent>();
            baselineSpeed = agent.speed;
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// Advances the active Frost slowdown timer by deltaTime. Public so Play Mode tests can
        /// drive it deterministically without waiting on real frames, mirroring
        /// EnemyPursuitMovement.Tick/EnemyTargetKnowledge.UpdateTargetKnowledge.
        public void Tick(float deltaTime)
        {
            if (frostTimeRemaining <= 0f) return;

            frostTimeRemaining -= deltaTime;

            if (frostTimeRemaining <= 0f)
            {
                frostTimeRemaining = 0f;
                RestoreBaselineSpeed();
            }
        }

        /// AC-001/AC-002: Frost Field calls this to slow this enemy's locomotion/repositioning
        /// speed to speedMultiplier of its baseline for duration seconds. Only
        /// NavMeshAgent.speed is touched here, so attack execution/timing owned by a separate
        /// attack component is never affected. A call while already active overwrites the
        /// previous multiplier/duration rather than stacking, keeping one reusable slowdown slot
        /// per enemy instead of layered timers. A non-positive duration is ignored rather than
        /// silently ending an in-progress effect.
        public void ApplyFrostSlowdown(float speedMultiplier, float duration)
        {
            if (agent == null || duration <= 0f) return;

            frostSpeedMultiplier = Mathf.Clamp01(speedMultiplier);
            frostTimeRemaining = duration;
            agent.speed = baselineSpeed * frostSpeedMultiplier;
        }

        /// AC-003/AC-004: Force Wave (or another ability) calls this with the radial knockback
        /// direction/distance it has already selected for this enemy. The enemy is warped to
        /// the nearest valid NavMesh point sampled along that direction so it never lands inside
        /// unwalkable geometry; EnemyPursuitMovement's own per-frame destination refresh then
        /// resumes pursuit/search movement from the new position without this component driving
        /// that state itself. A sampled point that exists on the NavMesh but is not reachable by
        /// an actual walkable path from the enemy's current position - for example a separate
        /// area across a wall - is rejected rather than warped into, since NavMesh.SamplePosition
        /// alone only proves a nearby polygon exists, not that it is path-connected. A
        /// non-positive distance, a missing agent, or an agent not currently on a NavMesh is a
        /// no-op.
        public void RequestDisplacement(Vector3 knockbackDirection, float knockbackDistance)
        {
            if (agent == null || !agent.isOnNavMesh || knockbackDistance <= 0f) return;

            var direction = knockbackDirection;
            direction.y = 0f;

            if (direction.sqrMagnitude < 0.0001f)
            {
                direction = transform.forward;
                direction.y = 0f;
            }

            direction.Normalize();

            // Shrinks the candidate distance on each retry so a knockback that would land
            // outside walkable geometry, or on a path-disconnected pocket, still resolves to the
            // closest valid, reachable point along the same requested direction instead of
            // leaving the enemy undisplaced.
            for (var attempt = 0; attempt < MaxDisplacementSampleAttempts; attempt++)
            {
                var candidateDistance = knockbackDistance / Mathf.Pow(2f, attempt);
                var candidate = transform.position + direction * candidateDistance;

                if (!NavMesh.SamplePosition(candidate, out var hit, displacementSampleMaxDistance, NavMesh.AllAreas))
                {
                    continue;
                }

                if (!NavMesh.CalculatePath(transform.position, hit.position, NavMesh.AllAreas, displacementPath) ||
                    displacementPath.status != NavMeshPathStatus.PathComplete)
                {
                    continue;
                }

                agent.Warp(hit.position);
                return;
            }
        }

        /// AC-005: owner-controlled reset entry point for the Floor Run/Restart Orchestrator.
        /// Clears any active Frost slowdown and restores this enemy's NavMeshAgent speed to its
        /// authored baseline. Forced displacement has no persistent state to clear because
        /// RequestDisplacement already completes as an instantaneous warp.
        public void ResetStatusEffects()
        {
            frostTimeRemaining = 0f;
            frostSpeedMultiplier = 1f;
            RestoreBaselineSpeed();
        }

        private void RestoreBaselineSpeed()
        {
            if (agent != null)
            {
                agent.speed = baselineSpeed;
            }
        }
    }
}
