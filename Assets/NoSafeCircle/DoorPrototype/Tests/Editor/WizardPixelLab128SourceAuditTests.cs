using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>
    /// Read-only NSC-095 VAL-001 audit of selected 128 px source art and its raw PixelLab exports.
    /// </summary>
    public sealed class WizardPixelLab128SourceAuditTests
    {
        private const string SourceRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128";
        private const string RawRoot = "Docs/Art/Wizard/Raw128";
        private const string InventoryPath = SourceRoot + "/source-inventory.json";
        private const int CanvasSize = 128;
        private const int FramesPerWalk = 6;
        private const int ExpectedFrameCount = 224;

        private static readonly string[] Variants =
        {
            "masculine-light", "masculine-dark", "feminine-light", "feminine-dark"
        };

        private static readonly string[] Directions =
        {
            "north", "north-east", "east", "south-east",
            "south", "south-west", "west", "north-west"
        };

        [Test]
        public void SelectedFilesAndInventoryContainExactlyFourCompleteEightDirectionWizards()
        {
            SourceInventory inventory = LoadInventory();
            List<string> expectedPaths = ExpectedPaths();
            Assert.AreEqual(ExpectedFrameCount, expectedPaths.Count);
            Assert.AreEqual("NSC-095", inventory.task);
            Assert.AreEqual(ExpectedFrameCount, inventory.frames.Length);

            string[] actualPaths = Directory.GetFiles(SourceRoot, "*.png", SearchOption.AllDirectories)
                .Select(NormalizePath).ToArray();
            CollectionAssert.AreEquivalent(expectedPaths, actualPaths,
                "PixelLab128 must contain exactly the 8 standing and 48 walk PNGs for each wizard.");

            var recordedPaths = new HashSet<string>(StringComparer.Ordinal);
            foreach (FrameRecord frame in inventory.frames)
            {
                Assert.IsTrue(recordedPaths.Add(frame.selected_path),
                    "Duplicate inventory entry: " + frame.selected_path);
                Assert.IsTrue(Variants.Contains(frame.key), frame.selected_path);
                Assert.IsTrue(Directions.Contains(frame.direction), frame.selected_path);
                Assert.IsFalse(string.IsNullOrWhiteSpace(frame.character_id), frame.selected_path);
                Assert.IsFalse(string.IsNullOrWhiteSpace(frame.prompt), frame.selected_path);
                Assert.IsNotNull(frame.settings, frame.selected_path);
                Assert.AreEqual("v3", frame.settings.mode, frame.selected_path);
                Assert.AreEqual(CanvasSize, frame.settings.size, frame.selected_path);

                string expectedPath;
                if (frame.group == "standing")
                {
                    expectedPath = StandingPath(frame.key, frame.direction);
                }
                else
                {
                    Assert.AreEqual("walk", frame.group, frame.selected_path);
                    Assert.That(frame.frame_index, Is.InRange(0, FramesPerWalk - 1), frame.selected_path);
                    Assert.AreEqual(FramesPerWalk, frame.settings.frame_count, frame.selected_path);
                    Assert.IsFalse(frame.settings.keep_first_frame, frame.selected_path);
                    Assert.IsFalse(string.IsNullOrWhiteSpace(frame.animation_group_id), frame.selected_path);
                    expectedPath = WalkPath(frame.key, frame.direction, frame.frame_index);
                }

                Assert.AreEqual(expectedPath, frame.selected_path,
                    "The inventory index must name the matching ordered frame.");
                Assert.IsTrue(File.Exists(frame.selected_path + ".meta"), frame.selected_path);
                TextureImporter importer = AssetImporter.GetAtPath(frame.selected_path) as TextureImporter;
                Assert.IsNotNull(importer, frame.selected_path);
                Assert.AreEqual(TextureImporterShape.Texture2D, importer.textureShape, frame.selected_path);
            }

            CollectionAssert.AreEquivalent(expectedPaths, recordedPaths.ToArray());
        }

        [Test]
        public void SelectedFramesAreLosslessGroundAligned128PixelRgbaImages()
        {
            SourceInventory inventory = LoadInventory();
            foreach (FrameRecord frame in inventory.frames)
            {
                WizardRecord wizard = GetWizard(inventory, frame.key);
                DirectionRecord direction = GetDirection(wizard, frame.direction);
                int groundLine = wizard.ground_line_y_from_top;
                Assert.That(groundLine, Is.InRange(1, CanvasSize), frame.key);
                Assert.IsTrue(frame.raw_path.StartsWith(RawRoot + "/" + frame.key + "/",
                    StringComparison.Ordinal), frame.raw_path);
                Assert.IsTrue(File.Exists(frame.raw_path), frame.raw_path);
                Assert.IsFalse(File.Exists(frame.raw_path + ".meta"), frame.raw_path);
                Assert.IsTrue(File.Exists(frame.selected_path), frame.selected_path);

                byte[] rawBytes = File.ReadAllBytes(frame.raw_path);
                byte[] selectedBytes = File.ReadAllBytes(frame.selected_path);
                Assert.AreEqual(frame.raw_sha256, Sha256(rawBytes), frame.raw_path);
                Assert.AreEqual(frame.selected_sha256, Sha256(selectedBytes), frame.selected_path);
                AssertRgbaPng(selectedBytes, frame.selected_path);

                Texture2D raw = LoadTexture(rawBytes, frame.raw_path);
                Texture2D selected = LoadTexture(selectedBytes, frame.selected_path);
                try
                {
                    Assert.IsNotNull(frame.raw_size, frame.raw_path);
                    Assert.AreEqual(2, frame.raw_size.Length, frame.raw_path);
                    Assert.AreEqual(frame.raw_size[0], raw.width, frame.raw_path);
                    Assert.AreEqual(frame.raw_size[1], raw.height, frame.raw_path);
                    Assert.AreEqual(CanvasSize, selected.width, frame.selected_path);
                    Assert.AreEqual(CanvasSize, selected.height, frame.selected_path);
                    Assert.IsNotNull(frame.padding_offset, frame.selected_path);
                    Assert.AreEqual(2, frame.padding_offset.Length, frame.selected_path);

                    Color32[] rawPixels = raw.GetPixels32();
                    Color32[] selectedPixels = selected.GetPixels32();
                    AlphaBounds rawBounds = MeasureAlpha(rawPixels, raw.width, raw.height);
                    AlphaBounds selectedBounds = MeasureAlpha(selectedPixels, CanvasSize, CanvasSize);
                    Assert.Greater(rawBounds.VisiblePixels, 0, frame.raw_path);
                    Assert.IsNotNull(frame.raw_alpha_bbox, frame.raw_path);
                    CollectionAssert.AreEqual(rawBounds.ToArray(), frame.raw_alpha_bbox,
                        "Every source frame must record its measured raw alpha bounds: " + frame.raw_path);
                    Assert.AreEqual(rawBounds.VisiblePixels, selectedBounds.VisiblePixels,
                        "Lossless placement must preserve every visible pixel: " + frame.selected_path);
                    Assert.AreEqual(groundLine, frame.alpha_bottom_y_from_top, frame.selected_path);
                    Assert.AreEqual(groundLine, selectedBounds.BottomExclusive, frame.selected_path);
                    Assert.AreEqual(0, selectedPixels[0].a, frame.selected_path + " lower-left");
                    Assert.AreEqual(0, selectedPixels[CanvasSize - 1].a, frame.selected_path + " lower-right");
                    Assert.AreEqual(0, selectedPixels[(CanvasSize - 1) * CanvasSize].a,
                        frame.selected_path + " upper-left");
                    Assert.AreEqual(0, selectedPixels[selectedPixels.Length - 1].a,
                        frame.selected_path + " upper-right");

                    int offsetX = frame.padding_offset[0];
                    int offsetY;
                    if (frame.group == "standing")
                    {
                        Assert.AreEqual(0, offsetX, frame.selected_path);
                        Assert.AreEqual(0, frame.padding_offset[1], frame.selected_path);
                        Assert.AreEqual(groundLine - 1, direction.standing.deepest_row_after,
                            frame.selected_path);
                        Assert.AreEqual(rawBounds.BottomExclusive - 1,
                            direction.standing.reference_row, frame.selected_path);
                        offsetY = direction.standing.dy;
                    }
                    else
                    {
                        int centeredX = (CanvasSize - raw.width) / 2;
                        int centeredY = (CanvasSize - raw.height) / 2;
                        Assert.AreEqual(centeredX, offsetX, frame.selected_path);
                        Assert.AreEqual(centeredY + direction.walk.dy + frame.plant_dy,
                            frame.padding_offset[1], frame.selected_path);
                        offsetY = frame.padding_offset[1];
                    }

                    Assert.AreEqual(selectedBounds.BottomExclusive - rawBounds.BottomExclusive,
                        offsetY, "Recorded whole-pixel shift differs from the alpha bottoms: " +
                        frame.selected_path);
                    AssertVisiblePixelsTranslateExactly(rawPixels, raw.width, raw.height,
                        selectedPixels, offsetX, offsetY, frame.selected_path);
                }
                finally
                {
                    UnityEngine.Object.DestroyImmediate(raw);
                    UnityEngine.Object.DestroyImmediate(selected);
                }
            }
        }

        [Test]
        public void EachDirectionRecordsItsMedianGroundRowAndZeroFootDip()
        {
            SourceInventory inventory = LoadInventory();
            foreach (string variant in Variants)
            {
                WizardRecord wizard = GetWizard(inventory, variant);
                Assert.AreEqual(0, wizard.max_dip_below_ground_line, variant);
                foreach (string facing in Directions)
                {
                    DirectionRecord direction = GetDirection(wizard, facing);
                    Assert.IsNotNull(direction.standing, variant + "/" + facing);
                    Assert.IsNotNull(direction.walk, variant + "/" + facing);
                    Assert.AreEqual(0, direction.standing.dip_below_ground_line,
                        variant + "/" + facing + " standing");
                    Assert.AreEqual(0, direction.walk.dip_below_ground_line,
                        variant + "/" + facing + " walk");
                    Assert.AreEqual(wizard.ground_line_y_from_top - 1,
                        direction.standing.reference_row + direction.standing.dy,
                        variant + "/" + facing + " standing");
                    Assert.AreEqual(wizard.ground_line_y_from_top - 1,
                        direction.walk.deepest_row_after, variant + "/" + facing + " walk");
                    Assert.AreEqual(direction.walk.reference_row + direction.walk.dy,
                        direction.walk.deepest_row_after, variant + "/" + facing + " walk");

                    FrameRecord[] frames = inventory.frames
                        .Where(frame => frame.key == variant && frame.direction == facing &&
                            frame.group == "walk")
                        .OrderBy(frame => frame.frame_index).ToArray();
                    Assert.AreEqual(FramesPerWalk, frames.Length, variant + "/" + facing);
                    CollectionAssert.AreEqual(Enumerable.Range(0, FramesPerWalk).ToArray(),
                        frames.Select(frame => frame.frame_index).ToArray(), variant + "/" + facing);

                    var centeredRawBottomRows = new List<int>();
                    foreach (FrameRecord frame in frames)
                    {
                        Texture2D raw = LoadTexture(File.ReadAllBytes(frame.raw_path), frame.raw_path);
                        try
                        {
                            AlphaBounds bounds = MeasureAlpha(raw.GetPixels32(), raw.width, raw.height);
                            centeredRawBottomRows.Add(bounds.BottomExclusive - 1 +
                                (CanvasSize - raw.height) / 2);
                        }
                        finally
                        {
                            UnityEngine.Object.DestroyImmediate(raw);
                        }

                        Assert.AreEqual(wizard.ground_line_y_from_top,
                            frame.alpha_bottom_y_from_top, frame.selected_path);
                    }

                    centeredRawBottomRows.Sort();
                    Assert.AreEqual(centeredRawBottomRows[(FramesPerWalk - 1) / 2],
                        direction.walk.reference_row, variant + "/" + facing + " median row");
                }
            }
        }

        private static List<string> ExpectedPaths()
        {
            var paths = new List<string>();
            foreach (string variant in Variants)
            {
                foreach (string direction in Directions)
                {
                    paths.Add(StandingPath(variant, direction));
                    for (int frame = 0; frame < FramesPerWalk; frame++)
                        paths.Add(WalkPath(variant, direction, frame));
                }
            }

            return paths;
        }

        private static string StandingPath(string variant, string direction)
        {
            return SourceRoot + "/" + variant + "/selected/standing/" + direction + ".png";
        }

        private static string WalkPath(string variant, string direction, int frame)
        {
            return SourceRoot + "/" + variant + "/selected/walk/" + direction +
                "/frame_" + frame.ToString("000") + ".png";
        }

        private static SourceInventory LoadInventory()
        {
            Assert.IsTrue(File.Exists(InventoryPath), InventoryPath);
            // JsonUtility has no dictionary support. These replacements affect property names only;
            // frame values and source paths retain the committed PixelLab keys and directions.
            string json = File.ReadAllText(InventoryPath);
            foreach (string name in Variants.Concat(Directions))
                json = json.Replace("\"" + name + "\":", "\"" + name.Replace('-', '_') + "\":");
            SourceInventory inventory = JsonUtility.FromJson<SourceInventory>(json);
            Assert.IsNotNull(inventory, InventoryPath);
            Assert.IsNotNull(inventory.wizards, InventoryPath);
            Assert.IsNotNull(inventory.frames, InventoryPath);
            return inventory;
        }

        private static WizardRecord GetWizard(SourceInventory inventory, string variant)
        {
            WizardRecord wizard;
            switch (variant)
            {
                case "masculine-light": wizard = inventory.wizards.masculine_light; break;
                case "masculine-dark": wizard = inventory.wizards.masculine_dark; break;
                case "feminine-light": wizard = inventory.wizards.feminine_light; break;
                case "feminine-dark": wizard = inventory.wizards.feminine_dark; break;
                default: throw new ArgumentOutOfRangeException(nameof(variant));
            }

            Assert.IsNotNull(wizard, variant);
            Assert.IsNotNull(wizard.groups, variant);
            return wizard;
        }

        private static DirectionRecord GetDirection(WizardRecord wizard, string facing)
        {
            DirectionRecord direction;
            switch (facing)
            {
                case "north": direction = wizard.groups.north; break;
                case "north-east": direction = wizard.groups.north_east; break;
                case "east": direction = wizard.groups.east; break;
                case "south-east": direction = wizard.groups.south_east; break;
                case "south": direction = wizard.groups.south; break;
                case "south-west": direction = wizard.groups.south_west; break;
                case "west": direction = wizard.groups.west; break;
                case "north-west": direction = wizard.groups.north_west; break;
                default: throw new ArgumentOutOfRangeException(nameof(facing));
            }

            Assert.IsNotNull(direction, facing);
            return direction;
        }

        private static Texture2D LoadTexture(byte[] bytes, string path)
        {
            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            if (!texture.LoadImage(bytes))
            {
                UnityEngine.Object.DestroyImmediate(texture);
                Assert.Fail("Could not decode PNG: " + path);
            }

            return texture;
        }

        private static void AssertRgbaPng(byte[] bytes, string path)
        {
            Assert.GreaterOrEqual(bytes.Length, 26, path);
            byte[] signature = { 137, 80, 78, 71, 13, 10, 26, 10 };
            for (int index = 0; index < signature.Length; index++)
                Assert.AreEqual(signature[index], bytes[index], path);
            Assert.AreEqual(6, bytes[25], "PNG must have an RGBA color channel: " + path);
        }

        private static void AssertVisiblePixelsTranslateExactly(Color32[] raw, int rawWidth,
            int rawHeight, Color32[] selected, int offsetX, int offsetY, string path)
        {
            for (int y = 0; y < rawHeight; y++)
            {
                for (int x = 0; x < rawWidth; x++)
                {
                    Color32 pixel = raw[y * rawWidth + x];
                    if (pixel.a == 0) continue;
                    int selectedX = x + offsetX;
                    int selectedY = CanvasSize - rawHeight + y - offsetY;
                    Assert.That(selectedX, Is.InRange(0, CanvasSize - 1), path);
                    Assert.That(selectedY, Is.InRange(0, CanvasSize - 1), path);
                    Color32 placed = selected[selectedY * CanvasSize + selectedX];
                    Assert.AreEqual(pixel, placed, "Visible pixel changed during placement: " + path);
                }
            }
        }

        private static AlphaBounds MeasureAlpha(Color32[] pixels, int width, int height)
        {
            int minX = width;
            int minTop = height;
            int maxX = -1;
            int maxTop = -1;
            int visible = 0;
            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    if (pixels[y * width + x].a == 0) continue;
                    int top = height - 1 - y;
                    minX = Math.Min(minX, x);
                    minTop = Math.Min(minTop, top);
                    maxX = Math.Max(maxX, x);
                    maxTop = Math.Max(maxTop, top);
                    visible++;
                }
            }

            return new AlphaBounds(minX, minTop, maxX + 1, maxTop + 1, visible);
        }

        private static string NormalizePath(string path)
        {
            return path.Replace('\\', '/');
        }

        private static string Sha256(byte[] bytes)
        {
            using (SHA256 sha = SHA256.Create())
                return string.Concat(sha.ComputeHash(bytes).Select(value => value.ToString("x2")));
        }

        private readonly struct AlphaBounds
        {
            public readonly int BottomExclusive;
            public readonly int VisiblePixels;
            private readonly int left;
            private readonly int top;
            private readonly int rightExclusive;

            public AlphaBounds(int left, int top, int rightExclusive, int bottomExclusive,
                int visiblePixels)
            {
                this.left = left;
                this.top = top;
                this.rightExclusive = rightExclusive;
                BottomExclusive = bottomExclusive;
                VisiblePixels = visiblePixels;
            }

            public int[] ToArray()
            {
                return new[] { left, top, rightExclusive, BottomExclusive };
            }
        }

        // JsonUtility maps public fields by name. Hyphenated JSON object keys are normalized
        // in LoadInventory, while every recorded frame path and identity value stays intact.
        [Serializable]
        private sealed class SourceInventory
        {
            public string task;
            public WizardMap wizards;
            public FrameRecord[] frames;
        }

        [Serializable]
        private sealed class WizardMap
        {
            public WizardRecord masculine_light;
            public WizardRecord masculine_dark;
            public WizardRecord feminine_light;
            public WizardRecord feminine_dark;
        }

        [Serializable]
        private sealed class WizardRecord
        {
            public int ground_line_y_from_top;
            public int max_dip_below_ground_line;
            public DirectionMap groups;
        }

        [Serializable]
        private sealed class DirectionMap
        {
            public DirectionRecord north;
            public DirectionRecord north_east;
            public DirectionRecord east;
            public DirectionRecord south_east;
            public DirectionRecord south;
            public DirectionRecord south_west;
            public DirectionRecord west;
            public DirectionRecord north_west;
        }

        [Serializable]
        private sealed class DirectionRecord
        {
            public GroupMetrics standing;
            public GroupMetrics walk;
        }

        [Serializable]
        private sealed class GroupMetrics
        {
            public int reference_row;
            public int dy;
            public int deepest_row_after;
            public int dip_below_ground_line;
        }

        [Serializable]
        private sealed class FrameRecord
        {
            public string key;
            public string group;
            public string direction;
            public int frame_index;
            public string character_id;
            public string animation_group_id;
            public string prompt;
            public FrameSettings settings;
            public string selected_path;
            public string raw_path;
            public int[] raw_size;
            public int[] raw_alpha_bbox;
            public int[] padding_offset;
            public int plant_dy;
            public string raw_sha256;
            public string selected_sha256;
            public int alpha_bottom_y_from_top;
        }

        [Serializable]
        private sealed class FrameSettings
        {
            public string mode;
            public int size;
            public int frame_count;
            public bool keep_first_frame;
        }
    }
}
