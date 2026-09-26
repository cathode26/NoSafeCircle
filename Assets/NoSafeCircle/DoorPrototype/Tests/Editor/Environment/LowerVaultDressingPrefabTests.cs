using System;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Editor.Environment;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.RoomDressing
{
    /// <summary>NSC-082. The Lower Vault dressing prefab reproduces its authored catalog exactly.</summary>
    /// <remarks>
    /// The catalog is ART and this fixture does not second-guess it. What it checks is that the
    /// BUILDER reproduces what the Art Director authored, and that the catalog obeys the contract
    /// the catalog itself declares -- so a drift between the two is named rather than silently
    /// resolved in the builder's favour.
    /// </remarks>
    public sealed class LowerVaultDressingPrefabTests
    {
        private const string CatalogPath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/RoomDressing/LowerVaultDressingCatalog.json";

        private static CatalogPlacement[] ReadCatalog()
        {
            // Read from disk: the catalogs carry no .meta on main, so the AssetDatabase has not
            // imported them and LoadAssetAtPath returns null for a file that plainly exists.
            Assert.IsTrue(File.Exists(CatalogPath),
                CatalogPath + " is missing; the authored dressing is the input.");
            string json = File.ReadAllText(CatalogPath);
            if (json.Length > 0 && json[0] == '\uFEFF') json = json.Substring(1);
            var catalog = JsonUtility.FromJson<CatalogFile>(json);
            Assert.IsNotNull(catalog?.props, CatalogPath + " parsed to no placements.");
            Assert.Greater(catalog.props.Length, 0, "The catalog declares no placements.");
            return catalog.props;
        }

        [Test]
        public void Builder_ReproducesEveryAuthoredPlacement()
        {
            CatalogPlacement[] authored = ReadCatalog();
            GameObject root = LowerVaultDressingPrefabBuilder.BuildDressingRoot();
            try
            {
                Assert.AreEqual(authored.Length, root.transform.childCount,
                    "The prefab must contain exactly the authored placements -- no more, no fewer.");

                var byName = new Dictionary<string, Transform>(StringComparer.Ordinal);
                foreach (Transform child in root.transform)
                {
                    byName[child.name] = child;
                }

                foreach (CatalogPlacement placement in authored)
                {
                    Assert.IsTrue(byName.TryGetValue(placement.instance_id, out Transform built),
                        $"Placement '{placement.instance_id}' is authored but was not built.");

                    Assert.AreEqual(placement.position.x, built.localPosition.x, 0.0001f,
                        placement.instance_id + " x");
                    Assert.AreEqual(placement.position.z, built.localPosition.z, 0.0001f,
                        placement.instance_id + " z");

                    // y IS ALWAYS ZERO. The standing guardian is 2.44 units against a 2.5-unit
                    // wall: 0.06 units of headroom, about four pixels at 64 PPU. Any lift puts it
                    // through the wall, so this is a hard assertion rather than a tolerance.
                    Assert.AreEqual(0f, built.localPosition.y, 0.0001f,
                        placement.instance_id + " must sit on the floor at y = 0.");

                    // Never scaled, for the same four pixels.
                    Assert.AreEqual(Vector3.one, built.localScale,
                        placement.instance_id + " must not be scaled.");

                    var renderer = built.GetComponent<SpriteRenderer>();
                    Assert.IsNotNull(renderer, placement.instance_id + " has no SpriteRenderer.");
                    Assert.IsNotNull(renderer.sprite,
                        placement.instance_id + " resolved no sprite for prop '" + placement.prop_id + "'.");
                    Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint,
                        placement.instance_id + " must sort by pivot, as the world-sprite convention requires.");
                    // NOT the authored sorting_order, deliberately. Every prop sits in the
                    // shared world-sprite band so the camera transparency axis decides its
                    // depth by POSITION. An authored integer here is compared BEFORE the axis
                    // and wins unconditionally, which is how a bookshelf came to render behind
                    // a wizard who was standing behind it. The catalog keeps its numbers and
                    // Catalog_ObeysTheSortingRuleItDeclares still checks them against the rule
                    // the catalog declares; they are simply not what the renderer carries.
                    Assert.AreEqual(
                        NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.WorldSpriteSortingOrder,
                        renderer.sortingOrder,
                        placement.instance_id + " must sit in the shared world-sprite band, not "
                        + "carry an authored order that outranks the camera axis.");

                    // NO COLLIDERS, EVER. Dressing is scenery; it must never change where the
                    // wizard can walk. Checked per placement rather than once on the root, because
                    // a collider on one prop is exactly the case a root-only check would miss.
                    Assert.IsEmpty(built.GetComponents<Collider>(),
                        placement.instance_id + " carries a collider; the dressing prefab must carry none.");
                    Assert.IsEmpty(built.GetComponents<Collider2D>(),
                        placement.instance_id + " carries a 2D collider; the dressing prefab must carry none.");
                }
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(root);
            }
        }

        [Test]
        public void Catalog_ObeysTheSortingRuleItDeclares()
        {
            // The catalog states its own rule: sorting_order = round((x - z) * 10). This compares
            // the AUTHORED value against that rule rather than against the builder, so if the two
            // ever disagree the failure names the placement instead of the builder quietly winning.
            foreach (CatalogPlacement placement in ReadCatalog())
            {
                int expected = LowerVaultDressingPrefabBuilder.ExpectedSortingOrder(
                    placement.position.x, placement.position.z);
                Assert.AreEqual(expected, placement.sorting_order,
                    $"{placement.instance_id} at x={placement.position.x} z={placement.position.z} " +
                    "does not match the catalog's own sorting rule.");
            }
        }

        [Test]
        public void EveryPlacement_LiesInsideTheRoom()
        {
            // A prop outside the room is invisible at best and through a wall at worst. Bounds come
            // from the committed layout, not from the catalog, so this cannot pass by construction.
            foreach (CatalogPlacement placement in ReadCatalog())
            {
                Assert.GreaterOrEqual(placement.position.x, LowerVaultLayout.MinimumX, placement.instance_id + " x");
                Assert.LessOrEqual(placement.position.x, LowerVaultLayout.MaximumX, placement.instance_id + " x");
                Assert.GreaterOrEqual(placement.position.z, LowerVaultLayout.MinimumZ, placement.instance_id + " z");
                Assert.LessOrEqual(placement.position.z, LowerVaultLayout.MaximumZ, placement.instance_id + " z");
            }
        }

        [Explicit("Set NSC_DRESSING_CAPTURE_OUTPUT to photograph the dressed room.")]
        [Test]
        public void CaptureDressedLowerVault()
        {
            string output = System.Environment.GetEnvironmentVariable("NSC_DRESSING_CAPTURE_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC_DRESSING_CAPTURE_OUTPUT to run the explicit dressing capture.");
            }

            string outputFull = Path.GetFullPath(output);
            string repository = Path.GetFullPath(Directory.GetCurrentDirectory())
                .TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            Assert.IsFalse(outputFull.StartsWith(repository, StringComparison.OrdinalIgnoreCase),
                "Write capture output OUTSIDE the repository so a run cannot dirty it.");
            Directory.CreateDirectory(outputFull);

            // The room is opened and dressed IN MEMORY and never saved. Assets/Scenes/Rooms and
            // Assets/Scenes/DoorPrototype.unity both belong to other tasks; this fixture must leave
            // the repository exactly as it found it.
            Scene scene = EditorSceneManager.OpenScene(
                "Assets/Scenes/Rooms/LowerVault.unity", OpenSceneMode.Single);
            Assert.IsTrue(scene.IsValid(), "Could not open Lower Vault.");

            GameObject dressing = LowerVaultDressingPrefabBuilder.BuildDressingRoot();
            GameObject cameraObject = null;
            RenderTexture target = null;
            try
            {
                var rotation = Quaternion.Euler(30f, -45f, 0f);
                var centre = new Vector3(
                    (LowerVaultLayout.MinimumX + LowerVaultLayout.MaximumX) * 0.5f,
                    0f,
                    (LowerVaultLayout.MinimumZ + LowerVaultLayout.MaximumZ) * 0.5f);

                cameraObject = new GameObject("DressingCaptureCamera", typeof(Camera));
                Camera camera = cameraObject.GetComponent<Camera>();
                camera.orthographic = true;
                camera.transform.rotation = rotation;
                cameraObject.transform.position = centre + rotation * Vector3.back * 51.96f;

                target = new RenderTexture(1600, 1200, 24);
                camera.targetTexture = target;

                // TWO SHOTS, because one size cannot do both jobs. Size 8 is the Art Director's
                // review size and is what VAL-002 will be judged at -- close enough to see a prop.
                // Size 20 frames the whole 28 x 26 room, which is what a person actually wants to
                // look at; at size 8 a room reads as a corner of empty floor.
                foreach (var shotSpec in new[]
                {
                    new KeyValuePair<string, float>("lower-vault-dressed.png", 8f),
                    new KeyValuePair<string, float>("lower-vault-dressed-room.png", 20f),
                })
                {
                    camera.orthographicSize = shotSpec.Value;
                    camera.Render();

                    RenderTexture previous = RenderTexture.active;
                    RenderTexture.active = target;
                    var shot = new Texture2D(target.width, target.height, TextureFormat.RGB24, false);
                    shot.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0);
                    shot.Apply();
                    RenderTexture.active = previous;

                    File.WriteAllBytes(Path.Combine(outputFull, shotSpec.Key), shot.EncodeToPNG());
                    UnityEngine.Object.DestroyImmediate(shot);
                }
            }
            finally
            {
                if (cameraObject != null) UnityEngine.Object.DestroyImmediate(cameraObject);
                if (target != null) UnityEngine.Object.DestroyImmediate(target);
                UnityEngine.Object.DestroyImmediate(dressing);
            }
        }

        [Serializable]
        private sealed class CatalogFile
        {
            public CatalogPlacement[] props;
        }

        [Serializable]
        public sealed class CatalogPlacement
        {
            public string instance_id;
            public string prop_id;
            public CatalogPosition position;
            public float rotation_euler_z;
            public int sorting_order;
        }

        [Serializable]
        public sealed class CatalogPosition
        {
            public float x;
            public float y;
            public float z;
        }
    }
}
