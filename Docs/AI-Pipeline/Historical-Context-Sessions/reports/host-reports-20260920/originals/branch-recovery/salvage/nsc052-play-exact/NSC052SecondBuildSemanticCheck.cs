using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Editor
{
    // Disposable validation probe. This file is not part of the candidate.
    public static class NSC052SecondBuildSemanticCheck
    {
        private const string ScenePath = "Assets/Scenes/DoorPrototype.unity";
        private const string EvidencePath = @"C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-052\20260914-0835-verification";

        public static void Run()
        {
            var before = Snapshot();
            Directory.CreateDirectory(EvidencePath);
            File.WriteAllText(Path.Combine(EvidencePath, "second-build-before.txt"), before);
            DoorPrototypeSceneBuilder.Build();
            var after = Snapshot();
            File.WriteAllText(Path.Combine(EvidencePath, "second-build-after.txt"), after);
            if (!string.Equals(before, after, StringComparison.Ordinal))
            {
                var left = before.Split('\n');
                var right = after.Split('\n');
                for (int i = 0; i < Math.Max(left.Length, right.Length); i++)
                    if (i >= left.Length || i >= right.Length || left[i] != right[i])
                        throw new InvalidOperationException("NSC-052 second-build semantic mismatch at line " +
                            (i + 1) + ": before=" + (i < left.Length ? left[i] : "<missing>") +
                            " after=" + (i < right.Length ? right[i] : "<missing>"));
            }
            Debug.Log("NSC-052 SECOND_BUILD_SEMANTIC_PASS: five door hierarchies, components, " +
                "feedback references, crack stages, and component values match.");
        }

        private static string Snapshot()
        {
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            var doors = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<DoorInteractable>(true))
                .OrderBy(door => door.DoorId.ToString(), StringComparer.Ordinal)
                .ToArray();
            if (doors.Length != 5) throw new InvalidOperationException("Expected five saved doors, found " + doors.Length);
            var builder = new StringBuilder();
            foreach (var door in doors)
            {
                var root = door.transform;
                var feedbackRoot = root.Find("DoorBreachFeedback");
                var feedback = feedbackRoot == null ? null : feedbackRoot.GetComponent<DoorBreachFeedback>();
                var shake = root.Find("DoorVisual/DoorSprite");
                if (feedback == null || shake == null) throw new InvalidOperationException("Missing feedback/visual for " + door.DoorId);
                builder.AppendLine("DOOR|" + door.DoorId + "|" + F(door.MaxDurability) + "|" +
                    F(door.CurrentDurability) + "|" + door.IsOpen + "|" + door.IsLocked + "|" + door.IsBroken);
                foreach (var node in root.GetComponentsInChildren<Transform>(true)
                    .OrderBy(node => RelativePath(root, node), StringComparer.Ordinal))
                {
                    builder.AppendLine("NODE|" + RelativePath(root, node) + "|" + node.gameObject.activeSelf +
                        "|" + V(node.localPosition) + "|" + Q(node.localRotation) + "|" + V(node.localScale) +
                        "|" + string.Join(",", node.GetComponents<Component>().Select(component =>
                            component == null ? "<missing>" : component.GetType().FullName)));
                }
                var serial = new SerializedObject(feedback);
                foreach (var property in new[] { "door", "shakeTarget", "durabilityIndicator", "durabilityFill", "bangAudio" })
                    builder.AppendLine("REF|" + property + "|" + Reference(root, serial.FindProperty(property).objectReferenceValue));
                var cracks = serial.FindProperty("crackStages");
                if (cracks.arraySize != 3) throw new InvalidOperationException("Expected three bound cracks for " + door.DoorId);
                for (int i = 0; i < cracks.arraySize; i++)
                {
                    var actual = cracks.GetArrayElementAtIndex(i).objectReferenceValue;
                    var expected = shake.Find("CrackStage" + (i + 1));
                    if (expected == null || actual != expected.gameObject)
                        throw new InvalidOperationException("Wrong crack binding " + door.DoorId + " stage " + (i + 1));
                    builder.AppendLine("CRACK|" + i + "|" + Reference(root, actual));
                }
                foreach (var property in new[] { "shakeDuration", "shakeMagnitude" })
                    builder.AppendLine("VALUE|" + property + "|" + F(serial.FindProperty(property).floatValue));
                var audio = feedbackRoot.GetComponent<AudioSource>();
                var indicator = feedbackRoot.Find("DurabilityIndicator");
                var fill = indicator == null ? null : indicator.Find("Background/Fill")?.GetComponent<Image>();
                if (audio == null || fill == null) throw new InvalidOperationException("Missing audio/indicator for " + door.DoorId);
                builder.AppendLine("AUDIO|" + audio.playOnAwake + "|" + F(audio.spatialBlend) + "|" + F(audio.volume));
                builder.AppendLine("INDICATOR|" + indicator.gameObject.activeSelf + "|" + F(fill.fillAmount) +
                    "|" + AssetDatabase.GetAssetPath(fill.sprite));
                builder.AppendLine("SHAKE_COLLIDERS|" + shake.GetComponentsInChildren<Collider>(true).Length);
            }
            return builder.ToString();
        }

        private static string Reference(Transform root, UnityEngine.Object value)
        {
            var gameObject = value as GameObject;
            var component = value as Component;
            var transform = gameObject != null ? gameObject.transform : component != null ? component.transform : null;
            return transform == null ? "<null>" : RelativePath(root, transform) +
                (component == null ? "" : ":" + component.GetType().FullName);
        }

        private static string RelativePath(Transform root, Transform node)
        {
            if (node == root) return root.name;
            var parent = node.parent;
            return parent == null ? "<outside>/" + node.name : RelativePath(root, parent) + "/" + node.name +
                "[" + node.GetSiblingIndex() + "]";
        }

        private static string F(float value) => value.ToString("R", CultureInfo.InvariantCulture);
        private static string V(Vector3 value) => F(value.x) + "," + F(value.y) + "," + F(value.z);
        private static string Q(Quaternion value) => F(value.x) + "," + F(value.y) + "," + F(value.z) + "," + F(value.w);
    }
}
