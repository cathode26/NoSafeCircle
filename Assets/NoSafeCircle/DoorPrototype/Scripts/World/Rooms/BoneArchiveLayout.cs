using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>Canonical blockout measurements for the Bone Archive source scene.</summary>
    public static class BoneArchiveLayout
    {
        public const float MinLaneWidth = 2.5f;
        public const float NormalLaneWidth = 3.5f;
        public const float WallThickness = 0.5f;
        public const float WallHeight = 2.5f;
        public const float DoorWidth = 3f;

        public static readonly Bounds RoomBounds = new Bounds(new Vector3(0f, 0f, 10f), new Vector3(20f, 0f, 20f));
        public static readonly Bounds ShelfA = BoundsFromRange(-6.5f, -5f, 4f, 16f, 2.5f);
        public static readonly Bounds ShelfB = BoundsFromRange(-1.5f, 0f, 3f, 14f, 2.5f);
        public static readonly Bounds ShelfC = BoundsFromRange(3.5f, 5f, 6f, 17f, 2.5f);
        public static readonly Bounds CollapsedFurnitureBA1 = BoundsFromRange(0f, 1f, 9f, 11f, 1.25f);
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
