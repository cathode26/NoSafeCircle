using UnityEngine;
using UnityEngine.InputSystem;

namespace NoSafeCircle.DoorPrototype
{
    [RequireComponent(typeof(CharacterController))]
    public class PlayerMovement : MonoBehaviour
    {
        private const float MovementThreshold = 0.001f;

        [SerializeField] private float moveSpeed = 4f;
        [SerializeField] private PlayerInteractionController interactionController;

        private CharacterController controller;

        private void Awake()
        {
            controller = GetComponent<CharacterController>();
            if (interactionController == null) interactionController = GetComponent<PlayerInteractionController>();
        }

        private void Update()
        {
            var keyboard = Keyboard.current;
            if (keyboard == null) return;

            var input = Vector2.zero;
            if (keyboard.wKey.isPressed) input.y += 1f;
            if (keyboard.sKey.isPressed) input.y -= 1f;
            if (keyboard.dKey.isPressed) input.x += 1f;
            if (keyboard.aKey.isPressed) input.x -= 1f;

            var horizontal = new Vector3(input.x, 0f, input.y);
            if (horizontal.sqrMagnitude > MovementThreshold)
            {
                horizontal = horizontal.normalized * moveSpeed;
            }

            var move = new Vector3(horizontal.x, -0.1f, horizontal.z);
            controller.Move(move * Time.deltaTime);

            if (input.sqrMagnitude > MovementThreshold)
            {
                interactionController?.OnPlayerMoved();
            }
        }
    }
}
