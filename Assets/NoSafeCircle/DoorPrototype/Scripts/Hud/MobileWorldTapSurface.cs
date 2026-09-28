using UnityEngine;
using UnityEngine.EventSystems;

namespace NoSafeCircle.DoorPrototype.Hud
{
    /// <summary>The transparent UI surface behind the hold buttons receives each world finger independently.</summary>
    [DisallowMultipleComponent]
    public sealed class MobileWorldTapSurface : MonoBehaviour, IPointerDownHandler
    {
        private MobileGameplayControls owner;
        private PlayerMovement movement;

        public void Bind(MobileGameplayControls controls, PlayerMovement player)
        {
            owner = controls;
            movement = player;
        }

        public void OnPointerDown(PointerEventData eventData)
        {
            if (eventData.button == PointerEventData.InputButton.Left && owner != null && owner.CanReceiveInput)
                movement.HandleWorldTap(eventData.position);
        }
    }
}
