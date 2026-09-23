using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>Approved blockout measurements for the Final Room authoring scene.</summary>
    public static class FinalRoomLayout
    {
        public const float MinimumX = -15f;
        public const float MaximumX = 15f;

        // D4Z is the shared Lower Vault boundary. Every other Z coordinate in this room is
        // derived from it so a later accepted Lower Vault boundary revision only moves this value.
        public const float D4X = 4f;
        public const float D4Z = 76f;
        public const float MinimumZ = D4Z;
        public const float MaximumZ = MinimumZ + 28f;

        public const float D5X = 0f;
        public const float D5Z = MaximumZ;
        public const float DoorOpeningWidth = 3f;

        public const float WallThickness = 0.5f;
        public const float GameplayWallColliderHeight = 2.5f;

        public const float FR1MinimumX = -3.5f;
        public const float FR1MaximumX = 3.5f;
        public const float FR1Height = 2f;

        public const float BenchHeight = 0.7f;

        public static Bounds RoomBounds => GroundBounds(MinimumX, MaximumX, MinimumZ, MaximumZ);

        public static Bounds FR1Bounds => SolidBounds(
            FR1MinimumX, FR1MaximumX, MinimumZ + 11f, MinimumZ + 18f, FR1Height);

        public static Bounds D5StagingBounds =>
            GroundBounds(-8f, 8f, MaximumZ - 6f, MaximumZ - 1f);

        public static Bounds WestSupportClusterBounds => GroundBounds(
            MinimumX + WallThickness * 0.5f, MinimumX + 5f, MinimumZ + 3f, MinimumZ + 8f);

        public static Bounds EastSupportClusterBounds => GroundBounds(
            MaximumX - 5f, MaximumX - WallThickness * 0.5f, MinimumZ + 17f, MinimumZ + 22f);

        public static Bounds WestProtectedFlankBounds => GroundBounds(
            MinimumX + 5f, MinimumX + 9.75f, MinimumZ + 9.25f, MinimumZ + 19.75f);

        public static Bounds EastProtectedFlankBounds => GroundBounds(
            MaximumX - 9.75f, MaximumX - 5f, MinimumZ + 9.25f, MinimumZ + 19.75f);

        public static Bounds EastExteriorHazardFrameBounds => GroundBounds(
            MaximumX + 0.25f, MaximumX + 2.25f, MinimumZ + 8f, MinimumZ + 20f);

        public static Bounds WestBenchBounds => SolidBounds(
            MinimumX + WallThickness * 0.5f, MinimumX + 2.75f,
            MinimumZ + 4.225f, MinimumZ + 4.775f, BenchHeight);

        public static Bounds EastBenchBounds => SolidBounds(
            MaximumX - 2.75f, MaximumX - WallThickness * 0.5f,
            MinimumZ + 19.225f, MinimumZ + 19.775f, BenchHeight);

        public static Vector3 D4 => new Vector3(D4X, 0f, D4Z);
        public static Vector3 D5 => new Vector3(D5X, 0f, D5Z);

        public static float WestCirculationWidth =>
            FR1Bounds.min.x - (MinimumX + WallThickness * 0.5f);

        public static float EastCirculationWidth =>
            (MaximumX - WallThickness * 0.5f) - FR1Bounds.max.x;

        public static float SouthCirculationWidth =>
            FR1Bounds.min.z - (MinimumZ + WallThickness * 0.5f);

        public static float NorthCirculationWidth =>
            (MaximumZ - WallThickness * 0.5f) - FR1Bounds.max.z;

        private static Bounds GroundBounds(float minX, float maxX, float minZ, float maxZ)
        {
            return new Bounds(
                new Vector3((minX + maxX) * 0.5f, 0f, (minZ + maxZ) * 0.5f),
                new Vector3(maxX - minX, 0f, maxZ - minZ));
        }

        private static Bounds SolidBounds(float minX, float maxX, float minZ, float maxZ, float height)
        {
            return new Bounds(
                new Vector3((minX + maxX) * 0.5f, height * 0.5f, (minZ + maxZ) * 0.5f),
                new Vector3(maxX - minX, height, maxZ - minZ));
        }
    }
}
