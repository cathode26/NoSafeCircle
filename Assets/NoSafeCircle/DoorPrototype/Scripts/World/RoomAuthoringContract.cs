using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World
{
    // NSC-069 AC-001/AC-002: the five stable room identities. Order is the fixed south-to-north
    // forward route from the approved GDD blockout and is authoritative for door-sequence
    // validation; it must not be reordered without a reviewed GDD/design revision.
    public enum RoomId
    {
        RuinedEntry,
        BoneArchive,
        ChapelOfAsh,
        LowerVault,
        FinalRoom
    }

    // NSC-069 AC-003: the five sealed-door shared boundaries from the approved blockout.
    public enum DoorId
    {
        D1,
        D2,
        D3,
        D4,
        D5
    }

    // Exit marks the door anchor authored by the room before a shared boundary; Entry marks the
    // matching anchor authored by the room after it. D5 has only an Exit anchor because Final
    // Room's exit is the escape boundary rather than another room.
    public enum DoorAnchorRole
    {
        Exit,
        Entry
    }

    // NSC-069 AC-002: the exact child categories every room authoring root separates. Authoring
    // content is Editor-only and is never cloned into composed output.
    public enum RoomContentCategory
    {
        Visuals,
        GameplayGeometry,
        DoorAnchors,
        Authoring
    }

    // Identifies one of the Visuals/GameplayGeometry/DoorAnchors/Authoring children directly
    // under a room's Room_<RoomId> authoring root, so RoomSceneComposer can locate
    // composition-eligible content without depending on fragile hierarchy name matching alone.
    [DisallowMultipleComponent]
    public sealed class RoomContentMarker : MonoBehaviour
    {
        [SerializeField] private RoomId roomId;
        [SerializeField] private RoomContentCategory category;

        public RoomId RoomId => roomId;
        public RoomContentCategory Category => category;
    }

    // Identifies one door opening authored inside a room's DoorAnchors container. D1-D4 shared
    // boundaries carry one matching Exit marker from the room before the boundary and one
    // matching Entry marker from the room after it; D5 carries only an Exit marker.
    [DisallowMultipleComponent]
    public sealed class DoorAnchorMarker : MonoBehaviour
    {
        [SerializeField] private RoomId roomId;
        [SerializeField] private DoorId doorId;
        [SerializeField] private DoorAnchorRole role;
        [SerializeField] private float openingWidth = 3f;

        public RoomId RoomId => roomId;
        public DoorId DoorId => doorId;
        public DoorAnchorRole Role => role;
        public float OpeningWidth => openingWidth;
    }
}
