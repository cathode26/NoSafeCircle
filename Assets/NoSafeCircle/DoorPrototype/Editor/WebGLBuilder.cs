using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Editor
{
    // Batchmode-invocable WebGL build entry point. Ships RuntimeWorld.unity, which builds its
    // world AT PLAY from prefabs, then writes a WebGL player to a caller-supplied output
    // directory. Invoked as:
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

            // NO PRE-BUILD STEP, AND THAT IS THE POINT OF THE NEW WORLD. RuntimeWorld.unity holds
            // three roots - GameManagers, Main Camera, Directional Light - and GameBootstrap
            // instantiates everything else at Play from prefabs it discovers in
            // Resources/Spawners. There is nothing to bake, so there is nothing that can be stale.
            //
            // WHAT THIS REPLACED, AND WHY IT MATTERED MORE THAN IT LOOKED. This shipped
            // Assets/Scenes/DoorPrototype.unity and called DoorPrototypeSceneBuilder.Build() first,
            // so the PLAYER BUILD WAS THE OLD COMPOSED WORLD even after the instantiate path landed
            // on main and was played in the editor. Nothing but tests referenced RuntimeWorld.unity,
            // so the new world could be complete, merged and demonstrated while every build anyone
            // actually played contained none of it.
            //
            // Content reaches the player through Resources, not Addressables - the spawn path has
            // zero Addressables calls, and Resources folders are included in a build by
            // construction - so no content-build step belongs here. If a lane later loads content
            // through Addressables it must add that step, and it must not use WaitForCompletion to
            // avoid it: standard 7.2 forbids that on WebGL.
            string[] scenes = { "Assets/Scenes/RuntimeWorld.unity" };
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
