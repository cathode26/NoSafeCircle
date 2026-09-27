using NoSafeCircle.DoorPrototype;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Covers the towed pursuit-leash anchor: "the owner must move with enemy" and "the enemy
    // must drag the owner when it runs out of slack" (Vincent). maximumPursuitDistanceFromStart
    // is a SLACK RADIUS around a movable anchor, not a fixed distance from the original spawn
    // point, so absolute pursuit distance from spawn is unbounded.
    //
    // Towing the anchor is only half the spec. Running out of slack no longer ends an ordinary
    // chase either - the enemy must stay Pursuing while the anchor trails it, or the two halves
    // combine into the reported defect ("the enemy keeps pacing back and forth"): walk to the
    // slack limit, give up, walk back to the anchor just towed, re-acquire, repeat forever one
    // leash-length from wherever it started. These assert the RELATION the spec requires - the
    // anchor has moved from spawn, the rope is exactly taut, AND the chase never breaks off for
    // distance - rather than a frozen coordinate, so the suite cannot pass on either the
    // pre-change fixed-at-spawn anchor or the tow-with-give-up half-fix, and will not falsely
    // fail the next time an unrelated change nudges an incidental value.
    public class EnemyTargetKnowledgeLeashAnchorPlayModeTests
    {
        private GameObject enemyObject;
        private EnemyTargetKnowledge targetKnowledge;
        private GameObject wizardObject;
        private Transform wizardTransform;

        [SetUp]
        public void SetUp()
        {
            enemyObject = new GameObject("TestEnemy");
            enemyObject.transform.position = Vector3.zero;
            targetKnowledge = enemyObject.AddComponent<EnemyTargetKnowledge>();

            wizardObject = new GameObject("TestWizard");
            wizardTransform = wizardObject.transform;

            targetKnowledge.Initialize(wizardTransform);
            targetKnowledge.ConfigureDistances(5f, 10f);
        }

        [TearDown]
        public void TearDown()
        {
            if (enemyObject != null)
            {
                UnityEngine.Object.DestroyImmediate(enemyObject);
            }

            if (wizardObject != null)
            {
                UnityEngine.Object.DestroyImmediate(wizardObject);
            }
        }

        private void AcquirePursuit(Vector3 wizardPosition)
        {
            wizardTransform.position = wizardPosition;
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(targetKnowledge.CurrentTarget, Is.EqualTo(wizardTransform));
        }

        // Spec: "once the enemy is further than the leash, the anchor is dragged along behind
        // it so the rope stays exactly taut" AND running out of slack no longer ends an
        // ordinary chase. The enemy starts at the spawn anchor (0,0,0), acquires the wizard,
        // then is dragged 8 units out on a 5-unit leash - 3 units past slack. The chase must
        // stay Pursuing (the give-up branch fires only for a spectral-decoy redirect, not here),
        // the anchor must have moved off spawn, and the enemy's distance from the (moved)
        // anchor must equal the leash length within tolerance, not the frozen spawn point.
        // Read via PursuitAnchor rather than LastKnownPosition: the give-up branch that used to
        // surface the anchor onto LastKnownPosition no longer runs for an ordinary chase.
        [Test]
        public void UpdateTargetKnowledge_DraggedBeyondSlack_AnchorMovesFromSpawnAndRopeIsExactlyTaut()
        {
            var spawnPosition = enemyObject.transform.position;
            targetKnowledge.SetMaximumPursuitDistanceFromStart(5f);
            AcquirePursuit(new Vector3(4f, 0f, 0f));

            enemyObject.transform.position = new Vector3(8f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing),
                "an ordinary chase must not give up for distance once the anchor is towed");

            var anchor = targetKnowledge.PursuitAnchor;
            Assert.That(anchor, Is.Not.EqualTo(spawnPosition),
                "the anchor must have been dragged off its original spawn point");
            Assert.That(Vector3.Distance(anchor, enemyObject.transform.position), Is.EqualTo(5f).Within(0.001f),
                "the rope must be exactly taut at the leash length after the drag");
        }

        // Spec: "Pursuit is thereby unbounded in absolute terms." Demonstrates the actual
        // consequence: an enemy dragged 8 units from its ORIGINAL spawn - beyond the old
        // fixed-at-spawn 5-unit cap, which under the pre-change behaviour would have ended the
        // chase for good - simply keeps chasing, because the (towed) anchor trails the enemy
        // rather than staying pinned to spawn. Renamed from "Reacquires...": with the give-up
        // removed there is nothing to re-acquire - CurrentTarget was never cleared - so a name
        // built around re-acquisition would no longer describe what the test does.
        [Test]
        public void UpdateTargetKnowledge_ContinuesFarFromOriginalSpawn_BecauseAnchorTrailedTheDrag()
        {
            var spawnPosition = enemyObject.transform.position;
            targetKnowledge.SetMaximumPursuitDistanceFromStart(5f);
            AcquirePursuit(new Vector3(4f, 0f, 0f));

            enemyObject.transform.position = new Vector3(8f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));

            // Wizard stays close to the enemy's current (far-from-spawn) position, well inside
            // detection/lose-target distance. Push the enemy to 1000 units from its ORIGINAL
            // spawn - vastly beyond the old fixed 5-unit cap - in one further step.
            enemyObject.transform.position = new Vector3(1000f, 0f, 0f);
            wizardTransform.position = new Vector3(1004f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing),
                "the chase 1000 units from original spawn must continue uninterrupted once the anchor has trailed the drag");
            Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(wizardTransform));

            var anchor = targetKnowledge.PursuitAnchor;
            Assert.That(anchor, Is.Not.EqualTo(spawnPosition),
                "the anchor must have been dragged off its original spawn point");
            Assert.That(Vector3.Distance(anchor, enemyObject.transform.position), Is.EqualTo(5f).Within(0.001f),
                "the rope must be exactly taut at the leash length after the drag");
        }

        // THE DEFECT ITSELF, not just the tow. Towing the anchor while still giving up produces
        // exactly the reported symptom - "The enemy keeps pacing back and forth" - because the
        // enemy walks to the slack limit, gives up, walks back to the anchor it just towed,
        // re-acquires, and repeats forever, one leash-length from wherever it started. A
        // single-step test cannot tell "towed and still gives up" apart from "towed and keeps
        // chasing," because both produce a moved anchor and a taut rope on step one; only
        // driving several cycles, progressively further out, can. This drives the enemy well
        // past two and three leash-lengths (10f, 15f) from the original spawn over repeated
        // steps and asserts the chase never once breaks off into SearchingLastKnownPosition for
        // distance reasons, and that the anchor keeps trailing at exactly the leash length on
        // every step - not just the first.
        [Test]
        public void UpdateTargetKnowledge_RepeatedDragCycles_NeverPacesIntoSearchingLastKnownPosition()
        {
            targetKnowledge.SetMaximumPursuitDistanceFromStart(5f);
            AcquirePursuit(new Vector3(4f, 0f, 0f));

            // Each step keeps the wizard 2 units ahead of the enemy on the same line, so
            // distanceToWizard(2) never approaches loseTargetDistance(10) - only the leash
            // mechanism is under test, not the separate lose-target-distance give-up path.
            // 14 and 20 are past two and three leash-lengths (10f, 15f) from the spawn at 0.
            float[] enemyXPositions = { 8f, 14f, 20f, 26f, 32f };

            foreach (var x in enemyXPositions)
            {
                enemyObject.transform.position = new Vector3(x, 0f, 0f);
                wizardTransform.position = new Vector3(x + 2f, 0f, 0f);
                targetKnowledge.UpdateTargetKnowledge(0f);

                Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing),
                    $"an ordinary chase must never pace into SearchingLastKnownPosition for distance reasons (x={x})");
                Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(wizardTransform));

                var anchor = targetKnowledge.PursuitAnchor;
                Assert.That(Vector3.Distance(anchor, enemyObject.transform.position), Is.EqualTo(5f).Within(0.001f),
                    $"the rope must stay exactly taut at the leash length as the anchor trails (x={x})");
            }
        }

        // Acceptance check: zero must keep meaning "unlimited," unchanged. An enemy dragged an
        // arbitrarily large distance from spawn while pursuing must never be forced to give up
        // for distance reasons when the leash is left at its default (0f).
        [Test]
        public void UpdateTargetKnowledge_DefaultUnlimitedLeash_NeverGivesUpForDistance()
        {
            Assert.That(targetKnowledge.LoseTargetDistance, Is.EqualTo(10f)); // sanity: ConfigureDistances applied
            AcquirePursuit(new Vector3(4f, 0f, 0f));

            enemyObject.transform.position = new Vector3(1000f, 0f, 0f);
            wizardTransform.position = new Vector3(1004f, 0f, 0f); // stays within loseTargetDistance too

            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing),
                "maximumPursuitDistanceFromStart <= 0f must remain unlimited, regardless of drag");
        }

        // startPosition's DUAL ROLE, pinned. IsBeyondPursuitLeash() has already dragged
        // startPosition by the time the spectral-decoy give-up reads it into LastKnownPosition
        // (EnemyTargetKnowledge.cs, the redirect branch under State == Pursuing) - that read is
        // of the TOWED anchor, not the enemy's original spawn point. Vincent's design is a home
        // that FOLLOWS ("the enemy post is fixed where it spawned, but it needs to be allowed to
        // drag its leash anchor"), so the towed post IS the home for this path too; a fixed
        // spawn post would contradict that. This asserts the RELATION - LastKnownPosition must
        // equal PursuitAnchor read AFTER the drag, and must differ from spawn - so it fails if
        // the give-up is ever pointed at a frozen spawn coordinate instead of the live anchor,
        // and does not depend on any particular numeric position.
        [Test]
        public void UpdateTargetKnowledge_RedirectedGivesUpBeyondSlack_SearchesTowedAnchorNotSpawn()
        {
            var spawnPosition = enemyObject.transform.position;
            targetKnowledge.SetMaximumPursuitDistanceFromStart(5f);
            AcquirePursuit(new Vector3(4f, 0f, 0f));

            var decoyObject = new GameObject("TestSpectralDecoy");
            try
            {
                var redirected = targetKnowledge.TryRedirectToSpectralDecoy(decoyObject.transform);
                Assert.That(redirected, Is.True, "redirect must succeed while Pursuing the wizard");
                Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.True);

                // Drag the enemy past the leash while still redirected to the decoy - this is
                // the exact call that tows startPosition and then, in the same tick, reads it
                // back for the give-up.
                enemyObject.transform.position = new Vector3(8f, 0f, 0f);
                targetKnowledge.UpdateTargetKnowledge(0f);

                var towedAnchor = targetKnowledge.PursuitAnchor;
                Assert.That(towedAnchor, Is.Not.EqualTo(spawnPosition),
                    "the anchor must have been dragged off spawn by running out of slack");

                Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition),
                    "running out of slack while redirected must end the redirect and start a search");
                Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
                Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(wizardTransform));

                Assert.That(targetKnowledge.LastKnownPosition, Is.EqualTo(towedAnchor),
                    "the redirected give-up must search the TOWED anchor (PursuitAnchor), not a fixed spawn point");
                Assert.That(targetKnowledge.LastKnownPosition, Is.Not.EqualTo(spawnPosition),
                    "the redirected give-up must not search the enemy's original spawn point");
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(decoyObject);
            }
        }
    }
}
