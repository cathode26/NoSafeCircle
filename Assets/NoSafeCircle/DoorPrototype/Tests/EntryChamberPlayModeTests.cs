using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class EntryChamberPlayModeTests
    {
        [Test]
        public void AnnexHasWalkableFloorAndGateWallWithThreeUnitPassage()
        {
            GameObject template = Resources.Load<GameObject>("Spawners/EntryChamberAnnexSpawner");
            Assert.IsNotNull(template);
            GameObject root = Object.Instantiate(template);
            try
            {
                EntryChamberAnnexSpawner spawner = root.GetComponent<EntryChamberAnnexSpawner>();
                Assert.IsNotNull(spawner);
                Assert.AreEqual(14, spawner.Spawn());
                Assert.AreEqual(14, spawner.SpawnedCount);
                Assert.AreEqual(14, spawner.Spawn(),
                    "Rebuilding the annex should preserve the same floor and wall count.");
                int activeRoots = 0;
                foreach (Transform child in root.transform)
                    if (child.gameObject.activeSelf) activeRoots++;
                Assert.AreEqual(2, activeRoots,
                    "Old floor and partition roots must be disabled immediately on rebuild.");

                Transform floor = root.transform.Find("EntryChamberFloor");
                Assert.IsNotNull(floor);
                Assert.Greater(floor.GetComponentInChildren<Tilemap>().GetUsedTilesCount(), 0);
                BoxCollider floorCollision = floor.Find(FloorSpawner.FloorCollisionName).GetComponent<BoxCollider>();
                Assert.AreEqual(EntryChamberLayout.RoomBounds.size.x, floorCollision.size.x, 0.001f);
                Assert.AreEqual(EntryChamberLayout.RoomBounds.size.z, floorCollision.size.z, 0.001f);

                Physics.SyncTransforms();
                Assert.IsFalse(Physics.Raycast(new Vector3(EntryChamberLayout.CenterX, 1f, -33f),
                    Vector3.forward, 2f), "The wizard must pass through the three-unit gate opening.");
                Assert.IsTrue(Physics.Raycast(new Vector3(-8f, 1f, -33f),
                    Vector3.forward, 2f), "The gate's west wall must block walking around its leaf.");
            }
            finally
            {
                Object.DestroyImmediate(root);
            }
        }

        [Test]
        public void StartDoorClosesOnlyAfterWizardEscapesAndBruteRemainsBehind()
        {
            Assert.AreEqual(5, DoorSpawner.CanonicalDoors().Length,
                "The cutscene gate must not be added to D1–D5 progression.");
            GameObject template = Resources.Load<GameObject>("Spawners/EntryChamberGateSpawner");
            Assert.IsNotNull(template);
            GameObject root = Object.Instantiate(template);
            try
            {
                EntryChamberGateSpawner spawner = root.GetComponent<EntryChamberGateSpawner>();
                Assert.AreEqual(1, spawner.Spawn());
                EntryChamberStartDoor gate = root.GetComponentInChildren<EntryChamberStartDoor>();
                Assert.IsNotNull(gate);
                Assert.AreEqual(EntryChamberLayout.StartDoorCenter, gate.transform.position);
                Assert.IsFalse(gate.IsOpen);

                Assert.IsTrue(gate.OpenForEntryCutscene());
                Assert.IsFalse(gate.CloseAfterEntryCutscene(
                    new Vector3(-4f, 0f, -33f), EntryChamberLayout.PursuerStop));
                Assert.IsFalse(gate.CloseAfterEntryCutscene(
                    EntryChamberLayout.DoorCloseTrigger, new Vector3(-4f, 0f, -31f)));
                Assert.IsTrue(gate.CloseAfterEntryCutscene(
                    EntryChamberLayout.DoorCloseTrigger, EntryChamberLayout.PursuerStop));
                Assert.IsFalse(gate.IsOpen);
                Assert.IsTrue(gate.transform.Find("DoorVisual").gameObject.activeSelf);
            }
            finally
            {
                Object.DestroyImmediate(root);
            }
        }
    }
}
