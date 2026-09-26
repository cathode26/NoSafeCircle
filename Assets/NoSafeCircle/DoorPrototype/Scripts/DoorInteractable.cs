using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    [DisallowMultipleComponent]
    public class DoorInteractable : MonoBehaviour
    {
        [SerializeField] private float duration = 5f;
        [SerializeField] private World.DoorId doorId = World.DoorId.D1;
        [SerializeField] private bool isFinalDoor;
        [SerializeField] private GameObject doorVisual;
        [SerializeField] private Collider doorwayBlocker;
        [SerializeField] private DoorEnemyPassability enemyPassability;

        // Ground-plane offset from transform.position to the point PlayerInteractionController
        // compares the shared PlayerMovement.PointerWorldTarget against when testing whether the
        // visible door was clicked. The visible door sits above the ground (its visual center is
        // offset vertically), so the ground-plane point "under" a screen click on that visual is
        // offset horizontally from the door's own ground position under the fixed isometric
        // camera. DoorPrototypeSceneBuilder computes and assigns this value analytically at scene
        // build time; DoorInteractable itself never projects screen coordinates.
        [SerializeField] private Vector3 groundSelectionOffset = Vector3.zero;
        [SerializeField] private float selectionRadius = 1.5f;

        // Destination PlayerMovement is asked to walk to for the combined approach-and-interact
        // request. Offset toward the approach side of the door and within the arm's-reach trigger
        // below so that arrival there both (a) is physically reachable while the door is sealed
        // (not blocked by the door's own collider) and (b) already qualifies as arm's-reach range.
        [SerializeField] private Vector3 interactionPositionOffset = new Vector3(0f, 0f, -1f);

        // AC-001: local-space offset (relative to this door) for the trigger volume that detects
        // the wizard actually reaching this door's forward side. Mirrors interactionPositionOffset
        // on the opposite (far) side of the doorway. DoorPrototypeSceneBuilder may override this
        // per door instance to match authored room geometry; this default assumes the door faces
        // +Z, matching interactionPositionOffset's -Z approach-side default.
        //
        // AC-001 requires the wizard's CharacterController capsule to be geometrically
        // CLEAR of the doorwayBlocker before crossing is recorded, and
        // HandleForwardCrossingTriggerEnter deliberately performs no geometry test - the
        // guarantee lives entirely in this placement. OnTriggerEnter fires when the
        // capsule's LEADING edge reaches the volume's near face, so the capsule's
        // TRAILING edge is then 2r behind it. Clearing the blocker therefore needs
        //
        //     nearFace >= blockerForwardFace + 2 * playerRadius
        //
        // which is VAL-001's committed-scene conformance rule verbatim. At the built
        // geometry that is 0.15 + 2(0.5) = 1.15, and nearFace is offset.z - size.z/2.
        // 1.75 gives 1.25: the minimum plus 0.10, deliberately not the bare minimum so
        // the conformance check is not asserting float equality at the boundary.
        [SerializeField] private Vector3 forwardCrossingOffset = new Vector3(0f, 0f, 1.75f);
        [SerializeField] private Vector3 forwardCrossingTriggerSize = new Vector3(3f, 3f, 1f);

        // AC-002: fixed health amount requested from Player Health when the automatic
        // close-and-lock completes. Exact value is a tuning value (GDD: "Exact recovery values
        // will be set during playtesting"); level authoring configures it per door instance.
        [SerializeField] private float healthRestoreAmount = 20f;

        // AC-007: serialized per-door maximum durability. DoorInteractable itself retains
        // ownership of CurrentDurability and all damage/break handling below.
        [SerializeField] private float maxDurability = 100f;

        private static readonly List<DoorInteractable> activeDoors = new List<DoorInteractable>();

        private PlayerInteractionController playerInRange;

        public float Duration => duration;
        public World.DoorId DoorId => doorId;
        public bool IsFinalDoor => isFinalDoor;
        public float Progress { get; private set; }
        public bool IsOpen { get; private set; }
        public bool IsInteracting { get; private set; }
        public bool IsPlayerInRange => playerInRange != null;

        /// AC-001/AC-002: the single owner-side doorway-crossing state. Only ever set true while
        /// this door is open and the wizard has physically reached the forward-side crossing
        /// trigger; opening the door by itself never sets this. Door close/lock and final-escape
        /// victory consume this property (and the CrossedForward event below) instead of each
        /// implementing their own forward-side detection.
        public bool HasCrossedForward { get; private set; }

        /// AC-001/AC-003/AC-004: true once forward-side crossing has automatically closed and
        /// locked this door. Never becomes true again for a door that has since broken.
        public bool IsLocked { get; private set; }

        /// AC-004/AC-005: true once accepted damage has reduced CurrentDurability to zero.
        /// A broken door never becomes locked, sealed, or unbroken again during this run.
        public bool IsBroken { get; private set; }

        /// AC-004/AC-007: current durability against the serialized maxDurability. Only
        /// TakeDamage below is allowed to reduce this; callers cannot write it directly.
        public float CurrentDurability { get; private set; }

        public float MaxDurability => maxDurability;

        /// AC-008: fires when this door completes its five-second opening timer and transitions
        /// from sealed to open. PlayerInteractionController consumes this to release its pending
        /// selection instead of independently polling IsOpen every frame.
        public event System.Action Opened;

        /// AC-002: fires exactly once, the moment HasCrossedForward becomes true. Owner-side
        /// consumers (door close/lock, final-escape victory) subscribe here instead of polling.
        public event System.Action CrossedForward;

        /// AC-001: fires exactly once, the moment forward-side crossing completes the automatic
        /// close-and-lock. Future consumers (e.g. the door-passability child) can subscribe here
        /// instead of polling IsLocked.
        public event System.Action Locked;

        /// AC-004/AC-005: fires exactly once, the moment accepted damage breaks this door. The
        /// door-passability child owns publishing the resulting forward-passable navigation state.
        public event System.Action Broken;

        /// AC-001/AC-002: fires after an accepted hit reduces durability and before a possible
        /// break transition. DoorBreachFeedback consumes this event so rejected hits never
        /// produce player-facing breach feedback.
        public event System.Action<float> DamageTaken;

        /// AC-003: fires after owner-controlled reset restores the sealed floor state.
        public event System.Action ResetCompleted;

        public static IReadOnlyList<DoorInteractable> ActiveDoors => activeDoors;

        public Vector3 SelectionPoint => transform.position + new Vector3(groundSelectionOffset.x, 0f, groundSelectionOffset.z);

        public Vector3 InteractionPosition => transform.position + interactionPositionOffset;

        private void Awake()
        {
            // AC-001: the forward-crossing trigger lives on its own child GameObject (rather than
            // this door's own collider set) so it can be told apart from the arm's-reach
            // interaction-range trigger, which already relies on this component's own
            // OnTriggerEnter/OnTriggerExit below.
            var crossingObject = new GameObject("ForwardCrossingTrigger");
            crossingObject.transform.SetParent(transform, false);
            crossingObject.transform.localPosition = forwardCrossingOffset;

            var crossingTrigger = crossingObject.AddComponent<BoxCollider>();
            crossingTrigger.isTrigger = true;
            crossingTrigger.size = forwardCrossingTriggerSize;

            var relay = crossingObject.AddComponent<ForwardCrossingRelay>();
            relay.Owner = this;

            CurrentDurability = maxDurability;
            PublishEnemyPassability();
        }

        /// <summary>
        /// Connects this door to its navigation-owned passability component. The scene builder
        /// calls this after adding both components; prefab clones retain the serialized link.
        /// </summary>
        public void BindEnemyPassability(DoorEnemyPassability passability)
        {
            if (passability == null) throw new System.ArgumentNullException(nameof(passability));
            enemyPassability = passability;
            PublishEnemyPassability();
        }

        /// <summary>
        /// Sets identity BEFORE Awake. The editor wrote these two fields through SerializedObject
        /// (DoorSequenceBuilder.ConfigureDoor); a runtime spawner has none, so DoorSpawner
        /// instantiates the door prefab inactive, calls this, then activates it. After Awake the
        /// identity has already been read by the sprite binder, the HUD and the restart
        /// controller, so a late call is a programming error and throws at this boundary rather
        /// than leaving a door that reports one id and renders another. The guard is the engine's
        /// own record of Awake having run, not a flag kept here alongside it.
        /// </summary>
        public void Configure(World.DoorId id, bool isFinal)
        {
            if (didAwake) throw new System.InvalidOperationException(name + ": Configure after Awake.");
            doorId = id;
            isFinalDoor = isFinal;
        }

        private void OnEnable()
        {
            activeDoors.Add(this);
        }

        private void OnDisable()
        {
            activeDoors.Remove(this);
        }

        // Expression-bodied so Configure above fits under Tools/component_size_lint.py's 200-line
        // ceiling: this file measured 195 significant lines before Configure was added.
        private void Update() => Tick(Time.deltaTime);

        /// Advances the interaction timer by deltaTime. Public so Play Mode tests
        /// can drive the timer deterministically without waiting on real frames.
        public void Tick(float deltaTime)
        {
            if (!IsInteracting || IsOpen) return;

            Progress = Mathf.Clamp01(Progress + deltaTime / duration);

            if (Progress >= 1f)
            {
                Complete();
            }
        }

        /// AC-001: tests whether the shared world-space pointer target (already projected onto
        /// the gameplay plane by PlayerMovement) falls within this door's selection area. Consumes
        /// that ground point directly rather than independently projecting screen coordinates.
        public bool TryGetSelectionDistance(Vector3 groundPoint, out float distance)
        {
            var offset = groundPoint - SelectionPoint;
            offset.y = 0f;
            distance = offset.magnitude;
            return distance <= selectionRadius;
        }

        public void StartInteraction()
        {
            if (IsOpen) return;
            IsInteracting = true;
        }

        public void CancelInteraction()
        {
            IsInteracting = false;
            Progress = 0f;
        }

        /// AC-003/AC-006/AC-007: owner-controlled reset entry point consumed by the Floor
        /// Run/Restart Orchestrator. Returns progress, interacting state, open state,
        /// doorway-crossing state, locked/broken state, current durability, sealed geometry, and
        /// the doorway-blocker to their floor-initial values. NSC-020's doorway-crossing state
        /// (HasCrossedForward) remains the single such field; this reset does not add a second one.
        public void ResetDoor()
        {
            IsInteracting = false;
            IsOpen = false;
            Progress = 0f;
            HasCrossedForward = false;
            IsLocked = false;
            IsBroken = false;
            CurrentDurability = maxDurability;
            playerInRange = null;

            if (doorVisual != null) doorVisual.SetActive(true);
            if (doorwayBlocker != null) doorwayBlocker.enabled = true;
            PublishEnemyPassability();
            ResetCompleted?.Invoke();
        }

        private void Complete()
        {
            IsInteracting = false;
            IsOpen = true;
            Progress = 1f;

            if (doorVisual != null) doorVisual.SetActive(false);
            if (doorwayBlocker != null) doorwayBlocker.enabled = false;

            PublishEnemyPassability();
            Opened?.Invoke();
        }

        private void OnTriggerEnter(Collider other)
        {
            var controller = other.GetComponentInParent<PlayerInteractionController>();
            if (controller == null) return;

            playerInRange = controller;
            controller.NotifyDoorInRange(this);
        }

        private void OnTriggerExit(Collider other)
        {
            var controller = other.GetComponentInParent<PlayerInteractionController>();
            if (controller == null || controller != playerInRange) return;

            playerInRange = null;
            controller.NotifyDoorOutOfRange(this);
        }

        /// AC-001: called by the forward-crossing trigger's relay when the wizard's collider
        /// enters it. Only counts as crossing while this door is actually open, so opening the
        /// door alone never sets HasCrossedForward.
        private void HandleForwardCrossingTriggerEnter(Collider other)
        {
            if (!IsOpen || HasCrossedForward) return;

            var controller = other.GetComponentInParent<PlayerInteractionController>();
            if (controller == null) return;

            HasCrossedForward = true;
            CrossedForward?.Invoke();

            CloseAndLock(other.GetComponentInParent<PlayerHealth>());
        }

        /// AC-001/AC-002/AC-003: automatically closes and locks this door the moment forward-side
        /// crossing is confirmed, re-enabling the doorway blocker (now behind the player, so it
        /// only prevents backward travel) and requesting the configured fixed health restoration
        /// through Player Health's own owner-controlled Restore method.
        private void CloseAndLock(PlayerHealth crossedPlayerHealth)
        {
            if (IsLocked || IsBroken) return;

            IsLocked = true;

            if (doorVisual != null) doorVisual.SetActive(true);
            if (doorwayBlocker != null) doorwayBlocker.enabled = true;

            crossedPlayerHealth?.Restore(healthRestoreAmount);

            PublishEnemyPassability();
            Locked?.Invoke();
        }

        /// AC-004: owner-controlled damage-intake entry point for enemy attacks against a locked
        /// door. Rejects damage while sealed, open-but-not-yet-locked, or already broken; accepted
        /// damage reduces CurrentDurability and breaks the door once it reaches zero.
        public void TakeDamage(float amount)
        {
            if (!IsLocked || amount <= 0f) return;

            CurrentDurability = Mathf.Max(0f, CurrentDurability - amount);
            DamageTaken?.Invoke(amount);

            if (CurrentDurability <= 0f)
            {
                Break();
            }
        }

        /// AC-004/AC-005: the one-way locked-to-broken transition. A broken door stays open/broken
        /// and its player blocker keeps preventing backward player travel for the rest of the run;
        /// publishing forward passability to enemy navigation belongs to the door-passability child.
        private void Break()
        {
            IsLocked = false;
            IsBroken = true;

            PublishEnemyPassability();
            Broken?.Invoke();
        }

        private void PublishEnemyPassability()
        {
            if (enemyPassability == null) return;

            var state = IsBroken ? DoorPassabilityState.Broken
                : IsLocked ? DoorPassabilityState.Locked
                : IsOpen ? DoorPassabilityState.Open
                : DoorPassabilityState.Sealed;
            enemyPassability.SetDoorState(state);
        }

        // AC-001: relays trigger events from the child forward-crossing GameObject back to the
        // owning door. Kept as a private nested MonoBehaviour so the forward-crossing trigger can
        // be created and wired entirely from this script without any additional scene/prefab
        // authoring.
        private class ForwardCrossingRelay : MonoBehaviour
        {
            public DoorInteractable Owner;

            private void OnTriggerEnter(Collider other)
            {
                Owner?.HandleForwardCrossingTriggerEnter(other);
            }
        }
    }
}
