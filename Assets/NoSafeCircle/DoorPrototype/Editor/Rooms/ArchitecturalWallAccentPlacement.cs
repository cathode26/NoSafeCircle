using System;
using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.Editor;
using UnityEditor;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Editor.Rooms
{
    /// <summary>The three roles NSC-109 could not bind as an ordinary one-unit wall Tile.</summary>
    public enum WallAccentRole
    {
        Corner,
        Jamb,
        EndCap
    }

    /// <summary>Which side of a rectangular room a wall run belongs to.</summary>
    public enum WallSide
    {
        North,
        South,
        East,
        West
    }

    /// <summary>A door opening cut into one side of a rectangular room, in the same terms every
    /// room builder already authors one: a centre coordinate along that side and a width.</summary>
    public readonly struct WallAccentDoorOpening
    {
        public readonly WallSide Side;
        public readonly float Center;
        public readonly float Width;

        public WallAccentDoorOpening(WallSide side, float center, float width)
        {
            Side = side;
            Center = center;
            Width = width;
        }
    }

    /// <summary>One straight wall segment's own centreline, in world space, independent of any
    /// single room builder's private layout constants.</summary>
    public readonly struct WallAccentRun
    {
        public readonly Vector3 Start;
        public readonly Vector3 End;
        public readonly Vector3 OutwardNormal;

        public WallAccentRun(Vector3 start, Vector3 end, Vector3 outwardNormal)
        {
            Start = start;
            End = end;
            OutwardNormal = outwardNormal.normalized;
        }

        public Vector3 Direction => (End - Start).normalized;

        public float Length => Vector3.Distance(Start, End);

        // True when the run's own long axis is world X rather than world Z. Every committed room
        // is axis-aligned, so this is exact rather than a nearest-axis approximation.
        public bool RunsAlongX => Mathf.Abs(Direction.x) >= Mathf.Abs(Direction.z);
    }

    /// <summary>The wall runs and floor height of one room, decoupled from any one room builder's
    /// own layout type so this placement helper works against any committed room without
    /// depending on that room's private constants.</summary>
    public sealed class WallAccentRoomGeometry
    {
        public WallAccentRoomGeometry(IReadOnlyList<WallAccentRun> runs, float floorY)
        {
            Runs = runs ?? throw new ArgumentNullException(nameof(runs));
            FloorY = floorY;
        }

        public IReadOnlyList<WallAccentRun> Runs { get; }

        public float FloorY { get; }
    }

    /// <summary>One accent placed by <see cref="ArchitecturalWallAccentPlacement.Place"/>.</summary>
    public readonly struct PlacedWallAccent
    {
        public readonly WallAccentRole Role;
        public readonly WallAccentRun Run;
        public readonly GameObject Instance;

        public PlacedWallAccent(WallAccentRole role, WallAccentRun run, GameObject instance)
        {
            Role = role;
            Run = run;
            Instance = instance;
        }
    }

    /// <summary>Places the three accent sprites NSC-109 could not bind as ordinary wall Tile
    /// segments -- wall_corner, wall_door_jamb and wall_end_cap -- by ROLE at a position derived
    /// from room geometry, and never by painting a Tilemap cell.</summary>
    /// <remarks>
    /// NSC-109 AC-001 revision 3: measured at the import PPU of 64 every wall .meta carries,
    /// wall_corner.png is 128x160 = 2.000 world units wide, wall_door_jamb.png is 128x176 = 2.000
    /// wide, and wall_end_cap.png is 80x160 = 1.250 wide with 80 not a multiple of 64. Binding any
    /// of them as a wall Tile reintroduces the exact one-unit-wide failure NSC-109 removed, since
    /// the committed wall-segment check requires every painted wall sprite to be exactly 1.0 unit
    /// wide.
    /// <para>
    /// AC-002: the Art Director owns the three sprites' .meta import settings, including their
    /// current non-zero vertical pivots (wall_corner y 0.1, wall_door_jamb y 0.147727,
    /// wall_end_cap y 0.1125). Every placement below reads the sprite's own <see cref="Sprite.bounds"/>
    /// at placement time -- which already reflects whatever pivot is currently imported -- and
    /// solves for the transform position that puts the rendered footprint's own edges on the
    /// floor and inside the wall run, rather than assuming a bottom-centre pivot. If the Art
    /// Director later corrects a pivot to 0, the same derivation keeps producing the same ground
    /// contact with no change here.
    /// </para>
    /// </remarks>
    public static class ArchitecturalWallAccentPlacement
    {
        private const string SourceFolder =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/walls/";

        public const string CornerSpritePath = SourceFolder + "wall_corner.png";
        public const string JambSpritePath = SourceFolder + "wall_door_jamb.png";
        public const string EndCapSpritePath = SourceFolder + "wall_end_cap.png";

        // How close two run endpoints must be to count as touching, in world units. Committed
        // room geometry places matching endpoints exactly, but this keeps classification honest
        // against float accumulation in caller-supplied geometry.
        private const float EndpointTolerance = 0.01f;

        /// <summary>Builds the wall runs of a rectangular room by splitting each side at whatever
        /// door openings fall on it, the same way every committed room builder already splits a
        /// wall side around its own door -- generalised once instead of re-derived five times.</summary>
        public static WallAccentRoomGeometry BuildRectangularRoomGeometry(
            Bounds roomBounds, float floorY, IReadOnlyList<WallAccentDoorOpening> doorOpenings)
        {
            if (doorOpenings == null) throw new ArgumentNullException(nameof(doorOpenings));

            var runs = new List<WallAccentRun>();
            AddWallSide(runs, WallSide.North, roomBounds, doorOpenings);
            AddWallSide(runs, WallSide.South, roomBounds, doorOpenings);
            AddWallSide(runs, WallSide.East, roomBounds, doorOpenings);
            AddWallSide(runs, WallSide.West, roomBounds, doorOpenings);
            return new WallAccentRoomGeometry(runs, floorY);
        }

        /// <summary>Places every corner, jamb and end-cap accent the geometry calls for as
        /// children of <paramref name="parent"/>. Visual only: adds no collider, resizes no
        /// existing collider and paints no Tilemap cell.</summary>
        public static IReadOnlyList<PlacedWallAccent> Place(Transform parent, WallAccentRoomGeometry geometry)
        {
            if (parent == null) throw new ArgumentNullException(nameof(parent));
            if (geometry == null) throw new ArgumentNullException(nameof(geometry));

            Sprite cornerSprite = LoadRequiredSprite(CornerSpritePath);
            Sprite jambSprite = LoadRequiredSprite(JambSpritePath);
            Sprite endCapSprite = LoadRequiredSprite(EndCapSpritePath);

            IReadOnlyList<WallAccentRun> runs = geometry.Runs;
            var placed = new List<PlacedWallAccent>();
            var handledCornerPoints = new List<Vector3>();

            for (int runIndex = 0; runIndex < runs.Count; runIndex++)
            {
                WallAccentRun run = runs[runIndex];
                PlaceAtEndpoint(run, run.Start, runs, runIndex, geometry.FloorY, handledCornerPoints,
                    cornerSprite, jambSprite, endCapSprite, parent, placed);
                PlaceAtEndpoint(run, run.End, runs, runIndex, geometry.FloorY, handledCornerPoints,
                    cornerSprite, jambSprite, endCapSprite, parent, placed);
            }

            return placed;
        }

        /// <summary>The world Y a sprite's own transform must sit at so its rendered bottom edge
        /// -- derived from the sprite's own pivot and bounds, never assumed to already be the
        /// pivot -- lands exactly on <paramref name="floorY"/>. Pure and free of any placement
        /// state, so a committed pivot and a hypothetical one can be compared directly.</summary>
        public static float ComputeGroundContactAnchorY(Sprite sprite, float floorY)
        {
            if (sprite == null) throw new ArgumentNullException(nameof(sprite));
            return floorY - sprite.bounds.min.y;
        }

        private static void AddWallSide(
            List<WallAccentRun> runs,
            WallSide side,
            Bounds roomBounds,
            IReadOnlyList<WallAccentDoorOpening> doorOpenings)
        {
            float fixedCoordinate;
            float spanMin;
            float spanMax;
            Vector3 outwardNormal;
            bool alongX;

            switch (side)
            {
                case WallSide.North:
                    fixedCoordinate = roomBounds.max.z;
                    spanMin = roomBounds.min.x;
                    spanMax = roomBounds.max.x;
                    outwardNormal = Vector3.forward;
                    alongX = true;
                    break;
                case WallSide.South:
                    fixedCoordinate = roomBounds.min.z;
                    spanMin = roomBounds.min.x;
                    spanMax = roomBounds.max.x;
                    outwardNormal = Vector3.back;
                    alongX = true;
                    break;
                case WallSide.East:
                    fixedCoordinate = roomBounds.max.x;
                    spanMin = roomBounds.min.z;
                    spanMax = roomBounds.max.z;
                    outwardNormal = Vector3.right;
                    alongX = false;
                    break;
                case WallSide.West:
                    fixedCoordinate = roomBounds.min.x;
                    spanMin = roomBounds.min.z;
                    spanMax = roomBounds.max.z;
                    outwardNormal = Vector3.left;
                    alongX = false;
                    break;
                default:
                    throw new ArgumentOutOfRangeException(nameof(side));
            }

            var segments = new List<Segment> { new Segment(spanMin, spanMax) };
            for (int index = 0; index < doorOpenings.Count; index++)
            {
                WallAccentDoorOpening opening = doorOpenings[index];
                if (opening.Side != side)
                {
                    continue;
                }

                float openingMin = opening.Center - opening.Width * 0.5f;
                float openingMax = opening.Center + opening.Width * 0.5f;
                segments = SubtractInterval(segments, openingMin, openingMax);
            }

            foreach (Segment segment in segments)
            {
                if (segment.Max - segment.Min <= 0f)
                {
                    continue;
                }

                Vector3 start = alongX
                    ? new Vector3(segment.Min, 0f, fixedCoordinate)
                    : new Vector3(fixedCoordinate, 0f, segment.Min);
                Vector3 end = alongX
                    ? new Vector3(segment.Max, 0f, fixedCoordinate)
                    : new Vector3(fixedCoordinate, 0f, segment.Max);
                runs.Add(new WallAccentRun(start, end, outwardNormal));
            }
        }

        // A tangential-axis interval of one wall side, before it is turned into world-space run
        // endpoints. Exists only so a door opening can be subtracted with plain arithmetic.
        private readonly struct Segment
        {
            public readonly float Min;
            public readonly float Max;

            public Segment(float min, float max)
            {
                Min = min;
                Max = max;
            }
        }

        private static List<Segment> SubtractInterval(List<Segment> segments, float cutMin, float cutMax)
        {
            var result = new List<Segment>();
            foreach (Segment segment in segments)
            {
                if (cutMax <= segment.Min || cutMin >= segment.Max)
                {
                    result.Add(segment);
                    continue;
                }

                if (cutMin > segment.Min)
                {
                    result.Add(new Segment(segment.Min, cutMin));
                }

                if (cutMax < segment.Max)
                {
                    result.Add(new Segment(cutMax, segment.Max));
                }
            }

            return result;
        }

        /// <summary>Classifies one endpoint of one run -- Corner, Jamb or EndCap -- purely from
        /// how the other runs in the same geometry sit relative to it, and places the matching
        /// accent. A Corner is deduplicated across the two runs that share it.</summary>
        private static void PlaceAtEndpoint(
            WallAccentRun run,
            Vector3 endpoint,
            IReadOnlyList<WallAccentRun> allRuns,
            int selfIndex,
            float floorY,
            List<Vector3> handledCornerPoints,
            Sprite cornerSprite,
            Sprite jambSprite,
            Sprite endCapSprite,
            Transform parent,
            List<PlacedWallAccent> placed)
        {
            bool isStart = Vector3.Distance(endpoint, run.Start) < EndpointTolerance;
            Vector3 inward = isStart ? run.Direction : -run.Direction;

            if (TryFindTouchingRun(run, endpoint, allRuns, selfIndex))
            {
                if (ContainsPoint(handledCornerPoints, endpoint))
                {
                    return;
                }

                handledCornerPoints.Add(endpoint);
                CreateAccent(WallAccentRole.Corner, run, endpoint, inward, cornerSprite, floorY, parent, placed);
                return;
            }

            if (TryFindColinearGapRun(run, endpoint, inward, allRuns, selfIndex))
            {
                CreateAccent(WallAccentRole.Jamb, run, endpoint, inward, jambSprite, floorY, parent, placed);
                return;
            }

            CreateAccent(WallAccentRole.EndCap, run, endpoint, inward, endCapSprite, floorY, parent, placed);
        }

        // A corner is two runs meeting at the same point along different axes. Two runs on the
        // SAME axis meeting exactly (no gap) never occurs in committed geometry -- only a door
        // opening splits a run -- so it deliberately falls through to the jamb/end-cap checks
        // below rather than being treated as a corner.
        private static bool TryFindTouchingRun(
            WallAccentRun self, Vector3 endpoint, IReadOnlyList<WallAccentRun> runs, int selfIndex)
        {
            for (int index = 0; index < runs.Count; index++)
            {
                if (index == selfIndex)
                {
                    continue;
                }

                WallAccentRun other = runs[index];
                if (other.RunsAlongX == self.RunsAlongX)
                {
                    continue;
                }

                if (Vector3.Distance(other.Start, endpoint) < EndpointTolerance ||
                    Vector3.Distance(other.End, endpoint) < EndpointTolerance)
                {
                    return true;
                }
            }

            return false;
        }

        // A jamb is a free endpoint with another run continuing further along the SAME line, on
        // the outward side of this endpoint, separated by a gap -- exactly the shape a door
        // opening leaves behind when it splits one wall side into two runs.
        private static bool TryFindColinearGapRun(
            WallAccentRun self, Vector3 endpoint, Vector3 inward, IReadOnlyList<WallAccentRun> runs, int selfIndex)
        {
            bool alongX = self.RunsAlongX;
            float fixedCoordinate = alongX ? endpoint.z : endpoint.x;
            float endpointTangential = alongX ? endpoint.x : endpoint.z;
            float outwardSign = alongX ? -Mathf.Sign(inward.x) : -Mathf.Sign(inward.z);

            for (int index = 0; index < runs.Count; index++)
            {
                if (index == selfIndex)
                {
                    continue;
                }

                WallAccentRun other = runs[index];
                if (other.RunsAlongX != alongX)
                {
                    continue;
                }

                float otherFixed = alongX ? other.Start.z : other.Start.x;
                if (Mathf.Abs(otherFixed - fixedCoordinate) > EndpointTolerance)
                {
                    continue;
                }

                float otherStartTangential = alongX ? other.Start.x : other.Start.z;
                float otherEndTangential = alongX ? other.End.x : other.End.z;
                float otherNearTangential = outwardSign >= 0f
                    ? Mathf.Min(otherStartTangential, otherEndTangential)
                    : Mathf.Max(otherStartTangential, otherEndTangential);

                float gap = outwardSign >= 0f
                    ? otherNearTangential - endpointTangential
                    : endpointTangential - otherNearTangential;

                if (gap > EndpointTolerance)
                {
                    return true;
                }
            }

            return false;
        }

        private static bool ContainsPoint(List<Vector3> points, Vector3 point)
        {
            for (int index = 0; index < points.Count; index++)
            {
                if (Vector3.Distance(points[index], point) < EndpointTolerance)
                {
                    return true;
                }
            }

            return false;
        }

        private static void CreateAccent(
            WallAccentRole role,
            WallAccentRun run,
            Vector3 endpoint,
            Vector3 inward,
            Sprite sprite,
            float floorY,
            Transform parent,
            List<PlacedWallAccent> placed)
        {
            // North/south-facing runs (along X) keep the sprite in its authored orientation, and
            // east/west-facing runs (along Z) get the same 90-degree yaw every room's own wall
            // Tilemap already uses, so an accent sits in the same plane as the wall it belongs to.
            Quaternion rotation = run.RunsAlongX ? Quaternion.identity : Quaternion.Euler(0f, 90f, 0f);
            Bounds localBounds = sprite.bounds;

            Vector3 worldOffsetAtLocalMinX = rotation * new Vector3(localBounds.min.x, 0f, 0f);
            Vector3 worldOffsetAtLocalMaxX = rotation * new Vector3(localBounds.max.x, 0f, 0f);

            // Whichever local edge lands farther along the inward direction is the edge that must
            // extend INTO the run; the opposite edge is anchored to the endpoint, so the footprint
            // starts at the corner/jamb/free end and stays inside this run rather than crossing
            // past it into whatever is on the other side.
            bool minEdgeIsInner =
                Vector3.Dot(worldOffsetAtLocalMinX, inward) > Vector3.Dot(worldOffsetAtLocalMaxX, inward);
            Vector3 anchoredWorldOffset = minEdgeIsInner ? worldOffsetAtLocalMaxX : worldOffsetAtLocalMinX;

            float anchorY = ComputeGroundContactAnchorY(sprite, floorY);
            Vector3 anchorPoint = new Vector3(endpoint.x, anchorY, endpoint.z);
            Vector3 position = anchorPoint - anchoredWorldOffset;

            GameObject instance = new GameObject(role + "Accent");
            instance.transform.SetParent(parent, false);
            instance.transform.SetPositionAndRotation(position, rotation);

            SpriteRenderer renderer = instance.AddComponent<SpriteRenderer>();
            renderer.sprite = sprite;
            renderer.sortingLayerName = DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName;

            placed.Add(new PlacedWallAccent(role, run, instance));
        }

        private static Sprite LoadRequiredSprite(string path)
        {
            Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
            if (sprite == null)
            {
                throw new InvalidOperationException(
                    $"Architectural wall accent placement requires the committed sprite at '{path}'.");
            }

            return sprite;
        }
    }
}
