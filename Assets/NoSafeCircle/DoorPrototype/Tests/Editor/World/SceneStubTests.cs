using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.World;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Tilemaps;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    /// <summary>
    /// The runtime scene is a STUB and must stay one.
    /// </summary>
    /// <remarks>
    /// <para>
    /// WHAT THIS FIXTURE IS FOR, and it is not what a scene test usually does. Vincent, 2026-09-26:
    /// "I never want to work in these big scenes. Lets create everything with instantiate from now
    /// on." The value of RuntimeWorld.unity is everything it does NOT contain. A scene with one
    /// prefab instance in it can be merged, reviewed and reasoned about; the moment someone bakes a
    /// wall into it, it becomes the artifact that cannot be merged and the whole partition collapses
    /// - quietly, because a baked scene looks correct and plays correctly.
    /// </para>
    /// <para>
    /// SO THESE TESTS COUNT WHAT SURVIVES RATHER THAN CHECKING WHAT IS THERE. This workspace learned
    /// that the hard way on BoneArchiveSceneTests, which asserted wall transforms, an exact collider
    /// count and Renderer.bounds three times, and could not see seven blockout cubes that should not
    /// have existed - because every assertion it made was about an object being CORRECT, and an
    /// object that should not exist is correct by every such measure. The expected counts below are
    /// derived from the design (one manager, one camera, one light) rather than from the scene, so
    /// the scene cannot supply its own expectations.
    /// </para>
    /// </remarks>
    public sealed class SceneStubTests
    {
        private const string ScenePath = "Assets/Scenes/RuntimeWorld.unity";
        private const string ManagersPrefabPath =
            "Assets/NoSafeCircle/DoorPrototype/Resources/GameManagers.prefab";
        private const string SpawnerFolder =
            "Assets/NoSafeCircle/DoorPrototype/Resources/Spawners";

        /// <summary>
        /// The only three roots the runtime scene may hold, and why each is allowed.
        /// GameManagers builds the world. The camera and the light are PLACEHOLDERS: they belong to
        /// the Player and Rooms lanes and are expected to leave this scene when those lanes ship.
        /// Nothing may be ADDED to this list without a reason written next to it.
        /// </summary>
        private static readonly string[] AllowedRoots = { "GameManagers", "Main Camera", "Directional Light" };

        private static Scene OpenSceneForReading()
        {
            Assert.IsTrue(System.IO.File.Exists(ScenePath),
                ScenePath + " does not exist. The runtime scene is what the game is played from.");
            return EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
        }

        [Test]
        public void TheSceneHoldsOnlyTheAllowedRoots()
        {
            Scene scene = OpenSceneForReading();
            GameObject[] roots = scene.GetRootGameObjects();

            var names = new List<string>();
            foreach (GameObject root in roots)
            {
                names.Add(root.name);
            }

            Assert.AreEqual(AllowedRoots.Length, roots.Length,
                "The runtime scene holds " + roots.Length + " roots (" + string.Join(", ", names)
                + ") and may hold exactly " + AllowedRoots.Length + " (" + string.Join(", ", AllowedRoots)
                + "). Anything else in this scene is content that should have been a prefab "
                + "instantiated by a spawner. See Vincent's decision of 2026-09-26.");

            foreach (string allowed in AllowedRoots)
            {
                Assert.Contains(allowed, names, "The runtime scene is missing its " + allowed + " root.");
            }
        }

        [Test]
        public void TheManagersRootIsAPrefabInstanceCarryingTheBootstrap()
        {
            Scene scene = OpenSceneForReading();
            GameObject managers = null;
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                if (root.name == "GameManagers")
                {
                    managers = root;
                }
            }

            Assert.IsNotNull(managers, "The runtime scene has no GameManagers root.");

            // A PREFAB INSTANCE, not a loose object. If someone unpacks it, the manager's
            // configuration stops being editable outside the scene and the scene starts changing
            // again - which is the exact thing this whole design removed.
            Assert.AreEqual(PrefabInstanceStatus.Connected,
                PrefabUtility.GetPrefabInstanceStatus(managers),
                "GameManagers is in the scene but is not a connected prefab instance. Editing it "
                + "would change the scene file instead of the prefab.");

            Object source = PrefabUtility.GetCorrespondingObjectFromSource(managers);
            Assert.IsNotNull(source, "GameManagers has no source prefab.");
            Assert.AreEqual(ManagersPrefabPath, AssetDatabase.GetAssetPath(source),
                "GameManagers points at a different prefab than the committed one.");

            Assert.IsNotNull(managers.GetComponent<GameBootstrap>(),
                "GameManagers carries no GameBootstrap, so nothing would build the world at Play.");
        }

        [Test]
        public void TheSceneContainsNoBakedWorldContent()
        {
            // THE ANTI-BAKE ASSERTION, and it is the load-bearing one in this file. Every one of
            // these component types is world content that used to be generated into a scene at edit
            // time. Finding any of them here means something was baked - and a baked scene passes
            // every other test in the repository, which is why this check has to exist separately
            // and has to be about ABSENCE.
            Scene scene = OpenSceneForReading();

            int sprites = 0;
            int tilemaps = 0;
            int colliders = 0;
            int meshes = 0;

            foreach (GameObject root in scene.GetRootGameObjects())
            {
                sprites += root.GetComponentsInChildren<SpriteRenderer>(true).Length;
                tilemaps += root.GetComponentsInChildren<Tilemap>(true).Length;
                colliders += root.GetComponentsInChildren<Collider>(true).Length;
                meshes += root.GetComponentsInChildren<MeshRenderer>(true).Length;
            }

            Assert.AreEqual(0, sprites, "The runtime scene contains " + sprites
                + " SpriteRenderer(s). Props and wall art are instantiated at Play, never baked.");
            Assert.AreEqual(0, tilemaps, "The runtime scene contains " + tilemaps
                + " Tilemap(s). Floors are painted at Play by a spawner, never baked.");
            Assert.AreEqual(0, colliders, "The runtime scene contains " + colliders
                + " Collider(s). Gameplay collision comes from prefabs and from the wall spawner.");
            Assert.AreEqual(0, meshes, "The runtime scene contains " + meshes
                + " MeshRenderer(s). Blockout primitives do not belong in the runtime scene.");
        }

        [Test]
        public void EverySpawnerPrefabIsASpawnerAndDoesNotSpawnItself()
        {
            // THE FOLDER IS THE REGISTRY, so the folder is what gets checked. A lane ships one
            // prefab here and is wired in by existing; this asserts the two rules that makes safe.
            string[] guids = AssetDatabase.FindAssets("t:Prefab", new[] { SpawnerFolder });
            Assert.Greater(guids.Length, 0,
                SpawnerFolder + " holds no prefabs, so GameBootstrap would build an empty world.");

            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);

                var spawner = prefab.GetComponent<ISpawner>();
                Assert.IsNotNull(spawner,
                    path + " is in the spawner folder but has no ISpawner component, so "
                    + "GameBootstrap will warn and skip it and that family will never appear.");

                // Instantiating an ACTIVE prefab runs its Awake immediately, which would place that
                // family before GameBootstrap has finished instantiating the others - out of phase
                // order, and before Rooms exist. The order is the one thing seven independent lanes
                // must agree on, so a lane cannot be allowed to opt out of it by accident.
                var propSpawner = prefab.GetComponent<PropSpawner>();
                if (propSpawner != null)
                {
                    SerializedProperty spawnOnAwake =
                        new SerializedObject(propSpawner).FindProperty("spawnOnAwake");
                    Assert.IsNotNull(spawnOnAwake,
                        "PropSpawner no longer has a spawnOnAwake field; this check needs updating "
                        + "rather than deleting - the rule it enforces has not changed.");
                    Assert.IsFalse(spawnOnAwake.boolValue,
                        path + " spawns on Awake. GameBootstrap owns the build order; a spawner "
                        + "that starts itself runs before Rooms exist.");
                }
            }
        }

        [Test]
        public void ThePlaceholderCameraUsesTheGamesIsometricConvention()
        {
            // A SCENE YOU CANNOT SEE ANYTHING IN IS NOT USEFUL, and the default camera Unity puts
            // in a new scene is perspective, size 5, at (0,1,-10) looking down +Z. Against a level
            // spanning Z -26 to 104 that frames nothing at all.
            //
            // THE FOUR VALUES BELOW ARE LITERALS ON PURPOSE. The builder's own constants -
            // DoorPrototypeGlobalSceneBuilder.IsometricCameraEulerAngles and
            // IsometricOrthographicSize - are `internal` to the Editor assembly, which this test
            // assembly cannot see (no InternalsVisibleTo exists anywhere under Assets; that exact
            // fact is what left NSC-045 unrecoverable). Reading them would also be the WRONG shape
            // even if it compiled: an expected value taken from the thing under test agrees with it
            // by construction. An independent literal is what pins a convention.
            Scene scene = OpenSceneForReading();
            Camera camera = null;
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                Camera found = root.GetComponentInChildren<Camera>(true);
                if (found != null)
                {
                    camera = found;
                }
            }

            Assert.IsNotNull(camera, "The runtime scene has no camera, so Play renders nothing.");

            Assert.IsTrue(camera.orthographic,
                "The camera is perspective. The game's presentation is fixed 2:1 dimetric "
                + "isometric, which requires an orthographic camera - a perspective one projects "
                + "the tilemap a second time and the floor diamonds stop lining up.");
            Assert.AreEqual(8f, camera.orthographicSize, 0.001f,
                "The camera's orthographic size is " + camera.orthographicSize
                + "; the game uses 8.");

            Vector3 euler = camera.transform.rotation.eulerAngles;
            Assert.AreEqual(30f, Mathf.DeltaAngle(0f, euler.x), 0.01f,
                "Camera tilt is " + euler.x + " degrees, not the 30 the isometric convention uses.");
            Assert.AreEqual(-45f, Mathf.DeltaAngle(0f, euler.y), 0.01f,
                "Camera yaw is " + euler.y + " degrees, not the -45 that faces a corner.");

            // THE SORTING CONVENTION IS THE PART THAT FAILS SILENTLY. transparencySortMode and
            // transparencySortAxis are not serialized into a scene by every supported editor
            // version - IsometricCameraFollow says so in its own comment and re-applies both in
            // OnEnable, which is why the COMPONENT is what this asserts rather than the fields.
            // Without it, world sprites sort by distance instead of along the isometric axis and a
            // door renders in front of a wizard standing south of it. That bug has happened here.
            var follow = camera.GetComponent<NoSafeCircle.DoorPrototype.IsometricCameraFollow>();
            Assert.IsNotNull(follow,
                "The camera has no IsometricCameraFollow, so nothing re-applies "
                + "transparencySortMode = CustomAxis and the isometric sort axis when the scene "
                + "loads. Sprite sorting will be wrong and it will look like an art bug.");
        }
    }
}
