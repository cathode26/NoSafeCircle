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
        [SerializeField] private Sprite openDoorSprite;

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
            Transform maskSource = authoredDoorPrefab != null
                ? authoredDoorPrefab.transform.Find("DoorwayMask") : null;
            SpriteMask doorwayMask = maskSource != null
                ? maskSource.GetComponent<SpriteMask>() : null;
            if (leafSource == null ||
                leafSource.GetComponentInChildren<SpriteRenderer>() == null ||
                leafSource.GetComponent<BoxCollider>() == null || openDoorSprite == null ||
                doorwayMask == null || doorwayMask.sprite == null ||
                !doorwayMask.enabled || !maskSource.gameObject.activeSelf)
            {
                Debug.LogError("EntranceDoorSpawner: DoorVisual, its sprite and blocker, the open SW sprite, and an active DoorwayMask are required.");
                SpawnedCount = 0;
                return 0;
            }

            GameObject root = new GameObject("EntranceDoor");
            root.transform.SetParent(transform, false);
            root.transform.SetPositionAndRotation(
                EntryApproachLayout.StartDoorCenter, Quaternion.identity);

            // Reuse the same committed leaf, art, and collider as the five progression doors.
            GameObject leaf = Instantiate(leafSource.gameObject, root.transform, false);
            leaf.name = "DoorVisual";

            // The sealed silhouette cuts the backing wall through every door state. Keep it
            // outside DoorVisual, in the authored plane, just as on the progression prefab.
            GameObject mask = Instantiate(maskSource.gameObject, root.transform, false);
            mask.name = "DoorwayMask";

            NavMeshObstacle obstacle = root.AddComponent<NavMeshObstacle>();
            obstacle.shape = NavMeshObstacleShape.Box;
            obstacle.center = new Vector3(0f, 1.25f, 0f);
            obstacle.size = new Vector3(EntryApproachLayout.OpeningWidth,
                EntryApproachLayout.WallHeight, EntryApproachLayout.WallThickness);
            obstacle.carving = true;

            root.AddComponent<EntranceDoor>().Configure(leaf, openDoorSprite);
            SpawnedCount = 1;
            return 1;
        }
    }
}
