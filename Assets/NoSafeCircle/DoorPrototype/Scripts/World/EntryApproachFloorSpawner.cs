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
            // The actors use only the narrow physical approach. Extend its tile art beyond
            // the chase camera so the cutscene does not reveal a rectangular floor edge.
            // The BoxCollider below still uses the authored approach bounds.
            Bounds route = EntryApproachLayout.ApproachBounds;
            const float visualWidth = RuinedEntryLayout.MaximumX - RuinedEntryLayout.MinimumX;
            const float visualSouthPadding = 8f;
            float visualMinimumZ = route.min.z - visualSouthPadding;
            var visualBounds = new Bounds(
                new Vector3((RuinedEntryLayout.MinimumX + RuinedEntryLayout.MaximumX) * 0.5f,
                    0f, (visualMinimumZ + route.max.z) * 0.5f),
                new Vector3(visualWidth, 0f, route.max.z - visualMinimumZ));
            FloorSpawner.PaintRoom(tilemap, visualBounds, ruinedEntryFloorTile);
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
