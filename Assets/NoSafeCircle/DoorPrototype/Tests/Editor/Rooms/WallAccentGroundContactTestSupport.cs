using NUnit.Framework;
using UnityEngine;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    /// <summary>Shared by <see cref="ArchitecturalWallAccentPlacementTests"/> and
    /// <see cref="RoomWallAccentIntegrationTests"/>: both need to know a wall accent sprite's
    /// alpha-tight bottom padding so they can assert ground contact against the DRAWN ART'S base
    /// rather than the sprite rect (which includes that padding). One measurement, reused, so the
    /// two suites cannot drift apart on what "padding" means.</summary>
    internal static class WallAccentGroundContactTestSupport
    {
        /// <summary>The alpha-tight bottom padding, in pixels, of the PNG at <paramref name="assetPath"/>.
        /// Decoded from the file's own bytes rather than read off the imported texture, so callers do
        /// not depend on a TextureImporter isReadable flag they do not own.</summary>
        internal static int MeasureAlphaTightBottomPaddingPixels(string assetPath)
        {
            byte[] fileBytes = System.IO.File.ReadAllBytes(assetPath);
            var decoded = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            decoded.hideFlags = HideFlags.HideAndDontSave;
            try
            {
                Assert.IsTrue(ImageConversion.LoadImage(decoded, fileBytes, false),
                    "Could not decode " + assetPath + " as an image.");

                Color32[] pixels = decoded.GetPixels32();
                for (int y = 0; y < decoded.height; y++)
                {
                    int rowStart = y * decoded.width;
                    for (int x = 0; x < decoded.width; x++)
                    {
                        if (pixels[rowStart + x].a != 0)
                        {
                            // GetPixels32 is bottom-up, so the first non-empty row IS the padding.
                            return y;
                        }
                    }
                }

                Assert.Fail(assetPath + " is fully transparent - there is no art to anchor.");
                return 0;
            }
            finally
            {
                Object.DestroyImmediate(decoded);
            }
        }
    }
}
