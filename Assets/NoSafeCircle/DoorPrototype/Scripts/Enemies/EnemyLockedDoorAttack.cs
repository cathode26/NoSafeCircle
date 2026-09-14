using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    /// Applies an enemy's timed locked-door hits through DoorInteractable.TakeDamage.
    /// Pursuit movement decides which door blocks the route; this component never changes
    /// navigation, door state, or durability directly.
    [DisallowMultipleComponent]
    [RequireComponent(typeof(EnemyTargetKnowledge), typeof(EnemyPursuitMovement))]
    public sealed class EnemyLockedDoorAttack : MonoBehaviour
    {
        [SerializeField, Min(0.01f)] private float attackReach = 1f;
        [SerializeField, Min(0.01f)] private float attackInterval = 0.8f;
        [SerializeField, Min(0.01f)] private float attackDamage = 10f;
        [SerializeField] private EnemyTargetKnowledge targetKnowledge;
        [SerializeField] private EnemyPursuitMovement pursuitMovement;

        private DoorInteractable pendingDoor;
        private float elapsedQualifyingTime;

        public DoorInteractable PendingDoor => pendingDoor;

        private void Awake()
        {
            if (targetKnowledge == null) targetKnowledge = GetComponent<EnemyTargetKnowledge>();
            if (pursuitMovement == null) pursuitMovement = GetComponent<EnemyPursuitMovement>();
        }

        private void OnDisable()
        {
            ResetAttack();
        }

        private void OnValidate()
        {
            attackReach = Mathf.Max(0.01f, attackReach);
            attackInterval = Mathf.Max(0.01f, attackInterval);
            attackDamage = Mathf.Max(0.01f, attackDamage);
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// Advances only uninterrupted time spent pursuing within reach of the selected
        /// locked door. A different door or any loss of qualification restarts the interval.
        public void Tick(float deltaTime)
        {
            var door = pursuitMovement == null ? null : pursuitMovement.BlockingLockedDoor;
            if (targetKnowledge == null || pursuitMovement == null ||
                targetKnowledge.State != EnemyTargetKnowledgeState.Pursuing ||
                targetKnowledge.CurrentTarget == null || door == null ||
                !door.IsLocked || door.IsBroken ||
                HorizontalDistance(transform.position, pursuitMovement.BlockingDoorApproachPoint) > attackReach)
            {
                ResetAttack();
                return;
            }

            if (pendingDoor != door)
            {
                pendingDoor = door;
                elapsedQualifyingTime = 0f;
            }

            elapsedQualifyingTime += Mathf.Max(0f, deltaTime);
            while (elapsedQualifyingTime >= attackInterval && pendingDoor == door)
            {
                elapsedQualifyingTime -= attackInterval;
                door.TakeDamage(attackDamage);
                if (!door.IsLocked || door.IsBroken)
                {
                    ResetAttack();
                    return;
                }
            }
        }

        /// Cancels this enemy's pending hit without changing target knowledge, movement, or
        /// the door. Floor-run restart calls this alongside EnemyPursuitMovement.ResetPursuit.
        public void ResetAttack()
        {
            pendingDoor = null;
            elapsedQualifyingTime = 0f;
        }

        private static float HorizontalDistance(Vector3 first, Vector3 second)
        {
            var offset = first - second;
            offset.y = 0f;
            return offset.magnitude;
        }
    }
}
