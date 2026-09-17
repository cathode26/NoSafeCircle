using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    public enum EnemyAnimationKind
    {
        MeleeEnemy,
        LanternWraith
    }

    /// Selects the directional idle or walk state and keeps the enemy Visual camera-facing
    /// without owning movement.
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Animator))]
    public sealed class EnemyAnimationController : MonoBehaviour
    {
        public static readonly Vector3 IsometricCameraEulerAngles =
            new Vector3(30f, -45f, 0f);

        private const float DirectionThreshold = 0.01f;
        private const float DirectionSwitchMargin = 0.001f;
        private const float DirectionTieEpsilon = 0.0001f;
        private const float StartWalkingSpeed = 0.1f;
        private const float StopWalkingSpeed = 0.05f;
        private const string InitialDirection = "south";

        private static readonly string[] ScreenDirections =
        {
            "north-east", "east", "south-east", "south",
            "south-west", "west", "north-west", "north"
        };

        private static readonly string[][] IdleStateNames =
        {
            new[]
            {
                "MeleeEnemy_idle_north-east", "MeleeEnemy_idle_east",
                "MeleeEnemy_idle_south-east", "MeleeEnemy_idle_south",
                "MeleeEnemy_idle_south-west", "MeleeEnemy_idle_west",
                "MeleeEnemy_idle_north-west", "MeleeEnemy_idle_north"
            },
            new[]
            {
                "LanternWraith_idle_north-east", "LanternWraith_idle_east",
                "LanternWraith_idle_south-east", "LanternWraith_idle_south",
                "LanternWraith_idle_south-west", "LanternWraith_idle_west",
                "LanternWraith_idle_north-west", "LanternWraith_idle_north"
            }
        };

        private static readonly string[][] WalkStateNames =
        {
            new[]
            {
                "MeleeEnemy_walk_north-east", "MeleeEnemy_walk_east",
                "MeleeEnemy_walk_south-east", "MeleeEnemy_walk_south",
                "MeleeEnemy_walk_south-west", "MeleeEnemy_walk_west",
                "MeleeEnemy_walk_north-west", "MeleeEnemy_walk_north"
            },
            new[]
            {
                "LanternWraith_walk_north-east", "LanternWraith_walk_east",
                "LanternWraith_walk_south-east", "LanternWraith_walk_south",
                "LanternWraith_walk_south-west", "LanternWraith_walk_west",
                "LanternWraith_walk_north-west", "LanternWraith_walk_north"
            }
        };

        private static readonly int[][] IdleStateHashes = CreateStateHashes(IdleStateNames);
        private static readonly int[][] WalkStateHashes = CreateStateHashes(WalkStateNames);

        private static readonly Vector2[] ScreenDirectionVectors =
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

        [SerializeField] private EnemyAnimationKind animationKind;
        [SerializeField] private Animator animator;

        private EnemyTargetKnowledge targetKnowledge;
        private EnemyLanternWispCaster lanternWispCaster;
        private Transform visual;
        private Vector3 previousPosition;
        private string currentState;
        private string lastDirection = InitialDirection;
        private bool isWalking;
        private bool visualLookupComplete;

        public string CurrentState => currentState;
        public string LastDirection => lastDirection;

        private void Awake()
        {
            CacheComponents();
            previousPosition = transform.position;
            RestoreCameraFacingVisual();
        }

        private void OnEnable()
        {
            CacheComponents();
            previousPosition = transform.position;
            currentState = null;
        }

        private void LateUpdate()
        {
            // NavMeshAgent applies its root rotation before MonoBehaviour LateUpdate. Restore the
            // child here so the SpriteRenderer's final world pose remains camera-facing.
            Tick(Time.deltaTime);
        }

        /// Configures the generated controller family while keeping movement ownership on the
        /// existing NavMeshAgent/pursuit components (or on no component for the stationary wraith).
        public void Initialize(Animator enemyAnimator, EnemyAnimationKind kind)
        {
            animator = enemyAnimator != null ? enemyAnimator : GetComponent<Animator>();
            animationKind = kind;
            CacheComponents();
            previousPosition = transform.position;
            isWalking = false;
            lastDirection = InitialDirection;
            currentState = null;
            ApplyState(false);
            RestoreCameraFacingVisual();
        }

        /// Advances animation-state selection and restores the Visual's presentation rotation.
        /// Tests can move or rotate the Transform, then call this method with an explicit frame
        /// time to exercise speed and facing deterministically.
        public void Tick(float deltaTime)
        {
            Vector3 displacement = transform.position - previousPosition;
            previousPosition = transform.position;
            displacement.y = 0f;

            float speed = deltaTime > 0f ? displacement.magnitude / deltaTime : 0f;
            isWalking = isWalking ? speed > StopWalkingSpeed : speed >= StartWalkingSpeed;

            if (isWalking)
            {
                Vector3 planarVelocity = deltaTime > 0f ? displacement / deltaTime : Vector3.zero;
                lastDirection = StableDirectionFor(planarVelocity, lastDirection);
            }
            else
            {
                Transform facingTarget = ResolveFacingTarget();
                if (facingTarget != null)
                {
                    Vector3 toTarget = facingTarget.position - transform.position;
                    toTarget.y = 0f;
                    lastDirection = StableDirectionFor(toTarget, lastDirection);
                }
            }

            ApplyState(isWalking);
            RestoreCameraFacingVisual();
        }

        private void CacheComponents()
        {
            if (animator == null) animator = GetComponent<Animator>();
            targetKnowledge = GetComponent<EnemyTargetKnowledge>();
            lanternWispCaster = GetComponent<EnemyLanternWispCaster>();
            if (!visualLookupComplete)
            {
                visual = transform.Find("Visual");
                visualLookupComplete = true;
            }
        }

        private void RestoreCameraFacingVisual()
        {
            if (visual != null)
            {
                visual.rotation = Quaternion.Euler(IsometricCameraEulerAngles);
            }
        }

        private Transform ResolveFacingTarget()
        {
            if (animationKind == EnemyAnimationKind.MeleeEnemy)
            {
                return targetKnowledge != null && targetKnowledge.HasTarget
                    ? targetKnowledge.CurrentTarget
                    : null;
            }

            return lanternWispCaster != null ? lanternWispCaster.FacingTarget : null;
        }

        private void ApplyState(bool walking)
        {
            int kindIndex = (int)animationKind;
            int directionIndex = IndexOf(lastDirection);
            string[][] stateNames = walking ? WalkStateNames : IdleStateNames;
            int[][] stateHashes = walking ? WalkStateHashes : IdleStateHashes;
            string state = stateNames[kindIndex][directionIndex];
            if (state == currentState) return;

            currentState = state;
            if (animator != null && animator.runtimeAnimatorController != null)
            {
                animator.Play(stateHashes[kindIndex][directionIndex], 0, 0f);
            }
        }

        private static int[][] CreateStateHashes(string[][] stateNames)
        {
            var hashes = new int[stateNames.Length][];
            for (int kindIndex = 0; kindIndex < stateNames.Length; kindIndex++)
            {
                hashes[kindIndex] = new int[stateNames[kindIndex].Length];
                for (int directionIndex = 0;
                    directionIndex < stateNames[kindIndex].Length;
                    directionIndex++)
                {
                    hashes[kindIndex][directionIndex] =
                        Animator.StringToHash(stateNames[kindIndex][directionIndex]);
                }
            }

            return hashes;
        }

        // The fixed isometric camera maps screen right to world X+Z and screen up to Z-X.
        private static string DirectionFor(Vector3 movement)
        {
            Vector2 screenMovement = new Vector2(
                movement.x + movement.z, movement.z - movement.x);
            if (screenMovement.sqrMagnitude < DirectionThreshold * DirectionThreshold)
            {
                return InitialDirection;
            }

            int bestIndex = 0;
            float bestScore = Vector2.Dot(screenMovement, ScreenDirectionVectors[0]);
            for (int index = 1; index < ScreenDirections.Length; index++)
            {
                float score = Vector2.Dot(screenMovement, ScreenDirectionVectors[index]);
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

            return ScreenDirections[bestIndex];
        }

        private static bool IsWorldAxisDirection(int directionIndex)
        {
            return directionIndex % 2 == 0;
        }

        // Match WizardAnimationController's angular switch margin and deterministic ties.
        private static string StableDirectionFor(Vector3 movement, string previousDirection)
        {
            Vector2 screenMovement = new Vector2(
                movement.x + movement.z, movement.z - movement.x);
            float movementLength = screenMovement.magnitude;
            if (movementLength < DirectionThreshold * Mathf.Sqrt(2f))
            {
                return previousDirection;
            }

            string candidateDirection = DirectionFor(movement);
            if (string.IsNullOrEmpty(previousDirection))
            {
                return candidateDirection;
            }

            float candidateScore = Vector2.Dot(
                screenMovement, ScreenDirectionVectors[IndexOf(candidateDirection)]);
            float previousScore = Vector2.Dot(
                screenMovement, ScreenDirectionVectors[IndexOf(previousDirection)]);
            if (previousScore + DirectionSwitchMargin * movementLength >= candidateScore)
            {
                return previousDirection;
            }

            return candidateDirection;
        }

        private static int IndexOf(string direction)
        {
            for (int index = 0; index < ScreenDirections.Length; index++)
            {
                if (ScreenDirections[index] == direction)
                {
                    return index;
                }
            }

            return 0;
        }
    }
}
