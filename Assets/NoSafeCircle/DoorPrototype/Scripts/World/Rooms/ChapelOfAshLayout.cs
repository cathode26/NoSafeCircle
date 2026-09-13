using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>Approved blockout measurements for the Chapel of Ash authoring scene.</summary>
    public static class ChapelOfAshLayout
    {
        public const float MinimumX = -12f;
        public const float MaximumX = 12f;
        public const float MinimumZ = 20f;
        public const float MaximumZ = 42f;
        public const float DoorWidth = 3f;
        public const float WallThickness = 0.5f;
        public const float WallHeight = 2.5f;
        public const float CentralAisleWidth = 4f;
        public const float PewHeight = 1.25f;
        public const float ColumnSize = 1.5f;
        public const float ColumnHeight = 2.5f;
        public const float MinimumSideRouteClearance = 2.5f;

        public static readonly Bounds RoomBounds = BoundsFromRange(MinimumX, MaximumX, MinimumZ, MaximumZ, 0f);
        public static readonly Bounds[] PewFootprints =
        {
            BoundsFromRange(-8.5f, -3f, 24f, 25.5f, PewHeight),
            BoundsFromRange(-8.5f, -3f, 28f, 29.5f, PewHeight),
            BoundsFromRange(-8.5f, -3f, 32f, 33.5f, PewHeight),
            BoundsFromRange(-8.5f, -3f, 36f, 37.5f, PewHeight),
            BoundsFromRange(3f, 8.5f, 24f, 25.5f, PewHeight),
            BoundsFromRange(3f, 8.5f, 28f, 29.5f, PewHeight),
            BoundsFromRange(3f, 8.5f, 32f, 33.5f, PewHeight),
            BoundsFromRange(3f, 8.5f, 36f, 37.5f, PewHeight)
        };

        public static readonly Vector3[] ColumnCenters =
        {
            new Vector3(-8.5f, 0f, 27f),
            new Vector3(8.5f, 0f, 27f),
            new Vector3(-8.5f, 0f, 35f),
            new Vector3(8.5f, 0f, 35f)
        };

        public static readonly Vector3 D2 = new Vector3(6f, 0f, 20f);
        public static readonly Vector3 D3 = new Vector3(-6f, 0f, 42f);
        public static readonly Vector3 CoverPocketWest = new Vector3(-10.5f, 0f, 31f);
        public static readonly Vector3 CoverPocketEast = new Vector3(10.5f, 0f, 35f);

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
