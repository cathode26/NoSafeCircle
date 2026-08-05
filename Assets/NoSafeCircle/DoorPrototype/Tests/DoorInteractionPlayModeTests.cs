using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class DoorInteractionPlayModeTests
    {
        private GameObject doorObject;
        private GameObject playerObject;
        private DoorInteractable door;
        private PlayerInteractionController controller;
        private PlayerHealth health;

        [SetUp]
        public void SetUp()
        {
            doorObject = new GameObject("TestDoor");
            door = doorObject.AddComponent<DoorInteractable>();

            playerObject = new GameObject("TestPlayer");
            health = playerObject.AddComponent<PlayerHealth>();
            controller = playerObject.AddComponent<PlayerInteractionController>();

            controller.NotifyDoorInRange(door);
        }

        [TearDown]
        public void TearDown()
        {
            Object.Destroy(playerObject);
            Object.Destroy(doorObject);
        }

        [UnityTest]
        public IEnumerator Completion_OpensDoor_AfterFullDuration()
        {
            controller.BeginInteraction();

            AdvanceDoorTime(door, door.Duration + 0.1f);

            yield return null;

            Assert.AreEqual(1f, door.Progress, 0.001f);
            Assert.IsTrue(door.IsOpen);
        }

        [UnityTest]
        public IEnumerator Progress_IsApproximatelyHalf_AtHalfDuration()
        {
            controller.BeginInteraction();

            AdvanceDoorTime(door, door.Duration * 0.5f);

            yield return null;

            Assert.AreEqual(0.5f, door.Progress, 0.05f);
            Assert.IsFalse(door.IsOpen);
        }

        [UnityTest]
        public IEnumerator ReleasingInteraction_CancelsAttempt()
        {
            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration * 0.4f);

            controller.EndInteraction();

            yield return null;

            Assert.AreEqual(0f, door.Progress);
            Assert.IsFalse(door.IsOpen);
        }

        [UnityTest]
        public IEnumerator PlayerMovement_CancelsAttempt()
        {
            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration * 0.4f);

            controller.OnPlayerMoved();

            yield return null;

            Assert.AreEqual(0f, door.Progress);
            Assert.IsFalse(door.IsOpen);
        }

        [UnityTest]
        public IEnumerator PlayerDamage_CancelsAttempt()
        {
            controller.BeginInteraction();
            AdvanceDoorTime(door, door.Duration * 0.4f);

            health.TakeDamage(10f);

            yield return null;

            Assert.AreEqual(0f, door.Progress);
            Assert.IsFalse(door.IsOpen);
        }

        private static void AdvanceDoorTime(DoorInteractable target, float totalSeconds)
        {
            const float step = 0.05f;
            var elapsed = 0f;
            while (elapsed < totalSeconds)
            {
                var dt = Mathf.Min(step, totalSeconds - elapsed);
                target.Tick(dt);
                elapsed += dt;
            }
        }
    }
}
