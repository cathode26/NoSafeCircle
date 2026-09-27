using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// <summary>Finds the horizontal floor line through the starting camera's view centre.</summary>
    public static class TitleScreenChaseLane
    {
        private const float EdgeInset = 1.5f;
        private const float MinX = RuinedEntryLayout.MinimumX + EdgeInset;
        private const float MaxX = RuinedEntryLayout.MaximumX - EdgeInset;
        private const float MinZ = RuinedEntryLayout.MinimumZ + EdgeInset;
        private const float MaxZ = RuinedEntryLayout.MaximumZ - EdgeInset;

        public static bool TryGetFloorSegment(Camera camera, out Vector3 start, out Vector3 end)
        {
            start = default;
            end = default;
            if (camera == null)
            {
                return false;
            }

            Ray centerRay = camera.ViewportPointToRay(new Vector3(0.5f, 0.5f, 0f));
            Plane floor = new Plane(Vector3.up, Vector3.zero);
            if (!floor.Raycast(centerRay, out float distance))
            {
                return false;
            }

            Vector3 center = centerRay.GetPoint(distance);
            Vector3 horizontal = Vector3.ProjectOnPlane(camera.transform.right, Vector3.up).normalized;
            if (Mathf.Abs(horizontal.x) < 0.001f || Mathf.Abs(horizontal.z) < 0.001f)
            {
                return false;
            }

            float lower = float.NegativeInfinity;
            float upper = float.PositiveInfinity;
            ClipAxis(center.x, horizontal.x, MinX, MaxX, ref lower, ref upper);
            ClipAxis(center.z, horizontal.z, MinZ, MaxZ, ref lower, ref upper);
            if (lower >= upper)
            {
                return false;
            }

            start = center + horizontal * lower;
            end = center + horizontal * upper;
            start.y = 0f;
            end.y = 0f;
            return true;
        }

        private static void ClipAxis(float center, float direction, float minimum, float maximum,
            ref float lower, ref float upper)
        {
            float first = (minimum - center) / direction;
            float second = (maximum - center) / direction;
            lower = Mathf.Max(lower, Mathf.Min(first, second));
            upper = Mathf.Min(upper, Mathf.Max(first, second));
        }
    }
}
