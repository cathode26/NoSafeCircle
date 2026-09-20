// Scratch diagnostic v2: why is the Final Room's navmesh floor higher than every other room's?
// Dumps navmesh vertex heights per room Z band, a coverage grid over the Final Room, and a
// downward raycast at each failing spawn so the responsible collider is named.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;

namespace NscDiag
{
    public static class NavCoverageProbe2
    {
        private const string ScenePath = "Assets/Scenes/DoorPrototype.unity";

        public static void Run()
        {
            string[] args = Environment.GetCommandLineArgs();
            int index = Array.IndexOf(args, "-navProbeOut");
            string outPath = index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
            var report = new StringBuilder();

            Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            Physics.SyncTransforms();

            NavMeshTriangulation triangulation = NavMesh.CalculateTriangulation();

            // Vertex-height histogram per room Z band: a uniform floor shows one height.
            var bands = new (string Name, float MinZ, float MaxZ)[]
            {
                ("RuinedEntry", -25f, 4f),
                ("BoneArchive", 4f, 22f),
                ("ChapelOfAsh", 22f, 44f),
                ("LowerVault", 44f, 64f),
                ("FinalRoom", 64f, 86f),
            };

            foreach (var band in bands)
            {
                var heights = triangulation.vertices
                    .Where(vertex => vertex.z >= band.MinZ && vertex.z <= band.MaxZ)
                    .GroupBy(vertex => Mathf.Round(vertex.y * 1000f) / 1000f)
                    .OrderBy(group => group.Key)
                    .Select(group => $"y={F(group.Key)}x{group.Count()}");
                report.AppendLine($"{band.Name} z[{band.MinZ},{band.MaxZ}] vertex heights: {string.Join(" ", heights)}");
            }

            // Coverage grid over the Final Room's interior.
            report.AppendLine("Final Room grid (nearest navmesh y within 5, '-' = nothing):");
            for (float z = 84f; z >= 66f; z -= 2f)
            {
                var row = new StringBuilder($"  z={F(z),-5}");
                for (float x = -10f; x <= 10f; x += 2f)
                {
                    bool hit = NavMesh.SamplePosition(new Vector3(x, 0f, z), out NavMeshHit near, 5f, NavMesh.AllAreas);
                    row.Append(hit ? $" {F(near.position.y),6}" : "      -");
                }

                report.AppendLine(row.ToString());
            }

            report.AppendLine("  x=      " + string.Join(" ", Enumerable.Range(0, 11).Select(step => $"{-10 + step * 2,6}")));

            // What is actually under each interesting point?
            foreach (Vector3 point in new[]
            {
                new Vector3(8f, 0f, 74f), new Vector3(-8f, 0f, 77f),
                new Vector3(-2f, 0f, 53f), new Vector3(0f, 0f, 82f), new Vector3(8f, 0f, 70f),
            })
            {
                RaycastHit[] hits = Physics.RaycastAll(
                    new Vector3(point.x, 5f, point.z), Vector3.down, 10f,
                    Physics.DefaultRaycastLayers, QueryTriggerInteraction.Collide);
                var descriptions = hits
                    .OrderByDescending(hit => hit.point.y)
                    .Select(hit => $"{Path(hit.collider.gameObject)}@y{F(hit.point.y)}" +
                                   $"(trigger={hit.collider.isTrigger},bounds y[{F(hit.collider.bounds.min.y)},{F(hit.collider.bounds.max.y)}])");
                report.AppendLine($"under ({F(point.x)},{F(point.z)}): {string.Join(" | ", descriptions)}");
            }

            string text = report.ToString();
            Debug.Log("NAV COVERAGE PROBE 2\n" + text);
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

        private static string F(float value)
        {
            return value.ToString("0.###", CultureInfo.InvariantCulture);
        }
    }
}
