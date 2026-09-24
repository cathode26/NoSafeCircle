using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Editor.Environment
{
    /// <summary>Builds the Chapel Of Ash dressing prefab from its authored catalog.</summary>
    /// <remarks>
    /// NSC-081. The catalog is ART, authored by the Art Director: 76 placements, every one of the
    /// room's props used. THIS BUILDER DECIDES NOTHING ABOUT THE ART. It reads the committed
    /// catalog and reproduces it exactly, so a re-run cannot drift from what was approved and a
    /// change of mind is a change to the JSON rather than to code.
    /// <para>
    /// THE CATALOG'S OWN builder_contract, honoured literally:
    /// <list type="bullet">
    /// <item>y IS ALWAYS ZERO. Its note explains why this is not a nicety: Ruined Entry's standing guardian is
    /// 2.44 units drawn against a 2.5-unit wall, which is 0.06 units of headroom -- about four
    /// pixels at 64 PPU -- so any lift puts it outside the room. It must not be scaled either.</item>
    /// <item>sorting_order = round((x - z) * 10); larger x-z is nearer the camera.</item>
    /// <item>THE DRESSING PREFAB CARRIES NO COLLIDERS. Dressing is scenery; it must never change
    /// where the wizard can walk.</item>
    /// <item>Pivot and PPU come from the committed import settings. THE BUILDER NEVER RECOMPUTES A
    /// PIVOT -- the sprite is used exactly as PropCatalog.json says it was published.</item>
    /// </list>
    /// </para>
    /// <para>
    /// SPRITE RESOLUTION IS DERIVED, NOT HARD-CODED. PropCatalog.json's source_path names the RAW
    /// original under Docs/, which Unity cannot load because it is outside Assets/. The published,
    /// importable copy lives under Props/Source/selected/&lt;category&gt;/&lt;id&gt;.png, and the
    /// category is taken from the raw path's own folder. That keeps one source of truth: adding a
    /// prop to PropCatalog is enough, and a prop published to a different category does not need
    /// this file edited.
    /// </para>
    /// </remarks>
    public static class ChapelOfAshDressingPrefabBuilder
    {
        private const string RoomName = "ChapelOfAsh";
        private const string DressingDirectory =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/RoomDressing/";
        private const string CatalogPath = DressingDirectory + RoomName + "DressingCatalog.json";
        private const string PrefabPath = DressingDirectory + RoomName + "Dressing.prefab";
        private const string PropCatalogPath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/PropCatalog.json";
        private const string PublishedPropRoot =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/";

        /// <summary>The registered entry point. The registry names this exact method.</summary>
        [MenuItem("No Safe Circle/Rooms/Build Chapel Of Ash Dressing")]
        public static void Build()
        {
            GameObject root = BuildDressingRoot();
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(PrefabPath) ?? DressingDirectory);
                PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
                AssetDatabase.SaveAssets();
                AssetDatabase.Refresh();
                Debug.Log($"{RoomName} dressing prefab written to {PrefabPath} with " +
                          $"{root.transform.childCount} placements.");
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(root);
            }
        }

        /// <summary>
        /// Builds the dressing hierarchy in memory without writing any asset.
        /// </summary>
        /// <remarks>
        /// The non-saving seam the fixture drives, so a test can assert every placement without
        /// touching the repository. The caller owns the returned object and must destroy it.
        /// </remarks>
        public static GameObject BuildDressingRoot()
        {
            DressingCatalog catalog = LoadCatalog();
            Dictionary<string, string> categories = LoadPropCategories();

            var root = new GameObject(RoomName + "Dressing");
            var seenInstanceIds = new HashSet<string>(StringComparer.Ordinal);

            foreach (DressingPlacement placement in catalog.props)
            {
                if (!seenInstanceIds.Add(placement.instance_id))
                {
                    throw new InvalidDataException(
                        $"{CatalogPath} repeats instance_id '{placement.instance_id}'. Instance ids " +
                        "identify a placement and must be unique, or a later edit silently moves the " +
                        "wrong prop.");
                }

                Sprite sprite = LoadPropSprite(placement.prop_id, categories);

                var instance = new GameObject(placement.instance_id);
                instance.transform.SetParent(root.transform, false);

                // y IS ALWAYS ZERO -- taken from the contract, not from the placement, so a stray
                // non-zero y in the JSON cannot lift the guardian out through the wall.
                instance.transform.localPosition =
                    new Vector3(placement.position.x, 0f, placement.position.z);
                instance.transform.localRotation =
                    Quaternion.Euler(0f, 0f, placement.rotation_euler_z);
                // Never scaled. The guardian's four pixels of headroom are the reason.
                instance.transform.localScale = Vector3.one;

                var renderer = instance.AddComponent<SpriteRenderer>();
                renderer.sprite = sprite;
                renderer.sortingLayerName = DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName;
                renderer.sortingOrder = placement.sorting_order;
                renderer.spriteSortPoint = SpriteSortPoint.Pivot;

                // No collider is added, ever. Dressing is scenery and must not change where the
                // wizard can walk.
            }

            return root;
        }

        /// <summary>The sorting order the contract's rule gives for a placement.</summary>
        /// <remarks>
        /// Public so the fixture can check the CATALOG's authored value against the rule without
        /// restating the rule in the test. If the two ever disagree the catalog is wrong, and the
        /// test should say which placement rather than silently preferring one of them.
        /// </remarks>
        public static int ExpectedSortingOrder(float x, float z)
        {
            return Mathf.RoundToInt((x - z) * 10f);
        }

        /// <summary>Reads a JSON file, tolerating a UTF-8 byte-order mark.</summary>
        /// <remarks>
        /// JsonUtility.FromJson returns null on a leading BOM rather than saying why, which reads
        /// exactly like a missing file. Strip it here so the failure cannot be misdiagnosed.
        /// </remarks>
        private static string ReadJson(string path)
        {
            string text = File.ReadAllText(path);
            return text.Length > 0 && text[0] == '\uFEFF' ? text.Substring(1) : text;
        }

        private static DressingCatalog LoadCatalog()
        {
            // READ FROM DISK, NOT THROUGH THE ASSETDATABASE. The dressing catalogs carry no .meta
            // on main, so Unity has not imported them as TextAssets and LoadAssetAtPath returns
            // null even though the file is right there. File.ReadAllText does not care whether the
            // importer has seen it yet. (The NSC-082 crew reached the same conclusion first.)
            if (!File.Exists(CatalogPath))
            {
                throw new FileNotFoundException(
                    $"{CatalogPath} is missing. The dressing catalog is authored art and this " +
                    "builder never invents placements, so there is nothing to build without it.",
                    CatalogPath);
            }

            DressingCatalog catalog = JsonUtility.FromJson<DressingCatalog>(ReadJson(CatalogPath));
            if (catalog?.props == null || catalog.props.Length == 0)
            {
                throw new InvalidDataException($"{CatalogPath} declares no placements.");
            }

            return catalog;
        }

        private static Dictionary<string, string> LoadPropCategories()
        {
            if (!File.Exists(PropCatalogPath))
            {
                throw new FileNotFoundException($"{PropCatalogPath} is missing.", PropCatalogPath);
            }

            PropCatalog catalog = JsonUtility.FromJson<PropCatalog>(ReadJson(PropCatalogPath));
            if (catalog?.entries == null || catalog.entries.Length == 0)
            {
                throw new InvalidDataException($"{PropCatalogPath} declares no entries.");
            }

            var categories = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (PropEntry entry in catalog.entries)
            {
                // source_path names the RAW original under Docs/; its immediate folder is the
                // category the published sprite was filed under.
                string directory = Path.GetDirectoryName(entry.source_path);
                categories[entry.id] = string.IsNullOrEmpty(directory)
                    ? string.Empty
                    : Path.GetFileName(directory);
            }

            return categories;
        }

        private static Sprite LoadPropSprite(string propId, Dictionary<string, string> categories)
        {
            if (!categories.TryGetValue(propId, out string category))
            {
                throw new InvalidDataException(
                    $"'{propId}' is placed by {CatalogPath} but is not in {PropCatalogPath}. The " +
                    "prop catalog is the published-art record, so a placement it does not know " +
                    "about cannot be resolved to a sprite.");
            }

            string path = PublishedPropRoot + category + "/" + propId + ".png";
            var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
            if (sprite == null)
            {
                throw new FileNotFoundException(
                    $"'{propId}' does not import as a Sprite at {path}. PropCatalog.json's " +
                    "source_path names the RAW original under Docs/, which Unity cannot load; the " +
                    "published copy must exist under Props/Source/selected/<category>/.",
                    path);
            }

            return sprite;
        }

        [Serializable]
        private sealed class DressingCatalog
        {
            public string room;
            public DressingPlacement[] props;
        }

        [Serializable]
        private sealed class DressingPlacement
        {
            public string instance_id;
            public string prop_id;
            public string footprint;
            public CatalogPosition position;
            public float rotation_euler_z;
            public int sorting_order;
        }

        [Serializable]
        private sealed class CatalogPosition
        {
            public float x;
            public float y;
            public float z;
        }

        [Serializable]
        private sealed class PropCatalog
        {
            public PropEntry[] entries;
        }

        [Serializable]
        private sealed class PropEntry
        {
            public string id;
            public string source_path;
        }
    }
}
