using System;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Tilemaps;
using NoSafeCircle.DoorPrototype.Editor.Rooms;

namespace NoSafeCircle.DoorPrototype.Editor.Generation
{
    // Extracted from DoorPrototypeSceneBuilder.cs and the five Rooms/*SceneBuilder.cs files.
    // PURE MOVE: every architectural-Tile generator that used to live inside a scene builder now
    // lives here instead, so the builders can be deleted later without losing the ability to
    // regenerate the committed Tile assets the runtime FloorSpawner loads from
    // Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/ (RuinedEntryFloorTile,
    // BoneArchiveFloorTile, ChapelOfAshFloorTile, LowerVaultFloorTile, FinalRoomFloorTile,
    // FloorTile). The committed assets themselves are unchanged; only where the code that can
    // rebuild them lives has moved. Same asset paths, same tile names, same colliderType, same
    // sprite sources, same load-existing-before-create logic as before the move - no behaviour
    // change. Each original builder method now forwards into this class; see the corresponding
    // builder file for its (unchanged) public entry point and comments explaining why each tile
    // is shaped as it is.
    public static class ArchitecturalTileGenerator
    {
        // ------------------------------------------------------------------------------------
        // From Editor/DoorPrototypeSceneBuilder.cs (CreateArchitecturalTileSet /
        // LoadOrCreateArchitecturalTile). Used for the demo/global layer's shared Floor/Wall/
        // ArchitecturalBorder tile trio.
        // ------------------------------------------------------------------------------------

        internal sealed class ArchitecturalTileSet
        {
            public readonly Tile Floor;
            public readonly Tile Wall;
            public readonly Tile Architectural;

            public ArchitecturalTileSet(Tile floor, Tile wall, Tile architectural)
            {
                Floor = floor;
                Wall = wall;
                Architectural = architectural;
            }
        }

        internal static ArchitecturalTileSet CreateArchitecturalTileSet(
            string assetFolder, string floorSpriteSourcePath, string wallSpriteSourcePath)
        {
            return new ArchitecturalTileSet(
                LoadOrCreateArchitecturalTile(
                    assetFolder, "FloorTile.asset", "FloorTile", floorSpriteSourcePath),
                LoadOrCreateArchitecturalTile(
                    assetFolder, "WallTile.asset", "WallTile", wallSpriteSourcePath),
                LoadOrCreateArchitecturalTile(
                    assetFolder, "ArchitecturalBorderTile.asset", "ArchitecturalBorderTile",
                    floorSpriteSourcePath));
        }

        internal static Tile LoadOrCreateArchitecturalTile(
            string assetFolder, string assetFileName, string tileName, string sourceSpritePath)
        {
            var sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourceSpritePath);
            if (sourceSprite == null)
            {
                throw new InvalidOperationException(
                    $"The Door Prototype scene requires the committed sprite at '{sourceSpritePath}'.");
            }

            if (!string.IsNullOrEmpty(assetFolder))
            {
                var assetPath = assetFolder + "/" + assetFileName;
                var existing = AssetDatabase.LoadAssetAtPath<Tile>(assetPath);

                if (existing != null)
                {
                    if (existing.sprite != sourceSprite || existing.colliderType != Tile.ColliderType.None)
                    {
                        existing.sprite = sourceSprite;
                        existing.colliderType = Tile.ColliderType.None;
                        EditorUtility.SetDirty(existing);
                        AssetDatabase.SaveAssetIfDirty(existing);
                    }
                    return existing;
                }

                var persistentTile = ScriptableObject.CreateInstance<Tile>();
                persistentTile.name = tileName;
                persistentTile.colliderType = Tile.ColliderType.None;
                persistentTile.sprite = sourceSprite;

                AssetDatabase.CreateAsset(persistentTile, assetPath);
                EditorUtility.SetDirty(persistentTile);
                AssetDatabase.SaveAssetIfDirty(persistentTile);

                return persistentTile;
            }

            var inMemoryTile =
                DoorPrototypeSceneBuilder.OwnTransientArchitecturalObject(
                    ScriptableObject.CreateInstance<Tile>());

            inMemoryTile.name = tileName;
            inMemoryTile.colliderType = Tile.ColliderType.None;
            inMemoryTile.hideFlags = HideFlags.HideAndDontSave;
            inMemoryTile.sprite = sourceSprite;

            return inMemoryTile;
        }

        // ------------------------------------------------------------------------------------
        // From Editor/Rooms/RuinedEntrySceneBuilder.cs. NOTE: this LoadOrCreateSpriteTile is
        // textually near-identical to ChapelOfAsh's and LowerVault's below, but each embeds its
        // own room-name text in the thrown InvalidOperationException message and reads its own
        // room's EnsureFolder, so they are kept as three separate methods rather than unified
        // into one shared helper.
        // ------------------------------------------------------------------------------------

        internal static class RuinedEntry
        {
            internal static Tile LoadOrCreateSpriteTile(string assetFolder, string tileName, string sourceSpritePath)
            {
                if (string.IsNullOrWhiteSpace(assetFolder) || !assetFolder.StartsWith("Assets/", StringComparison.Ordinal))
                {
                    throw new ArgumentException("The Tile asset folder must be under Assets.", nameof(assetFolder));
                }

                Sprite sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourceSpritePath);
                if (sourceSprite == null)
                {
                    throw new InvalidOperationException(
                        $"Ruined Entry requires the committed sprite at '{sourceSpritePath}'.");
                }

                RuinedEntrySceneBuilder.EnsureFolder(assetFolder);
                string assetPath = assetFolder + "/" + tileName + ".asset";
                Tile tile = AssetDatabase.LoadAssetAtPath<Tile>(assetPath);
                if (tile == null)
                {
                    tile = ScriptableObject.CreateInstance<Tile>();
                    tile.name = tileName;
                    tile.colliderType = Tile.ColliderType.None;
                    tile.sprite = sourceSprite;
                    AssetDatabase.CreateAsset(tile, assetPath);
                    EditorUtility.SetDirty(tile);
                    AssetDatabase.SaveAssetIfDirty(tile);
                    return tile;
                }

                if (tile.sprite != sourceSprite || tile.colliderType != Tile.ColliderType.None)
                {
                    tile.sprite = sourceSprite;
                    tile.colliderType = Tile.ColliderType.None;
                    EditorUtility.SetDirty(tile);
                    AssetDatabase.SaveAssetIfDirty(tile);
                }

                return tile;
            }
        }

        // ------------------------------------------------------------------------------------
        // From Editor/Rooms/BoneArchiveSceneBuilder.cs (LoadOrCreateBoneArchiveFloorTile).
        // Unlike the RuinedEntry/ChapelOfAsh/LowerVault family above, this one does not build
        // the asset path from assetFolder + tileName - it always writes to the fixed tilePath
        // constant the caller supplies and only uses assetFolder to ensure the folder exists.
        // That is how the original method behaved; preserved as-is.
        // ------------------------------------------------------------------------------------

        internal static class BoneArchive
        {
            // NSC-109 AC-001/AC-002: binds this room's floor Tile to the committed
            // floor_BoneArchive sprite rather than a procedurally generated texture.
            internal static Tile LoadOrCreateBoneArchiveFloorTile(
                string assetFolder, string tileName, string tilePath, string sourceSpritePath)
            {
                Sprite sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourceSpritePath);
                if (sourceSprite == null)
                {
                    throw new InvalidOperationException(
                        $"Bone Archive requires the committed sprite at '{sourceSpritePath}'.");
                }

                if (!AssetDatabase.IsValidFolder(assetFolder))
                {
                    Directory.CreateDirectory(assetFolder);
                    AssetDatabase.Refresh();
                }

                Tile tile = AssetDatabase.LoadAssetAtPath<Tile>(tilePath);
                if (tile == null)
                {
                    tile = ScriptableObject.CreateInstance<Tile>();
                    tile.name = tileName;
                    tile.colliderType = Tile.ColliderType.None;
                    tile.sprite = sourceSprite;
                    AssetDatabase.CreateAsset(tile, tilePath);
                    EditorUtility.SetDirty(tile);
                    AssetDatabase.SaveAssetIfDirty(tile);
                    return tile;
                }

                if (tile.sprite != sourceSprite || tile.colliderType != Tile.ColliderType.None)
                {
                    tile.sprite = sourceSprite;
                    tile.colliderType = Tile.ColliderType.None;
                    EditorUtility.SetDirty(tile);
                    AssetDatabase.SaveAssetIfDirty(tile);
                }

                return tile;
            }
        }

        // ------------------------------------------------------------------------------------
        // From Editor/Rooms/ChapelOfAshSceneBuilder.cs. Same family and same caveat as
        // RuinedEntry above: near-identical to RuinedEntry's and LowerVault's LoadOrCreateSpriteTile,
        // kept separate because the exception message and EnsureFolder target differ.
        // ------------------------------------------------------------------------------------

        internal static class ChapelOfAsh
        {
            internal static Tile LoadOrCreateSpriteTile(string assetFolder, string tileName, string sourceSpritePath)
            {
                if (string.IsNullOrWhiteSpace(assetFolder) || !assetFolder.StartsWith("Assets/", StringComparison.Ordinal))
                {
                    throw new ArgumentException("The Tile asset folder must be under Assets.", nameof(assetFolder));
                }

                Sprite sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourceSpritePath);
                if (sourceSprite == null)
                {
                    throw new InvalidOperationException(
                        $"Chapel of Ash requires the committed sprite at '{sourceSpritePath}'.");
                }

                ChapelOfAshSceneBuilder.EnsureFolder(assetFolder);
                string assetPath = assetFolder + "/" + tileName + ".asset";
                Tile tile = AssetDatabase.LoadAssetAtPath<Tile>(assetPath);
                if (tile == null)
                {
                    tile = ScriptableObject.CreateInstance<Tile>();
                    tile.name = tileName;
                    tile.colliderType = Tile.ColliderType.None;
                    tile.sprite = sourceSprite;
                    AssetDatabase.CreateAsset(tile, assetPath);
                    EditorUtility.SetDirty(tile);
                    AssetDatabase.SaveAssetIfDirty(tile);
                    return tile;
                }

                if (tile.sprite != sourceSprite || tile.colliderType != Tile.ColliderType.None)
                {
                    tile.sprite = sourceSprite;
                    tile.colliderType = Tile.ColliderType.None;
                    EditorUtility.SetDirty(tile);
                    AssetDatabase.SaveAssetIfDirty(tile);
                }

                return tile;
            }
        }

        // ------------------------------------------------------------------------------------
        // From Editor/Rooms/LowerVaultSceneBuilder.cs. Same family and same caveat as RuinedEntry
        // and ChapelOfAsh above.
        // ------------------------------------------------------------------------------------

        internal static class LowerVault
        {
            internal static Tile LoadOrCreateSpriteTile(string assetFolder, string tileName, string sourceSpritePath)
            {
                if (string.IsNullOrWhiteSpace(assetFolder) || !assetFolder.StartsWith("Assets/", StringComparison.Ordinal))
                {
                    throw new ArgumentException("The Tile asset folder must be under Assets.", nameof(assetFolder));
                }

                Sprite sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourceSpritePath);
                if (sourceSprite == null)
                {
                    throw new InvalidOperationException(
                        $"Lower Vault requires the committed sprite at '{sourceSpritePath}'.");
                }

                LowerVaultSceneBuilder.EnsureFolder(assetFolder);
                string assetPath = assetFolder + "/" + tileName + ".asset";
                Tile tile = AssetDatabase.LoadAssetAtPath<Tile>(assetPath);
                if (tile == null)
                {
                    tile = ScriptableObject.CreateInstance<Tile>();
                    tile.name = tileName;
                    tile.colliderType = Tile.ColliderType.None;
                    tile.sprite = sourceSprite;
                    AssetDatabase.CreateAsset(tile, assetPath);
                    EditorUtility.SetDirty(tile);
                    AssetDatabase.SaveAssetIfDirty(tile);
                    return tile;
                }

                if (tile.sprite != sourceSprite || tile.colliderType != Tile.ColliderType.None)
                {
                    tile.sprite = sourceSprite;
                    tile.colliderType = Tile.ColliderType.None;
                    EditorUtility.SetDirty(tile);
                    AssetDatabase.SaveAssetIfDirty(tile);
                }

                return tile;
            }
        }

        // ------------------------------------------------------------------------------------
        // From Editor/Rooms/FinalRoomSceneBuilder.cs (LoadOrCreateFloorTile). Same fixed-tilePath
        // shape as BoneArchive above, not the assetFolder+tileName shape of the other three.
        // ------------------------------------------------------------------------------------

        internal static class FinalRoom
        {
            // NSC-109 AC-001/AC-002: this room's own floor Tile, bound to the committed
            // floor_FinalRoom sprite rather than a procedurally generated texture.
            internal static Tile LoadOrCreateFloorTile(
                string assetFolder, string tileName, string tilePath, string sourceSpritePath)
            {
                Sprite sourceSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourceSpritePath);
                if (sourceSprite == null)
                {
                    throw new InvalidOperationException(
                        $"Final Room requires the committed sprite at '{sourceSpritePath}'.");
                }

                if (!AssetDatabase.IsValidFolder(assetFolder))
                {
                    Directory.CreateDirectory(assetFolder);
                    AssetDatabase.Refresh();
                }

                Tile tile = AssetDatabase.LoadAssetAtPath<Tile>(tilePath);
                if (tile == null)
                {
                    tile = ScriptableObject.CreateInstance<Tile>();
                    tile.name = tileName;
                    tile.colliderType = Tile.ColliderType.None;
                    tile.sprite = sourceSprite;
                    AssetDatabase.CreateAsset(tile, tilePath);
                    EditorUtility.SetDirty(tile);
                    AssetDatabase.SaveAssetIfDirty(tile);
                    return tile;
                }

                if (tile.sprite != sourceSprite || tile.colliderType != Tile.ColliderType.None)
                {
                    tile.sprite = sourceSprite;
                    tile.colliderType = Tile.ColliderType.None;
                    EditorUtility.SetDirty(tile);
                    AssetDatabase.SaveAssetIfDirty(tile);
                }

                return tile;
            }
        }
    }
}
