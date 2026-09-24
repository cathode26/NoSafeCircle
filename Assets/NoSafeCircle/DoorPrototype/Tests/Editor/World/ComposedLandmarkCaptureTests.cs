using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    /// <summary>VAL-002 review panels: each room's landmark, at review size, in the SHIPPED scene.</summary>
    /// <remarks>
    /// WHY THIS EXISTS RATHER THAN REUSING THE ROOM CAPTURES. The per-room dressing captures open
    /// the ROOM AUTHORING scenes, whose floors render with holes; the composed scene's floor does
    /// not. The Art Director declined to certify VAL-002 against the authoring frames and was right
    /// to -- they do not ship. These shots come from Assets/Scenes/DoorPrototype.unity, the scene
    /// Play opens.
    /// <para>
    /// AND WHY NOT THE WHOLE-ROOM COMPOSED SHOTS: VAL-002 items 2-4 are judgements about what the
    /// eye finds first, and at whole-room ortho the props are a few pixels across. The Art Director
    /// named the framing they need -- orthographicSize 8, one per room, centred on that room's
    /// landmark -- and named the landmark for each. This fixture encodes exactly that and nothing
    /// more; it makes no visual judgement of its own.
    /// </para>
    /// <para>
    /// THE FOCUS POINT IS READ FROM THE SCENE, NOT HARD-CODED. Each landmark is located by its
    /// authored instance id under the composed scene's dressing root, so the frame follows the art
    /// if a placement moves, and a MISSING landmark FAILS rather than quietly centring on the
    /// origin and producing a confident photograph of empty floor.
    /// </para>
    /// </remarks>
    public sealed class ComposedLandmarkCaptureTests
    {
        private const string ScenePath = "Assets/Scenes/DoorPrototype.unity";
        private const string DressingRootName = "RoomDressing";

        /// <summary>The landmark the Art Director named for each room, in their words.</summary>
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

        [Explicit("Set NSC_LANDMARK_CAPTURE_OUTPUT to shoot the VAL-002 landmark panels.")]
        [Test]
        public void CaptureComposedLandmarkPanels()
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

            byte[] sceneBefore = File.ReadAllBytes(ScenePath);
            Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);

            GameObject cameraObject = null;
            RenderTexture target = null;
            try
            {
                GameObject dressingRoot = scene.GetRootGameObjects()
                    .SingleOrDefault(root => root.name == DressingRootName);
                Assert.IsNotNull(dressingRoot,
                    "The composed scene has no '" + DressingRootName + "' root, so there is no " +
                    "dressing to photograph.");

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
                    Transform dressed = dressingRoot.transform.Find(landmark.Room + "Dressing");
                    Assert.IsNotNull(dressed,
                        landmark.Room + " has no dressing in the composed scene.");

                    var positions = new List<Vector3>();
                    foreach (string instanceId in landmark.Instances)
                    {
                        Transform prop = dressed.Find(instanceId);
                        Assert.IsNotNull(prop,
                            landmark.Room + ": landmark '" + instanceId + "' is not in the composed " +
                            "scene. Centring on the origin instead would produce a confident " +
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
                    UnityEngine.Object.DestroyImmediate(shot);

                    Debug.Log($"{landmark.Room}: landmark panel at {focus} -> {landmark.File}");
                }
            }
            finally
            {
                if (cameraObject != null) UnityEngine.Object.DestroyImmediate(cameraObject);
                if (target != null) UnityEngine.Object.DestroyImmediate(target);
                EditorSceneManager.CloseScene(scene, false);
                CollectionAssert.AreEqual(sceneBefore, File.ReadAllBytes(ScenePath),
                    "Photographing the composed scene must not modify it.");
            }
        }
    }
}
