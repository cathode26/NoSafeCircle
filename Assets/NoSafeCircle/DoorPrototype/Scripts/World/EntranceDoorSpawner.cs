using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>Places the south entrance door after navigation, preserving D1–D5.</summary>
    [DisallowMultipleComponent]
    public sealed class EntranceDoorSpawner : MonoBehaviour, ISpawner
    {
        [SerializeField] private GameObject authoredDoorPrefab;

        public SpawnPhase Phase => SpawnPhase.Doors;
        public int SpawnedCount { get; private set; } = -1;

        public int Spawn()
        {
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                GameObject previous = transform.GetChild(i).gameObject;
                previous.SetActive(false);
                Destroy(previous);
            }

            Transform leafSource = authoredDoorPrefab != null
                ? authoredDoorPrefab.transform.Find("DoorVisual") : null;
            if (leafSource == null)
            {
                Debug.LogError("EntranceDoorSpawner: Door prefab is missing DoorVisual.");
                SpawnedCount = 0;
                return 0;
            }

            GameObject root = new GameObject("EntranceDoor");
            root.transform.SetParent(transform, false);
            root.transform.position = EntryApproachLayout.StartDoorCenter;

            // Reuse the same committed leaf, art, and collider as the five progression doors.
            GameObject leaf = Instantiate(leafSource.gameObject, root.transform);
            leaf.name = "DoorVisual";
            leaf.transform.localPosition = new Vector3(0f, 1.25f, 0f);
            leaf.transform.localRotation = Quaternion.identity;
            leaf.transform.localScale = Vector3.one;

            NavMeshObstacle obstacle = root.AddComponent<NavMeshObstacle>();
            obstacle.shape = NavMeshObstacleShape.Box;
            obstacle.center = new Vector3(0f, 1.25f, 0f);
            obstacle.size = new Vector3(EntryApproachLayout.OpeningWidth,
                EntryApproachLayout.WallHeight, EntryApproachLayout.WallThickness);
            obstacle.carving = true;

            root.AddComponent<EntranceDoor>().Configure(leaf);
            SpawnedCount = 1;
            return 1;
        }
    }
}
