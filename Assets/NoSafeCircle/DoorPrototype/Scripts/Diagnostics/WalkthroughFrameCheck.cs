using System;

namespace NoSafeCircle.DoorPrototype.Diagnostics
{
    /// <summary>
    /// Decides whether a captured frame carries an image at all.
    /// </summary>
    /// <remarks>
    /// This exists because the failure it detects is silent and convincing. A capture
    /// path that resolves the wrong source texture still runs its coroutine, still
    /// fills its queue, still writes PNG files of a plausible size, and still logs
    /// that it saved them: every signal a caller would check reports a healthy
    /// capture, and only opening the image shows a flat rectangle. A walkthrough is
    /// evidence, so it has to fail loudly instead of producing a folder nobody can
    /// use. <see cref="WalkthroughCapture"/> runs this over captured frames until one
    /// proves to hold content, and reports an error if the first frames do not.
    /// </remarks>
    public static class WalkthroughFrameCheck
    {
        /// <summary>Bytes per pixel in the RGB24 buffers the capture path produces.</summary>
        public const int BytesPerPixel = 3;

        /// <summary>
        /// Per-channel slack, so that dithering or a subtle gradient in an otherwise
        /// flat frame is still reported as uniform, while any real scene content is not.
        /// </summary>
        public const byte DefaultTolerance = 2;

        /// <summary>
        /// True when every pixel matches the first within <paramref name="tolerance"/>,
        /// which means the frame shows nothing.
        /// </summary>
        /// <param name="rgb24">Tightly packed RGB24 pixels, row-major.</param>
        /// <param name="width">Frame width in pixels; must be positive.</param>
        /// <param name="height">Frame height in pixels; must be positive.</param>
        /// <param name="tolerance">Maximum per-channel difference still considered equal.</param>
        public static bool IsUniform(byte[] rgb24, int width, int height, byte tolerance = DefaultTolerance)
        {
            if (rgb24 == null)
            {
                throw new ArgumentNullException(nameof(rgb24));
            }

            if (width <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(width), width, "Frame width must be positive.");
            }

            if (height <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(height), height, "Frame height must be positive.");
            }

            int pixelCount = width * height;
            int requiredBytes = pixelCount * BytesPerPixel;

            if (rgb24.Length < requiredBytes)
            {
                throw new ArgumentException(
                    "Frame buffer holds " + rgb24.Length + " bytes but " + width + "x" + height +
                    " RGB24 needs " + requiredBytes + ".",
                    nameof(rgb24));
            }

            byte firstRed = rgb24[0];
            byte firstGreen = rgb24[1];
            byte firstBlue = rgb24[2];

            for (int pixel = 1; pixel < pixelCount; pixel++)
            {
                int offset = pixel * BytesPerPixel;

                if (Differs(rgb24[offset], firstRed, tolerance)
                    || Differs(rgb24[offset + 1], firstGreen, tolerance)
                    || Differs(rgb24[offset + 2], firstBlue, tolerance))
                {
                    return false;
                }
            }

            return true;
        }

        private static bool Differs(byte value, byte reference, byte tolerance)
        {
            int difference = value > reference ? value - reference : reference - value;
            return difference > tolerance;
        }
    }
}
