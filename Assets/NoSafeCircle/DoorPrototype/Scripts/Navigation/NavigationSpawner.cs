using NoSafeCircle.DoorPrototype.World;
using Unity.AI.Navigation;
using UnityEngine;
using UnityEngine.AI;
using Stopwatch = System.Diagnostics.Stopwatch;

namespace NoSafeCircle.DoorPrototype.Navigation
{
    // Bakes the gameplay NavMesh AT RUNTIME, in phase 2, around every solid collider the Rooms and
    // Props phases just created. This is the first production caller GameplayNavigationSurface has
    // ever had.
    //
    // WHY IT CALLS ConfigureAndBuild() INSTEAD OF OWNING A NavMeshSurface OF ITS OWN. That method
    // (Scripts/World/GameplayNavigationSurface.cs) already sets the three fields a correct bake
    // needs - agentTypeID from NavMesh.GetSettingsByIndex(0), collectObjects = All, and
    // useGeometry = PhysicsColliders - and NavMeshAgentConfigurationTests already pins all three.
    // It had ZERO runtime callers: its one non-test caller was Editor/DoorPrototypeSceneBuilder.cs,
    // which baked into the committed scenes, so the built game never baked at all. A second surface
    // owner here would be a second place for those settings to drift. So this class creates the
    // object, calls the method, and verifies the result; it configures nothing itself.
    //
    // useGeometry = PhysicsColliders IS THE LOAD-BEARING LINE, and it is why this lane must not
    // "improve" the surface. The world is drawn with SpriteRenderers; a bake configured for
    // RenderMeshes cannot see one (no MeshFilter) and cannot see the floor collider either (it has
    // no renderer at all), so it produces an empty or wrong surface. The walkable floor is the
    // Rooms lane's FloorCollision box; the holes are the props' colliders. Both are physics.
    //
    // WHY THE EDITOR'S SuppressDoorBlockingColliders STEP DOES NOT EXIST HERE. The editor disabled
    // every door's solid collider for the duration of its bake because DoorSequenceBuilder composed
    // the doors BEFORE the bake, and a sealed door standing in the opening wrote a permanent hole
    // across the doorway (DoorPrototypeSceneBuilder.cs:461-490, its own comment). SpawnPhase orders
    // Navigation(2) before Doors(3) and GameBootstrap.CollectSpawnersInPhaseOrder sorts on it, so
    // when this runs no door exists yet. The doorway is carved at runtime by DoorEnemyPassability's
    // NavMeshObstacle, the design DoorEnemyPassabilityPlayModeTests proves - that fixture also
    // builds its door after its bake. Read from source, not taken on trust.
    //
    // WHAT A RE-BAKE SEES, AND THE RULE EVERY LATER LANE MUST CARRY. A second BuildWorld runs this
    // phase before Doors, Player, Enemies and Hud have cleared their previous output, so their
    // objects are still alive and active during the re-bake, and any solid collider among them is
    // baked around as if it were a wall. The Unity-native exclusion is a NavMeshModifier with
    // ignoreFromBuild = true (applyToChildren = true on a prefab root) on every prefab those phases
    // spawn. NavMeshRebakeExclusion states that rule in code; this spawner reports each violator by
    // name before it bakes. It never disables or moves another lane's object - that would be the
    // editor's suppression step in a runtime costume, and the fix belongs in the lane's prefab.
    [DisallowMultipleComponent]
    public sealed class NavigationSpawner : MonoBehaviour, ISpawner
    {
        /// <summary>The child that carries the surface: named so a hierarchy reader finds it and a
        /// fixture can count exactly one.</summary>
        public const string SurfaceObjectName = "GameplayNavigation";

        [Tooltip("Log the collider count, the bake time and the baked bounds after each build. One "
            + "line per build, and the only place the bake is observable at runtime.")]
        [SerializeField] private bool logBuildTime = true;

        /// <summary>After Rooms and Props, whose colliders this bakes around; before Doors, Player
        /// and Enemies, which need a surface to stand on.</summary>
        public SpawnPhase Phase => SpawnPhase.Navigation;

        /// <summary>The surface owner the last Spawn() created, or null before one has run or when
        /// the last one failed its guard.</summary>
        public GameplayNavigationSurface Surface { get; private set; }

        /// <summary>What the last Spawn() returned, or -1 before it has run - deliberately
        /// distinguishable from a Spawn() that baked nothing.</summary>
        public int SpawnedCount { get; private set; } = -1;

        /// <summary>
        /// Bakes the NavMesh. Safe to call again: the previous surface is unregistered and destroyed
        /// before the new one is built, so a second call REPLACES the NavMesh rather than adding a
        /// second copy of it to the navigation system.
        /// </summary>
        /// <remarks>
        /// WHAT THE COUNT MEANS. A bake is not an object, so this cannot be "objects placed". It is
        /// the number of NavMesh surfaces this spawner has registered with the navigation system: 1
        /// when a surface baked over at least one solid collider is registered, 0 when nothing is -
        /// and every 0 comes with a LogError naming the reason. Whether the surface is walkable at a
        /// given point is what NavMesh.SamplePosition answers, and the fixture asks it; the count
        /// does not claim it.
        /// </remarks>
        public int Spawn()
        {
            ClearPreviousOutput();

            // The bake reads physics colliders, so with none there is nothing to bake on. One
            // scene-wide query per build, not a hot path. On a same-frame rebuild this also counts
            // an earlier phase's Destroy-pending corpses; that only inflates the log line.
            int solid = CountSolidColliders();
            if (solid == 0)
            {
                Debug.LogError($"{nameof(NavigationSpawner)}: no enabled non-trigger collider exists, "
                    + "so there is nothing to bake on. Rooms must run before Navigation.");
                SpawnedCount = 0;
                return 0;
            }

            ReportCollidersALaterPhaseLeftAlive();

            var root = new GameObject(SurfaceObjectName);
            root.transform.SetParent(transform, false);
            root.AddComponent<NavMeshSurface>();
            Surface = root.AddComponent<GameplayNavigationSurface>();

            var watch = Stopwatch.StartNew();
            Surface.ConfigureAndBuild();
            watch.Stop();

            NavMeshData data = Surface.Surface.navMeshData;
            if (data == null)
            {
                // The object is left in the hierarchy on purpose, so the failure can be inspected.
                Debug.LogError($"{nameof(NavigationSpawner)}: BuildNavMesh produced no data over "
                    + $"{solid} collider(s). Nothing is registered with the navigation system.");
                SpawnedCount = 0;
                return 0;
            }

            if (logBuildTime)
            {
                Debug.Log($"{nameof(NavigationSpawner)}: baked over {solid} collider(s) in "
                    + $"{watch.ElapsedMilliseconds} ms, bounds {data.sourceBounds}.");
            }

            SpawnedCount = 1;
            return 1;
        }

        private void ClearPreviousOutput()
        {
            if (Surface != null)
            {
                Surface.ClearBakedData();
                Surface = null;
            }

            // Deactivate THEN destroy. Destroy is deferred to the end of the frame, while the bake
            // below runs in this same call and collects only active objects, so an inactive corpse
            // contributes nothing and cannot be found by type in the meantime.
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                GameObject child = transform.GetChild(i).gameObject;
                child.SetActive(false);
                Destroy(child);
            }
        }

        private static int CountSolidColliders()
        {
            int solid = 0;
            foreach (Collider collider in FindObjectsByType<Collider>(FindObjectsSortMode.None))
            {
                if (collider.enabled && !collider.isTrigger)
                {
                    solid++;
                }
            }

            return solid;
        }

        // Names every solid collider a later phase left alive without the ignoreFromBuild exclusion.
        // Each one is about to be baked around, which is a real defect in the surface, so it is an
        // error rather than a warning - and it makes GameBootstrap's own "build twice" fixture fail
        // for any lane that forgets the modifier, naming the object. Read-only: nothing is changed.
        private void ReportCollidersALaterPhaseLeftAlive()
        {
            Transform bootstrap = transform.parent != null ? transform.parent : transform;
            foreach (Collider collider in NavMeshRebakeExclusion.FindCollectedUnderLaterPhases(bootstrap))
            {
                Debug.LogError($"{nameof(NavigationSpawner)}: this bake will collect '"
                    + NavMeshRebakeExclusion.HierarchyPath(collider.transform) + "', a solid collider "
                    + "spawned by a phase after Navigation with no NavMeshModifier.ignoreFromBuild "
                    + "covering it. It is being baked around as if it were a wall. Put the modifier "
                    + "on that prefab's root with applyToChildren = true.", collider);
            }
        }
    }
}
