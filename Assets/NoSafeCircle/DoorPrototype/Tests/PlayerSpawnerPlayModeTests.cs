using System;
using System.Collections;
using System.Reflection;
using System.Text.RegularExpressions;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.Navigation;
using NoSafeCircle.DoorPrototype.Player;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Proves the Player lane end to end, AT RUNTIME, with no bake and no scene: the shipped spawner
    // prefab instantiates the authored wizard and camera prefabs, the wizard stands at the Ruined
    // Entry start the layout declares, the camera is Camera.main with the isometric convention and
    // follows him, the runtime scene's placeholder camera is retired rather than left fighting for
    // the display, and a left-click on the floor moves him.
    //
    // THE FIXTURE INSTANTIATES THE SHIPPED PREFAB, NOT A STAND-IN BUILT IN CODE. The serialized
    // references in Resources/Spawners/PlayerSpawner.prefab - and the guids inside Player.prefab -
    // are the load-bearing part of this lane: a wrong guid there is a null field at Play and no
    // wizard, and no in-code fixture could see it. GameBootstrap does exactly this, so the path
    // exercised here is the path Play takes.
    //
    // EVERY EXPECTED VALUE NAMES ITS SOURCE, and none is read from the thing under test. Where the
    // source is internal to the Editor assembly (the builder's camera offset, the canonical wizard
    // look) it is restated here as an independent literal with that provenance, which is the
    // SceneStubTests precedent for the same reason.
    public sealed class PlayerSpawnerPlayModeTests : InputTestFixture
    {
        private const string SpawnerResourcePath = GameBootstrap.SpawnerResourceFolder + "/PlayerSpawner";
        private const string PlayerPrefabResourcePath = "Player/Player";
        private const string WizardIdleAssetPath =
            "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png";
        private const string MainCameraTag = "MainCamera";

        // Unity's CharacterController default, pinned independently by
        // DoorPrototypeSceneBuilderTests:629 (Build_PlayerStartsAtCharacterControllerGroundedHeight).
        private const float UnityDefaultSkinWidth = 0.08f;

        // "The game uses 8": SceneStubTests.ThePlaceholderCameraUsesTheGamesIsometricConvention.
        private const float IsometricOrthographicSize = 8f;

        // DoorPrototypeGlobalSceneBuilder.IsometricCameraOffset, private to the Editor assembly.
        private static readonly Vector3 BuilderCameraOffset = new Vector3(10f, 10f, -10f);

        // The canonical first look: Masculine / White facing south-east. BuildPlayer sets the two
        // enums (builder lines 308-309), WizardSelectionDefinitions[0] is the same pair, and
        // WizardAnimationController.CanonicalInitialDirection is "south-east" (internal).
        private const WizardPresentation CanonicalPresentation = WizardPresentation.Masculine;
        private const WizardSkin CanonicalSkin = WizardSkin.White;
        private const string CanonicalInitialDirection = "south-east";

        // One wizard and one camera per Spawn(), from the lane specification (section 4.4 step 7).
        private const int ObjectsPerSpawn = 2;

        private const int RenderWidth = 800;
        private const int RenderHeight = 600;

        private GameObject floor;
        private GameObject placeholderCameraObject;
        private GameObject spawnerObject;
        private PlayerSpawner spawner;
        private RenderTexture renderTexture;
        private Mouse mouse;

        public override void Setup()
        {
            base.Setup();

            // Both checks BEFORE anything is created: NUnit does not run TearDown when SetUp fails,
            // so a fixture that builds objects and then asserts would leak them into every later
            // fixture.
            GameObject spawnerPrefab = Resources.Load<GameObject>(SpawnerResourcePath);
            Assert.IsNotNull(spawnerPrefab,
                "Resources/" + SpawnerResourcePath + ".prefab did not load. It is the one file that "
                + "wires this lane into GameBootstrap; without it no wizard is ever created.");
            Assert.IsNotNull(spawnerPrefab.GetComponent<PlayerSpawner>(),
                "The spawner prefab carries no PlayerSpawner, so GameBootstrap would warn and skip it.");

            mouse = InputSystem.AddDevice<Mouse>();

            // A floor with its top face at y = 0 under the start: the Rooms lane's floor shape
            // (BoxCollider centre y -0.25, height 0.5). Without it the CharacterController has
            // nothing to stand on and every grounded-height assertion would measure a fall.
            Vector3 start = RuinedEntryLayout.PlayerStart;
            floor = new GameObject("FloorUnderTest");
            var floorCollider = floor.AddComponent<BoxCollider>();
            floorCollider.center = new Vector3(start.x, -0.25f, start.z);
            floorCollider.size = new Vector3(30f, 0.5f, 30f);

            // The runtime scene's placeholder, reproduced: an enabled camera tagged MainCamera with
            // a listener and a follow component whose target is null. Created BEFORE the spawn so
            // the retirement step has something real to retire, and so this fixture can tell a
            // retirement from an absence.
            placeholderCameraObject = new GameObject("PlaceholderMainCamera");
            placeholderCameraObject.tag = MainCameraTag;
            placeholderCameraObject.AddComponent<Camera>();
            placeholderCameraObject.AddComponent<AudioListener>();
            placeholderCameraObject.AddComponent<IsometricCameraFollow>();

            spawnerObject = Object.Instantiate(spawnerPrefab);
            spawnerObject.name = spawnerPrefab.name;
            spawner = spawnerObject.GetComponent<PlayerSpawner>();

            Physics.SyncTransforms();
        }

        public override void TearDown()
        {
            // DestroyImmediate rather than Destroy, deliberately: PlayerMovement.OnDisable is what
            // disables the actions it enabled on the PROJECT input asset, and it has to run before
            // base.TearDown restores the input system. A deferred Destroy would run it a frame late,
            // against a system that has already been reset.
            DestroyNow(ref spawnerObject);
            DestroyNow(ref placeholderCameraObject);
            DestroyNow(ref floor);

            if (renderTexture != null)
            {
                renderTexture.Release();
                Object.DestroyImmediate(renderTexture);
                renderTexture = null;
            }

            spawner = null;
            mouse = null;

            base.TearDown();
        }

        [UnityTest]
        public IEnumerator Spawn_CreatesExactlyOnePlayerAndOneCameraUnderTheSpawner()
        {
            int created = spawner.Spawn();
            yield return null;

            Assert.AreEqual(ObjectsPerSpawn, created,
                "Spawn() reported " + created + " objects; the lane creates one wizard and one camera.");
            Assert.AreEqual(created, spawner.SpawnedCount,
                "Spawn() returned " + created + " but recorded " + spawner.SpawnedCount + ".");

            // Count the OBJECTS, not just the return value: a method can return a number without
            // having created anything, and FindObjectsByType sees the whole scene, so a second
            // wizard left anywhere would show here.
            PlayerMovement[] players = Object.FindObjectsByType<PlayerMovement>(FindObjectsSortMode.None);
            Assert.AreEqual(1, players.Length,
                "The scene holds " + players.Length + " PlayerMovement(s) after one Spawn().");
            Assert.AreSame(spawner.Player, players[0], "spawner.Player is not the wizard in the scene.");
            Assert.AreEqual(PlayerSpawner.PlayerObjectName, players[0].gameObject.name,
                "The wizard is named '" + players[0].gameObject.name + "'; other fixtures look up "
                + "GameObject.Find(\"Player\").");
            Assert.AreSame(spawnerObject.transform, players[0].transform.parent,
                "The wizard is not parented under the spawner, so 'what I spawned' would no longer "
                + "be 'my children' and a re-spawn could not clear it.");

            Camera[] cameras = spawnerObject.GetComponentsInChildren<Camera>(true);
            Assert.AreEqual(1, cameras.Length,
                "The spawner holds " + cameras.Length + " camera(s) after one Spawn().");
            Assert.AreSame(spawner.Camera, cameras[0]);

            Assert.IsNotNull(GameObject.Find("Player"), "GameObject.Find(\"Player\") found nothing.");
            Assert.IsNotNull(GameObject.Find("Player/Visual"),
                "GameObject.Find(\"Player/Visual\") found nothing; WizardAnimationPlayModeTests and "
                + "TitleScreenPlayModeTests look the visual up by that path.");
        }

        [UnityTest]
        public IEnumerator Spawn_PlayerCarriesEveryComponentTheEditorBuilderGaveIt()
        {
            spawner.Spawn();
            yield return null;
            GameObject player = spawner.Player.gameObject;

            // From DoorPrototypeGlobalSceneBuilder.BuildPlayer: the CharacterController and Animator
            // it adds plus its seven out parameters. The Editor assembly cannot be referenced here,
            // so the list is restated with that provenance. A missing entry means a wrong script
            // guid in Player.prefab, which imports without a single complaint.
            Type[] expected =
            {
                typeof(CharacterController), typeof(Animator), typeof(WizardAnimationController),
                typeof(PlayerHealth), typeof(PlayerInteractionController), typeof(PlayerMovement),
                typeof(DebugDamageControl), typeof(PlayerMana), typeof(DebugManaSpendControl)
            };
            foreach (Type type in expected)
            {
                Assert.IsNotNull(player.GetComponent(type),
                    "The spawned wizard has no " + type.Name + ". Player.prefab is missing it or "
                    + "references the wrong script guid.");
            }

            Assert.IsNotNull(player.GetComponentInChildren<FloorRunRestartController>(),
                "No FloorRunRestartController under the wizard, so death would never restart the floor.");
        }

        [UnityTest]
        public IEnumerator Spawn_PlacesThePlayerAtRuinedEntryPlayerStartAtGroundedHeight()
        {
            spawner.Spawn();

            // Measured BEFORE any Update: the pose is what Instantiate placed, before the controller's
            // first grounding step can move it by a physics-resolved hair.
            Vector3 actual = spawner.Player.transform.position;

            Vector3 start = RuinedEntryLayout.PlayerStart;
            GameObject playerPrefab = Resources.Load<GameObject>(PlayerPrefabResourcePath);
            Assert.IsNotNull(playerPrefab, "Resources/Player/Player.prefab did not load.");
            float skinFromAsset = playerPrefab.GetComponent<CharacterController>().skinWidth;

            // Two witnesses that fail differently: the PREFAB's serialized skinWidth (an authored
            // input) and Unity's documented default (a literal). If Player.prefab's m_SkinWidth were
            // misspelled and silently ignored, both would still read 0.08 - but then the Visual's
            // -0.08 literal would still agree with it, which is the relation that matters.
            Assert.AreEqual(UnityDefaultSkinWidth, skinFromAsset, 0.0001f,
                "Player.prefab's CharacterController.skinWidth is " + skinFromAsset
                + ", not Unity's default 0.08 that the Visual's -0.08 offset was authored against.");

            Assert.AreEqual(start.x, actual.x, 0.0001f, "x is not RuinedEntryLayout.PlayerStart.x");
            Assert.AreEqual(skinFromAsset, actual.y, 0.0001f,
                "y is " + actual.y + ", not the grounded height (one skinWidth). Play would open "
                + "with the wizard visibly dropping onto the floor.");
            Assert.AreEqual(start.z, actual.z, 0.0001f, "z is not RuinedEntryLayout.PlayerStart.z");

            // And he STAYS there: three frames of PlayerMovement's grounding step against the floor
            // collider must not turn into a fall.
            yield return null;
            yield return null;
            yield return null;
            Assert.AreEqual(skinFromAsset, spawner.Player.transform.position.y, 0.05f,
                "After three frames the wizard is at y " + spawner.Player.transform.position.y
                + "; he is falling through or floating above the floor.");
        }

        [UnityTest]
        public IEnumerator Spawn_VisualCarriesTheWorldSpriteConventionWithItsFeetOnTheFloor()
        {
            spawner.Spawn();

            Transform visual = spawner.Player.transform.Find("Visual");
            Assert.IsNotNull(visual, "The wizard has no child named 'Visual'.");
            var renderer = visual.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(renderer, "Player/Visual has no SpriteRenderer.");
            Assert.IsNotNull(renderer.sprite, "Player/Visual has a null sprite; it would render nothing.");

            // From the RUNTIME convention class, never the literal the prefab carries.
            Assert.AreEqual(WorldSpriteConvention.SortingLayerName, renderer.sortingLayerName,
                "The wizard is on sorting layer '" + renderer.sortingLayerName + "'. The LAYER is "
                + "compared before the order, so anything left on Default draws behind every wall.");
            Assert.AreEqual(WorldSpriteConvention.SortingOrder, renderer.sortingOrder,
                "The wizard carries sortingOrder " + renderer.sortingOrder + "; any other value "
                + "outranks the camera's transparency axis unconditionally.");
            Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint,
                "The wizard sorts by Center rather than Pivot, its ground-contact point.");

            // The ground-contact convention: the root rides one skinWidth above the floor and the
            // visual is offset back down by exactly that, so the sprite's feet (pivot y 0) sit at
            // world y 0 for the transparency axis. Two prefab literals that must agree; this is
            // the relation, not either number.
            Assert.AreEqual(0f, visual.position.y, 0.0001f,
                "The wizard's feet sit at world y " + visual.position.y + " rather than 0, so the "
                + "isometric sort axis reads him behind a doorway he is standing south of.");
            Assert.Less(Quaternion.Angle(Quaternion.identity, visual.localRotation), 0.01f,
                "The wizard's visual is rotated. Unlike enemies it is NOT camera-tilted (builder "
                + "lines 280-284).");

            yield return null;
        }

        [UnityTest]
        public IEnumerator Spawn_VisualScaleIsUniformAndFillsTheControllerHeight()
        {
            spawner.Spawn();
            Transform visual = spawner.Player.transform.Find("Visual");
            Vector3 scale = visual.localScale;

            Assert.AreEqual(scale.x, scale.y, 0.0001f,
                "The wizard's scale is (" + scale.x + ", " + scale.y + "). Vincent, 2026-09-25: "
                + "'it has its scale wrong... a scale on the y but not on the x'. Uniform, always.");
            Assert.AreEqual(1f, scale.z, 0.0001f, "A world sprite's z scale is 1.");

#if UNITY_EDITOR
            // Expected from the ART and the CONTROLLER, not from the Visual: the wizard's world
            // height is the CharacterController's height (2 units, the capsule he fills), the sprite
            // is 180 px at PPU 180 (bounds 1.0), so the uniform scale must be height / bounds.
            var sprite = UnityEditor.AssetDatabase.LoadAssetAtPath<Sprite>(WizardIdleAssetPath);
            Assert.IsNotNull(sprite, WizardIdleAssetPath + " did not load as a Sprite.");
            float spriteHeight = sprite.bounds.size.y;

            // Second witness that fails differently: import settings rather than mesh bounds.
            float heightFromImport = sprite.rect.height / sprite.pixelsPerUnit;
            Assert.AreEqual(heightFromImport, spriteHeight, 0.0001f,
                "sprite.bounds and the import settings disagree about the wizard's height.");

            float controllerHeight = spawner.Player.GetComponent<CharacterController>().height;
            Assert.AreEqual(controllerHeight / spriteHeight, scale.y, 0.0001f,
                "The visual scale is " + scale.y + "; " + controllerHeight + " units of capsule "
                + "over " + spriteHeight + " units of sprite is " + (controllerHeight / spriteHeight)
                + ". Derived, never a literal, so a PPU change cannot silently stretch him.");

            Assert.AreEqual(sprite, visual.GetComponent<SpriteRenderer>().sprite,
                "The prefab's sprite is not the canonical masculine-light south-east idle.");
#endif
            yield return null;
        }

        [UnityTest]
        public IEnumerator Spawn_MakesTheIsometricCameraMainAndRetiresThePlaceholder()
        {
            var placeholder = placeholderCameraObject.GetComponent<Camera>();
            Assert.IsTrue(placeholder.enabled, "Precondition: the placeholder starts enabled.");
            Assert.AreSame(placeholder, Camera.main,
                "Precondition: before the spawn the placeholder IS Camera.main, so this test can tell "
                + "a retirement from an absence.");

            // The retirement must be SAID, not silent: it is the reminder for the scene's owner.
            LogAssert.Expect(LogType.Warning, new Regex("disabled placeholder camera"));

            spawner.Spawn();
            yield return null;

            Assert.IsNotNull(spawner.Camera, "Spawn() created no camera.");
            Assert.AreSame(spawner.Camera, Camera.main,
                "Camera.main is not the spawned camera. PlayerMovement projects the cursor through "
                + "Camera.main, so clicks would land wherever the placeholder points.");
            Assert.IsFalse(placeholder.enabled,
                "The placeholder camera is still enabled, fighting the real one for the display.");
            Assert.IsFalse(placeholderCameraObject.GetComponent<AudioListener>().enabled,
                "The placeholder's AudioListener is still enabled; Unity warns about two listeners.");

            Assert.IsTrue(spawner.Camera.orthographic, "The camera is perspective; the game is 2:1 dimetric.");
            Assert.AreEqual(IsometricOrthographicSize, spawner.Camera.orthographicSize, 0.001f,
                "orthographicSize is " + spawner.Camera.orthographicSize + "; the game uses 8.");

            // The rotation is compared against the ENEMIES' runtime copy of the same convention -
            // an independent source in a file this lane does not own.
            Quaternion expectedRotation = Quaternion.Euler(EnemyAnimationController.IsometricCameraEulerAngles);
            Assert.Less(Quaternion.Angle(expectedRotation, spawner.Camera.transform.rotation), 0.01f,
                "The camera is rotated " + spawner.Camera.transform.rotation.eulerAngles
                + ", not the isometric (30, -45, 0).");

            Assert.AreEqual(TransparencySortMode.CustomAxis, spawner.Camera.transparencySortMode,
                "transparencySortMode is not CustomAxis; sprites would sort by distance and a door "
                + "renders in front of a wizard standing south of it.");
            AssertVector(IsometricCameraFollow.IsometricTransparencySortAxis,
                spawner.Camera.transparencySortAxis, 0.00001f, "transparencySortAxis");

            AssertVector(BuilderCameraOffset,
                spawner.Camera.transform.position - spawner.Player.transform.position, 0.0001f,
                "camera offset from the wizard");

            Assert.AreEqual(PlayerSpawner.CameraObjectName, spawner.Camera.gameObject.name);
            Assert.IsTrue(spawner.Camera.CompareTag(MainCameraTag), "The spawned camera is not tagged MainCamera.");
            Assert.AreEqual(1, CountEnabledListeners(),
                "There are " + CountEnabledListeners() + " enabled AudioListeners; exactly one may be live.");
        }

        [UnityTest]
        public IEnumerator Camera_FollowsThePlayerWithoutRotating()
        {
            spawner.Spawn();
            yield return null;

            Quaternion rotationBefore = spawner.Camera.transform.rotation;
            var controller = spawner.Player.GetComponent<CharacterController>();
            controller.Move(new Vector3(3f, 0f, 2f));

            // IsometricCameraFollow moves in LateUpdate, so one frame must pass.
            yield return null;

            AssertVector(BuilderCameraOffset,
                spawner.Camera.transform.position - spawner.Player.transform.position, 0.0001f,
                "camera offset after the wizard moved");
            Assert.Less(Quaternion.Angle(rotationBefore, spawner.Camera.transform.rotation), 0.0001f,
                "The camera rotated while following. The isometric orientation is fixed.");
        }

        [UnityTest]
        public IEnumerator ClickToMove_MovesThePlayerTowardTheClickedFloorPoint()
        {
            spawner.Spawn();

            // Batch mode has no Game View: give the spawned camera a fixed pixel surface so
            // WorldToScreenPoint and ScreenPointToRay agree, as PlayerMovementPlayModeTests does.
            renderTexture = new RenderTexture(RenderWidth, RenderHeight, 24);
            renderTexture.Create();
            spawner.Camera.targetTexture = renderTexture;
            yield return null;

            Vector3 origin = spawner.Player.transform.position;
            var target = new Vector3(origin.x + 3f, 0f, origin.z + 3f);
            float leg = HorizontalDistance(origin, target);

            // Expected travel from the AUTHORED speed on the prefab asset (an input), not from the
            // instance: moveSpeed units per second, for one simulated second, clamped to the leg.
            GameObject playerPrefab = Resources.Load<GameObject>(PlayerPrefabResourcePath);
            float moveSpeed = ReadSerializedFloat(playerPrefab.GetComponent<PlayerMovement>(), "moveSpeed");
            Assert.Greater(moveSpeed, 0f, "Player.prefab authors a moveSpeed of " + moveSpeed + ".");
            const float seconds = 1f;
            const int ticks = 60;
            float expectedTravel = Mathf.Min(leg, moveSpeed * seconds);

            // The left button is the measured binding of MoveToCursor in
            // Assets/InputSystem_Actions.inputactions; PointerPosition is <Mouse>/position.
            SetMouse(spawner.Camera.WorldToScreenPoint(target), true);
            for (int i = 0; i < ticks; i++)
            {
                spawner.Player.Tick(seconds / ticks);
            }
            SetMouse(spawner.Camera.WorldToScreenPoint(target), false);

            float remaining = HorizontalDistance(spawner.Player.transform.position, target);
            Assert.Less(remaining, leg - 0.5f,
                "The wizard did not move toward the clicked point at all (" + remaining + " of "
                + leg + " units remain). Either the input asset is not wired, Camera.main is wrong, "
                + "or the click never reached PlayerMovement.");
            Assert.LessOrEqual(remaining, leg - expectedTravel + 0.1f,
                "After " + seconds + " s at " + moveSpeed + " u/s the wizard should be within "
                + (leg - expectedTravel) + " of the target; " + remaining + " remain.");
        }

        [UnityTest]
        public IEnumerator Spawn_CapturesTheInitialPoseSoResetMovementReturnsToIt()
        {
            spawner.Spawn();
            Vector3 pose = spawner.Player.transform.position;
            yield return null;

            var controller = spawner.Player.GetComponent<CharacterController>();
            controller.Move(new Vector3(2f, 0f, 2f));
            Assert.Greater(HorizontalDistance(spawner.Player.transform.position, pose), 1f,
                "Precondition: the wizard actually moved before the reset.");

            spawner.Player.ResetMovement();

            // Rule 4 of the lane spec: spawn AT the pose with the position overload, because
            // PlayerMovement.Awake records initialPosition inside Instantiate. Instantiate-then-move
            // would pass every other test here and restart the wizard at the origin.
            AssertVector(pose, spawner.Player.transform.position, 0.001f, "position after ResetMovement");
        }

        [UnityTest]
        public IEnumerator Death_RestartsTheFloorThroughTheWiredRestartController()
        {
            spawner.Spawn();
            Vector3 pose = spawner.Player.transform.position;
            yield return null;

            var controller = spawner.Player.GetComponent<CharacterController>();
            controller.Move(new Vector3(2f, 0f, 2f));
            var health = spawner.Player.GetComponent<PlayerHealth>();

            // FloorRunRestartController subscribes to PlayerHealth.Died only through its serialized
            // reference - it self-resolves nothing - so a restart proves the prefab wired all four.
            health.TakeDamage(health.MaxHealth);

            AssertVector(pose, spawner.Player.transform.position, 0.001f, "position after death");
            Assert.AreEqual(health.MaxHealth, health.CurrentHealth, 0.0001f,
                "Health was not restored on death; FloorRunRestartController.playerHealth is unwired.");
        }

        [UnityTest]
        public IEnumerator SpawningTwiceLeavesOnePlayerAndOneMainCamera()
        {
            int first = spawner.Spawn();
            PlayerMovement firstPlayer = spawner.Player;
            Camera firstCamera = spawner.Camera;
            yield return null;

            int second = spawner.Spawn();

            // Within the same frame the first pair still exists but is INACTIVE, which is what keeps
            // Camera.main and FindFirstObjectByType (the Enemies and Hud lanes) off the dying pair.
            Assert.IsFalse(firstPlayer.gameObject.activeSelf,
                "The previous wizard is still active in the frame it was replaced.");
            Assert.IsFalse(firstCamera.gameObject.activeSelf,
                "The previous camera is still active in the frame it was replaced.");
            Assert.AreNotSame(firstPlayer, spawner.Player, "spawner.Player still points at the old wizard.");
            Assert.AreSame(spawner.Camera, Camera.main, "Camera.main is not the second camera.");
            yield return null;

            Assert.AreEqual(first, second, "A second Spawn() returned a different count.");
            Assert.AreEqual(1, Object.FindObjectsByType<PlayerMovement>(FindObjectsSortMode.None).Length,
                "Two wizards are alive after two Spawn() calls.");
            Assert.AreEqual(1, spawnerObject.GetComponentsInChildren<PlayerMovement>(true).Length,
                "The previous wizard was hidden rather than destroyed.");
            Assert.AreEqual(1, spawnerObject.GetComponentsInChildren<Camera>(true).Length,
                "The previous camera was hidden rather than destroyed.");
            Assert.AreEqual(1, CountEnabledListeners(), "More than one AudioListener is live.");
            Assert.AreSame(spawner.Camera, Camera.main);
        }

        [UnityTest]
        public IEnumerator Spawn_PlayerRootIsExcludedFromNavMeshRebuilds()
        {
            spawner.Spawn();
            yield return null;

            // ASKED OF THE NAVIGATION LANE'S OWN SEAM, which answers "would my bake collect this?"
            // from the same rules the bake uses (NavMeshRebakeExclusion, branch
            // lane/navigation-runtime). This test assembly references no Unity.AI.Navigation
            // (NSC-089 AC-002 keeps it that way), so NavMeshModifier itself cannot be named here;
            // the seam returns only Collider and bool, which it can.
            //
            // THE CONTROL FIRST: a bare solid collider with no modifier MUST be reported, or an empty
            // result below would be indistinguishable from a query that sees nothing.
            var control = new GameObject("UnmarkedControl");
            try
            {
                control.AddComponent<BoxCollider>();
                Assert.AreEqual(1, NavMeshRebakeExclusion.FindCollected(control.transform).Count,
                    "The control collider was not reported, so FindCollected cannot see colliders and "
                    + "the empty result for the wizard would prove nothing.");
            }
            finally
            {
                Object.DestroyImmediate(control);
            }

            var controller = spawner.Player.GetComponent<CharacterController>();
            Assert.IsTrue(controller.enabled && !controller.isTrigger,
                "Precondition: the wizard's CharacterController is a solid collider the bake would "
                + "otherwise collect.");
            Assert.IsTrue(NavMeshRebakeExclusion.Excludes(controller),
                "The bake would collect the wizard's CharacterController. Player spawns after "
                + "Navigation, so a re-bake (BuildWorld twice) would bake around him as if he were a "
                + "wall, and NavigationSpawner would LogError it by hierarchy path.");

            System.Collections.Generic.List<Collider> collected =
                NavMeshRebakeExclusion.FindCollected(spawner.Player.transform);
            Assert.AreEqual(0, collected.Count,
                "A re-bake would collect " + collected.Count + " collider(s) under the wizard "
                + "(applyToChildren must cover the Visual and the restart controller too).");
        }

        [UnityTest]
        public IEnumerator Spawn_AnimatorResolvesTheCanonicalIdleState()
        {
            spawner.Spawn();
            var wizard = spawner.Player.GetComponent<WizardAnimationController>();
            var animator = spawner.Player.GetComponent<Animator>();
            Assert.IsNotNull(animator.runtimeAnimatorController,
                "The wizard's Animator has no controller; Player.prefab must reference WizardAnimator.controller.");

            Assert.AreEqual(CanonicalPresentation, wizard.Presentation, "Not the canonical presentation.");
            Assert.AreEqual(CanonicalSkin, wizard.Skin, "Not the canonical skin.");
            Assert.AreEqual(CanonicalInitialDirection, wizard.LastDirection, "Not the canonical first facing.");

            // WizardAnimationController.StateName is private; its pattern is
            // Wizard_{presentation}_{skin}_{motion}_{direction}, and the controller has 64 states
            // (4 variants x 8 directions x 2 motions). One frame of Update selects the idle state.
            yield return null;
            string state = "Wizard_" + wizard.Presentation + "_" + wizard.Skin + "_idle_" + wizard.LastDirection;
            Assert.IsTrue(animator.HasState(0, Animator.StringToHash(state)),
                "WizardAnimator.controller has no state '" + state + "', so the wizard would never animate.");
            Assert.AreEqual(state, wizard.CurrentState,
                "After one frame the controller is in '" + wizard.CurrentState + "', not the idle state.");
        }

        [UnityTest]
        public IEnumerator Spawn_WithNoPrefabsAssignedCreatesNothingAndLogsAnError()
        {
            // A spawner with nothing assigned - the shape a broken prefab reference produces at Play.
            var bare = new GameObject("BarePlayerSpawner").AddComponent<PlayerSpawner>();
            try
            {
                LogAssert.Expect(LogType.Error, new Regex("playerPrefab"));
                int created = bare.Spawn();

                Assert.AreEqual(0, created, "A spawner with no prefabs reported creating " + created + ".");
                Assert.AreEqual(0, bare.SpawnedCount, "SpawnedCount must record the refusal as 0, not -1.");
                Assert.AreEqual(0, bare.transform.childCount, "A refused Spawn() still created children.");
                Assert.IsNull(bare.Player);
                Assert.IsNull(bare.Camera);
            }
            finally
            {
                Object.DestroyImmediate(bare.gameObject);
            }

            yield return null;
        }

        private void SetMouse(Vector2 screenPosition, bool leftButtonPressed)
        {
            InputSystem.QueueStateEvent(mouse, new MouseState
            {
                position = screenPosition,
                buttons = leftButtonPressed ? (ushort)(1 << (int)MouseButton.Left) : (ushort)0
            });
            InputSystem.Update();
        }

        private static int CountEnabledListeners()
        {
            int count = 0;
            foreach (AudioListener listener in Object.FindObjectsByType<AudioListener>(
                FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (listener.enabled && listener.gameObject.activeInHierarchy)
                {
                    count++;
                }
            }

            return count;
        }

        private static float HorizontalDistance(Vector3 a, Vector3 b)
        {
            var offset = new Vector3(a.x - b.x, 0f, a.z - b.z);
            return offset.magnitude;
        }

        private static void AssertVector(Vector3 expected, Vector3 actual, float tolerance, string what)
        {
            Assert.AreEqual(expected.x, actual.x, tolerance, what + " x: expected " + expected + ", got " + actual);
            Assert.AreEqual(expected.y, actual.y, tolerance, what + " y: expected " + expected + ", got " + actual);
            Assert.AreEqual(expected.z, actual.z, tolerance, what + " z: expected " + expected + ", got " + actual);
        }

        private static float ReadSerializedFloat(object target, string fieldName)
        {
            FieldInfo field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, "Expected a private serialized field '" + fieldName + "' on "
                + target.GetType().Name + "; a rename must fail here rather than read as zero.");
            return (float)field.GetValue(target);
        }

        private static void DestroyNow(ref GameObject target)
        {
            if (target != null)
            {
                Object.DestroyImmediate(target);
            }

            target = null;
        }
    }
}
