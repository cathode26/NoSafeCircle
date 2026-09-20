// Evidence tooling for NSC-077 VAL-007 (contract revision 8): a normalized, fileID-free snapshot of a saved
// scene, so two builder runs can be compared for real content changes instead of regenerated local file IDs.
//
// Not part of the game. The Game Agent copies it into a verification checkout as a scratch Editor script
// (Assets/_NscEvidence/Editor/), runs it in batchmode, and removes it again. It never saves the scene.
//
// Unity.exe -batchmode -quit -projectPath <checkout> -executeMethod NscEvidence.NscSceneSnapshot.Run
//     -snapshotOut <file> [-snapshotScene Assets/Scenes/DoorPrototype.unity] [-snapshotPerturb] -logFile <log>
//
// Output, one line per item:
//   GO <path> name tag layer active static
//   C  <path> |<Type>#<index among same type>            (MISSING_SCRIPT for a missing MonoBehaviour)
//   P  <owner> <propertyPath> <propertyType> <value>     (every property from SerializedProperty.Next(true))
// A path is /<name>#<sibling index>/... from the scene root. Object references are written as scene:<path>
// [|<component key>], asset:<guid>:<local id>, null, or missing (a dangling reference). No fileID is written.
// -snapshotPerturb is the negative control: it changes one float and one object reference in memory first.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace NscEvidence
{
    public static class NscSceneSnapshot
    {
        private const string DefaultScenePath = "Assets/Scenes/DoorPrototype.unity";

        private static readonly Dictionary<GameObject, string> Paths = new Dictionary<GameObject, string>();
        private static readonly Dictionary<Component, string> ComponentKeys = new Dictionary<Component, string>();

        public static void Run()
        {
            string[] args = Environment.GetCommandLineArgs();
            string outPath = ArgValue(args, "-snapshotOut");
            if (string.IsNullOrEmpty(outPath))
            {
                throw new ArgumentException("-snapshotOut <file> is required.");
            }

            string scenePath = ArgValue(args, "-snapshotScene") ?? DefaultScenePath;
            bool perturb = args.Contains("-snapshotPerturb");

            Scene scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
            if (!scene.IsValid())
            {
                throw new InvalidOperationException("Could not open " + scenePath);
            }

            if (perturb)
            {
                Perturb(scene);
            }

            Paths.Clear();
            ComponentKeys.Clear();
            List<GameObject> roots = scene.GetRootGameObjects().OrderBy(root => root.transform.GetSiblingIndex()).ToList();
            foreach (GameObject root in roots)
            {
                Index(root);
            }

            var lines = new List<string>
            {
                "scene " + scenePath + " unity " + Application.unityVersion + " roots " + roots.Count + " perturbed " + perturb
            };
            foreach (GameObject root in roots)
            {
                Walk(root, lines);
            }

            lines.Add("summary gameObjects " + Paths.Count + " components " + ComponentKeys.Count + " lines " + (lines.Count + 1));
            byte[] bytes = new UTF8Encoding(false).GetBytes(string.Join("\n", lines) + "\n");
            File.WriteAllBytes(outPath, bytes);
            string sha;
            using (SHA256 hasher = SHA256.Create())
            {
                sha = string.Concat(hasher.ComputeHash(bytes).Select(b => b.ToString("x2")));
            }

            Debug.Log("NSC scene snapshot: " + scenePath + " -> " + outPath + " lines=" + lines.Count + " sha256=" + sha);

            // Discard anything in memory without saving (the perturbation, or any import side effect).
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        private static void Perturb(Scene scene)
        {
            GameObject[] all = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<Transform>(true))
                .Select(transform => transform.gameObject)
                .ToArray();
            GameObject player = all.FirstOrDefault(gameObject => gameObject.name == "Player") ?? all[0];
            Vector3 position = player.transform.localPosition;
            player.transform.localPosition = new Vector3(position.x + 0.001f, position.y, position.z);

            SpriteRenderer renderer = all.Select(gameObject => gameObject.GetComponent<SpriteRenderer>())
                .FirstOrDefault(candidate => candidate != null && candidate.sprite != null);
            if (renderer != null)
            {
                renderer.sprite = null;
            }

            Debug.Log("NSC scene snapshot: negative control moved " + player.name + " by 0.001 on local x and cleared the sprite on "
                + (renderer != null ? renderer.gameObject.name : "<no sprite renderer>"));
        }

        private static void Index(GameObject gameObject)
        {
            Transform parent = gameObject.transform.parent;
            string segment = "/" + gameObject.name + "#" + gameObject.transform.GetSiblingIndex().ToString(CultureInfo.InvariantCulture);
            Paths[gameObject] = (parent != null ? Paths[parent.gameObject] : string.Empty) + segment;

            Component[] components = gameObject.GetComponents<Component>();
            var seen = new Dictionary<string, int>();
            foreach (Component component in components)
            {
                string typeName = component != null ? component.GetType().FullName : "MissingScript";
                seen.TryGetValue(typeName, out int index);
                seen[typeName] = index + 1;
                if (component != null)
                {
                    ComponentKeys[component] = typeName + "#" + index.ToString(CultureInfo.InvariantCulture);
                }
            }

            for (int i = 0; i < gameObject.transform.childCount; i++)
            {
                Index(gameObject.transform.GetChild(i).gameObject);
            }
        }

        private static void Walk(GameObject gameObject, List<string> lines)
        {
            string path = Paths[gameObject];
            lines.Add("GO " + path + " name=" + Quote(gameObject.name) + " tag=" + Quote(gameObject.tag)
                + " layer=" + gameObject.layer.ToString(CultureInfo.InvariantCulture) + " active=" + (gameObject.activeSelf ? "true" : "false")
                + " static=" + ((int)GameObjectUtility.GetStaticEditorFlags(gameObject)).ToString(CultureInfo.InvariantCulture));
            DumpObject(new SerializedObject(gameObject), path + " :GameObject", lines);

            Component[] components = gameObject.GetComponents<Component>();
            int missing = 0;
            foreach (Component component in components)
            {
                if (component == null)
                {
                    lines.Add("C " + path + " |MissingScript#" + missing.ToString(CultureInfo.InvariantCulture) + " MISSING_SCRIPT");
                    missing++;
                    continue;
                }

                string owner = path + " |" + ComponentKeys[component];
                lines.Add("C " + owner);
                DumpObject(new SerializedObject(component), owner, lines);
            }

            for (int i = 0; i < gameObject.transform.childCount; i++)
            {
                Walk(gameObject.transform.GetChild(i).gameObject, lines);
            }
        }

        private static void DumpObject(SerializedObject serializedObject, string owner, List<string> lines)
        {
            SerializedProperty property = serializedObject.GetIterator();
            bool enterChildren = true;
            while (property.Next(enterChildren))
            {
                enterChildren = EntersChildren(property);
                // Written through Reference() instead: the raw m_FileID/m_PathID children are in-memory
                // instance IDs that change between Unity sessions.
                if (property.name == "m_LocalIdentfierInFile" || property.name == "m_FileID" || property.name == "m_PathID")
                {
                    continue;
                }

                lines.Add("P " + owner + " " + property.propertyPath + " " + property.propertyType + " " + ValueOf(property));
            }
        }

        // Value types written whole are not entered, so their x/y/z or char children are not listed twice, and object
        // references are not entered, so their instance-ID children never reach the snapshot.
        private static bool EntersChildren(SerializedProperty property)
        {
            switch (property.propertyType)
            {
                case SerializedPropertyType.String:
                case SerializedPropertyType.Color:
                case SerializedPropertyType.Vector2:
                case SerializedPropertyType.Vector3:
                case SerializedPropertyType.Vector4:
                case SerializedPropertyType.Rect:
                case SerializedPropertyType.AnimationCurve:
                case SerializedPropertyType.Bounds:
                case SerializedPropertyType.Gradient:
                case SerializedPropertyType.Quaternion:
                case SerializedPropertyType.Vector2Int:
                case SerializedPropertyType.Vector3Int:
                case SerializedPropertyType.RectInt:
                case SerializedPropertyType.BoundsInt:
                case SerializedPropertyType.Hash128:
                case SerializedPropertyType.ObjectReference:
                case SerializedPropertyType.ExposedReference:
                    return false;
                default:
                    return true;
            }
        }

        private static string ValueOf(SerializedProperty property)
        {
            switch (property.propertyType)
            {
                case SerializedPropertyType.Integer:
                    return property.longValue.ToString(CultureInfo.InvariantCulture);
                case SerializedPropertyType.Boolean:
                    return property.boolValue ? "true" : "false";
                case SerializedPropertyType.Float:
                    return F(property.doubleValue);
                case SerializedPropertyType.String:
                    return Quote(property.stringValue);
                case SerializedPropertyType.Color:
                    Color color = property.colorValue;
                    return "(" + F(color.r) + "," + F(color.g) + "," + F(color.b) + "," + F(color.a) + ")";
                case SerializedPropertyType.ObjectReference:
                    return Reference(property.objectReferenceValue, property.objectReferenceInstanceIDValue);
                case SerializedPropertyType.ExposedReference:
                    return Reference(property.exposedReferenceValue, 0);
                case SerializedPropertyType.LayerMask:
                case SerializedPropertyType.Enum:
                case SerializedPropertyType.ArraySize:
                case SerializedPropertyType.Character:
                    return property.intValue.ToString(CultureInfo.InvariantCulture);
                case SerializedPropertyType.FixedBufferSize:
                    return property.fixedBufferSize.ToString(CultureInfo.InvariantCulture);
                case SerializedPropertyType.Vector2:
                    Vector2 v2 = property.vector2Value;
                    return "(" + F(v2.x) + "," + F(v2.y) + ")";
                case SerializedPropertyType.Vector3:
                    Vector3 v3 = property.vector3Value;
                    return "(" + F(v3.x) + "," + F(v3.y) + "," + F(v3.z) + ")";
                case SerializedPropertyType.Vector4:
                    Vector4 v4 = property.vector4Value;
                    return "(" + F(v4.x) + "," + F(v4.y) + "," + F(v4.z) + "," + F(v4.w) + ")";
                case SerializedPropertyType.Quaternion:
                    Quaternion q = property.quaternionValue;
                    return "(" + F(q.x) + "," + F(q.y) + "," + F(q.z) + "," + F(q.w) + ")";
                case SerializedPropertyType.Rect:
                    Rect rect = property.rectValue;
                    return "(" + F(rect.x) + "," + F(rect.y) + "," + F(rect.width) + "," + F(rect.height) + ")";
                case SerializedPropertyType.Bounds:
                    Bounds bounds = property.boundsValue;
                    return "(" + F(bounds.center.x) + "," + F(bounds.center.y) + "," + F(bounds.center.z) + ";"
                        + F(bounds.extents.x) + "," + F(bounds.extents.y) + "," + F(bounds.extents.z) + ")";
                case SerializedPropertyType.Vector2Int:
                    return property.vector2IntValue.ToString();
                case SerializedPropertyType.Vector3Int:
                    return property.vector3IntValue.ToString();
                case SerializedPropertyType.RectInt:
                    RectInt rectInt = property.rectIntValue;
                    return "(" + rectInt.x + "," + rectInt.y + "," + rectInt.width + "," + rectInt.height + ")";
                case SerializedPropertyType.BoundsInt:
                    BoundsInt boundsInt = property.boundsIntValue;
                    return "(" + boundsInt.position + ";" + boundsInt.size + ")";
                case SerializedPropertyType.AnimationCurve:
                    return Curve(property.animationCurveValue);
                case SerializedPropertyType.Gradient:
                    return GradientText(property.gradientValue);
                case SerializedPropertyType.Hash128:
                    return property.hash128Value.ToString();
                case SerializedPropertyType.ManagedReference:
                    return Quote(property.managedReferenceFullTypename);
                default:
                    return property.propertyType.ToString() == "RenderingLayerMask"
                        ? property.uintValue.ToString(CultureInfo.InvariantCulture)
                        : "-";
            }
        }

        private static string Reference(Object target, int instanceId)
        {
            if (target == null)
            {
                return instanceId != 0 ? "missing" : "null";
            }

            if (!EditorUtility.IsPersistent(target))
            {
                if (target is GameObject gameObject && Paths.TryGetValue(gameObject, out string gameObjectPath))
                {
                    return "scene:" + gameObjectPath;
                }

                if (target is Component component && Paths.TryGetValue(component.gameObject, out string ownerPath)
                    && ComponentKeys.TryGetValue(component, out string key))
                {
                    return "scene:" + ownerPath + "|" + key;
                }

                return "transient:" + target.GetType().FullName + ":" + Quote(target.name);
            }

            if (AssetDatabase.TryGetGUIDAndLocalFileIdentifier(target, out string guid, out long localId))
            {
                return "asset:" + guid + ":" + localId.ToString(CultureInfo.InvariantCulture);
            }

            return "persistent:" + target.GetType().FullName + ":" + Quote(target.name);
        }

        private static string Curve(AnimationCurve curve)
        {
            if (curve == null)
            {
                return "null";
            }

            var builder = new StringBuilder("[" + curve.preWrapMode + "," + curve.postWrapMode);
            foreach (Keyframe key in curve.keys)
            {
                builder.Append(";").Append(F(key.time)).Append(",").Append(F(key.value)).Append(",")
                    .Append(F(key.inTangent)).Append(",").Append(F(key.outTangent)).Append(",")
                    .Append(F(key.inWeight)).Append(",").Append(F(key.outWeight)).Append(",").Append(key.weightedMode);
            }

            return builder.Append("]").ToString();
        }

        private static string GradientText(Gradient gradient)
        {
            if (gradient == null)
            {
                return "null";
            }

            var builder = new StringBuilder("[" + gradient.mode);
            foreach (GradientColorKey key in gradient.colorKeys)
            {
                builder.Append(";c").Append(F(key.time)).Append(",").Append(F(key.color.r)).Append(",")
                    .Append(F(key.color.g)).Append(",").Append(F(key.color.b));
            }

            foreach (GradientAlphaKey key in gradient.alphaKeys)
            {
                builder.Append(";a").Append(F(key.time)).Append(",").Append(F(key.alpha));
            }

            return builder.Append("]").ToString();
        }

        private static string F(double value)
        {
            return value.ToString("R", CultureInfo.InvariantCulture);
        }

        private static string Quote(string value)
        {
            if (value == null)
            {
                return "null";
            }

            return "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r") + "\"";
        }

        private static string ArgValue(string[] args, string name)
        {
            int index = Array.IndexOf(args, name);
            return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
        }
    }
}
