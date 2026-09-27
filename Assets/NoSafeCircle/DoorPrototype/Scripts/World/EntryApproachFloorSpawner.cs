using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>Paints the open approach and grass beneath the dungeon rooms.</summary>
    [DisallowMultipleComponent]
    public sealed class EntryApproachFloorSpawner : MonoBehaviour, ISpawner
    {
        [SerializeField] private GameObject roomFloorPrefab;
        [SerializeField] private Tile grassBaseTile;
        [SerializeField] private Tile grassTile;
        [SerializeField] private Tile grassVariantATile;
        [SerializeField] private Tile grassVariantBTile;
        [SerializeField] private Tile grassFlowerTile;

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

            if (roomFloorPrefab == null || grassBaseTile == null || grassTile == null ||
                grassVariantATile == null || grassVariantBTile == null || grassFlowerTile == null)
            {
                Debug.LogError("EntryApproachFloorSpawner: missing floor prefab or grass tile.");
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
            // The grass is a visual underlay for every room, not a larger walkable floor.
            // Default sorts below the stone room Tilemaps on WorldSprites.
            Bounds visualBounds = RuinedEntryLayout.RoomBounds;
            visualBounds.Encapsulate(EntryApproachLayout.ApproachBounds);
            visualBounds.Encapsulate(BoneArchiveLayout.RoomBounds);
            visualBounds.Encapsulate(ChapelOfAshLayout.RoomBounds);
            visualBounds.Encapsulate(LowerVaultLayout.RoomBounds);
            visualBounds.Encapsulate(FinalRoomLayout.RoomBounds);
            visualBounds.Expand(new Vector3(24f, 0f, 24f));

            TilemapRenderer baseRenderer = tilemap.GetComponent<TilemapRenderer>();
            baseRenderer.sortingLayerName = "Default";
            baseRenderer.sortingOrder = short.MinValue;
            Tilemap grass = Instantiate(tilemap, tilemap.transform.parent);
            grass.name = "GrassTilemap";
            TilemapRenderer grassRenderer = grass.GetComponent<TilemapRenderer>();
            grassRenderer.sortingLayerName = "Default";
            grassRenderer.sortingOrder = short.MinValue + 1;
            FloorSpawner.PaintRoom(tilemap, visualBounds, grassBaseTile);
            FloorSpawner.PaintRoom(grass, visualBounds, grassTile);
            PaintGrassVariants(grass);

            collision.center = EntryApproachLayout.ApproachBounds.center +
                               Vector3.down * (FloorSpawner.FloorCollisionThickness * 0.5f);
            collision.size = new Vector3(EntryApproachLayout.ApproachBounds.size.x,
                FloorSpawner.FloorCollisionThickness, EntryApproachLayout.ApproachBounds.size.z);

            // The approach has no enclosing walls or room identity. Ruined Entry's
            // south wall and entry leaf are spawned by their existing owners.
            SpawnedCount = 1;
            return SpawnedCount;
        }

        private void PaintGrassVariants(Tilemap grass)
        {
            var positions = new List<Vector3Int>();
            var tiles = new List<TileBase>();
            foreach (Vector3Int cell in grass.cellBounds.allPositionsWithin)
            {
                if (!grass.HasTile(cell)) continue;
                uint pattern = unchecked((uint)(cell.x * 73856093 ^ cell.y * 19349663)) % 32u;
                Tile variant = pattern == 0u ? grassFlowerTile
                    : pattern < 7u ? grassVariantATile
                    : pattern < 13u ? grassVariantBTile
                    : null;
                if (variant == null) continue;
                positions.Add(cell);
                tiles.Add(variant);
            }

            grass.SetTiles(positions.ToArray(), tiles.ToArray());
        }
    }
}
