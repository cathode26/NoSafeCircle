using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    // Keeps the fixed isometric camera framing the player by translating the camera to
    // track the target's position every frame. Rotation is never modified here, so the
    // camera keeps its fixed isometric orientation and never rotates.
    [RequireComponent(typeof(Camera))]
    public class IsometricCameraFollow : MonoBehaviour
    {
        [SerializeField] private Transform target;
        [SerializeField] private Vector3 offset;

        // Wires the follow target and captures the current camera-to-target offset so later
        // frames preserve whatever framing the caller already set up (e.g. the scene
        // builder's initial isometric placement). Called explicitly instead of doing this in
        // Awake, since AddComponent invokes Awake immediately - before a caller has a chance
        // to assign the target - which would otherwise capture a zero offset.
        public void Initialize(Transform followTarget)
        {
            target = followTarget;
            offset = target != null ? transform.position - target.position : Vector3.zero;
        }

        private void LateUpdate()
        {
            if (target == null) return;

            transform.position = target.position + offset;
        }
    }
}
