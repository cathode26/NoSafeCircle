using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    /// A stationary caster enemy that answers the wizard's fireball with its own. It spends
    /// mana per cast exactly like the player does, so it goes quiet once drained instead of
    /// firing forever. Self-contained and IMGUI-free: it owns its projectiles, its range test,
    /// and its sight test, so it needs no NavMesh and no pursuit components.
    public sealed class EnemyFireballCaster : MonoBehaviour
    {
        [SerializeField] private Transform wizardTransform;

        [SerializeField, Min(0f)] private float maximumMana = 60f;
        [SerializeField, Min(0.01f)] private float manaPerCast = 10f;
        [SerializeField, Min(0.05f)] private float castInterval = 1f;

        [SerializeField, Min(0.1f)] private float castRange = 14f;
        [SerializeField, Min(0.1f)] private float projectileSpeed = 8f;
        [SerializeField, Min(0.1f)] private float projectileHitRadius = 0.8f;
        [SerializeField, Min(0.1f)] private float projectileLifetime = 4f;
        [SerializeField, Min(0.1f)] private float projectileDamage = 5f;

        private readonly List<Projectile> projectiles = new List<Projectile>();
        private float castCooldown;
        private float currentMana;
        private PlayerHealth wizardHealth;

        public float CurrentMana => currentMana;
        public bool IsOutOfMana => currentMana < manaPerCast;

        private struct Projectile
        {
            public GameObject Visual;
            public Vector3 Direction;
            public float RemainingLifetime;
        }

        /// Wires the wizard this caster shoots at. Called by the scene builder; a test fixture
        /// can supply its own Transform independently of the inspector-assigned field.
        public void Initialize(Transform wizard)
        {
            wizardTransform = wizard;
            wizardHealth = wizard != null ? wizard.GetComponent<PlayerHealth>() : null;
        }

        private void Awake()
        {
            currentMana = maximumMana;

            if (wizardHealth == null && wizardTransform != null)
            {
                wizardHealth = wizardTransform.GetComponent<PlayerHealth>();
            }
        }

        private void Update()
        {
            Tick(Time.deltaTime);
        }

        /// Advances casting and projectile flight by deltaTime. Public so Play Mode tests can
        /// drive it deterministically, mirroring DoorInteractable.Tick and PlayerMana.Tick.
        public void Tick(float deltaTime)
        {
            AdvanceProjectiles(deltaTime);

            if (wizardTransform == null || IsOutOfMana) return;

            castCooldown -= deltaTime;
            if (castCooldown > 0f) return;

            if (!IsWizardInRange() || !HasUnobstructedViewOfWizard()) return;

            CastAtWizard();
            currentMana -= manaPerCast;
            castCooldown = castInterval;
        }

        private bool IsWizardInRange()
        {
            var toWizard = wizardTransform.position - transform.position;
            toWizard.y = 0f;
            return toWizard.sqrMagnitude <= castRange * castRange;
        }

        private bool HasUnobstructedViewOfWizard()
        {
            // Chest height on both ends so the floor never counts as an occluder, and triggers
            // such as a door's range volume are ignored - only solid geometry blocks a cast.
            var eye = transform.position + Vector3.up;
            var target = wizardTransform.position + Vector3.up;
            var toTarget = target - eye;
            var distance = toTarget.magnitude;
            if (distance <= 0.01f) return true;

            if (!Physics.Raycast(eye, toTarget / distance, out RaycastHit hit, distance,
                    Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore))
            {
                return true;
            }

            // The wizard's own CharacterController terminates this ray; that is a clear view.
            return hit.transform == wizardTransform || hit.transform.IsChildOf(wizardTransform);
        }

        private void CastAtWizard()
        {
            var direction = wizardTransform.position - transform.position;
            direction.y = 0f;
            if (direction.sqrMagnitude < 0.0001f) return;
            direction.Normalize();

            var visual = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            visual.name = "EnemyFireball";
            Destroy(visual.GetComponent<Collider>());
            visual.transform.localScale = Vector3.one * 0.45f;
            visual.transform.position = transform.position + Vector3.up + direction;

            var renderer = visual.GetComponent<Renderer>();
            if (renderer != null) renderer.material.color = new Color(1f, 0.25f, 0.1f);

            projectiles.Add(new Projectile
            {
                Visual = visual,
                Direction = direction,
                RemainingLifetime = projectileLifetime,
            });
        }

        private void AdvanceProjectiles(float deltaTime)
        {
            for (int index = projectiles.Count - 1; index >= 0; index--)
            {
                Projectile projectile = projectiles[index];
                if (projectile.Visual == null)
                {
                    projectiles.RemoveAt(index);
                    continue;
                }

                projectile.Visual.transform.position +=
                    projectile.Direction * (projectileSpeed * deltaTime);
                projectile.RemainingLifetime -= deltaTime;

                bool hitWizard = false;
                if (wizardTransform != null)
                {
                    var flatProjectile = projectile.Visual.transform.position;
                    var flatWizard = wizardTransform.position;
                    flatProjectile.y = 0f;
                    flatWizard.y = 0f;

                    if (Vector3.Distance(flatProjectile, flatWizard) <= projectileHitRadius)
                    {
                        if (wizardHealth != null) wizardHealth.TakeDamage(projectileDamage);
                        hitWizard = true;
                    }
                }

                if (hitWizard || projectile.RemainingLifetime <= 0f)
                {
                    Destroy(projectile.Visual);
                    projectiles.RemoveAt(index);
                    continue;
                }

                projectiles[index] = projectile;
            }
        }

        private void OnDestroy()
        {
            foreach (Projectile projectile in projectiles)
            {
                if (projectile.Visual != null) Destroy(projectile.Visual);
            }

            projectiles.Clear();
        }
    }
}
