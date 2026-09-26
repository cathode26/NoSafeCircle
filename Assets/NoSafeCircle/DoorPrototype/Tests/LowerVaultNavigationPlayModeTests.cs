using System.Collections;
using System.Linq;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
#if UNITY_EDITOR
    // NSC-032 defect repair (test repair, not a design change): proves the gameplay NavMesh does
    // NOT treat LV-H1 as climbable, on the COMMITTED Assets/Scenes/Rooms/LowerVault.unity
    // GameplayGeometry - following the committed precedent in BoneArchiveNavigationPlayModeTests.
    //
    // THE DEFECT THIS GUARDS. LowerVaultSceneBuilder builds LV-H1 (three obstacles:
    // LV-H1-WestCollision, LV-H1-CenterCollision, LV-H1-EastCollision, from
    // LowerVaultLayout.HallWestSpan/HallCenterSpan/HallEastSpan) as a "non-damaging walking
    // boundary" whose whole point is to stop a walking agent rather than merely stand in its line
    // of sight. LowerVaultLayout.HallSpanHeight is 0.5. Before this repair,
    // ProjectSettings/NavMeshAreas.asset's agent-type-0 agentClimb was 0.75, ABOVE that height, so
    // the baked NavMesh treated the 0.5-unit ledge as a climbable step rather than a barrier - the
    // gameplay NavMesh silently disagreed with the level design. agentClimb is now 0.4, below the
    // ledge height, and nothing before this file asserted the relationship between the two, so
    // raising agentClimb again would silently reintroduce the defect while every other test still
    // passed.
    //
    // WHY THIS CANNOT BE A SETTING READBACK. A test that re-reads agentClimb from
    // ProjectSettings/NavMeshAreas.asset and compares it to HallSpanHeight would pass on a stub
    // value and prove nothing about what the BAKED NavMesh actually does. Both assertions below
    // instead run NavMeshAgent.CalculatePath across the baked surface and read the resulting
    // NavMeshPath - the same API EnemyPursuitMovement itself would use - so a widened agentClimb
    // is caught by its effect on navigation, not by its own value.
    //
    // HOW THIS FIXTURE ISOLATES THE ROOM (Docs/Engineering/UNITY_TESTING_POLICY.md requires this
    // be stated). GameplayNavigationSurface.ConfigureAndBuild sets collectObjects = CollectObjects
    // .All, so it collects EVERY active collider in the running Play Mode session, not just this
    // room's. LoadSceneMode.Single unloads every other scene before the bake, so the only
    // scene-resident colliders that can exist are this room's, and
    // AssertNoColliderOutsideGameplayGeometry PROVES that rather than assuming it - it fails,
    // naming the offender, if any collider anywhere is not a descendant of this room's
    // GameplayGeometry. This fixture's own objects (the navigation surface host and the test
    // NavMeshAgent) carry no Collider of their own.
    //
    // NOTE ON THE FIXTURE'S OWN SCOPE: nothing here writes, saves or re-serializes the committed
    // scene, and no production code changes with this repair. It is loaded in Play Mode, read, and
    // unloaded without saving.
    public sealed class LowerVaultNavigationPlayModeTests
    {
        // ---- Identity of the committed room -------------------------------------------------
        // Assets/Scenes/Rooms/LowerVault.unity is NOT in ProjectSettings/EditorBuildSettings.asset,
        // so SceneManager.LoadScene by name cannot reach it.
        // UnityEditor.SceneManagement.EditorSceneManager.LoadSceneInPlayMode loads a committed
        // scene BY PATH in Play Mode - the committed precedent used by
        // BoneArchiveNavigationPlayModeTests and DoorCrossingCommittedSceneConformanceTests. That
        // is why this whole fixture sits under UNITY_EDITOR: the Tests assembly has
        // includePlatforms [] and no UnityEditor assembly reference, so the editor API must be
        // both guarded and fully qualified.
        private const string CommittedScenePath = "Assets/Scenes/Rooms/LowerVault.unity";
        private const string CommittedSceneName = "LowerVault";
        private const string RoomRootName = "Room_LowerVault";
        private const string GameplayGeometryName = "GameplayGeometry";
        private const string CleanupSceneName = "LowerVaultNavigationCleanup";
        private const string LedgeColliderName = "LV-H1-CenterCollision";

        // ---- Measurement constants ------------------------------------------------------------

        // Smaller than LowerVaultLayout.HallSpanHeight (0.5), so a SamplePosition query cannot
        // silently bridge between the floor (Y 0) and the top of the ledge (Y 0.5) and read as
        // "found" for the wrong surface. Both query points below sit essentially ON the surface
        // they name, so this only needs to absorb voxel/cell noise, not span a real gap.
        private const float SampleRadius = 0.3f;

        // How far south of LV-H1-CenterCollision's footprint the floor approach point sits, so it
        // samples onto open floor rather than onto (or inside) the obstacle's own collider.
        private const float FloorApproachMargin = 1f;

        // Slack below LowerVaultLayout.HallSpanHeight for the corner-height check. A path corner
        // reaching within this margin of the ledge top would mean the agent is standing on or
        // climbing the ledge, not merely approaching its base.
        private const float LedgeClimbMargin = 0.15f;

        private Scene roomScene;
        private Transform gameplayGeometry;
        private GameObject fixtureRoot;
        private GameplayNavigationSurface surfaceOwner;
        private NavMeshAgent agent;

        // ---- Derived, not duplicated: every point below comes from LowerVaultLayout.HallCenterSpan
        // rather than a literal, so a later layout revision moves these expectations with it.
        private static Bounds LedgeBounds => LowerVaultLayout.HallCenterSpan;

        private static Vector3 FloorApproachPoint => new Vector3(
            LedgeBounds.center.x, 0f, LedgeBounds.min.z - FloorApproachMargin);

        private static Vector3 LedgeTopPoint => new Vector3(
            LedgeBounds.center.x, LowerVaultLayout.HallSpanHeight, LedgeBounds.center.z);

        // =====================================================================================
        // Fixture
        // =====================================================================================

        [UnitySetUp]
        public IEnumerator LoadCommittedRoomAndBakeItsNavigation()
        {
            UnityEditor.SceneManagement.EditorSceneManager.LoadSceneInPlayMode(
                CommittedScenePath,
                new LoadSceneParameters(LoadSceneMode.Single));

            // One frame so the loaded scene's Awake calls run before anything is measured.
            yield return null;

            // Physics.autoSyncTransforms is off by default, and the bake reads Collider.bounds.
            // Syncing once here means those bounds describe where the committed colliders
            // actually are rather than a stale pre-load state.
            Physics.SyncTransforms();

            roomScene = SceneManager.GetSceneByName(CommittedSceneName);
            Assert.IsTrue(roomScene.IsValid() && roomScene.isLoaded,
                "Expected " + CommittedScenePath + " to load in Play Mode.");

            GameObject roomRoot = roomScene.GetRootGameObjects()
                .FirstOrDefault(rootObject => rootObject.name == RoomRootName);
            Assert.IsNotNull(roomRoot,
                "Expected one identity-transform " + RoomRootName + " root in " + CommittedScenePath + ".");

            gameplayGeometry = roomRoot.transform.Find(GameplayGeometryName);
            Assert.IsNotNull(gameplayGeometry,
                "Expected a separately marked " + GameplayGeometryName + " child under " +
                RoomRootName + "; the bake reads its colliders.");

            Assert.IsNotNull(gameplayGeometry.Find(LedgeColliderName),
                "Expected " + LedgeColliderName + " under " + GameplayGeometryName +
                " - LowerVaultSceneBuilder.BuildGameplayGeometry names it exactly this, from " +
                "LowerVaultLayout.HallCenterSpan. If this is missing, the fixture is reading the " +
                "wrong ledge.");

            AssertNoColliderOutsideGameplayGeometry("before the fixture created anything");

            fixtureRoot = new GameObject("LowerVaultNavigationFixture");

            // THE SCENE CARRIES NO BAKED NAVMESH AND THIS GATE MUST BUILD ONE - Room scenes keep
            // navigation configuration out of the room scene itself, so loading the room alone
            // would leave nothing to sample. GameplayNavigationSurface bakes it here, exactly as
            // BoneArchiveNavigationPlayModeTests does, over the COMMITTED colliders rather than
            // colliders this fixture creates.
            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(fixtureRoot.transform, false);
            surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surfaceOwner.ConfigureAndBuild();

            // A NavMeshAgent added off the NavMesh logs an error, which the Unity Test Framework
            // would report as a failure of whichever test ran first rather than as the setup
            // problem it is - the same reason BoneArchiveNavigationPlayModeTests places its
            // stand-in on the surface before adding the component. FloorApproachPoint sits well
            // clear of every obstacle in LowerVaultLayout, so it is used as the spawn point here.
            NavMeshBuildSettings settings = NavMesh.GetSettingsByIndex(0);
            Assert.IsTrue(
                NavMesh.SamplePosition(FloorApproachPoint, out NavMeshHit spawnHit, SampleRadius, NavMesh.AllAreas),
                "Expected the floor approach " + Describe(FloorApproachPoint) + " to sample onto the " +
                "surface baked from the committed " + GameplayGeometryName + ". If this fails, the bake " +
                "produced nothing and every assertion below would fail for the wrong reason.");

            var agentObject = new GameObject("LowerVaultNavigationAgent");
            agentObject.transform.SetParent(fixtureRoot.transform, false);
            agentObject.transform.position = spawnHit.position;

            agent = agentObject.AddComponent<NavMeshAgent>();
            agent.agentTypeID = settings.agentTypeID;
            agent.radius = settings.agentRadius;
            agent.height = settings.agentHeight;
            agent.Warp(spawnHit.position);

            Debug.Log(
                "NSC-032 VAL: baked GameplayNavigationSurface over the committed " + CommittedScenePath +
                " " + GameplayGeometryName + ". Agent configuration in use: agentTypeID=" +
                agent.agentTypeID + ", agentRadius=" + settings.agentRadius.ToString("F3") +
                ", agentHeight=" + settings.agentHeight.ToString("F3") + ", agentClimb=" +
                settings.agentClimb.ToString("F3") + ". LowerVaultLayout.HallSpanHeight=" +
                LowerVaultLayout.HallSpanHeight.ToString("F3") + ".");
        }

        // Names this order: ClearBakedData, destroy the fixture objects, then unload the scene
        // WITHOUT SAVING - the committed pattern from BoneArchiveNavigationPlayModeTests. A
        // cleanup scene is made active first because Unity refuses to unload the last loaded
        // scene. Skipping the unload would leave this room loaded for every fixture afterwards.
        [UnityTearDown]
        public IEnumerator ClearBakeDestroyFixtureAndUnloadSceneWithoutSaving()
        {
            if (surfaceOwner != null)
            {
                surfaceOwner.ClearBakedData();
            }

            if (fixtureRoot != null)
            {
                Object.Destroy(fixtureRoot);
            }

            // One frame so the deferred destruction completes before the scene goes away.
            yield return null;

            Scene loaded = SceneManager.GetSceneByName(CommittedSceneName);
            if (!loaded.IsValid() || !loaded.isLoaded)
            {
                yield break;
            }

            Scene cleanupScene = SceneManager.CreateScene(CleanupSceneName);
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(loaded);
        }

        // =====================================================================================
        // The guard
        // =====================================================================================

        // THE DEFECT: raise ProjectSettings/NavMeshAreas.asset's agent-type-0 agentClimb back to
        // (or above) LowerVaultLayout.HallSpanHeight and this must fail. At agentClimb 0.4 the
        // ledge is taller than the agent can step, so CalculatePath from the floor immediately
        // south of LV-H1-CenterCollision to a point on its top must NOT complete, and no corner of
        // whatever partial path is returned may reach the ledge's height.
        [UnityTest]
        public IEnumerator LedgeTop_IsUnreachableFromAdjacentFloor_WhenAgentClimbIsBelowLedgeHeight()
        {
            yield return null;

            Vector3 ledgeTopPoint = SampleOrFail(LedgeTopPoint,
                "the top of " + LedgeColliderName + " - if this fails, the ledge's flat top is not " +
                "baked as navmesh AT ALL regardless of agentClimb, which is a different, stronger " +
                "guarantee against climbing than this test was written to check.");

            var path = new NavMeshPath();
            agent.CalculatePath(ledgeTopPoint, path);

            float agentClimb = NavMesh.GetSettingsByIndex(0).agentClimb;

            Assert.AreNotEqual(NavMeshPathStatus.PathComplete, path.status,
                "NSC-032: " + LedgeColliderName + " is a " +
                LowerVaultLayout.HallSpanHeight.ToString("F2") +
                "-unit walking boundary (LowerVaultLayout.HallSpanHeight), and " +
                "ProjectSettings/NavMeshAreas.asset's agent-type-0 agentClimb (" +
                agentClimb.ToString("F2") + ") must stay below it so the baked gameplay NavMesh " +
                "cannot carry an agent up onto it. CalculatePath from the floor approach " +
                Describe(FloorApproachPoint) + " to the ledge top " + Describe(ledgeTopPoint) +
                " returned " + path.status + " instead of a blocked/partial route - agentClimb is " +
                "at or above the ledge height and the ledge has become climbable.");

            float maxCornerY = path.corners.Length == 0 ? 0f : path.corners.Max(corner => corner.y);
            Assert.Less(maxCornerY, LowerVaultLayout.HallSpanHeight - LedgeClimbMargin,
                "NSC-032: even the PARTIAL route CalculatePath returned toward the top of " +
                LedgeColliderName + " must not climb onto the ledge. Its highest corner reached Y " +
                maxCornerY.ToString("F3") + ", which is within " + LedgeClimbMargin.ToString("F2") +
                " of the " + LowerVaultLayout.HallSpanHeight.ToString("F2") +
                "-unit ledge top - agentClimb (" + agentClimb.ToString("F2") +
                ") is carrying the agent up the ledge face.");
        }

        // =====================================================================================
        // Helpers
        // =====================================================================================

        private Vector3 SampleOrFail(Vector3 requested, string which)
        {
            Assert.IsTrue(
                NavMesh.SamplePosition(requested, out NavMeshHit hit, SampleRadius, NavMesh.AllAreas),
                "Expected " + Describe(requested) + " to sample onto the surface baked from the " +
                "committed " + GameplayGeometryName + " (" + which + ").");
            return hit.position;
        }

        private void AssertNoColliderOutsideGameplayGeometry(string when)
        {
            Collider[] everyCollider = Object.FindObjectsByType<Collider>(FindObjectsSortMode.None);
            var strangers = everyCollider
                .Where(collider => !(collider.gameObject.scene == roomScene
                    && collider.transform.IsChildOf(gameplayGeometry)))
                .Select(collider => collider.name + " (scene '" + collider.gameObject.scene.name + "')")
                .ToArray();

            CollectionAssert.IsEmpty(strangers,
                "GameplayNavigationSurface.ConfigureAndBuild collects EVERY active collider in the " +
                "session, so the bake is only about this room while this room's " +
                GameplayGeometryName + " owns every collider that exists. Found colliders " + when +
                " that are not under " + RoomRootName + "/" + GameplayGeometryName + ": " +
                string.Join(", ", strangers) + ".");
        }

        private static string Describe(Vector3 point)
        {
            return "(X " + point.x.ToString("F2") + ", Y " + point.y.ToString("F2") + ", Z " +
                point.z.ToString("F2") + ")";
        }
    }
#endif
}
