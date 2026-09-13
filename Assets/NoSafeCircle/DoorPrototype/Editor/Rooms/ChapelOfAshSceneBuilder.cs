using System.IO;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor.Rooms
{
    /// <summary>Builds the Chapel of Ash authoring scene with separate visual and gameplay layers.</summary>
    public static class ChapelOfAshSceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/Rooms/ChapelOfAsh.unity";

        [MenuItem("No Safe Circle/Rooms/Build Chapel of Ash Authoring Scene")]
        public static void BuildAndSave()
        {
            BuildInMemoryForTests();
            EnsureFolder(Path.GetDirectoryName(ScenePath)?.Replace('\\', '/'));
            EditorSceneManager.SaveScene(SceneManager.GetActiveScene(), ScenePath);
            AssetDatabase.SaveAssets();
        }

        public static void BuildInMemoryForTests()
        {
            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            GameObject roomRoot = new GameObject("Room_ChapelOfAsh");
            Transform visuals = CreateChild("VisibleBlockout", roomRoot.transform);
            Transform gameplay = CreateChild("GameplayGeometry", roomRoot.transform);
            Transform anchors = CreateChild("DoorAnchors", roomRoot.transform);
            Transform authoring = CreateChild("Authoring", roomRoot.transform);

            BuildFloor(visuals, gameplay);
            BuildShell(visuals, gameplay);
            BuildPews(visuals, gameplay);
            BuildColumns(visuals, gameplay);
            CreateMarker(anchors, "D2Anchor", ChapelOfAshLayout.D2, Vector3.forward);
            CreateMarker(anchors, "D3Anchor", ChapelOfAshLayout.D3, Vector3.back);
            CreateMarker(authoring, "CA-W", ChapelOfAshLayout.CoverPocketWest, Vector3.right);
            CreateMarker(authoring, "CA-E", ChapelOfAshLayout.CoverPocketEast, Vector3.left);

            BuildLighting();
            BuildCamera();
            SceneManager.SetActiveScene(scene);
        }

        private static void BuildFloor(Transform visuals, Transform gameplay)
        {
            Vector3 center = ChapelOfAshLayout.RoomBounds.center;
            Vector3 size = new Vector3(ChapelOfAshLayout.RoomBounds.size.x, 0.1f, ChapelOfAshLayout.RoomBounds.size.z);
            CreateVisualBox(visuals, "FloorVisual", center + Vector3.down * 0.05f, size, new Color(0.06f, 0.055f, 0.07f));
            CreateGameplayBox(gameplay, "FloorCollision", center + Vector3.down * 0.05f, size);
        }

        private static void BuildShell(Transform visuals, Transform gameplay)
        {
            float centerY = ChapelOfAshLayout.WallHeight * 0.5f;
            float roomWidth = ChapelOfAshLayout.MaximumX - ChapelOfAshLayout.MinimumX;
            float roomDepth = ChapelOfAshLayout.MaximumZ - ChapelOfAshLayout.MinimumZ;

            CreateWallPair(visuals, gameplay, "SouthWall", ChapelOfAshLayout.D2.x, ChapelOfAshLayout.MinimumZ, true);
            CreateWallPair(visuals, gameplay, "NorthWall", ChapelOfAshLayout.D3.x, ChapelOfAshLayout.MaximumZ, true);
            CreateVisualBox(visuals, "WestWallVisual", new Vector3(ChapelOfAshLayout.MinimumX, centerY, ChapelOfAshLayout.RoomBounds.center.z), new Vector3(ChapelOfAshLayout.WallThickness, ChapelOfAshLayout.WallHeight, roomDepth), new Color(0.07f, 0.06f, 0.08f));
            CreateVisualBox(visuals, "EastWallVisual", new Vector3(ChapelOfAshLayout.MaximumX, centerY, ChapelOfAshLayout.RoomBounds.center.z), new Vector3(ChapelOfAshLayout.WallThickness, ChapelOfAshLayout.WallHeight, roomDepth), new Color(0.07f, 0.06f, 0.08f));
            CreateGameplayBox(gameplay, "WestWallCollision", new Vector3(ChapelOfAshLayout.MinimumX, centerY, ChapelOfAshLayout.RoomBounds.center.z), new Vector3(ChapelOfAshLayout.WallThickness, ChapelOfAshLayout.WallHeight, roomDepth));
            CreateGameplayBox(gameplay, "EastWallCollision", new Vector3(ChapelOfAshLayout.MaximumX, centerY, ChapelOfAshLayout.RoomBounds.center.z), new Vector3(ChapelOfAshLayout.WallThickness, ChapelOfAshLayout.WallHeight, roomDepth));
        }

        private static void CreateWallPair(Transform visuals, Transform gameplay, string name, float openingCenter, float z, bool horizontal)
        {
            float roomMinX = ChapelOfAshLayout.MinimumX;
            float roomMaxX = ChapelOfAshLayout.MaximumX;
            float openingHalfWidth = ChapelOfAshLayout.DoorWidth * 0.5f;
            float westLength = openingCenter - openingHalfWidth - roomMinX;
            float eastLength = roomMaxX - openingCenter - openingHalfWidth;
            float centerY = ChapelOfAshLayout.WallHeight * 0.5f;
            Vector3 westCenter = new Vector3(roomMinX + westLength * 0.5f, centerY, z);
            Vector3 eastCenter = new Vector3(roomMaxX - eastLength * 0.5f, centerY, z);
            Vector3 westSize = new Vector3(westLength, ChapelOfAshLayout.WallHeight, ChapelOfAshLayout.WallThickness);
            Vector3 eastSize = new Vector3(eastLength, ChapelOfAshLayout.WallHeight, ChapelOfAshLayout.WallThickness);
            CreateVisualBox(visuals, name + "WestVisual", westCenter, westSize, new Color(0.07f, 0.06f, 0.08f));
            CreateVisualBox(visuals, name + "EastVisual", eastCenter, eastSize, new Color(0.07f, 0.06f, 0.08f));
            CreateGameplayBox(gameplay, name + "WestCollision", westCenter, westSize);
            CreateGameplayBox(gameplay, name + "EastCollision", eastCenter, eastSize);
        }

        private static void BuildPews(Transform visuals, Transform gameplay)
        {
            for (int index = 0; index < ChapelOfAshLayout.PewFootprints.Length; index++)
            {
                Bounds bounds = ChapelOfAshLayout.PewFootprints[index];
                Color color = index % 2 == 0 ? new Color(0.20f, 0.12f, 0.16f) : new Color(0.25f, 0.14f, 0.17f);
                CreateVisualBox(visuals, "Pew" + (index + 1) + "Visual", bounds.center, bounds.size, color);
                CreateGameplayBox(gameplay, "Pew" + (index + 1) + "Collision", bounds.center, bounds.size);
            }
        }

        private static void BuildColumns(Transform visuals, Transform gameplay)
        {
            for (int index = 0; index < ChapelOfAshLayout.ColumnCenters.Length; index++)
            {
                Bounds bounds = ChapelOfAshLayout.ColumnBounds(ChapelOfAshLayout.ColumnCenters[index]);
                CreateVisualBox(visuals, "Column" + (index + 1) + "Visual", bounds.center, bounds.size, new Color(0.17f, 0.16f, 0.20f));
                CreateGameplayBox(gameplay, "Column" + (index + 1) + "Collision", bounds.center, bounds.size);
            }
        }

        private static GameObject CreateVisualBox(Transform parent, string name, Vector3 position, Vector3 size, Color color)
        {
            GameObject box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            box.transform.localScale = size;
            box.GetComponent<Renderer>().sharedMaterial = CreateMaterial(color);
            Object.DestroyImmediate(box.GetComponent<Collider>());
            return box;
        }

        private static GameObject CreateGameplayBox(Transform parent, string name, Vector3 position, Vector3 size)
        {
            GameObject box = new GameObject(name);
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            BoxCollider collider = box.AddComponent<BoxCollider>();
            collider.size = size;
            return box;
        }

        private static Transform CreateChild(string name, Transform parent)
        {
            GameObject child = new GameObject(name);
            child.transform.SetParent(parent, false);
            return child.transform;
        }

        private static void CreateMarker(Transform parent, string name, Vector3 position, Vector3 forward)
        {
            GameObject marker = new GameObject(name);
            marker.transform.SetParent(parent, false);
            marker.transform.position = position;
            marker.transform.forward = forward;
        }

        private static Material CreateMaterial(Color color)
        {
            Material material = new Material(Shader.Find("Standard"));
            material.color = color;
            return material;
        }

        private static void BuildLighting()
        {
            GameObject lightObject = new GameObject("Directional Light");
            Light light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 0.55f;
            light.color = new Color(0.63f, 0.58f, 0.72f);
            lightObject.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
        }

        private static void BuildCamera()
        {
            GameObject cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            Camera camera = cameraObject.AddComponent<Camera>();
            cameraObject.AddComponent<AudioListener>();
            camera.orthographic = true;
            camera.orthographicSize = 15f;
            cameraObject.transform.position = new Vector3(19f, 25f, 8f);
            cameraObject.transform.LookAt(new Vector3(0f, 0f, 31f));
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
