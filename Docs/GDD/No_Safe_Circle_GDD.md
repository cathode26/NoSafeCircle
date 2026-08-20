---
title: "No Safe Circle"
document_type: "Capstone Game Design Document"
status: "Final Draft"
author: "Vincent Liguori"
original_date: "2026-07-21"
revised_date: "2026-08-20"
source_docx: "Docs/GDD/No_Safe_Circle_GDD_Final.docx"
---

# No Safe Circle

**Capstone Game Design Document**

**Working Title | Final Draft | Originally July 21, 2026; revised August 20, 2026 | Vincent Liguori**

> A wizard must create brief moments of safety, open sealed doors under pressure, and escape a dungeon while the monsters left behind continue to pursue.

## 1. Executive Summary

No Safe Circle is a single-player, 2.5D isometric survival action game set on one handcrafted dungeon floor. The presentation is inspired by early isometric action/RPGs such as Diablo 1 and Ultima Online: the camera is fixed, the world is viewed at an angle, and the visible environment is authored as isometric art rather than as a free-rotation 3D space. The player controls a vulnerable wizard who can destroy small groups of monsters with powerful spells but cannot survive being surrounded. The player must control distance, wait for mana to regenerate, and decide when to fight, flee, or risk opening the next sealed door.

Each room ends at a door that takes five uninterrupted seconds to open. Before attempting it, the player must create space by luring enemies away, slowing them with Frost Field, knocking them back with Force Wave, or defeating enough of them to reduce the immediate threat. Enemies can follow the wizard through an open doorway. After crossing, the player can close and lock the door, but surviving pursuers will pound against it and eventually break through.

Locked doors provide recovery time, not permanent safety. In the final room, the player must create enough distance from the pursuing enemies to open the final door and escape. The player wins by passing through the final door and loses if the wizard's health reaches zero.

| Field | Value |
|---|---|
| Genre | 2.5D isometric dark-fantasy survival action |
| Platform | Windows PC |
| Playable Content | One handcrafted 2.5D isometric floor; five connected spaces |
| Player Character | One vulnerable wizard; no class selection |
| Core Abilities | Charged Fireball, Frost Field, Force Wave |
| Core Enemies | Melee Enemy and Ranged Enemy |
| Win Condition | Open the final door and escape |
| Loss Condition | The wizard reaches zero health |

### Design Pillars

- Safety is always temporary. Doors delay pursuing enemies but do not remove the threat created by monsters left alive.
- Magic creates opportunities rather than constant power. Frost Field slows pursuit, Force Wave creates space, and Charged Fireball rewards the player for preparing a safe moment to attack.
- Escape is a valid strategy with lasting consequences. The player is not required to defeat every enemy, but surviving monsters may follow through open doors or break into later rooms.

### Required Scope

See "Required Scope, Exclusions, and Stretch Goals" in Section 3 for the authoritative scope list.

## 2. Game Mechanics

The player moves through connected rooms toward the final door. In each room, the objective is to create five safe seconds, open the next door, cross through it, and lock it before the pursuing monsters arrive.

### Core Gameplay Loop

1. Scout the room, locate the sealed door, and identify a route for luring or slowing enemies.
2. Avoid the group, pull part of it away, or spend mana on a direct fight.
3. Use Frost Field and movement to stretch the chase; charge Fireball when enough distance exists.
4. Use Force Wave if enemies reach the wizard or block the door.
5. Open the door for five uninterrupted seconds, cross through it, lock it, and recover before pursuers break through.

### Player Actions and Systems

| Action | What the player does | Purpose |
|---|---|---|
| Move and Aim | Use mouse-directed movement: click to set a destination or hold to keep steering toward the cursor. The cursor also serves as the aiming and targeting reference for spells and cursor-targeted interactions such as sealed doors. | Create and preserve escape routes while maintaining the spatial feel of early isometric action/RPG movement. |
| Fireball | Tap for a quick, mobile shot against a single or separated enemy. Hold to charge: costs more mana and restricts movement further, rewarding preparation by damaging multiple clustered enemies. | Rewards distance and preparation; a charge's area advantage matters against groups, not against one target. |
| Frost Field | Place a temporary area that heavily slows enemies. | Divides crowds and protects routes. |
| Force Wave | Use a short-range radial knockback with a long cooldown. | Creates emergency space. |
| Open Sealed Door | Target the sealed door with the cursor while within arm's reach, then hold the interaction for five seconds. Once the interaction begins, the selected door remains latched even if the cursor moves off it. Player movement, taking damage, or releasing/canceling the hold resets the attempt. | Makes each exit a positioning challenge without requiring sustained pointer precision after the intended door has already been selected. |
| Close and Lock | Shut the door after crossing, restoring a small, fixed amount of health. Once locked, this door cannot be reopened or crossed again (see Door and Pursuit Rules). | Creates recovery time while pursuers attack it, and marks forward progress as final. |

### Spell and Enemy Interactions

| Spell | Against Melee Enemies | Against Ranged Enemies |
|---|---|---|
| Charged Fireball | Melee enemies naturally cluster while pursuing the wizard, making them strong area-damage targets. Charging becomes unsafe once they close the distance. | Telegraphed ranged attacks force the player to keep moving, reducing the time available for a full charge. Quick shots are safer but provide less damage and area. |
| Frost Field | Strongest against melee groups because it slows direct pursuit, stretches the formation, and creates an opening to charge Fireball or begin opening a door — though it draws a meaningful share of the shared mana pool and does not guarantee a fully safe charge in every position or against every group. Against a small or loosely spaced group, direct positioning, a partial charge, or tap Fireball can be the better resource decision. | Slows a ranged enemy's repositioning but does not stop its attacks. The player must still move laterally or use room geometry to avoid incoming shots. |
| Force Wave | The primary emergency response when melee enemies surround the wizard or block access to a door. Its long cooldown prevents repeated use. | Its short range makes it a poor answer to distant ranged pressure. Reaching a ranged enemy to use it may expose the wizard to the melee group. |

The three spells solve different problems: Frost Field controls pursuit, Force Wave repairs an immediate positioning mistake, and Charged Fireball converts a previously created opening into damage. No single spell reliably answers both enemy types by itself. Force Wave's cooldown is tuned so an encounter space typically allows only about one meaningful use: spending it to escape a mid-room surround may leave none available for that room's door attempt, and saving it for the door means resolving mid-room danger without it. This is an intentional resource decision, not proof that either use was wrong.

### Resources, Feedback, and Failure

- Health: The wizard survives a few isolated hits but dies quickly when trapped. Health does not regenerate during a room, and does not reset between rooms — it carries across the whole run. Successfully locking a door after crossing restores a small, fixed amount of health before the next room begins; this recovery is partial, so accumulated damage still matters across all five rooms. Exact recovery values will be set during playtesting.
- Player Health ownership: The shared Player Health system is the single owner of the wizard's current health. It exposes owner-controlled damage and restore interfaces. Door locking requests the fixed recovery through the Player Health restore interface; restoration is clamped to maximum health, and Door and Interaction never writes player-health state directly.
- Health feedback: The wizard's current health is continuously visible through a simple player-facing health indicator. Because damage persists across rooms, the player must be able to read accumulated damage and remaining survivability throughout the run.
- Mana: Mana regenerates slowly after a brief post-cast delay. Waiting restores power while locked doors continue losing durability.
- Movement: Circling or retreating creates temporary separation from pursuers, but Melee Enemies gradually close the distance over time; movement alone cannot preserve a completely safe distance indefinitely in later encounters. Sustaining real separation requires turning routes, obstacles, Frost Field, Force Wave, or reducing the threat directly.
- Force Wave: A visible long cooldown shows when the emergency escape tool is unavailable.
- Door feedback: Banging, shaking, cracks, and a durability indicator show when a breach is near.
- Setbacks: Door-opening attempts reset when player movement, taking damage, or releasing/canceling the hold interrupts them. Cursor movement away from the selected door after the interaction has begun does not reset progress.

### Win and Loss Conditions

**Win:** Open the final door and escape the dungeon. Victory occurs when the shared doorway-crossing state confirms that the wizard has crossed to the forward side of the final door; the win condition does not implement a separate crossing detector. Once victory is confirmed, normal gameplay input stops and a simple player-facing **You Escaped** overlay is displayed. No additional post-victory progression, menu flow, or meta-progression is required for the capstone.

**Loss:** Reach zero health. The floor then restarts from the beginning. This is an intentional, single-attempt structure — reaching zero health at any point restarts the entire floor by design, not as a placeholder. Restart resets all run-persistent gameplay state to the floor's initial state, including player resources/cooldowns, persistent enemy objects and enemy health, pursuit/search state, Active Enemy Registry bookkeeping, door lifecycle/crossing state, encounter activation state, and player position.

**Floor-run restart ownership:** A shared Floor Run/Restart Orchestrator owns starting a fresh floor attempt and coordinating the reset. It does not reach into or duplicate another system's internal state. Every system that owns run-persistent state must expose a reset entry point for the state it owns, and the orchestrator invokes those owned reset interfaces. Required reset participants include Player Health, Player Mana/cooldowns, player position, enemy health/defeat state, enemy pursuit/search state, Active Enemy Registry bookkeeping, door lifecycle/crossing/durability state, and encounter activation/admission state. Early implementation may validate the orchestrator against only the persistent systems that currently exist, but full restart closure remains required work until every implemented run-persistent owner participates; adding later rooms or persistent systems must extend the reset participants without redesigning the orchestration contract.

## 3. Player Experience and Content Scope

The player should feel powerful for a few seconds and vulnerable immediately afterward: control a corridor, charge a Fireball, sprint to a door, and lock it just before the crowd arrives. Pounding from the other side makes the next decision urgent.

### Dungeon Floor Structure

| Area | Layout and Tactical Purpose |
|---|---|
| 1. Ruined Entry | A mostly open space with a broad route around collapsed rubble. The player learns to circle a melee enemy, preserve an escape route, and recognize when charging Fireball is safe. |
| 2. Bone Archive | Tall shelves and collapsed archive furniture create narrow lanes and chokepoints. Melee enemies can be slowed inside a lane with Frost Field and clustered for Fireball, but the player can also be trapped by choosing the wrong aisle. |
| 3. Chapel of Ash | Pews and stone columns provide line-of-sight breaks from the newly introduced Ranged Enemy, which appears here alongside Melee Enemy support rather than alone. The central aisle offers the fastest route to the door but leaves the player exposed, while side routes provide cover at the cost of distance. |
| 4. Lower Vault | Columns and storage piles create several incomplete loops rather than one safe circuit. The player must watch both the current encounter and the previous doorway, because surviving enemies from earlier rooms are the same persistent pursuers breaking through behind them, not newly spawned enemies. |
| 5. Final Room | A comparatively open chamber with limited cover and one central obstacle, populated by both Melee and Ranged Enemies. The player must combine movement, Frost Field, Force Wave, and Fireball to create the final uninterrupted five-second escape window. |

### Required Enemy Roster

| Enemy | Basic behavior | Player effect |
|---|---|---|
| Melee Enemy | Runs at the wizard and attacks at close range. | Prevents long stationary casts and becomes dangerous in groups. |
| Ranged Enemy | Keeps moderate distance and fires a slow telegraphed shot. | Forces lateral movement while Melee Enemies close in. |

Ranged Enemies never appear as an isolated encounter: every encounter that introduces one also includes at least one Melee Enemy. A Ranged Enemy may still end up fighting alone if the player defeats its Melee support first — tap Fireball, cover, and lateral movement remain effective against a lone survivor.

Both enemy archetypes deal damage through the shared **Player Health** system. A successful Melee or Ranged Enemy attack calls the Player Health damage interface; enemy attack implementations do not maintain separate copies of player-health state.

### Enemy Detection, Pursuit, and Target Loss

- Each enemy uses a **Detection Distance** for acquiring the player and a larger **Lose Target Distance** for breaking active pursuit. Detection Distance must be smaller than Lose Target Distance so an enemy does not rapidly alternate between acquiring and losing the player at one boundary.
- When the player enters Detection Distance, the enemy acquires the wizard as its target and pursues according to its archetype. Crossing an open doorway does not by itself clear that target.
- When the player moves beyond Lose Target Distance, the enemy stops tracking the player's exact current position and enters a search state using the player's last known position. The distance threshold determines this transition; randomness does not decide whether the enemy forgets the player.
- The enemy continues toward the last known position. If it reaches that position without reacquiring the player, it performs a short, bounded search/wander using controlled randomness to choose a nearby navigable direction or point, periodically checking for the player again.
- If the player re-enters Detection Distance during search/wander, the enemy reacquires the wizard and returns to normal pursuit.
- If the bounded search completes without reacquisition, the enemy clears the target and returns to its local idle/wander behavior. Losing the target does not despawn, replace, or reset the enemy; it remains the same persistent enemy object and can be encountered again later.
- Exact Detection Distance, Lose Target Distance, search duration, and search/wander weighting are tuning values to be established during playtesting.


### Door and Pursuit Rules

- Enemies move between rooms through open doors; crossing a doorway does not clear pursuit. Active pursuit is lost only through the distance-and-search behavior defined in **Enemy Detection, Pursuit, and Target Loss**.
- A sealed door is a cursor-targeted interactable. The player must target the intended door with the cursor while within arm's reach to begin the five-second hold. After the interaction begins, the door remains selected even if the cursor moves off it. Player movement, taking damage, or releasing/canceling the hold resets the attempt.
- The **Door and Interaction system owns doorway-crossing state**. After a door is open, it detects when the wizard has actually crossed to that door's forward side and exposes that state to consumers. Opening a door does not by itself count as crossing. Door locking and the final escape condition consume this same crossing state rather than implementing separate crossing detectors.
- **Door passability contract:** Door and Interaction owns the semantic door state (`sealed`, `open`, `locked`, `broken`). The shared gameplay navigation/locomotion layer owns translating that semantic state into enemy walkability through a shared passability interface. Sealed and locked doors block enemy traversal; open and broken doors permit forward enemy traversal. Door state changes update the navigation layer through that interface, while enemy pursuit/attack code does not independently manipulate NavMesh or doorway passability. The exact Unity mechanism used beneath this interface (for example obstacle/carving, a navigation link, or runtime navigation-data update) is an implementation choice rather than a separate game-design decision.
- After crossing, the player can lock the door. Enemies actively pursuing the player that witnessed the escape and are blocked by that locked door begin attacking it; an enemy that has already lost the player does not begin attacking a locked door solely because it is nearby. Once locked, a door cannot be reopened, unlocked, or crossed again by the player — the floor is a forward-only escape sequence.
- If the player waits too long, the locked door breaks and the surviving group enters the current room. A broken door remains open and cannot be closed or relocked for the remainder of the run. The player cannot travel backward through an earlier doorway, including after its locked door has been broken; enemies may pass forward through the broken doorway, but it is not a return path for the player.
- Surviving enemies carry forward and combine with later encounters as the same persistent enemy objects, not new spawns, and the game never permits more than fifteen active enemies at once.

### Active Enemy Registry and Encounter Admission

- A shared **Active Enemy Registry** tracks the persistent enemy objects currently active in the run and exposes the current active count and remaining capacity under the hard limit of fifteen.
- Enemy activation registers an enemy with the registry; defeat removes that enemy from the active count. Target loss, searching, crossing rooms, or waiting behind a locked door does not remove a surviving persistent enemy from the registry.
- The Dungeon Encounter system consumes the registry before activating new encounter enemies. If activating the requested enemies would exceed fifteen active enemies, new encounter enemies are delayed or reduced first; existing persistent pursuers are never removed to make room.
- The registry/bookkeeping responsibility is a reusable runtime foundation and does not require the exact five-room encounter layouts, placements, or trigger authoring to be known first. Room-specific encounter authoring consumes this foundation later.
- Lower Vault is the primary validation case because a rear breach can coincide with the room's own encounter; persistent pursuers keep priority over admitting additional new enemies.

### Required Scope, Exclusions, and Stretch Goals

**Required:** one wizard, one handcrafted 2.5D isometric floor, five spaces, three spells, two enemies, mana regeneration, sealed doors, pursuit across rooms, death and restart, essential feedback, and a Windows build.

**Excluded:** multiplayer, classes, equipment, loot, skill trees, quests, vendors, procedural generation, persistent progression, multiple floors, bespoke 3D character models or rigs, free-rotation 3D camera presentation, and generative AI during play.

**Stretch goals:** Spectral Decoy, a third enemy, Fireball-charge reactions, an awareness indicator, Frost Field slowing a breach, advanced door damage, and one additional room.

### Environment Presentation and Authoring Direction

- The game uses a fixed 2.5D isometric presentation inspired by Diablo 1 and Ultima Online.
- The primary environment visual layer uses **Unity Isometric Tilemaps** for floors, walls, and repeatable architectural tiles.
- The wizard, enemies, taller props, interactive doors, obstacles, decorative set pieces, and other independently sorted objects use **world-space SpriteRenderers and prefabs** instead of being painted directly into a Tilemap. Placeholder character sprites are acceptable during development, but the wizard and enemy visual representations follow the same isometric sorting conventions as other world-space SpriteRenderers.
- The visible isometric art layer is kept separate from the underlying gameplay representation so art can be revised without redefining core gameplay rules.
- The gameplay layer still owns walkability, collision, trigger volumes, door state, pursuit logic, and other simulation behavior. The reusable Tilemap/SpriteRenderer world foundation establishes authoring conventions and visual/gameplay separation; it does **not** by itself include authoring all five room layouts or encounter content.

### Player Experience Success Criteria

- A first-time player understands that reaching a door is not enough; five safe seconds are required.
- Door interaction requires accurate target selection only when the interaction begins; normal cursor drift after the door is selected does not cancel opening.
- The player understands that enemies left alive remain a threat: leaving them alive means locking a door while they attack it, and later encountering them if that door breaks through.
- Encounters use three to eight enemies and never exceed fifteen active enemies.
- Failure is readable: poor positioning, low mana, using Force Wave without an immediate threat and leaving it unavailable when critical space is needed, or waiting too long.

### Peer and Agent Review Revision

Peer feedback identified that the earlier draft did not explain how the spells and room layouts produced different tactical decisions. A targeted multi-agent review then tested whether those decisions could collapse into a dominant strategy. This revision clarifies Fireball's tap-versus-charge tradeoff, Frost Field's resource commitment, Force Wave's mid-room-versus-door decision, mixed enemy compositions, persistent-pursuer priority, room-specific implementation checks, distance-based target loss and search behavior, accessible cursor-targeted door interaction, shared doorway-crossing ownership, enemy damage through Player Health, active-enemy bookkeeping, and runtime ownership boundaries, Player Health restoration ownership, door-to-navigation passability prerequisites, player-experience validation obligations, and failed-task retry policy without expanding the required content scope.

## 4. AI Architecture

Development agents help plan, implement, review, and test No Safe Circle; they do not run in the finished game. Each agent owns a visible game feature, receives concrete acceptance criteria, and produces a Unity test or implementation result.

### Development Agent Roles

| Agent | Plain-English role | Effect on this game |
|---|---|---|
| Feature Planning Agent | Turns one approved feature into acceptance criteria and a file list. | Keeps prompts specific and prevents scope growth. |
| Wizard Combat Agent | Implements player movement, Fireball, Frost Field's casting, mana cost, and feedback, Force Wave, health, mana, cooldowns, and recovery. Frost Field's actual slowdown effect is applied and restored by the Enemy Pursuit Agent, which owns enemy movement and all Ranged Enemy attack behavior; this agent only triggers the Frost Field effect and does not implement Ranged Enemy targeting or attacks. | Creates the tools used to slow, attack, escape, and recover, without editing enemy-movement or enemy-attack code directly. |
| Door and Interaction Agent | Implements cursor-targeted door selection, arm's-reach validation, the latched five-second opening interaction, interruption, shared doorway-crossing state, closing, locking, damage, and breaking. It is the single owner of detecting when the wizard crosses to the forward side of an opened door; locking and final escape consume that state. After a valid opening interaction begins, cursor movement off the selected door does not cancel it; movement, damage, or releasing/canceling the hold does. | Makes room exits risky and safety temporary without requiring sustained pointer precision after selection, while preventing multiple systems from inventing separate doorway-crossing logic. |
| Enemy Pursuit Agent | Implements detection, melee and ranged attacks, pursuit, movement through open doors, distance-based target loss, last-known-position search, bounded randomized search/wander, and reacquisition, including applying and restoring Frost Field's slowdown effect. Detection Distance is smaller than Lose Target Distance; crossing a doorway does not itself clear pursuit. Enemy attacks consume the shared Player Health damage interface rather than owning separate player-health state. Owns Ranged Enemy targeting, attack timing, and line-of-sight/projectile-occlusion checks, so Chapel of Ash's cover actually blocks shots. Enemy locomotion consumes the shared gameplay navigation/locomotion layer rather than choosing or configuring that layer independently. Owns the shared Active Enemy Registry bookkeeping for persistent active enemy objects; encounter activation consumes that registry rather than maintaining a separate count. Owns the ongoing state of persistent enemy objects whether they are actively pursuing, searching, or later reacquired. It also owns the application of forced enemy displacement requested by abilities such as Force Wave, including returning affected enemies to the appropriate pursuit/search movement state afterward. | Makes enemies left alive remain a visible, persistent consequence while allowing readable distance-based escape and search behavior, and keeps enemy behavior dependent on shared health/navigation interfaces instead of duplicating them. |
| Dungeon Encounter Agent | Authors placements, triggers, door durability, and final-room pressure, including the mixed Melee/Ranged compositions in Chapel of Ash and the Final Room. Owns encounter-admission policy and consumes the shared Active Enemy Registry before activating new enemies. When persistent enemies and a requested new encounter would together exceed fifteen active enemies, this agent delays or reduces the new encounter's enemies first rather than removing existing pursuers. | Controls when the player can lure, fight, flee, or become trapped, and enforces the encounter-admission rule without owning or duplicating the registry's persistent enemy bookkeeping. |
| Unity Validation Agent | Reviews changes and creates Play Mode checks for cleanup, references, and edge cases, including Bone Archive lane pathing, Chapel of Ash occlusion, Lower Vault enemy-cap priority, target-loss hysteresis/search and reacquisition, cursor-targeted door range and cursor-drift behavior, isometric sprite sorting, and alignment between Tilemap visuals and gameplay geometry. | Prevents permanent slowdown, stuck enemies, incorrect pursuit/search transitions, inaccessible door interaction behavior, incorrect door states, and visual/gameplay desynchronization. |

### Development Agent Ownership Invariants

The following ownership boundaries are required development-process constraints and must be preserved by planning, reconciliation, implementation, and validation agents:

- **Feature Planning Agent** may decompose approved work and identify dependencies, but it does not implement gameplay or create new design.
- **Wizard Combat Agent** owns player movement/resources and spell initiation. It requests enemy effects through enemy-owned interfaces and does not directly manipulate enemy locomotion, status restoration, or forced-displacement state.
- **Enemy Pursuit Agent** owns enemy pursuit/search state, enemy locomotion behavior, enemy attack behavior, Frost slowdown application/restoration, forced displacement, and shared Active Enemy Registry bookkeeping. Enemy attacks consume the shared Player Health damage interface, enemy locomotion consumes the shared gameplay navigation/locomotion layer, and encounter activation consumes the registry rather than maintaining a separate count. Pursuit and attack behavior consume doorway walkability from the shared navigation layer rather than directly changing NavMesh or door passability.
- **Door and Interaction Agent** owns door targeting, the latched opening interaction, shared doorway-crossing state, and semantic door lifecycle state. Other systems consume doorway-crossing state rather than implementing their own crossing detector. Door state changes are published through the shared navigation/locomotion passability interface; Door and Interaction does not own the navigation technology that translates those states into enemy walkability.
- **Door/navigation integration prerequisite:** the navigation-owned shared passability interface must exist before door-state publication through that interface is dispatch-ready. Door lifecycle work that does not require navigation may be decomposed and implemented earlier, but if passability publication remains bundled inside one executable door-lifecycle item, that item depends on the gameplay navigation/locomotion owner. An exclusive-resource lock is not a substitute for this behavioral dependency.
- **Dungeon Encounter Agent** owns encounter content/activation policy and consumes the shared Active Enemy Registry when admitting new enemies; it does not replace or remove existing persistent pursuers to satisfy the cap.
- **Unity Validation Agent** verifies integrated behavior and ownership boundaries but does not redefine runtime ownership or silently implement missing gameplay responsibilities.
- **Player Experience Success Criteria are required validation obligations, not advisory prose.** Each criterion in Section 3 must be represented as a validation requirement on the work item or items that own the underlying behavior. They do not require separate gameplay features when the behavior is already owned.
- An agent must not bypass another agent's owned runtime interface merely because both systems interact. Shared-write conflicts are sequencing/locking concerns, not proof of a dependency unless one task actually requires behavior another task must create first.

### Agent-Assisted Development Workflow

1. The developer approves one or more feature briefs describing what the player should see and do.
2. The Feature Planning Agent divides each feature into tasks, identifies dependencies, selects the required files, and removes unapproved additions.
3. The orchestration pipeline may assign independent tasks to multiple agents at the same time. For example, the Wizard Combat Agent can implement a spell while the Enemy Pursuit Agent works on enemy movement and the Dungeon Encounter Agent prepares an encounter layout.
4. Tasks that depend on unfinished work, or that require changes to the same scripts, scenes, or prefabs, are completed sequentially. Agents do not modify the same Unity assets concurrently.
5. Each implementation is reviewed by the Unity Validation Agent. The developer then tests the feature in Play Mode and merges the accepted change into the main project.

### Shared Context and Coordination Rules

- **Minimal-context dispatch is a required pipeline constraint:** agents receive only the approved feature brief, its acceptance criteria, the relevant GDD rules, and the files plus scene/prefab information required for the active task. Unrelated project files or broad project context are not included unless the task genuinely requires them.
- Independent agents work in isolated branches or workspaces so their changes can be reviewed before integration.
- Each task produces changed files, an implementation summary, known risks, and a Play Mode test checklist.
- Source control commits serve as the handoff between implementation, validation, and integration.
- Agents may report a risk or recommend a scope cut, but they cannot redesign the game or add features without developer approval.
- The human developer remains responsible for architecture, merging changes, inspecting Unity scenes and prefabs, playtesting, balance, and final integration.

### Example Game-Specific Agent Task

While the Door and Interaction Agent implements the five-second door-opening and locking behavior, the Enemy Pursuit Agent can independently implement melee enemies following the wizard through open doors. At the same time, the Dungeon Encounter Agent can define the enemy placement for the first encounter space.

After those tasks are complete, the Unity Validation Agent checks that enemies can cross an open doorway without automatically losing the player, that distance-based target loss leads through last-known-position search before target clearing, that movement or damage interrupts opening while cursor drift after selection does not, and that the door can only be locked after the wizard crosses it. The developer then combines and tests the features inside Unity.

## 5. Technical Strategy

No Safe Circle will be developed by one developer in Unity using C#. A raw Python orchestration pipeline using Claude Code agents will coordinate specialized development agents that assist with planning, implementation, review, debugging, and test design. Independent tasks may run at the same time, but tasks that modify the same scripts, scenes, or prefabs will be completed sequentially.

Section 4 defines the six development-agent roles and their effects on the game. This section explains how those agents will be coordinated, constrained, budgeted, and validated during development.

The finished Windows game will not use generative AI at runtime. Enemy behavior, spell effects, doors, damage, and pursuit will run locally through standard Unity systems. The game will require no external AI service, API key, token usage, or network connection after it is built. Development-time generative tools may be used to create isometric tiles, props, and directional sprites, but once imported they behave as ordinary Unity assets.

The developer approves feature briefs, resolves architecture decisions, inspects scenes and prefabs, tests game feel, balances encounters, merges changes, and decides which stretch features are accepted.

### Agent Coordination

The orchestration pipeline may run independent tasks in parallel. For example, the Wizard Combat Agent may implement Fireball and Force Wave while the Enemy Pursuit Agent independently implements melee chasing and Ranged Enemy targeting, and the Dungeon Encounter Agent plans an encounter layout. The **Development Agent Ownership Invariants** in Section 4 are mandatory pipeline constraints, not advisory prose; planning and reconciliation must preserve them as explicit process requirements and must not collapse cross-system ownership merely to simplify a task graph.

Agents will work in isolated branches or workspaces. Two agents will not modify the same gameplay files or Unity assets at the same time. Each completed task will produce:

- Changed files
- An implementation summary
- Known risks or limitations
- A Play Mode test checklist
- A source-control commit for review

Source control will serve as the handoff between implementation, validation, and final integration.

### 2.5D Isometric Visual and World Representation

- The project targets a **hybrid isometric architecture**. Unity **2D Tilemap Editor** (`com.unity.2d.tilemap`) is the approved authoring package for Isometric Tilemaps used for floors, walls, and repeatable architecture. **SpriteRenderer prefabs** are used for doors, props, obstacles, the wizard, enemies, and other independently sorted or interactive objects.
- A generated or hand-authored visual tile does **not** automatically define gameplay behavior. The simulation layer separately defines collision, door interactions, walkability, trigger zones, and navigation.
- The visible isometric layer and the gameplay/navigation layer should remain decoupled wherever practical so environment art can be regenerated or replaced without rewriting room logic.
- A shared **gameplay navigation/locomotion layer** owns the walkable movement representation and the navigation-facing configuration used by runtime movers. It also owns the navigation-side implementation of the shared door-passability interface: semantic door state is supplied by Door and Interaction, while this layer translates sealed/open/locked/broken state into enemy walkability. Enemy pursuit/search, melee/ranged behavior, status effects, and forced displacement consume this layer instead of each selecting or configuring navigation technology or doorway passability independently.
- The approved enemy-navigation implementation is **Unity AI Navigation** (`com.unity.ai.navigation`) using NavMesh-based runtime movement. A minimal working navigation/locomotion layer and the approved package configuration must exist before locomotion-dependent enemy implementation is dispatched, but room-specific visual authoring does not need to be complete first.
- The reusable visual world foundation (Tilemap/SpriteRenderer conventions and visual/gameplay separation) is distinct from authoring the five named room layouts and encounters. Five-room visual/content authoring consumes this foundation once it exists; encounter placement/content consumes the authored room spaces and the encounter-admission/cap foundation. These are real prerequisite relationships even when the downstream content features remain deferred for future decomposition.
- The camera is fixed in an isometric presentation; the player does not rotate the world view freely.
- Mouse-directed click/hold movement is projected onto the gameplay plane, preserving smooth movement similar to early isometric action/RPG controls rather than forcing tile-by-tile stepping.

### Runtime Implementation

- The primary environment visual layer will use Unity **Isometric Tilemaps** through the approved Unity 2D Tilemap Editor package (`com.unity.2d.tilemap`), preferably Isometric Z as Y where useful, for floors, walls, and repeatable architectural tiles. World-space **SpriteRenderer** prefabs will be used for sealed doors, tall props, obstacles, the wizard, enemies, and other independently sorted or interactive objects. Character presentation is therefore part of the reusable visual-world foundation rather than a separate rendering architecture.
- The gameplay layer remains separate from the visible art layer. Walkability, collision, trigger zones, doorway logic, and other simulation rules are defined independently from the Tilemap art so generated or swapped visual assets do not automatically change gameplay behavior.
- Player movement uses mouse-directed click/hold navigation over the gameplay plane. The cursor is also the primary targeting reference for spells and interactions, aligning movement and combat with the isometric presentation. Sealed doors require cursor targeting plus arm's-reach proximity to begin interaction; once the five-second hold has begun, the selected door remains latched and cursor movement off the door does not cancel the attempt.
- A shared gameplay navigation/locomotion layer provides the walkable movement representation and navigation-facing configuration consumed by enemy movement. The approved implementation uses Unity AI Navigation (`com.unity.ai.navigation`) and NavMesh-based runtime movement; enemy detection/pursuit/search logic does not choose or configure a different navigation technology independently. The same layer exposes the navigation side of the shared door-passability interface and translates Door and Interaction's semantic sealed/open/locked/broken state into enemy walkability. Once that shared navigation layer exists, finite-state components control pursuit, attacks, target loss, search, and reacquisition across the floor's spaces. Enemies acquire the player inside Detection Distance and use a larger Lose Target Distance to end exact pursuit. Exceeding Lose Target Distance transitions the enemy to the player's last known position, followed by a short bounded randomized search/wander if the player is not immediately reacquired; doorway crossing alone does not clear pursuit. Exact distance thresholds, search duration, random search weighting, and the underlying Unity mechanism used to update doorway passability are implementation/playtesting details beneath the approved shared contracts. Ranged Enemy attacks include a line-of-sight/occlusion check, and Bone Archive's lane widths are validated against enemy movement/navigation requirements so both rooms' stated tactical geometry holds in practice.
- Enemy movement is the authoritative owner of enemy locomotion and forced displacement. Player abilities may request changes to enemy motion but do not directly manipulate enemy position or navigation state. Force Wave determines which enemies are affected and the radial knockback to request; the enemy movement system applies that displacement, preserves valid movement/navigation state, and resumes the appropriate pursuit/search state afterward. Temporary movement modifiers such as Frost Field slowdown are applied through the enemy status-effect system and restored when the effect ends. The pursuit/search state contract must therefore exist before status-effect/displacement work is treated as independently dispatchable; status/displacement consumes that contract when handing control back to normal enemy behavior.
- All five encounter spaces exist inside one continuous Unity scene or continuous floor representation. Enemy objects, enemy health, pursuit state, active-enemy bookkeeping, and door state persist naturally as the player advances between spaces; no scene-load or cross-scene state-transfer system is required.
- A reusable status-effect/displacement component will apply Frost Field slowdown, apply enemy-owned forced displacement requests, and restore each enemy to the appropriate pursuit/search movement state afterward, per the Wizard Combat Agent / Enemy Pursuit Agent ownership split defined in Section 4. It consumes the pursuit/search state contract rather than defining a second enemy-state machine.
- A reusable door component will control opening, interruption, shared doorway-crossing state, closing, locking, damage, and breaking. It records when the wizard crosses to the forward side of an opened door and exposes that state to locking and final-victory logic; those consumers do not implement separate crossing detection. Once a door is locked by the player or broken by enemies, it does not return to an earlier state.
- A shared **Floor Run/Restart Orchestrator** coordinates a new floor attempt when player health reaches zero. It invokes reset entry points owned by each run-persistent system rather than directly mutating their internals. Player resources/position, enemy health and pursuit/search state, Active Enemy Registry bookkeeping, door lifecycle/crossing/durability state, and encounter activation/admission state must all participate once those systems exist. Early staged restart implementation is valid only as an incremental step; the persistent-systems closure remains required until all implemented run-persistent owners are connected to the orchestrator.
- Mana will regenerate through a local gameplay system after the defined post-cast delay.
- A shared Active Enemy Registry maintains the current persistent active-enemy set, active count, and remaining capacity. Enemy activation/defeat update that registry; target loss or room transitions do not unregister a surviving enemy. The Dungeon Encounter Agent queries the registry before activating new encounter enemies and delays or reduces new activation first when the result would exceed fifteen; existing persistent enemies are never removed to create capacity.
- Development-time art acquisition may use approved tools that can generate isometric tiles, props, and directional sprites. Those outputs are imported into Unity as normal assets; they do not imply automatic prefab creation, collision setup, sorting configuration, or gameplay integration.

### Token Budget

The project will use a maximum planning budget of 1.5 million combined input and output tokens across approximately thirty to forty development tasks. This is a spending ceiling rather than a required amount.

Most focused tasks will be limited to approximately 15,000–30,000 tokens. Larger context will be reserved for integration, debugging, and reviewing systems that interact with several Unity components.

| Budget category | Tokens |
|---|---|
| Feature planning and task preparation | 150,000 |
| Wizard combat and spells | 300,000 |
| Doors and enemy pursuit | 400,000 |
| Dungeon encounters and integration | 250,000 |
| Review, debugging, and validation | 400,000 |
| Total ceiling | 1,500,000 |

**Failed-task retry policy is a required pipeline constraint:** If a task fails, its scope and context will be reduced before it is attempted again. The entire project will not be repeatedly submitted to an agent for a single bug.

### Approved Unity Packages and Windows Build Configuration

- **Unity 2D Tilemap Editor** (`com.unity.2d.tilemap`) is approved and required for the intended Isometric Tilemap authoring workflow. If it is absent from `Packages/manifest.json`, adding/configuring it is concrete project-configuration work, not deferred design.
- **Unity AI Navigation** (`com.unity.ai.navigation`) is the approved enemy-navigation implementation. If it is absent from `Packages/manifest.json`, adding/configuring it is a prerequisite for the gameplay navigation/locomotion layer and locomotion-dependent enemy work.
- The required delivery target is a **Windows Standalone build**. The canonical gameplay scene must be registered in Unity Build Settings before the Windows delivery requirement can be considered complete. A committed `EditorBuildSettings.asset` with no registered gameplay scene is confirmed incomplete build configuration and must remain represented as open configuration work.
- Package-manifest and ProjectSettings changes authorized by these approved requirements may be implemented by an agent, but the developer must inspect the resulting package state, scene registration, and Windows build configuration before merge.

### API and Tool Constraints

- Generative AI tools are used only during development. Approved development-time asset tools may be used to generate isometric tiles, props, and directional sprite art, but they are not runtime dependencies.
- API credentials will remain outside the Unity project and source control.
- Minimal-context dispatch is mandatory: agents receive only the approved feature brief, its acceptance criteria, relevant GDD rules, and files plus scene/prefab information required for the active task. Unrelated repository context is withheld unless the active task requires it.
- Agents cannot add mechanics, redesign the game, or expand the scope without developer approval.
- Generated C# must compile before the task moves to validation.
- Unity scenes, prefab references, animations, and Inspector assignments require human inspection.
- Agent-generated work is not merged until its Play Mode checklist has been tested.
- Parallel work is limited to features that do not modify the same files or depend on unfinished systems.

### Six-Week Development Plan

| Window | Planned work |
|---|---|
| Weeks 1–2 | Wizard movement, health, mana regeneration, three spells, melee enemy, death, and restart |
| Weeks 3–4 | Door interactions, door-breaking pressure, room-to-room pursuit, ranged enemy, and 2.5D isometric dungeon floor construction |
| Weeks 5–6 | Final escape, visual and audio feedback, balancing, performance testing, bug fixes, build, and presentation |

Stretch features will be removed first if the schedule slips. Advanced door visuals and one encounter variation may also be reduced. The three spells, two enemy types, door loop, mana regeneration, pursuit, and final escape remain the required game. If required work in Weeks 5–6 (final escape, balancing, or performance passes) overruns, the fallback is to reduce final-room encounter density toward the low end of the stated three-to-eight-enemy range and simplify presentation polish; required systems are not cut.
