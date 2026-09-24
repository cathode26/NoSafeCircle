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
        internal const string DressingPrefabDirectory =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/RoomDressing/";
        internal const string DressingRootName = "RoomDressing";

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

            InstantiateRoomDressing(targetScene, catalog);

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

        /// <summary>Places each room's authored dressing into the composed scene.</summary>
        /// <remarks>
        /// NSC-079/080/081/082/083. The builders turn the Art Director's catalogs into prefabs;
        /// without this step those prefabs exist as assets and the composed scene stays bare, which
        /// is exactly the state the project sat in while five catalogs and five builders were all
        /// on main.
        /// <para>
        /// PARENTED AT IDENTITY UNDER ITS OWN ROOT, deliberately. Catalog placements are WORLD
        /// coordinates -- Ruined Entry's span X[-14,14] Z[-26,0] is where the room actually sits in
        /// the composed scene -- so parenting under a room root that carried any transform would
        /// silently double-offset every prop. A dedicated root at identity cannot.
        /// </para>
        /// <para>
        /// A MISSING PREFAB THROWS RATHER THAN SKIPPING. Skipping would compose a bare room and
        /// report success, which is the failure this project keeps meeting: a green result that is
        /// not evidence of the thing. If a room has no dressing prefab, the scene build should stop
        /// and say which room.
        /// </para>
        /// </remarks>
        private static void InstantiateRoomDressing(Scene targetScene, RoomSceneCatalog catalog)
        {
            var existing = FindSceneRoot(targetScene, DressingRootName);
            if (existing != null) UnityEngine.Object.DestroyImmediate(existing);

            var dressingRoot = new GameObject(DressingRootName);
            SceneManager.MoveGameObjectToScene(dressingRoot, targetScene);
            dressingRoot.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            dressingRoot.transform.localScale = Vector3.one;

            foreach (var room in catalog.Rooms)
            {
                var prefabPath = DressingPrefabDirectory + room.RoomId + "Dressing.prefab";
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
                if (prefab == null)
                {
                    throw new InvalidOperationException(
                        $"No dressing prefab for {room.RoomId} at {prefabPath}. Build it with " +
                        $"NoSafeCircle.DoorPrototype.Editor.Environment.{room.RoomId}DressingPrefabBuilder.Build " +
                        "before composing; composing without it would produce a bare room and report success.");
                }

                var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, targetScene);
                instance.name = room.RoomId + "Dressing";
                instance.transform.SetParent(dressingRoot.transform, false);
                instance.transform.localPosition = Vector3.zero;
                instance.transform.localRotation = Quaternion.identity;
                instance.transform.localScale = Vector3.one;
            }
        }

        private static GameObject FindSceneRoot(Scene scene, string rootName)
        {
            foreach (var root in scene.GetRootGameObjects())
            {
                if (root.name == rootName) return root;
            }
            return null;
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
            // Rebuilding an already-materialized scene leaves the previously generated D2-D5
            // roots behind because the legacy builder only owns DoorRoot (D1). Remove those
            // exact generated roots before cloning the sequence again so Build() is idempotent.
            var legacyNames = new HashSet<string>
            {
                "Floor", "Walls", "IsometricVisualGrid", "D2", "D3", "D4", "D5"
            };
            foreach (var root in scene.GetRootGameObjects())
            {
                if (legacyNames.Contains(root.name)) UnityEngine.Object.DestroyImmediate(root);
            }
        }
    }
}
