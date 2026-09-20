// Scratch diagnostic, not part of the game. Answers one question: does the baked gameplay
// NavMesh in the committed DoorPrototype scene cover every fixed enemy spawn, and each room?
//
// Unity.exe -batchmode -quit -projectPath <checkout> -executeMethod NscDiag.NavCoverageProbe.Run
//     -navProbeOut <file> -logFile <log>
using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;

namespace NscDiag
{
    public static class NavCoverageProbe
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
            report.AppendLine($"scene {ScenePath}, unity {Application.unityVersion}");
            report.AppendLine($"navmesh vertices {triangulation.vertices.Length}, indices {triangulation.indices.Length}");
            if (triangulation.vertices.Length > 0)
            {
                Vector3 min = triangulation.vertices.Aggregate(Vector3.Min);
                Vector3 max = triangulation.vertices.Aggregate(Vector3.Max);
                report.AppendLine($"navmesh bounds x [{F(min.x)}, {F(max.x)}] y [{F(min.y)}, {F(max.y)}] z [{F(min.z)}, {F(max.z)}]");
            }

            // What owns the surface, and does it hold data right now?
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                foreach (MonoBehaviour behaviour in root.GetComponentsInChildren<MonoBehaviour>(true))
                {
                    if (behaviour == null || behaviour.GetType().Name != "GameplayNavigationSurface")
                    {
                        continue;
                    }

                    report.AppendLine($"GameplayNavigationSurface on {Path(behaviour.gameObject)} enabled={behaviour.enabled}");
                    Component surface = behaviour.GetComponents<Component>()
                        .FirstOrDefault(c => c != null && c.GetType().Name == "NavMeshSurface");
                    if (surface == null)
                    {
                        report.AppendLine("  no NavMeshSurface component");
                        continue;
                    }

                    Type surfaceType = surface.GetType();
                    foreach (string member in new[] { "agentTypeID", "collectObjects", "useGeometry", "navMeshData" })
                    {
                        PropertyInfo property = surfaceType.GetProperty(member);
                        object value = property != null ? property.GetValue(surface) : "(no such property)";
                        report.AppendLine($"  {member} = {value ?? "null"}");
                    }
                }
            }

            // Every fixed spawn the builder authors, read the way the tests read it.
            Type builder = AppDomain.CurrentDomain.GetAssemblies()
                .Select(assembly => assembly.GetType("NoSafeCircle.DoorPrototype.Editor.World.DoorPrototypeGlobalSceneBuilder"))
                .FirstOrDefault(type => type != null);
            report.AppendLine(builder != null ? "builder type found" : "BUILDER TYPE NOT FOUND");

            foreach (string fieldName in new[] { "EnemySpawnPositions", "LanternWraithSpawnPositions", "PlayerSpawnPosition" })
            {
                FieldInfo field = builder?.GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Static);
                if (field == null)
                {
                    report.AppendLine($"{fieldName}: MISSING");
                    continue;
                }

                object value = field.GetValue(null);
                Vector3[] points = value is Vector3[] array ? array : new[] { (Vector3)value };
                foreach (Vector3 point in points)
                {
                    report.AppendLine($"{fieldName} ({F(point.x)}, {F(point.z)}): {Sample(point)}");
                }
            }

            // Each room's own centre, so a gap shows up as a room rather than a stray point.
            foreach (string layoutName in new[] { "RuinedEntryLayout", "BoneArchiveLayout", "ChapelOfAshLayout", "LowerVaultLayout", "FinalRoomLayout" })
            {
                Type layout = AppDomain.CurrentDomain.GetAssemblies()
                    .Select(assembly => assembly.GetType("NoSafeCircle.DoorPrototype.World.Rooms." + layoutName))
                    .FirstOrDefault(type => type != null);
                PropertyInfo bounds = layout?.GetProperty("RoomBounds", BindingFlags.Public | BindingFlags.Static);
                if (bounds == null)
                {
                    report.AppendLine($"{layoutName}: no RoomBounds");
                    continue;
                }

                var roomBounds = (Bounds)bounds.GetValue(null);
                Vector3 centre = new Vector3(roomBounds.center.x, 0f, roomBounds.center.z);
                report.AppendLine($"{layoutName} centre ({F(centre.x)}, {F(centre.z)}): {Sample(centre)}");
            }

            string text = report.ToString();
            Debug.Log("NAV COVERAGE PROBE\n" + text);
            if (!string.IsNullOrEmpty(outPath))
            {
                File.WriteAllText(outPath, text, new UTF8Encoding(false));
            }

            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        private static string Sample(Vector3 point)
        {
            bool tight = NavMesh.SamplePosition(point, out NavMeshHit near, 0.1f, NavMesh.AllAreas);
            bool loose = NavMesh.SamplePosition(point, out NavMeshHit far, 5f, NavMesh.AllAreas);
            string tightText = tight ? $"on mesh (dist {F(near.distance)})" : "NOT on mesh within 0.1";
            string looseText = loose ? $"nearest within 5 = ({F(far.position.x)}, {F(far.position.y)}, {F(far.position.z)}) dist {F(far.distance)}" : "nothing within 5";
            return tightText + "; " + looseText;
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
