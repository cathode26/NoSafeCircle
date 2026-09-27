using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using NoSafeCircle.DoorPrototype.Enemies;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class TitleScreenChaseBackdropPlayModeTests
    {
        private static readonly string[] WizardNames =
            { "Ember", "Ash", "Frost", "Dusk", "Ember", "Ash", "Frost", "Dusk", "Ember" };

        private static readonly string[] PursuerNames =
        {
            "DungeonBrute", "LanternWraith", "DungeonBrute", "LanternWraith",
            "LanternWraith", "DungeonBrute", "LanternWraith", "DungeonBrute",
            "DungeonBrute"
        };

        private static readonly ConfirmedWizardSelection[] OrderedWizards =
        {
            new ConfirmedWizardSelection(WizardPresentation.Masculine, WizardSkin.White),
            new ConfirmedWizardSelection(WizardPresentation.Masculine, WizardSkin.Black),
            new ConfirmedWizardSelection(WizardPresentation.Feminine, WizardSkin.White),
            new ConfirmedWizardSelection(WizardPresentation.Feminine, WizardSkin.Black)
        };

        private GameObject cameraObject;
        private GameObject titleObject;
        private GameObject titlePanel;
        private GameObject backdropObject;
        private GameObject registryObject;
        private Camera chaseCamera;
        private RenderTexture targetTexture;
        private TitleScreenController title;
        private TitleScreenChaseBackdrop backdrop;
        private ActiveEnemyRegistry registry;

        [SetUp]
        public void SetUp()
        {
            cameraObject = new GameObject("TitleChaseTestCamera", typeof(Camera));
            cameraObject.tag = "MainCamera";
            cameraObject.transform.position = new Vector3(0f, 10f, -13f);
            cameraObject.transform.rotation = Quaternion.Euler(45f, 0f, 0f);
            chaseCamera = cameraObject.GetComponent<Camera>();
            chaseCamera.orthographic = true;
            chaseCamera.orthographicSize = 8f;
            SetResolution(1920, 1080);

            titleObject = new GameObject("TitleChaseTestController");
            titleObject.SetActive(false);
            titlePanel = new GameObject("TitleScreen");
            titlePanel.transform.SetParent(titleObject.transform, false);
            title = titleObject.AddComponent<TitleScreenController>();
            SetPrivateField(title, "titlePanel", titlePanel);
            titleObject.SetActive(true);

            registryObject = new GameObject("TitleChaseTestRegistry");
            registry = registryObject.AddComponent<ActiveEnemyRegistry>();

            backdropObject = new GameObject("TitleChaseTestBackdrop");
            backdropObject.SetActive(false);
            backdrop = backdropObject.AddComponent<TitleScreenChaseBackdrop>();
            backdrop.AutomaticTick = false;
            backdrop.Configure(
                title,
                chaseCamera,
                ControllerFromPrefab("Player/Player"),
                ControllerFromPrefab("Enemies/MeleeEnemy"),
                ControllerFromPrefab("Enemies/LanternWraith"),
                OrderedWizards,
                new Vector3(-14f, 0f, -3f),
                new Vector3(14f, 0f, -3f));
            backdrop.ConfigureMotion(3f, 10f, 20f, 1.5f, 2.5f, 0.5f, 6f);
            // The shipped title uses unit scale for 128 px wizard art at 64 PPU.
            SetPrivateField(backdrop, "wizardVisualScale", 1f);
            SetPrivateField(backdrop, "pursuerVisualScale", 1f);
            backdropObject.SetActive(true);
            Assert.IsTrue(title.IsTitleScreenVisible);
        }

        [TearDown]
        public void TearDown()
        {
            if (backdropObject != null) UnityEngine.Object.DestroyImmediate(backdropObject);
            GameObject actors = GameObject.Find("TitleScreenChaseActors");
            if (actors != null) UnityEngine.Object.DestroyImmediate(actors);
            if (registryObject != null) UnityEngine.Object.DestroyImmediate(registryObject);
            if (titleObject != null) UnityEngine.Object.DestroyImmediate(titleObject);
            if (cameraObject != null) UnityEngine.Object.DestroyImmediate(cameraObject);
            if (targetTexture != null)
            {
                targetTexture.Release();
                UnityEngine.Object.DestroyImmediate(targetTexture);
            }
        }

        [Test]
        public void FirstPairingAndLaterIntervals_UseTheInjectedThreeTenAndTwentySecondBounds()
        {
            int intervalCalls = 0;
            backdrop.SetSelectors((minimum, maximum) =>
            {
                intervalCalls++;
                return intervalCalls == 1 ? maximum : minimum;
            }, () => true);

            backdrop.Tick(2.9f);
            Assert.AreEqual(0, backdrop.StartedPairingCount);
            backdrop.Tick(0.1f);
            Assert.AreEqual(1, backdrop.StartedPairingCount,
                "The first pairing may start at the three-second upper bound.");

            backdrop.Tick(9.9f);
            Assert.AreEqual(1, backdrop.StartedPairingCount);
            backdrop.Tick(0.101f);
            Assert.AreEqual(2, backdrop.StartedPairingCount,
                "The next pairing must wait at least ten seconds.");

            backdrop.ConfigureMotion(3f, 10f, 20f, 1.5f, 2.5f, 0.5f, 6f);
            intervalCalls = 0;
            backdrop.SetSelectors((minimum, maximum) =>
            {
                intervalCalls++;
                return intervalCalls == 1 ? maximum : maximum;
            }, () => false);
            backdrop.Tick(3f);
            backdrop.Tick(19.9f);
            Assert.AreEqual(1, backdrop.StartedPairingCount);
            backdrop.Tick(0.101f);
            Assert.AreEqual(2, backdrop.StartedPairingCount,
                "The injected twenty-second upper interval must be honored.");
        }

        [Test]
        public void NinePairings_CycleFourWizardIdentitiesAndBothPursuersFromBothEnds()
        {
            bool firstEndpoint = false;
            backdrop.SetSelectors((minimum, maximum) => minimum, () =>
            {
                firstEndpoint = !firstEndpoint;
                return firstEndpoint;
            });

            backdrop.Tick(0f);
            for (int index = 0; index < WizardNames.Length; index++)
            {
                Assert.AreEqual(index + 1, backdrop.StartedPairingCount);
                Assert.AreEqual(index + 1, backdrop.NextPairingIndex);
                GameObject wizard = GameObject.Find("TitleChaseWizard_" + WizardNames[index]);
                Assert.IsNotNull(wizard, "Missing wizard at pairing " + index);
                WizardAnimationController animation = wizard.GetComponent<WizardAnimationController>();
                Assert.IsNotNull(animation);
                Assert.AreEqual(OrderedWizards[index % 4].Presentation, animation.Presentation);
                Assert.AreEqual(OrderedWizards[index % 4].Skin, animation.Skin);
                Assert.AreEqual(1f, wizard.transform.Find("Visual").localScale.x, 0.001f,
                    "Title wizard art must read at the configured close-up scale.");
                Assert.AreEqual(index % 2 == 0 ? 0.55f : 0.9f,
                    chaseCamera.WorldToViewportPoint(wizard.transform.position).x,
                    0.001f, "Pairings must use alternating clipped lane endpoints.");
                AssertPresentationOnly(wizard);

                backdrop.Tick(2f);
                GameObject pursuer = GameObject.Find("TitleChasePursuer_" + PursuerNames[index]);
                Assert.IsNotNull(pursuer, "Missing pursuer at pairing " + index);
                EnemyAnimationController pursuerAnimation =
                    pursuer.GetComponent<EnemyAnimationController>();
                Assert.IsNotNull(pursuerAnimation);
                Assert.AreEqual(1f, pursuer.transform.Find("Visual").localScale.x, 0.001f,
                    "The pursuer should be as readable as the fleeing wizard.");
                Assert.That(pursuerAnimation.CurrentState,
                    Does.StartWith(PursuerNames[index] == "DungeonBrute"
                        ? "MeleeEnemy_walk_" : "LanternWraith_walk_"));
                AssertPresentationOnly(pursuer);
                Assert.AreEqual(0, registry.ActiveCount);

                if (index < WizardNames.Length - 1) backdrop.Tick(8f);
            }
        }

        [TestCase(1920, 1080)]
        [TestCase(1440, 1080)]
        public void Pairing_StaysOnClippedFloorLaneAndFadesAtBothEnds(int width, int height)
        {
            SetResolution(width, height);
            backdrop.SetSelectors((minimum, maximum) => minimum, () => true);
            backdrop.Tick(0f);

            GameObject wizard = GameObject.Find("TitleChaseWizard_Ember");
            Assert.IsNotNull(wizard);
            SpriteRenderer wizardRenderer = wizard.GetComponentInChildren<SpriteRenderer>();
            Assert.AreEqual(0f, wizardRenderer.color.a, 0.001f);
            AssertClippedPosition(wizard);

            backdrop.Tick(0.25f);
            Assert.AreEqual(0.5f, wizardRenderer.color.a, 0.02f);
            AssertClippedPosition(wizard);
            backdrop.Tick(0.25f);
            Assert.AreEqual(1f, wizardRenderer.color.a, 0.001f);

            const float pursuerDelay = 2.5f / 1.5f;
            backdrop.Tick(pursuerDelay - 0.5f);
            GameObject pursuer = GameObject.Find("TitleChasePursuer_DungeonBrute");
            Assert.IsNotNull(pursuer);
            Assert.AreEqual(0f,
                pursuer.GetComponentInChildren<SpriteRenderer>().color.a, 0.001f);
            Assert.AreEqual(2.5f,
                Vector3.Distance(wizard.transform.position, pursuer.transform.position), 0.002f,
                "The pursuer starts at the lane endpoint after a 2.5 / 1.5 second delay.");

            float laneLength = width == 1920 ? 0.35f * 16f * 1920f / 1080f
                : 0.35f * 16f * 1440f / 1080f;
            float midpointTime = laneLength / (2f * 1.5f);
            backdrop.Tick(midpointTime - pursuerDelay);
            Assert.AreEqual(1f, wizardRenderer.color.a, 0.001f);
            Assert.AreEqual(1f,
                pursuer.GetComponentInChildren<SpriteRenderer>().color.a, 0.001f);
            AssertClippedPosition(wizard);
            AssertClippedPosition(pursuer);
            AssertViewportMargin(wizard);
            AssertViewportMargin(pursuer);

            float duration = laneLength / 1.5f;
            backdrop.Tick(duration - 0.25f - midpointTime);
            Assert.AreEqual(0.5f, wizardRenderer.color.a, 0.02f,
                "Wizard fades during its last half second on the clipped lane.");
            AssertClippedPosition(wizard);
            AssertClippedPosition(pursuer);

            backdrop.Tick(pursuerDelay + 0.25f);
            Assert.AreEqual(0, backdrop.ActiveActorCount,
                "Both actors retire after reaching the far lane endpoint.");
            Assert.AreEqual(0, registry.ActiveCount);
        }

        [Test]
        public void NarrowAspect_SkipsPairingsBecauseTheClippedLaneIsUnderSixWorldUnits()
        {
            SetResolution(360, 1080);
            backdrop.SetSelectors((minimum, maximum) => minimum, () => true);
            backdrop.Tick(0f);
            backdrop.Tick(40f);
            Assert.AreEqual(0, backdrop.StartedPairingCount);
            Assert.AreEqual(5, backdrop.NextPairingIndex,
                "One immediate attempt and one attempt per ten seconds should be skipped.");
            Assert.AreEqual(0, backdrop.ActiveActorCount);
            Assert.IsNull(GameObject.Find("TitleScreenChaseActors"));
        }

        [Test]
        public void StartGame_ClearsActorsInTheSameCallAndPreventsFuturePairings()
        {
            backdrop.SetSelectors((minimum, maximum) => minimum, () => true);
            backdrop.Tick(0f);
            backdrop.Tick(2f);
            Assert.AreEqual(2, backdrop.ActiveActorCount);
            Assert.AreEqual(0, registry.ActiveCount);

            title.StartGame();

            Assert.IsFalse(title.IsTitleScreenVisible);
            Assert.IsTrue(title.HasRequestedWizardSelection);
            Assert.AreEqual(0, backdrop.ActiveActorCount);
            Assert.IsNull(GameObject.Find("TitleChaseWizard_Ember"));
            Assert.IsNull(GameObject.Find("TitleChasePursuer_DungeonBrute"));
            backdrop.Tick(100f);
            Assert.AreEqual(1, backdrop.StartedPairingCount);
            Assert.AreEqual(0, backdrop.ActiveActorCount);
            Assert.AreEqual(0, registry.ActiveCount);
        }

        [UnityTest]
        public IEnumerator WalkingWizard_UsesItsSelectedPresentationWithoutGameplayComponents()
        {
            backdrop.SetSelectors((minimum, maximum) => minimum, () => true);
            backdrop.Tick(0f);
            GameObject wizard = GameObject.Find("TitleChaseWizard_Ember");
            Assert.IsNotNull(wizard);
            // ApplyPresentation discards the first Unity Update displacement so the initial
            // placement is never misread as a walk. Let that reset frame run first.
            yield return null;
            backdrop.Tick(0.25f);
            yield return null;

            WizardAnimationController animation = wizard.GetComponent<WizardAnimationController>();
            Assert.AreEqual(WizardPresentation.Masculine, animation.Presentation);
            Assert.AreEqual(WizardSkin.White, animation.Skin);
            Assert.That(animation.CurrentState, Does.StartWith("Wizard_Masculine_White_walk_"));
            AssertPresentationOnly(wizard);
        }

        private void SetResolution(int width, int height)
        {
            if (chaseCamera.targetTexture != null) chaseCamera.targetTexture = null;
            if (targetTexture != null)
            {
                targetTexture.Release();
                UnityEngine.Object.DestroyImmediate(targetTexture);
            }
            targetTexture = new RenderTexture(width, height, 0);
            targetTexture.Create();
            chaseCamera.targetTexture = targetTexture;
        }

        private void AssertClippedPosition(GameObject actor)
        {
            Vector3 position = actor.transform.position;
            Vector3 viewport = chaseCamera.WorldToViewportPoint(position);
            Assert.That(position.x, Is.InRange(-14.001f, 14.001f));
            Assert.That(position.z, Is.InRange(-26.001f, 0.001f));
            Assert.AreEqual(0f, position.y, 0.001f);
            Assert.That(viewport.x, Is.InRange(0.549f, 0.901f));
            Assert.That(viewport.y, Is.InRange(0.05f, 0.95f));
            Assert.Greater(viewport.z, 0f);
            AssertSpriteRectClearOfTitle(actor);
        }

        private void AssertSpriteRectClearOfTitle(GameObject actor)
        {
            SpriteRenderer renderer = actor.GetComponentInChildren<SpriteRenderer>();
            Assert.IsNotNull(renderer);
            Assert.IsNotNull(renderer.sprite,
                actor.name + " must have visible sprite art while crossing the title.");
            Bounds bounds = renderer.bounds;
            float leftmostViewportX = float.PositiveInfinity;
            for (int x = 0; x < 2; x++)
            for (int y = 0; y < 2; y++)
            for (int z = 0; z < 2; z++)
            {
                Vector3 corner = new Vector3(
                    x == 0 ? bounds.min.x : bounds.max.x,
                    y == 0 ? bounds.min.y : bounds.max.y,
                    z == 0 ? bounds.min.z : bounds.max.z);
                Vector3 projected = chaseCamera.WorldToViewportPoint(corner);
                leftmostViewportX = Mathf.Min(leftmostViewportX, projected.x);
            }

            // All three sayings and Start Game occupy the left viewport column [0, 0.45].
            // Check the rendered sprite rectangle, not just its root position: a large
            // close-up scale may otherwise put the actor over the words.
            Assert.Greater(leftmostViewportX, 0.45f,
                actor.name + " overlaps the left-side sayings or Start Game button.");
        }

        private void AssertViewportMargin(GameObject actor)
        {
            Vector3 viewport = chaseCamera.WorldToViewportPoint(actor.transform.position);
            Assert.That(viewport.x, Is.InRange(0.05f, 0.95f));
            Assert.That(viewport.y, Is.InRange(0.05f, 0.95f));
        }

        private static void AssertPresentationOnly(GameObject actor)
        {
            foreach (Component component in actor.GetComponentsInChildren<Component>(true))
            {
                Assert.IsTrue(component is Transform || component is Animator ||
                    component is SpriteRenderer || component is WizardAnimationController ||
                    component is EnemyAnimationController,
                    actor.name + " unexpectedly carries " + component.GetType().Name);
            }
            Assert.IsNull(actor.GetComponentInChildren<NavMeshAgent>(true));
            Assert.IsNull(actor.GetComponentInChildren<Collider>(true));
            Assert.IsNull(actor.GetComponentInChildren<EnemyTargetKnowledge>(true));
            Assert.IsNull(actor.GetComponentInChildren<EnemyHealth>(true));
            Assert.IsNull(actor.GetComponentInChildren<EnemyPursuitMovement>(true));
            Assert.IsNull(actor.GetComponentInChildren<EnemyLanternWispCaster>(true));
        }

        private static RuntimeAnimatorController ControllerFromPrefab(string resourcePath)
        {
            GameObject prefab = Resources.Load<GameObject>(resourcePath);
            Assert.IsNotNull(prefab, "Missing chase art source prefab: " + resourcePath);
            Animator animator = prefab.GetComponentInChildren<Animator>(true);
            Assert.IsNotNull(animator, "Missing chase art Animator: " + resourcePath);
            Assert.IsNotNull(animator.runtimeAnimatorController,
                "Missing chase art controller: " + resourcePath);
            return animator.runtimeAnimatorController;
        }

        private static void SetPrivateField(object target, string name, object value)
        {
            FieldInfo field = target.GetType().GetField(
                name, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, "Missing TitleScreenController field " + name);
            field.SetValue(target, value);
        }
    }
}
