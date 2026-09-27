using System;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>The cinematic start gate; it has no D1–D5 progression identity.</summary>
    [DisallowMultipleComponent]
    public sealed class EntryChamberStartDoor : MonoBehaviour
    {
        private GameObject leaf;
        private NavMeshObstacle obstacle;

        public bool IsOpen { get; private set; }
        public event Action EntryCutsceneClosed;

        public void Configure(GameObject visualLeaf)
        {
            leaf = visualLeaf;
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
            if (!IsOpen || wizardPosition.z <= EntryChamberLayout.GateZ + 0.5f ||
                pursuerPosition.z >= EntryChamberLayout.GateZ - 0.5f)
                return false;

            IsOpen = false;
            ApplyState();
            EntryCutsceneClosed?.Invoke();
            return true;
        }

        private void ApplyState()
        {
            if (leaf != null) leaf.SetActive(!IsOpen);
            if (obstacle != null) obstacle.enabled = !IsOpen;
        }
    }
}
