// NSC-078 completion gate: the committed .png.meta files under Props/Source must carry the
// import settings DungeonPropImportPostprocessor applies, and must load as real Sprites.
//
// Two deliberate design choices, both bought with failures:
//
//  1. The expected values are asserted against the CONTRACT's list and cross-checked against
//     PropCatalog.json, which is written by a different process from the importer. A check
//     whose expectations come from the artifact it checks is self-consistent by construction:
//     an earlier hand-rolled check passed all sixteen props while Unity failed all sixteen,
//     because it asserted the eight fields copied from a template rather than the nine the
//     contract names. wrapMode was the missing one.
//
//  2. Every test refuses to pass on an empty set. A suite that silently enumerates zero
//     assets reports green and proves nothing.

using System.Collections.Generic;
using System.IO;
using System.Linq;
using NoSafeCircle.DoorPrototype.Editor.Art;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public class DungeonPropImportSettingsTests
    {
        private const string PropRoot =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected";

        private const string CatalogPath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/PropCatalog.json";

        private const float PivotTolerance = 0.002f;

        private static string[] SelectedPngPaths()
        {
            if (!Directory.Exists(PropRoot))
            {
                return new string[0];
            }

            return Directory.GetFiles(PropRoot, "*.png", SearchOption.AllDirectories)
                            .Select(p => p.Replace('\\', '/'))
                            .OrderBy(p => p, System.StringComparer.Ordinal)
                            .ToArray();
        }

        /// <summary>
        /// Force every prop through the importer before anything reads its settings.
        ///
        /// WITHOUT THIS THE WHOLE SUITE CAN PASS ON A STALE .meta. ReadTextureSettings
        /// returns what is STORED, not what the postprocessor would produce, so a run over
        /// assets nobody re-imported asserts hand-edited values against themselves and goes
        /// green. That is exactly what happened: this gate reported 5/5 while the three
        /// lie-within props imported on their ground line, and it was only caught when a
        /// merger built the branch from a fresh checkout.
        ///
        /// ForceUpdate makes the suite assert what the IMPORTER produces. That is the
        /// difference between verifying the .meta and verifying the imported sprite.
        /// </summary>
        [OneTimeSetUp]
        public void ReimportSoStaleSettingsCannotPass()
        {
            var paths = SelectedPngPaths();
            if (paths.Length == 0)
            {
                return;
            }

            try
            {
                AssetDatabase.StartAssetEditing();
                foreach (var path in paths)
                {
                    AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
                }
            }
            finally
            {
                AssetDatabase.StopAssetEditing();
            }

            AssetDatabase.Refresh();
        }

        /// <summary>
        /// The classification itself, proved from the catalog's text with no import at all.
        ///
        /// This is the check the old arrangement could not have: classification was only
        /// observable through the importer, so a classifier that never ran was
        /// indistinguishable from one that ran and answered "ground line". Here the rule is
        /// read straight from the bytes, so a regression fails on its own terms.
        /// </summary>
        [Test]
        public void EveryCatalogEntryClassifiesFromTheCatalogText()
        {
            string text;
            Assert.That(DungeonPropImportPostprocessor.TryReadCatalogText(out text), Is.True,
                "could not read " + CatalogPath + " off disk");

            var catalog = JsonUtility.FromJson<CatalogFile>(text);
            Assert.That(catalog, Is.Not.Null, "PropCatalog.json did not parse");
            Assert.That(catalog.entries, Is.Not.Null.And.Not.Empty,
                "PropCatalog.json has no entries; refusing to pass vacuously");

            var failures = new List<string>();
            var lieWithin = 0;
            foreach (var entry in catalog.entries)
            {
                var expected = entry.pivot_rule == "lie_within"
                    ? DungeonPropImportPostprocessor.PropPivotRule.LieWithin
                    : DungeonPropImportPostprocessor.PropPivotRule.GroundLine;
                if (expected == DungeonPropImportPostprocessor.PropPivotRule.LieWithin)
                {
                    lieWithin++;
                }

                var actual = DungeonPropImportPostprocessor.ClassifyFromCatalogText(text, entry.id);
                if (actual != expected)
                {
                    failures.Add(string.Format("{0}: catalog says {1}, scan says {2}",
                        entry.id, entry.pivot_rule, actual));
                }
            }

            Assert.That(lieWithin, Is.GreaterThan(0),
                "no entry is classified lie_within, so this test would pass without ever "
                + "exercising the branch it exists to cover");
            Assert.That(failures, Is.Empty, string.Join("\n", failures));
        }

        /// <summary>
        /// An unreadable catalog must answer GroundLine, and a neighbour's rule must not leak.
        ///
        /// The fallback is deliberate -- an unclassified prop should import exactly as it does
        /// today -- but it is also what hid the real defect, so it is asserted rather than
        /// assumed. The importer now logs an error on that path; the VALUE stays safe.
        /// </summary>
        [Test]
        public void AnUnreadableCatalogFallsBackToTheGroundLine()
        {
            var cases = new Dictionary<string, string>
            {
                { "null text", null },
                { "empty text", string.Empty },
                { "not json", "{{{ this is not a catalog" },
                { "id absent", "{\"entries\":[{\"id\":\"something_else\","
                               + "\"pivot_rule\":\"lie_within\"}]}" },
            };

            foreach (var c in cases)
            {
                Assert.That(
                    DungeonPropImportPostprocessor.ClassifyFromCatalogText(
                        c.Value, "ca_sigil_floor_mark"),
                    Is.EqualTo(DungeonPropImportPostprocessor.PropPivotRule.GroundLine),
                    c.Key + " should fall back to the ground line");
            }

            // A later entry's rule must not be read as this one's.
            const string twoEntries =
                "{\"entries\":["
                + "{\"id\":\"standing_prop\",\"pivot_rule\":\"ground_line\"},"
                + "{\"id\":\"lying_prop\",\"pivot_rule\":\"lie_within\"}]}";
            Assert.That(
                DungeonPropImportPostprocessor.ClassifyFromCatalogText(twoEntries, "standing_prop"),
                Is.EqualTo(DungeonPropImportPostprocessor.PropPivotRule.GroundLine),
                "a later entry's lie_within was read as this entry's rule");
            Assert.That(
                DungeonPropImportPostprocessor.ClassifyFromCatalogText(twoEntries, "lying_prop"),
                Is.EqualTo(DungeonPropImportPostprocessor.PropPivotRule.LieWithin),
                "the scan failed to find a rule it should have found");
        }

        /// <summary>
        /// Reimport the catalog IN THE SAME BATCH as the props, and require the classification
        /// to survive it.
        ///
        /// THIS IS THE CONDITION THAT PRODUCED TWO FAILING RUNS ON A MERGE TRIAL, and the one a
        /// settled Library hides completely. A checkout leaves PropCatalog.json queued for
        /// reimport alongside the PNGs; the importer was reading the catalog through
        /// AssetDatabase, which cannot serve an asset that is itself mid-reimport, so the
        /// classification silently fell back to the ground line and the three lie-within props
        /// imported up to 0.648 world units wrong.
        ///
        /// That is what CI does and what every fresh clone does, so it is not a cold-start
        /// curiosity. Reading the catalog off disk has no such dependency.
        ///
        /// The plain suite CANNOT catch this: with a warm Library the catalog is already
        /// imported, AssetDatabase resolves, and the old code passes. Only forcing the catalog
        /// into the same import batch reproduces it.
        /// </summary>
        [Test]
        public void ClassificationSurvivesTheCatalogReimportingWithTheProps()
        {
            var paths = SelectedPngPaths();
            Assert.That(paths, Is.Not.Empty, "no selected prop PNGs; refusing to pass vacuously");

            string text;
            Assert.That(DungeonPropImportPostprocessor.TryReadCatalogText(out text), Is.True,
                "could not read " + CatalogPath + " off disk");
            var catalog = JsonUtility.FromJson<CatalogFile>(text);
            Assert.That(catalog, Is.Not.Null, "PropCatalog.json did not parse");

            var lying = catalog.entries.Where(e => e.pivot_rule == "lie_within").ToList();
            Assert.That(lying, Is.Not.Empty,
                "no entry is classified lie_within, so this test cannot exercise the branch it "
                + "exists to cover and would pass while proving nothing");

            // The catalog goes into the SAME batch as the props. That ordering is the hazard.
            try
            {
                AssetDatabase.StartAssetEditing();
                AssetDatabase.ImportAsset(CatalogPath, ImportAssetOptions.ForceUpdate);
                foreach (var path in paths)
                {
                    AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
                }
            }
            finally
            {
                AssetDatabase.StopAssetEditing();
            }

            AssetDatabase.Refresh();

            var failures = new List<string>();
            foreach (var entry in lying)
            {
                var path = entry.source_path_selected();
                if (string.IsNullOrEmpty(path))
                {
                    failures.Add(entry.id + ": no PNG on disk for a lie_within entry");
                    continue;
                }

                var importer = AssetImporter.GetAtPath(path) as TextureImporter;
                if (importer == null)
                {
                    failures.Add(entry.id + ": no TextureImporter after reimport");
                    continue;
                }

                var settings = new TextureImporterSettings();
                importer.ReadTextureSettings(settings);

                if (Mathf.Abs(settings.spritePivot.y - entry.pivot_normalized.y) > PivotTolerance)
                {
                    failures.Add(string.Format(
                        "{0}: classified lie_within and the catalog says {1}, but after "
                        + "reimporting with the catalog it imported at {2}. The classification "
                        + "was lost during the import, not miscomputed.",
                        entry.id, entry.pivot_normalized.y, settings.spritePivot.y));
                }
            }

            Assert.That(failures, Is.Empty, string.Join("\n", failures));
        }

        [Test]
        public void SelectedPropsExist()
        {
            var paths = SelectedPngPaths();
            Assert.That(paths, Is.Not.Empty,
                "No selected prop PNGs found under " + PropRoot +
                ". Every other test here would pass vacuously, so this one fails first.");
        }

        [Test]
        public void EverySelectedPropImportsWithTheContractSettings()
        {
            var paths = SelectedPngPaths();
            Assert.That(paths, Is.Not.Empty, "no selected prop PNGs; refusing to pass vacuously");

            var failures = new List<string>();

            foreach (var path in paths)
            {
                var importer = AssetImporter.GetAtPath(path) as TextureImporter;
                if (importer == null)
                {
                    // This is what a GUID-only stub .meta produces: no TextureImporter at all.
                    failures.Add(path + ": no TextureImporter (stub .meta, imports as the wrong type)");
                    continue;
                }

                Check(failures, path, "textureType", TextureImporterType.Sprite, importer.textureType);
                Check(failures, path, "spriteImportMode", SpriteImportMode.Single, importer.spriteImportMode);
                Check(failures, path, "spritePixelsPerUnit", 64f, importer.spritePixelsPerUnit);
                Check(failures, path, "filterMode", FilterMode.Point, importer.filterMode);
                Check(failures, path, "textureCompression",
                    TextureImporterCompression.Uncompressed, importer.textureCompression);
                Check(failures, path, "alphaIsTransparency", true, importer.alphaIsTransparency);
                Check(failures, path, "mipmapEnabled", false, importer.mipmapEnabled);
                Check(failures, path, "wrapMode", TextureWrapMode.Clamp, importer.wrapMode);
                Check(failures, path, "textureShape", TextureImporterShape.Texture2D, importer.textureShape);
            }

            Assert.That(failures, Is.Empty,
                paths.Length + " selected props checked; " + failures.Count + " setting failures:\n"
                + string.Join("\n", failures));
        }

        [Test]
        public void EverySelectedPropLoadsAsASprite()
        {
            var paths = SelectedPngPaths();
            Assert.That(paths, Is.Not.Empty, "no selected prop PNGs; refusing to pass vacuously");

            var failures = new List<string>();
            foreach (var path in paths)
            {
                var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
                if (sprite == null)
                {
                    failures.Add(path + ": does not load as a Sprite");
                }
            }

            Assert.That(failures, Is.Empty,
                "Loading through AssetDatabase is the only check a wrong .meta cannot satisfy:\n"
                + string.Join("\n", failures));
        }

        [Test]
        public void EveryPivotMatchesItsClassifiedRule()
        {
            var paths = SelectedPngPaths();
            Assert.That(paths, Is.Not.Empty, "no selected prop PNGs; refusing to pass vacuously");

            var failures = new List<string>();
            var floating = new List<string>();

            foreach (var path in paths)
            {
                var importer = AssetImporter.GetAtPath(path) as TextureImporter;
                if (importer == null)
                {
                    continue;
                }

                var settings = new TextureImporterSettings();
                importer.ReadTextureSettings(settings);

                Vector2 expected;
                if (!DungeonPropImportPostprocessor.TryMeasurePivot(path, out expected))
                {
                    failures.Add(path + ": could not measure a ground line (fully transparent?)");
                    continue;
                }

                if (Mathf.Abs(settings.spritePivot.y - expected.y) > PivotTolerance)
                {
                    failures.Add(string.Format(
                        "{0}: pivot y {1} but the drawn ground line is {2}",
                        path, settings.spritePivot.y, expected.y));
                }

                // The catalog rule of (0.5, 0) floats every one of these props, because they
                // all carry transparent rows below the art. Catch a regression to it.
                //
                // `expected` now comes from TryMeasurePivot, which honours the catalog's
                // pivot_rule, so a lie-within prop expects its centre and this guard still
                // means what it says: the pivot collapsed to the canvas bottom.
                if (expected.y > PivotTolerance && settings.spritePivot.y <= PivotTolerance)
                {
                    floating.Add(path);
                }
            }

            Assert.That(floating, Is.Empty,
                "These props are pinned to the canvas bottom rather than their own ground line, "
                + "which makes them hover above the floor:\n" + string.Join("\n", floating));
            Assert.That(failures, Is.Empty, string.Join("\n", failures));
        }

        [Test]
        public void CatalogPivotsMatchTheImportedPivots()
        {
            Assert.That(File.Exists(CatalogPath), Is.True, "missing " + CatalogPath);

            var catalog = JsonUtility.FromJson<CatalogFile>(File.ReadAllText(CatalogPath));
            Assert.That(catalog, Is.Not.Null, "PropCatalog.json did not parse");
            Assert.That(catalog.entries, Is.Not.Null.And.Not.Empty,
                "PropCatalog.json has no entries; refusing to pass vacuously");

            var failures = new List<string>();
            foreach (var entry in catalog.entries)
            {
                var importer = AssetImporter.GetAtPath(entry.source_path_selected()) as TextureImporter;
                if (importer == null)
                {
                    failures.Add(entry.id + ": catalog entry has no imported texture");
                    continue;
                }

                var settings = new TextureImporterSettings();
                importer.ReadTextureSettings(settings);

                if (Mathf.Abs(settings.spritePivot.y - entry.pivot_normalized.y) > PivotTolerance)
                {
                    failures.Add(string.Format("{0}: catalog pivot y {1}, imported {2}",
                        entry.id, entry.pivot_normalized.y, settings.spritePivot.y));
                }

                if (!Mathf.Approximately(importer.spritePixelsPerUnit, entry.pixels_per_unit))
                {
                    failures.Add(string.Format("{0}: catalog ppu {1}, imported {2}",
                        entry.id, entry.pixels_per_unit, importer.spritePixelsPerUnit));
                }
            }

            Assert.That(failures, Is.Empty,
                "PropCatalog.json is written by a different process from the importer, so a "
                + "disagreement here means one of them is wrong:\n" + string.Join("\n", failures));
        }

        private static void Check<T>(ICollection<string> failures, string path,
                                     string field, T expected, T actual)
        {
            if (!EqualityComparer<T>.Default.Equals(expected, actual))
            {
                failures.Add(string.Format("{0}: {1} expected {2} but was {3}",
                    path, field, expected, actual));
            }
        }

        [System.Serializable]
        private class CatalogFile
        {
            public List<CatalogEntry> entries;
        }

        [System.Serializable]
        private class CatalogEntry
        {
            public string id;
            public float pixels_per_unit;
            public Pivot pivot_normalized;
            public string pivot_rule;

            public string source_path_selected()
            {
                var matches = Directory.Exists(PropRoot)
                    ? Directory.GetFiles(PropRoot, id + ".png", SearchOption.AllDirectories)
                    : new string[0];
                return matches.Length == 1 ? matches[0].Replace('\\', '/') : string.Empty;
            }
        }

        [System.Serializable]
        private class Pivot
        {
            public float x;
            public float y;
        }
    }
}
