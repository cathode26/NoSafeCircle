using System;
using System.Reflection;
using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    public sealed class WizardAnimationPlayModeTests
    {
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
            Assert.That(visual.position.y, Is.EqualTo(player.transform.position.y).Within(0.001f));
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

        [TestCase(1f, 0.0001f, "north-east")]
        [TestCase(1f, -0.0001f, "north-east")]
        [TestCase(-1f, 0.0001f, "south-west")]
        [TestCase(-1f, -0.0001f, "south-west")]
        [TestCase(0.0001f, 1f, "south-east")]
        [TestCase(-0.0001f, 1f, "south-east")]
        [TestCase(0.0001f, -1f, "north-west")]
        [TestCase(-0.0001f, -1f, "north-west")]
        public void DirectionFor_UsesDominantCameraBasisWhenOrthogonalNoiseChanges(
            float worldX, float worldZ, string expectedDirection)
        {
            Assert.AreEqual(expectedDirection,
                InvokeDirectionFor(new Vector3(worldX, 0f, worldZ)));
        }

        [Test]
        public void DirectionFor_RemainsStableAcrossHeldFramesForEveryWizardVariant()
        {
            WizardPresentation[] presentations =
                { WizardPresentation.Masculine, WizardPresentation.Feminine };
            WizardSkin[] skins = { WizardSkin.White, WizardSkin.Black };
            Vector3[][] heldSamplesByDirection =
            {
                new[]
                {
                    new Vector3(1f, 0f, 0.0001f),
                    new Vector3(1f, 0f, -0.0001f),
                    new Vector3(1f, 0f, 0.0001f),
                    new Vector3(1f, 0f, -0.0001f)
                },
                new[]
                {
                    new Vector3(-1f, 0f, 0.0001f),
                    new Vector3(-1f, 0f, -0.0001f),
                    new Vector3(-1f, 0f, 0.0001f),
                    new Vector3(-1f, 0f, -0.0001f)
                },
                new[]
                {
                    new Vector3(0.0001f, 0f, 1f),
                    new Vector3(-0.0001f, 0f, 1f),
                    new Vector3(0.0001f, 0f, 1f),
                    new Vector3(-0.0001f, 0f, 1f)
                },
                new[]
                {
                    new Vector3(0.0001f, 0f, -1f),
                    new Vector3(-0.0001f, 0f, -1f),
                    new Vector3(0.0001f, 0f, -1f),
                    new Vector3(-0.0001f, 0f, -1f)
                }
            };
            string[] expectedDirections = { "north-east", "south-west", "south-east", "north-west" };

            foreach (WizardPresentation presentation in presentations)
            {
                foreach (WizardSkin skin in skins)
                {
                    for (int directionIndex = 0; directionIndex < heldSamplesByDirection.Length; directionIndex++)
                    {
                        string previousDirection = null;
                        foreach (Vector3 sample in heldSamplesByDirection[directionIndex])
                        {
                            string direction = InvokeDirectionFor(sample);
                            Assert.AreEqual(expectedDirections[directionIndex], direction,
                                $"Unexpected direction for {presentation}/{skin}.");
                            if (previousDirection != null)
                                Assert.AreEqual(previousDirection, direction,
                                    $"Facing changed during held movement for {presentation}/{skin}.");
                            previousDirection = direction;
                        }
                    }
                }
            }
        }

        // NSC-070 regression-only invariant: deterministic collision/transform noise at the
        // equal-component boundary must not oscillate a held facing between adjacent states.
        [Test]
        public void DirectionFor_RetainsPriorAxisAtEqualComponentBoundary()
        {
            MethodInfo directionMethod = typeof(WizardAnimationController).GetMethod(
                "StableDirectionFor", BindingFlags.Static | BindingFlags.NonPublic,
                null, new[] { typeof(Vector3), typeof(string) }, null);
            Assert.IsNotNull(directionMethod,
                "The direction classifier needs a prior-facing seam for boundary hysteresis.");

            string direction = "north-east";
            Vector3[] noisyHeldSamples =
            {
                new Vector3(1f, 0f, 1f),
                new Vector3(1f, 0f, 1.0001f),
                new Vector3(1f, 0f, 1f),
                new Vector3(1f, 0f, 1.0001f)
            };

            foreach (Vector3 sample in noisyHeldSamples)
            {
                direction = (string)directionMethod.Invoke(null, new object[] { sample, direction });
                Assert.AreEqual("north-east", direction,
                    "Equal-component noise must retain the held world-axis facing.");
            }
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

            player.transform.position += new Vector3(1f, 0f, 1.0001f);
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

        private static string InvokeDirectionFor(Vector3 movement)
        {
            MethodInfo directionMethod = typeof(WizardAnimationController).GetMethod(
                "DirectionFor", BindingFlags.Static | BindingFlags.NonPublic);
            Assert.IsNotNull(directionMethod);
            return (string)directionMethod.Invoke(null, new object[] { movement });
        }
    }
}
