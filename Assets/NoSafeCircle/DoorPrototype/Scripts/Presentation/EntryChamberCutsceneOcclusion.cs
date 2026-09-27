using NoSafeCircle.DoorPrototype.Presentation;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// <summary>
    /// Softens only the chamber wall sprites that cross the entrance chase camera.
    /// Gameplay colliders and the start door leaf keep their authored state.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class EntryChamberCutsceneOcclusion : MonoBehaviour
    {
        private const float ChaseWallOpacity = 0.25f;
        private const float FadeSeconds = 0.12f;

        private GameObject fadeHost;
        private HierarchyFader fader;

        public int TargetCount { get; private set; }
        public int SouthWallTargetCount { get; private set; }
        public int GateFlankTargetCount { get; private set; }
        public bool IsActive => fadeHost != null;

        public bool Begin()
        {
            Restore();
            GameObject chamberWalls = GameObject.Find("EntryChamberWalls");
            GameObject gateFlanks = GameObject.Find("EntryChamberGateWall");
            if (chamberWalls == null || gateFlanks == null)
            {
                Debug.LogWarning("Entry chamber chase could not find its foreground wall art.", this);
                return false;
            }

            fadeHost = new GameObject("EntryChamberCutsceneWallFader", typeof(HierarchyFader));
            fadeHost.transform.SetParent(transform, false);
            fader = fadeHost.GetComponent<HierarchyFader>();
            TargetCount = 0;
            SouthWallTargetCount = 0;
            GateFlankTargetCount = 0;

            foreach (SpriteRenderer sprite in
                     chamberWalls.GetComponentsInChildren<SpriteRenderer>(true))
            {
                Transform piece = sprite.transform;
                while (piece != null && piece.parent != chamberWalls.transform)
                    piece = piece.parent;
                if (piece == null ||
                    piece.position.z > EntryChamberLayout.MinimumZ + 0.05f)
                    continue;
                fader.RegisterTarget(new SpriteOpacityTarget(sprite));
                TargetCount++;
                SouthWallTargetCount++;
            }

            foreach (SpriteRenderer sprite in
                     gateFlanks.GetComponentsInChildren<SpriteRenderer>(true))
            {
                fader.RegisterTarget(new SpriteOpacityTarget(sprite));
                TargetCount++;
                GateFlankTargetCount++;
            }

            if (SouthWallTargetCount == 0 || GateFlankTargetCount == 0)
            {
                Restore();
                Debug.LogWarning("Entry chamber chase found no foreground wall sprites.", this);
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
            SouthWallTargetCount = 0;
            GateFlankTargetCount = 0;
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
