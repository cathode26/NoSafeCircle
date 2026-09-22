using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>Canonical blockout measurements for the Lower Vault authoring scene (revision 5:
    /// X [-20,+20], Z [54,76], following Chapel of Ash's growth to Z [20,54]).</summary>
    public static class LowerVaultLayout
    {
        public const float MinimumX = -20f;
        public const float MaximumX = 20f;
        public const float MinimumZ = 54f;
        public const float MaximumZ = 76f;
        public const float DoorWidth = 3f;
        public const float WallThickness = 0.5f;
        public const float WallHeight = 2.5f;
        public const float HallSpanHeight = 0.5f;

        public static readonly Bounds RoomBounds = BoundsFromRange(MinimumX, MaximumX, MinimumZ, MaximumZ, 0f);

        public static readonly Vector3 D3 = new Vector3(-8f, 0f, MinimumZ);
        public static readonly Vector3 D4 = new Vector3(4f, 0f, MaximumZ);

        // LV-C1: central focal cover, intersects the straight D3-to-D4 sight line.
        public static readonly Bounds CentralColumnCluster = BoundsFromRange(-4f, 2f, 59.5f, 64.5f, 2.5f);
        // LV-W1: west storage pocket.
        public static readonly Bounds WestStoragePile = BoundsFromRange(-12f, -8f, 59.5f, 66.5f, 1.5f);
        // LV-E1: east storage pocket.
        public static readonly Bounds EastStoragePile = BoundsFromRange(7f, 12f, 59.5f, 64.5f, 1.5f);
        // LV-N1: joins the west and north inner wall faces and LV-H1-WestCollision so the west
        // pressure pocket cannot reach the north room.
        public static readonly Bounds NorthWestStorageBar = BoundsFromRange(-19.75f, -10f, 69.5f, 75.75f, 1.5f);

        // LV-H1: the non-damaging walking boundary (three spans) that forms the north merge.
        public static readonly Bounds HallWestSpan = BoundsFromRange(-15f, -6.5f, 66.5f, 69.5f, HallSpanHeight);
        public static readonly Bounds HallCenterSpan = BoundsFromRange(-6.5f, 7f, 67.5f, 70.5f, HallSpanHeight);
        public static readonly Bounds HallEastSpan = BoundsFromRange(12f, 19.75f, 64.5f, 68.5f, HallSpanHeight);

        public static readonly Bounds D3Apron = BoundsFromRange(-10.5f, -5.5f, 54.25f, 59.25f, 0f);
        public static readonly Bounds D4Apron = BoundsFromRange(1.5f, 6.5f, 70.75f, 75.75f, 0f);

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
