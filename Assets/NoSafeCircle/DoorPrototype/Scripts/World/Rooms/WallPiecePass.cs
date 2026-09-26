using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>
    /// The piece pass of Fable's addendum 2B: marching squares over floor01.txt with a 3x3
    /// neighbourhood, one sprite per one-unit slot, and overlays at corners, door edges and free
    /// run ends. Pure: it returns decisions and touches no GameObject, so it can be run into an
    /// empty scene or against a fixture map. Colliders are <see cref="WallColliderRuns"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A CELL IS TWO SLOTS. The map's 2-unit cell holding 1-unit wall art is the Diablo 1
    /// megatile/piece relationship, not a conflict: a wall-band cell contributes the two 1-unit
    /// intervals of its outer edge to that edge's line, and a corner cell contributes to two lines.
    /// The line coordinate is the layout's, never the cell's (see <see cref="WallRoom"/>), and a
    /// slot outside the layout span is dropped - which is how the Final Room's 32 cell-slots become
    /// its 30 layout-slots.
    /// </para>
    /// <para>
    /// AN OPENING IS NOT INTERIOR. The table classifies a wall cell by which of its eight
    /// neighbours is FLOOR. An opening cell sits in the band itself, beside its wall cells along
    /// the line, so reading it as interior would hand every opening-adjacent cell a phantom
    /// perpendicular edge at a coordinate that is no room line at all. The spec's last table row -
    /// an opening neighbour along the line keeps "its band class" - is exactly what excluding the
    /// opening glyph yields.
    /// </para>
    /// <para>
    /// PILASTERS: NSC-127 AC-001 fixes the rhythm at EVERY FOURTH CELL of the one-unit wall grid
    /// and forbids anything denser, so <see cref="PilasterInterval"/> is the contract's number, not
    /// a tuning choice. A run is the layout run between a corner and a door's collider edge; the
    /// first and last slot of a run keep the straight tile so a pilaster never abuts a post or a
    /// jamb. Only far (straight) sides carry them - the near sides are the 2.797-unit stub.
    /// </para>
    /// </remarks>
    public static class WallPiecePass
    {
        public const int PilasterInterval = 4;

        /// <summary>Every visual piece of one room, in placement order, honouring what earlier
        /// rooms claimed in <paramref name="state"/>.</summary>
        public static List<WallPiece> Pieces(
            AsciiRoomMap map, float originX, float originZ, WallRoom room, WallPassState state)
        {
            const float cell = AsciiRoomMap.WorldUnitsPerCell;
            var pieces = new List<WallPiece>();

            // The cells whose area overlaps the layout rectangle. Rooms touch along whole lines,
            // so a cell belongs to exactly one room; the Final Room's band cells overlap its
            // rectangle by one unit and are still its cells.
            int c0 = Mathf.FloorToInt((room.XMin - originX) / cell);
            int c1 = Mathf.CeilToInt((room.XMax - originX) / cell) - 1;
            int r0 = Mathf.FloorToInt((originZ - room.ZMax) / cell);
            int r1 = Mathf.CeilToInt((originZ - room.ZMin) / cell) - 1;

            var edges = new List<WallEdge>(2);
            for (int r = r0; r <= r1; r++)
            {
                for (int c = c0; c <= c1; c++)
                {
                    if (Cell(map, c, r) != AsciiCell.Wall) continue;

                    edges.Clear();
                    if (IsFloor(map, c, r + 1)) edges.Add(WallEdge.North);
                    if (IsFloor(map, c, r - 1)) edges.Add(WallEdge.South);
                    if (IsFloor(map, c + 1, r)) edges.Add(WallEdge.West);
                    if (IsFloor(map, c - 1, r)) edges.Add(WallEdge.East);

                    if (edges.Count == 0)
                    {
                        // No 4-neighbour is interior: a ring corner, whose interior is diagonal.
                        // The post goes at the LAYOUT corner, deduplicated by point, so the D4
                        // T-junction and a shared corner get exactly one.
                        if (IsFloor(map, c + 1, r + 1)) Corner(pieces, edges, room, WallEdge.North, WallEdge.West, state);
                        else if (IsFloor(map, c - 1, r + 1)) Corner(pieces, edges, room, WallEdge.North, WallEdge.East, state);
                        else if (IsFloor(map, c + 1, r - 1)) Corner(pieces, edges, room, WallEdge.South, WallEdge.West, state);
                        else if (IsFloor(map, c - 1, r - 1)) Corner(pieces, edges, room, WallEdge.South, WallEdge.East, state);
                    }

                    float x0 = originX + c * cell;
                    float zTop = originZ - r * cell;
                    foreach (WallEdge edge in edges)
                    {
                        Slots(pieces, room, edge, WallRoom.AlongX(edge) ? x0 : zTop - cell, state);
                    }

                    if (edges.Count == 1)
                    {
                        EndCaps(pieces, map, room, edges[0], c, r, x0, zTop);
                    }
                }
            }

            Jambs(pieces, room, state);
            return pieces;
        }

        private static void Corner(List<WallPiece> pieces, List<WallEdge> edges, WallRoom room,
            WallEdge zEdge, WallEdge xEdge, WallPassState state)
        {
            edges.Add(zEdge);
            edges.Add(xEdge);
            float x = room.Line(xEdge);
            float z = room.Line(zEdge);
            if (!state.Posts.Add((Mathf.RoundToInt(x), Mathf.RoundToInt(z)))) return;

            // Anchored along the north/south run, as today's placer reaches every corner from its
            // north or south run first: the post spans the run's first two slots from the corner.
            pieces.Add(new WallPiece(WallPieceKind.Corner, new Vector3(x, 0f, z), WallRoom.Inward(xEdge), true));
        }

        private static void Slots(List<WallPiece> pieces, WallRoom room, WallEdge edge, float lo, WallPassState state)
        {
            bool alongX = WallRoom.AlongX(edge);
            float line = room.Line(edge);
            float min = alongX ? room.XMin : room.ZMin;
            float max = alongX ? room.XMax : room.ZMax;

            for (int i = 0; i < 2; i++)
            {
                float start = lo + i;
                if (start < min || start + 1f > max) continue;
                if (!state.Slots.Add((alongX ? 0 : 1, Mathf.RoundToInt(line), Mathf.RoundToInt(start)))) continue;

                // Far sides (north, west) take the 2.5-unit straight tile; near sides (south, east)
                // take wall_broken_stub at its native 2.797 units, Vincent's own C pick. There is
                // no "WallLow": the stub IS the near wall.
                bool far = edge == WallEdge.North || edge == WallEdge.West;
                WallPieceKind kind = !far ? WallPieceKind.Stub
                    : IsPilasterSlot(room, edge, start) ? WallPieceKind.Pilaster
                    : WallPieceKind.Straight;
                Vector3 point = alongX ? new Vector3(start + 0.5f, 0f, line) : new Vector3(line, 0f, start + 0.5f);
                pieces.Add(new WallPiece(kind, point, WallRoom.Inward(edge), alongX));
            }
        }

        private static bool IsPilasterSlot(WallRoom room, WallEdge edge, float start)
        {
            bool alongX = WallRoom.AlongX(edge);
            float runStart = alongX ? room.XMin : room.ZMin;
            float runLast = (alongX ? room.XMax : room.ZMax) - 1f;
            foreach (Vector3 door in room.Doors)
            {
                if (room.EdgeOf(door) != edge) continue;
                float centre = alongX ? door.x : door.z;
                float half = room.DoorWidth * 0.5f;
                if (start > centre) runStart = Mathf.Max(runStart, Mathf.Ceil(centre + half));
                else runLast = Mathf.Min(runLast, Mathf.Floor(centre - half) - 1f);
            }

            int index = Mathf.RoundToInt(start - runStart);
            return index % PilasterInterval == 0 && start > runStart && start < runLast;
        }

        private static void EndCaps(List<WallPiece> pieces, AsciiRoomMap map, WallRoom room,
            WallEdge edge, int c, int r, float x0, float zTop)
        {
            // A band cell whose neighbour ALONG the line is outside the level ends its run against
            // nothing - neither a corner (that cell has no interior 4-neighbour) nor an opening
            // (that neighbour is the opening glyph). floor01's rings have none; kept for minisets.
            // The cap is anchored at the run's end on the layout line and extends INTO the run.
            const float cell = AsciiRoomMap.WorldUnitsPerCell;
            float line = room.Line(edge);
            bool alongX = WallRoom.AlongX(edge);
            bool lowFree = alongX ? Cell(map, c - 1, r) == AsciiCell.Outside : Cell(map, c, r + 1) == AsciiCell.Outside;
            bool highFree = alongX ? Cell(map, c + 1, r) == AsciiCell.Outside : Cell(map, c, r - 1) == AsciiCell.Outside;
            float low = alongX ? Mathf.Max(x0, room.XMin) : Mathf.Max(zTop - cell, room.ZMin);
            float high = alongX ? Mathf.Min(x0 + cell, room.XMax) : Mathf.Min(zTop, room.ZMax);
            Vector3 lowInward = alongX ? Vector3.right : Vector3.forward;
            if (lowFree) pieces.Add(new WallPiece(WallPieceKind.EndCap, OnLine(alongX, low, line), lowInward, alongX));
            if (highFree) pieces.Add(new WallPiece(WallPieceKind.EndCap, OnLine(alongX, high, line), -lowInward, alongX));
        }

        private static void Jambs(List<WallPiece> pieces, WallRoom room, WallPassState state)
        {
            foreach (Vector3 door in room.Doors)
            {
                // One pair per door, not per room: a shared door is authored by both rooms and the
                // placer anchors both pairs at the same two points, so the second pair is the same
                // art twice. Keyed at half-unit resolution because door centres are authored floats.
                if (!state.Jambs.Add((Mathf.RoundToInt(door.x * 2f), Mathf.RoundToInt(door.z * 2f)))) continue;

                WallEdge edge = room.EdgeOf(door);
                bool alongX = WallRoom.AlongX(edge);
                float line = room.Line(edge);
                float centre = alongX ? door.x : door.z;
                float half = room.DoorWidth * 0.5f;

                // Each jamb is anchored at the collider gap edge (centre +/- 1.5) and extends INTO
                // its run, away from the door - the run direction CreateAccent received.
                Vector3 lowInward = alongX ? Vector3.left : Vector3.back;
                pieces.Add(new WallPiece(WallPieceKind.Jamb, OnLine(alongX, centre - half, line), lowInward, alongX));
                pieces.Add(new WallPiece(WallPieceKind.Jamb, OnLine(alongX, centre + half, line), -lowInward, alongX));
            }
        }

        private static Vector3 OnLine(bool alongX, float along, float line) =>
            alongX ? new Vector3(along, 0f, line) : new Vector3(line, 0f, along);

        private static AsciiCell Cell(AsciiRoomMap map, int column, int row)
        {
            if (column < 0 || column >= map.Width || row < 0 || row >= map.Height) return AsciiCell.Outside;
            return map[column, row];
        }

        private static bool IsFloor(AsciiRoomMap map, int column, int row) => Cell(map, column, row) == AsciiCell.Floor;
    }
}
