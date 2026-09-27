namespace NoSafeCircle.DoorPrototype
{
    public partial class DoorInteractable
    {
        private bool isEntryCutsceneOpen;

        /// <summary>Raised when the inbound cutscene closes D1 back to its playable sealed state.</summary>
        public event System.Action EntryCutsceneClosed;

        /// <summary>
        /// Shows the real D1 leaf open while the presentation-only wizard enters Ruined Entry.
        /// This does not start the five-second player interaction or lock the door.
        /// </summary>
        public bool OpenForEntryCutscene()
        {
            if (doorId != World.DoorId.D1 || isEntryCutsceneOpen || IsOpen || IsLocked ||
                IsBroken || IsInteracting || HasCrossedForward) return false;

            isEntryCutsceneOpen = true;
            IsOpen = true;
            Progress = 1f;
            if (doorVisual != null) doorVisual.SetActive(false);
            if (doorwayBlocker != null) doorwayBlocker.enabled = false;
            PublishEnemyPassability();
            Opened?.Invoke();
            return true;
        }

        /// <summary>Closes the real leaf behind the cosmetic wizard before gameplay begins.</summary>
        public bool CloseAfterEntryCutscene()
        {
            if (!isEntryCutsceneOpen || !IsOpen || IsLocked || IsBroken) return false;

            isEntryCutsceneOpen = false;
            IsOpen = false;
            Progress = 0f;
            if (doorVisual != null) doorVisual.SetActive(true);
            if (doorwayBlocker != null) doorwayBlocker.enabled = true;
            PublishEnemyPassability();
            EntryCutsceneClosed?.Invoke();
            return true;
        }
    }
}
