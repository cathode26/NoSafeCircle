using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using NoSafeCircle.DoorPrototype;
using NoSafeCircle.DoorPrototype.World;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-130 (Tasks/NSC-130.yaml, contract_revision 7, hash 8019e3c4) VAL-001 / AC-006(b): props
    // actually occlude line of sight IN THE BUILT WORLD, proven by a real Physics.Raycast rather
    // than by any property of a prefab.
    //
    // WHY THIS MUST BE PLAYMODE, quoting the contract's own rev-7 provenance: "the only live
    // scenes on main are Assets/Scenes/RuntimeWorld.unity and SampleScene ... RuntimeWorld.unity
    // is 8,685 bytes with 13 components and 3 named objects ... and ZERO colliders of any kind."
    // Props are instantiated by PropSpawner (Scripts/World/PropSpawner.cs) AT RUNTIME in Awake,
    // per Vincent's own decision quoted in that file's header - "No we must stop this baking
    // thing", "The scene should just be some objects that create prefabs". So prop colliders exist
    // only after Play begins; an EditMode query against the committed scene would raycast through
    // an empty room and report CLEAR forever - "the zero-discovered-tests failure in another
    // coat: the query runs, the mechanism works, and the thing under test is not present."
    //
    // AC-006 (revisions 6-7) BANS any scalar standing in for a raycast in this fixture or a
    // helper - no threshold on depth, thickness, footprint area or aspect ratio may decide a
    // verdict, because no such number predicts occlusion: "a slab blocks broadside and misses
    // along its length, so occlusion depends on the ray's angle and no scalar predicts it." Every
    // OBSTRUCTED/CLEAR verdict below comes from a real Physics.Raycast using
    // HasUnobstructedView, copied line-for-line from production's
    // EnemyTargetKnowledge.HasUnobstructedViewOfWizard (Scripts/Enemies/EnemyTargetKnowledge.cs,
    // roughly lines 372-393). Live collider geometry is read ONLY to choose WHERE the two ends of
    // the ray sit - broadside across the prop's own thin axis, or alongside its long axis but
    // displaced clear of it - never to decide the outcome. The same geometric construction is used
    // by RuntimeWorldEnemyNavMeshPlayModeTests.cs (HasUnobstructedViewMirroringProduction) for the
    // same reason: a predicate that cannot disagree with the thing it checks is worthless.
#if UNITY_EDITOR
    public sealed class PropSightOcclusionPlayModeTests
    {
        private const string CatalogFolder =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/RoomDressing";

        private const string PrefabFolder =
            "Assets/NoSafeCircle/DoorPrototype/Resources/Props";

        private const string MeasurementTag = "[PropSightOcclusionMeasurement]";

        // Geometry-derived construction, never a pass/fail threshold: "beyond the box's own
        // measured half-extent" is a safety margin for where to put a ray endpoint, not a
        // criterion for whether the ray is obstructed.
        private const float CrossingMargin = 2.5f;
        private const float ClearSidestepMargin = 1.0f;

        private GameObject sightTarget;

        [TearDown]
        public void TearDown()
        {
            if (sightTarget != null)
            {
                Object.Destroy(sightTarget);
                sightTarget = null;
            }
        }

        // ---------------------------------------------------------------------------------
        // PART 1: the count the gate must see BEFORE anything about occlusion, taken from the
        // catalogs - never from PropSpawner.SpawnedCount. VAL-001's own text: "a count greater
        // than zero, taken from the catalogs rather than from the spawner's own output."
        // ---------------------------------------------------------------------------------

        private struct CatalogExpectation
        {
            public int TotalPlacements;
            public int ResolvablePlacements;
        }

        private static string[] CatalogPaths()
        {
            return Directory
                .GetFiles(CatalogFolder, "*DressingCatalog.json", SearchOption.TopDirectoryOnly)
                .Select(p => p.Replace('\\', '/'))
                .OrderBy(p => p, System.StringComparer.Ordinal)
                .ToArray();
        }

        // Reads the catalogs directly (AssetDatabase + JsonUtility, exactly as
        // PropSpawnerPlayModeTests.ExpectedPlacementCount / EveryPropIdInEveryCatalogHasAPrefabOnDisk
        // already do in this same folder) and separately checks File.Exists under PrefabFolder -
        // the SAME resolution PropSpawner performs internally with Resources.Load, but computed
        // here from scratch so this fixture cannot be agreeing with PropSpawner.SpawnedCount by
        // construction. LowerVault alone is known to carry 20 of 62 unresolvable placements (a
        // separate, already-known defect); resolvablePlacements is the tolerant figure the live
        // world is actually compared against, and both numbers are logged so the shortfall is
        // never hidden.
        private static CatalogExpectation ExpectedFromCatalogs(StringBuilder log)
        {
            string[] paths = CatalogPaths();
            Assert.AreEqual(5, paths.Length,
                "Expected five room dressing catalogs in " + CatalogFolder + ". Found "
                + paths.Length + " - every count in this fixture is derived from them, so a wrong "
                + "count here would make the rest pass vacuously.");

            int totalPlacements = 0;
            int resolvable = 0;
            var missingPrefabIds = new HashSet<string>();

            foreach (string path in paths)
            {
                var asset = UnityEditor.AssetDatabase.LoadAssetAtPath<TextAsset>(path);
                Assert.IsNotNull(asset, path + " did not import as a TextAsset.");

                var parsed = JsonUtility.FromJson<RoomDressingCatalog>(asset.text);
                Assert.IsNotNull(parsed, path + " did not deserialize.");
                Assert.IsNotNull(parsed.props, path + " has no props array.");

                int roomTotal = parsed.props.Length;
                int roomResolvable = 0;
                foreach (DressingPlacement placement in parsed.props)
                {
                    if (File.Exists(Path.Combine(PrefabFolder, placement.prop_id + ".prefab")))
                    {
                        roomResolvable++;
                    }
                    else
                    {
                        missingPrefabIds.Add(placement.prop_id);
                    }
                }

                totalPlacements += roomTotal;
                resolvable += roomResolvable;
                log.AppendLine(MeasurementTag + " " + parsed.room + ": " + roomResolvable + "/"
                    + roomTotal + " placements resolve to a prefab under " + PrefabFolder + ".");
            }

            log.AppendLine(MeasurementTag + " TOTAL: " + resolvable + "/" + totalPlacements
                + " resolvable across all catalogs. " + missingPrefabIds.Count + " distinct "
                + "prop_id(s) have no prefab on disk (a known, separate defect - not this "
                + "fixture's to fix): "
                + string.Join(", ", missingPrefabIds.OrderBy(s => s, System.StringComparer.Ordinal)));

            Assert.Greater(totalPlacements, 0,
                "The catalogs declare zero placements - every count below would pass vacuously.");

            return new CatalogExpectation
            {
                TotalPlacements = totalPlacements,
                ResolvablePlacements = resolvable,
            };
        }

        // ---------------------------------------------------------------------------------
        // PART 2: load the actual RuntimeWorld scene and let GameBootstrap build it - the ONLY
        // place props exist at all. Mirrors
        // RuntimeWorldEnemyNavMeshPlayModeTests.WaitForWorldBuilt / UnloadRuntimeWorldSceneWithoutSaving
        // exactly (same GameManagers/GameBootstrap/HasBuilt wait, same three-frame settle, same
        // unload-without-saving teardown), copied rather than shared because that file is other
        // in-flight work on this branch and is not in this task's allowed_files.
        // ---------------------------------------------------------------------------------

        private static IEnumerator LoadRuntimeWorld()
        {
            yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);

            yield return null;
            GameObject managers = GameObject.Find("GameManagers");
            Assert.IsNotNull(managers,
                "RuntimeWorld.unity carries no GameManagers object, so nothing builds the world.");
            var bootstrap = managers.GetComponent<GameBootstrap>();
            Assert.IsNotNull(bootstrap, "GameManagers carries no GameBootstrap.");

            yield return null;
            yield return null;

            Assert.IsTrue(bootstrap.HasBuilt,
                "GameBootstrap had not built after three frames, so every assertion below would "
                + "fail on an empty world rather than on the thing under test. SpawnedCount="
                + bootstrap.SpawnedCount + ".");
        }

        private static IEnumerator UnloadRuntimeWorldSceneWithoutSaving()
        {
            var scene = SceneManager.GetSceneByName("RuntimeWorld");
            if (scene.IsValid() && scene.isLoaded)
            {
                yield return SceneManager.UnloadSceneAsync(scene);
            }
        }

        // ---------------------------------------------------------------------------------
        // PART 3: the real sight query, copied rather than invented.
        // ---------------------------------------------------------------------------------

        // Mirrors EnemyTargetKnowledge.HasUnobstructedViewOfWizard EXACTLY
        // (Scripts/Enemies/EnemyTargetKnowledge.cs:372-393): same
        // SightOcclusionLayers.EyeOffset chest-height sample added to BOTH ends, same
        // SightOcclusionLayers.ExcludeLowDressing(Physics.DefaultRaycastLayers) mask, same
        // QueryTriggerInteraction.Ignore, same "a hit on the target's own transform, or a child of
        // it, still counts as clear" exception. Copied rather than reached by reflection so that a
        // future change to production which is not mirrored here DISAGREES visibly instead of
        // silently drifting apart.
        private static bool HasUnobstructedView(
            Vector3 originPosition, Transform targetTransform, out RaycastHit hit)
        {
            var eye = originPosition + SightOcclusionLayers.EyeOffset;
            var target = targetTransform.position + SightOcclusionLayers.EyeOffset;
            var toTarget = target - eye;
            var distance = toTarget.magnitude;
            if (distance <= 0.01f)
            {
                hit = default;
                return true;
            }

            if (!Physics.Raycast(eye, toTarget / distance, out hit, distance,
                    SightOcclusionLayers.ExcludeLowDressing(Physics.DefaultRaycastLayers),
                    QueryTriggerInteraction.Ignore))
            {
                return true;
            }

            return hit.transform == targetTransform || hit.transform.IsChildOf(targetTransform);
        }

        // One spawned, non-trigger BoxCollider whose world-space vertical span crosses eye height -
        // AC-006's own prefab-checkable NECESSARY condition, read from LIVE geometry rather than
        // restated. This is used ONLY to pick two ray endpoints; it never appears in a pass/fail
        // comparison itself. LocalAcrossWorld is the box's own local +Z axis in world space (its
        // thin/depth axis after the AC-001/AC-007 base-only reshape, though nothing here assumes
        // that ordering - see below); LocalAlongWorld is its local +X axis. Y is unaffected by a
        // pure yaw (rotation_euler_z) rotation, so the height check is exact for every placement in
        // this project regardless of its authored rotation.
        private struct Candidate
        {
            public BoxCollider Box;
            public Vector3 Center;
            public Vector3 GroundCenter;
            public Vector3 LocalAlongWorld;
            public Vector3 LocalAcrossWorld;
            public float HalfAlong;
            public float HalfAcross;
        }

        private static List<Candidate> FindEyeHeightCandidates(GameObject propsRoot)
        {
            var result = new List<Candidate>();
            float eyeY = SightOcclusionLayers.EyeOffset.y;

            foreach (BoxCollider box in propsRoot.GetComponentsInChildren<BoxCollider>(true))
            {
                if (box.isTrigger) continue;

                Transform t = box.transform;
                Vector3 halfSizeLocal = Vector3.Scale(box.size * 0.5f, t.lossyScale);
                Vector3 centerWorld = t.TransformPoint(box.center);

                float halfHeightWorld = Mathf.Abs(t.up.y) * halfSizeLocal.y
                    + Mathf.Abs(t.right.y) * halfSizeLocal.x
                    + Mathf.Abs(t.forward.y) * halfSizeLocal.z;
                float top = centerWorld.y + halfHeightWorld;
                float bottom = centerWorld.y - halfHeightWorld;
                if (!(top >= eyeY && bottom <= eyeY)) continue;

                result.Add(new Candidate
                {
                    Box = box,
                    Center = centerWorld,
                    // GROUND LEVEL (y=0), NOT the collider's own center Y. HasUnobstructedView
                    // mirrors production exactly: it adds SightOcclusionLayers.EyeOffset to
                    // whatever origin it is given, exactly as EnemyTargetKnowledge does to a
                    // ground-anchored enemy's transform.position. The FIRST version of this
                    // fixture passed the collider's own (already chest-height) center as that
                    // origin, so EyeOffset was applied on top of it a second time - every ray
                    // sailed clean over the top of every prop and reported CLEAR everywhere,
                    // including two false OBSTRUCTED hits on room walls instead of any prop. Ray
                    // endpoints must be built from a GROUND point, exactly like a real actor
                    // standing on the floor, so the single EyeOffset in HasUnobstructedView lands
                    // at the true eye height.
                    GroundCenter = new Vector3(centerWorld.x, 0f, centerWorld.z),
                    LocalAlongWorld = t.right.normalized,
                    LocalAcrossWorld = t.forward.normalized,
                    HalfAlong = halfSizeLocal.x,
                    HalfAcross = halfSizeLocal.z,
                });
            }

            return result;
        }

        [UnityTest]
        public IEnumerator
            PropsAreSpawnedAndAtLeastOneLandmarkPropObstructsARealSightQuery_InTheBuiltWorld()
        {
            var catalogLog = new StringBuilder();
            CatalogExpectation expected = ExpectedFromCatalogs(catalogLog);
            Debug.Log(catalogLog.ToString());

            Assert.Greater(expected.ResolvablePlacements, 0,
                "Zero catalog placements resolve to a prefab on disk - nothing could possibly "
                + "spawn, so every assertion below would be vacuous.");

            yield return LoadRuntimeWorld();

            var spawner = Object.FindFirstObjectByType<PropSpawner>();
            Assert.IsNotNull(spawner,
                "No PropSpawner exists in the built RuntimeWorld - the Props phase did not run, "
                + "so the world has no dressing at all and every occlusion check below would be a "
                + "false negative against an empty room.");

            // --- ASSERT PROPS WERE ACTUALLY SPAWNED, BEFORE ANYTHING ABOUT OCCLUSION. ---
            // Counted from the LIVE hierarchy, never from spawner.SpawnedCount: VAL-001's own
            // text is "a count greater than zero, taken from the catalogs rather than from the
            // spawner's own output." The expected side above never called Spawn() or read
            // SpawnedCount either - it is independent, from AssetDatabase + File.Exists.
            Collider[] spawnedColliders = spawner.GetComponentsInChildren<Collider>(true);
            var spawnedColliderSet = new HashSet<Collider>(spawnedColliders);
            int spawnedSpriteRenderers =
                spawner.GetComponentsInChildren<SpriteRenderer>(true).Length;

            Debug.Log(MeasurementTag + " catalogs: " + expected.ResolvablePlacements + "/"
                + expected.TotalPlacements + " resolvable placements. Live world: "
                + spawnedSpriteRenderers + " spawned prop object(s), " + spawnedColliders.Length
                + " carry a collider.");

            Assert.AreEqual(expected.ResolvablePlacements, spawnedSpriteRenderers,
                "The live world spawned " + spawnedSpriteRenderers + " prop object(s) against "
                + expected.ResolvablePlacements + " resolvable catalog placements (independently "
                + "computed above, not read from PropSpawner.SpawnedCount). A shortfall here means "
                + "PropSpawner failed to instantiate something the catalogs say should resolve.");

            Assert.Greater(spawnedColliders.Length, 0,
                "Zero of the " + spawnedSpriteRenderers + " spawned props carry a collider at "
                + "all. WITHOUT THIS the world is empty of anything a sight ray could possibly "
                + "hit, and the occlusion assertion below would pass on an empty room instead of "
                + "failing it - a raycast through nothing reports CLEAR every time.");
            Assert.LessOrEqual(spawnedColliders.Length, spawnedSpriteRenderers,
                "More colliders (" + spawnedColliders.Length + ") than spawned prop objects ("
                + spawnedSpriteRenderers + ") were found under the spawner - the collider count "
                + "is not commensurate with what the catalogs say should exist.");

            // --- ONLY NOW, THE REAL SIGHT QUERY. ---
            Physics.SyncTransforms();
            List<Candidate> candidates = FindEyeHeightCandidates(spawner.gameObject);
            Debug.Log(MeasurementTag + " " + candidates.Count + " spawned, non-trigger prop "
                + "collider(s) cross eye height (y=" + SightOcclusionLayers.EyeOffset.y
                + ") and are eligible for the sight query below.");
            Assert.Greater(candidates.Count, 0,
                "No spawned prop collider crosses eye height in the built world, so AC-006(b) has "
                + "nothing to test a sight query against. Known ground truth (measured "
                + "2026-09-27): ba_shelf_bank_z_middle/_start and fr_landmark_bone_throne should "
                + "still cross it.");

            sightTarget = new GameObject("PropSightOcclusion_SyntheticTarget");

            bool anyObstructedByAProp = false;
            bool anyEstablishedClear = false;
            string obstructedBy = null;
            var report = new StringBuilder();

            foreach (Candidate c in candidates)
            {
                // BROADSIDE: a straight line from outside one face of the box to outside the
                // opposite face, crossing its local-Z extent while its local-X coordinate is held
                // at dead center (so it stays within the box's local-X span throughout). This
                // construction passes through the box's interior regardless of its proportions -
                // it is a geometric guarantee, not a measurement of whether it occludes.
                Vector3 broadsideEye = c.GroundCenter - c.LocalAcrossWorld * (c.HalfAcross + CrossingMargin);
                Vector3 broadsideTargetPos = c.GroundCenter + c.LocalAcrossWorld * (c.HalfAcross + CrossingMargin);
                sightTarget.transform.position = broadsideTargetPos;
                Physics.SyncTransforms();
                bool broadsideClear = HasUnobstructedView(
                    broadsideEye, sightTarget.transform, out RaycastHit broadsideHit);

                // ALONG ITS LENGTH: travels parallel to the box's local-X extent but displaced
                // beyond its local-Z extent the whole way, so the line never enters the box at
                // all - the ESTABLISHED-CLEAR negative control, from the exact same
                // HasUnobstructedView query and the exact same box, required so the OBSTRUCTED
                // result above is not a query that can only ever return one answer.
                Vector3 sidestep = c.LocalAcrossWorld * (c.HalfAcross + ClearSidestepMargin);
                Vector3 alongEye =
                    c.GroundCenter - c.LocalAlongWorld * (c.HalfAlong + CrossingMargin) + sidestep;
                Vector3 alongTargetPos =
                    c.GroundCenter + c.LocalAlongWorld * (c.HalfAlong + CrossingMargin) + sidestep;
                sightTarget.transform.position = alongTargetPos;
                Physics.SyncTransforms();
                bool alongClear = HasUnobstructedView(
                    alongEye, sightTarget.transform, out RaycastHit alongHit);

                string who = c.Box.gameObject.name;
                report.AppendLine(MeasurementTag + " " + who + " center=" + c.Center
                    + " broadside=" + (broadsideClear ? "CLEAR" : "OBSTRUCTED")
                    + (broadsideClear ? "" : " (hit " + broadsideHit.transform.name + ")")
                    + " along-length=" + (alongClear ? "CLEAR" : "OBSTRUCTED")
                    + (alongClear ? "" : " (hit " + alongHit.transform.name + ")"));

                if (!broadsideClear && !anyObstructedByAProp
                    && spawnedColliderSet.Contains(broadsideHit.collider))
                {
                    // Attributable to a SPAWNED PROP specifically, not to architecture - a wall
                    // stopping the ray would prove nothing about props.
                    anyObstructedByAProp = true;
                    obstructedBy = who;
                }

                if (alongClear)
                {
                    anyEstablishedClear = true;
                }
            }

            Debug.Log(report.ToString());

            Assert.IsTrue(anyObstructedByAProp,
                "No spawned prop obstructed a broadside sight query anywhere in the built world "
                + "(" + candidates.Count + " candidate(s) checked; see the per-candidate log "
                + "above). Known ground truth (measured 2026-09-27): approaching ba-melee-1 in "
                + "the Bone Archive, 2 of 8 walkable directions are sight-blocked.");

            Assert.IsTrue(anyEstablishedClear,
                "NEGATIVE CONTROL FAILED: every along-length query also reported OBSTRUCTED. "
                + "HasUnobstructedView must be able to return true as well as false, or the "
                + "OBSTRUCTED result above is not evidence that props occlude - it would be "
                + "evidence that this query always reports the same answer.");

            Debug.Log(MeasurementTag + " asserted OBSTRUCTED via '" + obstructedBy
                + "'; asserted at least one CLEAR reading exists among " + candidates.Count
                + " candidate(s).");

            yield return UnloadRuntimeWorldSceneWithoutSaving();
        }
    }
#endif
}
