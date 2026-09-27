using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>A compact playable annex south of Ruined Entry, outside the five-room progression.</summary>
    public static class EntryChamberLayout
    {
        public const float MinimumX = -9f;
        public const float MaximumX = 1f;
        public const float MinimumZ = -38f;
        public const float MaximumZ = RuinedEntryLayout.MinimumZ;
        public const float CenterX = -4f;
        public const float GateZ = -32f;
        public const float OpeningWidth = 3f;
        public const float WallThickness = RuinedEntryLayout.WallThickness;
        public const float WallHeight = RuinedEntryLayout.WallHeight;

        public static Bounds RoomBounds =>
            new Bounds(new Vector3(CenterX, 0f, (MinimumZ + MaximumZ) * 0.5f),
                new Vector3(MaximumX - MinimumX, 0f, MaximumZ - MinimumZ));

        public static Vector3 RoomOpening => new Vector3(CenterX, 0f, MaximumZ);
        public static Vector3 StartDoorCenter => new Vector3(CenterX, 0f, GateZ);
        public static Vector3 WizardEntryStart => new Vector3(CenterX, 0f, -34f);
        public static Vector3 PursuerEntryStart => new Vector3(CenterX, 0f, -37f);
        public static Vector3 PursuerStop => new Vector3(CenterX, 0f, -33.5f);
        public static Vector3 DoorCloseTrigger => new Vector3(CenterX, 0f, -29.75f);
        public static Vector3 FirstRoomArrival => new Vector3(CenterX, 0f, -22f);
    }
}
