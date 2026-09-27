using System;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>The south entrance door; it has no D1–D5 progression identity.</summary>
    [DisallowMultipleComponent]
    public sealed class EntranceDoor : MonoBehaviour
    {
        private GameObject leaf;
        private SpriteRenderer doorSprite;
        private Sprite sealedSprite;
        private Sprite openSprite;
        private BoxCollider doorwayBlocker;
        private NavMeshObstacle obstacle;

        public bool IsOpen { get; private set; }
        public event Action EntryCutsceneClosed;

        public void Configure(GameObject visualLeaf, Sprite openDoorSprite)
        {
            leaf = visualLeaf;
            doorSprite = leaf.GetComponentInChildren<SpriteRenderer>();
            sealedSprite = doorSprite.sprite;
            openSprite = openDoorSprite;
            doorwayBlocker = leaf.GetComponent<BoxCollider>();
            obstacle = GetComponent<NavMeshObstacle>();
            IsOpen = false;
            ApplyState();
        }

        public bool OpenForEntryCutscene()
        {
            if (leaf == null || IsOpen) return false;
            IsOpen = true;
            ApplyState();
            return true;
        }

        /// <summary>Closes only after the wizard escaped north and the pursuer remains south.</summary>
        public bool CloseAfterEntryCutscene(Vector3 wizardPosition, Vector3 pursuerPosition)
        {
            if (!IsOpen || wizardPosition.z <= EntryApproachLayout.GateZ + 0.5f ||
                pursuerPosition.z >= EntryApproachLayout.GateZ - 0.5f)
                return false;

            IsOpen = false;
            ApplyState();
            EntryCutsceneClosed?.Invoke();
            return true;
        }

        /// <summary>Seals an interrupted entrance before gameplay input can resume.</summary>
        public void ResetDoor()
        {
            bool wasOpen = IsOpen;
            IsOpen = false;
            ApplyState();
            if (wasOpen) EntryCutsceneClosed?.Invoke();
        }

        private void ApplyState()
        {
            // The open SW sprite shows the stone doorway. Hide only its blocker so
            // the cutscene actors can pass through the visible arch.
            if (leaf != null) leaf.SetActive(true);
            if (doorSprite != null) doorSprite.sprite = IsOpen ? openSprite : sealedSprite;
            if (doorwayBlocker != null) doorwayBlocker.enabled = !IsOpen;
            if (obstacle != null) obstacle.enabled = !IsOpen;
        }
    }
}
