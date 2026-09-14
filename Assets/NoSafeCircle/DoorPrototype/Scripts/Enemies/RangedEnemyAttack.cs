using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    [DisallowMultipleComponent]
    public sealed class RangedEnemyAttack : MonoBehaviour
    {
        [SerializeField] private EnemyTargetKnowledge targetKnowledge;
        [SerializeField] private RangedEnemyProjectile projectileTemplate;
        [SerializeField] private Transform projectileOrigin;
        [SerializeField] private GameObject windUpFeedback;
        [SerializeField, Min(0.01f)] private float windUpSeconds = 0.4f;
        [SerializeField, Min(0f)] private float cooldownSeconds = 1f;

        private readonly HashSet<RangedEnemyProjectile> ownedProjectiles = new HashSet<RangedEnemyProjectile>();
        private float windUpRemaining;
        private float cooldownRemaining;

        public bool IsWindingUp { get; private set; }

        private void Awake()
        {
            if (targetKnowledge == null) targetKnowledge = GetComponent<EnemyTargetKnowledge>();
            if (windUpFeedback != null) windUpFeedback.SetActive(false);
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// <summary>Advances attack timing without advancing target knowledge or movement.</summary>
        public void Tick(float deltaTime)
        {
            if (!isActiveAndEnabled || deltaTime < 0f) return;

            bool pursuingWizard = targetKnowledge != null &&
                targetKnowledge.State == EnemyTargetKnowledgeState.Pursuing &&
                targetKnowledge.CurrentTarget != null;

            if (!pursuingWizard)
            {
                CancelWindUp();
                return;
            }

            if (cooldownRemaining > 0f)
            {
                cooldownRemaining = Mathf.Max(0f, cooldownRemaining - deltaTime);
                return;
            }

            if (!IsWindingUp)
            {
                Renderer feedbackRenderer = windUpFeedback != null
                    ? windUpFeedback.GetComponentInChildren<Renderer>(true) : null;
                if (projectileTemplate == null || projectileOrigin == null || windUpFeedback == null ||
                    feedbackRenderer == null || !feedbackRenderer.enabled || windUpSeconds <= 0f) return;
                IsWindingUp = true;
                windUpRemaining = windUpSeconds;
                if (windUpFeedback != null) windUpFeedback.SetActive(true);
            }

            windUpRemaining -= deltaTime;
            if (windUpRemaining > 0f) return;

            Transform target = targetKnowledge.CurrentTarget;
            Vector3 direction = target.position - projectileOrigin.position;
            direction.y = 0f;
            CancelWindUp();
            cooldownRemaining = cooldownSeconds;
            if (direction.sqrMagnitude < 0.0001f) return;

            RangedEnemyProjectile projectile = Instantiate(projectileTemplate);
            projectile.gameObject.SetActive(true);
            projectile.Launch(projectileOrigin.position, direction, this);
        }

        /// <summary>Cancels attack timing and removes every projectile launched by this enemy.</summary>
        public void ResetAttack()
        {
            CancelWindUp();
            cooldownRemaining = 0f;
            RangedEnemyProjectile[] projectiles = new RangedEnemyProjectile[ownedProjectiles.Count];
            ownedProjectiles.CopyTo(projectiles);
            foreach (RangedEnemyProjectile projectile in projectiles)
            {
                if (projectile != null) projectile.Stop();
            }
            ownedProjectiles.Clear();
        }

        internal void RegisterProjectile(RangedEnemyProjectile projectile)
        {
            ownedProjectiles.Add(projectile);
        }

        internal void ForgetProjectile(RangedEnemyProjectile projectile)
        {
            ownedProjectiles.Remove(projectile);
        }

        private void CancelWindUp()
        {
            IsWindingUp = false;
            windUpRemaining = 0f;
            if (windUpFeedback != null) windUpFeedback.SetActive(false);
        }

        private void OnDisable()
        {
            ResetAttack();
        }

        private void OnDestroy()
        {
            ResetAttack();
        }
    }
}
