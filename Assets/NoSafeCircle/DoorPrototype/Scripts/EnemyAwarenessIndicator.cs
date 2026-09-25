using NoSafeCircle.DoorPrototype.Enemies;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// AC-001: a read-only presenter over NSC-091's EnemyTargetKnowledge.State. It never writes,
    /// clears, or advances detection/pursuit/search state and never influences attack timing -
    /// it only reads State every frame and reflects it. "Currently detected" means actively
    /// Pursuing: SearchingLastKnownPosition/Wandering still remember a target
    /// (EnemyTargetKnowledge.HasTarget stays true) but the enemy has lost the wizard, so using
    /// HasTarget here would incorrectly latch the indicator on through the search phase.
    /// AC-003: the icon artwork itself is the Art Director's to choose and deliver, including
    /// its .meta import settings. This binds whatever Sprite it is given through a serialized
    /// reference; swapping the final art in later needs no change to this component.
    [DisallowMultipleComponent]
    public sealed class EnemyAwarenessIndicator : MonoBehaviour
    {
        [SerializeField] private EnemyTargetKnowledge targetKnowledge;
        [SerializeField] private SpriteRenderer indicatorRenderer;
        [SerializeField] private Sprite detectedIcon;

        private static Sprite missingIconFallbackSprite;

        private bool isLoggingMissingIcon;

        public bool IsDetected { get; private set; }

        private void Awake()
        {
            if (targetKnowledge == null) targetKnowledge = GetComponent<EnemyTargetKnowledge>();
        }

        private void Update()
        {
            IsDetected = targetKnowledge != null && targetKnowledge.State == EnemyTargetKnowledgeState.Pursuing;
            ApplyVisualState(IsDetected);
        }

        private void OnDisable()
        {
            if (indicatorRenderer != null) indicatorRenderer.enabled = false;
            isLoggingMissingIcon = false;
        }

        private void ApplyVisualState(bool isDetected)
        {
            if (indicatorRenderer == null) return;

            if (!isDetected)
            {
                indicatorRenderer.enabled = false;
                isLoggingMissingIcon = false;
                return;
            }

            if (detectedIcon != null)
            {
                indicatorRenderer.sprite = detectedIcon;
                indicatorRenderer.color = Color.white;
                indicatorRenderer.enabled = true;
                isLoggingMissingIcon = false;
                return;
            }

            // A missing art binding must never be mistaken for the enemy not having noticed the
            // wizard, so a bare disabled/blank renderer is not acceptable here. Render an
            // unmistakable code-only fallback marker and log once per occurrence instead.
            if (!isLoggingMissingIcon)
            {
                Debug.LogError($"EnemyAwarenessIndicator on '{name}' has detected the wizard but no " +
                    "detected-state icon is bound; rendering a fallback marker instead of silently " +
                    "showing nothing.");
                isLoggingMissingIcon = true;
            }

            indicatorRenderer.sprite = GetMissingIconFallbackSprite();
            indicatorRenderer.color = Color.magenta;
            indicatorRenderer.enabled = true;
        }

        private static Sprite GetMissingIconFallbackSprite()
        {
            if (missingIconFallbackSprite == null)
            {
                Texture2D texture = Texture2D.whiteTexture;
                missingIconFallbackSprite = Sprite.Create(
                    texture, new Rect(0f, 0f, texture.width, texture.height), new Vector2(0.5f, 0.5f));
            }

            return missingIconFallbackSprite;
        }
    }
}
