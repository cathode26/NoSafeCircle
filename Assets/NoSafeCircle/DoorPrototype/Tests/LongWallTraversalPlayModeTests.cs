using System.Collections;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-042 VAL-002: exercise the saved scene's PlayerMovement, wall Tilemap,
    // collision object, and camera sorting configuration with a representative long run.
    public sealed class LongWallTraversalPlayModeTests
    {
        [UnityTest]
        public IEnumerator SavedScene_WizardTraversesBothSidesAndCrossesLongWallAtD1WithCorrectSorting()
        {
            yield return SceneManager.LoadSceneAsync("DoorPrototype", LoadSceneMode.Single);
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            Assert.IsTrue(scene.IsValid() && scene.isLoaded);

            GameObject player = FindRoot(scene, "Player");
            PlayerMovement movement = player.GetComponent<PlayerMovement>();
            CharacterController controller = player.GetComponent<CharacterController>();
            SpriteRenderer wizard = player.transform.Find("Visual")?.GetComponent<SpriteRenderer>();
            Camera camera = FindRoot(scene, "Main Camera").GetComponent<Camera>();
            Transform room = FindRoot(scene, "World").transform
                .Find("ComposedRooms/Room_RuinedEntry");
            Assert.IsNotNull(room, "Use the room actually composed into the saved gameplay scene.");
            Tilemap wall = room.Find("Visuals/IsometricZAsY/NorthFullWallTilemap")
                ?.GetComponent<Tilemap>();
            BoxCollider collision = room.Find("GameplayGeometry/NorthWallWestCollision")
                ?.GetComponent<BoxCollider>();
            DoorInteractable door = FindRoot(scene, "DoorRoot").GetComponent<DoorInteractable>();
            Assert.IsNotNull(movement);
            Assert.IsNotNull(controller);
            Assert.IsNotNull(wizard);
            Assert.IsNotNull(camera);
            Assert.IsNotNull(wall,
                "The saved gameplay scene must contain the Ruined Entry room's composed twelve-cell WallTile Tilemap, not only its source room scene.");
            Assert.IsNotNull(collision,
                "The composed long wall must retain separate gameplay collision.");
            Assert.IsNotNull(door);

            // This used to read cell (-8,0,0) and require an unbroken run of twelve cells -14..-3.
            // NSC-049 AC-004's shared-boundary exclusion removes the SOUTHERN room's
            // NorthFullWallTilemap cells that fall inside the NORTHERN room's X span, so the
            // northern room's own south wall is the visible one where two rooms adjoin - NSC-046
            // records the same pattern at Z 54. Bone Archive spans X [-12,+12] and Ruined Entry
            // spans [-14,+14], so what survives here is the stretch at each END that no adjoining
            // room covers, and cell (-8,0,0) is now deliberately empty.
            //
            // Asserting the SHAPE rather than a cell list: a cell index is not a world X on this
            // isometric grid (cell n sits at n + 0.5), and hardcoding the survivors would go stale
            // the next time a room's width changes - which is exactly how the twelve-cell
            // expectation above came to be wrong.
            Vector3Int[] painted = wall.cellBounds.allPositionsWithin
                .Cast<Vector3Int>()
                .Where(candidate => wall.HasTile(candidate))
                .OrderBy(candidate => candidate.x)
                .ToArray();

            Assert.IsNotEmpty(painted,
                "Ruined Entry must keep the parts of its north wall that no adjoining room covers.");

            TileBase sharedTile = wall.GetTile(painted[0]);
            Assert.IsNotNull(sharedTile, "Use the Tile actually serialized in the saved room wall.");
            Assert.AreEqual("WallTile", sharedTile.name);
            foreach (Vector3Int cell in painted)
            {
                Assert.AreSame(sharedTile, wall.GetTile(cell),
                    "Every surviving north-wall cell must share the one serialized WallTile.");
            }

            Assert.IsFalse(wall.HasTile(new Vector3Int(0, 0, 0)),
                "AC-004 must clear this wall across the D1 opening so the doorway is passable.");
            Assert.IsTrue(painted.Any(cell => cell.x < 0) && painted.Any(cell => cell.x > 0),
                "The wall must survive at BOTH ends, beyond the adjoining room's width.");
            Assert.AreEqual(TilemapRenderer.Mode.Individual, wall.GetComponent<TilemapRenderer>().mode);
            Assert.AreEqual(wall.GetComponent<TilemapRenderer>().sortingOrder, wizard.sortingOrder);
            Assert.AreEqual(wall.GetComponent<TilemapRenderer>().sortingLayerName, wizard.sortingLayerName);

            // The wall LINE, not a painted cell: GetCellCenterWorld returns a coordinate whether or
            // not that cell carries a tile, and everything below measures the wizard's depth key
            // against that line as it moves around and through it. The gameplay collider is
            // unchanged by AC-004, which removes visual cells only, and D1 still provides the
            // opening for the crossing route.
            Vector3 center = wall.GetCellCenterWorld(new Vector3Int(-8, 0, 0));
            Assert.That(collision.bounds.size.x, Is.GreaterThan(10f));
            door.StartInteraction();
            door.Tick(10f);
            Assert.IsTrue(door.IsOpen, "D1 must be passable before the wizard crosses the wall line.");

            controller.enabled = false;
            player.transform.position = new Vector3(-10f, 0f, center.z - 2f);
            controller.enabled = true;
            movement.EnableGameplayInput();
            movement.CancelRequestedDestination();

            Vector3 sortAxis = camera.transparencySortAxis;
            float wallKey = Vector3.Dot(center, sortAxis);
            float frontKey = TraverseTo(movement, new Vector3(-4f, 0f, center.z - 2f), wizard, sortAxis);
            Assert.Greater(Mathf.Abs(frontKey - wallKey), 0.01f);
            TraverseTo(movement, new Vector3(0f, 0f, center.z - 2f), wizard, sortAxis);
            TraverseTo(movement, new Vector3(0f, 0f, center.z + 2f), wizard, sortAxis);
            float backKey = TraverseTo(movement, new Vector3(-4f, 0f, center.z + 2f), wizard, sortAxis);
            float farBackKey = TraverseTo(movement, new Vector3(-8f, 0f, center.z + 2f), wizard, sortAxis);

            Assert.Less((frontKey - wallKey) * (backKey - wallKey), 0f,
                "Real movement around the wall end must change wizard/wall depth order.");
            Assert.Greater((backKey - wallKey) * (farBackKey - wallKey), 0f,
                "Movement along the second side must keep the same depth relationship.");
        }

        [UnityTearDown]
        public IEnumerator UnloadSavedSceneWithoutSaving()
        {
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            if (!scene.IsValid() || !scene.isLoaded) yield break;
            Scene cleanup = SceneManager.CreateScene("LongWallTraversalTestCleanup");
            SceneManager.SetActiveScene(cleanup);
            yield return SceneManager.UnloadSceneAsync(scene);
        }

        private static float TraverseTo(
            PlayerMovement movement, Vector3 destination, SpriteRenderer wizard, Vector3 sortAxis)
        {
            movement.RequestDestination(destination);
            for (int step = 0; step < 160 && movement.HasActiveDestination; step++)
            {
                movement.Tick(0.05f);
            }
            Vector3 offset = movement.transform.position - destination;
            offset.y = 0f;
            Assert.Less(offset.magnitude, 0.15f,
                $"Wizard failed to reach {destination} along the loaded wall route; stopped at {movement.transform.position}.");
            return Vector3.Dot(wizard.transform.position, sortAxis);
        }

        private static GameObject FindRoot(Scene scene, string name)
        {
            GameObject root = scene.GetRootGameObjects().SingleOrDefault(item => item.name == name);
            Assert.IsNotNull(root, $"Expected one '{name}' root in saved scene {scene.path}.");
            return root;
        }
    }
}
