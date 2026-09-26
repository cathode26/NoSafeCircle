namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>
    /// Every content address and label the game uses, in one place.
    /// </summary>
    /// <remarks>
    /// <para>
    /// ENGINEERING_STANDARDS 8.3: "Centralize content IDs and label definitions", "Do not hand-build
    /// path strings throughout gameplay code", "Normalize IDs in one place only."
    /// SlotEngineGemReview 04 names the shape being avoided - gameplay code writing
    /// <c>GameName + "/" + ModeName + "/Sounds_WebGL"</c> - and the reason: a consumer that
    /// concatenates a path has silently taken on the resolver's job, so the fallback policy has to be
    /// re-implemented at every call site or forgotten at most of them.
    /// </para>
    /// <para>
    /// FAMILIES ARE FOLDERS AND FOLDERS ARE ADDRESSABLE GROUP ENTRIES. One folder per family, one
    /// group entry per folder, which is what lets seven lane owners add prefabs without any of them
    /// editing a shared list: a new prefab in <c>Content/Props</c> is addressable the moment it is
    /// imported, with no group edit at all. That is the same reasoning that put the 45 prop prefabs
    /// in a folder rather than a registry.
    /// </para>
    /// <para>
    /// THE FOLDER CONSTANTS ARE NOT A PATH-BUILDING KIT. They exist so <see cref="ContentResolver"/>
    /// can form an address; a spawner asks for <c>Address(Family.Props, "ca_pew_row_a")</c> and never
    /// sees a slash.
    /// </para>
    /// </remarks>
    public static class ContentId
    {
        /// <summary>A content family: one folder, one lifetime, one owner.</summary>
        public enum Family
        {
            /// <summary>Wall, floor and door modules. Owned by the room lanes.</summary>
            Environment = 0,

            /// <summary>The Art Director's authored dressing prefabs. 45 of them.</summary>
            Props = 1,

            /// <summary>Player, enemies, projectiles. Pooled.</summary>
            Gameplay = 2,

            /// <summary>HUD and menus.</summary>
            Ui = 3,

            /// <summary>Authored data: level maps, dressing catalogs, spawn tables.</summary>
            Data = 4
        }

        /// <summary>A platform variant of a family's content. ENGINEERING_STANDARDS 8.7 names exactly
        /// these three; <see cref="Shared"/> is the tree every platform loads and the one every
        /// fallback order must end on.</summary>
        public enum Variant
        {
            /// <summary>Loaded by every platform. The only tree that exists today.</summary>
            Shared = 0,

            /// <summary>A WebGL-only replacement for a shared asset of the same id.</summary>
            WebGL = 1,

            /// <summary>A desktop-player-only replacement for a shared asset of the same id.</summary>
            Desktop = 2
        }

        /// <summary>Root of all runtime-loaded content. NOT a Resources folder - see the note on
        /// <see cref="ContentRoot"/>'s value.</summary>
        /// <remarks>
        /// "Content" rather than "Resources" deliberately: everything under a Resources folder is
        /// forced into the initial player whether or not it is ever used, which would ship the props
        /// twice once they are also in an Addressables group. ENGINEERING_STANDARDS 8.1 lists "what
        /// content is part of the initial player" as the first reason we use Addressables at all.
        /// </remarks>
        public const string ContentRoot = "Assets/NoSafeCircle/DoorPrototype/Content";

        /// <summary>Label applied to every asset with application lifetime - loaded at bootstrap,
        /// released at quit.</summary>
        public const string ApplicationLabel = "application";

        /// <summary>Label applied to assets with level lifetime - released when the floor unloads.</summary>
        public const string LevelLabel = "level";

        /// <summary>Platform classification. ENGINEERING_STANDARDS 8.7 requires one and fails
        /// validation without it; everything we own today is genuinely shared.</summary>
        public const string SharedPlatformLabel = "shared";

        /// <summary>The folder name for a family, relative to <see cref="ContentRoot"/>.</summary>
        public static string FolderName(Family family)
        {
            switch (family)
            {
                case Family.Environment: return "Environment";
                case Family.Props: return "Props";
                case Family.Gameplay: return "Gameplay";
                case Family.Ui: return "Ui";
                case Family.Data: return "Levels";
                default:
                    // Not a default-and-continue: an unhandled family is a programmer error at a
                    // controlled boundary, which STANDARDS 4.2 says throws.
                    throw new System.ArgumentOutOfRangeException(nameof(family),
                        family, "No folder is defined for this content family.");
            }
        }

        /// <summary>The project folder holding a family's shared tree - what the editor setup registers
        /// as that family's group entry. An asset path, never an address.</summary>
        public static string FolderPath(Family family) => ContentRoot + "/" + FolderName(family);

        /// <summary>The top-level folder a platform variant tree lives under, or an empty string for
        /// <see cref="Variant.Shared"/>, which has no prefix.</summary>
        /// <remarks>
        /// THE PLATFORM IS THE OUTERMOST PARTITION, DELIBERATELY. A platform build includes or excludes
        /// whole groups (STANDARDS 8.7), and a group is made of folder entries, so a variant tree has to
        /// be a folder that can be registered on its own - <c>Content/WebGL/Props</c> - rather than a
        /// subfolder inside the shared family folder, which the shared folder entry would swallow.
        /// </remarks>
        public static string VariantFolderName(Variant variant)
        {
            switch (variant)
            {
                case Variant.Shared: return string.Empty;
                case Variant.WebGL: return "WebGL";
                case Variant.Desktop: return "Desktop";
                default:
                    throw new System.ArgumentOutOfRangeException(nameof(variant),
                        variant, "No folder is defined for this platform variant.");
            }
        }

        /// <summary>The address of one asset in one family. The ONLY place a content path is formed.</summary>
        public static string Address(Family family, string assetId)
        {
            if (string.IsNullOrEmpty(assetId))
            {
                throw new System.ArgumentException("An asset id is required.", nameof(assetId));
            }

            return FolderName(family) + "/" + assetId;
        }

        /// <summary>The address of one asset in one platform variant of a family. Shared is the plain
        /// family address; a platform tree is prefixed by its folder.</summary>
        public static string Address(Family family, Variant variant, string assetId)
        {
            if (variant == Variant.Shared)
            {
                return Address(family, assetId);
            }

            return VariantFolderName(variant) + "/" + Address(family, assetId);
        }

        /// <summary>The logical address of a catalog key: the key with the file extension a folder
        /// entry appends stripped off. The ONLY place that normalisation happens (STANDARDS 8.3).</summary>
        /// <remarks>
        /// MEASURED, NOT ASSUMED: Addressables 2.3.16 gives every asset under a folder entry the
        /// address <c>folderAddress + file.Substring(folderPath.Length)</c>
        /// (<c>Editor/Settings/AddressableAssetEntry.cs:546</c> and <c>:639</c>), so the catalog key for
        /// the pew is <c>Props/ca_pew_row_a.prefab</c> while <see cref="Address(Family, string)"/> forms
        /// <c>Props/ca_pew_row_a</c>. Both are wanted - the folder entry is what makes a new prefab
        /// addressable with no group edit, and an extensionless id is what keeps a spawner from knowing
        /// whether it asked for a prefab or a text file - so the loader indexes catalog keys by THIS and
        /// a caller never sees the extension.
        /// </remarks>
        public static string LogicalAddress(string primaryKey)
        {
            if (string.IsNullOrEmpty(primaryKey))
            {
                throw new System.ArgumentException("A catalog key is required.", nameof(primaryKey));
            }

            int lastSlash = primaryKey.LastIndexOf('/');
            int lastDot = primaryKey.LastIndexOf('.');
            return lastDot > lastSlash + 1 ? primaryKey.Substring(0, lastDot) : primaryKey;
        }

        /// <summary>The label naming a whole family as a logical set, for a load-by-label preload.</summary>
        public static string FamilyLabel(Family family) => FolderName(family).ToLowerInvariant();
    }
}
