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
    public static class RuinedEntrySceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/Rooms/RuinedEntry.unity";

        private const string RoomRootName = "Room_RuinedEntry";
        private const string VisualRootName = "Visuals";
        private const string GameplayRootName = "GameplayGeometry";
        private const string DoorMarkerName = "D1Opening";

        [MenuItem("No Safe Circle/Rooms/Build Ruined Entry")]
        public static void Build()
        {
            EnsureFolder(Path.GetDirectoryName(ScenePath)?.Replace('\\', '/'));

            Scene scene = File.Exists(ScenePath)
                ? EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single)
                : EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            RebuildSceneContents(scene);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.Refresh();

            Debug.Log($"Ruined Entry scene built at {ScenePath}");
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

            GameObject roomRoot = new GameObject(RoomRootName);
            roomRoot.AddComponent<RuinedEntryLayout>();

            Transform visibleRoot = CreateContentRoot(
                roomRoot.transform, VisualRootName, RoomContentCategory.Visuals);
            Transform gameplayRoot = CreateContentRoot(
                roomRoot.transform, GameplayRootName, RoomContentCategory.GameplayGeometry);
            Transform anchorsRoot = CreateContentRoot(
                roomRoot.transform, "DoorAnchors", RoomContentCategory.DoorAnchors);
            Transform authoringRoot = CreateContentRoot(
                roomRoot.transform, "Authoring", RoomContentCategory.Authoring);

            BuildVisibleBlockout(visibleRoot);
            BuildGameplayGeometry(gameplayRoot);
            CreateDoorAnchor(
                anchorsRoot,
                DoorMarkerName,
                DoorId.D1,
                DoorAnchorRole.Exit,
                new Vector3(RuinedEntryLayout.DoorCenterX, 0f, RuinedEntryLayout.DoorCenterZ),
                Quaternion.LookRotation(Vector3.forward));
            CreateMarker(authoringRoot, "D1StagingArea", RuinedEntryLayout.DoorStagingBounds.center);
        }

        private static void BuildVisibleBlockout(Transform parent)
        {
            CreateVisualBox(parent, "FloorVisual", RuinedEntryLayout.RoomBounds.center + Vector3.down * 0.05f,
                new Vector3(RuinedEntryLayout.RoomBounds.size.x, 0.1f, RuinedEntryLayout.RoomBounds.size.z));

            CreateShellBoxes(parent, "Visual", CreateVisualBox);
            CreateVisualBox(parent, "RubbleAVisual", RaisedCenter(RuinedEntryLayout.RubbleABounds,
                    RuinedEntryLayout.RubbleHeight),
                RaisedSize(RuinedEntryLayout.RubbleABounds, RuinedEntryLayout.RubbleHeight));
            CreateVisualBox(parent, "RubbleBVisual", RaisedCenter(RuinedEntryLayout.RubbleBBounds,
                    RuinedEntryLayout.RubbleHeight),
                RaisedSize(RuinedEntryLayout.RubbleBBounds, RuinedEntryLayout.RubbleHeight));
        }

        private static void BuildGameplayGeometry(Transform parent)
        {
            CreateGameplayBox(parent, "FloorCollision",
                RuinedEntryLayout.RoomBounds.center + Vector3.down * 0.05f,
                new Vector3(RuinedEntryLayout.RoomBounds.size.x, 0.1f, RuinedEntryLayout.RoomBounds.size.z));

            CreateShellBoxes(parent, "Collision", CreateGameplayBox);
            CreateGameplayBox(parent, "RubbleACollision",
                RaisedCenter(RuinedEntryLayout.RubbleABounds, RuinedEntryLayout.RubbleHeight),
                RaisedSize(RuinedEntryLayout.RubbleABounds, RuinedEntryLayout.RubbleHeight));
            CreateGameplayBox(parent, "RubbleBCollision",
                RaisedCenter(RuinedEntryLayout.RubbleBBounds, RuinedEntryLayout.RubbleHeight),
                RaisedSize(RuinedEntryLayout.RubbleBBounds, RuinedEntryLayout.RubbleHeight));
        }

        private static void CreateShellBoxes(
            Transform parent,
            string suffix,
            System.Action<Transform, string, Vector3, Vector3> createBox)
        {
            float centerY = RuinedEntryLayout.WallHeight * 0.5f;
            float roomWidth = RuinedEntryLayout.MaximumX - RuinedEntryLayout.MinimumX;
            float roomDepth = RuinedEntryLayout.MaximumZ - RuinedEntryLayout.MinimumZ;

            createBox(parent, "WestWall" + suffix,
                new Vector3(RuinedEntryLayout.MinimumX, centerY, RuinedEntryLayout.RoomBounds.center.z),
                new Vector3(RuinedEntryLayout.WallThickness, RuinedEntryLayout.WallHeight, roomDepth));
            createBox(parent, "EastWall" + suffix,
                new Vector3(RuinedEntryLayout.MaximumX, centerY, RuinedEntryLayout.RoomBounds.center.z),
                new Vector3(RuinedEntryLayout.WallThickness, RuinedEntryLayout.WallHeight, roomDepth));
            createBox(parent, "SouthWall" + suffix,
                new Vector3(RuinedEntryLayout.RoomBounds.center.x, centerY, RuinedEntryLayout.MinimumZ),
                new Vector3(roomWidth, RuinedEntryLayout.WallHeight, RuinedEntryLayout.WallThickness));

            float northSegmentWidth = (roomWidth - RuinedEntryLayout.DoorOpeningWidth) * 0.5f;
            float northOffset = (RuinedEntryLayout.DoorOpeningWidth + northSegmentWidth) * 0.5f;
            createBox(parent, "NorthWallWest" + suffix,
                new Vector3(-northOffset, centerY, RuinedEntryLayout.MaximumZ),
                new Vector3(northSegmentWidth, RuinedEntryLayout.WallHeight, RuinedEntryLayout.WallThickness));
            createBox(parent, "NorthWallEast" + suffix,
                new Vector3(northOffset, centerY, RuinedEntryLayout.MaximumZ),
                new Vector3(northSegmentWidth, RuinedEntryLayout.WallHeight, RuinedEntryLayout.WallThickness));
        }

        private static Transform CreateContentRoot(
            Transform parent,
            string name,
            RoomContentCategory category)
        {
            GameObject child = new GameObject(name);
            child.transform.SetParent(parent, false);

            RoomContentMarker marker = child.AddComponent<RoomContentMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.RuinedEntry;
            serialized.FindProperty("category").enumValueIndex = (int)category;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            return child.transform;
        }

        private static void CreateVisualBox(Transform parent, string name, Vector3 position, Vector3 size)
        {
            GameObject box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.transform.SetParent(parent, false);
            box.transform.position = position;
            box.transform.localScale = size;
            Object.DestroyImmediate(box.GetComponent<Collider>());
        }

        private static void CreateGameplayBox(Transform parent, string name, Vector3 position, Vector3 size)
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

        private static void CreateDoorAnchor(
            Transform parent,
            string name,
            DoorId doorId,
            DoorAnchorRole role,
            Vector3 position,
            Quaternion rotation)
        {
            GameObject anchor = new GameObject(name);
            anchor.transform.SetParent(parent, false);
            anchor.transform.SetPositionAndRotation(position, rotation);

            DoorAnchorMarker marker = anchor.AddComponent<DoorAnchorMarker>();
            SerializedObject serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)RoomId.RuinedEntry;
            serialized.FindProperty("doorId").enumValueIndex = (int)doorId;
            serialized.FindProperty("role").enumValueIndex = (int)role;
            serialized.FindProperty("openingWidth").floatValue = 3f;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static Vector3 RaisedCenter(Bounds bounds, float height)
        {
            return new Vector3(bounds.center.x, height * 0.5f, bounds.center.z);
        }

        private static Vector3 RaisedSize(Bounds bounds, float height)
        {
            return new Vector3(bounds.size.x, height, bounds.size.z);
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
