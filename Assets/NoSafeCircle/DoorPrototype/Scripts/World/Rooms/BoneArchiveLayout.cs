using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>Canonical blockout measurements for the Bone Archive source scene.</summary>
    /// <remarks>
    /// NSC-045 AC-001, the widened lane blockout. Every number here is the contract's, not a
    /// tuning choice. Until 2026-09-25 this file held the PRE-WIDENING geometry - RoomBounds
    /// X [-10,+10], shelves and BA-1 at different coordinates, and no archive bays at all - under
    /// a contract titled "Widened-Lane Blockout" that has required the widened values since
    /// revision 4. The room, its test and its delivery record were mutually consistent and all
    /// three disagreed with the contract, which is why it read conformant.
    ///
    /// RoomSceneCatalog.cs already declares Bone Archive as RoomBounds(-12, 12, 0, 20) and
    /// NSC-045 is forbidden from editing it, so the catalog and the contract agreed with each
    /// other and only this file was stale.
    /// </remarks>
    public static class BoneArchiveLayout
    {
        public const float MinLaneWidth = 2.5f;
        public const float NormalLaneWidth = 3.5f;
        public const float WallThickness = 0.5f;
        public const float WallHeight = 2.5f;
        public const float DoorWidth = 3f;

        /// <summary>AC-001/AC-003: shelf and bay VISUALS are exactly 1.0 unit high while their
        /// gameplay BoxColliders stay <see cref="ObstacleColliderHeight"/> high. The contract
        /// forbids choosing a different visual height without a later revision.</summary>
        public const float ShelfVisualHeight = 1f;

        public const float ObstacleColliderHeight = 2.5f;

        /// <summary>AC-001: BA-1 is the one obstacle whose visual matches its collider height.</summary>
        public const float CollapsedFurnitureHeight = 1.25f;

        // AC-001: a 24-by-20-world-unit room, walkable X [-12,+12], Z [0,20].
        public static readonly Bounds RoomBounds =
            new Bounds(new Vector3(0f, 0f, 10f), new Vector3(24f, 0f, 20f));

        public static readonly Bounds ShelfA =
            BoundsFromRange(-7.5f, -6f, 4f, 15f, ObstacleColliderHeight);

        public static readonly Bounds ShelfB =
            BoundsFromRange(-2.5f, -1f, 4f, 13.5f, ObstacleColliderHeight);

        public static readonly Bounds ShelfC =
            BoundsFromRange(2.5f, 4f, 5.5f, 15.5f, ObstacleColliderHeight);

        public static readonly Bounds CollapsedFurnitureBA1 =
            BoundsFromRange(-1f, 0f, 9f, 11f, CollapsedFurnitureHeight);

        /// <summary>AC-001: West Archive Bay W-1, a wall-side supporting cluster.</summary>
        public static readonly Bounds WestArchiveBayW1 =
            BoundsFromRange(-11.75f, -10.5f, 7f, 16f, ObstacleColliderHeight);

        /// <summary>AC-001: East Archive Bay E-1, a wall-side supporting cluster.</summary>
        public static readonly Bounds EastArchiveBayE1 =
            BoundsFromRange(7f, 11.75f, 5.5f, 13.5f, ObstacleColliderHeight);

        /// <summary>AC-003: the Archive Reliquary blockout against the north wall. It is
        /// NON-COLLIDING - a visual landmark only - so it carries no gameplay BoxCollider and must
        /// stay outside the D2 staging rectangle. The contract fixes its X/Z footprint and does
        /// not state a height, so it uses the same visual height as the shelves and bays.</summary>
        public static readonly Bounds ArchiveReliquary =
            BoundsFromRange(-2f, 2f, 18.75f, 19.75f, ShelfVisualHeight);

        public static readonly Vector3 D1 = new Vector3(0f, 0f, 0f);
        public static readonly Vector3 D2 = new Vector3(6f, 0f, 20f);

        public static Bounds BoundsFromRange(float minX, float maxX, float minZ, float maxZ, float height)
        {
            return new Bounds(new Vector3((minX + maxX) * 0.5f, height * 0.5f, (minZ + maxZ) * 0.5f),
                new Vector3(maxX - minX, height, maxZ - minZ));
        }

        public static float ClearWidthBetween(Bounds left, Bounds right)
        {
            return right.min.x - left.max.x;
        }
    }
}
