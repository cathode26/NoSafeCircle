using System;
using System.Collections.Generic;
using System.Reflection;
using NoSafeCircle.DoorPrototype.World;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.Tilemaps;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    /// <summary>
    /// The two hand-authored floor prefabs, read as assets without entering Play.
    /// </summary>
    /// <remarks>
    /// <para>
    /// WHAT THIS FIXTURE IS FOR. Under the instantiate-everything architecture a .prefab is a
    /// SOURCE FILE that people and agents hand-edit, and these two were written as YAML by hand.
    /// prefab_lint.py proves they are well formed; this proves what they MEAN: the spawner prefab
    /// binds every room to its own committed Tile, and the floor prefab is EMPTY - configuration
    /// and nothing else. The second half is the anti-bake assertion for floors, because a floor
    /// prefab with tiles painted into it passes every runtime test in FloorSpawnerPlayModeTests.
    /// </para>
    /// <para>
    /// The expected counts and paths are derived from RoomId and the folder conventions rather
    /// than read from the prefabs, so a prefab cannot supply its own expectations.
    /// </para>
    /// </remarks>
    public sealed class FloorPrefabTests
    {
        private const string SpawnerPrefabPath =
            "Assets/NoSafeCircle/DoorPrototype/Resources/Spawners/FloorSpawner.prefab";
        private const string RoomFloorPrefabPath =
            "Assets/NoSafeCircle/DoorPrototype/Resources/Floors/RoomFloor.prefab";
        private const string TileFolder =
            "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles";

        // The same contract-pinned literals FloorSpawnerPlayModeTests asserts at Play, asserted
        // here on the ASSET so a bad hand edit fails in the EditMode suite before anyone presses
        // Play. Sorting values are WorldSpriteConvention's, not the contract's "-100" (see the
        // PlayMode fixture for why).
        private static readonly Vector3 PinnedCellSize = new Vector3(1f, 0.5f, 1f);
        private static readonly Vector3 PinnedTilemapLocalPosition = new Vector3(0f, 0.01f, 0f);
        private static readonly Vector3 PinnedTilemapLocalEuler = new Vector3(-90f, 0f, 0f);
        private const string PinnedSortingLayerName = "WorldSprites";
        private const int PinnedFloorSortingOrder = short.MinValue;

        private static GameObject LoadPrefab(string path)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            Assert.IsNotNull(prefab, path + " did not load as a prefab. If it exists on disk, its YAML did not import.");
            return prefab;
        }

        private static void AssertVector(Vector3 expected, Vector3 actual, float tolerance, string what)
        {
            Assert.AreEqual(expected.x, actual.x, tolerance, what + " x: expected " + expected + ", got " + actual);
            Assert.AreEqual(expected.y, actual.y, tolerance, what + " y: expected " + expected + ", got " + actual);
            Assert.AreEqual(expected.z, actual.z, tolerance, what + " z: expected " + expected + ", got " + actual);
        }

        [Test]
        public void FloorSpawnerPrefab_IsInTheSpawnerFolderAndBindsTheFiveCommittedTiles()
        {
            GameObject prefab = LoadPrefab(SpawnerPrefabPath);

            // Reachable the way GameBootstrap reaches it, not only by asset path.
            Assert.IsNotNull(Resources.Load<GameObject>(GameBootstrap.SpawnerResourceFolder + "/FloorSpawner"),
                "Resources.Load cannot see the floor spawner under " + GameBootstrap.SpawnerResourceFolder
                + ", so GameBootstrap would never instantiate it.");

            var spawner = prefab.GetComponent<FloorSpawner>();
            Assert.IsNotNull(spawner, SpawnerPrefabPath + " carries no FloorSpawner component.");
            Assert.AreEqual(SpawnPhase.Rooms, ((ISpawner)spawner).Phase,
                "The floor spawner does not declare SpawnPhase.Rooms; every other family would build before the floor exists.");

            var serialized = new SerializedObject(spawner);

            SerializedProperty prefabReference = serialized.FindProperty("roomFloorPrefab");
            Assert.IsNotNull(prefabReference,
                "FloorSpawner no longer has a roomFloorPrefab field; update this check rather than deleting it.");
            Assert.IsNotNull(prefabReference.objectReferenceValue,
                "roomFloorPrefab is unassigned, so Spawn() logs an error and creates no floor.");
            Assert.AreEqual(RoomFloorPrefabPath, AssetDatabase.GetAssetPath(prefabReference.objectReferenceValue),
                "roomFloorPrefab points at a different prefab than the committed RoomFloor.");

            SerializedProperty rooms = serialized.FindProperty("rooms");
            Assert.IsNotNull(rooms, "FloorSpawner no longer has a rooms array; update this check rather than deleting it.");

            // ONE BINDING PER RoomId, and the count comes from the enum, not from the array.
            var all = (RoomId[])Enum.GetValues(typeof(RoomId));
            Assert.AreEqual(all.Length, rooms.arraySize,
                "The floor spawner binds " + rooms.arraySize + " rooms; RoomId declares " + all.Length
                + ". Every room needs exactly one floor binding.");

            var seen = new HashSet<RoomId>();
            for (int i = 0; i < rooms.arraySize; i++)
            {
                SerializedProperty element = rooms.GetArrayElementAtIndex(i);
                var room = (RoomId)element.FindPropertyRelative("room").intValue;
                Assert.IsTrue(seen.Add(room), "RoomId " + room + " is bound twice; the second floor would sit on the first.");

                Object tile = element.FindPropertyRelative("tile").objectReferenceValue;
                Assert.IsNotNull(tile, room + " has no floor Tile bound. Spawn() logs an error and skips the room.");
                Assert.IsInstanceOf<Tile>(tile, room + "'s binding is a " + tile.GetType().Name + ", not a Tile.");
                Assert.AreEqual(TileFolder + "/" + room + "FloorTile.asset", AssetDatabase.GetAssetPath(tile),
                    room + " is bound to '" + AssetDatabase.GetAssetPath(tile) + "', not to its own committed floor tile.");
            }

            Assert.AreEqual(all.Length, seen.Count, "Not every RoomId has a binding.");
        }

        [Test]
        public void FloorSpawnerDeclaresNoLifecycleEntryPointSoTheBootstrapOwnsTheMoment()
        {
            // Instantiating an ACTIVE prefab runs its Awake immediately and its OnEnable with it;
            // Start follows on the next frame. Any of the three calling Spawn() would place the
            // floors outside GameBootstrap's phase order, so none of them may exist. PropSpawner
            // kept a spawnOnAwake switch from its pre-bootstrap life; this lane has no such life
            // and no such switch - the absence of the method IS the guarantee.
            const BindingFlags declared = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.DeclaredOnly;
            foreach (string entryPoint in new[] { "Awake", "OnEnable", "Start" })
            {
                Assert.IsNull(typeof(FloorSpawner).GetMethod(entryPoint, declared),
                    "FloorSpawner declares " + entryPoint + "(). GameBootstrap owns the build order; a spawner "
                    + "that starts itself runs out of phase.");
            }
        }

        [Test]
        public void RoomFloorPrefab_HoldsNoTilesNoRoomAndNoBakedContent()
        {
            GameObject prefab = LoadPrefab(RoomFloorPrefabPath);

            Assert.AreEqual(1, prefab.GetComponentsInChildren<Grid>(true).Length, "The floor prefab must carry exactly one Grid.");

            Tilemap[] tilemaps = prefab.GetComponentsInChildren<Tilemap>(true);
            Assert.AreEqual(1, tilemaps.Length, "The floor prefab must carry exactly one Tilemap; found " + tilemaps.Length + ".");

            // THE ANTI-BAKE ASSERTION FOR FLOORS. Painting happens at Play from the layout; a
            // prefab with tiles in it is the bake with a different file extension, and it passes
            // every runtime test because the runtime paints over it with the same cells.
            Assert.AreEqual(0, tilemaps[0].GetUsedTilesCount(),
                "The floor prefab carries " + tilemaps[0].GetUsedTilesCount() + " painted tile(s). Nothing is "
                + "painted at edit time; FloorSpawner paints from the layout at Play.");

            Assert.AreEqual(1, prefab.GetComponentsInChildren<BoxCollider>(true).Length,
                "The floor prefab must carry exactly one BoxCollider - the FloorCollision.");
            Assert.IsNotNull(prefab.transform.Find(FloorSpawner.FloorCollisionName),
                "The floor prefab has no child named '" + FloorSpawner.FloorCollisionName + "'; FloorSpawner finds it by that name.");
            Assert.AreEqual(0, prefab.GetComponentsInChildren<SpriteRenderer>(true).Length,
                "The floor prefab carries a SpriteRenderer. Art is the Tile's; nothing else draws here.");
            Assert.AreEqual(0, prefab.GetComponentsInChildren<MeshRenderer>(true).Length,
                "The floor prefab carries a MeshRenderer. Blockout primitives do not belong in the runtime floor.");
            Assert.AreEqual(0, prefab.GetComponentsInChildren<TilemapCollider2D>(true).Length,
                "The floor prefab carries a TilemapCollider2D. The floor's physics is the FloorCollision box.");

            // NO ROOM IDENTITY: one prefab serves all five rooms, so its name is not a room's and
            // its transform is the identity the spawner expects to leave untouched.
            foreach (RoomId room in Enum.GetValues(typeof(RoomId)))
            {
                Assert.AreNotEqual(room + "Floor", prefab.name, "The floor prefab is named for one room; it serves all of them.");
            }

            AssertVector(Vector3.zero, prefab.transform.localPosition, 0.0001f, "RoomFloor root localPosition");
            AssertVector(Vector3.one, prefab.transform.localScale, 0.0001f, "RoomFloor root localScale");
        }

        [Test]
        public void RoomFloorPrefab_CarriesTheContractPinnedConfiguration()
        {
            GameObject prefab = LoadPrefab(RoomFloorPrefabPath);

            Assert.AreEqual(PinnedSortingLayerName, WorldSpriteConvention.SortingLayerName,
                "WorldSpriteConvention.SortingLayerName moved away from the literal this fixture pins.");
            Assert.AreEqual(PinnedFloorSortingOrder, WorldSpriteConvention.BackgroundGroundSortingOrder,
                "WorldSpriteConvention.BackgroundGroundSortingOrder moved away from the literal this fixture pins.");

            var grid = prefab.GetComponent<Grid>();
            Assert.IsNotNull(grid, "The Grid must sit on the prefab root, so cell coordinates are the root's coordinates.");
            AssertVector(PinnedCellSize, grid.cellSize, 0.0001f, "Grid.cellSize");
            AssertVector(Vector3.zero, grid.cellGap, 0.0001f, "Grid.cellGap");
            Assert.AreEqual(GridLayout.CellSwizzle.XYZ, grid.cellSwizzle, "Grid.cellSwizzle");
            Assert.AreEqual(GridLayout.CellLayout.Rectangle, grid.cellLayout,
                "Grid.cellLayout is " + grid.cellLayout + ". The contract leaves it at Rectangle; the isometric "
                + "projection is the camera's, and an isometric layout would project the floor twice.");

            var tilemap = prefab.GetComponentInChildren<Tilemap>(true);
            Assert.IsNotNull(tilemap, "No Tilemap in the floor prefab.");
            Assert.AreEqual("FloorTilemap", tilemap.name, "The floor Tilemap is not named FloorTilemap.");
            Assert.AreEqual(prefab.transform, tilemap.transform.parent, "FloorTilemap must be a direct child of the Grid root.");
            AssertVector(Vector3.zero, tilemap.tileAnchor, 0.0001f, "Tilemap.tileAnchor");
            Assert.AreEqual(Tilemap.Orientation.XY, tilemap.orientation, "Tilemap.orientation");
            AssertVector(PinnedTilemapLocalPosition, tilemap.transform.localPosition, 0.0001f, "FloorTilemap localPosition");
            Assert.Less(Quaternion.Angle(Quaternion.Euler(PinnedTilemapLocalEuler), tilemap.transform.localRotation), 0.01f,
                "FloorTilemap localRotation is " + tilemap.transform.localRotation.eulerAngles + ", not Euler" + PinnedTilemapLocalEuler + ".");
            AssertVector(Vector3.one, tilemap.transform.localScale, 0.0001f, "FloorTilemap localScale");

            var renderer = tilemap.GetComponent<TilemapRenderer>();
            Assert.IsNotNull(renderer, "FloorTilemap has no TilemapRenderer.");
            Assert.AreEqual(TilemapRenderer.Mode.Individual, renderer.mode, "TilemapRenderer.mode");
            Assert.AreEqual(TilemapRenderer.SortOrder.TopRight, renderer.sortOrder, "TilemapRenderer.sortOrder");
            Assert.AreEqual(PinnedSortingLayerName, renderer.sortingLayerName,
                "FloorTilemap is on sorting layer '" + renderer.sortingLayerName + "'; the layer is compared before the order.");
            Assert.AreEqual(PinnedFloorSortingOrder, renderer.sortingOrder,
                "FloorTilemap carries sortingOrder " + renderer.sortingOrder + "; the floor sits at the bottom of the range.");

            var collision = prefab.transform.Find(FloorSpawner.FloorCollisionName);
            Assert.IsNotNull(collision, "No '" + FloorSpawner.FloorCollisionName + "' child.");
            Assert.AreEqual(prefab.transform, collision.parent, "FloorCollision must be a direct child of the root.");
            AssertVector(Vector3.zero, collision.localPosition, 0.0001f, "FloorCollision localPosition");
            Assert.Less(Quaternion.Angle(Quaternion.identity, collision.localRotation), 0.01f, "FloorCollision is rotated.");
            var box = collision.GetComponent<BoxCollider>();
            Assert.IsNotNull(box, "FloorCollision carries no BoxCollider.");
            Assert.IsFalse(box.isTrigger, "FloorCollision is a trigger in the prefab; a CharacterController falls through a trigger.");
        }
    }
}
