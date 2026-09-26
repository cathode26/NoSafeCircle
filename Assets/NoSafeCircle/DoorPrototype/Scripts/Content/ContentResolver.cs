using System;
using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>What a catalog probe found at one candidate address.</summary>
    public enum CandidateProbe
    {
        Missing = 0,
        Found = 1,

        /// <summary>Something is at the address, but not the requested type.</summary>
        WrongType = 2
    }

    /// <summary>The candidate a fallback walk settled on, or why it settled on none.</summary>
    public readonly struct CandidateSelection
    {
        public CandidateSelection(AssetLoadStatus status, string address, int index, string message)
        {
            Status = status;
            Address = address;
            Index = index;
            Message = message;
        }

        /// <summary>Success, FallbackUsed, TypeMismatch or RequiredMissing - never a load-time status.</summary>
        public AssetLoadStatus Status { get; }

        /// <summary>The selected address, or the first candidate when nothing was selected.</summary>
        public string Address { get; }

        /// <summary>Position in the candidate list, or -1 when nothing was selected.</summary>
        public int Index { get; }

        public string Message { get; }

        public bool HasCandidate => Index >= 0;
    }

    /// <summary>
    /// The standard resolver: one ordered variant preference, applied to every query.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THE ORDER IS DATA, CHECKED ONCE AT CONSTRUCTION. ENGINEERING_STANDARDS 8.4: "The fallback policy
    /// is data/configuration, not duplicated procedural code at every call site." A preference must end
    /// with <see cref="ContentId.Variant.Shared"/> - that is the tree every platform loads, and a
    /// required asset with no shared address has nowhere to be found - and it is rejected with a
    /// specific message if it does not, rather than producing a resolver that quietly cannot find things.
    /// </para>
    /// <para>
    /// A WRONG TYPE AT A PREFERRED ADDRESS DOES NOT FALL THROUGH. An optional variant that is ABSENT is
    /// the normal case and the walk continues; a variant that is PRESENT as the wrong type is a build
    /// mistake, and falling back would hide it behind a working shared asset until the day the shared
    /// asset was removed. <see cref="Select"/> stops on it and says so.
    /// </para>
    /// </remarks>
    public sealed class ContentResolver : IContentResolver
    {
        private readonly ContentId.Variant[] preference;

        public ContentResolver(IReadOnlyList<ContentId.Variant> preference)
        {
            this.preference = ValidatedCopy(preference, nameof(preference));
        }

        /// <summary>Only the shared tree. Everything No Safe Circle owns today is shared.</summary>
        public static ContentResolver SharedOnly() =>
            new ContentResolver(new[] { ContentId.Variant.Shared });

        /// <summary>The preference a platform wants: its own variant first, shared last.</summary>
        public static ContentResolver ForPlatform(RuntimePlatform platform)
        {
            switch (platform)
            {
                case RuntimePlatform.WebGLPlayer:
                    return new ContentResolver(new[] { ContentId.Variant.WebGL, ContentId.Variant.Shared });
                case RuntimePlatform.WindowsPlayer:
                case RuntimePlatform.OSXPlayer:
                case RuntimePlatform.LinuxPlayer:
                case RuntimePlatform.WindowsEditor:
                case RuntimePlatform.OSXEditor:
                case RuntimePlatform.LinuxEditor:
                    return new ContentResolver(new[] { ContentId.Variant.Desktop, ContentId.Variant.Shared });
                default:
                    return SharedOnly();
            }
        }

        /// <summary>The composition root's choice. The Editor resolves as a desktop player, which only
        /// matters once a Desktop variant tree exists; none does today.</summary>
        public static ContentResolver ForCurrentPlatform() => ForPlatform(Application.platform);

        public IReadOnlyList<string> Resolve(ContentQuery query)
        {
            if (string.IsNullOrEmpty(query.AssetId))
            {
                throw new ArgumentException("The query has no asset id; a default ContentQuery is not a request.",
                    nameof(query));
            }

            ContentId.Variant[] order = query.Preference == null
                ? preference
                : ValidatedCopy(query.Preference, nameof(query));

            var addresses = new string[order.Length];
            for (int i = 0; i < order.Length; i++)
            {
                addresses[i] = ContentId.Address(query.Family, order[i], query.AssetId);
            }

            return addresses;
        }

        /// <summary>Walks candidates in order against a catalog probe and names the outcome. Pure, so the
        /// failure model is testable without a catalog; the loader supplies the real probe.</summary>
        public static CandidateSelection Select(IReadOnlyList<string> candidates, Func<string, CandidateProbe> probe)
        {
            if (candidates == null || candidates.Count == 0)
            {
                throw new ArgumentException("A selection needs at least one candidate address.", nameof(candidates));
            }

            if (probe == null)
            {
                throw new ArgumentNullException(nameof(probe));
            }

            for (int i = 0; i < candidates.Count; i++)
            {
                switch (probe(candidates[i]))
                {
                    case CandidateProbe.Found:
                        return i == 0
                            ? new CandidateSelection(AssetLoadStatus.Success, candidates[i], i, null)
                            : new CandidateSelection(AssetLoadStatus.FallbackUsed, candidates[i], i,
                                "'" + candidates[0] + "' is absent; using '" + candidates[i] + "'.");
                    case CandidateProbe.WrongType:
                        return new CandidateSelection(AssetLoadStatus.TypeMismatch, candidates[i], i,
                            "'" + candidates[i] + "' exists but is not the requested type.");
                }
            }

            return new CandidateSelection(AssetLoadStatus.RequiredMissing, candidates[0], -1,
                "None of [" + string.Join(", ", candidates) + "] exists in the content catalog.");
        }

        private static ContentId.Variant[] ValidatedCopy(IReadOnlyList<ContentId.Variant> source, string parameterName)
        {
            if (source == null || source.Count == 0)
            {
                throw new ArgumentException("A variant preference needs at least one entry.", parameterName);
            }

            if (source[source.Count - 1] != ContentId.Variant.Shared)
            {
                throw new ArgumentException("A variant preference must end with Shared, so a required asset "
                    + "always has a final address to fall back to. Got: [" + string.Join(", ", source) + "].",
                    parameterName);
            }

            var copy = new ContentId.Variant[source.Count];
            for (int i = 0; i < copy.Length; i++)
            {
                for (int j = 0; j < i; j++)
                {
                    if (copy[j] == source[i])
                    {
                        throw new ArgumentException("Variant '" + source[i] + "' appears twice in the preference.",
                            parameterName);
                    }
                }

                copy[i] = source[i];
            }

            return copy;
        }
    }
}
