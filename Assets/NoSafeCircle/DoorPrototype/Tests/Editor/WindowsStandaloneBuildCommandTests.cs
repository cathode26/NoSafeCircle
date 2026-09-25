using System.Linq;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Editor;
using UnityEditor;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    // Contract mapping: NSC-113 AC-001, VAL-001.
    // Reads only live EditorBuildSettings state and calls the command's public, non-mutating
    // helper methods (ResolveRegisteredScenePaths, CreateBuildPlayerOptions); performs no writes,
    // scene loads, or player builds, so it cannot dirty ProjectSettings/EditorBuildSettings.asset,
    // any tracked asset, or produce build output.
    public class WindowsStandaloneBuildCommandTests
    {
        private const string CanonicalScenePath = "Assets/Scenes/DoorPrototype.unity";
        private const string SampleLocationPathName = "Build/Windows/NoSafeCircle.exe";

        [Test]
        public void ResolveRegisteredScenePaths_MatchesLiveEnabledBuildSettingsScenes()
        {
            string[] expected = EditorBuildSettings.scenes
                .Where(scene => scene.enabled)
                .Select(scene => scene.path)
                .ToArray();

            string[] actual = WindowsStandaloneBuildCommand.ResolveRegisteredScenePaths();

            CollectionAssert.AreEqual(expected, actual,
                "The build must resolve scenes from the live NSC-037 Build Settings registration, not a " +
                "literal path, so it stays correct if that registration changes (AC-001).");
        }

        [Test]
        public void ResolveRegisteredScenePaths_IncludesTheCanonicalGameplayScene()
        {
            string[] actual = WindowsStandaloneBuildCommand.ResolveRegisteredScenePaths();

            CollectionAssert.Contains(actual, CanonicalScenePath,
                $"Expected the NSC-037-registered canonical gameplay scene {CanonicalScenePath} to be resolved " +
                "for the Windows Standalone build (AC-001).");
        }

        [Test]
        public void CreateBuildPlayerOptions_UsesTheRegisteredScenesRatherThanAHardcodedList()
        {
            BuildPlayerOptions options = WindowsStandaloneBuildCommand.CreateBuildPlayerOptions(SampleLocationPathName);

            CollectionAssert.AreEqual(WindowsStandaloneBuildCommand.ResolveRegisteredScenePaths(), options.scenes,
                "The scenes passed to BuildPipeline.BuildPlayer must come from the same NSC-037 registration " +
                "query the command resolves elsewhere, not a separate literal scene list (AC-001).");
        }

        [Test]
        public void CreateBuildPlayerOptions_TargetsStandaloneWindows64()
        {
            BuildPlayerOptions options = WindowsStandaloneBuildCommand.CreateBuildPlayerOptions(SampleLocationPathName);

            Assert.AreEqual(BuildTarget.StandaloneWindows64, options.target,
                "The Windows Standalone build command must target StandaloneWindows64, the target NSC-037 " +
                "already configures (AC-001).");
            Assert.AreEqual(BuildTargetGroup.Standalone, options.targetGroup,
                "The Windows Standalone build command must use the Standalone target group.");
        }

        [Test]
        public void CreateBuildPlayerOptions_PreservesTheSuppliedOutputLocation()
        {
            BuildPlayerOptions options = WindowsStandaloneBuildCommand.CreateBuildPlayerOptions(SampleLocationPathName);

            Assert.AreEqual(SampleLocationPathName, options.locationPathName,
                "The resolved output path must be passed through to the build options unchanged so the " +
                "command's reported output path matches what actually gets built (AC-002).");
        }

        [Test]
        public void ResolveRegisteredScenePaths_FollowsAChangedRegistrationRatherThanALiteralPath()
        {
            EditorBuildSettingsScene[] originalScenes = EditorBuildSettings.scenes;

            try
            {
                var swappedScenes = new[]
                {
                    new EditorBuildSettingsScene("Assets/Scenes/DoorPrototypeSwapped.unity", true),
                };
                EditorBuildSettings.scenes = swappedScenes;

                string[] resolved = WindowsStandaloneBuildCommand.ResolveRegisteredScenePaths();

                CollectionAssert.AreEqual(new[] { "Assets/Scenes/DoorPrototypeSwapped.unity" }, resolved,
                    "Changing the EditorBuildSettings registration must change the resolved scene list; a " +
                    "hard-coded literal path would still return the original canonical scene here (AC-001, VAL-001).");
                CollectionAssert.DoesNotContain(resolved, CanonicalScenePath,
                    "The resolved scenes must reflect the swapped registration, not the previously registered " +
                    "canonical scene (AC-001, VAL-001).");

                BuildPlayerOptions options = WindowsStandaloneBuildCommand.CreateBuildPlayerOptions(SampleLocationPathName);

                CollectionAssert.AreEqual(new[] { "Assets/Scenes/DoorPrototypeSwapped.unity" }, options.scenes,
                    "CreateBuildPlayerOptions must pass through the live registration, so it also follows the " +
                    "swapped scene set rather than a literal path (AC-001, VAL-001).");
            }
            finally
            {
                EditorBuildSettings.scenes = originalScenes;
            }

            CollectionAssert.AreEqual(originalScenes.Select(scene => scene.path).ToArray(),
                EditorBuildSettings.scenes.Select(scene => scene.path).ToArray(),
                "The live NSC-037 Build Settings registration must be restored exactly so the test leaves no " +
                "dirtied EditorBuildSettings state behind (AC-003).");
        }
    }
}
