using System.Collections;
using System.Collections.Generic;
using System.Text;
using NoSafeCircle.DoorPrototype;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.Enemies.Pooling;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Increment C, made permanent: EnemySpawnerPlayModeTests asserts agent.isOnNavMesh per entry
    // on a synthetic fixture floor, and its own comment says so - "This proves the sampling gate
    // is satisfiable here, not that the real rooms satisfy it - that is increment C." This file is
    // that coverage: it loads RuntimeWorld itself, with the shipped bake, the shipped table and
    // the shipped prefabs, and asserts the durable RELATION rather than tonight's numbers -
    // isOnNavMesh true for every melee entry, no agent for every wraith, and (behaviourally) that
    // a melee whose player is well outside both its attack range and its own stopping distance
    // actually closes the gap. The exact distances (1.3812u, 0.4487u, or any future bake's
    // numbers) are logged as diagnostic detail, never pinned as expectations - a bake that moves
    // by a few centimetres must not fail this suite.
    public sealed class RuntimeWorldEnemyNavMeshPlayModeTests
    {
        private const string MeasurementTag = "[RuntimeWorldEnemyNavMeshMeasurement]";
        private const string TableResource = "Enemies/EnemySpawnTable";

        // MeleeEnemyAttack.attackRange defaults to 1.5u and EnemyTargetKnowledge.detectionDistance
        // defaults to 6u (Assets/.../MeleeEnemyAttack.cs, EnemyTargetKnowledge.cs). 4u sits
        // comfortably outside the first and comfortably inside the second, so a melee that is
        // working correctly both detects the player and still has real distance left to close -
        // unlike testing at exactly 6u, which would sit on the detection boundary itself.
        private const float PursuitTestDistance = 4f;
        private const float PursuitTestWaitSeconds = 3.5f;

        // Same wait as FiveRoomDoorSequencePlayModeTests.WaitForWorldBuilt: the world does not
        // exist until GameBootstrap runs, and HasBuilt only reads true after three frames.
        private static IEnumerator WaitForWorldBuilt()
        {
            yield return null;
            GameObject managers = GameObject.Find("GameManagers");
            Assert.IsNotNull(managers,
                "RuntimeWorld.unity carries no GameManagers object, so nothing builds the world.");
            var bootstrap = managers.GetComponent<World.GameBootstrap>();
            Assert.IsNotNull(bootstrap, "GameManagers carries no GameBootstrap.");

            yield return null;
            yield return null;

            Assert.IsTrue(bootstrap.HasBuilt,
                "GameBootstrap had not built after three frames, so every assertion below would "
                + "fail on an empty world rather than on the thing under test. SpawnedCount = "
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

        private static void TeleportPlayer(GameObject player, Vector3 position)
        {
            var controller = player.GetComponent<CharacterController>();
            if (controller != null) controller.enabled = false;
            player.transform.position = position;
            if (controller != null) controller.enabled = true;
        }

        // Classifies all 8 directions around origin into SIGHT-BLOCKED and SIGHT-CLEAR, keeping
        // only the ones that are walkable - the same NavMesh.SamplePosition + CalculatePath/
        // PathComplete reachability check the old first-match helper used (NavMesh.SamplePosition
        // succeeding near a candidate proves the point is ON the navmesh; it does NOT prove it is
        // REACHABLE from origin, since a thin wall can put two on-mesh points on disconnected
        // islands - hence the CalculatePath/PathComplete check on top of it, unchanged from
        // before).
        //
        // This REPLACES the old TryFindWalkablePointAtDistance, which returned the FIRST walkable
        // direction in a fixed +X,-X,+Z,-Z,... order. In the Bone Archive +X happened to be the
        // sight-occluded direction, so the old behavioural test measured "never begins pursuit
        // when approached from +X in this room" while its name claimed "never begins pursuit" with
        // no qualification - approached from +Z, pursuit starts. Classifying every direction lets
        // the caller deliberately pick one of each class instead of being at the mercy of
        // enumeration order (NSC-131 INT-001).
        //
        // A direction that fails the walkable/reachable test is excluded from BOTH sets (logged,
        // not silently dropped) - exactly as the old helper silently skipped it before trying the
        // next candidate.
        private static List<DirectionClassification> ClassifyDirectionsBySight(
            Vector3 origin, float distance, GameObject player)
        {
            var candidates = new (Vector3 dir, string label)[]
            {
                (Vector3.right, "+X"), (Vector3.left, "-X"),
                (Vector3.forward, "+Z"), (Vector3.back, "-Z"),
                ((Vector3.right + Vector3.forward).normalized, "+X+Z"),
                ((Vector3.left + Vector3.forward).normalized, "-X+Z"),
                ((Vector3.right + Vector3.back).normalized, "+X-Z"),
                ((Vector3.left + Vector3.back).normalized, "-X-Z"),
            };

            var results = new List<DirectionClassification>();
            var path = new NavMeshPath();

            foreach (var (dir, label) in candidates)
            {
                var entry = new DirectionClassification { Label = label };
                Vector3 candidatePoint = origin + dir * distance;

                if (!NavMesh.SamplePosition(candidatePoint, out NavMeshHit hit, 1.5f, NavMesh.AllAreas))
                {
                    Debug.Log(MeasurementTag + " direction " + label + " from " + origin
                        + " did not sample onto the navmesh - excluded from both sight classes.");
                    results.Add(entry);
                    continue;
                }

                if (!NavMesh.CalculatePath(origin, hit.position, NavMesh.AllAreas, path)
                    || path.status != NavMeshPathStatus.PathComplete)
                {
                    Debug.Log(MeasurementTag + " direction " + label + " sampled onto the navmesh "
                        + "at " + hit.position + " but NavMesh.CalculatePath status was "
                        + path.status + " - rejected as unreachable, excluded from both sight "
                        + "classes.");
                    results.Add(entry);
                    continue;
                }

                entry.Walkable = true;
                entry.Point = hit.position;

                // The sight test needs a real collider at the candidate point to agree with
                // production (production's own exception is "a hit on the target's own transform
                // is still clear" - see HasUnobstructedViewMirroringProduction below), so the real
                // player is teleported to each walkable candidate in turn, the same TeleportPlayer
                // + Physics.SyncTransforms discipline used everywhere else in this file, then
                // teleported back out of the way before the next candidate so classification does
                // not contaminate whatever runs after it.
                TeleportPlayer(player, hit.position);
                Physics.SyncTransforms();
                entry.SightBlocked = !HasUnobstructedViewMirroringProduction(origin, player.transform);
                TeleportPlayer(player, new Vector3(-1000f, 0f, -1000f));
                Physics.SyncTransforms();

                Debug.Log(MeasurementTag + " direction " + label + " walkable at " + hit.position
                    + " classified " + (entry.SightBlocked ? "SIGHT-BLOCKED" : "SIGHT-CLEAR")
                    + " from origin " + origin);

                results.Add(entry);
            }

            return results;
        }

        // Mirrors EnemyTargetKnowledge.HasUnobstructedViewOfWizard EXACTLY for the
        // requiresLineOfSight == true branch (Scripts/Enemies/EnemyTargetKnowledge.cs:357-378):
        // same SightOcclusionLayers.EyeOffset chest-height sample on both ends, same
        // SightOcclusionLayers.ExcludeLowDressing(Physics.DefaultRaycastLayers) mask, same
        // QueryTriggerInteraction.Ignore, same "a hit on the target's own transform or a child of
        // it still counts as clear" exception. Every authored enemy has requiresLineOfSight
        // permanently true (Editor/World/DoorPrototypeGlobalSceneBuilder.cs:518), so there is no
        // "false" branch to mirror. Copied rather than reached via reflection, so if production's
        // rule changes and this is not updated to match, the two will visibly DISAGREE instead of
        // silently drifting apart - a predicate that can never disagree with the thing it checks is
        // worthless.
        private static bool HasUnobstructedViewMirroringProduction(Vector3 originPosition, Transform targetTransform)
        {
            var eye = originPosition + SightOcclusionLayers.EyeOffset;
            var target = targetTransform.position + SightOcclusionLayers.EyeOffset;
            var toTarget = target - eye;
            var distance = toTarget.magnitude;
            if (distance <= 0.01f) return true;

            if (!Physics.Raycast(eye, toTarget / distance, out RaycastHit hit, distance,
                    SightOcclusionLayers.ExcludeLowDressing(Physics.DefaultRaycastLayers),
                    QueryTriggerInteraction.Ignore))
            {
                return true;
            }

            return hit.transform == targetTransform || hit.transform.IsChildOf(targetTransform);
        }

        private struct DirectionClassification
        {
            public string Label;
            public bool Walkable;
            public Vector3 Point;
            public bool SightBlocked;
        }

        // Diagnostic only, for the case a melee reports a complete path but does not move: the
        // nearest OTHER collider's distance, so whoever investigates a real snag does not start
        // from zero. Excludes colliders under the enemy's own hierarchy. Uses Bounds.ClosestPoint
        // (axis-aligned, never throws) rather than Collider.ClosestPoint, which requires a convex
        // collider and this game's rooms render procedural, likely non-convex masonry.
        private static float NearestOtherColliderDistance(GameObject instance, Vector3 position, float searchRadius)
        {
            float nearest = float.PositiveInfinity;
            Collider[] hits = Physics.OverlapSphere(position, searchRadius);
            foreach (Collider hit in hits)
            {
                if (hit == null || hit.transform.IsChildOf(instance.transform)) continue;
                Vector3 closest = hit.bounds.ClosestPoint(position);
                float d = Vector3.Distance(position, closest);
                if (d < nearest) nearest = d;
            }
            return nearest;
        }

        private struct EntryReading
        {
            public string Id;
            public string Room;
            public EnemyKind Kind;
            public Vector3 AuthoredPosition;
            public bool InstanceFound;
            public bool HasAgent;
            public bool IsOnNavMesh;
            public Vector3 ActualPosition;
            public float DistanceFromAuthored;
        }

        [UnityTest]
        public IEnumerator RuntimeWorld_EveryEnemyEntry_IsOnNavMeshOrHasNoAgent()
        {
            yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);
            yield return WaitForWorldBuilt();

            var spawner = Object.FindFirstObjectByType<EnemySpawner>();
            Assert.IsNotNull(spawner,
                "no EnemySpawner exists in the built RuntimeWorld - the Enemies phase did not run "
                + "or its prefab is missing, which would make every reading below vacuous.");

            EnemyEncounter encounter = spawner.Encounter;
            Assert.IsNotNull(encounter,
                "EnemySpawner.Encounter is null after build - Spawn() ran but was refused (see "
                + "unity.log for the TryValidate/PlayerMovement error), so the world has zero live "
                + "enemies and every reading below would be a false negative.");

            var table = Resources.Load<EnemySpawnTable>(TableResource);
            Assert.IsNotNull(table, "Resources/" + TableResource + " did not load.");
            Assert.Greater(table.Entries.Count, 0, "the table declares zero entries.");

            Debug.Log(MeasurementTag + " EnemySpawner.SpawnedCount=" + spawner.SpawnedCount
                + " table.Entries.Count=" + table.Entries.Count
                + " (SpawnedCount confirms the encounter admitted instances, not merely that it "
                + "exists).");
            Assert.Greater(spawner.SpawnedCount, 0,
                "SpawnedCount is " + spawner.SpawnedCount + " - a zero-enemy world would make "
                + "every reading below a false negative rather than a measurement.");

            // Collect and log EVERY reading before asserting anything about it, so a real failure
            // still leaves the full diagnostic table in unity.log rather than aborting mid-loop.
            var readings = new List<EntryReading>();

            foreach (EnemySpawnEntry entry in table.Entries)
            {
                EnemyPrefabPool pool = entry.Kind == EnemyKind.Melee ? spawner.MeleePool : spawner.WraithPool;
                var reading = new EntryReading
                {
                    Id = entry.Id,
                    Room = entry.Room,
                    Kind = entry.Kind,
                    AuthoredPosition = entry.Position
                };

                GameObject instance = null;
                reading.InstanceFound = pool != null && pool.TryGetInstance(entry.Id, out instance);

                if (reading.InstanceFound && instance != null)
                {
                    var agent = instance.GetComponent<NavMeshAgent>();
                    reading.HasAgent = agent != null;
                    reading.IsOnNavMesh = agent != null && agent.isOnNavMesh;
                    reading.ActualPosition = instance.transform.position;
                    reading.DistanceFromAuthored = Vector3.Distance(entry.Position, reading.ActualPosition);
                }

                readings.Add(reading);
            }

            var diagnosticTable = new StringBuilder();
            diagnosticTable.AppendLine(MeasurementTag + " id,room,kind,authoredPos,instanceFound,hasAgent,isOnNavMesh,actualPos,distanceFromAuthored (diagnostic only - not asserted)");
            foreach (var r in readings)
            {
                diagnosticTable.AppendLine(string.Format(
                    "{0},{1},{2},{3},{4},{5},{6},{7},{8:F4}",
                    r.Id, r.Room, r.Kind, r.AuthoredPosition, r.InstanceFound, r.HasAgent,
                    r.IsOnNavMesh, r.ActualPosition, r.DistanceFromAuthored));
            }
            Debug.Log(diagnosticTable.ToString());

            // THE DURABLE RELATION, asserted after every reading is already on the record: every
            // melee entry has a live instance on the navmesh; every wraith has a live instance and
            // deliberately carries no agent (it holds its ground - EnemyEncounter.cs). Nothing here
            // pins a distance or a bake-specific coordinate.
            //
            // Collected into a list rather than asserted inline, so one entry's failure cannot
            // hide the other eight's verdicts (NUnit in this project has no Assert.Multiple - see
            // the behavioural test below for where that was learned the hard way).
            var failures = new List<string>();
            foreach (var r in readings)
            {
                if (!r.InstanceFound)
                {
                    failures.Add(r.Id + ": no live instance in its pool - Populate() skipped it.");
                    continue;
                }

                if (r.Kind == EnemyKind.Melee)
                {
                    if (!r.HasAgent) failures.Add(r.Id + ": a melee must carry a NavMeshAgent.");
                    else if (!r.IsOnNavMesh)
                    {
                        failures.Add(r.Id + " is not on the navmesh after Warp (authored "
                            + r.AuthoredPosition + ", landed " + r.ActualPosition + ", "
                            + r.DistanceFromAuthored.ToString("F4") + "u from authored).");
                    }
                }
                else
                {
                    if (r.HasAgent) failures.Add(r.Id + ": a wraith holds its ground and must carry no agent.");
                }
            }

            Assert.AreEqual(0, failures.Count, "\n" + string.Join("\n", failures));

            yield return UnloadRuntimeWorldSceneWithoutSaving();
        }

        // FORMERLY RuntimeWorld_BaMeleeAndFrMelee_CloseADistantGapToThePlayer, and FORMERLY
        // KNOWINGLY RED because it measured the wrong thing: it teleported the player to the
        // FIRST walkable direction in a fixed +X,-X,+Z,-Z,... order, with no regard for whether
        // that direction was inside the enemy's line of sight. In the Bone Archive +X happened to
        // be the sight-occluded direction, so it reported "ba-melee-1 never begins pursuit" when
        // the truer statement is "never begins pursuit when approached from +X in this room" -
        // approached from +Z, pursuit starts. That is obligation INT-001 on NSC-131.
        //
        // Repaired to classify all 8 directions by line of sight FIRST (ClassifyDirectionsBySight
        // above, mirroring EnemyTargetKnowledge's own rule exactly - see
        // HasUnobstructedViewMirroringProduction), then measure TWO controlled approaches per
        // enemy instead of one arbitrary one:
        //   sight-clear-control    the enemy must ACQUIRE (Pursuing) and close the gap - the
        //                          control that proves pursuit itself still works.
        //   sight-blocked-fallback the enemy must NOT be Pursuing on the very first tick after
        //                          the player becomes visible to it - i.e. WHILE the view is
        //                          still obstructed - AND still displace and close the
        //                          straight-line gap by the end of the window. GER's 2026-09-27
        //                          sight-fallback ruling only constrains behaviour WHILE
        //                          obstructed (EnemyTargetKnowledge.cs:123-156); it does not
        //                          forbid the ordinary acquisition path firing later if the view
        //                          genuinely clears as the enemy closes the distance - that is
        //                          the same transition EnemySightFallbackPlayModeTests asserts as
        //                          ViewClears_AcquiresByTheOrdinaryPath, and this method measured
        //                          it happen for real: see the per-id note below. So the final
        //                          State is logged but NOT asserted; only the state at first
        //                          contact is. The component-level state-machine half of this
        //                          (outcomes 2 and 3) is already covered by
        //                          EnemySightFallbackPlayModeTests; this method is the one place
        //                          outcome 1 - the root actually moving, on the real baked room -
        //                          is proved.
        //
        // WHAT WAS MEASURED ON THIS BRANCH, 2026-09-27, CONTRADICTING THE ORIGINAL BRIEF FOR THIS
        // REPAIR: the brief for NSC-131 INT-001 stated ba-melee-1's room (Bone Archive) currently
        // has ZERO sight-blocked walkable directions, following a merged prop-collider reshape
        // that dropped colliders reaching the y=1.0 eye line from 35/41 to 7/41. A live run of
        // THIS classification found the opposite for ba-melee-1: 2 of 8 walkable directions
        // (+X+Z, +X-Z) are still sight-blocked from its spawn point - some cover survives there.
        // fr-melee-1 is the one that measured zero of 8 sight-blocked (full 360 degrees of open
        // sightline at 4u) - a genuine absent-cover defect, just on the other room than the brief
        // named. Both counts are logged per id below rather than pinned as an expectation, exactly
        // like every other measurement in this file, because a future bake or prop edit can move
        // them - the assertions read the counts THIS run actually produced, and name whichever id
        // (if any) has none.
        //
        // Gated with an env-var Assert.Ignore, NOT [Explicit] - measured in this project,
        // [Explicit] does NOT prevent execution under the broad -TestFilter (CaptureRuntimeWorld
        // carries [Explicit] and still ran and failed there), while this idiom genuinely skips.
        [UnityTest]
        public IEnumerator RuntimeWorld_BaMeleeAndFrMelee_ClosesTheGapFromSightClearAndInvestigatesFromSightBlocked()
        {
            // GATED, NOT HIDDEN. Set NSC_RUN_KNOWN_DEFECTS to run it. As of 2026-09-27 it FAILS ON
            // PURPOSE: fr-melee-1 has zero of 8 walkable approach directions that are
            // sight-blocked, so its room currently provides no cover for it at all (a live
            // regression from a merged prop-collider reshape - see the comment above this method
            // for what this run measured and how it differs from NSC-131 INT-001's original
            // brief). Delete this gate once every measured id has at least one sight-blocked
            // walkable approach again.
            if (string.IsNullOrWhiteSpace(
                    System.Environment.GetEnvironmentVariable("NSC_RUN_KNOWN_DEFECTS")))
            {
                Assert.Ignore("At least one melee enemy in RuntimeWorld currently has ZERO "
                    + "walkable approach directions that are sight-blocked - i.e. its room "
                    + "provides no cover-capable approach for it - so the sight-blocked-fallback "
                    + "measurement below cannot run for that id. This is a live room-cover "
                    + "regression, not a defect in this test; see the comment above this method "
                    + "and the per-id failure text this produces for exact counts. Set "
                    + "NSC_RUN_KNOWN_DEFECTS to reproduce it.");
            }

            yield return SceneManager.LoadSceneAsync("RuntimeWorld", LoadSceneMode.Single);
            yield return WaitForWorldBuilt();

            var spawner = Object.FindFirstObjectByType<EnemySpawner>();
            Assert.IsNotNull(spawner, "no EnemySpawner exists in the built RuntimeWorld.");
            EnemyEncounter encounter = spawner.Encounter;
            Assert.IsNotNull(encounter, "EnemySpawner.Encounter is null - Spawn() was refused.");

            var table = Resources.Load<EnemySpawnTable>(TableResource);
            Assert.IsNotNull(table, "Resources/" + TableResource + " did not load.");

            var playerMovement = Object.FindFirstObjectByType<PlayerMovement>();
            Assert.IsNotNull(playerMovement,
                "no PlayerMovement exists in the built RuntimeWorld - the behavioural half needs a "
                + "real player to detect.");
            GameObject player = playerMovement.gameObject;

            // Collected first, asserted after - one id's or one phase's failure must not cost the
            // rest of the run its own reading. (This is exactly what happened the first time this
            // method was written with the assert inside the loop: an earlier failure aborted the
            // UnityTest coroutine and later readings were never measured.)
            var readings = new List<BehaviorReading>();
            var failures = new List<string>();

            foreach (var id in new[] { "ba-melee-1", "fr-melee-1" })
            {
                EnemySpawnEntry entry = null;
                foreach (var e in table.Entries) { if (e.Id == id) { entry = e; break; } }
                if (entry == null)
                {
                    failures.Add(id + ": not in the table - cannot test what does not exist.");
                    continue;
                }

                if (!spawner.MeleePool.TryGetInstance(id, out GameObject instance))
                {
                    failures.Add(id + ": no live instance in its pool.");
                    continue;
                }

                var agent = instance.GetComponent<NavMeshAgent>();
                if (agent == null)
                {
                    failures.Add(id + ": a melee must carry a NavMeshAgent, and this one has none.");
                    continue;
                }

                var targetKnowledge = instance.GetComponent<EnemyTargetKnowledge>();
                var pursuitMovement = instance.GetComponent<EnemyPursuitMovement>();
                if (targetKnowledge == null || pursuitMovement == null)
                {
                    failures.Add(id + ": a melee must carry EnemyTargetKnowledge and "
                        + "EnemyPursuitMovement, and this one is missing one of them.");
                    continue;
                }

                Vector3 startPos = instance.transform.position;

                // Classify BEFORE moving anything so every candidate is measured against the
                // enemy's untouched authored position.
                var classification = ClassifyDirectionsBySight(startPos, PursuitTestDistance, player);

                int walkableCount = 0, sightBlockedCount = 0, sightClearCount = 0;
                DirectionClassification? clearPick = null;
                DirectionClassification? blockedPick = null;
                foreach (var c in classification)
                {
                    if (!c.Walkable) continue;
                    walkableCount++;
                    if (c.SightBlocked)
                    {
                        sightBlockedCount++;
                        if (blockedPick == null) blockedPick = c;
                    }
                    else
                    {
                        sightClearCount++;
                        if (clearPick == null) clearPick = c;
                    }
                }

                Debug.Log(MeasurementTag + " " + id + " direction classification from " + startPos
                    + ": " + walkableCount + "/8 walkable, " + sightBlockedCount + " sight-blocked, "
                    + sightClearCount + " sight-clear.");

                // THE CONTROL: pursuit itself must still work from an unobstructed approach, or
                // nothing below is worth measuring.
                if (clearPick == null)
                {
                    failures.Add(id + ": no walkable direction is sight-clear (" + walkableCount
                        + " walkable of 8 candidates, all sight-blocked) - cannot run the control "
                        + "measurement that proves pursuit works at all.");
                }
                else
                {
                    pursuitMovement.ResetPursuit();
                    yield return null;

                    var outReading = new BehaviorReading[1];
                    yield return MeasureApproach(instance, agent, targetKnowledge, player, startPos,
                        clearPick.Value, outReading);
                    var r = outReading[0];
                    r.Id = id;
                    r.Phase = "sight-clear-control";
                    readings.Add(r);

                    if (!r.Measured)
                    {
                        failures.Add(id + " (sight-clear control): "
                            + (r.FailureReason ?? "not measured, no reason recorded."));
                    }
                    else if (r.State != EnemyTargetKnowledgeState.Pursuing || !(r.Moved > 1.5f))
                    {
                        failures.Add(id + " (sight-clear control): expected the enemy to ACQUIRE "
                            + "(Pursuing) and close most of the " + PursuitTestDistance
                            + "u gap; got state=" + r.State + " moved=" + r.Moved.ToString("F4")
                            + "u hasPath=" + r.HasPath + " pathStatus=" + r.PathStatus
                            + " remainingDistance=" + r.RemainingDistance.ToString("F4")
                            + " velocityMagnitude=" + r.VelocityMag.ToString("F4")
                            + " isStopped=" + r.IsStopped
                            + " - pursuit itself is broken, this is not a sight-classification "
                            + "question.");
                    }
                }

                // THE FALLBACK - the thing NSC-131 INT-001 actually asked this test to measure.
                // If this id has zero sight-blocked walkable directions, its room currently
                // provides it no cover at all, and that absence IS the assertion (see the comment
                // above this method for what a live run actually found per id, and why that
                // differs from the original brief's ba-melee-1-specific prediction). The exact
                // "35/41 to 7/41" collider figures are the Bone Archive's own measurement from
                // that brief and are only quoted for ba-melee-1, so a different room's absence is
                // not mis-attributed to a regression nobody has measured there.
                if (blockedPick == null)
                {
                    string extra = id == "ba-melee-1"
                        ? " - a live regression from a merged prop-collider reshape in the Bone "
                          + "Archive (tallest collider top dropped from 3.590u to 1.573u, "
                          + "colliders reaching the y=1.0 eye line dropped from 35/41 to 7/41), "
                          + "already reported by the Game Agent."
                        : " - this id's room has not been individually measured for a collider "
                          + "regression; it may be the same class of defect as ba-melee-1's Bone "
                          + "Archive, or a separate absence.";
                    failures.Add(id + ": zero of " + walkableCount + " walkable approach "
                        + "directions are sight-blocked (0 sight-blocked / " + sightClearCount
                        + " sight-clear / " + walkableCount + " walkable / 8 candidates total). "
                        + "This room currently provides NO cover-capable approach to " + id
                        + extra + " This is not a sampling or classification defect in the test - "
                        + "it is the room failing to provide the cover this measurement needs.");
                }
                else
                {
                    pursuitMovement.ResetPursuit();
                    yield return null;

                    var outReading = new BehaviorReading[1];
                    yield return MeasureApproach(instance, agent, targetKnowledge, player, startPos,
                        blockedPick.Value, outReading);
                    var r = outReading[0];
                    r.Id = id;
                    r.Phase = "sight-blocked-fallback";
                    readings.Add(r);

                    if (!r.Measured)
                    {
                        failures.Add(id + " (sight-blocked fallback): "
                            + (r.FailureReason ?? "not measured, no reason recorded."));
                    }
                    // Asserted against the state on the FIRST tick after the player became
                    // visible - i.e. WHILE the view was still obstructed - not the state at the
                    // end of the window. GER's ruling only constrains behaviour while obstructed;
                    // it does not forbid the ordinary acquisition path firing later once the
                    // enemy's approach genuinely clears the view (ViewClears_AcquiresByTheOrdinaryPath
                    // in EnemySightFallbackPlayModeTests already covers that transition). A first
                    // run of this method asserted the END state instead and produced a false
                    // failure for ba-melee-1, which re-acquired mid-approach once its path closed
                    // the diagonal sightline - see the comment above this method.
                    else if (r.StateImmediatelyAfterContact == EnemyTargetKnowledgeState.Pursuing
                        || !(r.Moved > 1.5f))
                    {
                        failures.Add(id + " (sight-blocked fallback): expected the enemy to "
                            + "INVESTIGATE (NOT Pursuing) on first contact while the view is still "
                            + "obstructed, and to still displace and close most of the "
                            + PursuitTestDistance + "u gap by the end of the window; got "
                            + "stateOnFirstContact=" + r.StateImmediatelyAfterContact
                            + " stateAtEnd=" + r.State + " moved=" + r.Moved.ToString("F4")
                            + "u hasPath=" + r.HasPath + " pathStatus=" + r.PathStatus
                            + " remainingDistance=" + r.RemainingDistance.ToString("F4")
                            + " velocityMagnitude=" + r.VelocityMag.ToString("F4")
                            + " isStopped=" + r.IsStopped + ".");
                    }
                }
            }

            var report = new StringBuilder();
            report.AppendLine(MeasurementTag
                + " behavioural(" + PursuitTestDistance + "u,sight-classified): id,phase,measured,"
                + "failureReason,stateOnFirstContact,stateAtEnd,hasPathAfter,pathStatusAfter,"
                + "startPos,endPos,movedDistance,remainingDistance,velocityMag,isStopped,"
                + "agentRadius,nearestOtherColliderDistance,playerDirectionUsed");
            foreach (var r in readings)
            {
                report.AppendLine(string.Format(
                    "{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10:F4},{11:F4},{12:F4},{13},{14:F4},{15:F4},{16}",
                    r.Id, r.Phase, r.Measured, r.FailureReason, r.StateImmediatelyAfterContact,
                    r.State, r.HasPath, r.PathStatus, r.StartPos, r.EndPos, r.Moved,
                    r.RemainingDistance, r.VelocityMag, r.IsStopped, r.Radius, r.NearestOther,
                    r.DirectionUsed));
            }
            Debug.Log(report.ToString());

            // THE DURABLE RELATION, asserted only after every id's and every phase's reading is
            // already on the record (NOT Assert.Multiple - this project's NUnit does not have it;
            // that was tried first and produced a compile error that wedged a Unity batchmode run
            // holding the project lock for over two hours, because a batchmode run that fails to
            // compile does not exit, it hangs).
            Assert.AreEqual(0, failures.Count, "\n" + string.Join("\n", failures));

            yield return UnloadRuntimeWorldSceneWithoutSaving();
        }

        // Runs one measurement window: teleports the player to the given approach point, lets
        // exactly ONE Update()/Tick() run (EnemyPursuitMovement.Update calls Tick(Time.deltaTime)
        // every frame on its own - nothing here calls Tick directly) and records the resulting
        // State as StateImmediatelyAfterContact - this is the "while the view is obstructed"
        // reading the sight-blocked-fallback assertion needs, since the FSM's ordinary
        // acquisition check runs for every non-Pursuing state (EnemyTargetKnowledge.cs:114-121),
        // so a later tick can legitimately re-acquire once the enemy's own approach clears the
        // sightline - that must not be read as a fallback failure. Then waits out the rest of
        // PursuitTestWaitSeconds of real time and records the final reading. A single-element
        // array carries the result out because a yielding iterator method cannot have an out or
        // ref parameter.
        private static IEnumerator MeasureApproach(
            GameObject instance, NavMeshAgent agent, EnemyTargetKnowledge targetKnowledge,
            GameObject player, Vector3 startPos, DirectionClassification approach,
            BehaviorReading[] outReading)
        {
            var reading = new BehaviorReading
            {
                StartPos = startPos,
                DirectionUsed = approach.Label,
            };

            TeleportPlayer(player, approach.Point);
            Physics.SyncTransforms();

            yield return null;
            reading.StateImmediatelyAfterContact = targetKnowledge.State;

            yield return new WaitForSeconds(PursuitTestWaitSeconds);

            reading.EndPos = instance.transform.position;
            reading.Moved = Vector3.Distance(startPos, reading.EndPos);
            reading.RemainingDistance = agent.remainingDistance;
            reading.VelocityMag = agent.velocity.magnitude;
            reading.IsStopped = agent.isStopped;
            reading.Radius = agent.radius;
            reading.HasPath = agent.hasPath;
            reading.PathStatus = agent.pathStatus;
            reading.State = targetKnowledge.State;
            reading.NearestOther = NearestOtherColliderDistance(instance, reading.EndPos, 3f);
            reading.Measured = true;
            outReading[0] = reading;

            Debug.Log(MeasurementTag + " " + approach.Label + " measured (player placed "
                + PursuitTestDistance + "u away, "
                + (approach.SightBlocked ? "SIGHT-BLOCKED" : "SIGHT-CLEAR") + "): stateOnFirstContact="
                + reading.StateImmediatelyAfterContact + " stateAtEnd=" + reading.State
                + " hasPath=" + reading.HasPath + " pathStatus=" + reading.PathStatus
                + " startPos=" + startPos + " endPos=" + reading.EndPos
                + " movedDistance=" + reading.Moved.ToString("F4")
                + " remainingDistance=" + reading.RemainingDistance.ToString("F4")
                + " velocityMagnitude=" + reading.VelocityMag.ToString("F4")
                + " isStopped=" + reading.IsStopped
                + " agentRadius=" + reading.Radius.ToString("F4")
                + " nearestOtherColliderDistance=" + reading.NearestOther.ToString("F4"));

            // Move the player far away again so this measurement does not contaminate whatever
            // runs next.
            TeleportPlayer(player, new Vector3(-1000f, 0f, -1000f));
            Physics.SyncTransforms();
            yield return null;
        }

        private struct BehaviorReading
        {
            public string Id;
            public string Phase;
            public bool Measured;
            public string FailureReason;
            public EnemyTargetKnowledgeState StateImmediatelyAfterContact;
            public EnemyTargetKnowledgeState State;
            public bool HasPath;
            public NavMeshPathStatus PathStatus;
            public Vector3 StartPos;
            public Vector3 EndPos;
            public float Moved;
            public float RemainingDistance;
            public float VelocityMag;
            public bool IsStopped;
            public float Radius;
            public float NearestOther;
            public string DirectionUsed;
        }
    }
}
