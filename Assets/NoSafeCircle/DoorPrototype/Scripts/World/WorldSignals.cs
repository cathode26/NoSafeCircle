using deVoid.Utils;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>
    /// The facts one lane announces and another needs. Typed, one-to-many, fire-and-observe.
    /// </summary>
    /// <remarks>
    /// <para>
    /// VINCENT NAMED THE TOOL AND THEN NAMED THE REASON, 2026-09-26: "another good tool to
    /// communicate between objects is the event listener tool called Signals", and then the half
    /// that matters - "YOU AVOID NEEDING TO WIRE OBJECTS TOGETHER WITH SIGNALS."
    /// </para>
    /// <para>
    /// THAT IS THE SAME MOVE AS EVERYTHING ELSE IN THIS ARCHITECTURE, ONE LEVEL DOWN. The fleet
    /// wrote 9,739 lines of edit-time generators for one reason: AN AGENT CANNOT CLICK. Authoring
    /// prefabs as YAML text removed the clicking for ASSETS. Discovering spawners in a folder
    /// removed the shared list that would otherwise need editing. Signals removes it for WIRING - a
    /// listener never holds a reference to the emitter, so there is no slot for anyone to drag an
    /// object into and no serialized field for two lanes to fight over. Nothing left in the build
    /// path needs a mouse.
    /// </para>
    /// <para>
    /// ENGINEERING_STANDARDS 5.4 already names the same
    /// one: "deVoid Signals: preferred for typed cross-system, one-to-many, fire-and-observe
    /// notifications when the library is installed." It IS installed, at Assets/Plugins/deVoid,
    /// as a Plugins-folder library rather than a UPM package - which is why it does not appear in
    /// Packages/manifest.json and why it is easy to conclude it is absent without looking.
    /// </para>
    /// <para>
    /// WHAT THIS FIXES, and it was found by an adversarial review before it could bite: with seven
    /// independent lanes, "doors, player, enemies and HUD can reach other lanes' output ONLY BY
    /// HIERARCHY-NAME LOOKUP." That means <c>GameObject.Find("Player")</c> - which is brittle
    /// against a rename, silently returns null in the wrong order, and cannot be tested without
    /// building the whole world. The HUD lane was reaching for a REFLECTION BINDER to solve the
    /// same problem, and flagged it as the hack it is.
    /// </para>
    /// <para>
    /// THE LINE THIS DOES NOT CROSS, and 5.3 draws it explicitly: "do not emit a global signal
    /// merely to avoid a direct call to an object already owned by the sender", and 5.4 keeps
    /// direct references as "the default for clear, local, one-to-one ownership." A spawner talking
    /// to a prefab it just instantiated uses the reference it already has. These three signals
    /// exist because they are genuinely ONE-TO-MANY and genuinely CROSS-LANE: several unrelated
    /// families care that the player now exists, and none of them owns it.
    /// </para>
    /// <para>
    /// SUBSCRIPTION MUST BE LIFECYCLE-SYMMETRIC (5.3, and 5.4 repeats it). Add in OnEnable, remove
    /// in OnDisable, and do not subscribe with an anonymous lambda - 5.3 forbids that where
    /// "reliable removal is required", and a listener that outlives its object throws into a dead
    /// reference on the next emit.
    /// </para>
    /// <para>
    /// ONE FILE, DELIBERATELY, AND IT IS THE ONE PLACE A NEW CROSS-LANE SIGNAL IS DECLARED. 5.3:
    /// "group contracts by feature" and "do not place dozens of unrelated subscriptions in one
    /// manager". This is the WORLD BUILD feature and nothing else belongs here. A lane that wants a
    /// signal about its own internals declares it in its own folder.
    /// </para>
    /// </remarks>
    public static class WorldSignals
    {
        /// <summary>The whole world is built and every phase has run. Payload: how many objects.</summary>
        /// <remarks>
        /// THE HONEST ALTERNATIVE TO A POLLED READINESS FLAG. Standard 7.2 forbids "exposing
        /// initialization as a bool that every consumer polls", and <c>GameBootstrap.HasBuilt</c>
        /// exists only so a fixture can assert the build ran - it is not for consumers. This is what
        /// consumers use instead.
        /// </remarks>
        public sealed class WorldBuilt : ASignal<int>
        {
        }

        /// <summary>The player exists and is placed. Payload: the wizard's root.</summary>
        /// <remarks>
        /// THE ONE THAT REPLACES <c>GameObject.Find("Player")</c>. The HUD binds to it, the camera
        /// follows it, enemies acquire it as a target - three unrelated lanes, none of which owns
        /// the wizard, all of which currently have to go looking for it by name.
        /// </remarks>
        public sealed class PlayerSpawned : ASignal<GameObject>
        {
        }

        /// <summary>One phase finished. Payload: which phase, and what it created.</summary>
        /// <remarks>
        /// Emitted per phase rather than only at the end, because some work legitimately has to
        /// happen BETWEEN phases - the navigation bake is the worked example, and a diagnostic that
        /// wants per-phase counts should not have to instrument the bootstrap to get them.
        /// </remarks>
        public sealed class PhaseCompleted : ASignal<SpawnPhase, int>
        {
        }
    }
}
