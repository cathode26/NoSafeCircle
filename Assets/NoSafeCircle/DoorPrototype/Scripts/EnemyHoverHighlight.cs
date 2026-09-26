using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// AC-001/AC-002: highlights the single enemy the shared PlayerMovement.PointerWorldTarget is
    /// currently over - a plain mouse-over, not an aim cone or facing arc - using the same
    /// shared-pointer-plus-flat-horizontal-distance pattern DoorInteractionFeedback/
    /// DoorInteractable already use for door hover. This adds no collider to the enemy
    /// (SPELL_DECISIONS.md S4 already established enemies carry none) and invents no picking API.
    /// AC-003: a separate component from NSC-114's EnemyAwarenessIndicator, which this never reads
    /// or writes; it only tints this enemy's own body renderer through a MaterialPropertyBlock, so
    /// the indicator's independent SpriteRenderer stays untouched and both remain readable
    /// together. AC-004: no outline/highlight third-party package - just a color swap on an
    /// existing renderer, the same technique DoorInteractionFeedback already ships. AC-005: purely
    /// observational; it never writes to EnemyHealth, EnemyTargetKnowledge, or any pursuit/
    /// movement/spell state.
    [DisallowMultipleComponent]
    public sealed class EnemyHoverHighlight : MonoBehaviour
    {
        [SerializeField] private PlayerMovement playerMovement;
        [SerializeField] private EnemyHealth enemyHealth;
        [SerializeField] private Renderer highlightRenderer;
        [SerializeField] private float hoverRadius = 1f;
        [SerializeField] private Color highlightColor = new Color(1f, 0.9f, 0.3f);

        private static readonly List<EnemyHoverHighlight> activeHighlights = new List<EnemyHoverHighlight>();
        private static readonly int ColorPropertyId = Shader.PropertyToID("_Color");
        private static readonly int BaseColorPropertyId = Shader.PropertyToID("_BaseColor");

        private MaterialPropertyBlock propertyBlock;
        private Color baseColor = Color.white;
        private bool hasCapturedBaseColor;

        /// AC-001: true only while this enemy is the single closest active, non-defeated enemy
        /// whose flat horizontal distance to the shared pointer target is within hoverRadius.
        /// Resolved against every other enabled EnemyHoverHighlight each frame (see
        /// IsClosestHoveredEnemy) so overlapping hover radii never light up more than one enemy at
        /// once, and none is highlighted when the cursor is over none.
        public bool IsHighlighted { get; private set; }

        private void Awake()
        {
            if (enemyHealth == null) enemyHealth = GetComponent<EnemyHealth>();
            if (playerMovement == null) playerMovement = FindFirstObjectByType<PlayerMovement>();
            if (highlightRenderer == null) highlightRenderer = GetComponentInChildren<Renderer>();

            propertyBlock = new MaterialPropertyBlock();
        }

        private void OnEnable()
        {
            activeHighlights.Add(this);
            CaptureBaseColorIfNeeded();
        }

        private void OnDisable()
        {
            activeHighlights.Remove(this);
            IsHighlighted = false;
            ApplyAppearance();
        }

        private void Update()
        {
            Tick();
        }

        /// Advances hover resolution for this frame. Public so Play Mode tests can drive it
        /// deterministically after moving the shared pointer target, mirroring
        /// DoorInteractionFeedback.Tick/PlayerMovement.Tick.
        public void Tick()
        {
            SetHighlighted(TryGetHoverDistance(out var distance) && IsClosestHoveredEnemy(distance));
        }

        /// AC-002: flat horizontal distance test against the shared pointer target, following the
        /// committed DoorInteractionFeedback/DoorInteractable pattern rather than a raycast against
        /// a newly added collider.
        private bool TryGetHoverDistance(out float distance)
        {
            distance = 0f;

            if (enemyHealth != null && enemyHealth.IsDefeated) return false;
            if (playerMovement == null || !playerMovement.HasPointerWorldTarget) return false;

            var offset = playerMovement.PointerWorldTarget - transform.position;
            offset.y = 0f;
            distance = offset.magnitude;
            return distance <= hoverRadius;
        }

        /// AC-001: resolves the "at most one enemy highlighted" rule across every enabled
        /// EnemyHoverHighlight sharing the same pointer target, so two enemies whose hover radii
        /// both cover the cursor never both light up. Ties break toward the lower instance ID so
        /// the outcome is deterministic rather than dependent on Update call order.
        private bool IsClosestHoveredEnemy(float ownDistance)
        {
            for (int i = 0; i < activeHighlights.Count; i++)
            {
                var other = activeHighlights[i];
                if (other == this || other == null) continue;
                if (!other.TryGetHoverDistance(out var otherDistance)) continue;

                if (otherDistance < ownDistance) return false;
                if (Mathf.Approximately(otherDistance, ownDistance) && other.GetInstanceID() < GetInstanceID())
                {
                    return false;
                }
            }

            return true;
        }

        private void SetHighlighted(bool highlighted)
        {
            IsHighlighted = highlighted;
            ApplyAppearance();
        }

        private void CaptureBaseColorIfNeeded()
        {
            if (hasCapturedBaseColor || highlightRenderer == null) return;

            var sharedMaterial = highlightRenderer.sharedMaterial;
            if (sharedMaterial != null && sharedMaterial.HasProperty(BaseColorPropertyId))
            {
                baseColor = sharedMaterial.GetColor(BaseColorPropertyId);
            }
            else if (sharedMaterial != null && sharedMaterial.HasProperty(ColorPropertyId))
            {
                baseColor = sharedMaterial.GetColor(ColorPropertyId);
            }

            hasCapturedBaseColor = true;
        }

        private void ApplyAppearance()
        {
            if (highlightRenderer == null) return;

            var color = IsHighlighted ? highlightColor : baseColor;

            if (propertyBlock == null) propertyBlock = new MaterialPropertyBlock();
            highlightRenderer.GetPropertyBlock(propertyBlock);
            propertyBlock.SetColor(ColorPropertyId, color);
            propertyBlock.SetColor(BaseColorPropertyId, color);
            highlightRenderer.SetPropertyBlock(propertyBlock);
        }
    }
}
