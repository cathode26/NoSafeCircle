using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    public sealed class RuinedEntryLayout : MonoBehaviour
    {
        public const float MinimumX = -14f;
        public const float MaximumX = 14f;
        public const float MinimumZ = -26f;
        public const float MaximumZ = 0f;

        public const float DoorCenterX = 0f;
        public const float DoorCenterZ = 0f;
        public const float DoorOpeningWidth = 3f;

        public const float RubbleAMinimumX = 2f;
        public const float RubbleAMaximumX = 8f;
        public const float RubbleAMinimumZ = -17f;
        public const float RubbleAMaximumZ = -10f;

        public const float RubbleBMinimumX = 6f;
        public const float RubbleBMaximumX = 10f;
        public const float RubbleBMinimumZ = -10f;
        public const float RubbleBMaximumZ = -6f;

        public const float WallThickness = 0.5f;
        public const float WallHeight = 2.5f;
        public const float RubbleHeight = 1.25f;

        public static Bounds RoomBounds => CreateGroundBounds(MinimumX, MaximumX, MinimumZ, MaximumZ);

        public static Bounds RubbleABounds =>
            CreateGroundBounds(RubbleAMinimumX, RubbleAMaximumX, RubbleAMinimumZ, RubbleAMaximumZ);

        public static Bounds RubbleBBounds =>
            CreateGroundBounds(RubbleBMinimumX, RubbleBMaximumX, RubbleBMinimumZ, RubbleBMaximumZ);

        public static Vector3 PlayerStart => new Vector3(-4f, 0f, -22f);

        public static Bounds DoorStagingBounds => CreateGroundBounds(-2.5f, 2.5f, -5.25f, -0.25f);

        public static Bounds D1LandmarkWestDressingBounds => CreateGroundBounds(-4.5f, -1.5f, -0.25f, 0.25f);
        public static Bounds D1LandmarkEastDressingBounds => CreateGroundBounds(1.5f, 4.5f, -0.25f, 0.25f);
        public static Bounds NorthWestClusterDressingBounds => CreateGroundBounds(-13.5f, -9.5f, -3f, -0.5f);
        public static Bounds WestWallClusterDressingBounds => CreateGroundBounds(-13.5f, -11f, -17f, -12f);

        public static float WestRouteWidth => RubbleAMinimumX - (MinimumX + WallThickness * 0.5f);

        public static float EastRouteWidth => MaximumX - WallThickness * 0.5f - RubbleBMaximumX;

        private static Bounds CreateGroundBounds(float minimumX, float maximumX, float minimumZ, float maximumZ)
        {
            var center = new Vector3(
                (minimumX + maximumX) * 0.5f,
                0f,
                (minimumZ + maximumZ) * 0.5f);
            var size = new Vector3(maximumX - minimumX, 0f, maximumZ - minimumZ);
            return new Bounds(center, size);
        }
    }
}
