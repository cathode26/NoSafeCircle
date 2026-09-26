using System;
using System.Collections.Generic;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>
    /// A logical content request: which family, which id, and optionally which platform variants to
    /// prefer. Never a path, never a label - a consumer that holds one of these has said WHAT it wants
    /// and nothing about where it lives.
    /// </summary>
    /// <remarks>
    /// SlotEngineGemReview 04's query model names a category, a game, a mode and a platform preference.
    /// No Safe Circle is one game with one mode, so the category IS <see cref="ContentId.Family"/> and
    /// the other two axes do not exist here; adding them later means adding fields to this struct and
    /// address forms to <see cref="ContentId"/>, and no call site changes.
    /// </remarks>
    public readonly struct ContentQuery
    {
        public ContentQuery(ContentId.Family family, string assetId)
            : this(family, assetId, null)
        {
        }

        public ContentQuery(ContentId.Family family, string assetId,
            IReadOnlyList<ContentId.Variant> preference)
        {
            if (string.IsNullOrEmpty(assetId))
            {
                throw new ArgumentException("A content query needs an asset id.", nameof(assetId));
            }

            Family = family;
            AssetId = assetId;
            Preference = preference;
        }

        public ContentId.Family Family { get; }

        public string AssetId { get; }

        /// <summary>Variants to try, most preferred first, or null to use the resolver's own order.
        /// Ends with <see cref="ContentId.Variant.Shared"/> or the resolver rejects it.</summary>
        public IReadOnlyList<ContentId.Variant> Preference { get; }

        public override string ToString() => Family + ":" + AssetId;
    }

    /// <summary>
    /// Turns a <see cref="ContentQuery"/> into the ordered addresses to try. The fallback policy lives in
    /// the implementation's DATA (ENGINEERING_STANDARDS 8.4), so no caller walks variants itself.
    /// </summary>
    public interface IContentResolver
    {
        /// <summary>The addresses for a query, most preferred first. Never empty, and the last entry is
        /// always the shared address, so a required asset always has a final place to be.</summary>
        IReadOnlyList<string> Resolve(ContentQuery query);
    }
}
