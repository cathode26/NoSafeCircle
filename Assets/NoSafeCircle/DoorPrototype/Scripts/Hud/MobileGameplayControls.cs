using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.InputSystem;

namespace NoSafeCircle.DoorPrototype.Hud
{
    /// <summary>Owns the authored mobile HUD, its safe-area placement and landscape-only input.</summary>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(CanvasGroup))]
    public sealed class MobileGameplayControls : MonoBehaviour
    {
        [SerializeField] private RectTransform safeArea;
        [SerializeField] private MobileFireHoldButton standFireButton;
        [SerializeField] private MobileFireHoldButton moveFireButton;
        [SerializeField] private MobileWorldTapSurface worldTapSurface;

        private CanvasGroup group;
        private PlayerMovement movement;
        private DemoRunFlow run;
        private PlayerHealth health;
        private bool hasFocus = true;
        private bool paused;
        private bool landscapeInitialized;

        public bool CanReceiveInput => isActiveAndEnabled && hasFocus && !paused
            && movement != null && movement.IsGameplayEnabled
            && (health == null || health.CurrentHealth > 0f)
            && (run == null || !run.HasEnded)
            && IsTouchDevice && Screen.width >= Screen.height;

        public static bool IsTouchDevice => Application.isMobilePlatform || Touchscreen.current != null;

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] private static extern void NSC_InitializeMobileLandscape();
        [DllImport("__Internal")] private static extern void NSC_DisposeMobileLandscape();
#endif

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void SetLandscapeOrientation()
        {
#if !UNITY_WEBGL
            if (!Application.isMobilePlatform) return;
            Screen.autorotateToPortrait = false;
            Screen.autorotateToPortraitUpsideDown = false;
            Screen.autorotateToLandscapeLeft = true;
            Screen.autorotateToLandscapeRight = true;
            Screen.orientation = ScreenOrientation.LandscapeLeft;
            Screen.orientation = ScreenOrientation.AutoRotation;
#endif
        }

        private void Awake()
        {
            group = GetComponent<CanvasGroup>();
            ApplyPresentation();
        }

        public void Bind(PlayerMovement player, DemoRunFlow flow)
        {
            ClearHolds();
            movement = player;
            run = flow;
            health = player != null ? player.GetComponent<PlayerHealth>() : null;
            standFireButton.Bind(this, player);
            moveFireButton.Bind(this, player);
            worldTapSurface.Bind(this, player);
            ApplyPresentation();
        }

        private void LateUpdate() => ApplyPresentation();

        private void ApplyPresentation()
        {
            if (group == null) return;
#if UNITY_WEBGL && !UNITY_EDITOR
            if (IsTouchDevice && !landscapeInitialized)
            {
                NSC_InitializeMobileLandscape();
                landscapeInitialized = true;
            }
#endif
            bool visible = CanReceiveInput;
            group.alpha = visible ? 1f : 0f;
            group.interactable = visible;
            group.blocksRaycasts = visible;
            if (!visible) ClearHolds();

            if (safeArea == null || Screen.width <= 0 || Screen.height <= 0) return;
            Rect area = Screen.safeArea;
            safeArea.anchorMin = new Vector2(area.xMin / Screen.width, area.yMin / Screen.height);
            safeArea.anchorMax = new Vector2(area.xMax / Screen.width, area.yMax / Screen.height);
            safeArea.offsetMin = Vector2.zero;
            safeArea.offsetMax = Vector2.zero;
        }

        private void ClearHolds()
        {
            if (standFireButton != null) standFireButton.ReleaseAll();
            if (moveFireButton != null) moveFireButton.ReleaseAll();
        }

        private void OnApplicationFocus(bool focused)
        {
            hasFocus = focused;
            ApplyPresentation();
        }

        private void OnApplicationPause(bool isPaused)
        {
            paused = isPaused;
            ApplyPresentation();
        }

        private void OnDisable()
        {
            ClearHolds();
            if (group != null)
            {
                group.alpha = 0f;
                group.interactable = false;
                group.blocksRaycasts = false;
            }
        }

        private void OnDestroy()
        {
            ClearHolds();
#if UNITY_WEBGL && !UNITY_EDITOR
            if (landscapeInitialized) NSC_DisposeMobileLandscape();
#endif
        }
    }
}
