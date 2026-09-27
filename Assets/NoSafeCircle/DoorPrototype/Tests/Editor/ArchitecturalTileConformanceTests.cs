using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    // F4 audit finding: every room's tile loader in
    // Editor/Generation/ArchitecturalTileGenerator.cs used to have a "load existing, and repair
    // it if wrong" branch reachable from BoneArchiveSceneBuilder.BuildInMemoryForTests and
    // FinalRoomSceneBuilder.BuildInMemoryForTests - so if a committed Tile asset lost its sprite
    // or gained a collider, running the ROOM TESTS would silently repair and save it, and the
    // regression would never surface. That reachable-write path is now closed (see
    // ArchitecturalTileGenerator.BoneArchive.LoadBoneArchiveFloorTileForTests /
    // ArchitecturalTileGenerator.FinalRoom.LoadFloorTileForTests and the allowAssetWrites split
    // in both room builders).
    //
    // THIS FILE IS THE OTHER HALF OF THAT FIX: a test whose job is to FAIL on wrong committed
    // tile data rather than repair it. It reads every committed architectural Tile directly from
    // disk with AssetDatabase.LoadAssetAtPath and asserts the DURABLE RELATION - this tile's
    // sprite must be the one committed source Sprite, and its colliderType must be None - never
    // a literal that happens to match today. A tile with the wrong sprite or a stray collider
    // fails HERE, by name, instead of being silently corrected by some other test's setup.
    //
    // This does not repair anything. If a listed tile is wrong, fix the ASSET (or, if this ever
    // needs to change intentionally, run the No Safe Circle/Regenerate Architectural Tiles menu
    // item in an isolated checkout, never in canonical - see RegenerateAssetsMenu.cs) and re-run.
    public class ArchitecturalTileConformanceTests
    {
        private const string TileFolder = "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";
        private const string FloorSpriteFolder = "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/floors";
        private const string WallSpriteFolder = "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls";

        private struct ExpectedTile
        {
            public readonly string DisplayName;
            public readonly string TilePath;
            public readonly string ExpectedSpritePath;

            public ExpectedTile(string displayName, string tilePath, string expectedSpritePath)
            {
                DisplayName = displayName;
                TilePath = tilePath;
                ExpectedSpritePath = expectedSpritePath;
            }

            public override string ToString() => DisplayName;
        }

        // One row per committed Tile asset RegenerateAssetsMenu.RegenerateArchitecturalTiles (or
        // a room builder's own write-capable LoadOrCreate... method) is allowed to produce.
        // Source-sprite paths are copied verbatim from the constants each room builder and
        // RegenerateAssetsMenu.cs already declare - see BoneArchiveSceneBuilder.cs,
        // FinalRoomSceneBuilder.cs, ChapelOfAshSceneBuilder.cs, LowerVaultSceneBuilder.cs,
        // RuinedEntrySceneBuilder.cs and DoorPrototypeSceneBuilder.cs's
        // ArchitecturalFloorSpriteSourcePath / ArchitecturalWallSpriteSourcePath.
        private static readonly ExpectedTile[] ExpectedTiles =
        {
            new ExpectedTile("FloorTile (demo layer)",
                TileFolder + "/FloorTile.asset", FloorSpriteFolder + "/floor_RuinedEntry.png"),
            new ExpectedTile("WallTile (shared full wall)",
                TileFolder + "/WallTile.asset", WallSpriteFolder + "/wall_straight.png"),
            new ExpectedTile("ArchitecturalBorderTile (demo layer)",
                TileFolder + "/ArchitecturalBorderTile.asset", FloorSpriteFolder + "/floor_RuinedEntry.png"),

            new ExpectedTile("RuinedEntryFloorTile",
                TileFolder + "/RuinedEntryFloorTile.asset", FloorSpriteFolder + "/floor_RuinedEntry.png"),
            new ExpectedTile("RuinedEntryLowWallTile",
                TileFolder + "/RuinedEntryLowWallTile.asset", WallSpriteFolder + "/wall_broken_stub.png"),

            new ExpectedTile("BoneArchiveFloorTile",
                TileFolder + "/BoneArchiveFloorTile.asset", FloorSpriteFolder + "/floor_BoneArchive.png"),

            new ExpectedTile("ChapelOfAshFloorTile",
                TileFolder + "/ChapelOfAshFloorTile.asset", FloorSpriteFolder + "/floor_ChapelOfAsh.png"),
            new ExpectedTile("ChapelOfAshFarWallTile",
                TileFolder + "/ChapelOfAshFarWallTile.asset", WallSpriteFolder + "/wall_straight.png"),
            new ExpectedTile("ChapelOfAshCutawayWallTile",
                TileFolder + "/ChapelOfAshCutawayWallTile.asset", WallSpriteFolder + "/wall_broken_stub.png"),

            new ExpectedTile("LowerVaultFloorTile",
                TileFolder + "/LowerVaultFloorTile.asset", FloorSpriteFolder + "/floor_LowerVault.png"),
            new ExpectedTile("LowerVaultNearWallStubTile",
                TileFolder + "/LowerVaultNearWallStubTile.asset", WallSpriteFolder + "/wall_broken_stub.png"),

            new ExpectedTile("FinalRoomFloorTile",
                TileFolder + "/FinalRoomFloorTile.asset", FloorSpriteFolder + "/floor_FinalRoom.png"),
        };

        private static System.Collections.Generic.IEnumerable<ExpectedTile> Cases() => ExpectedTiles;

        // NEGATIVE CONTROL: a tile name nothing generates. If this ever started passing, the
        // lookup below would be silently matching the wrong asset for everything.
        [Test]
        public void SanityProbe_NonExistentTileIsNotFound()
        {
            Tile phantom = AssetDatabase.LoadAssetAtPath<Tile>(TileFolder + "/ZZZNotATile.asset");
            Assert.IsNull(phantom, "Sanity probe must find nothing; a non-null result means the " +
                "lookup below cannot be trusted to report a real absence either.");
        }

        [TestCaseSource(nameof(Cases))]
        public void CommittedTile_HasExpectedSpriteAndNoCollider(ExpectedTile expected)
        {
            Tile tile = AssetDatabase.LoadAssetAtPath<Tile>(expected.TilePath);
            Assert.IsNotNull(tile,
                $"{expected.DisplayName}: expected a committed Tile asset at '{expected.TilePath}' " +
                "but AssetDatabase could not load one. This test never creates it - fix the " +
                "asset, or regenerate it in an isolated checkout via RegenerateAssetsMenu.");

            Sprite expectedSprite = AssetDatabase.LoadAssetAtPath<Sprite>(expected.ExpectedSpritePath);
            Assert.IsNotNull(expectedSprite,
                $"{expected.DisplayName}: the expected source sprite '{expected.ExpectedSpritePath}' " +
                "did not load - this is a fixture problem, not a tile problem.");

            Assert.AreEqual(Tile.ColliderType.None, tile.colliderType,
                $"{expected.DisplayName} at '{expected.TilePath}' has colliderType " +
                $"'{tile.colliderType}'; every architectural tile must be ColliderType.None. " +
                "A wrong committed value like this used to be silently repaired and saved by a " +
                "room test's own setup (F4 audit finding) - this test must fail instead.");

            Assert.AreSame(expectedSprite, tile.sprite,
                $"{expected.DisplayName} at '{expected.TilePath}' does not use the committed " +
                $"sprite at '{expected.ExpectedSpritePath}' (sprite is " +
                $"'{(tile.sprite == null ? "null" : tile.sprite.name)}'). A wrong committed " +
                "sprite like this used to be silently repaired and saved by a room test's own " +
                "setup (F4 audit finding) - this test must fail instead.");
        }
    }
}
