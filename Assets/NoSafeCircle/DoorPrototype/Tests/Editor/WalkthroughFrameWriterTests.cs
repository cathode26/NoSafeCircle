using System;
using System.IO;
using NoSafeCircle.DoorPrototype.Diagnostics;
using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>
    /// Edit Mode coverage for the background frame writer. Regression-only invariants
    /// covering ownership of the writer's queue and task.
    /// </summary>
    /// <remarks>
    /// Every file these tests produce is written under the system temporary directory
    /// and removed in teardown, so a test run never adds tracked or untracked files to
    /// the repository.
    /// </remarks>
    public class WalkthroughFrameWriterTests
    {
        private const int Width = 4;
        private const int Height = 3;

        private string temporaryDirectory;

        [SetUp]
        public void SetUp()
        {
            temporaryDirectory = Path.Combine(
                Path.GetTempPath(),
                "nsc-walkthrough-writer",
                Guid.NewGuid().ToString("N"));

            Directory.CreateDirectory(temporaryDirectory);
        }

        [TearDown]
        public void TearDown()
        {
            if (temporaryDirectory != null && Directory.Exists(temporaryDirectory))
            {
                Directory.Delete(temporaryDirectory, true);
            }
        }

        private string PathFor(string name)
        {
            return Path.Combine(temporaryDirectory, name);
        }

        private static byte[] Gradient()
        {
            var pixels = new byte[Width * Height * WalkthroughFrameCheck.BytesPerPixel];

            for (int index = 0; index < pixels.Length; index++)
            {
                pixels[index] = (byte)(index * 7 % 256);
            }

            return pixels;
        }

        [Test]
        public void A_queued_frame_is_written_as_a_decodable_png_of_the_right_size()
        {
            string path = PathFor("Screenshot000001.png");

            using (var writer = new WalkthroughFrameWriter(4))
            {
                Assert.IsTrue(writer.TryEnqueue(Gradient(), Width, Height, path));
                Assert.AreEqual(0, writer.CompleteWriting(TimeSpan.FromSeconds(10d)),
                    "Draining must leave nothing queued.");
            }

            FileAssert.Exists(path);

            // Decoding it is the claim that matters: a file of the right length is not
            // evidence that an image was encoded into it.
            var decoded = new Texture2D(2, 2);

            try
            {
                Assert.IsTrue(ImageConversion.LoadImage(decoded, File.ReadAllBytes(path)),
                    "The written bytes did not decode as an image.");
                Assert.AreEqual(Width, decoded.width);
                Assert.AreEqual(Height, decoded.height);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(decoded);
            }
        }

        [Test]
        public void Every_accepted_frame_reaches_disk_before_draining_returns()
        {
            const int frames = 6;

            using (var writer = new WalkthroughFrameWriter(frames))
            {
                for (int index = 1; index <= frames; index++)
                {
                    Assert.IsTrue(writer.TryEnqueue(Gradient(), Width, Height, PathFor(index + ".png")));
                }

                Assert.AreEqual(0, writer.CompleteWriting(TimeSpan.FromSeconds(20d)));
            }

            for (int index = 1; index <= frames; index++)
            {
                FileAssert.Exists(PathFor(index + ".png"));
            }
        }

        [Test]
        public void Back_pressure_refuses_frames_beyond_the_cap_and_counts_them()
        {
            // A writer with room for one frame and nothing draining it: the queue is
            // bounded, so the second frame must be refused rather than accumulate.
            using (var writer = new WalkthroughFrameWriter(1))
            {
                int accepted = 0;
                int refused = 0;

                for (int index = 0; index < 200; index++)
                {
                    if (writer.TryEnqueue(Gradient(), Width, Height, PathFor(index + ".png")))
                    {
                        accepted++;
                    }
                    else
                    {
                        refused++;
                    }
                }

                Assert.Greater(refused, 0, "A bounded queue must refuse something under this load.");
                Assert.AreEqual(refused, writer.DroppedCount, "Every refusal must be counted.");
                Assert.AreEqual(200, accepted + refused);

                writer.CompleteWriting(TimeSpan.FromSeconds(20d));
            }
        }

        [Test]
        public void A_writer_with_no_room_is_rejected_at_construction()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => new WalkthroughFrameWriter(0));
        }

        [Test]
        public void A_frame_without_a_destination_is_rejected()
        {
            using (var writer = new WalkthroughFrameWriter(2))
            {
                Assert.Throws<ArgumentNullException>(
                    () => writer.TryEnqueue(null, Width, Height, PathFor("a.png")));
                Assert.Throws<ArgumentException>(
                    () => writer.TryEnqueue(Gradient(), Width, Height, string.Empty));
            }
        }

        [Test]
        public void Enqueuing_after_the_session_stopped_is_refused_loudly()
        {
            // Silently accepting a frame that will never be written would put an entry
            // in the manifest for a PNG that does not exist.
            var writer = new WalkthroughFrameWriter(2);
            writer.CompleteWriting(TimeSpan.FromSeconds(10d));

            Assert.Throws<InvalidOperationException>(
                () => writer.TryEnqueue(Gradient(), Width, Height, PathFor("late.png")));

            writer.Dispose();
        }

        [Test]
        public void Disposing_twice_is_safe()
        {
            var writer = new WalkthroughFrameWriter(2);
            writer.Dispose();
            Assert.DoesNotThrow(writer.Dispose);
        }
    }
}
