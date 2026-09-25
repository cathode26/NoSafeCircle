using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Editor
{
    // Batchmode-invocable Windows Standalone build entry point. Reads the canonical gameplay
    // scene from the NSC-037 Build Settings registration rather than a literal path, so the
    // player build follows that registration if it changes. Unlike WebGLBuilder, this command
    // does not rebuild or save the scene first: the canonical checkout must stay clean, so the
    // committed scene asset is used exactly as it already is on disk. Invoked as:
    //   Unity.exe -batchmode -quit -projectPath <repo> -executeMethod
    //     NoSafeCircle.DoorPrototype.Editor.WindowsStandaloneBuildCommand.Build -nsc-output <dir>
    public static class WindowsStandaloneBuildCommand
    {
        private const string OutputArgument = "-nsc-output";
        private const string DefaultOutputDirectory = "Build/Windows";
        private const string ExecutableFileName = "NoSafeCircle.exe";

        [MenuItem("No Safe Circle/Build Windows Standalone Player")]
        public static void Build()
        {
            string outputDirectory = ResolveOutputDirectory();
            string locationPathName = Path.Combine(outputDirectory, ExecutableFileName);
            Directory.CreateDirectory(outputDirectory);

            BuildPlayerOptions options = CreateBuildPlayerOptions(locationPathName);
            BuildReport report = BuildPipeline.BuildPlayer(options);
            BuildSummary summary = report.summary;

            if (summary.result != BuildResult.Succeeded)
            {
                // Non-zero exit so a batchmode caller can tell a failed build from a good one.
                Debug.LogError($"Windows Standalone build {summary.result} with {summary.totalErrors} " +
                    $"error(s) after {summary.totalTime}. Output: {locationPathName}");
                EditorApplication.Exit(1);
                return;
            }

            Debug.Log($"Windows Standalone build succeeded in {summary.totalTime}, " +
                $"{summary.totalSize} bytes at {locationPathName}");
        }

        // Public so tests can assert the resolved scene list and target without invoking a full
        // player build.
        public static BuildPlayerOptions CreateBuildPlayerOptions(string locationPathName)
        {
            return new BuildPlayerOptions
            {
                scenes = ResolveRegisteredScenePaths(),
                locationPathName = locationPathName,
                target = BuildTarget.StandaloneWindows64,
                targetGroup = BuildTargetGroup.Standalone,
                options = BuildOptions.None,
            };
        }

        // The NSC-037 registration, not a hard-coded scene path: the build follows whatever is
        // enabled in Build Settings if that registration changes.
        public static string[] ResolveRegisteredScenePaths()
        {
            return EditorBuildSettings.scenes
                .Where(scene => scene.enabled)
                .Select(scene => scene.path)
                .ToArray();
        }

        private static string ResolveOutputDirectory()
        {
            string[] arguments = System.Environment.GetCommandLineArgs();
            for (int index = 0; index < arguments.Length - 1; index++)
            {
                if (string.Equals(arguments[index], OutputArgument, StringComparison.Ordinal))
                {
                    string candidate = arguments[index + 1];
                    if (!string.IsNullOrWhiteSpace(candidate))
                    {
                        return candidate;
                    }
                }
            }

            return DefaultOutputDirectory;
        }
    }
}
