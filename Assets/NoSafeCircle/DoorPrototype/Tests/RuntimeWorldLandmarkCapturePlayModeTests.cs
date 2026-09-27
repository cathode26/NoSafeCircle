using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Tests
{
    /// <summary>VAL-002 review panels: each room's landmark, at review size, in the RUNTIME-BUILT
    /// world. PlayMode port of Tests/Editor/World/ComposedLandmarkCaptureTests.cs, written so the
    /// Art Director's review artifact survives the deletion of the old world's committed scenes
    /// and Assets/Scenes/DoorPrototype.unity.</summary>
    /// <remarks>
    /// <para>
    /// WHY A NEW FIXTURE RATHER THAN A REPAIR OF THE OLD ONE. The old world is dying: its per-room
    /// authoring scenes and DoorPrototype.unity go away in a later commit that this port does not
    /// make. Vincent's PropSpawner/GameBootstrap world instead builds everything at Play from
    /// prefabs and JSON catalogs (see PropSpawner.cs's own remarks), and the only committed scene
    /// left is Assets/Scenes/RuntimeWorld.unity - a near-empty bootstrap scene carrying just
    /// GameManagers. So this captures against THAT scene, once it has built, rather than against
    /// anything this port deletes.
    /// </para>
    /// <para>
    /// THE FOCUS POINT IS STILL READ FROM THE WORLD, NOT HARD-CODED, AND A MISSING LANDMARK STILL
    /// FAILS - unchanged from the source fixture's own stated reason: centring on the origin
    /// instead would produce a confident photograph of the wrong thing. Each landmark is located
    /// by its authored instance id, exactly as before - PropSpawner.cs sets
    /// <c>instance.name = placement.instance_id</c> on every prop it spawns, so the same instance
    /// ids the Art Director named are the runtime GameObject names.
    /// </para>
    /// <para>
    /// WHAT CHANGED IS THE LOOKUP PATH, NOT THE IDENTIFIER. The Edit-mode source walked the
    /// composed scene's root-level "RoomDressing" object to "&lt;Room&gt;Dressing" to the instance
    /// id. At runtime, PropSpawner's prefab (Resources/Spawners/PropSpawner.prefab) ships
    /// <c>dressingRoot: {fileID: 0}</c> (unset), so <c>PropSpawner.Spawn()</c>'s
    /// <c>root = dressingRoot != null ? dressingRoot : transform</c> resolves to the PropSpawner
    /// instance's OWN transform, and GameBootstrap.InstantiateSpawnerPrefabs names that instance
    /// after the prefab asset ("PropSpawner") and parents it under GameManagers. So the runtime
    /// path is GameManagers -&gt; "PropSpawner" -&gt; "&lt;Room&gt;Dressing" -&gt; instanceId: one
    /// extra hop through the spawner itself, in place of the old scene-root "RoomDressing" hop.
    /// </para>
    /// </remarks>
    public sealed class RuntimeWorldLandmarkCapturePlayModeTests
    {
        private const string SceneName = "RuntimeWorld";
        private const string ScenePath = "Assets/Scenes/RuntimeWorld.unity";
        private const string PropSpawnerObjectName = "PropSpawner";

        /// <summary>The landmark the Art Director named for each room, in their words. Verbatim
        /// from the source fixture's table - unchanged instance ids, unchanged output filenames.
        /// All seven instance ids independently re-confirmed present in their room's
        /// *DressingCatalog.json under Assets/NoSafeCircle/DoorPrototype/Art/Environment/
        /// RoomDressing/ as part of this port.</summary>
        private static readonly (string Room, string File, string[] Instances)[] Landmarks =
        {
            // "the D1 door with BOTH guardians" -- the two straddle the doorway, so the midpoint
            // of the pair frames the door and both statues together.
            ("RuinedEntry", "nsc-079-ruined-entry-landmark.png",
                new[] { "D1-WEST-guardian-intact-01", "D1-EAST-guardian-fallen-01" }),
            ("BoneArchive", "nsc-080-bone-archive-landmark.png",
                new[] { "NORTH-STRIP-landmark-01" }),
            // "the altar and bell frame at the aisle's north end" -- both, so both are framed.
            ("ChapelOfAsh", "nsc-081-chapel-of-ash-landmark.png",
                new[] { "RITUAL-altar-01", "NORTH-landmark-01" }),
            ("LowerVault", "nsc-082-lower-vault-landmark.png",
                new[] { "LV-C1-landmark-01" }),
            ("FinalRoom", "nsc-083-final-room-landmark.png",
                new[] { "FR1-throne-01" }),
        };

        // Carries the pre-capture scene bytes from the test body to UnityTearDown, which is the
        // only hook NUnit guarantees runs even when an Assert inside the test throws partway.
        // Null means "never read" - either NSC_LANDMARK_CAPTURE_OUTPUT was unset (Assert.Ignore
        // fired before any read) or the repository-output guard failed first - and in both cases
        // there is nothing to compare, so TearDown must not report a spurious mismatch.
        private byte[] _sceneBytesBeforeCapture;

        // Same purpose and wording as FiveRoomDoorSequencePlayModeTests.WaitForWorldBuilt().
        // Duplicated rather than shared, matching that file's own stated convention (it duplicates
        // its own UnloadRuntimeWorldSceneWithoutSaving helper into its nested
        // FixedSquadSpawnPositionTests fixture for the identical reason) so this fixture carries no
        // compile-time dependency on that class's private members.
        private static IEnumerator WaitForWorldBuilt()
        {
            yield return null;
            GameObject managers = GameObject.Find("GameManagers");
            Assert.IsNotNull(managers,
                "RuntimeWorld.unity carries no GameManagers object, so nothing builds the world.");
            var bootstrap = managers.GetComponent<GameBootstrap>();
            Assert.IsNotNull(bootstrap, "GameManagers carries no GameBootstrap.");

            yield return null;
            yield return null;

            Assert.IsTrue(bootstrap.HasBuilt,
                "GameBootstrap had not built after three frames, so every assertion below would "
                + "fail on an empty world rather than on the thing under test. SpawnedCount = "
                + bootstrap.SpawnedCount + ".");
        }

        [Explicit("Set NSC_LANDMARK_CAPTURE_OUTPUT to shoot the VAL-002 landmark panels.")]
        [UnityTest]
        public IEnumerator CaptureComposedLandmarkPanels()
        {
            string output = Environment.GetEnvironmentVariable("NSC_LANDMARK_CAPTURE_OUTPUT");
            if (string.IsNullOrWhiteSpace(output))
            {
                Assert.Ignore("Set NSC_LANDMARK_CAPTURE_OUTPUT to run the explicit landmark capture.");
            }

            string outputFull = Path.GetFullPath(output);
            string repository = Path.GetFullPath(Directory.GetCurrentDirectory())
                .TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            Assert.IsFalse(outputFull.StartsWith(repository, StringComparison.OrdinalIgnoreCase),
                "Write capture output OUTSIDE the repository so a run cannot dirty it.");
            Directory.CreateDirectory(outputFull);

            // PROPERTY 3, SUBSTITUTED: read here, compared in TearDown() below, which is the only
            // hook guaranteed to run. See the comment on the comparison itself for what changed.
            _sceneBytesBeforeCapture = File.ReadAllBytes(ScenePath);

            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();

            GameObject cameraObject = null;
            RenderTexture target = null;
            try
            {
                GameObject managers = GameObject.Find("GameManagers");
                Assert.IsNotNull(managers,
                    "RuntimeWorld.unity carries no GameManagers object, so nothing builds the world.");

                Transform propSpawner = managers.transform.Find(PropSpawnerObjectName);
                Assert.IsNotNull(propSpawner,
                    "GameManagers has no '" + PropSpawnerObjectName + "' child, so PropSpawner's "
                    + "prefab was not instantiated and there is no dressing to photograph.");

                var rotation = Quaternion.Euler(30f, -45f, 0f);
                cameraObject = new GameObject("LandmarkCaptureCamera", typeof(Camera));
                Camera camera = cameraObject.GetComponent<Camera>();
                camera.orthographic = true;
                // The Art Director's review size. Not a parameter: this is the size VAL-002 is
                // judged at, and a panel shot at a different one answers a different question.
                camera.orthographicSize = 8f;
                camera.transform.rotation = rotation;

                target = new RenderTexture(1600, 1200, 24);
                camera.targetTexture = target;

                foreach (var landmark in Landmarks)
                {
                    Transform dressed = propSpawner.Find(landmark.Room + "Dressing");
                    Assert.IsNotNull(dressed,
                        landmark.Room + " has no dressing under PropSpawner in the runtime world.");

                    var positions = new List<Vector3>();
                    foreach (string instanceId in landmark.Instances)
                    {
                        Transform prop = dressed.Find(instanceId);
                        Assert.IsNotNull(prop,
                            landmark.Room + ": landmark '" + instanceId + "' is not in the runtime " +
                            "world. Centring on the origin instead would produce a confident " +
                            "photograph of the wrong thing, so this fails.");
                        positions.Add(prop.position);
                    }

                    Vector3 focus = Vector3.zero;
                    foreach (Vector3 position in positions) focus += position;
                    focus /= positions.Count;
                    focus.y = 0f;

                    cameraObject.transform.position = focus + rotation * Vector3.back * 51.96f;
                    camera.Render();

                    RenderTexture previous = RenderTexture.active;
                    RenderTexture.active = target;
                    var shot = new Texture2D(target.width, target.height, TextureFormat.RGB24, false);
                    shot.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0);
                    shot.Apply();
                    RenderTexture.active = previous;

                    File.WriteAllBytes(Path.Combine(outputFull, landmark.File), shot.EncodeToPNG());
                    // Object.Destroy, not DestroyImmediate: this runs in Play mode, where deferred
                    // destruction is the normal idiom and DestroyImmediate is the thing to avoid.
                    // The PNG bytes are already extracted above, so the one-frame deferral costs
                    // nothing here.
                    UnityEngine.Object.Destroy(shot);

                    Debug.Log($"{landmark.Room}: landmark panel at {focus} -> {landmark.File}");
                }
            }
            finally
            {
                if (cameraObject != null) UnityEngine.Object.Destroy(cameraObject);
                if (target != null) UnityEngine.Object.Destroy(target);
            }
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            yield return UnloadRuntimeWorldSceneWithoutSaving();

            if (_sceneBytesBeforeCapture != null)
            {
                // PROPERTY 3, THE BYTE-IDENTITY ASSERTION - SUBSTITUTED, NOT DROPPED.
                //
                // The Edit-mode source (ComposedLandmarkCaptureTests.cs:141) asserted
                // File.ReadAllBytes(ScenePath) unchanged around an
                // EditorSceneManager.OpenScene/CloseScene(saveChanges:false) pair on the COMPOSED
                // scene it opened FOR EDITING - the fleet's never-dirty-the-repository rule encoded
                // as an assertion, because OpenScene is exactly the kind of operation that can leave
                // a scene dirty if a later change forgets to guard the close.
                //
                // PlayMode never opens a committed scene for editing: SceneManager.LoadSceneAsync
                // loads RuntimeWorld.unity for SIMULATION, Unity does not write Play-mode state
                // back to the scene asset on disk, and the unload above never saves. So the exact
                // OpenScene/CloseScene risk the source guarded against does not exist on this path.
                // The Art Director's instruction was to say so rather than dropping the guard
                // silently, and to assert the equivalent if PlayMode can dirty anything.
                //
                // THE SUBSTITUTION: RuntimeWorld.unity is the scene PlayMode actually loads for
                // this capture, so its on-disk bytes are read before the load (in the test body
                // above) and compared here, after the unload. This guards a DIFFERENT risk than the
                // original - not OpenScene/CloseScene, which never runs here, but an editor
                // autosave, a domain reload, or a future change that opens this scene for editing
                // mid-capture. It is the equivalent the instruction asked for, not the same check.
                CollectionAssert.AreEqual(_sceneBytesBeforeCapture, File.ReadAllBytes(ScenePath),
                    "Photographing the runtime world must not modify the committed RuntimeWorld " +
                    "scene on disk.");
                _sceneBytesBeforeCapture = null;
            }
        }

        // Byte-for-byte identical in intent to
        // FiveRoomDoorSequencePlayModeTests.UnloadRuntimeWorldSceneWithoutSaving - duplicated
        // rather than shared, per that file's own stated convention. MUST be awaited: an unawaited
        // SceneManager.UnloadSceneAsync lands its unload asynchronously inside whichever fixture
        // runs next, per that file's PlayModeSceneCleanupConventionTests precedent.
        private static IEnumerator UnloadRuntimeWorldSceneWithoutSaving()
        {
            var scene = SceneManager.GetSceneByName(SceneName);
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            var cleanupScene = SceneManager.CreateScene("RuntimeWorldLandmarkCaptureTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }
    }
}
