using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>Approved blockout measurements for the Final Room authoring scene.</summary>
    public static class FinalRoomLayout
    {
        public const float MinimumX = -12f;
        public const float MaximumX = 12f;
        public const float MinimumZ = 64f;
        public const float MaximumZ = 86f;

        public const float D4X = 4f;
        public const float D4Z = 64f;
        public const float D5X = 0f;
        public const float D5Z = 86f;
        public const float DoorOpeningWidth = 3f;

        public const float WallThickness = 0.5f;
        public const float WallHeight = 2f;

        public const float FinalObstacleMinimumX = -2.5f;
        public const float FinalObstacleMaximumX = 2.5f;
        public const float FinalObstacleMinimumZ = 73.5f;
        public const float FinalObstacleMaximumZ = 78.5f;
        public const float FinalObstacleHeight = 2f;

        public static Bounds RoomBounds => GroundBounds(MinimumX, MaximumX, MinimumZ, MaximumZ);
        public static Bounds FinalObstacleBounds => SolidBounds(
            FinalObstacleMinimumX, FinalObstacleMaximumX,
            FinalObstacleMinimumZ, FinalObstacleMaximumZ, FinalObstacleHeight);

        public static Vector3 D4 => new Vector3(D4X, 0f, D4Z);
        public static Vector3 D5 => new Vector3(D5X, 0f, D5Z);

        public static Bounds NorthStagingBounds => GroundBounds(-9f, 9f, 80f, 84f);

        public static float WestCirculationWidth =>
            FinalObstacleMinimumX - (MinimumX + WallThickness * 0.5f);

        public static float EastCirculationWidth =>
            MaximumX - WallThickness * 0.5f - FinalObstacleMaximumX;

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
