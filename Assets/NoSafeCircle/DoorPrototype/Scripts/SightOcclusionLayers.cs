using UnityEngine;

namespace NoSafeCircle.DoorPrototype
{
    /// One shared home for the chest-height sample offset and the LowDressing exclusion used by
    /// every sight and projectile query in the game, so the wizard's fireball, the enemies'
    /// sight checks and the enemies' ranged attacks can never drift apart on what counts as
    /// cover. Knee-high dressing props sit on the LowDressing layer
    /// (ProjectSettings/TagManager.asset, layer index 8): their colliders still block movement
    /// unchanged, but a sight or projectile query must never stop on them. Landmark-scale props
    /// at or above eye height are left on the Default layer and keep blocking both.
    public static class SightOcclusionLayers
    {
        /// Must match the layer name at ProjectSettings/TagManager.asset index 8.
        public const string LowDressingLayerName = "LowDressing";

        /// Chest-height sample offset added to a Transform's position for every sight/projectile
        /// line in the game. Unchanged from the pre-existing per-site idiom (Vector3.up) -
        /// centralized here only so every site reads the same value instead of repeating it.
        public static readonly Vector3 EyeOffset = Vector3.up;

        private static int cachedLowDressingBit = int.MinValue;

        /// baseMask with the LowDressing layer's bit cleared. If the layer is not defined (a
        /// misconfigured project), baseMask is returned unchanged rather than throwing, so sight
        /// and projectiles fail closed to today's behaviour instead of erroring.
        public static int ExcludeLowDressing(int baseMask)
        {
            return baseMask & LowDressingExclusionMask;
        }

        private static int LowDressingExclusionMask
        {
            get
            {
                if (cachedLowDressingBit == int.MinValue)
                {
                    int layer = LayerMask.NameToLayer(LowDressingLayerName);
                    cachedLowDressingBit = layer >= 0 ? ~(1 << layer) : ~0;
                }

                return cachedLowDressingBit;
            }
        }
    }
}
