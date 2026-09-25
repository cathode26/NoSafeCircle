using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Tilemaps;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    // NSC-049 AC-001/VAL-001: committed-scene conformance checks for the single continuous world.
    public sealed class FiveRoomCompositionTests
    {
        private const string ScenePath = "Assets/Scenes/DoorPrototype.unity";

        [Test]
        public void CanonicalScene_ContainsAllRoomsAtApprovedBounds_AndKeepsSimulationSeparate()
        {
            var roomCatalog = RoomSceneCatalog.CreateCanonicalRooms();
            var sourceBytes = roomCatalog.ToDictionary(
                room => room.SceneAssetPath, room => File.ReadAllBytes(room.SceneAssetPath));
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            try
            {
                var world = scene.GetRootGameObjects().SingleOrDefault(root => root.name == RoomSceneComposer.WorldRootName);
                Assert.IsNotNull(world, "Canonical scene must contain the composed World root.");
                var roomsRoot = world.transform.Find(RoomSceneComposer.ComposedRoomsRootName);
                Assert.IsNotNull(roomsRoot, "Canonical scene must contain World/ComposedRooms.");

                foreach (var room in roomCatalog)
                {
                    var roomRoot = roomsRoot.Find("Room_" + room.RoomId);
                    Assert.IsNotNull(roomRoot, $"Missing composed room {room.RoomId}.");
                    Assert.IsNotNull(roomRoot.Find("Visuals"), $"{room.RoomId} is missing Visuals.");
                    Assert.IsNotNull(roomRoot.Find("GameplayGeometry"), $"{room.RoomId} is missing GameplayGeometry.");
                    Assert.IsNotNull(roomRoot.Find("DoorAnchors"), $"{room.RoomId} is missing DoorAnchors.");
                    Assert.IsTrue(roomRoot.Find("Visuals") != roomRoot.Find("GameplayGeometry"));
                }

                Assert.AreEqual(5, roomsRoot.childCount, "The canonical composition must contain exactly five rooms.");
                var rootNames = scene.GetRootGameObjects().Select(root => root.name).ToArray();
                CollectionAssert.DoesNotContain(rootNames, "Floor", "Legacy prototype floor must be removed.");
                CollectionAssert.DoesNotContain(rootNames, "Walls", "Legacy prototype walls must be removed.");
                CollectionAssert.DoesNotContain(rootNames, "IsometricVisualGrid",
                    "Legacy prototype visual grid must be removed.");
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, false);
                foreach (var pair in sourceBytes)
                {
                    CollectionAssert.AreEqual(pair.Value, File.ReadAllBytes(pair.Key),
                        $"Composition must not modify source scene {pair.Key}.");
                }
            }
        }

        // NSC-049 AC-003/VAL-003: the composed scene owns exactly one Player and one
        // PlayerSpawn, moved to the Ruined Entry start point NSC-044 records in
        // RuinedEntryLayout.cs, through DoorPrototypeGlobalSceneBuilder - never a second copy.
        [Test]
        public void ComposedScene_HasExactlyOnePlayerAndPlayerSpawn_AtRuinedEntryStart()
        {
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            try
            {
                var players = scene.GetRootGameObjects().Where(root => root.name == "Player").ToArray();
                var spawns = scene.GetRootGameObjects().Where(root => root.name == "PlayerSpawn").ToArray();

                Assert.AreEqual(1, players.Length, "VAL-003: canonical scene must contain exactly one Player.");
                Assert.AreEqual(1, spawns.Length, "VAL-003: canonical scene must contain exactly one PlayerSpawn.");

                var player = players[0];
                var spawn = spawns[0];
                var expectedStart = RuinedEntryLayout.PlayerStart;

                Assert.AreEqual(expectedStart.x, player.transform.position.x, 0.01f,
                    "VAL-003/AC-003: Player must sit at the Ruined Entry start point RuinedEntryLayout.cs records.");
                Assert.AreEqual(expectedStart.z, player.transform.position.z, 0.01f,
                    "VAL-003/AC-003: Player must sit at the Ruined Entry start point RuinedEntryLayout.cs records.");
                Assert.AreEqual(player.transform.position, spawn.transform.position,
                    "VAL-003: PlayerSpawn must match the Player's own position rather than a second, diverging copy.");
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, false);
            }
        }

        // NSC-049 AC-004/VAL-004: the shared-boundary wall rule at each of the four shared
        // room boundaries (Z0, Z20, Z54, Z76). Opens the composed scene deliberately and closes
        // it without saving; never opens or writes to a room source scene.
        [Test]
        public void ComposedScene_ReconcilesAllFourSharedRoomBoundaries()
        {
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            try
            {
                var world = scene.GetRootGameObjects().Single(root => root.name == RoomSceneComposer.WorldRootName);
                var roomsRoot = world.transform.Find(RoomSceneComposer.ComposedRoomsRootName);

                var ruinedEntry = roomsRoot.Find("Room_" + RoomId.RuinedEntry);
                var boneArchive = roomsRoot.Find("Room_" + RoomId.BoneArchive);
                var chapelOfAsh = roomsRoot.Find("Room_" + RoomId.ChapelOfAsh);
                var lowerVault = roomsRoot.Find("Room_" + RoomId.LowerVault);
                var finalRoom = roomsRoot.Find("Room_" + RoomId.FinalRoom);

                Assert.IsNotNull(ruinedEntry);
                Assert.IsNotNull(boneArchive);
                Assert.IsNotNull(chapelOfAsh);
                Assert.IsNotNull(lowerVault);
                Assert.IsNotNull(finalRoom);

                // Z0: Ruined Entry (south) / Bone Archive (north). Bone Archive's own span
                // [-12,12] is narrower than Ruined Entry's [-14,14], so only the shared span is
                // removed from Ruined Entry's own NorthFullWallTilemap; its west/east flanks stay.
                AssertPartialBoundary(
                    "Z0", southRoot: ruinedEntry, northRoot: boneArchive,
                    northRoomMinX: -12f, northRoomMaxX: 12f,
                    visualGapMinX: -2f, visualGapMaxX: 2f,
                    flankMinX: -14f, flankMaxX: 14f,
                    clearMinX: -1.5f, clearMaxX: 1.5f);
                AssertBoundaryCollider(
                    keepRoomRoot: ruinedEntry, keepPieceName: "NorthWallWestCollision",
                    removeRoomRoot: boneArchive, removePieceName: "SouthWallWestCollision",
                    clearMinX: -1.5f, clearMaxX: 1.5f, boundaryLabel: "Z0/West");
                AssertBoundaryCollider(
                    keepRoomRoot: ruinedEntry, keepPieceName: "NorthWallEastCollision",
                    removeRoomRoot: boneArchive, removePieceName: "SouthWallEastCollision",
                    clearMinX: -1.5f, clearMaxX: 1.5f, boundaryLabel: "Z0/East");

                // Z20: Bone Archive (south) / Chapel of Ash (north). Chapel of Ash's span
                // [-18,18] contains all of Bone Archive's [-12,12], so Bone Archive's own
                // NorthFullWallTilemap is removed in full.
                AssertFullyRemovedBoundary(
                    "Z20", southRoot: boneArchive, northRoot: chapelOfAsh,
                    visualGapMinX: 4f, visualGapMaxX: 8f,
                    northRoomMinX: -18f, northRoomMaxX: 18f,
                    clearMinX: 4.5f, clearMaxX: 7.5f);
                AssertBoundaryCollider(
                    keepRoomRoot: chapelOfAsh, keepPieceName: "SouthWallWestCollision",
                    removeRoomRoot: boneArchive, removePieceName: "NorthWallWestCollision",
                    clearMinX: 4.5f, clearMaxX: 7.5f, boundaryLabel: "Z20/West");
                AssertBoundaryCollider(
                    keepRoomRoot: chapelOfAsh, keepPieceName: "SouthWallEastCollision",
                    removeRoomRoot: boneArchive, removePieceName: "NorthWallEastCollision",
                    clearMinX: 4.5f, clearMaxX: 7.5f, boundaryLabel: "Z20/East");

                // Z54: Chapel of Ash (south) / Lower Vault (north). Lower Vault's span [-20,20]
                // contains all of Chapel of Ash's [-18,18], so Chapel of Ash's own
                // NorthFullWallTilemap is removed in full.
                AssertFullyRemovedBoundary(
                    "Z54", southRoot: chapelOfAsh, northRoot: lowerVault,
                    visualGapMinX: -10f, visualGapMaxX: -6f,
                    northRoomMinX: -20f, northRoomMaxX: 20f,
                    clearMinX: -9.5f, clearMaxX: -6.5f);
                AssertBoundaryCollider(
                    keepRoomRoot: lowerVault, keepPieceName: "SouthWallWestCollision",
                    removeRoomRoot: chapelOfAsh, removePieceName: "NorthWallWestCollision",
                    clearMinX: -9.5f, clearMaxX: -6.5f, boundaryLabel: "Z54/West");
                AssertBoundaryCollider(
                    keepRoomRoot: lowerVault, keepPieceName: "SouthWallEastCollision",
                    removeRoomRoot: chapelOfAsh, removePieceName: "NorthWallEastCollision",
                    clearMinX: -9.5f, clearMaxX: -6.5f, boundaryLabel: "Z54/East");

                // Z76: Lower Vault (south) / Final Room (north). Final Room's own span [-15,15]
                // is narrower than Lower Vault's [-20,20], so only the shared span is removed
                // from Lower Vault's own NorthFullWallTilemap; its west/east flanks stay.
                AssertPartialBoundary(
                    "Z76", southRoot: lowerVault, northRoot: finalRoom,
                    northRoomMinX: -15f, northRoomMaxX: 15f,
                    visualGapMinX: 2f, visualGapMaxX: 6f,
                    flankMinX: -20f, flankMaxX: 20f,
                    clearMinX: 2.5f, clearMaxX: 5.5f);
                AssertBoundaryCollider(
                    keepRoomRoot: lowerVault, keepPieceName: "NorthWallWestCollision",
                    removeRoomRoot: finalRoom, removePieceName: "SouthWallWestCollision",
                    clearMinX: 2.5f, clearMaxX: 5.5f, boundaryLabel: "Z76/West");
                AssertBoundaryCollider(
                    keepRoomRoot: lowerVault, keepPieceName: "NorthWallEastCollision",
                    removeRoomRoot: finalRoom, removePieceName: "SouthWallEastCollision",
                    clearMinX: 2.5f, clearMaxX: 5.5f, boundaryLabel: "Z76/East");
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, false);
            }
        }

        // South room's own north-facing wall visual keeps its own two flanks and loses exactly
        // the shared span; north room's own south-facing low wall visual keeps every cell
        // outside its own door gap. Neither the door's collider-clear interval nor the shared
        // span may carry a painted wall cell from either tilemap afterward.
        private static void AssertPartialBoundary(
            string label, Transform southRoot, Transform northRoot,
            float northRoomMinX, float northRoomMaxX,
            float visualGapMinX, float visualGapMaxX,
            float flankMinX, float flankMaxX,
            float clearMinX, float clearMaxX)
        {
            var northLow = FindWallTilemap(northRoot, "SouthLowWallTilemap");
            Assert.IsNotNull(northLow, $"{label}: expected {northRoot.name}'s SouthLowWallTilemap.");
            Assert.Greater(
                CountPaintedCellsInXRange(northLow, northRoomMinX, visualGapMinX) +
                CountPaintedCellsInXRange(northLow, visualGapMaxX, northRoomMaxX),
                0, $"{label}: {northRoot.name}'s SouthLowWallTilemap must keep cells outside its own door gap.");

            var southFull = FindWallTilemap(southRoot, "NorthFullWallTilemap");
            Assert.IsNotNull(southFull, $"{label}: expected {southRoot.name}'s NorthFullWallTilemap.");
            Assert.AreEqual(0, CountPaintedCellsInXRange(southFull, northRoomMinX, northRoomMaxX),
                $"{label}: {southRoot.name}'s NorthFullWallTilemap cells over the shared span must be removed.");
            Assert.Greater(CountPaintedCellsInXRange(southFull, flankMinX, northRoomMinX), 0,
                $"{label}: {southRoot.name}'s NorthFullWallTilemap must keep its west flank outside the shared span.");
            Assert.Greater(CountPaintedCellsInXRange(southFull, northRoomMaxX, flankMaxX), 0,
                $"{label}: {southRoot.name}'s NorthFullWallTilemap must keep its east flank outside the shared span.");

            Assert.AreEqual(0, CountPaintedCellsInXRange(northLow, clearMinX, clearMaxX),
                $"{label}: no wall visual may occupy the door's collider-clear interval.");
            Assert.AreEqual(0, CountPaintedCellsInXRange(southFull, clearMinX, clearMaxX),
                $"{label}: no wall visual may occupy the door's collider-clear interval.");
        }

        // Used when the northern room's own span fully contains the southern room's span, so the
        // southern room's own NorthFullWallTilemap is removed in full rather than partially.
        private static void AssertFullyRemovedBoundary(
            string label, Transform southRoot, Transform northRoot,
            float visualGapMinX, float visualGapMaxX,
            float northRoomMinX, float northRoomMaxX,
            float clearMinX, float clearMaxX)
        {
            var northLow = FindWallTilemap(northRoot, "SouthLowWallTilemap");
            Assert.IsNotNull(northLow, $"{label}: expected {northRoot.name}'s SouthLowWallTilemap.");
            Assert.Greater(
                CountPaintedCellsInXRange(northLow, northRoomMinX, visualGapMinX) +
                CountPaintedCellsInXRange(northLow, visualGapMaxX, northRoomMaxX),
                0, $"{label}: {northRoot.name}'s SouthLowWallTilemap must keep cells outside its own door gap.");

            var southFull = FindWallTilemap(southRoot, "NorthFullWallTilemap");
            Assert.IsNotNull(southFull, $"{label}: expected {southRoot.name}'s NorthFullWallTilemap.");
            Assert.AreEqual(0, CountPaintedCellsInXRange(southFull, -1000f, 1000f),
                $"{label}: {southRoot.name}'s NorthFullWallTilemap must be removed in full because the " +
                "northern room's span contains all of it.");

            Assert.AreEqual(0, CountPaintedCellsInXRange(northLow, clearMinX, clearMaxX),
                $"{label}: no wall visual may occupy the door's collider-clear interval.");
        }

        // Exactly one 2.5-unit gameplay wall BoxCollider remains along this part of the
        // boundary (unresized), and the piece it contained is removed by name rather than
        // resized.
        private static void AssertBoundaryCollider(
            Transform keepRoomRoot, string keepPieceName,
            Transform removeRoomRoot, string removePieceName,
            float clearMinX, float clearMaxX, string boundaryLabel)
        {
            var keepPiece = FindGameplayGeometryChild(keepRoomRoot, keepPieceName);
            Assert.IsNotNull(keepPiece,
                $"{boundaryLabel}: expected '{keepPieceName}' to remain under {keepRoomRoot.name}.");
            var keepCollider = keepPiece.GetComponent<BoxCollider>();
            Assert.IsNotNull(keepCollider, $"{boundaryLabel}: expected '{keepPieceName}' to carry a BoxCollider.");
            Assert.AreEqual(2.5f, keepCollider.size.y, 0.01f,
                $"{boundaryLabel}: '{keepPieceName}' must remain a 2.5-unit gameplay wall BoxCollider (unresized).");

            var removedPiece = FindGameplayGeometryChild(removeRoomRoot, removePieceName);
            Assert.IsNull(removedPiece,
                $"{boundaryLabel}: expected the contained piece '{removePieceName}' under {removeRoomRoot.name} " +
                "to be removed.");

            var keptBounds = keepCollider.bounds;
            Assert.IsTrue(keptBounds.max.x <= clearMinX + 0.01f || keptBounds.min.x >= clearMaxX - 0.01f,
                $"{boundaryLabel}: the surviving '{keepPieceName}' collider must not cover the door's " +
                "collider-clear interval.");
        }

        private static Tilemap FindWallTilemap(Transform roomRoot, string tilemapName)
        {
            var visuals = roomRoot.Find("Visuals");
            if (visuals == null) return null;

            foreach (var tilemap in visuals.GetComponentsInChildren<Tilemap>(true))
            {
                if (tilemap.name == tilemapName) return tilemap;
            }

            return null;
        }

        private static int CountPaintedCellsInXRange(Tilemap tilemap, float minX, float maxX)
        {
            if (tilemap == null) return 0;

            const float tolerance = 0.01f;
            var count = 0;
            foreach (var cell in tilemap.cellBounds.allPositionsWithin)
            {
                if (!tilemap.HasTile(cell)) continue;

                var worldX = tilemap.GetCellCenterWorld(cell).x;
                if (worldX >= minX - tolerance && worldX <= maxX + tolerance) count++;
            }

            return count;
        }

        private static GameObject FindGameplayGeometryChild(Transform roomRoot, string name)
        {
            var gameplayGeometry = roomRoot.Find("GameplayGeometry");
            if (gameplayGeometry == null) return null;

            var found = gameplayGeometry.Find(name);
            return found != null ? found.gameObject : null;
        }
    }
}
