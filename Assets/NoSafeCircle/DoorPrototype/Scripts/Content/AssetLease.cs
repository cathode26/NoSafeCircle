using System;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>
    /// One loaded asset and the right to use it. Disposing it releases the load.
    /// </summary>
    /// <typeparam name="T">The asset type.</typeparam>
    /// <remarks>
    /// <para>
    /// ENGINEERING_STANDARDS 8.5: "Every explicit load has an explicit owner", "Mirror every load
    /// with release of the same handle", "Do not use broad 'release all game handles' cleanup when
    /// the actual owners can be represented directly." A lease IS that representation - the owner is
    /// whoever holds the object, and it is visible in code rather than implied by a manager's
    /// dictionary.
    /// </para>
    /// <para>
    /// IT RELEASES THROUGH A CALLBACK AND KNOWS NOTHING ABOUT ADDRESSABLES, deliberately. That keeps
    /// this type - and <see cref="AssetScope"/>, and every consumer of both - compiling and testable
    /// without the package, and it means a test can hand out a lease over an asset it created
    /// itself. SlotEngineGemReview 05's instruction about the legacy manager was "DO NOT COPY.
    /// Rebuild as resolver + loader + scope + lease services"; the reason the split is worth having
    /// is exactly this, that most of it stops depending on the loader.
    /// </para>
    /// <para>
    /// DISPOSING TWICE IS SAFE AND DOES NOT DOUBLE-RELEASE. A double release on an Addressables
    /// handle is a real bug that surfaces far away from its cause, so the guard lives here once
    /// rather than in every owner.
    /// </para>
    /// </remarks>
    public sealed class AssetLease<T> : IDisposable where T : UnityEngine.Object
    {
        private Action release;

        public AssetLease(T asset, string address, Action releaseAction)
        {
            Asset = asset;
            Address = address;
            release = releaseAction;
        }

        /// <summary>The asset. Valid until this lease is disposed.</summary>
        public T Asset { get; private set; }

        /// <summary>The address this was loaded from, for diagnostics.</summary>
        public string Address { get; }

        /// <summary>True once <see cref="Dispose"/> has run.</summary>
        public bool IsReleased => release == null && Asset == null;

        /// <summary>A lease over an asset nothing needs to release - a test's own object, or one
        /// that came from somewhere other than a content load.</summary>
        public static AssetLease<T> Unmanaged(T asset, string address) =>
            new AssetLease<T>(asset, address, null);

        public void Dispose()
        {
            Action pending = release;
            release = null;
            Asset = null;
            pending?.Invoke();
        }
    }
}
