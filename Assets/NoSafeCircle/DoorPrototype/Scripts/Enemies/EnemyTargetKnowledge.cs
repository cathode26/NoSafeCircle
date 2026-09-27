using System;
using NoSafeCircle.DoorPrototype;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    /// Pursuit/search phase owned by EnemyTargetKnowledge. Movement consumes this to
    /// decide navigation without EnemyTargetKnowledge ever choosing a destination itself.
    public enum EnemyTargetKnowledgeState
    {
        Idle,
        Pursuing,
        SearchingLastKnownPosition,
        Wandering
    }

    /// Owns one enemy's target identity, last-known-position, and bounded search/wander
    /// state per the GDD's Enemy Detection, Pursuit, and Target Loss rules. This component
    /// never sets a NavMeshAgent destination, chooses a wander point, or moves the enemy
    /// Transform; movement consumes its read-only state and calls its movement-facing
    /// transition/reset methods through a one-way dependency.
    public class EnemyTargetKnowledge : MonoBehaviour
    {
        [SerializeField] private Transform wizardTransform;
        [SerializeField] private float detectionDistance = 6f;
        [SerializeField] private float loseTargetDistance = 10f;
        [SerializeField] private float searchDuration = 5f;

        private float searchTimeRemaining;

        public float DetectionDistance => detectionDistance;
        public float LoseTargetDistance => loseTargetDistance;
        public float SearchDuration => searchDuration;

        public EnemyTargetKnowledgeState State { get; private set; } = EnemyTargetKnowledgeState.Idle;
        public Transform CurrentTarget { get; private set; }
        public bool HasTarget => CurrentTarget != null;
        public Vector3 LastKnownPosition { get; private set; }
        public float SearchTimeRemaining => searchTimeRemaining;

        /// <summary>Where this enemy's pursuit leash is currently tied. Set at spawn and then
        /// TOWED: once the enemy runs out of slack the anchor is dragged along behind it so the
        /// rope stays exactly <see cref="maximumPursuitDistanceFromStart"/> long. Exposed so a
        /// test can observe the rope directly instead of inferring it from the give-up branch,
        /// which no longer fires for an ordinary chase.</summary>
        public Vector3 PursuitAnchor => startPosition;

        private void Awake()
        {
            ValidateDistances(detectionDistance, loseTargetDistance);

            // startPosition/hasStartPosition are deliberately not serialized, so the leash must
            // anchor itself here rather than relying on IsBeyondPursuitLeash being reached. The
            // sight test is evaluated first in the acquisition chain, so a lazy anchor would
            // never initialize while sight is blocked - and would then measure distance from
            // world origin, which for an enemy at Z 53 exceeds any leash and silently prevents
            // it from ever acquiring the wizard.
            startPosition = transform.position;
            hasStartPosition = true;
        }

        private void OnValidate()
        {
            if (loseTargetDistance <= detectionDistance)
            {
                loseTargetDistance = detectionDistance + 0.01f;
            }
        }

        /// Wires the wizard Transform this enemy checks distance against. Movement or a
        /// test fixture supplies this independently of the inspector-assigned field.
        public void Initialize(Transform wizard)
        {
            wizardTransform = wizard;
        }

        /// Owner-controlled configuration entry point that enforces the GDD's strict
        /// Detection Distance &lt; Lose Target Distance relationship. Throws rather than
        /// silently accepting an authoring value that would cause acquire/lose flicker.
        public void ConfigureDistances(float newDetectionDistance, float newLoseTargetDistance)
        {
            ValidateDistances(newDetectionDistance, newLoseTargetDistance);

            detectionDistance = newDetectionDistance;
            loseTargetDistance = newLoseTargetDistance;
        }

        private static void ValidateDistances(float candidateDetectionDistance, float candidateLoseTargetDistance)
        {
            if (candidateDetectionDistance >= candidateLoseTargetDistance)
            {
                throw new ArgumentException(
                    "Detection Distance must be strictly smaller than Lose Target Distance.");
            }
        }

        /// Movement-facing per-tick evaluation. Movement calls this every frame it advances
        /// (or a test drives it directly) so target acquisition, distance-only target loss,
        /// and bounded search expiry stay solely a function of distance and elapsed time.
        /// The wander/search interval is time-bounded on its own: it keeps counting down and
        /// still expires even if the wired wizard Transform is destroyed or unbound mid-search.
        public void UpdateTargetKnowledge(float deltaTime)
        {
            if (wizardTransform != null)
            {
                var distanceToWizard = Vector3.Distance(transform.position, wizardTransform.position);

                // A NEW CONTACT BEGINS WHEN THE WIZARD RE-ENTERS DETECTION RANGE.
                if (distanceToWizard > detectionDistance)
                {
                    hasInvestigatedCurrentContact = false;
                }

                if (State != EnemyTargetKnowledgeState.Pursuing
                    && distanceToWizard <= detectionDistance
                    && HasUnobstructedViewOfWizard()
                    && !IsBeyondPursuitLeash())
                {
                    AcquireTarget();
                    return;
                }

                // SIGHT-BLOCKED CONTACT: INVESTIGATE RATHER THAN FREEZE. Vincent reported this
                // as the enemy not walking around the furniture: a wizard standing behind a
                // 2.73-tall shelf is inside detectionDistance, so the distance test passes, but
                // HasUnobstructedViewOfWizard gates acquisition and NOTHING else ran - the enemy
                // stayed Idle with no path and zero velocity for the whole window.
                //
                // GER's ruling, 2026-09-27, stated as outcomes because a criterion naming the
                // mechanism would be satisfied by the defect itself:
                //   1  the root moves and the straight-line gap to the wizard closes
                //   2  while obstructed it is NOT Pursuing - this is what keeps cover meaningful,
                //      and it is why making the shelf stop occluding is NOT the fix
                //   3  it terminates, without alternating between moving and stationary twice
                //
                // Reusing SearchingLastKnownPosition gives 1 and 3 from machinery that already
                // exists: EnemyPursuitMovement.HandleSearching paths to LastKnownPosition, reports
                // arrival, and the bounded Wandering timer ends in ClearTarget. CurrentTarget is
                // deliberately NOT set - an investigating enemy is suspicious, not locked on, so it
                // can still be evaded, and TryRedirectToSpectralDecoy still requires Pursuing.
                //
                // LastKnownPosition is snapped ONCE, not re-aimed each tick: the enemy investigates
                // where it detected something, which is what makes the outcome terminal. This is
                // NOT an approach to the last-glimpsed point - GER ruled that unsatisfiable here
                // precisely because the enemy never acquired, so there is no glimpse to approach.
                if (State == EnemyTargetKnowledgeState.Idle
                    && distanceToWizard <= detectionDistance
                    && !hasInvestigatedCurrentContact
                    && !HasUnobstructedViewOfWizard())
                {
                    hasInvestigatedCurrentContact = true;
                    LastKnownPosition = wizardTransform.position;
                    State = EnemyTargetKnowledgeState.SearchingLastKnownPosition;
                    searchTimeRemaining = 0f;
                    return;
                }

                // THE ANCHOR IS TOWED, NOT A WALL. Vincent, 2026-09-27: "the enemy post is fixed
                // where it spawned, but it needs to be allowed to drag its leash anchor."
                // IsBeyondPursuitLeash drags startPosition to stay exactly
                // maximumPursuitDistanceFromStart behind, so for an ordinary chase the rope is
                // never actually broken and pursuit CONTINUES. The call is made for its towing
                // effect, so it is assigned rather than buried in a condition.
                //
                // WHY TOWING ALONE WAS NOT THE FIX. Dragging the anchor while still abandoning the
                // chase produces the defect he reported: the enemy walks out to the slack limit,
                // gives up, walks back to the anchor it just towed, re-acquires, and repeats -
                // settling into a pace one leash-length long. "The enemy keeps pacing back and
                // forth" is that loop. The anchor has to move AND the give-up has to go.
                //
                // A DECOY REDIRECT STILL ENDS HERE, and it is not a leftover. NSC-111 is
                // conformant with a delivery record and its criterion (3) requires that moving a
                // REDIRECTED enemy beyond the leash clears the redirect record, keeps the wizard as
                // CurrentTarget and searches the start position; that is preserved exactly.
                // NSC-091 owns this file and mentions the leash zero times, so nothing constrains
                // the ordinary path. Both checked at source before this was written.
                if (State == EnemyTargetKnowledgeState.Pursuing)
                {
                    bool ranOutOfSlack = IsBeyondPursuitLeash();
                    if (ranOutOfSlack && isRedirectedToSpectralDecoy)
                    {
                        ClearSpectralDecoyRedirectState();
                        CurrentTarget = wizardTransform;
                        // ONE FIELD, TWO JOBS, AND THAT IS A DECISION RATHER THAN AN OVERSIGHT.
                        // IsBeyondPursuitLeash has ALREADY dragged startPosition by the time this
                        // line runs, so a redirected enemy searches the TOWED post rather than where
                        // it spawned. That is deliberate: Vincent's design is a home that FOLLOWS
                        // ("it needs to be allowed to drag its leash anchor"), so the towed post is
                        // the home, and a separate spawnPosition would reinstate a fixed post for
                        // this one path and contradict the design he settled.
                        //
                        // WHY IT IS COMMENTED RATHER THAN LEFT TO THE GATE: NSC-111 VAL-001 (3)
                        // reads whatever this field holds, so it PASSES under either meaning and
                        // cannot detect that what it proves has changed. AC-003 binds to "exactly as
                        // the current leash branch does" and never says "spawn", so the criterion
                        // follows the implementation instead of breaking - which is why this was
                        // cheap, and also why nothing would have told us. Found by the GER Agent.
                        // EnemyTargetKnowledgeLeashAnchorPlayModeTests pins the relation directly.
                        LastKnownPosition = startPosition;
                        State = EnemyTargetKnowledgeState.SearchingLastKnownPosition;
                        searchTimeRemaining = 0f;
                        return;
                    }
                }

                if (State == EnemyTargetKnowledgeState.Pursuing
                    && !isRedirectedToSpectralDecoy
                    && distanceToWizard > loseTargetDistance)
                {
                    LastKnownPosition = wizardTransform.position;
                    State = EnemyTargetKnowledgeState.SearchingLastKnownPosition;
                    searchTimeRemaining = 0f;
                    return;
                }
            }

            if (State == EnemyTargetKnowledgeState.Wandering)
            {
                searchTimeRemaining -= deltaTime;

                if (searchTimeRemaining <= 0f)
                {
                    ClearTarget();
                }
            }
        }

        /// Demo-scoped sight rule. Off by default so existing component tests keep the
        /// distance-only acquisition contract they assert; the scene builder turns it on for
        /// the enemies it authors so a closed door actually hides the wizard. Solid gameplay
        /// colliders (wall boxes, a door's enabled doorwayBlocker) block the view; triggers
        /// such as the door's own range volume are ignored.
        [SerializeField] private bool requiresLineOfSight;

        /// Demo-scoped leash. Zero means unlimited, which is the behavior every existing test
        /// asserts. When set, the enemy gives up once it has been dragged this far from where
        /// it started, so it can never follow the wizard onto a doorway and camp the threshold
        /// the wizard is about to walk through.
        [SerializeField, Min(0f)] private float maximumPursuitDistanceFromStart;

        private Vector3 startPosition;
        private bool hasStartPosition;

        // ONE INVESTIGATION PER CONTACT. Cleared when the wizard leaves detection range
        // and when the target is acquired, so a later blocked contact investigates again.
        // WITHOUT THIS THE FIX OSCILLATES: investigate, arrive, wander, go idle, notice the
        // same blocked wizard, investigate again - which is the pacing defect in a different
        // state's clothing. GER's outcome 3 forbids alternating more than once.
        private bool hasInvestigatedCurrentContact;

        public void SetRequiresLineOfSight(bool required)
        {
            requiresLineOfSight = required;
        }

        public void SetMaximumPursuitDistanceFromStart(float distance)
        {
            maximumPursuitDistanceFromStart = Mathf.Max(0f, distance);
            startPosition = transform.position;
            hasStartPosition = true;
        }

        private bool isRedirectedToSpectralDecoy;
        private Transform spectralDecoyTarget;
        private Vector3 wizardPositionAtSpectralDecoyRedirect;

        public bool IsRedirectedToSpectralDecoy => isRedirectedToSpectralDecoy;

        /// Spectral Decoy-facing switch: redirects this enemy from the wizard to the given
        /// decoy Transform per the GDD's Spectral Decoy exception. Only Wizard Combat's
        /// Spectral Decoy behavior calls this; it never writes CurrentTarget or State itself.
        public bool TryRedirectToSpectralDecoy(Transform decoy)
        {
            if (decoy == null
                || !isActiveAndEnabled
                || isRedirectedToSpectralDecoy
                || State != EnemyTargetKnowledgeState.Pursuing
                || wizardTransform == null
                || CurrentTarget != wizardTransform)
            {
                return false;
            }

            var enemyHealth = GetComponent<EnemyHealth>();
            if (enemyHealth != null && enemyHealth.IsDefeated)
            {
                return false;
            }

            wizardPositionAtSpectralDecoyRedirect = wizardTransform.position;
            isRedirectedToSpectralDecoy = true;
            spectralDecoyTarget = decoy;
            CurrentTarget = decoy;
            return true;
        }

        /// Spectral Decoy-facing end entry point: only acts when the given Transform is
        /// this enemy's exact current decoy target, then returns the enemy to the wizard or
        /// a last-known-position search exactly as normal target loss would.
        public void EndSpectralDecoyRedirect(Transform decoy)
        {
            if (!isRedirectedToSpectralDecoy || decoy == null || decoy != spectralDecoyTarget)
            {
                return;
            }

            var savedWizardPosition = wizardPositionAtSpectralDecoyRedirect;
            ClearSpectralDecoyRedirectState();

            if (wizardTransform != null
                && Vector3.Distance(transform.position, wizardTransform.position) <= loseTargetDistance)
            {
                CurrentTarget = wizardTransform;
                State = EnemyTargetKnowledgeState.Pursuing;
                return;
            }

            if (wizardTransform != null)
            {
                CurrentTarget = wizardTransform;
            }

            LastKnownPosition = savedWizardPosition;
            State = EnemyTargetKnowledgeState.SearchingLastKnownPosition;
            searchTimeRemaining = 0f;
        }

        private void ClearSpectralDecoyRedirectState()
        {
            isRedirectedToSpectralDecoy = false;
            spectralDecoyTarget = null;
            wizardPositionAtSpectralDecoyRedirect = Vector3.zero;
        }

        /// The anchor ("owner") is no longer fixed at spawn: it moves with the enemy, and once
        /// the enemy has run out of slack the enemy drags the anchor along behind it so the
        /// rope stays exactly taut, per spec:
        ///     anchor = position - normalize(position - anchor) * leash
        /// Within slack the anchor holds still (this returns false and startPosition is
        /// untouched); once beyond it, startPosition is dragged to be exactly
        /// maximumPursuitDistanceFromStart from the current position before this returns true.
        /// maximumPursuitDistanceFromStart is thereby a SLACK RADIUS rather than an absolute
        /// cap on distance from the original spawn point - absolute pursuit distance is
        /// unbounded. Horizontal-only, matching the pre-existing distance test (fromStart.y is
        /// zeroed only for that test; the anchor's own Y is left as its prior carried value).
        private bool IsBeyondPursuitLeash()
        {
            if (maximumPursuitDistanceFromStart <= 0f) return false;

            if (!hasStartPosition)
            {
                startPosition = transform.position;
                hasStartPosition = true;
            }

            var fromStart = transform.position - startPosition;
            fromStart.y = 0f;

            if (fromStart.magnitude > maximumPursuitDistanceFromStart)
            {
                var direction = fromStart.normalized;
                startPosition = new Vector3(
                    transform.position.x - direction.x * maximumPursuitDistanceFromStart,
                    startPosition.y,
                    transform.position.z - direction.z * maximumPursuitDistanceFromStart);
                return true;
            }

            return false;
        }

        private bool HasUnobstructedViewOfWizard()
        {
            if (!requiresLineOfSight || wizardTransform == null) return true;

            // Sample at chest height so the ground plane itself never counts as an occluder.
            var eye = transform.position + SightOcclusionLayers.EyeOffset;
            var target = wizardTransform.position + SightOcclusionLayers.EyeOffset;
            var toTarget = target - eye;
            var distance = toTarget.magnitude;
            if (distance <= 0.01f) return true;

            if (!Physics.Raycast(eye, toTarget / distance, out RaycastHit hit, distance,
                    SightOcclusionLayers.ExcludeLowDressing(Physics.DefaultRaycastLayers),
                    QueryTriggerInteraction.Ignore))
            {
                return true;
            }

            // The wizard's own CharacterController sits at the end of this ray, so hitting it
            // means the view is clear. Anything else in the way is a real occluder.
            return hit.transform == wizardTransform || hit.transform.IsChildOf(wizardTransform);
        }

        private void AcquireTarget()
        {
            CurrentTarget = wizardTransform;
            State = EnemyTargetKnowledgeState.Pursuing;
            searchTimeRemaining = 0f;
            hasInvestigatedCurrentContact = false;
        }

        /// Movement-facing transition entry point: movement calls this once its owned
        /// arrival check reports the enemy reached the recorded last known position, which
        /// starts the bounded wander/search interval.
        public void ReportArrivedAtLastKnownPosition()
        {
            if (State != EnemyTargetKnowledgeState.SearchingLastKnownPosition) return;

            State = EnemyTargetKnowledgeState.Wandering;
            searchTimeRemaining = searchDuration;
        }

        private void ClearTarget()
        {
            State = EnemyTargetKnowledgeState.Idle;
            CurrentTarget = null;
            LastKnownPosition = Vector3.zero;
            searchTimeRemaining = 0f;
        }

        /// Restores the floor-initial target-knowledge state (idle, no target, no
        /// last-known position, no search timer), for use by owner-controlled floor-restart
        /// orchestration. Never destroys, disables, or replaces the enemy GameObject.
        public void ResetTargetKnowledge()
        {
            ClearTarget();
            ClearSpectralDecoyRedirectState();
            hasInvestigatedCurrentContact = false;
        }
    }
}
