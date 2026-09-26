using UnityEngine;
using NoSafeCircle.DoorPrototype.World.Rooms;

namespace NoSafeCircle.DoorPrototype.World
{
    // Instantiates the five sealed doors AT RUNTIME from ONE authored door prefab, at phase Doors.
    //
    // WHAT IT REPLACES. DoorPrototypeSceneBuilder.BuildDoor assembled D1 in code - seven components,
    // a sprite child, three crack cubes, a world-space durability canvas - and DoorSequenceBuilder
    // cloned that object four times into the committed scene, naming the clones and writing each
    // one's identity through SerializedObject. The door is now authored ONCE, as Resources/Doors/
    // Door.prefab, where a human or an agent can open it and have the edit survive. This component
    // sets POSITION, NAME and IDENTITY and nothing else: every offset, size, sprite, colour and
    // material lives in the prefab (PropSpawner's rule, and for the same reason).
    //
    // WHERE THE FIVE CENTRES COME FROM. The runtime *Layout.cs constants of each door's EXIT room,
    // compiled in. NOT RoomSceneCatalog: that class is in the Editor assembly (`using UnityEditor`)
    // and does not exist at Play. Each shared door also has a copy in its ENTRY room's layout; the
    // spawner reads only the exit-room copy and DoorPrefabTests holds the two copies and the editor
    // catalog to agreement, so a drift between them fails a test rather than moving a door.
    //
    // WHY THE PREFAB IS SAVED INACTIVE, AND WHY THAT IS NOT OPTIONAL. Instantiating an ACTIVE prefab
    // runs every component's Awake and OnEnable before Instantiate returns, and DoorStateSpriteBinder
    // reads DoorInteractable.IsFinalDoor in OnEnable to pick the closed-leaf skin. Identity has to be
    // written BEFORE that, so the clone is created inactive, configured, then activated. An active
    // prefab would spawn five doors that all believe they are D1, and the guard in Spawn() refuses
    // it out loud rather than letting that happen quietly.
    //
    // WHY DOORS RUN AFTER NAVIGATION. The bake must see one continuous floor; each door's
    // NavMeshObstacle then CARVES the opening at runtime while the door is sealed or locked, which
    // is the design DoorEnemyPassability documents. A door standing in the opening at bake time
    // writes a PERMANENT hole (the legacy builder measured "no walkable surface at the doorway
    // centre, nearest 0.67 units away" and had to suppress the door colliders around its bake).
    // The phase order removes that hack; nothing here touches navigation.
    [DisallowMultipleComponent]
    public sealed class DoorSpawner : MonoBehaviour, ISpawner
    {
        /// <summary>One door to place: identity, ground centre, final flag and the object name
        /// every existing fixture and two contracts (NSC-052, NSC-075) look the door up by.</summary>
        public readonly struct DoorPlacement
        {
            public readonly DoorId Id;
            public readonly Vector3 Centre;
            public readonly bool IsFinal;
            public readonly string ObjectName;

            public DoorPlacement(DoorId id, Vector3 centre, bool isFinal, string objectName)
            {
                Id = id;
                Centre = centre;
                IsFinal = isFinal;
                ObjectName = objectName;
            }
        }

        /// <summary>Doors run after Navigation so the bake never sees a door, and before Player so
        /// the wizard spawns into a world whose doors already exist and are registered.</summary>
        public SpawnPhase Phase => SpawnPhase.Doors;

        [Tooltip("Resources/Doors/Door.prefab. Must be saved INACTIVE: the spawner configures each "
            + "clone's identity before activating it, and an active prefab would run Awake first.")]
        [SerializeField] private GameObject doorPrefab;

        [Tooltip("Parent for the spawned doors. Left empty, doors are parented to this object.")]
        [SerializeField] private Transform doorsRoot;

        /// How many doors were instantiated by the last Spawn(). -1 until Spawn() has run, which is
        /// deliberately distinguishable from a Spawn() that created zero.
        public int SpawnedCount { get; private set; } = -1;

        /// Assigns the prefab and the parent from code instead of the inspector, for tests. Does NOT
        /// spawn - the bootstrap owns the moment, and a test calls Spawn() when it is ready.
        public void Configure(GameObject prefab, Transform root = null)
        {
            doorPrefab = prefab;
            doorsRoot = root;
        }

        /// The five doors, from the runtime layouts (exit-room constants). D1 is named "DoorRoot"
        /// because NSC-052 and NSC-075 pin the path DoorRoot/DoorVisual/DoorSprite in requirement
        /// prose and six PlayMode fixtures look the five names up; the names are not negotiable here.
        public static DoorPlacement[] CanonicalDoors()
        {
            return new[]
            {
                new DoorPlacement(DoorId.D1,
                    new Vector3(RuinedEntryLayout.DoorCenterX, 0f, RuinedEntryLayout.DoorCenterZ),
                    false, "DoorRoot"),
                new DoorPlacement(DoorId.D2, BoneArchiveLayout.D2, false, "D2"),
                new DoorPlacement(DoorId.D3, ChapelOfAshLayout.D3, false, "D3"),
                new DoorPlacement(DoorId.D4, LowerVaultLayout.D4, false, "D4"),
                new DoorPlacement(DoorId.D5,
                    new Vector3(FinalRoomLayout.D5X, 0f, FinalRoomLayout.D5Z),
                    true, "D5")
            };
        }

        /// Instantiates the five doors. Safe to call again: it clears what it previously spawned
        /// first. A destroyed door leaves DoorInteractable.ActiveDoors in its own OnDisable, so the
        /// registry is correct again one frame later without this class touching it.
        public int Spawn()
        {
            Transform root = doorsRoot != null ? doorsRoot : transform;

            for (int i = root.childCount - 1; i >= 0; i--)
            {
                Destroy(root.GetChild(i).gameObject);
            }

            if (doorPrefab == null)
            {
                Debug.LogError($"{nameof(DoorSpawner)}: no door prefab assigned. Expected "
                    + "Resources/Doors/Door.prefab. No door will exist and every fixture that "
                    + "looks one up by name will fail.");
                SpawnedCount = 0;
                return 0;
            }

            if (doorPrefab.activeSelf)
            {
                // Fail loudly rather than spawn five doors that all believe they are D1: an active
                // prefab runs Awake and OnEnable inside Instantiate, before Configure can run.
                Debug.LogError($"{nameof(DoorSpawner)}: '{doorPrefab.name}' must be saved inactive; "
                    + "an active prefab runs Awake before Configure, so the sprite binder and the "
                    + "HUD would read D1's identity on every door.");
                SpawnedCount = 0;
                return 0;
            }

            int spawned = 0;
            foreach (DoorPlacement placement in CanonicalDoors())
            {
                // Inactive, so no Awake or OnEnable has run on it yet.
                GameObject instance = Instantiate(doorPrefab, root);
                instance.name = placement.ObjectName;

                // y IS ALWAYS ZERO, written here rather than read from the constant, exactly as the
                // prop spawner forces prop y: every door stands on the ground line. World space,
                // identity rotation: all five doors face +Z (approach from -Z, cross toward +Z),
                // and the prefab's own orientation is the only orientation. Scale is never set on
                // anything but the root - the 1.54 art scale lives on DoorSprite in the prefab.
                instance.transform.SetPositionAndRotation(
                    new Vector3(placement.Centre.x, 0f, placement.Centre.z), Quaternion.identity);
                instance.transform.localScale = Vector3.one;

                var door = instance.GetComponent<DoorInteractable>();
                if (door == null)
                {
                    Debug.LogError($"{nameof(DoorSpawner)}: '{doorPrefab.name}' carries no "
                        + $"{nameof(DoorInteractable)}, so {placement.ObjectName} cannot be given "
                        + "an identity. Destroyed rather than left as an anonymous door.");
                    Destroy(instance);
                    continue;
                }

                door.Configure(placement.Id, placement.IsFinal);

                // Now DoorInteractable.Awake creates ForwardCrossingTrigger and publishes Sealed,
                // DoorEnemyPassability.Awake configures the obstacle that carves the navmesh baked
                // one phase earlier, and DoorStateSpriteBinder.OnEnable syncs the sprite - final for
                // D5, sealed otherwise - because IsFinalDoor was set before activation.
                instance.SetActive(true);
                spawned++;
            }

            SpawnedCount = spawned;
            Debug.Log($"{nameof(DoorSpawner)}: spawned {spawned} door(s) from "
                + $"'{doorPrefab.name}'.");
            return spawned;
        }
    }
}
