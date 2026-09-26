using System.Text;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype.Hud
{
    /// <summary>
    /// Sits on the Canvas root of Resources/Hud/Hud.prefab and wires the authored HUD to the player
    /// the Player lane spawned. The prefab serializes every reference that is internal to itself; this
    /// is the one place the references that cross into another lane's object are made, at runtime.
    /// </summary>
    /// <remarks>
    /// <para>
    /// WHAT IT BINDS, AND WHY EACH ONE HAS TO BE RUNTIME. The health and mana bars subscribe to
    /// components on the player (PlayerHealthUI.Bind and PlayerManaUI.Bind are public). The two debug
    /// buttons call methods on the player, and a persistent UnityEvent listener cannot point at another
    /// prefab's instance, so those are AddListener here. WorldSpawn is moved to where the player was
    /// spawned, so wizard-selection entry returns the player there and the Player lane keeps sole
    /// ownership of the spawn point. WizardGameEntryController holds the player in private fields with
    /// no setter, so it is written through <see cref="HudReflectionBinder"/> until its owner adds one.
    /// </para>
    /// <para>
    /// WHAT IT DOES NOT REFLECT ON, DELIBERATELY: TitleScreenController. Its private player fields are
    /// read in exactly one place, SuspendGameplayInput(), which runs from its Awake - and Awake ran at
    /// Instantiate, before any player was known, with those fields empty. Writing them afterwards would
    /// change nothing observable, so this class performs that suspension itself rather than pretending
    /// a post-Awake write does it. If NSC-066's file ever gains a Bind that re-runs the suspension, the
    /// block at the end of <see cref="BindToPlayer"/> is what it replaces.
    /// </para>
    /// </remarks>
    [DisallowMultipleComponent]
    public sealed class HudBindings : MonoBehaviour
    {
        [SerializeField] private PlayerHealthUI healthUi;
        [SerializeField] private Image healthFill;
        [SerializeField] private PlayerManaUI manaUi;
        [SerializeField] private Image manaFill;
        [SerializeField] private Button damageButton;
        [SerializeField] private Button manaButton;
        [SerializeField] private TitleScreenController titleScreen;
        [SerializeField] private WizardGameEntryController entry;
        [SerializeField] private Transform worldSpawn;

        /// <summary>True once <see cref="BindToPlayer"/> has completed; never true for a HUD that
        /// failed to bind, because the spawner destroys that one.</summary>
        public bool IsBound { get; private set; }

        public PlayerMovement BoundPlayer { get; private set; }

        /// <summary>Where wizard-selection entry places the player: the pose the player had when the
        /// HUD bound to it.</summary>
        public Transform WorldSpawn => worldSpawn;

        /// <summary>
        /// Wires every player-facing part of the HUD to <paramref name="movement"/>'s object. False, with
        /// an error naming what was missing, if the player lacks any of the six components the HUD
        /// binds to or if this prefab has lost one of its own parts. On false nothing has been wired.
        /// </summary>
        public bool BindToPlayer(PlayerMovement movement)
        {
            if (movement == null)
            {
                Debug.LogError($"{nameof(HudBindings)}: BindToPlayer was given no player.", this);
                return false;
            }

            if (!HasEveryOwnPart())
            {
                return false;
            }

            GameObject player = movement.gameObject;
            var health = player.GetComponent<PlayerHealth>();
            var mana = player.GetComponent<PlayerMana>();
            var interaction = player.GetComponent<PlayerInteractionController>();
            var wizard = player.GetComponent<WizardAnimationController>();
            var debugDamage = player.GetComponent<DebugDamageControl>();
            var debugMana = player.GetComponent<DebugManaSpendControl>();

            string missing = NamesOfMissing(
                (health, nameof(PlayerHealth)), (mana, nameof(PlayerMana)),
                (interaction, nameof(PlayerInteractionController)),
                (wizard, nameof(WizardAnimationController)),
                (debugDamage, nameof(DebugDamageControl)), (debugMana, nameof(DebugManaSpendControl)));

            if (missing.Length > 0)
            {
                Debug.LogError($"{nameof(HudBindings)}: player '{player.name}' is missing {missing}. The "
                    + "HUD binds to all six player components on the player ROOT and refuses to come up "
                    + "half-bound: a bar bound to nothing reads as a full bar.", this);
                return false;
            }

            // Reflection FIRST, before any side effect, so a failure leaves nothing partly wired.
            if (!HudReflectionBinder.TrySetPrivate(entry, "wizardAnimationController", wizard)
                || !HudReflectionBinder.TrySetPrivate(entry, "player", movement.transform)
                || !HudReflectionBinder.TrySetPrivate(entry, "playerMovement", movement)
                || !HudReflectionBinder.TrySetPrivate(entry, "playerInteractionController", interaction))
            {
                return false;
            }

            // A WORLD-SPACE MARKER CANNOT LIVE UNDER A SCREEN-SPACE CANVAS. The Canvas RectTransform is
            // re-positioned and re-scaled by the CanvasScaler whenever the screen changes, and a child's
            // world pose moves with it - so a resize would silently move where entry places the wizard.
            // Move it beside the Canvas, under the spawner, where the pose is exactly what was set.
            worldSpawn.SetParent(transform.parent, false);
            worldSpawn.SetPositionAndRotation(movement.transform.position, movement.transform.rotation);
            healthUi.Bind(health, healthFill);
            manaUi.Bind(mana, manaFill);

            // RemoveAllListeners clears only runtime listeners, and the prefab serializes none on these
            // two buttons, so a second bind cannot stack a second call onto the first.
            damageButton.onClick.RemoveAllListeners();
            damageButton.onClick.AddListener(debugDamage.TriggerDebugDamage);
            manaButton.onClick.RemoveAllListeners();
            manaButton.onClick.AddListener(debugMana.TriggerDebugSpend);

            // What TitleScreenController.Awake would have done had it known the player (see the class
            // remarks): the title owns input until wizard selection hands it back.
            if (titleScreen.IsTitleScreenVisible)
            {
                movement.SuspendGameplayInput();
                interaction.SuspendGameplayInput();
                debugDamage.enabled = false;
                debugMana.enabled = false;
            }

            IsBound = true;
            BoundPlayer = movement;
            return true;
        }

        private bool HasEveryOwnPart()
        {
            (Object part, string fieldName)[] parts =
            {
                (healthUi, nameof(healthUi)), (healthFill, nameof(healthFill)),
                (manaUi, nameof(manaUi)), (manaFill, nameof(manaFill)),
                (damageButton, nameof(damageButton)), (manaButton, nameof(manaButton)),
                (titleScreen, nameof(titleScreen)), (entry, nameof(entry)),
                (worldSpawn, nameof(worldSpawn)),
            };

            foreach ((Object part, string fieldName) in parts)
            {
                if (part == null)
                {
                    Debug.LogError($"{nameof(HudBindings)}: '{fieldName}' is not assigned on '{name}'. "
                        + "Hud.prefab has lost one of its own parts; nothing can bind until it is "
                        + "restored.", this);
                    return false;
                }
            }

            return true;
        }

        private static string NamesOfMissing(params (Component component, string typeName)[] required)
        {
            var missing = new StringBuilder();
            foreach ((Component component, string typeName) in required)
            {
                if (component == null)
                {
                    missing.Append(missing.Length > 0 ? ", " : string.Empty).Append(typeName);
                }
            }

            return missing.ToString();
        }
    }
}
