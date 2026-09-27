using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class EntryApproachPlayModeTests
    {
        [Test]
        public void OpenApproachHasFloorButNoSeparateRoomOrGatePartition()
        {
            GameObject template = Resources.Load<GameObject>("Spawners/EntryApproachFloorSpawner");
            Assert.IsNotNull(template);
            GameObject root = Object.Instantiate(template);
            try
            {
                EntryApproachFloorSpawner spawner = root.GetComponent<EntryApproachFloorSpawner>();
                Assert.IsNotNull(spawner);
                Assert.AreEqual(26f, RuinedEntryLayout.RoomBounds.size.z, 0.001f);
                Assert.AreEqual(RuinedEntryLayout.MinimumZ, EntryApproachLayout.GateZ);
                Assert.AreEqual(60f, EntryApproachLayout.ApproachBounds.size.z, 0.001f,
                    "Restoring the first room must retain the full outdoor chase run.");
                Assert.AreEqual(RuinedEntryLayout.PlayerStart,
                    EntryApproachLayout.FirstRoomArrival);
                Assert.AreEqual(1, spawner.Spawn());
                Assert.AreEqual(1, spawner.SpawnedCount);
                Assert.AreEqual(1, spawner.Spawn(),
                    "Rebuilding the open approach should preserve its single floor.");
                int activeRoots = 0;
                foreach (Transform child in root.transform)
                    if (child.gameObject.activeSelf) activeRoots++;
                Assert.AreEqual(1, activeRoots,
                    "Old approach floors must be disabled immediately on rebuild.");

                Transform floor = root.transform.Find("EntryApproachFloor");
                Assert.IsNotNull(floor);
                Tilemap grassBase = floor.GetComponentInChildren<Tilemap>();
                Tilemap grassDetail = floor.Find("GrassTilemap").GetComponent<Tilemap>();
                Assert.Greater(grassBase.GetUsedTilesCount(), 0);
                Assert.Greater(grassDetail.GetUsedTilesCount(), 0);
                Assert.AreEqual("Default", grassBase.GetComponent<TilemapRenderer>().sortingLayerName);
                Assert.AreEqual("Default", grassDetail.GetComponent<TilemapRenderer>().sortingLayerName);
                Vector3Int outsideDungeon = grassDetail.WorldToCell(
                    new Vector3(RuinedEntryLayout.MaximumX + 5f, 0f, -10f));
                Tile visibleGrass = grassDetail.GetTile<Tile>(outsideDungeon);
                Assert.IsNotNull(visibleGrass, "Grass should extend beside the Ruined Entry wall.");
                Assert.AreEqual("grass_tiles", visibleGrass.sprite.texture.name);
                Assert.AreEqual("grass_base",
                    grassBase.GetTile<Tile>(outsideDungeon).sprite.texture.name,
                    "Opaque grass must fill the atlas sprite's transparent corners.");
                Vector3Int chaseStart = grassDetail.WorldToCell(
                    EntryApproachLayout.WizardEntryStart);
                Assert.IsNotNull(grassDetail.GetTile(chaseStart),
                    "The outdoor run must stay grass-covered at the wizard's start.");
                Assert.IsNotNull(grassBase.GetTile(chaseStart),
                    "The opaque grass base must also reach the wizard's start.");
                Vector3Int beyondFinalRoom = grassDetail.WorldToCell(
                    new Vector3(FinalRoomLayout.MaximumX + 5f, 0f, FinalRoomLayout.MaximumZ - 2f));
                Assert.IsNotNull(grassDetail.GetTile(beyondFinalRoom),
                    "Grass should extend beside the last dungeon room as well.");
                BoxCollider floorCollision = floor.Find(FloorSpawner.FloorCollisionName).GetComponent<BoxCollider>();
                Assert.AreEqual(EntryApproachLayout.ApproachBounds.size.x, floorCollision.size.x, 0.001f);
                Assert.AreEqual(EntryApproachLayout.ApproachBounds.size.z, floorCollision.size.z, 0.001f);
                Assert.IsNull(root.transform.Find("EntryChamberGateWall"),
                    "The open approach must not rebuild the old interior gate partition.");
            }
            finally
            {
                Object.DestroyImmediate(root);
            }
        }

        // Play Mode component and read-only prefab regression: the entry door must retain
        // main's authored wall cutout through open, close, and interrupted-entry reset.
        [Test]
        public void StartDoorClosesOnlyAfterWizardEscapesAndBruteRemainsBehind()
        {
            Assert.AreEqual(5, DoorSpawner.CanonicalDoors().Length,
                "The cutscene gate must not be added to D1–D5 progression.");
            GameObject template = Resources.Load<GameObject>("Spawners/EntranceDoorSpawner");
            Assert.IsNotNull(template);
            GameObject root = Object.Instantiate(template);
            try
            {
                EntranceDoorSpawner spawner = root.GetComponent<EntranceDoorSpawner>();
                Assert.AreEqual(1, spawner.Spawn());
                EntranceDoor gate = root.GetComponentInChildren<EntranceDoor>();
                Assert.IsNotNull(gate);
                Assert.AreEqual(EntryApproachLayout.StartDoorCenter, gate.transform.position);
                Assert.AreEqual(RuinedEntryLayout.MinimumZ, gate.transform.position.z);
                Assert.IsFalse(gate.IsOpen);
                Transform visual = gate.transform.Find("DoorVisual");
                Assert.IsNotNull(visual);
                SpriteRenderer renderer = visual.GetComponentInChildren<SpriteRenderer>();
                BoxCollider blocker = visual.GetComponent<BoxCollider>();
                UnityEngine.AI.NavMeshObstacle obstacle =
                    gate.GetComponent<UnityEngine.AI.NavMeshObstacle>();
                Assert.IsNotNull(renderer);
                Assert.IsNotNull(blocker);
                Assert.IsNotNull(obstacle);
                Sprite sealedSprite = renderer.sprite;
                GameObject authoredDoor = Resources.Load<GameObject>("Doors/Door");
                Assert.IsNotNull(authoredDoor);
                SpriteMask authoredMask = authoredDoor.GetComponentInChildren<SpriteMask>(true);
                Assert.IsNotNull(authoredMask);
                SpriteMask[] masks = gate.GetComponentsInChildren<SpriteMask>(true);
                Assert.AreEqual(1, masks.Length,
                    "The entrance must copy the progression door's wall cutout.");
                SpriteMask mask = masks[0];
                Assert.AreEqual(gate.transform, mask.transform.parent,
                    "The cutout must remain independent of DoorVisual activation.");
                Assert.AreEqual(0, mask.GetComponentsInChildren<Collider>(true).Length,
                    "The cutout must not add a physical blocker.");
                Assert.AreSame(authoredMask.sprite, mask.sprite);
                Assert.AreSame(sealedSprite, mask.sprite,
                    "Open art must not replace the solid sealed silhouette.");
                Assert.AreEqual(authoredMask.alphaCutoff, mask.alphaCutoff);
                Assert.IsTrue(mask.isCustomRangeActive);
                Assert.AreEqual(authoredMask.backSortingLayerID, mask.backSortingLayerID);
                Assert.AreEqual(authoredMask.frontSortingLayerID, mask.frontSortingLayerID);
                Assert.AreEqual(authoredMask.backSortingOrder, mask.backSortingOrder);
                Assert.AreEqual(authoredMask.frontSortingOrder, mask.frontSortingOrder);
                Assert.AreEqual(SpriteMaskInteraction.None, renderer.maskInteraction,
                    "The mask cuts backing walls, never the door art itself.");
                AssertPersistentMask(mask, renderer, sealedSprite);
                Assert.IsTrue(blocker.enabled);
                Assert.IsTrue(obstacle.enabled);

                Assert.IsTrue(gate.OpenForEntryCutscene());
                Assert.IsTrue(visual.gameObject.activeInHierarchy,
                    "The open entrance must show the authored SW door art.");
                Assert.IsTrue(renderer.enabled);
                Assert.Greater(renderer.color.a, 0.9f);
                Assert.AreEqual("door_bonestone_open_SW_000", renderer.sprite.texture.name);
                Assert.AreNotSame(sealedSprite, renderer.sprite);
                AssertPersistentMask(mask, renderer, sealedSprite);
                Assert.IsFalse(blocker.enabled,
                    "The visible open door must not block the inbound wizard.");
                Assert.IsFalse(obstacle.enabled);
                Assert.IsFalse(gate.CloseAfterEntryCutscene(
                    new Vector3(-4f, 0f, -27f), EntryApproachLayout.PursuerStop));
                Assert.IsFalse(gate.CloseAfterEntryCutscene(
                    EntryApproachLayout.DoorCloseTrigger, new Vector3(-4f, 0f, -25f)));
                Assert.IsTrue(gate.CloseAfterEntryCutscene(
                    EntryApproachLayout.DoorCloseTrigger, EntryApproachLayout.PursuerStop));
                Assert.IsFalse(gate.IsOpen);
                Assert.IsTrue(visual.gameObject.activeSelf);
                Assert.AreSame(sealedSprite, renderer.sprite);
                AssertPersistentMask(mask, renderer, sealedSprite);
                Assert.IsTrue(blocker.enabled);
                Assert.IsTrue(obstacle.enabled);
                Assert.IsTrue(gate.OpenForEntryCutscene());
                AssertPersistentMask(mask, renderer, sealedSprite);
                gate.ResetDoor();
                Assert.IsFalse(gate.IsOpen,
                    "Interrupted entry must restore the gate to its sealed starting state.");
                Assert.IsTrue(visual.gameObject.activeSelf);
                Assert.AreSame(sealedSprite, renderer.sprite);
                AssertPersistentMask(mask, renderer, sealedSprite);
                Assert.IsTrue(blocker.enabled);
                Assert.IsTrue(obstacle.enabled);
            }
            finally
            {
                Object.DestroyImmediate(root);
            }
        }

        private static void AssertPersistentMask(
            SpriteMask mask, SpriteRenderer renderer, Sprite sealedSprite)
        {
            Assert.IsTrue(mask.enabled && mask.gameObject.activeInHierarchy,
                "The wall cutout must remain active in every entry-door state.");
            Assert.AreSame(sealedSprite, mask.sprite,
                "Changing the door state must preserve its solid wall-cutout silhouette.");
            Assert.Less(Vector3.Distance(renderer.transform.position, mask.transform.position), 0.001f,
                "The cutout must align with the door sprite's position.");
            Assert.Less(Quaternion.Angle(renderer.transform.rotation, mask.transform.rotation), 0.001f,
                "The cutout must occupy the door sprite's plane.");
            Assert.Less(Vector3.Distance(renderer.transform.lossyScale, mask.transform.lossyScale), 0.001f,
                "The cutout must match the door sprite's scale.");
        }
    }
}
