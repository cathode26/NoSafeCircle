using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>Which edge of a rectangular room a wall slot, run or door belongs to.</summary>
    public enum WallEdge
    {
        North,
        South,
        West,
        East
    }

    /// <summary>
    /// One room as the wall pass sees it: the LAYOUT rectangle, its door centres and its collider
    /// figures. Nothing here is authored; every number is read from that room's own *Layout.cs.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THE LAYOUT SETS THE LINE, THE MAP CLASSIFIES THE CELLS. Fable's addendum 2A, as corrected by
    /// the Game Agent on 2026-09-26: "rect = the room's layout bounds (the map classifies cells;
    /// the layout sets the line)". The Final Room is the case that decides it - its map cells span
    /// X [-16,16] because 15 is not on the 2-unit cell lattice, while NSC-048 delivered the room at
    /// X [-15,15] and eight contracts carry that literal. So the collider line, the slot extent and
    /// the corner points come from here, and floor01.txt only says which cells are wall band. The
    /// wall then stands on its own collider and there is no gap to close.
    /// </para>
    /// <para>
    /// ROOMS ARE LISTED, NOT DISCOVERED. Adjacent rooms' wall bands touch in the map (the Final
    /// Room's south band row sits directly above the Lower Vault's north band row), so "connected
    /// components of non-space cells" is ONE component, not five. The five layouts are the only
    /// thing that knows where one room ends and the next begins.
    /// </para>
    /// <para>
    /// NORTH TO SOUTH IS THE SHARED-BOUNDARY RULE. The pass claims each one-unit slot on a wall
    /// line for the first room that reaches it, so the northern room's south band wins every
    /// shared line and the southern room's north band fills only the jogs. That order replaces
    /// RoomSceneComposer.ReconcileSharedRoomBoundaries with no code, which is why this array is
    /// ordered rather than merely listed.
    /// </para>
    /// </remarks>
    public sealed class WallRoom
    {
        public readonly string Name;
        public readonly float XMin;
        public readonly float XMax;
        public readonly float ZMin;
        public readonly float ZMax;

        /// <summary>The 3.0-unit collider gap, centred on each door. The visual gap the map draws
        /// is a 4-unit '++' pair; the half-unit of jamb art each side overhangs this.</summary>
        public readonly float DoorWidth;
        public readonly float WallThickness;
        public readonly float WallHeight;

        /// <summary>Door centres, as the layouts author them: on the line they cut.</summary>
        public readonly Vector3[] Doors;

        public WallRoom(string name, float xMin, float xMax, float zMin, float zMax,
            float doorWidth, float wallThickness, float wallHeight, params Vector3[] doors)
        {
            Name = name;
            XMin = xMin;
            XMax = xMax;
            ZMin = zMin;
            ZMax = zMax;
            DoorWidth = doorWidth;
            WallThickness = wallThickness;
            WallHeight = wallHeight;
            Doors = doors;
        }

        /// <summary>The collider line an edge sits on: z for north/south, x for west/east.</summary>
        public float Line(WallEdge edge)
        {
            switch (edge)
            {
                case WallEdge.North: return ZMax;
                case WallEdge.South: return ZMin;
                case WallEdge.West: return XMin;
                default: return XMax;
            }
        }

        /// <summary>Which edge a door cuts, read from which bound its centre lies on.</summary>
        public WallEdge EdgeOf(Vector3 door)
        {
            if (Mathf.Approximately(door.z, ZMax)) return WallEdge.North;
            if (Mathf.Approximately(door.z, ZMin)) return WallEdge.South;
            if (Mathf.Approximately(door.x, XMin)) return WallEdge.West;
            return WallEdge.East;
        }

        /// <summary>Unit vector from an edge into the room. The sprite inset and the corner and
        /// jamb anchoring all run along these.</summary>
        public static Vector3 Inward(WallEdge edge)
        {
            switch (edge)
            {
                case WallEdge.North: return Vector3.back;
                case WallEdge.South: return Vector3.forward;
                case WallEdge.West: return Vector3.right;
                default: return Vector3.left;
            }
        }

        /// <summary>True for the lines that run along world X (yaw 0); false for the ones along
        /// world Z, which take the 90-degree yaw every wall Tilemap used.</summary>
        public static bool AlongX(WallEdge edge) => edge == WallEdge.North || edge == WallEdge.South;

        /// <summary>The five rooms of floor01, northernmost first. Every figure is the layout's.</summary>
        public static readonly WallRoom[] NorthToSouth =
        {
            new WallRoom("FinalRoom",
                FinalRoomLayout.MinimumX, FinalRoomLayout.MaximumX,
                FinalRoomLayout.MinimumZ, FinalRoomLayout.MaximumZ,
                FinalRoomLayout.DoorOpeningWidth, FinalRoomLayout.WallThickness,
                FinalRoomLayout.GameplayWallColliderHeight,
                new Vector3(FinalRoomLayout.D4X, 0f, FinalRoomLayout.D4Z),
                new Vector3(FinalRoomLayout.D5X, 0f, FinalRoomLayout.D5Z)),
            new WallRoom("LowerVault",
                LowerVaultLayout.MinimumX, LowerVaultLayout.MaximumX,
                LowerVaultLayout.MinimumZ, LowerVaultLayout.MaximumZ,
                LowerVaultLayout.DoorWidth, LowerVaultLayout.WallThickness, LowerVaultLayout.WallHeight,
                LowerVaultLayout.D3, LowerVaultLayout.D4),
            new WallRoom("ChapelOfAsh",
                ChapelOfAshLayout.MinimumX, ChapelOfAshLayout.MaximumX,
                ChapelOfAshLayout.MinimumZ, ChapelOfAshLayout.MaximumZ,
                ChapelOfAshLayout.DoorWidth, ChapelOfAshLayout.WallThickness, ChapelOfAshLayout.WallHeight,
                ChapelOfAshLayout.D2, ChapelOfAshLayout.D3),
            new WallRoom("BoneArchive",
                BoneArchiveLayout.RoomBounds.min.x, BoneArchiveLayout.RoomBounds.max.x,
                BoneArchiveLayout.RoomBounds.min.z, BoneArchiveLayout.RoomBounds.max.z,
                BoneArchiveLayout.DoorWidth, BoneArchiveLayout.WallThickness, BoneArchiveLayout.WallHeight,
                BoneArchiveLayout.D1, BoneArchiveLayout.D2),
            new WallRoom("RuinedEntry",
                RuinedEntryLayout.MinimumX, RuinedEntryLayout.MaximumX,
                RuinedEntryLayout.MinimumZ, RuinedEntryLayout.MaximumZ,
                RuinedEntryLayout.DoorOpeningWidth, RuinedEntryLayout.WallThickness,
                RuinedEntryLayout.WallHeight,
                new Vector3(RuinedEntryLayout.DoorCenterX, 0f, RuinedEntryLayout.DoorCenterZ))
        };
    }
}
