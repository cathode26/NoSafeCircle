using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using NoSafeCircle.DoorPrototype.Content;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AddressableAssets.ResourceLocators;
using UnityEngine.ResourceManagement.ResourceLocations;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Content
{
    /// <summary>
    /// Pure/component regression tests for F8 logical catalog lookup and F9 preload ownership.
    /// Exercises the production service, resolver, scopes and leases. Only package
    /// initialization, catalogs and individual load operations are replaced. No Addressables static
    /// state, scenes, project assets, settings or files are read or written.
    /// </summary>
    public sealed class AddressableAssetServiceTests
    {
        private readonly List<Object> assets = new List<Object>();
        private readonly List<IDisposable> owners = new List<IDisposable>();
        private MemoryOperations operations;
        private AddressableAssetService service;

        [SetUp]
        public void SetUp()
        {
            operations = new MemoryOperations();
            service = new AddressableAssetService(ContentResolver.SharedOnly(), operations);
        }

        [TearDown]
        public void TearDown()
        {
            for (int i = owners.Count - 1; i >= 0; i--)
            {
                owners[i].Dispose();
            }

            owners.Clear();
            operations.Dispose();
            foreach (Object asset in assets)
            {
                Object.DestroyImmediate(asset);
            }

            assets.Clear();
        }

        [TestCase("probe")]
        [TestCase("probe.prefab")]
        public void DirectLoad_UsesTheActualExtensionfulPrefabLocation(string requestedId)
        {
            Entry entry = AddPrefab("Props/probe.prefab");
            Task<AssetLoad<GameObject>> pending = service.LoadAsync<GameObject>(Query(requestedId), CancellationToken.None);

            Assert.That(operations.Loads, Has.Count.EqualTo(1));
            Assert.That(operations.Loads[0].Location, Is.SameAs(entry.Location));
            Assert.That(pending.IsCompleted, Is.False);
            operations.Finish(0);
            AssetLoad<GameObject> load = Own(Completed(pending));

            Assert.That(load.Result.Status, Is.EqualTo(AssetLoadStatus.Success));
            Assert.That(load.Result.Asset, Is.SameAs(entry.Asset));
            Assert.That(load.Result.Address, Is.EqualTo("Props/" + requestedId));
            Assert.That(service.TryGetResident<GameObject>(Query(requestedId), out GameObject resident), Is.True);
            Assert.That(resident, Is.SameAs(entry.Asset));
            load.Lease.Dispose();
            load.Lease.Dispose();
            AssertReleased(0);
            Assert.That(service.TryGetResident<GameObject>(Query(requestedId), out _), Is.False);
        }

        [Test]
        public void DirectLoad_NormalizesNonPrefabExtensionsWithoutGuessingTheirSuffix()
        {
            TextAsset text = Keep(new TextAsset("catalog data"));
            Entry entry = operations.Add("Levels/chapter.customdata", text);
            var query = new ContentQuery(ContentId.Family.Data, "chapter");
            Task<AssetLoad<TextAsset>> pending = service.LoadAsync<TextAsset>(query, CancellationToken.None);
            operations.Finish(0);
            AssetLoad<TextAsset> load = Own(Completed(pending));

            Assert.That(load.Result.Status, Is.EqualTo(AssetLoadStatus.Success));
            Assert.That(operations.Loads[0].Location, Is.SameAs(entry.Location));
            Assert.That(load.Result.Address, Is.EqualTo("Levels/chapter"));
            load.Lease.Dispose();
            AssertReleased(0);
            Assert.That(service.TryGetResident<TextAsset>(query, out _), Is.False);
        }

        [TestCase(true, AssetLoadStatus.Success, "Desktop/Props/probe")]
        [TestCase(false, AssetLoadStatus.FallbackUsed, "Props/probe")]
        public void DirectLoad_PreservesPlatformThenSharedOrder(bool hasDesktop, AssetLoadStatus status, string address)
        {
            Entry shared = AddPrefab("Props/probe.prefab");
            Entry desktop = hasDesktop ? AddPrefab("Desktop/Props/probe.prefab") : null;
            service = new AddressableAssetService(new ContentResolver(new[]
                { ContentId.Variant.Desktop, ContentId.Variant.Shared }), operations);

            Task<AssetLoad<GameObject>> pending = service.LoadAsync<GameObject>(Query("probe"), CancellationToken.None);
            operations.Finish(0);
            AssetLoad<GameObject> load = Own(Completed(pending));

            Assert.That(load.Result.Status, Is.EqualTo(status));
            Assert.That(load.Result.Address, Is.EqualTo(address));
            Assert.That(operations.Loads[0].Location, Is.SameAs((desktop ?? shared).Location));
            load.Lease.Dispose();
            AssertReleased(0);
            AssertNoResidents("probe");
        }

        [Test]
        public void DirectLoad_WrongTypeAtPreferredVariantDoesNotUseSharedPrefab()
        {
            operations.Add("Desktop/Props/probe.asset", Keep(new TextAsset("wrong type")));
            AddPrefab("Props/probe.prefab");
            service = new AddressableAssetService(new ContentResolver(new[]
                { ContentId.Variant.Desktop, ContentId.Variant.Shared }), operations);

            AssetLoad<GameObject> load = Completed(service.LoadAsync<GameObject>(Query("probe"), CancellationToken.None));

            Assert.That(load.Result.Status, Is.EqualTo(AssetLoadStatus.TypeMismatch));
            Assert.That(load.Result.Address, Is.EqualTo("Desktop/Props/probe"));
            Assert.That(operations.Loads, Is.Empty);
            AssertNoResidents("probe");
        }

        [Test]
        public void DirectLoad_TypeFiltersAllLocationsSharingTheLogicalStem()
        {
            operations.Add("Props/probe.txt", Keep(new TextAsset("different asset type")));
            Entry prefab = AddPrefab("Props/probe.prefab");

            Task<AssetLoad<GameObject>> pending = service.LoadAsync<GameObject>(Query("probe"), CancellationToken.None);
            operations.Finish(0);
            AssetLoad<GameObject> load = Own(Completed(pending));

            Assert.That(load.Result.Status, Is.EqualTo(AssetLoadStatus.Success));
            Assert.That(operations.Loads[0].Location, Is.SameAs(prefab.Location));
            load.Lease.Dispose();
            AssertReleased(0);
            AssertNoResidents("probe");
        }

        [Test]
        public void DirectLoad_RebuildsLocationsAfterCatalogReplacement()
        {
            AddPrefab("Props/probe.prefab");
            Task<AssetLoad<GameObject>> first = service.LoadAsync<GameObject>(Query("probe"), CancellationToken.None);
            operations.Finish(0);
            Own(Completed(first)).Lease.Dispose();

            operations.Catalog = new MemoryCatalog();
            AssetLoad<GameObject> missing = Completed(service.LoadAsync<GameObject>(Query("probe"), CancellationToken.None));
            Assert.That(missing.Result.Status, Is.EqualTo(AssetLoadStatus.RequiredMissing));
            Assert.That(operations.Loads, Has.Count.EqualTo(1));

            Entry replacement = AddPrefab("Props/probe.prefab");
            Task<AssetLoad<GameObject>> second = service.LoadAsync<GameObject>(Query("probe"), CancellationToken.None);
            operations.Finish(1);
            AssetLoad<GameObject> load = Own(Completed(second));
            Assert.That(load.Result.Asset, Is.SameAs(replacement.Asset));
            Assert.That(operations.Loads[1].Location, Is.SameAs(replacement.Location));
            load.Lease.Dispose();
            AssertReleased(0, 1);
            AssertNoResidents("probe");
        }

        [TestCase(false)]
        [TestCase(true)]
        public void DirectLoad_CancellationReleasesEveryStartedHandle(bool cancelBeforeStart)
        {
            AddPrefab("Props/probe.prefab");
            using (var cancellation = new CancellationTokenSource())
            {
                if (cancelBeforeStart) cancellation.Cancel();
                Task<AssetLoad<GameObject>> pending = service.LoadAsync<GameObject>(Query("probe"), cancellation.Token);
                cancellation.Cancel();
                Assert.That(Completed(pending).Result.Status, Is.EqualTo(AssetLoadStatus.Cancelled));

                if (cancelBeforeStart)
                {
                    Assert.That(operations.Loads, Is.Empty);
                }
                else
                {
                    Assert.That(operations.Loads[0].Releases, Is.Zero);
                    operations.Finish(0);
                    AssertReleased(0);
                }

                AssertNoResidents("probe");
            }
        }

        [Test]
        public void Preload_OwnsOutOfOrderCompletionsAndReturnsCatalogOrder()
        {
            AddThreePrefabs();
            AssetScope owner = Scope();
            Task<IReadOnlyList<AssetLoadResult<GameObject>>> pending = Preload(owner);
            Assert.That(operations.Loads, Has.Count.EqualTo(3), "All loads must start before the first completes.");

            operations.Finish(2);
            Assert.That(owner.Count, Is.EqualTo(1));
            Assert.That(service.TryGetResident<GameObject>(Query("third"), out _), Is.True);
            Assert.That(pending.IsCompleted, Is.False);
            operations.Finish(0);
            operations.Finish(1);
            IReadOnlyList<AssetLoadResult<GameObject>> results = Completed(pending);

            AssertOrdered(results, AssetLoadStatus.Success, AssetLoadStatus.Success, AssetLoadStatus.Success);
            Assert.That(owner.Count, Is.EqualTo(3));
            owner.Dispose();
            owner.Dispose();
            AssertReleased(0, 1, 2);
            AssertNoResidents("first", "second", "third");
        }

        [TestCase(false)]
        [TestCase(true)]
        public void Preload_DisposedOwnerBeforeLoadsStartReturnsCancelled(bool disposeDuringInitialization)
        {
            AddThreePrefabs();
            AssetScope owner = Scope();
            var ready = new TaskCompletionSource<bool>();
            operations.Ready = disposeDuringInitialization ? ready.Task : Task.CompletedTask;
            if (!disposeDuringInitialization) owner.Dispose();
            Task<IReadOnlyList<AssetLoadResult<GameObject>>> pending = Preload(owner);
            owner.Dispose();
            ready.SetResult(true);

            AssertOrdered(Completed(pending), AssetLoadStatus.Cancelled, AssetLoadStatus.Cancelled, AssetLoadStatus.Cancelled);
            Assert.That(operations.Loads, Is.Empty);
            Assert.That(owner.Count, Is.Zero);
            AssertNoResidents("first", "second", "third");
        }

        [TestCase(false)]
        [TestCase(true)]
        public void Preload_DisposedOwnerDrainsAllLoadsIncludingAlreadyCompletedOnes(bool completeOneBeforeDisposal)
        {
            AddThreePrefabs();
            AssetScope owner = Scope();
            Task<IReadOnlyList<AssetLoadResult<GameObject>>> pending = Preload(owner);
            if (completeOneBeforeDisposal)
            {
                operations.Finish(2);
                Assert.That(owner.Count, Is.EqualTo(1));
            }

            owner.Dispose();
            operations.Finish(1);
            if (!completeOneBeforeDisposal) operations.Finish(2);
            Assert.That(pending.IsCompleted, Is.False);
            operations.Finish(0);

            AssertOrdered(Completed(pending), AssetLoadStatus.Cancelled, AssetLoadStatus.Cancelled, AssetLoadStatus.Cancelled);
            Assert.That(owner.Count, Is.Zero);
            AssertReleased(0, 1, 2);
            AssertNoResidents("first", "second", "third");
        }

        [TestCase(false)]
        [TestCase(true)]
        public void Preload_CancellationReleasesPendingHandlesOnCompletion(bool cancelBeforeStart)
        {
            AddThreePrefabs();
            AssetScope owner = Scope();
            using (var cancellation = new CancellationTokenSource())
            {
                if (cancelBeforeStart) cancellation.Cancel();
                Task<IReadOnlyList<AssetLoadResult<GameObject>>> pending =
                    service.PreloadAsync<GameObject>(ContentId.Family.Props, owner, cancellation.Token);
                cancellation.Cancel();

                AssertOrdered(Completed(pending), AssetLoadStatus.Cancelled, AssetLoadStatus.Cancelled, AssetLoadStatus.Cancelled);
                Assert.That(owner.Count, Is.Zero);
                if (cancelBeforeStart)
                {
                    Assert.That(operations.Loads, Is.Empty);
                }
                else
                {
                    foreach (PendingLoad load in operations.Loads) Assert.That(load.Releases, Is.Zero);
                    operations.Finish(2);
                    operations.Finish(0);
                    operations.Finish(1);
                    AssertReleased(0, 1, 2);
                }

                AssertNoResidents("first", "second", "third");
            }
        }

        [TestCase(false)]
        [TestCase(true)]
        public void Preload_FailedOrFaultedLoadDoesNotAbandonLaterSuccessfulLoads(bool faulted)
        {
            AddThreePrefabs();
            AssetScope owner = Scope();
            Task<IReadOnlyList<AssetLoadResult<GameObject>>> pending = Preload(owner);
            if (faulted) operations.Loads[0].Fault();
            else operations.Finish(0, returnNull: true);
            AssertReleased(0);
            Assert.That(pending.IsCompleted, Is.False);
            operations.Finish(2);
            operations.Finish(1);

            AssertOrdered(Completed(pending), AssetLoadStatus.LoadFailed, AssetLoadStatus.Success, AssetLoadStatus.Success);
            Assert.That(owner.Count, Is.EqualTo(2));
            owner.Dispose();
            AssertReleased(0, 1, 2);
            AssertNoResidents("first", "second", "third");
        }

        [Test]
        public void Preload_ThrownLoadDoesNotAbandonEarlierOrLaterPendingLoads()
        {
            AddPrefab("Props/first.prefab");
            AddPrefab("Props/second.prefab").ThrowOnLoad = true;
            AddPrefab("Props/third.prefab");
            AssetScope owner = Scope();
            Task<IReadOnlyList<AssetLoadResult<GameObject>>> pending = Preload(owner);
            Assert.That(operations.Attempts, Is.EqualTo(3));
            Assert.That(operations.Loads, Has.Count.EqualTo(2));
            operations.Finish(1);
            Assert.That(pending.IsCompleted, Is.False);
            operations.Finish(0);

            AssertOrdered(Completed(pending), AssetLoadStatus.Success, AssetLoadStatus.LoadFailed, AssetLoadStatus.Success);
            Assert.That(owner.Count, Is.EqualTo(2));
            owner.Dispose();
            AssertReleased(0, 1);
            AssertNoResidents("first", "second", "third");
        }

        [Test]
        public void Preload_ReleaseExceptionDoesNotAbandonSiblingsOrResidentEntries()
        {
            AddPrefab("Props/first.prefab").ThrowAfterRelease = true;
            AddPrefab("Props/second.prefab");
            AddPrefab("Props/third.prefab");
            AssetScope owner = Scope();
            Task<IReadOnlyList<AssetLoadResult<GameObject>>> pending = Preload(owner);
            owner.Dispose();
            operations.Finish(0);
            Assert.That(pending.IsCompleted, Is.False);
            operations.Finish(2);
            operations.Finish(1);

            AssertOrdered(Completed(pending), AssetLoadStatus.LoadFailed, AssetLoadStatus.Cancelled, AssetLoadStatus.Cancelled);
            Assert.That(owner.Count, Is.Zero);
            AssertReleased(0, 1, 2);
            AssertNoResidents("first", "second", "third");
        }

        private static ContentQuery Query(string id) => new ContentQuery(ContentId.Family.Props, id);

        private Entry AddPrefab(string address) => operations.Add(address, Keep(new GameObject(address)));

        private void AddThreePrefabs()
        {
            AddPrefab("Props/first.prefab");
            AddPrefab("Props/second.prefab");
            AddPrefab("Props/third.prefab");
        }

        private T Keep<T>(T asset) where T : Object
        {
            assets.Add(asset);
            return asset;
        }

        private AssetScope Scope()
        {
            var owner = new AssetScope("test-preload");
            owners.Add(owner);
            return owner;
        }

        private AssetLoad<T> Own<T>(AssetLoad<T> load) where T : Object
        {
            if (load.Lease != null) owners.Add(load.Lease);
            return load;
        }

        private Task<IReadOnlyList<AssetLoadResult<GameObject>>> Preload(AssetScope owner) =>
            service.PreloadAsync<GameObject>(ContentId.Family.Props, owner, CancellationToken.None);

        private static T Completed<T>(Task<T> task)
        {
            Assert.That(task.IsCompleted, Is.True, "Tests drive every completion explicitly; never block on a pending task.");
            return task.GetAwaiter().GetResult();
        }

        private static void AssertOrdered(IReadOnlyList<AssetLoadResult<GameObject>> results,
            AssetLoadStatus first, AssetLoadStatus second, AssetLoadStatus third)
        {
            Assert.That(results, Has.Count.EqualTo(3));
            Assert.That(results[0].Address, Is.EqualTo("Props/first"));
            Assert.That(results[1].Address, Is.EqualTo("Props/second"));
            Assert.That(results[2].Address, Is.EqualTo("Props/third"));
            Assert.That(results[0].Status, Is.EqualTo(first));
            Assert.That(results[1].Status, Is.EqualTo(second));
            Assert.That(results[2].Status, Is.EqualTo(third));
        }

        private void AssertReleased(params int[] indices)
        {
            Assert.That(indices, Is.Not.Empty);
            foreach (int index in indices)
            {
                Assert.That(operations.Loads[index].Releases, Is.EqualTo(1), "Each handle must be released exactly once.");
                Assert.That(operations.Loads[index].IsReleased, Is.True);
            }
        }

        private void AssertNoResidents(params string[] ids)
        {
            foreach (string id in ids)
            {
                Assert.That(service.TryGetResident<GameObject>(Query(id), out _), Is.False, id);
            }
        }

        private sealed class Entry
        {
            public IResourceLocation Location;
            public Object Asset;
            public bool ThrowOnLoad;
            public bool ThrowAfterRelease;
        }

        private sealed class PendingLoad
        {
            public IResourceLocation Location;
            public Action<bool> Finish;
            public Action Fault;
            public int Releases;
            public bool IsFinished;
            public bool IsReleased;
            public bool ThrowAfterRelease;
        }

        private sealed class ManualOperation<T> : IAddressableAssetOperation<T> where T : Object
        {
            private readonly TaskCompletionSource<bool> completion = new TaskCompletionSource<bool>();
            private readonly PendingLoad load;
            private bool releaseOnCompletion;

            public ManualOperation(PendingLoad load)
            {
                this.load = load;
            }

            public bool Succeeded { get; private set; }
            public T Result { get; private set; }
            public Exception OperationException => null;

            public async Task<bool> WhenDoneOrCancelled(CancellationToken cancellation)
            {
                using (cancellation.Register(() =>
                {
                    releaseOnCompletion = true;
                    completion.TrySetResult(false);
                }))
                {
                    return await completion.Task;
                }
            }

            public void Finish(T asset)
            {
                load.IsFinished = true;
                Result = asset;
                Succeeded = true;
                if (releaseOnCompletion) Release();
                else completion.SetResult(true);
            }

            public void Fault()
            {
                load.IsFinished = true;
                completion.SetException(new InvalidOperationException("Deliberate asynchronous load failure."));
            }

            public void Release()
            {
                load.Releases++;
                load.IsReleased = true;
                if (load.ThrowAfterRelease) throw new InvalidOperationException("Deliberate post-release failure.");
            }
        }

        private sealed class MemoryCatalog : IResourceLocator
        {
            private readonly Dictionary<object, IList<IResourceLocation>> entries =
                new Dictionary<object, IList<IResourceLocation>>();

            public string LocatorId => "in-memory-regression-catalog";
            public IEnumerable<object> Keys => entries.Keys;
            public IEnumerable<IResourceLocation> AllLocations
            {
                get
                {
                    var visited = new HashSet<IResourceLocation>();
                    foreach (IList<IResourceLocation> locations in entries.Values)
                    {
                        foreach (IResourceLocation location in locations)
                        {
                            if (visited.Add(location)) yield return location;
                        }
                    }
                }
            }

            public void Add(IResourceLocation location)
            {
                entries.Add(location.PrimaryKey, new[] { location });
                string label = location.PrimaryKey.StartsWith("Levels/", StringComparison.Ordinal) ? "levels" : "props";
                if (!entries.TryGetValue(label, out IList<IResourceLocation> locations))
                {
                    locations = new List<IResourceLocation>();
                    entries.Add(label, locations);
                }

                locations.Add(location);
            }

            public bool Locate(object key, Type type, out IList<IResourceLocation> locations)
            {
                if (!entries.TryGetValue(key, out IList<IResourceLocation> matches))
                {
                    locations = null;
                    return false;
                }

                var compatible = new List<IResourceLocation>();
                foreach (IResourceLocation location in matches)
                {
                    if (type == null || type.IsAssignableFrom(location.ResourceType)) compatible.Add(location);
                }

                locations = compatible;
                return compatible.Count > 0;
            }
        }

        private sealed class MemoryOperations : IAddressableAssetOperations, IDisposable
        {
            private readonly Dictionary<IResourceLocation, Entry> entries = new Dictionary<IResourceLocation, Entry>();

            public MemoryCatalog Catalog = new MemoryCatalog();
            public readonly List<PendingLoad> Loads = new List<PendingLoad>();
            public int Attempts;
            public Task Ready = Task.CompletedTask;
            public IEnumerable<IResourceLocator> ResourceLocators => new[] { Catalog };

            public Task EnsureInitializedAsync() => Ready;

            public Entry Add(string key, Object asset)
            {
                var entry = new Entry
                {
                    Location = new ResourceLocationBase(key, key, "test-only", asset.GetType()),
                    Asset = asset
                };
                entries.Add(entry.Location, entry);
                Catalog.Add(entry.Location);
                return entry;
            }

            public IAddressableAssetOperation<T> LoadAssetAsync<T>(IResourceLocation location) where T : Object
            {
                Attempts++;
                Entry entry = entries[location];
                if (entry.ThrowOnLoad) throw new InvalidOperationException("Deliberate handle-creation failure.");
                var load = new PendingLoad
                {
                    Location = location,
                    ThrowAfterRelease = entry.ThrowAfterRelease
                };
                var operation = new ManualOperation<T>(load);
                load.Finish = returnNull => operation.Finish(returnNull ? null : (T)entry.Asset);
                load.Fault = operation.Fault;
                Loads.Add(load);
                return operation;
            }

            public void Finish(int index, bool returnNull = false)
            {
                Loads[index].Finish(returnNull);
            }

            public void Dispose()
            {
                // Cleanup also runs after an assertion failure. Complete any pending test callbacks.
                foreach (PendingLoad load in Loads)
                {
                    load.ThrowAfterRelease = false;
                    if (!load.IsFinished) load.Finish(false);
                }
            }
        }
    }
}
