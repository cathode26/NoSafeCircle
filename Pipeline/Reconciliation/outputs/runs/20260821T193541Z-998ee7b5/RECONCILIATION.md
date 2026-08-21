# No Safe Circle — Reconciliation

> Human-review artifact. This file does not itself become the persistent task graph.

## Seed Assessment

**Status:** `ready_with_warnings`

**Warnings:**
- 4 unresolved reconciliation question(s) remain for review.
- Deterministic provenance guard removed 1 non-authoritative summary finding(s) containing internal pipeline provenance language. Authoritative graph/evidence fields remain subject to strict provenance validation.
- 4 unresolved reconciliation question(s) remain for human/runtime/later-decomposition review.

## Summary

### Desired State

Player Core Systems: Per the current GDD (Docs/GDD/No_Safe_Circle_GDD.md), Player Movement must own player position/locomotion, movement-restriction state, and a shared cursor-to-gameplay-plane projection producing a world-space pointer target consumed by movement itself, cursor-aimed spells (Fireball, Frost Field), and Door/Interaction (Force Wave is the explicit player-centered exception). Movement must be mouse-directed (click to set a destination or hold to steer toward the cursor) and routed through the project's Unity Input System/Input Actions layer rather than direct hardware polling. Player Movement must expose an owner-controlled movement-restriction interface that Charged Fireball requests/releases without mutating movement internals directly, and must expose an owner-controlled reset entry point for player position/movement state consumed by the Floor Run/Restart Orchestrator. Player Health must remain the single owner of current health, exposing an owner-controlled damage interface (already present) plus an owner-controlled restore/heal interface clamped to max health (consumed by Door's lock-and-heal request), an observable zero-health/death transition consumed by the restart orchestrator without polling or internal mutation, a continuous player-facing health indicator, no passive regeneration, and an owner-controlled floor-restart reset entry point. Player Mana must remain the single owner of current mana and its post-cast regeneration-delay state, exposing the existing spend interface plus an owner-controlled reset entry point for floor restart, while never absorbing spell-local cooldown/charge/cast/placement/active-field state that belongs to Fireball, Frost Field, or Force Wave; denied-cast attempts should surface player-readable feedback given the GDD's failure-readability success criterion (exact presentation is an implementation choice). Wizard Combat and Spells: The GDD requires three spells owned by the Wizard Combat Agent: Charged Fireball (cursor-aimed tap-for-quick-shot / hold-to-charge-for-area-damage against clustered Melee Enemies, consuming a Player-Movement-owned movement-restriction interface while charging and an Enemy-Health/Defeat-owned damage interface to hurt enemies), Frost Field (placed at the Player-Movement-owned shared cursor world-space target, providing readable cast/active-field feedback, and triggering — but not implementing — enemy slowdown through the Enemy Pursuit/status-effect owner), and Force Wave (player-centered radial knockback, no cursor targeting, 25-mana initial cost, long cooldown, requesting enemy displacement through the same enemy-owned status-effect/displacement interface). Each spell owns its own local state (Fireball: tap/charge/cast; Frost Field: Wizard-Combat-side cast/placement/active-field; Force Wave: cooldown) and must expose an owner-controlled floor-restart reset entry point and an owner-controlled gameplay-enable/suspend interface consumed by the victory/game-flow capability. All three spend mana through Player Mana's existing spend interface and must route casting input through Unity Input System/Input Actions rather than independent hardware polling. Enemy State, Persistence, and Shared Effects: The GDD requires three reusable, ownership-scoped enemy capabilities beneath the Enemies feature: (1) a shared Active Enemy Registry that tracks persistent active enemy objects, exposes current count/remaining capacity under a hard 15-enemy cap, registers on activation, unregisters on defeat, and is never depleted by target loss/search/room-crossing/waiting-behind-a-locked-door; (2) a reusable Enemy Health/Defeat capability that owns each persistent enemy's current health, damage intake (consumed by Fireball and other canon damage sources), the defeat transition, and reports defeat-driven removal through the registry's own interface rather than duplicating bookkeeping; (3) a reusable status-effect/displacement component that applies and restores Frost Field slowdown (locomotion/repositioning only — it must never suppress or slow Ranged Enemy attack execution) and applies Force-Wave-requested forced displacement, returning the affected enemy to the correct pursuit/search movement state afterward. All three must expose owner-controlled reset entry points consumed by the Floor Run/Restart Orchestrator (owned by a different domain) rather than being reset by direct internal mutation. Enemy Pursuit and Attack Behavior: The GDD requires a shared detection/pursuit/target-loss/search/reacquisition state machine (Detection Distance smaller than Lose Target Distance; distance-based, non-random loss; last-known-position homing; short bounded randomized search/wander; reacquisition; no target clearing merely from crossing a doorway; explicit continued traversal through open/broken doorways) consumed by two required enemy archetypes: Melee Enemy (rushes and attacks at close range, naturally clusters while pursuing, gradually closes distance so retreat alone cannot preserve indefinite safety) and Ranged Enemy (keeps moderate distance, fires a slow telegraphed shot with line-of-sight/projectile occlusion, continues attacking while slowed by Frost Field even though its repositioning is slowed). Both archetypes deal damage only through the shared Player Health interface and must be delivered as usable assembled world-space SpriteRenderer prefabs integrating pursuit/locomotion, Enemy Health/Defeat, and Active Enemy Registry participation (both owned elsewhere). Separately, the GDD requires that any surviving enemy still actively tracking/pursuing the player and blocked by a newly locked door attacks that door (no separate witness flag) through the Door-owned damage interface, and resumes pursuit through the doorway once it breaks. Doors and Interaction: The GDD requires Door and Interaction to: (1) expose sealed doors as cursor-targeted interactables that trigger a combined approach-and-interact request through Player Movement's shared world-space pointer target, auto-start a five-second timer with no sustained hold once arm's-reach range is reached, ignore cursor drift after selection, and reset on damage/moving-away/interaction-cancelling commands; (2) own authoritative doorway-crossing state (forward-side crossing) as a single owner consumed by close/lock and final victory; (3) automatically close and lock the door after crossing (no second input), request a fixed Player Health restoration through Player Health's owner-controlled restore interface, own runtime durability and an owner-controlled damage-receive interface consumed by enemy attacks, own the locked-to-broken transition, enforce forward-only progression (no reopening/unlocking/re-crossing; a broken door stays open and is not a player return path), publish semantic door state through the navigation-owned passability interface, and provide required breach feedback (banging/shaking/cracks/durability indicator); and (4) expose an owner-controlled reset entry point for door lifecycle/crossing/durability state consumed by the Floor Run/Restart Orchestrator. World and Unity Foundations: The GDD requires: a fixed 2.5D isometric camera with no free world-view rotation; the approved Unity 2D Tilemap Editor (com.unity.2d.tilemap) and Unity AI Navigation (com.unity.ai.navigation) packages configured in the project; a shared gameplay navigation/locomotion layer that owns the walkable movement representation for NavMesh-based enemy movement and that also owns the navigation-side half of the door-passability contract (translating Door and Interaction's semantic sealed/open/locked/broken state into enemy walkability, with sealed/locked blocking and open/broken permitting traversal); and a reusable Tilemap/SpriteRenderer visual-world foundation (Isometric Tilemaps for floors/walls/repeatable architecture, world-space SpriteRenderer prefabs with isometric sorting for the wizard, enemies, doors, and other independently sorted objects) that is decoupled from the gameplay/collision/walkability layer so art can change without redefining gameplay rules, and that supports all five spaces existing inside one continuous scene/floor with no scene-loading or cross-scene state transfer. Room-specific five-space authoring and encounter content remain explicitly out of scope for this foundation and belong to a separate deferred content-authoring feature outside this domain. Floor Content and Encounters: The GDD requires one continuous handcrafted floor with five named tactical spaces (Ruined Entry, Bone Archive, Chapel of Ash, Lower Vault, Final Room), each with a specific layout/tactical purpose, built on the reusable Tilemap/SpriteRenderer world foundation. Encounter placement, triggers, per-door durability values, and mixed Melee/Ranged compositions (explicitly required in Chapel of Ash and the Final Room) are authored by the Dungeon Encounter Agent once the room spaces and admission foundation exist, but exact geometry/placement/tuning is intentionally left to later authoring/playtesting. Independently, the GDD already fully specifies a runtime encounter-admission rule that must not be blocked by deferred content: a shared Active Enemy Registry tracks up to fifteen active persistent enemies; when admitting a new encounter would exceed that cap, new encounter enemies are delayed/reduced first and existing persistent pursuers are never removed, with Lower Vault as the explicit validation case. Section 3 also fixes a three-to-eight enemy encounter-size range and the never-isolated-Ranged-Enemy composition rule as durable constraints on future encounter authoring. Run Lifecycle and Victory: The GDD requires two closely related capabilities in this domain. (1) Floor Run/Restart: a shared Floor Run/Restart Orchestrator consumes Player Health's observable zero-health/death transition and coordinates a fresh floor attempt by invoking owner-controlled reset entry points on every run-persistent state owner (Player Health, Player Mana, Player Movement/position, Fireball, Frost Field, Force Wave, enemy health/defeat, enemy pursuit/search/attack/status/displacement, Active Enemy Registry, door lifecycle/crossing/durability, encounter activation/admission). An early implementation may validate only against currently-existing persistent owners, but full closure remains required until every implemented owner participates. (2) Win/Loss Conditions: victory is confirmed only via the shared doorway-crossing state Door and Interaction owns (no separate crossing detector); a reusable Game Flow/Victory capability then owns the won-state transition, displays a simple "You Escaped" overlay, and coordinates suspension of Player Movement, Door/Interaction, Fireball, Frost Field, and Force Wave through each system's own owner-controlled suspend/re-enable interface rather than mutating their internals. No further post-victory progression is required. Loss is reaching zero health, which triggers the restart orchestrator described above. Delivery, Validation, and Pipeline Constraints: The GDD requires a Windows Standalone build as part of the Required Scope (Section 3) and Technical Strategy (Section 5), with the canonical gameplay scene registered in Unity Build Settings before that delivery obligation can be considered complete. The GDD also defines an extensive set of required development-process invariants governing the AI-assisted pipeline: minimal-context dispatch, isolated-branch/workspace execution with no concurrent edits to the same Unity assets, a scene-builder exclusive-write lock for `DoorPrototypeSceneBuilder.cs`/`DoorPrototype.unity`, compile-before-validation, failed-task scope-reduction retry policy, a planning token-budget ceiling, mandatory human inspection/merge/playtesting authority, agent scope/canon discipline, preservation of non-canonical stub scenes as a human decision, a boundary on what generated development-time art import does and does not imply, credential handling outside source control, and a runtime prohibition on generative AI in the shipped game. Section 3's Player Experience Success Criteria are required validation obligations that must be attached to the concrete work items (owned by other domain workers) that actually implement the underlying behavior, not treated as separate gameplay features. Stretch goals and explicitly excluded systems must be enumerated and kept out of required Milestone 1 work.

### Current State

Player Core Systems: Current repository state for player-core systems (Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs, PlayerHealth.cs, PlayerMana.cs, PlayerManaUI.cs, plus their scene wiring in DoorPrototype.unity and creation code in DoorPrototypeSceneBuilder.cs): PlayerMovement.cs is a CharacterController-driven WASD keyboard mover that polls Keyboard.current directly every Update; it has no mouse-directed click/hold movement, no cursor-to-gameplay-plane projection/world-space pointer target, no movement-restriction request/release interface, and no floor-restart reset entry point. It does call PlayerInteractionController.OnPlayerMoved() on movement input, which is the one GDD-relevant behavior already present. PlayerHealth.cs exposes CurrentHealth, a clamped TakeDamage(amount) damage interface, and a Damaged event, but has no restore/heal interface, no observable zero-health/death transition, and no reset entry point; there is no PlayerHealth UI component anywhere in the scripts, so the GDD's continuous health indicator is not implemented. PlayerMana.cs exposes CurrentMana/MaxMana, Spend(amount) (fails silently returning false when insufficient), Tick-based post-cast-delay regeneration, and a ManaSpent event; PlayerManaUI.cs already renders a continuous fill-bar tied to CurrentMana/MaxMana (confirmed wired in DoorPrototype.unity via DoorPrototypeSceneBuilder.BuildManaUI). PlayerMana has no reset entry point and no denied-cast feedback signal. All four scripts (PlayerHealth, PlayerMana, PlayerMovement, PlayerManaUI) are confirmed serialized onto the Player/Canvas GameObjects in Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity (verified by matching each script's .meta GUID against the scene file), and DoorPrototypeSceneBuilder.BuildPlayer/BuildUI is the current write surface that creates and wires them. Assets/InputSystem_Actions.inputactions is the unmodified default Unity template (Move/Look/Attack/Interact/Crouch/Jump/etc. plus a UI map with Point/Click); it has no gameplay-plane cursor-projection or click-to-move action, and PlayerMovement.cs does not consume it at all — it bypasses the Input Actions layer entirely via raw Keyboard.current polling, which conflicts with the GDD's explicit "routed through Unity Input System/Input Actions" requirement. PlayerManaPlayModeTests.cs and part of DoorInteractionPlayModeTests.cs give real Play Mode test coverage for PlayerMana spend/regen/post-cast-delay behavior and for PlayerHealth's damage-cancels-door-interaction interaction, but no tests exist for movement, cursor projection, health restore, or any reset behavior. Wizard Combat and Spells: Repository inspection confirms Fireball, Frost Field, and Force Wave do not exist anywhere under Assets/ (no matches for those terms, and no dedicated scripts). Only PlayerMana.cs (mana pool + Spend/regen), PlayerHealth.cs (damage), PlayerMovement.cs (WASD-only CharacterController movement, no mouse/cursor projection, no movement-restriction interface), PlayerInteractionController.cs, and DoorInteractable.cs are integrated. No enemy scripts of any kind exist (no health/damage/defeat capability, no status-effect/displacement capability), so any spell-consumed enemy-owned interface is itself an unfinished prerequisite. Assets/InputSystem_Actions.inputactions exists with a generic Player action map (Move/Look/Attack/Interact/Crouch/Jump/Previous/Next/Sprint) but has only one combat-adjacent action ("Attack", a plain Button bound to Mouse leftButton with no tap/hold distinction) and no Frost-Field- or Force-Wave-specific actions, so all three spells must add/modify bindings in that shared asset. DoorPrototypeSceneBuilder.cs assembles the Player GameObject (movement, interaction, health, mana, debug controls) and rebuilds/saves the canonical DoorPrototype.unity scene on every run, so attaching any new spell component to the Player requires modifying that builder and re-saving that scene. Enemy State, Persistence, and Shared Effects: The current integrated project contains zero enemy-related code, components, or scene objects. A repository-wide search of Assets/ (Scripts, Tests, and Editor) for Enemy, Registry, Defeat, Frost, and Displacement returned no matches. DoorPrototypeSceneBuilder.cs creates only Floor, Walls, DoorRoot, and player/camera-related objects — no enemy scaffolding. PlayerHealth.cs exists (health/damage only, no death event or restore method) but is outside this domain's ownership. No Active Enemy Registry, Enemy Health/Defeat capability, or status-effect/displacement component exists in any form (not even a builder-capability stub). This domain's required work is therefore entirely missing/open. Enemy Pursuit and Attack Behavior: The current repository contains zero enemy-related code. `Assets/NoSafeCircle/DoorPrototype/Scripts/` only has Door/Player/Camera/UI scripts (DoorInteractable.cs, DoorInteractionUI.cs, PlayerHealth.cs, PlayerInteractionController.cs, PlayerMovement.cs, PlayerMana.cs, PlayerManaUI.cs, IsometricCameraFollow.cs, DebugDamageControl.cs, DebugManaSpendControl.cs); a full `Assets/**/*.cs` glob confirms no file named Enemy/Melee/Ranged/Pursuit exists anywhere. `Packages/manifest.json` does not declare `com.unity.ai.navigation`, so the shared gameplay navigation/locomotion foundation this domain's locomotion depends on is itself unconfigured. `DoorInteractable.cs` currently implements only open/interacting/progress state — no durability, locked, or broken fields and no damage-receive interface exist yet, so the door-side interface locked-door enemy attacks must consume does not exist. `PlayerHealth.cs` already exposes a public `TakeDamage(float)` method, which is a usable existing interface for enemy attacks. Apparent "NavMesh"/"Occlusion" strings in `DoorPrototype.unity` are generic per-GameObject Unity serialization fields (`m_NavMeshLayer`, occlusion-culling settings), not an actual navigation or line-of-sight implementation. Doors and Interaction: The DoorPrototype scene implements a WASD-movement, arm's-reach-trigger, hold-E interaction model (DoorInteractable.cs + PlayerInteractionController.cs), with a five-second progress timer that resets on release/movement/damage. This is a partial precursor to the GDD's required door contract but is missing cursor-targeted click-to-approach selection, an automatic no-hold timer start, and Unity Input System/Input Actions routing (current code polls Keyboard.current directly). Nothing in the repository implements doorway-crossing detection, automatic close/lock, runtime durability, a damage-receive interface, the locked-to-broken transition, forward-only enforcement, breach feedback, or door-state publication to a navigation/passability layer — none of these exist in any script, the scene, or the builder. PlayerHealth.cs exposes only TakeDamage (no restore/heal interface), and no Unity AI Navigation package/NavMesh gameplay layer exists, confirming that this domain's cross-domain prerequisites (Player Movement's shared pointer projection, Player Health's restore interface, and the gameplay navigation/passability layer) are genuinely unfinished rather than stale ordering. World and Unity Foundations: The only committed canonical gameplay scene is Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity, generated/maintained by Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs. Within that scene: (1) the Main Camera is orthographic, fixed at the classic 30/-45 dimetric isometric rotation, and only ever translated (never rotated) by IsometricCameraFollow.cs, with automated editor tests (DoorPrototypeSceneBuilderTests.cs) directly asserting orthographic mode, the fixed rotation, absence of any Rotate/Orbit component, and that rotation never changes while following the player — this satisfies the GDD's fixed-isometric/no-free-rotation requirement. (2) Packages/manifest.json and Packages/packages-lock.json contain neither com.unity.2d.tilemap nor com.unity.ai.navigation; only the builtin com.unity.modules.tilemap runtime module (a different, lower-level module than the 2D Tilemap Editor authoring package) is present. (3) No Tilemap/Grid GameObjects and no NavMeshAgent/NavMeshSurface/NavMeshObstacle components exist anywhere in the scene; the scene's NavMeshSettings block is Unity's default per-scene stub, not evidence of an implemented navigation layer. (4) The builder currently generates Floor, Walls, and the door visual as plain primitive meshes (Plane/Cube) with MeshRenderers rather than as Isometric Tilemap tiles or world-space SpriteRenderer prefabs, so the reusable Tilemap/SpriteRenderer visual foundation and its sorting/visual-gameplay-separation conventions do not yet exist. Floor Content and Encounters: The current checkout contains only the single-door prototype under Assets/NoSafeCircle/DoorPrototype: a generic Floor plane, two Wall cubes, one DoorRoot/DoorInteractable, a Player object, and UI, all generated by DoorPrototypeSceneBuilder.cs and serialized in DoorPrototype.unity. There is no Tilemap content, no named room (Ruined Entry, Bone Archive, Chapel of Ash, Lower Vault, Final Room), no encounter/spawn/trigger authoring, and no Active Enemy Registry, encounter-admission, or enemy code anywhere in Assets/ (confirmed via glob of all NoSafeCircle .cs files and a grep for Encounter/Registry terms, which returned no matches). Five-room content and dungeon encounters are therefore entirely unimplemented, matching their status as GDD-deferred authoring plus one not-yet-built runtime foundation (encounter-admission cap enforcement). Run Lifecycle and Victory: No restart, death-transition, or victory/game-flow code exists anywhere in the current repository. PlayerHealth.cs only exposes CurrentHealth, TakeDamage, and a Damaged event — there is no zero-health/death event, no restore/heal interface, and no reset entry point. PlayerMana.cs and PlayerMovement.cs likewise expose no reset entry points. DoorInteractable.cs implements only the open-timer/interaction lifecycle (Progress, IsOpen, doorwayBlocker disable-on-open) — it has no doorway-crossing detection, no lock/durability/breaking, and no reset entry point either, even though its own Progress/IsOpen/blocker state is already run-persistent. No enemy, spell (Fireball/Frost Field/Force Wave), or navigation code exists in the project at all (confirmed by a repository-wide search), so the eventual full persistent-closure and victory-input-shutdown dependencies on those systems are currently unmet prerequisites rather than already-satisfied interfaces. Delivery, Validation, and Pipeline Constraints: This worker directly inspected only the global_pipeline domain (delivery/build configuration and non-code/pipeline requirements). `ProjectSettings/EditorBuildSettings.asset` contains `m_Scenes: []` — no gameplay scene is registered in Unity Build Settings, confirming the Windows-build delivery obligation has a concrete open configuration gap. `Packages/manifest.json` does not currently declare `com.unity.2d.tilemap` or `com.unity.ai.navigation` (this fact is relevant to the world_foundations domain, not represented as a work item here). `.gitignore` confirms `UserSettings/` and other Unity editor/user-local state are excluded from source control, consistent with the GDD's process expectations. No previous-candidate delivery/pipeline work items were found to be stale; the three routed keys (`no-safe-circle`, `delivery-and-build`, `windows-build-scene-registration`) remain current and required.

### Major Findings

- PlayerMovement.cs implements only WASD keyboard movement via raw Keyboard.current polling with a CharacterController; none of the GDD-required mouse-directed click/hold movement, shared cursor-to-gameplay-plane projection, movement-restriction interface, or floor-restart reset entry point exist. This is the single largest gap in the player-core domain.
- PlayerMovement bypasses the Unity Input System/Input Actions layer entirely (direct Keyboard.current polling) despite `using UnityEngine.InputSystem`, which conflicts with the GDD's explicit 'routed through the project's Unity Input System/Input Actions layer' requirement for both movement and door/spell input.
- Assets/InputSystem_Actions.inputactions is the stock Unity template asset (Move/Look/Attack/Interact/Crouch/Jump/Sprint/etc.) with no cursor-to-gameplay-plane or click-to-move action; implementing mouse-directed movement will require adding/modifying bindings in this shared asset.
- PlayerHealth.cs has a working clamped damage interface and Damaged event but is missing the owner-controlled restore/heal interface, the observable zero-health/death transition, and any reset entry point required for floor-restart participation and Door's lock-and-heal request.
- No PlayerHealth UI/feedback component exists anywhere in the repository, so the GDD's required continuous player-facing health indicator is currently unimplemented (unlike mana, which already has PlayerManaUI wired into the scene).
- PlayerMana.cs's spend/regen/post-cast-delay behavior is implemented and covered by real Play Mode tests, and its continuous mana fill-bar (PlayerManaUI) is already serialized in the canonical scene, but PlayerMana has no floor-restart reset entry point and no denied-cast feedback signal.
- All four current player scripts (PlayerHealth, PlayerMana, PlayerMovement, PlayerManaUI) were confirmed serialized in Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity by matching each script's .meta GUID against the scene contents, not merely inferred from DoorPrototypeSceneBuilder's capability to create them.
- DoorPrototypeSceneBuilder.cs is the current write surface that creates/wires Player, PlayerHealth, PlayerMana, PlayerMovement, and their UI; any player-core work that adds new components (e.g., a health UI) or rewires existing ones must modify this builder and re-save the canonical scene it maintains.
- Fireball, Frost Field, and Force Wave are entirely unimplemented; no matching script, class, or reference exists anywhere under Assets/.
- PlayerMana.Spend(amount) already exists and is a usable owner-controlled spend interface, so per the existing-interface rule none of the three spells need a formal depends_on edge targeting player-mana solely to spend mana.
- PlayerMovement.cs is WASD-only (CharacterController + Keyboard.current polling) with no mouse-directed movement, no cursor-to-gameplay-plane projection/pointer target, no Input System/Input Actions consumption, and no movement-restriction request/release interface. Because Fireball and Frost Field are cursor-targeted and Charged Fireball must consume a movement-restriction interface, both spells have a real unfinished prerequisite on player-movement; Force Wave does not, since it is the explicit player-centered no-cursor exception.
- No enemy scripts exist at all, so the Enemy-Health/Defeat damage interface Fireball must consume and the Enemy Pursuit/status-effect-displacement interface Frost Field (slow trigger) and Force Wave (forced displacement request) must consume are both unfinished prerequisites, producing real dependencies on enemy-health-damage-defeat (Fireball) and enemy-status-effect-displacement (Frost Field, Force Wave).
- Assets/InputSystem_Actions.inputactions has no Fireball/Frost-Field/Force-Wave-specific action and its only combat-adjacent action ('Attack') has no tap-vs-hold interaction configured, so all three spells are expected to add or modify actions/bindings in that single shared asset and must share its exclusive-resource lock.
- DoorPrototypeSceneBuilder.cs constructs the Player GameObject and destructively rebuilds+saves the canonical DoorPrototype.unity scene each run; attaching/wiring any new spell component to that Player object writes through both, so all three spells carry the current builder/scene locks per the repository's established write-surface pattern.
- Per the anti-decomposition instruction ('do not decompose a spell into projectile/VFX/input/damage subtasks'), each spell remains a single concrete implementation work item rather than being split further.
- No enemy code of any kind exists in the repository; this domain's entire required scope is currently missing.
- The GDD explicitly and separately owns three capabilities in this domain: Active Enemy Registry bookkeeping (count/capacity/register/unregister), Enemy Health/Defeat (health/damage/defeat + registry removal reporting), and status-effect/displacement (Frost slowdown apply/restore + forced displacement apply/restore + pursuit/search hand-back).
- Enemy Health/Defeat has a real, GDD-stated dependency on Active Enemy Registry because defeat must report removal through the registry's own unregister interface rather than duplicating the count.
- Status-effect/displacement explicitly consumes the pursuit/search state contract (owned by enemy-behavior domain's enemy-pursuit-search-foundation) and the shared gameplay navigation/locomotion layer (owned by world-foundations domain), per GDD Section 5 Runtime Implementation.
- The GDD explicitly requires that Frost slowdown affect only a Ranged Enemy's repositioning, never its attack execution timing; this is preserved as a direct acceptance criterion on enemy-status-effect-displacement rather than left as background evidence.
- Encounter admission policy (delay/reduce new enemies to respect the 15-cap, Lower Vault priority) is owned by the Dungeon Encounter system in the content_encounters domain and consumes this domain's registry query interface; it is not represented here to avoid duplicating that owner's responsibility.
- All three previously-hinted routing keys (active-enemy-registry, enemy-health-damage-defeat, enemy-status-effect-displacement) remain current and required; none were dropped.
- No enemy-related C# scripts exist anywhere in the repository; a full Assets/**/*.cs glob returns only Door/Player/Camera/UI scripts.
- Packages/manifest.json does not declare com.unity.ai.navigation, so the world-domain gameplay-navigation-locomotion foundation this domain's locomotion must consume is itself not yet configured; enemy-pursuit-search-foundation formally depends on that foundation.
- DoorInteractable.cs currently has no durability/locked/broken state and no damage-receive interface at all (only IsOpen/Progress/interaction-timer fields), so locked-door-enemy-attack's dependency on the doors-domain door-close-lock-break-lifecycle owner is a hard, currently-unmet prerequisite, not a stylistic choice.
- PlayerHealth.cs already exposes a public TakeDamage(float) method, so Melee/Ranged attack acceptance criteria can reference this existing interface directly without a formal dependency on unrelated Player Health work, per the existing-interface consumption rule.
- The apparent NavMesh/Occlusion strings inside DoorPrototype.unity are ordinary Unity per-GameObject serialization boilerplate (m_NavMeshLayer, OcclusionCullingSettings), not evidence of an actual navigation mesh, line-of-sight system, or enemy content; this negative finding is called out explicitly to avoid an overbroad claim being read as a positive one.
- All four routing-hint keys (enemy-pursuit-search-foundation, melee-enemy, ranged-enemy, locked-door-enemy-attack) remain valid, currently-required, and fully missing; none are retired in this refresh.
- door-open-interaction: current code (DoorInteractable.cs, PlayerInteractionController.cs) implements arm's-reach range detection via a trigger collider and a 5-second progress timer that cancels on player-health damage and on any player movement, matching the interruption/timer-progression concept, but it requires a sustained hold of the E key (GDD explicitly requires no sustained hold once the timer auto-starts on arrival) and has no cursor-targeted click-to-approach selection, no consumption of a shared world-space pointer target, and uses raw Keyboard.current polling rather than the Unity Input System/Input Actions layer. Classified partial.
- doorway-crossing-state: no forward-side crossing detection, event, or state exists anywhere in the repository — DoorInteractable.Complete() only disables the door visual/collider and sets IsOpen=true. Classified missing.
- door-close-lock-break-lifecycle: no closing, locking, durability, damage-receive interface, locked-to-broken transition, forward-only enforcement, breach feedback, or navigation-passability publication exists anywhere in the repository. Classified missing.
- PlayerHealth.cs currently exposes only TakeDamage(float) with no restore/heal method, confirming door-close-lock-break-lifecycle's dependency on player-health's still-unfinished restore interface is a real, current prerequisite rather than stale ordering.
- Packages/manifest.json contains no com.unity.ai.navigation dependency and no NavMesh/navigation script exists under Assets/NoSafeCircle, confirming door-close-lock-break-lifecycle's dependency on gameplay-navigation-locomotion for passability publication is real and current.
- PlayerMovement.cs is pure WASD CharacterController motion with no mouse/pointer handling of any kind, confirming door-open-interaction's dependency on player-movement's still-unfinished shared cursor-to-gameplay-plane pointer projection is real and current.
- The DoorPrototype scene serializes DoorInteractable with doorVisual/doorwayBlocker references wired by DoorPrototypeSceneBuilder.cs, confirming the current door is integrated (not merely buildable) but only for the simplified open-only behavior described above.
- InputSystem_Actions.inputactions currently has no Point/Click-style action on the gameplay 'Player' action map (only 'Interact' bound with a Hold interaction, presumed keyboard) — the UI map's Point/Click bindings are for UI navigation, not gameplay cursor targeting, so no existing binding currently satisfies cursor-targeted door selection.
- Fixed isometric camera requirement is fully implemented and test-covered: DoorPrototypeSceneBuilder.BuildCamera sets orthographic=true, orthographicSize=8, and a fixed Quaternion.Euler(30,-45,0) rotation that is never modified again; IsometricCameraFollow.LateUpdate only ever writes transform.position, never rotation. DoorPrototypeSceneBuilderTests.cs directly asserts orthographic mode, the exact fixed rotation, absence of any Rotate/Orbit component, and rotation invariance while following the player.
- Neither approved package (com.unity.2d.tilemap nor com.unity.ai.navigation) appears in Packages/manifest.json or Packages/packages-lock.json. This is concrete missing project-configuration work per the GDD's 'Approved Unity Packages and Windows Build Configuration' section, not deferred design.
- No Tilemap/Grid objects and no NavMesh runtime components (NavMeshAgent/NavMeshSurface/NavMeshObstacle) exist anywhere in the current scene. The scene's NavMeshSettings YAML block is Unity's default per-scene stub present in every scene and is not evidence of an implemented navigation/locomotion layer.
- DoorPrototypeSceneBuilder.cs currently builds Floor, Walls, and the door visual as primitive Unity meshes (Plane/Cube) with MeshRenderer, not as Isometric Tilemap tiles or world-space SpriteRenderer prefabs, so the required Tilemap/SpriteRenderer visual-world foundation does not currently exist.
- Because the future navigation/locomotion layer and the future visual foundation would both need to rebuild the same builder-generated Floor/Walls/DoorRoot objects and the same canonical scene, matching exclusive-resource locks (builder file + canonical scene) are required on both items per the writer-inventory rule, even though the two items have no dependency on each other.
- Both the navigation/locomotion layer and the visual foundation have a real dependency on the package-configuration item, since the GDD states the approved packages must be configured before the layers that consume them (NavMesh-based movement; Isometric Tilemap authoring) can be built.
- No five-room content, encounter, or registry code/scene evidence exists anywhere in the current checkout; the only authored space is the generic single-door prototype room.
- The fifteen-active-enemy admission rule (delay/reduce new activation first, never remove existing pursuers) is fully specified by the GDD independent of room-specific content and is represented as a concrete, currently-dispatchable-once-its-dependency-exists implementation item rather than folded into the deferred encounter-content feature, per the Known Runtime Behavior vs Deferred Content Authoring guidance.
- five-room-content-authoring and dungeon-encounter-content-authoring remain two separate deferred organizational features with no formal dependency edge between them (per the explicit GDD-hardening example), since neither is itself dispatchable; their relationship is preserved in decomposition_reason/notes instead.
- dungeon-encounter-content-authoring is represented as depending on encounter-admission-cap-enforcement (the concrete admission foundation it must consume) and on door-close-lock-break-lifecycle and the melee-enemy/ranged-enemy archetype implementations, because authoring per-door durability values and placing Melee/Ranged compositions genuinely requires those owners' runtime interfaces/archetypes to exist first, per real GDD ownership-split text (Dungeon Encounter Agent role and ownership invariants) rather than any pipeline-prompt closure text.
- Three-to-eight enemy encounter sizing, the never-isolated-Ranged-Enemy rule, and Lower Vault's active-enemy-cap priority validation are preserved as acceptance/validation requirements on the correct owning items rather than invented as new work items.
- Floor Run/Restart has zero current implementation: no orchestrator class, no zero-health event on PlayerHealth, and no reset entry points on any current system (PlayerHealth, PlayerMana, PlayerMovement, DoorInteractable).
- DoorInteractable.cs already owns run-persistent state (Progress, IsOpen, disabled doorwayBlocker) even though the close/lock/durability lifecycle is unimplemented; a bootstrap restart task must reset this existing state, not just health/mana/position.
- Win/Loss Conditions has zero current implementation: no doorway-crossing detector, no Game Flow/Victory capability, no You Escaped overlay, and no suspend/re-enable interfaces on any consumer system.
- Because no enemy, spell, or navigation code exists yet, floor-run-restart-persistent-closure and final-escape-victory both carry multiple currently-unmet cross-domain prerequisites (enemy/door-lifecycle/spell owners) rather than being blocked on ownership ambiguity.
- The routing hint keys (floor-run-restart, floor-run-restart-bootstrap, floor-run-restart-persistent-closure, win-loss-conditions, final-escape-victory) all remain valid current responsibilities under the present GDD and are preserved.
- Per the FRESH RUN CLOSURE and prior verification-round guidance, restart-orchestrator and victory work that wires participants through the current scene builder must carry the DoorPrototypeSceneBuilder.cs/DoorPrototype.unity locks in addition to the logical orchestrator lock.
- EditorBuildSettings.asset confirms zero registered scenes (`m_Scenes: []`), which is a concrete, currently-open build-configuration gap distinct from the general 'produce a Windows build' delivery obligation.
- Packages/manifest.json currently lacks com.unity.2d.tilemap and com.unity.ai.navigation; this is world_foundations-domain evidence and is not represented as a global_pipeline work item, but is noted for cross-domain awareness.
- .gitignore (approved narrow metadata source) confirms UserSettings/ and other Unity editor/user-local state are excluded from the committed repository, consistent with the GDD's process framing; no gameplay/design conclusions were drawn from it.
- All three routed keys from the previous candidate (no-safe-circle, delivery-and-build, windows-build-scene-registration) remain current and required; no stale work was found in this domain.
- Fifteen distinct typed non_code_requirements were identified covering delivery, and pipeline-process/technical constraints scattered across GDD Sections 3, 4, and 5 that were previously only present as prose.
- Seven requirement_overlays were created to attach Section 3 Player Experience Success Criteria validation obligations to concrete owner work items expected to be emitted by other domain workers (doors, enemy_behavior, encounters, player_core, wizard_combat), per the explicit GDD Section 4 instruction that these criteria are required validation obligations on the owning work rather than new features.
- Stretch goals and explicitly excluded systems from Section 3's Required Scope table were each enumerated individually under deferred_or_excluded rather than collapsed into two bulk entries, to make later coverage auditing straightforward.

## Reconciliation Table

| Key | Parent | Kind | Title | GDD basis | Repo state | Graph status | Depends on | Exclusive resources | Decomposition | Execution | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| player | no-safe-circle | feature | Player | GDD §2 Player Actions and Systems; §1 Executive Summary | partial | open |  |  | coarse | not_applicable | high |
| player-movement | player | implementation | Mouse-Directed Player Movement, Shared Pointer Projection, and Movement Restriction | GDD §2 Player Actions and Systems — Move and Aim; GDD §2 Resources, Feedback, and Failure — Player Movement ownership; GDD §2 Loss — Floor-run restart ownership | partial | open |  | repo-file:Assets/InputSystem_Actions.inputactions, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | concrete | single_agent | high |
| player-health | player | implementation | Player Health Ownership, Restore, Death Transition, and Feedback | GDD §2 Resources, Feedback, and Failure — Player Health ownership; GDD §2 Resources, Feedback, and Failure — Health feedback; GDD §2 Loss / Floor-run restart ownership | partial | open |  | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | concrete | single_agent | high |
| player-mana | player | implementation | Player Mana Ownership, Restart Reset, and Denied-Cast Feedback | GDD §2 Resources, Feedback, and Failure — Player Mana ownership; GDD §5 Runtime Implementation; GDD §2 Loss / Floor-run restart ownership | partial | open |  |  | concrete | single_agent | high |
| combat | no-safe-circle | feature | Wizard Combat and Spells | Section 1 — Core Abilities table row; Section 4 — Development Agent Roles, Wizard Combat Agent row | missing | open |  |  | coarse | not_applicable | high |
| fireball | combat | implementation | Charged Fireball | Section 2 — Player Actions and Systems, Fireball row; Section 2 — Spell and Enemy Interactions, Charged Fireball row; Section 2 — Player Movement ownership bullet; Section 2 — Spell-local state ownership bullet; Section 2 — Win and Loss Conditions, Victory/input-shutdown ownership; Section 3 — Required Enemy Roster / Enemy health and defeat ownership bullet; Section 4 — Development Agent Ownership Invariants, Wizard Combat Agent bullet | missing | open | player-movement, enemy-health-damage-defeat | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity, repo-file:Assets/InputSystem_Actions.inputactions | concrete | single_agent | medium |
| frost-field | combat | implementation | Frost Field | Section 2 — Player Actions and Systems, Frost Field row; Section 2 — Frost Field targeting and feedback bullet; Section 2 — Spell-local state ownership bullet; Section 2 — Spell and Enemy Interactions, Frost Field row; Section 4 — Development Agent Roles, Wizard Combat Agent row | missing | open | player-movement, enemy-status-effect-displacement | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity, repo-file:Assets/InputSystem_Actions.inputactions | concrete | single_agent | medium |
| force-wave | combat | implementation | Force Wave | Section 2 — Player Actions and Systems, Force Wave row; Section 2 — Force Wave bullet; Section 2 — Spell-local state ownership bullet; Section 2 — Spell and Enemy Interactions, Force Wave row; Section 5 — Runtime Implementation; Section 2 — Win and Loss Conditions, Victory/input-shutdown ownership | missing | open | enemy-status-effect-displacement | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity, repo-file:Assets/InputSystem_Actions.inputactions | concrete | single_agent | medium |
| enemies | no-safe-circle | feature | Enemies | Section 1 — Required Scope, Exclusions, and Stretch Goals; Section 3 — Active Enemy Registry and Encounter Admission; Section 3 — Enemy health and defeat ownership; Section 2 — Spell-local state ownership | missing | open |  |  | coarse | not_applicable | high |
| active-enemy-registry | enemies | implementation | Active Enemy Registry | Section 3 — Active Enemy Registry and Encounter Admission; Section 3 — Active Enemy Registry and Encounter Admission; Section 3 — Active Enemy Registry and Encounter Admission; Section 2 — Floor-run restart ownership; Section 4 — Enemy Pursuit Agent role | missing | open |  |  | concrete | single_agent | high |
| enemy-health-damage-defeat | enemies | implementation | Enemy Health/Defeat | Section 3 — Enemy health and defeat ownership; Section 3 — Enemy health and defeat ownership; Section 3 — Enemy health and defeat ownership; Section 3 — Enemy health and defeat ownership; Section 5 — Runtime Implementation | missing | open | active-enemy-registry |  | concrete | single_agent | high |
| enemy-status-effect-displacement | enemies | implementation | Enemy Status-Effect and Forced Displacement | Section 2 — Spell-local state ownership; Section 2 — Spell and Enemy Interactions (Frost Field row); Section 5 — Runtime Implementation; Section 5 — Runtime Implementation (enemy movement paragraph); Section 4 — Enemy Pursuit Agent role; Section 5 — 2.5D Isometric Visual and World Representation; Section 2 — Floor-run restart ownership | missing | open | enemy-pursuit-search-foundation, gameplay-navigation-locomotion | logical:enemy-locomotion-behavior-surface | concrete | single_agent | high |
| enemy-pursuit-search-foundation | enemies | implementation | Enemy Detection, Pursuit, and Search/Reacquisition Foundation | Enemy Detection, Pursuit, and Target Loss; Door and Pursuit Rules; Runtime Implementation; Floor-run restart ownership (Win and Loss Conditions) | missing | open | gameplay-navigation-locomotion | logical:enemy-locomotion-behavior-surface | concrete | needs_execution_decomposition | high |
| melee-enemy | enemies | implementation | Melee Enemy Archetype | Required Enemy Roster; Resources, Feedback, and Failure; Spell and Enemy Interactions; Required Enemy Roster; Environment Presentation and Authoring Direction / Runtime Implementation | missing | open | enemy-pursuit-search-foundation, enemy-health-damage-defeat, active-enemy-registry | logical:enemy-locomotion-behavior-surface | concrete | needs_execution_decomposition | high |
| ranged-enemy | enemies | implementation | Ranged Enemy Archetype | Required Enemy Roster; Required Enemy Roster; Runtime Implementation; Spell and Enemy Interactions; Environment Presentation and Authoring Direction / Runtime Implementation | missing | open | enemy-pursuit-search-foundation, enemy-health-damage-defeat, active-enemy-registry | logical:enemy-locomotion-behavior-surface | concrete | needs_execution_decomposition | high |
| locked-door-enemy-attack | enemies | implementation | Locked-Door Enemy Attack Initiation | Door and Pursuit Rules; Locked-door attack and durability ownership; Development Agent Ownership Invariants | missing | open | enemy-pursuit-search-foundation, door-close-lock-break-lifecycle | logical:enemy-locomotion-behavior-surface | concrete | single_agent | high |
| doors | no-safe-circle | feature | Doors and Interaction | Section 1 — Executive Summary / Design Pillars; Section 2 — Player Actions and Systems (Open Sealed Door, Close and Lock); Section 3 — Door and Pursuit Rules | partial | open |  |  | coarse | not_applicable | high |
| door-open-interaction | doors | implementation | Cursor-Targeted Door Opening (Click-to-Approach, Arm's-Reach Auto-Timer, Interruption) | Section 2 — Player Actions and Systems, 'Open Sealed Door'; Section 3 — Door and Pursuit Rules; Section 3 — Player Experience Success Criteria; Section 5 — Runtime Implementation / Player Movement ownership | partial | open | player-movement | repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs, repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerInteractionController.cs, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | concrete | single_agent | high |
| doorway-crossing-state | doors | implementation | Shared Doorway-Crossing State (Forward-Side Crossing Detection) | Section 3 — Door and Pursuit Rules; Section 2 — Win and Loss Conditions; Section 4 — Door and Interaction Agent row; Section 2 — Floor-run restart ownership | missing | open |  | repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | concrete | single_agent | high |
| door-close-lock-break-lifecycle | doors | implementation | Door Close/Lock, Health Restore Request, Durability, and Locked-to-Broken Lifecycle | Section 2 — Player Actions and Systems, 'Close and Lock'; Section 2 — Player Health ownership; Section 2 — Resources, Feedback, and Failure, 'Door feedback'; Section 3 — Door and Pursuit Rules; Section 4 — Door/navigation integration prerequisite; Section 2 — Floor-run restart ownership | missing | open | doorway-crossing-state, player-health, gameplay-navigation-locomotion | repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity, logical:gameplay-walkability-surface | concrete | needs_execution_decomposition | high |
| world | no-safe-circle | feature | World and Unity Foundations | GDD - Environment Presentation and Authoring Direction; GDD - 2.5D Isometric Visual and World Representation | partial | open |  |  | coarse | not_applicable | medium |
| fixed-isometric-camera | world | implementation | Fixed Isometric Camera | GDD - Executive Summary; GDD - 2.5D Isometric Visual and World Representation | implemented | complete |  |  | not_applicable | not_applicable | high |
| tilemap-navigation-package-configuration | world | implementation | Tilemap and AI Navigation Package Configuration | GDD - Approved Unity Packages and Windows Build Configuration; GDD - Approved Unity Packages and Windows Build Configuration | missing | open |  | repo-file:Packages/manifest.json | concrete | single_agent | high |
| gameplay-navigation-locomotion | world | implementation | Gameplay Navigation/Locomotion Foundation | GDD - 2.5D Isometric Visual and World Representation; GDD - Runtime Implementation; GDD - Door and Pursuit Rules (door passability contract); GDD - 2.5D Isometric Visual and World Representation | missing | open | tilemap-navigation-package-configuration | logical:gameplay-walkability-surface, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | concrete | needs_execution_decomposition | medium |
| world-visual-foundation | world | implementation | Tilemap and SpriteRenderer World Visual Foundation | GDD - Environment Presentation and Authoring Direction; GDD - Environment Presentation and Authoring Direction; GDD - Runtime Implementation; GDD - Required feedback and character presentation | missing | open | tilemap-navigation-package-configuration | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | concrete | needs_execution_decomposition | medium |
| encounters | no-safe-circle | feature | Dungeon Encounters | Section 2 — Active Enemy Registry and Encounter Admission; Section 4 — Dungeon Encounter Agent | missing | open |  |  | coarse | not_applicable | high |
| encounter-admission-cap-enforcement | encounters | implementation | Encounter Admission Active-Enemy-Cap Enforcement | Section 2 — Active Enemy Registry and Encounter Admission; Section 2 — Door and Pursuit Rules; Section 4 — Dungeon Encounter Agent / Ownership Invariants | missing | open | active-enemy-registry |  | concrete | single_agent | high |
| five-room-content-authoring | world | feature | Five-Room Floor Content Authoring | Section 3 — Dungeon Floor Structure; Section 5 — 2.5D Isometric Visual and World Representation; Section 5 — Runtime Implementation | missing | open | world-visual-foundation |  | needs_future_decomposition | not_applicable | high |
| dungeon-encounter-content-authoring | encounters | feature | Dungeon Encounter Placement and Composition Authoring | Section 4 — Dungeon Encounter Agent; Section 3 — Required Enemy Roster; Section 3 — Player Experience Success Criteria; Section 2 — Active Enemy Registry and Encounter Admission | missing | open | encounter-admission-cap-enforcement, door-close-lock-break-lifecycle, melee-enemy, ranged-enemy |  | needs_future_decomposition | not_applicable | high |
| floor-run-restart | no-safe-circle | feature | Floor Run/Restart | Win and Loss Conditions; Floor-run restart ownership | missing | open |  |  | coarse | not_applicable | high |
| floor-run-restart-bootstrap | floor-run-restart | implementation | Floor Run/Restart Bootstrap (Current-Owner Stage) | Floor-run restart ownership; Player Health ownership | missing | open | player-health, player-mana, player-movement, door-open-interaction | logical:floor-run-restart-orchestrator, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | concrete | single_agent | high |
| floor-run-restart-persistent-closure | floor-run-restart | implementation | Floor Run/Restart Persistent-Systems Closure | Floor-run restart ownership; Floor-run restart ownership; Spell-local state ownership | missing | open | floor-run-restart-bootstrap, player-health, player-mana, player-movement, door-open-interaction, doorway-crossing-state, door-close-lock-break-lifecycle, enemy-health-damage-defeat, enemy-pursuit-search-foundation, enemy-status-effect-displacement, active-enemy-registry, encounter-admission-cap-enforcement, fireball, frost-field, force-wave | logical:floor-run-restart-orchestrator, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | concrete | needs_execution_decomposition | high |
| win-loss-conditions | no-safe-circle | feature | Win/Loss Conditions | Win and Loss Conditions | missing | open |  |  | coarse | not_applicable | high |
| final-escape-victory | win-loss-conditions | implementation | Final Escape / Victory (Game Flow/Victory Capability) | Win and Loss Conditions; Victory/input-shutdown ownership | missing | open | doorway-crossing-state, player-movement, door-open-interaction, fireball, frost-field, force-wave | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | concrete | needs_execution_decomposition | high |
| no-safe-circle |  | feature | No Safe Circle | Section 1 - Executive Summary | partial | open |  |  | coarse | not_applicable | medium |
| delivery-and-build | no-safe-circle | feature | Delivery and Build | Section 3 - Required Scope, Exclusions, and Stretch Goals; Section 5 - Approved Unity Packages and Windows Build Configuration | missing | open |  |  | coarse | not_applicable | high |
| windows-build-scene-registration | delivery-and-build | implementation | Windows Build Scene Registration | Section 5 - Approved Unity Packages and Windows Build Configuration | missing | open |  | repo-file:ProjectSettings/EditorBuildSettings.asset | concrete | single_agent | high |

## Detailed Evidence

### `player` — Player

- **Kind:** `feature`
- **Type:** `feature`
- **Parent:** `no-safe-circle`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `partial`
- **Proposed graph status:** `open`
- **Decomposition:** `coarse` — Already decomposed into the three concrete owned systems (movement, health, mana) required by the current GDD; no further missing-design problem needs resolving at this organizational level.
- **Execution scope:** `not_applicable` — Organizational feature node; not directly dispatchable.
- **Confidence:** `high`

**GDD evidence**

- `GDD §2 Player Actions and Systems; §1 Executive Summary` — Defines the single required wizard player character and its movement, health, and mana systems.

**Notes:** Aggregate repository_state of partial reflects that PlayerHealth/PlayerMana/PlayerMovement all exist with real behavior but each is missing GDD-required interfaces (restore, reset, cursor projection, movement-restriction, health UI, denied-cast feedback).

### `player-movement` — Mouse-Directed Player Movement, Shared Pointer Projection, and Movement Restriction

- **Kind:** `implementation`
- **Type:** `implementation`
- **Parent:** `player`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `partial`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The required behavior (mouse-directed movement via Input System, shared pointer projection, movement-restriction interface, reset entry point) is fully specified by current GDD text without inventing new design.
- **Execution scope:** `single_agent` — All required responsibilities are cohesively owned by one system (PlayerMovement.cs) plus its Input Actions and builder/scene wiring; it is a bounded rewrite of one component's input/locomotion model rather than a multi-system integration.
- **Confidence:** `high`

**GDD evidence**

- `GDD §2 Player Actions and Systems — Move and Aim` — Mouse-directed movement through the shared Unity Input System/Input Actions layer: click to set a destination or hold to keep steering toward the cursor; Player Movement owns the shared cursor-to-gameplay-plane projection and exposes the resulting world-space pointer target consumed by movement, cursor-aimed spells, and cursor-targeted interactions (Force Wave is the exception).
- `GDD §2 Resources, Feedback, and Failure — Player Movement ownership` — Player Movement owns position, locomotion, movement-restriction state, and the shared cursor-to-gameplay-plane projection; runtime input is routed through Input System/Input Actions rather than direct hardware polling; Charged Fireball requests/releases its movement restriction through an owner-controlled Player Movement interface without mutating movement internals.
- `GDD §2 Loss — Floor-run restart ownership` — Player Movement/player position is a required reset participant invoked by the Floor Run/Restart Orchestrator through an owner-controlled reset entry point.

**Acceptance criteria**

- `GDD §2 Move and Aim` — Movement is mouse-directed: a click sets a destination the wizard walks toward, and holding continues steering toward the current cursor position, consumed through Unity Input System/Input Actions rather than direct hardware polling.
- `GDD §2 Player Movement ownership` — Exposes a shared world-space pointer target produced by projecting the cursor onto the gameplay plane, consumable by cursor-aimed spells and Door/Interaction without those systems independently projecting screen coordinates.
- `GDD §2 Player Movement ownership; §4 Development Agent Ownership Invariants` — Exposes an owner-controlled movement-restriction request/release interface that Charged Fireball can use to restrict movement while charging without Fireball mutating movement internals directly.
- `GDD §2 Floor-run restart ownership` — Exposes an owner-controlled reset entry point that restores player position/movement state to the floor's initial state, consumed by the Floor Run/Restart Orchestrator rather than having position mutated externally.

**Validation requirements**

- `GDD §2 Move and Aim` — Play Mode validation that clicking a location moves the wizard toward it and that holding steers continuously toward the live cursor position.
- `GDD §2 Player Movement ownership` — Validate that the exposed world-space pointer target is correctly consumable by a cursor-aimed spell or Door/Interaction integration once those systems exist.

**Repository evidence**

- `Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs` (`code`) — Implements only CharacterController-driven WASD movement via direct Keyboard.current polling; no mouse-directed movement, cursor projection, movement-restriction interface, or reset entry point exist.
- `Assets/InputSystem_Actions.inputactions` (`project_setting`) — Unmodified stock Unity template action asset; Player map has only WASD/Dpad Move and button actions (Attack/Interact/Crouch/Jump/etc.), no cursor-to-gameplay-plane or click-to-move action, and PlayerMovement.cs does not reference it.
- `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` (`scene`) — PlayerMovement.cs (guid 356044e6782dd0641a7e69b0abfa5c4a) is serialized on the Player GameObject, confirming current WASD movement is the integrated state, not merely available via the builder.

**Exclusive resources**

- `repo-file:Assets/InputSystem_Actions.inputactions` — Adding mouse-directed click/hold movement and cursor-to-gameplay-plane projection through the Input System requires adding or modifying actions/bindings in this single shared actions asset. Evidence/basis: GDD §2 Move and Aim requires routing through Unity Input System/Input Actions; current InputSystem_Actions.inputactions has no click-to-move or cursor-projection action for the Player map.
- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — DoorPrototypeSceneBuilder.BuildPlayer creates and wires PlayerMovement on the canonical Player GameObject; converting to mouse-directed movement requires modifying this builder's player-construction logic. Evidence/basis: DoorPrototypeSceneBuilder.cs BuildPlayer() currently adds and configures PlayerMovement, and the builder destructively clears/recreates the Player root each run.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The builder saves this canonical scene after (re)building the Player hierarchy, so any change to player movement wiring integrates through and re-serializes this scene. Evidence/basis: DoorPrototypeSceneBuilder.Build() calls EditorSceneManager.SaveScene against ScenePath = Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity.

**Notes:** Exact movement speed/feel tuning is left to playtesting per GDD and is not part of this item's required acceptance surface.

### `player-health` — Player Health Ownership, Restore, Death Transition, and Feedback

- **Kind:** `implementation`
- **Type:** `implementation`
- **Parent:** `player`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `partial`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — Required restore, death-transition, feedback, and reset behavior are fully specified by current GDD text without inventing new design; exact recovery/damage values are explicitly deferred to playtesting by the GDD itself.
- **Execution scope:** `single_agent` — Bounded addition to one existing component (PlayerHealth.cs) plus a small new UI component and its builder wiring, mirroring the already-integrated PlayerManaUI pattern.
- **Confidence:** `high`

**GDD evidence**

- `GDD §2 Resources, Feedback, and Failure — Player Health ownership` — The shared Player Health system is the single owner of current health, exposing owner-controlled damage and restore interfaces plus an observable zero-health/death transition consumed by the Floor Run/Restart Orchestrator; restoration is clamped to maximum health and other systems never write player-health state directly.
- `GDD §2 Resources, Feedback, and Failure — Health feedback` — The wizard's current health is continuously visible through a simple player-facing health indicator so accumulated damage is readable across the whole run.
- `GDD §2 Loss / Floor-run restart ownership` — Player Health is a required reset participant with an owner-controlled reset entry point invoked by the Floor Run/Restart Orchestrator.

**Acceptance criteria**

- `GDD §2 Player Health ownership` — Exposes an owner-controlled restore/heal entry point clamped to maximum health, to be requested by Door and Interaction's lock-and-heal behavior rather than Door writing health directly.
- `GDD §2 Player Health ownership` — Exposes an observable zero-health/death transition (e.g. an event) that the Floor Run/Restart Orchestrator can consume without polling health each frame or mutating Player Health internals.
- `GDD §2 Health feedback` — Provides a continuous player-facing health indicator reflecting current/maximum health at all times.
- `GDD §2 Loss / Floor-run restart ownership` — Exposes an owner-controlled reset entry point restoring current health to its floor-initial value, consumed by the Floor Run/Restart Orchestrator.
- `GDD §2 Resources, Feedback, and Failure` — Health does not passively regenerate during or between rooms; it changes only through the owner-controlled damage interface, the owner-controlled restore interface (door-lock recovery), or the orchestrator-invoked floor reset.

**Validation requirements**

- `GDD §3 Player Experience Success Criteria` — Validate that failure is readable through health/damage feedback (contributing cause alongside positioning, mana, and timing failures).
- `Section 3 - Player Experience Success Criteria` — Failure caused by poor positioning is readable to the player through health/damage feedback, as part of the required 'failure is readable' success criterion.

**Repository evidence**

- `Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerHealth.cs` (`code`) — Implements CurrentHealth, a clamped TakeDamage(amount) damage interface, and a Damaged event; has no restore/heal method, no zero-health/death event, and no reset entry point.
- `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` (`scene`) — PlayerHealth.cs (guid ddabb8b125ed06f42863f611de5826f7) is serialized on the Player GameObject, confirming the current damage-only implementation is integrated.
- `Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerInteractionController.cs` (`code`) — Subscribes to PlayerHealth.Damaged to cancel an in-progress door interaction, confirming the existing damage event is consumed elsewhere, but no analogous health-UI or death-event consumer exists.

**Exclusive resources**

- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — No PlayerHealth UI component currently exists; adding the required continuous health indicator will follow the same builder-wired pattern already used for PlayerManaUI (BuildManaUI/BuildUI), requiring changes to this builder. Evidence/basis: DoorPrototypeSceneBuilder.BuildUI/BuildManaUI currently constructs and wires PlayerManaUI into the canonical scene's Canvas but has no equivalent call for player health.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The builder saves this canonical scene after adding the new health UI/wiring, so the change integrates through and re-serializes this scene. Evidence/basis: DoorPrototypeSceneBuilder.Build() calls EditorSceneManager.SaveScene against ScenePath = Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity.

**Notes:** Exact fixed door-lock recovery amount is an explicitly deferred playtesting value per GDD; this item only needs to expose the clamped restore interface, not decide the tuning number.

### `player-mana` — Player Mana Ownership, Restart Reset, and Denied-Cast Feedback

- **Kind:** `implementation`
- **Type:** `implementation`
- **Parent:** `player`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `partial`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — Required reset and denied-cast-signal behavior are fully specified by current GDD text without inventing new design; exact feedback presentation is explicitly an implementation choice.
- **Execution scope:** `single_agent` — Bounded addition to one existing component (PlayerMana.cs) that does not require new scene-wired UI, since the existing PlayerManaUI/fill Image can consume a new denied-cast event without builder changes.
- **Confidence:** `high`

**GDD evidence**

- `GDD §2 Resources, Feedback, and Failure — Player Mana ownership` — The shared Player Mana system is the single owner of current mana and the post-cast regeneration-delay state; spells spend mana through its owner-controlled spend interface; Player Mana does not own spell-local cooldown/charge/cast/placement/active-field state.
- `GDD §5 Runtime Implementation` — Player Mana owns current mana and post-cast regeneration-delay state and exposes an owner-controlled spend/reset interface to spells and restart orchestration.
- `GDD §2 Loss / Floor-run restart ownership` — Player Mana and its regeneration-delay state are required reset participants for the Floor Run/Restart Orchestrator.

**Acceptance criteria**

- `GDD §5 Runtime Implementation` — Exposes an owner-controlled reset entry point that restores current mana to full and clears post-cast regeneration-delay timer state for floor restart.
- `GDD §3 Player Experience Success Criteria — Failure is readable` — Exposes a signal (e.g. an event) when a cast attempt is denied due to insufficient mana, distinct from a successful spend, so a consuming spell/UI can present readable low-mana feedback; exact presentation is an implementation choice.
- `GDD §2 Player Mana ownership` — Continues to own only current mana and post-cast regeneration-delay state; does not absorb Fireball/Frost Field/Force Wave spell-local cooldown, charge, cast, placement, or active-field state.

**Validation requirements**

- `GDD §2 Resources, Feedback, and Failure` — Existing Play Mode coverage of Spend/regen/post-cast-delay behavior (PlayerManaPlayModeTests.cs) continues to pass and is extended to cover the new reset entry point and denied-cast signal.
- `GDD §3 Player Experience Success Criteria` — Validate that failure is readable through low-mana feedback as one of the stated readable failure causes.
- `Section 3 - Player Experience Success Criteria` — Failure caused by low mana is readable to the player through the mana indicator, as part of the required 'failure is readable' success criterion.

**Repository evidence**

- `Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMana.cs` (`code`) — Implements CurrentMana/MaxMana, Spend(amount) with silent-fail-on-insufficient behavior, Tick-driven post-cast-delay regeneration, and a ManaSpent event; no reset entry point and no denied-cast event exist.
- `Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerManaUI.cs` (`code`) — Continuously binds a fill Image to CurrentMana/MaxMana every Update, satisfying the GDD's continuous mana indicator requirement.
- `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` (`scene`) — Both PlayerMana.cs (guid fd54c6f00e974856b70833ac4771b9ae) and PlayerManaUI.cs (guid 0a03ab321b0847f59d3f91214dabcf5c) are serialized and wired on the Player/Canvas GameObjects, confirming the continuous mana indicator is currently integrated, not just buildable.
- `Assets/NoSafeCircle/DoorPrototype/Tests/PlayerManaPlayModeTests.cs` (`test`) — Real Play Mode tests cover Spend success/failure, post-cast-delay non-regeneration, regeneration after delay, and delay-reset on subsequent spend.

**Notes:** Force Wave's 25-mana cost and other spell-local spend amounts remain owned by the individual spells, not this item; this item only owns the shared pool, regen-delay, spend interface, reset, and denied-cast signal.

### `combat` — Wizard Combat and Spells

- **Kind:** `feature`
- **Type:** `feature-group`
- **Parent:** `no-safe-circle`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `coarse` — The three required spells are each independently concrete; this node is a pure organizational grouping and needs no further decomposition of its own beyond its three children.
- **Execution scope:** `not_applicable` — Feature/organizational node; not directly dispatchable.
- **Confidence:** `high`

**GDD evidence**

- `Section 1 — Core Abilities table row` — Core Abilities: Charged Fireball, Frost Field, Force Wave.
- `Section 4 — Development Agent Roles, Wizard Combat Agent row` — Wizard Combat Agent implements player movement/Input System consumption, cursor-targeting projection, Fireball, Frost Field's casting/mana cost/feedback, Force Wave, health, mana, cooldowns, and recovery, without editing enemy-movement or enemy-attack code.

**Notes:** Aggregate repository_state is 'missing' because all three represented children (fireball, frost-field, force-wave) are currently unimplemented.

### `fireball` — Charged Fireball

- **Kind:** `implementation`
- **Type:** `spell`
- **Parent:** `combat`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — GDD Section 2 fully specifies Fireball's tap/charge behavior, cost/restriction relationship, and area-vs-single-target tradeoff; no missing design blocks representing it as one bounded implementation item.
- **Execution scope:** `single_agent` — Fireball is one cohesive spell component (tap/charge/cast state, mana spend, movement-restriction request, enemy-damage request, reset, suspend) matching the GDD's own granularity for a single agent task; the anti-decomposition instruction explicitly disallows splitting a spell into projectile/input/damage subtasks absent further approved design.
- **Confidence:** `medium`

**GDD evidence**

- `Section 2 — Player Actions and Systems, Fireball row` — Aim with the cursor. Tap for a quick, mobile shot against a single/separated enemy. Hold to charge: costs more mana and restricts movement further, rewarding preparation by damaging multiple clustered enemies.
- `Section 2 — Spell and Enemy Interactions, Charged Fireball row` — Melee enemies naturally cluster while pursuing, making them strong area-damage targets; charging becomes unsafe once they close distance. Against Ranged Enemies, telegraphed attacks force movement, reducing available charge time; quick shots are safer but do less damage/area.
- `Section 2 — Player Movement ownership bullet` — Charged Fireball requests and releases its charging movement restriction through an owner-controlled Player Movement interface; Fireball does not directly mutate movement internals.
- `Section 2 — Spell-local state ownership bullet` — Fireball owns its tap/charge/cast state... Each owner exposes a reset entry point for any owned state that can still be active when a floor restart occurs.
- `Section 2 — Win and Loss Conditions, Victory/input-shutdown ownership` — Fireball exposes an owner-controlled gameplay-enable/suspend interface that can immediately stop/cancel current input-driven activity, reject new commands while suspended, and be re-enabled by an authorized reset/test flow.
- `Section 3 — Required Enemy Roster / Enemy health and defeat ownership bullet` — Fireball and any other canon-required damage source request damage through the Enemy Health/Defeat owner-controlled interface rather than writing enemy health directly.
- `Section 4 — Development Agent Ownership Invariants, Wizard Combat Agent bullet` — Charged Fireball consumes the Player Movement restriction interface instead of mutating movement internals; spells consume Player Mana through its spend interface.

**Acceptance criteria**

- `Section 2 — Player Actions and Systems, Fireball row` — Tap-cast produces a quick, mobile, cursor-aimed shot suited to a single or separated enemy; hold-to-charge costs more mana, restricts movement further, and deals area damage effective against clustered enemies.
- `Section 2 — Player Movement ownership bullet` — While charging, Fireball requests the charging movement restriction through an owner-controlled Player Movement interface and releases it when charging ends/cancels/fires; Fireball never mutates Player Movement internals directly.
- `Section 2 — Resources, Feedback, and Failure / Development Agent Ownership Invariants` — Fireball spends mana for both tap and charge casts through Player Mana's existing owner-controlled Spend interface, with charge costing more than tap.
- `Section 3 — Enemy health and defeat ownership bullet` — Fireball damages enemies only by requesting damage through the Enemy Health/Defeat owner-controlled damage interface; it does not write enemy health directly.
- `Section 2 — Player Movement ownership / Runtime Implementation` — Fireball consumes the shared world-space pointer target exposed by Player Movement for cursor aiming rather than independently projecting screen coordinates.
- `Section 5 — Runtime Implementation / Section 2 Player Movement ownership bullet` — Fireball's casting input (tap/charge/release) is routed through the project's Unity Input System/Input Actions layer rather than independent direct hardware polling.
- `Section 2 — Spell-local state ownership bullet` — Fireball owns its tap/charge/cast state and exposes an owner-controlled reset entry point for that state, consumed by the Floor Run/Restart Orchestrator, so no residual charge/cast state survives a floor restart.
- `Section 2 — Victory/input-shutdown ownership bullet` — Fireball exposes an owner-controlled gameplay-enable/suspend interface that immediately stops active charging/casting, rejects new cast input while suspended, and can be re-enabled by an authorized reset/test flow, consumed by the Game Flow/Victory capability.

**Validation requirements**

- `Section 2 — Spell and Enemy Interactions table / Section 3 Ruined Entry tactical purpose` — Validate that a full charge produces meaningful area damage against multiple naturally-clustering pursuing Melee Enemies, not just a single target, and that charging is interruptible/unsafe once enemies close distance.
- `Section 2 — Spell and Enemy Interactions, Charged Fireball vs Ranged row` — Validate that a tap shot remains usable against a Ranged Enemy's telegraphed attack pattern where a full charge is impractical.
- `Section 2 — Floor-run restart ownership` — Validate that triggering a floor restart while Fireball is mid-charge/mid-cast clears that state through Fireball's own reset entry point rather than leaving residual charge/cooldown state.

**Exclusive resources**

- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — Attaching and wiring a Fireball component onto the scene-built Player GameObject requires modifying BuildPlayer/Build in this builder. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs — BuildPlayer() currently instantiates and wires PlayerMovement, PlayerHealth, PlayerMana, and their debug controls onto one Player GameObject; Build() clears and rebuilds known roots including Player every run.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The builder saves this scene on every run; any scene-integrated Fireball wiring is written to this same canonical scene file. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs — Build() calls EditorSceneManager.SaveScene(scene, ScenePath) against DoorPrototype.unity.
- `repo-file:Assets/InputSystem_Actions.inputactions` — Fireball needs a tap-vs-hold-distinguishing cast action that does not currently exist in the shared Input Actions asset and must add/modify bindings there. Evidence/basis: Assets/InputSystem_Actions.inputactions — the Player map's only combat-adjacent action is 'Attack' (Button, Mouse leftButton, no Hold interaction configured); no Fireball-specific action or tap/charge interaction exists.

**Dependencies**

- `player-movement` — Fireball is cursor-aimed and requires the Player-Movement-owned shared cursor-to-gameplay-plane pointer target for tap/charge aiming, plus an owner-controlled movement-restriction request/release interface for charging. Current PlayerMovement.cs is WASD-only CharacterController input with no cursor projection and no restriction interface, so both specific capabilities Fireball needs are unfinished. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs — Update() reads only Keyboard.current WASD axes into CharacterController.Move; no mouse/pointer projection, no Input Actions asset consumption, and no public restriction/modifier interface exist.
- `enemy-health-damage-defeat` — Fireball must request enemy damage through the Enemy Health/Defeat owner-controlled interface rather than writing enemy health directly, but no such capability currently exists. Evidence/basis: No enemy or enemy-health/defeat script exists anywhere under Assets/NoSafeCircle (confirmed via targeted search for Enemy-related class definitions); there is no owner interface for Fireball to consume yet.

**Notes:** Currently blocked on two real cross-domain prerequisites (player-movement's cursor/restriction interfaces, enemy-health-damage-defeat's damage interface); no dependency on player-mana is needed because PlayerMana.Spend already exists and is directly usable.

### `frost-field` — Frost Field

- **Kind:** `implementation`
- **Type:** `spell`
- **Parent:** `combat`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — GDD fully specifies Frost Field's targeting, ownership split (Wizard Combat triggers; Enemy Pursuit applies/restores), and feedback requirement; no missing design blocks a single bounded implementation item.
- **Execution scope:** `single_agent` — Frost Field is one cohesive spell component (cast/placement/active-field state, mana spend, feedback, trigger call to the enemy-owned status-effect interface, reset, suspend); splitting it further is not supported by approved design.
- **Confidence:** `medium`

**GDD evidence**

- `Section 2 — Player Actions and Systems, Frost Field row` — Place a temporary area at the current cursor world-space target that heavily slows enemies; Frost Field consumes the shared pointer target exposed by Player Movement rather than projecting screen coordinates independently.
- `Section 2 — Frost Field targeting and feedback bullet` — Frost Field is placed at the current shared world-space pointer target exposed by Player Movement. The cast and active field provide player-facing feedback that makes the targeted placement and active effect readable while it is being placed/used.
- `Section 2 — Spell-local state ownership bullet` — Frost Field owns its Wizard-Combat-side cast/placement/active-field state. Enemy-side Frost slowdown application/restoration remains owned by Enemy Pursuit/status-effect logic. Each owner exposes a reset entry point for owned state active at restart.
- `Section 2 — Spell and Enemy Interactions, Frost Field row` — Strongest against melee groups (slows pursuit, stretches formation, creates a Fireball/door opening) though it draws a meaningful share of the shared mana pool. Against Ranged Enemies, slows repositioning but does not stop attacks.
- `Section 4 — Development Agent Roles, Wizard Combat Agent row` — Frost Field's actual slowdown effect is applied and restored by the Enemy Pursuit Agent; the Wizard Combat Agent only triggers the Frost Field effect and does not implement Ranged Enemy targeting or attacks.

**Acceptance criteria**

- `Section 2 — Player Actions and Systems / Frost Field targeting and feedback bullet` — Frost Field places its temporary slow area at the current shared world-space pointer target exposed by Player Movement, without independently projecting screen-to-world coordinates.
- `Section 2 — Frost Field targeting and feedback bullet` — Frost Field provides player-facing feedback that makes the cast and the active field readable during placement and while active; the exact visual/audio treatment is an implementation choice.
- `Section 4 — Wizard Combat Agent row` — Frost Field triggers the enemy slowdown effect through the Enemy Pursuit/status-effect owner-controlled interface; it does not itself implement enemy slowdown application, restoration, Ranged Enemy targeting, or Ranged Enemy attacks.
- `Section 2 — Resources, Feedback, and Failure / Development Agent Ownership Invariants` — Frost Field spends mana through Player Mana's existing owner-controlled Spend interface when cast.
- `Section 5 — Runtime Implementation` — Frost Field's casting input is routed through the project's Unity Input System/Input Actions layer rather than independent direct hardware polling.
- `Section 2 — Spell-local state ownership bullet` — Frost Field owns its Wizard-Combat-side cast/placement/active-field state and exposes an owner-controlled reset entry point for that state, consumed by the Floor Run/Restart Orchestrator.
- `Section 2 — Victory/input-shutdown ownership bullet` — Frost Field exposes an owner-controlled gameplay-enable/suspend interface that immediately stops active casting/placement, rejects new cast input while suspended, and can be re-enabled by an authorized reset/test flow, consumed by the Game Flow/Victory capability.

**Validation requirements**

- `Section 2 — Spell and Enemy Interactions, Frost Field row` — Validate that casting Frost Field creates a readable opening against a melee group (stretches pursuit) without itself guaranteeing a fully safe Fireball charge in every position, matching the resource-tradeoff description.
- `Section 2 — Floor-run restart ownership` — Validate that triggering a floor restart while a Frost Field cast/placement is active clears Frost Field's own casting-side state through its reset entry point.

**Exclusive resources**

- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — Attaching and wiring a Frost Field component onto the scene-built Player GameObject requires modifying this builder. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs — BuildPlayer() currently wires PlayerMovement/PlayerHealth/PlayerMana onto one Player GameObject and Build() rebuilds/saves the scene every run.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The builder saves this scene on every run; scene-integrated Frost Field wiring is written to this same canonical scene file. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs — Build() calls EditorSceneManager.SaveScene(scene, ScenePath) against DoorPrototype.unity.
- `repo-file:Assets/InputSystem_Actions.inputactions` — Frost Field needs its own cast action, which does not currently exist in the shared Input Actions asset. Evidence/basis: Assets/InputSystem_Actions.inputactions — no Frost-Field-specific action exists in the Player action map.

**Dependencies**

- `player-movement` — Frost Field's placement target is explicitly the shared world-space pointer target owned by Player Movement, which does not yet exist (current PlayerMovement.cs has no cursor-to-gameplay-plane projection at all). Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs — no mouse/pointer projection or exposed world-space pointer target exists; only WASD CharacterController input is implemented.
- `enemy-status-effect-displacement` — Frost Field only triggers the slow effect; the actual slowdown application/restoration is owned by the Enemy Pursuit/status-effect capability, which does not exist because no enemy scripts exist at all. Evidence/basis: No status-effect/displacement or enemy script exists anywhere under Assets/NoSafeCircle; there is no owner interface for Frost Field to call yet.

**Notes:** No dependency on player-mana is needed because PlayerMana.Spend already exists and is directly usable; Frost Field's real prerequisites are the still-unfinished Player-Movement pointer projection and the still-unfinished Enemy Pursuit status-effect owner.

### `force-wave` — Force Wave

- **Kind:** `implementation`
- **Type:** `spell`
- **Parent:** `combat`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — GDD fully specifies Force Wave's radial/player-centered aiming model, cost, cooldown role, and displacement-request ownership split; no missing design blocks a single bounded implementation item.
- **Execution scope:** `single_agent` — Force Wave is a small, self-contained spell component (cooldown state, mana spend, radius-based enemy-affected query, displacement request, reset, suspend) with no cursor-aiming complexity; it fits one focused agent task.
- **Confidence:** `medium`

**GDD evidence**

- `Section 2 — Player Actions and Systems, Force Wave row` — Use a player-centered short-range radial knockback with a long cooldown. Each cast costs 25 mana. Force Wave does not use cursor direction or target selection.
- `Section 2 — Force Wave bullet` — Each cast spends 25 mana through Player Mana and also starts its visible long cooldown. Twenty-five mana is the initial implementation/balance value; Force Wave remains a mana-consuming spell unless the GDD is revised.
- `Section 2 — Spell-local state ownership bullet` — Force Wave owns its cooldown state... exposes a reset entry point for any owned state that can still be active when a floor restart occurs.
- `Section 2 — Spell and Enemy Interactions, Force Wave row` — The primary emergency response when melee enemies surround the wizard or block a door; long cooldown prevents repeated use. Its short range makes it a poor answer to distant ranged pressure.
- `Section 5 — Runtime Implementation` — Force Wave determines which enemies are affected and the radial knockback to request; the enemy movement system applies that displacement, preserves valid navigation state, and resumes the appropriate pursuit/search state afterward.
- `Section 2 — Win and Loss Conditions, Victory/input-shutdown ownership` — Force Wave exposes an owner-controlled gameplay-enable/suspend interface consumed by the victory capability.

**Acceptance criteria**

- `Section 2 — Player Actions and Systems, Force Wave row` — Force Wave is a player-centered short-range radial knockback that does not use cursor direction or target selection, with a long cooldown limiting reuse.
- `Section 2 — Force Wave bullet` — Each cast spends 25 mana (initial tuning value) through Player Mana's existing owner-controlled Spend interface and starts Force Wave's own visible long cooldown; the cast is refused if the spend fails.
- `Section 5 — Runtime Implementation` — Force Wave determines which enemies within its radius are affected and requests the radial knockback displacement through the Enemy Pursuit/status-effect-displacement owner-controlled interface; Force Wave does not directly move enemies or manipulate their navigation/pursuit state.
- `Section 5 — Runtime Implementation / Section 2 Player Movement ownership bullet` — Force Wave's cast input is routed through the project's Unity Input System/Input Actions layer rather than independent direct hardware polling.
- `Section 2 — Spell-local state ownership bullet` — Force Wave owns its cooldown state and exposes an owner-controlled reset entry point for that state, consumed by the Floor Run/Restart Orchestrator.
- `Section 2 — Victory/input-shutdown ownership bullet` — Force Wave exposes an owner-controlled gameplay-enable/suspend interface that immediately stops any current cast activity, rejects new cast input while suspended, and can be re-enabled by an authorized reset/test flow, consumed by the Game Flow/Victory capability.

**Validation requirements**

- `Section 2 — Spell and Enemy Interactions, Force Wave row` — Validate Force Wave functions as an effective emergency response against a surrounding melee cluster or a group blocking a door, and confirm its short range makes it ineffective against distant Ranged Enemy pressure.
- `Section 2 — Design Pillars / narrative resource-tension text` — Validate the cooldown is long enough that an encounter space typically allows only about one meaningful Force Wave use, matching the intended resource-decision tension (spend mid-room vs. save for the door).
- `Section 2 — Floor-run restart ownership` — Validate that triggering a floor restart while Force Wave's cooldown is active clears the cooldown through Force Wave's own reset entry point.
- `Section 3 - Player Experience Success Criteria` — Failure caused by using Force Wave without an immediate threat and then lacking it during a later critical moment, due to its long cooldown, is readable to the player.

**Exclusive resources**

- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — Attaching and wiring a Force Wave component onto the scene-built Player GameObject requires modifying this builder. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs — BuildPlayer() currently wires PlayerMovement/PlayerHealth/PlayerMana onto one Player GameObject and Build() rebuilds/saves the scene every run.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The builder saves this scene on every run; scene-integrated Force Wave wiring is written to this same canonical scene file. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs — Build() calls EditorSceneManager.SaveScene(scene, ScenePath) against DoorPrototype.unity.
- `repo-file:Assets/InputSystem_Actions.inputactions` — Force Wave needs its own cast action, which does not currently exist in the shared Input Actions asset. Evidence/basis: Assets/InputSystem_Actions.inputactions — no Force-Wave-specific action exists in the Player action map.

**Dependencies**

- `enemy-status-effect-displacement` — Force Wave only determines affected enemies and requests knockback; actual displacement application, navigation-state preservation, and pursuit/search-state resumption are owned by the Enemy Pursuit/status-effect-displacement capability, which does not exist because no enemy scripts exist at all. Evidence/basis: No status-effect/displacement or enemy script exists anywhere under Assets/NoSafeCircle; there is no owner interface for Force Wave to call yet.

**Notes:** No dependency on player-movement because Force Wave is the GDD's explicit player-centered, no-cursor-targeting exception; no dependency on player-mana because PlayerMana.Spend already exists and is directly usable.

### `enemies` — Enemies

- **Kind:** `feature`
- **Type:** `feature`
- **Parent:** `no-safe-circle`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `coarse` — This is an organizational parent for shared enemy state/persistence capabilities. The GDD already specifies enough for the three concrete child implementation items below (registry, health/defeat, status-effect/displacement); no further top-level decomposition is needed for this bootstrap. Enemy archetype behavior (Melee/Ranged pursuit, attacks, locked-door attack) is owned by the separate enemy_behavior domain and is not represented under this node's evidence to avoid duplicate ownership.
- **Execution scope:** `not_applicable` — Feature/organizational node; not directly dispatchable.
- **Confidence:** `high`

**GDD evidence**

- `Section 1 — Required Scope, Exclusions, and Stretch Goals` — Required scope includes 'two enemies' (Melee Enemy and Ranged Enemy) as part of the required game.
- `Section 3 — Active Enemy Registry and Encounter Admission` — A shared Active Enemy Registry tracks persistent active enemy objects and enforces a hard 15-active-enemy cap.
- `Section 3 — Enemy health and defeat ownership` — A reusable Enemy Health/Defeat capability owns each persistent enemy object's health, damage intake, and defeat transition.
- `Section 2 — Spell-local state ownership` — Enemy-side Frost slowdown application/restoration is owned by Enemy Pursuit/status-effect logic, distinct from the spell that triggers it.

**Notes:** Aggregate repository_state is missing because none of this domain's represented child work (registry, health/defeat, status-effect/displacement) currently exists anywhere in Assets/. Enemy roster stats, pursuit/attack behavior, and locked-door attack ownership belong to the enemy_behavior domain's nodes (enemy-pursuit-search-foundation, melee-enemy, ranged-enemy, locked-door-enemy-attack) and are intentionally not duplicated here.

### `active-enemy-registry` — Active Enemy Registry

- **Kind:** `implementation`
- **Type:** `implementation`
- **Parent:** `enemies`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD fully specifies this capability's contract: what it tracks, the hard cap, register/unregister semantics, what does NOT remove an enemy, and reset participation. No missing design blocks turning this into a bounded implementation item.
- **Execution scope:** `single_agent` — Self-contained bookkeeping component (count/capacity tracking with register/unregister and a reset entry point) with no other current-repository system to integrate against; a single agent can implement and validate it in isolation.
- **Confidence:** `high`

**GDD evidence**

- `Section 3 — Active Enemy Registry and Encounter Admission` — A shared Active Enemy Registry tracks the persistent enemy objects currently active in the run and exposes the current active count and remaining capacity under the hard limit of fifteen.
- `Section 3 — Active Enemy Registry and Encounter Admission` — Enemy activation registers an enemy with the registry; defeat removes that enemy from the active count. Target loss, searching, crossing rooms, or waiting behind a locked door does not remove a surviving persistent enemy from the registry.
- `Section 3 — Active Enemy Registry and Encounter Admission` — The registry/bookkeeping responsibility is a reusable runtime foundation and does not require the exact five-room encounter layouts, placements, or trigger authoring to be known first.
- `Section 2 — Floor-run restart ownership` — Active Enemy Registry bookkeeping is a required reset participant invoked through the registry's own owner-controlled reset entry point during floor restart.
- `Section 4 — Enemy Pursuit Agent role` — Enemy Pursuit Agent owns the shared Active Enemy Registry bookkeeping for persistent active enemy objects; encounter activation consumes that registry rather than maintaining a separate count.

**Acceptance criteria**

- `Section 3 — Active Enemy Registry and Encounter Admission` — Registry exposes the current active enemy count and remaining capacity under the hard cap of fifteen active enemies.
- `Section 3 — Active Enemy Registry and Encounter Admission` — Enemy activation registers an enemy; only a defeat-driven unregister call (consumed by Enemy Health/Defeat) removes an enemy from the active count.
- `Section 3 — Active Enemy Registry and Encounter Admission` — Target loss, entering search state, crossing between rooms, and waiting behind a locked door do not remove a surviving persistent enemy from the registry.
- `Section 2 — Floor-run restart ownership` — Registry exposes an owner-controlled reset entry point that returns bookkeeping to its initial empty/starting state; the Floor Run/Restart Orchestrator invokes this rather than mutating registry internals directly.

**Validation requirements**

- `Section 3 — Active Enemy Registry and Encounter Admission` — Verify the registry's reported active count and remaining capacity stay accurate as enemies are registered and unregistered, including at the fifteen-enemy hard cap boundary.
- `Section 3 — Active Enemy Registry and Encounter Admission` — Verify target loss, search-state transition, room crossing, and waiting behind a locked door do not remove a surviving enemy from the registry's active count.
- `Section 2 — Floor-run restart ownership` — Verify floor restart returns registry bookkeeping to its initial empty/starting state through its owner-controlled reset entry point.

**Notes:** A repository-wide grep across Assets/ for 'Registry' found no matches; this component does not exist in any form, including as builder-capability scaffolding.

### `enemy-health-damage-defeat` — Enemy Health/Defeat

- **Kind:** `implementation`
- **Type:** `implementation`
- **Parent:** `enemies`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD fully specifies health/damage/defeat ownership, the damage-interface contract, the registry-removal reporting contract, and reset participation. No missing design blocks a bounded implementation item.
- **Execution scope:** `single_agent` — A cohesive, bounded component (health tracking, damage interface, defeat transition, one outbound call to the registry's interface, and a reset entry point) that one agent can implement and validate without needing to also implement pursuit, attacks, or navigation.
- **Confidence:** `high`

**GDD evidence**

- `Section 3 — Enemy health and defeat ownership` — A reusable Enemy Health/Defeat capability owns each persistent enemy object's current health, damage intake, defeat transition, and restartable health/defeat state.
- `Section 3 — Enemy health and defeat ownership` — Fireball and any other canon-required damage source request damage through this owner-controlled interface rather than writing enemy health directly.
- `Section 3 — Enemy health and defeat ownership` — When defeat occurs, the Enemy Health/Defeat owner reports that transition through the Active Enemy Registry owner's removal/unregister interface so the active count is updated without duplicating registry bookkeeping.
- `Section 3 — Enemy health and defeat ownership` — Floor restart restores enemy health/defeat state through the enemy-owned reset entry point; the Floor Run/Restart Orchestrator does not mutate enemy-health internals directly.
- `Section 5 — Runtime Implementation` — A reusable Enemy Health/Defeat runtime capability owns each persistent enemy's current health, damage intake, defeat transition, and floor-restart reset.

**Acceptance criteria**

- `Section 3 — Enemy health and defeat ownership` — Exposes an owner-controlled damage-intake interface that any canon-required damage source (e.g. Fireball) calls rather than writing enemy health directly.
- `Section 3 — Enemy health and defeat ownership` — Reaching zero health triggers a defeat transition exactly once for that persistent enemy object.
- `Section 3 — Enemy health and defeat ownership` — Defeat reports removal through the Active Enemy Registry's owner-controlled unregister interface rather than the Enemy Health/Defeat component independently decrementing a separate count.
- `Section 3 — Enemy health and defeat ownership` — Exposes an owner-controlled reset entry point that restores health and clears the defeat transition for floor restart, invoked by the Floor Run/Restart Orchestrator rather than by direct internal mutation.

**Validation requirements**

- `Section 3 — Enemy health and defeat ownership` — Verify a damage source can only reduce a persistent enemy's health through the owner-controlled damage interface and that zero health triggers the defeat transition exactly once.
- `Section 3 — Enemy health and defeat ownership` — Verify defeat reports removal through the Active Enemy Registry's unregister interface without the registry double-counting or the two systems maintaining duplicate bookkeeping.
- `Section 2 — Floor-run restart ownership` — Verify floor restart returns a previously-damaged/defeated enemy's health and defeat state to its initial value through the owner-controlled reset entry point.

**Dependencies**

- `active-enemy-registry` — Defeat must report removal through the Active Enemy Registry's own owner-controlled unregister interface rather than duplicating active-count bookkeeping; that interface must exist first. Evidence/basis: GDD Section 3 — Enemy health and defeat ownership: 'the Enemy Health/Defeat owner reports that transition through the Active Enemy Registry owner's removal/unregister interface so the active count is updated without duplicating registry bookkeeping.'

**Notes:** A repository-wide grep across Assets/ for 'Defeat' found no matches; this capability does not exist in any form. Fireball's consumption of this interface is out of scope for this domain and belongs to the wizard_combat domain's fireball item.

### `enemy-status-effect-displacement` — Enemy Status-Effect and Forced Displacement

- **Kind:** `implementation`
- **Type:** `implementation`
- **Parent:** `enemies`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD fully specifies this component's two effect types (Frost slowdown apply/restore; forced displacement apply/restore), the explicit Ranged-Enemy-attack-is-unaffected constraint, the pursuit/search hand-back requirement, and reset participation. No missing design blocks a bounded implementation item; the two effect types are explicitly bundled into one reusable component by GDD Section 5.
- **Execution scope:** `single_agent` — Although it consumes two other systems' interfaces (pursuit/search contract, navigation layer) and covers two effect types, it is architecturally one reusable component with a clear, bounded validation target (apply/restore semantics for each effect plus a reset entry point); the GDD itself describes it as a single reusable component rather than multiple independently-owned pieces.
- **Confidence:** `high`

**GDD evidence**

- `Section 2 — Spell-local state ownership` — Enemy-side Frost slowdown application/restoration remains owned by Enemy Pursuit/status-effect logic. Each owner exposes a reset entry point for any owned state that can still be active when a floor restart occurs.
- `Section 2 — Spell and Enemy Interactions (Frost Field row)` — Frost Field slows a ranged enemy's repositioning but does not stop its attacks; the player must still move laterally or use room geometry to avoid incoming shots.
- `Section 5 — Runtime Implementation` — A reusable status-effect/displacement component will apply Frost Field slowdown, apply enemy-owned forced displacement requests, and restore each enemy to the appropriate pursuit/search movement state afterward. It consumes the pursuit/search state contract rather than defining a second enemy-state machine.
- `Section 5 — Runtime Implementation (enemy movement paragraph)` — Enemy movement is the authoritative owner of enemy locomotion and forced displacement. Force Wave determines which enemies are affected and the radial knockback to request; the enemy movement system applies that displacement, preserves valid movement/navigation state, and resumes the appropriate pursuit/search state afterward.
- `Section 4 — Enemy Pursuit Agent role` — Owns the application of forced enemy displacement requested by abilities such as Force Wave, including returning affected enemies to the appropriate pursuit/search movement state afterward, and owns applying/restoring Frost Field's slowdown effect.
- `Section 5 — 2.5D Isometric Visual and World Representation` — Enemy pursuit/search, melee/ranged behavior, status effects, and forced displacement consume the shared gameplay navigation/locomotion layer instead of each selecting or configuring navigation technology or doorway passability independently.
- `Section 2 — Floor-run restart ownership` — Required reset participants include enemy pursuit/search/attack/status/displacement state, restored through the state-owning system's reset entry point.

**Acceptance criteria**

- `Section 2 — Spell and Enemy Interactions (Frost Field row)` — Frost Field slowdown modifies an affected enemy's locomotion/repositioning speed only; it must never suppress, pause, or slow a Ranged Enemy's attack execution/timing.
- `Section 5 — Runtime Implementation` — Frost slowdown is restored (movement speed returns to normal) when the effect ends, with no permanent slowdown remaining.
- `Section 5 — Runtime Implementation (enemy movement paragraph)` — Applies forced displacement requested by an ability (e.g. Force Wave's radial knockback selection) to the affected enemy while preserving valid movement/navigation state.
- `Section 5 — Runtime Implementation` — After displacement or Frost slowdown ends, returns the affected enemy to the appropriate pursuit/search movement state per the pursuit/search state contract, rather than defining a second enemy-state machine.
- `Section 2 — Spell-local state ownership` — Exposes an owner-controlled reset entry point that clears any active Frost slowdown or displacement state for floor restart, invoked by the Floor Run/Restart Orchestrator.

**Validation requirements**

- `Section 5 — Runtime Implementation` — Verify Frost Field slowdown applies to a pursuing enemy's movement speed and is fully restored when the effect ends, with no permanent slowdown remaining (Unity Validation Agent concern in Section 4).
- `Section 5 — Runtime Implementation (enemy movement paragraph)` — Verify forced displacement (e.g. Force Wave knockback) moves an affected enemy while preserving valid navigation/movement state and that the enemy resumes appropriate pursuit/search behavior afterward rather than becoming stuck.
- `Section 2 — Spell and Enemy Interactions (Frost Field row)` — Verify a Ranged Enemy under active Frost slowdown continues executing its telegraphed attack on schedule while only its repositioning speed is reduced.
- `Section 2 — Floor-run restart ownership` — Verify floor restart clears any active Frost slowdown or displacement state on all enemies through the owner-controlled reset entry point.

**Exclusive resources**

- `logical:enemy-locomotion-behavior-surface` — Status-effect/displacement modifies the same persistent enemy objects' locomotion/movement state that enemy pursuit/search, melee attack, ranged attack, and locked-door-attack work (enemy_behavior domain) also read and write concurrently on the same enemy scripts/prefab; concurrent unsynchronized edits to that shared behavior surface are unsafe. Evidence/basis: Derived rationale grounded in GDD Section 5 — Runtime Implementation, which states that pursuit/attack, status-effect/displacement, and locked-door-attack behavior all act on the same persistent enemy objects and all consume/restore the same pursuit/search state contract and shared navigation layer; this is a scheduling/write-collision inference from that shared-ownership architecture, not a quoted GDD requirement.

**Dependencies**

- `enemy-pursuit-search-foundation` — Status-effect/displacement must hand affected enemies back to the correct pursuit/search movement state after an effect ends, and the GDD states this component consumes the pursuit/search state contract rather than defining a second enemy-state machine; that contract must exist first. Evidence/basis: GDD Section 5 — Runtime Implementation: 'The pursuit/search state contract must therefore exist before status-effect/displacement work is treated as independently dispatchable; status/displacement consumes that contract when handing control back to normal enemy behavior.'
- `gameplay-navigation-locomotion` — Displacement must preserve valid movement/navigation state, and Frost slowdown/forced displacement are required to consume the shared gameplay navigation/locomotion layer rather than independently configuring navigation technology; that layer must exist first. Evidence/basis: GDD Section 5 — 2.5D Isometric Visual and World Representation: 'Enemy pursuit/search, melee/ranged behavior, status effects, and forced displacement consume this layer instead of each selecting or configuring navigation technology or doorway passability independently.'

**Notes:** A repository-wide grep across Assets/ for 'Frost' and 'Displacement' found no matches; this capability does not exist in any form. Force Wave's request to trigger displacement is a consumer relationship owned by the wizard_combat domain's force-wave item, not a dependency of this item.

### `enemy-pursuit-search-foundation` — Enemy Detection, Pursuit, and Search/Reacquisition Foundation

- **Kind:** `implementation`
- **Type:** `enemy_ai_foundation`
- **Parent:** `enemies`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The detection/pursuit/lose-target/search/wander/reacquisition contract, threshold relationship, doorway-traversal rule, and reset participation are already fully specified by the GDD; only exact distance/duration tuning numbers are explicitly deferred to playtesting and do not block building the mechanism.
- **Execution scope:** `needs_execution_decomposition` — Bundles several independently verifiable responsibilities — detection acquisition, distance-based target loss, last-known-position homing, bounded randomized search/wander, reacquisition, doorway-passability-aware traversal, and restart-reset participation — reused as the shared base for two archetypes; too broad for one implementation agent to safely execute and validate as a single unit even though the design itself is concrete.
- **Confidence:** `high`

**GDD evidence**

- `Enemy Detection, Pursuit, and Target Loss` — Detection Distance must be smaller than Lose Target Distance; acquiring, pursuing, distance-based (non-random) target loss to a search state at last-known position, bounded randomized search/wander, reacquisition, and clearing to idle/wander without despawning the persistent object.
- `Door and Pursuit Rules` — Crossing an open doorway does not by itself clear pursuit; active pursuit is lost only through the distance-and-search behavior.
- `Runtime Implementation` — Enemy locomotion consumes the shared gameplay navigation/locomotion layer rather than choosing/configuring navigation technology independently.
- `Floor-run restart ownership (Win and Loss Conditions)` — Every system owning persistable state exposes a reset entry point, invoked by the Floor Run/Restart Orchestrator, returning each enemy to its authored spawn region and initial AI state with no retained target/search knowledge.

**Acceptance criteria**

- `Enemy Detection, Pursuit, and Target Loss` — Detection Distance is strictly smaller than Lose Target Distance so acquisition/loss does not oscillate at one boundary.
- `Enemy Detection, Pursuit, and Target Loss` — Entering Detection Distance acquires the wizard and begins pursuit; crossing an open doorway does not by itself clear an acquired target.
- `Enemy Detection, Pursuit, and Target Loss` — Exceeding Lose Target Distance transitions to a search state directed at the player's last known position using the distance threshold, not randomness, to decide the transition.
- `Enemy Detection, Pursuit, and Target Loss` — On reaching the last-known position without reacquisition, perform a short, bounded search/wander using controlled randomness over navigable points, periodically re-checking for the player; re-entering Detection Distance during this state reacquires the player.
- `Enemy Detection, Pursuit, and Target Loss` — If bounded search completes without reacquisition, clear the target and return to local idle/wander; the enemy remains the same persistent object and is not despawned, replaced, or reset.
- `Door and Pursuit Rules` — A pursuing/searching enemy can continue forward traversal through an open or broken doorway when the shared navigation/locomotion passability result permits it, without losing its target solely because of the crossing.
- `Runtime Implementation` — Enemy locomotion consumes the shared gameplay navigation/locomotion layer's walkable movement representation rather than selecting or configuring navigation technology independently.
- `Floor-run restart ownership (Win and Loss Conditions)` — Exposes an owner-controlled restart/reset entry point that returns the enemy to its authored encounter/spawn region and clears all target/last-known-position/search state, for consumption by the Floor Run/Restart Orchestrator (owned by a different domain).

**Validation requirements**

- `Development Agent Roles (Unity Validation Agent)` — Target-loss hysteresis/search and reacquisition Play Mode validation.
- `Dungeon Floor Structure (Bone Archive)` — Bone Archive lane-pathing validation confirming enemy movement/navigation fits the room's described narrow-lane geometry.
- `Door and Pursuit Rules` — Verify a tracking/pursuing or searching enemy follows the player or last-known position through an open/broken doorway without spuriously clearing its target solely due to the crossing.

**Exclusive resources**

- `logical:enemy-locomotion-behavior-surface` — This foundation is the base behavior surface that melee-enemy, ranged-enemy, and locked-door-enemy-attack are built directly on top of/extend; concurrent edits to the same shared enemy-behavior codebase would collide. Evidence/basis: Derived rationale: GDD Development Agent Roles / Development Agent Ownership Invariants assign pursuit/search, melee/ranged attack behavior, and locked-door-attack initiation all to one Enemy Pursuit Agent-owned behavior surface. Since Assets/NoSafeCircle/DoorPrototype/Scripts currently contains no enemy scripts, these tasks are expected to create/extend the same shared code.

**Dependencies**

- `gameplay-navigation-locomotion` — Enemy locomotion during pursuit, search, and doorway traversal must move through the shared gameplay navigation/locomotion layer (NavMesh-based) rather than the pursuit FSM choosing/configuring navigation independently; that shared layer does not yet exist. Evidence/basis: GDD Runtime Implementation: 'A shared gameplay navigation/locomotion layer provides the walkable movement representation... enemy detection/pursuit/search logic does not choose or configure a different navigation technology independently.' Packages/manifest.json declares no com.unity.ai.navigation dependency and no navigation/locomotion script exists in Assets/NoSafeCircle/DoorPrototype/Scripts.

**Notes:** This item is the shared base that melee-enemy and ranged-enemy consume for their core movement/targeting loop; it does not itself include archetype-specific attack behavior, which stays on the archetype items. It does not own Frost Field slowdown application/restoration or forced-displacement handling (owned by enemy-status-effect-displacement in the enemy_state domain), but per GDD text that consumer depends on this item's pursuit/search state contract, not the reverse — no dependency edge is added here in that direction.

### `melee-enemy` — Melee Enemy Archetype

- **Kind:** `implementation`
- **Type:** `enemy_archetype`
- **Parent:** `enemies`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — Melee Enemy's behavior (rush-and-melee-attack, gradual distance closing, natural clustering) and its role as an assembled archetype integrating existing-to-be-built shared capabilities are already concretely specified by the GDD; no additional design invention is required.
- **Execution scope:** `needs_execution_decomposition` — Integrates several distinct subsystem contracts (shared pursuit/locomotion consumption, Enemy Health/Defeat participation, Active Enemy Registry participation, melee attack execution, and SpriteRenderer prefab presentation/sorting) into one assembled archetype; each integration point has its own validation concern, exceeding a single bounded agent handoff.
- **Confidence:** `high`

**GDD evidence**

- `Required Enemy Roster` — Melee Enemy runs at the wizard and attacks at close range; prevents long stationary casts and becomes dangerous in groups.
- `Resources, Feedback, and Failure` — Melee Enemies gradually close the distance over time; movement alone cannot preserve a completely safe distance indefinitely in later encounters.
- `Spell and Enemy Interactions` — Melee enemies naturally cluster while pursuing the wizard, making them strong area-damage targets for Charged Fireball; Frost Field stretches that formation.
- `Required Enemy Roster` — Both enemy archetypes deal damage through the shared Player Health system rather than maintaining separate copies of player-health state.
- `Environment Presentation and Authoring Direction / Runtime Implementation` — The wizard and enemies use world-space SpriteRenderers and prefabs with the same isometric sorting conventions as other world-space objects.

**Acceptance criteria**

- `Required Enemy Roster` — Runs at the wizard and attacks at close range once the shared pursuit foundation acquires the player as target.
- `Required Enemy Roster` — Deals damage to the player exclusively through the shared Player Health damage interface (existing PlayerHealth.TakeDamage), never writing separate player-health state.
- `Resources, Feedback, and Failure` — A retreating player cannot maintain indefinite safety through ordinary movement alone; Melee Enemy pursuit gradually closes distance over time, with exact speed/tuning left to playtesting.
- `Spell and Enemy Interactions` — Multiple simultaneously pursuing Melee Enemies exhibit natural clustering while chasing (not rigid uniform spacing), preserving the relevance of Charged Fireball area damage and Frost Field formation-stretching.
- `Environment Presentation and Authoring Direction` — Delivers a usable assembled world-space SpriteRenderer archetype prefab integrating the shared pursuit/locomotion foundation, Enemy Health/Defeat participation, Active Enemy Registry participation, and Melee attack behavior.

**Validation requirements**

- `Spell and Enemy Interactions` — Exercise multiple simultaneously pursuing Melee Enemies (not only one) to validate that clustering behavior remains meaningful for area-damage/formation-stretch interactions.
- `Required Enemy Roster` — Verify melee damage is applied only through PlayerHealth.TakeDamage and not through any duplicated health-writing path.

**Exclusive resources**

- `logical:enemy-locomotion-behavior-surface` — Melee Enemy is built directly on the shared pursuit foundation and shares its behavior surface with ranged-enemy and locked-door-enemy-attack; concurrent edits risk collision. Evidence/basis: Derived rationale: same GDD ownership assignment cited on enemy-pursuit-search-foundation; no enemy scripts currently exist so this work extends the same shared codebase.

**Dependencies**

- `enemy-pursuit-search-foundation` — Melee Enemy's chase/close-distance behavior is the archetype-specific behavior built directly on the shared detection/pursuit/search/reacquisition state machine, which does not yet exist. Evidence/basis: GDD Enemy Detection, Pursuit, and Target Loss + Required Enemy Roster describe Melee Enemy pursuit as an application of the shared contract; no pursuit/search code exists in the repository.
- `enemy-health-damage-defeat` — The assembled archetype must integrate the reusable Enemy Health/Defeat capability rather than maintaining its own health/damage/defeat state; that capability does not yet exist. Evidence/basis: GDD Required Enemy Roster 'Enemy health and defeat ownership' paragraph; no such component exists anywhere in Assets/NoSafeCircle/DoorPrototype/Scripts.
- `active-enemy-registry` — The archetype must register with and participate in the Active Enemy Registry's active-count bookkeeping so encounter admission and the fifteen-enemy cap function correctly; the registry does not yet exist. Evidence/basis: GDD 'Active Enemy Registry and Encounter Admission': enemy activation registers with the registry and defeat removes the enemy from the active count; no registry implementation exists in the repository.

**Notes:** Frost Field's slowdown application/restoration is owned by enemy-status-effect-displacement (a different domain); this item only needs to expose a locomotion speed that can be externally modified, and no formal dependency in that direction is added since the GDD makes status-effect the consumer of this behavior, not the reverse.

### `ranged-enemy` — Ranged Enemy Archetype

- **Kind:** `implementation`
- **Type:** `enemy_archetype`
- **Parent:** `enemies`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — Ranged Enemy's behavior (moderate-distance keep-away, slow telegraphed shot, occlusion check, standalone viability, Frost interaction) is already concretely specified by the GDD; no additional design invention is required at this coarse level.
- **Execution scope:** `needs_execution_decomposition` — Bundles keep-away positioning logic, telegraphed-attack timing, line-of-sight/occlusion checks, Frost-interaction correctness, plus Enemy Health/Defeat and Active Enemy Registry integration and SpriteRenderer presentation into one archetype; these are independently verifiable responsibilities exceeding a single bounded handoff.
- **Confidence:** `high`

**GDD evidence**

- `Required Enemy Roster` — Ranged Enemy keeps moderate distance and fires a slow telegraphed shot; forces lateral movement while Melee Enemies close in.
- `Required Enemy Roster` — A Ranged Enemy may end up fighting alone if its Melee support is defeated first; tap Fireball, cover, and lateral movement remain effective against a lone survivor.
- `Runtime Implementation` — Ranged Enemy attacks include a line-of-sight/projectile-occlusion check so Chapel of Ash's cover actually blocks shots.
- `Spell and Enemy Interactions` — Frost Field slows a Ranged Enemy's repositioning but does not stop its attacks; the player must still move laterally or use room geometry to avoid incoming shots.
- `Environment Presentation and Authoring Direction / Runtime Implementation` — The wizard and enemies use world-space SpriteRenderers and prefabs with consistent isometric sorting conventions.

**Acceptance criteria**

- `Required Enemy Roster` — Keeps moderate distance from the player and fires a slow, telegraphed ranged shot rather than an instantaneous attack.
- `Runtime Implementation` — Attack includes a line-of-sight/projectile-occlusion check so cover (e.g., Chapel of Ash pews/columns) actually blocks shots.
- `Required Enemy Roster` — Deals damage to the player exclusively through the shared Player Health damage interface (existing PlayerHealth.TakeDamage).
- `Required Enemy Roster` — Functions correctly as a standalone pursuer if it ends up fighting without Melee support, without requiring melee presence to operate.
- `Spell and Enemy Interactions` — Frost Field slowdown affects only the Ranged Enemy's repositioning/locomotion speed and does not suppress, pause, or otherwise slow its telegraphed attack execution.
- `Environment Presentation and Authoring Direction` — Delivers a usable assembled world-space SpriteRenderer archetype prefab integrating the shared pursuit/locomotion foundation (moderate-distance keep-away behavior), Enemy Health/Defeat participation, Active Enemy Registry participation, and Ranged attack/occlusion behavior.

**Validation requirements**

- `Dungeon Floor Structure (Chapel of Ash) / Development Agent Roles (Unity Validation Agent)` — Chapel of Ash line-of-sight/projectile-occlusion Play Mode validation confirming cover blocks shots.
- `Spell and Enemy Interactions` — Verify a slowed (Frost Field) Ranged Enemy continues its normal telegraphed attack behavior while its repositioning speed is reduced.

**Exclusive resources**

- `logical:enemy-locomotion-behavior-surface` — Ranged Enemy is built directly on the shared pursuit foundation and shares its behavior surface with melee-enemy and locked-door-enemy-attack; concurrent edits risk collision. Evidence/basis: Derived rationale: same GDD ownership assignment cited on enemy-pursuit-search-foundation; no enemy scripts currently exist so this work extends the same shared codebase.

**Dependencies**

- `enemy-pursuit-search-foundation` — Ranged Enemy's moderate-distance-keeping and target acquisition/loss are built directly on the shared detection/pursuit/search/reacquisition state machine, which does not yet exist. Evidence/basis: GDD Enemy Detection, Pursuit, and Target Loss + Required Enemy Roster; no pursuit/search code exists in the repository.
- `enemy-health-damage-defeat` — The assembled archetype must integrate the reusable Enemy Health/Defeat capability rather than maintaining its own health/damage/defeat state; that capability does not yet exist. Evidence/basis: GDD Required Enemy Roster 'Enemy health and defeat ownership' paragraph; no such component exists in the repository.
- `active-enemy-registry` — The archetype must register with and participate in the Active Enemy Registry's active-count bookkeeping; the registry does not yet exist. Evidence/basis: GDD 'Active Enemy Registry and Encounter Admission'; no registry implementation exists in the repository.

**Notes:** The GDD's encounter-composition rule that Ranged Enemy never spawns as an isolated encounter is content/authoring policy owned by dungeon-encounter-content-authoring (a different domain), not this archetype's own behavior; this item only needs to remain correct when it happens to end up alone mid-encounter.

### `locked-door-enemy-attack` — Locked-Door Enemy Attack Initiation

- **Kind:** `implementation`
- **Type:** `enemy_behavior`
- **Parent:** `enemies`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The qualifying condition (still tracking/pursuing + blocked by locked door), the damage-interface boundary, and the post-break pursuit continuation are already fully specified by the GDD Door and Pursuit Rules section; nothing further needs to be invented.
- **Execution scope:** `single_agent` — A narrowly scoped behavior branch — checking existing tracking state, requesting door damage through one interface, and resuming pursuit after breach — with a small, well-defined validation target once its two prerequisites exist; bounded enough for one implementation agent.
- **Confidence:** `high`

**GDD evidence**

- `Door and Pursuit Rules` — Any surviving enemy still actively tracking/pursuing the player and whose route is blocked by the newly locked door begins attacking that door; no separate 'witnessed escape' or line-of-sight-to-crossing state is tracked, and an enemy that has already lost the player does not attack a locked door solely because it is nearby. When the door breaks, tracking/pursuing enemies continue pursuit through the now-passable doorway.
- `Locked-door attack and durability ownership` — Enemy Pursuit/attack behavior owns deciding when a qualifying blocked pursuer attacks and executing the attack attempt; Door and Interaction owns durability, the damage-receive interface, and the locked-to-broken transition. Enemy attack code requests door damage through that interface and does not directly write door durability or semantic door state.
- `Development Agent Ownership Invariants` — Enemy Pursuit owns initiating the locked-door attack when a surviving enemy is still actively tracking/pursuing the player and blocked; the attack requests damage through the Door-owned interface rather than mutating door state, and pursuit continues through the doorway after it breaks.

**Acceptance criteria**

- `Door and Pursuit Rules` — A surviving enemy still actively tracking/pursuing the player and whose route is blocked by a newly locked door begins attacking that door; no separate 'witnessed escape' or line-of-sight-to-crossing flag is tracked.
- `Door and Pursuit Rules` — An enemy that has already lost the player (cleared target) does not attack a locked door merely because it is nearby.
- `Locked-door attack and durability ownership` — The attack requests door damage exclusively through the Door-owned damage-receive interface and never writes door durability or semantic door state directly.
- `Door and Pursuit Rules` — When the door breaks (transitions to broken), the still-tracking/pursuing enemy continues pursuit forward through the now-passable doorway using the shared navigation/locomotion passability result, without independently manipulating door or navigation state.

**Validation requirements**

- `Dungeon Floor Structure (Lower Vault) / Door and Pursuit Rules` — Verify that after a rear breach, locked-door-attacking pursuers correctly resume forward pursuit through the broken doorway rather than stalling.
- `Door and Pursuit Rules` — Verify an enemy that has already lost the player (post bounded-search target clear) does not initiate a locked-door attack solely from proximity.
- `Section 3 - Player Experience Success Criteria` — The player understands that enemies left alive remain a threat: leaving them alive means locking a door while they attack it, and later encountering them if that door breaks through.

**Exclusive resources**

- `logical:enemy-locomotion-behavior-surface` — This behavior extends the same shared enemy-behavior codebase used by pursuit foundation, melee, and ranged work; concurrent edits risk collision. Evidence/basis: Derived rationale: same GDD ownership assignment cited on enemy-pursuit-search-foundation; no enemy scripts currently exist so this work extends the same shared codebase.

**Dependencies**

- `enemy-pursuit-search-foundation` — Determining whether a blocked enemy is still 'actively tracking/pursuing the player' — the sole qualifying condition for a locked-door attack — requires the tracking/pursuit state owned by the shared pursuit/search foundation; no separate witness flag exists per the GDD, so this state must come from that foundation, which does not yet exist. Evidence/basis: GDD Door and Pursuit Rules: 'if the enemy can still track the player, it is already aggroed/pursuing... An enemy that has already lost the player does not begin attacking a locked door.' No pursuit/tracking state currently exists in the repository.
- `door-close-lock-break-lifecycle` — The attack must request door damage through the Door-owned damage-receive interface and must stop/transition when the door's locked-to-broken state changes; DoorInteractable.cs currently has no durability, locked, or broken state, and no damage-receive method exists at all. Evidence/basis: GDD 'Locked-door attack and durability ownership'. Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs currently implements only IsOpen/Progress/interaction-timer fields (StartInteraction/CancelInteraction/Tick) with no durability, locked, broken, or damage-receive members.

**Notes:** Does not consume or write the shared gameplay-walkability-surface directly; it only reads the navigation layer's passability result once the door breaks, per GDD's explicit statement that 'pursuit and attack behavior consume doorway walkability... rather than directly changing NavMesh or door passability,' so no logical:gameplay-walkability-surface lock is applied here.

### `doors` — Doors and Interaction

- **Kind:** `feature`
- **Type:** `feature_group`
- **Parent:** `no-safe-circle`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `partial`
- **Proposed graph status:** `open`
- **Decomposition:** `coarse` — The feature is organizational; its three concrete children (door-open-interaction, doorway-crossing-state, door-close-lock-break-lifecycle) already carry the bounded, GDD-specified responsibilities. No further coarse-level design gap needs resolving at this bootstrap stage.
- **Execution scope:** `not_applicable` — Feature/organizational node; not directly dispatchable.
- **Confidence:** `high`

**GDD evidence**

- `Section 1 — Executive Summary / Design Pillars` — Each room ends at a door that takes five uninterrupted seconds to open; enemies can follow through it; after crossing it automatically closes and locks and pursuers eventually break through.
- `Section 2 — Player Actions and Systems (Open Sealed Door, Close and Lock)` — Defines cursor-targeted click-to-approach opening with an automatic no-hold timer, and automatic close/lock with a small fixed health restore.
- `Section 3 — Door and Pursuit Rules` — Defines shared doorway-crossing ownership, the door passability contract, locked-door attack/durability ownership, breaking, and forward-only progression.

**Notes:** Aggregate repository_state of partial reflects that door-open-interaction has meaningful (if incomplete) current behavior while doorway-crossing-state and door-close-lock-break-lifecycle are entirely unimplemented.

### `door-open-interaction` — Cursor-Targeted Door Opening (Click-to-Approach, Arm's-Reach Auto-Timer, Interruption)

- **Kind:** `implementation`
- **Type:** `gameplay_system`
- **Parent:** `doors`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `partial`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD fully specifies click-to-approach selection, arrival-triggered auto-timing, cursor-drift tolerance, and interruption conditions; no missing design remains for this responsibility.
- **Execution scope:** `single_agent` — The work is bounded to a known, small set of files (DoorInteractable.cs, PlayerInteractionController.cs, the scene/builder wiring) implementing one cohesive interaction flow; it is not yet dispatch-ready until player-movement's shared pointer projection exists, but its own scope is not so broad that it needs further execution splitting.
- **Confidence:** `high`

**GDD evidence**

- `Section 2 — Player Actions and Systems, 'Open Sealed Door'` — Click the sealed door to request movement to its interaction position; wizard walks there automatically; the five-second timer begins automatically at arm's-reach range with no sustained hold; cursor drift after selection does not matter; damage, moving away, or a cancelling/replacing command resets the attempt.
- `Section 3 — Door and Pursuit Rules` — A sealed door is a cursor-targeted interactable; clicking issues a combined approach-and-interact request; after selection, cursor drift does not cancel the request or timer.
- `Section 3 — Player Experience Success Criteria` — A first-time player understands that clicking sends the wizard to the door and reaching it is not enough — the automatic timer still requires five uninterrupted seconds; accurate target selection is required only on the initial click.
- `Section 5 — Runtime Implementation / Player Movement ownership` — Movement, cursor-aimed spells, and Door/Interaction consume the shared world-space pointer target exposed by Player Movement rather than independently projecting screen coordinates; runtime input is routed through Unity Input System/Input Actions rather than direct hardware polling.

**Acceptance criteria**

- `Section 2 — Open Sealed Door` — Clicking a sealed door issues a combined approach-and-interact request using the shared world-space pointer target exposed by Player Movement; Door and Interaction does not independently project screen-to-world coordinates.
- `Section 2 — Open Sealed Door; Section 3 — Door and Pursuit Rules` — The wizard automatically moves to the door's interaction position; when arm's-reach range is reached, the five-second opening timer starts automatically with no sustained button hold required.
- `Section 2 — Open Sealed Door` — After the door is selected, cursor movement/drift away from the door does not cancel the approach request or the running timer.
- `Section 2 — Setbacks; Section 3 — Door and Pursuit Rules` — Taking damage, moving away once timing has begun, or issuing another command that cancels/replaces the door interaction resets progress to zero.
- `Section 5 — Runtime Implementation` — Door selection/approach input is consumed through the project's Unity Input System/Input Actions layer rather than independent direct hardware polling.

**Validation requirements**

- `Section 3 — Player Experience Success Criteria` — Validate that a first-time player understands reaching the door alone is insufficient and that the automatic five-second timer must complete uninterrupted.
- `Section 4 — Unity Validation Agent row; Example Game-Specific Agent Task` — Validate cursor-targeted door range and cursor-drift behavior: drift after selection does not cancel, while damage/moving away during timing does.
- `Section 3 - Player Experience Success Criteria` — A first-time player understands that clicking a door sends the wizard to it, and that reaching the door is not enough — the automatic opening timer still requires five safe, uninterrupted seconds.
- `Section 3 - Player Experience Success Criteria` — Door interaction requires accurate cursor target selection only on the initial click; the wizard's automatic approach, the timer's automatic start on arrival, and tolerance of normal cursor drift after selection are all readable to a first-time player.

**Repository evidence**

- `Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs` (`code`) — Implements arm's-reach range detection via OnTriggerEnter/Exit against PlayerInteractionController, a 5-second Progress timer via StartInteraction/Tick/Complete, and cancellation via CancelInteraction; matches the general timer/interruption shape but has no crossing/close/lock/durability behavior.
- `Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerInteractionController.cs` (`code`) — BeginInteraction/EndInteraction are driven by a keyboard hold of interactKey (default Key.E) read directly from Keyboard.current in Update(), not by a cursor click-to-approach request or the Unity Input System/Input Actions layer; EndInteraction is also called on any player movement and on PlayerHealth.Damaged, matching the GDD's interruption rules for movement/damage.
- `Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs` (`code`) — Movement is pure WASD CharacterController motion; there is no mouse/pointer reading, no cursor-to-gameplay-plane projection, and no click-to-move/approach request of any kind.
- `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` (`code`) — BuildUI sets the interaction prompt text to 'Hold E to Open' and the ControlsHud text to 'Hold E - Open Door', confirming the currently integrated interaction model is a sustained keyboard hold, not an automatic no-hold timer.
- `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` (`scene`) — DoorInteractable component is serialized on DoorRoot with doorVisual and doorwayBlocker object references wired (fileID 965940337 / 965940338), confirming the simplified door is actually integrated into the canonical scene, not merely buildable.
- `Assets/InputSystem_Actions.inputactions` (`project_setting`) — The 'Player' action map defines Move/Look/Attack/Interact/Crouch/Jump/Previous/Next/Sprint actions; 'Interact' uses a Hold interaction with no visible mouse/pointer binding in the reviewed section. No gameplay-map Point/Click action exists; Point/Click bindings only exist in the separate 'UI' action map used for UI navigation.

**Exclusive resources**

- `repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs` — Implementation will modify DoorInteractable to accept a click-triggered approach-and-interact request and to switch the timer's start condition from a sustained key hold to automatic arrival, and this file is also a shared write surface with doorway-crossing-state and door-close-lock-break-lifecycle. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs currently implements StartInteraction/CancelInteraction/Tick and will need to change alongside the other door-lifecycle work in this same file/component cluster.
- `repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerInteractionController.cs` — Implementation must replace the current hold-E keyboard consumption with cursor-targeted selection/click-to-approach consumption and Input System routing, directly modifying this file's input-handling and BeginInteraction/EndInteraction logic. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerInteractionController.cs reads Keyboard.current[interactKey] directly in Update() and owns BeginInteraction/EndInteraction.
- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — The builder currently creates/wires PlayerMovement, PlayerInteractionController, and the door prompt/HUD UI text describing the hold-E interaction; this work must update that wiring and text to match the new click-to-approach/auto-timer behavior. Evidence/basis: DoorPrototypeSceneBuilder.cs BuildPlayer()/BuildUI() creates and wires PlayerInteractionController and the 'Hold E to Open' prompt/HUD text, and the builder destructively rebuilds/saves the canonical scene.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The builder saves this scene on every run and the door/player/UI objects it configures are serialized here; integration work on this task writes through the same scene. Evidence/basis: DoorPrototypeSceneBuilder.Build() calls EditorSceneManager.SaveScene(scene, ScenePath) for Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity after configuring Player/DoorRoot/Canvas objects.

**Dependencies**

- `player-movement` — Cursor-targeted door selection and click-to-approach must consume the shared world-space pointer target that Player Movement owns and exposes; PlayerMovement.cs currently has no pointer/mouse handling of any kind, so this specific capability does not yet exist. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs contains only WASD CharacterController motion with no pointer projection.

**Notes:** Whether this task must itself add/modify bindings in Assets/InputSystem_Actions.inputactions (e.g., a distinct door-select binding) or purely consumes a Point/Click binding added by Player Movement's projection work is not yet resolved by current evidence; see unresolved_questions.

### `doorway-crossing-state` — Shared Doorway-Crossing State (Forward-Side Crossing Detection)

- **Kind:** `implementation`
- **Type:** `gameplay_system`
- **Parent:** `doors`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD specifies the exact required behavior (detect actual forward-side crossing after open, expose to consumers, participate in reset); the underlying Unity mechanism is an explicit implementation choice, not missing design.
- **Execution scope:** `single_agent` — Bounded to adding one detection/state capability to the existing door object and exposing it through a small interface; touches a known, small set of files.
- **Confidence:** `high`

**GDD evidence**

- `Section 3 — Door and Pursuit Rules` — Door and Interaction owns doorway-crossing state; after a door is open it detects when the wizard has actually crossed to that door's forward side and exposes that state to consumers; opening does not by itself count as crossing.
- `Section 2 — Win and Loss Conditions` — Victory occurs when the shared doorway-crossing state confirms the wizard has crossed to the forward side of the final door; the win condition does not implement a separate crossing detector.
- `Section 4 — Door and Interaction Agent row` — It is the single owner of detecting when the wizard crosses to the forward side of an opened door; locking and final escape consume that state.
- `Section 2 — Floor-run restart ownership` — Door lifecycle/crossing/durability state is a required reset participant for the Floor Run/Restart Orchestrator.

**Acceptance criteria**

- `Section 3 — Door and Pursuit Rules` — Detects, for an open door, when the wizard has actually crossed to that door's forward side; opening the door alone does not set crossing state.
- `Section 4 — Door and Interaction Agent row` — Exposes the crossing state/event through a stable owner-side interface consumed by door close/lock and final-escape victory, so those consumers do not implement their own crossing detector.
- `Section 2 — Floor-run restart ownership` — Exposes an owner-controlled reset entry point for its crossing state, consumed by the Floor Run/Restart Orchestrator.

**Validation requirements**

- `Section 4 — Example Game-Specific Agent Task` — Validate that crossing is detected only after the door is open and the wizard has reached the forward side, not merely on interaction completion.

**Repository evidence**

- `Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs` (`code`) — Complete() only sets IsOpen=true, disables doorVisual and doorwayBlocker, and resets Progress; there is no forward-side crossing trigger, event, property, or any related state anywhere in this file or elsewhere in the DoorPrototype scripts.

**Exclusive resources**

- `repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs` — Crossing-state detection is expected to live on or alongside the existing DoorInteractable component and is a shared write surface with door-open-interaction and door-close-lock-break-lifecycle. Evidence/basis: DoorInteractable.cs currently owns the door's only runtime state (Progress/IsOpen/IsInteracting) and is the natural owner for the new crossing state.
- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — Per the GDD's current prototype scene-builder lock, work that creates/configures the forward-side crossing trigger on objects generated by this builder requires an exclusive-write lock on it. Evidence/basis: Section 5 — Shared Context and Coordination Rules: 'Current prototype scene-builder lock ... specifically applies to doorway-crossing work that creates/configures the forward-side crossing trigger'; DoorPrototypeSceneBuilder.BuildDoor() currently creates the DoorRoot/DoorVisual objects this trigger would attach to.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The new crossing trigger/collider would be serialized into this canonical scene, which the builder saves on every run. Evidence/basis: DoorPrototypeSceneBuilder.Build() saves Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity after configuring the DoorRoot hierarchy.

**Notes:** No dependency on door-open-interaction was added because the existing DoorInteractable.IsOpen property this work consumes already exists and is usable independent of that item's still-open click-to-approach/Input-System rework.

### `door-close-lock-break-lifecycle` — Door Close/Lock, Health Restore Request, Durability, and Locked-to-Broken Lifecycle

- **Kind:** `implementation`
- **Type:** `gameplay_system`
- **Parent:** `doors`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD fully specifies close/lock triggering, health-restore request semantics, durability/damage-interface ownership, the locked-to-broken transition, forward-only enforcement, required breach feedback, and navigation-publication ownership; no missing design remains, only implementation bundling.
- **Execution scope:** `needs_execution_decomposition` — This item currently bundles several independently verifiable responsibilities — core close/lock state-machine and durability/damage-API logic, player-facing breach feedback presentation (visual/audio), and navigation-passability publication integration against a not-yet-existing navigation layer — which together span more files, subsystems, and validation concerns than is safe to hand to one implementation agent at once, even though the underlying design is fully concrete.
- **Confidence:** `high`

**GDD evidence**

- `Section 2 — Player Actions and Systems, 'Close and Lock'` — After the wizard crosses to the forward side of an opened door, it automatically closes and locks with no additional input; completing the automatic close-and-lock restores a small fixed amount of health; once locked the door cannot be reopened or crossed again.
- `Section 2 — Player Health ownership` — Door locking requests the fixed recovery through the Player Health restore interface; restoration is clamped to maximum health; Door and Interaction never writes player-health state directly.
- `Section 2 — Resources, Feedback, and Failure, 'Door feedback'` — Banging, shaking, cracks, and a durability indicator show when a breach is near.
- `Section 3 — Door and Pursuit Rules` — Door passability contract: Door and Interaction owns semantic door state (sealed/open/locked/broken); the shared navigation/locomotion layer owns translating that into enemy walkability; door state changes update the navigation layer through that interface. Locked-door attack and durability ownership: Enemy Pursuit owns deciding/executing the attack; Door and Interaction owns durability, the owner-controlled damage-receive interface, and the locked-to-broken transition. If the player waits too long the locked door breaks; a broken door remains open and cannot be closed/relocked; the player cannot travel backward through any earlier doorway including a broken one.
- `Section 4 — Door/navigation integration prerequisite` — The navigation-owned shared passability interface must exist before door-state publication through that interface is dispatch-ready; if passability publication remains bundled inside one executable door-lifecycle item, that item depends on the gameplay navigation/locomotion owner.
- `Section 2 — Floor-run restart ownership` — Door lifecycle/crossing/durability state is a required reset participant for the Floor Run/Restart Orchestrator.

**Acceptance criteria**

- `Section 2 — Close and Lock` — After doorway-crossing-state confirms forward-side crossing, the door automatically closes and locks with no additional player input.
- `Section 2 — Player Health ownership` — Completing the automatic close/lock requests the small fixed health restoration through the Player Health owner-controlled restore interface (clamped to max health); this component never writes Player Health state directly.
- `Section 3 — Door and Pursuit Rules` — Once locked, the door cannot be reopened, unlocked, or crossed again by the player; the floor is a forward-only escape sequence, including after any door has broken.
- `Section 3 — Locked-door attack and durability ownership` — Exposes runtime durability and an owner-controlled damage-receive interface that other systems (e.g., enemy locked-door attacks) call to reduce durability; owns the locked-to-broken state transition; requesting systems never write durability or semantic door state directly.
- `Section 3 — Door and Pursuit Rules` — When durability reaches zero the door breaks; a broken door remains open and cannot be closed or relocked for the remainder of the run, permits forward enemy traversal, and is not a return path for the player.
- `Section 3 — Door passability contract` — Publishes semantic door state (sealed/open/locked/broken) through the shared navigation-owned passability interface so sealed/locked blocks enemy traversal and open/broken permits it; this component does not directly manipulate NavMesh or doorway passability itself.
- `Section 2 — Door feedback` — Provides required player-facing breach feedback — banging, shaking, cracks, and a durability indicator — as the door nears breaking; this is implementation behavior, not validation-only prose.
- `Section 2 — Floor-run restart ownership` — Exposes an owner-controlled reset entry point for door lifecycle/crossing/durability state, consumed by the Floor Run/Restart Orchestrator.

**Validation requirements**

- `Section 3 — Door and Pursuit Rules` — Validate that a surviving enemy still actively tracking/pursuing the player and blocked by the locked door continues attacking it until it breaks, and that pursuit resumes through the doorway once broken (exercised jointly with the enemy_behavior domain's locked-door attack owner).
- `Section 3 — Door and Pursuit Rules` — Validate that a broken or locked door is never a return path for the player, including after breaking.
- `Section 2 — Door feedback` — Validate that breach feedback (banging/shaking/crack/durability indicator) is player-perceivable before the door actually breaks.
- `Section 3 - Player Experience Success Criteria` — Crossing an opened doorway causes automatic close-and-lock with no second player input required, and this behavior is readable/expected by a first-time player.
- `Section 3 - Player Experience Success Criteria` — Failure caused by waiting too long — allowing a locked door to break under sustained pursuer pressure — is readable to the player through durability/breach feedback.

**Repository evidence**

- `Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs` (`code`) — No closing, locking, durability field, damage-receive method, broken state, breach feedback, or navigation-publication code exists; Complete() is a one-way IsOpen=true transition with no further lifecycle.
- `Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerHealth.cs` (`code`) — Only exposes TakeDamage(float) and a CurrentHealth getter; there is no restore/heal method, confirming the Player Health restore interface this work must request does not yet exist.
- `Packages/manifest.json` (`project_setting`) — com.unity.ai.navigation is not declared, and no NavMesh-related script exists under Assets/NoSafeCircle, confirming the gameplay navigation/passability layer this work must publish to does not yet exist.

**Exclusive resources**

- `repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs` — Closing/locking/durability/damage-receive/broken-transition logic is expected to extend the existing DoorInteractable component, and this file is a shared write surface with door-open-interaction and doorway-crossing-state. Evidence/basis: DoorInteractable.cs is currently the sole runtime door component in the repository.
- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — New durability/breach-feedback UI and door-lock behavior on objects the builder generates/maintains requires the exclusive-write lock defined by the GDD's current prototype scene-builder rule. Evidence/basis: GDD Section 5 — 'Current prototype scene-builder lock: scene-authoring work that changes objects generated or maintained through DoorPrototypeSceneBuilder.cs must take exclusive-write locks on both that builder and the DoorPrototype scene.'
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — New durability/breach-feedback UI and lock/break state changes on the door and its UI would be serialized into this canonical scene. Evidence/basis: DoorPrototypeSceneBuilder.Build() saves Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity after configuring DoorRoot and Canvas objects.
- `logical:gameplay-walkability-surface` — This work writes/toggles the shared passability surface by publishing sealed/open/locked/broken door state; the navigation/locomotion owner also writes this same shared surface, so both must be sequenced through the same lock. Evidence/basis: GDD Section 3 — 'Door state changes update the navigation layer through that interface' and Section 4 — 'Door state changes are published through the shared navigation/locomotion passability interface.'

**Dependencies**

- `doorway-crossing-state` — Automatic close/lock is explicitly triggered by the shared doorway-crossing state confirming forward-side crossing; that detection/state does not currently exist anywhere in the repository. Evidence/basis: GDD Section 3 — Door and Pursuit Rules: 'After the shared doorway-crossing state confirms that the wizard reached the forward side, the door automatically closes and locks'; Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs has no crossing detection.
- `player-health` — The automatic lock must request a fixed health restoration through Player Health's owner-controlled restore interface, which does not currently exist on PlayerHealth.cs. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerHealth.cs exposes only TakeDamage(float), with no restore/heal method.
- `gameplay-navigation-locomotion` — This item bundles publication of semantic door state through the navigation-owned passability interface; per the GDD's door/navigation integration prerequisite, that publication cannot be dispatch-ready until the navigation-owned passability interface exists, and no navigation/locomotion layer currently exists in the repository. Evidence/basis: GDD Section 4 — 'the navigation-owned shared passability interface must exist before door-state publication through that interface is dispatch-ready'; Packages/manifest.json has no com.unity.ai.navigation dependency and no NavMesh code exists under Assets/NoSafeCircle.

**Notes:** Enemy-side decision-making for when a locked-door attack occurs belongs to the enemy_behavior domain's locked-door-enemy-attack owner and is intentionally excluded from this item's acceptance criteria; this item owns only durability, the damage-receive interface, and the locked-to-broken transition that attack requests through.

### `world` — World and Unity Foundations

- **Kind:** `feature`
- **Type:** `feature-group`
- **Parent:** `no-safe-circle`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `partial`
- **Proposed graph status:** `open`
- **Decomposition:** `coarse` — The organizational grouping itself needs no additional design; its represented children are individually concrete or already resolved to a bounded configuration gap. No missing-design problem blocks bootstrapping this feature.
- **Execution scope:** `not_applicable` — Organizational feature node; not directly dispatchable.
- **Confidence:** `medium`

**GDD evidence**

- `GDD - Environment Presentation and Authoring Direction` — Fixed 2.5D isometric presentation using Unity Isometric Tilemaps for architecture and world-space SpriteRenderer prefabs for independently sorted/interactive objects, with the gameplay layer kept separate from the visual layer.
- `GDD - 2.5D Isometric Visual and World Representation` — A shared gameplay navigation/locomotion layer owning walkable movement representation and the navigation side of the door-passability interface, using the approved Unity AI Navigation package.

**Notes:** Aggregate of one implemented child (fixed-isometric-camera) and three missing children (package configuration, navigation/locomotion layer, visual foundation). Does not include five-room content/encounter authoring, which belongs to a separate deferred feature outside this domain.

### `fixed-isometric-camera` — Fixed Isometric Camera

- **Kind:** `implementation`
- **Type:** `world-foundation`
- **Parent:** `world`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `implemented`
- **Proposed graph status:** `complete`
- **Decomposition:** `not_applicable` — Work is already complete and atomic; no further decomposition is meaningful.
- **Execution scope:** `not_applicable` — Already implemented and test-validated; not awaiting dispatch or further execution decomposition.
- **Confidence:** `high`

**GDD evidence**

- `GDD - Executive Summary` — The camera is fixed, the world is viewed at an angle, and the visible environment is authored as isometric art rather than a free-rotation 3D space.
- `GDD - 2.5D Isometric Visual and World Representation` — The camera is fixed in an isometric presentation; the player does not rotate the world view freely.

**Acceptance criteria**

- `GDD - Executive Summary / 2.5D Isometric Visual and World Representation` — Camera renders the gameplay world using a fixed orthographic 2.5D isometric projection at a consistent dimetric angle.
- `GDD - 2.5D Isometric Visual and World Representation` — No player-controllable free rotation of the world view is exposed; the camera's rotation never changes at runtime.

**Validation requirements**

- `GDD - Camera completion and future integration` — Once the Tilemap/SpriteRenderer world-visual foundation exists, validate that the fixed isometric camera framing remains visually compatible with the new visual layer (alignment/sorting check), without reopening the already-satisfied fixed-angle/no-rotation requirement.

**Repository evidence**

- `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` (`code`) — BuildCamera sets camera.orthographic = true, camera.orthographicSize = 8f, and cameraObject.transform.rotation = Quaternion.Euler(30f, -45f, 0f) once; no later code path in the builder modifies camera rotation.
- `Assets/NoSafeCircle/DoorPrototype/Scripts/IsometricCameraFollow.cs` (`code`) — LateUpdate only writes transform.position = target.position + offset; rotation is never read or written after Initialize captures the position offset.
- `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` (`scene`) — Serialized Main Camera has orthographic: 1, orthographic size: 8, and a wired IsometricCameraFollow component (target + offset {10,10,-10}); no rotation-modifying component is attached.
- `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs` (`test`) — Build_MainCamera_IsFixedOrthographicIsometric asserts orthographic mode and rotation equal to Quaternion.Euler(30,-45,0) within 0.01 degrees and absence of any Rotate/Orbit-named component; Build_MainCamera_TranslatesWithPlayerButRotationStaysFixed asserts rotation is unchanged after the player moves and LateUpdate runs.

**Notes:** Per current provenance boundary: only the fixed-angle/no-free-rotation requirement is treated as GDD-backed acceptance criteria. The camera's player-follow translation (IsometricCameraFollow) is a valid current implementation detail and is recorded as repository evidence only, since the current GDD does not require player-follow camera behavior.

### `tilemap-navigation-package-configuration` — Tilemap and AI Navigation Package Configuration

- **Kind:** `implementation`
- **Type:** `world-foundation`
- **Parent:** `world`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — This is a bounded project-configuration change (adding two named, already-approved package entries) with no missing design.
- **Execution scope:** `single_agent` — Adding two declared package dependencies and confirming resolution is a small, well-bounded configuration change with a clear validation target (manifest + lock file content), not a task that spans multiple implementation responsibilities.
- **Confidence:** `high`

**GDD evidence**

- `GDD - Approved Unity Packages and Windows Build Configuration` — Unity 2D Tilemap Editor (com.unity.2d.tilemap) is approved and required for the intended Isometric Tilemap authoring workflow; if absent from Packages/manifest.json, adding/configuring it is concrete project-configuration work, not deferred design.
- `GDD - Approved Unity Packages and Windows Build Configuration` — Unity AI Navigation (com.unity.ai.navigation) is the approved enemy-navigation implementation; if absent from Packages/manifest.json, adding/configuring it is a prerequisite for the gameplay navigation/locomotion layer and locomotion-dependent enemy work.

**Acceptance criteria**

- `GDD - Approved Unity Packages and Windows Build Configuration` — com.unity.2d.tilemap is declared in Packages/manifest.json.
- `GDD - Approved Unity Packages and Windows Build Configuration` — com.unity.ai.navigation is declared in Packages/manifest.json.
- `GDD - Approved Unity Packages and Windows Build Configuration` — Both packages resolve successfully (reflected in Packages/packages-lock.json) so downstream Tilemap and NavMesh workflows are actually usable in the editor.

**Validation requirements**

- `GDD - Approved Unity Packages and Windows Build Configuration` — The developer inspects the resulting package state after configuration and before merge, per the GDD's requirement that package-manifest changes be developer-inspected.

**Repository evidence**

- `Packages/manifest.json` (`project_setting`) — Dependency list contains com.unity.inputsystem, com.unity.ugui, com.unity.timeline, com.unity.visualscripting, various com.unity.modules.* builtin modules, etc., but no com.unity.2d.tilemap and no com.unity.ai.navigation entry.
- `Packages/packages-lock.json` (`project_setting`) — Resolved dependency graph includes only com.unity.modules.tilemap (the builtin low-level Tilemap runtime module bundled with Unity) and no com.unity.2d.tilemap or com.unity.ai.navigation entry at any depth, confirming neither approved package is currently resolved.

**Exclusive resources**

- `repo-file:Packages/manifest.json` — Adding the two approved package dependency entries requires exclusive write access to the shared package manifest so concurrent package-configuration work cannot silently overwrite each other's entries. Evidence/basis: Packages/manifest.json is the single shared dependency-declaration file for the whole project; current inspection shows both approved packages absent from it.

**Notes:** com.unity.modules.tilemap (builtin runtime module) already present is a different, lower-level package than the required com.unity.2d.tilemap authoring package and does not satisfy this requirement.

### `gameplay-navigation-locomotion` — Gameplay Navigation/Locomotion Foundation

- **Kind:** `implementation`
- **Type:** `world-foundation`
- **Parent:** `world`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD already specifies the approved technology (Unity AI Navigation/NavMesh), the ownership split for the passability interface, and the exact semantic-to-walkability translation rules; no additional design invention is needed to scope this item.
- **Execution scope:** `needs_execution_decomposition` — This item bundles several independently verifiable responsibilities for one agent: consuming/validating the newly configured AI Navigation package, adding NavMesh-capable walkability configuration to builder-generated scene geometry, and designing and implementing the shared passability interface that two other domains (Door and Interaction, Enemy Pursuit) will depend on. That combination of package integration, scene/builder rework, and a new cross-domain interface contract is broader than a single bounded implementation unit.
- **Confidence:** `medium`

**GDD evidence**

- `GDD - 2.5D Isometric Visual and World Representation` — A shared gameplay navigation/locomotion layer owns the walkable movement representation and navigation-facing configuration used by runtime movers, and owns the navigation-side implementation of the shared door-passability interface, translating Door and Interaction's sealed/open/locked/broken state into enemy walkability.
- `GDD - Runtime Implementation` — The approved implementation uses Unity AI Navigation (com.unity.ai.navigation) and NavMesh-based runtime movement; enemy detection/pursuit/search logic does not choose or configure a different navigation technology independently. The exact underlying mechanism for updating doorway passability is an implementation choice.
- `GDD - Door and Pursuit Rules (door passability contract)` — Sealed and locked doors block enemy traversal; open and broken doors permit forward enemy traversal, translated through the navigation layer's shared passability interface rather than by enemy code directly manipulating NavMesh or doorway passability.
- `GDD - 2.5D Isometric Visual and World Representation` — A minimal working navigation/locomotion layer and the approved package configuration must exist before locomotion-dependent enemy implementation is dispatched, but room-specific visual authoring does not need to be complete first.

**Acceptance criteria**

- `GDD - 2.5D Isometric Visual and World Representation` — Owns the walkable movement representation and navigation-facing configuration consumed by all enemy runtime movement; enemy pursuit/search/status/displacement code consumes this layer rather than independently selecting or configuring navigation technology.
- `GDD - Runtime Implementation` — Implemented using Unity AI Navigation (com.unity.ai.navigation) with NavMesh-based runtime movement as the approved technology.
- `GDD - Door and Pursuit Rules (door passability contract)` — Exposes a shared passability interface that translates Door and Interaction's semantic sealed/open/locked/broken state into enemy walkability: sealed and locked block traversal; open and broken permit forward traversal.
- `GDD - Runtime Implementation` — The specific Unity mechanism used beneath the passability interface (obstacle/carving, navigation link, or runtime navigation-data update) is left as an implementation choice.

**Validation requirements**

- `GDD - Runtime Implementation` — Bone Archive's lane widths are validated against enemy movement/navigation requirements so the room's stated tactical geometry holds in practice; this check becomes fully executable once Bone Archive content is authored, but the navigation layer's agent-radius/walkability configuration is the artifact being validated.
- `GDD - Door and Pursuit Rules (door passability contract)` — Verify that toggling each door semantic state (sealed, open, locked, broken) produces the correct enemy-walkability result through the shared passability interface.

**Repository evidence**

- `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` (`scene`) — No NavMeshAgent, NavMeshSurface, or NavMeshObstacle component exists anywhere in the scene; the only NavMesh-related block present is Unity's default per-scene NavMeshSettings stub (m_NavMeshData: {fileID: 0}), which every Unity scene contains by default and is not evidence of a built navigation layer.
- `Assets/NoSafeCircle/DoorPrototype/NoSafeCircle.DoorPrototype.asmdef` (`code`) — Assembly definition references only Unity.InputSystem and UnityEngine.UI; no AI Navigation assembly reference exists.

**Exclusive resources**

- `logical:gameplay-walkability-surface` — This item is the sole owner of the shared enemy-walkability/passability surface; any door-lifecycle work that later toggles semantic door state through this interface must not write to it concurrently. Evidence/basis: GDD 'Door and Pursuit Rules' establishes one shared passability interface owned jointly across Door and Interaction (semantic state) and this navigation layer (walkability translation).
- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — Implementing NavMesh-based walkability for the current Floor/Walls/DoorRoot objects requires modifying how the builder constructs and configures those objects (e.g. navigation-static flags, NavMesh surface/agent setup). Evidence/basis: DoorPrototypeSceneBuilder.cs currently builds Floor via GameObject.CreatePrimitive(PrimitiveType.Plane) and Walls/DoorRoot as plain cubes with no navigation configuration; GDD 'Current prototype scene-builder lock' requires exclusive-write locks on this builder for scene-authoring work that changes its generated objects.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The builder clears and regenerates its known root objects and saves this exact scene file, so any task that changes builder-generated objects must also lock the scene it writes to. Evidence/basis: DoorPrototypeSceneBuilder.Build() calls ClearExistingObjects then EditorSceneManager.SaveScene(scene, ScenePath) where ScenePath is Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity.

**Dependencies**

- `tilemap-navigation-package-configuration` — The approved com.unity.ai.navigation package must be declared and resolved before a NavMesh-based navigation/locomotion layer can be built against it. Evidence/basis: Packages/manifest.json and Packages/packages-lock.json currently contain no com.unity.ai.navigation entry; GDD 'Approved Unity Packages and Windows Build Configuration' states its absence is a concrete configuration prerequisite for the navigation/locomotion layer.

**Notes:** Exact Detection/Lose Target distances and other tuning values remain GDD-deferred playtesting values and are not part of this item's scope; only the walkable-representation and passability-interface responsibilities belong here.

### `world-visual-foundation` — Tilemap and SpriteRenderer World Visual Foundation

- **Kind:** `implementation`
- **Type:** `world-foundation`
- **Parent:** `world`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD already specifies which object categories use Tilemap versus SpriteRenderer, the sorting-convention requirement, and the visual/gameplay separation principle; no missing design blocks scoping this item at the foundation level. Authoring the five actual room layouts remains separately deferred and out of this item's scope.
- **Execution scope:** `needs_execution_decomposition` — This item bundles multiple independently verifiable responsibilities: introducing Tilemap-based floor/wall authoring, converting the door visual and other builder-generated objects to SpriteRenderer prefabs with sorting configuration, and preserving/validating separation from the existing collision/walkability layer across several already-generated scene objects (Floor, Walls, DoorRoot, Player visual). That combination spans more than one bounded, independently testable unit for a single agent.
- **Confidence:** `medium`

**GDD evidence**

- `GDD - Environment Presentation and Authoring Direction` — The primary environment visual layer uses Unity Isometric Tilemaps for floors, walls, and repeatable architectural tiles; the wizard, enemies, taller props, interactive doors, obstacles, decorative set pieces, and other independently sorted objects use world-space SpriteRenderers and prefabs instead of being painted into a Tilemap.
- `GDD - Environment Presentation and Authoring Direction` — The visible isometric art layer is kept separate from the underlying gameplay representation so art can be revised without redefining core gameplay rules; the gameplay layer still owns walkability, collision, trigger volumes, door state, and pursuit logic.
- `GDD - Runtime Implementation` — All five encounter spaces exist inside one continuous Unity scene or continuous floor representation; enemy objects, health, pursuit state, active-enemy bookkeeping, and door state persist naturally as the player advances; no scene-load or cross-scene state-transfer system is required.
- `GDD - Required feedback and character presentation` — The wizard and enemies follow the same isometric sorting conventions as other world-space SpriteRenderers; placeholder character sprites are acceptable during development.

**Acceptance criteria**

- `GDD - Environment Presentation and Authoring Direction` — Floors, walls, and repeatable architectural tiles are authored using Unity Isometric Tilemaps (com.unity.2d.tilemap).
- `GDD - Environment Presentation and Authoring Direction` — The wizard, enemies, doors, props, obstacles, and other independently sorted/interactive objects use world-space SpriteRenderer prefabs rather than being painted into the Tilemap, following consistent isometric sorting conventions.
- `GDD - Environment Presentation and Authoring Direction` — The gameplay/simulation layer (walkability, collision, trigger volumes, door state, pursuit logic) remains defined independently of the visual Tilemap/SpriteRenderer layer so visual assets can be revised without changing gameplay rules.
- `GDD - Runtime Implementation` — The world/floor representation supports all five spaces existing inside one continuous Unity scene with no scene-loading or cross-scene state transfer required.

**Validation requirements**

- `GDD - Unity Validation Agent role (Section 4)` — Isometric sprite-sorting checks confirming SpriteRenderer objects sort correctly relative to Tilemap geometry and each other.
- `GDD - Unity Validation Agent role (Section 4)` — Alignment checks between Tilemap visuals and gameplay geometry (collision/walkability) so the visible and simulated layouts do not desynchronize.

**Repository evidence**

- `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` (`code`) — BuildFloor creates a primitive Plane with a MeshRenderer; BuildWalls and BuildDoor create primitive Cubes with MeshRenderers. No Tilemap, TilemapRenderer, Grid, or SpriteRenderer component is created anywhere in the builder.
- `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` (`scene`) — No Grid/Tilemap/TilemapRenderer serialized objects are present in the scene; door and wall visuals are serialized MeshRenderer/BoxCollider/MeshFilter primitives, not SpriteRenderer prefabs.

**Exclusive resources**

- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — Replacing the current primitive-mesh Floor/Walls/door-visual generation with Tilemap tiles and SpriteRenderer prefabs requires exclusive write access to the builder that currently constructs those objects. Evidence/basis: DoorPrototypeSceneBuilder.BuildFloor/BuildWalls/BuildDoor currently create primitive GameObjects directly; GDD 'Current prototype scene-builder lock' requires exclusive-write locks on this file for scene-authoring work that changes its generated objects.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The builder clears its known root objects and saves this exact scene file, so visual-foundation work that changes those generated objects must also lock the scene being regenerated. Evidence/basis: DoorPrototypeSceneBuilder.Build() calls ClearExistingObjects then EditorSceneManager.SaveScene(scene, ScenePath) targeting Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity.

**Dependencies**

- `tilemap-navigation-package-configuration` — The approved com.unity.2d.tilemap package must be declared and resolved before an Isometric Tilemap authoring workflow can be built against it. Evidence/basis: Packages/manifest.json and Packages/packages-lock.json currently contain no com.unity.2d.tilemap entry; GDD 'Approved Unity Packages and Windows Build Configuration' states its absence is concrete project-configuration work required for the Tilemap authoring workflow.

**Notes:** Does not include authoring the five named room layouts or encounter content; those remain a separately deferred content-authoring feature outside this domain that will consume this foundation once built.

### `encounters` — Dungeon Encounters

- **Kind:** `feature`
- **Type:** `feature-group`
- **Parent:** `no-safe-circle`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `coarse` — This is the organizational parent for encounter-admission runtime enforcement and deferred encounter-content authoring; it is not itself a design problem to resolve, so it is coarse rather than needs_future_decomposition.
- **Execution scope:** `not_applicable` — Feature/organizational node; not directly dispatchable.
- **Confidence:** `high`

**GDD evidence**

- `Section 2 — Active Enemy Registry and Encounter Admission` — A shared registry gates new encounter enemy activation against a hard fifteen-active-enemy cap, and encounter content is authored on top of that foundation.
- `Section 4 — Dungeon Encounter Agent` — Authors placements, triggers, configured per-door durability values, and final-room pressure; owns encounter-admission policy and consumes the Active Enemy Registry before activating new enemies.

**Notes:** Aggregates encounter-admission-cap-enforcement (concrete runtime foundation) and dungeon-encounter-content-authoring (deferred content feature).

### `encounter-admission-cap-enforcement` — Encounter Admission Active-Enemy-Cap Enforcement

- **Kind:** `implementation`
- **Type:** `runtime-system`
- **Parent:** `encounters`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The admission rule itself (delay/reduce new activation first, never remove existing pursuers, hard cap of fifteen) is fully specified by current GDD text and does not require any room-specific encounter layout, placement, or trigger design to be known first; the GDD explicitly calls this out as a reusable runtime foundation.
- **Execution scope:** `single_agent` — The admission-gating logic (query registry capacity, delay/reduce a requested activation batch, never deregister existing enemies) is a bounded, independently testable runtime responsibility once the Active Enemy Registry interface exists, with a clear validation target (Lower Vault priority case) that does not require full room content to be authored.
- **Confidence:** `high`

**GDD evidence**

- `Section 2 — Active Enemy Registry and Encounter Admission` — The registry tracks active persistent enemies under a hard fifteen-enemy cap; the Dungeon Encounter system consumes the registry before activating new encounter enemies, and if activation would exceed fifteen, new encounter enemies are delayed or reduced first while existing persistent pursuers are never removed to make room. This bookkeeping/admission foundation is explicitly reusable and does not require the exact five-room encounter layouts, placements, or trigger authoring to be known first.
- `Section 2 — Door and Pursuit Rules` — Surviving enemies carry forward and combine with later encounters as the same persistent enemy objects, not new spawns, and the game never permits more than fifteen active enemies at once.
- `Section 4 — Dungeon Encounter Agent / Ownership Invariants` — Dungeon Encounter Agent owns encounter-admission policy and consumes the shared Active Enemy Registry when admitting new enemies; it does not replace or remove existing persistent pursuers to satisfy the cap.

**Acceptance criteria**

- `Section 2 — Active Enemy Registry and Encounter Admission` — Before activating a requested encounter's enemies, query the registry's current active count and remaining capacity under the fifteen-enemy hard limit.
- `Section 2 — Active Enemy Registry and Encounter Admission` — When activating the requested enemies would exceed fifteen active enemies, delay or reduce the new encounter's enemy activation first; never remove or deregister an existing persistent pursuer to make room.
- `Section 4 — Dungeon Encounter Agent` — Consume the Active Enemy Registry's owner-exposed active count/capacity interface rather than maintaining a separate duplicate count.

**Validation requirements**

- `Section 2 — Active Enemy Registry and Encounter Admission` — Lower Vault is the primary validation case: verify that when a rear breach (surviving pursuers breaking through an earlier locked door) coincides with Lower Vault's own encounter admission request, the persistent pursuers keep priority over admitting the new encounter's enemies.
- `Section 3 — Player Experience Success Criteria` — Verify the floor-wide active-enemy count never exceeds fifteen across combined persistent-pursuer and newly-admitted-encounter enemies.
- `Section 3 - Player Experience Success Criteria` — Encounters use three to eight enemies and never exceed fifteen active enemies at once.

**Dependencies**

- `active-enemy-registry` — Admission enforcement gates new encounter activation against the registry's active count and remaining capacity; that registry interface must exist before admission logic can query or be validated against it. Evidence/basis: GDD Section 2 — Active Enemy Registry and Encounter Admission: 'The Dungeon Encounter system consumes the registry before activating new encounter enemies... existing persistent pursuers are never removed to make room.'

**Notes:** Must not be folded into or blocked by dungeon-encounter-content-authoring's needs_future_decomposition status; this is the 'known runtime behavior' half of the split required by the reconciliation guidance.

### `five-room-content-authoring` — Five-Room Floor Content Authoring

- **Kind:** `feature`
- **Type:** `content-authoring`
- **Parent:** `world`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `needs_future_decomposition` — Exact room geometry, dimensions, prop placement, and chokepoint/cover layout for each of the five named spaces are not specified beyond their stated tactical purpose; inventing that geometry now would fabricate missing design. The named-space tactical requirements are preserved as acceptance context for a future Progressive Decomposer rather than resolved here.
- **Execution scope:** `not_applicable` — Deferred content-authoring feature; not yet a bounded dispatchable unit.
- **Confidence:** `high`

**GDD evidence**

- `Section 3 — Dungeon Floor Structure` — Five named tactical spaces are required: 1. Ruined Entry — open space, broad rubble route, teaches circling a melee enemy and safe Fireball charging. 2. Bone Archive — narrow shelf lanes/chokepoints enabling Frost Field lane-slow-and-cluster tactics but risking the player being trapped. 3. Chapel of Ash — pews/columns provide line-of-sight breaks against the newly introduced Ranged Enemy (with Melee support), central aisle vs. side-route cover/distance tradeoff. 4. Lower Vault — incomplete loops; player must watch both the current encounter and the previous doorway because surviving enemies breaking through are the same persistent pursuers, not new spawns. 5. Final Room — comparatively open chamber with one central obstacle, populated by both Melee and Ranged Enemies, requiring combined use of movement, Frost Field, Force Wave, and Fireball for the final escape window.
- `Section 5 — 2.5D Isometric Visual and World Representation` — Five-room visual/content authoring consumes the reusable Tilemap/SpriteRenderer world foundation once it exists; this is a real prerequisite relationship even though the downstream content feature remains deferred.
- `Section 5 — Runtime Implementation` — All five encounter spaces exist inside one continuous Unity scene or continuous floor representation; no scene-load or cross-scene state-transfer system is required.

**Acceptance criteria**

- `Section 3 — Dungeon Floor Structure` — All five named spaces (Ruined Entry, Bone Archive, Chapel of Ash, Lower Vault, Final Room) are authored with their stated tactical layout purpose; none may be dropped or substituted merely because other rooms have more specialized validation cases.
- `Section 5 — Runtime Implementation` — All five spaces are authored inside one continuous Unity scene/floor representation rather than separate scenes with cross-scene state transfer.

**Dependencies**

- `world-visual-foundation` — Room authoring must build on the reusable Tilemap/SpriteRenderer conventions and visual/gameplay separation before room-specific geometry and content can be authored on top of it. Evidence/basis: GDD Section 5 — 2.5D Isometric Visual and World Representation: 'The reusable visual world foundation (Tilemap/SpriteRenderer conventions and visual/gameplay separation) is distinct from authoring the five named room layouts and encounters. Five-room visual/content authoring consumes this foundation once it exists.'

**Notes:** No formal dependency exists on dungeon-encounter-content-authoring or vice versa; both are deferred organizational features per the GDD-hardening example prohibiting feature-to-feature dependencies. Their consumption relationship (encounter placement consumes authored room spaces) is preserved here in notes only.

### `dungeon-encounter-content-authoring` — Dungeon Encounter Placement and Composition Authoring

- **Kind:** `feature`
- **Type:** `content-authoring`
- **Parent:** `encounters`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `needs_future_decomposition` — Exact encounter placements, triggers, per-door durability values, and Final Room pressure composition are explicitly left to later authoring/playtesting by the GDD; only composition/sizing rules (3-8 enemies, never-isolated Ranged Enemy, mixed compositions in two named rooms) are currently fixed. Inventing exact placements/triggers now would fabricate missing design.
- **Execution scope:** `not_applicable` — Deferred content-authoring feature; not yet a bounded dispatchable unit.
- **Confidence:** `high`

**GDD evidence**

- `Section 4 — Dungeon Encounter Agent` — Authors placements, triggers, configured per-door durability values, and final-room pressure, including the mixed Melee/Ranged compositions in Chapel of Ash and the Final Room. Does not own runtime door durability state, damage intake, or the locked-to-broken transition.
- `Section 3 — Required Enemy Roster` — Ranged Enemies never appear as an isolated encounter: every encounter that introduces one also includes at least one Melee Enemy. A Ranged Enemy may end up fighting alone only if its Melee support is defeated first.
- `Section 3 — Player Experience Success Criteria` — Encounters use three to eight enemies and never exceed fifteen active enemies.
- `Section 2 — Active Enemy Registry and Encounter Admission` — Room-specific encounter authoring consumes the registry/admission foundation once it exists; it is not itself required to exist before that foundation is built.

**Acceptance criteria**

- `Section 3 — Required Enemy Roster` — No authored encounter introduces a Ranged Enemy without at least one accompanying Melee Enemy in that same encounter.
- `Section 3 — Player Experience Success Criteria` — Each authored encounter uses between three and eight enemies; the registry-enforced fifteen-active-enemy ceiling remains a separate floor-wide constraint.
- `Section 4 — Dungeon Encounter Agent` — Chapel of Ash and the Final Room are authored with mixed Melee/Ranged compositions as required; Dungeon Encounter authors the per-door durability configuration value but does not implement runtime durability state, damage intake, or the locked-to-broken transition.

**Dependencies**

- `encounter-admission-cap-enforcement` — Encounter placement/activation must be authored against an existing admission/cap-enforcement foundation so authored encounters are gated correctly rather than bypassing the registry. Evidence/basis: GDD Section 2 — Active Enemy Registry and Encounter Admission: 'The registry/bookkeeping responsibility is a reusable runtime foundation... Room-specific encounter authoring consumes this foundation later.'
- `door-close-lock-break-lifecycle` — Authoring a configured per-door durability value requires the runtime door-durability field/mechanism it configures to already exist, since Door and Interaction, not Dungeon Encounter, owns runtime durability state and the locked-to-broken transition. Evidence/basis: GDD Section 4 — Dungeon Encounter Agent: 'Authors placements, triggers, configured per-door durability values... It does not own runtime door durability state, damage intake, or the locked-to-broken transition; those remain Door and Interaction responsibilities.'
- `melee-enemy` — Placing and composing encounters (including the required mixed Chapel of Ash and Final Room compositions) requires a usable, assembled Melee Enemy archetype to place. Evidence/basis: GDD Section 4 — Dungeon Encounter Agent: 'Authors placements... including the mixed Melee/Ranged compositions in Chapel of Ash and the Final Room.'
- `ranged-enemy` — Placing and composing encounters (including the required mixed Chapel of Ash and Final Room compositions, and the never-isolated-Ranged-Enemy rule) requires a usable, assembled Ranged Enemy archetype to place. Evidence/basis: GDD Section 4 — Dungeon Encounter Agent: 'Authors placements... including the mixed Melee/Ranged compositions in Chapel of Ash and the Final Room.'

**Notes:** No formal dependency on five-room-content-authoring (both are deferred organizational features per the GDD-hardening example prohibiting feature-to-feature dependencies); it consumes authored room spaces once five-room-content-authoring produces concrete descendants, preserved here as decomposition context only.

### `floor-run-restart` — Floor Run/Restart

- **Kind:** `feature`
- **Type:** `run_lifecycle`
- **Parent:** `no-safe-circle`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `coarse` — The GDD already specifies the orchestrator's ownership contract and required participants in full; this feature node organizes a staged bootstrap implementation plus a later full-closure implementation without inventing missing design.
- **Execution scope:** `not_applicable` — Organizational feature node; not directly dispatchable.
- **Confidence:** `high`

**GDD evidence**

- `Win and Loss Conditions` — Reaching zero health restarts the entire floor by design; restart resets all run-persistent gameplay state to the floor's initial state.
- `Floor-run restart ownership` — A shared Floor Run/Restart Orchestrator consumes Player Health's zero-health transition and invokes owned reset entry points on every run-persistent system rather than mutating their internals directly.

**Notes:** Aggregate repository_state of missing reflects that no restart-related code exists in the current repository at all.

### `floor-run-restart-bootstrap` — Floor Run/Restart Bootstrap (Current-Owner Stage)

- **Kind:** `implementation`
- **Type:** `run_lifecycle`
- **Parent:** `floor-run-restart`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD explicitly authorizes a staged bootstrap that validates only against currently-existing persistent owners, and every owner it must invoke is already named.
- **Execution scope:** `single_agent` — The task subscribes to one existing signal (once added to Player Health) and invokes a small, known set of already-defined owner reset interfaces; it does not itself implement those owners' reset logic.
- **Confidence:** `high`

**GDD evidence**

- `Floor-run restart ownership` — Early implementation may validate the orchestrator against only the persistent systems that currently exist, but full restart closure remains required work until every implemented state owner participates.
- `Player Health ownership` — The restart orchestrator consumes the zero-health transition rather than polling or mutating Player Health internals.

**Acceptance criteria**

- `Floor-run restart ownership` — Subscribes to an owner-exposed zero-health/death transition from Player Health without polling CurrentHealth or writing PlayerHealth fields directly.
- `Floor-run restart ownership` — On trigger, invokes owner-controlled reset entry points for every currently-existing run-persistent owner: Player Health, Player Mana (current mana and regeneration-delay state), Player Movement (player position/movement state), and the door-open-interaction system's currently owned state (open flag, opening progress, and the disabled doorway blocker).
- `Floor-run restart ownership` — Does not directly mutate any consumed owner's internal fields; only calls each owner's exposed reset entry point.

**Validation requirements**

- `Floor-run restart ownership` — Play Mode check: reducing Player Health to zero triggers a fresh floor attempt exactly once per zero-health transition.
- `Floor-run restart ownership` — Play Mode check: after restart, Player Health, Player Mana, player position, and door-open-interaction state (progress/open/blocker) are all back to their floor-initial values.

**Exclusive resources**

- `logical:floor-run-restart-orchestrator` — Both restart stages share one logical orchestrator integration surface; concurrent work on either stage must not race on the orchestrator's wiring. Evidence/basis: Derived rationale: GDD 'A shared Floor Run/Restart Orchestrator coordinates a new floor attempt' describes one orchestrator extended across a bootstrap and a closure stage.
- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — If the orchestrator component is created/wired onto scene objects through the current builder, this file is a shared write surface with other builder-writing tasks. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs builds/clears Floor, Walls, and DoorRoot and saves the scene.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The orchestrator's scene-resident wiring is saved into this canonical scene file, which is a non-merge-safe integration surface. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs saves DoorPrototype.unity.

**Dependencies**

- `player-health` — PlayerHealth.cs currently exposes only TakeDamage/Damaged; it has no zero-health/death event and no reset entry point, both of which this task must consume. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerHealth.cs
- `player-mana` — PlayerMana.cs has no reset entry point for CurrentMana or the post-cast regen-delay timer, which the bootstrap orchestrator must invoke. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMana.cs
- `player-movement` — PlayerMovement.cs has no reset entry point for player position/movement state, which the bootstrap orchestrator must invoke. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs
- `door-open-interaction` — DoorInteractable.cs already owns run-persistent state (Progress, IsOpen, disabled doorwayBlocker) but exposes no reset entry point; the bootstrap orchestrator must invoke one. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs

**Notes:** This is the staged bootstrap explicitly permitted by the GDD; it must not become the graph's only terminal restart work.

### `floor-run-restart-persistent-closure` — Floor Run/Restart Persistent-Systems Closure

- **Kind:** `implementation`
- **Type:** `run_lifecycle`
- **Parent:** `floor-run-restart`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD names the complete required participant list and the exact reset contract for full closure; no missing design remains, though most listed owners do not yet exist.
- **Execution scope:** `needs_execution_decomposition` — This item spans wiring reset participation across roughly a dozen independently-owned systems (player systems, three spells, door lifecycle, enemy state, registry, encounters); that breadth exceeds a single bounded agent handoff even though each individual wiring point is simple once its owner exists.
- **Confidence:** `high`

**GDD evidence**

- `Floor-run restart ownership` — Required reset participants include Player Health, Player Mana, Player Movement/player position, Fireball, Frost Field, Force Wave, enemy health/defeat state, enemy pursuit/search/attack/status/displacement state, Active Enemy Registry bookkeeping, door lifecycle/crossing/durability state, and encounter activation/admission state.
- `Floor-run restart ownership` — Enemy reset returns each persistent enemy to its original authored encounter/spawn region and initial AI state, with no retained target/last-known-position/search/attack/displacement state from the failed run.
- `Spell-local state ownership` — Each spell owner (Fireball, Frost Field, Force Wave) exposes a reset entry point for any owned state that can still be active when a floor restart occurs.

**Acceptance criteria**

- `Floor-run restart ownership` — Extends the same orchestrator used by the bootstrap stage to additionally invoke reset entry points for every implemented persistent owner beyond the bootstrap set, without redesigning the orchestration contract.
- `Floor-run restart ownership` — Full closure is not considered complete while any implemented run-persistent owner does not yet expose/participate in a reset entry point.
- `Floor-run restart ownership` — Enemy reset consumes an enemy-owned restart/reset operation that returns each persistent enemy to its authored encounter/spawn region and initial pursuit/search/attack state, with no retained target or search state; the orchestrator does not write enemy Transform/locomotion internals itself.

**Validation requirements**

- `Floor-run restart ownership` — Play Mode check, expanded as each owner is implemented, confirming every implemented persistent-state owner is reset to its floor-initial state after a zero-health restart.
- `Floor-run restart ownership` — Play Mode check confirming a defeated/repositioned enemy returns to its authored spawn region with no carried target/search/displacement/status state.

**Exclusive resources**

- `logical:floor-run-restart-orchestrator` — Shares the same orchestrator integration surface as the bootstrap stage. Evidence/basis: Derived rationale: GDD describes one orchestrator extended across stages.
- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — Extending/wiring additional restart participants through the current builder is a shared write surface with other builder-writing tasks. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs builds/clears Floor, Walls, and DoorRoot and saves the scene.
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The extended orchestrator wiring is saved into this canonical scene file. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs saves DoorPrototype.unity.

**Dependencies**

- `floor-run-restart-bootstrap` — This item extends the same orchestrator the bootstrap stage creates; the orchestrator implementation must exist first. Evidence/basis: Derived rationale: GDD describes one Floor Run/Restart Orchestrator extended in stages, not two independent orchestrators.
- `player-health` — Required reset participant named directly by the GDD restart contract. Evidence/basis: GDD 'Floor-run restart ownership' required-participant list.
- `player-mana` — Required reset participant named directly by the GDD restart contract. Evidence/basis: GDD 'Floor-run restart ownership' required-participant list.
- `player-movement` — Required reset participant named directly by the GDD restart contract. Evidence/basis: GDD 'Floor-run restart ownership' required-participant list.
- `door-open-interaction` — Required reset participant; also currently owns persistent Progress/IsOpen/blocker state. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs
- `doorway-crossing-state` — Door lifecycle/crossing state is a named required reset participant and is not yet implemented. Evidence/basis: GDD 'Floor-run restart ownership' required-participant list.
- `door-close-lock-break-lifecycle` — Door lifecycle/durability state is a named required reset participant and is not yet implemented. Evidence/basis: GDD 'Floor-run restart ownership' required-participant list.
- `enemy-health-damage-defeat` — Enemy health/defeat state is a named required reset participant and is not yet implemented. Evidence/basis: GDD 'Floor-run restart ownership' required-participant list; repository-wide search found no enemy code.
- `enemy-pursuit-search-foundation` — Enemy pursuit/search/attack state and enemy repositioning to authored spawn regions are named required reset participants and are not yet implemented. Evidence/basis: GDD 'Floor-run restart ownership' required-participant list; repository-wide search found no enemy code.
- `enemy-status-effect-displacement` — Enemy status/displacement state is a named required reset participant and is not yet implemented. Evidence/basis: GDD 'Floor-run restart ownership' required-participant list; repository-wide search found no enemy code.
- `active-enemy-registry` — Active Enemy Registry bookkeeping is a named required reset participant and is not yet implemented. Evidence/basis: GDD 'Floor-run restart ownership' required-participant list; repository-wide search found no registry code.
- `encounter-admission-cap-enforcement` — Encounter activation/admission state is a named required reset participant and is not yet implemented. Evidence/basis: GDD 'Floor-run restart ownership' required-participant list.
- `fireball` — Fireball owns tap/charge/cast state and must expose a reset entry point that full closure invokes; Fireball does not yet exist. Evidence/basis: Repository-wide search found no Fireball implementation.
- `frost-field` — Frost Field owns casting-side cast/placement/active-field state and must expose a reset entry point that full closure invokes; Frost Field does not yet exist. Evidence/basis: Repository-wide search found no Frost Field implementation.
- `force-wave` — Force Wave owns cooldown state and must expose a reset entry point that full closure invokes; Force Wave does not yet exist. Evidence/basis: Repository-wide search found no Force Wave implementation.

**Notes:** Most of this item's dependencies are currently missing entirely (not merely unfinished), so this item cannot be dispatched meaningfully until the underlying owners exist.

### `win-loss-conditions` — Win/Loss Conditions

- **Kind:** `feature`
- **Type:** `run_lifecycle`
- **Parent:** `no-safe-circle`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `coarse` — The GDD fully specifies both the win trigger and the loss trigger; this feature organizes the concrete victory implementation while the loss trigger's handling is owned by floor-run-restart.
- **Execution scope:** `not_applicable` — Organizational feature node; not directly dispatchable.
- **Confidence:** `high`

**GDD evidence**

- `Win and Loss Conditions` — Win: open the final door and escape via confirmed doorway-crossing state, then stop gameplay input and display a You Escaped overlay. Loss: reach zero health, which restarts the floor.

**Notes:** Loss handling itself is represented under floor-run-restart rather than duplicated here, since the GDD routes zero health directly to the restart orchestrator.

### `final-escape-victory` — Final Escape / Victory (Game Flow/Victory Capability)

- **Kind:** `implementation`
- **Type:** `run_lifecycle`
- **Parent:** `win-loss-conditions`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD fully specifies the victory trigger, overlay, and suspend-interface consumption contract; no missing design remains.
- **Execution scope:** `needs_execution_decomposition` — The capability must integrate against six separate owner suspend interfaces plus the crossing-state trigger plus a scene-built overlay; that many independently-owned integration points exceeds a single bounded agent handoff, and none of the consumed owner interfaces exist yet.
- **Confidence:** `high`

**GDD evidence**

- `Win and Loss Conditions` — Victory occurs when the shared doorway-crossing state confirms the wizard crossed to the forward side of the final door; the win condition does not implement a separate crossing detector. Normal gameplay input then stops and a simple You Escaped overlay is displayed.
- `Victory/input-shutdown ownership` — A reusable Game Flow/Victory capability owns the won-state transition, overlay display, and gameplay-shutdown coordination. Player Movement, Door/Interaction, Fireball, Frost Field, and Force Wave each expose an owner-controlled gameplay-enable/suspend interface that the victory capability consumes rather than mutating internal state; the interface must stop already-active input-driven activity, not merely block new input.

**Acceptance criteria**

- `Win and Loss Conditions` — Victory is triggered exactly when the shared doorway-crossing state (owned by Door and Interaction) reports forward-side crossing of the final door; no independent crossing check is implemented.
- `Win and Loss Conditions` — On victory, a simple player-facing 'You Escaped' overlay is displayed; no additional post-victory progression, menu flow, or meta-progression is implemented.
- `Victory/input-shutdown ownership` — On victory, the capability calls owner-controlled suspend entry points on Player Movement, Door/Interaction, Fireball, Frost Field, and Force Wave; each suspend call stops that system's already-active input-driven activity (e.g., an in-progress door approach or spell charge) and causes new gameplay commands to that system to be rejected while suspended.
- `Victory/input-shutdown ownership` — The capability does not directly mutate movement/door/spell-internal state; it only invokes each owner's exposed suspend/re-enable interface, and re-enable is reachable only through an authorized reset/test flow.

**Validation requirements**

- `Win and Loss Conditions` — Play Mode check: crossing the final door's forward side triggers the You Escaped overlay and halts movement, door interaction, and all three spells' input-driven activity, including activity already in progress at the moment of crossing.
- `Victory/input-shutdown ownership` — Play Mode check: after victory, issuing movement/door/spell input produces no gameplay effect until an authorized re-enable/reset flow runs.

**Exclusive resources**

- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` — Under the current scene-built UI approach, final-victory work creates/configures the You Escaped overlay through this builder, a shared write surface with other builder-writing tasks. Evidence/basis: Shared Context and Coordination Rules: 'Current prototype scene-builder lock ... applies ... under the current scene-built UI approach, to final-victory work that creates/configures the You Escaped overlay.'
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` — The overlay/victory wiring is saved into this canonical scene file. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs saves DoorPrototype.unity.

**Dependencies**

- `doorway-crossing-state` — Victory consumes Door and Interaction's shared forward-side crossing state as its sole trigger; that state does not yet exist. Evidence/basis: GDD 'Door and Pursuit Rules' establishes Door and Interaction as sole owner of doorway-crossing state; repository search found no crossing detection in DoorInteractable.cs.
- `player-movement` — Victory must be able to stop already-active movement through an owner-controlled suspend interface; PlayerMovement.cs currently exposes no such interface. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs
- `door-open-interaction` — Victory must be able to stop an in-progress door approach/opening through an owner-controlled suspend interface; DoorInteractable.cs/PlayerInteractionController.cs currently expose no such interface. Evidence/basis: Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs; Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerInteractionController.cs
- `fireball` — Victory must be able to stop in-progress Fireball charging/casting through an owner-controlled suspend interface; Fireball does not yet exist. Evidence/basis: Repository-wide search found no Fireball implementation.
- `frost-field` — Victory must be able to stop in-progress Frost Field casting/placement through an owner-controlled suspend interface; Frost Field does not yet exist. Evidence/basis: Repository-wide search found no Frost Field implementation.
- `force-wave` — Victory must be able to stop in-progress Force Wave cooldown/casting through an owner-controlled suspend interface; Force Wave does not yet exist. Evidence/basis: Repository-wide search found no Force Wave implementation.

**Notes:** If a future graph introduces a single shared input-gating owner that centralizes these consumers, victory should depend on that owner instead of duplicating six edges (per prompt guidance); no such owner currently exists.

### `no-safe-circle` — No Safe Circle

- **Kind:** `feature`
- **Type:** `root`
- **Parent:** ``
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `partial`
- **Proposed graph status:** `open`
- **Decomposition:** `coarse` — Root organizational feature; all concrete decomposition is represented by domain-specific descendant features/implementations produced across the full set of reconciliation workers.
- **Execution scope:** `not_applicable` — Root feature is not directly executable; it exists purely to aggregate the complete work graph.
- **Confidence:** `medium`

**GDD evidence**

- `Section 1 - Executive Summary` — No Safe Circle is a single-player, 2.5D isometric survival action game set on one handcrafted dungeon floor; the player wins by escaping through the final door and loses at zero health.

**Acceptance criteria**

- `Section 3 - Required Scope, Exclusions, and Stretch Goals` — The completed game satisfies the stated Required Scope: one wizard, one handcrafted 2.5D isometric floor with five connected spaces, three spells, two enemy archetypes, mana regeneration, sealed doors, cross-room pursuit, death and restart, essential feedback, and a Windows build.

**Notes:** This worker only directly inspected the global_pipeline domain (delivery/build and non-code/process requirements). Aggregate repository_state of 'partial' reflects that the GDD's own Current Prototype Scene Evidence section confirms a working DoorPrototype scene/script set exists, while the confirmed zero-scene Windows build registration (see windows-build-scene-registration) and the broad required scope described in Section 3 indicate most required systems remain open. Per the feature-aggregate rule, no child repository_evidence is duplicated here; other domain workers' own root-adjacent findings should be reconciled against this at merge time.

### `delivery-and-build` — Delivery and Build

- **Kind:** `feature`
- **Type:** `delivery`
- **Parent:** `no-safe-circle`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `coarse` — The delivery obligation is already fully specified by the GDD (Windows Standalone target, canonical scene registration prerequisite); the concrete configuration work is represented by windows-build-scene-registration without inventing new design.
- **Execution scope:** `not_applicable` — Organizational feature grouping delivery/build obligations; not itself directly executable.
- **Confidence:** `high`

**GDD evidence**

- `Section 3 - Required Scope, Exclusions, and Stretch Goals` — Required scope explicitly includes 'a Windows build.'
- `Section 5 - Approved Unity Packages and Windows Build Configuration` — The required delivery target is a Windows Standalone build; the canonical gameplay scene must be registered in Unity Build Settings before the Windows delivery requirement can be considered complete.

**Acceptance criteria**

- `Section 5 - Approved Unity Packages and Windows Build Configuration` — A Windows Standalone build of the completed game is the required delivery artifact for the capstone.

**Notes:** Aggregate repository_state of 'missing' reflects that its sole currently-known concrete descendant (windows-build-scene-registration) has confirmed zero registered scenes and no other build-configuration evidence was found. Per the feature-aggregate rule, evidence is kept on the child implementation item rather than duplicated here.

### `windows-build-scene-registration` — Windows Build Scene Registration

- **Kind:** `implementation`
- **Type:** `build-configuration`
- **Parent:** `delivery-and-build`
- **Basis:** `direct_gdd` / `required`
- **Repository state:** `missing`
- **Proposed graph status:** `open`
- **Decomposition:** `concrete` — The GDD explicitly names the required action (register the canonical scene, configure Windows Standalone) and the current repository state (zero registered scenes) confirms the gap without requiring any new design.
- **Execution scope:** `single_agent` — Registering one named scene and configuring the Windows Standalone build target is a bounded project-configuration change one agent can perform; the required human inspection of the result afterward is a separate pipeline gate (see 'Human inspection and final integration authority'), not an execution-scope split.
- **Confidence:** `high`

**GDD evidence**

- `Section 5 - Approved Unity Packages and Windows Build Configuration` — The current canonical gameplay scene is Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity; that scene (or a later human-approved replacement) must be registered in Unity Build Settings before the Windows delivery requirement can be considered complete. A committed EditorBuildSettings.asset with no registered canonical gameplay scene is confirmed incomplete build configuration. The top-level Assets/Scenes/DoorPrototype.unity and Assets/Scenes/SampleScene.unity stubs do not satisfy this requirement merely because they are .unity files.

**Acceptance criteria**

- `Section 5 - Approved Unity Packages and Windows Build Configuration` — The canonical gameplay scene (currently Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity, or a later human-approved replacement) is registered in Unity Build Settings.
- `Section 5 - Approved Unity Packages and Windows Build Configuration` — Windows Standalone is configured as the active/target build platform.
- `Section 5 - Current Prototype Scene Evidence` — The non-canonical Assets/Scenes/DoorPrototype.unity and Assets/Scenes/SampleScene.unity stub scenes must not be registered as substitutes for the canonical gameplay scene.

**Validation requirements**

- `Section 5 - Approved Unity Packages and Windows Build Configuration` — The developer inspects the resulting package state, scene registration, and Windows build configuration before merge.
- `Section 5 - Technical Strategy` — A Windows Standalone build must be producible from the registered canonical gameplay scene.

**Repository evidence**

- `ProjectSettings/EditorBuildSettings.asset` (`project_setting`) — m_Scenes: [] — no scene is currently registered in Unity Build Settings, directly confirming the GDD's stated incomplete build-configuration fact.

**Exclusive resources**

- `repo-file:ProjectSettings/EditorBuildSettings.asset` — EditorBuildSettings.asset is the single project-wide Build Settings scene list; concurrent edits from another task risk conflicting/overwritten scene registrations. Evidence/basis: ProjectSettings/EditorBuildSettings.asset currently contains m_Scenes: [] as the sole authoritative Unity build-scene list for this project.

**Notes:** Do not repurpose the non-canonical Assets/Scenes/DoorPrototype.unity or Assets/Scenes/SampleScene.unity stubs to satisfy this item; per the GDD's Current Prototype Scene Evidence section and the 'Non-canonical prototype scene preservation' pipeline constraint, their disposition is a separate human decision.

## Non-Code Requirements

- **[delivery_requirement / confirmed] Windows build:** Directly and repeatedly stated as required delivery scope in the current GDD; represented as an actionable configuration gap via windows-build-scene-registration.
- **[pipeline_constraint / confirmed] No concurrent Unity asset edits:** Stated identically in both Section 4 and Section 5 as a hard process invariant; applications of this rule are represented per-task via exclusive_resources across all domain workers.
- **[pipeline_constraint / confirmed] Credentials outside source control:** Directly stated in Section 5 API and Tool Constraints.
- **[pipeline_constraint / confirmed] Minimal-context dispatch:** Explicitly required by both Section 4 and Section 5 as a mandatory pipeline constraint.
- **[pipeline_constraint / confirmed] Failed-task retry policy:** Directly stated as a required pipeline constraint in Section 5.
- **[pipeline_constraint / confirmed] Compile-before-validation gate:** Directly stated in Section 5 API and Tool Constraints.
- **[pipeline_constraint / confirmed] Isolated execution and task handoff requirements:** Directly stated as required process/handoff structure in Section 4 and reiterated in Section 5 Agent Coordination.
- **[pipeline_constraint / confirmed] Human inspection and final integration authority:** Explicitly stated as required human-authority process constraints in Sections 4 and 5.
- **[pipeline_constraint / confirmed] Agent scope and canon discipline:** Stated identically in Section 4 and Section 5 as a required scope-discipline constraint on implementation/planning/reconciliation agents.
- **[non_code_requirement / confirmed] Runtime generative-AI prohibition:** Directly and explicitly required/excluded scope in the current GDD; a non-code technical constraint on the shipped game rather than a build step or agent-process rule.
- **[pipeline_constraint / confirmed] Development-time generated-art import boundary:** Directly stated in Section 5 Runtime Implementation and reiterated in the Technical Strategy generative-tools note; a required process/validation constraint on content/asset pipeline work rather than gameplay implementation.
- **[pipeline_constraint / confirmed] Non-canonical prototype scene preservation:** Directly stated in Section 5 Current Prototype Scene Evidence; confirmed present via Assets/Scenes/DoorPrototype.unity and Assets/Scenes/SampleScene.unity glob results.
- **[pipeline_constraint / confirmed] Current prototype scene-builder exclusive-write lock:** Directly stated as a required durable process rule in Section 4; per-task applications are represented as matching exclusive_resources entries across domain workers whose implementation writes through the builder/scene.
- **[pipeline_constraint / confirmed] Development Agent Ownership Invariants:** Directly stated as a required cross-cutting process constraint in Section 4; the specific per-agent ownership boundaries (Wizard Combat, Enemy Pursuit, Door and Interaction, victory coordination, Dungeon Encounter, Unity Validation) are represented as acceptance criteria/dependencies on their respective owning work items across the other domain workers.
- **[pipeline_constraint / confirmed] Planning token budget ceiling:** Directly stated as a pipeline planning/orchestration constraint in Section 5 Token Budget.

## Deferred / Excluded

- **[stretch] Spectral Decoy:** Named stretch goal, not required Milestone 1 scope.
- **[stretch] Third enemy archetype:** Named stretch goal beyond the two required enemy archetypes (Melee Enemy, Ranged Enemy).
- **[stretch] Fireball-charge reactions:** Named stretch goal extending Charged Fireball beyond required behavior.
- **[stretch] Awareness indicator:** Named stretch goal for additional enemy-awareness feedback beyond required feedback.
- **[stretch] Frost Field slowing a breach:** Named stretch goal extending Frost Field's effect to door-breach mechanics beyond required scope.
- **[stretch] Advanced door damage:** Named stretch goal extending door durability/damage behavior beyond required scope.
- **[stretch] One additional room:** Named stretch goal beyond the required five-space floor.
- **[explicitly_excluded] Multiplayer:** Explicitly excluded scope; the game is single-player.
- **[explicitly_excluded] Character classes:** Explicitly excluded scope; the player controls one wizard with no class selection.
- **[explicitly_excluded] Equipment:** Explicitly excluded scope.
- **[explicitly_excluded] Loot:** Explicitly excluded scope.
- **[explicitly_excluded] Skill trees:** Explicitly excluded scope.
- **[explicitly_excluded] Quests:** Explicitly excluded scope.
- **[explicitly_excluded] Vendors:** Explicitly excluded scope.
- **[explicitly_excluded] Procedural generation:** Explicitly excluded scope; the floor is handcrafted.
- **[explicitly_excluded] Persistent progression:** Explicitly excluded scope; no meta-progression across runs.
- **[explicitly_excluded] Multiple floors:** Explicitly excluded scope; only one handcrafted floor is required.
- **[explicitly_excluded] Bespoke 3D character models or rigs:** Explicitly excluded scope; presentation is 2.5D isometric with SpriteRenderer prefabs, not bespoke 3D models/rigs.
- **[explicitly_excluded] Free-rotation 3D camera presentation:** Explicitly excluded scope; the camera is fixed isometric with no free world-view rotation.
- **[explicitly_excluded] Generative AI during play:** Explicitly excluded scope; also independently represented as the 'Runtime generative-AI prohibition' non_code_requirement.

## Unresolved Questions

### Will Play Mode validation for enemy-pursuit-search-foundation/melee-enemy/ranged-enemy (e.g., Bone Archive lane pathing, Chapel of Ash occlusion, cross-doorway pursuit) require instantiating enemy prefabs into the canonical DoorPrototype.unity scene via DoorPrototypeSceneBuilder.cs, which would require adding the current builder/scene exclusive-resource locks used by other tasks that write through that builder?

- **Affects:** enemy-pursuit-search-foundation, melee-enemy, ranged-enemy
- **Why unresolved:** The current DoorPrototypeSceneBuilder.cs does not build or reference any enemy object today, and no repository evidence establishes that these archetype/foundation tasks must modify that specific builder script; encounter placement (a different domain) is the more likely owner of scene-integration writes. Adding the lock now would be speculative.
- **Recommended resolution:** `later_decomposition`

### Does door-open-interaction need to independently add/modify a binding in Assets/InputSystem_Actions.inputactions (e.g., a distinct door-select action), or does it purely consume a Point/Click binding that Player Movement's shared pointer-projection work will add to the Player action map?

- **Affects:** door-open-interaction, player-movement
- **Why unresolved:** The current 'Player' action map has no gameplay Point/Click action (only 'Interact' with a Hold interaction, and the UI map's Point/Click bindings serve UI navigation, not gameplay). Whether door selection reuses Player Movement's forthcoming shared click/pointer target or requires its own binding cannot be determined without the actual Player Movement implementation design.
- **Recommended resolution:** `later_decomposition`

### Should the final overlay/victory-shutdown integration be represented as one implementation item (as done here) or split at bootstrap time into a trigger/consumption item versus a suspend-coordination item, given it currently depends on six not-yet-existing owner interfaces?

- **Affects:** final-escape-victory
- **Why unresolved:** The GDD describes one Game Flow/Victory capability, but every consumed suspend interface is currently missing, making the true execution-decomposition shape hard to judge until at least Player Movement and one spell exist.
- **Recommended resolution:** `later_decomposition`

### Is the enemy-owned restart/reset operation (returning a persistent enemy to its authored spawn region with cleared pursuit/search/status/displacement state) a single reset entry point on one enemy-behavior owner, or does it need to be split across enemy-pursuit-search-foundation and enemy-status-effect-displacement since those are separate registered keys?

- **Affects:** floor-run-restart-persistent-closure, enemy-pursuit-search-foundation, enemy-status-effect-displacement
- **Why unresolved:** No enemy code exists yet, so the current repository gives no evidence of how pursuit/search state and status/displacement state will be split across components.
- **Recommended resolution:** `later_decomposition`

## Sources

- **GDD:** `Docs/GDD/No_Safe_Circle_GDD.md`
- **Code root:** `Assets`
- **Historical evidence reviewed:**
  - `GoalOrientedAgent/outputs/goal_analysis.json`

## Next Step

Treat this file as an immutable point-in-time reconciliation snapshot. Do not edit it to reflect later implementation progress. Review the accompanying `PROPOSED_GRAPH_DELTA.md`; approved changes belong in the persistent `Tasks/*.yaml` graph, not back in this snapshot.
