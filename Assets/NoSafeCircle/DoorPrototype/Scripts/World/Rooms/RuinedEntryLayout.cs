using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    public sealed class RuinedEntryLayout : MonoBehaviour
    {
        public const float MinimumX = -10f;
        public const float MaximumX = 10f;
        public const float MinimumZ = -18f;
        public const float MaximumZ = 0f;

        public const float DoorCenterX = 0f;
        public const float DoorCenterZ = 0f;
        public const float DoorOpeningWidth = 3f;

        public const float RubbleAMinimumX = 2f;
        public const float RubbleAMaximumX = 6f;
        public const float RubbleAMinimumZ = -12f;
        public const float RubbleAMaximumZ = -8f;

        public const float RubbleBMinimumX = 4f;
        public const float RubbleBMaximumX = 7f;
        public const float RubbleBMinimumZ = -8f;
        public const float RubbleBMaximumZ = -6f;

        public const float WallThickness = 0.5f;
        public const float WallHeight = 2f;
        public const float RubbleHeight = 1.25f;

        public static Bounds RoomBounds => CreateGroundBounds(MinimumX, MaximumX, MinimumZ, MaximumZ);

        public static Bounds RubbleABounds =>
            CreateGroundBounds(RubbleAMinimumX, RubbleAMaximumX, RubbleAMinimumZ, RubbleAMaximumZ);

        public static Bounds RubbleBBounds =>
            CreateGroundBounds(RubbleBMinimumX, RubbleBMaximumX, RubbleBMinimumZ, RubbleBMaximumZ);

        public static Bounds DoorStagingBounds => CreateGroundBounds(-2.5f, 2.5f, -5f, MaximumZ);

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
