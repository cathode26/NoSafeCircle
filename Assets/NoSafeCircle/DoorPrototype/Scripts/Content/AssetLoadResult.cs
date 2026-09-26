namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>Why a content load ended the way it did.</summary>
    /// <remarks>
    /// ENGINEERING_STANDARDS 7.2: "Report failure through a typed result or exception boundary; do not
    /// return an empty string or null for every failure category." SlotEngineGemReview 04 is sharper
    /// about why it matters here: "A missing optional override is not the same as a failed required
    /// asset." One returns null and logs an error; the other returns null and is completely normal.
    /// A caller cannot tell those apart from a null, so it either treats every miss as fatal or none
    /// of them - and the legacy manager chose "none", which is how required content goes missing
    /// quietly.
    /// </remarks>
    public enum AssetLoadStatus
    {
        /// <summary>The requested asset is loaded and the lease owns it.</summary>
        Success = 0,

        /// <summary>An optional variant was absent and a lower-priority fallback was used. NORMAL.
        /// Never logged as an error.</summary>
        FallbackUsed = 1,

        /// <summary>Required content is absent. Fatal, and said so loudly.</summary>
        RequiredMissing = 2,

        /// <summary>The caller cancelled before the load finished.</summary>
        Cancelled = 3,

        /// <summary>The load itself failed - download, corruption, a broken bundle.</summary>
        LoadFailed = 4,

        /// <summary>The address resolved to an asset of the wrong type, or the configuration is
        /// invalid. A build-time mistake surfacing at runtime.</summary>
        TypeMismatch = 5
    }

    /// <summary>The outcome of one typed load: a status, the asset when there is one, and a message.</summary>
    /// <typeparam name="T">The asset type requested.</typeparam>
    public readonly struct AssetLoadResult<T> where T : UnityEngine.Object
    {
        private AssetLoadResult(AssetLoadStatus status, T asset, string address, string message)
        {
            Status = status;
            Asset = asset;
            Address = address;
            Message = message;
        }

        /// <summary>How the load ended.</summary>
        public AssetLoadStatus Status { get; }

        /// <summary>The asset, or null for every status other than Success and FallbackUsed.</summary>
        public T Asset { get; }

        /// <summary>The address that was finally used, or the one that failed. Never assembled by a
        /// caller - see <see cref="ContentId"/>.</summary>
        public string Address { get; }

        /// <summary>Why, in words a log line can carry.</summary>
        public string Message { get; }

        /// <summary>True when there is an asset to use, whether or not a fallback supplied it.</summary>
        public bool HasAsset => Status == AssetLoadStatus.Success || Status == AssetLoadStatus.FallbackUsed;

        /// <summary>True when the caller must stop rather than continue without the asset.</summary>
        public bool IsFatal => Status == AssetLoadStatus.RequiredMissing
            || Status == AssetLoadStatus.LoadFailed
            || Status == AssetLoadStatus.TypeMismatch;

        public static AssetLoadResult<T> Success(T asset, string address) =>
            new AssetLoadResult<T>(AssetLoadStatus.Success, asset, address, null);

        public static AssetLoadResult<T> FallbackUsed(T asset, string address, string message) =>
            new AssetLoadResult<T>(AssetLoadStatus.FallbackUsed, asset, address, message);

        public static AssetLoadResult<T> RequiredMissing(string address, string message) =>
            new AssetLoadResult<T>(AssetLoadStatus.RequiredMissing, null, address, message);

        public static AssetLoadResult<T> Cancelled(string address) =>
            new AssetLoadResult<T>(AssetLoadStatus.Cancelled, null, address, "Cancelled by the caller.");

        public static AssetLoadResult<T> LoadFailed(string address, string message) =>
            new AssetLoadResult<T>(AssetLoadStatus.LoadFailed, null, address, message);

        public static AssetLoadResult<T> TypeMismatch(string address, string message) =>
            new AssetLoadResult<T>(AssetLoadStatus.TypeMismatch, null, address, message);
    }
}
