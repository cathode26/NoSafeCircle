using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>One typed load's outcome, and - when there is an asset - the lease that owns it.</summary>
    /// <remarks>
    /// The result says what happened; the lease says who must release it. They travel together because
    /// ENGINEERING_STANDARDS 8.5 wants "every explicit load has an explicit owner", and a caller that
    /// receives a lease cannot forget it exists the way it can forget a handle the manager kept.
    /// </remarks>
    public readonly struct AssetLoad<T> where T : UnityEngine.Object
    {
        private AssetLoad(AssetLoadResult<T> result, AssetLease<T> lease)
        {
            Result = result;
            Lease = lease;
        }

        public AssetLoadResult<T> Result { get; }

        /// <summary>The owner's handle on the asset. Null exactly when the result has no asset.</summary>
        public AssetLease<T> Lease { get; }

        public static AssetLoad<T> Failed(AssetLoadResult<T> result)
        {
            if (result.HasAsset)
            {
                throw new ArgumentException("A load that produced an asset must carry its lease.", nameof(result));
            }

            return new AssetLoad<T>(result, null);
        }

        public static AssetLoad<T> Leased(AssetLoadResult<T> result, AssetLease<T> lease)
        {
            if (!result.HasAsset)
            {
                throw new ArgumentException("A lease over a failed load is a lease over nothing.", nameof(result));
            }

            if (lease == null)
            {
                throw new ArgumentNullException(nameof(lease), "A successful load must be owned by a lease.");
            }

            return new AssetLoad<T>(result, lease);
        }
    }

    /// <summary>
    /// Typed loads that return leases and results, never bare nulls. Implementations await initialization
    /// themselves, so a caller only ever needs the readiness boundary once, in the bootstrap.
    /// </summary>
    public interface IAssetService
    {
        /// <summary>Loads the best available candidate for a query.</summary>
        Task<AssetLoad<T>> LoadAsync<T>(ContentQuery query, CancellationToken cancellation)
            where T : UnityEngine.Object;

        /// <summary>Loads every asset of type <typeparamref name="T"/> carrying the family's label, one
        /// lease each, all owned by <paramref name="owner"/>. Returns one result per catalog entry, in
        /// catalog order; a failure is reported, not thrown, so one bad prop does not empty a room.</summary>
        Task<IReadOnlyList<AssetLoadResult<T>>> PreloadAsync<T>(ContentId.Family family, AssetScope owner,
            CancellationToken cancellation) where T : UnityEngine.Object;

        /// <summary>Synchronous lookup of an asset some live lease has already made resident, in the
        /// resolver's fallback order. This is the spawn-phase path: after the bootstrap's preload it
        /// always succeeds for preloaded content, and it never starts a load.</summary>
        bool TryGetResident<T>(ContentQuery query, out T asset) where T : UnityEngine.Object;
    }
}
