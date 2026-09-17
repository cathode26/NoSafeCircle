using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class WizardAnimationPlayModeTests : InputTestFixture
    {
        private static readonly WizardPresentation[] ExpectedPresentations =
        {
            WizardPresentation.Masculine,
            WizardPresentation.Masculine,
            WizardPresentation.Feminine,
            WizardPresentation.Feminine
        };

        private static readonly WizardSkin[] ExpectedSkins =
        {
            WizardSkin.White,
            WizardSkin.Black,
            WizardSkin.White,
            WizardSkin.Black
        };

        private static readonly ScreenDirection[] ScreenDirections =
        {
            new ScreenDirection("north", new Vector2(0f, 1f)),
            new ScreenDirection("north-east", new Vector2(0.70710677f, 0.70710677f)),
            new ScreenDirection("east", new Vector2(1f, 0f)),
            new ScreenDirection("south-east", new Vector2(0.70710677f, -0.70710677f)),
            new ScreenDirection("south", new Vector2(0f, -1f)),
            new ScreenDirection("south-west", new Vector2(-0.70710677f, -0.70710677f)),
            new ScreenDirection("west", new Vector2(-1f, 0f)),
            new ScreenDirection("north-west", new Vector2(-0.70710677f, 0.70710677f))
        };

        private Mouse mouseDevice;
        private RenderTexture testRenderTexture;
        private Camera renderCamera;
        private InputActionAsset testMovementActions;

        public override void Setup()
        {
            base.Setup();
            mouseDevice = InputSystem.AddDevice<Mouse>();
            testRenderTexture = new RenderTexture(800, 600, 24);
            testRenderTexture.Create();
        }

        public override void TearDown()
        {
            ReleaseTestMovementActions();
            DetachTestRenderTexture();
            if (testRenderTexture != null)
            {
                testRenderTexture.Release();
                UnityEngine.Object.Destroy(testRenderTexture);
            }

            testRenderTexture = null;
            renderCamera = null;
            mouseDevice = null;
            base.TearDown();
        }

        [UnitySetUp]
        public IEnumerator LoadDoorPrototypeScene()
        {
            yield return SceneManager.LoadSceneAsync("DoorPrototype", LoadSceneMode.Single);
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            Assert.IsTrue(scene.IsValid() && scene.isLoaded);
        }

        [UnityTearDown]
        public IEnumerator UnloadDoorPrototypeSceneWithoutSaving()
        {
            Scene scene = SceneManager.GetSceneByName("DoorPrototype");
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            Scene cleanupScene = SceneManager.CreateScene("WizardAnimationTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }

        [Test]
        public void PlayerVisualHasOneWizardAnimationDriverAndRetainsGroundContact()
        {
            var player = GameObject.Find("Player");
            Assert.IsNotNull(player);
            Assert.AreEqual(1, player.GetComponents<WizardAnimationController>().Length);
            Assert.IsNotNull(player.GetComponent<Animator>());
            var visual = player.transform.Find("Visual");
            Assert.IsNotNull(visual);
            var characterController = player.GetComponent<CharacterController>();
            Assert.IsNotNull(characterController);
            Assert.That(
                visual.position.y,
                Is.EqualTo(player.transform.position.y - characterController.skinWidth).Within(0.001f));
        }

        // NSC-062 AC-003/AC-004 and VAL-003: the presentation owner applies both serialized
        // choices atomically, refreshes the selected idle state immediately, and leaves every
        // Player gameplay owner and collision property unchanged.
        [Test]
        public void ApplyPresentation_RefreshesSelectedIdleWithoutChangingPlayerGameplayState()
        {
            GameObject player = GameObject.Find("Player");
            Assert.IsNotNull(player);

            WizardAnimationController wizard = player.GetComponent<WizardAnimationController>();
            Animator animator = player.GetComponent<Animator>();
            SpriteRenderer renderer = player.transform.Find("Visual")?.GetComponent<SpriteRenderer>();
            PlayerMovement movement = player.GetComponent<PlayerMovement>();
            PlayerInteractionController interaction = player.GetComponent<PlayerInteractionController>();
            CharacterController characterController = player.GetComponent<CharacterController>();

            Assert.IsNotNull(wizard);
            Assert.IsNotNull(animator);
            Assert.IsNotNull(renderer);
            Assert.IsNotNull(renderer.sprite);
            Assert.IsNotNull(movement);
            Assert.IsNotNull(interaction);
            Assert.IsNotNull(characterController);

            Vector3 originalPosition = player.transform.position;
            Quaternion originalRotation = player.transform.rotation;
            Vector3 originalScale = player.transform.localScale;
            float originalHeight = characterController.height;
            float originalRadius = characterController.radius;
            bool originalMovementState = movement.IsGameplayEnabled;
            bool originalInteractionState = interaction.IsGameplayEnabled;
            Sprite originalSprite = renderer.sprite;

            wizard.ApplyPresentation(WizardPresentation.Feminine, WizardSkin.Black);

            const string expectedState = "Wizard_Feminine_Black_idle_south-east";
            Assert.AreEqual(WizardPresentation.Feminine, wizard.Presentation);
            Assert.AreEqual(WizardSkin.Black, wizard.Skin);
            Assert.AreEqual(expectedState, wizard.CurrentState);
            Assert.IsTrue(animator.GetCurrentAnimatorStateInfo(0).IsName(expectedState));
            Assert.AreNotSame(originalSprite, renderer.sprite,
                "The selected idle Sprite must refresh in the same ApplyPresentation call.");

            Assert.AreEqual(originalPosition, player.transform.position);
            Assert.AreEqual(originalRotation, player.transform.rotation);
            Assert.AreEqual(originalScale, player.transform.localScale);
            Assert.AreEqual(originalHeight, characterController.height);
            Assert.AreEqual(originalRadius, characterController.radius);
            Assert.AreEqual(originalMovementState, movement.IsGameplayEnabled);
            Assert.AreEqual(originalInteractionState, interaction.IsGameplayEnabled);
            Assert.AreSame(movement, player.GetComponent<PlayerMovement>());
            Assert.AreSame(interaction, player.GetComponent<PlayerInteractionController>());
        }

        // NSC-062 AC-003 regression: invalid values fail before either presentation field changes.
        [Test]
        public void ApplyPresentation_InvalidChoiceIsRejectedAtomically()
        {
            WizardAnimationController wizard =
                GameObject.Find("Player")?.GetComponent<WizardAnimationController>();
            Assert.IsNotNull(wizard);

            WizardPresentation originalPresentation = wizard.Presentation;
            WizardSkin originalSkin = wizard.Skin;

            Assert.Throws<ArgumentOutOfRangeException>(() =>
                wizard.ApplyPresentation((WizardPresentation)999, WizardSkin.White));
            Assert.AreEqual(originalPresentation, wizard.Presentation);
            Assert.AreEqual(originalSkin, wizard.Skin);

            Assert.Throws<ArgumentOutOfRangeException>(() =>
                wizard.ApplyPresentation(WizardPresentation.Feminine, (WizardSkin)999));
            Assert.AreEqual(originalPresentation, wizard.Presentation);
            Assert.AreEqual(originalSkin, wizard.Skin);
        }

        [TestCase(1f, 0f, "north-east")]
        [TestCase(0f, 1f, "south-east")]
        [TestCase(-1f, 0f, "south-west")]
        [TestCase(0f, -1f, "north-west")]
        [TestCase(1f, 1f, "east")]
        [TestCase(1f, -1f, "north")]
        [TestCase(-1f, 1f, "south")]
        [TestCase(-1f, -1f, "west")]
        public void DirectionFor_MapsWorldAxesAndDiagonalsToScreenDirections(
            float worldX, float worldZ, string expectedDirection)
        {
            Assert.AreEqual(expectedDirection,
                InvokeDirectionFor(new Vector3(worldX, 0f, worldZ)));
        }

        [Test]
        public void DirectionFor_ResolvesEveryExactSectorBoundaryDeterministically()
        {
            float[] boundaryAngles =
            {
                22.5f,
                -22.5f,
                -67.5f,
                -112.5f,
                -157.5f,
                157.5f,
                112.5f,
                67.5f
            };
            string[] expectedDirections =
            {
                "north-east",
                "south-east",
                "south-east",
                "south-west",
                "south-west",
                "north-west",
                "north-west",
                "north-east"
            };

            for (int index = 0; index < boundaryAngles.Length; index++)
            {
                Vector3 movement = WorldMovementForScreenAngle(boundaryAngles[index]);
                Assert.AreEqual(expectedDirections[index], InvokeDirectionFor(movement));
                Assert.AreEqual(expectedDirections[index], InvokeDirectionFor(movement));
            }
        }

        // NSC-075 AC-001/AC-004 and VAL-002/VAL-003: the real title/selection flow applies
        // every wizard to the one existing Player at PlayerSpawn. Mouse movement and door
        // selection remain live, then all eight held screen directions keep the expected walk
        // state progressing through alternating orthogonal noise and retain that facing on idle.
        [UnityTest]
        public IEnumerator EachConfirmedWizard_LobbyEntrySupportsStableEightDirectionAnimationAndMouseInput()
        {
            for (int optionIndex = 0; optionIndex < ExpectedPresentations.Length; optionIndex++)
            {
                if (optionIndex > 0)
                {
                    yield return SceneManager.LoadSceneAsync("DoorPrototype", LoadSceneMode.Single);
                }

                Scene scene = SceneManager.GetSceneByName("DoorPrototype");
                Assert.IsTrue(scene.IsValid() && scene.isLoaded);
                GameObject player = FindRoot(scene, "Player");
                GameObject playerSpawn = FindRoot(scene, "PlayerSpawn");
                GameObject canvas = FindRoot(scene, "Canvas");
                Camera camera = FindRoot(scene, "Main Camera").GetComponent<Camera>();
                DoorInteractable door = FindRoot(scene, "DoorRoot").GetComponent<DoorInteractable>();
                WizardSelectionController selection = canvas.GetComponent<WizardSelectionController>();
                WizardGameEntryController entry = canvas.GetComponent<WizardGameEntryController>();
                WizardAnimationController wizard = player.GetComponent<WizardAnimationController>();
                PlayerMovement movement = player.GetComponent<PlayerMovement>();
                PlayerInteractionController interaction = player.GetComponent<PlayerInteractionController>();
                Animator animator = player.GetComponent<Animator>();
                CharacterController characterController = player.GetComponent<CharacterController>();
                SpriteRenderer renderer = player.transform.Find("Visual")?.GetComponent<SpriteRenderer>();

                Assert.IsNotNull(camera);
                Assert.IsNotNull(door);
                Assert.IsNotNull(selection);
                Assert.IsNotNull(entry);
                Assert.IsNotNull(wizard);
                Assert.IsNotNull(movement);
                Assert.IsNotNull(interaction);
                Assert.IsNotNull(animator);
                Assert.IsNotNull(characterController);
                Assert.IsNotNull(renderer);
                Assert.IsNotNull(player.GetComponent<PlayerHealth>());
                Assert.IsNotNull(player.GetComponent<PlayerMana>());

                Component[] originalComponents = player.GetComponents<Component>();
                Collider[] originalColliders = player.GetComponents<Collider>();
                Vector3 originalScale = player.transform.localScale;
                float originalHeight = characterController.height;
                float originalRadius = characterController.radius;
                string originalSortingLayer = renderer.sortingLayerName;
                int originalSortingOrder = renderer.sortingOrder;
                SpriteSortPoint originalSortPoint = renderer.spriteSortPoint;

                BeginSelection(canvas);
                selection.GetOption(optionIndex).Button.onClick.Invoke();
                ConfirmSelection(canvas);

                Assert.IsTrue(entry.HasEnteredGameplay);
                Assert.AreEqual(1, entry.GameplayEntryCount);
                ConfirmedWizardSelection expectedSelection = new ConfirmedWizardSelection(
                    ExpectedPresentations[optionIndex], ExpectedSkins[optionIndex]);
                Assert.AreEqual(expectedSelection, entry.AppliedSelection);
                Assert.AreEqual(expectedSelection, selection.ConfirmedSelection);
                Assert.AreEqual(ExpectedPresentations[optionIndex], wizard.Presentation);
                Assert.AreEqual(ExpectedSkins[optionIndex], wizard.Skin);
                Assert.AreEqual(playerSpawn.transform.position, player.transform.position);
                Assert.AreEqual(playerSpawn.transform.rotation, player.transform.rotation);
                Assert.AreSame(player, FindRoot(scene, "Player"));
                Assert.AreEqual(1, scene.GetRootGameObjects().Count(root => root.name == "Player"));
                Assert.IsTrue(movement.IsGameplayEnabled);
                Assert.IsTrue(interaction.IsGameplayEnabled);
                CollectionAssert.AreEqual(originalComponents, player.GetComponents<Component>());
                CollectionAssert.AreEqual(originalColliders, player.GetComponents<Collider>());
                Assert.AreEqual(originalScale, player.transform.localScale);
                Assert.AreEqual(originalHeight, characterController.height);
                Assert.AreEqual(originalRadius, characterController.radius);
                Assert.AreEqual(originalSortingLayer, renderer.sortingLayerName);
                Assert.AreEqual(originalSortingOrder, renderer.sortingOrder);
                Assert.AreEqual(originalSortPoint, renderer.spriteSortPoint);

                ConfigureMouseInput(movement, camera);
                yield return null;
                SetMouse(Vector2.zero, false);
                interaction.ResetInteraction();
                movement.ResetMovement();
                movement.Tick(0.02f);

                Vector3 movementTarget = playerSpawn.transform.position + new Vector3(1f, 0f, -1f);
                SetMouse(camera.WorldToScreenPoint(movementTarget), true);
                movement.Tick(0.02f);
                Assert.IsTrue(movement.HasPointerWorldTarget,
                    "The confirmed wizard must retain the scene's mouse pointer projection.");
                Assert.IsTrue(movement.HasActiveDestination,
                    "The confirmed wizard must retain mouse-directed movement input.");

                SetMouse(camera.WorldToScreenPoint(movementTarget), false);
                movement.Tick(0.02f);
                movement.CancelRequestedDestination();
                SetMouse(camera.WorldToScreenPoint(door.SelectionPoint), true);
                movement.Tick(0.02f);
                Assert.AreSame(door, interaction.PendingDoor,
                    "The confirmed wizard must retain mouse-driven door selection.");
                Assert.IsTrue(interaction.HasLockedDoorInteraction);

                SetMouse(camera.WorldToScreenPoint(door.SelectionPoint), false);
                movement.Tick(0.02f);
                interaction.ResetInteraction();
                movement.ResetMovement();
                movement.enabled = false;
                yield return null;

                yield return DriveEveryScreenDirection(
                    player,
                    wizard,
                    animator,
                    ExpectedPresentations[optionIndex],
                    ExpectedSkins[optionIndex]);

                ConfirmSelection(canvas);
                selection.ConfirmSelection();
                movement.SuspendGameplayInput();
                interaction.SuspendGameplayInput();
                entry.EnterWorld(expectedSelection);
                Assert.AreEqual(1, entry.GameplayEntryCount,
                    "Confirmation must remain a one-shot handoff without a fallback or second Player.");
                Assert.IsFalse(movement.IsGameplayEnabled,
                    "A duplicate entry must not issue another movement input-enable call.");
                Assert.IsFalse(interaction.IsGameplayEnabled,
                    "A duplicate entry must not issue another interaction input-enable call.");
                Assert.AreEqual(1, scene.GetRootGameObjects().Count(root => root.name == "Player"));
            }
        }

        // NSC-070 regression plus NSC-075 AC-001/VAL-002: deterministic collision/transform
        // noise at each sector boundary must not oscillate a held facing between adjacent states.
        [Test]
        public void DirectionFor_RetainsPriorDirectionAtEverySectorBoundary()
        {
            MethodInfo directionMethod = typeof(WizardAnimationController).GetMethod(
                "StableDirectionFor", BindingFlags.Static | BindingFlags.NonPublic,
                null, new[] { typeof(Vector3), typeof(string) }, null);
            Assert.IsNotNull(directionMethod,
                "The direction classifier needs a prior-facing seam for boundary hysteresis.");

            string[] priorDirections =
            {
                "north-east", "east", "south-east", "south",
                "south-west", "west", "north-west", "north"
            };

            foreach (string priorDirection in priorDirections)
            {
                string direction = priorDirection;
                for (int sampleIndex = 0; sampleIndex < 6; sampleIndex++)
                {
                    float offset = sampleIndex % 2 == 0 ? -0.05f : 0.05f;
                    Vector3 sample = BoundaryMovementFor(priorDirection, offset);
                    direction = (string)directionMethod.Invoke(
                        null, new object[] { sample, direction });
                    Assert.AreEqual(priorDirection, direction,
                        $"Boundary noise changed held facing from {priorDirection}.");
                }
            }

            string switchedDirection = (string)directionMethod.Invoke(
                null, new object[] { BoundaryMovementFor("north-east", -0.2f), "north-east" });
            Assert.AreEqual("east", switchedDirection,
                "Movement beyond the hysteresis band must switch to the adjacent sector.");
        }

        // NSC-070 VAL-002: held movement keeps its Animator state and time, then idle
        // retains the last meaningful facing across real MonoBehaviour Update frames.
        [UnityTest]
        public IEnumerator HeldBoundaryMovementDoesNotRestartAndIdleRetainsFacing()
        {
            GameObject player = GameObject.Find("Player");
            Assert.IsNotNull(player);

            PlayerMovement movement = player.GetComponent<PlayerMovement>();
            WizardAnimationController wizard = player.GetComponent<WizardAnimationController>();
            Animator animator = player.GetComponent<Animator>();
            Assert.IsNotNull(movement);
            Assert.IsNotNull(wizard);
            Assert.IsNotNull(animator);

            movement.enabled = false;
            yield return null;

            // Prime the intended X-axis facing before exercising ambiguous boundary noise.
            // With no prior movement, retaining the canonical initial Z-axis facing is valid.
            player.transform.position += new Vector3(1f, 0f, 0f);
            yield return null;
            const string expectedWalkState = "Wizard_Masculine_White_walk_north-east";
            Assert.AreEqual(expectedWalkState, wizard.CurrentState);
            animator.Update(0f);
            Assert.IsTrue(animator.GetCurrentAnimatorStateInfo(0).IsName(expectedWalkState));
            animator.Update(0.1f);
            float firstWalkTime = animator.GetCurrentAnimatorStateInfo(0).normalizedTime;

            player.transform.position += new Vector3(1f, 0f, 0.4143f);
            yield return null;
            Assert.AreEqual(expectedWalkState, wizard.CurrentState);
            animator.Update(0f);
            Assert.IsTrue(animator.GetCurrentAnimatorStateInfo(0).IsName(expectedWalkState));
            animator.Update(0.1f);
            float secondWalkTime = animator.GetCurrentAnimatorStateInfo(0).normalizedTime;
            Assert.Greater(secondWalkTime, firstWalkTime,
                "A held walk state must advance Animator time instead of restarting.");

            yield return null;
            Assert.AreEqual("Wizard_Masculine_White_idle_north-east", wizard.CurrentState);
            Assert.AreEqual("north-east", wizard.LastDirection);
        }

        private static IEnumerator DriveEveryScreenDirection(
            GameObject player,
            WizardAnimationController wizard,
            Animator animator,
            WizardPresentation presentation,
            WizardSkin skin)
        {
            foreach (ScreenDirection direction in ScreenDirections)
            {
                string expectedWalkState =
                    $"Wizard_{presentation}_{skin}_walk_{direction.Name}";
                float previousWalkTime = -1f;
                for (int sampleIndex = 0; sampleIndex < 4; sampleIndex++)
                {
                    player.transform.position += HeldMovement(direction.Vector, sampleIndex);
                    yield return null;

                    Assert.AreEqual(expectedWalkState, wizard.CurrentState,
                        $"Unexpected held state for {presentation}/{skin}/{direction.Name}.");
                    Assert.AreEqual(direction.Name, wizard.LastDirection);
                    animator.Update(0f);
                    Assert.IsTrue(animator.GetCurrentAnimatorStateInfo(0).IsName(expectedWalkState));
                    animator.Update(0.05f);
                    float walkTime = animator.GetCurrentAnimatorStateInfo(0).normalizedTime;
                    if (previousWalkTime >= 0f)
                    {
                        Assert.Greater(walkTime, previousWalkTime,
                            $"Held {direction.Name} animation restarted for {presentation}/{skin}.");
                    }

                    previousWalkTime = walkTime;
                }

                yield return null;
                string expectedIdleState =
                    $"Wizard_{presentation}_{skin}_idle_{direction.Name}";
                Assert.AreEqual(expectedIdleState, wizard.CurrentState,
                    $"Idle did not retain {direction.Name} for {presentation}/{skin}.");
                Assert.AreEqual(direction.Name, wizard.LastDirection);
                animator.Update(0f);
                Assert.IsTrue(animator.GetCurrentAnimatorStateInfo(0).IsName(expectedIdleState));
            }
        }

        private void ConfigureMouseInput(PlayerMovement movement, Camera camera)
        {
            ReleaseTestMovementActions();
            camera.targetTexture = testRenderTexture;
            renderCamera = camera;
            SetPrivateField(movement, "mainCamera", camera);

            InputActionAsset sceneMovementActions =
                GetPrivateField<InputActionAsset>(movement, "inputActions");
            testMovementActions = UnityEngine.Object.Instantiate(sceneMovementActions);
            InputActionMap playerMap = testMovementActions.FindActionMap("Player", true);
            playerMap.devices = new InputDevice[] { mouseDevice };
            InputAction pointerPosition = playerMap.FindAction("PointerPosition", true);
            InputAction moveToCursor = playerMap.FindAction("MoveToCursor", true);
            SetPrivateField(movement, "inputActions", testMovementActions);
            SetPrivateField(movement, "pointerPositionAction", pointerPosition);
            SetPrivateField(movement, "moveToCursorAction", moveToCursor);
            playerMap.Enable();
        }

        private void ReleaseTestMovementActions()
        {
            if (testMovementActions == null) return;

            testMovementActions.Disable();
            UnityEngine.Object.DestroyImmediate(testMovementActions);
            testMovementActions = null;
        }

        private void DetachTestRenderTexture()
        {
            if (renderCamera != null && renderCamera.targetTexture == testRenderTexture)
            {
                renderCamera.targetTexture = null;
            }
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

        private static GameObject FindRoot(Scene scene, string name)
        {
            GameObject result = scene.GetRootGameObjects().SingleOrDefault(root => root.name == name);
            Assert.IsNotNull(result, $"Expected one '{name}' root in {scene.path}.");
            return result;
        }

        private static void BeginSelection(GameObject canvas)
        {
            Button startButton = canvas.transform
                .Find("TitleScreen/TitleCard/StartGameButton")?.GetComponent<Button>();
            Assert.IsNotNull(startButton);
            startButton.onClick.Invoke();
        }

        private static void ConfirmSelection(GameObject canvas)
        {
            Button confirmButton = canvas.transform
                .Find("WizardSelectionScreen/ConfirmSelectionButton")?.GetComponent<Button>();
            Assert.IsNotNull(confirmButton);
            confirmButton.onClick.Invoke();
        }

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            FieldInfo field = target.GetType().GetField(
                fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            field.SetValue(target, value);
        }

        private static T GetPrivateField<T>(object target, string fieldName) where T : class
        {
            FieldInfo field = target.GetType().GetField(
                fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private field named '{fieldName}' on {target.GetType().Name}.");
            T value = field.GetValue(target) as T;
            Assert.IsNotNull(value, $"Expected '{fieldName}' on {target.GetType().Name} to contain {typeof(T).Name}.");
            return value;
        }

        private static string InvokeDirectionFor(Vector3 movement)
        {
            MethodInfo directionMethod = typeof(WizardAnimationController).GetMethod(
                "DirectionFor", BindingFlags.Static | BindingFlags.NonPublic);
            Assert.IsNotNull(directionMethod);
            return (string)directionMethod.Invoke(null, new object[] { movement });
        }

        private static Vector3 HeldMovement(Vector2 screenDirection, int sampleIndex)
        {
            Vector2 perpendicular = new Vector2(-screenDirection.y, screenDirection.x);
            float noise = sampleIndex % 2 == 0 ? 0.0005f : -0.0005f;
            Vector2 screenMovement = (screenDirection + perpendicular * noise) * 0.2f;
            return ScreenToWorldMovement(screenMovement);
        }

        private static Vector3 WorldMovementForScreenAngle(float angle)
        {
            float radians = angle * Mathf.Deg2Rad;
            return ScreenToWorldMovement(new Vector2(Mathf.Cos(radians), Mathf.Sin(radians)));
        }

        private static Vector3 ScreenToWorldMovement(Vector2 screenMovement)
        {
            return new Vector3(
                (screenMovement.x + screenMovement.y) * 0.5f,
                0f,
                (screenMovement.x - screenMovement.y) * 0.5f);
        }

        private static Vector3 BoundaryMovementFor(string direction, float offset)
        {
            float angle = 0f;
            switch (direction)
            {
                case "north-east": angle = 22.5f; break;
                case "east": angle = -22.5f; break;
                case "south-east": angle = -67.5f; break;
                case "south": angle = -112.5f; break;
                case "south-west": angle = -157.5f; break;
                case "west": angle = 157.5f; break;
                case "north-west": angle = 112.5f; break;
                case "north": angle = 67.5f; break;
                default: throw new ArgumentOutOfRangeException(nameof(direction));
            }

            float radians = (angle + offset) * Mathf.Deg2Rad;
            float screenX = Mathf.Cos(radians);
            float screenY = Mathf.Sin(radians);
            return new Vector3((screenX + screenY) * 0.5f, 0f,
                (screenX - screenY) * 0.5f);
        }

        private readonly struct ScreenDirection
        {
            public readonly string Name;
            public readonly Vector2 Vector;

            public ScreenDirection(string name, Vector2 vector)
            {
                Name = name;
                Vector = vector;
            }
        }
    }
}
