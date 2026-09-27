using NoSafeCircle.DoorPrototype.Presentation;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// <summary>
    /// Softens the first room's south entrance wall while the wizard passes through it.
    /// Gameplay colliders and the start door leaf keep their authored state.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class WizardEntryWallOcclusion : MonoBehaviour
    {
        private const float ChaseWallOpacity = 0.25f;
        private const float FadeSeconds = 0.12f;

        private GameObject fadeHost;
        private HierarchyFader fader;

        public int TargetCount { get; private set; }
        public int DoorWallTargetCount { get; private set; }
        public bool IsActive => fadeHost != null;

        public bool Begin()
        {
            Restore();
            GameObject roomWalls = GameObject.Find("RuinedEntryWalls");
            if (roomWalls == null)
            {
                Debug.LogWarning("Wizard entry could not find the first room's south wall art.", this);
                return false;
            }

            fadeHost = new GameObject("WizardEntryDoorWallFader", typeof(HierarchyFader));
            fadeHost.transform.SetParent(transform, false);
            fader = fadeHost.GetComponent<HierarchyFader>();
            TargetCount = 0;
            DoorWallTargetCount = 0;

            foreach (SpriteRenderer sprite in
                     roomWalls.GetComponentsInChildren<SpriteRenderer>(true))
            {
                Transform piece = sprite.transform;
                while (piece != null && piece.parent != roomWalls.transform)
                    piece = piece.parent;
                if (piece == null ||
                    Mathf.Abs(piece.position.z - RuinedEntryLayout.MinimumZ) > 0.75f)
                    continue;
                fader.RegisterTarget(new SpriteOpacityTarget(sprite));
                TargetCount++;
                DoorWallTargetCount++;
            }

            if (DoorWallTargetCount == 0)
            {
                Restore();
                Debug.LogWarning("Wizard entry found no south entrance wall sprites.", this);
                return false;
            }

            fader.FadeTo(ChaseWallOpacity, FadeSeconds);
            return true;
        }

        public void Restore()
        {
            if (fader != null) fader.Restore();
            if (fadeHost != null)
            {
                fadeHost.SetActive(false);
                Destroy(fadeHost);
            }
            fader = null;
            fadeHost = null;
            TargetCount = 0;
            DoorWallTargetCount = 0;
        }

        private void OnDisable() => Restore();
        private void OnDestroy() => Restore();

        private sealed class SpriteOpacityTarget : IFadeTarget
        {
            private readonly SpriteRenderer sprite;
            private Color original;

            public SpriteOpacityTarget(SpriteRenderer spriteOwner) => sprite = spriteOwner;
            public bool IsValid => sprite != null;
            public void CaptureOriginalState() => original = sprite.color;
            public void ApplyOpacity(float normalizedOpacity)
            {
                Color color = original;
                color.a *= normalizedOpacity;
                sprite.color = color;
            }
            public void RestoreOriginalState() => sprite.color = original;
        }
    }
}
