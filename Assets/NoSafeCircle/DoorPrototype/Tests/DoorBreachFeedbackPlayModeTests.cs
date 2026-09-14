using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class DoorBreachFeedbackPlayModeTests
    {
        private GameObject doorObject;
        private GameObject playerObject;
        private DoorInteractable door;
        private DoorBreachFeedback feedback;
        private Image fill;
        private GameObject[] cracks;

        [SetUp]
        public void SetUp()
        {
            doorObject = new GameObject("TestDoor");
            door = doorObject.AddComponent<DoorInteractable>();
            var visual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            visual.transform.SetParent(doorObject.transform, false);
            SetPrivateField(door, "doorVisual", visual);
            SetPrivateField(door, "doorwayBlocker", visual.GetComponent<Collider>());

            var feedbackObject = new GameObject("Feedback");
            feedback = feedbackObject.AddComponent<DoorBreachFeedback>();
            fill = new GameObject("DurabilityFill", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image)).GetComponent<Image>();
            cracks = new[] { new GameObject("Crack1"), new GameObject("Crack2") };
            feedback.Bind(door, feedbackObject.transform, fill, cracks);

            playerObject = new GameObject("Player");
            var controller = playerObject.AddComponent<PlayerInteractionController>();
            playerObject.AddComponent<BoxCollider>();
            controller.NotifyDoorInRange(door);
            controller.BeginInteraction();
            door.Tick(door.Duration + 0.1f);
            InvokePrivate(door, "HandleForwardCrossingTriggerEnter", playerObject.GetComponent<Collider>());
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(playerObject);
            Object.DestroyImmediate(fill.transform.parent != null ? fill.transform.parent.gameObject : fill.gameObject);
            Object.DestroyImmediate(feedback.gameObject);
            Object.DestroyImmediate(doorObject);
        }

        [Test]
        public void AcceptedDamage_UpdatesIndicatorCracksAndShake()
        {
            door.TakeDamage(25f);

            Assert.AreEqual(0.75f, fill.fillAmount, 0.001f);
            Assert.IsTrue(cracks[0].activeSelf);
            Assert.IsFalse(cracks[1].activeSelf);
            Assert.IsTrue(feedback.IsShaking);
        }

        [Test]
        public void RejectedDamage_LeavesFeedbackUnchanged()
        {
            door.ResetDoor();
            feedback.ResetFeedback();
            door.TakeDamage(25f);

            Assert.AreEqual(1f, fill.fillAmount, 0.001f);
            Assert.IsFalse(cracks[0].activeSelf);
            Assert.IsFalse(feedback.IsShaking);
        }

        [Test]
        public void ResetDoor_ResetFeedbackRestoresIndicatorAndCracks()
        {
            door.TakeDamage(25f);
            door.ResetDoor();

            Assert.AreEqual(1f, fill.fillAmount, 0.001f);
            Assert.IsFalse(cracks[0].activeSelf);
            Assert.IsFalse(cracks[1].activeSelf);
            Assert.IsFalse(feedback.IsShaking);
        }

        private static void InvokePrivate(object target, string method, Collider argument)
        {
            target.GetType().GetMethod(method, BindingFlags.NonPublic | BindingFlags.Instance)
                .Invoke(target, new object[] { argument });
        }

        private static void SetPrivateField(object target, string name, object value)
        {
            target.GetType().GetField(name, BindingFlags.NonPublic | BindingFlags.Instance).SetValue(target, value);
        }
    }
}
