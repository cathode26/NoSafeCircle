using System;
using NoSafeCircle.DoorPrototype.Diagnostics;
using NUnit.Framework;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>
    /// Edit Mode coverage for the check that decides whether a captured frame shows
    /// anything. Regression-only invariants: this proves the detector itself, while
    /// <c>WalkthroughCapturePlayModeTests</c> proves the capture path it guards.
    /// </summary>
    public class WalkthroughFrameCheckTests
    {
        private const int Width = 8;
        private const int Height = 4;
        private const int PixelCount = Width * Height;

        private static byte[] FilledFrame(byte red, byte green, byte blue)
        {
            var pixels = new byte[PixelCount * WalkthroughFrameCheck.BytesPerPixel];

            for (int pixel = 0; pixel < PixelCount; pixel++)
            {
                int offset = pixel * WalkthroughFrameCheck.BytesPerPixel;
                pixels[offset] = red;
                pixels[offset + 1] = green;
                pixels[offset + 2] = blue;
            }

            return pixels;
        }

        [Test]
        public void A_frame_of_one_colour_is_uniform()
        {
            Assert.IsTrue(WalkthroughFrameCheck.IsUniform(FilledFrame(40, 40, 40), Width, Height));
        }

        [Test]
        public void A_black_frame_is_uniform()
        {
            // The exact shape produced when a capture path resolves no source at all.
            Assert.IsTrue(WalkthroughFrameCheck.IsUniform(FilledFrame(0, 0, 0), Width, Height));
        }

        [Test]
        public void A_single_differing_pixel_in_the_last_position_is_not_uniform()
        {
            // The last pixel specifically: an off-by-one loop bound passes every other
            // case in this fixture and fails only here.
            byte[] pixels = FilledFrame(10, 10, 10);
            int lastOffset = (PixelCount - 1) * WalkthroughFrameCheck.BytesPerPixel;
            pixels[lastOffset] = 200;

            Assert.IsFalse(WalkthroughFrameCheck.IsUniform(pixels, Width, Height));
        }

        [Test]
        public void A_difference_in_any_single_channel_is_detected()
        {
            // One case per channel, because a check that forgets one channel still
            // passes a test that only ever varies red.
            for (int channel = 0; channel < WalkthroughFrameCheck.BytesPerPixel; channel++)
            {
                byte[] pixels = FilledFrame(10, 10, 10);
                pixels[WalkthroughFrameCheck.BytesPerPixel + channel] = 250;

                Assert.IsFalse(
                    WalkthroughFrameCheck.IsUniform(pixels, Width, Height),
                    "Channel " + channel + " difference was not detected.");
            }
        }

        [Test]
        public void A_difference_within_tolerance_is_still_uniform()
        {
            byte[] pixels = FilledFrame(10, 10, 10);
            pixels[WalkthroughFrameCheck.BytesPerPixel] = (byte)(10 + WalkthroughFrameCheck.DefaultTolerance);

            Assert.IsTrue(WalkthroughFrameCheck.IsUniform(pixels, Width, Height));
        }

        [Test]
        public void A_difference_just_beyond_tolerance_is_not_uniform()
        {
            byte[] pixels = FilledFrame(10, 10, 10);
            pixels[WalkthroughFrameCheck.BytesPerPixel] = (byte)(10 + WalkthroughFrameCheck.DefaultTolerance + 1);

            Assert.IsFalse(WalkthroughFrameCheck.IsUniform(pixels, Width, Height));
        }

        [Test]
        public void Tolerance_is_symmetric_around_the_reference_pixel()
        {
            // Darker as well as brighter: an unsigned subtraction that never goes
            // negative would pass the brighter case and silently fail this one.
            byte[] pixels = FilledFrame(200, 200, 200);
            pixels[WalkthroughFrameCheck.BytesPerPixel] = 100;

            Assert.IsFalse(WalkthroughFrameCheck.IsUniform(pixels, Width, Height));
        }

        [Test]
        public void A_null_buffer_is_rejected()
        {
            Assert.Throws<ArgumentNullException>(
                () => WalkthroughFrameCheck.IsUniform(null, Width, Height));
        }

        [Test]
        public void Non_positive_dimensions_are_rejected()
        {
            byte[] pixels = FilledFrame(0, 0, 0);

            Assert.Throws<ArgumentOutOfRangeException>(
                () => WalkthroughFrameCheck.IsUniform(pixels, 0, Height));
            Assert.Throws<ArgumentOutOfRangeException>(
                () => WalkthroughFrameCheck.IsUniform(pixels, Width, -1));
        }

        [Test]
        public void A_buffer_too_small_for_its_dimensions_is_rejected()
        {
            // Reporting "uniform" for a truncated buffer would be the same silent
            // false negative the whole check exists to prevent.
            var truncated = new byte[(PixelCount - 1) * WalkthroughFrameCheck.BytesPerPixel];

            Assert.Throws<ArgumentException>(
                () => WalkthroughFrameCheck.IsUniform(truncated, Width, Height));
        }
    }
}
