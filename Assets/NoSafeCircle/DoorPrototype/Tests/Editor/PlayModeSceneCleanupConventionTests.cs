using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>Requires every PlayMode fixture that loads a scene Single to restore one after.</summary>
    /// <remarks>
    /// A fixture that calls SceneManager.LoadScene(..., LoadSceneMode.Single) REPLACES the active
    /// scene and leaves it loaded for every fixture that runs after it in the same PlayMode
    /// session. On 2026-09-23 DoorBreachFeedbackPlayModeTests did exactly that with the composed
    /// five-room floor, and two fixtures in completely different components failed as a result:
    /// DoorEnemyPassability baked its NavMesh with five rooms of walls in it, and
    /// DoorInteractionFeedbackHover raycast its camera into another room. Eight tests were red,
    /// one scene unload fixed seven of them, and nothing in either failing component was wrong.
    /// <para>
    /// SEVEN OF THE EIGHT FIXTURES ALREADY DID THE RIGHT THING. The pattern was followed by
    /// convention and enforced on nobody, so a ninth fixture reintroduces the defect and the only
    /// symptom is unrelated tests failing somewhere else. That is what this test exists to stop --
    /// it converts a convention into a guard.
    /// </para>
    /// <para>
    /// This reads SOURCE rather than running anything, which is crude and is the point: the defect
    /// it guards against is invisible at runtime until another fixture happens to fail.
    /// </para>
    /// </remarks>
    public sealed class PlayModeSceneCleanupConventionTests
    {
        private const string PlayModeTestRoot = "Assets/NoSafeCircle/DoorPrototype/Tests";
        private const string SingleLoadMarker = "LoadSceneMode.Single";
        private const string UnloadMarker = "UnloadSceneAsync";

        // Measured on 2026-09-23: eight fixtures load a scene in Single mode. If a refactor drops
        // that to zero this test would pass while checking nothing, so require the haystack.
        private const int MinimumExpectedSingleLoaders = 5;

        [Test]
        public void EveryPlayModeFixtureThatLoadsASceneSingleAlsoRestoresOne()
        {
            Assert.IsTrue(Directory.Exists(PlayModeTestRoot), PlayModeTestRoot);

            string[] fixtures = Directory
                .GetFiles(PlayModeTestRoot, "*PlayModeTests.cs", SearchOption.TopDirectoryOnly)
                .OrderBy(path => path, StringComparer.Ordinal)
                .ToArray();
            Assert.Greater(fixtures.Length, 0, "Found no PlayMode fixtures to check under " + PlayModeTestRoot);

            var singleLoaders = new List<string>();
            var offenders = new List<string>();
            foreach (string path in fixtures)
            {
                string source = File.ReadAllText(path);
                if (source.IndexOf(SingleLoadMarker, StringComparison.Ordinal) < 0)
                {
                    continue;
                }

                singleLoaders.Add(Path.GetFileName(path));
                if (source.IndexOf(UnloadMarker, StringComparison.Ordinal) < 0)
                {
                    offenders.Add(Path.GetFileName(path));
                }
            }

            // A sweep that reports zero is only as good as its haystack. If this drops below the
            // measured population, the query broke rather than the codebase improving.
            Assert.GreaterOrEqual(singleLoaders.Count, MinimumExpectedSingleLoaders,
                "Only " + singleLoaders.Count + " fixtures matched '" + SingleLoadMarker +
                "'. Eight did when this guard was written, so suspect the query before the codebase.");

            CollectionAssert.IsEmpty(offenders,
                "These PlayMode fixtures load a scene with " + SingleLoadMarker + " and never call " +
                UnloadMarker + ", so they leave that scene loaded for every fixture that runs after " +
                "them: " + string.Join(", ", offenders) + ". Copy the [UnityTearDown] from " +
                "FiveRoomDoorSequencePlayModeTests: create an empty scene, make it active, then " +
                "unload the loaded one.");
        }
    }
}
