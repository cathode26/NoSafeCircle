---
title: "No Safe Circle"
document_type: "Capstone Game Design Document"
status: "Final Draft"
author: "Vincent Liguori"
original_date: "2026-07-21"
revised_date: "2026-08-13"
source_docx: "Docs/GDD/No_Safe_Circle_GDD_Final.docx"
---

# No Safe Circle

**Capstone Game Design Document**

**Working Title | Final Draft | Originally July 21, 2026; revised August 13, 2026 | Vincent Liguori**

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
| Move and Aim | Use mouse-directed movement: click to set a destination or hold to keep steering toward the cursor. The cursor also serves as the aiming and targeting reference for spells and interactions. | Create and preserve escape routes while maintaining the spatial feel of early isometric action/RPG movement. |
| Fireball | Tap for a quick, mobile shot against a single or separated enemy. Hold to charge: costs more mana and restricts movement further, rewarding preparation by damaging multiple clustered enemies. | Rewards distance and preparation; a charge's area advantage matters against groups, not against one target. |
| Frost Field | Place a temporary area that heavily slows enemies. | Divides crowds and protects routes. |
| Force Wave | Use a short-range radial knockback with a long cooldown. | Creates emergency space. |
| Open Sealed Door | Hold for five seconds; movement or damage cancels. | Makes each exit a positioning challenge. |
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
- Mana: Mana regenerates slowly after a brief post-cast delay. Waiting restores power while locked doors continue losing durability.
- Movement: Circling or retreating creates temporary separation from pursuers, but Melee Enemies gradually close the distance over time; movement alone cannot preserve a completely safe distance indefinitely in later encounters. Sustaining real separation requires turning routes, obstacles, Frost Field, Force Wave, or reducing the threat directly.
- Force Wave: A visible long cooldown shows when the emergency escape tool is unavailable.
- Door feedback: Banging, shaking, cracks, and a durability indicator show when a breach is near.
- Setbacks: Door-opening attempts reset when movement or damage interrupts them.

### Win and Loss Conditions

**Win:** Open the final door and escape the dungeon.

**Loss:** Reach zero health. The floor then restarts from the beginning. This is an intentional, single-attempt structure — reaching zero health at any point restarts the entire floor by design, not as a placeholder.

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

### Door and Pursuit Rules

- Enemies move between rooms through open doors; crossing a doorway does not clear pursuit.
- A sealed door requires five uninterrupted seconds. Moving away or taking damage cancels the attempt.
- After crossing, the player can lock the door. Enemies that saw the escape begin attacking it. Once locked, a door cannot be reopened, unlocked, or crossed again by the player — the floor is a forward-only escape sequence.
- If the player waits too long, the locked door breaks and the surviving group enters the current room. A broken door remains open and cannot be closed or relocked for the remainder of the run. The player cannot travel backward through an earlier doorway, including after its locked door has been broken; enemies may pass forward through the broken doorway, but it is not a return path for the player.
- Surviving enemies carry forward and combine with later encounters as the same persistent enemy objects, not new spawns, and the game never permits more than fifteen active enemies at once. When persistent pursuers and a new encounter would together exceed that limit — most notably in Lower Vault, where a rear breach can coincide with the room's own encounter — activation of the new encounter's additional enemies is delayed or reduced first; enemies already pursuing the player are never removed to make room.

### Required Scope, Exclusions, and Stretch Goals

**Required:** one wizard, one handcrafted 2.5D isometric floor, five spaces, three spells, two enemies, mana regeneration, sealed doors, pursuit across rooms, death and restart, essential feedback, and a Windows build.

**Excluded:** multiplayer, classes, equipment, loot, skill trees, quests, vendors, procedural generation, persistent progression, multiple floors, bespoke 3D character models or rigs, free-rotation 3D camera presentation, and generative AI during play.

**Stretch goals:** Spectral Decoy, a third enemy, Fireball-charge reactions, an awareness indicator, Frost Field slowing a breach, advanced door damage, and one additional room.

### Environment Presentation and Authoring Direction

- The game uses a fixed 2.5D isometric presentation inspired by Diablo 1 and Ultima Online.
- The primary environment visual layer uses **Unity Isometric Tilemaps** for floors, walls, and repeatable architectural tiles.
- Taller props, interactive doors, obstacles, decorative set pieces, and independently sorted objects may use **world-space SpriteRenderers and prefabs** instead of being painted directly into a Tilemap.
- The visible isometric art layer is kept separate from the underlying gameplay representation so art can be revised without redefining core gameplay rules.
- The gameplay layer still owns walkability, collision, trigger volumes, door state, pursuit logic, and other simulation behavior.

### Player Experience Success Criteria

- A first-time player understands that reaching a door is not enough; five safe seconds are required.
- The player understands that enemies left alive remain a threat: leaving them alive means locking a door while they attack it, and later encountering them if that door breaks through.
- Encounters use three to eight enemies and never exceed fifteen active enemies.
- Failure is readable: poor positioning, low mana, using Force Wave without an immediate threat and leaving it unavailable when critical space is needed, or waiting too long.

### Peer and Agent Review Revision

Peer feedback identified that the earlier draft did not explain how the spells and room layouts produced different tactical decisions. A targeted multi-agent review then tested whether those decisions could collapse into a dominant strategy. This revision clarifies Fireball's tap-versus-charge tradeoff, Frost Field's resource commitment, Force Wave's mid-room-versus-door decision, mixed enemy compositions, persistent-pursuer priority, and room-specific implementation checks without adding mechanics or expanding the required scope.

## 4. AI Architecture

Development agents help plan, implement, review, and test No Safe Circle; they do not run in the finished game. Each agent owns a visible game feature, receives concrete acceptance criteria, and produces a Unity test or implementation result.

### Development Agent Roles

| Agent | Plain-English role | Effect on this game |
|---|---|---|
| Feature Planning Agent | Turns one approved feature into acceptance criteria and a file list. | Keeps prompts specific and prevents scope growth. |
| Wizard Combat Agent | Implements player movement, Fireball, Frost Field's casting, mana cost, and feedback, Force Wave, health, mana, cooldowns, and recovery. Frost Field's actual slowdown effect is applied and restored by the Enemy Pursuit Agent, which owns enemy movement and all Ranged Enemy attack behavior; this agent only triggers the Frost Field effect and does not implement Ranged Enemy targeting or attacks. | Creates the tools used to slow, attack, escape, and recover, without editing enemy-movement or enemy-attack code directly. |
| Door and Interaction Agent | Implements opening, interruption, crossing, closing, locking, damage, and breaking. | Makes room exits risky and safety temporary. |
| Enemy Pursuit Agent | Implements detection, melee and ranged attacks, pursuit, and movement through open doors, including applying and restoring Frost Field's slowdown effect. Owns Ranged Enemy targeting, attack timing, and line-of-sight/projectile-occlusion checks, so Chapel of Ash's cover actually blocks shots. Validates NavMesh agent radius and lane behavior so Bone Archive's chokepoints hold. Owns the ongoing state of enemies already pursuing the player, including those carried forward from earlier rooms. | Makes enemies left alive remain a visible, persistent consequence, and makes Chapel of Ash's cover and Bone Archive's lanes function as designed. |
| Dungeon Encounter Agent | Authors placements, triggers, door durability, and final-room pressure, including the mixed Melee/Ranged compositions in Chapel of Ash and the Final Room. Owns encounter activation and enforcement of the fifteen-active-enemy ceiling: when persistent pursuers and a new encounter would together exceed it, this agent delays or reduces the new encounter's enemies first rather than displacing enemies already pursuing the player. | Controls when the player can lure, fight, flee, or become trapped, and ensures carried-forward enemies never push the floor's total active count beyond the stated limit. |
| Unity Validation Agent | Reviews changes and creates Play Mode checks for cleanup, references, and edge cases, including Bone Archive lane pathing, Chapel of Ash occlusion, Lower Vault enemy-cap priority, isometric sprite sorting, and alignment between Tilemap visuals and gameplay geometry. | Prevents permanent slowdown, stuck enemies, incorrect door states, and visual/gameplay desynchronization. |

### Agent-Assisted Development Workflow

1. The developer approves one or more feature briefs describing what the player should see and do.
2. The Feature Planning Agent divides each feature into tasks, identifies dependencies, selects the required files, and removes unapproved additions.
3. The orchestration pipeline may assign independent tasks to multiple agents at the same time. For example, the Wizard Combat Agent can implement a spell while the Enemy Pursuit Agent works on enemy movement and the Dungeon Encounter Agent prepares an encounter layout.
4. Tasks that depend on unfinished work, or that require changes to the same scripts, scenes, or prefabs, are completed sequentially. Agents do not modify the same Unity assets concurrently.
5. Each implementation is reviewed by the Unity Validation Agent. The developer then tests the feature in Play Mode and merges the accepted change into the main project.

### Shared Context and Coordination Rules

- Agents receive only the approved feature brief, acceptance criteria, relevant files, and necessary scene or prefab information.
- Independent agents work in isolated branches or workspaces so their changes can be reviewed before integration.
- Each task produces changed files, an implementation summary, known risks, and a Play Mode test checklist.
- Source control commits serve as the handoff between implementation, validation, and integration.
- Agents may report a risk or recommend a scope cut, but they cannot redesign the game or add features without developer approval.
- The human developer remains responsible for architecture, merging changes, inspecting Unity scenes and prefabs, playtesting, balance, and final integration.

### Example Game-Specific Agent Task

While the Door and Interaction Agent implements the five-second door-opening and locking behavior, the Enemy Pursuit Agent can independently implement melee enemies following the wizard through open doors. At the same time, the Dungeon Encounter Agent can define the enemy placement for the first encounter space.

After those tasks are complete, the Unity Validation Agent checks that enemies can cross an open doorway, that movement or damage interrupts opening, and that the door can only be locked after the wizard crosses it. The developer then combines and tests the features inside Unity.

## 5. Technical Strategy

No Safe Circle will be developed by one developer in Unity using C#. A raw Python orchestration pipeline using Claude Code agents will coordinate specialized development agents that assist with planning, implementation, review, debugging, and test design. Independent tasks may run at the same time, but tasks that modify the same scripts, scenes, or prefabs will be completed sequentially.

Section 4 defines the six development-agent roles and their effects on the game. This section explains how those agents will be coordinated, constrained, budgeted, and validated during development.

The finished Windows game will not use generative AI at runtime. Enemy behavior, spell effects, doors, damage, and pursuit will run locally through standard Unity systems. The game will require no external AI service, API key, token usage, or network connection after it is built. Development-time generative tools may be used to create isometric tiles, props, and directional sprites, but once imported they behave as ordinary Unity assets.

The developer approves feature briefs, resolves architecture decisions, inspects scenes and prefabs, tests game feel, balances encounters, merges changes, and decides which stretch features are accepted.

### Agent Coordination

The orchestration pipeline may run independent tasks in parallel. For example, the Wizard Combat Agent may implement Fireball and Force Wave while the Enemy Pursuit Agent independently implements melee chasing and Ranged Enemy targeting, and the Dungeon Encounter Agent plans an encounter layout. Agent ownership boundaries, including Frost Field's cast-versus-slowdown split between the Wizard Combat Agent and the Enemy Pursuit Agent, are defined in Section 4.

Agents will work in isolated branches or workspaces. Two agents will not modify the same gameplay files or Unity assets at the same time. Each completed task will produce:

- Changed files
- An implementation summary
- Known risks or limitations
- A Play Mode test checklist
- A source-control commit for review

Source control will serve as the handoff between implementation, validation, and final integration.

### 2.5D Isometric Visual and World Representation

- The project targets a **hybrid isometric architecture**: Unity **Isometric Tilemaps** are the preferred environment-authoring method for floors, walls, and repeatable architecture, while **SpriteRenderer prefabs** are preferred for doors, props, obstacles, characters, and other independently sorted or interactive objects.
- A generated or hand-authored visual tile does **not** automatically define gameplay behavior. The simulation layer separately defines collision, door interactions, walkability, trigger zones, and navigation.
- The visible isometric layer and the gameplay/navigation layer should remain decoupled wherever practical so environment art can be regenerated or replaced without rewriting room logic.
- The camera is fixed in an isometric presentation; the player does not rotate the world view freely.
- Mouse-directed click/hold movement is projected onto the gameplay plane, preserving smooth movement similar to early isometric action/RPG controls rather than forcing tile-by-tile stepping.

### Runtime Implementation

- The primary environment visual layer will use Unity **Isometric Tilemaps** (preferably Isometric Z as Y where useful) for floors, walls, and repeatable architectural tiles. World-space **SpriteRenderer** prefabs will be used for sealed doors, tall props, obstacles, characters, and other independently sorted or interactive objects.
- The gameplay layer remains separate from the visible art layer. Walkability, collision, trigger zones, doorway logic, and other simulation rules are defined independently from the Tilemap art so generated or swapped visual assets do not automatically change gameplay behavior.
- Player movement uses mouse-directed click/hold navigation over the gameplay plane. The cursor is also the primary targeting reference for spells and interactions, aligning movement and combat with the isometric presentation.
- Unity navigation and finite-state components will control enemy movement, pursuit, attacks, and target loss across the floor's spaces. Ranged Enemy attacks include a line-of-sight/occlusion check, and Bone Archive's lane widths are validated against enemy movement/navigation requirements so both rooms' stated tactical geometry holds in practice.
- All five encounter spaces exist inside one continuous Unity scene or continuous floor representation. Enemy objects, enemy health, pursuit state, active-enemy bookkeeping, and door state persist naturally as the player advances between spaces; no scene-load or cross-scene state-transfer system is required.
- A reusable status-effect component will apply Frost Field slowdown and restore each enemy's normal movement behavior afterward, per the Wizard Combat Agent / Enemy Pursuit Agent ownership split defined in Section 4.
- A reusable door component will control opening, interruption, closing, locking, damage, and breaking; once a door is locked by the player or broken by enemies, it does not return to an earlier state.
- Mana will regenerate through a local gameplay system after the defined post-cast delay.
- The game enforces a hard maximum of fifteen active enemies; the Dungeon Encounter Agent enforces this ceiling when activating new encounters, delaying or reducing new-encounter spawns first when persistent pursuers and a new encounter would together exceed it, while the Enemy Pursuit Agent tracks the state of enemies already pursuing the player.
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

If a task fails, its scope and context will be reduced before it is attempted again. The entire project will not be repeatedly submitted to an agent for a single bug.

### API and Tool Constraints

- Generative AI tools are used only during development. Approved development-time asset tools may be used to generate isometric tiles, props, and directional sprite art, but they are not runtime dependencies.
- API credentials will remain outside the Unity project and source control.
- Agents receive only the approved feature brief, relevant GDD rules, and files required for the active task.
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
