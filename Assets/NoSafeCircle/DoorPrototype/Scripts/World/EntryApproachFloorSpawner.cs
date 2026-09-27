using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>Paints the open cutscene approach outside Ruined Entry's south wall.</summary>
    [DisallowMultipleComponent]
    public sealed class EntryApproachFloorSpawner : MonoBehaviour, ISpawner
    {
        [SerializeField] private GameObject roomFloorPrefab;
        [SerializeField] private Tile ruinedEntryFloorTile;

        public SpawnPhase Phase => SpawnPhase.Rooms;
        public int SpawnedCount { get; private set; } = -1;

        public int Spawn()
        {
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                GameObject previous = transform.GetChild(i).gameObject;
                previous.SetActive(false);
                Destroy(previous);
            }

            if (roomFloorPrefab == null || ruinedEntryFloorTile == null)
            {
                Debug.LogError("EntryApproachFloorSpawner: missing floor prefab or floor tile.");
                SpawnedCount = 0;
                return 0;
            }

            GameObject floor = Instantiate(roomFloorPrefab, transform);
            floor.name = "EntryApproachFloor";
            floor.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            floor.transform.localScale = Vector3.one;
            Tilemap tilemap = floor.GetComponentInChildren<Tilemap>();
            Transform floorCollision = floor.transform.Find(FloorSpawner.FloorCollisionName);
            BoxCollider collision = floorCollision != null ? floorCollision.GetComponent<BoxCollider>() : null;
            if (tilemap == null || collision == null)
            {
                Debug.LogError("EntryApproachFloorSpawner: RoomFloor prefab is missing its tilemap or collision.");
                Destroy(floor);
                SpawnedCount = 0;
                return 0;
            }
            FloorSpawner.PaintRoom(tilemap, EntryApproachLayout.ApproachBounds, ruinedEntryFloorTile);
            collision.center = EntryApproachLayout.ApproachBounds.center +
                               Vector3.down * (FloorSpawner.FloorCollisionThickness * 0.5f);
            collision.size = new Vector3(EntryApproachLayout.ApproachBounds.size.x,
                FloorSpawner.FloorCollisionThickness, EntryApproachLayout.ApproachBounds.size.z);

            // The approach has no enclosing walls or room identity. Ruined Entry's
            // south wall and entry leaf are spawned by their existing owners.
            SpawnedCount = 1;
            return SpawnedCount;
        }
    }
}
