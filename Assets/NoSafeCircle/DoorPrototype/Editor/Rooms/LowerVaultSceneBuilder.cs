using System;
using System.IO;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor.Rooms
{
    /// <summary>Builds the Lower Vault authoring scene without touching the canonical gameplay scene.</summary>
    public static class LowerVaultSceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/Rooms/LowerVault.unity";

        private static readonly Color FloorColor = new Color(0.055f, 0.045f, 0.08f);
        private static readonly Color WallColor = new Color(0.09f, 0.06f, 0.13f);
        private static readonly Color StoneColor = new Color(0.16f, 0.10f, 0.20f);
        private static readonly Color StorageColor = new Color(0.20f, 0.09f, 0.10f);
        private static readonly Color AccentColor = new Color(0.45f, 0.10f, 0.20f);

        [MenuItem("No Safe Circle/Rooms/Build Lower Vault Authoring Scene")]
        public static void BuildAndSave()
        {
            EnsureFolder(Path.GetDirectoryName(ScenePath)?.Replace('\\', '/'));
            Scene scene = File.Exists(ScenePath)
                ? EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single)
                : EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            RebuildSceneContents(scene);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
        }

        public static void BuildInMemoryForTests()
        {
            RebuildSceneContents(SceneManager.GetActiveScene());
        }

        private static void RebuildSceneContents(Scene scene)
        {
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                Object.DestroyImmediate(root);
            }

            GameObject roomRoot = new GameObject("LowerVault");
            Transform visibleRoot = CreateChild(roomRoot.transform, "VisibleBlockout");
            Transform gameplayRoot = CreateChild(roomRoot.transform, "GameplayGeometry");
            Transform anchorsRoot = CreateChild(roomRoot.transform, "DoorAnchors");
            CreateChild(roomRoot.transform, "Authoring");

            BuildVisibleBlockout(visibleRoot);
            BuildGameplayGeometry(gameplayRoot);
            CreateMarker(anchorsRoot, "D3Opening", LowerVaultLayout.D3);
            CreateMarker(anchorsRoot, "D4Opening", LowerVaultLayout.D4);
            CreateMarker(roomRoot.transform, "D3StagingArea", new Vector3(-6f, 0f, 45f));
            CreateMarker(roomRoot.transform, "D4StagingArea", new Vector3(4f, 0f, 61f));
            BuildLighting();
            BuildCamera();
            SceneManager.SetActiveScene(scene);
        }

        private static void BuildVisibleBlockout(Transform parent)
        {
            CreateVisualBox(parent, "VaultFloor", new Vector3(0f, -0.05f, 53f), new Vector3(22f, 0.1f, 22f), FloorColor);
            CreateShellBoxes(parent, "Visual", CreateVisualBox);
            CreateVisualObstacle(parent, "LV-C1", LowerVaultLayout.CentralColumnCluster, StoneColor);
            CreateVisualObstacle(parent, "LV-W1", LowerVaultLayout.WestStoragePile, StorageColor);
            CreateVisualObstacle(parent, "LV-E1", LowerVaultLayout.EastStoragePile, StorageColor);
            CreateVisualObstacle(parent, "LV-N1", LowerVaultLayout.NorthWestStorageBar, StorageColor);

            CreateTrim(parent, new Vector3(-10.65f, 0.08f, 53f), new Vector3(0.12f, 0.08f, 20f));
            CreateTrim(parent, new Vector3(10.65f, 0.08f, 53f), new Vector3(0.12f, 0.08f, 20f));
            CreateCrateCluster(parent, new Vector3(-9f, 0f, 47f), 3);
            CreateCrateCluster(parent, new Vector3(8.8f, 0f, 57f), 2);
            CreateLantern(parent, new Vector3(-9.2f, 1.7f, 60.5f));
            CreateLantern(parent, new Vector3(8.8f, 1.7f, 45.2f));
            CreateVaultMark(parent, new Vector3(0f, 0.04f, 62.5f));
        }

        private static void BuildGameplayGeometry(Transform parent)
        {
            CreateGameplayBox(parent, "FloorCollision", new Vector3(0f, -0.05f, 53f), new Vector3(22f, 0.1f, 22f), Color.clear);
            CreateShellBoxes(parent, "Collision", CreateGameplayBox);
            CreateGameplayObstacle(parent, "LV-C1Collision", LowerVaultLayout.CentralColumnCluster);
            CreateGameplayObstacle(parent, "LV-W1Collision", LowerVaultLayout.WestStoragePile);
            CreateGameplayObstacle(parent, "LV-E1Collision", LowerVaultLayout.EastStoragePile);
            CreateGameplayObstacle(parent, "LV-N1Collision", LowerVaultLayout.NorthWestStorageBar);
        }

        private static void CreateShellBoxes(Transform parent, string suffix, Action<Transform, string, Vector3, Vector3, Color> createBox)
        {
            float centerY = LowerVaultLayout.WallHeight * 0.5f;
            float depth = LowerVaultLayout.MaximumZ - LowerVaultLayout.MinimumZ;
            createBox(parent, "WestWall" + suffix, new Vector3(-11f, centerY, 53f), new Vector3(0.5f, 2.5f, depth), WallColor);
            createBox(parent, "EastWall" + suffix, new Vector3(11f, centerY, 53f), new Vector3(0.5f, 2.5f, depth), WallColor);
            CreateOpeningWall(parent, "SouthWall", suffix, LowerVaultLayout.D3.x, LowerVaultLayout.MinimumZ, createBox);
            CreateOpeningWall(parent, "NorthWall", suffix, LowerVaultLayout.D4.x, LowerVaultLayout.MaximumZ, createBox);
        }

        private static void CreateOpeningWall(Transform parent, string name, string suffix, float openingCenter, float z, Action<Transform, string, Vector3, Vector3, Color> createBox)
        {
            float halfOpening = LowerVaultLayout.DoorWidth * 0.5f;
            float westLength = openingCenter - halfOpening - LowerVaultLayout.MinimumX;
            float eastLength = LowerVaultLayout.MaximumX - openingCenter - halfOpening;
            float centerY = LowerVaultLayout.WallHeight * 0.5f;
            createBox(parent, name + "West" + suffix, new Vector3(LowerVaultLayout.MinimumX + westLength * 0.5f, centerY, z), new Vector3(westLength, 2.5f, 0.5f), WallColor);
            createBox(parent, name + "East" + suffix, new Vector3(LowerVaultLayout.MaximumX - eastLength * 0.5f, centerY, z), new Vector3(eastLength, 2.5f, 0.5f), WallColor);
        }

        private static void CreateVisualObstacle(Transform parent, string name, Bounds bounds, Color color)
        {
            CreateVisualBox(parent, name, new Vector3(bounds.center.x, bounds.size.y * 0.5f, bounds.center.z), bounds.size, color);
            CreateTrim(parent, new Vector3(bounds.center.x, bounds.size.y + 0.04f, bounds.center.z), new Vector3(bounds.size.x * 0.75f, 0.08f, bounds.size.z * 0.75f));
        }

        private static void CreateGameplayObstacle(Transform parent, string name, Bounds bounds)
        {
            CreateGameplayBox(parent, name, bounds.center, bounds.size, Color.clear);
        }

        private static void CreateCrateCluster(Transform parent, Vector3 origin, int count)
        {
            for (int index = 0; index < count; index++)
            {
                float offsetX = (index % 2) * 0.8f;
                float offsetZ = (index / 2) * 0.7f;
                CreateVisualBox(parent, "Crate_" + origin.x + "_" + index, origin + new Vector3(offsetX, 0.35f, offsetZ), new Vector3(0.65f, 0.7f, 0.65f), StorageColor);
            }
        }

        private static void CreateLantern(Transform parent, Vector3 position)
        {
            CreateVisualBox(parent, "LanternGlow", position, new Vector3(0.22f, 0.22f, 0.22f), AccentColor);
            GameObject lightObject = new GameObject("LanternLight");
            lightObject.transform.SetParent(parent, false);
            lightObject.transform.position = position;
            Light light = lightObject.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = new Color(0.85f, 0.18f, 0.28f);
            light.intensity = 0.8f;
            light.range = 4f;
        }

        private static void CreateVaultMark(Transform parent, Vector3 position)
        {
            CreateVisualBox(parent, "CuteHorrorVaultMark", position, new Vector3(3f, 0.04f, 0.18f), AccentColor);
            CreateVisualBox(parent, "CuteHorrorVaultMarkEye", position + new Vector3(0f, 0.02f, -0.35f), new Vector3(0.18f, 0.04f, 0.18f), AccentColor);
        }

        private static void CreateTrim(Transform parent, Vector3 position, Vector3 size)
        {
            CreateVisualBox(parent, "VaultTrim", position, size, AccentColor);
        }

        private static void CreateVisualBox(Transform parent, string name, Vector3 position, Vector3 size, Color color)
        {
            GameObject box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            box.transform.localScale = size;
            box.GetComponent<Renderer>().sharedMaterial = CreateMaterial(color);
            Object.DestroyImmediate(box.GetComponent<Collider>());
        }

        private static void CreateGameplayBox(Transform parent, string name, Vector3 position, Vector3 size, Color unused)
        {
            GameObject box = new GameObject(name);
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            BoxCollider collider = box.AddComponent<BoxCollider>();
            collider.size = size;
        }

        private static void CreateMarker(Transform parent, string name, Vector3 position)
        {
            GameObject marker = new GameObject(name);
            marker.transform.SetParent(parent, false);
            marker.transform.position = position;
        }

        private static Material CreateMaterial(Color color)
        {
            Material material = new Material(Shader.Find("Standard"));
            material.color = color;
            return material;
        }

        private static Transform CreateChild(Transform parent, string name)
        {
            GameObject child = new GameObject(name);
            child.transform.SetParent(parent, false);
            return child.transform;
        }

        private static void BuildLighting()
        {
            GameObject lightObject = new GameObject("Vault Moonlight");
            Light light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.color = new Color(0.32f, 0.25f, 0.5f);
            light.intensity = 0.35f;
            lightObject.transform.rotation = Quaternion.Euler(45f, -35f, 0f);
        }

        private static void BuildCamera()
        {
            GameObject cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            Camera camera = cameraObject.AddComponent<Camera>();
            cameraObject.AddComponent<AudioListener>();
            camera.orthographic = true;
            camera.orthographicSize = 15f;
            cameraObject.transform.position = new Vector3(20f, 24f, 20f);
            cameraObject.transform.LookAt(new Vector3(0f, 0f, 53f));
        }

        private static void EnsureFolder(string folder)
        {
            if (string.IsNullOrWhiteSpace(folder) || AssetDatabase.IsValidFolder(folder))
            {
                return;
            }

            Directory.CreateDirectory(folder);
            AssetDatabase.Refresh();
        }
    }
}
