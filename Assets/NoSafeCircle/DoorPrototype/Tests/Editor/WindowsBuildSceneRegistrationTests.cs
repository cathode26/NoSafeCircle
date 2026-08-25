using System.Linq;
using NUnit.Framework;
using UnityEditor;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    // Contract mapping: NSC-037 AC-001, AC-002, AC-003.
    // Reads only live EditorBuildSettings/EditorUserBuildSettings Editor API state; performs no writes or scene loads,
    // so it cannot dirty ProjectSettings/EditorBuildSettings.asset or any tracked asset.
    public class WindowsBuildSceneRegistrationTests
    {
        private const string CanonicalScenePath = "Assets/Scenes/DoorPrototype.unity";
        private const string NonCanonicalScenePath = "Assets/Scenes/SampleScene.unity";

        [Test]
        public void CanonicalGameplayScene_IsRegisteredAndEnabledInBuildSettings()
        {
            var scenes = EditorBuildSettings.scenes;
            var canonicalEntry = scenes.FirstOrDefault(scene => scene.path == CanonicalScenePath);

            Assert.IsNotNull(canonicalEntry,
                $"Expected {CanonicalScenePath} to be registered in Unity Build Settings (AC-001).");
            Assert.IsTrue(canonicalEntry.enabled,
                $"Expected {CanonicalScenePath} to be enabled in Unity Build Settings (AC-001).");
        }

        [Test]
        public void CanonicalGameplayScene_BuildSettingsGuidMatchesSceneAssetGuid()
        {
            var scenes = EditorBuildSettings.scenes;
            var canonicalEntry = scenes.FirstOrDefault(scene => scene.path == CanonicalScenePath);
            Assert.IsNotNull(canonicalEntry,
                $"Expected {CanonicalScenePath} to be registered in Unity Build Settings (AC-001).");

            var assetGuid = AssetDatabase.AssetPathToGUID(CanonicalScenePath);
            Assert.AreEqual(assetGuid, canonicalEntry.guid.ToString(),
                "The registered Build Settings scene GUID must match the canonical scene asset's own GUID, " +
                "so the entry does not silently drift from the actual scene asset (AC-001).");
        }

        [Test]
        public void NonCanonicalSampleScene_IsNotRegisteredInBuildSettings()
        {
            var scenes = EditorBuildSettings.scenes;
            var sampleSceneEntry = scenes.FirstOrDefault(scene => scene.path == NonCanonicalScenePath);

            Assert.IsNull(sampleSceneEntry,
                $"{NonCanonicalScenePath} is non-canonical and must not be registered as a substitute for the " +
                "canonical gameplay scene (AC-003).");
        }

        [Test]
        public void ActiveBuildTarget_IsWindowsStandalone()
        {
            var activeTarget = EditorUserBuildSettings.activeBuildTarget;

            Assert.That(activeTarget,
                Is.EqualTo(BuildTarget.StandaloneWindows64).Or.EqualTo(BuildTarget.StandaloneWindows),
                "Windows Standalone must be configured as the active/target build platform (AC-002). " +
                "Unity's active build target is local Editor/UserSettings state that is intentionally excluded " +
                "from version control (see .gitignore), so this validation run must itself be invoked against an " +
                "Editor session already targeting Windows Standalone (for example via `-buildTarget " +
                "StandaloneWindows64`) for this assertion to be meaningful.");
        }
    }
}
