using System.IO;
using NoSafeCircle.DoorPrototype.World;
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
            Transform visuals = CreateCategory(root.transform, "Visuals", RoomContentCategory.Visuals);
            Transform geometry = CreateCategory(root.transform, "GameplayGeometry", RoomContentCategory.GameplayGeometry);
            Transform anchors = CreateCategory(root.transform, "DoorAnchors", RoomContentCategory.DoorAnchors);
            Transform authoring = CreateCategory(root.transform, "Authoring", RoomContentCategory.Authoring);
            GameObject dressingObject = new GameObject("FittingRoomDressing");
            dressingObject.transform.SetParent(visuals, false);
            Transform dressing = dressingObject.transform;

            CreateBox("FloorVisual", visuals.transform,
                FinalRoomLayout.RoomBounds.center + Vector3.down * 0.05f,
                new Vector3(FinalRoomLayout.RoomBounds.size.x, 0.1f, FinalRoomLayout.RoomBounds.size.z),
                new Color(0.055f, 0.04f, 0.075f), false);
            CreateBox("FloorCollision", geometry.transform,
                FinalRoomLayout.RoomBounds.center + Vector3.down * 0.05f,
                new Vector3(FinalRoomLayout.RoomBounds.size.x, 0.1f, FinalRoomLayout.RoomBounds.size.z),
                Color.clear, true);

            CreatePerimeter(visuals, false);
            CreatePerimeter(geometry, true);
            CreateObstacle(visuals, false);
            CreateObstacle(geometry, true);
            CreateFittingRoomDressing(dressing, geometry);

            CreateAnchor("D4Anchor", anchors, FinalRoomLayout.D4, Vector3.back, DoorId.D4, DoorAnchorRole.Entry);
            CreateAnchor("D5Anchor", anchors, FinalRoomLayout.D5, Vector3.forward, DoorId.D5, DoorAnchorRole.Exit);
            GameObject staging = new GameObject("D5Staging");
            staging.transform.SetParent(authoring, false);
            staging.transform.position = FinalRoomLayout.NorthStagingBounds.center;
            SceneManager.SetActiveScene(scene);
        }

        private static void CreatePerimeter(Transform parent, bool collision)
        {
            float y = FinalRoomLayout.WallHeight * 0.5f;
            float depth = FinalRoomLayout.MaximumZ - FinalRoomLayout.MinimumZ;
            CreateBox("WestWall" + Suffix(collision), parent,
                new Vector3(FinalRoomLayout.MinimumX, y, FinalRoomLayout.RoomBounds.center.z),
                new Vector3(FinalRoomLayout.WallThickness, FinalRoomLayout.WallHeight, depth), WallColor, collision);
            CreateBox("EastWall" + Suffix(collision), parent,
                new Vector3(FinalRoomLayout.MaximumX, y, FinalRoomLayout.RoomBounds.center.z),
                new Vector3(FinalRoomLayout.WallThickness, FinalRoomLayout.WallHeight, depth), WallColor, collision);
            CreateOpeningWall("SouthWall", parent, FinalRoomLayout.D4X, FinalRoomLayout.MinimumZ, collision);
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

        private static void CreateFittingRoomDressing(Transform parent, Transform gameplay)
        {
            // Low, visual-only dressing keeps the single hard-cover obstacle and routes intact.
            CreateBox("NorthExitSigil", parent, new Vector3(0f, 0.025f, 83.5f), new Vector3(6f, 0.04f, 0.08f), new Color(0.65f, 0.22f, 0.55f), false);
            CreateBox("WestMirror", parent, new Vector3(-10.9f, 1.15f, 76f), new Vector3(0.08f, 1.4f, 2.8f), new Color(0.2f, 0.45f, 0.55f), false);
            CreateBox("EastMirror", parent, new Vector3(10.9f, 1.15f, 76f), new Vector3(0.08f, 1.4f, 2.8f), new Color(0.2f, 0.45f, 0.55f), false);
            CreateBox("WestBench", parent, FinalRoomLayout.WestBenchBounds.center, FinalRoomLayout.WestBenchBounds.size, new Color(0.23f, 0.12f, 0.16f), false);
            CreateBox("EastBench", parent, FinalRoomLayout.EastBenchBounds.center, FinalRoomLayout.EastBenchBounds.size, new Color(0.23f, 0.12f, 0.16f), false);
            CreateBox("WestBenchCollision", gameplay, FinalRoomLayout.WestBenchBounds.center, FinalRoomLayout.WestBenchBounds.size, Color.clear, true);
            CreateBox("EastBenchCollision", gameplay, FinalRoomLayout.EastBenchBounds.center, FinalRoomLayout.EastBenchBounds.size, Color.clear, true);
            CreateBox("FR1Ribbon", parent, new Vector3(0f, 1.15f, 78.5f), new Vector3(4.5f, 0.08f, 0.08f), new Color(0.7f, 0.28f, 0.5f), false);
            for (int i = 0; i < 5; i++)
            {
                float x = -8f + i * 4f;
                CreateCandle("Candle" + (i + 1), parent, new Vector3(x, 0f, 82f));
            }
        }

        private static void CreateCandle(string name, Transform parent, Vector3 groundPosition)
        {
            GameObject root = new GameObject(name);
            root.transform.SetParent(parent, false);
            root.transform.position = groundPosition;

            GameObject wax = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            wax.name = "Wax";
            wax.transform.SetParent(root.transform, false);
            wax.transform.localPosition = new Vector3(0f, 0.16f, 0f);
            wax.transform.localScale = new Vector3(0.12f, 0.16f, 0.12f);
            wax.GetComponent<Renderer>().sharedMaterial = CreateMaterial(new Color(0.72f, 0.55f, 0.32f));
            Object.DestroyImmediate(wax.GetComponent<Collider>());

            GameObject flame = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            flame.name = "Flame";
            flame.transform.SetParent(root.transform, false);
            flame.transform.localPosition = new Vector3(0f, 0.38f, 0f);
            flame.transform.localScale = new Vector3(0.09f, 0.15f, 0.09f);
            flame.GetComponent<Renderer>().sharedMaterial = CreateMaterial(new Color(1f, 0.35f, 0.05f));
            Object.DestroyImmediate(flame.GetComponent<Collider>());

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

        private static void CreateAnchor(
            string name, Transform parent, Vector3 position, Vector3 forward, DoorId doorId, DoorAnchorRole role)
        {
            GameObject anchor = new GameObject(name);
            anchor.transform.SetParent(parent, false);
            anchor.transform.position = position;
            anchor.transform.forward = forward;
            DoorAnchorMarker marker = anchor.AddComponent<DoorAnchorMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.FinalRoom;
            serialized.FindProperty("doorId").enumValueIndex = (int)doorId;
            serialized.FindProperty("role").enumValueIndex = (int)role;
            serialized.FindProperty("openingWidth").floatValue = FinalRoomLayout.DoorOpeningWidth;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static Transform CreateCategory(Transform parent, string name, RoomContentCategory category)
        {
            GameObject child = new GameObject(name);
            child.transform.SetParent(parent, false);
            RoomContentMarker marker = child.AddComponent<RoomContentMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.FinalRoom;
            serialized.FindProperty("category").enumValueIndex = (int)category;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            return child.transform;
        }

        private static string Suffix(bool collision) => collision ? "Collision" : "Visual";
        private static readonly Color WallColor = new Color(0.09f, 0.07f, 0.12f);

        private static Material CreateMaterial(Color color)
        {
            var material = new Material(Shader.Find("Standard"));
            material.color = color;
            return material;
        }

    }

}
