using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public sealed class EnemyArtIntegrationTests
    {
        private const string SourceRoot =
            "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source";
        private const string WalkRoot = SourceRoot + "/Walk";
        private const string GeneratedRoot =
            "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Generated";
        private const string ScenePath = "Assets/Scenes/DoorPrototype.unity";
        private const int IdleSize = 128;
        private const int WalkSize = 176;

        private static readonly EnemyDefinition[] Enemies =
        {
            new EnemyDefinition("melee", "MeleeEnemy"),
            new EnemyDefinition("ranged", "LanternWraith")
        };

        private static readonly DirectionDefinition[] Directions =
        {
            new DirectionDefinition("n", "north"),
            new DirectionDefinition("ne", "north-east"),
            new DirectionDefinition("e", "east"),
            new DirectionDefinition("se", "south-east"),
            new DirectionDefinition("s", "south"),
            new DirectionDefinition("sw", "south-west"),
            new DirectionDefinition("w", "west"),
            new DirectionDefinition("nw", "north-west")
        };

        [SetUp]
        public void OpenCandidateScene()
        {
            EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
        }

        [TearDown]
        public void CloseCandidateSceneWithoutSaving()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        // NSC-077 AC-002/AC-003 and VAL-001: exact source inventory, dimensions, explicit
        // Texture2D Sprite import settings, and ground-line pivots for all 112 frames.
        [Test]
        public void ApprovedEnemySourcesHaveExactInventoryImportSettingsAndGroundPivots()
        {
            Assert.AreEqual(64f, EnemyAnimationAssetBuilder.EnemyPixelsPerUnit,
                "NSC-077's shared enemy pixels-per-unit constant changed.");

            List<ExpectedFrame> expectedFrames = ExpectedFrames().ToList();
            Assert.AreEqual(112, expectedFrames.Count);
            Assert.AreEqual(112, expectedFrames.Select(frame => frame.Path).Distinct().Count());

            string[] actualPngPaths = Directory.GetFiles(SourceRoot, "*.png", SearchOption.AllDirectories)
                .Select(path => path.Replace('\\', '/'))
                .OrderBy(path => path)
                .ToArray();
            CollectionAssert.AreEquivalent(
                expectedFrames.Select(frame => frame.Path),
                actualPngPaths);

            WalkInventory inventory = JsonUtility.FromJson<WalkInventory>(
                File.ReadAllText(WalkRoot + "/inventory.json"));
            Assert.IsNotNull(inventory);
            CollectionAssert.AreEqual(new[] { WalkSize, WalkSize }, inventory.canvas_size);
            Assert.AreEqual(132, inventory.alpha_bottom_y_from_top);
            Assert.AreEqual(96, inventory.entries.Length);
            Assert.AreEqual(96, inventory.entries.Select(entry => entry.file).Distinct().Count());

            Dictionary<string, WalkInventoryEntry> inventoryByFile = inventory.entries.ToDictionary(
                entry => entry.file, entry => entry);
            foreach (ExpectedFrame frame in expectedFrames)
            {
                if (frame.IsWalk)
                {
                    string fileName = Path.GetFileName(frame.Path);
                    Assert.IsTrue(inventoryByFile.TryGetValue(fileName, out WalkInventoryEntry entry),
                        fileName);
                    Assert.AreEqual(frame.Enemy.SourceName, entry.archetype, fileName);
                    Assert.AreEqual(frame.Direction.Name, entry.direction, fileName);
                    Assert.AreEqual(frame.FrameIndex, entry.selected_frame_index, fileName);
                }

                AssertSourceImport(frame, inventory.alpha_bottom_y_from_top);
            }

            string[] importedSpritePaths = AssetDatabase.FindAssets("t:Sprite", new[] { SourceRoot })
                .Select(AssetDatabase.GUIDToAssetPath)
                .OrderBy(path => path)
                .ToArray();
            CollectionAssert.AreEquivalent(expectedFrames.Select(frame => frame.Path), importedSpritePaths);
        }

        // NSC-077 AC-003 and VAL-003: runtime code owns its camera-facing constant independently
        // of the Editor builder, and both values remain the contract's literal Euler angles.
        [Test]
        public void RuntimeAndBuilderCameraEulerAnglesMatchExactly()
        {
            Vector3 expected = new Vector3(30f, -45f, 0f);
            Vector3 builderAngles = EditorCameraEulerAngles();

            AssertVector3Exactly(expected, builderAngles, "builder");
            AssertVector3Exactly(
                expected,
                EnemyAnimationController.IsometricCameraEulerAngles,
                "runtime controller");
            AssertVector3Exactly(
                builderAngles,
                EnemyAnimationController.IsometricCameraEulerAngles,
                "runtime/editor agreement");
        }

        // NSC-077 AC-004 and VAL-002: two exact 16-state controllers, same-named clips, and
        // exact enemy/direction/frame SpriteRenderer mappings.
        [Test]
        public void GeneratedEnemyControllersHaveExactStateClipAndSpriteMappings()
        {
            var allExpectedClipPaths = new HashSet<string>();
            foreach (EnemyDefinition enemy in Enemies)
            {
                string controllerPath = GeneratedRoot + "/" + enemy.AnimatorName +
                    "Animator.controller";
                AnimatorController controller =
                    AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
                Assert.IsNotNull(controller, controllerPath);
                Assert.AreEqual(1, controller.layers.Length, controllerPath);

                ChildAnimatorState[] childStates = controller.layers[0].stateMachine.states;
                Assert.AreEqual(16, childStates.Length, controllerPath);
                Assert.AreEqual(16, childStates.Select(child => child.state.name).Distinct().Count(),
                    controllerPath);
                Dictionary<string, AnimatorState> states = childStates.ToDictionary(
                    child => child.state.name, child => child.state);

                var expectedStateNames = new HashSet<string>();
                foreach (DirectionDefinition direction in Directions)
                {
                    string idleName = enemy.AnimatorName + "_idle_" + direction.Name;
                    AssertStateAndClip(
                        states,
                        idleName,
                        new[] { IdlePath(enemy.SourceName, direction.Code) },
                        1,
                        expectedStateNames,
                        allExpectedClipPaths);

                    string walkName = enemy.AnimatorName + "_walk_" + direction.Name;
                    AssertStateAndClip(
                        states,
                        walkName,
                        Enumerable.Range(0, 6)
                            .Select(frame => WalkPath(enemy.SourceName, direction.Code, frame))
                            .ToArray(),
                        12,
                        expectedStateNames,
                        allExpectedClipPaths);
                }

                CollectionAssert.AreEquivalent(expectedStateNames, states.Keys);
                CollectionAssert.AreEquivalent(
                    expectedStateNames,
                    controller.animationClips.Select(clip => clip.name));
            }

            string[] generatedClips = AssetDatabase.FindAssets("t:AnimationClip", new[] { GeneratedRoot })
                .Select(AssetDatabase.GUIDToAssetPath)
                .ToArray();
            Assert.AreEqual(32, generatedClips.Length);
            CollectionAssert.AreEquivalent(allExpectedClipPaths, generatedClips);
        }

        // NSC-077 AC-001/AC-007/AC-008 and VAL-003: the committed production scene contains
        // the existing five moving enemies and four stationary Lantern Wraiths with generated art.
        [Test]
        public void SavedSceneEnemiesUseGeneratedArtControllersAndExistingGameplaySetup()
        {
            Scene scene = SceneManager.GetActiveScene();
            Assert.AreEqual(ScenePath, scene.path);
            GameObject enemiesRoot = scene.GetRootGameObjects()
                .SingleOrDefault(root => root.name == "Enemies");
            Assert.IsNotNull(enemiesRoot);

            GameObject[] enemies = Enumerable.Range(0, enemiesRoot.transform.childCount)
                .Select(index => enemiesRoot.transform.GetChild(index).gameObject)
                .ToArray();
            GameObject[] meleeEnemies = enemies.Where(enemy => enemy.name == "MeleeEnemy").ToArray();
            GameObject[] wraiths = enemies.Where(enemy => enemy.name == "LanternWraith").ToArray();
            Assert.AreEqual(5, meleeEnemies.Length);
            Assert.AreEqual(4, wraiths.Length);
            Assert.AreEqual(9, enemies.Length);
            Assert.IsFalse(enemies.Any(enemy => enemy.name == "FireCasterEnemy"));

            GameObject[] sceneObjects = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<Transform>(true))
                .Select(item => item.gameObject)
                .ToArray();
            foreach (GameObject sceneObject in sceneObjects)
            {
                Assert.AreEqual(
                    0,
                    GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(sceneObject),
                    "Saved scene has a missing script on " + HierarchyPath(sceneObject.transform));
            }

            CollectionAssert.AreEquivalent(
                new[]
                {
                    new Vector3(-6f, 0f, 10f),
                    new Vector3(7f, 0f, 31f),
                    new Vector3(-7f, 0f, 53f),
                    new Vector3(8f, 0f, 74f),
                    new Vector3(-8f, 0f, 77f)
                },
                meleeEnemies.Select(enemy => enemy.transform.position).ToArray());
            CollectionAssert.AreEquivalent(
                new[]
                {
                    new Vector3(7f, 0f, 13f),
                    new Vector3(-9f, 0f, 27f),
                    new Vector3(8f, 0f, 57f),
                    new Vector3(0f, 0f, 70f)
                },
                wraiths.Select(enemy => enemy.transform.position).ToArray());

            SpriteRenderer doorRenderer = scene.GetRootGameObjects()
                .Single(root => root.name == "DoorRoot")
                .transform.Find("DoorVisual/DoorSprite")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(doorRenderer);

            NavMeshBuildSettings navigationSettings = NavMesh.GetSettingsByIndex(0);
            foreach (GameObject enemy in meleeEnemies)
            {
                AssertEnemyVisualAndAnimator(
                    enemy,
                    "melee",
                    "MeleeEnemyAnimator.controller",
                    EnemyAnimationKind.MeleeEnemy,
                    doorRenderer);
                Assert.AreEqual(1, enemy.GetComponents<EnemyTargetKnowledge>().Length);
                Assert.AreEqual(1, enemy.GetComponents<EnemyPursuitMovement>().Length);
                Assert.AreEqual(1, enemy.GetComponents<EnemyHealth>().Length);
                Assert.AreEqual(0, enemy.GetComponents<EnemyLanternWispCaster>().Length);

                NavMeshAgent agent = enemy.GetComponent<NavMeshAgent>();
                Assert.IsNotNull(agent);
                Assert.AreEqual(navigationSettings.agentTypeID, agent.agentTypeID);
                Assert.That(agent.radius, Is.EqualTo(navigationSettings.agentRadius).Within(0.001f));
                Assert.That(agent.height, Is.EqualTo(navigationSettings.agentHeight).Within(0.001f));
                Assert.That(agent.speed, Is.EqualTo(2.2f).Within(0.001f));
                Assert.That(agent.acceleration, Is.EqualTo(12f).Within(0.001f));
                Assert.That(agent.angularSpeed, Is.EqualTo(720f).Within(0.001f));
                Assert.That(agent.stoppingDistance, Is.EqualTo(0.6f).Within(0.001f));
                Assert.IsTrue(agent.autoBraking);
            }

            foreach (GameObject wraith in wraiths)
            {
                AssertEnemyVisualAndAnimator(
                    wraith,
                    "ranged",
                    "LanternWraithAnimator.controller",
                    EnemyAnimationKind.LanternWraith,
                    doorRenderer);
                Assert.AreEqual(1, wraith.GetComponents<EnemyLanternWispCaster>().Length);
                Assert.AreEqual(1, wraith.GetComponents<EnemyHealth>().Length);
                Assert.AreEqual(0, wraith.GetComponents<NavMeshAgent>().Length);
                Assert.AreEqual(0, wraith.GetComponents<EnemyTargetKnowledge>().Length);
                Assert.AreEqual(0, wraith.GetComponents<EnemyPursuitMovement>().Length);
            }

        }

        private static void AssertSourceImport(ExpectedFrame frame, int walkGroundLineFromTop)
        {
            TextureImporter importer = AssetImporter.GetAtPath(frame.Path) as TextureImporter;
            Assert.IsNotNull(importer, frame.Path);
            Assert.AreEqual(TextureImporterType.Sprite, importer.textureType, frame.Path);
            Assert.AreEqual(TextureImporterShape.Texture2D, importer.textureShape, frame.Path);
            Assert.AreEqual(SpriteImportMode.Single, importer.spriteImportMode, frame.Path);
            Assert.AreEqual(FilterMode.Point, importer.filterMode, frame.Path);
            Assert.AreEqual(TextureImporterCompression.Uncompressed, importer.textureCompression,
                frame.Path);
            Assert.IsFalse(importer.mipmapEnabled, frame.Path);
            Assert.AreEqual(EnemyAnimationAssetBuilder.EnemyPixelsPerUnit,
                importer.spritePixelsPerUnit, frame.Path);

            AssertSerializedZero(importer, "m_ApplyGammaDecoding", frame.Path);
            AssertSerializedZero(importer, "m_CookieLightType", frame.Path);

            var settings = new TextureImporterSettings();
            importer.ReadTextureSettings(settings);
            Assert.AreEqual((int)SpriteAlignment.Custom, settings.spriteAlignment, frame.Path);
            Assert.That(settings.spritePivot.x, Is.EqualTo(0.5f).Within(0.0001f), frame.Path);

            int size = frame.IsWalk ? WalkSize : IdleSize;
            int groundLine = frame.IsWalk
                ? size - walkGroundLineFromTop
                : FindGroundLineFromBottom(frame.Path);
            groundLine += EnemyAnimationAssetBuilder.PivotCorrectionPixels(
                frame.Enemy.SourceName, frame.Direction.Name);
            float expectedPivotY = groundLine / (float)size;
            Assert.That(settings.spritePivot.y, Is.EqualTo(expectedPivotY).Within(0.0001f),
                frame.Path);

            Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(frame.Path);
            Assert.IsNotNull(sprite, frame.Path);
            Assert.That(sprite.rect.width, Is.EqualTo(size).Within(0.001f), frame.Path);
            Assert.That(sprite.rect.height, Is.EqualTo(size).Within(0.001f), frame.Path);
            Assert.That(sprite.pivot.x, Is.EqualTo(size * 0.5f).Within(0.001f), frame.Path);
            Assert.That(sprite.pivot.y, Is.EqualTo(groundLine).Within(0.001f), frame.Path);
        }

        private static void AssertSerializedZero(TextureImporter importer, string propertyName,
            string path)
        {
            var serializedImporter = new SerializedObject(importer);
            SerializedProperty property = serializedImporter.FindProperty(propertyName);
            Assert.IsNotNull(property, path + " " + propertyName);
            if (property.propertyType == SerializedPropertyType.Boolean)
            {
                Assert.IsFalse(property.boolValue, path + " " + propertyName);
            }
            else
            {
                Assert.AreEqual(0, property.intValue, path + " " + propertyName);
            }
        }

        private static int FindGroundLineFromBottom(string path)
        {
            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                Assert.IsTrue(texture.LoadImage(File.ReadAllBytes(path)), path);
                Color32[] pixels = texture.GetPixels32();
                for (int y = 0; y < texture.height; y++)
                {
                    int rowStart = y * texture.width;
                    for (int x = 0; x < texture.width; x++)
                    {
                        if (pixels[rowStart + x].a > 0) return y;
                    }
                }
            }
            finally
            {
                Object.DestroyImmediate(texture);
            }

            Assert.Fail("No opaque pixels: " + path);
            return -1;
        }

        private static void AssertStateAndClip(
            IReadOnlyDictionary<string, AnimatorState> states,
            string expectedName,
            IReadOnlyList<string> expectedSourcePaths,
            int expectedFrameRate,
            ISet<string> expectedStateNames,
            ISet<string> expectedClipPaths)
        {
            Assert.IsTrue(expectedStateNames.Add(expectedName), expectedName);
            Assert.IsTrue(states.TryGetValue(expectedName, out AnimatorState state), expectedName);

            string clipPath = GeneratedRoot + "/" + expectedName + ".anim";
            Assert.IsTrue(expectedClipPaths.Add(clipPath), clipPath);
            AnimationClip clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
            Assert.IsNotNull(clip, clipPath);
            Assert.AreSame(clip, state.motion, expectedName);
            Assert.AreEqual(expectedName, clip.name, clipPath);
            Assert.AreEqual(expectedFrameRate, clip.frameRate, clipPath);
            Assert.IsTrue(AnimationUtility.GetAnimationClipSettings(clip).loopTime, clipPath);
            Assert.AreEqual(0, AnimationUtility.GetCurveBindings(clip).Length, clipPath);

            EditorCurveBinding[] bindings = AnimationUtility.GetObjectReferenceCurveBindings(clip);
            Assert.AreEqual(1, bindings.Length, clipPath);
            Assert.AreEqual("Visual", bindings[0].path, clipPath);
            Assert.AreEqual(typeof(SpriteRenderer), bindings[0].type, clipPath);
            Assert.AreEqual("m_Sprite", bindings[0].propertyName, clipPath);

            ObjectReferenceKeyframe[] keyframes =
                AnimationUtility.GetObjectReferenceCurve(clip, bindings[0]);
            Assert.AreEqual(expectedSourcePaths.Count, keyframes.Length, clipPath);
            for (int frame = 0; frame < expectedSourcePaths.Count; frame++)
            {
                string sourcePath = expectedSourcePaths[frame];
                Sprite expectedSprite = AssetDatabase.LoadAssetAtPath<Sprite>(sourcePath);
                Assert.IsNotNull(expectedSprite, sourcePath);
                Assert.That(keyframes[frame].time,
                    Is.EqualTo(frame / (float)expectedFrameRate).Within(0.0001f), clipPath);
                Assert.AreSame(expectedSprite, keyframes[frame].value, clipPath + " frame " + frame);
                Assert.AreEqual(sourcePath, AssetDatabase.GetAssetPath(keyframes[frame].value), clipPath);
            }
        }

        private static void AssertEnemyVisualAndAnimator(
            GameObject enemy,
            string sourceEnemyName,
            string controllerFileName,
            EnemyAnimationKind kind,
            SpriteRenderer doorRenderer)
        {
            Assert.AreEqual(1, enemy.GetComponents<EnemyAnimationController>().Length, enemy.name);
            EnemyAnimationController animation = enemy.GetComponent<EnemyAnimationController>();
            Assert.IsNotNull(animation);

            Animator animator = enemy.GetComponent<Animator>();
            Assert.IsNotNull(animator, enemy.name);
            Assert.AreEqual(1, enemy.GetComponents<Animator>().Length, enemy.name);
            RuntimeAnimatorController expectedController =
                AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(
                    GeneratedRoot + "/" + controllerFileName);
            Assert.IsNotNull(expectedController);
            Assert.AreSame(expectedController, animator.runtimeAnimatorController, enemy.name);

            SpriteRenderer renderer = enemy.transform.Find("Visual")?.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(renderer, enemy.name);
            Sprite southIdle = AssetDatabase.LoadAssetAtPath<Sprite>(
                IdlePath(sourceEnemyName, "s"));
            Assert.IsNotNull(southIdle);
            Assert.AreSame(southIdle, renderer.sprite, enemy.name);
            Assert.AreEqual(Vector3.one, renderer.transform.localScale, enemy.name);
            Quaternion expectedRotation = Quaternion.Euler(30f, -45f, 0f);
            Assert.That(Quaternion.Angle(expectedRotation, renderer.transform.rotation),
                Is.LessThan(0.01f), enemy.name + " Visual must face the isometric camera.");
            Assert.AreEqual(doorRenderer.sortingLayerName, renderer.sortingLayerName, enemy.name);
            Assert.AreEqual(doorRenderer.sortingOrder, renderer.sortingOrder, enemy.name);
            Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint, enemy.name);

            string expectedInitialState = kind + "_idle_south";
            Assert.IsTrue(animator.runtimeAnimatorController.animationClips
                .Any(clip => clip.name == expectedInitialState), enemy.name);
        }

        private static Vector3 EditorCameraEulerAngles()
        {
            Type builderType = typeof(EnemyAnimationAssetBuilder).Assembly.GetType(
                "NoSafeCircle.DoorPrototype.Editor.World.DoorPrototypeGlobalSceneBuilder");
            Assert.IsNotNull(builderType);
            FieldInfo field = builderType.GetField(
                "IsometricCameraEulerAngles",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.IsNotNull(field);
            return (Vector3)field.GetValue(null);
        }

        private static void AssertVector3Exactly(
            Vector3 expected,
            Vector3 actual,
            string context)
        {
            Assert.AreEqual(expected.x, actual.x, context + " x");
            Assert.AreEqual(expected.y, actual.y, context + " y");
            Assert.AreEqual(expected.z, actual.z, context + " z");
        }

        private static string HierarchyPath(Transform item)
        {
            string path = item.name;
            while (item.parent != null)
            {
                item = item.parent;
                path = item.name + "/" + path;
            }

            return path;
        }

        private static IEnumerable<ExpectedFrame> ExpectedFrames()
        {
            foreach (EnemyDefinition enemy in Enemies)
            {
                foreach (DirectionDefinition direction in Directions)
                {
                    yield return new ExpectedFrame(
                        IdlePath(enemy.SourceName, direction.Code), enemy, direction, false, 0);
                    for (int frame = 0; frame < 6; frame++)
                    {
                        yield return new ExpectedFrame(
                            WalkPath(enemy.SourceName, direction.Code, frame),
                            enemy,
                            direction,
                            true,
                            frame);
                    }
                }
            }
        }

        private static string IdlePath(string enemy, string directionCode)
        {
            return SourceRoot + "/enemy_" + enemy + "_" + directionCode + "_idle_00.png";
        }

        private static string WalkPath(string enemy, string directionCode, int frame)
        {
            return WalkRoot + "/enemy_" + enemy + "_" + directionCode + "_walk_" +
                frame.ToString("00") + ".png";
        }

        private readonly struct EnemyDefinition
        {
            public readonly string SourceName;
            public readonly string AnimatorName;

            public EnemyDefinition(string sourceName, string animatorName)
            {
                SourceName = sourceName;
                AnimatorName = animatorName;
            }
        }

        private readonly struct DirectionDefinition
        {
            public readonly string Code;
            public readonly string Name;

            public DirectionDefinition(string code, string name)
            {
                Code = code;
                Name = name;
            }
        }

        private readonly struct ExpectedFrame
        {
            public readonly string Path;
            public readonly EnemyDefinition Enemy;
            public readonly DirectionDefinition Direction;
            public readonly bool IsWalk;
            public readonly int FrameIndex;

            public ExpectedFrame(string path, EnemyDefinition enemy, DirectionDefinition direction,
                bool isWalk, int frameIndex)
            {
                Path = path;
                Enemy = enemy;
                Direction = direction;
                IsWalk = isWalk;
                FrameIndex = frameIndex;
            }
        }

        [Serializable]
        private sealed class WalkInventory
        {
            public int[] canvas_size;
            public int alpha_bottom_y_from_top;
            public WalkInventoryEntry[] entries;
        }

        [Serializable]
        private sealed class WalkInventoryEntry
        {
            public string file;
            public string archetype;
            public string direction;
            public int selected_frame_index;
        }
    }
}
