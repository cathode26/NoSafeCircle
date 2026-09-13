using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;
using UnityEngine;
using NoSafeCircle.DoorPrototype.World.Rooms;

namespace NoSafeCircle.DoorPrototype.Editor.Rooms
{
    /// <summary>Builds only the Bone Archive authoring scene; it never touches the canonical scene.</summary>
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
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var root = new GameObject("Room_BoneArchive");
            CreateChild("Visuals", root.transform);
            var geometry = CreateChild("GameplayGeometry", root.transform);
            var anchors = CreateChild("DoorAnchors", root.transform);
            CreateChild("Authoring", root.transform);

            CreateBox("Floor", geometry.transform, new Vector3(0f, -0.25f, 10f), new Vector3(20f, 0.5f, 20f), Color.gray);
            CreatePerimeter(geometry.transform);
            CreateShelf("Shelf A", geometry.transform, BoneArchiveLayout.ShelfA);
            CreateShelf("Shelf B", geometry.transform, BoneArchiveLayout.ShelfB);
            CreateShelf("Shelf C", geometry.transform, BoneArchiveLayout.ShelfC);
            CreateBox("Collapsed Furniture BA-1", geometry.transform, BoneArchiveLayout.CollapsedFurnitureBA1.center, BoneArchiveLayout.CollapsedFurnitureBA1.size, new Color(0.28f, 0.18f, 0.12f));
            CreateAnchor("D1", anchors.transform, BoneArchiveLayout.D1, Vector3.forward);
            CreateAnchor("D2", anchors.transform, BoneArchiveLayout.D2, Vector3.back);
            SceneManager.SetActiveScene(scene);
        }

        private static void CreatePerimeter(Transform parent)
        {
            CreateOpeningWall("SouthWall", parent, 0f, 0f);
            CreateOpeningWall("NorthWall", parent, 6f, 20f);
            CreateBox("WestWall", parent, new Vector3(-10.25f, 1.25f, 10f), new Vector3(0.5f, 2.5f, 20f), Color.black);
            CreateBox("EastWall", parent, new Vector3(10.25f, 1.25f, 10f), new Vector3(0.5f, 2.5f, 20f), Color.black);
        }

        private static void CreateOpeningWall(string name, Transform parent, float openingCenter, float z)
        {
            var roomMinX = BoneArchiveLayout.RoomBounds.min.x;
            var roomMaxX = BoneArchiveLayout.RoomBounds.max.x;
            var openingHalfWidth = BoneArchiveLayout.DoorWidth * 0.5f;
            var westLength = openingCenter - openingHalfWidth - roomMinX;
            var eastLength = roomMaxX - openingCenter - openingHalfWidth;
            var y = 1.25f;
            CreateBox(name + "West", parent, new Vector3(roomMinX + westLength * 0.5f, y, z), new Vector3(westLength, BoneArchiveLayout.WallHeight, BoneArchiveLayout.WallThickness), Color.black);
            CreateBox(name + "East", parent, new Vector3(roomMaxX - eastLength * 0.5f, y, z), new Vector3(eastLength, BoneArchiveLayout.WallHeight, BoneArchiveLayout.WallThickness), Color.black);
        }

        private static void CreateShelf(string name, Transform parent, Bounds bounds)
        {
            CreateBox(name, parent, bounds.center, bounds.size, new Color(0.22f, 0.12f, 0.08f));
        }

        private static GameObject CreateBox(string name, Transform parent, Vector3 position, Vector3 size, Color color)
        {
            var box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            box.transform.localScale = size;
            var renderer = box.GetComponent<Renderer>();
            renderer.sharedMaterial = CreateMaterial(color);
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

        private static Material CreateMaterial(Color color)
        {
            var material = new Material(Shader.Find("Standard"));
            material.color = color;
            return material;
        }
    }

}
