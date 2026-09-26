using System.Collections;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using NoSafeCircle.DoorPrototype.Content;
using NoSafeCircle.DoorPrototype.Enemies.Pooling;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Proves the ENGINEERING_STANDARDS 9.2 behaviours and 9.4 diagnostics of EnemyPrefabPool with a
    // stub poolable that records every call it receives. Every expected count below is the number
    // of things THIS TEST did - checkouts it made, returns it made, objects it destroyed - never a
    // number read back from the pool and restated.
    //
    // The pool's faults log errors in development, so every test that provokes one declares it
    // with LogAssert.Expect first; an unexpected error is a failure, which is the point.
    public sealed class EnemyPrefabPoolPlayModeTests
    {
        private static readonly Pose PoseA = new Pose(new Vector3(1f, 0f, 1f), Quaternion.identity);
        private static readonly Pose PoseB = new Pose(new Vector3(2f, 0f, 2f), Quaternion.Euler(0f, 90f, 0f));

        private GameObject root;
        private GameObject template;
        private Transform activeRoot;
        private EnemyPrefabPool pool;
        private int leaseReleases;
        private int liveInstancesAtRelease;

        /// <summary>Records the pool's calls. Its counts are the fixture's own bookkeeping.</summary>
        private sealed class RecordingPoolable : MonoBehaviour, IEnemyPoolable
        {
            public readonly List<Pose> Checkouts = new List<Pose>();
            public int Returns;

            public void OnCheckout(Pose spawnPose) => Checkouts.Add(spawnPose);

            public void OnReturn() => Returns++;
        }

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("EnemyPrefabPoolTestRoot");

            // The "prefab": a scene object the pool clones. Parked far from the slot poses so a
            // clone that failed to move would be caught by the pose assertions.
            template = new GameObject("PooledTemplate");
            template.transform.SetParent(root.transform, false);
            template.transform.position = new Vector3(500f, 0f, 500f);
            template.AddComponent<RecordingPoolable>();

            activeRoot = new GameObject("PoolRoot").transform;
            activeRoot.SetParent(root.transform, false);

            leaseReleases = 0;
            liveInstancesAtRelease = -1;
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            pool?.Dispose();
            pool = null;
            if (root != null) Object.Destroy(root);
            yield return null;
        }

        private EnemyPrefabPool CreatePool(bool recycleOnReturn)
        {
            // A lease whose release callback records what the pool looked like AT THE MOMENT the
            // lease was released. That single observation is what proves "instances gone, then
            // lease" rather than the other order.
            var lease = new AssetLease<GameObject>(template, "test/PooledTemplate", () =>
            {
                leaseReleases++;
                liveInstancesAtRelease = pool.LiveInstanceCount;
            });

            pool = new EnemyPrefabPool("Pooled", lease, new[] { ("a", PoseA), ("b", PoseB) },
                activeRoot, recycleOnReturn);
            return pool;
        }

        private static RecordingPoolable StubOf(GameObject instance) =>
            instance.GetComponent<RecordingPoolable>();

        [UnityTest]
        public IEnumerator PrewarmCreatesOneInactiveInstancePerSlotAtItsPose()
        {
            CreatePool(recycleOnReturn: true);
            yield return null;

            // Two slots were asked for, so two instances, both parked and both at their slot pose
            // - because Awake-time state (an enemy's leash anchor) is recorded at creation.
            Assert.AreEqual(2, activeRoot.childCount, "one instance per slot, created up front");
            Assert.AreEqual(2, pool.Capacity);
            Assert.AreEqual(2, pool.LiveInstanceCount);
            Assert.AreEqual(0, pool.Diagnostics.ActiveNow);
            Assert.AreEqual(0, pool.Diagnostics.PeakActive);

            Assert.IsTrue(pool.TryGetInstance("a", out GameObject a));
            Assert.IsTrue(pool.TryGetInstance("b", out GameObject b));
            Assert.IsFalse(a.activeSelf, "a parked instance must be inactive");
            Assert.IsFalse(b.activeSelf, "a parked instance must be inactive");
            Assert.AreEqual(PoseA.position, a.transform.position);
            Assert.AreEqual(PoseB.position, b.transform.position);
            Assert.Less(Quaternion.Angle(PoseB.rotation, b.transform.rotation), 0.01f);
            Assert.AreEqual("Pooled", a.name);
            Assert.AreEqual(0, StubOf(a).Checkouts.Count, "prewarm is creation, not checkout");
            Assert.AreEqual(0, StubOf(b).Checkouts.Count, "prewarm is creation, not checkout");
            Assert.IsFalse(pool.Diagnostics.HasFault, pool.Diagnostics.Report("Pooled"));
        }

        [UnityTest]
        public IEnumerator CheckoutReturnsTheSlotInstanceInactiveAndResetsIt()
        {
            CreatePool(recycleOnReturn: true);

            GameObject a = pool.Checkout("a");
            yield return null;

            Assert.IsNotNull(a);
            Assert.IsTrue(pool.Owns(a));
            Assert.IsFalse(a.activeSelf,
                "Checkout hands the instance out INACTIVE. Activation is the admission controller's "
                + "job, which is how the 15-enemy cap keeps working under pooling.");
            Assert.AreEqual(1, StubOf(a).Checkouts.Count, "OnCheckout called exactly once");
            Assert.AreEqual(PoseA, StubOf(a).Checkouts[0], "OnCheckout receives the slot's own pose");
            Assert.AreEqual(0, StubOf(a).Returns);
            Assert.AreEqual(1, pool.Diagnostics.ActiveNow);
            Assert.AreEqual(1, pool.Diagnostics.PeakActive);
            Assert.IsTrue(pool.TryGetInstance("a", out GameObject again) && ReferenceEquals(a, again),
                "the slot's instance is the one handed out");
        }

        [UnityTest]
        public IEnumerator UnknownIdAndSecondCheckoutAreRejectedAndCounted()
        {
            CreatePool(recycleOnReturn: true);

            // Overflow policy: REJECT. Nothing is instantiated past capacity, ever.
            LogAssert.Expect(LogType.Error, new Regex("checkout of 'x' rejected"));
            Assert.IsNull(pool.Checkout("x"), "an unknown slot id must return null");
            Assert.AreEqual(1, pool.Diagnostics.Rejected);

            Assert.IsNotNull(pool.Checkout("a"));
            LogAssert.Expect(LogType.Error, new Regex("'a' is already checked out"));
            Assert.IsNull(pool.Checkout("a"), "a slot already out must return null");
            Assert.AreEqual(1, pool.Diagnostics.DoubleCheckout);
            yield return null;

            Assert.AreEqual(1, pool.Diagnostics.ActiveNow, "a rejected checkout is not out");
            Assert.AreEqual(2, activeRoot.childCount, "rejections instantiate nothing");
            Assert.AreEqual(0, pool.Diagnostics.CapacityExpansion, "this pool never expands");
        }

        [UnityTest]
        public IEnumerator DoubleAndForeignReturnsAreCountedAndIgnored()
        {
            CreatePool(recycleOnReturn: true);
            GameObject a = pool.Checkout("a");
            a.SetActive(true); // as admission would
            yield return null;

            Assert.IsTrue(pool.Return(a), "the first return is legitimate");
            Assert.IsFalse(a.activeSelf, "a returned instance is deactivated");
            Assert.AreEqual(1, StubOf(a).Returns);

            LogAssert.Expect(LogType.Error, new Regex("'a' returned twice"));
            Assert.IsFalse(pool.Return(a));
            Assert.AreEqual(1, pool.Diagnostics.DoubleReturn);
            Assert.AreEqual(1, StubOf(a).Returns, "a double return must not reset the instance again");

            var foreign = new GameObject("NotFromThisPool");
            foreign.transform.SetParent(root.transform, false);
            LogAssert.Expect(LogType.Error, new Regex("'NotFromThisPool' was not created by this pool"));
            Assert.IsFalse(pool.Return(foreign));
            Assert.AreEqual(1, pool.Diagnostics.ForeignReturn);
            Assert.IsTrue(foreign.activeSelf, "a foreign object is left exactly as it was");

            LogAssert.Expect(LogType.Error, new Regex("'null' was not created by this pool"));
            Assert.IsFalse(pool.Return(null));
            Assert.AreEqual(2, pool.Diagnostics.ForeignReturn);

            Assert.AreEqual(0, pool.Diagnostics.ActiveNow, "one checkout, one legitimate return");
        }

        [UnityTest]
        public IEnumerator ExternallyDestroyedInstanceIsReplacedOnCheckoutAndCounted()
        {
            CreatePool(recycleOnReturn: true);

            // Path 1: destroyed while PARKED (DemoRunFlow's Destroy after a defeat lands here).
            GameObject a = pool.Checkout("a");
            int firstId = a.GetInstanceID();
            Assert.IsTrue(pool.Return(a));
            Object.Destroy(a);
            yield return null;

            Assert.AreEqual(1, pool.LiveInstanceCount, "only b is alive after a died");
            LogAssert.Expect(LogType.Error, new Regex("'a' was destroyed by something other than this pool"));
            GameObject replacement = pool.Checkout("a");
            Assert.IsNotNull(replacement, "the slot is re-created rather than lost");
            Assert.AreNotEqual(firstId, replacement.GetInstanceID(), "a new object, not the corpse");
            Assert.AreEqual(PoseA.position, replacement.transform.position, "re-created at its slot pose");
            Assert.AreEqual(1, pool.Diagnostics.DestroyedExternally);
            Assert.AreEqual(1, pool.Diagnostics.ActiveNow);

            // Path 2: destroyed while OUT, then returned. No reset can run on a corpse; the slot is
            // vacated and counted, and the next checkout re-creates it WITHOUT a second count,
            // because that destruction is the pool's own bookkeeping.
            GameObject b = pool.Checkout("b");
            int bId = b.GetInstanceID();
            Object.Destroy(b);
            yield return null;

            LogAssert.Expect(LogType.Error, new Regex("'b' was destroyed while checked out"));
            Assert.IsTrue(pool.Return(b), "returning a dead instance is accepted and cleaned up");
            Assert.AreEqual(2, pool.Diagnostics.DestroyedExternally);
            Assert.AreEqual(1, pool.Diagnostics.ActiveNow, "b is no longer out");

            GameObject b2 = pool.Checkout("b");
            Assert.IsNotNull(b2);
            Assert.AreNotEqual(bId, b2.GetInstanceID());
            Assert.AreEqual(2, pool.Diagnostics.DestroyedExternally, "a vacated slot is not a second fault");
            Assert.AreEqual(2, activeRoot.childCount, "still exactly one instance per slot");
        }

        [UnityTest]
        public IEnumerator DisposeCountsActiveInstancesAndReleasesTheLeaseLast()
        {
            CreatePool(recycleOnReturn: true);
            GameObject a = pool.Checkout("a");
            GameObject b = pool.Checkout("b");
            Assert.IsTrue(pool.Return(b));
            yield return null;

            pool.Dispose();

            // The lease callback ran exactly once, and when it ran the pool held ZERO instances:
            // that is standards 8.5/9.5 - the prefab lease outlives every instance.
            Assert.AreEqual(1, leaseReleases, "the lease is released exactly once");
            Assert.AreEqual(0, liveInstancesAtRelease,
                "the lease was released while " + liveInstancesAtRelease + " instance(s) still "
                + "existed. Instances must be gone BEFORE the prefab lease goes.");
            Assert.AreEqual(1, pool.Diagnostics.ActiveAtDisposal, "a was still out; b had come back");
            Assert.AreEqual(2, pool.Diagnostics.PeakActive, "two were out at once before b returned");
            Assert.AreEqual(0, pool.Diagnostics.ActiveNow);
            Assert.IsTrue(pool.IsDisposed);
            Assert.AreEqual(0, pool.LiveInstanceCount);

            yield return null;
            Assert.AreEqual(0, activeRoot.childCount, "every instance was destroyed");
            Assert.IsTrue(a == null, "the checked-out instance was destroyed too");

            // After disposal the pool refuses, counts, and never re-creates.
            LogAssert.Expect(LogType.Error, new Regex("pool is disposed"));
            Assert.IsNull(pool.Checkout("a"));
            Assert.AreEqual(1, pool.Diagnostics.Rejected);

            pool.Dispose();
            Assert.AreEqual(1, leaseReleases, "a second Dispose must not release the lease again");
        }

        [UnityTest]
        public IEnumerator RecycleFalseDestroysOnReturnAndRecreatesOnCheckout()
        {
            CreatePool(recycleOnReturn: false);
            GameObject first = pool.Checkout("a");
            int firstId = first.GetInstanceID();
            Assert.AreEqual(1, StubOf(first).Checkouts.Count);

            Assert.IsTrue(pool.Return(first));
            yield return null;

            Assert.IsTrue(first == null, "a non-recycling return destroys the instance");
            Assert.IsFalse(pool.TryGetInstance("a", out _), "the slot is vacant until the next checkout");
            Assert.AreEqual(1, pool.LiveInstanceCount, "b is untouched");

            GameObject second = pool.Checkout("a");
            Assert.IsNotNull(second);
            Assert.AreNotEqual(firstId, second.GetInstanceID(), "re-created, so a fresh Awake ran");
            Assert.AreEqual(PoseA.position, second.transform.position);
            Assert.AreEqual(1, StubOf(second).Checkouts.Count, "the fresh instance was checked out once");
            Assert.AreEqual(0, pool.Diagnostics.DestroyedExternally,
                "the pool destroyed it on purpose; that is policy, not a fault");
            Assert.IsFalse(pool.Diagnostics.HasFault, pool.Diagnostics.Report("Pooled"));
            Assert.AreEqual(2, activeRoot.childCount);
        }

        [UnityTest]
        public IEnumerator RecycleTrueHandsBackTheSameInstance()
        {
            CreatePool(recycleOnReturn: true);
            GameObject first = pool.Checkout("a");
            int firstId = first.GetInstanceID();
            Assert.IsTrue(pool.Return(first));
            yield return null;

            GameObject second = pool.Checkout("a");
            Assert.AreEqual(firstId, second.GetInstanceID(), "recycling keeps the object");
            Assert.AreEqual(2, StubOf(second).Checkouts.Count, "the same stub saw both checkouts");
            Assert.AreEqual(1, StubOf(second).Returns);
        }

        [UnityTest]
        public IEnumerator ReturnAllTakesBackEverythingCheckedOut()
        {
            CreatePool(recycleOnReturn: true);
            GameObject a = pool.Checkout("a");
            GameObject b = pool.Checkout("b");
            a.SetActive(true);
            b.SetActive(true);
            yield return null;

            pool.ReturnAll();

            Assert.AreEqual(0, pool.Diagnostics.ActiveNow);
            Assert.IsFalse(a.activeSelf);
            Assert.IsFalse(b.activeSelf);
            Assert.AreEqual(1, StubOf(a).Returns);
            Assert.AreEqual(1, StubOf(b).Returns);
            Assert.IsFalse(pool.Diagnostics.HasFault, pool.Diagnostics.Report("Pooled"));

            pool.ReturnAll();
            Assert.AreEqual(0, pool.Diagnostics.DoubleReturn, "ReturnAll on an idle pool returns nothing");
        }
    }
}
