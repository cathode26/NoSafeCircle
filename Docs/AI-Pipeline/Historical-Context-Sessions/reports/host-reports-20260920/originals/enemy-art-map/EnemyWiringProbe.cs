// Scratch diagnostic: what is actually attached to the authored enemies in the committed scene?
// The text reference map proves all 112 PNGs reach a controller; only Unity can say whether the
// controller reaches the object. Also reports sprite pixel size and PPU, which answers the
// enemy-versus-wizard scale question from the scene rather than from the art folder.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NscDiag
{
    public static class EnemyWiringProbe
    {
        private const string ScenePath = "Assets/Scenes/DoorPrototype.unity";

        public static void Run()
        {
            string[] args = Environment.GetCommandLineArgs();
            int index = Array.IndexOf(args, "-probeOut");
            string outPath = index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
            var report = new StringBuilder();

            Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);

            foreach (GameObject root in scene.GetRootGameObjects())
            {
                if (root.name != "Enemies" && root.name != "World")
                {
                    continue;
                }

                report.AppendLine($"=== root '{root.name}' ===");
                foreach (Transform child in root.GetComponentsInChildren<Transform>(true))
                {
                    var animator = child.GetComponent<Animator>();
                    var renderer = child.GetComponent<SpriteRenderer>();
                    if (animator == null && renderer == null)
                    {
                        continue;
                    }

                    // Only report things that look like enemies, to keep this readable.
                    string path = Path(child.gameObject);
                    if (!path.Contains("Enem") && !path.Contains("Melee") && !path.Contains("Wraith")
                        && !path.Contains("Wizard") && !path.Contains("Player"))
                    {
                        continue;
                    }

                    report.AppendLine($"  {path}");
                    if (animator != null)
                    {
                        var controller = animator.runtimeAnimatorController;
                        report.AppendLine($"    Animator controller : {(controller == null ? "NONE ASSIGNED" : controller.name)}");
                    }
                    else
                    {
                        report.AppendLine("    Animator            : none");
                    }

                    if (renderer != null)
                    {
                        Sprite sprite = renderer.sprite;
                        if (sprite == null)
                        {
                            report.AppendLine("    SpriteRenderer      : no sprite assigned");
                        }
                        else
                        {
                            report.AppendLine($"    sprite              : {sprite.name}");
                            report.AppendLine($"    texture px          : {sprite.texture.width}x{sprite.texture.height}");
                            report.AppendLine($"    pixelsPerUnit       : {F(sprite.pixelsPerUnit)}");
                            report.AppendLine($"    world size (units)  : {F(sprite.bounds.size.x)} x {F(sprite.bounds.size.y)}");
                            report.AppendLine($"    lossyScale          : {F3(child.lossyScale)}");
                        }
                    }
                }

                report.AppendLine();
            }

            string text = report.ToString();
            Debug.Log("ENEMY WIRING PROBE\n" + text);
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

        private static string F3(Vector3 v)
        {
            return string.Format(CultureInfo.InvariantCulture, "({0:0.##}, {1:0.##}, {2:0.##})", v.x, v.y, v.z);
        }
    }
}
