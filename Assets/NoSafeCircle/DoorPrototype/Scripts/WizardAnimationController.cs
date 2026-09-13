using System;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    public enum WizardPresentation
    {
        Masculine,
        Feminine
    }

    public enum WizardSkin
    {
        White,
        Black
    }

    /// Owns only the Player visual's selected art and animation state.
    /// Movement and collision remain owned by PlayerMovement and CharacterController.
    [RequireComponent(typeof(Animator))]
    public sealed class WizardAnimationController : MonoBehaviour
    {
        private const float DirectionThreshold = 0.01f;
        private const float DirectionSwitchMargin = 0.001f;
        internal const string CanonicalInitialDirection = "south-east";

        [SerializeField] private WizardPresentation presentation = WizardPresentation.Masculine;
        [SerializeField] private WizardSkin skin = WizardSkin.White;
        [SerializeField] private Animator animator;

        private SpriteRenderer spriteRenderer;
        private Vector3 previousPosition;
        private string currentState;
        private string lastDirection = CanonicalInitialDirection;
        private bool ignoreNextDisplacement;

        public WizardPresentation Presentation => presentation;
        public WizardSkin Skin => skin;
        public string CurrentState => currentState;
        public string LastDirection => lastDirection;

        private void Awake()
        {
            if (animator == null) animator = GetComponent<Animator>();
            spriteRenderer = GetComponentInChildren<SpriteRenderer>();
            previousPosition = transform.position;
        }

        private void Update()
        {
            if (ignoreNextDisplacement)
            {
                previousPosition = transform.position;
                ignoreNextDisplacement = false;
                return;
            }

            var displacement = transform.position - previousPosition;
            previousPosition = transform.position;
            displacement.y = 0f;

            var isWalking = displacement.magnitude >= DirectionThreshold;
            if (isWalking) lastDirection = StableDirectionFor(displacement, lastDirection);

            var state = StateName(isWalking ? "walk" : "idle", lastDirection);
            if (state == currentState) return;

            currentState = state;
            if (animator != null && animator.runtimeAnimatorController != null)
                animator.Play(state, 0, 0f);
        }

        /// <summary>
        /// Applies one validated NSC-062 presentation choice without changing Player gameplay state.
        /// </summary>
        public void ApplyPresentation(WizardPresentation selectedPresentation, WizardSkin selectedSkin)
        {
            if (!Enum.IsDefined(typeof(WizardPresentation), selectedPresentation))
                throw new ArgumentOutOfRangeException(nameof(selectedPresentation));
            if (!Enum.IsDefined(typeof(WizardSkin), selectedSkin))
                throw new ArgumentOutOfRangeException(nameof(selectedSkin));

            presentation = selectedPresentation;
            skin = selectedSkin;
            currentState = StateName("idle", lastDirection);
            ignoreNextDisplacement = true;

            if (animator == null) animator = GetComponent<Animator>();
            if (animator == null || animator.runtimeAnimatorController == null) return;

            animator.Play(currentState, 0, 0f);
            animator.Update(0f);
        }

        private string StateName(string motion, string direction)
        {
            return $"Wizard_{presentation}_{skin}_{motion}_{direction}";
        }

        // The fixed camera maps the dominant world axis to a screen diagonal. Using
        // the dominant component keeps a small orthogonal movement component from
        // changing the facing state while the pointer remains in one direction.
        private static string DirectionFor(Vector3 movement)
        {
            if (Mathf.Abs(movement.x) >= Mathf.Abs(movement.z))
                return movement.x >= 0f ? "north-east" : "south-west";

            return movement.z >= 0f ? "south-east" : "north-west";
        }

        // Keep the previously selected world axis until the other component exceeds it
        // by a small margin. This prevents equal-component collision/transform noise from
        // changing the held diagonal state every frame while preserving sign changes.
        private static string StableDirectionFor(Vector3 movement, string previousDirection)
        {
            float absoluteX = Mathf.Abs(movement.x);
            float absoluteZ = Mathf.Abs(movement.z);
            bool previousDirectionUsesX = previousDirection == "north-east" ||
                                          previousDirection == "south-west";
            bool useX = previousDirectionUsesX
                ? absoluteX + DirectionSwitchMargin >= absoluteZ
                : absoluteX > absoluteZ + DirectionSwitchMargin;

            if (useX)
                return movement.x >= 0f ? "north-east" : "south-west";

            return movement.z >= 0f ? "south-east" : "north-west";
        }
    }
}
