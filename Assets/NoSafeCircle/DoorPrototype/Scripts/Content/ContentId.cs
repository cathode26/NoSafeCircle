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

        /// <summary>The address of one asset in one family. The ONLY place a content path is formed.</summary>
        public static string Address(Family family, string assetId)
        {
            if (string.IsNullOrEmpty(assetId))
            {
                throw new System.ArgumentException("An asset id is required.", nameof(assetId));
            }

            return FolderName(family) + "/" + assetId;
        }

        /// <summary>The label naming a whole family as a logical set, for a load-by-label preload.</summary>
        public static string FamilyLabel(Family family) => FolderName(family).ToLowerInvariant();
    }
}
