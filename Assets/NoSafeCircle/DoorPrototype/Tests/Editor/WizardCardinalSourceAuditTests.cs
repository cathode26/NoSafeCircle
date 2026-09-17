using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>
    /// Read-only NSC-074 audit of the PixelLab cardinal wizard walk source PNGs.
    /// It reads files and AssetDatabase identities only; it never imports, saves, or rewrites assets.
    /// </summary>
    public sealed class WizardCardinalSourceAuditTests
    {
        private const string SourceRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab";
        private const string InventoryPath = SourceRoot + "/source-inventory.json";
        private const int ExpectedCardinalFileCount = 96;
        private const int FramesPerDirection = 6;
        private const int CanvasSize = 180;

        private static readonly string[] Variants =
        {
            "feminine-light",
            "feminine-dark",
            "masculine-light",
            "masculine-dark"
        };

        private static readonly string[] CardinalDirections =
        {
            "north",
            "east",
            "south",
            "west"
        };

        private static readonly Regex GuidLine = new Regex(@"^guid: ([0-9a-f]{32})\s*$", RegexOptions.Multiline);

        [Test]
        public void CardinalWalkFoldersContainExactlySixOrderedFramesEach()
        {
            List<string> expected = ExpectedCardinalPaths();
            Assert.AreEqual(ExpectedCardinalFileCount, expected.Count);

            foreach (string variant in Variants)
            {
                foreach (string direction in CardinalDirections)
                {
                    string folder = WalkFolder(variant, direction);
                    Assert.IsTrue(Directory.Exists(folder), folder);
                    Assert.IsTrue(File.Exists(folder + ".meta"), "Missing folder .meta: " + folder);

                    string[] pngNames = Directory.GetFiles(folder, "*.png")
                        .Select(Path.GetFileName)
                        .OrderBy(name => name, StringComparer.Ordinal)
                        .ToArray();
                    string[] expectedNames = Enumerable.Range(0, FramesPerDirection)
                        .Select(FrameFileName)
                        .ToArray();
                    CollectionAssert.AreEqual(expectedNames, pngNames, folder);

                    string[] unexpected = Directory.GetFiles(folder)
                        .Select(Path.GetFileName)
                        .Where(name => !expectedNames.Contains(name) && !expectedNames.Contains(name.Replace(".meta", string.Empty)))
                        .ToArray();
                    CollectionAssert.IsEmpty(unexpected, folder);
                }
            }
        }

        [Test]
        public void CardinalWalkPngsAreTransparent180By180Images()
        {
            foreach (string path in ExpectedCardinalPaths())
            {
                var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                try
                {
                    Assert.IsTrue(texture.LoadImage(File.ReadAllBytes(path)), path);
                    Assert.AreEqual(CanvasSize, texture.width, path);
                    Assert.AreEqual(CanvasSize, texture.height, path);

                    Color32[] pixels = texture.GetPixels32();
                    Assert.IsTrue(pixels.Any(pixel => pixel.a == 0), "No transparent pixels: " + path);
                    Assert.IsTrue(pixels.Any(pixel => pixel.a == 255), "No opaque character pixels: " + path);
                }
                finally
                {
                    UnityEngine.Object.DestroyImmediate(texture);
                }
            }
        }

        [Test]
        public void CardinalWalkMetaFilesUseInventoryGuidsAndSpriteImport()
        {
            SourceInventory inventory = LoadInventory();
            Dictionary<string, CardinalFile> recorded = CardinalFilesByPath(inventory);
            var guids = new HashSet<string>();

            foreach (string path in ExpectedCardinalPaths())
            {
                string metaPath = path + ".meta";
                Assert.IsTrue(File.Exists(metaPath), "Missing .meta: " + metaPath);
                string metaText = File.ReadAllText(metaPath);
                Match guidMatch = GuidLine.Match(metaText);
                Assert.IsTrue(guidMatch.Success, "No guid line: " + metaPath);

                string guid = guidMatch.Groups[1].Value;
                Assert.IsTrue(guids.Add(guid), "Duplicate cardinal guid: " + metaPath);
                Assert.AreEqual(DeterministicMetaGuid(path), guid, "Non-deterministic guid: " + metaPath);
                Assert.AreEqual(recorded[path].meta_guid, guid, metaPath);
                Assert.AreEqual(guid, AssetDatabase.AssetPathToGUID(path), "AssetDatabase guid differs: " + path);
            }

            string[] otherWizardMetas = Directory.GetFiles(SourceRoot, "*.meta", SearchOption.AllDirectories)
                .Select(NormalizePath)
                .Where(metaPath => !recorded.ContainsKey(metaPath.Substring(0, metaPath.Length - ".meta".Length)))
                .ToArray();
            foreach (string metaPath in otherWizardMetas)
            {
                Match guidMatch = GuidLine.Match(File.ReadAllText(metaPath));
                if (guidMatch.Success)
                    Assert.IsFalse(guids.Contains(guidMatch.Groups[1].Value), "Cardinal guid collides with " + metaPath);
            }
        }

        [Test]
        public void InventoryRecordsExactlyTheCardinalFilesOnDisk()
        {
            SourceInventory inventory = LoadInventory();
            Assert.IsNotNull(inventory.cardinal_walk_extension, "Missing cardinal_walk_extension in " + InventoryPath);
            Assert.AreEqual("NSC-074", inventory.cardinal_walk_extension.task_id);

            Dictionary<string, CardinalFile> recorded = CardinalFilesByPath(inventory);
            List<string> expected = ExpectedCardinalPaths();
            CollectionAssert.AreEquivalent(expected, recorded.Keys.ToList());

            foreach (string path in expected)
            {
                CardinalFile file = recorded[path];
                byte[] bytes = File.ReadAllBytes(path);
                Assert.AreEqual(file.size_bytes, bytes.Length, path);
                Assert.AreEqual(file.sha256, Sha256(bytes), path);
                Assert.AreEqual(CanvasSize, file.width, path);
                Assert.AreEqual(CanvasSize, file.height, path);
            }
        }

        [Test]
        public void PreExistingStandingAndDiagonalArtIsPreservedAndUnclaimed()
        {
            SourceInventory inventory = LoadInventory();
            HashSet<string> cardinalPaths = new HashSet<string>(ExpectedCardinalPaths());
            int preExistingCount = 0;

            foreach (SourceEntry source in inventory.sources)
            {
                foreach (AuthorizedFile file in source.authorized_files)
                {
                    string path = SourceRoot + "/" + file.path;
                    Assert.IsFalse(cardinalPaths.Contains(path), "Pre-existing inventory already claims cardinal path: " + path);
                    Assert.IsTrue(File.Exists(path), "Pre-existing art missing: " + path);
                    Assert.AreEqual(file.sha256, Sha256(File.ReadAllBytes(path)), "Pre-existing art changed: " + path);
                    preExistingCount++;
                }
            }

            Assert.AreEqual(128, preExistingCount, "Standing plus diagonal walk inventory count changed.");
        }

        private static List<string> ExpectedCardinalPaths()
        {
            var paths = new List<string>();
            foreach (string variant in Variants)
            {
                foreach (string direction in CardinalDirections)
                {
                    for (int frame = 0; frame < FramesPerDirection; frame++)
                        paths.Add(WalkFolder(variant, direction) + "/" + FrameFileName(frame));
                }
            }

            return paths;
        }

        private static string WalkFolder(string variant, string direction)
        {
            return SourceRoot + "/" + variant + "/selected/walk/" + direction;
        }

        private static string FrameFileName(int frame)
        {
            return "frame_" + frame.ToString("000") + ".png";
        }

        private static SourceInventory LoadInventory()
        {
            Assert.IsTrue(File.Exists(InventoryPath), InventoryPath);
            SourceInventory inventory = JsonUtility.FromJson<SourceInventory>(File.ReadAllText(InventoryPath));
            Assert.IsNotNull(inventory, InventoryPath);
            Assert.IsNotNull(inventory.sources, InventoryPath);
            return inventory;
        }

        private static Dictionary<string, CardinalFile> CardinalFilesByPath(SourceInventory inventory)
        {
            Assert.IsNotNull(inventory.cardinal_walk_extension, "Missing cardinal_walk_extension in " + InventoryPath);
            var files = new Dictionary<string, CardinalFile>();
            foreach (CardinalSource source in inventory.cardinal_walk_extension.sources)
            {
                foreach (CardinalFile file in source.files)
                {
                    string path = SourceRoot + "/" + file.path;
                    Assert.IsFalse(files.ContainsKey(path), "Duplicate cardinal inventory path: " + path);
                    files.Add(path, file);
                }
            }

            return files;
        }

        private static string NormalizePath(string path)
        {
            return path.Replace('\\', '/');
        }

        private static string Sha256(byte[] bytes)
        {
            using (SHA256 sha = SHA256.Create())
            {
                return string.Concat(sha.ComputeHash(bytes).Select(value => value.ToString("x2")));
            }
        }

        // Mirrors Pipeline/ExecutionCrew/run_crew.py unity_meta_bytes so sidecar GUIDs stay reproducible.
        private static string DeterministicMetaGuid(string assetPath)
        {
            string normalized = string.Join("/", assetPath.Split('/').Select(part => part.ToLowerInvariant()));
            byte[] prefix = Encoding.UTF8.GetBytes("NoSafeCircle.ExecutionCrew.UnityMeta/v1\0");
            byte[] pathBytes = Encoding.UTF8.GetBytes(normalized);
            return Sha256(prefix.Concat(pathBytes).ToArray()).Substring(0, 32);
        }

        // Field names mirror the snake_case JSON keys because JsonUtility maps fields by exact name.
        [Serializable]
        private sealed class SourceInventory
        {
            public SourceEntry[] sources;
            public CardinalWalkExtension cardinal_walk_extension;
        }

        [Serializable]
        private sealed class SourceEntry
        {
            public string source_key;
            public AuthorizedFile[] authorized_files;
        }

        [Serializable]
        private sealed class AuthorizedFile
        {
            public string path;
            public string sha256;
        }

        [Serializable]
        private sealed class CardinalWalkExtension
        {
            public string task_id;
            public CardinalSource[] sources;
        }

        [Serializable]
        private sealed class CardinalSource
        {
            public string source_key;
            public CardinalFile[] files;
        }

        [Serializable]
        private sealed class CardinalFile
        {
            public string path;
            public string direction;
            public int frame;
            public int width;
            public int height;
            public int size_bytes;
            public string sha256;
            public string meta_guid;
        }
    }
}
