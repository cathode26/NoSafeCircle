using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Editor.Environment
{
    // Verifies HAND-WRITTEN prop prefabs without needing anyone to open the editor.
    //
    // WHY THIS EXISTS. Vincent, 2026-09-26: "we must stop this baking thing", "I write code to
    // instantiate prefabs", "The scene should just be some objects that create prefabs", and the
    // diagnosis behind all of it - "you guys are doing unity in a non human way :) humans dont do
    // what you are doing". The fleet had been generating scene content from 9,739 lines of editor
    // builders because an agent cannot drag a prefab into an inspector. That was the wrong
    // conclusion: a .prefab is YAML, so an agent can WRITE the same artifact a human's mouse
    // produces. These prefabs are authored text files, not build output.
    //
    // WHAT THIS BUYS. Because each prop prefab is an independent file, many workers can author
    // many prefabs at once with no merge conflict and no Unity contention - Vincent's own reason
    // for wanting prefabs ("an agent can work on a prefab", "this will allow you to create many
    // workers and get many prefabs done at the same time"). Unity is then needed only to CONFIRM
    // an import, never to produce the artifact. This is that confirmation, and it is one command.
    //
    // It asserts the things a hand-written file can plausibly get wrong, and nothing else:
    // that Unity imported it at all, that the sprite reference resolved rather than silently
    // becoming null, that the sorting fields match the single shared band the camera's
    // transparency axis depends on, and that the collider is solid with sane extents.
    public static class PropPrefabVerifier
    {
        // Under Resources/ so PropSpawner can reach a prop by prop_id at runtime with no shared
        // registry file to serialize 45 authors behind.
        private const string PrefabFolder =
            "Assets/NoSafeCircle/DoorPrototype/Resources/Props";

        // The ONLY props allowed to carry no collider, named individually with the reason.
        //
        // This is a DECLARED exception list, not a relaxed check: a prefab missing its collider by
        // accident still fails, and adding a prop here is a visible edit with a stated reason.
        // Vincent's rule is "props should block you", and his own chest.prefab pairs a solid base
        // collider with a walk-through trigger over the whole sprite, so "you can walk through it"
        // is already part of his model. These four are a web or a mark on the floor; a collider on
        // them would read as a defect - you would bump into a stain. This is a judgement, it is his
        // to overrule, and it is recorded rather than hidden.
        private static readonly Dictionary<string, string> NoColliderByDesign =
            new Dictionary<string, string>
            {
                ["shared_web_corner_a"] = "a cobweb in a corner - you walk through a web",
                ["shared_web_drape_b"] = "a hanging cobweb - you walk through a web",
                ["ca_sigil_floor_mark"] = "a sigil painted on the floor - flat, nothing to bump into",
                ["lv_sluice_slime_spill"] = "a slime spill on the floor - flat, nothing to bump into",
            };

        // Read from the builder rather than restated, so a change to the band cannot pass here.
        private static int ExpectedSortingOrder => WorldSpriteConvention.SortingOrder;

        private static string ExpectedSortingLayer =>
            WorldSpriteConvention.SortingLayerName;

        [MenuItem("Tools/No Safe Circle/Verify Prop Prefabs")]
        public static void Verify()
        {
            var failures = new List<string>();
            var lines = new List<string>();

            if (!Directory.Exists(PrefabFolder))
            {
                Debug.LogError($"PROP PREFAB VERIFY: folder does not exist: {PrefabFolder}");
                EditorApplication.Exit(2);
                return;
            }

            // Enumerate the FILES on disk, not an AssetDatabase search. A search that returns
            // nothing is indistinguishable from a folder that imported nothing, and this check
            // exists precisely to catch a prefab Unity refused.
            string[] paths = Directory
                .GetFiles(PrefabFolder, "*.prefab", SearchOption.TopDirectoryOnly)
                .Select(p => p.Replace('\\', '/'))
                .OrderBy(p => p, StringComparer.Ordinal)
                .ToArray();

            lines.Add($"PROP PREFAB VERIFY: {paths.Length} .prefab file(s) on disk in {PrefabFolder}");

            if (paths.Length == 0)
            {
                Debug.LogError("PROP PREFAB VERIFY: no prefab files found. Nothing was verified, "
                    + "which is not the same as everything passing.");
                EditorApplication.Exit(2);
                return;
            }

            foreach (string path in paths)
            {
                string id = Path.GetFileNameWithoutExtension(path);
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);

                if (prefab == null)
                {
                    failures.Add($"{id}: UNITY DID NOT IMPORT IT. LoadAssetAtPath returned null.");
                    continue;
                }

                if (prefab.name != id)
                {
                    failures.Add($"{id}: m_Name is '{prefab.name}'. The GameObject name must equal "
                        + "the prop_id, because the spawner resolves prefabs by prop_id.");
                }

                var renderer = prefab.GetComponent<SpriteRenderer>();
                if (renderer == null)
                {
                    failures.Add($"{id}: no SpriteRenderer on the root.");
                    continue;
                }

                // The single most likely hand-authoring failure: a wrong guid or a wrong sub-asset
                // fileID leaves m_Sprite null and the prop renders as nothing at all.
                if (renderer.sprite == null)
                {
                    failures.Add($"{id}: m_Sprite did not resolve - null after import. The guid or "
                        + "the fileID (must be 21300000 for a spriteMode:1 texture) is wrong.");
                }
                else if (renderer.sprite.name != id)
                {
                    failures.Add($"{id}: resolved sprite is '{renderer.sprite.name}', not '{id}'. "
                        + "The guid points at another prop's texture.");
                }

                if (renderer.sortingLayerName != ExpectedSortingLayer)
                {
                    failures.Add($"{id}: sortingLayerName is '{renderer.sortingLayerName}', expected "
                        + $"'{ExpectedSortingLayer}'. A prop on the Default layer draws behind every "
                        + "wall whatever order it carries.");
                }

                if (renderer.sortingOrder != ExpectedSortingOrder)
                {
                    failures.Add($"{id}: sortingOrder is {renderer.sortingOrder}, expected "
                        + $"{ExpectedSortingOrder}. sortingOrder is compared BEFORE the camera's "
                        + "transparency axis, so any other value outranks position unconditionally.");
                }

                if (renderer.spriteSortPoint != SpriteSortPoint.Pivot)
                {
                    failures.Add($"{id}: spriteSortPoint is {renderer.spriteSortPoint}, expected "
                        + "Pivot. Center sorting reads the sprite's middle rather than its ground "
                        + "contact point and breaks depth against the wizard.");
                }

                var box = prefab.GetComponent<BoxCollider>();
                if (box == null)
                {
                    if (NoColliderByDesign.TryGetValue(id, out string why))
                    {
                        lines.Add(string.Format(CultureInfo.InvariantCulture,
                            "  {0,-38} sprite={1,-30} layer={2,-13} order={3,-3} NO COLLIDER BY "
                            + "DESIGN: {4}",
                            id,
                            renderer.sprite == null ? "<NULL>" : renderer.sprite.name,
                            renderer.sortingLayerName,
                            renderer.sortingOrder,
                            why));
                        continue;
                    }

                    failures.Add($"{id}: no BoxCollider. Vincent's decision is that props block the "
                        + "player and have a shape. If this prop should be walk-through, add it to "
                        + "NoColliderByDesign with a reason rather than leaving the collider off.");
                    continue;
                }

                // The inverse guard, and it is the one that actually earns its keep: a prop on the
                // declared walk-through list that HAS acquired a collider. A check that only looks
                // for a missing collider cannot see a collider that should not exist.
                if (NoColliderByDesign.ContainsKey(id))
                {
                    failures.Add($"{id}: carries a collider but is on the declared walk-through "
                        + $"list ({NoColliderByDesign[id]}). Remove one or the other deliberately.");
                }

                if (box.isTrigger)
                {
                    failures.Add($"{id}: the collider is a TRIGGER. A trigger stops neither the "
                        + "CharacterController nor a fireball raycast (which passes "
                        + "QueryTriggerInteraction.Ignore), so the prop would block nothing.");
                }

                if (box.size.x <= 0f || box.size.y <= 0f || box.size.z <= 0f)
                {
                    failures.Add($"{id}: collider size {Fmt(box.size)} has a non-positive extent.");
                }

                lines.Add(string.Format(CultureInfo.InvariantCulture,
                    "  {0,-38} sprite={1,-30} layer={2,-13} order={3,-3} size={4} center={5}",
                    id,
                    renderer.sprite == null ? "<NULL>" : renderer.sprite.name,
                    renderer.sortingLayerName,
                    renderer.sortingOrder,
                    Fmt(box.size),
                    Fmt(box.center)));
            }

            foreach (string line in lines) Debug.Log(line);

            if (failures.Count > 0)
            {
                foreach (string f in failures) Debug.LogError("PROP PREFAB VERIFY FAIL: " + f);
                Debug.LogError($"PROP PREFAB VERIFY: {failures.Count} failure(s) across "
                    + $"{paths.Length} prefab(s).");
                EditorApplication.Exit(1);
                return;
            }

            Debug.Log($"PROP PREFAB VERIFY: PASS. {paths.Length} prefab(s), 0 failures.");
            EditorApplication.Exit(0);
        }

        private static string Fmt(Vector3 v)
        {
            return string.Format(CultureInfo.InvariantCulture, "({0:0.###},{1:0.###},{2:0.###})",
                v.x, v.y, v.z);
        }
    }
}
