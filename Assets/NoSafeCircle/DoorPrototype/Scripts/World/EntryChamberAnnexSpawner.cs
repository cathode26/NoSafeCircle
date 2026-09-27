using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>Builds the annex floor and gate partition before navigation is baked.</summary>
    [DisallowMultipleComponent]
    public sealed class EntryChamberAnnexSpawner : MonoBehaviour, ISpawner
    {
        [SerializeField] private GameObject roomFloorPrefab;
        [SerializeField] private Tile ruinedEntryFloorTile;
        [SerializeField] private GameObject wallStraightPrefab;
        [SerializeField] private GameObject wallJambPrefab;

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

            if (roomFloorPrefab == null || ruinedEntryFloorTile == null ||
                wallStraightPrefab == null || wallJambPrefab == null)
            {
                Debug.LogError("EntryChamberAnnexSpawner: missing floor or wall prefab binding.");
                SpawnedCount = 0;
                return 0;
            }

            GameObject floor = Instantiate(roomFloorPrefab, transform);
            floor.name = "EntryChamberFloor";
            floor.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            floor.transform.localScale = Vector3.one;
            Tilemap tilemap = floor.GetComponentInChildren<Tilemap>();
            Transform floorCollision = floor.transform.Find(FloorSpawner.FloorCollisionName);
            BoxCollider collision = floorCollision != null ? floorCollision.GetComponent<BoxCollider>() : null;
            if (tilemap == null || collision == null)
            {
                Debug.LogError("EntryChamberAnnexSpawner: RoomFloor prefab is missing its tilemap or collision.");
                Destroy(floor);
                SpawnedCount = 0;
                return 0;
            }
            FloorSpawner.PaintRoom(tilemap, EntryChamberLayout.RoomBounds, ruinedEntryFloorTile);
            collision.center = EntryChamberLayout.RoomBounds.center +
                               Vector3.down * (FloorSpawner.FloorCollisionThickness * 0.5f);
            collision.size = new Vector3(EntryChamberLayout.RoomBounds.size.x,
                FloorSpawner.FloorCollisionThickness, EntryChamberLayout.RoomBounds.size.z);

            // The interior gate line is independent of D1 and has two 3.5-unit solid runs.
            // The gate leaf itself arrives in the Doors phase, after navmesh bake.
            GameObject partition = new GameObject("EntryChamberGateWall");
            partition.transform.SetParent(transform, false);
            float halfOpening = EntryChamberLayout.OpeningWidth * 0.5f;
            SpawnRun(partition.transform, "West", EntryChamberLayout.MinimumX,
                EntryChamberLayout.CenterX - halfOpening);
            SpawnRun(partition.transform, "East", EntryChamberLayout.CenterX + halfOpening,
                EntryChamberLayout.MaximumX);
            SpawnJamb(partition.transform, EntryChamberLayout.CenterX - halfOpening);
            SpawnJamb(partition.transform, EntryChamberLayout.CenterX + halfOpening);

            SpawnedCount = 2 + partition.transform.childCount; // floor, partition, and its pieces
            return SpawnedCount;
        }

        private void SpawnRun(Transform parent, string side, float minimumX, float maximumX)
        {
            GameObject colliderRoot = new GameObject(side + "GateWallCollision");
            colliderRoot.transform.SetParent(parent, false);
            colliderRoot.transform.position = new Vector3((minimumX + maximumX) * 0.5f,
                EntryChamberLayout.WallHeight * 0.5f, EntryChamberLayout.GateZ);
            colliderRoot.AddComponent<BoxCollider>().size =
                new Vector3(maximumX - minimumX, EntryChamberLayout.WallHeight,
                    EntryChamberLayout.WallThickness);

            // One-unit authored wall art. The jambs cover the half-unit endpoint overlap.
            int first = Mathf.FloorToInt(minimumX);
            int last = Mathf.CeilToInt(maximumX);
            for (int x = first; x < last; x++)
            {
                GameObject piece = Instantiate(wallStraightPrefab, parent);
                piece.name = side + "GateWall" + x;
                piece.transform.position = new Vector3(x + 0.5f, 0f, EntryChamberLayout.GateZ);
            }
        }

        private void SpawnJamb(Transform parent, float x)
        {
            GameObject jamb = Instantiate(wallJambPrefab, parent);
            jamb.name = "EntryGateJamb" + x;
            Vector3 intoRun = x < EntryChamberLayout.CenterX ? Vector3.left : Vector3.right;
            var piece = new WallPiece(WallPieceKind.Jamb,
                new Vector3(x, 0f, EntryChamberLayout.GateZ), intoRun, true);
            jamb.transform.position = WallSpawner.AccentPosition(jamb, piece, Quaternion.identity);
        }
    }
}
