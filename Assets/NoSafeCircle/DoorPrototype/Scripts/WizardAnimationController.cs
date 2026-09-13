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
            if (isWalking) lastDirection = DirectionFor(displacement);

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

        private static string DirectionFor(Vector3 movement)
        {
            if (movement.z >= 0f)
                return movement.x >= 0f ? "north-east" : "north-west";
            return movement.x >= 0f ? "south-east" : "south-west";
        }
    }
}
