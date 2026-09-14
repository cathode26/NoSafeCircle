using System.Collections;
using System.Reflection;
using NoSafeCircle.DoorPrototype.World;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class DoorBreachFeedbackPlayModeTests
    {
        private GameObject doorObject;
        private GameObject playerObject;
        private DoorInteractable door;
        private DoorBreachFeedback feedback;
        private AudioSource bangAudio;
        private Image fill;
        private GameObject[] cracks;

        [SetUp]
        public void SetUp()
        {
            if (TestContext.CurrentContext.Test.Name.StartsWith("CommittedScene_") ||
                TestContext.CurrentContext.Test.Name.StartsWith("HumanReview_")) return;
            doorObject = new GameObject("TestDoor");
            door = doorObject.AddComponent<DoorInteractable>();
            var visual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            visual.transform.SetParent(doorObject.transform, false);
            SetPrivateField(door, "doorVisual", visual);
            SetPrivateField(door, "doorwayBlocker", visual.GetComponent<Collider>());

            var feedbackObject = new GameObject("Feedback");
            feedback = feedbackObject.AddComponent<DoorBreachFeedback>();
            bangAudio = feedbackObject.AddComponent<AudioSource>();
            bangAudio.playOnAwake = false;
            fill = new GameObject("DurabilityFill", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image)).GetComponent<Image>();
            cracks = new[] { new GameObject("Crack1"), new GameObject("Crack2") };
            feedback.Bind(door, feedbackObject.transform, fill, cracks, bangAudio);

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
            if (doorObject == null) return;
            Object.DestroyImmediate(playerObject);
            Object.DestroyImmediate(fill.transform.parent != null ? fill.transform.parent.gameObject : fill.gameObject);
            foreach (var crack in cracks) Object.DestroyImmediate(crack);
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
            Assert.IsNotNull(bangAudio.clip, "Accepted damage needs an audible bang clip.");
            Assert.IsTrue(bangAudio.isPlaying, "Accepted damage must play the bang.");
        }

        [Test]
        public void RejectedDamage_LeavesFeedbackUnchanged()
        {
            door.ResetDoor();
            door.TakeDamage(25f);

            Assert.AreEqual(1f, fill.fillAmount, 0.001f);
            Assert.IsFalse(cracks[0].activeSelf);
            Assert.IsFalse(feedback.IsShaking);
            Assert.IsFalse(bangAudio.isPlaying, "Rejected damage must not play a bang.");
        }

        [Test]
        public void ResetDoor_ResetFeedbackRestoresIndicatorAndCracks()
        {
            door.TakeDamage(25f);
            Assert.IsTrue(bangAudio.isPlaying, "Test setup must start the bang before reset.");
            door.ResetDoor();

            Assert.AreEqual(1f, fill.fillAmount, 0.001f);
            Assert.IsFalse(cracks[0].activeSelf);
            Assert.IsFalse(cracks[1].activeSelf);
            Assert.IsFalse(feedback.IsShaking);
            Assert.IsFalse(bangAudio.isPlaying, "Reset must cancel an active bang.");
        }

        // NSC-052 VAL-001/VAL-002: exercise the committed scene and public
        // opening, crossing, damage, and reset path. The three tests above remain
        // component regressions and do not stand in for this production proof.
        [UnityTest]
        public IEnumerator CommittedScene_D1_BreachFeedbackFollowsPublicDoorPath()
        {
            yield return VerifyCommittedDoor(DoorId.D1);
        }

        [UnityTest]
        public IEnumerator CommittedScene_D2_BreachFeedbackFollowsPublicDoorPath()
        {
            yield return VerifyCommittedDoor(DoorId.D2);
        }

        [UnityTest]
        [Explicit("Vincent judges the exact candidate's visual and audio feedback in Game view.")]
        public IEnumerator HumanReview_RearLockedDoorFeedbackAtNextDoor()
        {
            yield return LoadCommittedScene();
            DoorInteractable d1 = FindDoor(DoorId.D1);
            DoorInteractable d2 = FindDoor(DoorId.D2);
            PlayerInteractionController player = FindPlayer();
            yield return OpenAndCross(d1, player);
            for (int hit = 0; hit < 4; hit++)
            {
                d1.TakeDamage(d1.MaxDurability * 0.25f);
                yield return new WaitForSeconds(1.2f);
            }

            d1.ResetDoor();
            yield return OpenAndCross(d1, player);
            player.transform.position = d2.InteractionPosition;
            Physics.SyncTransforms();
            yield return new WaitForFixedUpdate();
            yield return new WaitForSeconds(1f);
            for (int hit = 0; hit < 4; hit++)
            {
                d1.TakeDamage(d1.MaxDurability * 0.25f);
                yield return new WaitForSeconds(1.2f);
            }
        }

        private static IEnumerator VerifyCommittedDoor(DoorId id)
        {
            yield return LoadCommittedScene();
            DoorInteractable target = FindDoor(id);
            PlayerInteractionController player = FindPlayer();
            Transform feedbackRoot = target.transform.Find("DoorBreachFeedback");
            Transform shakeTarget = target.transform.Find("DoorVisual/DoorSprite");
            Transform indicator = feedbackRoot?.Find("DurabilityIndicator");
            Image indicatorFill = indicator?.Find("Background/Fill")?.GetComponent<Image>();
            DoorBreachFeedback presenter = feedbackRoot?.GetComponent<DoorBreachFeedback>();
            AudioSource audio = feedbackRoot?.GetComponent<AudioSource>();
            Collider blocker = target.transform.Find("DoorVisual")?.GetComponent<Collider>();
            Assert.IsNotNull(presenter);
            Assert.IsNotNull(shakeTarget);
            Assert.IsNotNull(indicator);
            Assert.IsNotNull(indicatorFill);
            Assert.IsNotNull(audio);
            Assert.IsNotNull(blocker);
            Assert.AreEqual(0, shakeTarget.GetComponentsInChildren<Collider>(true).Length);
            Assert.IsFalse(indicator.gameObject.activeSelf, "Sealed indicator must be hidden.");

            float fullDurability = target.CurrentDurability;
            target.TakeDamage(target.MaxDurability * 0.2f);
            Assert.AreEqual(fullDurability, target.CurrentDurability);
            Assert.IsFalse(audio.isPlaying);
            target.StartInteraction();
            target.Tick(target.Duration + 0.01f);
            Assert.IsTrue(target.IsOpen);
            Assert.IsFalse(indicator.gameObject.activeSelf, "Open indicator must be hidden.");
            target.TakeDamage(target.MaxDurability * 0.2f);
            Assert.AreEqual(fullDurability, target.CurrentDurability);
            yield return CrossOpenDoor(target, player);
            Assert.IsTrue(target.IsLocked, "The scene Player must enter this door's real crossing trigger.");

            Vector3 authoredPosition = shakeTarget.localPosition;
            Bounds authoredBlocker = blocker.bounds;
            float priorFill = 1f;
            int priorCracks = 0;
            for (int hit = 0; hit < 3; hit++)
            {
                target.TakeDamage(target.MaxDurability * 0.2f);
                Assert.IsTrue(indicator.gameObject.activeSelf);
                Assert.Less(indicatorFill.fillAmount, priorFill);
                priorFill = indicatorFill.fillAmount;
                int activeCracks = CountCracks(shakeTarget);
                Assert.Greater(activeCracks, 0);
                Assert.GreaterOrEqual(activeCracks, priorCracks);
                priorCracks = activeCracks;
                Assert.IsNotNull(audio.clip);
                Assert.IsTrue(audio.isPlaying, "Accepted damage must play its door-local bang.");
                bool visiblyShook = false;
                for (int frame = 0; frame < 6; frame++)
                {
                    yield return null;
                    visiblyShook |= Vector3.Distance(shakeTarget.localPosition, authoredPosition) > 0.001f;
                }
                Assert.IsTrue(visiblyShook);
                Assert.Less(Vector3.Distance(blocker.bounds.center, authoredBlocker.center), 0.001f);
                Assert.Less(Vector3.Distance(blocker.bounds.size, authoredBlocker.size), 0.001f);
                Assert.AreEqual(0, shakeTarget.GetComponentsInChildren<Collider>(true).Length);
            }

            yield return new WaitForSeconds(audio.clip.length + 0.05f);
            target.TakeDamage(0f);
            Assert.IsFalse(audio.isPlaying);
            Assert.AreEqual(priorFill, indicatorFill.fillAmount, 0.001f);
            target.TakeDamage(target.MaxDurability);
            Assert.IsTrue(target.IsBroken);
            Assert.AreEqual(3, CountCracks(shakeTarget));
            Assert.IsFalse(indicator.gameObject.activeSelf, "Exhausted indicator must hide.");
            Assert.IsTrue(audio.isPlaying, "Final accepted hit must sound after break.");
            Assert.IsTrue(target.transform.Find("DoorVisual").gameObject.activeSelf);
            Assert.IsTrue(blocker.enabled);
            Assert.Less(Vector3.Distance(blocker.bounds.center, authoredBlocker.center), 0.001f);
            Assert.Less(Vector3.Distance(blocker.bounds.size, authoredBlocker.size), 0.001f);
            yield return new WaitForSeconds(audio.clip.length + 0.05f);
            target.TakeDamage(target.MaxDurability);
            Assert.IsFalse(audio.isPlaying, "Broken door must reject further damage.");

            target.ResetDoor();
            Assert.IsFalse(target.IsBroken);
            Assert.IsFalse(target.IsLocked);
            Assert.AreEqual(target.MaxDurability, target.CurrentDurability, 0.001f);
            Assert.AreEqual(1f, indicatorFill.fillAmount, 0.001f);
            Assert.IsFalse(indicator.gameObject.activeSelf);
            Assert.AreEqual(0, CountCracks(shakeTarget));
            Assert.IsFalse(presenter.IsShaking);
            Assert.IsFalse(audio.isPlaying);
            Assert.Less(Vector3.Distance(shakeTarget.localPosition, authoredPosition), 0.001f);
        }

        private static IEnumerator LoadCommittedScene()
        {
            SceneManager.LoadScene("DoorPrototype", LoadSceneMode.Single);
            yield return null;
            Assert.AreEqual("DoorPrototype", SceneManager.GetActiveScene().name);
        }

        private static IEnumerator OpenAndCross(DoorInteractable target, PlayerInteractionController player)
        {
            target.StartInteraction();
            target.Tick(target.Duration + 0.01f);
            yield return CrossOpenDoor(target, player);
            Assert.IsTrue(target.IsLocked);
        }

        private static IEnumerator CrossOpenDoor(DoorInteractable target, PlayerInteractionController player)
        {
            Transform crossing = target.transform.Find("ForwardCrossingTrigger");
            Assert.IsNotNull(crossing);
            BoxCollider trigger = crossing.GetComponent<BoxCollider>();
            Assert.IsNotNull(trigger);
            CharacterController controller = player.GetComponent<CharacterController>();
            Assert.IsNotNull(controller);
            // Start just outside the actual trigger, in the already-open
            // doorway. A long Move from the room's interaction marker can be
            // stopped by unrelated room geometry before the trigger is reached.
            float approachDistance = trigger.size.z * 0.5f + controller.radius + 0.2f;
            controller.enabled = false;
            player.transform.position = crossing.position - crossing.forward * approachDistance;
            controller.enabled = true;
            Physics.SyncTransforms();
            yield return new WaitForFixedUpdate();
            controller.Move(crossing.position - player.transform.position);
            Physics.SyncTransforms();
            yield return new WaitForFixedUpdate();
            Assert.IsTrue(trigger.bounds.Intersects(controller.bounds),
                "The scene Player collider must physically overlap the runtime crossing trigger.");
        }

        private static int CountCracks(Transform shakeTarget)
        {
            int count = 0;
            for (int stage = 1; stage <= 3; stage++)
                if (shakeTarget.Find("CrackStage" + stage).gameObject.activeSelf) count++;
            return count;
        }

        private static DoorInteractable FindDoor(DoorId id)
        {
            foreach (GameObject root in SceneManager.GetActiveScene().GetRootGameObjects())
                foreach (DoorInteractable candidate in root.GetComponentsInChildren<DoorInteractable>(true))
                    if (candidate.DoorId == id) return candidate;
            Assert.Fail("Committed scene is missing door " + id);
            return null;
        }

        private static PlayerInteractionController FindPlayer()
        {
            foreach (GameObject root in SceneManager.GetActiveScene().GetRootGameObjects())
                foreach (PlayerInteractionController candidate in root.GetComponentsInChildren<PlayerInteractionController>(true))
                    return candidate;
            Assert.Fail("Committed scene is missing PlayerInteractionController.");
            return null;
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
