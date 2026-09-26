using NoSafeCircle.DoorPrototype.World;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Hud
{
    /// <summary>
    /// Phase 6, last: instantiates the authored HUD (Resources/Hud/Hud.prefab) and binds it to the
    /// player that phase 4 created. One Canvas, or nothing - never a half-bound HUD.
    /// </summary>
    /// <remarks>
    /// <para>
    /// IT RUNS LAST ON PURPOSE. <see cref="SpawnPhase.Hud"/> is 6 because the HUD binds to a player that
    /// must already exist; the phase order is the contract between seven lanes and is not reordered
    /// here. The player is found by type at spawn time, the mechanism DoorInteractionUI, DemoRunFlow
    /// and the enemy components already use, so this lane never references another lane's file.
    /// </para>
    /// <para>
    /// NO NavMeshModifier, AND THE REASON IS MEASURED RATHER THAN ASSUMED. The rule for anything that
    /// spawns after Navigation is to carry ignoreFromBuild so a re-bake excludes it - but the bake reads
    /// PHYSICS COLLIDERS (GameplayNavigationSurface sets useGeometry = PhysicsColliders), and a
    /// ScreenSpaceOverlay canvas carries no collider and no world renderer. HudSpawnerPlayModeTests
    /// asserts both counts are zero, so the day someone adds a collider to the HUD the test says so.
    /// </para>
    /// <para>
    /// A SPAWNER MUST NOT SPAWN IN Awake. There is no Awake here at all: Spawn runs only when
    /// GameBootstrap, or a fixture, calls it.
    /// </para>
    /// </remarks>
    [DisallowMultipleComponent]
    public sealed class HudSpawner : MonoBehaviour, ISpawner
    {
        /// <summary>The name every existing fixture looks the HUD up by (TitleScreenPlayModeTests:191,
        /// WizardGameEntryPlayModeTests:78).</summary>
        public const string CanvasObjectName = "Canvas";

        [Tooltip("Resources/Hud/Hud.prefab: the authored Canvas, carrying HudBindings on its root.")]
        [SerializeField] private GameObject hudPrefab;

        public SpawnPhase Phase => SpawnPhase.Hud;

        /// <summary>The live HUD's bindings, or null when nothing is spawned.</summary>
        public HudBindings Hud { get; private set; }

        /// <summary>1 after a successful Spawn, 0 after a failed one, -1 before any - deliberately
        /// distinguishable from a Spawn that created nothing.</summary>
        public int SpawnedCount { get; private set; } = -1;

        public int Spawn()
        {
            Clear();

            if (hudPrefab == null)
            {
                Debug.LogError($"{nameof(HudSpawner)}: '{nameof(hudPrefab)}' is not assigned on '{name}'. "
                    + "Resources/Spawners/HudSpawner.prefab should reference Resources/Hud/Hud.prefab.",
                    this);
                return Fail();
            }

            if (hudPrefab.GetComponent<HudBindings>() == null)
            {
                Debug.LogError($"{nameof(HudSpawner)}: '{hudPrefab.name}' carries no {nameof(HudBindings)} "
                    + "on its root, so nothing could wire it to the player.", this);
                return Fail();
            }

            var movement = FindFirstObjectByType<PlayerMovement>();
            if (movement == null)
            {
                Debug.LogError($"{nameof(HudSpawner)}: no active {nameof(PlayerMovement)} exists, so there "
                    + $"is no player to bind the HUD to. Player (phase {(int)SpawnPhase.Player}) must run "
                    + $"before Hud (phase {(int)SpawnPhase.Hud}). Nothing was created.", this);
                return Fail();
            }

            GameObject hud = Instantiate(hudPrefab, transform);
            hud.name = CanvasObjectName;
            var bindings = hud.GetComponent<HudBindings>();

            if (!bindings.BindToPlayer(movement))
            {
                Debug.LogError($"{nameof(HudSpawner)}: the HUD could not bind to '{movement.name}' - the "
                    + "error above names what was missing - so it was destroyed rather than left on "
                    + "screen half-bound.", this);
                Retire(hud);
                return Fail();
            }

            Hud = bindings;
            SpawnedCount = 1;
            return 1;
        }

        private int Fail()
        {
            SpawnedCount = 0;
            return 0;
        }

        /// <summary>Deactivate, then destroy: Destroy is deferred to end of frame, and FindFirstObjectByType
        /// skips inactive objects, so nothing can bind to a dying HUD in the same frame. Every child goes,
        /// which is the Canvas and the WorldSpawn marker HudBindings parks beside it (see HudBindings).</summary>
        private void Clear()
        {
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                Retire(transform.GetChild(i).gameObject);
            }

            Hud = null;
        }

        private static void Retire(GameObject child)
        {
            child.SetActive(false);
            Destroy(child);
        }
    }
}
