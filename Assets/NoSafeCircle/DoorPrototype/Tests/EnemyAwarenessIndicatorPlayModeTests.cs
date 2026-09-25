using System.Collections;
using System.Reflection;
using System.Text.RegularExpressions;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-114 VAL-001: drives NSC-091's real EnemyTargetKnowledge.UpdateTargetKnowledge path -
    // the same public entry point EnemyPursuitMovement calls - rather than setting detection
    // state through reflection. Reflection here is only used to wire this presenter's own
    // inspector-only SpriteRenderer/Sprite serialized fields, matching the SetPrivateField
    // convention already used by DoorBreachFeedbackPlayModeTests for the same purpose.
    public sealed class EnemyAwarenessIndicatorPlayModeTests
    {
        private const float DetectionDistance = 5f;
        private const float LoseTargetDistance = 10f;

        private static readonly Vector3 WizardNearPoint = new Vector3(4f, 0f, 0f);
        private static readonly Vector3 WizardFarPoint = new Vector3(11f, 0f, 0f);

        private GameObject enemyObject;
        private GameObject wizardObject;
        private Transform wizardTransform;
        private EnemyTargetKnowledge targetKnowledge;
        private SpriteRenderer indicatorRenderer;
        private EnemyAwarenessIndicator indicator;
        private Texture2D placeholderTexture;
        private Sprite placeholderSprite;

        [SetUp]
        public void SetUp()
        {
            enemyObject = new GameObject("TestEnemy");
            targetKnowledge = enemyObject.AddComponent<EnemyTargetKnowledge>();

            wizardObject = new GameObject("TestWizard");
            wizardTransform = wizardObject.transform;
            targetKnowledge.Initialize(wizardTransform);
            targetKnowledge.ConfigureDistances(DetectionDistance, LoseTargetDistance);

            var visualObject = new GameObject("IndicatorVisual");
            visualObject.transform.SetParent(enemyObject.transform, false);
            indicatorRenderer = visualObject.AddComponent<SpriteRenderer>();

            placeholderTexture = new Texture2D(1, 1);
            placeholderSprite = Sprite.Create(
                placeholderTexture, new Rect(0f, 0f, 1f, 1f), new Vector2(0.5f, 0.5f));

            // EnemyTargetKnowledge is already present on enemyObject, so Awake's
            // GetComponent<EnemyTargetKnowledge>() fallback wires it through the component's own
            // production auto-wire path rather than reflection.
            indicator = enemyObject.AddComponent<EnemyAwarenessIndicator>();
            SetPrivateField(indicator, "indicatorRenderer", indicatorRenderer);
        }

        [TearDown]
        public void TearDown()
        {
            if (enemyObject != null) Object.DestroyImmediate(enemyObject);
            if (wizardObject != null) Object.DestroyImmediate(wizardObject);
            if (placeholderSprite != null) Object.DestroyImmediate(placeholderSprite);
            if (placeholderTexture != null) Object.DestroyImmediate(placeholderTexture);
        }

        // AC-001/AC-002/AC-003, VAL-001: driving the wizard into Detection Distance through the
        // real EnemyTargetKnowledge path makes the indicator reflect the detected condition
        // within one Update tick, rendering the bound placeholder sprite it was given.
        [UnityTest]
        public IEnumerator WizardEntersDetectionDistance_IndicatorReflectsDetectedWithinOneUpdate()
        {
            SetPrivateField(indicator, "detectedIcon", placeholderSprite);
            yield return null;
            Assert.IsFalse(indicator.IsDetected, "Expected the indicator to start undetected.");
            Assert.IsFalse(indicatorRenderer.enabled, "Expected no detected icon before acquisition.");

            wizardTransform.position = WizardNearPoint;
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.AreEqual(EnemyTargetKnowledgeState.Pursuing, targetKnowledge.State);

            yield return null;

            Assert.IsTrue(indicator.IsDetected,
                "Expected the indicator to reflect detection within one Update tick.");
            Assert.IsTrue(indicatorRenderer.enabled);
            Assert.AreEqual(placeholderSprite, indicatorRenderer.sprite);
            Assert.AreEqual(Color.white, indicatorRenderer.color);
        }

        // AC-002, VAL-001: the enemy losing the wizard (Pursuing -> SearchingLastKnownPosition)
        // reverts the indicator to undetected within one Update tick, even though
        // EnemyTargetKnowledge.HasTarget stays true during the search phase. A one-way indicator
        // that latches on HasTarget instead of active pursuit would fail this.
        [UnityTest]
        public IEnumerator EnemyLosesWizardWhilePursuing_IndicatorRevertsToUndetectedWithinOneUpdate()
        {
            SetPrivateField(indicator, "detectedIcon", placeholderSprite);
            wizardTransform.position = WizardNearPoint;
            targetKnowledge.UpdateTargetKnowledge(0f);
            yield return null;
            Assert.IsTrue(indicator.IsDetected, "Test setup did not reach the detected condition.");

            wizardTransform.position = WizardFarPoint;
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.AreEqual(EnemyTargetKnowledgeState.SearchingLastKnownPosition, targetKnowledge.State);
            Assert.IsTrue(targetKnowledge.HasTarget,
                "Test setup must keep HasTarget true during search to prove the indicator isn't " +
                "reading HasTarget instead of active pursuit.");

            yield return null;

            Assert.IsFalse(indicator.IsDetected,
                "Expected the indicator to revert to undetected within one Update tick instead of " +
                "latching on.");
            Assert.IsFalse(indicatorRenderer.enabled);
        }

        // AC-001, VAL-001: reading detection state to render it must never write back to
        // EnemyTargetKnowledge. State is captured immediately before and after the Update tick in
        // which the indicator renders, and must be unchanged.
        [UnityTest]
        public IEnumerator Update_RenderingDetectedState_NeverWritesEnemyTargetKnowledgeState()
        {
            SetPrivateField(indicator, "detectedIcon", placeholderSprite);
            wizardTransform.position = WizardNearPoint;
            targetKnowledge.UpdateTargetKnowledge(0f);

            EnemyTargetKnowledgeState stateBefore = targetKnowledge.State;
            bool hasTargetBefore = targetKnowledge.HasTarget;
            Transform currentTargetBefore = targetKnowledge.CurrentTarget;
            Vector3 lastKnownPositionBefore = targetKnowledge.LastKnownPosition;
            float searchTimeRemainingBefore = targetKnowledge.SearchTimeRemaining;

            yield return null;

            Assert.AreEqual(stateBefore, targetKnowledge.State,
                "The indicator must never advance or alter EnemyTargetKnowledge.State.");
            Assert.AreEqual(hasTargetBefore, targetKnowledge.HasTarget);
            Assert.AreEqual(currentTargetBefore, targetKnowledge.CurrentTarget);
            Assert.AreEqual(lastKnownPositionBefore, targetKnowledge.LastKnownPosition);
            Assert.AreEqual(searchTimeRemainingBefore, targetKnowledge.SearchTimeRemaining);
        }

        // AC-003, VAL-001: a missing detected-icon binding must fail visibly (a distinct
        // fallback marker plus a logged error) rather than silently rendering nothing, so a
        // missing art binding can never be mistaken for an enemy that has not noticed the wizard.
        [UnityTest]
        public IEnumerator DetectedWithNoIconBound_RendersVisibleFallbackAndLogsErrorInsteadOfNothing()
        {
            wizardTransform.position = WizardNearPoint;
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.AreEqual(EnemyTargetKnowledgeState.Pursuing, targetKnowledge.State);

            LogAssert.Expect(LogType.Error, new Regex("no detected-state icon is bound"));

            yield return null;

            Assert.IsTrue(indicator.IsDetected);
            Assert.IsTrue(indicatorRenderer.enabled,
                "A missing icon binding must still render visibly, not disable the renderer.");
            Assert.IsNotNull(indicatorRenderer.sprite,
                "A missing icon binding must render a fallback sprite, not a blank renderer.");
            Assert.AreEqual(Color.magenta, indicatorRenderer.color,
                "The fallback marker must be visually distinct from a normal bound-icon render.");
        }

        private static void SetPrivateField(object target, string name, object value)
        {
            target.GetType().GetField(name, BindingFlags.NonPublic | BindingFlags.Instance)
                .SetValue(target, value);
        }
    }
}
