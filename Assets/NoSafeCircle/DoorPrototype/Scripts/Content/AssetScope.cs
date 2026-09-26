using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>
    /// A set of leases with one lifetime. Dispose the scope and every lease in it is released, last
    /// added first.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THIS IS THE OWNER THAT REPLACES THE MANAGER'S DICTIONARY. SlotEngineGemReview 04: "No 'release
    /// everything the manager thinks is game content' dictionary should be required." Vincent's engine
    /// kept two of those (game and lobby) and released whichever one a global player-state flag pointed
    /// at; here the bootstrap holds an application scope and a level scope as plain fields, a menu
    /// holds a UI scope, and a one-off preview is a <c>using</c> block. The owner is visible in code,
    /// which is ENGINEERING_STANDARDS 2.3 and 8.5 in one object.
    /// </para>
    /// <para>
    /// REVERSE ORDER, ALWAYS. 8.5 asks for "a predictable order"; last-in-first-out is the one that
    /// releases a thing before the things it was loaded after, which is the only order that is safe
    /// when a later load depended on an earlier one. A release that throws is logged and does not stop
    /// the rest: a scope that gives up halfway leaks everything after the fault.
    /// </para>
    /// <para>
    /// IT KNOWS NOTHING ABOUT ADDRESSABLES, like <see cref="AssetLease{T}"/>, so it is tested here with
    /// leases over objects the test made itself.
    /// </para>
    /// </remarks>
    public sealed class AssetScope : IDisposable
    {
        private readonly List<IDisposable> leases = new List<IDisposable>();

        public AssetScope(string name)
        {
            if (string.IsNullOrEmpty(name))
            {
                throw new ArgumentException("A scope needs a name; it is the only thing a leak report can say.",
                    nameof(name));
            }

            Name = name;
        }

        /// <summary>For diagnostics: "application", "level", "pause-menu".</summary>
        public string Name { get; }

        /// <summary>Leases currently owned. Zero after disposal.</summary>
        public int Count => leases.Count;

        public bool IsDisposed { get; private set; }

        /// <summary>Takes ownership of a lease. Returned unchanged so a load can be leased and scoped in
        /// one expression.</summary>
        public AssetLease<T> Add<T>(AssetLease<T> lease) where T : UnityEngine.Object
        {
            if (IsDisposed)
            {
                throw new ObjectDisposedException(Name, "This scope has been disposed; it cannot own a new lease.");
            }

            if (lease == null)
            {
                throw new ArgumentNullException(nameof(lease));
            }

            if (lease.IsReleased)
            {
                throw new ArgumentException("The lease over '" + lease.Address + "' is already released.", nameof(lease));
            }

            leases.Add(lease);
            return lease;
        }

        /// <summary>Loads through the service and, when there is an asset, owns the lease. The result is
        /// returned either way so the caller can act on a failure without ever seeing the lease.</summary>
        public async Task<AssetLoadResult<T>> LoadAsync<T>(IAssetService service, ContentQuery query,
            CancellationToken cancellation) where T : UnityEngine.Object
        {
            if (service == null)
            {
                throw new ArgumentNullException(nameof(service));
            }

            AssetLoad<T> load = await service.LoadAsync<T>(query, cancellation);
            if (load.Result.HasAsset)
            {
                if (IsDisposed)
                {
                    // Disposed while the load was in flight: nothing can own it now, so let it go.
                    load.Lease.Dispose();
                    return AssetLoadResult<T>.Cancelled(load.Result.Address);
                }

                Add(load.Lease);
            }

            return load.Result;
        }

        public void Dispose()
        {
            if (IsDisposed)
            {
                return;
            }

            IsDisposed = true;
            for (int i = leases.Count - 1; i >= 0; i--)
            {
                try
                {
                    leases[i].Dispose();
                }
                catch (Exception failure)
                {
                    Debug.LogException(new InvalidOperationException(
                        "Scope '" + Name + "' could not release lease " + i + " of " + leases.Count + "; continuing.", failure));
                }
            }

            leases.Clear();
        }
    }
}
