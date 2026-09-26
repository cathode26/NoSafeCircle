using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World
{
    // Instantiates the Art Director's authored prop placements AT RUNTIME, from authored prefabs.
    //
    // WHY THIS EXISTS, in Vincent's words, 2026-09-26:
    //     "No we must stop this baking thing"
    //     "I write code to instantiate prefabs"
    //     "The scene should just be some objects that create prefabs"
    //     "Yes, this is our problem, you guys are doing unity in a non human way :) humans dont do
    //      what you are doing"
    // This is the SpaceInvaders shape he pointed at: his ObjectPooler does
    // `Instantiate(pool.prefab, transform)` in Awake and his AlienSpawner reads a LevelData asset
    // and instantiates. Nothing is generated at edit time and nothing is committed as build output.
    //
    // WHAT IT REPLACES. Five *DressingPrefabBuilder.cs ran in the editor, created 222 GameObjects
    // with `new GameObject` + `AddComponent<SpriteRenderer>`, and BAKED them into five committed
    // prefabs. Three consequences, all of which this removes: a hand edit to any prop died at the
    // next re-bake; a builder change was invisible until someone ran Unity; and the output was 222
    // inline copies in an unmergeable artifact, so two agents could not work on props at once.
    //
    // THE PREFABS ARE THE AUTHORED ARTIFACT. 45 of them, one per prop_id, hand-written as YAML and
    // verified by PropPrefabVerifier. Each carries its own SpriteRenderer, its own sorting fields
    // and its own collider. This component sets POSITION and ROTATION and nothing else - every
    // visual and physical property belongs to the prefab, where a human or an agent can edit it and
    // have the edit survive.
    [DisallowMultipleComponent]
    public sealed class PropSpawner : MonoBehaviour
    {
        // Resources rather than a serialized prefab registry, deliberately, and the reason is
        // concurrency rather than convenience: a registry is ONE shared file that every prop author
        // must edit, which would be the single merge hotspot in an otherwise perfectly partitioned
        // set of 45 independent files. With Resources, adding a prop is one prefab plus one meta and
        // touches nothing anyone else owns.
        private const string PropResourceFolder = "Props/";

        [Tooltip("The *DressingCatalog.json files, as TextAssets. Drag all five in. Read as "
            + "TextAsset rather than File.ReadAllText because File IO does not work on WebGL.")]
        [SerializeField] private TextAsset[] catalogs = new TextAsset[0];

        [Tooltip("Parent for the spawned props. Left empty, props are parented to this object.")]
        [SerializeField] private Transform dressingRoot;

        [Tooltip("Spawn on Awake. Turn this off when something else owns the order - a bootstrap "
            + "that must build rooms first, or a test that wants to call Spawn() itself.")]
        [SerializeField] private bool spawnOnAwake = true;

        /// How many props were instantiated by the last Spawn(). -1 until Spawn() has run, which is
        /// deliberately distinguishable from a Spawn() that found zero.
        public int SpawnedCount { get; private set; } = -1;

        private void Awake()
        {
            if (spawnOnAwake)
            {
                Spawn();
            }
        }

        /// Assigns the catalogs and the parent from code instead of the inspector, for a bootstrap
        /// that owns the build order and for tests. Does NOT spawn - call Spawn() when ready, which
        /// is the whole point: a caller that must build rooms and bake a navmesh around this needs
        /// to choose the moment.
        public void Configure(IEnumerable<TextAsset> catalogAssets, Transform root = null)
        {
            var list = new List<TextAsset>();
            if (catalogAssets != null)
            {
                list.AddRange(catalogAssets);
            }

            catalogs = list.ToArray();
            dressingRoot = root;
            spawnOnAwake = false;
        }

        /// Instantiates every placement in every assigned catalog. Safe to call again: it clears
        /// what it previously spawned first, so a re-spawn cannot silently double the dressing.
        public int Spawn()
        {
            Transform root = dressingRoot != null ? dressingRoot : transform;

            // Clear a previous spawn rather than adding to it. A second call producing 444 props
            // would look like a placement bug rather than a lifecycle bug, so make it impossible.
            for (int i = root.childCount - 1; i >= 0; i--)
            {
                Destroy(root.GetChild(i).gameObject);
            }

            var prefabCache = new Dictionary<string, GameObject>();
            int spawned = 0;
            int missingPrefabs = 0;

            foreach (TextAsset catalogAsset in catalogs)
            {
                if (catalogAsset == null)
                {
                    Debug.LogError($"{nameof(PropSpawner)}: an empty slot in the catalogs array. "
                        + "A room's dressing is silently missing until that is filled.");
                    continue;
                }

                // JsonUtility returns null on a leading BOM rather than saying why. Say why.
                var catalog = JsonUtility.FromJson<RoomDressingCatalog>(catalogAsset.text);
                if (catalog == null || catalog.props == null)
                {
                    Debug.LogError($"{nameof(PropSpawner)}: '{catalogAsset.name}' did not "
                        + "deserialize. JsonUtility returns null for a byte-order mark or a shape "
                        + "mismatch and reports neither; check both.");
                    continue;
                }

                Transform roomRoot = new GameObject(catalog.room + "Dressing").transform;
                roomRoot.SetParent(root, false);

                // PER CATALOG, NOT GLOBAL, and that distinction was measured rather than assumed.
                // instance_ids are ROOM-SCOPED by design: "NORTH-WALL-drape-01" means the first
                // drape on the north wall of THIS room, and each room's props live under their own
                // <Room>Dressing parent, so the names are unique where Unity resolves them.
                //
                // Measured across all five catalogs: 222 placements, 219 distinct ids, ZERO
                // within-catalog duplicates, and exactly 2 cross-catalog collisions -
                // NORTH-WALL-drape-01 (BoneArchive + FinalRoom) and NW-CORNER-web-01 (BoneArchive +
                // FinalRoom + RuinedEntry). A global check flagged those as defects and dropped
                // three real props. The editor builders each checked one catalog and were right;
                // this scope was briefly "improved" to global and it was a regression.
                var seenInstanceIds = new HashSet<string>();

                foreach (DressingPlacement placement in catalog.props)
                {
                    if (!seenInstanceIds.Add(placement.instance_id))
                    {
                        // Within ONE room this is a real defect: a later edit moves the wrong prop
                        // and nothing would show it.
                        Debug.LogError($"{nameof(PropSpawner)}: '{catalogAsset.name}' repeats "
                            + $"instance_id '{placement.instance_id}'. Instance ids identify a "
                            + "placement within a room and must be unique there.");
                        continue;
                    }

                    if (!prefabCache.TryGetValue(placement.prop_id, out GameObject prefab))
                    {
                        prefab = Resources.Load<GameObject>(PropResourceFolder + placement.prop_id);
                        prefabCache[placement.prop_id] = prefab;
                    }

                    if (prefab == null)
                    {
                        // Counted and reported once at the end as well, because 222 separate errors
                        // scroll the actual cause off the console.
                        missingPrefabs++;
                        Debug.LogError($"{nameof(PropSpawner)}: no prefab at Resources/"
                            + $"{PropResourceFolder}{placement.prop_id} for placement "
                            + $"'{placement.instance_id}'.");
                        continue;
                    }

                    GameObject instance = Instantiate(prefab, roomRoot);
                    instance.name = placement.instance_id;

                    // y IS ALWAYS ZERO, taken from here rather than from the placement, exactly as
                    // the editor builder did: a stray non-zero y in the json cannot lift a prop out
                    // through the wall. The catalog's own y field is read and discarded on purpose.
                    instance.transform.localPosition =
                        new Vector3(placement.position.x, 0f, placement.position.z);
                    instance.transform.localRotation =
                        Quaternion.Euler(0f, 0f, placement.rotation_euler_z);

                    // Never scaled. The guardian statue's four pixels of headroom are the reason.
                    instance.transform.localScale = Vector3.one;

                    // Nothing else is set. sortingLayerName, sortingOrder, spriteSortPoint, the
                    // sprite and the collider all live in the prefab. If a prop draws wrongly, the
                    // prefab is where it is wrong, and it is a text file anyone can open.

                    spawned++;
                }
            }

            SpawnedCount = spawned;

            if (missingPrefabs > 0)
            {
                Debug.LogError($"{nameof(PropSpawner)}: {missingPrefabs} placement(s) had no "
                    + $"prefab. Spawned {spawned}.");
            }
            else
            {
                Debug.Log($"{nameof(PropSpawner)}: spawned {spawned} prop(s) from "
                    + $"{catalogs.Length} catalog(s).");
            }

            return spawned;
        }
    }
}
