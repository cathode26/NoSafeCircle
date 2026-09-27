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
        private bool entryGateFailed;
        private bool isWaitingForGameplayReveal;
        private bool hasRevealedGameplayPresentation;
        private TitleScreenChaseBackdrop entryChase;
        private TitleScreenGameplayHudVisibility presentationVisibility;
        private EntryChamberStartDoor entryDoor;
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
        /// Gameplay input remains suspended until the chamber gate has closed and the chase has completed.
        /// </summary>
        public void EnterWorld(ConfirmedWizardSelection selection)
        {
            if (HasEnteredGameplay || isEntryCutsceneRunning || isWaitingForGameplayReveal) return;
            entryGateFailed = false;
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
                    "the Entry Chamber gate, and the gameplay camera follow.", this);
                RecoverWithoutCutscene();
                return;
            }

            cameraOffset = cameraFollow.transform.position - player.position;
            if (!entryDoor.OpenForEntryCutscene())
            {
                Debug.LogError("The Entry Chamber gate could not open for wizard entry.", this);
                RecoverWithoutCutscene();
                return;
            }

            entryChase.EntryWizardCrossedDoorway += OnEntryWizardCrossedDoorway;
            entryChase.EntryChaseCompleted += OnEntryChaseCompleted;
            if (!entryChase.BeginEntryChase(selection,
                    EntryChamberLayout.WizardEntryStart,
                    EntryChamberLayout.FirstRoomArrival,
                    EntryChamberLayout.DoorCloseTrigger.z,
                    EntryChamberLayout.PursuerStop.z))
            {
                Debug.LogError("The selected wizard chase could not start.", this);
                RecoverWithoutCutscene();
                return;
            }

            isEntryCutsceneRunning = true;
            if (GetComponentInParent<Canvas>() != null)
            {
                WizardEntryFadeTransition fade = GetComponent<WizardEntryFadeTransition>();
                if (fade == null) fade = gameObject.AddComponent<WizardEntryFadeTransition>();
                fade.Configure(entryChase, this);
            }
            Transform entryWizard = entryChase.EntryWizardTransform;
            cameraFollow.transform.position = entryWizard.position + cameraOffset;
            cameraFollow.Initialize(entryWizard);
        }

        private void OnEntryWizardCrossedDoorway()
        {
            if (!isEntryCutsceneRunning || entryDoor == null) return;
            Transform wizard = entryChase != null ? entryChase.EntryWizardTransform : null;
            Transform pursuer = entryChase != null ? entryChase.EntryPursuerTransform : null;
            if (wizard == null || pursuer == null ||
                !entryDoor.CloseAfterEntryCutscene(wizard.position, pursuer.position))
            {
                Debug.LogError("The Entry Chamber gate failed to close with the wizard north " +
                    "and the pursuer south; restoring playable state.", this);
                entryGateFailed = true;
                entryDoor.ResetDoor();
            }
        }

        private void OnEntryChaseCompleted()
        {
            if (!isEntryCutsceneRunning) return;
            isEntryCutsceneRunning = false;
            UnsubscribeFromEntryChase();
            if (entryGateFailed)
            {
                RecoverWithoutCutscene();
                return;
            }
            if (entryDoor == null || entryDoor.IsOpen)
            {
                Debug.LogError("The Entry Chamber gate was not sealed at wizard entry " +
                    "completion; restoring it before enabling control.", this);
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

        /// <summary>Shows the playable wizard behind the fade while input remains suspended.</summary>
        public void RevealGameplayPresentation()
        {
            if (!isWaitingForGameplayReveal || hasRevealedGameplayPresentation) return;
            hasRevealedGameplayPresentation = true;
            presentationVisibility.RestoreGameplayPresentation();
        }

        /// <summary>Called after the room has been revealed and the player may take control.</summary>
        public void CompleteEntryAfterCutscene()
        {
            if (!isWaitingForGameplayReveal || HasEnteredGameplay) return;
            RevealGameplayPresentation();
            isWaitingForGameplayReveal = false;
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

        private static EntryChamberStartDoor FindEntryDoor()
        {
            return UnityEngine.Object.FindFirstObjectByType<EntryChamberStartDoor>();
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
