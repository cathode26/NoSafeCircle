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
        private const float DirectionTieEpsilon = 0.0001f;
        internal const string CanonicalInitialDirection = "south-east";

        private static readonly string[] screenDirections =
        {
            "north-east", "east", "south-east", "south",
            "south-west", "west", "north-west", "north"
        };

        private static readonly Vector2[] screenDirectionVectors =
        {
            new Vector2(0.70710677f, 0.70710677f),
            new Vector2(1f, 0f),
            new Vector2(0.70710677f, -0.70710677f),
            new Vector2(0f, -1f),
            new Vector2(-0.70710677f, -0.70710677f),
            new Vector2(-1f, 0f),
            new Vector2(-0.70710677f, 0.70710677f),
            new Vector2(0f, 1f)
        };

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

        // The fixed camera maps world movement into screen coordinates where
        // horizontal = X + Z and vertical = X - Z. The eight equally spaced screen
        // sectors therefore cover both the world axes and their diagonals.
        private static string DirectionFor(Vector3 movement)
        {
            Vector2 screenMovement = new Vector2(
                movement.x + movement.z, movement.x - movement.z);
            if (screenMovement.sqrMagnitude < DirectionThreshold * DirectionThreshold)
                return CanonicalInitialDirection;

            int bestIndex = 0;
            float bestScore = Vector2.Dot(screenMovement, screenDirectionVectors[0]);
            for (int index = 1; index < screenDirections.Length; index++)
            {
                float score = Vector2.Dot(screenMovement, screenDirectionVectors[index]);
                float tieEpsilon = DirectionTieEpsilon * screenMovement.magnitude;
                bool isTie = Mathf.Abs(score - bestScore) <= tieEpsilon;
                bool prefersWorldAxis = IsWorldAxisDirection(index) &&
                                         !IsWorldAxisDirection(bestIndex);
                if (score > bestScore + tieEpsilon || (isTie && prefersWorldAxis))
                {
                    bestIndex = index;
                    bestScore = score;
                }
            }

            return screenDirections[bestIndex];
        }

        private static bool IsWorldAxisDirection(int directionIndex)
        {
            return directionIndex % 2 == 0;
        }

        // Keep the prior sector while a new sector's projection is only marginally
        // stronger. Scaling the margin by movement length makes the hysteresis angular,
        // so it behaves consistently for slow and fast transforms.
        private static string StableDirectionFor(Vector3 movement, string previousDirection)
        {
            Vector2 screenMovement = new Vector2(
                movement.x + movement.z, movement.x - movement.z);
            float movementLength = screenMovement.magnitude;
            if (movementLength < DirectionThreshold * Mathf.Sqrt(2f))
                return previousDirection;

            string candidateDirection = DirectionFor(movement);
            if (string.IsNullOrEmpty(previousDirection))
                return candidateDirection;

            float candidateScore = Vector2.Dot(
                screenMovement, screenDirectionVectors[IndexOf(candidateDirection)]);
            float previousScore = Vector2.Dot(
                screenMovement, screenDirectionVectors[IndexOf(previousDirection)]);
            if (previousScore + DirectionSwitchMargin * movementLength >= candidateScore)
                return previousDirection;

            return candidateDirection;
        }

        private static int IndexOf(string direction)
        {
            for (int index = 0; index < screenDirections.Length; index++)
            {
                if (screenDirections[index] == direction)
                    return index;
            }

            return 0;
        }
    }
}
