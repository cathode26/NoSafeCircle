// NSC-078: import settings for the dungeon prop source sprites.
//
// The nine settings below are the ones NSC-078's completion gate names, and they are
// written here so the importer -- not a hand-authored .meta -- is what applies them.
//
// wrapMode is Clamp. Note that in a serialized .meta this appears as `wrapU: 1`, NOT 0:
// the serialized enum is inverted from the intuition, and asserting the wrong value
// failed sixteen props in one run while every text-level check passed them.
//
// The pivot is the drawn GROUND LINE, measured from the sprite's alpha bounds. The
// catalog rule of bottom-centre (0.5, 0) assumes the art touches the canvas bottom and
// none of these do -- every prop carries transparent rows beneath it, so (0.5, 0) would
// float it by up to 0.23 world units at 64 px per unit.

using System.IO;
using UnityEditor;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Editor.Art
{
    public sealed class DungeonPropImportPostprocessor : AssetPostprocessor
    {
        public const string PropRoot =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/";

        public const float PixelsPerUnit = 64f;

        public const string CatalogPath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/PropCatalog.json";

        public static bool IsDungeonProp(string assetPath)
        {
            return assetPath != null
                   && assetPath.Replace('\\', '/').StartsWith(PropRoot, System.StringComparison.Ordinal)
                   && assetPath.EndsWith(".png", System.StringComparison.OrdinalIgnoreCase);
        }

        private void OnPreprocessTexture()
        {
            if (!IsDungeonProp(assetPath))
            {
                return;
            }

            var importer = (TextureImporter)assetImporter;

            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePixelsPerUnit = PixelsPerUnit;
            importer.filterMode = FilterMode.Point;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.alphaIsTransparency = true;
            importer.mipmapEnabled = false;
            importer.wrapMode = TextureWrapMode.Clamp;
            importer.textureShape = TextureImporterShape.Texture2D;

            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spriteBorder = Vector4.zero;

            Vector2 pivot;
            if (TryMeasurePivot(assetPath, out pivot))
            {
                var settings = new TextureImporterSettings();
                importer.ReadTextureSettings(settings);
                settings.spriteAlignment = (int)SpriteAlignment.Custom;
                settings.spritePivot = pivot;
                importer.SetTextureSettings(settings);
            }
        }

        /// <summary>
        /// The pivot this prop should carry, honouring the catalog's pivot_rule.
        ///
        /// Most props STAND ON a base and take the drawn ground line. A few LIE WITHIN an
        /// area -- a floor sigil, a ring of candles, bones strewn flat -- and for those the
        /// bottom edge of the sprite is the NEAR RIM of the shape, not a base. Anchoring a
        /// lying prop to its bottom edge puts that rim at the placement point and pushes
        /// the whole object behind where it belongs: measured at 0.594 world units for
        /// ca_sigil_floor_mark and 0.492 for shared_bone_pile_b, against 0.234 for the
        /// wizard hover defect that produced NSC-075 AC-008.
        ///
        /// The classification CANNOT be derived from the footprint. Ranking all 45 props by
        /// height over depth gives 0.00 / 0.20 / 0.33 / 0.37 / 0.40 -- a continuum with no
        /// break, so any threshold would be tuned to whichever cases were looked at first.
        /// It is an art judgement, so the catalog records it and this reads it.
        ///
        /// Unknown or unlisted falls back to the ground line, so a prop that has never been
        /// classified imports exactly as it does today rather than silently moving.
        /// </summary>
        public static bool TryMeasurePivot(string assetPath, out Vector2 pivot)
        {
            if (!LiesWithinItsFootprint(assetPath))
            {
                return TryMeasureGroundPivot(assetPath, out pivot);
            }

            pivot = new Vector2(0.5f, 0f);
            int top, bottom, height;
            if (!TryMeasureAlphaRows(assetPath, out top, out bottom, out height))
            {
                return false;
            }

            float raw = (height - (top + bottom) * 0.5f) / height;
            pivot = new Vector2(0.5f, Mathf.Round(raw * 1000000f) / 1000000f);
            return true;
        }

        private static bool LiesWithinItsFootprint(string assetPath)
        {
            var id = Path.GetFileNameWithoutExtension(assetPath);
            var catalog = AssetDatabase.LoadAssetAtPath<TextAsset>(CatalogPath);
            if (catalog == null)
            {
                return false;
            }

            // Deliberately a substring scan rather than a JSON parse: the postprocessor runs
            // during import, the catalog is itself an imported asset, and a parse failure
            // here would silently reclassify every prop. A miss falls back to the ground
            // line, which is the safe direction.
            var text = catalog.text;
            var at = text.IndexOf("\"" + id + "\"", System.StringComparison.Ordinal);
            if (at < 0)
            {
                return false;
            }

            var rule = text.IndexOf("\"pivot_rule\"", at, System.StringComparison.Ordinal);
            if (rule < 0)
            {
                return false;
            }

            var nextEntry = text.IndexOf("\"id\":", at + 1, System.StringComparison.Ordinal);
            if (nextEntry >= 0 && rule > nextEntry)
            {
                return false;                      // that pivot_rule belongs to a later entry
            }

            var line = text.Substring(rule, System.Math.Min(64, text.Length - rule));
            return line.Contains("lie_within");
        }

        private static bool TryMeasureAlphaRows(string assetPath, out int top, out int bottom,
                                                out int height)
        {
            top = bottom = 0;
            height = 0;
            if (!File.Exists(assetPath))
            {
                return false;
            }

            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                if (!texture.LoadImage(File.ReadAllBytes(assetPath), false))
                {
                    return false;
                }

                height = texture.height;
                int width = texture.width;
                var pixels = texture.GetPixels32();

                int lowest = -1, highest = -1;
                for (int y = 0; y < height; y++)
                {
                    int rowStart = y * width;
                    for (int x = 0; x < width; x++)
                    {
                        if (pixels[rowStart + x].a != 0)
                        {
                            if (lowest < 0)
                            {
                                lowest = y;
                            }
                            highest = y;
                            break;
                        }
                    }
                }

                if (lowest < 0)
                {
                    return false;
                }

                // rows run bottom-up; convert to top-down so the caller's arithmetic matches
                // the alpha bounding box everything else is measured against
                top = height - 1 - highest;
                bottom = height - lowest;
                return true;
            }
            finally
            {
                Object.DestroyImmediate(texture);
            }
        }

        /// <summary>
        /// Normalised pivot on the drawn figure's bottom edge: x centred, y measured from
        /// the alpha bounds so the sprite sits on its own ground line rather than on the
        /// bottom of its canvas.
        /// </summary>
        public static bool TryMeasureGroundPivot(string assetPath, out Vector2 pivot)
        {
            pivot = new Vector2(0.5f, 0f);
            if (!File.Exists(assetPath))
            {
                return false;
            }

            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                if (!texture.LoadImage(File.ReadAllBytes(assetPath), false))
                {
                    return false;
                }

                int height = texture.height;
                int width = texture.width;
                var pixels = texture.GetPixels32();

                // Texture rows run bottom-up; find the lowest row holding any opaque pixel.
                int lowestOpaqueRow = -1;
                for (int y = 0; y < height && lowestOpaqueRow < 0; y++)
                {
                    int rowStart = y * width;
                    for (int x = 0; x < width; x++)
                    {
                        if (pixels[rowStart + x].a != 0)
                        {
                            lowestOpaqueRow = y;
                            break;
                        }
                    }
                }

                if (lowestOpaqueRow < 0)
                {
                    return false;
                }

                // Rounded to six decimals, and that is not cosmetic. Unity serialises a raw
                // float at full precision (0.045454547) while the committed metas carry the
                // rounded form (0.045455). The two are the same number and produce a
                // byte-level diff, so an unrounded pivot silently rewrites every meta on
                // every import -- including nine that belong to NSC-102, whose contract
                // requires re-importing them to be a no-op.
                float raw = lowestOpaqueRow / (float)height;
                pivot = new Vector2(0.5f, Mathf.Round(raw * 1000000f) / 1000000f);
                return true;
            }
            finally
            {
                Object.DestroyImmediate(texture);
            }
        }
    }
}
