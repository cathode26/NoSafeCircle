using NoSafeCircle.DoorPrototype.Hud;
using UnityEditor;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Editor
{
    public static class MobileControlsPreviewMenu
    {
        private const string MenuPath = "No Safe Circle/Preview/Force Mobile Controls";
        private const string Preference = "NoSafeCircle.ForceMobileControls";

        [InitializeOnLoadMethod]
        private static void LoadPreference()
        {
            MobileGameplayControls.EditorPreviewEnabled = EditorPrefs.GetBool(Preference, false);
        }

        [MenuItem(MenuPath)]
        public static void Toggle()
        {
            bool enabled = !MobileGameplayControls.EditorPreviewEnabled;
            MobileGameplayControls.EditorPreviewEnabled = enabled;
            EditorPrefs.SetBool(Preference, enabled);
            EditorApplication.QueuePlayerLoopUpdate();
            Debug.Log(enabled ? "Mobile preview enabled. Use a landscape Game View; hold Ctrl to stand/fire or Shift to move/fire, then click to aim. You can also hold and slide between the buttons."
                : "Mobile preview disabled.");
        }

        [MenuItem(MenuPath, true)]
        private static bool Validate()
        {
            Menu.SetChecked(MenuPath, MobileGameplayControls.EditorPreviewEnabled);
            return true;
        }
    }
}
