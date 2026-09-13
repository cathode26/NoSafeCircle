using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>Canonical blockout measurements for the Lower Vault authoring scene.</summary>
    public static class LowerVaultLayout
    {
        public const float MinimumX = -11f;
        public const float MaximumX = 11f;
        public const float MinimumZ = 42f;
        public const float MaximumZ = 64f;
        public const float DoorWidth = 3f;
        public const float WallThickness = 0.5f;
        public const float WallHeight = 2.5f;
        public const float MinimumRouteClearance = 3f;

        public static readonly Bounds RoomBounds = BoundsFromRange(MinimumX, MaximumX, MinimumZ, MaximumZ, 0f);
        public static readonly Bounds CentralColumnCluster = BoundsFromRange(-1f, 1f, 48f, 52f, 2.5f);
        public static readonly Bounds WestStoragePile = BoundsFromRange(-7.5f, -4f, 53f, 57f, 1.5f);
        public static readonly Bounds EastStoragePile = BoundsFromRange(4f, 7.5f, 47f, 50f, 1.5f);
        public static readonly Bounds NorthWestStorageBar = BoundsFromRange(-7.5f, -1f, 59f, 61f, 1.5f);
        public static readonly Vector3 D3 = new Vector3(-6f, 0f, 42f);
        public static readonly Vector3 D4 = new Vector3(4f, 0f, 64f);

        public static Bounds BoundsFromRange(float minX, float maxX, float minZ, float maxZ, float height)
        {
            return new Bounds(
                new Vector3((minX + maxX) * 0.5f, height * 0.5f, (minZ + maxZ) * 0.5f),
                new Vector3(maxX - minX, height, maxZ - minZ));
        }

        public static float ClearWidthBetween(Bounds left, Bounds right)
        {
            return right.min.x - left.max.x;
        }
    }
}
