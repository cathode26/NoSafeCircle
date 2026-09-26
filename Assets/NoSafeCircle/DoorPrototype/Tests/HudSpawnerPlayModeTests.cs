using System.Collections;
using System.Reflection;
using System.Text.RegularExpressions;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Hud;
using NoSafeCircle.DoorPrototype.World;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.TestTools;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // The HUD lane, proved at runtime with no scene: the committed spawner prefab is loaded from
    // Resources exactly as GameBootstrap loads it, a stand-in player is built in code, and Spawn()
    // must produce ONE bound Canvas whose hierarchy the existing fixtures already look up by name.
    //
    // EVERY EXPECTED VALUE NAMES ITS SOURCE, and none is the HUD itself: hierarchy names come from
    // TitleScreenPlayModeTests and WizardGameEntryPlayModeTests, which look them up in the committed
    // scene; bar fractions are derived from the stand-in's own components; the top-left column is
    // recomputed from the four numbers the Art Director derived it from; the debug amounts are read
    // from the debug controls on the stand-in.
    //
    // THE FAILURE PATHS ARE TESTED ON PURPOSE. A HUD that comes up silently unbound is the worst shape
    // this lane can produce - bars that read full over a wizard taking damage - so a missing player,
    // a player missing a component, an unassigned prefab and a vanished reflection target must each
    // produce a red line that names what is missing, and no Canvas.
    public sealed class HudSpawnerPlayModeTests
    {
        private const string SpawnerResourcePath = GameBootstrap.SpawnerResourceFolder + "/HudSpawner";

        // Off the origin on every axis, so a HUD that quietly used (0,0,0) for the world spawn fails.
        private static readonly Vector3 StandInSpawnPose = new Vector3(3f, 0.08f, -5f);

        private GameObject spawnerObject;
        private GameObject playerObject;
        private GameObject scratchObject;

        [TearDown]
        public void TearDown()
        {
            Retire(ref spawnerObject);
            Retire(ref playerObject);
            Retire(ref scratchObject);
        }

        private static void Retire(ref GameObject target)
        {
            if (target == null) return;

            // Deactivate first: an inactive EventSystem leaves EventSystem's live list immediately,
            // while Destroy is deferred to end of frame, so the next test cannot see two of them.
            target.SetActive(false);
            Object.Destroy(target);
            target = null;
        }

        private HudSpawner CreateSpawnerFromTheCommittedPrefab()
        {
            var prefab = Resources.Load<GameObject>(SpawnerResourcePath);
            Assert.IsNotNull(prefab,
                "Resources/" + SpawnerResourcePath + ".prefab did not load. Either the prefab is missing "
                + "or its YAML failed to import; GameBootstrap loads spawners from exactly this path.");

            spawnerObject = Object.Instantiate(prefab);
            spawnerObject.name = "HudSpawnerUnderTest";
            var spawner = spawnerObject.GetComponent<HudSpawner>();
            Assert.IsNotNull(spawner,
                "The committed spawner prefab carries no HudSpawner, so GameBootstrap would warn and "
                + "skip it and the HUD would never appear.");
            return spawner;
        }

        // The six components HudBindings binds to, all on the root, as Player.prefab is specified and
        // as the built player has them today. No input asset: PlayerMovement warns and is otherwise
        // fine, and nothing here drives the mouse.
        private GameObject CreateStandInPlayer(bool withMana = true)
        {
            playerObject = new GameObject("Player");
            playerObject.SetActive(false);
            playerObject.transform.position = StandInSpawnPose;
            playerObject.AddComponent<CharacterController>();
            playerObject.AddComponent<PlayerHealth>();
            if (withMana)
            {
                playerObject.AddComponent<PlayerMana>();
            }

            playerObject.AddComponent<PlayerInteractionController>();
            playerObject.AddComponent<PlayerMovement>();
            playerObject.AddComponent<WizardAnimationController>(); // RequireComponent adds the Animator
            playerObject.AddComponent<DebugDamageControl>();
            playerObject.AddComponent<DebugManaSpendControl>();
            playerObject.SetActive(true);
            return playerObject;
        }

        private Transform CanvasRoot()
        {
            Transform canvas = spawnerObject.transform.Find(HudSpawner.CanvasObjectName);
            Assert.IsNotNull(canvas,
                "No '" + HudSpawner.CanvasObjectName + "' child under the spawner. Every existing fixture "
                + "finds the HUD by that name (TitleScreenPlayModeTests:191).");
            return canvas;
        }

        private static T Part<T>(Transform canvas, string path) where T : Component
        {
            Transform found = canvas.Find(path);
            Assert.IsNotNull(found,
                "No '" + path + "' under the Canvas. The names come from TitleScreenPlayModeTests:196-198 "
                + "and WizardGameEntryPlayModeTests:309-318, which look them up in the committed scene.");
            var component = found.GetComponent<T>();
            Assert.IsNotNull(component, path + " carries no " + typeof(T).Name + ".");
            return component;
        }

        private static int ActiveChildCount(Transform parent)
        {
            int count = 0;
            for (int i = 0; i < parent.childCount; i++)
            {
                if (parent.GetChild(i).gameObject.activeSelf) count++;
            }

            return count;
        }

        // Component-wise with a tolerance: a pose that round-trips through a parent transform can
        // differ from the value that was set by a floating-point ulp, and exact Vector3 equality
        // would turn that into a false failure.
        private static void AssertPose(Vector3 expected, Vector3 actual, string message)
        {
            Assert.AreEqual(expected.x, actual.x, 0.0001f, message + " (x)");
            Assert.AreEqual(expected.y, actual.y, 0.0001f, message + " (y)");
            Assert.AreEqual(expected.z, actual.z, 0.0001f, message + " (z)");
        }

        private static float ReadPrivateFloat(object target, string fieldName)
        {
            FieldInfo field = target.GetType().GetField(fieldName,
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field,
                "Expected a private field '" + fieldName + "' on " + target.GetType().Name
                + "; this fixture reads the control's own serialized default rather than restating it.");
            return (float)field.GetValue(target);
        }

        [UnityTest]
        public IEnumerator SpawnerPrefabDoesNotSpawnOnItsOwn()
        {
            CreateStandInPlayer();
            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();
            yield return null;

            Assert.AreEqual(0, spawnerObject.transform.childCount,
                "Instantiating the spawner prefab created children. A spawner that spawns in Awake runs "
                + "before GameBootstrap owns the order, and before the player it must bind to exists.");
            Assert.AreEqual(-1, spawner.SpawnedCount, "SpawnedCount must read -1 until Spawn() runs.");
            Assert.AreEqual(SpawnPhase.Hud, spawner.Phase,
                "The HUD must run in SpawnPhase.Hud, last, because it binds to a player phase 4 created.");
        }

        [UnityTest]
        public IEnumerator Spawn_CreatesTheCanvasWithTheHierarchyTheFixturesLookUp()
        {
            CreateStandInPlayer();
            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();

            int created = spawner.Spawn();
            yield return null;

            Assert.AreEqual(1, created, "Spawn() must report exactly one Canvas.");
            Assert.AreEqual(1, spawner.SpawnedCount, "The returned count and SpawnedCount disagree.");
            Assert.IsNotNull(spawner.Hud, "Spawn() reported success but exposes no HudBindings.");

            Transform canvas = CanvasRoot();
            Assert.AreEqual(RenderMode.ScreenSpaceOverlay, canvas.GetComponent<Canvas>().renderMode,
                "The HUD canvas must be ScreenSpaceOverlay; it does not sit in the world.");

            // TitleScreenPlayModeTests:203 asserts this exact text in the committed scene.
            Assert.AreEqual("NO SAFE CIRCLE", Part<Text>(canvas, "TitleScreen/TitleCard/Title").text);

            Part<Button>(canvas, "TitleScreen/TitleCard/StartGameButton");
            Part<Button>(canvas, "WizardSelectionScreen/ConfirmSelectionButton");
            for (int option = 1; option <= 4; option++)
            {
                Part<Button>(canvas, "WizardSelectionScreen/WizardOption" + option);
            }

            Part<Image>(canvas, "HealthFill/Fill");
            Part<Image>(canvas, "ManaFill/Fill");
            Part<Image>(canvas, "ProgressFill/Fill");
            Part<Text>(canvas, "ControlsHud/Text");
            Assert.IsNotNull(canvas.Find("InteractPrompt"), "No 'InteractPrompt' under the Canvas.");

            Assert.AreEqual(1, canvas.GetComponentsInChildren<EventSystem>(true).Length,
                "The HUD must carry exactly one EventSystem; the runtime scene has none of its own.");
            Assert.AreEqual(1, canvas.GetComponentsInChildren<InputSystemUIInputModule>(true).Length,
                "The EventSystem must use the Input System module, the one the game's input runs on.");
            Assert.AreEqual(1, canvas.GetComponentsInChildren<DemoRunFlow>(true).Length,
                "DemoRunFlow rides inside the HUD prefab, unchanged, exactly once.");
        }

        [UnityTest]
        public IEnumerator Spawn_BindsTheHealthAndManaBarsToThePlayer()
        {
            GameObject player = CreateStandInPlayer();
            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();
            spawner.Spawn();
            yield return null;

            var health = player.GetComponent<PlayerHealth>();
            var mana = player.GetComponent<PlayerMana>();
            Image healthFill = Part<Image>(CanvasRoot(), "HealthFill/Fill");
            Image manaFill = Part<Image>(CanvasRoot(), "ManaFill/Fill");

            Assert.AreEqual(1f, healthFill.fillAmount, 0.0001f, "A freshly bound health bar reads full.");

            // The fractions are derived from the stand-in's own components, never restated.
            const float damage = 25f;
            health.TakeDamage(damage);
            float expectedHealth = (health.MaxHealth - damage) / health.MaxHealth;
            Assert.AreEqual(expectedHealth, healthFill.fillAmount, 0.0001f,
                "HealthFill/Fill did not follow PlayerHealth. PlayerHealthUI.Bind was not called with "
                + "this player's PlayerHealth, or its fill image is not the one under HealthFill.");

            const float spend = 20f;
            Assert.IsTrue(mana.Spend(spend), "The stand-in could not spend " + spend + " mana.");
            yield return null; // PlayerManaUI refreshes its fill in Update
            float expectedMana = (mana.MaxMana - spend) / mana.MaxMana;
            Assert.AreEqual(expectedMana, manaFill.fillAmount, 0.001f,
                "ManaFill/Fill did not follow PlayerMana. PlayerManaUI.Bind was not called with this "
                + "player's PlayerMana, or its fill image is not the one under ManaFill.");
        }

        [UnityTest]
        public IEnumerator Spawn_ShowsTheTitleAndSuspendsGameplayInputUntilEntry()
        {
            GameObject player = CreateStandInPlayer();
            var movement = player.GetComponent<PlayerMovement>();
            var interaction = player.GetComponent<PlayerInteractionController>();
            var debugDamage = player.GetComponent<DebugDamageControl>();
            var debugMana = player.GetComponent<DebugManaSpendControl>();
            var wizard = player.GetComponent<WizardAnimationController>();

            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();
            spawner.Spawn();

            // Same frame as the spawn, before any Update: WorldSpawn is where the player stood.
            AssertPose(StandInSpawnPose, spawner.Hud.WorldSpawn.position,
                "WorldSpawn was not moved to the player's pose at spawn, so wizard-selection entry would "
                + "teleport the player somewhere the Player lane never chose.");
            Assert.AreSame(spawnerObject.transform, spawner.Hud.WorldSpawn.parent,
                "WorldSpawn must sit beside the Canvas under the spawner, not under the screen-space "
                + "Canvas, whose RectTransform rescales with the screen and would drag the world pose "
                + "with it on every resize.");
            yield return null;

            Transform canvas = CanvasRoot();
            var title = canvas.GetComponent<TitleScreenController>();
            var selection = canvas.GetComponent<WizardSelectionController>();
            var entry = canvas.GetComponent<WizardGameEntryController>();
            Assert.IsNotNull(title);
            Assert.IsNotNull(selection);
            Assert.IsNotNull(entry);

            Assert.IsTrue(title.IsTitleScreenVisible, "The HUD must come up on the title screen.");
            Assert.IsTrue(canvas.Find("TitleScreen").gameObject.activeSelf);
            Assert.IsFalse(canvas.Find("WizardSelectionScreen").gameObject.activeSelf);
            Assert.IsFalse(movement.IsGameplayEnabled,
                "Movement must be suspended while the title owns the flow (NSC-066 AC-002).");
            Assert.IsFalse(interaction.IsGameplayEnabled, "Door interaction must be suspended at the title.");
            Assert.IsFalse(debugDamage.enabled, "The debug damage key must be inert at the title.");
            Assert.IsFalse(debugMana.enabled, "The debug mana key must be inert at the title.");

            // Through the prefab's OWN serialized listeners, so the persistent calls are proven too.
            Part<Button>(canvas, "TitleScreen/TitleCard/StartGameButton").onClick.Invoke();
            Assert.IsTrue(title.HasRequestedWizardSelection,
                "StartGameButton's serialized onClick did not reach TitleScreenController.StartGame.");
            Assert.IsFalse(canvas.Find("TitleScreen").gameObject.activeSelf);
            Assert.IsTrue(selection.IsSelectionVisible, "Start Game must open wizard selection.");

            Part<Button>(canvas, "WizardSelectionScreen/WizardOption1").onClick.Invoke();
            Assert.AreEqual(0, selection.SelectedOptionIndex,
                "WizardOption1's serialized onClick must call SelectOption(0).");
            Assert.IsTrue(selection.IsConfirmationAvailable);

            // Move the player away, as WizardGameEntryPlayModeTests:104 does, so the return is real.
            player.transform.position = StandInSpawnPose + new Vector3(2f, 0f, -1f);
            Part<Button>(canvas, "WizardSelectionScreen/ConfirmSelectionButton").onClick.Invoke();

            Assert.IsTrue(entry.HasEnteredGameplay,
                "Confirming did not enter the world. WizardGameEntryController refuses with empty player "
                + "references, so the reflection-bound fields did not take (see HudReflectionBinder).");
            Assert.AreEqual(1, entry.GameplayEntryCount);

            // Option 0 is Masculine/White as serialized in the prefab; the same pair is
            // WizardGameEntryPlayModeTests.ExpectedPresentations[0] / ExpectedSkins[0].
            Assert.AreEqual(WizardPresentation.Masculine, wizard.Presentation);
            Assert.AreEqual(WizardSkin.White, wizard.Skin);

            AssertPose(spawner.Hud.WorldSpawn.position, player.transform.position,
                "Entry must place the player at WorldSpawn, which is where it was spawned.");
            Assert.IsFalse(canvas.Find("TitleScreen").gameObject.activeSelf);
            Assert.IsFalse(canvas.Find("WizardSelectionScreen").gameObject.activeSelf);
            Assert.IsTrue(movement.IsGameplayEnabled, "Entry must hand movement back to the player.");
            Assert.IsTrue(interaction.IsGameplayEnabled, "Entry must hand door interaction back.");
        }

        [UnityTest]
        public IEnumerator Spawn_LayoutMatchesTheApprovedTopLeftColumn()
        {
            CreateStandInPlayer();
            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();
            spawner.Spawn();
            yield return null;

            // The Art Director's derivation of 2026-09-25 (DoorPrototypeGlobalSceneBuilder.cs:1387-1397,
            // an Editor-assembly constant this assembly cannot read, so its four INPUTS are restated and
            // the rows are recomputed here): each row starts one gap below the previous one, under the
            // 100 px band DemoRunFlow's IMGUI labels own.
            const float margin = 16f;
            const float gap = 8f;
            const float bar = 14f;
            const float demoRunFlowBand = 100f;
            float healthTop = demoRunFlowBand + gap;
            float manaTop = healthTop + bar + gap;
            float controlsTop = manaTop + bar + gap;

            Transform canvas = CanvasRoot();
            AssertTopLeftRow(Part<RectTransform>(canvas, "HealthFill"),
                new Vector2(margin, -healthTop), new Vector2(220f, bar));
            AssertTopLeftRow(Part<RectTransform>(canvas, "ManaFill"),
                new Vector2(margin, -manaTop), new Vector2(220f, bar));
            AssertTopLeftRow(Part<RectTransform>(canvas, "ControlsHud"),
                new Vector2(margin, -controlsTop), new Vector2(300f, 130f));
        }

        private static void AssertTopLeftRow(RectTransform row, Vector2 anchoredPosition, Vector2 size)
        {
            string who = row.name;
            Assert.AreEqual(new Vector2(0f, 1f), row.anchorMin, who + " anchorMin must be top-left.");
            Assert.AreEqual(new Vector2(0f, 1f), row.anchorMax, who + " anchorMax must be top-left.");
            Assert.AreEqual(new Vector2(0f, 1f), row.pivot, who + " pivot must be top-left.");
            Assert.AreEqual(anchoredPosition.x, row.anchoredPosition.x, 0.001f, who + " x");
            Assert.AreEqual(anchoredPosition.y, row.anchoredPosition.y, 0.001f,
                who + " y: the rows are derived as height + gap, and a literal y is how 32 px rects on "
                + "a 28 px pitch once overlapped by 4.");
            Assert.AreEqual(size.x, row.sizeDelta.x, 0.001f, who + " width");
            Assert.AreEqual(size.y, row.sizeDelta.y, 0.001f, who + " height");
        }

        [UnityTest]
        public IEnumerator Spawn_DebugButtonsReachThePlayer()
        {
            GameObject player = CreateStandInPlayer();
            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();
            spawner.Spawn();
            yield return null;

            var health = player.GetComponent<PlayerHealth>();
            var mana = player.GetComponent<PlayerMana>();

            // The amounts are the controls' own serialized defaults, read from the stand-in.
            float damageAmount = ReadPrivateFloat(player.GetComponent<DebugDamageControl>(), "damageAmount");
            float spendAmount = ReadPrivateFloat(player.GetComponent<DebugManaSpendControl>(), "spendAmount");
            Assert.Greater(damageAmount, 0f, "A zero debug damage would make this pass vacuously.");
            Assert.Greater(spendAmount, 0f, "A zero debug spend would make this pass vacuously.");

            Transform canvas = CanvasRoot();
            float healthBefore = health.CurrentHealth;
            Part<Button>(canvas, "DebugDamageButton").onClick.Invoke();
            Assert.AreEqual(healthBefore - damageAmount, health.CurrentHealth, 0.0001f,
                "DebugDamageButton did not reach the player's DebugDamageControl. Its listener is added "
                + "at runtime because a persistent listener cannot point at another prefab's instance.");

            float manaBefore = mana.CurrentMana;
            Part<Button>(canvas, "DebugManaSpendButton").onClick.Invoke();
            Assert.AreEqual(manaBefore - spendAmount, mana.CurrentMana, 0.0001f,
                "DebugManaSpendButton did not reach the player's DebugManaSpendControl.");
        }

        [UnityTest]
        public IEnumerator Spawn_WithoutAPlayerCreatesNothingAndLogsAnErrorNamingTheMissingType()
        {
            // No stand-in at all: this is what phase 6 sees if the Player lane did not run.
            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();

            LogAssert.Expect(LogType.Error, new Regex("PlayerMovement"));
            int created = spawner.Spawn();
            yield return null;

            Assert.AreEqual(0, created, "With no player the HUD must create nothing.");
            Assert.AreEqual(0, spawner.SpawnedCount);
            Assert.IsNull(spawner.Hud, "No HUD may be exposed when nothing was bound.");
            Assert.AreEqual(0, spawnerObject.transform.childCount,
                "A Canvas exists with no player to bind to. That is the silent-unbound HUD this lane "
                + "exists to make impossible.");
        }

        [UnityTest]
        public IEnumerator Spawn_WithAPlayerMissingAComponentCreatesNothingAndNamesIt()
        {
            CreateStandInPlayer(withMana: false);
            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();

            // Two red lines, in order: HudBindings names the missing component, then the spawner says
            // it destroyed the HUD rather than leave it half-bound.
            LogAssert.Expect(LogType.Error, new Regex("PlayerMana"));
            LogAssert.Expect(LogType.Error, new Regex("half-bound"));
            int created = spawner.Spawn();

            Assert.AreEqual(0, created, "A player missing PlayerMana must produce no HUD.");
            Assert.AreEqual(0, ActiveChildCount(spawnerObject.transform),
                "The half-bound HUD must be deactivated the same frame, not merely scheduled to die.");
            yield return null;
            Assert.AreEqual(0, spawnerObject.transform.childCount,
                "The half-bound HUD must be gone by the next frame.");
            Assert.IsNull(spawner.Hud);
        }

        [UnityTest]
        public IEnumerator Spawn_WithAnUnassignedHudPrefabCreatesNothingAndLogsAnError()
        {
            CreateStandInPlayer();
            scratchObject = new GameObject("BareHudSpawner");
            var spawner = scratchObject.AddComponent<HudSpawner>(); // hudPrefab left empty on purpose

            LogAssert.Expect(LogType.Error, new Regex("hudPrefab"));
            int created = spawner.Spawn();
            yield return null;

            Assert.AreEqual(0, created);
            Assert.AreEqual(0, spawner.SpawnedCount);
            Assert.AreEqual(0, scratchObject.transform.childCount);
        }

        [UnityTest]
        public IEnumerator SpawningTwiceLeavesOneCanvasAndOneEventSystem()
        {
            GameObject player = CreateStandInPlayer();
            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();

            int first = spawner.Spawn();
            yield return null;
            int second = spawner.Spawn();
            yield return null;

            Assert.AreEqual(first, second, "A second Spawn() returned a different count.");
            Assert.AreEqual(1, second);
            Assert.AreEqual(1, spawnerObject.GetComponentsInChildren<Canvas>(true).Length,
                "After two Spawn() calls the spawner holds more than one Canvas. Spawn() must clear its "
                + "previous output first; two HUDs would draw two title screens over each other.");
            Assert.AreEqual(1, spawnerObject.GetComponentsInChildren<EventSystem>(true).Length,
                "Two EventSystems after a re-spawn; Unity warns and one of them wins at random.");
            Assert.AreSame(spawner.Hud, CanvasRoot().GetComponent<HudBindings>(),
                "Hud must point at the live instance, not the one that was cleared.");
            Assert.IsFalse(player.GetComponent<PlayerMovement>().IsGameplayEnabled,
                "A re-spawned HUD starts at the title again, so it must suspend gameplay input again.");
        }

        [UnityTest]
        public IEnumerator Spawn_HudCarriesNoWorldGeometryForNavigationToExclude()
        {
            CreateStandInPlayer();
            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();
            spawner.Spawn();
            yield return null;

            // WHY THE HUD CARRIES NO NavMeshModifier, measured rather than assumed: NavigationSpawner's
            // bake collects PHYSICS COLLIDERS, and a rebuild re-bakes with the previous phase's objects
            // alive for one frame. A screen-space canvas has nothing a bake could collect, so there is
            // nothing to exclude. The day a collider appears here, this test says so.
            Transform canvas = CanvasRoot();
            Assert.AreEqual(0, canvas.GetComponentsInChildren<Collider>(true).Length,
                "The HUD carries a Collider. It would be baked into the navmesh on a rebuild unless it "
                + "also carried a NavMeshModifier with ignoreFromBuild, which the HUD deliberately omits.");
            Assert.AreEqual(0, canvas.GetComponentsInChildren<Renderer>(true).Length,
                "The HUD carries a world Renderer. UI draws through CanvasRenderers, which are not "
                + "Renderers; a SpriteRenderer or MeshRenderer here would be world content in a HUD.");
        }

        [UnityTest]
        public IEnumerator Spawn_EventSystemReceivesDefaultActionsAtRuntime()
        {
            CreateStandInPlayer();
            HudSpawner spawner = CreateSpawnerFromTheCommittedPrefab();
            spawner.Spawn();
            yield return null;

            var module = CanvasRoot().GetComponentInChildren<InputSystemUIInputModule>(true);
            Assert.IsNotNull(module);
            Assert.IsTrue(module.isActiveAndEnabled, "The input module must be live for clicks to reach buttons.");

            // The prefab serializes NO actions. InputSystemUIInputModule.OnEnable assigns
            // DefaultInputActions when none are set (com.unity.inputsystem 1.14.0,
            // InputSystemUIInputModule.cs:1651-1652); that is what makes the title buttons clickable
            // in the built game without the prefab referencing a package asset.
            Assert.IsNotNull(module.actionsAsset,
                "The input module has no actions, so no mouse click would ever reach a button.");
            Assert.IsNotNull(module.leftClick, "No left-click action: the title's buttons are unclickable.");
            Assert.IsNotNull(module.point, "No point action: the module cannot tell what is under the cursor.");
        }

        [Test]
        public void ReflectionBinder_FailsLoudlyAndNamesTheFieldWhenItIsGone()
        {
            // THE ONE MOST LIKELY TO HAPPEN FOR REAL: NSC-068's file renames a field, and the interim
            // reflection binder must say so in red rather than let the HUD come up unbound.
            scratchObject = new GameObject("BinderTarget");
            scratchObject.SetActive(false);
            var entry = scratchObject.AddComponent<WizardGameEntryController>();
            Transform marker = new GameObject("SpawnMarker").transform;
            marker.SetParent(scratchObject.transform, false);

            // Positive control first, so a binder that never works cannot pass the negative cases.
            Assert.IsTrue(HudReflectionBinder.TrySetPrivate(entry, "worldSpawn", marker),
                "The binder could not set an existing private field; the negatives below prove nothing.");
            FieldInfo worldSpawn = typeof(WizardGameEntryController).GetField("worldSpawn",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(worldSpawn, "WizardGameEntryController no longer has 'worldSpawn'.");
            Assert.AreSame(marker, worldSpawn.GetValue(entry), "The write did not land in the field.");

            // The field name is this test's own input; the error must name the type, the field and
            // the task that retires the binder, in that order.
            const string gone = "fieldThatDoesNotExist";
            LogAssert.Expect(LogType.Error,
                new Regex("WizardGameEntryController[\\s\\S]*" + gone + "[\\s\\S]*NSC-068"));
            Assert.IsFalse(HudReflectionBinder.TrySetPrivate(entry, gone, marker),
                "A missing field must be reported as a failure, not swallowed.");

            // A field that exists but cannot hold the value is the same failure in a different costume.
            LogAssert.Expect(LogType.Error, new Regex("worldSpawn[\\s\\S]*Transform"));
            Assert.IsFalse(HudReflectionBinder.TrySetPrivate(entry, "worldSpawn", scratchObject),
                "A type mismatch must be refused; SetValue would have thrown mid-bind.");
            Assert.AreSame(marker, worldSpawn.GetValue(entry), "A refused write must leave the field untouched.");
        }
    }
}
