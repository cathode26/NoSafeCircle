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
    // These assert the RELATION the spec requires - the anchor has moved from spawn AND the
    // rope is exactly taut - rather than a frozen coordinate, so the suite cannot pass on the
    // pre-change fixed-at-spawn anchor and will not falsely fail the next time an unrelated
    // change nudges an incidental value.
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
        // it so the rope stays exactly taut." The enemy starts at the spawn anchor (0,0,0),
        // acquires the wizard, then is dragged 8 units out on a 5-unit leash - 3 units past
        // slack. The anchor must have moved off spawn, and the enemy's distance from the
        // (moved) anchor must equal the leash length within tolerance, not the frozen spawn
        // point.
        [Test]
        public void UpdateTargetKnowledge_DraggedBeyondSlack_AnchorMovesFromSpawnAndRopeIsExactlyTaut()
        {
            var spawnPosition = enemyObject.transform.position;
            targetKnowledge.SetMaximumPursuitDistanceFromStart(5f);
            AcquirePursuit(new Vector3(4f, 0f, 0f));

            enemyObject.transform.position = new Vector3(8f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            // The give-up-while-beyond-leash branch is what surfaces the anchor value onto the
            // public LastKnownPosition field; see the SpectralDecoy leash tests for the same
            // mechanism. This is a case of it firing without any spectral decoy involved.
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));

            var anchor = targetKnowledge.LastKnownPosition;
            Assert.That(anchor, Is.Not.EqualTo(spawnPosition),
                "the anchor must have been dragged off its original spawn point");
            Assert.That(Vector3.Distance(anchor, enemyObject.transform.position), Is.EqualTo(5f).Within(0.001f),
                "the rope must be exactly taut at the leash length after the drag");
        }

        // Spec: "Pursuit is thereby unbounded in absolute terms." Demonstrates the actual
        // consequence: an enemy dragged 8 units from its ORIGINAL spawn - beyond the old
        // fixed-at-spawn 5-unit cap, which would have permanently blocked re-acquisition past
        // that radius - can still re-acquire the wizard, because the (towed) anchor trails the
        // enemy rather than staying pinned to spawn.
        [Test]
        public void UpdateTargetKnowledge_ReacquiresFarFromOriginalSpawn_BecauseAnchorTrailedTheDrag()
        {
            targetKnowledge.SetMaximumPursuitDistanceFromStart(5f);
            AcquirePursuit(new Vector3(4f, 0f, 0f));

            enemyObject.transform.position = new Vector3(8f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));

            // Wizard stays close to the enemy's current (far-from-spawn) position, well inside
            // detection distance and exactly at the fresh anchor's slack boundary.
            wizardTransform.position = new Vector3(10f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing),
                "re-acquisition 8 units from original spawn must succeed once the anchor has trailed the drag");
            Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(wizardTransform));
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
    }
}
