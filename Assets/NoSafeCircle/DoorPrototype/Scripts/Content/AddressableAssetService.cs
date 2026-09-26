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
    /// STANDARDS 8.4 forbids for an optional variant. Locating first costs one in-memory lookup against
    /// the catalog Addressables has already loaded (<see cref="Addressables.ResourceLocators"/>), finds
    /// nothing without complaint, and gives the load a location it cannot fail to find. This is
    /// SlotEngineGemReview 05 rule 7, "pre-resolved locations", and NOT the sediment it lists as
    /// "existence-check followed by a load lookup for the same key": nothing is looked up twice.
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

        private readonly IContentResolver resolver;
        private readonly Dictionary<string, Resident> resident = new Dictionary<string, Resident>();

        public AddressableAssetService(IContentResolver resolver)
        {
            this.resolver = resolver ?? throw new ArgumentNullException(nameof(resolver),
                "The service needs a resolver; it never forms an address itself.");
        }

        public async Task<AssetLoad<T>> LoadAsync<T>(ContentQuery query, CancellationToken cancellation)
            where T : Object
        {
            await AddressablesInitialization.EnsureInitializedAsync();
            IReadOnlyList<string> candidates = resolver.Resolve(query);
            if (cancellation.IsCancellationRequested)
            {
                return AssetLoad<T>.Failed(AssetLoadResult<T>.Cancelled(candidates[0]));
            }

            CandidateSelection selection = ContentResolver.Select(candidates, address => Probe(address, typeof(T)));
            switch (selection.Status)
            {
                case AssetLoadStatus.RequiredMissing:
                    return AssetLoad<T>.Failed(AssetLoadResult<T>.RequiredMissing(selection.Address, selection.Message));
                case AssetLoadStatus.TypeMismatch:
                    return AssetLoad<T>.Failed(AssetLoadResult<T>.TypeMismatch(selection.Address, selection.Message));
            }

            IResourceLocation location = Locate(selection.Address, typeof(T))[0];
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

            await AddressablesInitialization.EnsureInitializedAsync();

            // Start every load before awaiting any, so the bundle work overlaps instead of serialising
            // one frame per asset. Results come back in catalog order regardless.
            IList<IResourceLocation> locations = Locate(ContentId.FamilyLabel(family), typeof(T));
            var loads = new List<Task<AssetLoad<T>>>(locations.Count);
            foreach (IResourceLocation location in locations)
            {
                loads.Add(LoadLocationAsync<T>(location, ContentId.LogicalAddress(location.PrimaryKey), cancellation));
            }

            var results = new List<AssetLoadResult<T>>(loads.Count);
            foreach (Task<AssetLoad<T>> pending in loads)
            {
                AssetLoad<T> load = await pending;
                if (load.Result.HasAsset)
                {
                    owner.Add(load.Lease);
                }

                results.Add(load.Result);
            }

            return results;
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

            AsyncOperationHandle<T> handle = Addressables.LoadAssetAsync<T>(location);
            bool finished = await AddressableHandles.WhenDoneOrCancelled(handle, cancellation);
            if (!finished)
            {
                // The helper releases the handle when the load lands; it is not ours to touch now.
                return AssetLoad<T>.Failed(AssetLoadResult<T>.Cancelled(address));
            }

            if (handle.Status != AsyncOperationStatus.Succeeded || handle.Result == null)
            {
                string reason = handle.OperationException?.Message ?? "no exception was reported";
                Addressables.Release(handle);
                return AssetLoad<T>.Failed(AssetLoadResult<T>.LoadFailed(address,
                    "'" + address + "' failed to load: " + reason));
            }

            if (cancellation.IsCancellationRequested)
            {
                Addressables.Release(handle);
                return AssetLoad<T>.Failed(AssetLoadResult<T>.Cancelled(address));
            }

            T asset = handle.Result;
            Register(address, asset);
            var lease = new AssetLease<T>(asset, address, () =>
            {
                Addressables.Release(handle);
                Unregister(address);
            });
            return AssetLoad<T>.Leased(AssetLoadResult<T>.Success(asset, address), lease);
        }

        private static CandidateProbe Probe(string address, Type type)
        {
            if (Locate(address, type).Count > 0)
            {
                return CandidateProbe.Found;
            }

            return Locate(address, null).Count > 0 ? CandidateProbe.WrongType : CandidateProbe.Missing;
        }

        private static IList<IResourceLocation> Locate(object key, Type type)
        {
            foreach (IResourceLocator locator in Addressables.ResourceLocators)
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
