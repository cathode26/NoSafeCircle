using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>
    /// A pool of instances of one addressable prefab. Owns the prefab's lease AND the instances, and
    /// releases the lease only after the last instance is back.
    /// </summary>
    /// <typeparam name="T">The component the pool hands out; it must restore its own state (9.3).</typeparam>
    /// <remarks>
    /// <para>
    /// THE LEASE OUTLIVES EVERY INSTANCE, WHICH IS THE WHOLE REASON THIS CLASS EXISTS. ENGINEERING_STANDARDS
    /// 9.5: "An Addressable prefab pool owns the prefab load lease. The lease outlives all instances and
    /// is released only when the pool has been disposed safely." An instance is a clone of the prefab's
    /// meshes, sprites and materials by reference; release the bundle while one is still on screen and
    /// the instance keeps drawing from memory the ResourceManager thinks is free. So <see cref="Dispose"/>
    /// with instances still checked out is not refused and not forced: the pool destroys what it holds,
    /// records the leak in <see cref="Diagnostics"/>, and hands the lease over the moment the last
    /// instance returns.
    /// </para>
    /// <para>
    /// 9.2, ITEM BY ITEM: creation is <c>Object.Instantiate</c> of the leased prefab under
    /// <c>root</c>; initial and maximum capacity are constructor data; overflow is a declared
    /// <see cref="PoolOverflowPolicy"/>; checkout reset is activate-then-<see cref="IPoolable.OnCheckout"/>;
    /// return reset is <see cref="IPoolable.OnReturn"/>-then-deactivate-and-reparent; destruction is at
    /// disposal, or on return after disposal; the owner is whoever holds this object; and the
    /// diagnostics are <see cref="PoolDiagnostics"/>, counted always.
    /// </para>
    /// <para>
    /// DESTRUCTION IN EDIT MODE USES <c>DestroyImmediate</c>, on purpose and only there. STANDARDS 6 says
    /// to avoid it in runtime gameplay code; a pool disposed in an EditMode test is neither, and
    /// <c>Destroy</c> is refused outside Play Mode, so this is the one branch that lets the lifetime
    /// tests exist at all.
    /// </para>
    /// </remarks>
    public sealed class AddressablePrefabPool<T> : IDisposable where T : Component, IPoolable
    {
        private readonly string name;
        private readonly int initialCapacity;
        private readonly int maximumCapacity;
        private readonly PoolOverflowPolicy overflow;
        private readonly Transform root;
        private readonly Stack<T> idle = new Stack<T>();
        private readonly HashSet<T> active = new HashSet<T>();
        private AssetLease<GameObject> prefabLease;
        private T prefab;
        private int created;
        private bool disposed;

        public AddressablePrefabPool(string name, int initialCapacity, int maximumCapacity,
            PoolOverflowPolicy overflow, Transform root)
        {
            if (string.IsNullOrEmpty(name))
            {
                throw new ArgumentException("A pool needs a name; it is what every diagnostic is filed under.", nameof(name));
            }

            if (initialCapacity < 0 || maximumCapacity < 1 || maximumCapacity < initialCapacity)
            {
                throw new ArgumentOutOfRangeException(nameof(maximumCapacity), "Pool '" + name + "': initial capacity "
                    + initialCapacity + " and maximum " + maximumCapacity + "; initial must be >= 0 and maximum >= max(1, initial).");
            }

            this.name = name;
            this.initialCapacity = initialCapacity;
            this.maximumCapacity = maximumCapacity;
            this.overflow = overflow;
            this.root = root;
        }

        public string Name => name;

        public PoolDiagnostics Diagnostics { get; } = new PoolDiagnostics();

        public int ActiveCount => active.Count;

        public int IdleCount => idle.Count;

        public bool IsDisposed => disposed;

        /// <summary>True from a successful <see cref="PrewarmAsync"/> until the lease is released.</summary>
        public bool HoldsPrefab => prefabLease != null;

        /// <summary>Loads the prefab and creates the initial instances. The result is the load's, so a
        /// missing or mistyped prefab is reported in the same vocabulary as any other load.</summary>
        public async Task<AssetLoadResult<GameObject>> PrewarmAsync(IAssetService service, ContentQuery query,
            CancellationToken cancellation)
        {
            if (service == null)
            {
                throw new ArgumentNullException(nameof(service));
            }

            if (disposed)
            {
                throw new ObjectDisposedException(name);
            }

            if (prefabLease != null)
            {
                throw new InvalidOperationException("Pool '" + name + "' already holds '" + prefabLease.Address
                    + "'; a pool owns one prefab for its whole life.");
            }

            AssetLoad<GameObject> load = await service.LoadAsync<GameObject>(query, cancellation);
            if (!load.Result.HasAsset)
            {
                return load.Result;
            }

            T component = load.Result.Asset.GetComponent<T>();
            if (component == null)
            {
                // 8.5: a load we cannot use is released, not leaked. Failed here means failed.
                load.Lease.Dispose();
                return AssetLoadResult<GameObject>.TypeMismatch(load.Result.Address, "'" + load.Result.Address
                    + "' has no " + typeof(T).Name + " component, so pool '" + name + "' cannot use it.");
            }

            if (disposed)
            {
                load.Lease.Dispose();
                return AssetLoadResult<GameObject>.Cancelled(load.Result.Address);
            }

            prefabLease = load.Lease;
            prefab = component;
            for (int i = 0; i < initialCapacity; i++)
            {
                idle.Push(CreateInstance());
            }

            return load.Result;
        }

        /// <summary>An active, reset instance - or false, counted, when the pool is full and rejecting.</summary>
        public bool TryCheckout(out T instance)
        {
            if (disposed)
            {
                throw new ObjectDisposedException(name);
            }

            if (prefab == null)
            {
                throw new InvalidOperationException("Pool '" + name + "' has no prefab; await PrewarmAsync first.");
            }

            if (idle.Count == 0 && created >= maximumCapacity && overflow == PoolOverflowPolicy.Reject)
            {
                Diagnostics.RejectedRequests++;
                instance = null;
                return false;
            }

            instance = idle.Count > 0 ? idle.Pop() : CreateInstance();
            if (!active.Add(instance))
            {
                Diagnostics.DoubleCheckouts++;
            }

            Diagnostics.RecordActive(active.Count);
            instance.gameObject.SetActive(true);
            instance.OnCheckout();
            return true;
        }

        /// <summary>Takes an instance back. A double or foreign return is counted, warned about, and ignored.</summary>
        public void Return(T instance)
        {
            if (instance == null)
            {
                throw new ArgumentNullException(nameof(instance));
            }

            if (!active.Remove(instance))
            {
                Diagnostics.RecordMisreturn(idle.Contains(instance));
                Debug.LogWarning("Pool '" + name + "': '" + instance.name + "' was returned but is not checked out of this pool. Ignored and counted.");
                return;
            }

            instance.OnReturn();
            instance.gameObject.SetActive(false);
            instance.transform.SetParent(root, false);

            if (disposed)
            {
                DestroyInstance(instance);
                ReleasePrefabIfUnused();
            }
            else
            {
                idle.Push(instance);
            }
        }

        public void Dispose()
        {
            if (disposed)
            {
                return;
            }

            disposed = true;
            while (idle.Count > 0)
            {
                DestroyInstance(idle.Pop());
            }

            Diagnostics.ActiveAtDisposal = active.Count;
            if (active.Count > 0)
            {
                Debug.LogWarning("Pool '" + name + "' disposed with " + active.Count + " instance(s) still checked out; the prefab lease is held until the last one returns (STANDARDS 9.5).");
            }

            ReleasePrefabIfUnused();
        }

        private void ReleasePrefabIfUnused()
        {
            if (!disposed || active.Count > 0 || prefabLease == null)
            {
                return;
            }

            prefabLease.Dispose();
            prefabLease = null;
            prefab = null;
        }

        private T CreateInstance()
        {
            T instance = Object.Instantiate(prefab, root);
            instance.gameObject.SetActive(false);
            created++;
            if (created > initialCapacity)
            {
                Diagnostics.Expansions++;
            }

            return instance;
        }

        private static void DestroyInstance(T instance)
        {
            if (instance == null)
            {
                return;
            }

            if (Application.isPlaying)
            {
                Object.Destroy(instance.gameObject);
            }
            else
            {
                Object.DestroyImmediate(instance.gameObject);
            }
        }
    }
}
