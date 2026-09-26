using System;
using System.Linq;
using System.Reflection;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    /// <summary>
    /// The door prefab and its spawner prefab, read as ASSETS, without entering Play.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The prefab was hand-authored from a code listing (DoorPrototypeSceneBuilder.BuildDoor and
    /// BuildBreachFeedback) rather than saved from an Inspector, so every value in it is a
    /// transcription. These tests hold the transcription to sources that are NOT the prefab: the
    /// camera angles the builder projected with, the approved art on disk and its importer, the
    /// crack placements the builder authored, the layouts, and the editor catalog.
    /// </para>
    /// <para>
    /// Test 9 is the one that lets DoorSpawner read only the EXIT room's copy of each shared door:
    /// it holds the two layout copies and the editor catalog (unreachable at Play) to agreement,
    /// so a drift between them fails here rather than moving a door at runtime.
    /// </para>
    /// </remarks>
    public sealed class DoorPrefabTests
    {
        private const string DoorPrefabPath = "Assets/NoSafeCircle/DoorPrototype/Resources/Doors/Door.prefab";
        private const string SpawnerPrefabPath = "Assets/NoSafeCircle/DoorPrototype/Resources/Spawners/DoorSpawner.prefab";
        private const string DoorArtSourceFolder = "Assets/NoSafeCircle/DoorPrototype/Art/Doors/Source/";

        // Docs/Art/Doors/APPROVAL.md: sprites are 128x128 at PPU 64, bound at x1.54 (Vincent, 2026-09-17).
        private const float ApprovedPixelsPerUnit = 64f;
        private const float ApprovedArtScale = 1.54f;

        private static GameObject LoadDoorPrefab()
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(DoorPrefabPath);
            Assert.IsNotNull(prefab, DoorPrefabPath + " did not load. DoorSpawner has nothing to instantiate.");
            return prefab;
        }

        [Test]
        public void DoorPrefab_GroundSelectionOffsetIsTheCameraProjectionOfTheVisualHeight()
        {
            GameObject prefab = LoadDoorPrefab();
            var door = prefab.GetComponent<DoorInteractable>();
            Assert.IsNotNull(door, "The door prefab carries no DoorInteractable.");

            SerializedProperty offsetProperty = new SerializedObject(door).FindProperty("groundSelectionOffset");
            Assert.IsNotNull(offsetProperty, "DoorInteractable no longer has a 'groundSelectionOffset' field.");
            Vector3 offset = offsetProperty.vector3Value;

            // THE CAMERA'S ANGLES, from the builder that owns them. The class and the field are
            // both `internal` to the Editor assembly and no InternalsVisibleTo exists under Assets,
            // so reflection is the only honest route; a literal here would agree with the prefab
            // by construction.
            Type globalBuilder = typeof(RoomSceneCatalog).Assembly.GetType(
                "NoSafeCircle.DoorPrototype.Editor.World.DoorPrototypeGlobalSceneBuilder");
            Assert.IsNotNull(globalBuilder, "DoorPrototypeGlobalSceneBuilder is gone; the camera angles moved.");
            FieldInfo anglesField = globalBuilder.GetField("IsometricCameraEulerAngles",
                BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Static);
            Assert.IsNotNull(anglesField, "DoorPrototypeGlobalSceneBuilder.IsometricCameraEulerAngles is gone.");
            var angles = (Vector3)anglesField.GetValue(null);

            float visualHeight = prefab.transform.Find("DoorVisual").localPosition.y;

            // DoorPrototypeSceneBuilder.ComputeGroundSelectionOffset, ported.
            Vector3 forward = Quaternion.Euler(angles) * Vector3.forward;
            Assert.IsFalse(Mathf.Approximately(forward.y, 0f), "A level camera has no ground projection to check.");
            float t = -visualHeight / forward.y;
            var expected = new Vector3(forward.x * t, 0f, forward.z * t);

            // SANITY PROBE on the derivation itself: at the 2:1 dimetric angles (30, -45, 0) and a
            // 1.25 visual height the projection is (-1.5309, 0, 1.5309). If this line fails, the
            // camera convention changed and BOTH the prefab and this expectation need a look.
            Assert.AreEqual(-1.5309f, expected.x, 0.001f, "The camera angles are no longer the 2:1 dimetric convention.");

            Assert.AreEqual(expected.x, offset.x, 0.001f, "groundSelectionOffset.x is not the camera projection of the visual height.");
            Assert.AreEqual(0f, offset.y, 0.001f, "groundSelectionOffset must lie on the ground plane.");
            Assert.AreEqual(expected.z, offset.z, 0.001f, "groundSelectionOffset.z is not the camera projection of the visual height.");
        }

        [Test]
        public void DoorPrefab_IsInactiveBindsExactlyTheFourApprovedSpritesAndCarriesTheAnatomy()
        {
            GameObject prefab = LoadDoorPrefab();

            Assert.IsFalse(prefab.activeSelf,
                "Door.prefab is saved ACTIVE. Instantiate would run Awake and OnEnable before DoorSpawner "
                + "can call Configure, and every door would report D1's identity.");

            // THE FOUR APPROVED SPRITES, and only those. DoorwayOpeningSealTests enforces this on the
            // built door; this is the same rule on the prefab asset.
            var binder = prefab.GetComponent<DoorStateSpriteBinder>();
            Assert.IsNotNull(binder, "The door prefab carries no DoorStateSpriteBinder.");
            FieldInfo[] spriteFields = typeof(DoorStateSpriteBinder)
                .GetFields(BindingFlags.NonPublic | BindingFlags.Instance)
                .Where(field => field.FieldType == typeof(Sprite))
                .ToArray();
            Assert.AreEqual(4, spriteFields.Length, "DoorStateSpriteBinder must expose exactly four sprite slots.");

            var forbiddenWords = new[] { "damaged", "opening", "broken" };
            foreach (FieldInfo field in spriteFields)
            {
                var sprite = (Sprite)field.GetValue(binder);
                Assert.IsNotNull(sprite, field.Name + " is unassigned on the prefab.");

                string assetPath = AssetDatabase.GetAssetPath(sprite);
                // sealedSprite -> sealed, lockedSprite -> locked, openSprite -> open, finalSprite -> final.
                string state = field.Name.Replace("Sprite", string.Empty);
                Assert.AreEqual(DoorArtSourceFolder + "door_bonestone_" + state + "_S_000.png", assetPath,
                    field.Name + " does not reference the approved " + state + " sprite.");
                foreach (string forbidden in forbiddenWords)
                {
                    Assert.IsFalse(assetPath.ToLowerInvariant().Contains(forbidden),
                        field.Name + " references a " + forbidden + " sprite; no code path can reach that state.");
                }

                var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
                Assert.IsNotNull(importer, assetPath + " has no TextureImporter.");
                Assert.AreEqual(TextureImporterType.Sprite, importer.textureType, assetPath + " is not imported as a Sprite.");
                Assert.AreEqual(ApprovedPixelsPerUnit, importer.spritePixelsPerUnit, 0.001f, assetPath + " pixels per unit");
            }

            // Anatomy the builder pinned and NSC-052 names by path.
            Transform visual = prefab.transform.Find("DoorVisual");
            Assert.IsNotNull(visual, "No DoorVisual child.");
            Transform sprite = visual.Find("DoorSprite");
            Assert.IsNotNull(sprite, "No DoorVisual/DoorSprite child.");
            AssertVector(new Vector3(ApprovedArtScale, ApprovedArtScale, ApprovedArtScale), sprite.localScale,
                "DoorSprite scale (Docs/Art/Doors/APPROVAL.md: x1.54)");
            Assert.AreEqual(0, sprite.GetComponentsInChildren<Collider>(true).Length,
                "NSC-052: the shake target DoorRoot/DoorVisual/DoorSprite and its descendants carry no Collider.");

            FieldInfo obstacleSizeField = typeof(DoorEnemyPassability).GetField(
                "obstacleSize", BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(obstacleSizeField, "Expected a private 'obstacleSize' field on DoorEnemyPassability.");
            var passability = prefab.GetComponent<DoorEnemyPassability>();
            Assert.IsNotNull(passability, "The door prefab carries no DoorEnemyPassability.");
            var blocker = visual.GetComponent<BoxCollider>();
            Assert.IsNotNull(blocker, "DoorVisual carries no doorway blocker.");
            Assert.AreEqual(((Vector3)obstacleSizeField.GetValue(passability)).x, blocker.size.x, 0.001f,
                "The doorway blocker's width must be the obstacle's opening width, authored once.");

            Assert.AreEqual(0, prefab.GetComponentsInChildren<Transform>(true).Count(t => t.name == "ForwardCrossingTrigger"),
                "The prefab contains a ForwardCrossingTrigger. DoorInteractable.Awake creates it; a prefab copy doubles it.");

            // Breach feedback: the child's Awake falls back to GetComponent on ITS OWN object, so
            // every reference must be serialized rather than discovered.
            var breach = prefab.GetComponentInChildren<DoorBreachFeedback>(true);
            Assert.IsNotNull(breach, "No DoorBreachFeedback under the door prefab.");
            Assert.AreEqual("DoorBreachFeedback", breach.gameObject.name, "DoorBreachFeedbackPlayModeTests finds it by this name.");
            var breachObject = new SerializedObject(breach);
            foreach (string reference in new[] { "door", "shakeTarget", "durabilityIndicator", "durabilityFill", "bangAudio" })
            {
                SerializedProperty property = breachObject.FindProperty(reference);
                Assert.IsNotNull(property, "DoorBreachFeedback no longer has a '" + reference + "' field.");
                Assert.IsNotNull(property.objectReferenceValue, "DoorBreachFeedback." + reference + " is unassigned on the prefab.");
            }
            // AreEqual, not AreSame: UnityEngine.Object equality compares instance ids, and two
            // managed wrappers for one native object are not guaranteed to be the same reference.
            Assert.AreEqual(sprite, breachObject.FindProperty("shakeTarget").objectReferenceValue,
                "NSC-052: the shake target is DoorRoot/DoorVisual/DoorSprite.");
            Assert.IsNotNull(breachObject.FindProperty("durabilityFill").objectReferenceValue as Image,
                "durabilityFill is not an Image.");
            Assert.IsNotNull(breach.transform.Find("DurabilityIndicator/Background/Fill"),
                "DoorBreachFeedbackPlayModeTests looks the fill up at DurabilityIndicator/Background/Fill.");

            SerializedProperty cracks = breachObject.FindProperty("crackStages");
            Assert.IsNotNull(cracks, "DoorBreachFeedback no longer has a 'crackStages' field.");
            Assert.AreEqual(3, cracks.arraySize, "Three crack stages, as the builder authored.");
            for (int i = 0; i < 3; i++)
            {
                Transform crack = sprite.Find("CrackStage" + (i + 1));
                Assert.IsNotNull(crack, "No DoorSprite/CrackStage" + (i + 1) + ".");
                Assert.AreEqual(crack.gameObject, cracks.GetArrayElementAtIndex(i).objectReferenceValue,
                    "crackStages[" + i + "] is not CrackStage" + (i + 1) + ".");
                Assert.IsFalse(crack.gameObject.activeSelf, "CrackStage" + (i + 1) + " must be saved inactive.");

                // BuildBreachFeedback authored each crack under DoorVisual at this local position and
                // then reparented it to DoorSprite with world position kept, so the WORLD position is
                // the invariant and the saved local numbers are whatever the reparent produced.
                Vector3 expectedWorld = visual.TransformPoint(new Vector3(-0.45f + i * 0.45f, 0.15f + i * 0.2f, -0.18f));
                AssertVector(expectedWorld, crack.position, "CrackStage" + (i + 1) + " world position");
            }
        }

        [Test]
        public void CanonicalDoorsAgreeWithTheEditorCatalogAndWithBothRoomsOfEachSharedLine()
        {
            DoorSpawner.DoorPlacement[] spawnerDoors = DoorSpawner.CanonicalDoors();
            RoomSceneCatalog.DoorSequenceEntry[] catalog = RoomSceneCatalog.CreateCanonicalDoors();

            Assert.AreEqual(catalog.Length, spawnerDoors.Length, "The spawner and the editor catalog disagree on how many doors exist.");
            Assert.AreEqual(Enum.GetValues(typeof(DoorId)).Length, catalog.Length, "The catalog does not cover every DoorId.");

            for (int i = 0; i < catalog.Length; i++)
            {
                RoomSceneCatalog.DoorSequenceEntry entry = catalog[i];
                DoorSpawner.DoorPlacement placement = spawnerDoors[i];
                string who = entry.DoorId.ToString();

                Assert.AreEqual(entry.DoorId, placement.Id, "Door order differs at index " + i + ".");
                Assert.AreEqual(entry.ExpectedGroundCenter.x, placement.Centre.x, 0.001f, who + " x vs the editor catalog");
                Assert.AreEqual(entry.ExpectedGroundCenter.y, placement.Centre.z, 0.001f, who + " z vs the editor catalog");
                Assert.AreEqual(entry.IsFinal, placement.IsFinal, who + " IsFinal vs the editor catalog");
                Assert.AreEqual(RuinedEntryLayout.DoorOpeningWidth, entry.OpeningWidth, 0.001f,
                    who + ": the catalog's opening width is not the layouts' 3.");

                // The name rule NSC-052 and NSC-075 pin in prose, as DoorSequenceBuilder.ConfigureDoor applied it.
                string expectedName = entry.DoorId == DoorId.D1 ? "DoorRoot" : entry.DoorId.ToString();
                Assert.AreEqual(expectedName, placement.ObjectName, who + " object name");
            }

            // BOTH ROOMS OF EACH SHARED LINE agree with each other and with the spawner. The spawner
            // reads the exit room's constant; the entry room's copy is the witness.
            var sharedLines = new[]
            {
                (id: DoorId.D1,
                    exit: new Vector3(RuinedEntryLayout.DoorCenterX, 0f, RuinedEntryLayout.DoorCenterZ),
                    entry: BoneArchiveLayout.D1),
                (id: DoorId.D2, exit: BoneArchiveLayout.D2, entry: ChapelOfAshLayout.D2),
                (id: DoorId.D3, exit: ChapelOfAshLayout.D3, entry: LowerVaultLayout.D3),
                (id: DoorId.D4, exit: LowerVaultLayout.D4, entry: new Vector3(FinalRoomLayout.D4X, 0f, FinalRoomLayout.D4Z))
            };
            foreach (var (id, exit, entry) in sharedLines)
            {
                AssertVector(exit, entry, id + ": the exit room's door constant and the entry room's copy differ");
                DoorSpawner.DoorPlacement placement = spawnerDoors.Single(candidate => candidate.Id == id);
                AssertVector(entry, placement.Centre, id + ": the spawner's centre is not the entry room's copy");
            }
        }

        [Test]
        public void DoorSpawnerPrefab_IsASpawnerAtPhaseDoorsAndDoesNotSpawnItself()
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(SpawnerPrefabPath);
            Assert.IsNotNull(prefab, SpawnerPrefabPath + " did not load, so GameBootstrap would never run the doors.");

            var spawner = prefab.GetComponent<DoorSpawner>();
            Assert.IsNotNull(spawner, "The spawner prefab carries no DoorSpawner.");
            Assert.AreEqual(SpawnPhase.Doors, spawner.Phase, "Doors must run at the Doors phase.");

            SerializedProperty doorPrefabProperty = new SerializedObject(spawner).FindProperty("doorPrefab");
            Assert.IsNotNull(doorPrefabProperty, "DoorSpawner no longer has a 'doorPrefab' field.");
            Assert.IsNotNull(doorPrefabProperty.objectReferenceValue, "The spawner prefab has no door prefab assigned.");
            Assert.AreEqual(DoorPrefabPath, AssetDatabase.GetAssetPath(doorPrefabProperty.objectReferenceValue),
                "The spawner references a different door prefab than the committed one.");

            // GameBootstrap owns the moment: a spawner that starts itself runs before Rooms exist.
            const BindingFlags any = BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance;
            foreach (string message in new[] { "Awake", "OnEnable", "Start" })
            {
                Assert.IsNull(typeof(DoorSpawner).GetMethod(message, any),
                    "DoorSpawner has a " + message + " message and could spawn out of phase order.");
            }
        }

        private static void AssertVector(Vector3 expected, Vector3 actual, string what)
        {
            Assert.AreEqual(expected.x, actual.x, 0.001f, what + " x");
            Assert.AreEqual(expected.y, actual.y, 0.001f, what + " y");
            Assert.AreEqual(expected.z, actual.z, 0.001f, what + " z");
        }
    }
}
