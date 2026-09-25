using NoSafeCircle.DoorPrototype;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public class SpectralDecoyEnemyTargetKnowledgePlayModeTests
    {
        private GameObject enemyObject;
        private EnemyTargetKnowledge targetKnowledge;
        private GameObject wizardObject;
        private Transform wizardTransform;
        private GameObject decoyObject;
        private Transform decoyTransform;

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

            // Test-owned decoy Transform, deliberately without a SpectralDecoy component:
            // EnemyTargetKnowledge's redirect API only ever needs a Transform.
            decoyObject = new GameObject("TestDecoy");
            decoyTransform = decoyObject.transform;
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

            if (decoyObject != null)
            {
                UnityEngine.Object.DestroyImmediate(decoyObject);
            }
        }

        private void AcquirePursuit(Vector3 wizardPosition)
        {
            wizardTransform.position = wizardPosition;
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            Assert.That(targetKnowledge.CurrentTarget, Is.EqualTo(wizardTransform));
        }

        private void EnterSearchingState()
        {
            wizardTransform.position = new Vector3(4f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            wizardTransform.position = new Vector3(11f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);
        }

        // AC-002, VAL-001 (case 1): a Pursuing enemy targeting the exact wizard, still inside
        // Detection Distance, redirects on success.
        [Test]
        public void TryRedirectToSpectralDecoy_WhilePursuingWizardInsideDetectionDistance_ReturnsTrueAndRedirects()
        {
            AcquirePursuit(new Vector3(4f, 0f, 0f));

            var result = targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform);

            Assert.That(result, Is.True);
            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.True);
            Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(decoyTransform));
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
        }

        // AC-002, VAL-001 (case 1): there is no separate decoy attraction radius, so an enemy
        // outside Detection Distance but still inside Lose Target Distance is eligible.
        [Test]
        public void TryRedirectToSpectralDecoy_WhilePursuingWizardOutsideDetectionButInsideLoseTargetDistance_ReturnsTrueAndRedirects()
        {
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            wizardTransform.position = new Vector3(8f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));

            var result = targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform);

            Assert.That(result, Is.True);
            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.True);
            Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(decoyTransform));
        }

        // AC-002, VAL-001 (case 2): an Idle enemy does not switch.
        [Test]
        public void TryRedirectToSpectralDecoy_WhileIdle_ReturnsFalse()
        {
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));

            var result = targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform);

            Assert.That(result, Is.False);
            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
        }

        // AC-002, VAL-001 (case 2): an enemy in SearchingLastKnownPosition does not switch.
        [Test]
        public void TryRedirectToSpectralDecoy_WhileSearchingLastKnownPosition_ReturnsFalse()
        {
            EnterSearchingState();
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));

            var result = targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform);

            Assert.That(result, Is.False);
            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
        }

        // AC-002, VAL-001 (case 2): a Wandering enemy does not switch.
        [Test]
        public void TryRedirectToSpectralDecoy_WhileWandering_ReturnsFalse()
        {
            EnterSearchingState();
            targetKnowledge.ReportArrivedAtLastKnownPosition();
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Wandering));

            var result = targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform);

            Assert.That(result, Is.False);
            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
        }

        // AC-002, VAL-001 (case 2): a defeated enemy (EnemyHealth.IsDefeated true) does not switch.
        [Test]
        public void TryRedirectToSpectralDecoy_EnemyDefeated_ReturnsFalse()
        {
            var enemyHealth = enemyObject.AddComponent<EnemyHealth>();
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            enemyHealth.TakeDamage(enemyHealth.MaxHealth);
            Assert.That(enemyHealth.IsDefeated, Is.True);

            var result = targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform);

            Assert.That(result, Is.False);
            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
        }

        // AC-002, VAL-001 (case 2): a disabled component does not switch.
        [Test]
        public void TryRedirectToSpectralDecoy_ComponentDisabled_ReturnsFalse()
        {
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            targetKnowledge.enabled = false;

            var result = targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform);

            Assert.That(result, Is.False);
            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
        }

        // AC-002, VAL-001 (case 2): an already-redirected enemy does not switch again, and the
        // first decoy remains the current target.
        [Test]
        public void TryRedirectToSpectralDecoy_AlreadyRedirected_ReturnsFalse()
        {
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            Assert.That(targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform), Is.True);

            var secondDecoyObject = new GameObject("SecondDecoy");
            try
            {
                var result = targetKnowledge.TryRedirectToSpectralDecoy(secondDecoyObject.transform);

                Assert.That(result, Is.False);
                Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(decoyTransform));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(secondDecoyObject);
            }
        }

        // AC-002, VAL-001 (case 2): an enemy whose CurrentTarget is not the exact initialized
        // wizard Transform does not switch, even while Pursuing.
        [Test]
        public void TryRedirectToSpectralDecoy_CurrentTargetNotInitializedWizard_ReturnsFalse()
        {
            AcquirePursuit(new Vector3(4f, 0f, 0f));

            var otherWizardObject = new GameObject("OtherWizard");
            try
            {
                targetKnowledge.Initialize(otherWizardObject.transform);
                Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
                Assert.That(targetKnowledge.CurrentTarget, Is.Not.SameAs(otherWizardObject.transform));

                var result = targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform);

                Assert.That(result, Is.False);
                Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(otherWizardObject);
            }
        }

        // AC-002: the Transform passed in must be non-null.
        [Test]
        public void TryRedirectToSpectralDecoy_NullDecoy_ReturnsFalse()
        {
            AcquirePursuit(new Vector3(4f, 0f, 0f));

            var result = targetKnowledge.TryRedirectToSpectralDecoy(null);

            Assert.That(result, Is.False);
            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
            Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(wizardTransform));
        }

        // AC-003, VAL-001 (case 3): the existing maximum-pursuit-distance-from-start leash stays
        // active while redirected. Exceeding it clears the redirect record, restores the wizard
        // as CurrentTarget, and searches the enemy's own start position.
        [Test]
        public void UpdateTargetKnowledge_RedirectedEnemyBeyondLeash_ClearsRedirectRestoresWizardAndSearchesStartPosition()
        {
            targetKnowledge.SetMaximumPursuitDistanceFromStart(6f);
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            Assert.That(targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform), Is.True);

            enemyObject.transform.position = new Vector3(7f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);

            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
            Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(wizardTransform));
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
            Assert.That(targetKnowledge.LastKnownPosition, Is.EqualTo(Vector3.zero));
        }

        // AC-003, VAL-001 (case 3): once the leash has already cleared the redirect record, a
        // later EndSpectralDecoyRedirect call for the former decoy must not overwrite the
        // search state the leash just established.
        [Test]
        public void EndSpectralDecoyRedirect_AfterLeashClearedRedirect_DoesNotOverwriteSearchState()
        {
            targetKnowledge.SetMaximumPursuitDistanceFromStart(6f);
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            Assert.That(targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform), Is.True);

            enemyObject.transform.position = new Vector3(7f, 0f, 0f);
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));

            targetKnowledge.EndSpectralDecoyRedirect(decoyTransform);

            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
            Assert.That(targetKnowledge.LastKnownPosition, Is.EqualTo(Vector3.zero));
            Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(wizardTransform));
        }

        // AC-003, VAL-001 (case 4): requiresLineOfSight still gates fresh acquisition.
        [Test]
        public void UpdateTargetKnowledge_RequiresLineOfSightBlocksFreshAcquisition()
        {
            targetKnowledge.SetRequiresLineOfSight(true);
            var occluder = new GameObject("Occluder");
            try
            {
                occluder.transform.position = new Vector3(2f, 1f, 0f);
                occluder.AddComponent<BoxCollider>();

                wizardTransform.position = new Vector3(4f, 0f, 0f);
                targetKnowledge.UpdateTargetKnowledge(0f);

                Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(occluder);
            }
        }

        // AC-003, VAL-001 (case 4): requiresLineOfSight is never consulted to keep an active
        // redirect, even once the real wizard's line of sight becomes blocked afterward.
        [Test]
        public void UpdateTargetKnowledge_RequiresLineOfSightDoesNotClearActiveRedirect()
        {
            targetKnowledge.SetRequiresLineOfSight(true);
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            Assert.That(targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform), Is.True);

            var occluder = new GameObject("Occluder");
            try
            {
                occluder.transform.position = new Vector3(2f, 1f, 0f);
                occluder.AddComponent<BoxCollider>();

                targetKnowledge.UpdateTargetKnowledge(0f);
                targetKnowledge.UpdateTargetKnowledge(0f);

                Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.True);
                Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(decoyTransform));
                Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(occluder);
            }
        }

        // AC-004, VAL-001 (case 5): a Transform that is not the exact current decoy changes no
        // target-knowledge state.
        [Test]
        public void EndSpectralDecoyRedirect_WithTransformThatIsNotCurrentDecoy_ChangesNothing()
        {
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            Assert.That(targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform), Is.True);

            var otherObject = new GameObject("NotTheDecoy");
            try
            {
                targetKnowledge.EndSpectralDecoyRedirect(otherObject.transform);

                Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.True);
                Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(decoyTransform));
                Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(otherObject);
            }
        }

        // AC-004, VAL-002: ending a redirect with the wizard exactly at Lose Target Distance
        // restores the wizard immediately and keeps Pursuing, with no line-of-sight check even
        // when requiresLineOfSight is enabled and the real line of sight is blocked.
        [Test]
        public void EndSpectralDecoyRedirect_WizardExactlyAtLoseTargetDistance_RestoresWizardAndStaysPursuing()
        {
            targetKnowledge.SetRequiresLineOfSight(true);
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            Assert.That(targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform), Is.True);

            wizardTransform.position = new Vector3(10f, 0f, 0f);

            var occluder = new GameObject("Occluder");
            try
            {
                occluder.transform.position = new Vector3(5f, 1f, 0f);
                occluder.AddComponent<BoxCollider>();

                targetKnowledge.EndSpectralDecoyRedirect(decoyTransform);

                Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
                Assert.That(targetKnowledge.CurrentTarget, Is.SameAs(wizardTransform));
                Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Pursuing));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(occluder);
            }
        }

        // AC-003/AC-004, VAL-002: ending a redirect with the wizard just beyond Lose Target
        // Distance enters SearchingLastKnownPosition, using the wizard position saved at the
        // moment the redirect began rather than the wizard's current position.
        [Test]
        public void EndSpectralDecoyRedirect_WizardJustBeyondLoseTargetDistance_EntersSearchingAtSavedWizardPosition()
        {
            var wizardPositionAtRedirect = new Vector3(4f, 0f, 0f);
            AcquirePursuit(wizardPositionAtRedirect);
            Assert.That(targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform), Is.True);

            wizardTransform.position = new Vector3(11f, 0f, 0f);

            targetKnowledge.EndSpectralDecoyRedirect(decoyTransform);

            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
            Assert.That(targetKnowledge.LastKnownPosition, Is.EqualTo(wizardPositionAtRedirect));
        }

        // AC-004, VAL-002: destroying the wizard before a redirect ends must not throw, and the
        // enemy still enters SearchingLastKnownPosition at the saved position.
        [Test]
        public void EndSpectralDecoyRedirect_WizardDestroyed_DoesNotThrowAndEntersSearchingAtSavedPosition()
        {
            var wizardPositionAtRedirect = new Vector3(4f, 0f, 0f);
            AcquirePursuit(wizardPositionAtRedirect);
            Assert.That(targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform), Is.True);

            UnityEngine.Object.DestroyImmediate(wizardObject);
            wizardObject = null;

            Assert.DoesNotThrow(() => targetKnowledge.EndSpectralDecoyRedirect(decoyTransform));

            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.SearchingLastKnownPosition));
            Assert.That(targetKnowledge.LastKnownPosition, Is.EqualTo(wizardPositionAtRedirect));
        }

        // AC-003, VAL-002: ResetTargetKnowledge() during a redirect clears
        // IsRedirectedToSpectralDecoy and returns the enemy to floor-initial Idle state.
        [Test]
        public void ResetTargetKnowledge_WhileRedirected_ClearsRedirectFlagAndReturnsToIdle()
        {
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            Assert.That(targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform), Is.True);

            targetKnowledge.ResetTargetKnowledge();

            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(targetKnowledge.HasTarget, Is.False);
            Assert.That(targetKnowledge.CurrentTarget, Is.Null);
        }

        // AC-003, VAL-002: after a reset during a redirect, the decoy reference is also
        // cleared, so a later end call for the former decoy is a no-op rather than reviving it.
        [Test]
        public void EndSpectralDecoyRedirect_AfterResetDuringRedirect_WithFormerDecoy_DoesNothing()
        {
            AcquirePursuit(new Vector3(4f, 0f, 0f));
            Assert.That(targetKnowledge.TryRedirectToSpectralDecoy(decoyTransform), Is.True);
            targetKnowledge.ResetTargetKnowledge();

            targetKnowledge.EndSpectralDecoyRedirect(decoyTransform);

            Assert.That(targetKnowledge.IsRedirectedToSpectralDecoy, Is.False);
            Assert.That(targetKnowledge.State, Is.EqualTo(EnemyTargetKnowledgeState.Idle));
            Assert.That(targetKnowledge.CurrentTarget, Is.Null);
        }
    }
}
