using UnityEngine;
using UnityEngine.Rendering;

namespace NoSafeCircle.DoorPrototype.Editor.Rooms
{
    // ONE PLACEHOLDER TONE FOR EVERY ROOM'S BLOCKOUT MASSES, and one material path that
    // actually applies it. Before this existed each room invented its own: Ruined Entry shipped
    // untinted white cubes, the Final Room an FR-1 mass in saturated indigo, and the Lower Vault
    // hazard planes in magenta. Each read as a rendering bug rather than as a placeholder, and
    // the Art Director's pick was to reuse the tone already approved for the rubble instead of
    // adding a fourth.
    internal static class RoomPlaceholderVisuals
    {
        // The approved blockout tone. Alpha is deliberately below 255 so a placeholder mass
        // reads as provisional rather than as finished geometry.
        internal static readonly Color32 BlockoutPlaceholder = new Color32(96, 88, 80, 230);

        // SETTING material.color ALONE SILENTLY DROPS ALPHA. The Standard shader ships in Opaque
        // mode, where the alpha channel is simply not consulted - the assignment succeeds, the
        // colour reads back correctly, and the object renders fully solid. That is why the
        // placeholder alpha had no effect anywhere it was set by hand, and why this helper
        // exists rather than a convention everyone is asked to remember.
        internal static Material CreateStandardMaterial(Color32 color)
        {
            Material material = new Material(Shader.Find("Standard"));
            material.color = color;
            if (color.a < 255)
            {
                material.SetFloat("_Mode", 2f); // Fade
                material.SetInt("_SrcBlend", (int)BlendMode.SrcAlpha);
                material.SetInt("_DstBlend", (int)BlendMode.OneMinusSrcAlpha);
                material.SetInt("_ZWrite", 0);
                material.DisableKeyword("_ALPHATEST_ON");
                material.EnableKeyword("_ALPHABLEND_ON");
                material.DisableKeyword("_ALPHAPREMULTIPLY_ON");
                material.renderQueue = (int)RenderQueue.Transparent;
            }

            return material;
        }

        // Derives a lighter edge tone from a base tone at a given ratio, for placeholder
        // textures that draw a border to mark their own extent. This is a COMPUTATION, not a
        // second authored colour: the Lower Vault proxy encoded its edge at roughly 2x its
        // fill's channels, and repointing the fill keeps that relationship rather than
        // inventing a tone nobody picked.
        internal static Color32 EdgeFrom(Color32 fill, float ratio)
        {
            return new Color32(
                (byte)Mathf.Clamp(Mathf.RoundToInt(fill.r * ratio), 0, 255),
                (byte)Mathf.Clamp(Mathf.RoundToInt(fill.g * ratio), 0, 255),
                (byte)Mathf.Clamp(Mathf.RoundToInt(fill.b * ratio), 0, 255),
                fill.a);
        }
    }
}
