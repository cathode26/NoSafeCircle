using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine.AddressableAssets;
using UnityEngine.AddressableAssets.ResourceLocators;
using UnityEngine.ResourceManagement.AsyncOperations;
using UnityEngine.ResourceManagement.ResourceLocations;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>
    /// The loader. Resolves a query to catalog locations, loads by location, and hands back a typed
    /// result with a lease. It owns no content and keeps no list of handles to "release later".
    /// </summary>
    /// <remarks>
    /// <para>
    /// IT LOADS BY LOCATION, NOT BY KEY, AND THAT IS WHAT MAKES A MISSING VARIANT QUIET. Loading an absent
    /// key fails the operation and the ResourceManager's exception handler logs an error - which
    /// STANDARDS 8.4 forbids for an optional variant. Locating first reads the catalog Addressables has
    /// already loaded (<see cref="Addressables.ResourceLocators"/>), finds nothing without complaint,
    /// and retains the actual location for the load. This is
    /// SlotEngineGemReview 05 rule 7, "pre-resolved locations", and NOT the sediment it lists as
    /// "existence-check followed by a load lookup for the same key": the load uses the chosen location.
    /// </para>
    /// <para>
    /// LOGICAL ADDRESSES ARE THE KEYS OF THE RESIDENT TABLE. A folder entry names its assets with the file
    /// extension (see <see cref="ContentId.LogicalAddress"/>), a spawner asks without one, and this is
    /// where the two meet: every lease is registered under the logical address it was resolved from, and
    /// <see cref="TryGetResident{T}"/> answers in the resolver's fallback order. The table holds nothing
    /// a live lease does not hold; a released lease removes itself.
    /// </para>
    /// <para>
    /// Lifecycle knowledge lifted from Vincent's slot engine, adapted rather than copied: locate before you
    /// load, release a handle that failed as carefully as one that succeeded, and never clear the
    /// dependency cache on the way out - STANDARDS 8.6 makes that last one a rule.
    /// </para>
    /// </remarks>
    public sealed class AddressableAssetService : IAssetService
    {
        private sealed class Resident
        {
            public Object Asset;
            public int Leases;
        }

        private sealed class AddressableOperations : IAddressableAssetOperations
        {
            public IEnumerable<IResourceLocator> ResourceLocators => Addressables.ResourceLocators;

            public Task EnsureInitializedAsync() => AddressablesInitialization.EnsureInitializedAsync();

            public IAddressableAssetOperation<T> LoadAssetAsync<T>(IResourceLocation location) where T : Object =>
                new HandleOperation<T>(Addressables.LoadAssetAsync<T>(location));
        }

        private sealed class HandleOperation<T> : IAddressableAssetOperation<T> where T : Object
        {
            private readonly AsyncOperationHandle<T> handle;

            public HandleOperation(AsyncOperationHandle<T> handle)
            {
                this.handle = handle;
            }

            public bool Succeeded => handle.Status == AsyncOperationStatus.Succeeded;
            public T Result => handle.Result;
            public Exception OperationException => handle.OperationException;

            public Task<bool> WhenDoneOrCancelled(CancellationToken cancellation) =>
                AddressableHandles.WhenDoneOrCancelled(handle, cancellation);

            public void Release() => Addressables.Release(handle);
        }

        private readonly IContentResolver resolver;
        private readonly IAddressableAssetOperations operations;
        private readonly Dictionary<string, Resident> resident = new Dictionary<string, Resident>();

        public AddressableAssetService(IContentResolver resolver)
            : this(resolver, new AddressableOperations())
        {
        }

        internal AddressableAssetService(IContentResolver resolver, IAddressableAssetOperations operations)
        {
            this.resolver = resolver ?? throw new ArgumentNullException(nameof(resolver),
                "The service needs a resolver; it never forms an address itself.");
            this.operations = operations ?? throw new ArgumentNullException(nameof(operations));
        }

        public async Task<AssetLoad<T>> LoadAsync<T>(ContentQuery query, CancellationToken cancellation)
            where T : Object
        {
            await operations.EnsureInitializedAsync();
            IReadOnlyList<string> candidates = resolver.Resolve(query);
            if (cancellation.IsCancellationRequested)
            {
                return AssetLoad<T>.Failed(AssetLoadResult<T>.Cancelled(candidates[0]));
            }

            Dictionary<string, List<IResourceLocation>> catalog = IndexLocations();
            IResourceLocation location = null;
            CandidateSelection selection = ContentResolver.Select(candidates, address =>
                Probe(catalog, address, typeof(T), out location));
            switch (selection.Status)
            {
                case AssetLoadStatus.RequiredMissing:
                    return AssetLoad<T>.Failed(AssetLoadResult<T>.RequiredMissing(selection.Address, selection.Message));
                case AssetLoadStatus.TypeMismatch:
                    return AssetLoad<T>.Failed(AssetLoadResult<T>.TypeMismatch(selection.Address, selection.Message));
            }

            AssetLoad<T> load = await LoadLocationAsync<T>(location, selection.Address, cancellation);
            if (selection.Status != AssetLoadStatus.FallbackUsed || !load.Result.HasAsset)
            {
                return load;
            }

            return AssetLoad<T>.Leased(
                AssetLoadResult<T>.FallbackUsed(load.Result.Asset, selection.Address, selection.Message), load.Lease);
        }

        public async Task<IReadOnlyList<AssetLoadResult<T>>> PreloadAsync<T>(ContentId.Family family,
            AssetScope owner, CancellationToken cancellation) where T : Object
        {
            if (owner == null)
            {
                throw new ArgumentNullException(nameof(owner), "A preload needs the scope that will own what it loads.");
            }

            await operations.EnsureInitializedAsync();

            // Start every load before awaiting any, so the bundle work overlaps instead of serialising
            // one frame per asset. Results come back in catalog order regardless.
            IList<IResourceLocation> locations = Locate(ContentId.FamilyLabel(family), typeof(T));
            var loads = new List<Task<AssetLoadResult<T>>>(locations.Count);
            foreach (IResourceLocation location in locations)
            {
                loads.Add(LoadAndOwnAsync<T>(location, owner, cancellation));
            }

            // Each task settles its own lease even if a sibling faults. WhenAll observes every
            // started task and preserves catalog order while ownership follows completion order.
            //
            // Task.WhenAll hands back its result as a bare array. Returning that array directly
            // through this IReadOnlyList<T>-typed method leaks the concrete array type to every
            // caller: an array's IReadOnlyList<T>.Count / ICollection.Count are runtime-supplied
            // (SZArrayHelper), not an ordinary reflectable public property, so a caller that
            // inspects "Count" by reflection (as NUnit's older Has.Count constraint does) throws
            // "Property Count was not found" rather than reading the value. Copy into a List<T> so
            // the concrete type actually carries the public Count member the declared contract
            // implies, regardless of what inspects it.
            AssetLoadResult<T>[] completed = await Task.WhenAll(loads);
            var results = new List<AssetLoadResult<T>>(completed.Length);
            results.AddRange(completed);
            if (owner.IsDisposed)
            {
                for (int i = 0; i < results.Count; i++)
                {
                    if (results[i].HasAsset)
                    {
                        results[i] = AssetLoadResult<T>.Cancelled(results[i].Address);
                    }
                }
            }

            return results;
        }

        private async Task<AssetLoadResult<T>> LoadAndOwnAsync<T>(IResourceLocation location,
            AssetScope owner, CancellationToken cancellation) where T : Object
        {
            string address = location.PrimaryKey;
            AssetLease<T> unowned = null;
            try
            {
                address = ContentId.LogicalAddress(address);
                if (owner.IsDisposed)
                {
                    return AssetLoadResult<T>.Cancelled(address);
                }

                AssetLoad<T> load = await LoadLocationAsync<T>(location, address, cancellation);
                if (!load.Result.HasAsset)
                {
                    return load.Result;
                }

                unowned = load.Lease;
                if (owner.IsDisposed || cancellation.IsCancellationRequested)
                {
                    unowned.Dispose();
                    return AssetLoadResult<T>.Cancelled(address);
                }

                owner.Add(unowned);
                unowned = null;
                return load.Result;
            }
            catch (Exception failure)
            {
                try
                {
                    unowned?.Dispose();
                }
                catch (Exception releaseFailure)
                {
                    failure = new AggregateException(failure, releaseFailure);
                }

                return AssetLoadResult<T>.LoadFailed(address,
                    "'" + address + "' failed to preload: " + failure.Message);
            }
        }

        public bool TryGetResident<T>(ContentQuery query, out T asset) where T : Object
        {
            IReadOnlyList<string> candidates = resolver.Resolve(query);
            for (int i = 0; i < candidates.Count; i++)
            {
                if (resident.TryGetValue(candidates[i], out Resident entry) && entry.Asset is T typed)
                {
                    asset = typed;
                    return true;
                }
            }

            asset = null;
            return false;
        }

        private async Task<AssetLoad<T>> LoadLocationAsync<T>(IResourceLocation location, string address,
            CancellationToken cancellation) where T : Object
        {
            if (cancellation.IsCancellationRequested)
            {
                return AssetLoad<T>.Failed(AssetLoadResult<T>.Cancelled(address));
            }

            IAddressableAssetOperation<T> operation = operations.LoadAssetAsync<T>(location);
            bool releaseHandle = true;
            try
            {
                bool finished = await operation.WhenDoneOrCancelled(cancellation);
                if (!finished)
                {
                    // The helper releases the handle when the load lands; it is not ours to touch now.
                    releaseHandle = false;
                    return AssetLoad<T>.Failed(AssetLoadResult<T>.Cancelled(address));
                }

                if (!operation.Succeeded || operation.Result == null)
                {
                    string reason = operation.OperationException?.Message ?? "no exception was reported";
                    return AssetLoad<T>.Failed(AssetLoadResult<T>.LoadFailed(address,
                        "'" + address + "' failed to load: " + reason));
                }

                if (cancellation.IsCancellationRequested)
                {
                    return AssetLoad<T>.Failed(AssetLoadResult<T>.Cancelled(address));
                }

                T asset = operation.Result;
                Register(address, asset);
                var lease = new AssetLease<T>(asset, address, () =>
                {
                    try
                    {
                        operation.Release();
                    }
                    finally
                    {
                        Unregister(address);
                    }
                });
                releaseHandle = false;
                return AssetLoad<T>.Leased(AssetLoadResult<T>.Success(asset, address), lease);
            }
            finally
            {
                if (releaseHandle)
                {
                    operation.Release();
                }
            }
        }

        private static CandidateProbe Probe(Dictionary<string, List<IResourceLocation>> catalog,
            string address, Type type, out IResourceLocation selected)
        {
            selected = null;
            if (!catalog.TryGetValue(address, out List<IResourceLocation> locations))
            {
                return CandidateProbe.Missing;
            }

            foreach (IResourceLocation location in locations)
            {
                if (type.IsAssignableFrom(location.ResourceType))
                {
                    selected = location;
                    return CandidateProbe.Found;
                }
            }

            return CandidateProbe.WrongType;
        }

        private Dictionary<string, List<IResourceLocation>> IndexLocations()
        {
            // Locators can be replaced when a catalog is updated. Keep this snapshot local to one
            // request; a service-wide index would retain removed locations and miss new variants.
            var catalog = new Dictionary<string, List<IResourceLocation>>(StringComparer.Ordinal);
            foreach (IResourceLocator locator in operations.ResourceLocators)
            {
                foreach (object key in locator.Keys)
                {
                    if (!locator.Locate(key, null, out IList<IResourceLocation> locations))
                    {
                        continue;
                    }

                    foreach (IResourceLocation location in locations)
                    {
                        AddLocation(catalog, key as string, location);
                        AddLocation(catalog, location.PrimaryKey, location);
                        AddLocation(catalog, ContentId.LogicalAddress(location.PrimaryKey), location);
                    }
                }
            }

            return catalog;
        }

        private static void AddLocation(Dictionary<string, List<IResourceLocation>> catalog,
            string address, IResourceLocation location)
        {
            if (address == null)
            {
                return;
            }

            if (!catalog.TryGetValue(address, out List<IResourceLocation> locations))
            {
                locations = new List<IResourceLocation>();
                catalog.Add(address, locations);
            }

            if (!locations.Contains(location))
            {
                locations.Add(location);
            }
        }

        private IList<IResourceLocation> Locate(object key, Type type)
        {
            foreach (IResourceLocator locator in operations.ResourceLocators)
            {
                if (locator.Locate(key, type, out IList<IResourceLocation> locations) && locations.Count > 0)
                {
                    return locations;
                }
            }

            return Array.Empty<IResourceLocation>();
        }

        private void Register(string address, Object asset)
        {
            if (!resident.TryGetValue(address, out Resident entry))
            {
                entry = new Resident { Asset = asset };
                resident[address] = entry;
            }

            entry.Leases++;
        }

        private void Unregister(string address)
        {
            if (resident.TryGetValue(address, out Resident entry) && --entry.Leases == 0)
            {
                resident.Remove(address);
            }
        }
    }
}
