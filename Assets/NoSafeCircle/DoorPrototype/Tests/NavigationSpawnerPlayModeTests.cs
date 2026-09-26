using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Text.RegularExpressions;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Navigation;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;
using Stopwatch = System.Diagnostics.Stopwatch;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Proves the Navigation lane at runtime with the REAL NavigationSpawner: the bake reads physics
    // colliders and not renderers, it is configured from ProjectSettings, it carves around solids,
    // a second Spawn() replaces the surface rather than doubling it, and the ignoreFromBuild
    // exclusion every later lane depends on actually works. Nothing here loads a scene.
    //
    // EVERY EXPECTED VALUE NAMES ITS SOURCE, and none comes from the spawner. Sample points come
    // from this fixture's own geometry or from the ten authored spawn points; agent numbers come
    // from NavMesh.GetSettingsByIndex(0), which is ProjectSettings/NavMeshAreas.asset; the surface's
    // settings are read back by reflection because NavMeshSurface lives in the Unity.AI.Navigation
    // assembly, which NSC-089 AC-002 lets only the runtime assembly reference - the same route
    // NavMeshAgentConfigurationTests takes, and the reason the modifier is added through
    // NavMeshRebakeExclusion.Apply rather than named here.
    //
    // WHY 0.1. It is AC-006's number (NSC-055): NavMesh.SamplePosition must succeed within 0.1 of an
    // authored spawn point. The older fixtures sample at 2.0, which any surface in the neighbourhood
    // satisfies; 0.1 is the gate the game is actually held to, and one measured LowerVault point
    // failed it at 0.129 (DoorPrototypeGlobalSceneBuilder.cs, the EnemySpawnPositions comment).
    public sealed class NavigationSpawnerPlayModeTests
    {
        private const float SampleTolerance = 0.1f;

        // THE NINE AUTHORED ENEMY SPAWN POINTS, pinned VERBATIM from
        // Editor/World/DoorPrototypeGlobalSceneBuilder.cs - EnemySpawnPositions (lines 373-389) and
        // LanternWraithSpawnPositions (401-419) - which this assembly cannot reference. The tenth,
        // RuinedEntryLayout.PlayerStart, is runtime and is read live. None is on any lattice, and
        // (-4.5, 0, 64.75) sits where it does because (-2, 0, 66) measured 0.129 from the surface.
        private static readonly Vector3[] PinnedEnemySpawnPoints =
        {
            new Vector3(1.25f, 0f, 10f),
            new Vector3(-2f, 0f, 36f),
            new Vector3(-4.5f, 0f, 64.75f),
            new Vector3(-2f, 0f, 86f),
            new Vector3(4f, 0f, 95f),
            new Vector3(9f, 0f, 16f),
            new Vector3(0f, 0f, 45f),
            new Vector3(2f, 0f, 56f),
            new Vector3(10f, 0f, 80f),
        };

        private GameObject root;
        private NavigationSpawner spawner;
        private Texture2D spriteTexture;
        private Sprite sprite;

        [SetUp]
        public void SetUp()
        {
            root = new GameObject("NavigationSpawnerTestRoot");
            var spawnerObject = new GameObject("NavigationSpawner");
            spawnerObject.transform.SetParent(root.transform, false);
            spawner = spawnerObject.AddComponent<NavigationSpawner>();
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            if (spawner != null && spawner.Surface != null)
            {
                spawner.Surface.ClearBakedData();
            }

            if (root != null) Object.Destroy(root);
            if (sprite != null) Object.Destroy(sprite);
            if (spriteTexture != null) Object.Destroy(spriteTexture);
            root = null;
            spawner = null;
            sprite = null;
            spriteTexture = null;

            // One frame, so every Destroy above has completed before the next test counts the
            // scene's colliders or bakes over them.
            yield return null;
        }

        // ----------------------------------------------------------------------------------------
        // Fixture geometry
        // ----------------------------------------------------------------------------------------

        // The Rooms lane's floor shape: a BoxCollider whose TOP is at y = 0 - centre y -0.25, height
        // 0.5 - copied from the editor room builders' CreateVisualAndCollision("Floor", ...)
        // (Editor/Rooms/BoneArchiveSceneBuilder.cs:55-57), which the runtime floors replace. The
        // spawn points are authored at y = 0 against exactly this shape.
        private BoxCollider AddFloor(Vector3 centreXZ, float sizeX, float sizeZ)
        {
            var floor = new GameObject("FloorCollision");
            floor.transform.SetParent(root.transform, false);
            var box = floor.AddComponent<BoxCollider>();
            box.center = new Vector3(centreXZ.x, -0.25f, centreXZ.z);
            box.size = new Vector3(sizeX, 0.5f, sizeZ);
            return box;
        }

        private BoxCollider AddDefaultFloor()
        {
            return AddFloor(Vector3.zero, 40f, 40f);
        }

        // A solid cube of the given edge, centred at `centre` (so a 2-unit box at y = 1 stands on
        // the floor). The agent radius from ProjectSettings then erodes the walkable area around it.
        private GameObject AddSolidBox(string name, Vector3 centre, float edge, Transform parent = null)
        {
            var box = new GameObject(name);
            box.transform.SetParent(parent != null ? parent : root.transform, false);
            box.transform.position = centre;
            box.AddComponent<BoxCollider>().size = Vector3.one * edge;
            return box;
        }

        private static bool Samples(Vector3 point)
        {
            return NavMesh.SamplePosition(point, out _, SampleTolerance, NavMesh.AllAreas);
        }

        // ----------------------------------------------------------------------------------------
        // Reading the surface without referencing the package assembly
        // ----------------------------------------------------------------------------------------

        private static object ReadPublicProperty(object instance, string name)
        {
            PropertyInfo property = instance.GetType()
                .GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
            Assert.IsNotNull(property,
                "Expected a public property '" + name + "' on " + instance.GetType().Name + ".");
            return property.GetValue(instance);
        }

        private static object SurfaceOf(NavigationSpawner subject)
        {
            Assert.IsNotNull(subject.Surface, "Spawn() left no GameplayNavigationSurface behind.");
            object surface = ReadPublicProperty(subject.Surface, "Surface");
            Assert.IsNotNull(surface, "GameplayNavigationSurface.Surface resolved no NavMeshSurface.");
            return surface;
        }

        // NavMeshSurface.activeSurfaces is the package's own registry of enabled surfaces
        // (com.unity.ai.navigation 2.0.14, Runtime/NavMeshSurface.cs:174), which fails differently
        // from counting GameObjects in the hierarchy.
        private static int ActiveSurfaceCount(System.Type surfaceType)
        {
            PropertyInfo active = surfaceType.GetProperty("activeSurfaces",
                BindingFlags.Public | BindingFlags.Static);
            Assert.IsNotNull(active,
                "Expected a public static 'activeSurfaces' on " + surfaceType.Name + ".");
            return ((System.Collections.ICollection)active.GetValue(null)).Count;
        }

        // ----------------------------------------------------------------------------------------
        // Tests
        // ----------------------------------------------------------------------------------------

        [UnityTest]
        public IEnumerator Spawn_BakesFromPhysicsCollidersNotFromRenderers()
        {
            // The floor is a collider with NO renderer, so it is walkable only if colliders are
            // collected. The two controls are renderers with NO collider, far from the floor: a
            // SpriteRenderer, which is what this game draws its world with, and a mesh quad, which
            // is exactly what useGeometry = RenderMeshes would collect. Neither may become walkable.
            AddDefaultFloor();

            var spriteOnly = new GameObject("SpriteOnly");
            spriteOnly.transform.SetParent(root.transform, false);
            spriteOnly.transform.position = new Vector3(100f, 0f, 100f);
            spriteOnly.transform.rotation = Quaternion.Euler(90f, 0f, 0f);
            spriteTexture = new Texture2D(4, 4);
            // 4 px at 0.2 px per unit = a 20 x 20 unit sprite, lying flat on the y = 0 plane.
            sprite = Sprite.Create(spriteTexture, new Rect(0f, 0f, 4f, 4f), new Vector2(0.5f, 0.5f), 0.2f);
            var spriteRenderer = spriteOnly.AddComponent<SpriteRenderer>();
            spriteRenderer.sprite = sprite;
            Assert.AreEqual(20f, spriteRenderer.bounds.size.x, 0.01f,
                "The sprite control is not 20 units wide, so it would be a weak control.");

            GameObject meshOnly = GameObject.CreatePrimitive(PrimitiveType.Quad);
            meshOnly.name = "MeshOnly";
            meshOnly.transform.SetParent(root.transform, false);
            // CreatePrimitive adds a MeshCollider; remove it NOW, not deferred, or it is baked.
            Object.DestroyImmediate(meshOnly.GetComponent<Collider>());
            meshOnly.transform.position = new Vector3(-100f, 0f, -100f);
            meshOnly.transform.rotation = Quaternion.Euler(90f, 0f, 0f);
            meshOnly.transform.localScale = new Vector3(20f, 20f, 1f);
            Assert.IsNull(meshOnly.GetComponent<Collider>(), "The mesh control still has a collider.");

            int count = spawner.Spawn();
            yield return null;

            Assert.AreEqual(1, count, "Spawn() did not report one registered surface.");
            Assert.IsTrue(Samples(Vector3.zero),
                "The floor collider was not baked. With useGeometry = RenderMeshes a floor that has "
                + "no renderer simply vanishes from the bake; PhysicsColliders is the load-bearing "
                + "setting and it is not in effect.");
            Assert.IsFalse(Samples(new Vector3(100f, 0f, 100f)),
                "A SpriteRenderer with no collider became walkable. The bake is reading renderers.");
            Assert.IsFalse(Samples(new Vector3(-100f, 0f, -100f)),
                "A mesh quad with no collider became walkable, which is what a RenderMeshes bake "
                + "does. The bake is reading renderers.");
        }

        [UnityTest]
        public IEnumerator Spawn_ConfiguresTheSurfaceFromProjectSettingsAndParentsItUnderTheSpawner()
        {
            AddDefaultFloor();
            spawner.Spawn();
            yield return null;

            object surface = SurfaceOf(spawner);

            // ProjectSettings/NavMeshAreas.asset through the NavMesh API, not through the surface.
            NavMeshBuildSettings expected = NavMesh.GetSettingsByIndex(0);
            Assert.AreEqual(expected.agentTypeID, (int)ReadPublicProperty(surface, "agentTypeID"),
                "The surface does not bake with the project's single configured agent type.");
            Assert.AreEqual("All", ReadPublicProperty(surface, "collectObjects").ToString(),
                "The surface must collect the whole scene; the geometry belongs to other lanes' objects.");
            // A NavMeshSurface's own default is RenderMeshes, so this is the line that discriminates.
            Assert.AreEqual("PhysicsColliders", ReadPublicProperty(surface, "useGeometry").ToString(),
                "The surface is not reading physics colliders. SpriteRenderers carry no mesh, so a "
                + "RenderMeshes bake sees none of this game's world.");

            Transform child = spawner.transform.Find(NavigationSpawner.SurfaceObjectName);
            Assert.IsNotNull(child,
                "No child named '" + NavigationSpawner.SurfaceObjectName + "' under the spawner; "
                + "output is parented under the spawner so 'what I spawned' is 'my children'.");
            Assert.AreSame(child.gameObject, spawner.Surface.gameObject,
                "The Surface property and the named child are different objects.");
        }

        [UnityTest]
        public IEnumerator Spawn_CarvesAroundASolidCollider()
        {
            AddDefaultFloor();
            // A 2 x 2 x 2 box standing on the floor at the origin occupies x, z in [-1, 1]; the agent
            // radius from ProjectSettings (0.5) erodes the walkable area out to 1.5, so the origin
            // is at least ~1.3 from any walkable surface and (3, 0, 0) is well inside one.
            AddSolidBox("Crate", new Vector3(0f, 1f, 0f), 2f);
            float radius = NavMesh.GetSettingsByIndex(0).agentRadius;
            Assert.Greater(radius, 0f, "ProjectSettings reports a zero agent radius; nothing erodes.");

            int count = spawner.Spawn();
            yield return null;

            Assert.AreEqual(1, count);
            Assert.IsFalse(Samples(Vector3.zero),
                "The centre of a solid 2-unit box is walkable. The box's collider was not baked around.");
            Assert.IsTrue(Samples(new Vector3(3f, 0f, 0f)),
                "3 units from the box (1 + radius " + radius + " = " + (1f + radius) + " is the "
                + "erosion edge) is not walkable, so the bake carved far more than the collider.");

            // Endpoints are taken from the surface itself, as every existing fixture does, so the
            // path query is not also a test of CalculatePath's snapping tolerance.
            Assert.IsTrue(NavMesh.SamplePosition(new Vector3(-5f, 0f, 0f), out NavMeshHit start,
                SampleTolerance, NavMesh.AllAreas), "(-5, 0, 0) is not on the baked floor.");
            Assert.IsTrue(NavMesh.SamplePosition(new Vector3(5f, 0f, 0f), out NavMeshHit end,
                SampleTolerance, NavMesh.AllAreas), "(5, 0, 0) is not on the baked floor.");

            var path = new NavMeshPath();
            Assert.IsTrue(NavMesh.CalculatePath(start.position, end.position, NavMesh.AllAreas, path),
                "No path could be computed across the floor.");
            Assert.AreEqual(NavMeshPathStatus.PathComplete, path.status,
                "The box split the floor in two, so a 2-unit prop is blocking a 40-unit room.");
            // A path straight through the box has exactly two corners; a detour needs at least three.
            Assert.Greater(path.corners.Length, 2,
                "The complete path has only " + path.corners.Length + " corners, so it went "
                + "straight through the box rather than around it.");
        }

        [UnityTest]
        public IEnumerator SpawningTwiceLeavesOneSurfaceAndDoesNotDoubleTheNavMesh()
        {
            AddDefaultFloor();

            int first = spawner.Spawn();
            yield return null;
            int trianglesAfterFirst = NavMesh.CalculateTriangulation().indices.Length;
            Assert.Greater(trianglesAfterFirst, 0, "The first bake produced no triangles at all.");
            System.Type surfaceType = SurfaceOf(spawner).GetType();

            int second = spawner.Spawn();
            yield return null;
            int trianglesAfterSecond = NavMesh.CalculateTriangulation().indices.Length;

            Assert.AreEqual(first, second, "A second Spawn() returned a different count.");
            Assert.AreEqual(1, second, "Spawn() reports " + second + " surfaces; one was asked for.");
            Assert.AreEqual(1, spawner.SpawnedCount);

            int namedChildren = 0;
            foreach (Transform child in spawner.transform)
            {
                if (child.name == NavigationSpawner.SurfaceObjectName) namedChildren++;
            }

            Assert.AreEqual(1, namedChildren,
                "After two Spawn() calls and a frame the spawner holds " + namedChildren + " '"
                + NavigationSpawner.SurfaceObjectName + "' children. The previous one was not destroyed.");
            Assert.AreEqual(1, Object.FindObjectsByType<GameplayNavigationSurface>(FindObjectsSortMode.None).Length,
                "More than one active GameplayNavigationSurface exists in the scene.");
            Assert.AreEqual(1, ActiveSurfaceCount(surfaceType),
                "NavMeshSurface.activeSurfaces holds more than one surface. Either the previous "
                + "surface was not unregistered, or another fixture leaked one - the message names "
                + "the count, not the owner.");
            Assert.AreEqual(trianglesAfterFirst, trianglesAfterSecond,
                "The navigation system holds " + trianglesAfterSecond + " indices after the second "
                + "bake against " + trianglesAfterFirst + " after the first. The re-bake ADDED a "
                + "surface instead of replacing it.");
            Assert.IsTrue(Samples(Vector3.zero), "The floor is no longer walkable after the re-bake.");
        }

        [UnityTest]
        public IEnumerator RebakeIgnoresAnObjectCarryingIgnoreFromBuildAndCollectsOneWithout()
        {
            // THE MECHANISM THE DOORS, PLAYER AND ENEMIES LANES DEPEND ON. Both boxes are added after
            // the first bake and are alive during the second, exactly as a previous build's player or
            // door is alive during a re-bake. The excluded one uses the prefab shape - modifier on the
            // root, collider on a child - and the control has no modifier and MUST carve, or the
            // passing half proves nothing.
            AddDefaultFloor();
            spawner.Spawn();
            yield return null;
            Assert.IsTrue(Samples(Vector3.zero), "Baseline: the origin is walkable before any box exists.");
            Assert.IsTrue(Samples(new Vector3(10f, 0f, 10f)), "Baseline: (10, 0, 10) is walkable.");

            var playerLeftAlive = new GameObject("PlayerLeftAlive");
            playerLeftAlive.transform.SetParent(root.transform, false);
            NavMeshRebakeExclusion.Apply(playerLeftAlive);
            GameObject body = AddSolidBox("Body", new Vector3(0f, 1f, 0f), 2f, playerLeftAlive.transform);
            GameObject control = AddSolidBox("DoorWithoutTheModifier", new Vector3(10f, 1f, 10f), 2f);

            Assert.IsTrue(NavMeshRebakeExclusion.Excludes(body.GetComponent<Collider>()),
                "The helper says the modifier on the root does not cover the child's collider.");
            Assert.IsFalse(NavMeshRebakeExclusion.Excludes(control.GetComponent<Collider>()),
                "The helper says an unmarked collider is excluded.");

            int count = spawner.Spawn();
            yield return null;

            Assert.AreEqual(1, count);
            Assert.IsTrue(Samples(Vector3.zero),
                "The re-bake carved around a collider under a NavMeshModifier with ignoreFromBuild "
                + "and applyToChildren. Every later lane's prefab relies on this exclusion.");
            Assert.IsFalse(Samples(new Vector3(10f, 0f, 10f)),
                "The CONTROL box without a modifier did not carve, so the passing assertion above "
                + "says nothing about the modifier.");
        }

        [UnityTest]
        public IEnumerator Spawn_WithNoCollidersCreatesNothingAndLogsAnError()
        {
            // The haystack: this test's zero is only meaningful if nothing in the scene carries a
            // solid collider. A leak from another fixture is named here rather than mistaken for
            // spawner behaviour.
            var leaked = new List<string>();
            foreach (Collider collider in Object.FindObjectsByType<Collider>(FindObjectsSortMode.None))
            {
                if (collider.enabled && !collider.isTrigger)
                {
                    leaked.Add(NavMeshRebakeExclusion.HierarchyPath(collider.transform));
                }
            }

            Assert.IsEmpty(leaked,
                "Solid colliders exist before this test built anything: " + string.Join(", ", leaked)
                + ". Some fixture is leaking scene objects, and this test cannot run against them.");

            LogAssert.Expect(LogType.Error, new Regex("no enabled non-trigger collider"));
            int count = spawner.Spawn();
            yield return null;

            Assert.AreEqual(0, count, "Spawn() claimed to register a surface with nothing to bake on.");
            Assert.AreEqual(0, spawner.SpawnedCount);
            Assert.IsNull(spawner.Surface, "A surface owner exists after a refused bake.");
            Assert.IsNull(spawner.transform.Find(NavigationSpawner.SurfaceObjectName),
                "A '" + NavigationSpawner.SurfaceObjectName + "' child was created with nothing to bake on.");
        }

        [UnityTest]
        public IEnumerator Spawn_ReportsItsBuildTimeWithinTheBudget()
        {
            AddDefaultFloor();
            LogAssert.Expect(LogType.Log, new Regex("baked over 1 collider"));

            var watch = Stopwatch.StartNew();
            int count = spawner.Spawn();
            watch.Stop();
            yield return null;

            Assert.AreEqual(1, count);
            // 5000 ms is the BUDGET the architecture set for the real five-room floor with 222 prop
            // colliders (v3 item 7), not a measurement of it; that bake has never been timed. A
            // single 40 x 40 floor taking longer than the whole-level budget means something is
            // badly wrong, which is all this asserts.
            Assert.Less(watch.ElapsedMilliseconds, 5000L,
                "Baking one 40 x 40 floor took " + watch.ElapsedMilliseconds + " ms against the "
                + "5000 ms budget for the whole level.");
        }

        [Test]
        public void Prefab_IsDiscoveredByTheBootstrapInTheNavigationPhaseAndDoesNotSpawnOnAwake()
        {
            var prefab = Resources.Load<GameObject>(GameBootstrap.SpawnerResourceFolder + "/NavigationSpawner");
            Assert.IsNotNull(prefab,
                "Resources/" + GameBootstrap.SpawnerResourceFolder + "/NavigationSpawner.prefab did "
                + "not load, so GameBootstrap will never run this lane.");
            Assert.IsNotNull(prefab.GetComponent<NavigationSpawner>(),
                "The prefab carries no NavigationSpawner; GameBootstrap warns and skips it.");

            // A floor, so that IF the prefab spawned on Awake the bake would succeed and be visible.
            AddDefaultFloor();
            var managers = new GameObject("GameManagersUnderTest");
            managers.transform.SetParent(root.transform, false);
            var bootstrap = managers.AddComponent<GameBootstrap>();

            // Instantiate runs each prefab's Awake synchronously, so the Awake check is made HERE,
            // before any frame passes and before the bootstrap's own Start could build the world.
            bootstrap.InstantiateSpawnerPrefabs();
            NavigationSpawner instance = managers.GetComponentInChildren<NavigationSpawner>(true);
            Assert.IsNotNull(instance, "GameBootstrap did not instantiate the NavigationSpawner prefab.");
            Assert.AreEqual("NavigationSpawner", instance.gameObject.name);
            Assert.AreEqual(-1, instance.SpawnedCount,
                "The spawner baked on Awake. GameBootstrap owns the order; a spawner that starts "
                + "itself runs before Rooms exist.");
            Assert.IsNull(instance.Surface);
            Assert.AreEqual(0, instance.transform.childCount, "The spawner created children on Awake.");

            List<ISpawner> ordered = bootstrap.CollectSpawnersInPhaseOrder();
            int propsIndex = -1;
            int navigationIndex = -1;
            for (int i = 0; i < ordered.Count; i++)
            {
                if (ordered[i].Phase == SpawnPhase.Props && propsIndex < 0) propsIndex = i;
                if (ReferenceEquals(ordered[i], instance)) navigationIndex = i;
            }

            Assert.GreaterOrEqual(propsIndex, 0, "No Props-phase spawner was instantiated; the order cannot be checked.");
            Assert.GreaterOrEqual(navigationIndex, 0, "The NavigationSpawner instance is not in the phase-ordered list.");
            Assert.Less(propsIndex, navigationIndex,
                "Navigation would run BEFORE Props, so the bake could not see the prop colliders.");
            Assert.AreEqual(SpawnPhase.Navigation, instance.Phase);

            // Never let this bootstrap reach Start(): it would build the whole prop world into the
            // test scene. Inactive objects do not Start, and TearDown destroys it.
            managers.SetActive(false);
        }

        [UnityTest]
        public IEnumerator AuthoredSpawnPointsSampleOntoAFlatFloorWithinTheAcceptanceTolerance()
        {
            // WHAT THIS PROVES, AND WHAT IT DOES NOT. On a flat floor whose top is at y = 0, the
            // baked surface sits one voxel height above the collider (0.0833 with cellSize 0.1667 -
            // the builder's own measurement on the real rooms: "Chapel of Ash reads a flat 0.083
            // across its whole room"). So this shows the 0.1 gate is compatible with the bake's own
            // height error at these ten coordinates, i.e. AC-006 is achievable by the bake at all;
            // it does NOT show the real rooms are walkable there, which is increment C's integration
            // test with the Rooms and Props lanes present. If this fails while the flat-floor tests
            // above pass, the voxel height is no longer under 0.1 and every spawn point is affected.
            var points = new List<Vector3>(PinnedEnemySpawnPoints) { RuinedEntryLayout.PlayerStart };
            Assert.AreEqual(10, points.Count, "Ten authored spawn points were expected.");

            // A floor covering every point with eight agent radii to spare on each side, so no point
            // is inside the erosion band of an edge and the fixture cannot be "too small" by accident.
            float radius = NavMesh.GetSettingsByIndex(0).agentRadius;
            float margin = 8f * radius;
            Vector3 min = points[0];
            Vector3 max = points[0];
            foreach (Vector3 point in points)
            {
                min = Vector3.Min(min, point);
                max = Vector3.Max(max, point);
            }

            Vector3 centre = (min + max) * 0.5f;
            AddFloor(new Vector3(centre.x, 0f, centre.z), max.x - min.x + 2f * margin, max.z - min.z + 2f * margin);

            int count = spawner.Spawn();
            yield return null;
            Assert.AreEqual(1, count);

            var failures = new List<string>();
            foreach (Vector3 point in points)
            {
                if (NavMesh.SamplePosition(point, out _, SampleTolerance, NavMesh.AllAreas)) continue;

                // Say how far the surface actually is, which is the number the next reader needs.
                string nearest = NavMesh.SamplePosition(point, out NavMeshHit wide, 2f, NavMesh.AllAreas)
                    ? (wide.position - point).magnitude.ToString("F3") + " away at " + wide.position
                    : "nowhere within 2 units";
                failures.Add(point + ": surface " + nearest);
            }

            Assert.IsEmpty(failures,
                "These authored spawn points do not sample within " + SampleTolerance + " on a flat "
                + "y = 0 floor, so AC-006 cannot be met by the bake itself, before any room geometry "
                + "is involved: " + string.Join("; ", failures));
        }

        [UnityTest]
        public IEnumerator Spawn_SkipsAColliderOnAnObjectCarryingANavMeshObstacle()
        {
            // The second rule NavMeshRebakeExclusion states: NavMeshSurface drops any source whose
            // GameObject carries a NavMeshObstacle (ignoreNavMeshObstacle defaults to true and the
            // spawner leaves it). A door's DoorEnemyPassability puts its obstacle on the door root,
            // so this is the rule that decides whether a root collider there needs the modifier.
            // The obstacle does not carve (carving defaults to false), so the floor under it stays.
            AddDefaultFloor();
            GameObject withObstacle = AddSolidBox("BoxWithObstacle", new Vector3(10f, 1f, 10f), 2f);
            withObstacle.AddComponent<NavMeshObstacle>();
            GameObject control = AddSolidBox("BoxWithoutObstacle", new Vector3(-10f, 1f, -10f), 2f);

            Assert.IsTrue(NavMeshRebakeExclusion.Excludes(withObstacle.GetComponent<Collider>()));
            Assert.IsFalse(NavMeshRebakeExclusion.Excludes(control.GetComponent<Collider>()));

            spawner.Spawn();
            yield return null;

            Assert.IsTrue(Samples(new Vector3(10f, 0f, 10f)),
                "A collider sharing its GameObject with a NavMeshObstacle was baked around. Either "
                + "the surface's ignoreNavMeshObstacle default changed or the spawner overrode it.");
            Assert.IsFalse(Samples(new Vector3(-10f, 0f, -10f)),
                "The CONTROL box without an obstacle did not carve, so the assertion above proves nothing.");
        }

        [UnityTest]
        public IEnumerator RebakeAudit_NamesTheSolidColliderALaterPhaseLeftWithoutTheExclusion()
        {
            // THE STRUCTURAL DETECTOR, self-tested with probe spawners, so the integrator can point
            // NavMeshRebakeExclusion.FindCollectedUnderLaterPhases at the real GameManagers after a
            // BuildWorld() and get the list of prefabs that still need the modifier. Every expected
            // membership below is decided by how this fixture built the object.
            var managers = new GameObject("GameManagersUnderTest");
            managers.transform.SetParent(root.transform, false);
            spawner.transform.SetParent(managers.transform, false);
            AddDefaultFloor();

            // Doors (3): a solid collider with no modifier. THE violation.
            GameObject doorsProbe = AddProbeSpawner(managers.transform, "DoorsProbe", SpawnPhase.Doors);
            GameObject door = AddSolidBox("Door", new Vector3(10f, 1f, 10f), 2f, doorsProbe.transform);

            // Player (4): the prefab shape - modifier on the root, collider on a child. Covered.
            GameObject playerProbe = AddProbeSpawner(managers.transform, "PlayerProbe", SpawnPhase.Player);
            var player = new GameObject("Player");
            player.transform.SetParent(playerProbe.transform, false);
            NavMeshRebakeExclusion.Apply(player);
            AddSolidBox("Body", new Vector3(-10f, 1f, -10f), 2f, player.transform);

            // Enemies (5): a trigger and a disabled collider. Neither is baked, neither is reported.
            GameObject enemiesProbe = AddProbeSpawner(managers.transform, "EnemiesProbe", SpawnPhase.Enemies);
            AddSolidBox("TriggerVolume", new Vector3(10f, 1f, -10f), 2f, enemiesProbe.transform)
                .GetComponent<BoxCollider>().isTrigger = true;
            AddSolidBox("DisabledCollider", new Vector3(-10f, 1f, 10f), 2f, enemiesProbe.transform)
                .GetComponent<BoxCollider>().enabled = false;

            // Props (1): an earlier phase. Baked around, correctly - props ARE walls to the navmesh -
            // and outside the rule, so not reported.
            GameObject propsProbe = AddProbeSpawner(managers.transform, "PropsProbe", SpawnPhase.Props);
            AddSolidBox("Crate", new Vector3(0f, 1f, -10f), 2f, propsProbe.transform);

            List<Collider> found = NavMeshRebakeExclusion.FindCollectedUnderLaterPhases(managers.transform);
            var names = new List<string>();
            foreach (Collider collider in found) names.Add(NavMeshRebakeExclusion.HierarchyPath(collider.transform));
            Assert.AreEqual(1, found.Count,
                "Expected exactly the unmarked door to be reported; got: " + string.Join(", ", names));
            Assert.AreSame(door.GetComponent<Collider>(), found[0]);

            // The spawner reports the same violator by path, then bakes anyway - a missing navmesh
            // would be worse than a wrong one - and the sample points show the consequence.
            LogAssert.Expect(LogType.Error, new Regex("DoorsProbe/Door"));
            int count = spawner.Spawn();
            yield return null;

            Assert.AreEqual(1, count);
            Assert.IsFalse(Samples(new Vector3(10f, 0f, 10f)),
                "The unmarked door was NOT baked around, so the error names a defect that did not happen.");
            Assert.IsTrue(Samples(new Vector3(-10f, 0f, -10f)), "The excluded player body was baked around.");
            Assert.IsTrue(Samples(new Vector3(10f, 0f, -10f)), "A trigger volume was baked around.");
            Assert.IsTrue(Samples(new Vector3(-10f, 0f, 10f)), "A disabled collider was baked around.");
            Assert.IsFalse(Samples(new Vector3(0f, 0f, -10f)),
                "The Props-phase crate was not baked around; props are supposed to be walls to the navmesh.");
        }

        private static GameObject AddProbeSpawner(Transform parent, string name, SpawnPhase phase)
        {
            var probe = new GameObject(name);
            probe.transform.SetParent(parent, false);
            probe.AddComponent<PhaseProbe>().Configure(phase);
            return probe;
        }

        /// <summary>A spawner that only declares a phase, so the audit is tested against the phase
        /// rule and nothing else - the same probe GameBootstrapPlayModeTests uses.</summary>
        private sealed class PhaseProbe : MonoBehaviour, ISpawner
        {
            private SpawnPhase phase;

            public void Configure(SpawnPhase value) => phase = value;

            public SpawnPhase Phase => phase;

            public int Spawn() => 0;
        }
    }
}
