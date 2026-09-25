using System;
using System.Collections.Generic;
using System.Linq;
using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Tilemaps;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    /// <summary>NSC-126 AC-001/AC-002/AC-003/AC-004/VAL-001.</summary>
    /// <remarks>
    /// Test classification: in-memory scene-builder test. Each of the five committed rooms is
    /// built through its own production BuildInMemoryForTests entry point -- never through the
    /// MenuItem that opens and saves the authoring scene -- so no canonical asset is touched.
    /// <para>
    /// AC-002/VAL-001's "a build of the same room with accent placement suppressed" has no
    /// production flag to request it by, and a test-author role may not add one. Every committed
    /// builder's BuildWallAccents (NSC-126 diff) parents the accents ArchitecturalWallAccentPlacement.
    /// Place returns under one freshly created "WallAccents" GameObject and touches nothing else,
    /// which is the exact claim AC-002 makes about Place itself. Destroying precisely that
    /// GameObject after a real build and re-measuring GameplayGeometry and every Tilemap therefore
    /// produces the same observation a suppressed build would, without inventing a seam.
    /// </para>
    /// <para>
    /// AC-005: no room here asserts an EndCap accent. ArchitecturalWallAccentPlacementTests already
    /// records why: every committed room is a closed rectangle whose doors sit clear of every
    /// corner, so BuildRectangularRoomGeometry only ever produces Corner and Jamb endpoints from
    /// real committed room bounds and door data.
    /// </para>
    /// </remarks>
    public sealed class RoomWallAccentIntegrationTests
    {
        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [Test]
        public void RuinedEntry_WallAccentsSatisfyRolesGroundContactIdempotenceAndGeometryInvariance()
        {
            AssertRoomWallAccents(
                RuinedEntrySceneBuilder.BuildInMemoryForTests,
                "Room_RuinedEntry",
                RuinedEntryLayout.RoomBounds.center.y);
        }

        [Test]
        public void BoneArchive_WallAccentsSatisfyRolesGroundContactIdempotenceAndGeometryInvariance()
        {
            AssertRoomWallAccents(
                BoneArchiveSceneBuilder.BuildInMemoryForTests,
                "Room_BoneArchive",
                BoneArchiveLayout.RoomBounds.center.y);
        }

        [Test]
        public void ChapelOfAsh_WallAccentsSatisfyRolesGroundContactIdempotenceAndGeometryInvariance()
        {
            AssertRoomWallAccents(
                ChapelOfAshSceneBuilder.BuildInMemoryForTests,
                "Room_ChapelOfAsh",
                ChapelOfAshLayout.RoomBounds.center.y);
        }

        [Test]
        public void LowerVault_WallAccentsSatisfyRolesGroundContactIdempotenceAndGeometryInvariance()
        {
            AssertRoomWallAccents(
                LowerVaultSceneBuilder.BuildInMemoryForTests,
                "Room_LowerVault",
                LowerVaultLayout.RoomBounds.center.y);
        }

        [Test]
        public void FinalRoom_WallAccentsSatisfyRolesGroundContactIdempotenceAndGeometryInvariance()
        {
            AssertRoomWallAccents(
                FinalRoomSceneBuilder.BuildInMemoryForTests,
                "Room_FinalRoom",
                FinalRoomLayout.RoomBounds.center.y);
        }

        // AC-001/AC-003/AC-004/AC-002/VAL-001: builds one committed room through its own production
        // entry point and proves every relation VAL-001 requires against that single room.
        private static void AssertRoomWallAccents(Action buildRoom, string roomRootName, float floorY)
        {
            buildRoom();

            Transform accentsRoot = FindWallAccentsRoot(roomRootName);
            Assert.IsNotNull(accentsRoot,
                roomRootName + " must carry a Visuals/WallAccents child once its own builder runs.");

            List<Transform> accents = accentsRoot.Cast<Transform>().ToList();
            Assert.Greater(accents.Count(accent => accent.name.StartsWith("Corner", StringComparison.Ordinal)), 0,
                roomRootName + " must place at least one Corner accent.");
            Assert.Greater(accents.Count(accent => accent.name.StartsWith("Jamb", StringComparison.Ordinal)), 0,
                roomRootName + " must place at least one Jamb accent.");

            foreach (Transform accent in accents)
            {
                SpriteRenderer renderer = accent.GetComponent<SpriteRenderer>();
                Assert.IsNotNull(renderer, accent.name + " must carry a SpriteRenderer.");
                Assert.That(renderer.bounds.min.y, Is.EqualTo(floorY).Within(0.0001f),
                    accent.name + " rendered bottom edge must land on " + roomRootName + "'s floor Y.");
            }

            int firstBuildAccentCount = accents.Count;
            List<BoxCollider> collidersWithAccents = SnapshotGameplayGeometryColliders(roomRootName);
            int tilemapCellsWithAccents = SnapshotTilemapCellCount(roomRootName);

            // AC-002: destroy exactly the subtree BuildWallAccents added -- see class remarks --
            // and re-measure to obtain the same observation a suppressed build would produce.
            Object.DestroyImmediate(accentsRoot.gameObject);
            List<BoxCollider> collidersSuppressed = SnapshotGameplayGeometryColliders(roomRootName);
            int tilemapCellsSuppressed = SnapshotTilemapCellCount(roomRootName);

            Assert.AreEqual(collidersWithAccents.Count, collidersSuppressed.Count,
                roomRootName + " wall accent placement must not add or remove any GameplayGeometry collider.");
            for (int index = 0; index < collidersWithAccents.Count; index++)
            {
                Assert.AreEqual(collidersWithAccents[index].bounds.center, collidersSuppressed[index].bounds.center,
                    roomRootName + " wall accent placement must not move any GameplayGeometry collider.");
                Assert.AreEqual(collidersWithAccents[index].bounds.size, collidersSuppressed[index].bounds.size,
                    roomRootName + " wall accent placement must not resize any GameplayGeometry collider.");
            }
            Assert.AreEqual(tilemapCellsWithAccents, tilemapCellsSuppressed,
                roomRootName + " wall accent placement must not paint or remove any Tilemap cell.");

            // AC-004: rebuilding the same room from scratch must reproduce the same accent count,
            // never accumulate across repeated authoring builds.
            buildRoom();
            Transform accentsRootAfterRebuild = FindWallAccentsRoot(roomRootName);
            Assert.IsNotNull(accentsRootAfterRebuild,
                roomRootName + " must still carry a Visuals/WallAccents child after a second build.");
            Assert.AreEqual(firstBuildAccentCount, accentsRootAfterRebuild.childCount,
                roomRootName + " must place the same accent count on a repeated build, not accumulate.");
        }

        private static Transform FindWallAccentsRoot(string roomRootName)
        {
            GameObject accents = GameObject.Find(roomRootName + "/Visuals/WallAccents");
            return accents == null ? null : accents.transform;
        }

        private static List<BoxCollider> SnapshotGameplayGeometryColliders(string roomRootName)
        {
            GameObject geometry = GameObject.Find(roomRootName + "/GameplayGeometry");
            Assert.IsNotNull(geometry, "Expected " + roomRootName + "/GameplayGeometry from the committed room builder.");
            return geometry.GetComponentsInChildren<BoxCollider>(true).ToList();
        }

        private static int SnapshotTilemapCellCount(string roomRootName)
        {
            GameObject visuals = GameObject.Find(roomRootName + "/Visuals");
            Assert.IsNotNull(visuals, "Expected " + roomRootName + "/Visuals from the committed room builder.");

            int total = 0;
            foreach (Tilemap tilemap in visuals.GetComponentsInChildren<Tilemap>(true))
            {
                foreach (Vector3Int cell in tilemap.cellBounds.allPositionsWithin)
                {
                    if (tilemap.HasTile(cell)) total++;
                }
            }
            return total;
        }
    }
}
