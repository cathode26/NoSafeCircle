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

        private void OnDestroy()
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

            if (pendingDoor != door) AdoptPendingDoor(door);

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
            ReleasePendingDoor();
            elapsedQualifyingTime = 0f;
        }

        /// Adopts the door this enemy is winding up against and listens for its break. Another
        /// enemy can land the breaking hit, so DoorInteractable.Broken clears this enemy's
        /// pending hit in the same frame instead of on its next Tick (NSC-017 AC-004).
        private void AdoptPendingDoor(DoorInteractable door)
        {
            ReleasePendingDoor();
            pendingDoor = door;
            elapsedQualifyingTime = 0f;
            if (pendingDoor != null) pendingDoor.Broken += OnPendingDoorBroken;
        }

        private void ReleasePendingDoor()
        {
            if (pendingDoor != null) pendingDoor.Broken -= OnPendingDoorBroken;
            pendingDoor = null;
        }

        private void OnPendingDoorBroken()
        {
            ResetAttack();
        }

        private static float HorizontalDistance(Vector3 first, Vector3 second)
        {
            var offset = first - second;
            offset.y = 0f;
            return offset.magnitude;
        }
    }
}
