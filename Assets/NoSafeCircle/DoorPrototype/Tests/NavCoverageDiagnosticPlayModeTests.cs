using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // TEMPORARY DIAGNOSTIC - NOT FOR COMMIT. Answers one question for NSC-049: does the composed
    // scene's baked NavMesh cover every room, or does it stop somewhere? AC-006 fails because
    // (-2,0,66) in the Lower Vault will not sample the navmesh, and VAL-007's broken-door path
    // will not reconnect. Both are consistent with a bake that does not reach the later rooms,
    // and that is a different problem from anything the door carving does.
    public sealed class NavCoverageDiagnosticPlayModeTests
    {
        [UnityTest]
        public IEnumerator ReportNavMeshCoverageAcrossTheComposedFloor()
        {
            yield return SceneManager.LoadSceneAsync("DoorPrototype", LoadSceneMode.Single);
            yield return null;

            NavMeshTriangulation tri = NavMesh.CalculateTriangulation();
            var min = new Vector3(float.MaxValue, 0f, float.MaxValue);
            var max = new Vector3(float.MinValue, 0f, float.MinValue);
            foreach (Vector3 v in tri.vertices)
            {
                min.x = Mathf.Min(min.x, v.x); min.z = Mathf.Min(min.z, v.z);
                max.x = Mathf.Max(max.x, v.x); max.z = Mathf.Max(max.z, v.z);
            }

            Debug.Log("[NAVDIAG] vertices=" + tri.vertices.Length + " indices=" + tri.indices.Length
                + " extentX=[" + min.x.ToString("F1") + "," + max.x.ToString("F1")
                + "] extentZ=[" + min.z.ToString("F1") + "," + max.z.ToString("F1") + "]");

            // One probe per room centre plus the two spawns the gates actually name.
            (string Label, Vector3 Point)[] probes =
            {
                ("RuinedEntry centre", new Vector3(0f, 0f, -10f)),
                ("BoneArchive centre", new Vector3(0f, 0f, 10f)),
                ("BoneArchive melee spawn", new Vector3(1.25f, 0f, 10f)),
                ("ChapelOfAsh centre", new Vector3(0f, 0f, 37f)),
                ("ChapelOfAsh melee spawn", new Vector3(-2f, 0f, 36f)),
                ("LowerVault centre", new Vector3(0f, 0f, 65f)),
                ("LowerVault melee spawn", new Vector3(-2f, 0f, 66f)),
                ("FinalRoom centre", new Vector3(0f, 0f, 90f)),
                ("FinalRoom west flank", new Vector3(-2f, 0f, 86f)),
            };

            foreach ((string label, Vector3 point) in probes)
            {
                bool hit = NavMesh.SamplePosition(point, out NavMeshHit sample, 0.1f, NavMesh.AllAreas);
                bool wide = NavMesh.SamplePosition(point, out NavMeshHit wideSample, 5f, NavMesh.AllAreas);
                Debug.Log("[NAVDIAG] " + label + " " + point.ToString("F2")
                    + " within0.1=" + hit
                    + " within5=" + wide
                    + (wide ? " nearest=" + wideSample.position.ToString("F2")
                        + " dist=" + Vector3.Distance(point, wideSample.position).ToString("F2") : ""));
            }

            Assert.Pass("diagnostic only");
        }
    }
}
