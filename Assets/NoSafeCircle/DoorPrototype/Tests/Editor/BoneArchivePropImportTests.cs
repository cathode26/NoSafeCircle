using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>NSC-102. The nine Bone Archive props import as the catalog says they were published.</summary>
    /// <remarks>
    /// VAL-001 and VAL-002. The point of this fixture is that IT COMPUTES ITS OWN EXPECTATION FROM
    /// THE COMMITTED IMAGE. Only <c>pivot_rule</c> is read from PropCatalog.json; the alpha bounding
    /// box is measured from the PNG's pixels, never taken from the catalog's <c>alpha_bounds_px</c>.
    /// A fixture that compared the catalog's pivot against the catalog's own bounds would agree with
    /// itself whatever the imported asset actually did.
    /// <para>
    /// THE TWO BRANCHES, and the gate is explicit that the fixture must not re-decide which applies:
    /// <c>lie_within</c> puts the pivot at the VERTICAL CENTRE of the alpha box, everything else puts
    /// it on the GROUND LINE, the box's bottom row. PIVOT X IS 0.5 IN BOTH CASES -- measured, not
    /// assumed: shared_bone_pile_b's alpha box centres on x 0.505 while its committed pivot x is 0.5.
    /// </para>
    /// <para>
    /// WHY THE BRANCH MATTERS, from the contract's own withdrawal: an earlier revision derived the
    /// ground line for all nine. shared_bone_pile_b is lie_within, its committed pivot y is 0.479167,
    /// and the ground-line derivation gives 0.041667 -- 31.5 pixels apart on a 72-pixel canvas. The
    /// old gate FAILED A CORRECTLY IMPORTED ASSET. A prop whose pivot_rule is missing or unrecognised
    /// therefore FAILS here rather than defaulting to either branch.
    /// </para>
    /// <para>
    /// AND THE TYPE CHECK IS NOT REDUNDANT: a stub .meta yields a non-Sprite asset while several
    /// importer fields still read plausibly, so the fixture asserts the loaded asset IS a Sprite as
    /// well as asserting the importer's settings.
    /// </para>
    /// </remarks>
    public sealed class BoneArchivePropImportTests
    {
        private const string PropCatalogPath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/PropCatalog.json";
        private const string PublishedPropRoot =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/";
        private const int ExpectedPixelsPerUnit = 64;

        private static readonly string[] BoneArchiveProps =
        {
            "ba_landmark_chained_grimoire_lectern",
            "ba_book_and_scroll_stack",
            "ba_spilled_scroll_basket",
            "ba_collapsed_reading_table_z",
            "ba_comedy_skull_with_spectacles",
            "shared_bone_pile_a",
            "shared_bone_pile_b",
            "shared_web_corner_a",
            "shared_web_drape_b",
        };

        [Test] // VAL-001
        public void EveryProp_ImportsAsASpriteWithTheApprovedImportSettings()
        {
            foreach (string id in BoneArchiveProps)
            {
                string path = ResolvePath(id);

                // The asset's TYPE is checked, not just the importer's fields: a stub .meta produces
                // a non-Sprite asset whose importer settings can still read plausibly.
                UnityEngine.Object asset = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(path);
                Assert.IsNotNull(asset, id + ": nothing imported at " + path);
                var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
                Assert.IsNotNull(sprite, id + ": did not import as a Sprite at " + path);

                var importer = AssetImporter.GetAtPath(path) as TextureImporter;
                Assert.IsNotNull(importer, id + ": has no TextureImporter at " + path);

                Assert.AreEqual(TextureImporterType.Sprite, importer.textureType, id + " textureType");
                Assert.AreEqual(SpriteImportMode.Single, importer.spriteImportMode, id + " spriteImportMode");
                Assert.AreEqual(ExpectedPixelsPerUnit, importer.spritePixelsPerUnit, id + " spritePixelsPerUnit");
                Assert.AreEqual(FilterMode.Point, importer.filterMode, id + " filterMode");
                Assert.AreEqual(TextureImporterCompression.Uncompressed, importer.textureCompression,
                    id + " textureCompression must be None");
                Assert.IsTrue(importer.alphaIsTransparency, id + " alphaIsTransparency");
                Assert.IsFalse(importer.mipmapEnabled, id + " mipmapEnabled must be false");
                Assert.AreEqual(TextureWrapMode.Clamp, importer.wrapMode, id + " wrapMode");
                Assert.AreEqual(TextureImporterShape.Texture2D, importer.textureShape, id + " textureShape");
            }
        }

        [Test] // VAL-002
        public void EveryProp_PivotMatchesTheRuleItsCatalogEntryNames()
        {
            Dictionary<string, string> rules = ReadPivotRules();

            foreach (string id in BoneArchiveProps)
            {
                string path = ResolvePath(id);

                Assert.IsTrue(rules.TryGetValue(id, out string rule) && !string.IsNullOrWhiteSpace(rule),
                    id + ": PropCatalog.json declares no pivot_rule. This fixture reads the field and " +
                    "does not re-decide it, so a missing rule fails rather than defaulting to a branch.");

                RectInt box = AlphaBoundsFromCommittedImage(path, out int canvasWidth, out int canvasHeight);
                Assert.Greater(box.width, 0, id + ": the committed image has no opaque pixels.");
                Assert.Greater(box.height, 0, id + ": the committed image has no opaque pixels.");

                // box.y is the TOP row in image coordinates (y grows downward); Unity's pivot is
                // normalized from the BOTTOM, hence canvasHeight - row.
                float expectedY;
                switch (rule)
                {
                    case "lie_within":
                        expectedY = (canvasHeight - (box.y + box.height / 2f)) / (float)canvasHeight;
                        break;
                    case "ground_line":
                        // (float) IS LOAD-BEARING: every term here is an int, so without it C# does INTEGER
                        // division and 16/188 becomes 0. The lie_within branch above only escaped
                        // that because its `/ 2f` already forced float -- which is why this bug
                        // hid on one path and not the other.
                        expectedY = (canvasHeight - (box.y + box.height)) / (float)canvasHeight;
                        break;
                    default:
                        Assert.Fail(id + ": unrecognised pivot_rule '" + rule + "'. The gate names " +
                                    "lie_within and ground_line; an unknown rule fails rather than " +
                                    "falling through to either branch.");
                        return;
                }

                var importer = (TextureImporter)AssetImporter.GetAtPath(path);
                var settings = new TextureImporterSettings();
                importer.ReadTextureSettings(settings);

                Assert.AreEqual((int)SpriteAlignment.Custom, settings.spriteAlignment,
                    id + ": spriteAlignment must be Custom for an authored pivot.");
                Assert.AreEqual(0.5f, settings.spritePivot.x, 1f / canvasWidth,
                    id + " pivot x must be 0.5 (within one pixel), whichever branch applies.");
                Assert.AreEqual(expectedY, settings.spritePivot.y, 1f / canvasHeight,
                    string.Format(CultureInfo.InvariantCulture,
                        "{0} pivot y: rule '{1}' over an alpha box measured from the committed image " +
                        "(x {2}, y {3}, {4}x{5} on a {6}x{7} canvas) gives {8:F6}, but the asset imports " +
                        "{9:F6}. The expectation is computed here, never written in as a constant.",
                        id, rule, box.x, box.y, box.width, box.height, canvasWidth, canvasHeight,
                        expectedY, settings.spritePivot.y));
            }
        }

        /// <summary>Measures the opaque bounding box from the committed PNG's own bytes.</summary>
        /// <remarks>
        /// Decoded from disk rather than through the imported texture, so the measurement does not
        /// depend on isReadable or on any other import setting this fixture is meant to be judging.
        /// </remarks>
        private static RectInt AlphaBoundsFromCommittedImage(string path, out int width, out int height)
        {
            byte[] bytes = File.ReadAllBytes(path);
            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                Assert.IsTrue(texture.LoadImage(bytes), "Could not decode " + path);
                width = texture.width;
                height = texture.height;

                Color32[] pixels = texture.GetPixels32();
                int minX = width, minY = height, maxX = -1, maxY = -1;
                for (int row = 0; row < height; row++)
                {
                    for (int column = 0; column < width; column++)
                    {
                        if (pixels[row * width + column].a == 0) continue;
                        // GetPixels32 is bottom-up; convert to a top-down row so the arithmetic
                        // matches the catalog's alpha_bounds_px convention.
                        int topDownRow = height - 1 - row;
                        if (column < minX) minX = column;
                        if (column > maxX) maxX = column;
                        if (topDownRow < minY) minY = topDownRow;
                        if (topDownRow > maxY) maxY = topDownRow;
                    }
                }

                return maxX < 0
                    ? new RectInt(0, 0, 0, 0)
                    : new RectInt(minX, minY, maxX - minX + 1, maxY - minY + 1);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(texture);
            }
        }

        private static Dictionary<string, string> ReadPivotRules()
        {
            Assert.IsTrue(File.Exists(PropCatalogPath), PropCatalogPath + " is missing.");
            string json = File.ReadAllText(PropCatalogPath);
            if (json.Length > 0 && json[0] == '﻿') json = json.Substring(1);

            var catalog = JsonUtility.FromJson<PropCatalogFile>(json);
            Assert.IsNotNull(catalog?.entries, PropCatalogPath + " parsed to no entries.");

            var rules = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (PropCatalogEntry entry in catalog.entries)
            {
                rules[entry.id] = entry.pivot_rule;
            }
            return rules;
        }

        private static string ResolvePath(string id)
        {
            Assert.IsTrue(File.Exists(PropCatalogPath), PropCatalogPath + " is missing.");
            string json = File.ReadAllText(PropCatalogPath);
            if (json.Length > 0 && json[0] == '﻿') json = json.Substring(1);
            var catalog = JsonUtility.FromJson<PropCatalogFile>(json);

            foreach (PropCatalogEntry entry in catalog.entries)
            {
                if (entry.id != id) continue;
                // source_path names the RAW original under Docs/, which Unity cannot load; its
                // folder is the category the published sprite was filed under.
                string category = Path.GetFileName(Path.GetDirectoryName(entry.source_path));
                return PublishedPropRoot + category + "/" + id + ".png";
            }

            Assert.Fail(id + " is not in " + PropCatalogPath);
            return null;
        }

        [Serializable]
        private sealed class PropCatalogFile
        {
            public PropCatalogEntry[] entries;
        }

        [Serializable]
        private sealed class PropCatalogEntry
        {
            public string id;
            public string source_path;
            public string pivot_rule;
        }
    }
}
