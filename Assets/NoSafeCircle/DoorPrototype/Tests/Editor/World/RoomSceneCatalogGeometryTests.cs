using System.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    // NSC-101 VAL-001 and VAL-002.
    //
    // This is a NEW type, deliberately NOT a partial of
    // NoSafeCircle.DoorPrototype.Tests.Editor.World.RoomSceneCompositionFoundationTests, which is
    // split across RoomSceneComposerTests.cs and RoomSceneContractTests.cs. The contract asks for a
    // distinct type so that a test-path filter naming this file resolves to exactly one file: a
    // filter that lands on a partial class selects whatever other files contribute to it, and a
    // filter naming a type that does not resolve selects nothing at all and still exits clean.
    //
    // The same expectations are asserted twice: once against the C# source
    // (CreateCanonicalRooms/CreateCanonicalDoors) and once against the generated
    // RoomSceneCatalog.asset, so the pair proves the source and the serialized asset agree rather
    // than only proving the source agrees with itself.
    public sealed class RoomSceneCatalogGeometryTests
    {
        // Contract order matters and is asserted: RuinedEntry, BoneArchive, ChapelOfAsh,
        // LowerVault, FinalRoom.
        //
        // RuinedEntry is listed even though NSC-101 does not change it. The contract is explicit
        // about why: a fixture that checked only the four changed rooms would still pass if
        // RuinedEntry's bounds were corrupted. An unchanged value is only verified if something
        // asserts it.
        private static readonly (RoomId Room, string ScenePath, float MinX, float MaxX, float MinZ, float MaxZ)[]
            ExpectedRooms =
            {
                (RoomId.RuinedEntry, "Assets/Scenes/Rooms/RuinedEntry.unity", -14f, 14f, -26f, 0f),
                (RoomId.BoneArchive, "Assets/Scenes/Rooms/BoneArchive.unity", -12f, 12f, 0f, 20f),
                (RoomId.ChapelOfAsh, "Assets/Scenes/Rooms/ChapelOfAsh.unity", -18f, 18f, 20f, 54f),
                (RoomId.LowerVault, "Assets/Scenes/Rooms/LowerVault.unity", -20f, 20f, 54f, 76f),
                (RoomId.FinalRoom, "Assets/Scenes/Rooms/FinalRoom.unity", -15f, 15f, 76f, 104f),
            };

        // D1 and D2 are unchanged by NSC-101 and are asserted for the same reason as RuinedEntry.
        private const float ExpectedOpeningWidth = 3f;

        private static readonly (DoorId Door, RoomId Exit, RoomId Entry, bool IsFinal, float CenterX, float CenterZ)[]
            ExpectedDoors =
            {
                (DoorId.D1, RoomId.RuinedEntry, RoomId.BoneArchive, false, 0f, 0f),
                (DoorId.D2, RoomId.BoneArchive, RoomId.ChapelOfAsh, false, 6f, 20f),
                (DoorId.D3, RoomId.ChapelOfAsh, RoomId.LowerVault, false, -8f, 54f),
                (DoorId.D4, RoomId.LowerVault, RoomId.FinalRoom, false, 4f, 76f),
                (DoorId.D5, RoomId.FinalRoom, RoomId.FinalRoom, true, 0f, 104f),
            };

        [Test]
        public void CanonicalRoomSource_MatchesEveryContractValue()
        {
            AssertRooms(RoomSceneCatalog.CreateCanonicalRooms(), "CreateCanonicalRooms()");
        }

        [Test]
        public void CanonicalDoorSource_MatchesEveryContractValue()
        {
            AssertDoors(RoomSceneCatalog.CreateCanonicalDoors(), "CreateCanonicalDoors()");
        }

        [Test]
        public void GeneratedCatalogAsset_RoomsMatchTheSameContractValues()
        {
            AssertRooms(LoadCommittedCatalog().Rooms.ToArray(), RoomSceneCatalog.AssetPath);
        }

        [Test]
        public void GeneratedCatalogAsset_DoorsMatchTheSameContractValues()
        {
            AssertDoors(LoadCommittedCatalog().Doors.ToArray(), RoomSceneCatalog.AssetPath);
        }

        // AssetDatabase.LoadAssetAtPath, deliberately, not RoomSceneCatalog.LoadOrBuildAsset: the
        // latter would CREATE the asset when it is missing, so a run against a tree where the asset
        // had not been regenerated would silently write into the repository and then pass. Other
        // gates on this work assert the tree is unchanged by the tests, and a test that can mutate
        // the repository cannot support that claim. A missing asset is a failure here, not a
        // prompt to build one.
        private static RoomSceneCatalog LoadCommittedCatalog()
        {
            var catalog = AssetDatabase.LoadAssetAtPath<RoomSceneCatalog>(RoomSceneCatalog.AssetPath);
            Assert.IsNotNull(catalog,
                $"The committed catalog asset is missing at {RoomSceneCatalog.AssetPath}. Run " +
                "\"No Safe Circle/World/Build Room Scene Catalog\" to regenerate it from the C# " +
                "source; this test will not create it.");
            return catalog;
        }

        private static void AssertRooms(RoomSceneCatalog.RoomCatalogEntry[] actual, string source)
        {
            Assert.AreEqual(ExpectedRooms.Length, actual.Length,
                $"{source} must contain exactly {ExpectedRooms.Length} room entries.");

            for (var index = 0; index < ExpectedRooms.Length; index++)
            {
                var expected = ExpectedRooms[index];
                var entry = actual[index];
                var where = $"{source} room[{index}] (expected {expected.Room})";

                Assert.AreEqual(expected.Room, entry.RoomId, $"{where}: room order or identity differs.");
                Assert.AreEqual(expected.ScenePath, entry.SceneAssetPath, $"{where}: sceneAssetPath differs.");
                Assert.AreEqual(expected.MinX, entry.Bounds.MinX, $"{where}: RoomBounds.MinX differs.");
                Assert.AreEqual(expected.MaxX, entry.Bounds.MaxX, $"{where}: RoomBounds.MaxX differs.");
                Assert.AreEqual(expected.MinZ, entry.Bounds.MinZ, $"{where}: RoomBounds.MinZ differs.");
                Assert.AreEqual(expected.MaxZ, entry.Bounds.MaxZ, $"{where}: RoomBounds.MaxZ differs.");
            }
        }

        private static void AssertDoors(RoomSceneCatalog.DoorSequenceEntry[] actual, string source)
        {
            Assert.AreEqual(ExpectedDoors.Length, actual.Length,
                $"{source} must contain exactly {ExpectedDoors.Length} door entries.");

            for (var index = 0; index < ExpectedDoors.Length; index++)
            {
                var expected = ExpectedDoors[index];
                var entry = actual[index];
                var where = $"{source} door[{index}] (expected {expected.Door})";

                Assert.AreEqual(expected.Door, entry.DoorId, $"{where}: door order or identity differs.");
                Assert.AreEqual(expected.Exit, entry.ExitRoom, $"{where}: exit room differs.");
                Assert.AreEqual(expected.Entry, entry.EntryRoom, $"{where}: entry room differs.");
                Assert.AreEqual(expected.IsFinal, entry.IsFinal, $"{where}: isFinal differs.");
                Assert.AreEqual(expected.CenterX, entry.ExpectedGroundCenter.x,
                    $"{where}: ExpectedGroundCenter.x differs.");
                Assert.AreEqual(expected.CenterZ, entry.ExpectedGroundCenter.y,
                    $"{where}: ExpectedGroundCenter.z differs.");
                Assert.AreEqual(ExpectedOpeningWidth, entry.OpeningWidth, $"{where}: openingWidth differs.");
            }

            // Asserted as a set property as well as per-entry: the loop above would still pass if a
            // second door were marked final and the table were ever edited to match it.
            var finalDoors = actual.Where(entry => entry.IsFinal).Select(entry => entry.DoorId).ToArray();
            Assert.AreEqual(1, finalDoors.Length,
                $"{source}: exactly one door may be final, found [{string.Join(", ", finalDoors)}].");
            Assert.AreEqual(DoorId.D5, finalDoors[0], $"{source}: D5 must be the only final door.");
        }
    }
}
