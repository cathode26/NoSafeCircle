using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor.Rooms
{
    /// <summary>Builds only the Bone Archive authoring scene; it never touches the composed scene.</summary>
    public static class BoneArchiveSceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/Rooms/BoneArchive.unity";

        [MenuItem("No Safe Circle/Rooms/Build Bone Archive Authoring Scene")]
        public static void BuildAndSave()
        {
            BuildInMemoryForTests();
            EditorSceneManager.SaveScene(SceneManager.GetActiveScene(), ScenePath);
            AssetDatabase.SaveAssets();
        }

        public static void BuildInMemoryForTests()
        {
            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            GameObject root = new GameObject("Room_BoneArchive");
            Transform visuals = CreateCategory(root.transform, "Visuals", RoomContentCategory.Visuals);
            Transform geometry = CreateCategory(root.transform, "GameplayGeometry", RoomContentCategory.GameplayGeometry);
            Transform anchors = CreateCategory(root.transform, "DoorAnchors", RoomContentCategory.DoorAnchors);
            CreateCategory(root.transform, "Authoring", RoomContentCategory.Authoring);

            CreateVisualAndCollision("Floor", visuals, geometry, new Vector3(0f, -0.25f, 10f), new Vector3(20f, 0.5f, 20f), Color.gray);
            CreatePerimeter(visuals, geometry);
            CreateVisualAndCollision("Shelf A", visuals, geometry, BoneArchiveLayout.ShelfA.center, BoneArchiveLayout.ShelfA.size, new Color(0.22f, 0.12f, 0.08f));
            CreateVisualAndCollision("Shelf B", visuals, geometry, BoneArchiveLayout.ShelfB.center, BoneArchiveLayout.ShelfB.size, new Color(0.22f, 0.12f, 0.08f));
            CreateVisualAndCollision("Shelf C", visuals, geometry, BoneArchiveLayout.ShelfC.center, BoneArchiveLayout.ShelfC.size, new Color(0.22f, 0.12f, 0.08f));
            CreateVisualAndCollision("Collapsed Furniture BA-1", visuals, geometry, BoneArchiveLayout.CollapsedFurnitureBA1.center, BoneArchiveLayout.CollapsedFurnitureBA1.size, new Color(0.28f, 0.18f, 0.12f));
            CreateAnchor("D1Anchor", anchors, BoneArchiveLayout.D1, Vector3.back, DoorId.D1, DoorAnchorRole.Entry);
            CreateAnchor("D2Anchor", anchors, BoneArchiveLayout.D2, Vector3.forward, DoorId.D2, DoorAnchorRole.Exit);
            SceneManager.SetActiveScene(scene);
        }

        private static void CreatePerimeter(Transform visuals, Transform geometry)
        {
            CreateOpeningWall("SouthWall", visuals, geometry, 0f, 0f);
            CreateOpeningWall("NorthWall", visuals, geometry, 6f, 20f);
            CreateVisualAndCollision("WestWall", visuals, geometry, new Vector3(-10.25f, 1.25f, 10f), new Vector3(0.5f, 2.5f, 20f), Color.black);
            CreateVisualAndCollision("EastWall", visuals, geometry, new Vector3(10.25f, 1.25f, 10f), new Vector3(0.5f, 2.5f, 20f), Color.black);
        }

        private static void CreateOpeningWall(string name, Transform visuals, Transform geometry, float openingCenter, float z)
        {
            float roomMinX = BoneArchiveLayout.RoomBounds.min.x;
            float roomMaxX = BoneArchiveLayout.RoomBounds.max.x;
            float openingHalfWidth = BoneArchiveLayout.DoorWidth * 0.5f;
            float westLength = openingCenter - openingHalfWidth - roomMinX;
            float eastLength = roomMaxX - openingCenter - openingHalfWidth;
            float y = BoneArchiveLayout.WallHeight * 0.5f;
            CreateVisualAndCollision(name + "West", visuals, geometry, new Vector3(roomMinX + westLength * 0.5f, y, z), new Vector3(westLength, BoneArchiveLayout.WallHeight, BoneArchiveLayout.WallThickness), Color.black);
            CreateVisualAndCollision(name + "East", visuals, geometry, new Vector3(roomMaxX - eastLength * 0.5f, y, z), new Vector3(eastLength, BoneArchiveLayout.WallHeight, BoneArchiveLayout.WallThickness), Color.black);
        }

        private static void CreateVisualAndCollision(string name, Transform visuals, Transform geometry, Vector3 position, Vector3 size, Color color)
        {
            GameObject visual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            visual.name = name + "Visual";
            visual.transform.SetParent(visuals, false);
            visual.transform.position = position;
            visual.transform.localScale = size;
            visual.GetComponent<Renderer>().sharedMaterial = CreateMaterial(color);
            Object.DestroyImmediate(visual.GetComponent<Collider>());

            GameObject collision = new GameObject(name + "Collision");
            collision.transform.SetParent(geometry, false);
            collision.transform.position = position;
            collision.AddComponent<BoxCollider>().size = size;
        }

        private static Transform CreateCategory(Transform parent, string name, RoomContentCategory category)
        {
            GameObject child = new GameObject(name);
            child.transform.SetParent(parent, false);
            RoomContentMarker marker = child.AddComponent<RoomContentMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.BoneArchive;
            serialized.FindProperty("category").enumValueIndex = (int)category;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            return child.transform;
        }

        private static void CreateAnchor(string name, Transform parent, Vector3 position, Vector3 forward, DoorId doorId, DoorAnchorRole role)
        {
            GameObject anchor = new GameObject(name);
            anchor.transform.SetParent(parent, false);
            anchor.transform.position = position;
            anchor.transform.forward = forward;
            DoorAnchorMarker marker = anchor.AddComponent<DoorAnchorMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.BoneArchive;
            serialized.FindProperty("doorId").enumValueIndex = (int)doorId;
            serialized.FindProperty("role").enumValueIndex = (int)role;
            serialized.FindProperty("openingWidth").floatValue = BoneArchiveLayout.DoorWidth;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static Material CreateMaterial(Color color)
        {
            Material material = new Material(Shader.Find("Standard"));
            material.color = color;
            return material;
        }
    }
}
