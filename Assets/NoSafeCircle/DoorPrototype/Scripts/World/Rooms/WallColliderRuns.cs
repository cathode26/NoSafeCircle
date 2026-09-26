using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>
    /// The per-run gameplay wall colliders of one room, from its layout: 0.5 thick centred on the
    /// line, 2.5 tall, split at door centre +/- 1.5, named as every committed builder names them
    /// (WestWallCollision, SouthWallWestCollision, ...). On a line an earlier room already covered,
    /// the box is clipped to the span that room's boxes leave uncovered, so exactly one collider
    /// stands along every part of a shared boundary outside its door gap - NSC-048's clause.
    /// </summary>
    /// <remarks>
    /// <para>
    /// PER RUN, NEVER PER SLOT. Fable retracted v3's per-segment 1 x 2.5 x 0.3 box for a concrete
    /// reason: the map's visual door gap is 4 units (the '++' pair) while the contract-pinned
    /// collider gap is 3, so half a unit of jamb art overhangs the collider on each side, and a
    /// per-slot box cannot express that. Keeping the run also keeps NSC-048 AC-004's named boxes
    /// (SouthWallWestCollision X [-15,+2.5] and friends) exactly as delivered.
    /// </para>
    /// <para>
    /// CLIPPED, WHERE THE COMPOSER REMOVED. RoomSceneComposer.RemoveContainedWallColliders drops
    /// whichever piece lies wholly inside the other room's piece, so today the Lower Vault's full
    /// north boxes survive and the Final Room's south boxes are destroyed. Both shapes satisfy the
    /// clause; clipping is the addendum's choice and it leaves every room's own named boxes in
    /// place, with the wider room's box reduced to the jogs (X [-20,-15] and [15,20] at Z 76).
    /// </para>
    /// </remarks>
    public static class WallColliderRuns
    {
        private static readonly WallEdge[] Edges =
            { WallEdge.North, WallEdge.South, WallEdge.West, WallEdge.East };

        public static List<WallColliderRun> ForRoom(WallRoom room, WallPassState state)
        {
            var runs = new List<WallColliderRun>();
            foreach (WallEdge edge in Edges)
            {
                bool alongX = WallRoom.AlongX(edge);
                float line = room.Line(edge);
                var segments = new List<(float, float)>
                    { (alongX ? room.XMin : room.ZMin, alongX ? room.XMax : room.ZMax) };

                int doors = 0;
                foreach (Vector3 door in room.Doors)
                {
                    if (room.EdgeOf(door) != edge) continue;
                    doors++;
                    float centre = alongX ? door.x : door.z;
                    segments = Subtract(segments, centre - room.DoorWidth * 0.5f, centre + room.DoorWidth * 0.5f);
                }

                var key = (alongX ? 0 : 1, Mathf.RoundToInt(line));
                if (!state.Covered.TryGetValue(key, out List<(float, float)> covered))
                {
                    state.Covered[key] = covered = new List<(float, float)>();
                }

                for (int i = 0; i < segments.Count; i++)
                {
                    // A doored side names its two pieces by the end they hold; a whole side has
                    // no label. A third piece between two doors would be new geometry, so it is
                    // named rather than silently dropped.
                    string label = doors == 0 ? ""
                        : i == 0 ? (alongX ? "West" : "South")
                        : i == segments.Count - 1 ? (alongX ? "East" : "North")
                        : "Middle" + i;

                    var pieces = new List<(float, float)> { segments[i] };
                    foreach ((float min, float max) in covered.ToArray())
                    {
                        pieces = Subtract(pieces, min, max);
                    }

                    for (int p = 0; p < pieces.Count; p++)
                    {
                        (float a, float b) = pieces[p];
                        covered.Add((a, b));
                        float mid = (a + b) * 0.5f;
                        runs.Add(new WallColliderRun(
                            edge + "Wall" + label + "Collision" + (p > 0 ? p.ToString() : ""),
                            alongX ? new Vector3(mid, room.WallHeight * 0.5f, line)
                                   : new Vector3(line, room.WallHeight * 0.5f, mid),
                            alongX ? new Vector3(b - a, room.WallHeight, room.WallThickness)
                                   : new Vector3(room.WallThickness, room.WallHeight, b - a)));
                    }
                }
            }

            return runs;
        }

        // Ported from ArchitecturalWallAccentPlacement.SubtractInterval: cut one closed interval
        // out of a list of ascending disjoint intervals.
        private static List<(float, float)> Subtract(List<(float, float)> segments, float cutMin, float cutMax)
        {
            var result = new List<(float, float)>();
            foreach ((float min, float max) in segments)
            {
                if (cutMax <= min || cutMin >= max)
                {
                    result.Add((min, max));
                    continue;
                }
                if (cutMin > min) result.Add((min, cutMin));
                if (cutMax < max) result.Add((cutMax, max));
            }
            return result;
        }
    }
}
