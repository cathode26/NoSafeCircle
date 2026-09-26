using System.Reflection;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Hud
{
    /// <summary>
    /// INTERIM. Writes a private serialized field on another component by reflection, so the HUD can
    /// hand the runtime-spawned player to <see cref="WizardGameEntryController"/>, which has no public
    /// way to receive it.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THIS FILE IS SCHEDULED TO DIE; IT IS NOT THE DESIGN. WizardGameEntryController keeps the player
    /// in private [SerializeField] fields with no setter. Under the bake, the editor builder wrote those
    /// fields with SerializedObject at edit time; under instantiate-everything the player does not exist
    /// until Play, so the write has to happen at runtime, and the only runtime way into a private field
    /// is this. It retires the day that file (declared by NSC-068; RESOURCE_GROUPS.yaml also lists
    /// NSC-008, NSC-009, NSC-112, NSC-118 on it) gains
    ///     public void Bind(WizardAnimationController wizard, Transform player,
    ///                      PlayerMovement movement, PlayerInteractionController interaction)
    /// - at which point <see cref="HudBindings"/> calls that instead and this file is deleted. It is the
    /// same mechanism DoorPrototypeGlobalSceneBuilder.SetPrivateField used at edit time, moved to runtime
    /// and confined to ONE place so the next reader can find every use of it with one grep.
    /// </para>
    /// <para>
    /// IT FAILS LOUDLY. A renamed field in the target class would otherwise make the HUD come up silently
    /// unbound: the title flow would confirm a wizard and nothing would happen, with no line in the
    /// console saying why. Every failure here logs an error naming the type, the field and the task that
    /// owns the fix, and returns false so the caller can refuse to leave a half-bound HUD in the scene.
    /// </para>
    /// </remarks>
    public static class HudReflectionBinder
    {
        /// <summary>The seam whose arrival deletes this file. Named in every error so the reader who
        /// hits one knows it is scheduled work, not a design to preserve.</summary>
        public const string RetiredBy = "NSC-068 (a public Bind on WizardGameEntryController)";

        /// <summary>
        /// Sets <paramref name="fieldName"/> on <paramref name="target"/>. False, with an error that names
        /// what was wrong, if the field does not exist or cannot hold <paramref name="value"/>.
        /// </summary>
        public static bool TrySetPrivate(Object target, string fieldName, object value)
        {
            if (target == null)
            {
                Debug.LogError($"{nameof(HudReflectionBinder)}: no target to set '{fieldName}' on.");
                return false;
            }

            FieldInfo field = target.GetType().GetField(fieldName,
                BindingFlags.NonPublic | BindingFlags.Instance);

            if (field == null)
            {
                Debug.LogError($"{nameof(HudReflectionBinder)}: {target.GetType().Name} has no private "
                    + $"field '{fieldName}'. The HUD sets that field by reflection until {RetiredBy} lands, "
                    + "so the field was renamed or removed and the HUD cannot bind the player. It will not "
                    + "be created rather than come up unbound.", target);
                return false;
            }

            if (value != null && !field.FieldType.IsInstanceOfType(value))
            {
                Debug.LogError($"{nameof(HudReflectionBinder)}: {target.GetType().Name}.{fieldName} is a "
                    + $"{field.FieldType.Name} and cannot hold a {value.GetType().Name}. The field changed "
                    + $"type; see {RetiredBy}.", target);
                return false;
            }

            field.SetValue(target, value);
            return true;
        }
    }
}
