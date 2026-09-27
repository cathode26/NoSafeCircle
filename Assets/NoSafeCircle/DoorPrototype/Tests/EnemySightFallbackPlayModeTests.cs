using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-132 (a): a sight-blocked enemy INVESTIGATES rather than freezing.
    //
    // The defect in Vincent's words: the enemy will not walk around the furniture. A wizard
    // standing behind a 2.73-unit shelf is INSIDE detectionDistance, so the distance test
    // passes, but HasUnobstructedViewOfWizard gates acquisition and nothing else ran - the
    // enemy stayed Idle with hasPath false and velocity 0 for the whole window.
    //
    // GER ruled the design on 2026-09-27 and stated it as OUTCOMES, because a criterion naming
    // the mechanism would be satisfied by the defect itself:
    //   1  the root moves and the straight-line gap to the wizard closes
    //   2  while obstructed the enemy is NOT Pursuing - this is what keeps cover meaningful
    //   3  it terminates, without alternating between moving and stationary more than once
    //
    // WHAT THIS FIXTURE PROVES AND WHAT IT DOES NOT, stated because the split is the honest
    // part. These are component tests: they drive UpdateTargetKnowledge directly and assert the
    // STATE MACHINE - outcomes 2 and 3, plus the entry condition outcome 1 depends on. They
    // cannot prove a root moves, because nothing here owns a NavMeshAgent. Outcome 1 is
    // delivered by EnemyPursuitMovement.HandleSearching, which already paths to
    // LastKnownPosition under its own AC-002 coverage, and is proved end to end on the real
    // room by RuntimeWorld_BaMeleeAndFrMelee_CloseADistantGapToThePlayer.
    //
    // Every assertion below is a RELATION rather than a coordinate, so the fixture cannot pass
    // on the frozen pre-fix behaviour and will not falsely fail when an unrelated change nudges
    // an incidental value.
    public class EnemySightFallbackPlayModeTests
    {
        private const float DetectionDistance = 5f;
        private const float LoseTargetDistance = 10f;

        private GameObject enemyObject;
        private EnemyTargetKnowledge targetKnowledge;
        private GameObject wizardObject;
        private Transform wizardTransform;
        private GameObject occluderObject;

        [SetUp]
        public void SetUp()
        {
            enemyObject = new GameObject("TestEnemy");
            enemyObject.transform.position = Vector3.zero;
            targetKnowledge = enemyObject.AddComponent<EnemyTargetKnowledge>();

            wizardObject = new GameObject("TestWizard");
            wizardTransform = wizardObject.transform;

            targetKnowledge.Initialize(wizardTransform);
            targetKnowledge.ConfigureDistances(DetectionDistance, LoseTargetDistance);
        }

        [TearDown]
        public void TearDown()
        {
            DestroyOccluder();

            if (enemyObject != null)
            {
                UnityEngine.Object.DestroyImmediate(enemyObject);
            }

            if (wizardObject != null)
            {
                UnityEngine.Object.DestroyImmediate(wizardObject);
            }
        }

        // A solid, non-trigger box on the Default layer, tall enough to cross the chest-height
        // sample line (SightOcclusionLayers.EyeOffset is Vector3.up). This stands in for
        // ba_shelf_bank_z_middle, which is 2.73 units tall on Default and SHOULD block sight -
        // GER ruled that making it stop occluding is not the fix, so the test keeps it opaque.
        private void PlaceOccluderBetweenEnemyAndWizard()
        {
            DestroyOccluder();

            occluderObject = GameObject.CreatePrimitive(PrimitiveType.Cube);
            occluderObject.name = "TestOccluder";
            occluderObject.transform.position =
                (enemyObject.transform.position + wizardTransform.position) * 0.5f;
            // THIN IN X ON PURPOSE. A cube scaled 4 and centred midway spans the whole gap, so
            // the ray would START on the collider's own face - a raycast begun inside a collider
            // is not reliable, and the test would be measuring that instead of the sight rule.
            occluderObject.transform.localScale = new Vector3(1f, 4f, 4f);
            Physics.SyncTransforms();
        }

        private void DestroyOccluder()
        {
            if (occluderObject != null)
            {
                UnityEngine.Object.DestroyImmediate(occluderObject);
                occluderObject = null;
            }

            Physics.SyncTransforms();
        }

        private void PlaceWizardInsideDetectionRange()
        {
            wizardTransform.position = new Vector3(DetectionDistance - 1f, 0f, 0f);
            Physics.SyncTransforms();
        }

        // CONTROL: with the sight rule OFF, nothing in this change may alter acquisition. Every
        // pre-existing component test asserts the distance-only contract, and this is the local
        // witness that the blast radius really is limited to sight-gated enemies.
        [Test]
        public void SightRuleOff_StillAcquiresImmediately_Control()
        {
            targetKnowledge.SetRequiresLineOfSight(false);
            PlaceWizardInsideDetectionRange();
            PlaceOccluderBetweenEnemyAndWizard();

            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing),
                "an enemy that does not require line of sight must acquire on distance alone, "
                + "occluder or no occluder - this is the unchanged pre-existing contract");
        }

        // OUTCOME 2, first half, and the reproduction of the defect's entry condition: the
        // wizard is inside detectionDistance and the view is blocked, so the enemy must NOT be
        // Pursuing. Before the fix it also sat in Idle doing nothing, which is why the second
        // assertion is the one that carries the change.
        [Test]
        public void ViewBlocked_DoesNotPursue_AndInvestigatesTheDetectedPosition()
        {
            targetKnowledge.SetRequiresLineOfSight(true);
            PlaceWizardInsideDetectionRange();
            PlaceOccluderBetweenEnemyAndWizard();

            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.Not.EqualTo(EnemyTargetKnowledgeState.Pursuing),
                "sight must still gate Pursuing - an investigating enemy is suspicious, not "
                + "locked on, and that is what keeps cover meaningful");
            Assert.That(targetKnowledge.State,
                Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition),
                "a blocked contact must leave Idle: this is the state EnemyPursuitMovement "
                + "already paths from, and staying Idle is the reported defect");
            Assert.That(
                Vector3.Distance(targetKnowledge.LastKnownPosition, wizardTransform.position),
                Is.LessThan(0.001f),
                "the investigation must head for the position the enemy actually detected, "
                + "which is what makes the gap close");
        }

        // An investigating enemy is not a locked-on one. TryRedirectToSpectralDecoy requires
        // Pursuing, and CurrentTarget is the field the rest of the game reads to mean acquired,
        // so leaving it null is what makes evasion still possible.
        [Test]
        public void ViewBlocked_DoesNotClaimTheWizardAsAnAcquiredTarget()
        {
            targetKnowledge.SetRequiresLineOfSight(true);
            PlaceWizardInsideDetectionRange();
            PlaceOccluderBetweenEnemyAndWizard();

            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.CurrentTarget, Is.Null,
                "investigating is not acquiring - CurrentTarget must stay unset until the view "
                + "actually clears");
        }

        // OUTCOME 2, second half: the sight gate is a gate, not a wall. Once the occluder is
        // gone the ordinary acquisition path must fire, from the investigating state.
        [Test]
        public void ViewClears_AcquiresByTheOrdinaryPath()
        {
            targetKnowledge.SetRequiresLineOfSight(true);
            PlaceWizardInsideDetectionRange();
            PlaceOccluderBetweenEnemyAndWizard();
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State, Is.Not.EqualTo(EnemyTargetKnowledgeState.Pursuing),
                "precondition: the view must start blocked");

            DestroyOccluder();
            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing),
                "when the view clears the enemy must acquire by the ordinary path");
            Assert.That(targetKnowledge.CurrentTarget, Is.EqualTo(wizardTransform));
        }

        // OUTCOME 3, AND THE REASON THE LATCH EXISTS. Without it this is the pacing defect in a
        // different state's clothing: investigate, arrive, wander, fall back to Idle, notice the
        // same blocked wizard, investigate again, for ever. The leash fix taught us that an
        // oscillation arrives as a SIDE EFFECT of a correct-looking change, so it is asserted
        // directly rather than assumed.
        [Test]
        public void ViewStillBlockedAfterAFinishedInvestigation_DoesNotInvestigateAgain()
        {
            targetKnowledge.SetRequiresLineOfSight(true);
            PlaceWizardInsideDetectionRange();
            PlaceOccluderBetweenEnemyAndWizard();

            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State,
                Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition),
                "precondition: the first blocked contact must start an investigation");

            // Movement reports arrival, then the bounded wander/search interval expires. This is
            // the existing termination path; nothing new had to be built to reach a terminal
            // state, which is why outcome 3 is cheap here.
            targetKnowledge.ReportArrivedAtLastKnownPosition();
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Wandering),
                "precondition: arrival must begin the bounded wander interval");

            targetKnowledge.UpdateTargetKnowledge(1000f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle),
                "precondition: the bounded interval must expire back to Idle");

            // Nothing has changed: same wizard, same position, same occluder. The enemy must
            // stay put rather than starting the cycle over.
            for (int tick = 0; tick < 10; tick++)
            {
                targetKnowledge.UpdateTargetKnowledge(0.1f);
                Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle),
                    "with the wizard and the occluder unchanged the enemy must reach a terminal "
                    + "outcome and hold it - re-investigating is the oscillation outcome 3 "
                    + "forbids (tick " + tick + ")");
            }
        }

        // The latch is per CONTACT, not per lifetime. An enemy that has given up on a blocked
        // wizard must investigate again the next time that wizard turns up, or one shelf would
        // disable it permanently - a worse bug than the one being fixed.
        [Test]
        public void WizardLeavesAndReturns_InvestigatesTheNewContact()
        {
            targetKnowledge.SetRequiresLineOfSight(true);
            PlaceWizardInsideDetectionRange();
            PlaceOccluderBetweenEnemyAndWizard();

            targetKnowledge.UpdateTargetKnowledge(0f);
            targetKnowledge.ReportArrivedAtLastKnownPosition();
            targetKnowledge.UpdateTargetKnowledge(1000f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle),
                "precondition: the first investigation must have run and terminated");

            // Out of detection range - this is what ends the contact.
            wizardTransform.position = new Vector3(DetectionDistance * 4f, 0f, 0f);
            Physics.SyncTransforms();
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle),
                "precondition: a wizard outside detection range must not start anything");

            PlaceWizardInsideDetectionRange();
            PlaceOccluderBetweenEnemyAndWizard();
            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State,
                Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition),
                "a wizard that leaves and returns is a NEW contact and must be investigated "
                + "again - the latch bounds one investigation per contact, not per lifetime");
        }
    }
}
