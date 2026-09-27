using System;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// <summary>
    /// Consumes the confirmed wizard choice and hands control to the existing Player.
    /// </summary>
    public sealed partial class WizardGameEntryController : MonoBehaviour
    {
        [SerializeField] private WizardSelectionController wizardSelectionController;
        [SerializeField] private WizardAnimationController wizardAnimationController;
        [SerializeField] private Transform player;
        [SerializeField] private Transform worldSpawn;
        [SerializeField] private PlayerMovement playerMovement;
        [SerializeField] private PlayerInteractionController playerInteractionController;
        [SerializeField] private GameObject[] menuUiRoots;

        private bool isSubscribed;
        private bool isEntryCutsceneRunning;
        private bool isWaitingForGameplayReveal;
        private TitleScreenChaseBackdrop entryChase;
        private TitleScreenGameplayHudVisibility presentationVisibility;
        private DoorInteractable entryDoor;
        private IsometricCameraFollow cameraFollow;
        private Vector3 cameraOffset;

        public bool HasEnteredGameplay { get; private set; }
        public bool IsEntryCutsceneRunning => isEntryCutsceneRunning;
        public bool IsWaitingForGameplayReveal => isWaitingForGameplayReveal;
        public int GameplayEntryCount { get; private set; }
        public ConfirmedWizardSelection? AppliedSelection { get; private set; }

        /// <summary>Optional transition seam. A subscriber calls CompleteEntryAfterCutscene after its fade.</summary>
        public event Action EntryCutsceneReadyForGameplay;

        private void OnEnable()
        {
            SubscribeToSelection();
        }

        private void OnDisable()
        {
            UnsubscribeFromSelection();
            if (isEntryCutsceneRunning || isWaitingForGameplayReveal)
                RecoverWithoutCutscene();
            else UnsubscribeFromEntryChase();
        }

        private void SubscribeToSelection()
        {
            if (HasEnteredGameplay || isSubscribed || wizardSelectionController == null) return;

            wizardSelectionController.WizardSelectionConfirmed += EnterWorld;
            isSubscribed = true;
        }

        private void UnsubscribeFromSelection()
        {
            if (!isSubscribed) return;

            if (wizardSelectionController != null)
            {
                wizardSelectionController.WizardSelectionConfirmed -= EnterWorld;
            }

            isSubscribed = false;
        }

        /// <summary>
        /// Applies the confirmed appearance to the existing Player, then plays one inbound chase.
        /// Gameplay input remains suspended until D1 has closed and the chase has completed.
        /// </summary>
        public void EnterWorld(ConfirmedWizardSelection selection)
        {
            if (HasEnteredGameplay || isEntryCutsceneRunning || isWaitingForGameplayReveal) return;
            if (!HasValidReferences())
            {
                Debug.LogError(
                    "WizardGameEntryController requires one selection source, one existing Player with " +
                    "its wizard, movement, and interaction owners, one world spawn, and complete menu roots.",
                    this);
                return;
            }

            entryChase = GetComponent<TitleScreenChaseBackdrop>();
            presentationVisibility = GetComponent<TitleScreenGameplayHudVisibility>();
            entryDoor = FindEntryDoor();
            Camera camera = Camera.main;
            cameraFollow = camera != null ? camera.GetComponent<IsometricCameraFollow>() : null;

            wizardAnimationController.ApplyPresentation(selection.Presentation, selection.Skin);
            player.SetPositionAndRotation(worldSpawn.position, worldSpawn.rotation);
            playerMovement.SuspendGameplayInput();
            playerInteractionController.SuspendGameplayInput();

            foreach (GameObject menuUiRoot in menuUiRoots)
            {
                menuUiRoot.SetActive(false);
            }

            AppliedSelection = selection;
            UnsubscribeFromSelection();

            if (entryChase == null || presentationVisibility == null || entryDoor == null ||
                cameraFollow == null)
            {
                Debug.LogError("Wizard entry needs the title chase, presentation visibility, " +
                    "the real D1 door, and the gameplay camera follow.", this);
                RecoverWithoutCutscene();
                return;
            }

            cameraOffset = cameraFollow.transform.position - player.position;
            if (!entryDoor.OpenForEntryCutscene())
            {
                Debug.LogError("The real D1 door could not open for wizard entry.", this);
                RecoverWithoutCutscene();
                return;
            }

            entryChase.EntryWizardCrossedDoorway += OnEntryWizardCrossedDoorway;
            entryChase.EntryChaseCompleted += OnEntryChaseCompleted;
            Vector3 entryStart = new Vector3(RuinedEntryLayout.DoorCenterX, 0f,
                RuinedEntryLayout.DoorCenterZ + 2.5f);
            if (!entryChase.BeginEntryChase(selection, entryStart, worldSpawn.position))
            {
                Debug.LogError("The selected wizard chase could not start.", this);
                RecoverWithoutCutscene();
                return;
            }

            isEntryCutsceneRunning = true;
            Transform entryWizard = entryChase.EntryWizardTransform;
            cameraFollow.transform.position = entryWizard.position + cameraOffset;
            cameraFollow.Initialize(entryWizard);
        }

        private void OnEntryWizardCrossedDoorway()
        {
            if (!isEntryCutsceneRunning || entryDoor == null) return;
            if (!entryDoor.CloseAfterEntryCutscene())
                Debug.LogError("D1 failed to close behind the entering wizard.", this);
        }

        private void OnEntryChaseCompleted()
        {
            if (!isEntryCutsceneRunning) return;
            isEntryCutsceneRunning = false;
            UnsubscribeFromEntryChase();
            if (entryDoor != null && entryDoor.IsOpen)
                entryDoor.CloseAfterEntryCutscene();
            if (entryDoor == null || entryDoor.IsOpen || entryDoor.IsLocked)
            {
                Debug.LogError("D1 was not sealed at wizard entry completion; restoring its " +
                    "floor-initial state before enabling control.", this);
                RecoverWithoutCutscene();
                return;
            }

            cameraFollow.transform.position = player.position + cameraOffset;
            cameraFollow.Initialize(player);
            isWaitingForGameplayReveal = true;
            Action transition = EntryCutsceneReadyForGameplay;
            if (transition == null) CompleteEntryAfterCutscene();
            else transition.Invoke();
        }

        /// <summary>Called after an optional transition reveals the real player in the room.</summary>
        public void CompleteEntryAfterCutscene()
        {
            if (!isWaitingForGameplayReveal || HasEnteredGameplay) return;
            isWaitingForGameplayReveal = false;
            presentationVisibility.RestoreGameplayPresentation();
            HasEnteredGameplay = true;
            GameplayEntryCount++;
            playerMovement.EnableGameplayInput();
            playerInteractionController.EnableGameplayInput();
        }

        private void UnsubscribeFromEntryChase()
        {
            if (entryChase == null) return;
            entryChase.EntryWizardCrossedDoorway -= OnEntryWizardCrossedDoorway;
            entryChase.EntryChaseCompleted -= OnEntryChaseCompleted;
        }

        private static DoorInteractable FindEntryDoor()
        {
            foreach (DoorInteractable door in DoorInteractable.ActiveDoors)
                if (door != null && door.DoorId == DoorId.D1) return door;
            return null;
        }

        private bool HasValidReferences()
        {
            if (wizardSelectionController == null || wizardAnimationController == null ||
                player == null || worldSpawn == null || playerMovement == null ||
                playerInteractionController == null || menuUiRoots == null || menuUiRoots.Length == 0)
            {
                return false;
            }

            if (wizardAnimationController.transform != player || playerMovement.transform != player ||
                playerInteractionController.transform != player)
            {
                return false;
            }

            foreach (GameObject menuUiRoot in menuUiRoots)
            {
                if (menuUiRoot == null) return false;
            }

            return true;
        }
    }
}
