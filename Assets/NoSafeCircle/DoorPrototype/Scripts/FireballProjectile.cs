using System;
using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// Owns one runtime-created Fireball shot's straight-line flight, maximum-lifetime fizzle,
    /// cover collision, and enemy damage. Fireball's cast/charge state calls Launch and never
    /// reaches into this component's fields; no prefab or cursor/ground target is involved -
    /// the shot only ever travels along the direction it was launched with.
    [DisallowMultipleComponent]
    public sealed class FireballProjectile : MonoBehaviour
    {
        private Vector3 direction;
        private float speed;
        private float remainingLifetime;
        private float contactRadius;
        private float damage;
        private float areaRadius;
        private CharacterController caster;
        private float flightHeight;
        private bool isFlying;

        public bool IsFlying => isFlying;

        /// Starts one fixed-direction gameplay-plane flight. direction is projected onto the
        /// gameplay plane (its Y component is discarded) so the shot cannot be aimed at a
        /// cursor or ground point in 3D; only a horizontal heading is meaningful.
        public void Launch(Vector3 startPosition, Vector3 direction, float speed,
            float maximumLifetimeSeconds, float contactRadius, float damage, float areaRadius,
            CharacterController caster)
        {
            Vector3 flatDirection = direction;
            flatDirection.y = 0f;
            if (flatDirection.sqrMagnitude < 0.0001f)
            {
                throw new ArgumentException(
                    "Fireball direction must be nonzero in the gameplay plane.", nameof(direction));
            }
            if (speed <= 0f) throw new ArgumentException("Fireball speed must be positive.", nameof(speed));
            if (maximumLifetimeSeconds <= 0f)
            {
                throw new ArgumentException(
                    "Fireball maximum lifetime must be positive.", nameof(maximumLifetimeSeconds));
            }

            this.direction = flatDirection.normalized;
            this.speed = speed;
            remainingLifetime = maximumLifetimeSeconds;
            this.contactRadius = Mathf.Max(0f, contactRadius);
            this.damage = Mathf.Max(0f, damage);
            this.areaRadius = Mathf.Max(0f, areaRadius);
            this.caster = caster;
            flightHeight = startPosition.y;
            transform.position = startPosition;
            isFlying = true;
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// Advances the shot by deltaTime: moves it in a straight line, stops it at whichever
        /// blocking Collider or contacted enemy is reached first along the segment, and fizzles
        /// it with no damage once the configured maximum lifetime elapses without contact.
        public void Tick(float deltaTime)
        {
            if (!isFlying || deltaTime <= 0f) return;

            float travelledTime = Mathf.Min(deltaTime, remainingLifetime);
            float distance = speed * travelledTime;
            Vector3 origin = transform.position;
            Vector3 endPosition = new Vector3(
                origin.x + direction.x * distance, flightHeight, origin.z + direction.z * distance);

            Physics.SyncTransforms();

            bool hasBlockingHit = TryFindBlockingHit(origin, distance, out RaycastHit blockingHit);
            EnemyHealth contactedEnemy = FindContactAlongSegment(origin, endPosition, out float enemyContactDistance);

            if (contactedEnemy != null && (!hasBlockingHit || enemyContactDistance <= blockingHit.distance))
            {
                Vector3 detonationPoint = new Vector3(
                    origin.x + direction.x * enemyContactDistance,
                    flightHeight,
                    origin.z + direction.z * enemyContactDistance);
                transform.position = detonationPoint;
                Detonate(detonationPoint, contactedEnemy);
                return;
            }

            if (hasBlockingHit)
            {
                Vector3 detonationPoint = new Vector3(blockingHit.point.x, flightHeight, blockingHit.point.z);
                transform.position = detonationPoint;
                Detonate(detonationPoint, null);
                return;
            }

            transform.position = endPosition;
            remainingLifetime -= travelledTime;
            if (remainingLifetime <= 0f)
            {
                isFlying = false;
                Destroy(gameObject);
            }
        }

        /// AC-002: the same chest-height, trigger-ignoring, default-gameplay-layer query used by
        /// the Ranged Enemy caster's HasUnobstructedViewOfWizard, cast forward along the flight
        /// direction and filtered so the caster's own CharacterController never stops the shot.
        private bool TryFindBlockingHit(Vector3 origin, float distance, out RaycastHit blockingHit)
        {
            blockingHit = default;
            if (distance <= 0f) return false;

            Vector3 chestOrigin = origin + Vector3.up;
            RaycastHit[] hits = Physics.RaycastAll(chestOrigin, direction, distance,
                Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);

            bool found = false;
            float closestDistance = float.MaxValue;
            foreach (RaycastHit hit in hits)
            {
                if (IsCaster(hit.transform)) continue;
                if (hit.distance >= closestDistance) continue;

                closestDistance = hit.distance;
                blockingHit = hit;
                found = true;
            }

            return found;
        }

        /// Enemies carry no Collider, so contact is tested as flat horizontal distance against
        /// the closest point of the travelled segment to each active, non-defeated EnemyHealth,
        /// mirroring the swept precision the wall/door raycast above already gets for free.
        private EnemyHealth FindContactAlongSegment(Vector3 origin, Vector3 endPosition, out float contactDistance)
        {
            contactDistance = float.MaxValue;
            EnemyHealth closestEnemy = null;

            Vector3 flatOrigin = Flatten(origin);
            Vector3 flatEnd = Flatten(endPosition);
            Vector3 segment = flatEnd - flatOrigin;
            float segmentLength = segment.magnitude;
            Vector3 segmentDirection = segmentLength > 0.0001f ? segment / segmentLength : Vector3.zero;

            foreach (EnemyHealth enemy in FindObjectsByType<EnemyHealth>(FindObjectsSortMode.None))
            {
                if (enemy == null || enemy.IsDefeated || !enemy.isActiveAndEnabled) continue;

                Vector3 flatEnemy = Flatten(enemy.transform.position);
                float travelled = segmentLength > 0.0001f
                    ? Mathf.Clamp(Vector3.Dot(flatEnemy - flatOrigin, segmentDirection), 0f, segmentLength)
                    : 0f;
                Vector3 closestPoint = flatOrigin + segmentDirection * travelled;
                if (Vector3.Distance(closestPoint, flatEnemy) > contactRadius) continue;
                if (travelled >= contactDistance) continue;

                contactDistance = travelled;
                closestEnemy = enemy;
            }

            return closestEnemy;
        }

        /// AC-002: detonates the shot, damages the directly contacted enemy (if any) exactly
        /// once, and, when this shot was launched with a splash area radius, also damages every
        /// other active, non-defeated enemy inside that radius with an unobstructed line from the
        /// detonation point. A tap shot is launched with no area radius, so only the contacted
        /// enemy is ever damaged.
        private void Detonate(Vector3 detonationPoint, EnemyHealth contactedEnemy)
        {
            isFlying = false;

            HashSet<EnemyHealth> damagedEnemies = null;
            if (contactedEnemy != null)
            {
                contactedEnemy.TakeDamage(damage);
                damagedEnemies = new HashSet<EnemyHealth> { contactedEnemy };
            }

            if (areaRadius > 0f)
            {
                Vector3 flatDetonationPoint = Flatten(detonationPoint);
                foreach (EnemyHealth enemy in FindObjectsByType<EnemyHealth>(FindObjectsSortMode.None))
                {
                    if (enemy == null || enemy.IsDefeated || !enemy.isActiveAndEnabled) continue;
                    if (damagedEnemies != null && damagedEnemies.Contains(enemy)) continue;
                    if (Vector3.Distance(Flatten(enemy.transform.position), flatDetonationPoint) > areaRadius) continue;
                    if (!HasUnobstructedLine(detonationPoint, enemy.transform.position)) continue;

                    enemy.TakeDamage(damage);
                    damagedEnemies ??= new HashSet<EnemyHealth>();
                    damagedEnemies.Add(enemy);
                }
            }

            Destroy(gameObject);
        }

        /// AC-002: the same chest-height, trigger-ignoring, default-gameplay-layer query used by
        /// HasUnobstructedViewOfWizard, applied between the detonation point and a splash
        /// candidate. Enemies carry no Collider, so any hit at all means something solid is
        /// between the detonation and that enemy.
        private static bool HasUnobstructedLine(Vector3 fromPoint, Vector3 toPosition)
        {
            Vector3 eye = fromPoint + Vector3.up;
            Vector3 target = toPosition + Vector3.up;
            Vector3 toTarget = target - eye;
            float distance = toTarget.magnitude;
            if (distance <= 0.01f) return true;

            return !Physics.Raycast(eye, toTarget / distance, distance,
                Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
        }

        private bool IsCaster(Transform hitTransform)
        {
            return caster != null && (hitTransform == caster.transform || hitTransform.IsChildOf(caster.transform));
        }

        private static Vector3 Flatten(Vector3 point)
        {
            point.y = 0f;
            return point;
        }
    }
}
