using NoSafeCircle.DoorPrototype;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    /// Read-only cycle phase exposed for EnemyPursuitMovement (NSC-092) to hold translation
    /// during wind-up. This component never writes locomotion state itself.
    public enum MeleeAttackPhase
    {
        Idle,
        WindingUp,
        Cooldown
    }

    /// Close-range attack owner for one melee enemy (NSC-124). Consumes EnemyTargetKnowledge's
    /// read-only Pursuing/CurrentTarget state and EnemyHealth's read-only IsDefeated state; it
    /// never writes either component's internals and never moves the enemy or touches
    /// locomotion state directly. Damage is requested through PlayerHealth's owner-controlled
    /// TakeDamage entry point rather than maintaining a duplicate player-health copy.
    [DisallowMultipleComponent]
    public sealed class MeleeEnemyAttack : MonoBehaviour
    {
        [SerializeField] private EnemyTargetKnowledge targetKnowledge;
        [SerializeField] private EnemyHealth enemyHealth;
        [SerializeField, Min(0.01f)] private float attackRange = 1.5f;
        [SerializeField, Min(0.01f)] private float windUpSeconds = 0.5f;
        [SerializeField, Min(0f)] private float cooldownSeconds = 1f;
        [SerializeField, Min(0.01f)] private float attackDamage = 10f;

        private float windUpRemaining;
        private float cooldownRemaining;
        private Transform windUpTarget;

        public MeleeAttackPhase Phase { get; private set; } = MeleeAttackPhase.Idle;

        private void Awake()
        {
            if (targetKnowledge == null) targetKnowledge = GetComponent<EnemyTargetKnowledge>();
            if (enemyHealth == null) enemyHealth = GetComponent<EnemyHealth>();
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// Advances the wind-up/impact/cooldown cycle without advancing target knowledge or
        /// movement. Public so Play Mode tests can drive it deterministically.
        public void Tick(float deltaTime)
        {
            if (!isActiveAndEnabled || deltaTime < 0f) return;

            if (Phase == MeleeAttackPhase.Cooldown)
            {
                cooldownRemaining = Mathf.Max(0f, cooldownRemaining - deltaTime);
                if (cooldownRemaining <= 0f) Phase = MeleeAttackPhase.Idle;
                return;
            }

            bool canAttack = IsPursuingTargetInRange(out Transform currentTarget);

            if (Phase == MeleeAttackPhase.WindingUp && !canAttack)
            {
                CancelWindUp();
                return;
            }

            if (Phase == MeleeAttackPhase.Idle)
            {
                if (!canAttack) return;
                Phase = MeleeAttackPhase.WindingUp;
                windUpRemaining = windUpSeconds;
                windUpTarget = currentTarget;
            }

            windUpRemaining -= deltaTime;
            if (windUpRemaining > 0f) return;

            ResolveImpact();
        }

        /// Cancels an early or late wind-up and any pending impact, clears cooldown, and
        /// returns to idle so a later valid cycle can begin normally. Prevents delayed damage
        /// from the cancelled cycle since ResolveImpact only runs from within Tick.
        public void ResetAttack()
        {
            Phase = MeleeAttackPhase.Idle;
            windUpRemaining = 0f;
            cooldownRemaining = 0f;
            windUpTarget = null;
        }

        private bool IsPursuingTargetInRange(out Transform target)
        {
            target = null;

            if (targetKnowledge == null ||
                targetKnowledge.State != EnemyTargetKnowledgeState.Pursuing ||
                targetKnowledge.CurrentTarget == null ||
                (enemyHealth != null && enemyHealth.IsDefeated) ||
                !IsWithinRange(targetKnowledge.CurrentTarget)) return false;

            target = targetKnowledge.CurrentTarget;
            return true;
        }

        private bool IsWithinRange(Transform target)
        {
            return Vector3.Distance(transform.position, target.position) <= attackRange;
        }

        private void CancelWindUp()
        {
            Phase = MeleeAttackPhase.Idle;
            windUpRemaining = 0f;
            windUpTarget = null;
        }

        // Rechecks the same target, Pursuing state, range, and defeat state at the moment of
        // impact; an invalid impact completes without damage.
        private void ResolveImpact()
        {
            Transform target = windUpTarget;
            windUpTarget = null;
            windUpRemaining = 0f;
            Phase = MeleeAttackPhase.Cooldown;
            cooldownRemaining = cooldownSeconds;

            if (!IsValidImpactTarget(target)) return;

            if (target.TryGetComponent(out PlayerHealth playerHealth))
            {
                playerHealth.TakeDamage(attackDamage);
            }
        }

        private bool IsValidImpactTarget(Transform target)
        {
            if (target == null || targetKnowledge == null) return false;
            if (targetKnowledge.State != EnemyTargetKnowledgeState.Pursuing) return false;
            if (targetKnowledge.CurrentTarget != target) return false;
            if (enemyHealth != null && enemyHealth.IsDefeated) return false;
            return IsWithinRange(target);
        }

        private void OnDisable()
        {
            ResetAttack();
        }
    }
}
