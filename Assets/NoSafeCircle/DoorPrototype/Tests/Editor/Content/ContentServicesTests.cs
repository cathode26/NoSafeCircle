using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using NoSafeCircle.DoorPrototype.Content;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Content
{
    /// <summary>
    /// EditMode coverage of the content services that hold without a built catalog: resolver ordering
    /// and selection, the failure-model mapping, lease and scope lifetime, and pool lifetime ordering
    /// against a fake service.
    /// </summary>
    /// <remarks>
    /// <para>
    /// ENGINEERING_STANDARDS 8.8 LISTS TEN REQUIRED TESTS. WHAT THIS FILE COVERS, BY NAME, AND WHAT IT
    /// DOES NOT, because pretending otherwise is worse than a gap:
    /// </para>
    /// <list type="bullet">
    /// <item>required load success - PARTIAL. <c>ContentResolver.Select</c> maps a first-candidate hit to
    /// Success and the fake returns a Success lease. The real <c>AddressableAssetService</c> is not
    /// exercised; it needs a catalog.</item>
    /// <item>optional variant fallback - PARTIAL. Ordering is asserted and Select maps a later hit to
    /// FallbackUsed. No real catalog.</item>
    /// <item>missing required content - PARTIAL. Select maps an all-miss to RequiredMissing and the pool
    /// reacts to it correctly. No real catalog.</item>
    /// <item>cancellation - CONTRACT ONLY. The fake honours a cancelled token and the scope registers
    /// nothing. <c>AddressableHandles.WhenDoneOrCancelled</c> needs a live handle.</item>
    /// <item>scope disposal - COVERED.</item>
    /// <item>failed-load handle release - NOT COVERED. Needs a real failing handle. The nearest thing
    /// here is the pool releasing a lease over a prefab it cannot use.</item>
    /// <item>pooled prefab lifetime ordering - COVERED, against the fake.</item>
    /// <item>group platform filtering - NOT COVERED. Needs settings and a content build.</item>
    /// <item>restoration of group settings after successful and failed builds - NOT COVERED. No build
    /// script exists in this lane yet.</item>
    /// <item>WebGL player loading and unload behaviour - NOT COVERED. Needs a WebGL player.</item>
    /// </list>
    /// <para>
    /// EVERY TEST IS SYNCHRONOUS ON PURPOSE. The fake completes its tasks before returning them, so an
    /// <c>async</c> method awaiting it continues inline and its task is complete by the time it is
    /// handed back; each test asserts <c>IsCompleted</c> before reading a result, so nothing here ever
    /// blocks on a task.
    /// </para>
    /// </remarks>
    public sealed class ContentServicesTests
    {
        private const string ProbeId = "probe";
        private const string PlainId = "plain";
        private static readonly ContentQuery ProbeQuery = new ContentQuery(ContentId.Family.Gameplay, ProbeId);
        private static readonly ContentQuery PlainQuery = new ContentQuery(ContentId.Family.Gameplay, PlainId);
        private static readonly ContentQuery MissingQuery = new ContentQuery(ContentId.Family.Gameplay, "nothing");
        private static readonly string ProbeAddress = ContentId.Address(ContentId.Family.Gameplay, ProbeId);
        private static readonly string PlainAddress = ContentId.Address(ContentId.Family.Gameplay, PlainId);

        private GameObject root;
        private FakeAssetService fake;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject(nameof(ContentServicesTests));
            fake = new FakeAssetService(ContentResolver.SharedOnly());

            GameObject template = new GameObject("ProbeTemplate");
            template.transform.SetParent(root.transform, false);
            template.AddComponent<PoolableProbe>();
            template.SetActive(false);
            fake.Add(ProbeAddress, template);

            GameObject plain = new GameObject("PlainTemplate");
            plain.transform.SetParent(root.transform, false);
            plain.SetActive(false);
            fake.Add(PlainAddress, plain);
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(root);
        }

        // ---- Resolver: ordering and fallback selection ----------------------------------------

        [Test]
        public void Resolver_OrdersCandidatesByThePreferenceData()
        {
            var resolver = new ContentResolver(new[] { ContentId.Variant.WebGL, ContentId.Variant.Shared });

            IReadOnlyList<string> candidates = resolver.Resolve(new ContentQuery(ContentId.Family.Props, "ca_pew_row_a"));

            CollectionAssert.AreEqual(new[] { "WebGL/Props/ca_pew_row_a", "Props/ca_pew_row_a" }, candidates);
        }

        [Test]
        public void Resolver_SharedOnlyResolvesToThePlainFamilyAddress()
        {
            IReadOnlyList<string> candidates = ContentResolver.SharedOnly()
                .Resolve(new ContentQuery(ContentId.Family.Data, "floor01"));

            CollectionAssert.AreEqual(new[] { "Levels/floor01" }, candidates);
        }

        [Test]
        public void Resolver_QueryPreferenceOverridesTheResolverDefault()
        {
            var query = new ContentQuery(ContentId.Family.Ui, "hud",
                new[] { ContentId.Variant.Desktop, ContentId.Variant.Shared });

            IReadOnlyList<string> candidates = ContentResolver.SharedOnly().Resolve(query);

            CollectionAssert.AreEqual(new[] { "Desktop/Ui/hud", "Ui/hud" }, candidates);
        }

        [Test]
        public void Resolver_RejectsAPreferenceThatDoesNotEndWithShared()
        {
            var failure = Assert.Throws<ArgumentException>(() =>
                new ContentResolver(new[] { ContentId.Variant.Shared, ContentId.Variant.WebGL }));

            StringAssert.Contains("must end with Shared", failure.Message);
            Assert.Throws<ArgumentException>(() => new ContentResolver(new ContentId.Variant[0]));
            Assert.Throws<ArgumentException>(() =>
                new ContentResolver(new[] { ContentId.Variant.WebGL, ContentId.Variant.WebGL, ContentId.Variant.Shared }));
        }

        [Test]
        public void Resolver_ForPlatformPrefersThePlatformTreeThenShared()
        {
            var query = new ContentQuery(ContentId.Family.Environment, "wall");

            CollectionAssert.AreEqual(new[] { "WebGL/Environment/wall", "Environment/wall" },
                ContentResolver.ForPlatform(RuntimePlatform.WebGLPlayer).Resolve(query));
            CollectionAssert.AreEqual(new[] { "Desktop/Environment/wall", "Environment/wall" },
                ContentResolver.ForPlatform(RuntimePlatform.WindowsPlayer).Resolve(query));
            CollectionAssert.AreEqual(new[] { "Environment/wall" },
                ContentResolver.ForPlatform(RuntimePlatform.Android).Resolve(query));
        }

        [Test]
        public void Resolver_RejectsADefaultQuery()
        {
            Assert.Throws<ArgumentException>(() => ContentResolver.SharedOnly().Resolve(default(ContentQuery)));
        }

        [Test]
        public void ContentQuery_RejectsAnEmptyId()
        {
            Assert.Throws<ArgumentException>(() => new ContentQuery(ContentId.Family.Props, ""));
        }

        // ---- Failure-model mapping: the pure selection walk ------------------------------------

        [Test]
        public void Select_FirstCandidateFound_IsSuccess()
        {
            CandidateSelection selection = ContentResolver.Select(new[] { "a", "b" }, address => CandidateProbe.Found);

            Assert.AreEqual(AssetLoadStatus.Success, selection.Status);
            Assert.AreEqual("a", selection.Address);
            Assert.AreEqual(0, selection.Index);
            Assert.IsTrue(selection.HasCandidate);
        }

        [Test]
        public void Select_LaterCandidateFound_IsFallbackUsed()
        {
            CandidateSelection selection = ContentResolver.Select(new[] { "a", "b", "c" },
                address => address == "c" ? CandidateProbe.Found : CandidateProbe.Missing);

            Assert.AreEqual(AssetLoadStatus.FallbackUsed, selection.Status);
            Assert.AreEqual("c", selection.Address);
            Assert.AreEqual(2, selection.Index);
            StringAssert.Contains("'a' is absent", selection.Message);
        }

        [Test]
        public void Select_NothingFound_IsRequiredMissingAndNamesEveryCandidate()
        {
            CandidateSelection selection = ContentResolver.Select(new[] { "a", "b" }, address => CandidateProbe.Missing);

            Assert.AreEqual(AssetLoadStatus.RequiredMissing, selection.Status);
            Assert.AreEqual("a", selection.Address);
            Assert.IsFalse(selection.HasCandidate);
            StringAssert.Contains("a, b", selection.Message);
        }

        [Test]
        public void Select_WrongTypeAtAPreferredCandidate_IsTypeMismatchAndDoesNotFallThrough()
        {
            CandidateSelection selection = ContentResolver.Select(new[] { "a", "b" },
                address => address == "a" ? CandidateProbe.WrongType : CandidateProbe.Found);

            Assert.AreEqual(AssetLoadStatus.TypeMismatch, selection.Status);
            Assert.AreEqual("a", selection.Address);
        }

        [Test]
        public void Select_RejectsAnEmptyCandidateList()
        {
            Assert.Throws<ArgumentException>(() => ContentResolver.Select(new string[0], address => CandidateProbe.Found));
        }

        // ---- ContentId: the logical address of a folder-entry key ------------------------------

        [Test]
        public void LogicalAddress_StripsTheExtensionAFolderEntryAppends()
        {
            Assert.AreEqual("Props/ca_pew_row_a", ContentId.LogicalAddress("Props/ca_pew_row_a.prefab"));
            Assert.AreEqual("Levels/floor01", ContentId.LogicalAddress("Levels/floor01.txt"));
            Assert.AreEqual("Props/ca_pew_row_a", ContentId.LogicalAddress("Props/ca_pew_row_a"));
            Assert.AreEqual("WebGL/Props/wall.v2", ContentId.LogicalAddress("WebGL/Props/wall.v2.prefab"));
            Assert.AreEqual("a.b/c", ContentId.LogicalAddress("a.b/c"));
            Assert.Throws<ArgumentException>(() => ContentId.LogicalAddress(""));
        }

        [Test]
        public void Address_WithAVariantPrefixesThePlatformTree()
        {
            Assert.AreEqual("Props/x", ContentId.Address(ContentId.Family.Props, ContentId.Variant.Shared, "x"));
            Assert.AreEqual("WebGL/Props/x", ContentId.Address(ContentId.Family.Props, ContentId.Variant.WebGL, "x"));
            Assert.AreEqual("Assets/NoSafeCircle/DoorPrototype/Content/Levels", ContentId.FolderPath(ContentId.Family.Data));
        }

        // ---- Lease and scope lifetime -----------------------------------------------------------

        [Test]
        public void Lease_DisposingTwiceReleasesOnce()
        {
            int releases = 0;
            var lease = new AssetLease<GameObject>(root, "test/root", () => releases++);

            lease.Dispose();
            lease.Dispose();

            Assert.AreEqual(1, releases);
            Assert.IsTrue(lease.IsReleased);
            Assert.IsNull(lease.Asset);
        }

        [Test]
        public void Lease_UnmanagedDisposeIsSafe()
        {
            AssetLease<GameObject> lease = AssetLease<GameObject>.Unmanaged(root, "test/root");

            Assert.DoesNotThrow(lease.Dispose);
            Assert.IsTrue(lease.IsReleased);
        }

        [Test]
        public void Scope_DisposesLeasesInReverseOrderOfAdding()
        {
            var order = new List<string>();
            var scope = new AssetScope("test");
            scope.Add(new AssetLease<GameObject>(root, "a", () => order.Add("a")));
            scope.Add(new AssetLease<GameObject>(root, "b", () => order.Add("b")));
            scope.Add(new AssetLease<GameObject>(root, "c", () => order.Add("c")));

            scope.Dispose();

            CollectionAssert.AreEqual(new[] { "c", "b", "a" }, order);
            Assert.AreEqual(0, scope.Count);
            Assert.IsTrue(scope.IsDisposed);
        }

        [Test]
        public void Scope_DisposingTwiceReleasesOnce_AndAddingAfterwardsThrows()
        {
            int releases = 0;
            var scope = new AssetScope("test");
            scope.Add(new AssetLease<GameObject>(root, "a", () => releases++));

            scope.Dispose();
            scope.Dispose();

            Assert.AreEqual(1, releases);
            Assert.Throws<ObjectDisposedException>(() =>
                scope.Add(new AssetLease<GameObject>(root, "b", null)));
        }

        [Test]
        public void Scope_RejectsAReleasedLease()
        {
            var scope = new AssetScope("test");
            var lease = new AssetLease<GameObject>(root, "a", null);
            lease.Dispose();

            Assert.Throws<ArgumentException>(() => scope.Add(lease));
        }

        [Test]
        public void Scope_LoadAsyncOwnsTheLeaseAndReturnsTheResult()
        {
            var scope = new AssetScope("test");

            Task<AssetLoadResult<GameObject>> load = scope.LoadAsync<GameObject>(fake, ProbeQuery, CancellationToken.None);

            Assert.IsTrue(load.IsCompleted);
            Assert.AreEqual(AssetLoadStatus.Success, load.Result.Status);
            Assert.AreEqual(1, scope.Count);
            CollectionAssert.DoesNotContain(fake.Events, "release:" + ProbeAddress);

            scope.Dispose();

            CollectionAssert.Contains(fake.Events, "release:" + ProbeAddress);
        }

        [Test]
        public void Scope_LoadAsyncOfMissingContentOwnsNothing()
        {
            var scope = new AssetScope("test");

            Task<AssetLoadResult<GameObject>> load = scope.LoadAsync<GameObject>(fake, MissingQuery, CancellationToken.None);

            Assert.IsTrue(load.IsCompleted);
            Assert.AreEqual(AssetLoadStatus.RequiredMissing, load.Result.Status);
            Assert.IsTrue(load.Result.IsFatal);
            Assert.AreEqual(0, scope.Count);
        }

        [Test]
        public void Scope_LoadAsyncWithACancelledTokenOwnsNothing()
        {
            var scope = new AssetScope("test");

            Task<AssetLoadResult<GameObject>> load = scope.LoadAsync<GameObject>(fake, ProbeQuery, new CancellationToken(true));

            Assert.IsTrue(load.IsCompleted);
            Assert.AreEqual(AssetLoadStatus.Cancelled, load.Result.Status);
            Assert.AreEqual(0, scope.Count);
            CollectionAssert.DoesNotContain(fake.Events, "load:" + ProbeAddress);
        }

        [Test]
        public void AssetLoad_RefusesAnInconsistentPairing()
        {
            AssetLoadResult<GameObject> success = AssetLoadResult<GameObject>.Success(root, "a");
            AssetLoadResult<GameObject> missing = AssetLoadResult<GameObject>.RequiredMissing("a", "gone");

            Assert.Throws<ArgumentException>(() => AssetLoad<GameObject>.Failed(success));
            Assert.Throws<ArgumentException>(() => AssetLoad<GameObject>.Leased(missing, AssetLease<GameObject>.Unmanaged(root, "a")));
            Assert.Throws<ArgumentNullException>(() => AssetLoad<GameObject>.Leased(success, null));
        }

        // ---- Pool lifetime ordering against the fake service ---------------------------------

        [Test]
        public void Pool_PrewarmCreatesTheInitialCapacityInactiveUnderTheRoot()
        {
            AddressablePrefabPool<PoolableProbe> pool = Prewarmed(2, 4, PoolOverflowPolicy.Reject);

            Assert.AreEqual(2, pool.IdleCount);
            Assert.AreEqual(0, pool.ActiveCount);
            Assert.IsTrue(pool.HoldsPrefab);
            Assert.AreEqual(4, root.transform.childCount, "two templates plus two instances");
            CollectionAssert.Contains(fake.Events, "load:" + ProbeAddress);
        }

        [Test]
        public void Pool_ReleasesThePrefabLeaseOnlyAfterTheLastInstanceReturns()
        {
            AddressablePrefabPool<PoolableProbe> pool = Prewarmed(1, 2, PoolOverflowPolicy.Reject);
            Assert.IsTrue(pool.TryCheckout(out PoolableProbe first));
            Assert.IsTrue(pool.TryCheckout(out PoolableProbe second));

            LogAssert.Expect(LogType.Warning, new Regex("still checked out"));
            pool.Dispose();

            Assert.IsTrue(pool.IsDisposed);
            Assert.IsTrue(pool.HoldsPrefab, "the lease must outlive checked-out instances");
            Assert.AreEqual(2, pool.Diagnostics.ActiveAtDisposal);
            CollectionAssert.DoesNotContain(fake.Events, "release:" + ProbeAddress);

            pool.Return(first);
            Assert.IsTrue(pool.HoldsPrefab, "one instance is still out");
            Assert.IsTrue(first == null, "an instance returned after disposal is destroyed");

            pool.Return(second);
            Assert.IsFalse(pool.HoldsPrefab);
            Assert.AreEqual("release:" + ProbeAddress, fake.Events[fake.Events.Count - 1]);
            Assert.IsTrue(second == null);
        }

        [Test]
        public void Pool_DisposeWithNothingCheckedOutReleasesAtOnceAndDestroysIdleInstances()
        {
            AddressablePrefabPool<PoolableProbe> pool = Prewarmed(3, 3, PoolOverflowPolicy.Reject);
            Assert.AreEqual(5, root.transform.childCount);

            pool.Dispose();

            Assert.IsFalse(pool.HoldsPrefab);
            Assert.AreEqual(0, pool.IdleCount);
            Assert.AreEqual(2, root.transform.childCount, "only the two templates remain");
            Assert.AreEqual(0, pool.Diagnostics.ActiveAtDisposal);
            CollectionAssert.Contains(fake.Events, "release:" + ProbeAddress);
        }

        [Test]
        public void Pool_CheckoutActivatesAndResets_ReturnResetsAndDeactivates()
        {
            AddressablePrefabPool<PoolableProbe> pool = Prewarmed(1, 1, PoolOverflowPolicy.Reject);

            Assert.IsTrue(pool.TryCheckout(out PoolableProbe instance));
            Assert.IsTrue(instance.gameObject.activeSelf);
            Assert.AreEqual(1, instance.Checkouts);
            Assert.IsTrue(instance.CheckedOut);
            Assert.AreEqual(1, pool.ActiveCount);

            pool.Return(instance);
            Assert.IsFalse(instance.gameObject.activeSelf);
            Assert.AreEqual(1, instance.Returns);
            Assert.IsFalse(instance.CheckedOut);
            Assert.AreEqual(1, pool.IdleCount);
            Assert.AreSame(root.transform, instance.transform.parent);
            Assert.AreEqual(1, pool.Diagnostics.PeakActive);
            Assert.IsFalse(pool.Diagnostics.HasAnomaly, pool.Diagnostics.Report(pool.Name));
        }

        [Test]
        public void Pool_RejectsAtMaximumWhenThePolicyIsReject()
        {
            AddressablePrefabPool<PoolableProbe> pool = Prewarmed(0, 1, PoolOverflowPolicy.Reject);

            Assert.IsTrue(pool.TryCheckout(out PoolableProbe only));
            Assert.IsFalse(pool.TryCheckout(out PoolableProbe refused));

            Assert.IsNull(refused);
            Assert.AreEqual(1, pool.Diagnostics.RejectedRequests);
            Assert.AreEqual(1, pool.Diagnostics.Expansions, "the first instance was created beyond an initial capacity of zero");
            Assert.AreEqual(1, pool.Diagnostics.PeakActive);
            Assert.IsNotNull(only);
        }

        [Test]
        public void Pool_ExpandsPastMaximumWhenThePolicyIsExpand()
        {
            AddressablePrefabPool<PoolableProbe> pool = Prewarmed(0, 1, PoolOverflowPolicy.Expand);

            Assert.IsTrue(pool.TryCheckout(out PoolableProbe first));
            Assert.IsTrue(pool.TryCheckout(out PoolableProbe second));

            Assert.AreNotSame(first, second);
            Assert.AreEqual(2, pool.Diagnostics.Expansions);
            Assert.AreEqual(2, pool.Diagnostics.PeakActive);
            Assert.AreEqual(0, pool.Diagnostics.RejectedRequests);
        }

        [Test]
        public void Pool_DoubleAndForeignReturnsAreCountedAndIgnored()
        {
            AddressablePrefabPool<PoolableProbe> pool = Prewarmed(1, 1, PoolOverflowPolicy.Reject);
            Assert.IsTrue(pool.TryCheckout(out PoolableProbe instance));
            pool.Return(instance);

            LogAssert.Expect(LogType.Warning, new Regex("not checked out"));
            pool.Return(instance);

            GameObject stranger = new GameObject("Stranger");
            stranger.transform.SetParent(root.transform, false);
            LogAssert.Expect(LogType.Warning, new Regex("not checked out"));
            pool.Return(stranger.AddComponent<PoolableProbe>());

            Assert.AreEqual(1, pool.Diagnostics.DoubleReturns);
            Assert.AreEqual(1, pool.Diagnostics.ForeignReturns);
            Assert.AreEqual(1, pool.IdleCount);
            Assert.IsTrue(pool.Diagnostics.HasAnomaly);
        }

        [Test]
        public void Pool_PrewarmOfMissingContentReportsRequiredMissingAndHoldsNothing()
        {
            var pool = new AddressablePrefabPool<PoolableProbe>("missing", 1, 1, PoolOverflowPolicy.Reject, root.transform);

            Task<AssetLoadResult<GameObject>> prewarm = pool.PrewarmAsync(fake, MissingQuery, CancellationToken.None);

            Assert.IsTrue(prewarm.IsCompleted);
            Assert.AreEqual(AssetLoadStatus.RequiredMissing, prewarm.Result.Status);
            Assert.IsFalse(pool.HoldsPrefab);
            Assert.AreEqual(0, pool.IdleCount);
            Assert.Throws<InvalidOperationException>(() => pool.TryCheckout(out PoolableProbe none));
        }

        [Test]
        public void Pool_PrewarmOfAPrefabWithoutTheComponentIsTypeMismatchAndReleasesTheLease()
        {
            var pool = new AddressablePrefabPool<PoolableProbe>("plain", 1, 1, PoolOverflowPolicy.Reject, root.transform);

            Task<AssetLoadResult<GameObject>> prewarm = pool.PrewarmAsync(fake, PlainQuery, CancellationToken.None);

            Assert.IsTrue(prewarm.IsCompleted);
            Assert.AreEqual(AssetLoadStatus.TypeMismatch, prewarm.Result.Status);
            StringAssert.Contains(nameof(PoolableProbe), prewarm.Result.Message);
            Assert.IsFalse(pool.HoldsPrefab);
            CollectionAssert.Contains(fake.Events, "release:" + PlainAddress);
        }

        [Test]
        public void Pool_PrewarmingTwiceThrows_AndConstructionValidatesCapacities()
        {
            AddressablePrefabPool<PoolableProbe> pool = Prewarmed(0, 1, PoolOverflowPolicy.Reject);

            Assert.Throws<InvalidOperationException>(() =>
                pool.PrewarmAsync(fake, ProbeQuery, CancellationToken.None).GetAwaiter().GetResult());
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                new AddressablePrefabPool<PoolableProbe>("bad", 2, 1, PoolOverflowPolicy.Reject, root.transform));
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                new AddressablePrefabPool<PoolableProbe>("bad", 0, 0, PoolOverflowPolicy.Reject, root.transform));
        }

        [Test]
        public void TryGetResident_AnswersOnlyWhileALeaseLives()
        {
            var scope = new AssetScope("test");
            Task<AssetLoadResult<GameObject>> load = scope.LoadAsync<GameObject>(fake, ProbeQuery, CancellationToken.None);
            Assert.IsTrue(load.IsCompleted);

            Assert.IsTrue(fake.TryGetResident(ProbeQuery, out GameObject resident));
            Assert.AreSame(load.Result.Asset, resident);

            scope.Dispose();

            Assert.IsFalse(fake.TryGetResident(ProbeQuery, out GameObject gone));
            Assert.IsNull(gone);
        }

        private AddressablePrefabPool<PoolableProbe> Prewarmed(int initial, int maximum, PoolOverflowPolicy policy)
        {
            var pool = new AddressablePrefabPool<PoolableProbe>("probes", initial, maximum, policy, root.transform);
            Task<AssetLoadResult<GameObject>> prewarm = pool.PrewarmAsync(fake, ProbeQuery, CancellationToken.None);
            Assert.IsTrue(prewarm.IsCompleted, "the fake completes synchronously");
            Assert.AreEqual(AssetLoadStatus.Success, prewarm.Result.Status, prewarm.Result.Message);
            return pool;
        }

        /// <summary>A poolable that counts what the pool asked of it.</summary>
        private sealed class PoolableProbe : MonoBehaviour, IPoolable
        {
            public int Checkouts { get; private set; }

            public int Returns { get; private set; }

            public bool CheckedOut { get; private set; }

            public void OnCheckout()
            {
                Checkouts++;
                CheckedOut = true;
            }

            public void OnReturn()
            {
                Returns++;
                CheckedOut = false;
            }
        }

        /// <summary>An <see cref="IAssetService"/> over a dictionary. It resolves through the real
        /// resolver and selection walk and completes every task before returning it.</summary>
        private sealed class FakeAssetService : IAssetService
        {
            private readonly IContentResolver resolver;
            private readonly Dictionary<string, Object> catalog = new Dictionary<string, Object>();
            private readonly Dictionary<string, Object> resident = new Dictionary<string, Object>();

            public FakeAssetService(IContentResolver resolver)
            {
                this.resolver = resolver;
            }

            /// <summary>"load:address" and "release:address", in the order they happened.</summary>
            public List<string> Events { get; } = new List<string>();

            public void Add(string address, Object asset)
            {
                catalog[address] = asset;
            }

            public Task<AssetLoad<T>> LoadAsync<T>(ContentQuery query, CancellationToken cancellation) where T : Object
            {
                IReadOnlyList<string> candidates = resolver.Resolve(query);
                if (cancellation.IsCancellationRequested)
                {
                    return Task.FromResult(AssetLoad<T>.Failed(AssetLoadResult<T>.Cancelled(candidates[0])));
                }

                CandidateSelection selection = ContentResolver.Select(candidates, address => Probe<T>(address));
                switch (selection.Status)
                {
                    case AssetLoadStatus.Success:
                    case AssetLoadStatus.FallbackUsed:
                        return Task.FromResult(Lease<T>(selection));
                    case AssetLoadStatus.TypeMismatch:
                        return Task.FromResult(AssetLoad<T>.Failed(
                            AssetLoadResult<T>.TypeMismatch(selection.Address, selection.Message)));
                    default:
                        return Task.FromResult(AssetLoad<T>.Failed(
                            AssetLoadResult<T>.RequiredMissing(selection.Address, selection.Message)));
                }
            }

            public Task<IReadOnlyList<AssetLoadResult<T>>> PreloadAsync<T>(ContentId.Family family, AssetScope owner,
                CancellationToken cancellation) where T : Object
            {
                throw new NotSupportedException("Preload is not exercised by these tests; it needs a catalog to enumerate.");
            }

            public bool TryGetResident<T>(ContentQuery query, out T asset) where T : Object
            {
                foreach (string candidate in resolver.Resolve(query))
                {
                    if (resident.TryGetValue(candidate, out Object found) && found is T typed)
                    {
                        asset = typed;
                        return true;
                    }
                }

                asset = null;
                return false;
            }

            private CandidateProbe Probe<T>(string address) where T : Object
            {
                if (!catalog.TryGetValue(address, out Object found))
                {
                    return CandidateProbe.Missing;
                }

                return found is T ? CandidateProbe.Found : CandidateProbe.WrongType;
            }

            private AssetLoad<T> Lease<T>(CandidateSelection selection) where T : Object
            {
                string address = selection.Address;
                T asset = (T)catalog[address];
                Events.Add("load:" + address);
                resident[address] = asset;
                var lease = new AssetLease<T>(asset, address, () =>
                {
                    Events.Add("release:" + address);
                    resident.Remove(address);
                });
                AssetLoadResult<T> result = selection.Status == AssetLoadStatus.Success
                    ? AssetLoadResult<T>.Success(asset, address)
                    : AssetLoadResult<T>.FallbackUsed(asset, address, selection.Message);
                return AssetLoad<T>.Leased(result, lease);
            }
        }
    }
}
