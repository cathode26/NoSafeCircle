using UnityEditor;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Editor.Generation
{
    // Menu / batchmode entry points for the two generators extracted so they would survive the
    // deletion of the scene builders (ArchitecturalTileGenerator, CharacterAnimationGenerator).
    // Before this file existed neither generator had a MenuItem, and every caller of either was
    // a scene-builder file scheduled to die - Editor/DoorPrototypeSceneBuilder.cs and the five
    // Editor/Rooms/*SceneBuilder.cs files for ArchitecturalTileGenerator,
    // Editor/World/DoorPrototypeGlobalSceneBuilder.cs for CharacterAnimationGenerator. So once
    // those builders are deleted the generation code would still compile but nothing could ever
    // reach it again - "capability preserved" would be false in practice. This file is that
    // reachable entry point.
    //
    // ADD ONLY. This calls into ArchitecturalTileGenerator and CharacterAnimationGenerator with
    // the exact same asset folder, tile names and source sprite paths their current (dying)
    // callers use - see the entry-point-to-generator-method table in the task report. Neither
    // generator, nor any builder, nor any scene is modified by this file.
    //
    // Each method is both a [MenuItem] under "No Safe Circle/" (for interactive use) and a plain
    // public static method with no parameters, so it can also be invoked headlessly with
    // -executeMethod, the same pattern Editor/WebGLBuilder.cs:BuildFinal already establishes in
    // this project. A menu item alone cannot be run in batchmode, and batchmode is how
    // regeneration gets verified without a human at the editor.
    //
    // WARNING - MEASURED, NOT HYPOTHETICAL. Running any of these reimports every source sprite it
    // touches, and Unity's asset pipeline rewrites ~211 COMMITTED FILES with trailing-whitespace
    // churn as a side effect of that reimport - 208 of them are the SOURCE ART .meta files under
    // Assets/NoSafeCircle/DoorPrototype/Art/** that the generators read sprites from, the rest are
    // the regenerated Tile/.anim/.controller assets themselves. That churn is content-harmless
    // (whitespace only) but it leaves the working tree dirty, and a dirty canonical checkout
    // blocks every merge and decompose for everyone (CLAUDE.md, "NEVER POINT UNITY AT
    // CANONICAL"). Anyone invoking these entry points should expect ~211 dirtied files afterward,
    // review/discard whitespace-only churn before committing anything else, and must never run
    // this against the canonical checkout - only an isolated one.
    internal static class RegenerateAssetsMenu
    {
        // Identical to DoorPrototypeSceneBuilder.ArchitecturalTileAssetFolder and to each
        // Rooms/*SceneBuilder's own ArchitecturalTileFolder constant - all are the same literal
        // path today. Duplicated here rather than referenced because every one of those constants
        // is private to a scene-builder file that is being deleted.
        private const string ArchitecturalTileAssetFolder =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";

        // Source sprite paths, copied verbatim from the FloorSpriteSourcePath constant each dying
        // caller uses (DoorPrototypeSceneBuilder's generic ArchitecturalFloorSpriteSourcePath
        // also points at floor_RuinedEntry.png - that is not a typo, both the generic FloorTile
        // and RuinedEntryFloorTile are generated from the same source sprite today).
        private const string RuinedEntryFloorSpritePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_RuinedEntry.png";
        private const string BoneArchiveFloorSpritePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_BoneArchive.png";
        private const string ChapelOfAshFloorSpritePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_ChapelOfAsh.png";
        private const string LowerVaultFloorSpritePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_LowerVault.png";
        private const string FinalRoomFloorSpritePath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors/floor_FinalRoom.png";

        // ------------------------------------------------------------------------------------
        // The six architectural tiles: the generic FloorTile plus the five per-room floor tiles,
        // all written into ArchitecturalTileAssetFolder.
        // ------------------------------------------------------------------------------------

        [MenuItem("No Safe Circle/Regenerate Architectural Tiles")]
        public static void RegenerateArchitecturalTiles()
        {
            Debug.LogWarning("RegenerateArchitecturalTiles: reimports every source floor sprite " +
                "and will dirty roughly 211 committed files (mostly source-art .meta " +
                "trailing-whitespace churn). Never run this against the canonical checkout.");

            // Mirrors DoorPrototypeSceneBuilder.CreateArchitecturalTileSet's FloorTile leg only
            // (WallTile/ArchitecturalBorderTile are out of scope here - see task brief).
            ArchitecturalTileGenerator.LoadOrCreateArchitecturalTile(
                ArchitecturalTileAssetFolder, "FloorTile.asset", "FloorTile",
                RuinedEntryFloorSpritePath);

            // Mirrors RuinedEntrySceneBuilder.LoadOrCreateRuinedEntryFloorTile.
            ArchitecturalTileGenerator.RuinedEntry.LoadOrCreateSpriteTile(
                ArchitecturalTileAssetFolder, "RuinedEntryFloorTile", RuinedEntryFloorSpritePath);

            // Mirrors BoneArchiveSceneBuilder.LoadOrCreateBoneArchiveFloorTile.
            ArchitecturalTileGenerator.BoneArchive.LoadOrCreateBoneArchiveFloorTile(
                ArchitecturalTileAssetFolder, "BoneArchiveFloorTile",
                ArchitecturalTileAssetFolder + "/BoneArchiveFloorTile.asset",
                BoneArchiveFloorSpritePath);

            // Mirrors ChapelOfAshSceneBuilder.LoadOrCreateFloorTile.
            ArchitecturalTileGenerator.ChapelOfAsh.LoadOrCreateSpriteTile(
                ArchitecturalTileAssetFolder, "ChapelOfAshFloorTile", ChapelOfAshFloorSpritePath);

            // Mirrors LowerVaultSceneBuilder.LoadOrCreateFloorTile.
            ArchitecturalTileGenerator.LowerVault.LoadOrCreateSpriteTile(
                ArchitecturalTileAssetFolder, "LowerVaultFloorTile", LowerVaultFloorSpritePath);

            // Mirrors FinalRoomSceneBuilder.LoadOrCreateFloorTile.
            ArchitecturalTileGenerator.FinalRoom.LoadOrCreateFloorTile(
                ArchitecturalTileAssetFolder, "FinalRoomFloorTile",
                ArchitecturalTileAssetFolder + "/FinalRoomFloorTile.asset",
                FinalRoomFloorSpritePath);

            AssetDatabase.SaveAssets();
            Debug.Log("RegenerateArchitecturalTiles: done - FloorTile, RuinedEntryFloorTile, " +
                "BoneArchiveFloorTile, ChapelOfAshFloorTile, LowerVaultFloorTile, " +
                "FinalRoomFloorTile written to " + ArchitecturalTileAssetFolder);
        }

        // ------------------------------------------------------------------------------------
        // Wizard animation assets: WizardAnimator.controller plus its animation clips under
        // Art/Wizard/Generated/.
        // ------------------------------------------------------------------------------------

        [MenuItem("No Safe Circle/Regenerate Wizard Animations")]
        public static void RegenerateWizardAnimations()
        {
            Debug.LogWarning("RegenerateWizardAnimations: reimports every wizard source sprite " +
                "and will dirty committed .meta files with trailing-whitespace churn. Never run " +
                "this against the canonical checkout.");

            // Mirrors DoorPrototypeGlobalSceneBuilder.BuildPlayer's regeneration branch
            // (CharacterAnimationGenerator.BuildWizardAnimationAssets, as opposed to its
            // load-existing branch, CharacterAnimationGenerator.LoadWizardAnimationAssets).
            CharacterAnimationGenerator.BuildWizardAnimationAssets();

            AssetDatabase.SaveAssets();
            Debug.Log("RegenerateWizardAnimations: done - WizardAnimator.controller and its " +
                "clips written under Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated");
        }

        // ------------------------------------------------------------------------------------
        // Convenience: both of the above in one interactive click or one batchmode invocation.
        // ------------------------------------------------------------------------------------

        [MenuItem("No Safe Circle/Regenerate All Generated Assets")]
        public static void RegenerateAll()
        {
            RegenerateArchitecturalTiles();
            RegenerateWizardAnimations();
        }
    }
}
