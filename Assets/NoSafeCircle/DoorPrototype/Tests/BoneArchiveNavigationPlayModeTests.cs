using System.Collections;
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Enemies;
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
    // NSC-071 AC-001/VAL-001: proves the configured enemy can traverse every lane NSC-045 INT-002
    // assigns to this task, on the COMMITTED Assets/Scenes/Rooms/BoneArchive.unity GameplayGeometry
    // rather than on a builder-produced in-memory scene or a synthetic corridor.
    //
    // WHY A COMPLETE PATH IS NOT ENOUGH, AND WHY EVERY ASSERTION BELOW CHECKS CORNERS.
    // NSC-045 AC-002 requires the A-to-B and B-to-C lanes to INDEPENDENTLY connect the entry area
    // to the north cross-aisle, and adds a western and an eastern bypass. Parallel routes are a
    // design requirement here, so if the bake severs BA-1's 2.5-unit pinch the two endpoints on
    // either side of it stay connected around Shelf C and CalculatePath still returns
    // PathComplete. An earlier revision of VAL-001 asserted exactly that and therefore could not
    // detect the severance it existed to detect. Every lane test below therefore asserts that
    // EVERY corner of the returned NavMeshPath stays inside that lane's own X/Z envelope, so a
    // route that escapes into a neighbouring aisle fails even though it "arrives".
    //
    // WHY THIS CANNOT BE A WIDTH COMPARISON. ProjectSettings/NavMeshAreas.asset configures
    // agentRadius 0.5, so the 1.0-diameter agent clears every lane on arithmetic alone and clears
    // the 2.5 pinch by 0.75 on each side. Every width comparison available here passes before the
    // NavMesh is consulted, and NSC-045's own Edit Mode gates already make them. What can actually
    // fail is the BAKE - erosion by the agent radius plus voxel rounding can sever a gap the raw
    // geometry clears - and proving the bake is the only thing this Play Mode gate can do that
    // Edit Mode cannot.
    //
    // WHERE THE NUMBERS COME FROM. Every envelope and endpoint is DERIVED from BoneArchiveLayout
    // and from the committed colliders in the loaded scene; nothing is a duplicated literal.
    // NSC-071 AC-001 is explicit that NSC-045's figures are CITED, NOT ADOPTED - if a later
    // NSC-045 revision moves a shelf, these expectations must move with it, which they do because
    // they are relations rather than constants.
    //
    // NOTE ON THE FIXTURE'S OWN SCOPE: nothing here writes, saves or re-serializes the committed
    // scene. It is loaded in Play Mode, read, and unloaded without saving.
    public sealed class BoneArchiveNavigationPlayModeTests
    {
        // ---- Identity of the committed room -------------------------------------------------
        // Assets/Scenes/Rooms/BoneArchive.unity is NOT in ProjectSettings/EditorBuildSettings.asset
        // (only Assets/Scenes/DoorPrototype.unity is), so SceneManager.LoadScene by name cannot
        // reach it. EditorSceneManager.LoadSceneInPlayMode loads a committed scene BY PATH in Play
        // Mode and is the committed precedent for exactly this - see
        // DoorCrossingCommittedSceneConformanceTests in DoorInteractionPlayModeTests.cs. That is
        // why this whole fixture sits under UNITY_EDITOR: the Tests assembly has includePlatforms
        // [] and no UnityEditor assembly reference, so the editor API must be both guarded and
        // fully qualified.
        private const string CommittedScenePath = "Assets/Scenes/Rooms/BoneArchive.unity";
        private const string CommittedSceneName = "BoneArchive";
        private const string RoomRootName = "Room_BoneArchive";
        private const string GameplayGeometryName = "GameplayGeometry";
        private const string CleanupSceneName = "BoneArchiveNavigationCleanup";

        // ---- Measurement constants ------------------------------------------------------------

        // TIGHT, AND CHECKED. The committed door tests sample with a 2-unit radius, which in this
        // room would silently relocate a rejected point onto a NEIGHBOURING route - after which
        // every later assertion passes about the wrong place. 0.75 is smaller than the >= 1.0
        // clearance every endpoint below keeps from the nearest obstacle face, so a point that
        // needs relocating cannot reach another lane; and SampleInsideLane asserts the result is
        // still inside its intended lane regardless. 0.75 is also enough to pull the D1/D2
        // approach points (which sit ON the inner wall line) onto the agent-radius-eroded surface.
        private const float SampleRadius = 0.75f;

        // Slack for float/voxel noise on the corner containment check. The narrowest lane envelope
        // here is 2.5 units wide (half-width 1.25), and escaping into a neighbouring aisle means
        // crossing at least a 1.5-unit-deep shelf, so 0.25 cannot mask an escape.
        private const float EnvelopeTolerance = 0.25f;

        // How far past a lane's longitudinal run its endpoints sit, so the path must span the
        // WHOLE lane rather than stopping inside it. Larger than the 0.5 agent radius, so the
        // endpoint lands on open cross-aisle surface rather than on the eroded lane mouth.
        private const float LaneEndMargin = 1f;

        // NSC-045 AC-005 puts the floor BoxCollider's top face at Y 0 and stands every obstacle,
        // wall and bay on top of it. So "bounds.max.y above zero" separates obstacles from the
        // floor without depending on a GameObject name.
        private const float FloorTopEpsilon = 0.01f;
        private const float GeometryEpsilon = 0.001f;

        // A sweep that reports zero is only as good as its haystack. Measured on main at
        // 106b73f75cbe9708d9c291a2ad1ea65cecc16600: the committed scene carries 11 BoxColliders
        // under GameplayGeometry. NSC-045 AC-005 requires exactly 13 once its W-1 and E-1 archive
        // bays land. A count BELOW 11 means this query broke, not that the room got simpler.
        private const int MinimumExpectedGameplayColliders = 11;

        // The agent radius these endpoint placements and envelope margins were derived against,
        // read from ProjectSettings/NavMeshAreas.asset. VAL-001 requires a later WIDENING of the
        // agent to show up here as a FAILURE rather than as a silent change of what was proven,
        // so this is asserted, not merely logged: widen the agent and re-derive the margins.
        private const float RecordedAgentRadius = 0.5f;

        private Scene roomScene;
        private Transform gameplayGeometry;
        private Collider[] gameplayColliders;
        private Collider[] obstacles;
        private GameObject fixtureRoot;
        private GameplayNavigationSurface surfaceOwner;
        private NavMeshAgent agent;
        private EnemyPursuitMovement pursuitMovement;
        private float agentRadius;
        private float westBypassWestBoundX;
        private float eastBypassEastBoundX;

        // =====================================================================================
        // Fixture
        // =====================================================================================

        [UnitySetUp]
        public IEnumerator LoadCommittedRoomAndBakeItsNavigation()
        {
            // HOW THIS FIXTURE ISOLATES THE ROOM (VAL-001 requires this to be stated).
            // GameplayNavigationSurface.ConfigureAndBuild sets collectObjects = CollectObjects.All,
            // so it collects EVERY active collider in the running Play Mode session, not just this
            // room's. Two things keep that honest:
            //   1. LoadSceneMode.Single, which unloads every other scene before the bake, so the
            //      only scene-resident colliders that can exist are this room's; and
            //   2. AssertRoomIsIsolatedFromOtherGeometry below, which PROVES it rather than
            //      assuming it - it fails, naming the offender, if any collider anywhere is not a
            //      descendant of this room's GameplayGeometry.
            // The fixture's own objects (the navigation surface host, the stand-in wizard and the
            // enemy) carry no Collider at all, which BakeReadsOnlyTheCommittedGameplayGeometry
            // re-checks AFTER they exist.
            UnityEditor.SceneManagement.EditorSceneManager.LoadSceneInPlayMode(
                CommittedScenePath,
                new LoadSceneParameters(LoadSceneMode.Single));

            // One frame so the loaded scene's Awake calls run before anything is measured.
            yield return null;

            // Physics.autoSyncTransforms is off by default, and every envelope below is derived
            // from Collider.bounds. Syncing once here means those bounds describe where the
            // committed colliders actually are rather than a stale pre-load state - a failure
            // caused by a stale bound would read as a severed lane, which is the wrong reason.
            Physics.SyncTransforms();

            roomScene = SceneManager.GetSceneByName(CommittedSceneName);
            Assert.IsTrue(roomScene.IsValid() && roomScene.isLoaded,
                "Expected " + CommittedScenePath + " to load in Play Mode. NSC-045 AC-001 " +
                "materializes the Bone Archive layout into that committed scene asset, and " +
                "NSC-045 INT-002 forbids standing in a builder-produced or synthetic scene.");

            GameObject roomRoot = roomScene.GetRootGameObjects()
                .FirstOrDefault(rootObject => rootObject.name == RoomRootName);
            Assert.IsNotNull(roomRoot,
                "NSC-045 AC-006 requires one identity-transform " + RoomRootName + " root in " +
                CommittedScenePath + ".");

            gameplayGeometry = roomRoot.transform.Find(GameplayGeometryName);
            Assert.IsNotNull(gameplayGeometry,
                "NSC-045 AC-006 requires a separately marked " + GameplayGeometryName +
                " child under " + RoomRootName + "; the bake reads its colliders.");

            AssertRoomIsIsolatedFromOtherGeometry("before the fixture created anything");
            CollectCommittedColliders();
            DeriveBypassBoundsFromCommittedGeometry();

            fixtureRoot = new GameObject("BoneArchiveNavigationFixture");

            // THE SCENE CARRIES NO BAKED NAVMESH AND THIS GATE MUST BUILD ONE. BoneArchive.unity
            // holds NavMeshSettings with no NavMesh data, and NSC-045 AC-006 keeps navigation
            // configuration out of the room scene, so loading the room alone would leave nothing
            // to sample and every assertion below would fail for the wrong reason. NSC-089's
            // GameplayNavigationSurface bakes it here, exactly as the two committed door tests do
            // - but over the COMMITTED colliders rather than over colliders this fixture creates,
            // which is the distinction NSC-045 INT-002 draws.
            var navigationRoot = new GameObject("GameplayNavigation");
            navigationRoot.transform.SetParent(fixtureRoot.transform, false);
            surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surfaceOwner.ConfigureAndBuild();

            BuildConfiguredEnemy();

            // VAL-001: record the agent radius the run actually used, in the test output.
            Debug.Log(
                "NSC-071 VAL-001: baked GameplayNavigationSurface over " + gameplayColliders.Length +
                " committed " + GameplayGeometryName + " colliders in " + CommittedScenePath +
                ". Agent configuration in use: agentTypeID=" + agent.agentTypeID +
                ", agentRadius=" + agentRadius.ToString("F3") +
                ", agentHeight=" + agent.height.ToString("F3") +
                ". Derived bypass bounds: west X " + westBypassWestBoundX.ToString("F3") +
                " to " + BoneArchiveLayout.ShelfA.min.x.ToString("F3") +
                ", east X " + BoneArchiveLayout.ShelfC.max.x.ToString("F3") +
                " to " + eastBypassEastBoundX.ToString("F3") + ".");
        }

        // VAL-001 names this order: ClearBakedData, destroy the fixture objects, then unload the
        // scene WITHOUT SAVING. A cleanup scene is made active first because Unity refuses to
        // unload the last loaded scene - the committed pattern from
        // DoorwayTraversalPlayModeTests/DoorCrossingCommittedSceneConformanceTests. Skipping the
        // unload would leave this room loaded for every fixture that runs afterwards, which is the
        // exact defect PlayModeSceneCleanupConventionTests was written to stop.
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
        // NSC-045 INT-002's six lanes
        // =====================================================================================

        // Lane 1 of 6. The A-to-B lane, NSC-045 AC-002's 3.5-unit clearance between Shelf A and
        // Shelf B, which must INDEPENDENTLY connect the entry area to the north cross-aisle.
        [UnityTest]
        public IEnumerator AToBLane_TraversesItsOwnEnvelopeFromSouthAisleToNorthAisle()
        {
            yield return null;
            AssertLaneIsTraversed(BuildAToBLane());
        }

        // Lane 2 of 6. The B-to-C lane INCLUDING BA-1's deliberate 2.5-unit pinch. This is the
        // lane the whole corner assertion exists for: sever the pinch and the endpoints below stay
        // connected around Shelf C, so PathComplete alone would still pass.
        [UnityTest]
        public IEnumerator BToCLane_TraversesBa1PinchWithinItsOwnEnvelope()
        {
            yield return null;
            AssertLaneIsTraversed(BuildBToCLane());
        }

        // Lane 3 of 6. The western bypass including its W-1 narrowing (NSC-045 AC-002: narrows to
        // 3.0 units between W-1 and Shelf A over Z 7 to 15).
        [UnityTest]
        public IEnumerator WesternBypass_TraversesW1NarrowingWithinItsOwnEnvelope()
        {
            yield return null;
            AssertLaneIsTraversed(BuildWesternBypassLane());
        }

        // Lane 4 of 6. The eastern bypass including its E-1 narrowing (NSC-045 AC-002: narrows to
        // 3.0 units between Shelf C and E-1 over Z 5.5 to 13.5).
        [UnityTest]
        public IEnumerator EasternBypass_TraversesE1NarrowingWithinItsOwnEnvelope()
        {
            yield return null;
            AssertLaneIsTraversed(BuildEasternBypassLane());
        }

        // Lane 5 of 6. The south cross-aisle connection - the east-west run that joins the entry
        // area to the southern mouth of all four north-south lanes above.
        [UnityTest]
        public IEnumerator SouthCrossAisle_ConnectsWesternAndEasternLaneMouthsWithinItsOwnEnvelope()
        {
            yield return null;
            AssertLaneIsTraversed(BuildSouthCrossAisleLane());
        }

        // Lane 6 of 6. The north cross-aisle connection - the east-west run that joins the northern
        // mouth of all four north-south lanes above and reaches the D2 staging rectangle.
        [UnityTest]
        public IEnumerator NorthCrossAisle_ConnectsWesternAndEasternLaneMouthsWithinItsOwnEnvelope()
        {
            yield return null;
            AssertLaneIsTraversed(BuildNorthCrossAisleLane());
        }

        // =====================================================================================
        // The D1-to-D2 route, asserted SEPARATELY because it proves no lane
        // =====================================================================================

        // NSC-071 AC-001: NSC-045 AC-002 requires the direct segment from (0, 0.25) to (6, 19.75)
        // to INTERSECT Shelf C, forcing a route choice, so an end-to-end path is necessarily a
        // detour through one of several lanes and cannot be evidence about any of them. It is
        // required only because a pursuing enemy must be able to cross the room at all - which is
        // why this test asserts PathComplete and NOT a lane envelope. Reading a pass here as
        // evidence about any individual lane is the error VAL-001's earlier revision made.
        [UnityTest]
        public IEnumerator D1ToD2Route_IsComplete_ButIsDeliberatelyNotEvidenceAboutAnyLane()
        {
            yield return null;

            Vector3 d1Approach = D1ApproachPoint;
            Vector3 d2Approach = D2ApproachPoint;

            AssertPointIsClearOfCommittedObstacles(d1Approach, "the D1 approach point");
            AssertPointIsClearOfCommittedObstacles(d2Approach, "the D2 approach point");

            Vector3 start = SampleNearRequestedPoint(d1Approach, "D1 approach");
            Vector3 end = SampleNearRequestedPoint(d2Approach, "D2 approach");

            Assert.IsTrue(agent.Warp(start),
                "Expected to warp the configured enemy onto the baked surface at the D1 approach.");

            var path = new NavMeshPath();
            bool produced = agent.CalculatePath(end, path);

            Assert.IsTrue(produced,
                "NSC-071 AC-001: a pursuing enemy must be able to cross the Bone Archive at all, " +
                "so CalculatePath from the D1 approach to the D2 approach must produce a path.");

            // PathPartial FAILS, and so does a true return with a non-complete status:
            // CalculatePath returning true means it PRODUCED a path, not that the path ARRIVES.
            Assert.AreEqual(NavMeshPathStatus.PathComplete, path.status,
                "NSC-071 AC-001: the D1-to-D2 route must be PathComplete, not " + path.status +
                ". This is the status EnemyPursuitMovement itself acts on, so the gate asserts " +
                "the same condition the game depends on.");
        }

        // =====================================================================================
        // The bake and the agent it was baked for
        // =====================================================================================

        // VAL-001: the bake must read the COMMITTED GameplayGeometry colliders and nothing else.
        // Re-asserted here AFTER the fixture's own objects exist, which is the half that a
        // setup-time check cannot cover: it proves the navigation host, the stand-in wizard and
        // the enemy contributed no geometry of their own to the surface the lane tests path on.
        [UnityTest]
        public IEnumerator BakeReadsOnlyTheCommittedGameplayGeometry()
        {
            yield return null;

            AssertRoomIsIsolatedFromOtherGeometry("after the fixture built its navigation and enemy");

            Assert.GreaterOrEqual(gameplayColliders.Length, MinimumExpectedGameplayColliders,
                "Only " + gameplayColliders.Length + " colliders were found under " +
                GameplayGeometryName + ". 11 were committed when this guard was written and " +
                "NSC-045 AC-005 requires 13, so suspect this query before the room.");

            int floors = gameplayColliders.Length - obstacles.Length;
            Assert.AreEqual(1, floors,
                "NSC-045 AC-005 authors exactly one floor BoxCollider whose top face is at Y 0; " +
                "every other gameplay collider stands above it. Found " + floors + ".");
        }

        // VAL-001: record the agent radius the run used, and make a later WIDENING of the agent
        // fail here rather than silently change what was proven.
        [UnityTest]
        public IEnumerator ConfiguredAgent_MatchesTheBakedSurfaceSettings_AndItsRadiusIsRecorded()
        {
            yield return null;

            NavMeshBuildSettings settings = NavMesh.GetSettingsByIndex(0);

            Debug.Log("NSC-071 VAL-001: agent radius used by this run = " +
                agentRadius.ToString("F3") + " (ProjectSettings/NavMeshAreas.asset, agentTypeID " +
                settings.agentTypeID + ").");

            // NSC-089: enemy movement and this fixture's agent navigate with the same
            // project-configured agent type GameplayNavigationSurface baked with, so their
            // radius/height/slope always match the baked surface.
            Assert.AreEqual(settings.agentTypeID, agent.agentTypeID,
                "The enemy agent must use the same agent type the surface was baked with.");
            Assert.AreEqual(settings.agentRadius, agent.radius, GeometryEpsilon,
                "The enemy agent must use the baked surface's radius.");
            Assert.AreEqual(settings.agentHeight, agent.height, GeometryEpsilon,
                "The enemy agent must use the baked surface's height.");

            // NSC-092's pursuit and search movement is present on the same enemy and is the
            // production owner of this agent's locomotion, so the traversal proven above is the
            // configured enemy's rather than a stand-in agent's.
            Assert.IsNotNull(pursuitMovement,
                "NSC-071 AC-001: the enemy must be the configured one - NSC-089's agent " +
                "configuration carrying NSC-092's delivered pursuit and search movement.");

            // The durable relation these lane expectations rest on: the configured agent must fit
            // through the narrowest lane NSC-045 authors.
            Assert.Less(2f * agentRadius, BoneArchiveLayout.MinLaneWidth,
                "The configured agent's diameter must fit NSC-045's " +
                BoneArchiveLayout.MinLaneWidth + "-unit minimum lane.");

            // The pinned figure. Widening the agent changes which endpoints are walkable and how
            // much margin each envelope has, so it must re-derive this fixture rather than quietly
            // prove something weaker.
            Assert.AreEqual(RecordedAgentRadius, agentRadius, GeometryEpsilon,
                "This fixture's endpoint placements and envelope margins were derived against " +
                "agentRadius " + RecordedAgentRadius + " and the run used " + agentRadius +
                ". VAL-001 requires a later widening of the agent to surface HERE as a failure. " +
                "Re-derive the endpoints and margins, then update this constant.");
        }

        // =====================================================================================
        // Lane construction - every figure DERIVED, none duplicated
        // =====================================================================================

        // NSC-045 AC-005 centres each perimeter wall BoxCollider on its RoomBounds line and makes
        // it WallThickness deep, so the inner (walkable) face sits half a thickness inside.
        private static float WestInnerFaceX =>
            BoneArchiveLayout.RoomBounds.min.x + (BoneArchiveLayout.WallThickness * 0.5f);

        private static float EastInnerFaceX =>
            BoneArchiveLayout.RoomBounds.max.x - (BoneArchiveLayout.WallThickness * 0.5f);

        private static float SouthInnerFaceZ =>
            BoneArchiveLayout.RoomBounds.min.z + (BoneArchiveLayout.WallThickness * 0.5f);

        private static float NorthInnerFaceZ =>
            BoneArchiveLayout.RoomBounds.max.z - (BoneArchiveLayout.WallThickness * 0.5f);

        // The longitudinal extents of the shelf field: NSC-045 AC-002's south cross-aisle lies
        // before the southmost shelf face, and its north cross-aisle beyond the northmost one.
        private static float ShelfFieldSouthFaceZ => Mathf.Min(
            BoneArchiveLayout.ShelfA.min.z,
            BoneArchiveLayout.ShelfB.min.z,
            BoneArchiveLayout.ShelfC.min.z);

        private static float ShelfFieldNorthFaceZ => Mathf.Max(
            BoneArchiveLayout.ShelfA.max.z,
            BoneArchiveLayout.ShelfB.max.z,
            BoneArchiveLayout.ShelfC.max.z);

        // ENDPOINTS COME FROM NSC-045's NAMED BOUNDARIES AND LONGITUDINAL EXTENTS. Each
        // north-south lane is probed from a point in the south cross-aisle to a point in the north
        // cross-aisle, one LaneEndMargin clear of the shelf field at each end, so the path must
        // span the lane's ENTIRE run rather than stopping inside it.
        private static float SouthAisleProbeZ => ShelfFieldSouthFaceZ - LaneEndMargin;

        private static float NorthAisleProbeZ => ShelfFieldNorthFaceZ + LaneEndMargin;

        // NSC-045 AC-002 names the direct segment from (0, 0.25) to (6, 19.75) - the D1 and D2
        // anchors projected onto the inner wall faces.
        private static Vector3 D1ApproachPoint =>
            new Vector3(BoneArchiveLayout.D1.x, 0f, SouthInnerFaceZ);

        private static Vector3 D2ApproachPoint =>
            new Vector3(BoneArchiveLayout.D2.x, 0f, NorthInnerFaceZ);

        private Lane BuildAToBLane()
        {
            float minX = BoneArchiveLayout.ShelfA.max.x;
            float maxX = BoneArchiveLayout.ShelfB.min.x;
            return NorthSouthLane("A-to-B lane", "NSC-045 AC-002 (3.5 clear, Shelf A to Shelf B)",
                minX, maxX, (minX + maxX) * 0.5f);
        }

        private Lane BuildBToCLane()
        {
            float minX = BoneArchiveLayout.ShelfB.max.x;
            float maxX = BoneArchiveLayout.ShelfC.min.x;

            // The probe X is the centre of the PINCH, not of the lane: NSC-045 AC-002 reduces this
            // lane to its deliberate 2.5-unit minimum where BA-1 intrudes, and BA-1 sits inside the
            // lane's own envelope. Both faces used here bound the SAME free gap with nothing
            // between them, which is what separates this from the midpoint rule VAL-001 forbids -
            // that rule spans an INTERVENING obstacle (Shelf C's east face to the east walkable
            // bound puts X 8 inside E-1). AssertPointIsClearOfCommittedObstacles re-checks this
            // against the room's real colliders rather than trusting the arithmetic.
            float pinchProbeX =
                (BoneArchiveLayout.CollapsedFurnitureBA1.max.x + BoneArchiveLayout.ShelfC.min.x) * 0.5f;

            return NorthSouthLane("B-to-C lane (BA-1 pinch)",
                "NSC-045 AC-002 (3.5 clear, reduced to the 2.5 minimum by BA-1)",
                minX, maxX, pinchProbeX);
        }

        private Lane BuildWesternBypassLane()
        {
            float minX = westBypassWestBoundX;
            float maxX = BoneArchiveLayout.ShelfA.min.x;
            return NorthSouthLane("western bypass (W-1 narrowing)",
                "NSC-045 AC-002 (3.0 narrowing between W-1 and Shelf A, Z 7 to 15)",
                minX, maxX, (minX + maxX) * 0.5f);
        }

        private Lane BuildEasternBypassLane()
        {
            float minX = BoneArchiveLayout.ShelfC.max.x;
            float maxX = eastBypassEastBoundX;
            return NorthSouthLane("eastern bypass (E-1 narrowing)",
                "NSC-045 AC-002 (3.0 narrowing between Shelf C and E-1, Z 5.5 to 13.5)",
                minX, maxX, (minX + maxX) * 0.5f);
        }

        private Lane BuildSouthCrossAisleLane()
        {
            // Envelope: everything south of the shelf field, between the inner wall faces. A route
            // that detoured north to get across would have to pass a shelf, leaving this envelope.
            return new Lane(
                "south cross-aisle connection",
                "NSC-045 AC-002 (south cross-aisle at least 3.5 deep before the shelf field)",
                WestInnerFaceX, EastInnerFaceX, SouthInnerFaceZ, ShelfFieldSouthFaceZ,
                new Vector3(WesternBypassProbeX, 0f, SouthAisleProbeZ),
                new Vector3(EasternBypassProbeX, 0f, SouthAisleProbeZ));
        }

        private Lane BuildNorthCrossAisleLane()
        {
            return new Lane(
                "north cross-aisle connection",
                "NSC-045 AC-002 (north cross-aisle at least 3.5 deep beyond the shelf field)",
                WestInnerFaceX, EastInnerFaceX, ShelfFieldNorthFaceZ, NorthInnerFaceZ,
                new Vector3(WesternBypassProbeX, 0f, NorthAisleProbeZ),
                new Vector3(EasternBypassProbeX, 0f, NorthAisleProbeZ));
        }

        // The cross-aisle probes deliberately reuse the two bypass probe columns, so a passing
        // cross-aisle test states that the aisle joins the outermost lane mouths - which is what
        // "connects the entry area to the north cross-aisle" needs on the east-west axis.
        private float WesternBypassProbeX =>
            (westBypassWestBoundX + BoneArchiveLayout.ShelfA.min.x) * 0.5f;

        private float EasternBypassProbeX =>
            (BoneArchiveLayout.ShelfC.max.x + eastBypassEastBoundX) * 0.5f;

        private static Lane NorthSouthLane(string name, string authority, float minX, float maxX, float probeX)
        {
            return new Lane(name, authority, minX, maxX, SouthAisleProbeZ, NorthAisleProbeZ,
                new Vector3(probeX, 0f, SouthAisleProbeZ),
                new Vector3(probeX, 0f, NorthAisleProbeZ));
        }

        // =====================================================================================
        // Assertions
        // =====================================================================================

        private void AssertLaneIsTraversed(Lane lane)
        {
            AssertPointIsClearOfCommittedObstacles(lane.Start, lane.Name + " start point");
            AssertPointIsClearOfCommittedObstacles(lane.End, lane.Name + " end point");

            Vector3 start = SampleInsideLane(lane, lane.Start, "start");
            Vector3 end = SampleInsideLane(lane, lane.End, "end");

            Assert.IsTrue(agent.Warp(start),
                "Expected to warp the configured enemy onto the baked surface at the " +
                lane.Name + " start " + Describe(start) + ".");

            var path = new NavMeshPath();
            bool produced = agent.CalculatePath(end, path);

            Assert.IsTrue(produced,
                "NSC-071 AC-001: the configured enemy must be able to traverse the " + lane.Name +
                " (" + lane.Authority + "), so CalculatePath must produce a path from " +
                Describe(start) + " to " + Describe(end) + ".");

            // PathPartial FAILS, and so does a true return value with a non-complete status.
            // CalculatePath returning true means it PRODUCED a path, not that the path ARRIVES;
            // asserting only the return value is the shape that passes on a severed NavMesh.
            Assert.AreEqual(NavMeshPathStatus.PathComplete, path.status,
                "NSC-071 AC-001: the " + lane.Name + " must return PathComplete, not " +
                path.status + ". " + lane.Authority + ".");

            Vector3[] corners = path.corners;
            Assert.GreaterOrEqual(corners.Length, 2,
                "A complete path across the " + lane.Name + " must carry at least a start and an " +
                "end corner; found " + corners.Length + ".");

            // THE ASSERTION THIS GATE EXISTS FOR. A complete path between two points does not
            // prove the lane between them: this room is designed with parallel routes, so a
            // severed lane still yields PathComplete by routing around it. Requiring every corner
            // to stay inside the lane's own envelope makes such an escape a failure.
            for (int index = 0; index < corners.Length; index++)
            {
                Assert.IsTrue(lane.ContainsXZ(corners[index], EnvelopeTolerance),
                    "NSC-071 AC-001/VAL-001: corner " + index + " of " + corners.Length + " on the " +
                    lane.Name + " route is at " + Describe(corners[index]) +
                    ", outside that lane's envelope " + lane.Envelope + " (tolerance " +
                    EnvelopeTolerance + "). The path ARRIVED but ESCAPED into a neighbouring " +
                    "route, which means the lane itself is severed on the baked surface even " +
                    "though the raw geometry clears it. " + lane.Authority + ".");
            }
        }

        // VAL-001: sampling must be TIGHT AND CHECKED. A rejected point silently relocated onto a
        // neighbouring route makes every later assertion pass about the wrong place.
        private Vector3 SampleInsideLane(Lane lane, Vector3 requested, string which)
        {
            Assert.IsTrue(
                NavMesh.SamplePosition(requested, out NavMeshHit hit, SampleRadius, NavMesh.AllAreas),
                "No walkable NavMesh within " + SampleRadius + " units of the " + lane.Name + " " +
                which + " " + Describe(requested) + ". The bake produced no surface there, so the " +
                "lane cannot be entered at all. " + lane.Authority + ".");

            Assert.IsTrue(lane.ContainsXZ(hit.position, EnvelopeTolerance),
                "NavMesh.SamplePosition moved the " + lane.Name + " " + which + " from " +
                Describe(requested) + " to " + Describe(hit.position) + ", which is outside that " +
                "lane's envelope " + lane.Envelope + ". Every assertion after this point would " +
                "have been about a different lane.");

            return hit.position;
        }

        private Vector3 SampleNearRequestedPoint(Vector3 requested, string which)
        {
            Assert.IsTrue(
                NavMesh.SamplePosition(requested, out NavMeshHit hit, SampleRadius, NavMesh.AllAreas),
                "No walkable NavMesh within " + SampleRadius + " units of the " + which + " point " +
                Describe(requested) + ".");

            // The D1/D2 approach points sit ON the inner wall line, so the agent-radius erosion
            // legitimately pulls them a little into the room. Bound that move so a sample cannot
            // wander somewhere else entirely; there is no lane envelope to check it against here,
            // because the D1-to-D2 route deliberately proves no lane.
            float moved = Vector2.Distance(
                new Vector2(requested.x, requested.z), new Vector2(hit.position.x, hit.position.z));
            Assert.LessOrEqual(moved, LaneEndMargin,
                "NavMesh.SamplePosition moved the " + which + " point " + moved.ToString("F3") +
                " units, from " + Describe(requested) + " to " + Describe(hit.position) + ".");

            return hit.position;
        }

        // A midpoint rule picks points INSIDE obstacles in this room, and an endpoint inside an
        // obstacle is silently relocated by SamplePosition and then proves nothing. This checks
        // every chosen point against the room's REAL committed colliders - including W-1 and E-1,
        // which have no BoneArchiveLayout symbol to read - rather than against the arithmetic that
        // produced it.
        private void AssertPointIsClearOfCommittedObstacles(Vector3 point, string which)
        {
            foreach (Collider collider in obstacles)
            {
                Bounds footprint = collider.bounds;
                bool insideX = point.x >= footprint.min.x - agentRadius
                    && point.x <= footprint.max.x + agentRadius;
                bool insideZ = point.z >= footprint.min.z - agentRadius
                    && point.z <= footprint.max.z + agentRadius;

                Assert.IsFalse(insideX && insideZ,
                    "NSC-071 VAL-001: " + which + " " + Describe(point) + " lies inside the " +
                    "committed obstacle '" + collider.name + "' (X [" +
                    footprint.min.x.ToString("F2") + "," + footprint.max.x.ToString("F2") + "] Z [" +
                    footprint.min.z.ToString("F2") + "," + footprint.max.z.ToString("F2") +
                    "]) once expanded by the agent radius " + agentRadius.ToString("F2") + ".");
            }
        }

        private void AssertRoomIsIsolatedFromOtherGeometry(string when)
        {
            Collider[] everyCollider = Object.FindObjectsByType<Collider>(FindObjectsSortMode.None);
            var strangers = new List<string>();

            foreach (Collider collider in everyCollider)
            {
                if (collider.gameObject.scene == roomScene
                    && collider.transform.IsChildOf(gameplayGeometry))
                {
                    continue;
                }

                strangers.Add(collider.name + " (scene '" + collider.gameObject.scene.name + "')");
            }

            CollectionAssert.IsEmpty(strangers,
                "GameplayNavigationSurface.ConfigureAndBuild collects EVERY active collider in the " +
                "session, so the bake is only about this room while this room's " +
                GameplayGeometryName + " owns every collider that exists. Found colliders " + when +
                " that are not under " + RoomRootName + "/" + GameplayGeometryName + ": " +
                string.Join(", ", strangers) + ". Any of these was baked into the surface the lane " +
                "assertions path on.");
        }

        // =====================================================================================
        // Collection and derivation from the committed scene
        // =====================================================================================

        private void CollectCommittedColliders()
        {
            gameplayColliders = gameplayGeometry.GetComponentsInChildren<Collider>(false);
            Assert.GreaterOrEqual(gameplayColliders.Length, MinimumExpectedGameplayColliders,
                "Found only " + gameplayColliders.Length + " active colliders under " +
                GameplayGeometryName + "; 11 were committed when this fixture was written.");

            obstacles = gameplayColliders
                .Where(collider => collider.bounds.max.y > FloorTopEpsilon)
                .ToArray();

            Assert.AreEqual(gameplayColliders.Length - 1, obstacles.Length,
                "NSC-045 AC-005 authors exactly one floor collider (top face at Y 0) and stands " +
                "every wall, shelf and bay on it, so exactly one collider must be excluded here.");
        }

        // W-1 and E-1 have no reachable BoneArchiveLayout symbol, so their facing bounds are read
        // from the COMMITTED colliders instead of guessed from a GameObject name or frozen as a
        // literal: the western bypass is bounded by whatever committed obstacle stands nearest west
        // of Shelf A at the room's mid-Z, and the eastern bypass by whatever stands nearest east of
        // Shelf C there. This follows NSC-045 rather than duplicating it, which NSC-071 AC-001
        // requires ("THOSE FIGURES ARE CITED, NOT ADOPTED").
        private void DeriveBypassBoundsFromCommittedGeometry()
        {
            float probeZ = BoneArchiveLayout.RoomBounds.center.z;
            float shelfAWestFaceX = BoneArchiveLayout.ShelfA.min.x;
            float shelfCEastFaceX = BoneArchiveLayout.ShelfC.max.x;

            westBypassWestBoundX = float.NegativeInfinity;
            eastBypassEastBoundX = float.PositiveInfinity;

            foreach (Collider collider in obstacles)
            {
                Bounds footprint = collider.bounds;
                if (footprint.min.z > probeZ || footprint.max.z < probeZ)
                {
                    continue;
                }

                if (footprint.max.x <= shelfAWestFaceX + GeometryEpsilon
                    && footprint.max.x > westBypassWestBoundX)
                {
                    westBypassWestBoundX = footprint.max.x;
                }

                if (footprint.min.x >= shelfCEastFaceX - GeometryEpsilon
                    && footprint.min.x < eastBypassEastBoundX)
                {
                    eastBypassEastBoundX = footprint.min.x;
                }
            }

            Assert.IsFalse(float.IsInfinity(westBypassWestBoundX),
                "No committed obstacle bounds the western bypass west of Shelf A at Z " +
                probeZ.ToString("F2") + ". At minimum the west perimeter wall must, so this query " +
                "broke rather than the room changing.");
            Assert.IsFalse(float.IsInfinity(eastBypassEastBoundX),
                "No committed obstacle bounds the eastern bypass east of Shelf C at Z " +
                probeZ.ToString("F2") + ". At minimum the east perimeter wall must, so this query " +
                "broke rather than the room changing.");

            // Sanity probe on the derivation itself: NSC-045 AC-002 allows no hard-geometry gap
            // below the 2.5-unit minimum, so a derived bypass narrower than that means the query
            // picked the wrong collider, not that the room is impassable.
            Assert.GreaterOrEqual(shelfAWestFaceX - westBypassWestBoundX,
                BoneArchiveLayout.MinLaneWidth - GeometryEpsilon,
                "The derived western bypass is narrower than NSC-045 AC-002's " +
                BoneArchiveLayout.MinLaneWidth + "-unit minimum.");
            Assert.GreaterOrEqual(eastBypassEastBoundX - shelfCEastFaceX,
                BoneArchiveLayout.MinLaneWidth - GeometryEpsilon,
                "The derived eastern bypass is narrower than NSC-045 AC-002's " +
                BoneArchiveLayout.MinLaneWidth + "-unit minimum.");
        }

        // NSC-089's configuration and NSC-092's pursuit/search movement, assembled exactly as the
        // committed EnemyPursuitPlayModeTests assembles the production enemy.
        //
        // WHY THE ENEMY IS HELD IN ITS IDLE BRANCH. EnemyPursuitMovement.Update drives
        // agent.SetDestination once EnemyTargetKnowledge acquires a target, which would move the
        // agent between the warp and the path request and make every lane measurement
        // non-deterministic. EnemyTargetKnowledge acquires on `distanceToWizard <=
        // detectionDistance`, so a detection distance of zero with the stand-in wizard parked far
        // outside the room never acquires, and EnemyPursuitMovement's Idle branch drives no
        // destination at all. The component is still the production locomotion owner of this
        // agent, and agent.CalculatePath is the same call it makes itself.
        //
        // The two distances are 0 and 0.01 rather than 0 and 0 because
        // EnemyTargetKnowledge.ValidateDistances THROWS unless detection is STRICTLY smaller than
        // lose-target; 0 and 0 would abort this fixture in setup.
        private void BuildConfiguredEnemy()
        {
            NavMeshBuildSettings settings = NavMesh.GetSettingsByIndex(0);
            agentRadius = settings.agentRadius;

            var wizardObject = new GameObject("BoneArchiveNavigationWizardStandIn");
            wizardObject.transform.SetParent(fixtureRoot.transform, false);
            wizardObject.transform.position = new Vector3(
                BoneArchiveLayout.RoomBounds.max.x + 1000f,
                0f,
                BoneArchiveLayout.RoomBounds.max.z + 1000f);

            // The enemy is created ON the baked surface: a NavMeshAgent added off the NavMesh logs
            // an error, which the Unity Test Framework would report as a failure of whichever test
            // ran first rather than as the setup problem it is. The south cross-aisle centre is the
            // one column NSC-045 AC-002 keeps clear across the whole room width.
            var spawnRequest = new Vector3(
                BoneArchiveLayout.D1.x, 0f, (SouthInnerFaceZ + ShelfFieldSouthFaceZ) * 0.5f);
            Assert.IsTrue(
                NavMesh.SamplePosition(spawnRequest, out NavMeshHit spawnHit, SampleRadius, NavMesh.AllAreas),
                "Expected the south cross-aisle centre " + Describe(spawnRequest) + " to sample " +
                "onto the surface baked from the committed " + GameplayGeometryName + ". If this " +
                "fails, the bake produced nothing and every lane assertion would fail for the " +
                "wrong reason.");

            var enemyObject = new GameObject("BoneArchiveNavigationEnemy");
            enemyObject.transform.SetParent(fixtureRoot.transform, false);
            enemyObject.transform.position = spawnHit.position;

            agent = enemyObject.AddComponent<NavMeshAgent>();
            agent.agentTypeID = settings.agentTypeID;
            agent.radius = settings.agentRadius;
            agent.height = settings.agentHeight;
            agent.Warp(spawnHit.position);

            var targetKnowledge = enemyObject.AddComponent<EnemyTargetKnowledge>();
            targetKnowledge.Initialize(wizardObject.transform);
            targetKnowledge.ConfigureDistances(0f, 0.01f);

            pursuitMovement = enemyObject.AddComponent<EnemyPursuitMovement>();
        }

        private static string Describe(Vector3 point)
        {
            return "(X " + point.x.ToString("F2") + ", Z " + point.z.ToString("F2") + ")";
        }

        // =====================================================================================
        // Lane envelope
        // =====================================================================================

        // One lane of NSC-045 INT-002's six: the X/Z rectangle NSC-045 AC-002 bounds it with, plus
        // the two endpoints the route between them must stay inside.
        private readonly struct Lane
        {
            public readonly string Name;
            public readonly string Authority;
            public readonly float MinX;
            public readonly float MaxX;
            public readonly float MinZ;
            public readonly float MaxZ;
            public readonly Vector3 Start;
            public readonly Vector3 End;

            public Lane(string name, string authority, float minX, float maxX, float minZ, float maxZ,
                Vector3 start, Vector3 end)
            {
                Name = name;
                Authority = authority;
                MinX = minX;
                MaxX = maxX;
                MinZ = minZ;
                MaxZ = maxZ;
                Start = start;
                End = end;
            }

            public string Envelope =>
                "X [" + MinX.ToString("F2") + "," + MaxX.ToString("F2") + "] Z [" +
                MinZ.ToString("F2") + "," + MaxZ.ToString("F2") + "]";

            public bool ContainsXZ(Vector3 point, float tolerance)
            {
                return point.x >= MinX - tolerance
                    && point.x <= MaxX + tolerance
                    && point.z >= MinZ - tolerance
                    && point.z <= MaxZ + tolerance;
            }
        }
    }
#endif
}
