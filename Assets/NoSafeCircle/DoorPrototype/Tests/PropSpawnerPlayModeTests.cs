using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Proves the architecture Vincent asked for, end to end, AT RUNTIME, with NO BAKE and no scene
    // mutation: authored prop prefabs are instantiated from authored catalog data at Play, they
    // land where the catalog says, they carry the sorting convention, and their colliders actually
    // stop things.
    //
    // His words: "No we must stop this baking thing", "I write code to instantiate prefabs", "The
    // scene should just be some objects that create prefabs", "props should block you :) they
    // should have a shape".
    //
    // WHY A PLAYMODE TEST RATHER THAN EDITING THE SCENE. The proof that matters is "does this work
    // at Play", and a test answers it without touching Assets/Scenes/DoorPrototype.unity - a 685KB
    // binary artifact that 35 contracts name and that no agent can merge. So this is both the
    // cheaper proof and the safer one.
    //
    // WHY IT DELIBERATELY DOES NOT CALL ConfigureAndBuild(). Eleven PlayMode fixtures in this
    // project call GameplayNavigationSurface.ConfigureAndBuild() in their own setup, which
    // manufactures a navmesh the built game may never have, then verify pathfinding on top of it.
    // This fixture tests spawning and physics only, so it does not need one and does not fake one.
#if UNITY_EDITOR
    public sealed class PropSpawnerPlayModeTests
    {
        private const string CatalogFolder =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/RoomDressing";

        private const string PrefabFolder =
            "Assets/NoSafeCircle/DoorPrototype/Resources/Props";

        private GameObject spawnerObject;

        [TearDown]
        public void TearDown()
        {
            if (spawnerObject != null)
            {
                Object.Destroy(spawnerObject);
                spawnerObject = null;
            }
        }

        private static TextAsset[] LoadCatalogs()
        {
            // Enumerate the FILES, then load each. A glob through AssetDatabase.FindAssets that
            // returned nothing would be indistinguishable from a folder with no catalogs, and the
            // count is the thing every assertion below is derived from.
            string[] paths = Directory
                .GetFiles(CatalogFolder, "*DressingCatalog.json", SearchOption.TopDirectoryOnly)
                .Select(p => p.Replace('\\', '/'))
                .OrderBy(p => p, System.StringComparer.Ordinal)
                .ToArray();

            Assert.AreEqual(5, paths.Length,
                "Expected five room dressing catalogs in " + CatalogFolder + ". Found "
                + paths.Length + ". Every expectation in this fixture is derived from them, so a "
                + "wrong count here would make the rest pass vacuously.");

            var assets = paths
                .Select(UnityEditor.AssetDatabase.LoadAssetAtPath<TextAsset>)
                .ToArray();

            for (int i = 0; i < assets.Length; i++)
            {
                Assert.IsNotNull(assets[i],
                    paths[i] + " did not import as a TextAsset. PropSpawner reads catalogs as "
                    + "TextAssets rather than with File IO, because File IO does not work on WebGL.");
            }

            return assets;
        }

        /// The number of placements the catalogs themselves declare. Computed, never restated: a
        /// literal here would pass while the catalogs said something else.
        private static int ExpectedPlacementCount(IEnumerable<TextAsset> catalogs)
        {
            int total = 0;
            foreach (TextAsset catalog in catalogs)
            {
                var parsed = JsonUtility.FromJson<RoomDressingCatalog>(catalog.text);
                Assert.IsNotNull(parsed, catalog.name + " did not deserialize.");
                Assert.IsNotNull(parsed.props, catalog.name + " has no props array.");
                total += parsed.props.Length;
            }

            Assert.Greater(total, 0, "The catalogs declare zero placements, so every count "
                + "assertion below would pass on an empty spawn.");
            return total;
        }

        private PropSpawner CreateSpawner(out TextAsset[] catalogs)
        {
            catalogs = LoadCatalogs();
            spawnerObject = new GameObject("PropSpawnerUnderTest");
            var spawner = spawnerObject.AddComponent<PropSpawner>();
            spawner.Configure(catalogs);
            return spawner;
        }

        [UnityTest]
        public IEnumerator Spawn_InstantiatesEveryPlacementTheCatalogsDeclare()
        {
            PropSpawner spawner = CreateSpawner(out TextAsset[] catalogs);
            int expected = ExpectedPlacementCount(catalogs);

            int spawned = spawner.Spawn();
            yield return null;

            Assert.AreEqual(expected, spawned,
                "PropSpawner spawned " + spawned + " of " + expected + " declared placements. A "
                + "shortfall means a prop_id did not resolve to a prefab under Resources/Props, "
                + "which the console errors name individually.");

            // Count the actual objects too, not just the return value. A method can return a
            // number without having created anything.
            int actualChildren = spawnerObject.GetComponentsInChildren<SpriteRenderer>(true).Length;
            Assert.AreEqual(expected, actualChildren,
                "The returned count and the objects in the hierarchy disagree.");
        }

        [UnityTest]
        public IEnumerator EverySpawnedPropCarriesTheSortingConventionFromItsPrefab()
        {
            PropSpawner spawner = CreateSpawner(out _);
            spawner.Spawn();
            yield return null;

            SpriteRenderer[] renderers =
                spawnerObject.GetComponentsInChildren<SpriteRenderer>(true);
            Assert.Greater(renderers.Length, 0, "Nothing spawned, so this passes vacuously.");

            // From the RUNTIME convention class, not restated. This assembly cannot see the
            // Editor assembly, and it should not: the values the built game uses are the
            // ones worth asserting.
            var expectedLayer = WorldSpriteConvention.SortingLayerName;
            var expectedOrder = WorldSpriteConvention.SortingOrder;

            foreach (SpriteRenderer renderer in renderers)
            {
                string who = renderer.gameObject.name;

                Assert.IsNotNull(renderer.sprite, who + " has a null sprite after Instantiate.");

                Assert.AreEqual(expectedLayer, renderer.sortingLayerName,
                    who + " is on sorting layer '" + renderer.sortingLayerName + "'. A prop on the "
                    + "Default layer draws behind every wall whatever order it carries, because the "
                    + "LAYER is compared before the order.");

                Assert.AreEqual(expectedOrder, renderer.sortingOrder,
                    who + " carries sortingOrder " + renderer.sortingOrder + ". sortingOrder is "
                    + "compared BEFORE the camera's transparency axis, so any other value outranks "
                    + "position unconditionally - which is how a bookshelf drew in front of a "
                    + "wizard standing behind it.");

                Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint,
                    who + " sorts by Center rather than Pivot, which reads the sprite's middle "
                    + "instead of its ground contact point.");

                // The spawner sets position and rotation and nothing else, so each of the above is
                // evidence that the PREFAB carries the convention - which is the design's claim.
            }
        }

        [UnityTest]
        public IEnumerator SpawnedPropsLandWhereTheCatalogSaysAndNeverAboveTheFloor()
        {
            PropSpawner spawner = CreateSpawner(out TextAsset[] catalogs);
            spawner.Spawn();
            yield return null;

            // LOOK UP PER ROOM, not globally. instance_ids are room-scoped: measured across the five
            // catalogs there are 222 placements but only 219 distinct ids, because
            // NORTH-WALL-drape-01 and NW-CORNER-web-01 recur in two and three rooms respectively.
            // A single name->transform dictionary throws on those, and a first-wins lookup would
            // silently check one room's prop against another room's coordinates.
            int checked_ = 0;
            foreach (TextAsset catalog in catalogs)
            {
                var parsed = JsonUtility.FromJson<RoomDressingCatalog>(catalog.text);

                Transform roomRoot = spawnerObject.transform.Find(parsed.room + "Dressing");
                Assert.IsNotNull(roomRoot,
                    "No '" + parsed.room + "Dressing' parent was created for " + catalog.name + ".");

                var byInstanceId = roomRoot
                    .GetComponentsInChildren<SpriteRenderer>(true)
                    .ToDictionary(r => r.gameObject.name, r => r.transform);

                foreach (DressingPlacement placement in parsed.props)
                {
                    Assert.IsTrue(byInstanceId.TryGetValue(placement.instance_id, out Transform t),
                        "No spawned object named '" + placement.instance_id + "' under "
                        + parsed.room + "Dressing.");

                    Assert.AreEqual(placement.position.x, t.localPosition.x, 0.0001f,
                        placement.instance_id + " x");
                    Assert.AreEqual(placement.position.z, t.localPosition.z, 0.0001f,
                        placement.instance_id + " z");

                    // y is forced to zero by the spawner rather than read from the placement, so a
                    // stray non-zero y in authored json cannot lift a prop out through a wall.
                    Assert.AreEqual(0f, t.localPosition.y, 0.0001f,
                        placement.instance_id + " must sit on the floor. The spawner forces y to "
                        + "zero deliberately; the catalog's own y field is read and discarded.");

                    Assert.AreEqual(Vector3.one, t.localScale,
                        placement.instance_id + " is scaled. Props are never scaled - the guardian "
                        + "statue's four pixels of headroom are the reason.");

                    checked_++;
                }
            }

            Assert.Greater(checked_, 0, "Checked zero placements.");
        }

        [UnityTest]
        public IEnumerator SolidPropsActuallyBlockAChestHeightRay_AndShortOnesDoNot()
        {
            PropSpawner spawner = CreateSpawner(out _);
            spawner.Spawn();
            yield return null;

            // Physics.Raycast needs the colliders registered; one physics step is enough.
            Physics.SyncTransforms();

            BoxCollider[] boxes = spawnerObject.GetComponentsInChildren<BoxCollider>(true);
            Assert.Greater(boxes.Length, 0,
                "No spawned prop carries a collider, so Vincent's 'props should block you' is not "
                + "satisfied at all.");

            SpriteRenderer[] all = spawnerObject.GetComponentsInChildren<SpriteRenderer>(true);
            Assert.Less(boxes.Length, all.Length,
                "EVERY spawned prop carries a collider. Four prop ids are deliberately "
                + "walk-through (two cobwebs, two floor marks), so the set must discriminate - "
                + "otherwise this fixture cannot tell a correct collider from a blanket one.");

            foreach (BoxCollider box in boxes)
            {
                Assert.IsFalse(box.isTrigger,
                    box.gameObject.name + " has a TRIGGER collider. A trigger stops neither a "
                    + "CharacterController nor a fireball raycast, which passes "
                    + "QueryTriggerInteraction.Ignore - so the prop would block nothing.");
            }

            // THE REAL PROOF, and it is the one a component assertion cannot give: fire the same
            // shape of ray FireballProjectile uses - chest height, triggers ignored - at a prop tall
            // enough to be hit, and require that it is hit.
            BoxCollider tallest = boxes.OrderByDescending(b => b.size.y).First();
            Assert.Greater(tallest.size.y, 1f,
                "The tallest spawned collider is only " + tallest.size.y + " units, so no prop "
                + "reaches the chest height a fireball flies at and this check would be vacuous.");

            Vector3 target = tallest.transform.position;
            Vector3 chestOrigin = target + Vector3.up - Vector3.forward * 6f;
            bool hit = Physics.Raycast(chestOrigin, Vector3.forward, out RaycastHit info, 12f,
                Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);

            Assert.IsTrue(hit,
                "A chest-height ray fired at '" + tallest.gameObject.name + "' (collider height "
                + tallest.size.y + ") hit nothing. This is the shape FireballProjectile uses, so "
                + "props would not stop spells.");

            Assert.AreSame(tallest, info.collider,
                "The chest-height ray hit '" + info.collider.gameObject.name + "' rather than the "
                + "prop it was aimed at. Another prop is in the way, which makes this a weaker "
                + "check than intended rather than a failure of the design.");
        }

        [UnityTest]
        public IEnumerator SpawningTwiceDoesNotDoubleTheDressing()
        {
            PropSpawner spawner = CreateSpawner(out _);

            int first = spawner.Spawn();
            yield return null;
            int second = spawner.Spawn();
            yield return null;

            Assert.AreEqual(first, second, "A second Spawn() returned a different count.");

            int actual = spawnerObject.GetComponentsInChildren<SpriteRenderer>(true).Length;
            Assert.AreEqual(first, actual,
                "After two Spawn() calls the hierarchy holds " + actual + " props rather than "
                + first + ". Doubled dressing reads as a placement bug rather than a lifecycle "
                + "bug, which is why Spawn() clears first.");
        }

        [Test]
        public void EveryPropIdInEveryCatalogHasAPrefabOnDisk()
        {
            // Cheapest guard in the set and the one that fails first in practice. Runs without
            // entering Play mode at all.
            TextAsset[] catalogs = LoadCatalogs();
            var missing = new List<string>();
            var seen = new HashSet<string>();

            foreach (TextAsset catalog in catalogs)
            {
                var parsed = JsonUtility.FromJson<RoomDressingCatalog>(catalog.text);
                foreach (DressingPlacement placement in parsed.props)
                {
                    if (!seen.Add(placement.prop_id)) continue;
                    if (!File.Exists(Path.Combine(PrefabFolder, placement.prop_id + ".prefab")))
                    {
                        missing.Add(placement.prop_id);
                    }
                }
            }

            Assert.Greater(seen.Count, 0, "Zero distinct prop ids, so this passes vacuously.");
            Assert.IsEmpty(missing,
                "These prop ids are placed but have no prefab under " + PrefabFolder + ": "
                + string.Join(", ", missing));
        }
    }
#endif
}
