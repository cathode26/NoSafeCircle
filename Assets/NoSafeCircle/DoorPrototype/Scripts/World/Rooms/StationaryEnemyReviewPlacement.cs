using System;
using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.Enemies;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    public readonly struct StationaryEnemyReviewAnchor
    {
        public RoomId Room { get; }
        public StationaryEnemyArchetype Archetype { get; }
        public StationaryEnemyDirection Facing { get; }
        public Vector3 GroundPosition { get; }

        public StationaryEnemyReviewAnchor(RoomId room, StationaryEnemyArchetype archetype,
            StationaryEnemyDirection facing, Vector3 groundPosition)
        {
            Room = room;
            Archetype = archetype;
            Facing = facing;
            GroundPosition = groundPosition;
        }
    }

    // Review-only placements. These SpriteRenderers have no Collider and do not enter
    // enemy simulation. Later encounter tasks own real spawn and movement decisions.
    public static class StationaryEnemyReviewPlacement
    {
        private static readonly IReadOnlyList<StationaryEnemyReviewAnchor> AuthoredAnchors =
            Array.AsReadOnly(new[]
            {
                new StationaryEnemyReviewAnchor(RoomId.RuinedEntry,
                    StationaryEnemyArchetype.Melee, StationaryEnemyDirection.SouthEast,
                    new Vector3(-8f, 0f, -15f)),
                new StationaryEnemyReviewAnchor(RoomId.RuinedEntry,
                    StationaryEnemyArchetype.Ranged, StationaryEnemyDirection.SouthWest,
                    new Vector3(-4f, 0f, -10f)),
                new StationaryEnemyReviewAnchor(RoomId.BoneArchive,
                    StationaryEnemyArchetype.Melee, StationaryEnemyDirection.North,
                    new Vector3(2f, 0f, 5f)),
                new StationaryEnemyReviewAnchor(RoomId.BoneArchive,
                    StationaryEnemyArchetype.Ranged, StationaryEnemyDirection.South,
                    new Vector3(6f, 0f, 16f)),
                new StationaryEnemyReviewAnchor(RoomId.ChapelOfAsh,
                    StationaryEnemyArchetype.Melee, StationaryEnemyDirection.West,
                    new Vector3(-1.5f, 0f, 27f)),
                new StationaryEnemyReviewAnchor(RoomId.ChapelOfAsh,
                    StationaryEnemyArchetype.Ranged, StationaryEnemyDirection.NorthEast,
                    new Vector3(-1.5f, 0f, 35f)),
                new StationaryEnemyReviewAnchor(RoomId.LowerVault,
                    StationaryEnemyArchetype.Melee, StationaryEnemyDirection.NorthWest,
                    new Vector3(-8f, 0f, 48f)),
                new StationaryEnemyReviewAnchor(RoomId.LowerVault,
                    StationaryEnemyArchetype.Ranged, StationaryEnemyDirection.East,
                    new Vector3(2f, 0f, 56f)),
                new StationaryEnemyReviewAnchor(RoomId.FinalRoom,
                    StationaryEnemyArchetype.Melee, StationaryEnemyDirection.East,
                    new Vector3(-7f, 0f, 75f)),
                new StationaryEnemyReviewAnchor(RoomId.FinalRoom,
                    StationaryEnemyArchetype.Ranged, StationaryEnemyDirection.North,
                    new Vector3(7f, 0f, 75f))
            });

        public static IReadOnlyList<StationaryEnemyReviewAnchor> Anchors => AuthoredAnchors;
    }
}
