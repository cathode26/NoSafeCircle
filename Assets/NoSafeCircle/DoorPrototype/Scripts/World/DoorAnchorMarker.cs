using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World
{
    // Identifies one door opening authored inside a room's DoorAnchors container. Keeping this
    // MonoBehaviour in its matching script asset gives serialized room scenes one stable GUID;
    // scene-local MonoScript records are not reliable after a fresh Editor reload.
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
