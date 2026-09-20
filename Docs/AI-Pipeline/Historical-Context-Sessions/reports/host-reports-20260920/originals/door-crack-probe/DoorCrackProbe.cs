// Scratch diagnostic, not part of the game. Answers three questions about Vincent's
// "crack in the door": does each doorway blocker span its opening, is it enabled in the sealed
// state, and does a chest-height sightline pass through the blocker or past its edge?
//
// Uses the same query EnemyTargetKnowledge.HasUnobstructedViewOfWizard uses: a ray at
// transform.position + Vector3.up, DefaultRaycastLayers, QueryTriggerInteraction.Ignore.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NscDiag
{
    public static class DoorCrackProbe
    {
        private const string ScenePath = "Assets/Scenes/DoorPrototype.unity";

        public static void Run()
        {
            string[] args = Environment.GetCommandLineArgs();
            int index = Array.IndexOf(args, "-probeOut");
            string outPath = index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
            var report = new StringBuilder();

            Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            Physics.SyncTransforms();

            var doors = new List<MonoBehaviour>();
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                doors.AddRange(root.GetComponentsInChildren<MonoBehaviour>(true)
                    .Where(b => b != null && b.GetType().Name == "DoorInteractable"));
            }

            report.AppendLine($"scene {ScenePath}, doors found {doors.Count}");
            report.AppendLine();

            foreach (MonoBehaviour door in doors.OrderBy(d => d.transform.position.z))
            {
                report.AppendLine($"=== {Path(door.gameObject)} at {F(door.transform.position)} ===");

                FieldInfo field = door.GetType().GetField("doorwayBlocker",
                    BindingFlags.NonPublic | BindingFlags.Instance);
                var blocker = field?.GetValue(door) as Collider;
                if (blocker == null)
                {
                    report.AppendLine("  doorwayBlocker: NULL");
                    continue;
                }

                report.AppendLine($"  blocker enabled  : {blocker.enabled}");
                report.AppendLine($"  blocker bounds   : center {F(blocker.bounds.center)} size {F(blocker.bounds.size)}");
                report.AppendLine($"  blocker x span   : [{F1(blocker.bounds.min.x)}, {F1(blocker.bounds.max.x)}]");

                // Force the sealed state the enemy sees when a door is shut, so the answer isn't
                // an artefact of whatever state the committed scene happens to hold.
                bool previouslyEnabled = blocker.enabled;
                blocker.enabled = true;
                Physics.SyncTransforms();

                // Sweep the chest-height sightline laterally across the doorway. The ray crosses
                // the doorway along Z, offset along X, exactly as an enemy on one side looking at
                // a wizard on the other would.
                float doorX = door.transform.position.x;
                float doorZ = door.transform.position.z;
                report.AppendLine("  chest-height sightline across the doorway (ray + Vector3.up):");
                var open = new List<float>();
                for (float offset = -2.0f; offset <= 2.0001f; offset += 0.25f)
                {
                    var origin = new Vector3(doorX + offset, 0f, doorZ - 2f) + Vector3.up;
                    var target = new Vector3(doorX + offset, 0f, doorZ + 2f) + Vector3.up;
                    Vector3 direction = target - origin;
                    bool blockedByAnything = Physics.Raycast(origin, direction.normalized, out RaycastHit hit,
                        direction.magnitude, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
                    string what = blockedByAnything ? hit.collider.gameObject.name : "NOTHING - sightline is OPEN";
                    if (!blockedByAnything)
                    {
                        open.Add(offset);
                    }

                    report.AppendLine($"    x offset {F1(offset),6} : {what}");
                }

                blocker.enabled = previouslyEnabled;
                Physics.SyncTransforms();

                report.AppendLine(open.Count == 0
                    ? "  RESULT: sealed - no open sightline at any offset in [-2, +2]"
                    : $"  RESULT: OPEN at x offsets {string.Join(", ", open.Select(F1))} - the crack is real");
                report.AppendLine();
            }

            string text = report.ToString();
            Debug.Log("DOOR CRACK PROBE\n" + text);
            if (!string.IsNullOrEmpty(outPath))
            {
                File.WriteAllText(outPath, text, new UTF8Encoding(false));
            }

            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        private static string Path(GameObject gameObject)
        {
            string path = gameObject.name;
            Transform parent = gameObject.transform.parent;
            while (parent != null)
            {
                path = parent.name + "/" + path;
                parent = parent.parent;
            }

            return path;
        }

        private static string F(Vector3 v)
        {
            return string.Format(CultureInfo.InvariantCulture, "({0:0.##}, {1:0.##}, {2:0.##})", v.x, v.y, v.z);
        }

        private static string F1(float value)
        {
            return value.ToString("0.##", CultureInfo.InvariantCulture);
        }
    }
}
