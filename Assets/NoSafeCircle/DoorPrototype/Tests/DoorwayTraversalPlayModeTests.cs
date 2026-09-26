using System.Collections;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // NSC-097 VAL-002 (Play Mode half)/VAL-003: every Play-Mode assertion for this task lives
    // here, against the committed DoorPrototype scene's real D1 door - production
    // DoorInteractable, DoorStateSpriteBinder, doorway BoxCollider, and PlayerMovement/
    // CharacterController - rather than a synthetic rig. AC-002's central coupling (doorVisual
    // and the doorway blocker are the SAME GameObject) and AC-001's jamb seal only mean
    // something against the actual composed room geometry these components sit in; the Edit
    // Mode fixture's lightweight in-memory seam does not carry that geometry.
    public sealed class DoorwayTraversalPlayModeTests
    {
        /// <summary>Scene 0 of ProjectSettings/EditorBuildSettings.asset - what a build launches.
        /// Ported from the dying DoorPrototype.unity: see e82bd6f23 for the pilot and its
        /// reasoning (RuntimeWorld builds its hierarchy from GameBootstrap at Play, not from a
        /// serialized scene, so a frame must be spent waiting for it before anything is found).</summary>
        private const string SceneName = "RuntimeWorld";

        [UnityTearDown]
        public IEnumerator UnloadSavedSceneWithoutSaving()
        {
            var scene = SceneManager.GetSceneByName(SceneName);
            if (!scene.IsValid() || !scene.isLoaded) yield break;

            var cleanupScene = SceneManager.CreateScene("DoorwayTraversalTestCleanup");
            SceneManager.SetActiveScene(cleanupScene);
            yield return SceneManager.UnloadSceneAsync(scene);
        }

        // The new world does not exist until GameBootstrap runs: the wait is not optional. See
        // e82bd6f23 (TitleScreenPlayModeTests) for why two frames plus HasBuilt, not a frame count.
        private static IEnumerator WaitForWorldBuilt()
        {
            yield return null;
            GameObject managers = GameObject.Find("GameManagers");
            Assert.IsNotNull(managers,
                "RuntimeWorld.unity carries no GameManagers object, so nothing builds the world.");
            var bootstrap = managers.GetComponent<World.GameBootstrap>();
            Assert.IsNotNull(bootstrap, "GameManagers carries no GameBootstrap.");

            yield return null;
            yield return null;

            Assert.IsTrue(bootstrap.HasBuilt,
                "GameBootstrap had not built after three frames, so every assertion below would "
                + "fail on an empty world rather than on the thing under test. SpawnedCount = "
                + bootstrap.SpawnedCount + ".");
        }

        // VAL-002: DoorInteractable.Complete() deactivates DoorVisual before raising Opened, so
        // the binder's handler must re-enable it before the open sprite is assigned - otherwise
        // the door renders the correct sprite on a hidden object and simply vanishes.
        [UnityTest]
        public IEnumerator SavedScene_Door1Opens_ReactivatesVisualAndRendersOpenSprite()
        {
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName(SceneName);
            var doorRoot = FindRoot(scene, "DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var binder = doorRoot.GetComponent<DoorStateSpriteBinder>();
            var visual = doorRoot.transform.Find("DoorVisual");
            var spriteRenderer = visual.Find("DoorSprite").GetComponent<SpriteRenderer>();

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            yield return null;

            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door.");
            Assert.IsTrue(visual.gameObject.activeInHierarchy,
                "AC-002: HandleOpened must re-enable DoorVisual before the open sprite can be seen - " +
                "not merely assign it to a renderer on a hidden object.");
            Assert.AreSame(GetPrivateSprite(binder, "openSprite"), spriteRenderer.sprite,
                "The door must render the approved open bonestone sprite once opened.");
        }

        // VAL-002: doorVisual and the doorway blocker are the SAME GameObject. A binder that
        // re-enables the collider alongside the object would make an open door block the wizard
        // and stop projectiles again - reintroducing AC-001's defect through this task's own art
        // half. Asserting only that the sprite is visible would pass while the collider came
        // back with its GameObject, so this checks the collider state and a real raycast query
        // (AC-001's "projectile") directly.
        [UnityTest]
        public IEnumerator SavedScene_Door1Opens_BlockerStaysDisabled_AndProjectileRaycastCrossesCleanly()
        {
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName(SceneName);
            var doorRoot = FindRoot(scene, "DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var blocker = doorRoot.transform.Find("DoorVisual").GetComponent<BoxCollider>();

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            yield return null;

            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door.");
            Assert.IsFalse(blocker.enabled,
                "AC-001/AC-002: the doorway blocker (the same GameObject the binder reactivates) must " +
                "stay disabled while the door is open.");

            Physics.SyncTransforms();
            var doorwayCenter = doorRoot.transform.position + new Vector3(0f, 1.25f, 0f);
            var origin = doorwayCenter + new Vector3(0f, 0f, -1f);
            var hit = Physics.Raycast(origin, Vector3.forward, out _, 2f,
                Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);

            Assert.IsFalse(hit,
                "AC-001: a projectile raycast across the open doorway must not be blocked - the same " +
                "query that previously found ten open sightlines through a still-sealed door must now " +
                "find the genuinely open doorway clear.");
        }

        // VAL-002: reaching forward crossing must close, lock, and swap to the locked sprite
        // while keeping DoorVisual active (still the same GameObject the blocker sits on).
        [UnityTest]
        public IEnumerator SavedScene_Door1LockedAfterForwardCrossing_RendersLockedSprite_WithVisualActive()
        {
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName(SceneName);
            var doorRoot = FindRoot(scene, "DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var binder = doorRoot.GetComponent<DoorStateSpriteBinder>();
            var visual = doorRoot.transform.Find("DoorVisual");
            var spriteRenderer = visual.Find("DoorSprite").GetComponent<SpriteRenderer>();
            var playerCollider = FindRoot(scene, "Player").GetComponent<CharacterController>();

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            yield return null;
            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before crossing.");

            InvokeForwardCrossingTriggerEnter(door, playerCollider);
            yield return null;

            Assert.IsTrue(door.IsLocked, "Test setup must actually lock the door.");
            Assert.IsTrue(visual.gameObject.activeInHierarchy);
            Assert.AreSame(GetPrivateSprite(binder, "lockedSprite"), spriteRenderer.sprite);
        }

        // VAL-002: the owner-controlled reset entry point must return D1 to its sealed sprite,
        // with the visual active.
        [UnityTest]
        public IEnumerator SavedScene_Door1ResetAfterOpening_RendersSealedSprite_WithVisualActive()
        {
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName(SceneName);
            var doorRoot = FindRoot(scene, "DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var binder = doorRoot.GetComponent<DoorStateSpriteBinder>();
            var visual = doorRoot.transform.Find("DoorVisual");
            var spriteRenderer = visual.Find("DoorSprite").GetComponent<SpriteRenderer>();

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            yield return null;
            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before reset.");

            door.ResetDoor();
            yield return null;

            Assert.IsFalse(door.IsOpen);
            Assert.IsTrue(visual.gameObject.activeInHierarchy);
            Assert.AreSame(GetPrivateSprite(binder, "sealedSprite"), spriteRenderer.sprite);
        }

        // VAL-002: the canonical scene's actual final door is D5, and D5 is never built
        // directly by DoorPrototypeSceneBuilder.BuildDoor - DoorSequenceBuilder.BuildCanonical
        // clones the already-built, non-final D1 and only sets isFinalDoor on the clone
        // afterward (ConfigureDoor). This exercises that real clone-then-configure path rather
        // than a freshly built D1-shaped door with isFinalDoor set directly, so the sealed
        // win-condition door is proven to render the approved gold-glow final sprite from its
        // actual at-rest state, not merely after a later Locked event.
        [UnityTest]
        public IEnumerator SavedScene_Door5IsFinalAndSealed_RendersFinalSprite_WithVisualActive()
        {
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName(SceneName);
            var doorRoot = FindRoot(scene, "D5");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var binder = doorRoot.GetComponent<DoorStateSpriteBinder>();
            var visual = doorRoot.transform.Find("DoorVisual");
            var spriteRenderer = visual.Find("DoorSprite").GetComponent<SpriteRenderer>();

            Assert.IsTrue(door.IsFinalDoor, "Test setup expects D5 to be the composed scene's final door.");
            Assert.IsFalse(door.IsOpen, "Test setup expects D5 to still be sealed.");
            Assert.IsFalse(door.IsLocked, "Test setup expects D5 to still be sealed, not locked.");
            Assert.IsTrue(visual.gameObject.activeInHierarchy);
            Assert.AreSame(GetPrivateSprite(binder, "finalSprite"), spriteRenderer.sprite,
                "AC-002: a sealed, closed final door built through DoorSequenceBuilder's real " +
                "clone-then-configure path (Instantiate the non-final D1, then set isFinalDoor " +
                "afterward on the clone) must render the approved gold-glow final sprite - not the " +
                "sealed sprite left over from before isFinalDoor was set on this exact door.");
        }

        // VAL-003: production PlayerMovement/CharacterController must actually cross an open D1
        // from the approach (south) side to the forward (north) side without becoming wedged.
        [UnityTest]
        public IEnumerator SavedScene_Door1Open_WizardWalksFromApproachSideToForwardSide()
        {
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName(SceneName);
            var doorRoot = FindRoot(scene, "DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var player = FindRoot(scene, "Player");
            var movement = player.GetComponent<PlayerMovement>();
            var controller = player.GetComponent<CharacterController>();

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            yield return null;
            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before crossing.");

            var doorPosition = doorRoot.transform.position;
            TeleportPlayer(controller, new Vector3(doorPosition.x, player.transform.position.y, doorPosition.z - 1f));

            yield return TraverseTo(
                movement, new Vector3(doorPosition.x, player.transform.position.y, doorPosition.z + 1.5f));
        }

        // VAL-003: same open doorway, the opposite direction (forward side back to approach
        // side), proving the crossing check does not depend on approach direction.
        [UnityTest]
        public IEnumerator SavedScene_Door1Open_WizardWalksFromForwardSideToApproachSide()
        {
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName(SceneName);
            var doorRoot = FindRoot(scene, "DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var player = FindRoot(scene, "Player");
            var movement = player.GetComponent<PlayerMovement>();
            var controller = player.GetComponent<CharacterController>();

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            yield return null;
            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before crossing.");

            var doorPosition = doorRoot.transform.position;
            TeleportPlayer(controller, new Vector3(doorPosition.x, player.transform.position.y, doorPosition.z + 1.5f));

            yield return TraverseTo(
                movement, new Vector3(doorPosition.x, player.transform.position.y, doorPosition.z - 1f));
        }

        // VAL-003: with the door sealed, the same real collider that the raycast check above
        // relies on must still stop the wizard's own approach.
        [UnityTest]
        public IEnumerator SavedScene_Door1Sealed_WizardApproachDoesNotCrossDoorway()
        {
            yield return SceneManager.LoadSceneAsync(SceneName, LoadSceneMode.Single);
            yield return WaitForWorldBuilt();
            var scene = SceneManager.GetSceneByName(SceneName);
            var doorRoot = FindRoot(scene, "DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var player = FindRoot(scene, "Player");
            var movement = player.GetComponent<PlayerMovement>();
            var controller = player.GetComponent<CharacterController>();

            Assert.IsFalse(door.IsOpen, "Test setup must keep the door sealed.");

            var doorPosition = doorRoot.transform.position;
            TeleportPlayer(controller, new Vector3(doorPosition.x, player.transform.position.y, doorPosition.z - 1f));
            movement.EnableGameplayInput();
            movement.CancelRequestedDestination();

            var destination = new Vector3(doorPosition.x, player.transform.position.y, doorPosition.z + 1.5f);
            movement.RequestDestination(destination);
            for (var step = 0; step < 160 && movement.HasActiveDestination; step++)
            {
                movement.Tick(0.05f);
            }

            Assert.Less(player.transform.position.z, doorPosition.z,
                "AC-001: the sealed doorway blocker must actually stop the wizard's real approach before " +
                "the doorway plane, the same collider a projectile raycast relies on.");
        }

        private static IEnumerator TraverseTo(PlayerMovement movement, Vector3 destination)
        {
            movement.EnableGameplayInput();
            movement.CancelRequestedDestination();
            movement.RequestDestination(destination);

            for (var step = 0; step < 160 && movement.HasActiveDestination; step++)
            {
                movement.Tick(0.05f);
            }

            var offset = movement.transform.position - destination;
            offset.y = 0f;
            Assert.Less(offset.magnitude, 0.15f,
                $"Wizard failed to reach {destination} through the open doorway without becoming wedged; " +
                $"stopped at {movement.transform.position}.");
            yield break;
        }

        private static void TeleportPlayer(CharacterController controller, Vector3 position)
        {
            controller.enabled = false;
            controller.transform.position = position;
            controller.enabled = true;
        }

        private static Sprite GetPrivateSprite(DoorStateSpriteBinder binder, string fieldName)
        {
            var field = typeof(DoorStateSpriteBinder).GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private Sprite field named '{fieldName}' on DoorStateSpriteBinder.");
            return (Sprite)field.GetValue(binder);
        }

        private static void InvokeForwardCrossingTriggerEnter(DoorInteractable target, Collider other)
        {
            var method = target.GetType().GetMethod("HandleForwardCrossingTriggerEnter",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(method,
                "Expected a private HandleForwardCrossingTriggerEnter(Collider) method on DoorInteractable.");
            method.Invoke(target, new object[] { other });
        }

        // NOT root-scoped: RuntimeWorld nests every spawned object under its spawner (GameManagers
        // -> <Family>Spawner -> the object), never at the scene root, unlike the old committed
        // scene this helper was written against. Recurses the whole loaded scene instead and keeps
        // the original "expect exactly one" guarantee, which the old SingleOrDefault only
        // ever checked at the root level anyway.
        private static GameObject FindRoot(Scene scene, string name)
        {
            var matches = new System.Collections.Generic.List<GameObject>();
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                CollectByName(root.transform, name, matches);
            }
            Assert.AreEqual(1, matches.Count,
                $"Expected exactly one '{name}' object in loaded scene {scene.path}, found {matches.Count}.");
            return matches[0];
        }

        private static void CollectByName(Transform node, string name, System.Collections.Generic.List<GameObject> matches)
        {
            if (node.name == name) matches.Add(node.gameObject);
            for (int i = 0; i < node.childCount; i++)
            {
                CollectByName(node.GetChild(i), name, matches);
            }
        }
    }
}
