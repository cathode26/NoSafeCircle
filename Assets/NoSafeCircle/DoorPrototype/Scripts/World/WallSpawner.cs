using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World
{
    // Instantiates the walls AT RUNTIME: authored wall prefabs, placed from the committed ASCII map
    // and the room layout constants, plus the per-run gameplay colliders the layouts pin.
    //
    // WHY THIS EXISTS. The same words that produced PropSpawner - Vincent, 2026-09-26: "No we must
    // stop this baking thing", "I write code to instantiate prefabs", "The scene should just be
    // some objects that create prefabs". Today every wall is a Tilemap painted by one of five
    // Editor/Rooms/*SceneBuilder.cs files into a committed room scene, reconciled by
    // RoomSceneComposer, decorated by ArchitecturalWallAccentPlacement, and re-baked by hand -
    // which is how NSC-126's accents merged, passed, and stayed invisible for a night. This
    // component replaces all of that at Play, and the scene file stops changing.
    //
    // WHAT DECIDES WHAT (Fable's addenda 2A/2B, as corrected 2026-09-26):
    //   the MAP     which cells are wall band, opening or outside      -> WallPiecePass
    //   the LAYOUTS every collider line, run extent and door centre    -> WallRoom
    //   the PREFABS every sprite, sorting field and the 0.151 inset    -> Content/Environment
    // This class sets POSITION and ROTATION and nothing else, exactly as PropSpawner does. The one
    // apparent exception - flipping the sign of the Visual child's authored inset per side - is
    // still the prefab's number; only its direction is the spawner's, because "toward the room"
    // is not a property a prefab can know.
    //
    // WALL PREFABS CARRY NO COLLIDER, DELIBERATELY. The visual door gap is 4 units (a '++' cell
    // pair) while the contract-pinned collider gap is 3, so half a unit of jamb art overhangs the
    // collider on each side; per-slot boxes cannot express that. The colliders are per run, from
    // the layouts, with the names NSC-048 AC-004 asserts (SouthWallWestCollision and friends).
    [DisallowMultipleComponent]
    public sealed class WallSpawner : MonoBehaviour, ISpawner
    {
        /// <summary>The child of every wall prefab that carries the SpriteRenderer. The root sits
        /// on the collider line; this child is inset toward the room.</summary>
        public const string VisualChildName = "Visual";

        // The builders pass roomBounds.center.y, which every ground bounds makes 0. Carried, so
        // the ported accent arithmetic below reads exactly as its source did.
        private const float FloorY = 0f;

        /// <summary>Walls are the Rooms phase: nothing else has anywhere to be until they exist.</summary>
        public SpawnPhase Phase => SpawnPhase.Rooms;

        [Tooltip("floor01.txt as a TextAsset. Its declared grid is derived from the rooms it must "
            + "cover, so the map and the layouts agree by construction or parsing fails loudly.")]
        [SerializeField] private TextAsset map;

        [SerializeField] private GameObject wallStraight;
        [SerializeField] private GameObject wallStub;
        [SerializeField] private GameObject wallPilaster;
        [SerializeField] private GameObject wallCorner;
        [SerializeField] private GameObject wallDoorJamb;
        [SerializeField] private GameObject wallEndCap;

        [Tooltip("Parent for the spawned walls. Left empty, walls are parented to this object.")]
        [SerializeField] private Transform wallsRoot;

        [Tooltip("Spawn on Awake. Ships OFF: GameBootstrap owns the build order, and a spawner "
            + "that starts itself runs before the other families exist.")]
        [SerializeField] private bool spawnOnAwake = false;

        /// <summary>Objects created by the last Spawn(), or -1 before it has run - deliberately
        /// distinguishable from a Spawn() that created nothing.</summary>
        public int SpawnedCount { get; private set; } = -1;

        private void Awake()
        {
            if (spawnOnAwake)
            {
                Spawn();
            }
        }

        /// <summary>Assigns everything from code instead of the inspector, for a fixture. Does
        /// NOT spawn - the caller chooses the moment, which is the whole point.</summary>
        public void Configure(TextAsset mapAsset, GameObject straight, GameObject stub, GameObject pilaster,
            GameObject corner, GameObject jamb, GameObject endCap, Transform root = null)
        {
            map = mapAsset;
            wallStraight = straight;
            wallStub = stub;
            wallPilaster = pilaster;
            wallCorner = corner;
            wallDoorJamb = jamb;
            wallEndCap = endCap;
            wallsRoot = root;
            spawnOnAwake = false;
        }

        /// <summary>Places every wall piece and every wall collider of every room, north to south,
        /// synchronously. Safe to call again: it clears what it previously spawned first.</summary>
        public int Spawn()
        {
            Transform root = wallsRoot != null ? wallsRoot : transform;
            for (int i = root.childCount - 1; i >= 0; i--)
            {
                Destroy(root.GetChild(i).gameObject);
            }

            // THE DECLARED GRID IS DERIVED, NOT RESTATED. AsciiRoomMap insists the caller declare
            // the grid; the rooms are what the map must cover, so their union IS the declaration:
            // origin at the west-most X and north-most Z, one column per two units across. For
            // floor01 that is 20x65 at (-20, 104), the figures Floor01AsciiMapTests asserts.
            WallRoom[] rooms = WallRoom.NorthToSouth;
            float originX = float.MaxValue, originZ = float.MinValue, maxX = float.MinValue, minZ = float.MaxValue;
            foreach (WallRoom room in rooms)
            {
                originX = Mathf.Min(originX, room.XMin);
                originZ = Mathf.Max(originZ, room.ZMax);
                maxX = Mathf.Max(maxX, room.XMax);
                minZ = Mathf.Min(minZ, room.ZMin);
            }

            const float cell = AsciiRoomMap.WorldUnitsPerCell;
            int columns = Mathf.RoundToInt((maxX - originX) / cell);
            int rowCount = Mathf.RoundToInt((originZ - minZ) / cell);
            if (!AsciiRoomMap.TryParse(map != null ? map.text : null, columns, rowCount, out AsciiRoomMap parsed, out string error))
            {
                Debug.LogError($"{nameof(WallSpawner)}: the map did not parse as {columns}x{rowCount}: {error}");
                SpawnedCount = 0;
                return 0;
            }

            var state = new WallPassState();
            int count = 0;
            foreach (WallRoom room in rooms)
            {
                Transform roomRoot = new GameObject(room.Name + "Walls").transform;
                roomRoot.SetParent(root, false);

                foreach (WallPiece piece in WallPiecePass.Pieces(parsed, originX, originZ, room, state))
                {
                    count += Place(piece, roomRoot);
                }

                foreach (WallColliderRun run in WallColliderRuns.ForRoom(room, state))
                {
                    GameObject box = new GameObject(run.Name);
                    box.transform.SetParent(roomRoot, false);
                    box.transform.position = run.Center;
                    box.AddComponent<BoxCollider>().size = run.Size;
                    count++;
                }
            }

            SpawnedCount = count;
            Debug.Log($"{nameof(WallSpawner)}: spawned {count} wall piece(s) and collider(s) across {rooms.Length} room(s).");
            return count;
        }

        private int Place(WallPiece piece, Transform parent)
        {
            GameObject prefab = PrefabFor(piece.Kind);
            if (prefab == null)
            {
                Debug.LogError($"{nameof(WallSpawner)}: no prefab assigned for {piece.Kind}, so a wall piece at {piece.Point} is missing.");
                return 0;
            }

            // North/south lines keep the sprite's authored orientation; west/east lines take the
            // same 90-degree yaw every wall Tilemap used, so the piece stands in its wall's plane.
            Quaternion rotation = piece.AlongX ? Quaternion.identity : Quaternion.Euler(0f, 90f, 0f);
            GameObject instance = Instantiate(prefab, parent);
            instance.name = $"{prefab.name} {piece.Point.x:0.##},{piece.Point.z:0.##}";

            bool overlay = piece.Kind == WallPieceKind.Corner || piece.Kind == WallPieceKind.Jamb
                || piece.Kind == WallPieceKind.EndCap;
            instance.transform.SetPositionAndRotation(overlay ? AccentPosition(instance, piece, rotation) : piece.Point, rotation);
            if (overlay)
            {
                return 1;
            }

            // The root is ON the line; the prefab's Visual child carries the 0.151 inset. In local
            // space that inset is along -z for the authored (north) side, so the sign is flipped
            // for the south side, and under the 90-degree yaw local +z is world +x, so west is
            // positive and east negative. The MAGNITUDE stays the prefab's.
            Transform visual = instance.transform.Find(VisualChildName);
            if (visual != null)
            {
                Vector3 local = visual.localPosition;
                float sign = piece.AlongX ? piece.Inward.z : piece.Inward.x;
                visual.localPosition = new Vector3(local.x, local.y, Mathf.Abs(local.z) * sign);
            }

            return 1;
        }

        // PORTED LITERALLY from ArchitecturalWallAccentPlacement.CreateAccent (Editor/Rooms, lines
        // 447-463 at 0a59043bc): the sprite's OUTER local-x edge is anchored at the run endpoint so
        // the art extends INTO the run, and the transform's y is whatever puts the sprite's bounds
        // bottom on the floor. Those offsets are the approved look on screen; they are not
        // re-tuned here. Note what that y means for a sprite whose pivot sits on its DRAWN base:
        // wall_corner's transform lands at y 0.25 and wall_door_jamb's at 0.406 - the committed
        // room scenes carry exactly those values - so a reader expecting root y 0 for overlays is
        // reading the spec's pivot sentence, not the placer. Change it here, in one place, if the
        // Art Director decides otherwise.
        private static Vector3 AccentPosition(GameObject instance, WallPiece piece, Quaternion rotation)
        {
            var renderer = instance.GetComponentInChildren<SpriteRenderer>(true);
            if (renderer == null || renderer.sprite == null)
            {
                Debug.LogError($"{nameof(WallSpawner)}: '{instance.name}' has no sprite to anchor, so it sits on its endpoint.");
                return piece.Point;
            }

            Bounds localBounds = renderer.sprite.bounds;
            Vector3 worldOffsetAtLocalMinX = rotation * new Vector3(localBounds.min.x, 0f, 0f);
            Vector3 worldOffsetAtLocalMaxX = rotation * new Vector3(localBounds.max.x, 0f, 0f);
            bool minEdgeIsInner =
                Vector3.Dot(worldOffsetAtLocalMinX, piece.Inward) > Vector3.Dot(worldOffsetAtLocalMaxX, piece.Inward);
            Vector3 anchoredWorldOffset = minEdgeIsInner ? worldOffsetAtLocalMaxX : worldOffsetAtLocalMinX;
            float anchorY = FloorY - localBounds.min.y;
            return new Vector3(piece.Point.x, anchorY, piece.Point.z) - anchoredWorldOffset;
        }

        // In WallPieceKind order, which the enum declares as the order of these six slots.
        private GameObject PrefabFor(WallPieceKind kind) =>
            new[] { wallStraight, wallStub, wallPilaster, wallCorner, wallDoorJamb, wallEndCap }[(int)kind];
    }
}
