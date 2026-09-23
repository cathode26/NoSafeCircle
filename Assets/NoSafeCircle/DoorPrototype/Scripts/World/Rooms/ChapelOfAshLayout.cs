using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>Approved revision-6 blockout measurements for the Chapel of Ash authoring scene.</summary>
    public static class ChapelOfAshLayout
    {
        public const float MinimumX = -18f;
        public const float MaximumX = 18f;
        public const float MinimumZ = 20f;
        public const float MaximumZ = 54f;
        public const float DoorWidth = 3f;
        public const float WallThickness = 0.5f;
        public const float WallHeight = 2.5f;
        public const float PewHeight = 1.25f;
        public const float ColumnSize = 1.5f;
        public const float ColumnHeight = 2.5f;

        // AC-002: the column-constrained side-route clearance produced by this layout, and the
        // minimum it must never fall below.
        public const float SideRouteColumnClearance = 3.75f;
        public const float MinimumSideRouteClearance = 3.5f;
        public const float PewRowGapWidth = 4f;
        public const float MinimumHardGeometryPassage = 2.5f;

        public static readonly Bounds RoomBounds = BoundsFromRange(MinimumX, MaximumX, MinimumZ, MaximumZ, 0f);

        // AC-001: unobstructed central aisle, D2 landing, and D3 staging area, measured to the
        // interior faces of the 0.5-unit wall colliders.
        public static readonly Bounds CentralAisleBounds = BoundsFromRange(-2.5f, 2.5f, 25f, 49f, 0f);
        public static readonly Bounds D2LandingBounds = BoundsFromRange(3.5f, 8.5f, 20.25f, 25.25f, 0f);
        public static readonly Bounds D3StagingBounds = BoundsFromRange(-10.5f, -5.5f, 48.75f, 53.75f, 0f);

        // AC-001: the north ritual reservation and its two supporting cluster reserves, read by
        // NSC-081 dressing without opening the authoring scene.
        public static readonly Bounds RitualFocusReserveBounds = BoundsFromRange(-2.5f, 2.5f, 50f, 53f, 0f);
        public static readonly Bounds WestRemembranceClusterReserveBounds = BoundsFromRange(-16.5f, -13f, 50f, 53.5f, 0f);
        public static readonly Bounds EastVestryClusterReserveBounds = BoundsFromRange(8f, 14f, 50f, 53.5f, 0f);

        // AC-002: eight 1.25-unit-high pew footprints, four per side, with a 4.0-unit opening
        // between successive rows.
        public static readonly Bounds[] PewFootprints =
        {
            BoundsFromRange(-12.5f, -3.5f, 27f, 29f, PewHeight),
            BoundsFromRange(-12.5f, -3.5f, 33f, 35f, PewHeight),
            BoundsFromRange(-12.5f, -3.5f, 39f, 41f, PewHeight),
            BoundsFromRange(-12.5f, -3.5f, 45f, 47f, PewHeight),
            BoundsFromRange(3.5f, 12.5f, 27f, 29f, PewHeight),
            BoundsFromRange(3.5f, 12.5f, 33f, 35f, PewHeight),
            BoundsFromRange(3.5f, 12.5f, 39f, 41f, PewHeight),
            BoundsFromRange(3.5f, 12.5f, 45f, 47f, PewHeight)
        };

        // AC-002: four columns touching the outer ends of pew rows 1 and 3.
        public static readonly Vector3[] ColumnCenters =
        {
            new Vector3(-13.25f, 0f, 28f),
            new Vector3(13.25f, 0f, 28f),
            new Vector3(-13.25f, 0f, 40f),
            new Vector3(13.25f, 0f, 40f)
        };

        public static readonly Vector3 D2 = new Vector3(6f, 0f, 20f);
        public static readonly Vector3 D3 = new Vector3(-8f, 0f, 54f);

        // AC-002: CA-W and column-backed CA-E cover pockets.
        public static readonly Vector3 CoverPocketWest = new Vector3(-15.5f, 0f, 34f);
        public static readonly Vector3 CoverPocketEast = new Vector3(15.5f, 0f, 40f);

        // AC-001/AC-008: the four gameplay-camera review stations, exposed as public layout data
        // so builders and downstream dressing tests do not need to read Authoring-only objects.
        public static readonly Vector3[] GameplayCameraReviewStations =
        {
            new Vector3(6f, 0f, 24f),
            new Vector3(-15.5f, 0f, 37f),
            new Vector3(12f, 0f, 42f),
            new Vector3(-8f, 0f, 51f)
        };

        public static Bounds BoundsFromRange(float minX, float maxX, float minZ, float maxZ, float height)
        {
            return new Bounds(
                new Vector3((minX + maxX) * 0.5f, height * 0.5f, (minZ + maxZ) * 0.5f),
                new Vector3(maxX - minX, height, maxZ - minZ));
        }

        public static Bounds ColumnBounds(Vector3 center)
        {
            return new Bounds(
                new Vector3(center.x, ColumnHeight * 0.5f, center.z),
                new Vector3(ColumnSize, ColumnHeight, ColumnSize));
        }
    }
}
