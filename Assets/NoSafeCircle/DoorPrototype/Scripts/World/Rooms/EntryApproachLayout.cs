using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>Open floor used only for the chase leading into Ruined Entry's south doorway.</summary>
    public static class EntryApproachLayout
    {
        public const float MinimumX = -9f;
        public const float MaximumX = 1f;
        public const float MinimumZ = -64f;
        public const float MaximumZ = RuinedEntryLayout.MinimumZ;
        public const float CenterX = -4f;
        public const float GateZ = MaximumZ;
        public const float OpeningWidth = 3f;
        public const float WallThickness = RuinedEntryLayout.WallThickness;
        public const float WallHeight = RuinedEntryLayout.WallHeight;

        public static Bounds ApproachBounds =>
            new Bounds(new Vector3(CenterX, 0f, (MinimumZ + MaximumZ) * 0.5f),
                new Vector3(MaximumX - MinimumX, 0f, MaximumZ - MinimumZ));

        public static Vector3 StartDoorCenter => new Vector3(CenterX, 0f, GateZ);
        public static Vector3 WizardEntryStart => new Vector3(CenterX, 0f, -60f);
        public static Vector3 PursuerEntryStart => new Vector3(CenterX, 0f, -62.5f);
        public static Vector3 PursuerStop => new Vector3(CenterX, 0f, -53.5f);
        public static Vector3 DoorCloseTrigger => new Vector3(CenterX, 0f, -50.75f);
        public static Vector3 FirstRoomArrival => new Vector3(CenterX, 0f, -48f);
    }
}
