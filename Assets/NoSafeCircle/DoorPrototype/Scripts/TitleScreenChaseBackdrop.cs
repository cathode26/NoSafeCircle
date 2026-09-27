using System;
using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// <summary>
    /// Presentation-only wizard and Brute entry chase. The scene builder supplies the art,
    /// camera, and floor references; this component never creates gameplay actors.
    /// </summary>
    public sealed class TitleScreenChaseBackdrop : MonoBehaviour
    {
        [Serializable]
        public struct WizardChoice
        {
            public WizardPresentation Presentation;
            public WizardSkin Skin;

            public WizardChoice(WizardPresentation presentation, WizardSkin skin)
            {
                Presentation = presentation;
                Skin = skin;
            }
        }

        private sealed class ChasePairing
        {
            public Vector3 Start;
            public Vector3 End;
            public float Duration;
            public float Elapsed;
            public EnemyAnimationKind EnemyKind;
            public GameObject Wizard;
            public SpriteRenderer WizardRenderer;
            public GameObject Pursuer;
            public SpriteRenderer PursuerRenderer;
            public EnemyAnimationController PursuerAnimation;
        }

        private sealed class EntryShot
        {
            public GameObject Visual;
            public SpriteRenderer Renderer;
            public Vector3 Start;
            public Vector3 End;
            public float FiredAt;
            public bool HitsPursuer;
        }

        private sealed class EntrySequence
        {
            public Vector3 Start;
            public Vector3 Destination;
            public Vector3 BruteStart;
            public Vector3 BruteStop;
            public float DoorCloseTriggerZ;
            public bool MovesNorth;
            public float Duration;
            public float TotalDuration;
            public float DoorCrossingTime;
            public float FinalTurnStartsAt;
            public float HitCastAt;
            public float HitImpactAt;
            public float ResumeAt;
            public float Elapsed;
            public int NextShot;
            public bool DoorwayNotified;
            public bool EndingNotified;
            public GameObject Wizard;
            public SpriteRenderer WizardRenderer;
            public WizardAnimationController WizardAnimation;
            public int WizardPose;
            public GameObject Brute;
            public SpriteRenderer BruteRenderer;
            public EnemyAnimationController BruteAnimation;
            public readonly List<EntryShot> Shots = new List<EntryShot>();
            public GameObject Impact;
            public float ImpactEndsAt;
        }

        private const float ViewportMinX = 0.55f;
        private const float ViewportMaxX = 0.9f;
        private const float ViewportSafeMin = 0.05f;
        private const float ViewportSafeMax = 0.95f;
        private const float TimeEpsilon = 0.00001f;
        private const float EntrySpeed = 3f;
        private const float BruteEntrySpeed = 3f;
        // One floor cell along the entry lane is 0.5 world units in Z.
        private const float EntryPursuerExtraTile = 0.5f;
        private const float LegacyDoorwayInsideZ = -1.5f;
        private const float LegacyBruteStopZ = 0.75f;
        private const float EntryShotFlightSeconds = 0.28f;
        private const float EntryImpactSeconds = 0.28f;
        private const float EntryTurnSeconds = 0.5f;
        private const float EntryStunSeconds = 0.5f;
        private const float EntryHitShotLeadSeconds = EntryTurnSeconds - EntryShotFlightSeconds;
        // The third shot starts an early turn, leaving the Brute room to visibly
        // stop on impact before it reaches its scripted end position.
        private static readonly float[] EntryShotProgress = { 0.18f, 0.45f, 0.60f };

        [Header("Title and art")]
        [SerializeField] private TitleScreenController titleScreen;
        [SerializeField] private Camera chaseCamera;
        [SerializeField] private RuntimeAnimatorController wizardAnimatorController;
        [SerializeField] private RuntimeAnimatorController meleeAnimatorController;
        [SerializeField] private RuntimeAnimatorController wraithAnimatorController;
        [SerializeField] private WizardChoice[] wizardChoices =
        {
            new WizardChoice(WizardPresentation.Masculine, WizardSkin.White),
            new WizardChoice(WizardPresentation.Masculine, WizardSkin.Black),
            new WizardChoice(WizardPresentation.Feminine, WizardSkin.White),
            new WizardChoice(WizardPresentation.Feminine, WizardSkin.Black)
        };

        [Header("World-space floor segment")]
        [SerializeField] private Vector3 floorSegmentStart;
        [SerializeField] private Vector3 floorSegmentEnd;

        [Header("Timing and motion")]
        [SerializeField] private int randomSeed = 107;
        [SerializeField] private float firstPairingMaxDelay = 3f;
        [SerializeField] private float minInterval = 10f;
        [SerializeField] private float maxInterval = 20f;
        [SerializeField] private float actorSpeed = 1.5f;
        [SerializeField] private float pursuerSeparation = 2.5f;
        [SerializeField] private float fadeDuration = 0.5f;
        [SerializeField] private float minLaneLength = 6f;
        [SerializeField] private float wizardVisualScale = 2f;
        [SerializeField] private float pursuerVisualScale = 2f;
        [SerializeField] private Sprite[] entryFireballFrames;
        [SerializeField] private Sprite entryFireballImpact;

        private readonly List<ChasePairing> pairings = new List<ChasePairing>();
        private System.Random random;
        private Func<float, float, float> intervalSelector;
        private Func<bool> startAtFirstEndpointSelector;
        private Transform actorContainer;
        private bool scheduleStarted;
        private bool stopped;
        private float nextPairingIn;
        private int nextPairingIndex;
        private int startedPairingCount;
        private EntrySequence entry;

        /// <summary>Disable the Unity clock when a test drives Tick directly.</summary>
        public bool AutomaticTick { get; set; } = true;
        public int NextPairingIndex => nextPairingIndex;
        public int StartedPairingCount => startedPairingCount;
        public int ActiveActorCount { get; private set; }
        public int ActiveFireballCount => entry != null ? entry.Shots.Count : 0;
        public int FiredEntryShotCount { get; private set; }
        public int EntryImpactCount { get; private set; }
        public bool IsEntryChaseRunning => entry != null;
        public bool IsEntryWizardTurningToShoot => entry != null &&
            entry.Elapsed >= entry.FinalTurnStartsAt && entry.Elapsed < entry.HitImpactAt;
        public bool IsEntryPursuerStunned => entry != null &&
            entry.Elapsed >= entry.HitImpactAt && entry.Elapsed < entry.ResumeAt;
        public Transform EntryWizardTransform => entry != null && entry.Wizard != null
            ? entry.Wizard.transform : null;
        public Transform EntryPursuerTransform => entry != null && entry.Brute != null
            ? entry.Brute.transform : null;

        // The older repeating-pairing seam remains useful for its deterministic regression
        // fixtures. Production leaves it false: the chosen wizard now runs once after selection.
        public bool TitlePreviewLoopEnabled { get; set; }
        public event Action EntryWizardCrossedDoorway;
        public event Action EntryChaseEnding;
        public event Action EntryChaseCompleted;

        private void OnEnable()
        {
            Subscribe();
        }

        private void OnDisable()
        {
            Unsubscribe();
            ClearActors();
        }

        private void OnDestroy()
        {
            Unsubscribe();
            ClearActors();
        }

        private void Update()
        {
            if (AutomaticTick) Tick(Time.deltaTime);
        }

        /// <summary>Assigns the same references that the scene builder serializes.</summary>
        public void Configure(
            TitleScreenController controller,
            Camera camera,
            RuntimeAnimatorController wizardController,
            RuntimeAnimatorController meleeController,
            RuntimeAnimatorController wraithController,
            ConfirmedWizardSelection[] orderedWizardChoices,
            Vector3 floorStart,
            Vector3 floorEnd)
        {
            if (controller == null) throw new ArgumentNullException(nameof(controller));
            if (camera == null) throw new ArgumentNullException(nameof(camera));
            if (wizardController == null) throw new ArgumentNullException(nameof(wizardController));
            if (meleeController == null) throw new ArgumentNullException(nameof(meleeController));
            if (wraithController == null) throw new ArgumentNullException(nameof(wraithController));
            if (orderedWizardChoices == null || orderedWizardChoices.Length != 4)
                throw new ArgumentException("The chase needs four ordered wizard choices.",
                    nameof(orderedWizardChoices));
            for (int index = 0; index < orderedWizardChoices.Length; index++)
            {
                if (!IsExpectedChoice(index, orderedWizardChoices[index].Presentation,
                        orderedWizardChoices[index].Skin))
                    throw new ArgumentException(
                        "Wizard choices must be Ember, Ash, Frost, Dusk order.",
                        nameof(orderedWizardChoices));
            }

            Unsubscribe();
            ClearActors();
            titleScreen = controller;
            chaseCamera = camera;
            wizardAnimatorController = wizardController;
            meleeAnimatorController = meleeController;
            wraithAnimatorController = wraithController;
            wizardChoices = new WizardChoice[4];
            for (int index = 0; index < wizardChoices.Length; index++)
            {
                wizardChoices[index] = new WizardChoice(
                    orderedWizardChoices[index].Presentation, orderedWizardChoices[index].Skin);
            }

            floorSegmentStart = floorStart;
            floorSegmentEnd = floorEnd;
            ResetSchedule();
            Subscribe();
        }

        /// <summary>Overrides serialized motion settings for an in-memory fixture.</summary>
        public void ConfigureMotion(
            float firstDelay, float intervalMinimum, float intervalMaximum,
            float speed, float separation, float fadeSeconds, float minimumLane)
        {
            if (!IsFinite(firstDelay) || firstDelay < 0f ||
                !IsFinite(intervalMinimum) || intervalMinimum <= TimeEpsilon ||
                !IsFinite(intervalMaximum) || intervalMaximum < intervalMinimum ||
                !IsFinite(speed) || speed <= 0f ||
                !IsFinite(separation) || separation < 0f ||
                !IsFinite(fadeSeconds) || fadeSeconds < 0f ||
                !IsFinite(minimumLane) || minimumLane < 0f)
                throw new ArgumentOutOfRangeException(nameof(intervalMinimum),
                    "Chase timing, speed, fade, and lane length must be finite and valid.");

            firstPairingMaxDelay = firstDelay;
            minInterval = intervalMinimum;
            maxInterval = intervalMaximum;
            actorSpeed = speed;
            pursuerSeparation = separation;
            fadeDuration = fadeSeconds;
            minLaneLength = minimumLane;
            ResetSchedule();
        }

        /// <summary>
        /// Injects deterministic choices. The interval selector receives inclusive bounds;
        /// true starts at the supplied floor segment's first clipped endpoint.
        /// </summary>
        public void SetSelectors(
            Func<float, float, float> selectInterval,
            Func<bool> selectStartAtFirstEndpoint)
        {
            intervalSelector = selectInterval;
            startAtFirstEndpointSelector = selectStartAtFirstEndpoint;
            ResetSchedule();
        }

        public void SetRandomSeed(int seed)
        {
            randomSeed = seed;
            ResetSchedule();
        }

        public void ConfigureFireballArt(Sprite[] projectileFrames, Sprite impact)
        {
            if (projectileFrames == null || projectileFrames.Length == 0)
                throw new ArgumentException("At least one fireball frame is required.",
                    nameof(projectileFrames));
            foreach (Sprite frame in projectileFrames)
            {
                if (frame == null)
                    throw new ArgumentException("Fireball frames cannot contain null.",
                        nameof(projectileFrames));
            }
            if (impact == null) throw new ArgumentNullException(nameof(impact));
            entryFireballFrames = (Sprite[])projectileFrames.Clone();
            entryFireballImpact = impact;
        }

        /// <summary>
        /// Starts one cosmetic entrance after the selected wizard has left the menus. The caller
        /// owns the real door, camera follow, and gameplay handoff; this component only animates
        /// the chosen wizard, a Brute behind them, two misses, and one cosmetic hit.
        /// </summary>
        public bool BeginEntryChase(ConfirmedWizardSelection selection,
            Vector3 entryStart, Vector3 gameplayDestination)
        {
            return BeginEntryChase(selection, entryStart, gameplayDestination,
                LegacyDoorwayInsideZ, LegacyBruteStopZ);
        }

        /// <summary>
        /// Starts the chase using the door-close and pursuer-stop Z positions. The
        /// trigger must lie between entry and arrival, and the pursuer stops behind that trigger.
        /// </summary>
        public bool BeginEntryChase(ConfirmedWizardSelection selection,
            Vector3 entryStart, Vector3 gameplayDestination,
            float doorCloseTriggerZ, float pursuerStopZ)
        {
            bool movesNorth = gameplayDestination.z > entryStart.z;
            float entryPursuerSeparation = pursuerSeparation + EntryPursuerExtraTile;
            if (entry != null || titleScreen == null ||
                !titleScreen.HasRequestedWizardSelection || !HasRuntimeInputs() ||
                entryFireballFrames == null || entryFireballFrames.Length == 0 ||
                entryFireballImpact == null ||
                !IsFinite(entryStart.x) || !IsFinite(entryStart.y) || !IsFinite(entryStart.z) ||
                !IsFinite(gameplayDestination.x) || !IsFinite(gameplayDestination.y) ||
                !IsFinite(gameplayDestination.z) ||
                !IsFinite(doorCloseTriggerZ) || !IsFinite(pursuerStopZ) ||
                entryStart.z == gameplayDestination.z ||
                !IsStrictlyBetween(doorCloseTriggerZ, entryStart.z, gameplayDestination.z) ||
                !IsStrictlyBetween(pursuerStopZ,
                    entryStart.z + (movesNorth ? -entryPursuerSeparation : entryPursuerSeparation),
                    doorCloseTriggerZ) ||
                Vector3.Distance(entryStart, gameplayDestination) < minLaneLength)
                return false;

            int choiceIndex = (int)selection.Presentation * 2 + (int)selection.Skin;
            if (choiceIndex < 0 || choiceIndex >= wizardChoices.Length ||
                !IsExpectedChoice(choiceIndex, selection.Presentation, selection.Skin))
                return false;

            ClearActors();
            stopped = false;
            FiredEntryShotCount = 0;
            EntryImpactCount = 0;
            Vector3 forward = (gameplayDestination - entryStart).normalized;
            Vector3 bruteStart = entryStart - forward * entryPursuerSeparation;
            var sequence = new EntrySequence
            {
                Start = entryStart,
                Destination = gameplayDestination,
                BruteStart = bruteStart,
                BruteStop = new Vector3(entryStart.x, entryStart.y, pursuerStopZ),
                DoorCloseTriggerZ = doorCloseTriggerZ,
                MovesNorth = movesNorth,
                Duration = Vector3.Distance(entryStart, gameplayDestination) / EntrySpeed
            };
            sequence.DoorCrossingTime = sequence.Duration *
                ((doorCloseTriggerZ - entryStart.z) /
                 (gameplayDestination.z - entryStart.z));
            sequence.FinalTurnStartsAt = sequence.DoorCrossingTime *
                EntryShotProgress[EntryShotProgress.Length - 1];
            sequence.HitCastAt = sequence.FinalTurnStartsAt + EntryHitShotLeadSeconds;
            sequence.HitImpactAt = sequence.FinalTurnStartsAt + EntryTurnSeconds;
            sequence.ResumeAt = sequence.HitImpactAt + EntryStunSeconds;
            sequence.TotalDuration = sequence.Duration + EntryTurnSeconds + EntryStunSeconds;
            sequence.Wizard = CreateActor("TitleEntryWizard_" + WizardName(choiceIndex),
                wizardAnimatorController, entryStart, out sequence.WizardRenderer);
            Transform wizardVisual = sequence.Wizard.transform.Find("Visual");
            wizardVisual.localRotation = Quaternion.identity;
            wizardVisual.localScale = new Vector3(wizardVisualScale, wizardVisualScale, 1f);
            sequence.WizardAnimation = sequence.Wizard.AddComponent<WizardAnimationController>();
            sequence.WizardAnimation.ApplyPresentation(selection.Presentation, selection.Skin);

            sequence.Brute = CreateActor("TitleEntryPursuer_DungeonBrute",
                meleeAnimatorController, bruteStart, out sequence.BruteRenderer);
            sequence.Brute.transform.Find("Visual").localScale =
                new Vector3(pursuerVisualScale, pursuerVisualScale, 1f);
            sequence.BruteAnimation = sequence.Brute.AddComponent<EnemyAnimationController>();
            sequence.BruteAnimation.Initialize(sequence.Brute.GetComponent<Animator>(),
                EnemyAnimationKind.MeleeEnemy);
            sequence.BruteAnimation.enabled = false;
            sequence.Brute.GetComponent<Animator>().Update(0f);
            entry = sequence;
            return true;
        }

        /// <summary>Aborts an interrupted menu or scene rebuild without a gameplay handoff.</summary>
        public void CancelEntryChase()
        {
            ClearActors();
            stopped = true;
        }

        /// <summary>Advances the schedule and all actor transforms by precisely deltaTime.</summary>
        public void Tick(float deltaTime)
        {
            if (!IsFinite(deltaTime) || deltaTime < 0f)
                throw new ArgumentOutOfRangeException(nameof(deltaTime));

            if (entry != null)
            {
                AdvanceEntry(deltaTime);
                return;
            }

            if (!TitlePreviewLoopEnabled) return;

            if (stopped || titleScreen == null) return;
            if (titleScreen.HasRequestedWizardSelection)
            {
                StopBackdrop();
                return;
            }

            if (!titleScreen.IsTitleScreenVisible)
            {
                ClearActors();
                scheduleStarted = false;
                return;
            }

            if (!HasRuntimeInputs()) return;

            if (!scheduleStarted)
            {
                scheduleStarted = true;
                nextPairingIn = SelectInterval(0f, firstPairingMaxDelay);
            }

            float remaining = deltaTime;
            while (true)
            {
                if (nextPairingIn <= 0f)
                {
                    AttemptPairing();
                    nextPairingIn = SelectInterval(minInterval, maxInterval);
                }

                if (remaining <= 0f) break;

                float step = Mathf.Min(remaining, nextPairingIn);
                AdvancePairings(step);
                remaining -= step;
                nextPairingIn -= step;
                if (remaining <= 0f)
                {
                    // A pairing exactly due at the end of this Tick still starts now.
                    if (nextPairingIn <= 0f)
                    {
                        AttemptPairing();
                        nextPairingIn = SelectInterval(minInterval, maxInterval);
                    }
                    break;
                }
            }
        }

        private bool HasRuntimeInputs()
        {
            return chaseCamera != null && wizardAnimatorController != null &&
                   meleeAnimatorController != null && wraithAnimatorController != null &&
                   HasOrderedWizardChoices() &&
                   actorSpeed > 0f && minInterval > TimeEpsilon &&
                   maxInterval >= minInterval &&
                   IsFinite(wizardVisualScale) && wizardVisualScale > 0f &&
                   IsFinite(pursuerVisualScale) && pursuerVisualScale > 0f;
        }

        private bool HasOrderedWizardChoices()
        {
            if (wizardChoices == null || wizardChoices.Length != 4) return false;
            for (int index = 0; index < wizardChoices.Length; index++)
            {
                if (!IsExpectedChoice(index, wizardChoices[index].Presentation,
                        wizardChoices[index].Skin)) return false;
            }

            return true;
        }

        private static bool IsExpectedChoice(
            int index, WizardPresentation presentation, WizardSkin skin)
        {
            return presentation == (index < 2
                       ? WizardPresentation.Masculine : WizardPresentation.Feminine) &&
                   skin == (index % 2 == 0 ? WizardSkin.White : WizardSkin.Black);
        }

        private void ResetSchedule()
        {
            scheduleStarted = false;
            nextPairingIn = 0f;
            nextPairingIndex = 0;
            startedPairingCount = 0;
            random = new System.Random(randomSeed);
            stopped = titleScreen != null && titleScreen.HasRequestedWizardSelection;
            ClearActors();
        }

        private float SelectInterval(float minimum, float maximum)
        {
            float selected = intervalSelector != null
                ? intervalSelector(minimum, maximum)
                : minimum + (maximum - minimum) * (float)(random ??
                    (random = new System.Random(randomSeed))).NextDouble();
            if (!IsFinite(selected)) return minimum;
            return Mathf.Clamp(selected, minimum, maximum);
        }

        private bool StartAtFirstEndpoint()
        {
            return startAtFirstEndpointSelector != null
                ? startAtFirstEndpointSelector()
                : (random ?? (random = new System.Random(randomSeed))).Next(2) == 0;
        }

        private void AttemptPairing()
        {
            int sequenceIndex = nextPairingIndex % 8;
            nextPairingIndex++;

            if (!TryClipLane(out Vector3 first, out Vector3 second) ||
                Vector3.Distance(first, second) < minLaneLength)
                return;

            bool startAtFirst = StartAtFirstEndpoint();
            Vector3 start = startAtFirst ? first : second;
            Vector3 end = startAtFirst ? second : first;
            EnemyAnimationKind kind = (sequenceIndex < 4
                    ? sequenceIndex % 2 == 0
                    : sequenceIndex % 2 != 0)
                ? EnemyAnimationKind.MeleeEnemy
                : EnemyAnimationKind.LanternWraith;

            var pairing = new ChasePairing
            {
                Start = start,
                End = end,
                Duration = Vector3.Distance(start, end) / actorSpeed,
                EnemyKind = kind
            };
            WizardChoice choice = wizardChoices[sequenceIndex % 4];
            pairing.Wizard = CreateActor(
                "TitleChaseWizard_" + WizardName(sequenceIndex % 4),
                wizardAnimatorController, start, out pairing.WizardRenderer);
            Transform wizardVisual = pairing.Wizard.transform.Find("Visual");
            wizardVisual.localRotation = Quaternion.identity;
            wizardVisual.localScale = new Vector3(
                wizardVisualScale, wizardVisualScale, 1f);
            pairing.Wizard.AddComponent<WizardAnimationController>()
                .ApplyPresentation(choice.Presentation, choice.Skin);
            SetAlpha(pairing.WizardRenderer, 0f);
            pairings.Add(pairing);
            startedPairingCount++;
        }

        private bool TryClipLane(out Vector3 first, out Vector3 second)
        {
            first = second = default(Vector3);
            Vector3 projectedStart = chaseCamera.WorldToViewportPoint(floorSegmentStart);
            Vector3 projectedEnd = chaseCamera.WorldToViewportPoint(floorSegmentEnd);
            if (projectedStart.z <= 0f || projectedEnd.z <= 0f) return false;

            float x0 = projectedStart.x;
            float x1 = projectedEnd.x;
            if (Mathf.Abs(x1 - x0) <= 0.000001f) return false;
            float lowest = Mathf.Min(x0, x1);
            float highest = Mathf.Max(x0, x1);
            if (highest < ViewportMinX || lowest > ViewportMaxX) return false;

            float lowerX = Mathf.Max(lowest, ViewportMinX);
            float upperX = Mathf.Min(highest, ViewportMaxX);
            // Keep floating-point projection error on the safe side of the band.
            if (lowerX == ViewportMinX) lowerX += 0.0001f;
            if (upperX == ViewportMaxX) upperX -= 0.0001f;
            if (upperX <= lowerX) return false;
            float lowerT = FindSegmentParameterAtViewportX(lowerX, x1 > x0);
            float upperT = FindSegmentParameterAtViewportX(upperX, x1 > x0);
            first = Vector3.Lerp(floorSegmentStart, floorSegmentEnd,
                Mathf.Min(lowerT, upperT));
            second = Vector3.Lerp(floorSegmentStart, floorSegmentEnd,
                Mathf.Max(lowerT, upperT));

            Vector3 midpoint = chaseCamera.WorldToViewportPoint((first + second) * 0.5f);
            return midpoint.y >= ViewportSafeMin && midpoint.y <= ViewportSafeMax;
        }

        private float FindSegmentParameterAtViewportX(float desiredX, bool increasing)
        {
            float low = 0f;
            float high = 1f;
            for (int iteration = 0; iteration < 28; iteration++)
            {
                float midpoint = (low + high) * 0.5f;
                float x = chaseCamera.WorldToViewportPoint(
                    Vector3.Lerp(floorSegmentStart, floorSegmentEnd, midpoint)).x;
                if ((x < desiredX) == increasing) low = midpoint;
                else high = midpoint;
            }

            return (low + high) * 0.5f;
        }

        private void AdvancePairings(float deltaTime)
        {
            float pursuerDelay = pursuerSeparation / actorSpeed;
            for (int index = pairings.Count - 1; index >= 0; index--)
            {
                ChasePairing pairing = pairings[index];
                float previousElapsed = pairing.Elapsed;
                pairing.Elapsed += deltaTime;

                float wizardTime = Mathf.Min(pairing.Elapsed, pairing.Duration);
                if (pairing.Wizard != null)
                {
                    pairing.Wizard.transform.position = Vector3.Lerp(
                        pairing.Start, pairing.End, wizardTime / pairing.Duration);
                    SetAlpha(pairing.WizardRenderer, AlphaAt(wizardTime, pairing.Duration));
                    if (pairing.Elapsed >= pairing.Duration)
                    {
                        RetireActor(pairing.Wizard);
                        pairing.Wizard = null;
                        pairing.WizardRenderer = null;
                    }
                }

                if (pairing.Elapsed >= pursuerDelay &&
                    pairing.Pursuer == null && previousElapsed < pursuerDelay)
                {
                    pairing.Pursuer = CreateActor(
                        pairing.EnemyKind == EnemyAnimationKind.MeleeEnemy
                            ? "TitleChasePursuer_DungeonBrute"
                            : "TitleChasePursuer_LanternWraith",
                        pairing.EnemyKind == EnemyAnimationKind.MeleeEnemy
                            ? meleeAnimatorController : wraithAnimatorController,
                        pairing.Start, out pairing.PursuerRenderer);
                    pairing.Pursuer.transform.Find("Visual").localScale =
                        new Vector3(pursuerVisualScale, pursuerVisualScale, 1f);
                    pairing.PursuerAnimation =
                        pairing.Pursuer.AddComponent<EnemyAnimationController>();
                    pairing.PursuerAnimation.Initialize(
                        pairing.Pursuer.GetComponent<Animator>(), pairing.EnemyKind);
                    // The backdrop drives this presentation controller from Tick. Leaving its
                    // own LateUpdate enabled would immediately turn a moved actor idle again.
                    pairing.PursuerAnimation.enabled = false;
                    pairing.Pursuer.GetComponent<Animator>().Update(0f);
                    SetAlpha(pairing.PursuerRenderer, 0f);
                }

                float pursuerTime = pairing.Elapsed - pursuerDelay;
                if (pairing.Pursuer != null)
                {
                    float clampedTime = Mathf.Min(pursuerTime, pairing.Duration);
                    pairing.Pursuer.transform.position = Vector3.Lerp(
                        pairing.Start, pairing.End, clampedTime / pairing.Duration);
                    pairing.PursuerAnimation.Tick(Mathf.Max(
                        0f, pairing.Elapsed - Mathf.Max(previousElapsed, pursuerDelay)));
                    SetAlpha(pairing.PursuerRenderer,
                        AlphaAt(clampedTime, pairing.Duration));
                    if (pursuerTime >= pairing.Duration)
                    {
                        RetireActor(pairing.Pursuer);
                        pairing.Pursuer = null;
                        pairing.PursuerRenderer = null;
                    }
                }

                if (pairing.Elapsed >= pairing.Duration + pursuerDelay)
                    pairings.RemoveAt(index);
            }
        }

        private void AdvanceEntry(float deltaTime)
        {
            EntrySequence sequence = entry;
            float previous = sequence.Elapsed;
            sequence.Elapsed = Mathf.Min(sequence.TotalDuration, previous + deltaTime);
            float elapsed = sequence.Elapsed;
            Vector3 forward = (sequence.Destination - sequence.Start).normalized;
            float wizardTravel = elapsed < sequence.FinalTurnStartsAt
                ? elapsed
                : elapsed < sequence.ResumeAt
                    ? sequence.FinalTurnStartsAt
                    : elapsed - EntryTurnSeconds - EntryStunSeconds;
            float bruteTravel = elapsed < sequence.HitImpactAt
                ? elapsed
                : elapsed < sequence.ResumeAt
                    ? sequence.HitImpactAt
                    : elapsed - EntryStunSeconds;

            sequence.Wizard.transform.position = Vector3.Lerp(
                sequence.Start, sequence.Destination, wizardTravel / sequence.Duration);
            sequence.Brute.transform.position = Vector3.MoveTowards(
                sequence.BruteStart, sequence.BruteStop, BruteEntrySpeed * bruteTravel);
            sequence.BruteAnimation.Tick(elapsed - previous);
            bool stunned = elapsed >= sequence.HitImpactAt && elapsed < sequence.ResumeAt;
            if (stunned && previous < sequence.HitImpactAt)
                sequence.BruteAnimation.Tick(0f);

            int desiredPose = elapsed < sequence.FinalTurnStartsAt ? 0
                : elapsed < sequence.HitImpactAt ? 1
                : elapsed < sequence.ResumeAt ? 2 : 3;
            if (sequence.WizardPose != desiredPose)
            {
                sequence.WizardPose = desiredPose;
                if (desiredPose == 1)
                    sequence.WizardAnimation.FaceForCutscene(-forward);
                else if (desiredPose == 2)
                    sequence.WizardAnimation.FaceForCutscene(forward);
                else if (desiredPose == 3)
                    sequence.WizardAnimation.ResumeForCutscene(forward);
            }

            while (sequence.NextShot < EntryShotProgress.Length &&
                   (sequence.NextShot == EntryShotProgress.Length - 1
                       ? sequence.HitCastAt
                       : sequence.DoorCrossingTime * EntryShotProgress[sequence.NextShot])
                   <= elapsed)
            {
                float firedAt = sequence.NextShot == EntryShotProgress.Length - 1
                    ? sequence.HitCastAt
                    : sequence.DoorCrossingTime * EntryShotProgress[sequence.NextShot];
                FireEntryShot(sequence, sequence.NextShot, firedAt);
                sequence.NextShot++;
            }

            for (int index = sequence.Shots.Count - 1; index >= 0; index--)
            {
                EntryShot shot = sequence.Shots[index];
                float flight = (elapsed - shot.FiredAt) / EntryShotFlightSeconds;
                if (shot.HitsPursuer ? elapsed >= sequence.HitImpactAt : flight >= 1f)
                {
                    if (shot.HitsPursuer)
                        ShowEntryImpact(sequence, shot.End, shot.FiredAt + EntryShotFlightSeconds);
                    RetireVisual(shot.Visual);
                    sequence.Shots.RemoveAt(index);
                    continue;
                }

                shot.Visual.transform.position = Vector3.Lerp(shot.Start, shot.End, flight);
                int frameIndex = Mathf.Min(entryFireballFrames.Length - 1,
                    Mathf.FloorToInt(flight * entryFireballFrames.Length));
                shot.Renderer.sprite = entryFireballFrames[frameIndex];
            }

            if (sequence.Impact != null && elapsed >= sequence.ImpactEndsAt)
            {
                RetireVisual(sequence.Impact);
                sequence.Impact = null;
            }

            float wizardZ = sequence.Wizard.transform.position.z;
            if (!sequence.DoorwayNotified &&
                (sequence.MovesNorth ? wizardZ >= sequence.DoorCloseTriggerZ
                    : wizardZ <= sequence.DoorCloseTriggerZ))
            {
                sequence.DoorwayNotified = true;
                EntryWizardCrossedDoorway?.Invoke();
            }

            if (!sequence.EndingNotified && elapsed >= sequence.TotalDuration - 0.3f)
            {
                sequence.EndingNotified = true;
                EntryChaseEnding?.Invoke();
            }

            if (elapsed >= sequence.TotalDuration)
            {
                ClearActors();
                EntryChaseCompleted?.Invoke();
            }
        }

        private void FireEntryShot(EntrySequence sequence, int shotIndex, float firedAt)
        {
            float arrival = firedAt + EntryShotFlightSeconds;
            bool hits = shotIndex == EntryShotProgress.Length - 1;
            float wizardTravelAtFire = hits ? sequence.FinalTurnStartsAt : firedAt;
            Vector3 wizardPosition = Vector3.Lerp(
                sequence.Start, sequence.Destination, wizardTravelAtFire / sequence.Duration);
            Vector3 brutePosition = Vector3.MoveTowards(
                sequence.BruteStart, sequence.BruteStop, BruteEntrySpeed * arrival);
            Vector3 origin = wizardPosition + Vector3.up * 1.15f;
            Vector3 target = brutePosition + Vector3.up * 1.15f;
            if (!hits)
                target.x += shotIndex == 0 ? -1.75f : 1.75f;

            GameObject visual = CreateEntrySpriteVisual(
                "TitleEntryFireball_" + shotIndex, entryFireballFrames[0], origin, 1f);
            sequence.Shots.Add(new EntryShot
            {
                Visual = visual,
                Renderer = visual.GetComponent<SpriteRenderer>(),
                Start = origin,
                End = target,
                FiredAt = firedAt,
                HitsPursuer = hits
            });
            FiredEntryShotCount++;
        }

        private void ShowEntryImpact(EntrySequence sequence, Vector3 position, float impactAt)
        {
            sequence.Impact = CreateEntrySpriteVisual(
                "TitleEntryFireballImpact", entryFireballImpact, position, 1.15f);
            sequence.ImpactEndsAt = impactAt + EntryImpactSeconds;
            EntryImpactCount++;
        }

        private GameObject CreateEntrySpriteVisual(string name, Sprite sprite,
            Vector3 position, float scale)
        {
            var visual = new GameObject(name);
            visual.transform.SetParent(actorContainer, false);
            visual.transform.position = position;
            visual.transform.rotation = chaseCamera.transform.rotation;
            visual.transform.localScale = Vector3.one * scale;
            var renderer = visual.AddComponent<SpriteRenderer>();
            renderer.sprite = sprite;
            renderer.sortingLayerName = WorldSpriteConvention.SortingLayerName;
            renderer.sortingOrder = WorldSpriteConvention.SortingOrder + 2;
            return visual;
        }

        private void RetireVisual(GameObject visual)
        {
            if (visual == null) return;
            visual.SetActive(false);
            Destroy(visual);
        }

        private GameObject CreateActor(
            string name, RuntimeAnimatorController controller, Vector3 position,
            out SpriteRenderer renderer)
        {
            if (actorContainer == null)
                actorContainer = new GameObject("TitleScreenChaseActors").transform;

            var actor = new GameObject(name);
            actor.transform.SetParent(actorContainer, false);
            actor.transform.position = position;
            var visual = new GameObject("Visual");
            visual.transform.SetParent(actor.transform, false);
            visual.transform.rotation = chaseCamera.transform.rotation;
            renderer = visual.AddComponent<SpriteRenderer>();
            renderer.sortingLayerName = WorldSpriteConvention.SortingLayerName;
            renderer.sortingOrder = WorldSpriteConvention.SortingOrder;
            renderer.spriteSortPoint = SpriteSortPoint.Pivot;
            var animator = actor.AddComponent<Animator>();
            animator.runtimeAnimatorController = controller;
            ActiveActorCount++;
            return actor;
        }

        private float AlphaAt(float elapsed, float duration)
        {
            if (fadeDuration <= 0f) return elapsed >= duration ? 0f : 1f;
            return Mathf.Clamp01(Mathf.Min(elapsed, duration - elapsed) / fadeDuration);
        }

        private static void SetAlpha(SpriteRenderer renderer, float alpha)
        {
            if (renderer == null) return;
            Color color = renderer.color;
            color.a = alpha;
            renderer.color = color;
        }

        private static string WizardName(int index)
        {
            switch (index)
            {
                case 0: return "Ember";
                case 1: return "Ash";
                case 2: return "Frost";
                default: return "Dusk";
            }
        }

        private static bool IsFinite(float value)
        {
            return !float.IsNaN(value) && !float.IsInfinity(value);
        }

        private static bool IsStrictlyBetween(float value, float first, float second)
        {
            return value > Mathf.Min(first, second) && value < Mathf.Max(first, second);
        }

        private void Subscribe()
        {
            if (titleScreen == null) return;
            titleScreen.WizardSelectionRequested -= StopBackdrop;
            titleScreen.WizardSelectionRequested += StopBackdrop;
        }

        private void Unsubscribe()
        {
            if (titleScreen != null)
                titleScreen.WizardSelectionRequested -= StopBackdrop;
        }

        private void StopBackdrop()
        {
            stopped = true;
            ClearActors();
        }

        private void ClearActors()
        {
            pairings.Clear();
            entry = null;
            ActiveActorCount = 0;
            if (actorContainer == null) return;
            actorContainer.gameObject.SetActive(false);
            Destroy(actorContainer.gameObject);
            actorContainer = null;
        }

        private void RetireActor(GameObject actor)
        {
            if (actor == null) return;
            actor.SetActive(false);
            Destroy(actor);
            ActiveActorCount--;
        }
    }
}
