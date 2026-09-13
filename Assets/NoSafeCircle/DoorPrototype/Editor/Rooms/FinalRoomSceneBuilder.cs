using System.IO;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor.Rooms
{
    /// <summary>Builds only the Final Room authoring scene; it never touches the canonical scene.</summary>
    public static class FinalRoomSceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/Rooms/FinalRoom.unity";

        [MenuItem("No Safe Circle/Rooms/Build Final Room Authoring Scene")]
        public static void BuildAndSave()
        {
            BuildInMemoryForTests();
            EditorSceneManager.SaveScene(SceneManager.GetActiveScene(), ScenePath);
            AssetDatabase.SaveAssets();
        }

        public static void BuildInMemoryForTests()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var root = new GameObject("Room_FinalRoom");
            var visuals = CreateChild("VisualBlockout", root.transform);
            var geometry = CreateChild("GameplayGeometry", root.transform);
            var anchors = CreateChild("DoorAnchors", root.transform);
            var dressing = CreateChild("FittingRoomDressing", visuals.transform);

            CreateBox("FloorVisual", visuals.transform,
                FinalRoomLayout.RoomBounds.center + Vector3.down * 0.05f,
                new Vector3(FinalRoomLayout.RoomBounds.size.x, 0.1f, FinalRoomLayout.RoomBounds.size.z),
                new Color(0.055f, 0.04f, 0.075f), false);
            CreateBox("FloorCollision", geometry.transform,
                FinalRoomLayout.RoomBounds.center + Vector3.down * 0.05f,
                new Vector3(FinalRoomLayout.RoomBounds.size.x, 0.1f, FinalRoomLayout.RoomBounds.size.z),
                Color.clear, true);

            CreatePerimeter(visuals.transform, false);
            CreatePerimeter(geometry.transform, true);
            CreateObstacle(visuals.transform, false);
            CreateObstacle(geometry.transform, true);
            CreateFittingRoomDressing(dressing.transform);

            CreateAnchor("D4", anchors.transform, FinalRoomLayout.D4, Vector3.forward);
            CreateAnchor("D5Final", anchors.transform, FinalRoomLayout.D5, Vector3.back);
            CreateAnchor("D5Staging", anchors.transform, FinalRoomLayout.NorthStagingBounds.center, Vector3.back);
            BuildLighting();
            BuildCamera();
            SceneManager.SetActiveScene(scene);
        }

        private static void CreatePerimeter(Transform parent, bool collision)
        {
            float y = FinalRoomLayout.WallHeight * 0.5f;
            float width = FinalRoomLayout.MaximumX - FinalRoomLayout.MinimumX;
            float depth = FinalRoomLayout.MaximumZ - FinalRoomLayout.MinimumZ;
            CreateBox("WestWall" + Suffix(collision), parent,
                new Vector3(FinalRoomLayout.MinimumX, y, FinalRoomLayout.RoomBounds.center.z),
                new Vector3(FinalRoomLayout.WallThickness, FinalRoomLayout.WallHeight, depth), WallColor, collision);
            CreateBox("EastWall" + Suffix(collision), parent,
                new Vector3(FinalRoomLayout.MaximumX, y, FinalRoomLayout.RoomBounds.center.z),
                new Vector3(FinalRoomLayout.WallThickness, FinalRoomLayout.WallHeight, depth), WallColor, collision);
            CreateBox("SouthWall" + Suffix(collision), parent,
                new Vector3(FinalRoomLayout.RoomBounds.center.x, y, FinalRoomLayout.MinimumZ),
                new Vector3(width, FinalRoomLayout.WallHeight, FinalRoomLayout.WallThickness), WallColor, collision);
            CreateOpeningWall("NorthWall", parent, FinalRoomLayout.D5X, FinalRoomLayout.MaximumZ, collision);
        }

        private static void CreateOpeningWall(string name, Transform parent, float openingCenter, float z, bool collision)
        {
            float halfOpening = FinalRoomLayout.DoorOpeningWidth * 0.5f;
            float westLength = openingCenter - halfOpening - FinalRoomLayout.MinimumX;
            float eastLength = FinalRoomLayout.MaximumX - openingCenter - halfOpening;
            float y = FinalRoomLayout.WallHeight * 0.5f;
            CreateBox(name + "West" + Suffix(collision), parent,
                new Vector3(FinalRoomLayout.MinimumX + westLength * 0.5f, y, z),
                new Vector3(westLength, FinalRoomLayout.WallHeight, FinalRoomLayout.WallThickness), WallColor, collision);
            CreateBox(name + "East" + Suffix(collision), parent,
                new Vector3(FinalRoomLayout.MaximumX - eastLength * 0.5f, y, z),
                new Vector3(eastLength, FinalRoomLayout.WallHeight, FinalRoomLayout.WallThickness), WallColor, collision);
        }

        private static void CreateObstacle(Transform parent, bool collision)
        {
            CreateBox("FR-1" + Suffix(collision), parent,
                FinalRoomLayout.FinalObstacleBounds.center,
                FinalRoomLayout.FinalObstacleBounds.size,
                new Color(0.16f, 0.08f, 0.2f), collision);
        }

        private static void CreateFittingRoomDressing(Transform parent)
        {
            // Low, visual-only dressing keeps the single hard-cover obstacle and routes intact.
            CreateBox("NorthExitSigil", parent, new Vector3(0f, 0.025f, 83.5f), new Vector3(6f, 0.04f, 0.08f), new Color(0.65f, 0.22f, 0.55f), false);
            CreateBox("WestMirror", parent, new Vector3(-10.9f, 1.15f, 76f), new Vector3(0.08f, 1.4f, 2.8f), new Color(0.2f, 0.45f, 0.55f), false);
            CreateBox("EastMirror", parent, new Vector3(10.9f, 1.15f, 76f), new Vector3(0.08f, 1.4f, 2.8f), new Color(0.2f, 0.45f, 0.55f), false);
            CreateBox("WestBench", parent, new Vector3(-8.5f, 0.35f, 68.5f), new Vector3(2.5f, 0.7f, 0.55f), new Color(0.23f, 0.12f, 0.16f), false);
            CreateBox("EastBench", parent, new Vector3(8.5f, 0.35f, 68.5f), new Vector3(2.5f, 0.7f, 0.55f), new Color(0.23f, 0.12f, 0.16f), false);
            CreateBox("FR1Ribbon", parent, new Vector3(0f, 1.15f, 78.5f), new Vector3(4.5f, 0.08f, 0.08f), new Color(0.7f, 0.28f, 0.5f), false);
            for (int i = 0; i < 5; i++)
            {
                float x = -8f + i * 4f;
                CreateBox("Candle" + (i + 1), parent, new Vector3(x, 0.35f, 82f), new Vector3(0.22f, 0.7f, 0.22f), new Color(0.8f, 0.38f, 0.18f), false);
            }
        }

        private static GameObject CreateBox(string name, Transform parent, Vector3 position, Vector3 size, Color color, bool collision)
        {
            GameObject box = collision ? new GameObject(name) : GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            box.transform.localScale = collision ? Vector3.one : size;
            if (collision)
            {
                BoxCollider collider = box.AddComponent<BoxCollider>();
                collider.size = size;
            }
            else
            {
                box.GetComponent<Renderer>().sharedMaterial = CreateMaterial(color);
                Object.DestroyImmediate(box.GetComponent<Collider>());
            }
            return box;
        }

        private static void CreateAnchor(string name, Transform parent, Vector3 position, Vector3 forward)
        {
            var anchor = new GameObject(name + "Anchor");
            anchor.transform.SetParent(parent, false);
            anchor.transform.position = position;
            anchor.transform.forward = forward;
        }

        private static GameObject CreateChild(string name, Transform parent)
        {
            var child = new GameObject(name);
            child.transform.SetParent(parent, false);
            return child;
        }

        private static string Suffix(bool collision) => collision ? "Collision" : "Visual";
        private static readonly Color WallColor = new Color(0.09f, 0.07f, 0.12f);

        private static Material CreateMaterial(Color color)
        {
            var material = new Material(Shader.Find("Standard"));
            material.color = color;
            return material;
        }

        private static void BuildLighting()
        {
            var lightObject = new GameObject("Moonlight");
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.color = new Color(0.38f, 0.48f, 0.8f);
            light.intensity = 0.65f;
            lightObject.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
        }

        private static void BuildCamera()
        {
            var cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            cameraObject.AddComponent<AudioListener>();
            var camera = cameraObject.AddComponent<Camera>();
            camera.orthographic = true;
            camera.orthographicSize = 15f;
            cameraObject.transform.position = new Vector3(20f, 27f, 42f);
            cameraObject.transform.LookAt(new Vector3(0f, 0f, 75f));
        }
    }

}
