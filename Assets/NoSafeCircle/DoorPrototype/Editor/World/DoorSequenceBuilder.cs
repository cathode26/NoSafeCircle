using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Editor.World
{
    // NSC-049 AC-001/AC-002: materializes the approved five-room composition in the canonical
    // scene. DoorInteractable remains the owner of each door's semantic and crossing state;
    // this builder supplies only authored identity, placement, and scene composition.
    internal static class DoorSequenceBuilder
    {
        internal const string CanonicalScenePath = "Assets/Scenes/DoorPrototype.unity";

        internal static void BuildCanonical(Scene targetScene, GameObject existingD1)
        {
            if (targetScene.path != CanonicalScenePath) return;

            var catalog = RoomSceneCatalog.LoadOrBuildAsset();
            if (!RoomSceneComposer.ValidateFixedRoomOrder(catalog.Rooms, out var orderError))
            {
                throw new InvalidOperationException(orderError);
            }

            foreach (var room in catalog.Rooms)
            {
                if (!RoomSceneComposer.TryComposeRoom(catalog, room.RoomId, targetScene, out var validation))
                {
                    throw new InvalidOperationException(
                        $"Cannot compose {room.RoomId}:\n{string.Join("\n", validation.Errors)}");
                }
            }

            RemoveLegacyEnvironmentRoots(targetScene);
            ConfigureDoor(existingD1, DoorId.D1, false, catalog.Doors[0].ExpectedGroundCenter);

            var doorParent = existingD1.transform.parent;
            for (var index = 1; index < catalog.Doors.Count; index++)
            {
                var entry = catalog.Doors[index];
                var clone = UnityEngine.Object.Instantiate(existingD1, doorParent);
                clone.name = entry.DoorId.ToString();
                ConfigureDoor(clone, entry.DoorId, entry.IsFinal, entry.ExpectedGroundCenter);
            }
        }

        private static void ConfigureDoor(GameObject doorRoot, DoorId doorId, bool isFinal, Vector2 groundCenter)
        {
            if (doorRoot == null) throw new ArgumentNullException(nameof(doorRoot));

            doorRoot.name = doorId == DoorId.D1 ? "DoorRoot" : doorId.ToString();
            doorRoot.transform.position = new Vector3(groundCenter.x, 0f, groundCenter.y);

            var door = doorRoot.GetComponent<DoorInteractable>();
            if (door == null) throw new InvalidOperationException($"'{doorRoot.name}' has no DoorInteractable.");

            var serialized = new SerializedObject(door);
            serialized.FindProperty("doorId").enumValueIndex = (int)doorId;
            serialized.FindProperty("isFinalDoor").boolValue = isFinal;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static void RemoveLegacyEnvironmentRoots(Scene scene)
        {
            var legacyNames = new HashSet<string> { "Floor", "Walls", "IsometricVisualGrid" };
            foreach (var root in scene.GetRootGameObjects())
            {
                if (legacyNames.Contains(root.name)) UnityEngine.Object.DestroyImmediate(root);
            }
        }
    }
}
