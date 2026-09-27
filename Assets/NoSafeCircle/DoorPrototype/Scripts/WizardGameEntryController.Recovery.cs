using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    public sealed partial class WizardGameEntryController
    {
        /// <summary>
        /// A missing chase dependency or HUD rebuild must leave the chosen wizard playable.
        /// The door returns to its sealed starting state before input can resume.
        /// </summary>
        private void RecoverWithoutCutscene()
        {
            if (HasEnteredGameplay) return;
            GetComponent<WizardEntryFadeTransition>()?.Cancel();
            isEntryCutsceneRunning = false;
            isWaitingForGameplayReveal = false;
            entryGateFailed = false;
            UnsubscribeFromEntryChase();
            if (entryChase != null) entryChase.CancelEntryChase();

            if (entryDoor != null) entryDoor.ResetDoor();

            if (cameraFollow != null && player != null)
            {
                cameraFollow.transform.position = player.position + cameraOffset;
                cameraFollow.Initialize(player);
            }

            if (presentationVisibility != null)
                presentationVisibility.RestoreGameplayPresentation();
            else if (player != null)
            {
                SpriteRenderer renderer = player.Find("Visual")?.GetComponent<SpriteRenderer>();
                if (renderer != null) renderer.enabled = true;
            }

            HasEnteredGameplay = true;
            GameplayEntryCount++;
            if (playerMovement != null) playerMovement.EnableGameplayInput();
            if (playerInteractionController != null) playerInteractionController.EnableGameplayInput();
        }
    }
}
