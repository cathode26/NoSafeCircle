using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Editor
{
    // Batchmode-invocable WebGL build entry point. Rebuilds the canonical scene first so the
    // player build always matches the committed builder, then writes a WebGL player to a
    // caller-supplied output directory. Invoked as:
    //   Unity.exe -batchmode -quit -projectPath <repo> -executeMethod
    //     NoSafeCircle.DoorPrototype.Editor.WebGLBuilder.BuildFinal -nsc-output <dir>
    internal static class WebGLBuilder
    {
        private const string OutputArgument = "-nsc-output";
        private const string DefaultOutputDirectory = "Build/WebGL";

        [MenuItem("No Safe Circle/Build WebGL Player")]
        public static void BuildFinal()
        {
            string outputDirectory = ResolveOutputDirectory();

            // The enemy and every other authored object come from the scene builder, so rebuild
            // and save before packaging rather than shipping whatever was last left on disk.
            DoorPrototypeSceneBuilder.Build();

            string[] scenes = { "Assets/Scenes/DoorPrototype.unity" };
            Directory.CreateDirectory(outputDirectory);

            var options = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = outputDirectory,
                target = BuildTarget.WebGL,
                targetGroup = BuildTargetGroup.WebGL,
                options = BuildOptions.None,
            };

            BuildReport report = BuildPipeline.BuildPlayer(options);
            BuildSummary summary = report.summary;

            if (summary.result != BuildResult.Succeeded)
            {
                // Non-zero exit so a batchmode caller can tell a failed build from a good one.
                Debug.LogError($"WebGL build {summary.result} with {summary.totalErrors} error(s) " +
                    $"after {summary.totalTime}. Output: {outputDirectory}");
                EditorApplication.Exit(1);
                return;
            }

            Debug.Log($"WebGL build succeeded in {summary.totalTime}, " +
                $"{summary.totalSize} bytes at {outputDirectory}");
        }

        private static string ResolveOutputDirectory()
        {
            string[] arguments = Environment.GetCommandLineArgs();
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
