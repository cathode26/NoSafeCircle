using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Hud
{
    /// <summary>A modifier held by one or more UI pointers. A different finger can aim in the world.</summary>
    [DisallowMultipleComponent]
    public sealed class MobileFireHoldButton : MonoBehaviour, IPointerDownHandler, IPointerUpHandler, IPointerEnterHandler, IPointerExitHandler
    {
        [SerializeField] private MobileFireMode mode;
        [SerializeField] private Image background;
        [SerializeField] private Color idleColor = new Color(0.27f, 0.12f, 0.28f, 0.94f);
        [SerializeField] private Color heldColor = new Color(0.72f, 0.25f, 0.47f, 1f);

        private readonly HashSet<int> pointers = new HashSet<int>();
        private MobileGameplayControls owner;
        private PlayerMovement movement;

        public void Bind(MobileGameplayControls controls, PlayerMovement player)
        {
            ReleaseAll();
            owner = controls;
            movement = player;
        }

        public void OnPointerDown(PointerEventData eventData)
        {
            if (eventData.button != PointerEventData.InputButton.Left || owner == null || !owner.CanReceiveInput)
                return;
            owner.BeginHoldGesture(this, eventData.pointerId);
        }

        public void OnPointerUp(PointerEventData eventData)
        {
            if (eventData.button == PointerEventData.InputButton.Left && owner != null)
                owner.EndHoldGesture(eventData.pointerId);
        }

        public void OnPointerEnter(PointerEventData eventData)
        {
            if (owner != null) owner.SlideHoldGesture(this, eventData.pointerId);
        }

        public void OnPointerExit(PointerEventData eventData)
        {
            if (owner != null) owner.ExitHoldGesture(this, eventData.pointerId);
        }

        public void SetPointerHeld(int pointerId, bool held)
        {
            if (held)
            {
                if (pointers.Add(pointerId)) movement.SetMobileFireHeld(mode, pointerId, true);
            }
            else if (pointers.Remove(pointerId) && movement != null)
                movement.SetMobileFireHeld(mode, pointerId, false);
            RefreshVisual();
        }

        public void ReleaseAll()
        {
            if (movement != null)
                foreach (int pointer in pointers)
                    movement.SetMobileFireHeld(mode, pointer, false);
            pointers.Clear();
            RefreshVisual();
        }

        private void LateUpdate()
        {
            // A floor reset or gameplay suspension clears owner state even while a finger stays down.
            if (movement == null || !movement.IsGameplayEnabled || movement.CurrentMobileFireMode == MobileFireMode.None)
                ReleaseAll();
            RefreshVisual();
        }

        private void OnDisable() => ReleaseAll();
        private void RefreshVisual()
        {
            if (background != null) background.color = pointers.Count > 0 || (movement != null && movement.IsMobileFireHeld(mode)) ? heldColor : idleColor;
        }
    }
}
