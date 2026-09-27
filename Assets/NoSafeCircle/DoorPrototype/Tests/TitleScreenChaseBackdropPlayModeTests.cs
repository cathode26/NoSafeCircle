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
        private Texture2D fireballTexture;
        private Sprite fireballSprite;

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
            backdrop.TitlePreviewLoopEnabled = true;
            fireballTexture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            fireballTexture.SetPixels(new[] { Color.red, Color.red, Color.red, Color.red });
            fireballTexture.Apply();
            fireballSprite = Sprite.Create(fireballTexture, new Rect(0, 0, 2, 2),
                new Vector2(0.5f, 0.5f), 2f);
            backdrop.ConfigureFireballArt(new[]
                { fireballSprite, fireballSprite, fireballSprite, fireballSprite }, fireballSprite);
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
            GameObject fallenWizards = GameObject.Find("EntryChaseFallenWizards");
            if (fallenWizards != null) UnityEngine.Object.DestroyImmediate(fallenWizards);
            if (registryObject != null) UnityEngine.Object.DestroyImmediate(registryObject);
            if (fireballSprite != null) UnityEngine.Object.DestroyImmediate(fireballSprite);
            if (fireballTexture != null) UnityEngine.Object.DestroyImmediate(fireballTexture);
            if (titleObject != null) UnityEngine.Object.DestroyImmediate(titleObject);
            if (cameraObject != null) UnityEngine.Object.DestroyImmediate(cameraObject);
            if (targetTexture != null)
            {
                targetTexture.Release();
                UnityEngine.Object.DestroyImmediate(targetTexture);
            }
        }

        [Test]
        public void TitleScreen_DoesNotLoopChaseBeforeWizardSelection()
        {
            backdrop.TitlePreviewLoopEnabled = false;
            backdrop.Tick(60f);
            Assert.AreEqual(0, backdrop.StartedPairingCount);
            Assert.AreEqual(0, backdrop.ActiveActorCount);
            Assert.IsNull(GameObject.Find("TitleScreenChaseActors"));
        }

        [TestCase(WizardPresentation.Masculine, WizardSkin.White, "Ember")]
        [TestCase(WizardPresentation.Masculine, WizardSkin.Black, "Ash")]
        [TestCase(WizardPresentation.Feminine, WizardSkin.White, "Frost")]
        [TestCase(WizardPresentation.Feminine, WizardSkin.Black, "Dusk")]
        public void EntryChase_UsesConfirmedWizard_ThreeCompanionsAndEightCosmeticPursuers(
            WizardPresentation presentation, WizardSkin skin, string wizardName)
        {
            backdrop.TitlePreviewLoopEnabled = false;
            title.StartGame();
            Assert.IsTrue(backdrop.BeginEntryChase(
                new ConfirmedWizardSelection(presentation, skin),
                new Vector3(0f, 0f, 2.5f), new Vector3(-4f, 0f, -22f),
                -1.5f, 0.75f));

            GameObject wizard = GameObject.Find("TitleEntryWizard_" + wizardName);
            GameObject brute = GameObject.Find("TitleEntryPursuer_DungeonBrute");
            GameObject secondBrute = GameObject.Find("TitleEntryPursuer_DungeonBrute_2");
            GameObject wraith = GameObject.Find("TitleEntryPursuer_LanternWraith");
            Assert.IsNotNull(wizard);
            Assert.IsNotNull(brute);
            Assert.IsNotNull(secondBrute);
            Assert.IsNotNull(wraith);
            Assert.AreSame(wizard.transform, backdrop.EntryWizardTransform);
            Assert.AreSame(brute.transform, backdrop.EntryPursuerTransform);
            Assert.AreSame(secondBrute.transform, backdrop.EntrySecondPursuerTransform);
            Assert.AreSame(wraith.transform, backdrop.EntryWraithTransform);
            Assert.AreEqual(3, backdrop.EntryCompanionCount);
            Assert.AreEqual(0, backdrop.FallenEntryCompanionCount);
            Assert.AreEqual(6, backdrop.EntryMeleePursuerCount);
            Assert.AreEqual(2, backdrop.EntryWraithPursuerCount);
            Assert.AreEqual(12, backdrop.ActiveActorCount,
                "The entry starts with four wizards and eight cosmetic pursuers.");
            Assert.AreEqual(presentation, wizard.GetComponent<WizardAnimationController>().Presentation);
            Assert.AreEqual(skin, wizard.GetComponent<WizardAnimationController>().Skin);
            AssertPresentationOnly(wizard);
            AssertPresentationOnly(brute);
            AssertPresentationOnly(secondBrute);
            AssertPresentationOnly(wraith);
            Assert.IsNotNull(backdrop.EntrySecondWraithTransform);
            AssertPresentationOnly(backdrop.EntrySecondWraithTransform.gameObject);
            for (int index = 0; index < 4; index++)
            {
                Transform additionalMelee = backdrop.EntryAdditionalMeleeTransform(index);
                Assert.IsNotNull(additionalMelee);
                AssertPresentationOnly(additionalMelee.gameObject);
            }

            int selectedIndex = (int)presentation * 2 + (int)skin;
            for (int index = 0; index < 4; index++)
            {
                if (index == selectedIndex) continue;
                GameObject companion = GameObject.Find("TitleEntryCompanion_" + WizardNames[index]);
                Assert.IsNotNull(companion,
                    "The unselected wizard " + WizardNames[index] + " is missing.");
                WizardAnimationController companionAnimation =
                    companion.GetComponent<WizardAnimationController>();
                Assert.IsNotNull(companionAnimation);
                Assert.AreEqual(OrderedWizards[index].Presentation,
                    companionAnimation.Presentation);
                Assert.AreEqual(OrderedWizards[index].Skin, companionAnimation.Skin);
                AssertPresentationOnly(companion);
            }
            for (int index = 0; index < backdrop.EntryCompanionCount; index++)
                Assert.IsNotNull(backdrop.EntryCompanionTransform(index));
            Assert.AreEqual(0, registry.ActiveCount);
        }

        [Test]
        public void EntryChase_ThreeUnselectedWizardsFallInOrder_BeforeSelectedWizardEnters()
        {
            backdrop.TitlePreviewLoopEnabled = false;
            title.StartGame();
            Assert.IsTrue(backdrop.BeginEntryChase(OrderedWizards[2],
                new Vector3(0f, 0f, -30f), new Vector3(0f, 0f, -6f),
                -8.75f, -11.5f));

            GameObject selected = GameObject.Find("TitleEntryWizard_Frost");
            Assert.IsNotNull(selected);
            Assert.IsNull(GameObject.Find("TitleEntryCompanion_Frost"),
                "The selected wizard must not also appear as a casualty.");
            Assert.AreEqual(0, backdrop.FallenEntryCompanionCount);
            for (int expectedFalls = 1; expectedFalls <= 3; expectedFalls++)
            {
                for (int step = 0; step < 2000 &&
                     backdrop.FallenEntryCompanionCount < expectedFalls; step++)
                    backdrop.Tick(0.01f);

                Assert.AreEqual(expectedFalls, backdrop.FallenEntryCompanionCount,
                    "A companion fall was skipped or repeated.");
                Assert.IsTrue(selected.activeInHierarchy,
                    "The selected wizard must survive each companion's fall.");
                Assert.Less(backdrop.FiredEntryShotCount, 3,
                    "All three companion falls should precede the selected wizard's final hit.");
                Assert.AreEqual(0, registry.ActiveCount,
                    "Cosmetic pursuers and fallen wizards must not enter the gameplay registry.");
            }

            backdrop.Tick(100f);
            Assert.AreEqual(3, backdrop.FallenEntryCompanionCount);
            Assert.IsFalse(backdrop.IsEntryChaseRunning);
            Assert.AreEqual(0, backdrop.ActiveActorCount);
            Assert.IsNotNull(GameObject.Find("EntryChaseFallenWizards"),
                "Fallen wizard visuals should persist after the selected wizard enters.");
            Assert.IsNotNull(GameObject.Find("TitleEntryCompanion_Ember"));
            Assert.IsNotNull(GameObject.Find("TitleEntryCompanion_Ash"));
            Assert.IsNotNull(GameObject.Find("TitleEntryCompanion_Dusk"));
            Assert.IsNull(GameObject.Find("TitleEntryWizard_Frost"),
                "Only the selected cutscene actor retires at gameplay handoff.");
        }

        [Test]
        public void EntryChase_FiresTwoMissesThenOneHit_StunsBruteAndReachesDoor()
        {
            backdrop.TitlePreviewLoopEnabled = false;
            title.StartGame();
            int doorwayCalls = 0;
            int endingCalls = 0;
            int completionCalls = 0;
            backdrop.EntryWizardCrossedDoorway += () => doorwayCalls++;
            backdrop.EntryChaseEnding += () =>
            {
                endingCalls++;
                Assert.IsNotNull(backdrop.EntryWizardTransform,
                    "The fade begins while the selected wizard is still visible.");
            };
            backdrop.EntryChaseCompleted += () => completionCalls++;
            Assert.IsTrue(backdrop.BeginEntryChase(OrderedWizards[0],
                new Vector3(0f, 0f, 2.5f), new Vector3(-4f, 0f, -22f),
                -18f, -1f));

            GameObject wizard = GameObject.Find("TitleEntryWizard_Ember");
            GameObject brute = GameObject.Find("TitleEntryPursuer_DungeonBrute");
            backdrop.Tick(0.3f);
            Assert.AreEqual(0, backdrop.FiredEntryShotCount,
                "The longer chase should not fire every shot at its starting line.");
            backdrop.Tick(1f);
            Assert.AreEqual(1, backdrop.FiredEntryShotCount);
            Assert.AreEqual(1, backdrop.ActiveFireballCount);
            Assert.IsNotNull(GameObject.Find("TitleEntryFireball_0"));
            Assert.IsNull(GameObject.Find("TitleEntryFireball_0").GetComponent<Collider>());

            for (int step = 0; step < 500 &&
                 !backdrop.IsEntryWizardTurningToShoot; step++)
                backdrop.Tick(0.02f);
            Assert.IsTrue(backdrop.IsEntryWizardTurningToShoot,
                "The wizard must stop and turn for the final shot.");
            Assert.AreEqual(2, backdrop.FiredEntryShotCount);
            Vector3 shootingPosition = wizard.transform.position;
            for (int step = 0; step < 50 &&
                 !backdrop.IsEntryPursuerStunned; step++)
                backdrop.Tick(0.02f);
            Assert.IsTrue(backdrop.IsEntryPursuerStunned,
                "The final shot must stun the pursuer.");
            Assert.AreEqual(3, backdrop.FiredEntryShotCount);
            Assert.AreEqual(1, backdrop.EntryImpactCount,
                "Only the final of three cosmetic shots should hit the Brute.");
            Assert.Less(Vector3.Distance(shootingPosition, wizard.transform.position), 0.01f,
                "The wizard must hold the turned firing pose until impact.");
            Assert.AreEqual(0, doorwayCalls);
            Assert.GreaterOrEqual(brute.transform.position.z, -1f,
                "The cosmetic Brute must stay behind the wizard's door.");

            Vector3 stunnedWizardPosition = wizard.transform.position;
            Vector3 stunnedBrutePosition = brute.transform.position;
            backdrop.Tick(0.25f);
            Assert.IsTrue(backdrop.IsEntryPursuerStunned);
            Assert.Greater(Vector3.Distance(stunnedWizardPosition, wizard.transform.position), 0.1f,
                "The wizard should run for the entrance while the fast pursuer is stunned.");
            Assert.Less(Vector3.Distance(stunnedBrutePosition, brute.transform.position), 0.01f);
            backdrop.Tick(0.8f);
            Assert.IsTrue(backdrop.IsEntryPursuerStunned,
                "The hit must hold the lead melee enemy for longer than half a second.");
            backdrop.Tick(0.25f);
            Assert.IsFalse(backdrop.IsEntryPursuerStunned);
            Assert.AreEqual(2, backdrop.FiredEntryWispCount);
            Assert.AreEqual(1, backdrop.DodgedEntryWispCount);
            for (int step = 0; step < 500 && doorwayCalls == 0; step++)
                backdrop.Tick(0.02f);
            Assert.AreEqual(1, doorwayCalls);
            Assert.IsTrue(backdrop.IsEntryChaseRunning);
            Assert.GreaterOrEqual(brute.transform.position.z, -1f);
            backdrop.Tick(10f);
            Assert.AreEqual(1, endingCalls);
            Assert.AreEqual(1, completionCalls);
            Assert.IsFalse(backdrop.IsEntryChaseRunning);
            Assert.IsNull(backdrop.EntryWizardTransform);
            Assert.IsNull(backdrop.EntryPursuerTransform);
            Assert.IsNull(backdrop.EntrySecondPursuerTransform);
            Assert.IsNull(backdrop.EntryWraithTransform);
            Assert.AreEqual(0, backdrop.ActiveActorCount);
            Assert.AreEqual(0, backdrop.ActiveFireballCount);
            Assert.IsNull(GameObject.Find("TitleEntryWizard_Ember"));
            Assert.IsNull(GameObject.Find("TitleEntryPursuer_DungeonBrute"));
            Assert.AreEqual(0, registry.ActiveCount);
            backdrop.Tick(10f);
            Assert.AreEqual(1, endingCalls);
            Assert.AreEqual(1, completionCalls,
                "The gameplay handoff must happen exactly once.");
        }

        [Test]
        public void NorthboundChase_SpreadsShotsBeforeDoorAndCompletesAtArrival()
        {
            backdrop.TitlePreviewLoopEnabled = false;
            title.StartGame();

            const float entryZ = -30f;
            const float pursuerStopZ = -11.5f;
            const float doorCloseTriggerZ = -8.75f;
            const float arrivalZ = -6f;
            var gateCalls = 0;
            var completionCalls = 0;
            backdrop.EntryWizardCrossedDoorway += () =>
            {
                gateCalls++;
                Assert.GreaterOrEqual(backdrop.EntryWizardTransform.position.z, doorCloseTriggerZ);
                Assert.LessOrEqual(backdrop.EntryPursuerTransform.position.z, pursuerStopZ);
            };
            backdrop.EntryChaseCompleted += () => completionCalls++;

            Assert.IsTrue(backdrop.BeginEntryChase(OrderedWizards[0],
                new Vector3(0f, 0f, entryZ), new Vector3(0f, 0f, arrivalZ),
                doorCloseTriggerZ, pursuerStopZ));
            Assert.AreEqual(entryZ, backdrop.EntryWizardTransform.position.z, 0.001f);
            Assert.Less(backdrop.EntryPursuerTransform.position.z, entryZ);

            backdrop.Tick(6.1f);
            Assert.AreEqual(3, backdrop.FiredEntryShotCount,
                "The northbound chase keeps two miss shots followed by one hit shot.");
            Assert.AreEqual(0, backdrop.EntryImpactCount);
            backdrop.Tick(0.2f);
            Assert.AreEqual(1, backdrop.EntryImpactCount);
            Assert.AreEqual(0, gateCalls,
                "The door must stay open while the wizard is south of the close trigger.");
            Assert.Less(backdrop.EntryWizardTransform.position.z, doorCloseTriggerZ);
            Assert.Less(backdrop.EntryPursuerTransform.position.z,
                pursuerStopZ);

            backdrop.Tick(1f);
            Assert.AreEqual(0, gateCalls,
                "The half-second turn must delay the doorway crossing.");
            backdrop.Tick(1f);
            Assert.AreEqual(1, gateCalls);
            Assert.AreEqual(0, completionCalls);
            Assert.IsTrue(backdrop.IsEntryChaseRunning);
            Assert.LessOrEqual(backdrop.EntryPursuerTransform.position.z, pursuerStopZ);

            backdrop.Tick(0.1f);
            Assert.AreEqual(0, completionCalls);
            Assert.Less(backdrop.EntryWizardTransform.position.z, arrivalZ);
            Assert.AreEqual(pursuerStopZ, backdrop.EntryPursuerTransform.position.z, 0.001f);
            backdrop.Tick(0.1f);
            Assert.AreEqual(1, completionCalls);
            Assert.AreEqual(1, gateCalls);
            Assert.IsFalse(backdrop.IsEntryChaseRunning);
            Assert.IsNull(backdrop.EntryPursuerTransform);
        }

        [Test]
        public void NorthboundChase_TurnsForHalfSecond_StunsLeadLonger_ThenRunsOn()
        {
            backdrop.TitlePreviewLoopEnabled = false;
            title.StartGame();
            Assert.IsTrue(backdrop.BeginEntryChase(OrderedWizards[2],
                new Vector3(0f, 0f, -30f), new Vector3(0f, 0f, -6f),
                -8.75f, -11.5f));

            Transform wizard = backdrop.EntryWizardTransform;
            Transform brute = backdrop.EntryPursuerTransform;
            WizardAnimationController animation = wizard.GetComponent<WizardAnimationController>();
            EnemyAnimationController bruteAnimation = brute.GetComponent<EnemyAnimationController>();
            for (int step = 0; step < 1000 &&
                 !backdrop.IsEntryWizardTurningToShoot; step++)
                backdrop.Tick(0.01f);

            Assert.IsTrue(backdrop.IsEntryWizardTurningToShoot);
            Assert.AreEqual(2, backdrop.FiredEntryShotCount,
                "Only the two misses should have fired before the wizard turns.");
            Assert.AreEqual("south-west", animation.LastDirection,
                "A northbound wizard must turn to face the pursuer to the south.");
            StringAssert.EndsWith("_idle_south-west", animation.CurrentState,
                "The turned wizard must visibly hold a backward-facing idle pose.");
            Vector3 firingPosition = wizard.position;
            Vector3 bruteBeforeShot = brute.position;
            float gapAtTurn = wizard.position.z - brute.position.z;
            float turnDuration = 0f;
            while (backdrop.IsEntryWizardTurningToShoot && turnDuration < 1f)
            {
                backdrop.Tick(0.01f);
                turnDuration += 0.01f;
                if (backdrop.IsEntryWizardTurningToShoot)
                    Assert.Less(Vector3.Distance(firingPosition, wizard.position), 0.01f,
                        "The wizard moved while aiming and firing.");
            }

            Assert.That(turnDuration, Is.InRange(0.47f, 0.53f),
                "The backward-facing firing beat should last half a second.");
            Assert.AreEqual(3, backdrop.FiredEntryShotCount);
            Assert.AreEqual(1, backdrop.EntryImpactCount);
            Assert.IsTrue(backdrop.IsEntryPursuerStunned,
                "The hit should begin a distinct pursuer stun beat.");
            StringAssert.StartsWith("MeleeEnemy_idle_", bruteAnimation.CurrentState,
                "The stunned pursuer must stop its walking animation.");
            Assert.Greater(Vector3.Distance(bruteBeforeShot, brute.position), 0.5f,
                "The pursuer should still be advancing before the impact.");
            Assert.Greater(gapAtTurn, wizard.position.z - brute.position.z + 1f,
                "The faster melee enemy should visibly close the gap during the turn.");
            Assert.Greater(wizard.position.z - brute.position.z, 1f,
                "The fast melee enemy must not overtake the wizard before the hit.");
            Vector3 stunnedBrutePosition = brute.position;
            Vector3 stunnedWizardPosition = wizard.position;
            float stunDuration = 0f;
            while (backdrop.IsEntryPursuerStunned && stunDuration < 1.5f)
            {
                backdrop.Tick(0.01f);
                stunDuration += 0.01f;
                if (backdrop.IsEntryPursuerStunned)
                {
                    Assert.Less(Vector3.Distance(stunnedBrutePosition, brute.position), 0.01f,
                        "The hit pursuer must remain in place throughout the stun.");
                }
            }

            Assert.That(stunDuration, Is.InRange(1.22f, 1.28f),
                "The lead pursuer stun should last 1.25 seconds.");
            Assert.Greater(wizard.position.z, stunnedWizardPosition.z + 3f,
                "The wizard should run toward the door while the lead pursuer is stunned.");
            backdrop.Tick(0.1f);
            Assert.Greater(brute.position.z, stunnedBrutePosition.z + 0.1f,
                "The pursuer must resume its chase after the stun.");
            StringAssert.StartsWith("MeleeEnemy_walk_", bruteAnimation.CurrentState);
            Assert.AreEqual("north-east", animation.LastDirection,
                "The wizard should face the entrance again after turning back.");
        }

        [Test]
        public void NorthboundChase_WraithFiresOneWisp_AndWizardDodgesItsPath()
        {
            backdrop.TitlePreviewLoopEnabled = false;
            title.StartGame();
            Assert.IsTrue(backdrop.BeginEntryChase(OrderedWizards[2],
                new Vector3(0f, 0f, -30f), new Vector3(0f, 0f, -6f),
                -8.75f, -11.5f));

            backdrop.Tick(1.2f);
            Assert.AreEqual(1, backdrop.FiredEntryWispCount);
            Assert.IsNotNull(backdrop.EntryWraithTransform);
            Assert.IsNotNull(backdrop.EntrySecondPursuerTransform);
            Transform wisp = backdrop.EntryWispTransform;
            Assert.IsNotNull(wisp, "The Lantern Wraith's teal shot must be visible in flight.");
            Collider projectileCollider = wisp.GetComponent<Collider>();
            Assert.IsTrue(projectileCollider == null || !projectileCollider.enabled,
                "The cutscene missile must not damage the selected wizard.");

            backdrop.Tick(1.25f);
            Assert.IsTrue(backdrop.IsEntryWizardDodging);
            Assert.AreEqual(0, backdrop.EntryImpactCount);
            Assert.Greater(backdrop.EntryWizardTransform.position.x, 1.5f,
                "The wizard must sidestep out of the Wraith's aimed path.");
            Assert.IsNotNull(backdrop.EntryWispTransform);
            Assert.Greater(Mathf.Abs(backdrop.EntryWizardTransform.position.x -
                backdrop.EntryWispTransform.position.x), 1.5f,
                "The wisp must miss the dodging wizard at the crossing.");

            backdrop.Tick(0.7f);
            Assert.AreEqual(1, backdrop.DodgedEntryWispCount);
            Assert.IsFalse(backdrop.IsEntryWizardDodging);
            Assert.AreEqual(0f, backdrop.EntryWizardTransform.position.x, 0.01f,
                "She should return to the route leading into the door.");
            Assert.IsNull(backdrop.EntryWispTransform);
        }

        [Test]
        public void EntryChase_LargeTickCrossingBothPauses_NotifiesDoorAndCompletionOnce()
        {
            backdrop.TitlePreviewLoopEnabled = false;
            title.StartGame();
            int doorCalls = 0;
            int endingCalls = 0;
            int completionCalls = 0;
            backdrop.EntryWizardCrossedDoorway += () => doorCalls++;
            backdrop.EntryChaseEnding += () => endingCalls++;
            backdrop.EntryChaseCompleted += () => completionCalls++;
            Assert.IsTrue(backdrop.BeginEntryChase(OrderedWizards[2],
                new Vector3(0f, 0f, -30f), new Vector3(0f, 0f, -6f),
                -8.75f, -11.5f));

            backdrop.Tick(100f);
            Assert.AreEqual(3, backdrop.FiredEntryShotCount);
            Assert.AreEqual(1, backdrop.EntryImpactCount);
            Assert.AreEqual(2, backdrop.FiredEntryWispCount);
            Assert.AreEqual(1, backdrop.DodgedEntryWispCount);
            Assert.AreEqual(3, backdrop.FallenEntryCompanionCount);
            Assert.AreEqual(1, doorCalls);
            Assert.AreEqual(1, endingCalls);
            Assert.AreEqual(1, completionCalls);
            Assert.IsFalse(backdrop.IsEntryChaseRunning);
            Assert.AreEqual(0, backdrop.ActiveActorCount);
            Assert.AreEqual(0, backdrop.ActiveFireballCount);
            Assert.IsNull(backdrop.EntryWispTransform);

            backdrop.Tick(100f);
            Assert.AreEqual(1, doorCalls);
            Assert.AreEqual(1, endingCalls);
            Assert.AreEqual(1, completionCalls);
        }

        [Test]
        public void EntryChase_RejectsGateOrPursuerStopOutsideChamberOrder()
        {
            backdrop.TitlePreviewLoopEnabled = false;
            title.StartGame();
            Vector3 start = new Vector3(0f, 0f, -34f);
            Vector3 arrival = new Vector3(0f, 0f, -22f);

            Assert.IsFalse(backdrop.BeginEntryChase(OrderedWizards[0],
                start, arrival, -35f, -33.5f));
            Assert.IsFalse(backdrop.BeginEntryChase(OrderedWizards[0],
                start, arrival, -29.75f, -28f));
            Assert.IsNull(backdrop.EntryWizardTransform);
            Assert.IsNull(backdrop.EntryPursuerTransform);
            Assert.AreEqual(0, backdrop.ActiveActorCount);
        }

        [Test]
        public void CancelEntryChase_CleansVisualsWithoutCompletingOrClosingDoor()
        {
            backdrop.TitlePreviewLoopEnabled = false;
            title.StartGame();
            int doorwayCalls = 0;
            int completionCalls = 0;
            backdrop.EntryWizardCrossedDoorway += () => doorwayCalls++;
            backdrop.EntryChaseCompleted += () => completionCalls++;
            Assert.IsTrue(backdrop.BeginEntryChase(OrderedWizards[2],
                new Vector3(0f, 0f, 2.5f), new Vector3(-4f, 0f, -22f),
                -1.5f, 0.75f));
            backdrop.Tick(0.4f);
            Assert.AreEqual(1, backdrop.ActiveFireballCount);

            backdrop.CancelEntryChase();
            backdrop.CancelEntryChase();
            backdrop.Tick(20f);
            Assert.IsFalse(backdrop.IsEntryChaseRunning);
            Assert.IsNull(backdrop.EntryWizardTransform);
            Assert.IsNull(backdrop.EntryPursuerTransform);
            Assert.AreEqual(0, backdrop.ActiveActorCount);
            Assert.AreEqual(0, backdrop.ActiveFireballCount);
            Assert.AreEqual(0, doorwayCalls);
            Assert.AreEqual(0, completionCalls);
            Assert.IsNull(GameObject.Find("TitleScreenChaseActors"));
        }

        [Test]
        public void CancelEntryChase_AfterCompanionFall_RemovesPersistentBody()
        {
            backdrop.TitlePreviewLoopEnabled = false;
            title.StartGame();
            Assert.IsTrue(backdrop.BeginEntryChase(OrderedWizards[2],
                new Vector3(0f, 0f, -30f), new Vector3(0f, 0f, -6f),
                -8.75f, -11.5f));
            for (int step = 0; step < 2000 &&
                 backdrop.FallenEntryCompanionCount == 0; step++)
                backdrop.Tick(0.01f);

            Assert.AreEqual(1, backdrop.FallenEntryCompanionCount);
            Assert.IsNotNull(GameObject.Find("EntryChaseFallenWizards"));
            backdrop.CancelEntryChase();
            Assert.IsFalse(backdrop.IsEntryChaseRunning);
            Assert.IsNull(GameObject.Find("EntryChaseFallenWizards"));
            Assert.IsNull(GameObject.Find("TitleScreenChaseActors"));
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
