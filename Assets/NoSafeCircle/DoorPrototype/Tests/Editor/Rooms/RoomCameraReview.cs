using System;
using System.Collections.Generic;
using System.IO;
using NoSafeCircle.DoorPrototype.Editor;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    /// <summary>Shared mechanics for the rooms' developer gameplay-camera review captures.</summary>
    /// <remarks>
    /// Four rooms have a "Vincent looks at it" completion gate and each specifies its own stations,
    /// but the machinery around them is identical: refuse to write inside the repository, refuse to
    /// overwrite earlier evidence, stage a wizard, render an orthographic isometric shot per
    /// position, and assemble a contact sheet. That machinery lives here once.
    /// <para>
    /// WHAT DELIBERATELY DOES NOT LIVE HERE: the rig numbers and the station lists. Each gate
    /// states its own -- NSC-048 requires 16:9 where the NSC-044 fixture renders 4:3, and copying
    /// one room's numbers into another is exactly the mistake this file must not make easy. Callers
    /// pass their own and the comment above each says which gate the numbers came from.
    /// </para>
    /// </remarks>
    internal static class RoomCameraReview
    {
        /// <summary>Resolves the output directory and refuses anything inside the repository.</summary>
        internal static string RequireDirectoryOutsideRepository(string output)
        {
            Assert.IsTrue(Path.IsPathRooted(output), "The review output directory must be absolute.");
            string outputFull = Path.GetFullPath(output);
            string repository = Path.GetFullPath(Directory.GetCurrentDirectory())
                .TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            Assert.IsFalse(
                outputFull.TrimEnd(Path.DirectorySeparatorChar).Equals(
                    repository.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase)
                || outputFull.StartsWith(repository, StringComparison.OrdinalIgnoreCase),
                "Camera review PNGs must be written outside the repository.");
            Directory.CreateDirectory(outputFull);
            return outputFull;
        }

        /// <summary>Refuses to run into a directory that already holds review evidence.</summary>
        internal static void EnsureFreshOutput(string outputFull, IEnumerable<string> names)
        {
            foreach (string name in names)
            {
                Assert.IsFalse(File.Exists(Path.Combine(outputFull, name + ".png")),
                    "Use a fresh output directory so earlier visual evidence is preserved.");
            }
            Assert.IsFalse(File.Exists(Path.Combine(outputFull, "contact-sheet.png")));
        }

        internal static GameObject CreateWizard(string name, string spritePath)
        {
            Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(spritePath);
            Assert.IsNotNull(sprite, spritePath);
            GameObject wizard = new GameObject(name, typeof(SpriteRenderer));
            wizard.transform.localScale = new Vector3(1f, 2f, 1f);
            SpriteRenderer renderer = wizard.GetComponent<SpriteRenderer>();
            renderer.sprite = sprite;
            // The durable relation, not the value it currently has. A literal "Default" passes
            // today only because the constant equals it, and would keep passing after it moves.
            renderer.sortingLayerName = DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName;
            renderer.sortingOrder = 0;
            return wizard;
        }

        internal static GameObject CreateCamera(
            string name, float orthographicSize, Vector3 eulerAngles,
            int width, int height, out Camera camera, out RenderTexture target)
        {
            GameObject cameraObject = new GameObject(name, typeof(Camera), typeof(IsometricCameraFollow));
            camera = cameraObject.GetComponent<Camera>();
            camera.orthographic = true;
            camera.orthographicSize = orthographicSize;
            camera.transparencySortMode = TransparencySortMode.CustomAxis;
            camera.transparencySortAxis = IsometricCameraFollow.IsometricTransparencySortAxis;
            cameraObject.transform.rotation = Quaternion.Euler(eulerAngles);
            target = new RenderTexture(width, height, 24);
            target.Create();
            camera.targetTexture = target;
            return cameraObject;
        }

        /// <summary>Finds a Tilemap by GameObject name across the loaded scenes.</summary>
        internal static Tilemap FindTilemap(string name)
        {
            foreach (Tilemap tilemap in UnityEngine.Object.FindObjectsByType<Tilemap>(
                         FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (string.Equals(tilemap.gameObject.name, name, StringComparison.Ordinal))
                {
                    return tilemap;
                }
            }
            return null;
        }

        /// <summary>Places the wizard and camera, renders one shot and writes it.</summary>
        internal static Texture2D Shoot(
            Camera camera, GameObject cameraObject, GameObject wizard, RenderTexture target,
            Vector3 groundPosition, Vector3 cameraOffset, int width, int height, string pngPath)
        {
            wizard.transform.position = groundPosition;
            cameraObject.transform.position = groundPosition + cameraOffset;
            cameraObject.GetComponent<IsometricCameraFollow>().Initialize(wizard.transform);
            camera.Render();
            RenderTexture.active = target;
            Texture2D shot = new Texture2D(width, height, TextureFormat.RGBA32, false);
            shot.ReadPixels(new Rect(0f, 0f, width, height), 0, 0);
            shot.Apply(false, false);
            File.WriteAllBytes(pngPath, shot.EncodeToPNG());
            return shot;
        }

        /// <summary>Assembles a two-column contact sheet, filling any spare cell deliberately.</summary>
        /// <remarks>
        /// A fresh Texture2D is NOT cleared, so an unfilled cell carries uninitialised memory that
        /// renders as a plausible frame. Every cell is written, including the spare ones.
        /// </remarks>
        internal static Texture2D WriteContactSheet(
            string outputFull, IReadOnlyList<Texture2D> shots, int shotCount, int width, int height)
        {
            const int columns = 2;
            int rows = (shotCount + columns - 1) / columns;
            Texture2D contact = new Texture2D(columns * width, rows * height, TextureFormat.RGBA32, false);
            var blank = new Color32[width * height];
            for (int index = 0; index < columns * rows; index++)
            {
                Color32[] pixels = index < shotCount ? shots[index].GetPixels32() : blank;
                int originX = (index % columns) * width;
                int originY = (rows - 1 - (index / columns)) * height;
                contact.SetPixels32(originX, originY, width, height, pixels);
            }
            contact.Apply(false, false);
            File.WriteAllBytes(Path.Combine(outputFull, "contact-sheet.png"), contact.EncodeToPNG());
            return contact;
        }
    }
}
