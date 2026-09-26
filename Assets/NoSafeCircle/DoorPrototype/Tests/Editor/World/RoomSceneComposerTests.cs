using System;
using System.IO;
using System.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using NoSafeCircle.DoorPrototype.Editor;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.World;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    // NSC-069 VAL-001: this file and RoomSceneContractTests.cs both contribute tests to the one
    // authoritative NoSafeCircle.DoorPrototype.Tests.Editor.World.RoomSceneCompositionFoundationTests
    // fixture named by the committed EditMode validation filter. This half covers
    // RoomSceneComposer's validation/composition behavior (AC-002, AC-003, AC-004) against
    // isolated in-memory/temporary fixtures, never the five real room assets or the canonical
    // Assets/Scenes/DoorPrototype.unity scene.
    public partial class RoomSceneCompositionFoundationTests
    {
        private const float FixtureBoundaryZ = 5f;

        private sealed class PlayerFixtureBehaviour : MonoBehaviour
        {
        }

        private sealed class ExternalReferenceFixtureBehaviour : MonoBehaviour
        {
            [SerializeField] private Transform externalReference;
        }

        private static RoomSceneCatalog.RoomCatalogEntry CreateFixtureRoomEntry(RoomId roomId)
        {
            return new RoomSceneCatalog.RoomCatalogEntry(
                roomId, "Assets/Scenes/Rooms/Fixture.unity",
                new RoomSceneCatalog.RoomBounds(-10f, 10f, -5f, FixtureBoundaryZ));
        }

        private static RoomSceneCatalog.DoorSequenceEntry[] CreateFixtureDoors(RoomId exitRoom, RoomId entryRoom)
        {
            return new[]
            {
                new RoomSceneCatalog.DoorSequenceEntry(
                    DoorId.D1, exitRoom, entryRoom, false, new Vector2(0f, FixtureBoundaryZ), 3f)
            };
        }

        private static GameObject BuildRoomRoot(Scene scene, RoomId roomId)
        {
            var root = new GameObject("Room_" + roomId);
            SceneManager.MoveGameObjectToScene(root, scene);
            return root;
        }

        private static GameObject AddCategoryChild(
            GameObject roomRoot, RoomId roomId, RoomContentCategory category, string name)
        {
            var child = new GameObject(name);
            child.transform.SetParent(roomRoot.transform, false);

            var marker = child.AddComponent<RoomContentMarker>();
            var serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)roomId;
            serialized.FindProperty("category").enumValueIndex = (int)category;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            return child;
        }

        private static DoorAnchorMarker AddDoorAnchorMarkerOnly(
            GameObject gameObject, RoomId roomId, DoorId doorId, DoorAnchorRole role, float openingWidth)
        {
            var marker = gameObject.AddComponent<DoorAnchorMarker>();
            var serialized = new SerializedObject(marker);
            serialized.FindProperty("roomId").enumValueIndex = (int)roomId;
            serialized.FindProperty("doorId").enumValueIndex = (int)doorId;
            serialized.FindProperty("role").enumValueIndex = (int)role;
            serialized.FindProperty("openingWidth").floatValue = openingWidth;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            return marker;
        }

        private static DoorAnchorMarker AddDoorAnchor(
            GameObject doorAnchorsRoot, RoomId roomId, DoorId doorId, DoorAnchorRole role,
            Vector3 worldPosition, Quaternion rotation, float openingWidth)
        {
            var anchorObject = new GameObject(doorId + "_" + role);
            anchorObject.transform.SetParent(doorAnchorsRoot.transform, false);
            anchorObject.transform.SetPositionAndRotation(worldPosition, rotation);
            return AddDoorAnchorMarkerOnly(anchorObject, roomId, doorId, role, openingWidth);
        }

        // Builds a scene-conformant Room_<RoomId> root: identity-transform, with Visuals (a
        // correctly sorted SpriteRenderer), GameplayGeometry (a collider), and DoorAnchors (one
        // Exit anchor matching doorEntry) children, each carrying its RoomContentMarker.
        private static GameObject BuildValidRoomFixture(
            Scene scene, RoomId roomId, RoomSceneCatalog.DoorSequenceEntry doorEntry)
        {
            var roomRoot = BuildRoomRoot(scene, roomId);

            var visuals = AddCategoryChild(roomRoot, roomId, RoomContentCategory.Visuals, "Visuals");
            var spriteObject = new GameObject("Sprite");
            spriteObject.transform.SetParent(visuals.transform, false);
            // AC-005/AC-006: this is the shared "valid" baseline every other fixture in this
            // file starts from, so it must itself satisfy the two validation rules those
            // criteria add (shared sorting layer, Pivot sort point) or every test that reuses
            // it to check an UNRELATED rule would start failing on this rule instead. Assert
            // the constant, not a literal, so this setup cannot go stale the way AC-007's
            // pinned literal assertions did.
            var spriteRenderer = spriteObject.AddComponent<SpriteRenderer>();
            spriteRenderer.sortingLayerName = WorldSpriteConvention.SortingLayerName;
            spriteRenderer.spriteSortPoint = SpriteSortPoint.Pivot;

            var gameplayGeometry =
                AddCategoryChild(roomRoot, roomId, RoomContentCategory.GameplayGeometry, "GameplayGeometry");
            var wallObject = new GameObject("Wall");
            wallObject.transform.SetParent(gameplayGeometry.transform, false);
            wallObject.AddComponent<BoxCollider>();

            var doorAnchors = AddCategoryChild(roomRoot, roomId, RoomContentCategory.DoorAnchors, "DoorAnchors");
            AddDoorAnchor(
                doorAnchors, roomId, doorEntry.DoorId, DoorAnchorRole.Exit,
                new Vector3(doorEntry.ExpectedGroundCenter.x, 1f, doorEntry.ExpectedGroundCenter.y),
                Quaternion.identity, doorEntry.OpeningWidth);

            return roomRoot;
        }

        private static void SaveFixtureRoomScene(
            string folder, string scenePath, RoomId roomId, RoomSceneCatalog.DoorSequenceEntry doorEntry)
        {
            if (!AssetDatabase.IsValidFolder(folder))
            {
                AssetDatabase.CreateFolder("Assets", folder.Substring("Assets/".Length));
            }

            var fixtureScene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            BuildValidRoomFixture(fixtureScene, roomId, doorEntry);
            EditorSceneManager.SaveScene(fixtureScene, scenePath);
            EditorSceneManager.CloseScene(fixtureScene, true);
        }

        // AC-002/AC-003: a conformant room root, with correctly categorized children, the shared
        // sorting convention, and one matching door anchor, must validate cleanly.
        [Test]
        public void ValidateOpenRoomScene_ValidFixture_IsValidWithNoErrors()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                CollectionAssert.IsEmpty(result.Errors, string.Join("\n", result.Errors));
                Assert.IsTrue(result.IsValid);
                Assert.AreEqual(1, result.DoorAnchors.Count);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-005/VAL-001: restores the negative sorting-layer case NSC-069 revision 8 removed,
        // now provable because a second sorting layer (WorldSprites) exists. A Visuals or
        // GameplayGeometry SpriteRenderer or TilemapRenderer authored on a sorting layer other
        // than the shared WorldSprites layer must fail validation with an error naming it.
        [Test]
        public void ValidateOpenRoomScene_VisualsSpriteRendererOnWrongSortingLayer_ReportsError()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);
                var offendingRenderer = roomRoot.transform.Find("Visuals/Sprite").GetComponent<SpriteRenderer>();
                offendingRenderer.sortingLayerName = "Default";

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(
                    result.Errors.Contains(
                        $"SpriteRenderer 'Sprite' must use the shared '{WorldSpriteConvention.SortingLayerName}' sorting layer."),
                    string.Join("\n", result.Errors));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-006/VAL-001: a Visuals or GameplayGeometry SpriteRenderer left at the default
        // spriteSortPoint.Center, rather than Pivot, must fail validation with an error naming
        // it. TilemapRenderer has no spriteSortPoint and is not covered by this rule.
        [Test]
        public void ValidateOpenRoomScene_VisualsSpriteRendererNotPivotSortPoint_ReportsError()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);
                var offendingRenderer = roomRoot.transform.Find("Visuals/Sprite").GetComponent<SpriteRenderer>();
                offendingRenderer.spriteSortPoint = SpriteSortPoint.Center;

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(
                    result.Errors.Contains(
                        $"SpriteRenderer 'Sprite' must use the '{nameof(SpriteSortPoint.Pivot)}' sprite sort point."),
                    string.Join("\n", result.Errors));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-002: the room root must be an identity-transform root so authored child positions
        // are already canonical world coordinates.
        [Test]
        public void ValidateOpenRoomScene_NonIdentityRoomRoot_ReportsError()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);
                roomRoot.transform.localPosition = new Vector3(1f, 0f, 0f);

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(result.Errors.Any(error => error.Contains("identity-transform")));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-002: Visuals, GameplayGeometry, and DoorAnchors are each required categories.
        [Test]
        public void ValidateOpenRoomScene_MissingCategoryChild_ReportsError()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);
                Object.DestroyImmediate(roomRoot.transform.Find("GameplayGeometry").gameObject);

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(result.Errors.Any(error => error.Contains("GameplayGeometry")));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-002: room authoring content must not contain a Light (or other global-system)
        // component; those are owned by DoorPrototypeGlobalSceneBuilder, not room content.
        [Test]
        public void ValidateOpenRoomScene_DisallowedLightComponent_ReportsError()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);
                var lightObject = new GameObject("StrayLight");
                lightObject.transform.SetParent(roomRoot.transform, false);
                lightObject.AddComponent<Light>();

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(result.Errors.Any(error => error.Contains("Light")));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-002: room authoring content must not contain a run-state-service component; enemy
        // active-count bookkeeping is a global-system concern, not room content.
        [Test]
        public void ValidateOpenRoomScene_DisallowedActiveEnemyRegistryComponent_ReportsError()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);
                var registryObject = new GameObject("StrayActiveEnemyRegistry");
                registryObject.transform.SetParent(roomRoot.transform, false);
                registryObject.AddComponent<ActiveEnemyRegistry>();

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(result.Errors.Any(error => error.Contains("ActiveEnemyRegistry")));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-002: room authoring content must not contain an encounter-population component.
        [Test]
        public void ValidateOpenRoomScene_DisallowedEncounterAdmissionControllerComponent_ReportsError()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);
                var admissionObject = new GameObject("StrayEncounterAdmissionController");
                admissionObject.transform.SetParent(roomRoot.transform, false);
                admissionObject.AddComponent<EncounterAdmissionController>();

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(result.Errors.Any(error => error.Contains("EncounterAdmissionController")));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-002: room authoring content must not contain a live Player-owned component.
        [Test]
        public void ValidateOpenRoomScene_PlayerPrefixedComponent_ReportsError()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);
                roomRoot.AddComponent<PlayerFixtureBehaviour>();

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(result.Errors.Any(error => error.Contains("Player-owned component")));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-003: a door anchor must sit at its catalog-defined world-space ground center and on
        // its room's shared boundary, not merely somewhere on the correct X plane.
        [Test]
        public void ValidateOpenRoomScene_DoorAnchorOutsideSharedBoundary_ReportsError()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);
                var anchor = roomRoot.GetComponentInChildren<DoorAnchorMarker>();
                anchor.transform.position += new Vector3(0f, 0f, 2f);

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(result.Errors.Any(error => error.Contains("shared boundary")));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-003: a door anchor's opening width must match the shared catalog's 3.0-unit contract.
        [Test]
        public void ValidateOpenRoomScene_DoorAnchorWrongOpeningWidth_ReportsError()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);
                var anchor = roomRoot.GetComponentInChildren<DoorAnchorMarker>();
                var serialized = new SerializedObject(anchor);
                serialized.FindProperty("openingWidth").floatValue = 4f;
                serialized.ApplyModifiedPropertiesWithoutUndo();

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(result.Errors.Any(error => error.Contains("opening width")));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        // AC-003: room authoring content may only hold local (own-scene) serialized references.
        [Test]
        public void ValidateOpenRoomScene_ReferenceOutsideSourceScene_ReportsLocalOwnershipError()
        {
            var externalObject = new GameObject("ExternalObject");
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                var roomRoot = BuildValidRoomFixture(scene, RoomId.RuinedEntry, doors[0]);

                var referencer = roomRoot.AddComponent<ExternalReferenceFixtureBehaviour>();
                var serialized = new SerializedObject(referencer);
                serialized.FindProperty("externalReference").objectReferenceValue = externalObject.transform;
                serialized.ApplyModifiedPropertiesWithoutUndo();

                var result = RoomSceneComposer.ValidateOpenRoomScene(RoomId.RuinedEntry, scene, roomEntry, doors);

                Assert.IsFalse(result.IsValid);
                Assert.IsTrue(result.Errors.Any(error => error.Contains("outside its own source scene")));
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
                Object.DestroyImmediate(externalObject);
            }
        }

        // AC-003: a D1-D4 boundary requires one Exit anchor and one matching Entry anchor sharing
        // a world-space center, width, and opposing forward vectors.
        [Test]
        public void ValidateAnchorPairing_OpposingForwardVectorsAtSharedCenter_Succeeds()
        {
            var exitObject = new GameObject("ExitAnchor");
            var entryObject = new GameObject("EntryAnchor");
            try
            {
                var sharedCenter = new Vector3(0f, 1f, FixtureBoundaryZ);
                exitObject.transform.SetPositionAndRotation(sharedCenter, Quaternion.LookRotation(Vector3.forward));
                entryObject.transform.SetPositionAndRotation(sharedCenter, Quaternion.LookRotation(Vector3.back));

                var exitAnchor =
                    AddDoorAnchorMarkerOnly(exitObject, RoomId.RuinedEntry, DoorId.D1, DoorAnchorRole.Exit, 3f);
                var entryAnchor =
                    AddDoorAnchorMarkerOnly(entryObject, RoomId.BoneArchive, DoorId.D1, DoorAnchorRole.Entry, 3f);

                Assert.IsTrue(RoomSceneComposer.ValidateAnchorPairing(exitAnchor, entryAnchor, out var error), error);
            }
            finally
            {
                Object.DestroyImmediate(exitObject);
                Object.DestroyImmediate(entryObject);
            }
        }

        [Test]
        public void ValidateAnchorPairing_SameDirectionForwardVectors_Fails()
        {
            var exitObject = new GameObject("ExitAnchor");
            var entryObject = new GameObject("EntryAnchor");
            try
            {
                var sharedCenter = new Vector3(0f, 1f, FixtureBoundaryZ);
                exitObject.transform.SetPositionAndRotation(sharedCenter, Quaternion.LookRotation(Vector3.forward));
                entryObject.transform.SetPositionAndRotation(sharedCenter, Quaternion.LookRotation(Vector3.forward));

                var exitAnchor =
                    AddDoorAnchorMarkerOnly(exitObject, RoomId.RuinedEntry, DoorId.D1, DoorAnchorRole.Exit, 3f);
                var entryAnchor =
                    AddDoorAnchorMarkerOnly(entryObject, RoomId.BoneArchive, DoorId.D1, DoorAnchorRole.Entry, 3f);

                Assert.IsFalse(RoomSceneComposer.ValidateAnchorPairing(exitAnchor, entryAnchor, out var error));
                StringAssert.Contains("oppose", error);
            }
            finally
            {
                Object.DestroyImmediate(exitObject);
                Object.DestroyImmediate(entryObject);
            }
        }

        [Test]
        public void ValidateAnchorPairing_MismatchedDoorId_Fails()
        {
            var exitObject = new GameObject("ExitAnchor");
            var entryObject = new GameObject("EntryAnchor");
            try
            {
                var exitAnchor =
                    AddDoorAnchorMarkerOnly(exitObject, RoomId.RuinedEntry, DoorId.D1, DoorAnchorRole.Exit, 3f);
                var entryAnchor =
                    AddDoorAnchorMarkerOnly(entryObject, RoomId.BoneArchive, DoorId.D2, DoorAnchorRole.Entry, 3f);

                Assert.IsFalse(RoomSceneComposer.ValidateAnchorPairing(exitAnchor, entryAnchor, out var error));
                StringAssert.Contains("mismatch", error);
            }
            finally
            {
                Object.DestroyImmediate(exitObject);
                Object.DestroyImmediate(entryObject);
            }
        }

        [Test]
        public void ValidateAnchorPairing_MismatchedOpeningWidth_Fails()
        {
            var exitObject = new GameObject("ExitAnchor");
            var entryObject = new GameObject("EntryAnchor");
            try
            {
                var sharedCenter = new Vector3(0f, 1f, FixtureBoundaryZ);
                exitObject.transform.SetPositionAndRotation(sharedCenter, Quaternion.LookRotation(Vector3.forward));
                entryObject.transform.SetPositionAndRotation(sharedCenter, Quaternion.LookRotation(Vector3.back));

                var exitAnchor =
                    AddDoorAnchorMarkerOnly(exitObject, RoomId.RuinedEntry, DoorId.D1, DoorAnchorRole.Exit, 3f);
                var entryAnchor =
                    AddDoorAnchorMarkerOnly(entryObject, RoomId.BoneArchive, DoorId.D1, DoorAnchorRole.Entry, 4f);

                Assert.IsFalse(RoomSceneComposer.ValidateAnchorPairing(exitAnchor, entryAnchor, out var error));
                StringAssert.Contains("opening width", error);
            }
            finally
            {
                Object.DestroyImmediate(exitObject);
                Object.DestroyImmediate(entryObject);
            }
        }

        // VAL-001 regression-only invariant: ValidateFixedRoomOrder must reject malformed
        // room-order input rather than only ever being exercised against the real catalog.
        [Test]
        public void ValidateFixedRoomOrder_WrongCount_Fails()
        {
            var rooms = new[]
            {
                CreateFixtureRoomEntry(RoomId.RuinedEntry),
                CreateFixtureRoomEntry(RoomId.BoneArchive)
            };

            Assert.IsFalse(RoomSceneComposer.ValidateFixedRoomOrder(rooms, out var error));
            Assert.IsNotEmpty(error);
        }

        [Test]
        public void ValidateFixedRoomOrder_OutOfOrderRooms_Fails()
        {
            var reversed = RoomSceneCatalog.CreateCanonicalRooms().Reverse().ToArray();

            Assert.IsFalse(RoomSceneComposer.ValidateFixedRoomOrder(reversed, out var error));
            Assert.IsNotEmpty(error);
        }

        // AC-004/VAL-004: room authoring scenes are Editor-only composition inputs and must never
        // be registered as enabled build-settings scenes.
        [Test]
        public void AreRoomScenesExcludedFromBuild_CatalogRoomPaths_AreNotRegisteredInBuildSettings()
        {
            var rooms = RoomSceneCatalog.CreateCanonicalRooms();

            var excluded = RoomSceneComposer.AreRoomScenesExcludedFromBuild(rooms, out var violations);

            Assert.IsTrue(excluded, string.Join(", ", violations));
            CollectionAssert.IsEmpty(violations);
        }

        // AC-004/VAL-003: composing a valid source scene clones only its validated content under
        // World/ComposedRooms in the target scene and closes the source scene without saving it.
        [Test]
        public void TryComposeRoom_ValidSourceScene_ClonesContentAndClosesSourceWithoutSaving()
        {
            var temporaryFolder = "Assets/__RoomSceneComposerTests_" + Guid.NewGuid().ToString("N");
            var sourceScenePath = temporaryFolder + "/FixtureRoom.unity";
            var targetScene = default(Scene);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                SaveFixtureRoomScene(temporaryFolder, sourceScenePath, RoomId.RuinedEntry, doors[0]);
                var bytesBeforeCompose = File.ReadAllBytes(sourceScenePath);
                targetScene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);

                var composed = RoomSceneComposer.TryComposeRoom(
                    sourceScenePath, RoomId.RuinedEntry, roomEntry, doors, targetScene, out var validation);

                Assert.IsTrue(composed, string.Join("\n", validation.Errors));

                var worldRoot = targetScene.GetRootGameObjects()
                    .SingleOrDefault(root => root.name == RoomSceneComposer.WorldRootName);
                Assert.IsNotNull(worldRoot, "Expected a 'World' root created in the target scene.");

                var composedRoomsRoot = worldRoot.transform.Find(RoomSceneComposer.ComposedRoomsRootName);
                Assert.IsNotNull(composedRoomsRoot, "Expected a 'ComposedRooms' child under 'World'.");

                var composedRoomRoot = composedRoomsRoot.Find("Room_" + RoomId.RuinedEntry);
                Assert.IsNotNull(composedRoomRoot, "Expected the cloned room content under ComposedRooms.");
                Assert.IsNotNull(composedRoomRoot.Find("Visuals"));
                Assert.IsNotNull(composedRoomRoot.Find("GameplayGeometry"));
                Assert.IsNotNull(composedRoomRoot.Find("DoorAnchors"));

                var reopenedSourceScene = EditorSceneManager.GetSceneByPath(sourceScenePath);
                Assert.IsFalse(reopenedSourceScene.isLoaded,
                    "Composition must close the source scene after composing it.");
                CollectionAssert.AreEqual(bytesBeforeCompose, File.ReadAllBytes(sourceScenePath),
                    "Composition must close the source scene without saving it.");
            }
            finally
            {
                if (targetScene.isLoaded)
                {
                    EditorSceneManager.CloseScene(targetScene, true);
                }
                if (AssetDatabase.IsValidFolder(temporaryFolder))
                {
                    AssetDatabase.DeleteAsset(temporaryFolder);
                }
            }
        }

        // VAL-003: two consecutive compositions of the same room must replace, not duplicate, the
        // composed output.
        [Test]
        public void TryComposeRoom_RunTwice_ReplacesComposedRoomWithoutDuplicating()
        {
            var temporaryFolder = "Assets/__RoomSceneComposerTests_" + Guid.NewGuid().ToString("N");
            var sourceScenePath = temporaryFolder + "/FixtureRoom.unity";
            var targetScene = default(Scene);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);
                SaveFixtureRoomScene(temporaryFolder, sourceScenePath, RoomId.RuinedEntry, doors[0]);
                targetScene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);

                Assert.IsTrue(RoomSceneComposer.TryComposeRoom(
                    sourceScenePath, RoomId.RuinedEntry, roomEntry, doors, targetScene, out _));
                Assert.IsTrue(RoomSceneComposer.TryComposeRoom(
                    sourceScenePath, RoomId.RuinedEntry, roomEntry, doors, targetScene, out _));

                var worldRootCount = targetScene.GetRootGameObjects()
                    .Count(root => root.name == RoomSceneComposer.WorldRootName);
                Assert.AreEqual(1, worldRootCount, "Composing twice must not duplicate the World root.");

                var composedRoomsRoot = targetScene.GetRootGameObjects()
                    .Single(root => root.name == RoomSceneComposer.WorldRootName)
                    .transform.Find(RoomSceneComposer.ComposedRoomsRootName);

                var roomRootCount = composedRoomsRoot.Cast<Transform>()
                    .Count(child => child.name == "Room_" + RoomId.RuinedEntry);
                Assert.AreEqual(1, roomRootCount,
                    "Composing twice must replace, not duplicate, the composed room root.");
            }
            finally
            {
                if (targetScene.isLoaded)
                {
                    EditorSceneManager.CloseScene(targetScene, true);
                }
                if (AssetDatabase.IsValidFolder(temporaryFolder))
                {
                    AssetDatabase.DeleteAsset(temporaryFolder);
                }
            }
        }

        // AC-004/VAL-001: composition must fail before any content is cloned into the target
        // (canonical) scene, and must still close the invalid source scene without saving it.
        [Test]
        public void TryComposeRoom_InvalidSourceScene_FailsAndLeavesTargetSceneUnmodified()
        {
            var temporaryFolder = "Assets/__RoomSceneComposerTests_" + Guid.NewGuid().ToString("N");
            var sourceScenePath = temporaryFolder + "/FixtureRoom.unity";
            var targetScene = default(Scene);
            try
            {
                var roomEntry = CreateFixtureRoomEntry(RoomId.RuinedEntry);
                var doors = CreateFixtureDoors(RoomId.RuinedEntry, RoomId.BoneArchive);

                if (!AssetDatabase.IsValidFolder(temporaryFolder))
                {
                    AssetDatabase.CreateFolder("Assets", temporaryFolder.Substring("Assets/".Length));
                }
                var fixtureScene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
                var roomRoot = BuildValidRoomFixture(fixtureScene, RoomId.RuinedEntry, doors[0]);
                Object.DestroyImmediate(roomRoot.transform.Find("DoorAnchors").gameObject);
                EditorSceneManager.SaveScene(fixtureScene, sourceScenePath);
                EditorSceneManager.CloseScene(fixtureScene, true);
                var bytesBeforeCompose = File.ReadAllBytes(sourceScenePath);
                targetScene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);

                var composed = RoomSceneComposer.TryComposeRoom(
                    sourceScenePath, RoomId.RuinedEntry, roomEntry, doors, targetScene, out var validation);

                Assert.IsFalse(composed);
                Assert.IsTrue(validation.Errors.Any(error => error.Contains("DoorAnchors")));

                Assert.AreEqual(0, targetScene.GetRootGameObjects().Length,
                    "A failed validation must not clone any content into the target scene before canonical save.");

                var reopenedSourceScene = EditorSceneManager.GetSceneByPath(sourceScenePath);
                Assert.IsFalse(reopenedSourceScene.isLoaded,
                    "Composition must close the source scene even when validation fails.");
                CollectionAssert.AreEqual(bytesBeforeCompose, File.ReadAllBytes(sourceScenePath),
                    "A failed composition attempt must not save the source scene.");
            }
            finally
            {
                if (targetScene.isLoaded)
                {
                    EditorSceneManager.CloseScene(targetScene, true);
                }
                if (AssetDatabase.IsValidFolder(temporaryFolder))
                {
                    AssetDatabase.DeleteAsset(temporaryFolder);
                }
            }
        }
    }
}
