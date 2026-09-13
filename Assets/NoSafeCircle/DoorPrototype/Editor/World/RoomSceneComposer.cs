using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.Tilemaps;
using NoSafeCircle.DoorPrototype.World;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor.World
{
    // NSC-069 AC-003/AC-004: deterministic Editor-time validation and composition seam. Room
    // tasks (NSC-044 through NSC-048) never call this directly; NSC-049 uses it to compose the
    // five conformant room source scenes into Assets/Scenes/DoorPrototype.unity. The validation
    // API is intentionally scene/path-agnostic so tests can exercise it against isolated fixture
    // scenes without creating or rewriting the five real room assets.
    public static class RoomSceneComposer
    {
        public const string WorldRootName = "World";
        public const string ComposedRoomsRootName = "ComposedRooms";
        private const string RoomRootNamePrefix = "Room_";

        private const float PositionTolerance = 0.01f;
        private const float WidthTolerance = 0.01f;
        private const float ForwardOppositionTolerance = 0.02f;

        private static readonly Type[] DisallowedComponentTypes =
        {
            typeof(Camera),
            typeof(Light),
            typeof(Canvas),
            typeof(EventSystem),
            typeof(DoorInteractable),
            typeof(ActiveEnemyRegistry),
            typeof(EncounterAdmissionController)
        };

        public sealed class RoomValidationResult
        {
            private readonly List<string> errors = new List<string>();
            private readonly List<DoorAnchorMarker> doorAnchors = new List<DoorAnchorMarker>();

            public IReadOnlyList<string> Errors => errors;
            public bool IsValid => errors.Count == 0;
            public IReadOnlyList<DoorAnchorMarker> DoorAnchors => doorAnchors;
            public GameObject VisualsRoot { get; internal set; }
            public GameObject GameplayGeometryRoot { get; internal set; }
            public GameObject DoorAnchorsRoot { get; internal set; }

            internal void AddError(string message) => errors.Add(message);
            internal void AddDoorAnchor(DoorAnchorMarker marker) => doorAnchors.Add(marker);
        }

        // AC-002/AC-003: validates the identity-transform room root, its Visuals/GameplayGeometry/
        // DoorAnchors/Authoring children, its door anchors against the shared door-sequence
        // contract, the approved sorting convention, disallowed content, and local-reference
        // ownership. Never mutates the scene.
        public static RoomValidationResult ValidateOpenRoomScene(
            RoomId expectedRoomId,
            Scene scene,
            RoomSceneCatalog.RoomCatalogEntry roomEntry,
            IReadOnlyList<RoomSceneCatalog.DoorSequenceEntry> doors)
        {
            var result = new RoomValidationResult();
            var roots = scene.GetRootGameObjects();
            var expectedRootName = RoomRootNamePrefix + expectedRoomId;

            if (roots.Length != 1)
            {
                result.AddError(
                    $"Scene '{scene.path}' must contain exactly one root GameObject, found {roots.Length}.");
            }

            GameObject roomRoot = null;
            foreach (var root in roots)
            {
                if (root.name != expectedRootName) continue;
                if (roomRoot != null)
                {
                    result.AddError($"Scene '{scene.path}' contains more than one '{expectedRootName}' root.");
                }
                roomRoot = root;
            }

            if (roomRoot == null)
            {
                result.AddError($"Scene '{scene.path}' does not contain a '{expectedRootName}' root.");
                return result;
            }

            if (roomRoot.transform.localPosition != Vector3.zero ||
                roomRoot.transform.localRotation != Quaternion.identity ||
                roomRoot.transform.localScale != Vector3.one)
            {
                result.AddError(
                    $"'{expectedRootName}' must be an identity-transform root so its children's authored " +
                    "positions are already canonical world coordinates.");
            }

            ValidateNoDisallowedComponents(roomRoot, result);
            ValidateContentCategories(roomRoot, expectedRoomId, result);
            ValidateSortingConvention(result);
            ValidateDoorAnchors(result, expectedRoomId, roomEntry, doors);
            ValidateLocalReferenceOwnership(roomRoot, scene, result);

            return result;
        }

        // AC-003: cross-room pairing check for a shared door boundary. D1-D4 boundaries require
        // one Exit anchor from the room before the boundary and one Entry anchor from the room
        // after it, sharing one world-space center and opening width with opposing forward
        // vectors. D5 has no pairing partner and is validated only through ValidateOpenRoomScene.
        public static bool ValidateAnchorPairing(DoorAnchorMarker exitAnchor, DoorAnchorMarker entryAnchor, out string error)
        {
            if (exitAnchor == null || entryAnchor == null)
            {
                error = "Both an Exit and an Entry anchor are required to validate a door pairing.";
                return false;
            }

            if (exitAnchor.DoorId != entryAnchor.DoorId)
            {
                error = $"Anchor DoorId mismatch: '{exitAnchor.DoorId}' vs '{entryAnchor.DoorId}'.";
                return false;
            }

            if (exitAnchor.Role != DoorAnchorRole.Exit || entryAnchor.Role != DoorAnchorRole.Entry)
            {
                error = $"'{exitAnchor.DoorId}' pairing requires one Exit anchor and one Entry anchor.";
                return false;
            }

            if (Vector3.Distance(exitAnchor.transform.position, entryAnchor.transform.position) > PositionTolerance)
            {
                error = $"'{exitAnchor.DoorId}' Exit and Entry anchors must share the same world-space center.";
                return false;
            }

            if (Mathf.Abs(exitAnchor.OpeningWidth - entryAnchor.OpeningWidth) > WidthTolerance)
            {
                error = $"'{exitAnchor.DoorId}' Exit and Entry anchors must share the same opening width.";
                return false;
            }

            if (Vector3.Dot(exitAnchor.transform.forward, entryAnchor.transform.forward) > -1f + ForwardOppositionTolerance)
            {
                error = $"'{exitAnchor.DoorId}' Exit and Entry anchor forward vectors must oppose each other.";
                return false;
            }

            error = null;
            return true;
        }

        // AC-001/VAL-001: the catalog's five entries must appear in the fixed south-to-north
        // forward route order from the approved GDD blockout.
        public static bool ValidateFixedRoomOrder(IReadOnlyList<RoomSceneCatalog.RoomCatalogEntry> rooms, out string error)
        {
            var expectedOrder = new[]
            {
                RoomId.RuinedEntry, RoomId.BoneArchive, RoomId.ChapelOfAsh, RoomId.LowerVault, RoomId.FinalRoom
            };

            if (rooms.Count != expectedOrder.Length)
            {
                error = $"Catalog must contain exactly {expectedOrder.Length} rooms, found {rooms.Count}.";
                return false;
            }

            for (var i = 0; i < expectedOrder.Length; i++)
            {
                if (rooms[i].RoomId != expectedOrder[i])
                {
                    error = $"Room at catalog index {i} must be '{expectedOrder[i]}' but was '{rooms[i].RoomId}'.";
                    return false;
                }
            }

            error = null;
            return true;
        }

        // AC-004/VAL-004: none of the room authoring scenes may be an enabled build-settings
        // scene, since they are Editor-only composition inputs.
        public static bool AreRoomScenesExcludedFromBuild(
            IReadOnlyList<RoomSceneCatalog.RoomCatalogEntry> rooms, out List<string> violations)
        {
            violations = new List<string>();
            foreach (var buildScene in EditorBuildSettings.scenes)
            {
                if (!buildScene.enabled) continue;
                foreach (var room in rooms)
                {
                    if (string.Equals(buildScene.path, room.SceneAssetPath, StringComparison.OrdinalIgnoreCase))
                    {
                        violations.Add(room.SceneAssetPath);
                    }
                }
            }

            return violations.Count == 0;
        }

        // AC-004: opens sourceScenePath additively, validates it, clones only its validated
        // Visuals/GameplayGeometry/DoorAnchors content under World/ComposedRooms in targetScene
        // when valid, and always closes the source scene without saving it. Composition never
        // writes to targetScene when validation fails.
        public static bool TryComposeRoom(
            string sourceScenePath,
            RoomId roomId,
            RoomSceneCatalog.RoomCatalogEntry roomEntry,
            IReadOnlyList<RoomSceneCatalog.DoorSequenceEntry> doors,
            Scene targetScene,
            out RoomValidationResult validation)
        {
            if (string.IsNullOrEmpty(sourceScenePath) || !File.Exists(sourceScenePath))
            {
                validation = new RoomValidationResult();
                validation.AddError($"Room source scene '{sourceScenePath}' does not exist.");
                return false;
            }

            var sourceScene = EditorSceneManager.OpenScene(sourceScenePath, OpenSceneMode.Additive);
            try
            {
                validation = ValidateOpenRoomScene(roomId, sourceScene, roomEntry, doors);
                if (!validation.IsValid) return false;

                CloneComposedRoomContent(roomId, validation, targetScene);
                return true;
            }
            finally
            {
                EditorSceneManager.CloseScene(sourceScene, true);
            }
        }

        public static bool TryComposeRoom(
            RoomSceneCatalog catalog, RoomId roomId, Scene targetScene, out RoomValidationResult validation)
        {
            if (catalog == null || !catalog.TryGetRoom(roomId, out var roomEntry))
            {
                validation = new RoomValidationResult();
                validation.AddError($"Catalog does not contain an entry for '{roomId}'.");
                return false;
            }

            return TryComposeRoom(roomEntry.SceneAssetPath, roomId, roomEntry, catalog.Doors, targetScene, out validation);
        }

        private static void ValidateNoDisallowedComponents(GameObject roomRoot, RoomValidationResult result)
        {
            foreach (var disallowedType in DisallowedComponentTypes)
            {
                if (roomRoot.GetComponentInChildren(disallowedType, true) != null)
                {
                    result.AddError($"Room authoring content must not contain a '{disallowedType.Name}' component.");
                }
            }

            foreach (var behaviour in roomRoot.GetComponentsInChildren<MonoBehaviour>(true))
            {
                if (behaviour == null) continue;
                var typeName = behaviour.GetType().Name;
                if (typeName.StartsWith("Player", StringComparison.Ordinal))
                {
                    result.AddError($"Room authoring content must not contain a Player-owned component ('{typeName}').");
                }
            }
        }

        private static void ValidateContentCategories(GameObject roomRoot, RoomId expectedRoomId, RoomValidationResult result)
        {
            GameObject visuals = null;
            GameObject gameplayGeometry = null;
            GameObject doorAnchors = null;

            foreach (Transform child in roomRoot.transform)
            {
                var marker = child.GetComponent<RoomContentMarker>();
                if (marker == null)
                {
                    result.AddError(
                        $"Child '{child.name}' under '{roomRoot.name}' has no RoomContentMarker identifying its category.");
                    continue;
                }

                if (marker.RoomId != expectedRoomId)
                {
                    result.AddError(
                        $"'{child.name}' RoomContentMarker.RoomId is '{marker.RoomId}' but the room root is '{expectedRoomId}'.");
                }

                switch (marker.Category)
                {
                    case RoomContentCategory.Visuals:
                        if (visuals != null) result.AddError("More than one Visuals child was found.");
                        visuals = child.gameObject;
                        break;
                    case RoomContentCategory.GameplayGeometry:
                        if (gameplayGeometry != null) result.AddError("More than one GameplayGeometry child was found.");
                        gameplayGeometry = child.gameObject;
                        break;
                    case RoomContentCategory.DoorAnchors:
                        if (doorAnchors != null) result.AddError("More than one DoorAnchors child was found.");
                        doorAnchors = child.gameObject;
                        break;
                    case RoomContentCategory.Authoring:
                        break;
                }
            }

            if (visuals == null) result.AddError("Missing a Visuals child with a RoomContentMarker.");
            if (gameplayGeometry == null) result.AddError("Missing a GameplayGeometry child with a RoomContentMarker.");
            if (doorAnchors == null) result.AddError("Missing a DoorAnchors child with a RoomContentMarker.");

            result.VisualsRoot = visuals;
            result.GameplayGeometryRoot = gameplayGeometry;
            result.DoorAnchorsRoot = doorAnchors;

            if (doorAnchors == null) return;

            foreach (var anchor in doorAnchors.GetComponentsInChildren<DoorAnchorMarker>(true))
            {
                result.AddDoorAnchor(anchor);
            }
        }

        private static void ValidateSortingConvention(RoomValidationResult result)
        {
            ValidateRendererSortingLayer(result.VisualsRoot, result);
            ValidateRendererSortingLayer(result.GameplayGeometryRoot, result);
        }

        private static void ValidateRendererSortingLayer(GameObject categoryRoot, RoomValidationResult result)
        {
            if (categoryRoot == null) return;

            foreach (var renderer in categoryRoot.GetComponentsInChildren<SpriteRenderer>(true))
            {
                if (renderer.sortingLayerName != DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName)
                {
                    result.AddError(
                        $"SpriteRenderer '{renderer.name}' must use the shared '{DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName}' sorting layer.");
                }
            }

            foreach (var renderer in categoryRoot.GetComponentsInChildren<TilemapRenderer>(true))
            {
                if (renderer.sortingLayerName != DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName)
                {
                    result.AddError(
                        $"TilemapRenderer '{renderer.name}' must use the shared '{DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName}' sorting layer.");
                }
            }
        }

        private static void ValidateDoorAnchors(
            RoomValidationResult result,
            RoomId expectedRoomId,
            RoomSceneCatalog.RoomCatalogEntry roomEntry,
            IReadOnlyList<RoomSceneCatalog.DoorSequenceEntry> doors)
        {
            if (doors == null) return;

            var expectedRoles = new Dictionary<DoorId, DoorAnchorRole>();
            foreach (var door in doors)
            {
                if (door.ExitRoom == expectedRoomId) expectedRoles[door.DoorId] = DoorAnchorRole.Exit;
                if (!door.IsFinal && door.EntryRoom == expectedRoomId) expectedRoles[door.DoorId] = DoorAnchorRole.Entry;
            }

            var foundDoorIds = new HashSet<DoorId>();

            foreach (var anchor in result.DoorAnchors)
            {
                if (anchor.RoomId != expectedRoomId)
                {
                    result.AddError(
                        $"DoorAnchorMarker on '{anchor.name}' has RoomId '{anchor.RoomId}' but the room root is '{expectedRoomId}'.");
                }

                if (!expectedRoles.TryGetValue(anchor.DoorId, out var expectedRole))
                {
                    result.AddError($"'{expectedRoomId}' does not own a door anchor for '{anchor.DoorId}' per the catalog.");
                    continue;
                }

                foundDoorIds.Add(anchor.DoorId);

                if (anchor.Role != expectedRole)
                {
                    result.AddError(
                        $"'{anchor.DoorId}' anchor in '{expectedRoomId}' must have role '{expectedRole}' but has '{anchor.Role}'.");
                }

                RoomSceneCatalog.DoorSequenceEntry matchingDoor = null;
                foreach (var door in doors)
                {
                    if (door.DoorId != anchor.DoorId) continue;
                    matchingDoor = door;
                    break;
                }

                if (matchingDoor == null) continue;

                if (Mathf.Abs(anchor.OpeningWidth - matchingDoor.OpeningWidth) > WidthTolerance)
                {
                    result.AddError(
                        $"'{anchor.DoorId}' opening width must be {matchingDoor.OpeningWidth} but was {anchor.OpeningWidth}.");
                }

                var worldPosition = anchor.transform.position;
                var groundPosition = new Vector2(worldPosition.x, worldPosition.z);
                if (Vector2.Distance(groundPosition, matchingDoor.ExpectedGroundCenter) > PositionTolerance)
                {
                    result.AddError(
                        $"'{anchor.DoorId}' world-space ground center must be {matchingDoor.ExpectedGroundCenter} but was {groundPosition}.");
                }

                if (roomEntry != null && !roomEntry.Bounds.ContainsX(worldPosition.x))
                {
                    result.AddError(
                        $"'{anchor.DoorId}' anchor X position {worldPosition.x} falls outside '{expectedRoomId}' global bounds.");
                }

                if (roomEntry != null)
                {
                    var expectedBoundaryZ = expectedRole == DoorAnchorRole.Exit
                        ? roomEntry.Bounds.MaxZ
                        : roomEntry.Bounds.MinZ;
                    if (Mathf.Abs(worldPosition.z - expectedBoundaryZ) > PositionTolerance)
                    {
                        result.AddError(
                            $"'{anchor.DoorId}' anchor Z position {worldPosition.z} must sit on '{expectedRoomId}'s shared boundary at {expectedBoundaryZ}.");
                    }
                }
            }

            foreach (var expectedDoorId in expectedRoles.Keys)
            {
                if (!foundDoorIds.Contains(expectedDoorId))
                {
                    result.AddError($"'{expectedRoomId}' is missing a required door anchor for '{expectedDoorId}'.");
                }
            }
        }

        private static void ValidateLocalReferenceOwnership(GameObject roomRoot, Scene scene, RoomValidationResult result)
        {
            foreach (var component in roomRoot.GetComponentsInChildren<Component>(true))
            {
                if (component == null) continue;

                var serializedObject = new SerializedObject(component);
                var property = serializedObject.GetIterator();
                var enterChildren = true;
                while (property.NextVisible(enterChildren))
                {
                    enterChildren = false;
                    if (property.propertyType != SerializedPropertyType.ObjectReference) continue;

                    var referenced = property.objectReferenceValue;
                    if (referenced == null) continue;
                    if (EditorUtility.IsPersistent(referenced)) continue;

                    var referencedGameObject = ResolveGameObject(referenced);
                    if (referencedGameObject != null && referencedGameObject.scene != scene)
                    {
                        result.AddError(
                            $"'{component.GetType().Name}' on '{component.gameObject.name}' holds a serialized reference to " +
                            $"'{referenced.name}' outside its own source scene; room authoring content must own only local references.");
                    }
                }
            }
        }

        private static GameObject ResolveGameObject(Object obj)
        {
            if (obj is GameObject gameObject) return gameObject;
            if (obj is Component component) return component.gameObject;
            return null;
        }

        private static void CloneComposedRoomContent(RoomId roomId, RoomValidationResult validation, Scene targetScene)
        {
            var worldRoot = FindOrCreateSceneRoot(targetScene, WorldRootName);
            var composedRoomsRoot = FindOrCreateChild(worldRoot, ComposedRoomsRootName);

            var roomRootName = RoomRootNamePrefix + roomId;
            var existingRoomRoot = composedRoomsRoot.transform.Find(roomRootName);
            if (existingRoomRoot != null)
            {
                Object.DestroyImmediate(existingRoomRoot.gameObject);
            }

            var composedRoomRoot = new GameObject(roomRootName);
            composedRoomRoot.transform.SetParent(composedRoomsRoot.transform, false);

            CloneCategoryUnderComposedRoot(validation.VisualsRoot, composedRoomRoot.transform);
            CloneCategoryUnderComposedRoot(validation.GameplayGeometryRoot, composedRoomRoot.transform);
            CloneCategoryUnderComposedRoot(validation.DoorAnchorsRoot, composedRoomRoot.transform);
        }

        private static void CloneCategoryUnderComposedRoot(GameObject categoryRoot, Transform destinationParent)
        {
            if (categoryRoot == null) return;

            var clone = Object.Instantiate(categoryRoot);
            clone.name = categoryRoot.name;

            // worldPositionStays: true - the source room root is identity-transform, so the
            // category's current world transform already is its canonical world coordinate; the
            // clone must land at that same world position under the new composed-scene parent.
            clone.transform.SetParent(destinationParent, true);
        }

        private static GameObject FindOrCreateSceneRoot(Scene scene, string name)
        {
            foreach (var root in scene.GetRootGameObjects())
            {
                if (root.name == name) return root;
            }

            var created = new GameObject(name);
            SceneManager.MoveGameObjectToScene(created, scene);
            return created;
        }

        private static GameObject FindOrCreateChild(GameObject parent, string name)
        {
            var existing = parent.transform.Find(name);
            if (existing != null) return existing.gameObject;

            var created = new GameObject(name);
            created.transform.SetParent(parent.transform, false);
            return created;
        }
    }
}
