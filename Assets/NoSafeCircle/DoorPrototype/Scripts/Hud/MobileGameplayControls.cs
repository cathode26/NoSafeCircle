using System.Runtime.InteropServices;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;

namespace NoSafeCircle.DoorPrototype.Hud
{
    /// <summary>Owns the authored mobile HUD, its safe-area placement and landscape-only input.</summary>
    [DefaultExecutionOrder(-1100)]
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
        private readonly Dictionary<int, MobileFireHoldButton> holdGestures = new Dictionary<int, MobileFireHoldButton>();
#if UNITY_EDITOR
        public static bool EditorPreviewEnabled { get; set; }
        private const int PreviewStandPointer = -10001;
        private const int PreviewMovingPointer = -10002;
        private bool previewKeysNeedRelease;
#endif
        public bool UsesTouchControls => IsTouchDevice
#if UNITY_EDITOR
            || EditorPreviewEnabled
#endif
            ;

        public bool CanReceiveInput => isActiveAndEnabled && hasFocus && !paused
            && movement != null && movement.IsGameplayEnabled
            && (health == null || health.CurrentHealth > 0f)
            && (run == null || !run.HasEnded)
            && UsesTouchControls && Screen.width >= Screen.height;

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
            if (movement != null)
            {
                movement.MobileFireHoldsCleared -= OnPlayerHoldsCleared;
                movement.SetMobileWorldInputEnabled(false);
            }
            movement = player;
            if (movement != null && isActiveAndEnabled) movement.MobileFireHoldsCleared += OnPlayerHoldsCleared;
            run = flow;
            health = player != null ? player.GetComponent<PlayerHealth>() : null;
            standFireButton.Bind(this, player);
            moveFireButton.Bind(this, player);
            worldTapSurface.Bind(this, player);
            ApplyPresentation();
        }

        private void Update()
        {
            ApplyPresentation();
#if UNITY_EDITOR
            RefreshEditorModifiers();
#endif
        }
        private void LateUpdate() => ApplyPresentation();
        private void OnEnable()
        {
            if (movement != null) movement.MobileFireHoldsCleared += OnPlayerHoldsCleared;
        }

        public void BeginHoldGesture(MobileFireHoldButton button, int pointerId)
        {
            if (!CanReceiveInput) return;
            EndHoldGesture(pointerId);
            holdGestures.Add(pointerId, button);
            button.SetPointerHeld(pointerId, true);
        }

        public void SlideHoldGesture(MobileFireHoldButton button, int pointerId)
        {
            // Only a finger that started on a fire button can slide between modes.
            if (!CanReceiveInput || !holdGestures.TryGetValue(pointerId, out MobileFireHoldButton previous)
                || previous == button) return;
            if (previous != null) previous.SetPointerHeld(pointerId, false);
            holdGestures[pointerId] = button;
            button.SetPointerHeld(pointerId, true);
        }

        public void ExitHoldGesture(MobileFireHoldButton button, int pointerId)
        {
            if (!holdGestures.TryGetValue(pointerId, out MobileFireHoldButton current) || current != button) return;
            button.SetPointerHeld(pointerId, false);
            holdGestures[pointerId] = null; // Keep its button origin so entering the next button can press it.
        }

        public void EndHoldGesture(int pointerId)
        {
            // UGUI sends pointer-up to the original press target, even after a slide.
            if (!holdGestures.TryGetValue(pointerId, out MobileFireHoldButton current)) return;
            holdGestures.Remove(pointerId);
            if (current != null) current.SetPointerHeld(pointerId, false);
        }

        private void OnPlayerHoldsCleared() => ClearHolds();

#if UNITY_EDITOR
        private void RefreshEditorModifiers()
        {
            Keyboard keyboard = Keyboard.current;
            bool stand = keyboard != null && keyboard.leftCtrlKey.isPressed;
            bool moving = keyboard != null && keyboard.leftShiftKey.isPressed;
            if (!EditorPreviewEnabled || !CanReceiveInput || previewKeysNeedRelease)
            {
                movement?.SetMobileFireHeld(MobileFireMode.StandAndFire, PreviewStandPointer, false);
                movement?.SetMobileFireHeld(MobileFireMode.FireWhileMoving, PreviewMovingPointer, false);
                if (!stand && !moving) previewKeysNeedRelease = false;
                return;
            }
            movement.SetMobileFireHeld(MobileFireMode.FireWhileMoving, PreviewMovingPointer, moving);
            movement.SetMobileFireHeld(MobileFireMode.StandAndFire, PreviewStandPointer, stand);
        }
#endif

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
            if (movement != null) movement.SetMobileWorldInputEnabled(UsesTouchControls);
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
            holdGestures.Clear();
#if UNITY_EDITOR
            Keyboard keyboard = Keyboard.current;
            previewKeysNeedRelease = keyboard != null && (keyboard.leftCtrlKey.isPressed || keyboard.leftShiftKey.isPressed);
            movement?.SetMobileFireHeld(MobileFireMode.StandAndFire, PreviewStandPointer, false);
            movement?.SetMobileFireHeld(MobileFireMode.FireWhileMoving, PreviewMovingPointer, false);
#endif
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
            if (movement != null)
            {
                movement.MobileFireHoldsCleared -= OnPlayerHoldsCleared;
                movement.SetMobileWorldInputEnabled(false);
            }
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
            if (movement != null)
            {
                movement.MobileFireHoldsCleared -= OnPlayerHoldsCleared;
                movement.SetMobileWorldInputEnabled(false);
            }
            ClearHolds();
#if UNITY_WEBGL && !UNITY_EDITOR
            if (landscapeInitialized) NSC_DisposeMobileLandscape();
#endif
        }
    }
}
