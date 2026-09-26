using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>What a placed wall piece is. The three base kinds fill one-unit slots; the three
    /// overlay kinds are anchored at a point and drawn additively over the base run. The order is
    /// the order of the six prefab slots on WallSpawner.</summary>
    public enum WallPieceKind
    {
        Straight,
        Stub,
        Pilaster,
        Corner,
        Jamb,
        EndCap
    }

    /// <summary>One piece the pass decided to place, in world terms the spawner turns into a
    /// transform. For a base piece <see cref="Point"/> is the root position ON the collider line
    /// and <see cref="Inward"/> is the direction the sprite is inset. For an overlay
    /// <see cref="Point"/> is the run endpoint the art is anchored to and <see cref="Inward"/>
    /// points along the run, INTO it - exactly the pair ArchitecturalWallAccentPlacement.CreateAccent
    /// took.</summary>
    public readonly struct WallPiece
    {
        public readonly WallPieceKind Kind;
        public readonly Vector3 Point;
        public readonly Vector3 Inward;
        public readonly bool AlongX;

        public WallPiece(WallPieceKind kind, Vector3 point, Vector3 inward, bool alongX)
        {
            Kind = kind;
            Point = point;
            Inward = inward;
            AlongX = alongX;
        }
    }

    /// <summary>One gameplay wall collider, named as the committed builders named it.</summary>
    public readonly struct WallColliderRun
    {
        public readonly string Name;
        public readonly Vector3 Center;
        public readonly Vector3 Size;

        public WallColliderRun(string name, Vector3 center, Vector3 size)
        {
            Name = name;
            Center = center;
            Size = size;
        }
    }

    /// <summary>What earlier (more northern) rooms have already claimed. One instance per pass;
    /// processing rooms north to south through it IS the shared-boundary rule.</summary>
    public sealed class WallPassState
    {
        /// <summary>(axis, line, slot start): the north-first occupancy that resolves shared lines.</summary>
        public readonly HashSet<(int, int, int)> Slots = new HashSet<(int, int, int)>();

        /// <summary>Corner points already carrying a post, so a T-junction gets one.</summary>
        public readonly HashSet<(int, int)> Posts = new HashSet<(int, int)>();

        /// <summary>Door centres already carrying their pair of jambs.</summary>
        public readonly HashSet<(int, int)> Jambs = new HashSet<(int, int)>();

        /// <summary>(axis, line) to the spans already covered by a collider on that line.</summary>
        public readonly Dictionary<(int, int), List<(float, float)>> Covered =
            new Dictionary<(int, int), List<(float, float)>>();
    }
}
