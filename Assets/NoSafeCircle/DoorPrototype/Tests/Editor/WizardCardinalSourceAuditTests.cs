using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using NUnit.Framework;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public sealed class WizardCardinalSourceAuditTests
    {
        private const string SourceRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab";
        private const string InventoryPath = SourceRoot + "/source-inventory.json";
        private const int FrameCount = 6;
        private const int ExpectedCardinalPngCount = 96;
        private const int ExpectedPreservedPngCount = 128;

        private static readonly string[] Variants =
        {
            "masculine-dark", "feminine-dark", "masculine-light", "feminine-light"
        };

        private static readonly string[] Directions = { "north", "east", "south", "west" };

        [Test]
        public void CardinalSourceSet_HasExactlyFourVariantsFourDirectionsAndSixOrderedFrames()
        {
            string root = RepositoryRoot();
            List<string> expected = ExpectedCardinalPaths();
            List<string> actual = Directory
                .EnumerateFiles(Path.Combine(root, SourceRoot.Replace('/', Path.DirectorySeparatorChar)), "*.png", SearchOption.AllDirectories)
                .Select(path => RelativePath(root, path))
                .Where(path => path.Contains("/selected/walk/"))
                .Where(path => IsCardinalPath(path))
                .OrderBy(path => path, StringComparer.Ordinal)
                .ToList();

            Assert.AreEqual(ExpectedCardinalPngCount, actual.Count,
                "NSC-074 requires exactly 96 cardinal PNGs (four variants x four directions x six frames); found " + actual.Count + ".");
            CollectionAssert.AreEquivalent(expected, actual,
                "The cardinal source paths must use the exact variant/direction/frame naming contract.");

            List<string> actualMetas = Directory
                .EnumerateFiles(Path.Combine(root, SourceRoot.Replace('/', Path.DirectorySeparatorChar)), "*.png.meta", SearchOption.AllDirectories)
                .Select(path => RelativePath(root, path.Substring(0, path.Length - ".meta".Length)))
                .Where(path => IsCardinalPath(path))
                .OrderBy(path => path, StringComparer.Ordinal)
                .ToList();
            Assert.AreEqual(ExpectedCardinalPngCount, actualMetas.Count,
                "NSC-074 requires exactly 96 cardinal PNG .meta companions; found " + actualMetas.Count + ".");
            CollectionAssert.AreEquivalent(expected, actualMetas,
                "Every cardinal PNG must have exactly one matching .meta companion.");

            foreach (string path in expected)
            {
                string file = Path.Combine(root, path.Replace('/', Path.DirectorySeparatorChar));
                Assert.That(File.Exists(file), Is.True, "Required cardinal PNG is missing: " + path);
                Assert.That(File.Exists(file + ".meta"), Is.True, "Required deterministic .meta is missing: " + path + ".meta");
                Assert.AreEqual(ExpectedMeta(path), File.ReadAllText(file + ".meta", Encoding.UTF8),
                    "The .meta companion is not the deterministic companion for: " + path);
            }

            foreach (string cycle in expected.Select(path => path.Substring(0, path.LastIndexOf('/'))).Distinct())
            {
                List<string> frames = expected.Where(path => path.StartsWith(cycle + "/", StringComparison.Ordinal))
                    .OrderBy(path => path, StringComparer.Ordinal).ToList();
                CollectionAssert.AreEqual(Enumerable.Range(0, FrameCount)
                    .Select(frame => cycle + "/frame_" + frame.ToString("D3") + ".png").ToList(), frames,
                    "Frames must be ordered frame_000 through frame_005 for cycle: " + cycle);
                Assert.AreEqual(FrameCount, frames.Select(path => Sha256(Path.Combine(root, path.Replace('/', Path.DirectorySeparatorChar)))).Distinct().Count(),
                    "Every frame in a cardinal cycle must have distinct bytes: " + cycle);
            }
        }

        [Test]
        public void CardinalSourceSet_ContainsTransparentEightBitRgba180By180Pngs()
        {
            string root = RepositoryRoot();
            foreach (string path in ExpectedCardinalPaths())
            {
                string file = Path.Combine(root, path.Replace('/', Path.DirectorySeparatorChar));
                Assert.That(File.Exists(file), Is.True, "Cannot inspect missing cardinal PNG: " + path);
                PngInfo png = ReadPng(file);
                Assert.AreEqual(180, png.Width, "Cardinal PNG width must be 180: " + path);
                Assert.AreEqual(180, png.Height, "Cardinal PNG height must be 180: " + path);
                Assert.AreEqual(8, png.BitDepth, "Cardinal PNG must use 8-bit channels: " + path);
                Assert.AreEqual(6, png.ColorType, "Cardinal PNG must be RGBA: " + path);
                Assert.IsTrue(png.HasTransparentPixel, "Cardinal PNG must contain transparent pixels: " + path);
            }
        }

        [Test]
        public void ExistingSelectedPixelLabPng_ExercisesPngDecoder()
        {
            const string path = SourceRoot + "/masculine-dark/selected/standing/east.png";
            PngInfo png = ReadPng(Path.Combine(RepositoryRoot(), path.Replace('/', Path.DirectorySeparatorChar)));
            Assert.AreEqual(180, png.Width, "The inventoried decoder fixture must be 180 pixels wide: " + path);
            Assert.AreEqual(180, png.Height, "The inventoried decoder fixture must be 180 pixels high: " + path);
            Assert.AreEqual(8, png.BitDepth, "The inventoried decoder fixture must use 8-bit channels: " + path);
            Assert.AreEqual(6, png.ColorType, "The inventoried decoder fixture must be RGBA: " + path);
            Assert.IsTrue(png.HasTransparentPixel, "The inventoried decoder fixture must contain transparent pixels: " + path);
        }

        [Test]
        public void ExistingSelectedWizardArt_IsPreservedFromSourceInventory()
        {
            string root = RepositoryRoot();
            string inventory = File.ReadAllText(Path.Combine(root, InventoryPath.Replace('/', Path.DirectorySeparatorChar)));
            MatchCollection records = Regex.Matches(inventory,
                @"""path""\s*:\s*""(?<path>[^""]+\.png)""\s*,\s*""size_bytes""\s*:\s*\d+\s*,\s*""sha256""\s*:\s*""(?<sha>[0-9a-f]{64})""",
                RegexOptions.IgnoreCase);
            Assert.AreEqual(ExpectedPreservedPngCount, records.Count,
                "The pre-existing source inventory must retain all 128 approved PNG records.");

            foreach (Match record in records)
            {
                string path = SourceRoot + "/" + record.Groups["path"].Value;
                Assert.IsFalse(IsCardinalPath(path), "A pre-existing inventory record must not claim a new cardinal path: " + path);
                string file = Path.Combine(root, path.Replace('/', Path.DirectorySeparatorChar));
                Assert.That(File.Exists(file), Is.True, "Pre-existing selected art is missing: " + path);
                Assert.AreEqual(record.Groups["sha"].Value, Sha256(file),
                    "Pre-existing selected art changed from its inventory hash: " + path);
            }
        }

        private static List<string> ExpectedCardinalPaths()
        {
            return (from variant in Variants
                    from direction in Directions
                    from frame in Enumerable.Range(0, FrameCount)
                    select SourceRoot + "/" + variant + "/selected/walk/" + direction + "/frame_" + frame.ToString("D3") + ".png")
                .ToList();
        }

        private static bool IsCardinalPath(string path)
        {
            return ExpectedCardinalPaths().Any(expected => string.Equals(expected, path, StringComparison.Ordinal));
        }

        private static string RepositoryRoot()
        {
            DirectoryInfo directory = new DirectoryInfo(Directory.GetCurrentDirectory());
            while (directory != null)
            {
                if (File.Exists(Path.Combine(directory.FullName, InventoryPath.Replace('/', Path.DirectorySeparatorChar))))
                    return directory.FullName;
                directory = directory.Parent;
            }
            throw new AssertionException("Could not locate the repository root containing " + InventoryPath + ".");
        }

        private static string RelativePath(string root, string path)
        {
            return path.Substring(root.Length + 1).Replace(Path.DirectorySeparatorChar, '/');
        }

        private static string Sha256(string path)
        {
            using (SHA256 sha = SHA256.Create())
            using (FileStream stream = File.OpenRead(path))
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }

        private static string ExpectedMeta(string path)
        {
            string normalized = string.Join("/", path.Split('/').Select(part => part.ToLowerInvariant()).ToArray());
            byte[] prefix = Encoding.UTF8.GetBytes("NoSafeCircle.ExecutionCrew.UnityMeta/v1\0" + normalized);
            string guid;
            using (SHA256 sha = SHA256.Create())
                guid = BitConverter.ToString(sha.ComputeHash(prefix)).Replace("-", "").ToLowerInvariant().Substring(0, 32);
            return "fileFormatVersion: 2\nguid: " + guid + "\n";
        }

        private sealed class PngInfo
        {
            public int Width;
            public int Height;
            public int BitDepth;
            public int ColorType;
            public bool HasTransparentPixel;
        }

        private static PngInfo ReadPng(string path)
        {
            byte[] bytes = File.ReadAllBytes(path);
            byte[] signature = { 137, 80, 78, 71, 13, 10, 26, 10 };
            Assert.IsTrue(bytes.Take(8).SequenceEqual(signature), "Invalid PNG signature: " + path);
            int offset = 8;
            List<byte> compressed = new List<byte>();
            PngInfo info = new PngInfo();
            while (offset + 12 <= bytes.Length)
            {
                int length = ReadInt32(bytes, offset);
                string type = Encoding.ASCII.GetString(bytes, offset + 4, 4);
                Assert.That(length, Is.GreaterThanOrEqualTo(0), "Invalid PNG chunk length: " + path);
                Assert.That(offset + 12 + length, Is.LessThanOrEqualTo(bytes.Length), "Truncated PNG chunk: " + path);
                if (type == "IHDR")
                {
                    info.Width = ReadInt32(bytes, offset + 8);
                    info.Height = ReadInt32(bytes, offset + 12);
                    info.BitDepth = bytes[offset + 16];
                    info.ColorType = bytes[offset + 17];
                    Assert.AreEqual(0, bytes[offset + 24], "Interlaced PNGs are not deterministic audit inputs: " + path);
                }
                else if (type == "IDAT")
                    compressed.AddRange(bytes.Skip(offset + 8).Take(length));
                offset += length + 12;
                if (type == "IEND")
                    break;
            }
            Assert.AreEqual(180, info.Width, "PNG must declare a 180 pixel width before decoding: " + path);
            Assert.AreEqual(180, info.Height, "PNG must declare a 180 pixel height before decoding: " + path);
            Assert.AreEqual(8, info.BitDepth, "PNG must declare 8-bit channels before decoding: " + path);
            Assert.AreEqual(6, info.ColorType, "PNG must declare RGBA before decoding: " + path);
            byte[] raw;
            using (MemoryStream input = new MemoryStream(compressed.ToArray()))
            using (DeflateStream deflate = new DeflateStream(input, CompressionMode.Decompress))
            using (MemoryStream output = new MemoryStream())
            {
                deflate.CopyTo(output);
                raw = output.ToArray();
            }
            int stride = info.Width * 4;
            Assert.AreEqual(info.Height * (stride + 1), raw.Length, "RGBA scanline data is not 180x180: " + path);
            byte[] previous = new byte[stride];
            byte[] current = new byte[stride];
            for (int y = 0; y < info.Height; y++)
            {
                int filter = raw[y * (stride + 1)];
                Assert.That(filter, Is.InRange(0, 4), "Unsupported PNG filter byte " + filter + ": " + path);
                for (int x = 0; x < stride; x++)
                {
                    int left = x >= 4 ? current[x - 4] : 0;
                    int up = previous[x];
                    int upperLeft = x >= 4 ? previous[x - 4] : 0;
                    int value = raw[y * (stride + 1) + x + 1];
                    current[x] = (byte)(value + (filter == 0 ? 0 : filter == 1 ? left : filter == 2 ? up : filter == 3 ? (left + up) / 2 : Paeth(left, up, upperLeft)));
                }
                for (int x = 3; x < stride; x += 4)
                    info.HasTransparentPixel |= current[x] < 255;
                byte[] swap = previous;
                previous = current;
                current = swap;
            }
            return info;
        }

        private static int ReadInt32(byte[] bytes, int offset)
        {
            return (bytes[offset] << 24) | (bytes[offset + 1] << 16) | (bytes[offset + 2] << 8) | bytes[offset + 3];
        }

        private static int Paeth(int a, int b, int c)
        {
            int p = a + b - c;
            int pa = Math.Abs(p - a), pb = Math.Abs(p - b), pc = Math.Abs(p - c);
            return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
        }
    }
}
