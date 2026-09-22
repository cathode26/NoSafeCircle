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
        public void EveryPivotSitsOnTheDrawnGroundLine()
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
                if (!DungeonPropImportPostprocessor.TryMeasureGroundPivot(path, out expected))
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
