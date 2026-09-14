using System;
using System.Collections.Generic;
using DG.Tweening;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Presentation
{
    /// <summary>A visual participant whose original state is owned by a HierarchyFader.</summary>
    public interface IFadeTarget
    {
        bool IsValid { get; }
        void CaptureOriginalState();
        void ApplyOpacity(float normalizedOpacity);
        void RestoreOriginalState();
    }

    /// <summary>
    /// Fades a hierarchy's visual alpha without changing gameplay state or cloning materials.
    /// A completed ordinary fade keeps its terminal opacity; Restore or the default Cancel
    /// returns every participant to the state captured before the first owned fade.
    /// Disabling or destroying the component always cancels and restores.
    /// </summary>
    public sealed class HierarchyFader : MonoBehaviour
    {
        [SerializeField] private Transform targetRoot;
        [SerializeField] private bool includeInactive = true;

        private readonly List<IFadeTarget> registeredTargets = new List<IFadeTarget>();
        private readonly List<IFadeTarget> activeTargets = new List<IFadeTarget>();
        private Tween ownedTween;
        private bool captured;
        private float currentOpacity = 1f;

        public float CurrentOpacity => currentOpacity;
        public bool HasOwnedTween => ownedTween != null && ownedTween.IsActive();

        /// <summary>Adds a custom adapter. The fader, not its caller, starts capture.</summary>
        public void RegisterTarget(IFadeTarget target)
        {
            if (target == null) throw new ArgumentNullException(nameof(target));
            if (registeredTargets.Contains(target)) return;
            registeredTargets.Add(target);
            if (!captured || !target.IsValid) return;

            target.CaptureOriginalState();
            target.ApplyOpacity(currentOpacity);
            activeTargets.Add(target);
        }

        /// <summary>Restores a registered target before removing it from this fader.</summary>
        public void UnregisterTarget(IFadeTarget target)
        {
            if (target == null || !registeredTargets.Remove(target)) return;
            if (!activeTargets.Remove(target) || !target.IsValid) return;
            target.RestoreOriginalState();
        }

        /// <summary>
        /// Starts a fade from the current normalized opacity. A replacement kills the old
        /// tween without restoring, so it starts smoothly from the visible value.
        /// A zero-duration fade applies immediately and returns null.
        /// </summary>
        public Tween FadeTo(float normalizedOpacity, float duration, bool restoreOnComplete = false)
        {
            if (!isActiveAndEnabled) throw new InvalidOperationException("The fader must be enabled to start a fade.");
            if (float.IsNaN(normalizedOpacity) || normalizedOpacity < 0f || normalizedOpacity > 1f)
                throw new ArgumentOutOfRangeException(nameof(normalizedOpacity));
            if (float.IsNaN(duration) || duration < 0f || float.IsInfinity(duration))
                throw new ArgumentOutOfRangeException(nameof(duration));
            if (duration > 0f && !Application.isPlaying)
                throw new InvalidOperationException("Timed DOTween fades require Play Mode.");

            CaptureTargetsIfNeeded();
            KillOwnedTween();
            if (duration == 0f)
            {
                ApplyOpacity(normalizedOpacity);
                if (restoreOnComplete) Restore();
                return null;
            }

            Tween tween = DOTween.To(() => currentOpacity, ApplyOpacity, normalizedOpacity, duration)
                .SetEase(Ease.Linear)
                .SetRecyclable(false)
                .SetTarget(this);
            tween.OnComplete(() =>
            {
                if (restoreOnComplete) Restore();
            });
            tween.OnKill(() =>
            {
                if (ReferenceEquals(ownedTween, tween)) ownedTween = null;
            });
            ownedTween = tween;
            return tween;
        }

        /// <summary>
        /// Stops the current tween. By default the original state is restored; passing false
        /// holds the current visual opacity until another fade or an explicit Restore.
        /// </summary>
        public void Cancel(bool restoreOriginalState = true)
        {
            KillOwnedTween();
            if (restoreOriginalState) RestoreOriginalState();
        }

        public void Restore()
        {
            KillOwnedTween();
            RestoreOriginalState();
        }

        /// <summary>Restores current targets, then discovers the hierarchy again next fade.</summary>
        public void RefreshTargets()
        {
            Restore();
        }

#if UNITY_EDITOR
        [ContextMenu("Preview/Fade Out")]
        private void PreviewFadeOut()
        {
            if (Application.isPlaying) FadeTo(0f, 0.75f);
        }

        [ContextMenu("Preview/Restore")]
        private void PreviewRestore() => Restore();
#endif

        private void OnDisable() => Restore();
        private void OnDestroy() => Restore();

        private void KillOwnedTween()
        {
            Tween tween = ownedTween;
            ownedTween = null;
            if (tween != null && tween.IsActive()) tween.Kill(false);
        }

        private void RestoreOriginalState()
        {
            if (!captured) return;
            foreach (IFadeTarget target in activeTargets)
                if (target.IsValid) target.RestoreOriginalState();
            activeTargets.Clear();
            captured = false;
            currentOpacity = 1f;
        }

        private void ApplyOpacity(float opacity)
        {
            // DOTween can invoke its setter during teardown; never mutate a disabled owner.
            if (!isActiveAndEnabled) return;
            currentOpacity = Mathf.Clamp01(opacity);
            foreach (IFadeTarget target in activeTargets)
                if (target.IsValid) target.ApplyOpacity(currentOpacity);
        }

        private void CaptureTargetsIfNeeded()
        {
            if (captured) return;
            Transform root = targetRoot != null ? targetRoot : transform;
            var canvasGroups = root.GetComponentsInChildren<CanvasGroup>(includeInactive);
            var allGroups = new HashSet<CanvasGroup>(canvasGroups);
            var selectedGroups = new HashSet<CanvasGroup>();
            foreach (CanvasGroup group in canvasGroups)
            {
                if (HasSelectedCanvasGroup(group.transform.parent, root, allGroups)) continue;
                selectedGroups.Add(group);
                AddCapturedTarget(new CanvasGroupTarget(group));
            }

            foreach (Graphic graphic in root.GetComponentsInChildren<Graphic>(includeInactive))
                if (!HasSelectedCanvasGroup(graphic.transform, root, selectedGroups))
                    AddCapturedTarget(new GraphicTarget(graphic));

            foreach (SpriteRenderer sprite in root.GetComponentsInChildren<SpriteRenderer>(includeInactive))
                AddCapturedTarget(new SpriteTarget(sprite));

            foreach (Renderer renderer in root.GetComponentsInChildren<Renderer>(includeInactive))
            {
                if (renderer is SpriteRenderer) continue;
                if (RendererColorTarget.TryCreate(renderer, out RendererColorTarget target))
                    AddCapturedTarget(target);
            }

            foreach (IFadeTarget target in registeredTargets)
                AddCapturedTarget(target);
            captured = true;
        }

        private void AddCapturedTarget(IFadeTarget target)
        {
            if (!target.IsValid) return;
            target.CaptureOriginalState();
            activeTargets.Add(target);
        }

        private static bool HasSelectedCanvasGroup(Transform objectTransform, Transform root,
            HashSet<CanvasGroup> selectedGroups)
        {
            for (Transform current = objectTransform; current != null; current = current.parent)
            {
                CanvasGroup group = current.GetComponent<CanvasGroup>();
                if (group != null && selectedGroups.Contains(group)) return true;
                if (current == root) break;
            }
            return false;
        }

        private sealed class CanvasGroupTarget : IFadeTarget
        {
            private readonly CanvasGroup group;
            private float originalAlpha;
            public CanvasGroupTarget(CanvasGroup group) => this.group = group;
            public bool IsValid => group != null;
            public void CaptureOriginalState() => originalAlpha = group.alpha;
            public void ApplyOpacity(float opacity) => group.alpha = originalAlpha * opacity;
            public void RestoreOriginalState() => group.alpha = originalAlpha;
        }

        private sealed class GraphicTarget : IFadeTarget
        {
            private readonly Graphic graphic;
            private Color originalColor;
            public GraphicTarget(Graphic graphic) => this.graphic = graphic;
            public bool IsValid => graphic != null;
            public void CaptureOriginalState() => originalColor = graphic.color;
            public void ApplyOpacity(float opacity)
            {
                Color color = originalColor;
                color.a *= opacity;
                graphic.color = color;
            }
            public void RestoreOriginalState() => graphic.color = originalColor;
        }

        private sealed class SpriteTarget : IFadeTarget
        {
            private readonly SpriteRenderer sprite;
            private Color originalColor;
            public SpriteTarget(SpriteRenderer sprite) => this.sprite = sprite;
            public bool IsValid => sprite != null;
            public void CaptureOriginalState() => originalColor = sprite.color;
            public void ApplyOpacity(float opacity)
            {
                Color color = originalColor;
                color.a *= opacity;
                sprite.color = color;
            }
            public void RestoreOriginalState() => sprite.color = originalColor;
        }

        private sealed class RendererColorTarget : IFadeTarget
        {
            private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
            private static readonly int ColorId = Shader.PropertyToID("_Color");
            private readonly Renderer renderer;
            private readonly int colorPropertyId;
            private MaterialPropertyBlock originalBlock;
            private MaterialPropertyBlock workingBlock;
            private Color originalColor;

            private RendererColorTarget(Renderer renderer, int colorPropertyId)
            {
                this.renderer = renderer;
                this.colorPropertyId = colorPropertyId;
            }

            public static bool TryCreate(Renderer renderer, out RendererColorTarget target)
            {
                target = null;
                Material material = renderer.sharedMaterial;
                if (material == null) return false;
                int propertyId = material.HasProperty(BaseColorId) ? BaseColorId :
                    material.HasProperty(ColorId) ? ColorId : -1;
                if (propertyId < 0) return false;
                target = new RendererColorTarget(renderer, propertyId);
                return true;
            }

            public bool IsValid => renderer != null;
            public void CaptureOriginalState()
            {
                originalBlock = new MaterialPropertyBlock();
                renderer.GetPropertyBlock(originalBlock);
                workingBlock = new MaterialPropertyBlock();
                renderer.GetPropertyBlock(workingBlock);
                originalColor = originalBlock.HasColor(colorPropertyId)
                    ? originalBlock.GetColor(colorPropertyId)
                    : renderer.sharedMaterial.GetColor(colorPropertyId);
            }

            public void ApplyOpacity(float opacity)
            {
                Color color = originalColor;
                color.a *= opacity;
                workingBlock.SetColor(colorPropertyId, color);
                renderer.SetPropertyBlock(workingBlock);
            }

            public void RestoreOriginalState() => renderer.SetPropertyBlock(originalBlock);
        }
    }
}
