using System;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    [DisallowMultipleComponent]
    public sealed class RangedEnemyProjectile : MonoBehaviour
    {
        [SerializeField, Min(0.01f)] private float speed = 3f;
        [SerializeField, Min(0.01f)] private float lifetimeSeconds = 5f;
        [SerializeField, Min(0f)] private float collisionRadius = 0.08f;
        [SerializeField, Min(0f)] private float damage = 10f;

        private RangedEnemyAttack owner;
        private Vector3 direction;
        private float remainingLifetime;
        private float flightHeight;
        private bool isFlying;

        public bool IsFlying => isFlying;

        /// <summary>Starts one fixed-direction horizontal flight owned by an attack component.</summary>
        public void Launch(Vector3 origin, Vector3 direction, RangedEnemyAttack owner)
        {
            if (owner == null) throw new ArgumentNullException(nameof(owner));

            Vector3 horizontal = direction;
            horizontal.y = 0f;
            if (horizontal.sqrMagnitude < 0.0001f)
                throw new ArgumentException("Projectile direction must be nonzero in the horizontal plane.", nameof(direction));

            this.owner = owner;
            this.direction = horizontal.normalized;
            flightHeight = origin.y;
            transform.position = origin;
            remainingLifetime = lifetimeSeconds;
            isFlying = true;
            owner.RegisterProjectile(this);
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// <summary>Sweeps the complete travelled segment, including repeated ticks in one frame.</summary>
        public void Tick(float deltaTime)
        {
            if (!isFlying || deltaTime <= 0f) return;
            if (owner == null || !owner.isActiveAndEnabled)
            {
                Stop();
                return;
            }

            float travelledTime = Mathf.Min(deltaTime, remainingLifetime);
            float distance = speed * travelledTime;
            Vector3 origin = transform.position;

            // Tests can move temporary colliders between Tick calls without a physics frame.
            Physics.SyncTransforms();
            if (StopForInitialOverlap(origin)) return;
            RaycastHit[] hits = Physics.SphereCastAll(origin, collisionRadius, direction, distance,
                ~0, QueryTriggerInteraction.Ignore);
            Array.Sort(hits, (left, right) => left.distance.CompareTo(right.distance));

            foreach (RaycastHit hit in hits)
            {
                Collider collider = hit.collider;
                if (collider == null || ShouldIgnore(collider)) continue;

                PlayerHealth health = collider.GetComponent<PlayerHealth>();
                if (health != null) health.TakeDamage(damage);
                transform.position = new Vector3(hit.point.x, flightHeight, hit.point.z);
                Stop();
                return;
            }

            transform.position = new Vector3(origin.x + direction.x * distance,
                flightHeight, origin.z + direction.z * distance);
            remainingLifetime -= travelledTime;
            if (remainingLifetime <= 0f) Stop();
        }

        private bool StopForInitialOverlap(Vector3 origin)
        {
            Collider[] overlaps = Physics.OverlapSphere(origin, collisionRadius,
                ~0, QueryTriggerInteraction.Ignore);
            PlayerHealth contactedPlayer = null;
            foreach (Collider collider in overlaps)
            {
                if (collider == null || ShouldIgnore(collider)) continue;
                PlayerHealth player = collider.GetComponent<PlayerHealth>();
                if (player == null)
                {
                    // If cover and the player overlap the starting footprint, cover wins.
                    Stop();
                    return true;
                }
                contactedPlayer = player;
            }

            if (contactedPlayer == null) return false;
            contactedPlayer.TakeDamage(damage);
            Stop();
            return true;
        }

        private bool ShouldIgnore(Collider collider)
        {
            Transform hitTransform = collider.transform;
            if (hitTransform.IsChildOf(transform)) return true;
            if (owner != null && hitTransform.IsChildOf(owner.transform)) return true;
            if (collider.GetComponentInParent<RangedEnemyProjectile>() != null) return true;
            if (collider.GetComponentInParent<EnemyTargetKnowledge>() != null) return true;

            // PlayerHealth belongs to its exact collider GameObject. A child or parent
            // collider is neither the damage target nor accidental cover.
            PlayerHealth relatedHealth = collider.GetComponentInParent<PlayerHealth>();
            if (relatedHealth != null && collider.GetComponent<PlayerHealth>() == null) return true;
            if (collider.GetComponent<PlayerHealth>() == null && collider.GetComponentInChildren<PlayerHealth>() != null) return true;
            return false;
        }

        /// <summary>Immediately makes this projectile unable to deal later damage.</summary>
        public void Stop()
        {
            if (!isFlying) return;
            isFlying = false;
            RangedEnemyAttack launchingOwner = owner;
            owner = null;
            if (launchingOwner != null) launchingOwner.ForgetProjectile(this);
            gameObject.SetActive(false);
            Destroy(gameObject);
        }
    }
}
