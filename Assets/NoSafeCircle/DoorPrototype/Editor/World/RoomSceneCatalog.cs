using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Editor.World
{
    // NSC-069 AC-001/AC-006: the shared, generated data asset that records the five stable room
    // identities, their authoring-scene paths, and the fixed D1-D5 door sequence. NSC-044 through
    // NSC-048 read these entries to know which scene path and RoomId they own; they do not add,
    // remove, or reorder catalog entries.
    public sealed class RoomSceneCatalog : ScriptableObject
    {
        public const string AssetPath = "Assets/NoSafeCircle/DoorPrototype/Generated/World/RoomSceneCatalog.asset";

        [Serializable]
        public struct RoomBounds
        {
            public float MinX;
            public float MaxX;
            public float MinZ;
            public float MaxZ;

            public RoomBounds(float minX, float maxX, float minZ, float maxZ)
            {
                MinX = minX;
                MaxX = maxX;
                MinZ = minZ;
                MaxZ = maxZ;
            }

            public bool ContainsX(float x) => x >= MinX && x <= MaxX;
        }

        [Serializable]
        public sealed class RoomCatalogEntry
        {
            [SerializeField] private RoomId roomId;
            [SerializeField] private string sceneAssetPath;
            [SerializeField] private RoomBounds bounds;

            public RoomCatalogEntry(RoomId roomId, string sceneAssetPath, RoomBounds bounds)
            {
                this.roomId = roomId;
                this.sceneAssetPath = sceneAssetPath;
                this.bounds = bounds;
            }

            public RoomId RoomId => roomId;
            public string SceneAssetPath => sceneAssetPath;
            public RoomBounds Bounds => bounds;
        }

        // NSC-069 AC-003: the shared-boundary contract between two adjoining rooms. ExpectedGroundCenter
        // is expressed as gameplay-plane (X, Z) per the approved GDD blockout; door opening height is
        // an interior room-authoring detail, not a shared cross-room contract value. D5 has no entry
        // room because Final Room's exit is the escape boundary rather than another room.
        [Serializable]
        public sealed class DoorSequenceEntry
        {
            [SerializeField] private DoorId doorId;
            [SerializeField] private RoomId exitRoom;
            [SerializeField] private bool isFinal;
            [SerializeField] private RoomId entryRoom;
            [SerializeField] private Vector2 expectedGroundCenter;
            [SerializeField] private float openingWidth;

            public DoorSequenceEntry(
                DoorId doorId,
                RoomId exitRoom,
                RoomId entryRoom,
                bool isFinal,
                Vector2 expectedGroundCenter,
                float openingWidth)
            {
                this.doorId = doorId;
                this.exitRoom = exitRoom;
                this.entryRoom = entryRoom;
                this.isFinal = isFinal;
                this.expectedGroundCenter = expectedGroundCenter;
                this.openingWidth = openingWidth;
            }

            public DoorId DoorId => doorId;
            public RoomId ExitRoom => exitRoom;
            public bool IsFinal => isFinal;
            public RoomId EntryRoom => entryRoom;
            public Vector2 ExpectedGroundCenter => expectedGroundCenter;
            public float OpeningWidth => openingWidth;
        }

        [SerializeField] private RoomCatalogEntry[] rooms = Array.Empty<RoomCatalogEntry>();
        [SerializeField] private DoorSequenceEntry[] doors = Array.Empty<DoorSequenceEntry>();

        public IReadOnlyList<RoomCatalogEntry> Rooms => rooms;
        public IReadOnlyList<DoorSequenceEntry> Doors => doors;

        // NSC-069 AC-001/AC-003: canonical definition from the Vincent-approved Five-Room Spatial
        // Layout Blockout (GDD §§4-10). Room order is the fixed south-to-north forward route.
        public static RoomCatalogEntry[] CreateCanonicalRooms()
        {
            return new[]
            {
                new RoomCatalogEntry(
                    RoomId.RuinedEntry,
                    "Assets/Scenes/Rooms/RuinedEntry.unity",
                    new RoomBounds(-14f, 14f, -26f, 0f)),
                new RoomCatalogEntry(
                    RoomId.BoneArchive,
                    "Assets/Scenes/Rooms/BoneArchive.unity",
                    new RoomBounds(-12f, 12f, 0f, 20f)),
                new RoomCatalogEntry(
                    RoomId.ChapelOfAsh,
                    "Assets/Scenes/Rooms/ChapelOfAsh.unity",
                    new RoomBounds(-18f, 18f, 20f, 54f)),
                new RoomCatalogEntry(
                    RoomId.LowerVault,
                    "Assets/Scenes/Rooms/LowerVault.unity",
                    new RoomBounds(-20f, 20f, 54f, 76f)),
                new RoomCatalogEntry(
                    RoomId.FinalRoom,
                    "Assets/Scenes/Rooms/FinalRoom.unity",
                    new RoomBounds(-15f, 15f, 76f, 104f))
            };
        }

        public static DoorSequenceEntry[] CreateCanonicalDoors()
        {
            const float openingWidth = 3f;

            return new[]
            {
                new DoorSequenceEntry(
                    DoorId.D1, RoomId.RuinedEntry, RoomId.BoneArchive, false,
                    new Vector2(0f, 0f), openingWidth),
                new DoorSequenceEntry(
                    DoorId.D2, RoomId.BoneArchive, RoomId.ChapelOfAsh, false,
                    new Vector2(6f, 20f), openingWidth),
                new DoorSequenceEntry(
                    DoorId.D3, RoomId.ChapelOfAsh, RoomId.LowerVault, false,
                    new Vector2(-8f, 54f), openingWidth),
                new DoorSequenceEntry(
                    DoorId.D4, RoomId.LowerVault, RoomId.FinalRoom, false,
                    new Vector2(4f, 76f), openingWidth),
                new DoorSequenceEntry(
                    DoorId.D5, RoomId.FinalRoom, RoomId.FinalRoom, true,
                    new Vector2(0f, 104f), openingWidth)
            };
        }

        // Deterministic materialization entry point, mirroring the existing LoadOrCreate
        // persistent-asset convention already used for architectural Tile assets: repeated calls
        // reconcile the canonical definition into the same asset rather than creating duplicates.
        [MenuItem("No Safe Circle/World/Build Room Scene Catalog")]
        public static RoomSceneCatalog BuildAsset()
        {
            var existing = AssetDatabase.LoadAssetAtPath<RoomSceneCatalog>(AssetPath);
            if (existing != null)
            {
                existing.ApplyCanonicalDefinition();
                EditorUtility.SetDirty(existing);
                AssetDatabase.SaveAssetIfDirty(existing);
                return existing;
            }

            var created = CreateInstance<RoomSceneCatalog>();
            created.ApplyCanonicalDefinition();
            AssetDatabase.CreateAsset(created, AssetPath);
            EditorUtility.SetDirty(created);
            AssetDatabase.SaveAssetIfDirty(created);
            return created;
        }

        public static RoomSceneCatalog LoadOrBuildAsset()
        {
            var existing = AssetDatabase.LoadAssetAtPath<RoomSceneCatalog>(AssetPath);
            return existing != null ? existing : BuildAsset();
        }

        private void ApplyCanonicalDefinition()
        {
            rooms = CreateCanonicalRooms();
            doors = CreateCanonicalDoors();
        }

        public bool TryGetRoom(RoomId roomId, out RoomCatalogEntry entry)
        {
            foreach (var room in rooms)
            {
                if (room.RoomId != roomId) continue;
                entry = room;
                return true;
            }

            entry = null;
            return false;
        }
    }
}
