using System;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class EnemyTargetKnowledgePlayModeTests
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

        private void EnterSearchingState()
        {
            wizardTransform.position = new Vector3(4f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            wizardTransform.position = new Vector3(11f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);
        }

        // AC-001, VAL-001: default authored distances already satisfy the strict
        // Detection Distance < Lose Target Distance relationship.
        [Test]
        public void InitialState_IsIdleWithoutTarget()
        {
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(targetKnowledge.HasTarget, Is.False);
            Assert.That(targetKnowledge.DetectionDistance, Is.LessThan(targetKnowledge.LoseTargetDistance));
        }

        // AC-001, VAL-001: the owner-controlled configuration entry point accepts a strictly
        // ordered pair and exposes both values read-only.
        [Test]
        public void ConfigureDistances_DetectionDistanceStrictlySmaller_UpdatesBothValues()
        {
            targetKnowledge.ConfigureDistances(3f, 7f);

            Assert.That(targetKnowledge.DetectionDistance, Is.EqualTo(3f));
            Assert.That(targetKnowledge.LoseTargetDistance, Is.EqualTo(7f));
        }

        // AC-001, VAL-001: equal distances would let acquire/lose flicker at one boundary,
        // so configuration must reject them rather than silently accepting the pair.
        [Test]
        public void ConfigureDistances_DetectionDistanceEqualToLoseTargetDistance_ThrowsArgumentException()
        {
            Assert.Throws<ArgumentException>(() => targetKnowledge.ConfigureDistances(5f, 5f));
        }

        // AC-001, VAL-001: a Detection Distance larger than Lose Target Distance is likewise
        // rejected by the strict threshold validation.
        [Test]
        public void ConfigureDistances_DetectionDistanceGreaterThanLoseTargetDistance_ThrowsArgumentException()
        {
            Assert.Throws<ArgumentException>(() => targetKnowledge.ConfigureDistances(10f, 5f));
        }

        // AC-002, VAL-001: the wizard entering Detection Distance acquires it as the current
        // target and enters active pursuit.
        [Test]
        public void UpdateTargetKnowledge_WizardInsideDetectionDistance_AcquiresTargetAndEntersPursuing()
        {
            wizardTransform.position = new Vector3(4f, 0f, 0f);

            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(targetKnowledge.CurrentTarget, Is.EqualTo(wizardTransform));
            Assert.That(targetKnowledge.HasTarget, Is.True);
        }

        // AC-001/AC-002, VAL-001: exactly at Detection Distance still counts as inside it.
        [Test]
        public void UpdateTargetKnowledge_WizardExactlyAtDetectionDistance_Acquires()
        {
            wizardTransform.position = new Vector3(5f, 0f, 0f);

            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
        }

        // AC-002, VAL-001: a wizard beyond Detection Distance does not acquire and the
        // enemy stays idle.
        [Test]
        public void UpdateTargetKnowledge_WizardOutsideDetectionDistance_StaysIdle()
        {
            wizardTransform.position = new Vector3(6f, 0f, 0f);

            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(targetKnowledge.HasTarget, Is.False);
        }

        // AC-002: a doorway-crossing style position change that stays within Lose Target
        // Distance does not clear the acquired target. EnemyTargetKnowledge never inspects
        // doorway events, so this proves persistence purely from distance.
        [Test]
        public void UpdateTargetKnowledge_WizardPositionChangeWithinLoseTargetDistance_RetainsPursuit()
        {
            wizardTransform.position = new Vector3(4f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            wizardTransform.position = new Vector3(9f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(targetKnowledge.CurrentTarget, Is.EqualTo(wizardTransform));
        }

        // AC-003, VAL-001: exceeding Lose Target Distance while pursuing records the last
        // known position and transitions solely from that distance comparison.
        [Test]
        public void UpdateTargetKnowledge_PursuingWizardExceedsLoseTargetDistance_TransitionsToSearchingAndRecordsLastKnownPosition()
        {
            wizardTransform.position = new Vector3(4f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));

            var lastKnownPosition = new Vector3(11f, 0f, 0f);
            wizardTransform.position = lastKnownPosition;
            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
            Assert.That(targetKnowledge.LastKnownPosition, Is.EqualTo(lastKnownPosition));
            Assert.That(targetKnowledge.HasTarget, Is.True);
        }

        // AC-003, VAL-001: exactly at Lose Target Distance has not yet exceeded it, so
        // pursuit continues.
        [Test]
        public void UpdateTargetKnowledge_PursuingWizardExactlyAtLoseTargetDistance_StaysPursuing()
        {
            wizardTransform.position = new Vector3(4f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            wizardTransform.position = new Vector3(10f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
        }

        // AC-004, VAL-001: movement reporting arrival at the last known position starts the
        // bounded wander/search interval at its full configured duration.
        [Test]
        public void ReportArrivedAtLastKnownPosition_WhileSearching_EntersWanderingWithFullSearchDuration()
        {
            EnterSearchingState();

            targetKnowledge.ReportArrivedAtLastKnownPosition();

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Wandering));
            Assert.That(targetKnowledge.SearchTimeRemaining, Is.EqualTo(targetKnowledge.SearchDuration));
        }

        // AC-004: reporting arrival while not searching is a no-op, so movement cannot force
        // a spurious wander transition outside the search state.
        [Test]
        public void ReportArrivedAtLastKnownPosition_WhileIdle_DoesNotChangeState()
        {
            targetKnowledge.ReportArrivedAtLastKnownPosition();

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
        }

        // AC-004, VAL-001: before the bounded interval elapses, the enemy remains in the
        // wander/search state with its target identity retained.
        [Test]
        public void UpdateTargetKnowledge_WhileWanderingBeforeDurationElapses_StaysWandering()
        {
            EnterSearchingState();
            targetKnowledge.ReportArrivedAtLastKnownPosition();

            targetKnowledge.UpdateTargetKnowledge(targetKnowledge.SearchDuration * 0.5f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Wandering));
            Assert.That(targetKnowledge.HasTarget, Is.True);
        }

        // AC-004, VAL-001: the wizard re-entering Detection Distance during the wander/search
        // state reacquires it and restores active pursuit.
        [Test]
        public void UpdateTargetKnowledge_WizardReentersDetectionDistanceWhileWandering_ReacquiresAndReturnsToPursuing()
        {
            EnterSearchingState();
            targetKnowledge.ReportArrivedAtLastKnownPosition();
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Wandering));

            wizardTransform.position = new Vector3(3f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0.1f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(targetKnowledge.CurrentTarget, Is.EqualTo(wizardTransform));
        }

        // AC-003/AC-004: re-entering Detection Distance while still heading toward the last
        // known position (before arrival is reported) also reacquires and returns to
        // pursuit, matching the GDD's combined search/wander reacquisition rule.
        [Test]
        public void UpdateTargetKnowledge_WizardReentersDetectionDistanceWhileSearchingBeforeArrival_ReacquiresAndReturnsToPursuing()
        {
            EnterSearchingState();
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));

            wizardTransform.position = new Vector3(2f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0.1f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
        }

        // AC-005, VAL-001: the bounded wander/search interval completing without
        // reacquisition clears the current target and returns to idle.
        [Test]
        public void UpdateTargetKnowledge_WanderingDurationFullyElapsesWithoutReacquisition_ClearsTargetAndReturnsToIdle()
        {
            EnterSearchingState();
            targetKnowledge.ReportArrivedAtLastKnownPosition();

            targetKnowledge.UpdateTargetKnowledge(targetKnowledge.SearchDuration + 1f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(targetKnowledge.HasTarget, Is.False);
            Assert.That(targetKnowledge.CurrentTarget, Is.Null);
        }

        // AC-005, VAL-001: the wander/search interval is bounded on its own and still
        // expires and clears the target even if the wired wizard Transform is destroyed or
        // unbound mid-search, so a lost reference cannot pin the enemy in Wandering forever.
        [Test]
        public void UpdateTargetKnowledge_WizardDestroyedWhileWandering_StillExpiresAndClearsTarget()
        {
            EnterSearchingState();
            targetKnowledge.ReportArrivedAtLastKnownPosition();
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Wandering));

            UnityEngine.Object.DestroyImmediate(wizardObject);
            wizardObject = null;

            targetKnowledge.UpdateTargetKnowledge(targetKnowledge.SearchDuration + 1f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(targetKnowledge.HasTarget, Is.False);
            Assert.That(targetKnowledge.CurrentTarget, Is.Null);
        }

        // AC-005, VAL-001: losing the target does not despawn, disable, or replace the
        // persistent enemy GameObject, and it can be encountered again afterward.
        [Test]
        public void FullTargetLossAndExpiryCycle_DoesNotDestroyOrReplaceEnemyGameObject_AndAllowsReacquisitionLater()
        {
            var originalInstanceId = enemyObject.GetInstanceID();

            EnterSearchingState();
            targetKnowledge.ReportArrivedAtLastKnownPosition();
            targetKnowledge.UpdateTargetKnowledge(targetKnowledge.SearchDuration + 1f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(enemyObject, Is.Not.Null);
            Assert.That(enemyObject.GetInstanceID(), Is.EqualTo(originalInstanceId));
            Assert.That(enemyObject.activeInHierarchy, Is.True);
            Assert.That(targetKnowledge.gameObject, Is.SameAs(enemyObject));

            wizardTransform.position = new Vector3(4f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
        }

        // AC-006, VAL-001: reset clears an acquired target and returns to idle.
        [Test]
        public void ResetTargetKnowledge_WhilePursuing_ClearsTargetAndReturnsToIdle()
        {
            wizardTransform.position = new Vector3(4f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));

            targetKnowledge.ResetTargetKnowledge();

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(targetKnowledge.HasTarget, Is.False);
            Assert.That(targetKnowledge.CurrentTarget, Is.Null);
        }

        // AC-006, VAL-001: reset clears the last known position and the running search
        // timer, not merely the current target reference.
        [Test]
        public void ResetTargetKnowledge_WhileWandering_ClearsLastKnownPositionAndSearchTimer()
        {
            EnterSearchingState();
            targetKnowledge.ReportArrivedAtLastKnownPosition();
            targetKnowledge.UpdateTargetKnowledge(0.5f);
            Assert.That(targetKnowledge.SearchTimeRemaining, Is.GreaterThan(0f));

            targetKnowledge.ResetTargetKnowledge();

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(targetKnowledge.LastKnownPosition, Is.EqualTo(Vector3.zero));
            Assert.That(targetKnowledge.SearchTimeRemaining, Is.EqualTo(0f));
            Assert.That(enemyObject, Is.Not.Null);
        }

        // AC-006, VAL-001: after reset, the same persistent enemy can acquire the wizard
        // again through the normal Detection Distance rule, matching floor-restart reuse.
        [Test]
        public void ResetTargetKnowledge_ThenWizardReentersDetectionDistance_CanAcquireAgain()
        {
            wizardTransform.position = new Vector3(4f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);
            targetKnowledge.ResetTargetKnowledge();

            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
        }

        // Defensive: without a wired wizard, per-tick evaluation must not throw and must
        // leave the enemy idle.
        [Test]
        public void UpdateTargetKnowledge_WithoutWizardWired_DoesNotThrowAndStaysIdle()
        {
            var unwiredObject = new GameObject("UnwiredEnemy");
            try
            {
                var unwiredTargetKnowledge = unwiredObject.AddComponent<EnemyTargetKnowledge>();

                Assert.DoesNotThrow(() => unwiredTargetKnowledge.UpdateTargetKnowledge(1f));
                Assert.That(unwiredTargetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(unwiredObject);
            }
        }
    }
}
