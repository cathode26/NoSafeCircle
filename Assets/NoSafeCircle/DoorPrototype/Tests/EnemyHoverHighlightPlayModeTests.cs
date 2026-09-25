using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Pointer-driven coverage for EnemyHoverHighlight (VAL-001), mirroring
    // DoorInteractionFeedbackHoverPlayModeTests' real-camera/real-InputSystem pattern: every
    // assertion is reached by actually moving the mouse and re-deriving PlayerMovement's shared
    // PointerWorldTarget through its own real screen-to-world projection, never by setting a
    // hover flag directly. EnemyHoverHighlight resolves "at most one highlighted" against a
    // static registry of every enabled instance (see IsClosestHoveredEnemy in production code),
    // so instances are kept enabled here rather than disabled-and-manually-ticked: disabling
    // would remove them from that registry and silently defeat the single-highlight rule under
    // test. Tick() itself is a stateless per-call recompute, so the automatic Update() this
    // enables alongside each manual Tick() call is idempotent and does not double-apply anything.
    public class EnemyHoverHighlightPlayModeTests : InputTestFixture
    {
        private Mouse mouseDevice;
        private GameObject cameraObject;
        private Camera testCamera;
        private RenderTexture testRenderTexture;
        private InputActionAsset inputActionsAsset;

        private GameObject playerObject;
        private PlayerMovement movement;

        private readonly List<GameObject> spawnedObjects = new List<GameObject>();

        public override void Setup()
        {
            base.Setup();
            mouseDevice = InputSystem.AddDevice<Mouse>();

            cameraObject = new GameObject("TestMainCamera");
            cameraObject.tag = "MainCamera";
            testCamera = cameraObject.AddComponent<Camera>();
            testCamera.orthographic = true;
            testCamera.orthographicSize = 20f;
            cameraObject.transform.SetPositionAndRotation(new Vector3(0f, 10f, 0f), Quaternion.Euler(90f, 0f, 0f));

            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
            testCamera.targetTexture = testRenderTexture;

            playerObject = new GameObject("TestPlayer");
            playerObject.SetActive(false);
            playerObject.transform.position = new Vector3(0f, 1f, 0f);
            playerObject.AddComponent<CharacterController>();
            movement = playerObject.AddComponent<PlayerMovement>();
            inputActionsAsset = BuildInputActionsAsset();
            SetPrivateField(movement, "inputActions", inputActionsAsset);
            playerObject.SetActive(true);
        }

        public override void TearDown()
        {
            // DestroyImmediate (rather than Destroy) so EnemyHoverHighlight.OnDisable runs
            // synchronously and removes each instance from its static activeHighlights registry
            // before the next test's SetUp, per the testing policy's "leave no static or global
            // state behind" isolation rule.
            foreach (var spawned in spawnedObjects)
            {
                if (spawned != null) Object.DestroyImmediate(spawned);
            }
            spawnedObjects.Clear();

            if (playerObject != null) Object.DestroyImmediate(playerObject);
            if (cameraObject != null) Object.DestroyImmediate(cameraObject);
            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                Object.DestroyImmediate(testRenderTexture);
                testRenderTexture = null;
            }
            if (inputActionsAsset != null) Object.DestroyImmediate(inputActionsAsset);

            mouseDevice = null;
            base.TearDown();
        }

        // VAL-001/AC-001: the enemy under the cursor becomes highlighted, and the same enemy
        // away from the cursor does not.
        [UnityTest]
        public IEnumerator Highlighted_WhenPointerOverEnemy_AndNotWhenPointerAway()
        {
            var enemyObject = CreateEnemy(new Vector3(3f, 0f, 3f), true, out var highlight, out _);

            var overEnemy = testCamera.WorldToScreenPoint(enemyObject.transform.position);
            SetMouse(overEnemy, false);
            movement.Tick(0.02f);
            highlight.Tick();
            yield return null;

            Assert.IsTrue(movement.HasPointerWorldTarget,
                "Test setup must actually produce a shared pointer world target via the real camera projection.");
            Assert.IsTrue(highlight.IsHighlighted,
                "VAL-001/AC-001: the enemy under the cursor must become highlighted.");

            var farAway = testCamera.WorldToScreenPoint(enemyObject.transform.position + new Vector3(30f, 0f, 30f));
            SetMouse(farAway, false);
            movement.Tick(0.02f);
            highlight.Tick();
            yield return null;

            Assert.IsFalse(highlight.IsHighlighted,
                "VAL-001/AC-001: the same enemy away from the cursor must not remain highlighted.");
        }

        // VAL-001/AC-001: with two enemies present and the cursor over one, at most one enemy is
        // highlighted at a time.
        [UnityTest]
        public IEnumerator AtMostOneHighlighted_WithTwoEnemiesPresent_CursorOverOnlyOne()
        {
            var enemyA = CreateEnemy(new Vector3(2f, 0f, 2f), true, out var highlightA, out _);
            var enemyB = CreateEnemy(new Vector3(9f, 0f, 9f), true, out var highlightB, out _);

            var overA = testCamera.WorldToScreenPoint(enemyA.transform.position);
            SetMouse(overA, false);
            movement.Tick(0.02f);
            highlightA.Tick();
            highlightB.Tick();
            yield return null;

            Assert.IsTrue(highlightA.IsHighlighted,
                "VAL-001/AC-001: the enemy under the cursor must be highlighted.");
            Assert.IsFalse(highlightB.IsHighlighted,
                "VAL-001/AC-001: at most one enemy may be highlighted at a time, even with two present.");
        }

        // VAL-001/AC-001: moving the cursor off every enemy clears the highlight.
        [UnityTest]
        public IEnumerator MovingCursorOffEveryEnemy_ClearsHighlightForAll()
        {
            var enemyA = CreateEnemy(new Vector3(2f, 0f, 2f), true, out var highlightA, out _);
            var enemyB = CreateEnemy(new Vector3(9f, 0f, 9f), true, out var highlightB, out _);

            var overA = testCamera.WorldToScreenPoint(enemyA.transform.position);
            SetMouse(overA, false);
            movement.Tick(0.02f);
            highlightA.Tick();
            highlightB.Tick();
            yield return null;
            Assert.IsTrue(highlightA.IsHighlighted, "Test setup must actually hover enemy A first.");

            var offBoth = testCamera.WorldToScreenPoint(new Vector3(60f, 0f, 60f));
            SetMouse(offBoth, false);
            movement.Tick(0.02f);
            highlightA.Tick();
            highlightB.Tick();
            yield return null;

            Assert.IsFalse(highlightA.IsHighlighted,
                "VAL-001/AC-001: moving the cursor off every enemy must clear the highlight.");
            Assert.IsFalse(highlightB.IsHighlighted,
                "VAL-001/AC-001: moving the cursor off every enemy must clear the highlight.");
        }

        // VAL-001/AC-003: an enemy carrying NSC-114's EnemyAwarenessIndicator still reports that
        // indicator's own detected state while highlighted - neither component suppresses the
        // other. EnemyAwarenessIndicator.cs is read-only here and driven only through its own
        // unmodified Update(), never written to directly.
        [UnityTest]
        public IEnumerator HighlightedEnemy_WithAwarenessIndicatorDetecting_ReportsBothStatesTogether()
        {
            var enemyObject = CreateEnemy(new Vector3(3f, 0f, 3f), true, out var highlight, out _);

            var targetKnowledge = enemyObject.AddComponent<EnemyTargetKnowledge>();
            targetKnowledge.Initialize(playerObject.transform);
            targetKnowledge.ConfigureDistances(50f, 60f);
            targetKnowledge.UpdateTargetKnowledge(0f);
            Assert.AreEqual(EnemyTargetKnowledgeState.Pursuing, targetKnowledge.State,
                "Test setup must actually put the enemy into NSC-114's detected/pursuing state.");

            var indicatorVisual = new GameObject("TestIndicatorVisual");
            indicatorVisual.transform.SetParent(enemyObject.transform, false);
            var indicatorRenderer = indicatorVisual.AddComponent<SpriteRenderer>();

            var indicator = enemyObject.AddComponent<EnemyAwarenessIndicator>();
            SetPrivateField(indicator, "targetKnowledge", targetKnowledge);
            SetPrivateField(indicator, "indicatorRenderer", indicatorRenderer);
            SetPrivateField(indicator, "detectedIcon", CreateDummySprite());

            var overEnemy = testCamera.WorldToScreenPoint(enemyObject.transform.position);
            SetMouse(overEnemy, false);
            movement.Tick(0.02f);
            highlight.Tick();
            yield return null;

            Assert.IsTrue(highlight.IsHighlighted, "Test setup must actually hover the enemy.");
            Assert.IsTrue(indicator.IsDetected,
                "AC-003: NSC-114's awareness indicator must still report its own detected state while this " +
                "enemy is highlighted; neither component may suppress or obscure the other.");
        }

        // VAL-001/AC-005: enemy position, health, and pursuit state are identical to a run in
        // which the highlight is suppressed (no EnemyHoverHighlight component at all), proving the
        // highlight is purely observational and changes no gameplay state. The comparison is
        // between two measured runs, not against hard-coded expected values.
        [UnityTest]
        public IEnumerator SuppressingHighlight_DoesNotChangeEnemyPositionHealthOrPursuitState()
        {
            var activeEnemy = CreateEnemy(new Vector3(4f, 0f, 4f), true, out var highlight, out var activeHealth);
            var suppressedEnemy = CreateEnemy(new Vector3(4f, 0f, 4f), false, out _, out var suppressedHealth);

            var activeKnowledge = activeEnemy.AddComponent<EnemyTargetKnowledge>();
            activeKnowledge.Initialize(playerObject.transform);
            activeKnowledge.ConfigureDistances(50f, 60f);

            var suppressedKnowledge = suppressedEnemy.AddComponent<EnemyTargetKnowledge>();
            suppressedKnowledge.Initialize(playerObject.transform);
            suppressedKnowledge.ConfigureDistances(50f, 60f);

            var overActiveEnemy = testCamera.WorldToScreenPoint(activeEnemy.transform.position);
            SetMouse(overActiveEnemy, false);
            movement.Tick(0.02f);
            highlight.Tick();
            activeKnowledge.UpdateTargetKnowledge(0.02f);
            suppressedKnowledge.UpdateTargetKnowledge(0.02f);
            activeHealth.TakeDamage(15f);
            suppressedHealth.TakeDamage(15f);
            yield return null;

            Assert.IsTrue(highlight.IsHighlighted,
                "Test setup must actually engage the highlight on the active-run enemy.");

            Assert.AreEqual(suppressedEnemy.transform.position, activeEnemy.transform.position,
                "AC-005: the highlight must not move the enemy relative to a run where it is suppressed.");
            Assert.AreEqual(suppressedHealth.CurrentHealth, activeHealth.CurrentHealth,
                "AC-005: the highlight must not change enemy health relative to a run where it is suppressed.");
            Assert.AreEqual(suppressedKnowledge.State, activeKnowledge.State,
                "AC-005: the highlight must not change enemy pursuit state relative to a run where it is " +
                "suppressed.");
        }

        private GameObject CreateEnemy(
            Vector3 position, bool withHighlight, out EnemyHoverHighlight highlight, out EnemyHealth health)
        {
            var enemyObject = new GameObject("TestEnemy");
            enemyObject.transform.position = position;
            spawnedObjects.Add(enemyObject);

            var visual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            visual.transform.SetParent(enemyObject.transform, false);
            var renderer = visual.GetComponent<Renderer>();

            health = enemyObject.AddComponent<EnemyHealth>();

            if (withHighlight)
            {
                highlight = enemyObject.AddComponent<EnemyHoverHighlight>();
                SetPrivateField(highlight, "playerMovement", movement);
                SetPrivateField(highlight, "enemyHealth", health);
                SetPrivateField(highlight, "highlightRenderer", renderer);
            }
            else
            {
                highlight = null;
            }

            return enemyObject;
        }

        private static Sprite CreateDummySprite()
        {
            var texture = new Texture2D(1, 1);
            return Sprite.Create(texture, new Rect(0f, 0f, 1f, 1f), new Vector2(0.5f, 0.5f));
        }

        private static InputActionAsset BuildInputActionsAsset()
        {
            var asset = ScriptableObject.CreateInstance<InputActionAsset>();
            var playerMap = asset.AddActionMap("Player");
            playerMap.AddAction("PointerPosition", InputActionType.Value, binding: "<Mouse>/position");
            playerMap.AddAction("MoveToCursor", InputActionType.Button, binding: "<Mouse>/leftButton");
            return asset;
        }

        private void SetMouse(Vector2 screenPosition, bool leftButtonPressed)
        {
            InputSystem.QueueStateEvent(mouseDevice, new MouseState
            {
                position = screenPosition,
                buttons = leftButtonPressed ? (ushort)(1 << (int)MouseButton.Left) : (ushort)0
            });
            InputSystem.Update();
        }

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }
    }
}
