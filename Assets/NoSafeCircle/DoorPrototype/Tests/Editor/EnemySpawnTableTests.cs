using System;
using System.Linq;
using System.Reflection;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.Enemies.Pooling;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    // The Enemies lane's authored data and prefabs, checked without entering Play mode.
    //
    // THE SPAWN TABLE HAS TWO INDEPENDENT WITNESSES, so a transcription error cannot pass:
    //   1. the editor arrays the points were MOVED FROM, read by reflection out of
    //      DoorPrototypeGlobalSceneBuilder (private, static, Editor assembly);
    //   2. the nine literals transcribed by hand into this file.
    // A typo in the asset fails both; a typo in one witness fails one and names itself.
    public sealed class EnemySpawnTableTests
    {
        private const string ResourcesRoot = "Assets/NoSafeCircle/DoorPrototype/Resources/";
        private const string TablePath = ResourcesRoot + "Enemies/EnemySpawnTable.asset";
        private const string MeleePrefabPath = ResourcesRoot + "Enemies/MeleeEnemy.prefab";
        private const string WraithPrefabPath = ResourcesRoot + "Enemies/LanternWraith.prefab";
        private const string SpawnerPrefabPath = ResourcesRoot + "Spawners/EnemySpawner.prefab";

        private const string EditorBuilderTypeName =
            "NoSafeCircle.DoorPrototype.Editor.World.DoorPrototypeGlobalSceneBuilder";
        private const string MeleeArrayField = "EnemySpawnPositions";
        private const string WraithArrayField = "LanternWraithSpawnPositions";

        // WITNESS 2. Transcribed by hand on 2026-09-26 from
        // Editor/World/DoorPrototypeGlobalSceneBuilder.cs: EnemySpawnPositions (five melee, in
        // array order) then LanternWraithSpawnPositions (four wraiths, in array order). The ids
        // and rooms are the lane's own naming; the positions are the editor's, verbatim.
        private static readonly (string id, EnemyKind kind, string room, Vector3 position)[] Transcribed =
        {
            ("ba-melee-1", EnemyKind.Melee, "BoneArchive", new Vector3(1.25f, 0f, 10f)),
            ("ca-melee-1", EnemyKind.Melee, "ChapelOfAsh", new Vector3(-2f, 0f, 36f)),
            ("lv-melee-1", EnemyKind.Melee, "LowerVault", new Vector3(-4.5f, 0f, 64.75f)),
            ("fr-melee-1", EnemyKind.Melee, "FinalRoom", new Vector3(-2f, 0f, 86f)),
            ("fr-melee-2", EnemyKind.Melee, "FinalRoom", new Vector3(4f, 0f, 95f)),
            ("ba-wraith-1", EnemyKind.LanternWraith, "BoneArchive", new Vector3(9f, 0f, 16f)),
            ("ca-wraith-1", EnemyKind.LanternWraith, "ChapelOfAsh", new Vector3(0f, 0f, 45f)),
            ("lv-wraith-1", EnemyKind.LanternWraith, "LowerVault", new Vector3(2f, 0f, 56f)),
            ("fr-wraith-1", EnemyKind.LanternWraith, "FinalRoom", new Vector3(10f, 0f, 80f)),
        };

        private static EnemySpawnTable LoadTable()
        {
            var table = AssetDatabase.LoadAssetAtPath<EnemySpawnTable>(TablePath);
            Assert.IsNotNull(table, TablePath + " did not load as an EnemySpawnTable.");
            Assert.Greater(table.Entries.Count, 0, "the table is empty, so every check would be vacuous");
            return table;
        }

        private static T LoadPrefab<T>(string path) where T : Component
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            Assert.IsNotNull(prefab, path + " did not load.");
            var component = prefab.GetComponent<T>();
            Assert.IsNotNull(component, path + " has no " + typeof(T).Name + " on its root.");
            return component;
        }

        private static void AssertSamePoint(Vector3 expected, Vector3 actual, string what)
        {
            // Exact, on purpose. These are the literals the acceptance criteria pin; a
            // "close enough" comparison is exactly the tidying this test exists to catch.
            Assert.AreEqual(expected.x, actual.x, what + " x");
            Assert.AreEqual(expected.y, actual.y, what + " y");
            Assert.AreEqual(expected.z, actual.z, what + " z");
        }

        private static Vector3[] EditorArray(string fieldName)
        {
            // Reflection because the builder is internal to the Editor assembly, and because a
            // production reference from a test to a generator scheduled for deletion would be
            // wrong. When the generator IS deleted, this witness must be retired deliberately -
            // hence a loud failure rather than a silent skip.
            Type builder = typeof(RoomSceneCatalog).Assembly.GetType(EditorBuilderTypeName);
            Assert.IsNotNull(builder, EditorBuilderTypeName + " no longer exists. The editor arrays "
                + "were this table's origin; retire this witness on purpose, do not delete it quietly.");
            FieldInfo field = builder.GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Static);
            Assert.IsNotNull(field, EditorBuilderTypeName + "." + fieldName + " no longer exists.");
            var values = (Vector3[])field.GetValue(null);
            Assert.IsNotNull(values);
            Assert.Greater(values.Length, 0, fieldName + " is empty");
            return values;
        }

        [Test]
        public void TableMatchesTheEditorArraysItWasMovedFrom()
        {
            EnemySpawnTable table = LoadTable();
            Vector3[] melee = EditorArray(MeleeArrayField);
            Vector3[] wraiths = EditorArray(WraithArrayField);

            EnemySpawnEntry[] tableMelee = table.Entries.Where(e => e.Kind == EnemyKind.Melee).ToArray();
            EnemySpawnEntry[] tableWraiths = table.Entries.Where(e => e.Kind == EnemyKind.LanternWraith).ToArray();

            Assert.AreEqual(melee.Length, tableMelee.Length, "melee count differs from the editor array");
            Assert.AreEqual(wraiths.Length, tableWraiths.Length, "wraith count differs from the editor array");
            Assert.AreEqual(melee.Length + wraiths.Length, table.Entries.Count, "the table holds entries of no editor kind");

            for (int i = 0; i < melee.Length; i++)
            {
                AssertSamePoint(melee[i], tableMelee[i].Position, "melee " + i + " (" + tableMelee[i].Id + ")");
            }

            for (int i = 0; i < wraiths.Length; i++)
            {
                AssertSamePoint(wraiths[i], tableWraiths[i].Position, "wraith " + i + " (" + tableWraiths[i].Id + ")");
            }
        }

        [Test]
        public void TableMatchesTheHandTranscribedLiterals()
        {
            EnemySpawnTable table = LoadTable();
            Assert.AreEqual(Transcribed.Length, table.Entries.Count, "entry count differs from the transcription");

            for (int i = 0; i < Transcribed.Length; i++)
            {
                (string id, EnemyKind kind, string room, Vector3 position) = Transcribed[i];
                EnemySpawnEntry entry = table.Entries[i];
                Assert.AreEqual(id, entry.Id, "entry " + i + " id");
                Assert.AreEqual(kind, entry.Kind, id + " kind");
                Assert.AreEqual(room, entry.Room, id + " room");
                AssertSamePoint(position, entry.Position, id);
            }
        }

        [Test]
        public void TableValidatesAndEveryIdIsUnique()
        {
            EnemySpawnTable table = LoadTable();
            Assert.IsTrue(table.TryValidate(out string problem), problem);
            Assert.AreEqual(table.Entries.Count, table.Entries.Select(e => e.Id).Distinct().Count(), "ids repeat");
            Assert.IsTrue(table.Entries.All(e => e.Position.y == 0f), "every point is authored at y 0");

            // The validator must actually reject a repeat, or the assertion above tests nothing.
            EnemySpawnEntry first = table.Entries[0];
            EnemySpawnTable broken = EnemySpawnTable.CreateRuntime(new[] { first, first });
            try
            {
                Assert.IsFalse(broken.TryValidate(out string why), "a repeated id passed validation");
                StringAssert.Contains(first.Id, why);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(broken);
            }
        }

        private static Bounds RoomBoundsOf(string room)
        {
            switch (room)
            {
                case "BoneArchive": return BoneArchiveLayout.RoomBounds;
                case "ChapelOfAsh": return ChapelOfAshLayout.RoomBounds;
                case "LowerVault": return LowerVaultLayout.RoomBounds;
                case "FinalRoom": return FinalRoomLayout.RoomBounds;
                default:
                    Assert.Fail("no runtime layout for room '" + room + "'. RuinedEntry is deliberately "
                        + "empty: the wizard spawns there.");
                    return default;
            }
        }

        [Test]
        public void EveryEntryLiesInsideItsRoomWithAUnitOfClearance()
        {
            // The layouts are the source: the table was not derived from them, so they are an
            // independent statement of where each room is.
            foreach (EnemySpawnEntry entry in LoadTable().Entries)
            {
                Bounds room = RoomBoundsOf(entry.Room);
                Vector3 p = entry.Position;
                Assert.GreaterOrEqual(p.x, room.min.x + 1f, entry.Id + " is within a unit of the west wall");
                Assert.LessOrEqual(p.x, room.max.x - 1f, entry.Id + " is within a unit of the east wall");
                Assert.GreaterOrEqual(p.z, room.min.z + 1f, entry.Id + " is within a unit of the south wall");
                Assert.LessOrEqual(p.z, room.max.z - 1f, entry.Id + " is within a unit of the north wall");
            }
        }

        private static float DistanceXZ(Vector3 a, Vector3 b)
        {
            a.y = 0f;
            b.y = 0f;
            return Vector3.Distance(a, b);
        }

        /// <summary>Positive on one side of the line lineStart -> lineEnd, negative on the other, in XZ.</summary>
        private static float SideOfLine(Vector3 lineStart, Vector3 lineEnd, Vector3 point)
        {
            Vector3 line = lineEnd - lineStart;
            Vector3 offset = point - lineStart;
            return line.x * offset.z - line.z * offset.x;
        }

        private static EnemySpawnEntry Entry(EnemySpawnTable table, string id)
        {
            EnemySpawnEntry entry = table.Entries.FirstOrDefault(e => e.Id == id);
            Assert.IsNotNull(entry, "no entry '" + id + "'");
            return entry;
        }

        [Test]
        public void MeleePointsHonourTheAc005DoorLineRelations()
        {
            // AC-005 (contract revision 8), as the builder's own comments state it: each
            // single-melee room's spawn sits within 4 units of the midpoint of that room's two
            // door centres; the Final Room's pair flank FR-1 on opposite sides of the D4-D5 line
            // within 6 units of its midpoint. Door centres come from the runtime layouts.
            EnemySpawnTable table = LoadTable();

            Assert.Less(DistanceXZ(Entry(table, "ba-melee-1").Position, (BoneArchiveLayout.D1 + BoneArchiveLayout.D2) * 0.5f), 4f);
            Assert.Less(DistanceXZ(Entry(table, "ca-melee-1").Position, (ChapelOfAshLayout.D2 + ChapelOfAshLayout.D3) * 0.5f), 4f);
            Assert.Less(DistanceXZ(Entry(table, "lv-melee-1").Position, (LowerVaultLayout.D3 + LowerVaultLayout.D4) * 0.5f), 4f);

            Vector3 d4 = FinalRoomLayout.D4;
            Vector3 d5 = FinalRoomLayout.D5;
            Vector3 midpoint = (d4 + d5) * 0.5f;
            Vector3 west = Entry(table, "fr-melee-1").Position;
            Vector3 east = Entry(table, "fr-melee-2").Position;
            Assert.Less(DistanceXZ(west, midpoint), 6f, "fr-melee-1 is more than 6 u from the D4-D5 midpoint");
            Assert.Less(DistanceXZ(east, midpoint), 6f, "fr-melee-2 is more than 6 u from the D4-D5 midpoint");
            Assert.Less(SideOfLine(d4, d5, west) * SideOfLine(d4, d5, east), 0f,
                "the Final Room melee pair must flank the D4-D5 line on opposite sides");
        }

        [Test]
        public void WraithPointsSitAcrossTheDoorLineFromTheirMeleeAndClearOfIt()
        {
            // As the builder's comments state it: each wraith sits on the opposite side of its
            // room's door line from that room's melee, at least 6 units clear of it; the Final
            // Room wraith sits within 12 units of D4.
            EnemySpawnTable table = LoadTable();
            (string melee, string wraith, Vector3 lineStart, Vector3 lineEnd)[] rooms =
            {
                ("ba-melee-1", "ba-wraith-1", BoneArchiveLayout.D1, BoneArchiveLayout.D2),
                ("ca-melee-1", "ca-wraith-1", ChapelOfAshLayout.D2, ChapelOfAshLayout.D3),
                ("lv-melee-1", "lv-wraith-1", LowerVaultLayout.D3, LowerVaultLayout.D4),
            };

            foreach ((string melee, string wraith, Vector3 lineStart, Vector3 lineEnd) in rooms)
            {
                Vector3 m = Entry(table, melee).Position;
                Vector3 w = Entry(table, wraith).Position;
                Assert.Less(SideOfLine(lineStart, lineEnd, m) * SideOfLine(lineStart, lineEnd, w), 0f,
                    wraith + " is on the same side of the door line as " + melee);
                Assert.GreaterOrEqual(DistanceXZ(m, w), 6f, wraith + " is within 6 u of " + melee);
            }

            Assert.LessOrEqual(DistanceXZ(Entry(table, "fr-wraith-1").Position, FinalRoomLayout.D4), 12f);
        }

        [Test]
        public void RuntimeLayoutDoorCentresAgreeWithTheRoomSceneCatalog()
        {
            // The relations above trust the layouts' door constants. RoomSceneCatalog is a
            // second, editor-side statement of the same five centres; if the two ever disagree,
            // the relations are being checked against the wrong doors.
            RoomSceneCatalog.DoorSequenceEntry[] doors = RoomSceneCatalog.CreateCanonicalDoors();
            Assert.AreEqual(5, doors.Length);

            Vector2 Centre(string door)
            {
                RoomSceneCatalog.DoorSequenceEntry entry = doors.FirstOrDefault(d => d.DoorId.ToString() == door);
                Assert.IsNotNull(entry, "the catalog has no door " + door);
                return entry.ExpectedGroundCenter;
            }

            void AssertDoor(string door, Vector3 layout)
            {
                Vector2 c = Centre(door);
                Assert.AreEqual(c.x, layout.x, 0.0001f, door + " x");
                Assert.AreEqual(c.y, layout.z, 0.0001f, door + " z");
            }

            AssertDoor("D1", BoneArchiveLayout.D1);
            AssertDoor("D2", BoneArchiveLayout.D2);
            AssertDoor("D2", ChapelOfAshLayout.D2);
            AssertDoor("D3", ChapelOfAshLayout.D3);
            AssertDoor("D3", LowerVaultLayout.D3);
            AssertDoor("D4", LowerVaultLayout.D4);
            AssertDoor("D4", FinalRoomLayout.D4);
            AssertDoor("D5", FinalRoomLayout.D5);
        }

        private static void AssertEnemyPrefabConvention(string path, EnemyAnimationKind expectedKind)
        {
            EnemyPoolable poolable = LoadPrefab<EnemyPoolable>(path);
            GameObject prefab = poolable.gameObject;

            Assert.IsNotNull(prefab.GetComponent<EnemyHealth>(), path + " has no EnemyHealth");
            var animator = prefab.GetComponent<Animator>();
            Assert.IsNotNull(animator, path + " has no Animator");
            Assert.IsNotNull(animator.runtimeAnimatorController, path + ": the Animator has no controller");
            Assert.IsFalse(animator.keepAnimatorStateOnDisable,
                path + ": the poolable relies on the Animator resetting when the instance is deactivated");

            var animation = prefab.GetComponent<EnemyAnimationController>();
            Assert.IsNotNull(animation, path + " has no EnemyAnimationController");
            SerializedProperty kind = new SerializedObject(animation).FindProperty("animationKind");
            Assert.IsNotNull(kind, "EnemyAnimationController no longer serializes 'animationKind'");
            Assert.AreEqual((int)expectedKind, kind.enumValueIndex, path + " animationKind");

            Transform visual = prefab.transform.Find("Visual");
            Assert.IsNotNull(visual, path + ": EnemyAnimationController finds the child by the name 'Visual'");
            Assert.AreEqual(Vector3.zero, visual.localPosition, path + ": Visual sits at the root's ground contact");
            Assert.AreEqual(Vector3.one, visual.localScale, path + ": Visual is never scaled");
            Assert.Less(Quaternion.Angle(visual.localRotation, Quaternion.Euler(EnemyAnimationController.IsometricCameraEulerAngles)), 0.01f,
                path + ": Visual is not camera-facing; RestoreCameraFacingVisual re-applies exactly this rotation");

            var renderer = visual.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(renderer, path + ": Visual has no SpriteRenderer");
            Assert.IsNotNull(renderer.sprite, path + ": the sprite did not resolve");
            Assert.AreEqual(WorldSpriteConvention.SortingLayerName, renderer.sortingLayerName, path + " sorting layer");
            Assert.AreEqual(WorldSpriteConvention.SortingOrder, renderer.sortingOrder, path + " sorting order");
            Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint, path + " sort point");
        }

        [Test]
        public void EnemyPrefabsCarryTheConventionAndThePoolContract()
        {
            AssertEnemyPrefabConvention(MeleePrefabPath, EnemyAnimationKind.MeleeEnemy);
            AssertEnemyPrefabConvention(WraithPrefabPath, EnemyAnimationKind.LanternWraith);

            // The melee's agent matches the project's one configured agent type, read from the
            // NavMesh settings rather than from the prefab: a mismatched radius or height silently
            // refuses to produce a complete path.
            GameObject melee = LoadPrefab<EnemyPoolable>(MeleePrefabPath).gameObject;
            var agent = melee.GetComponent<NavMeshAgent>();
            Assert.IsNotNull(agent, "a melee must carry a NavMeshAgent");
            NavMeshBuildSettings settings = NavMesh.GetSettingsByIndex(0);
            Assert.AreEqual(settings.agentTypeID, agent.agentTypeID, "agent type differs from the project's");
            Assert.AreEqual(settings.agentRadius, agent.radius, 0.0001f, "agent radius differs from the project's");
            Assert.AreEqual(settings.agentHeight, agent.height, 0.0001f, "agent height differs from the project's");
            Assert.AreEqual(0f, agent.baseOffset, 0.0001f,
                "baseOffset lifts the root above the navmesh. The sprite's pivot is at its feet and "
                + "the Visual sits at local y 0, so any offset floats the enemy above the floor.");
            Assert.IsNotNull(melee.GetComponent<EnemyTargetKnowledge>());
            Assert.IsNotNull(melee.GetComponent<EnemyPursuitMovement>());
            Assert.IsNull(melee.GetComponent<EnemyLanternWispCaster>());

            GameObject wraith = LoadPrefab<EnemyPoolable>(WraithPrefabPath).gameObject;
            Assert.IsNull(wraith.GetComponent<NavMeshAgent>(), "a wraith holds its ground: no agent");
            Assert.IsNotNull(wraith.GetComponent<EnemyLanternWispCaster>());
            Assert.IsNull(wraith.GetComponent<EnemyPursuitMovement>());
        }

        [Test]
        public void SpawnerPrefabWiresRegistryAdmissionAndDataAndNeverSpawnsItself()
        {
            EnemySpawner spawner = LoadPrefab<EnemySpawner>(SpawnerPrefabPath);
            GameObject prefab = spawner.gameObject;
            Assert.AreEqual(SpawnPhase.Enemies, ((ISpawner)spawner).Phase);

            // THE REGISTRY AND ADMISSION EXIST HERE, and nowhere else in production.
            var registry = prefab.GetComponent<ActiveEnemyRegistry>();
            var admission = prefab.GetComponent<EncounterAdmissionController>();
            Assert.IsNotNull(registry, "the spawner prefab carries no ActiveEnemyRegistry");
            Assert.IsNotNull(admission, "the spawner prefab carries no EncounterAdmissionController");
            Assert.AreEqual(registry, admission.Registry, "admission's serialized registry is not the sibling");

            var serialized = new SerializedObject(spawner);
            Assert.AreEqual(AssetDatabase.LoadAssetAtPath<EnemySpawnTable>(TablePath),
                serialized.FindProperty("spawnTable").objectReferenceValue, "spawnTable");
            Assert.AreEqual(AssetDatabase.LoadAssetAtPath<GameObject>(MeleePrefabPath),
                serialized.FindProperty("meleePrefab").objectReferenceValue, "meleePrefab");
            Assert.AreEqual(AssetDatabase.LoadAssetAtPath<GameObject>(WraithPrefabPath),
                serialized.FindProperty("wraithPrefab").objectReferenceValue, "wraithPrefab");
            Assert.AreEqual(registry, serialized.FindProperty("registry").objectReferenceValue, "registry");
            Assert.AreEqual(admission, serialized.FindProperty("admission").objectReferenceValue, "admission");

            // GameBootstrap owns the build order, so a spawner may not start itself: no Awake, no
            // OnEnable, no Start. Checked structurally because a runtime test can only prove the
            // absence of an effect it thought to look for.
            const BindingFlags Own = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;
            foreach (string lifecycle in new[] { "Awake", "OnEnable", "Start" })
            {
                Assert.IsNull(typeof(EnemySpawner).GetMethod(lifecycle, Own),
                    "EnemySpawner declares " + lifecycle + "; a spawner must only act when Spawn() is called");
            }
        }
    }
}
