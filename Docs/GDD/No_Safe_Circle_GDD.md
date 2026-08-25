---
title: "No Safe Circle"
document_type: "Capstone Game Design Document"
status: "Final Draft"
author: "Vincent Liguori"
original_date: "2026-07-21"
revised_date: "2026-08-25"
source_docx: "Docs/GDD/No_Safe_Circle_GDD_Final.docx"
---

# No Safe Circle

**Capstone Game Design Document**

**Working Title | Final Draft | Originally July 21, 2026; revised August 25, 2026 | Vincent Liguori**

> A wizard must create brief moments of safety, open sealed doors under pressure, and escape a dungeon while the monsters left behind continue to pursue.

## 1. Executive Summary

No Safe Circle is a single-player, 2.5D isometric survival action game set on one handcrafted dungeon floor. The presentation is inspired by early isometric action/RPGs such as Diablo 1 and Ultima Online: the camera is fixed, the world is viewed at an angle, and the visible environment is authored as isometric art rather than as a free-rotation 3D space. The player controls a vulnerable wizard who can destroy small groups of monsters with powerful spells but cannot survive being surrounded. The player must control distance, wait for mana to regenerate, and decide when to fight, flee, or risk opening the next sealed door.

Each room ends at a door that takes five uninterrupted seconds to open. Before attempting it, the player must create space by luring enemies away, slowing them with Frost Field, knocking them back with Force Wave, or defeating enough of them to reduce the immediate threat. Enemies can follow the wizard through an open doorway. After crossing, the door automatically closes and locks behind the player; surviving pursuers will pound against it and eventually break through.

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

The player moves through connected rooms toward the final door. In each room, the objective is to click the next sealed door, reach its interaction position, survive five uninterrupted seconds while it opens, cross through it, and let it automatically close and lock behind the wizard before the pursuing monsters arrive.

### Core Gameplay Loop

1. Scout the room, locate the sealed door, and identify a route for luring or slowing enemies.
2. Avoid the group, pull part of it away, or spend mana on a direct fight.
3. Use Frost Field and movement to stretch the chase; charge Fireball when enough distance exists.
4. Use Force Wave if enemies reach the wizard or block the door.
5. Click the sealed door to request movement to its interaction position. When the wizard arrives within interaction range, the five-second opening timer starts automatically. If no interruption occurs, the door opens; cross through it and the door automatically closes and locks, granting its recovery before pursuers break through.

### Player Actions and Systems

| Action | What the player does | Purpose |
|---|---|---|
| Move and Aim | Use mouse-directed movement through the shared Unity Input System/Input Actions layer: click to set a destination or hold to keep steering toward the cursor. Player Movement owns the shared cursor-to-gameplay-plane projection and exposes the resulting world-space pointer target. Movement, cursor-aimed spells, and cursor-targeted interactions consume that shared target; Force Wave is the player-centered exception. | Create and preserve escape routes while maintaining the spatial feel of early isometric action/RPG movement and one consistent pointer projection across gameplay systems. |
| Fireball | Aim with the cursor. Tap for a quick, mobile shot against a single or separated enemy. Hold to charge: costs more mana and restricts movement further, rewarding preparation by damaging multiple clustered enemies. | Rewards distance and preparation; a charge's area advantage matters against groups, not against one target. |
| Frost Field | Place a temporary area at the current cursor world-space target that heavily slows enemies. Frost Field consumes the shared pointer target exposed by Player Movement rather than projecting screen coordinates independently. | Divides crowds and protects routes. |
| Force Wave | Use a player-centered short-range radial knockback with a long cooldown. Each cast costs **25 mana**. Force Wave does not use cursor direction or target selection. | Creates emergency space at a real resource cost. The 25-mana cost is an initial tuning value and may change during later balance work. |
| Open Sealed Door | Click the intended sealed door to request movement to its interaction position. The wizard walks there automatically. When the wizard reaches arm's-reach interaction range, the five-second opening timer begins automatically; no sustained button hold is required. Cursor drift does not matter after selection. Taking damage, moving away, or issuing another command that cancels/replaces the door approach resets the attempt. If uninterrupted for five seconds, the door opens. | Makes each exit a positioning challenge while allowing one click to mean "go to this door and start opening it when I arrive." |
| Close and Lock | After the wizard crosses to the forward side of an opened door, the door automatically closes and locks; no additional input is required. Completing the automatic close-and-lock restores a small, fixed amount of health. Once locked, this door cannot be reopened or crossed again (see Door and Pursuit Rules). | Creates recovery time while pursuers attack it, removes an unnecessary second interaction, and marks forward progress as final. |

### Spell and Enemy Interactions

| Spell | Against Melee Enemies | Against Ranged Enemies |
|---|---|---|
| Charged Fireball | Melee enemies naturally cluster while pursuing the wizard, making them strong area-damage targets. Charging becomes unsafe once they close the distance. | Telegraphed ranged attacks force the player to keep moving, reducing the time available for a full charge. Quick shots are safer but provide less damage and area. |
| Frost Field | Strongest against melee groups because it slows direct pursuit, stretches the formation, and creates an opening to charge Fireball or begin opening a door — though it draws a meaningful share of the shared mana pool and does not guarantee a fully safe charge in every position or against every group. Against a small or loosely spaced group, direct positioning, a partial charge, or tap Fireball can be the better resource decision. | Slows a ranged enemy's repositioning but does not stop its attacks. The player must still move laterally or use room geometry to avoid incoming shots. |
| Force Wave | The primary emergency response when melee enemies surround the wizard or block access to a door. Its long cooldown prevents repeated use. | Its short range makes it a poor answer to distant ranged pressure. Reaching a ranged enemy to use it may expose the wizard to the melee group. |

The three spells solve different problems: Frost Field controls pursuit, Force Wave repairs an immediate positioning mistake, and Charged Fireball converts a previously created opening into damage. No single spell reliably answers both enemy types by itself. Force Wave's cooldown is tuned so an encounter space typically allows only about one meaningful use: spending it to escape a mid-room surround may leave none available for that room's door attempt, and saving it for the door means resolving mid-room danger without it. This is an intentional resource decision, not proof that either use was wrong.

### Resources, Feedback, and Failure

- Health: The wizard survives a few isolated hits but dies quickly when trapped. Health does not regenerate during a room, and does not reset between rooms — it carries across the whole run. Successfully locking a door after crossing restores a small, fixed amount of health before the next room begins; this recovery is partial, so accumulated damage still matters across all five rooms. Exact recovery values will be set during playtesting.
- Player Health ownership: The shared Player Health system is the single owner of the wizard's current health. It exposes owner-controlled damage and restore interfaces plus an observable zero-health/death transition consumed by the Floor Run/Restart Orchestrator. Door locking requests the fixed recovery through the Player Health restore interface; restoration is clamped to maximum health, and Door and Interaction never writes player-health state directly. The restart orchestrator consumes the zero-health transition rather than polling or mutating Player Health internals.
- Health feedback: The wizard's current health is continuously visible through a simple player-facing health indicator. Because damage persists across rooms, the player must be able to read accumulated damage and remaining survivability throughout the run.
- Mana: Mana regenerates slowly after a brief post-cast delay. Waiting restores power while locked doors continue losing durability. Force Wave currently costs **25 mana per cast**; this is an initial balance value that may be tuned later after the game is playable.
- Player Mana ownership: The shared Player Mana system is the single owner of current mana and the post-cast regeneration-delay state. Spells spend mana through its owner-controlled spend interface. Player Mana does not own spell-local cooldown, charge, cast, placement, or active-effect state merely because those spells consume mana.
- Movement: Circling or retreating creates temporary separation from pursuers, but Melee Enemies gradually close the distance over time; movement alone cannot preserve a completely safe distance indefinitely in later encounters. Sustaining real separation requires turning routes, obstacles, Frost Field, Force Wave, or reducing the threat directly.
- Player Movement ownership: The player movement system owns player position, locomotion, movement-restriction state, and the shared cursor-to-gameplay-plane projection used to produce a world-space pointer target. Runtime input is routed through the project's Unity Input System/Input Actions layer rather than independent direct hardware polling in gameplay systems. Player Movement, cursor-aimed Wizard Combat abilities, and Door/Interaction consume the shared pointer target instead of independently projecting screen coordinates. Charged Fireball requests and releases its charging movement restriction through an owner-controlled Player Movement interface; Fireball does not directly mutate movement internals.
- Frost Field targeting and feedback: Frost Field is placed at the current shared world-space pointer target exposed by Player Movement. Frost Field does not independently project screen coordinates. The cast and active field provide player-facing feedback that makes the targeted placement and active effect readable while it is being placed/used. The exact visual or audio treatment is an implementation choice.
- Force Wave: Each cast spends **25 mana** through Player Mana and also starts its visible long cooldown. Twenty-five mana is the initial implementation/balance value; later playtesting may change the number, but Force Wave remains a mana-consuming spell unless the GDD is revised.
- Spell-local state ownership: Fireball owns its tap/charge/cast state, Frost Field owns its Wizard-Combat-side cast/placement/active-field state, and Force Wave owns its cooldown state. Enemy-side Frost slowdown application/restoration remains owned by Enemy Pursuit/status-effect logic. Each owner exposes a reset entry point for any owned state that can still be active when a floor restart occurs.
- Door feedback: Banging, shaking, cracks, and a durability indicator show when a breach is near.
- Setbacks: Once the wizard has reached the selected door and the five-second timer has begun, taking damage, moving away, or issuing another command that cancels/replaces the door interaction resets progress. Releasing the mouse button does not matter because the door interaction does not require a sustained hold. Cursor movement away from the selected door after the initial click does not reset progress.

### Win and Loss Conditions

**Win:** Open the final door and escape the dungeon. Victory occurs when the shared doorway-crossing state confirms that the wizard has crossed to the forward side of the final door; the win condition does not implement a separate crossing detector. Once victory is confirmed, normal gameplay input — player movement, door interaction, Fireball, Frost Field, and Force Wave — stops and a simple player-facing **You Escaped** overlay is displayed. No additional post-victory progression, menu flow, or meta-progression is required for the capstone.

**Victory/input-shutdown ownership:** A reusable Game Flow/Victory capability owns the transition into the won state, display of the **You Escaped** overlay, and coordination of gameplay shutdown. Player Movement, Door/Interaction, Fireball, Frost Field, and Force Wave each expose an owner-controlled gameplay-enable/suspend interface that can immediately stop or cancel their current input-driven activity, reject new gameplay commands while suspended, and be re-enabled by an authorized reset/test flow. The victory capability consumes those interfaces rather than mutating another system's internal state. Disabling an Input Actions map may be part of the implementation, but the runtime contract must also stop already-active movement, door-opening, charging/casting, or other input-driven activity rather than merely preventing the next button press.

**Loss:** Reach zero health. The floor then restarts from the beginning. This is an intentional, single-attempt structure — reaching zero health at any point restarts the entire floor by design, not as a placeholder. Restart resets all run-persistent gameplay state to the floor's initial state, including Player Health, Player Mana and its regeneration-delay state, player position/movement state, Fireball charge/cast state, Frost Field casting/active-field state, Force Wave cooldown state, persistent enemy objects and enemy health, pursuit/search/status/attack state, Active Enemy Registry bookkeeping, door lifecycle/crossing/durability state, and encounter activation/admission state. Each persistent enemy is returned to the authored encounter/spawn region associated with its original room and starts again in its initial AI state; the exact coordinate within that authored region may vary, but no target, last-known-position, search, attack, status-effect, or displacement state carries over from the failed run.

**Floor-run restart ownership:** Player Health's observable zero-health/death transition triggers the shared Floor Run/Restart Orchestrator, which owns starting a fresh floor attempt and coordinating the reset. It does not reach into or duplicate another system's internal state. Every system that owns state that can persist or remain active when restart occurs must expose a reset entry point for the state it owns, and the orchestrator invokes those owned reset interfaces. Required reset participants include Player Health, Player Mana, Player Movement/player position, Fireball, Frost Field's casting-side state, Force Wave, enemy health/defeat state, enemy pursuit/search/attack/status/displacement state, Active Enemy Registry bookkeeping, door lifecycle/crossing/durability state, and encounter activation/admission state. Enemy reset returns each persistent enemy to its original authored encounter/spawn region and initial AI state, with no retained target knowledge from the failed run; exact placement within that authored region is an encounter implementation detail. Early implementation may validate the orchestrator against only the persistent systems that currently exist, but full restart closure remains required work until every implemented state owner participates; adding later rooms or stateful systems must extend the reset participants without redesigning the orchestration contract.

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

### Approved Five-Room Spatial Layout Blockout

> **Design approval provenance:** Human-approved on August 25, 2026 after Progressive Decomposer run `nsc-029-decomp-20260825-034021` identified the missing `Five-Room Spatial Layout Specification` as the smallest design artifact needed to unblock NSC-029. This section promotes that approved blockout into canonical GDD design.

## 1. Purpose and authority boundary

This section defines the human-approved initial blockout-level spatial layout for the five canonical spaces in **No Safe Circle** so NSC-029 can be decomposed into bounded implementation work without asking implementation agents to invent missing level geometry.

This blockout specification is now part of the GDD. If a later GDD revision changes these requirements, the later approved GDD revision is authoritative.

This approved blockout specifies:

- the continuous-floor spatial topology;
- room boundaries and blockout dimensions;
- the forward route through all five named spaces;
- Ruined Entry rubble placement and its broad circling route;
- Bone Archive shelf/furniture placement and lane clearances;
- Chapel of Ash central aisle, side routes, pews, columns, and cover pockets;
- Lower Vault columns/storage and incomplete-loop routes;
- Final Room open layout, limited cover, and one central obstacle;
- each room's exit-door location;
- designation of the Final Room exit as the final door.

This blockout does **not** add or authorize:

- enemy placement, encounter composition, activation, admission, or balance;
- new mechanics, rooms, doors, enemies, spells, progression, lore, or rewards;
- changes to runtime ownership, navigation technology, door state behavior, doorway crossing, or victory behavior;
- production-quality art, lighting, audio, VFX, or decorative polish;
- implementation, Unity scene edits, test execution, readiness, delivery, or completion claims.

## 2. Authoring conventions

### Gameplay coordinates

All blockout dimensions in this specification are expressed in Unity gameplay-plane world coordinates:

- **X** = horizontal/east-west;
- **Z** = forward/north-south;
- **Y** = vertical height.

The floor progresses generally toward positive Z.

### Visual/simulation separation

The existing isometric Tilemap remains a **visual architectural layer**. Gameplay walkability, collision, trigger volumes, door state, and other simulation behavior remain separately authored and authoritative.

Room layout implementation must therefore provide matching visual and gameplay representations rather than using Tilemap cells as gameplay truth.

### Existing isometric visual convention

The current world foundation uses an isometric `Grid` with cell size approximately:

- X = 1.0
- Y = 0.5
- Z = 1.0

The blockout coordinates below use 0.5-unit increments where practical. Implementations may snap visual Tilemap cells to the existing isometric grid while keeping gameplay geometry aligned to the intended world-space footprint.

### Global blockout dimensions

Unless a room section overrides them:

- perimeter wall gameplay thickness: **0.5 world units**;
- perimeter wall blockout height: **2.5 world units**;
- sealed-door clear opening width: **3.0 world units**;
- ordinary primary route target width: **3.5 world units or greater**;
- intentional Bone Archive pinch width: **2.5 world units minimum**;
- no accidental hard-geometry gap may be narrower than **2.5 world units**.

The 2.5-unit Bone Archive minimum is an initial level-design clearance. The navigation implementation must later validate the configured enemy agent radius against these authored lanes, as required by NSC-029 VAL-001. If the configured navigation footprint cannot traverse a 2.5-unit clear lane with the project's required margin, the layout must be revised rather than silently changing navigation ownership or technology.

## 3. Continuous-floor topology

The five rooms exist in one continuous floor, arranged generally south-to-north:

```text
START
  |
  v
[ Ruined Entry ]
       |
      D1
       |
[ Bone Archive ]
       |
      D2
       |
[ Chapel of Ash ]
       |
      D3
       |
[ Lower Vault ]
       |
      D4
       |
[ Final Room ]
       |
   D5 FINAL
       |
     ESCAPE
```

There are no room scene loads and no cross-scene transitions.

Each `D#` is a sealed-door location in the shared boundary between spaces. Once the player crosses a room's exit and the existing door lifecycle closes/locks it, that same doorway is the previous doorway visible from the next room.

## 4. Global room and door coordinates

| Space | X bounds | Z bounds | Nominal size | Exit door |
|---|---:|---:|---:|---|
| Ruined Entry | -10 to +10 | -18 to 0 | 20 Ã— 18 | D1 at **(0, 0)** |
| Bone Archive | -10 to +10 | 0 to 20 | 20 Ã— 20 | D2 at **(+6, 20)** |
| Chapel of Ash | -12 to +12 | 20 to 42 | 24 Ã— 22 | D3 at **(-6, 42)** |
| Lower Vault | -11 to +11 | 42 to 64 | 22 Ã— 22 | D4 at **(+4, 64)** |
| Final Room | -12 to +12 | 64 to 86 | 24 Ã— 22 | D5 FINAL at **(0, 86)** |

Door coordinates are the center of the clear opening in the shared north/south room boundary.

The changing room widths create short wall jogs at shared boundaries. Those jogs are part of the continuous floor and do not create corridors or separate rooms.

## 5. Room 1 â€” Ruined Entry

### Tactical purpose

Ruined Entry remains a mostly open teaching space. It must allow the player to circle a melee threat, preserve a visible escape route, and recognize when enough separation exists to charge Fireball.

### Room shell

- rectangular walkable footprint: X **[-10, +10]**, Z **[-18, 0]**;
- solid west, east, and south perimeter walls;
- north wall contains D1 centered at **X = 0**;
- D1 clear opening width: **3.0**.

### Collapsed-rubble blockout

The primary rubble mass is an east-of-center L-shaped cluster formed from two touching hard-geometry footprints:

- **Rubble A:** X **[+2, +6]**, Z **[-12, -8]**;
- **Rubble B:** X **[+4, +7]**, Z **[-8, -6]**.

The cluster may later be visually broken into multiple rubble sprites/meshes, but its gameplay footprint should preserve the same blockout silhouette unless this artifact is revised.

### Route requirements

- west side of the rubble remains a **broad circling route** with at least **6.0 units** of usable width through its widest teaching section;
- east side remains traversable with at least **2.5 units** of clear space between rubble and perimeter wall;
- no rubble placement creates a dead-end pocket;
- D1 remains reachable from both sides of the rubble cluster;
- the final approach to D1 provides at least a **5 Ã— 5 unit** mostly open staging area south of the door.

## 6. Room 2 â€” Bone Archive

### Tactical purpose

Bone Archive creates narrow shelf lanes and chokepoints. It should reward Frost Field lane control and clustered Fireball opportunities while making poor aisle choices capable of trapping the player.

### Room shell

- rectangular walkable footprint: X **[-10, +10]**, Z **[0, 20]**;
- D1 enters from the south at **(0, 0)**;
- D2 exits north at **(+6, 20)**;
- D1 and D2 clear opening width: **3.0**.

### Shelf banks

Three tall, hard-geometry shelf banks run predominantly north-south:

- **Shelf A:** X **[-6.5, -5.0]**, Z **[4, 16]**;
- **Shelf B:** X **[-1.5, 0.0]**, Z **[3, 14]**;
- **Shelf C:** X **[+3.5, +5.0]**, Z **[6, 17]**.

Shelf blockout height should be at least **2.5 units** so they read as substantial lane-forming architecture and can support later visual replacement.

### Intentional chokepoint

A collapsed archive-furniture protrusion extends from Shelf B into the aisle toward Shelf C:

- **Collapsed Furniture BA-1:** X **[0.0, +1.0]**, Z **[9, 11]**.

This reduces the local clear width between BA-1 and Shelf C to **2.5 units**. No authored hard-geometry gap in Bone Archive may be narrower than this value.

### Route requirements

- the lane between Shelf A and Shelf B remains **3.5 units** clear;
- the normal lane between Shelf B and Shelf C remains **3.5 units** clear except at BA-1;
- the BA-1 pinch is the deliberate minimum-clearance chokepoint;
- a western bypass remains at least **3.0 units** clear;
- an eastern bypass remains at least **3.0 units** clear;
- at least two different navigable routes connect the southern half of the room to the northern half;
- the route to offset D2 at X = +6 requires at least one lane choice rather than a straight centered sprint.

### Navigation-validation intent

NSC-029 VAL-001 must later verify that the configured enemy navigation agent can traverse the 2.5-unit BA-1 pinch and the room's intended lanes. This artifact defines the geometry to validate; it does not select or configure the navigation technology.

## 7. Room 3 â€” Chapel of Ash

### Tactical purpose

Chapel of Ash introduces meaningful line-of-sight breaks against ranged pressure while melee support remains relevant. The central aisle is the fastest route but exposes the player; side routes trade distance for cover.

### Room shell

- rectangular walkable footprint: X **[-12, +12]**, Z **[20, 42]**;
- D2 enters from the south at **(+6, 20)**;
- D3 exits north at **(-6, 42)**;
- clear door opening width: **3.0**.

### Central aisle

The central aisle is the unobstructed strip:

- X **[-2, +2]**;
- Z **[22, 40]**.

Target clear width: **4.0 units**.

### Pews

Four rows of pew blockouts occupy each side of the central aisle.

Left-side pew footprints:

- X **[-8.5, -3]**, Z **[24, 25.5]**;
- X **[-8.5, -3]**, Z **[28, 29.5]**;
- X **[-8.5, -3]**, Z **[32, 33.5]**;
- X **[-8.5, -3]**, Z **[36, 37.5]**.

Right-side pew footprints:

- X **[+3, +8.5]**, Z **[24, 25.5]**;
- X **[+3, +8.5]**, Z **[28, 29.5]**;
- X **[+3, +8.5]**, Z **[32, 33.5]**;
- X **[+3, +8.5]**, Z **[36, 37.5]**.

Pew blockout height: **1.25 units**.

### Columns

Four stone columns reinforce the side-cover pattern:

- **C1:** center **(-8.5, 27)**;
- **C2:** center **(+8.5, 27)**;
- **C3:** center **(-8.5, 35)**;
- **C4:** center **(+8.5, 35)**.

Each column footprint is **1.5 Ã— 1.5 units** with blockout height **2.5 units**.

### Side routes and cover

- the west side route between pew ends/columns and the west wall must preserve at least **2.5 units** clear;
- the east side route must preserve at least **2.5 units** clear;
- the spaces between pew rows create lateral openings back toward the central aisle;
- designated cover pocket **CA-W** is centered approximately at **(-10.5, 31)**;
- designated cover pocket **CA-E** is centered approximately at **(+10.5, 35)**.

At least one of CA-W or CA-E must be geometrically occluded from a representative straight-line ranged attack crossing from the opposite half of the chapel by a real pew or column collider. The later validation may choose a representative ranged test position; this artifact does not define an encounter spawn.

### Route tradeoff

- central-aisle travel is shorter and more direct between D2 and D3;
- using either side route adds lateral travel but provides repeated occluders;
- no cover route becomes a fully safe tunnel isolated from melee approach.

## 8. Room 4 â€” Lower Vault

### Tactical purpose

Lower Vault uses columns and storage piles to create several incomplete loops rather than one safe circuit. The layout must keep the previous doorway relevant so surviving pursuers breaking in behind the player remain a spatial threat.

### Room shell

- rectangular walkable footprint: X **[-11, +11]**, Z **[42, 64]**;
- D3 enters from the south at **(-6, 42)**;
- D4 exits north at **(+4, 64)**;
- clear door opening width: **3.0**.

### Major obstacles

**Central column cluster LV-C1**

- footprint: X **[-1, +1]**, Z **[48, 52]**;
- height: **2.5**.

**West storage pile LV-W1**

- footprint: X **[-7.5, -4]**, Z **[53, 57]**;
- height: **1.5**.

**East storage pile LV-E1**

- footprint: X **[+4, +7.5]**, Z **[47, 50]**;
- height: **1.5**.

**North-west storage bar LV-N1**

- footprint: X **[-7.5, -1]**, Z **[59, 61]**;
- height: **1.5**.

### Incomplete-loop requirements

- obstacles must allow local movement around multiple sides but must not combine into one clean, repeatable perimeter circuit;
- LV-N1 intentionally breaks the easiest north-west loop;
- the east side remains the most direct approach to D4;
- the central cluster forces at least one meaningful left/right route choice;
- the southern half of the room retains an open visual/movement connection back toward D3;
- no obstacle arrangement permanently walls off D3 after the player enters the room;
- at least **3.0 units** of clear space remains on every intended route.

## 9. Room 5 â€” Final Room

### Tactical purpose

Final Room is comparatively open, provides limited cover, and has one central obstacle. The player must create the final uninterrupted opening window through movement and the existing spell kit rather than hiding behind extensive room geometry.

### Room shell

- rectangular walkable footprint: X **[-12, +12]**, Z **[64, 86]**;
- D4 enters from the south at **(+4, 64)**;
- D5 exits north at **(0, 86)**;
- D5 is the **final door**;
- clear door opening width: **3.0**.

### Single central obstacle

**Final Obstacle FR-1**

- footprint: X **[-2.5, +2.5]**, Z **[73.5, 78.5]**;
- blockout height: **2.0 units**.

This is the room's one major hard-cover obstacle.

### Openness requirements

- preserve at least **4.0 units** of clear circulation around each side of FR-1;
- do not add other hard-cover props large enough to create another equivalent obstacle;
- the D4-to-D5 route can pass either side of FR-1;
- the north staging region immediately before D5 remains mostly open;
- limited incidental decoration may eventually exist, but it must not materially change the approved blockout cover topology without a reviewed GDD/design revision.

## 10. Door sequence

| Door | Shared boundary / role | Center | Final? |
|---|---|---:|---|
| D1 | Ruined Entry â†’ Bone Archive | (0, 0) | No |
| D2 | Bone Archive â†’ Chapel of Ash | (+6, 20) | No |
| D3 | Chapel of Ash â†’ Lower Vault | (-6, 42) | No |
| D4 | Lower Vault â†’ Final Room | (+4, 64) | No |
| D5 | Final Room â†’ escape boundary | (0, 86) | **Yes** |

This blockout section defines door placement and final-door identity. Door lifecycle, opening time, automatic close/lock, break-through behavior, crossing state, health restore, and victory consumption remain owned by their existing gameplay systems/GDD contracts.

## 11. Blockout acceptance checklist

- [ ] all five named spaces have explicit gameplay-plane bounds;
- [ ] all five spaces coexist in one continuous floor;
- [ ] D1â€“D5 have explicit locations and D5 is identified as the final door;
- [ ] Ruined Entry has a mostly open layout and broad circling route around rubble;
- [ ] Bone Archive has explicit shelves, alternate lanes, and a 2.5-unit intentional pinch;
- [ ] Chapel of Ash has a 4-unit central aisle, longer side routes, real pew/column occluders, and designated cover pockets;
- [ ] Lower Vault has several obstacle-driven route choices without one safe repeatable circuit and keeps the previous doorway relevant;
- [ ] Final Room is comparatively open and contains exactly one major central obstacle;
- [ ] gameplay geometry remains independent from the visual Tilemap;
- [ ] no enemy placement, encounter composition, runtime redesign, or production-art requirement has been added.

## 12. Validation expectations after implementation

1. **Bone Archive navigation validation**
   - verify the configured enemy navigation agent can traverse the BA-1 2.5-unit pinch and intended aisles;
   - if not, fail the room-layout validation and revise design/configuration through the proper owning work rather than faking passability.

2. **Chapel of Ash occlusion validation**
   - verify at least one designated side cover pocket is truly occluded from a representative ranged line-of-sight/projectile path by authored pew/column gameplay geometry.

3. **Visual/simulation alignment**
   - verify visible Tilemap walls/floors correspond to the separately authored collision/walkability footprint.

4. **Continuous-floor validation**
   - verify all five room shells and D1â€“D5 coexist in the canonical continuous gameplay scene/floor representation without scene loading.

## 13. Revision policy

These dimensions are **human-approved initial blockout targets**. They are not final balance values or final art.

Playtesting may justify later room-layout revisions, but changes to room bounds, major obstacle topology, lane widths, cover topology, or door positions should create a reviewed GDD/design revision rather than being silently changed during implementation.

### Required Enemy Roster

| Enemy | Basic behavior | Player effect |
|---|---|---|
| Melee Enemy | Runs at the wizard and attacks at close range. | Prevents long stationary casts and becomes dangerous in groups. |
| Ranged Enemy | Keeps moderate distance and fires a slow telegraphed shot. | Forces lateral movement while Melee Enemies close in. |

Ranged Enemies never appear as an isolated encounter: every encounter that introduces one also includes at least one Melee Enemy. A Ranged Enemy may still end up fighting alone if the player defeats its Melee support first — tap Fireball, cover, and lateral movement remain effective against a lone survivor.

Both enemy archetypes deal damage through the shared **Player Health** system. A successful Melee or Ranged Enemy attack calls the Player Health damage interface; enemy attack implementations do not maintain separate copies of player-health state.

**Enemy health and defeat ownership:** A reusable **Enemy Health/Defeat** capability owns each persistent enemy object's current health, damage intake, defeat transition, and restartable health/defeat state. Fireball and any other canon-required damage source request damage through this owner-controlled interface rather than writing enemy health directly. When defeat occurs, the Enemy Health/Defeat owner reports that transition through the **Active Enemy Registry** owner's removal/unregister interface so the active count is updated without duplicating registry bookkeeping. Floor restart restores enemy health/defeat state through the enemy-owned reset entry point; the Floor Run/Restart Orchestrator does not mutate enemy-health internals directly.

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
- A sealed door is a cursor-targeted interactable. Clicking the intended door issues a combined approach-and-interact request: the wizard moves to that door's interaction position, and the five-second opening timer begins automatically when the wizard reaches arm's-reach range. No sustained button hold is required. After the door is selected, cursor drift does not cancel the request or the timer. Taking damage, moving away after timing begins, or issuing another command that cancels/replaces the door interaction resets the attempt.
- The **Door and Interaction system owns doorway-crossing state**. After a door is open, it detects when the wizard has actually crossed to that door's forward side and exposes that state to consumers. Opening a door does not by itself count as crossing. Door locking and the final escape condition consume this same crossing state rather than implementing separate crossing detectors.
- **Door passability contract:** Door and Interaction owns the semantic door state (`sealed`, `open`, `locked`, `broken`). The shared gameplay navigation/locomotion layer owns translating that semantic state into enemy walkability through a shared passability interface. Sealed and locked doors block enemy traversal; open and broken doors permit forward enemy traversal. Door state changes update the navigation layer through that interface, while enemy pursuit/attack code does not independently manipulate NavMesh or doorway passability. The exact Unity mechanism used beneath this interface (for example obstacle/carving, a navigation link, or runtime navigation-data update) is an implementation choice rather than a separate game-design decision.
- After the shared doorway-crossing state confirms that the wizard reached the forward side, the door automatically closes and locks; the player does not provide a second close/lock input. The completed automatic lock requests the small fixed health restoration through Player Health. Any surviving enemy that is still actively tracking/pursuing the player and whose route to the player is blocked by that locked door begins attacking the door. No separate `witnessed escape` or line-of-sight-to-the-crossing state is tracked: if the enemy can still track the player, it is already aggroed/pursuing. An enemy that has already lost the player does not begin attacking a locked door solely because it is nearby. When the door breaks, those tracking/pursuing enemies continue their pursuit through the now-passable doorway. Once locked, a door cannot be reopened, unlocked, or crossed again by the player — the floor is a forward-only escape sequence.
- **Locked-door attack and durability ownership:** Enemy Pursuit/attack behavior owns deciding when a qualifying blocked pursuer attacks and executing that attack attempt. **Door and Interaction** owns door durability, the owner-controlled door-damage receive interface, and the locked-to-broken state transition. Enemy attack code requests door damage through that interface and does not directly write door durability or semantic door state.
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

- A first-time player understands that clicking a door sends the wizard to it, and reaching the door is not enough; the automatic opening timer still requires five safe, uninterrupted seconds.
- Door interaction requires accurate target selection only on the initial click. The wizard approaches automatically, the five-second timer starts automatically on arrival, normal cursor drift does not cancel opening, and crossing an opened doorway causes automatic close-and-lock with no second input.
- The player understands that enemies left alive remain a threat: leaving them alive means locking a door while they attack it, and later encountering them if that door breaks through.
- Encounters use three to eight enemies and never exceed fifteen active enemies.
- Failure is readable: poor positioning, low mana, using Force Wave without an immediate threat and leaving it unavailable when critical space is needed, or waiting too long.

### Peer and Agent Review Revision

Peer feedback identified that the earlier draft did not explain how the spells and room layouts produced different tactical decisions. A targeted multi-agent review then tested whether those decisions could collapse into a dominant strategy. This revision clarifies Fireball's tap-versus-charge tradeoff, Frost Field's resource commitment, Force Wave's mid-room-versus-door decision, mixed enemy compositions, persistent-pursuer priority, room-specific implementation checks, distance-based target loss and search behavior, accessible cursor-targeted door interaction, shared doorway-crossing ownership, enemy damage through Player Health, active-enemy bookkeeping, and runtime ownership boundaries, Player Health restoration ownership, enemy health/defeat ownership, locked-door attack-to-durability ownership, door-to-navigation passability prerequisites, player-experience validation obligations, and failed-task retry policy without expanding the required content scope.

## 4. AI Architecture

Development agents help plan, implement, review, and test No Safe Circle; they do not run in the finished game. Each agent owns a visible game feature, receives concrete acceptance criteria, and produces a Unity test or implementation result.

### Development Agent Roles

| Agent | Plain-English role | Effect on this game |
|---|---|---|
| Feature Planning Agent | Turns one approved feature into acceptance criteria and a file list. | Keeps prompts specific and prevents scope growth. |
| Wizard Combat Agent | Implements player movement, the shared Unity Input System/Input Actions consumption pattern, the Player Movement-owned cursor-to-gameplay-plane targeting projection, Fireball, Frost Field's casting, mana cost, and feedback, Force Wave, health, mana, cooldowns, and recovery. Frost Field's actual slowdown effect is applied and restored by the Enemy Pursuit Agent, which owns enemy movement and all Ranged Enemy attack behavior; this agent only triggers the Frost Field effect and does not implement Ranged Enemy targeting or attacks. | Creates the tools used to slow, attack, escape, and recover, without editing enemy-movement or enemy-attack code directly. |
| Door and Interaction Agent | Implements cursor-targeted door selection, click-to-approach movement request consumption, arm's-reach arrival validation, automatic five-second opening timing, interruption, shared doorway-crossing state, automatic closing/locking after forward-side crossing, runtime door durability, the owner-controlled door-damage receive interface, and breaking. It is the single owner of detecting when the wizard crosses to the forward side of an opened door; locking and final escape consume that state. Enemy attack behavior requests door damage through the Door-owned interface instead of writing durability or lifecycle state directly. After a door is clicked, cursor movement off the selected door does not cancel the approach or timer; after timing begins, damage, moving away, or issuing another command that cancels/replaces the interaction resets it. No sustained interaction hold is required. | Makes room exits risky and safety temporary without requiring sustained pointer precision after selection, while preventing multiple systems from inventing separate doorway-crossing or door-durability ownership. |
| Enemy Pursuit Agent | Implements detection, melee and ranged attacks, pursuit, movement through open doors, distance-based target loss, last-known-position search, bounded randomized search/wander, and reacquisition, including applying and restoring Frost Field's slowdown effect. Detection Distance is smaller than Lose Target Distance; crossing a doorway does not itself clear pursuit. Enemy attacks consume the shared Player Health damage interface rather than owning separate player-health state. Owns the reusable Enemy Health/Defeat capability for persistent enemy objects: damage sources consume its damage interface, defeat reports removal through the Active Enemy Registry interface, and floor restart consumes its reset interface. Owns Ranged Enemy targeting, attack timing, and line-of-sight/projectile-occlusion checks, so Chapel of Ash's cover actually blocks shots. Enemy locomotion consumes the shared gameplay navigation/locomotion layer rather than choosing or configuring that layer independently. Owns the shared Active Enemy Registry bookkeeping for persistent active enemy objects; encounter activation consumes that registry rather than maintaining a separate count. Owns the ongoing state of persistent enemy objects whether they are actively pursuing, searching, or later reacquired. It also owns the application of forced enemy displacement requested by abilities such as Force Wave, including returning affected enemies to the appropriate pursuit/search movement state afterward. Qualifying locked-door attacks are initiated by this enemy behavior but apply durability loss only through the Door and Interaction damage interface. | Makes enemies left alive remain a visible, persistent consequence while preserving explicit ownership of enemy health/defeat, player-health damage, navigation, registry bookkeeping, and Door-owned durability. |
| Dungeon Encounter Agent | Authors placements, triggers, configured per-door durability values, and final-room pressure, including the mixed Melee/Ranged compositions in Chapel of Ash and the Final Room. It does not own runtime door durability state, damage intake, or the locked-to-broken transition; those remain Door and Interaction responsibilities. Owns encounter-admission policy and consumes the shared Active Enemy Registry before activating new enemies. When persistent enemies and a requested new encounter would together exceed fifteen active enemies, this agent delays or reduces the new encounter's enemies first rather than removing existing pursuers. | Controls when the player can lure, fight, flee, or become trapped, and authors encounter/durability tuning without taking ownership of runtime Door state or the registry's persistent-enemy bookkeeping. |
| Unity Validation Agent | Reviews changes and creates Play Mode checks for cleanup, references, and edge cases, including Bone Archive lane pathing, Chapel of Ash occlusion, Lower Vault enemy-cap priority, target-loss hysteresis/search and reacquisition, cursor-targeted door range and cursor-drift behavior, isometric sprite sorting, and alignment between Tilemap visuals and gameplay geometry. | Prevents permanent slowdown, stuck enemies, incorrect pursuit/search transitions, inaccessible door interaction behavior, incorrect door states, and visual/gameplay desynchronization. |

### Development Agent Ownership Invariants

The following ownership boundaries are required development-process constraints and must be preserved by planning, reconciliation, implementation, and validation agents:

- **Feature Planning Agent** may decompose approved work and identify dependencies, but it does not implement gameplay or create new design.
- **Wizard Combat Agent** owns player movement/resources, shared pointer projection, and spell initiation. Within that responsibility, Player Health, Player Mana, Player Movement, and each spell remain separate runtime state owners rather than collapsing their state into one shared player system. Player Health owns health and its zero-health transition; Player Mana owns mana and regeneration-delay state; Player Movement owns position/locomotion, movement-restriction state, and shared cursor-to-gameplay-plane projection; Fireball, Frost Field, and Force Wave own their spell-local state. Charged Fireball consumes the Player Movement restriction interface instead of mutating movement internals. Spells consume Player Mana through its spend interface; Force Wave's initial cost is 25 mana per cast. Wizard Combat requests enemy effects through enemy-owned interfaces and does not directly manipulate enemy locomotion, status restoration, or forced-displacement state.
- **Enemy Pursuit Agent** owns enemy pursuit/search state, enemy locomotion behavior, enemy attack behavior, the reusable Enemy Health/Defeat capability, Frost slowdown application/restoration, forced displacement, and shared Active Enemy Registry bookkeeping. Enemy attacks consume the shared Player Health damage interface; damage dealt to enemies consumes the Enemy Health/Defeat interface; defeat reports registry removal through the registry-owned interface; enemy locomotion consumes the shared gameplay navigation/locomotion layer; and encounter activation consumes the registry rather than maintaining a separate count. When a surviving enemy is still actively tracking/pursuing the player and a locked door blocks its route, Enemy Pursuit owns initiating the locked-door attack; no separate witness flag is required. The attack requests damage through the Door and Interaction damage interface rather than mutating door durability or lifecycle state, and pursuit continues through the doorway after the door breaks. Pursuit and attack behavior consume doorway walkability from the shared navigation layer rather than directly changing NavMesh or door passability.
- **Door and Interaction Agent** owns door targeting, click-to-approach interaction consumption, automatic five-second timing on arrival, shared doorway-crossing state, runtime door durability, the owner-controlled door-damage receive interface, and semantic door lifecycle state including the locked-to-broken transition. Other systems consume doorway-crossing state rather than implementing their own crossing detector, and enemy attack behavior requests durability loss through the Door-owned damage interface rather than mutating Door state directly. Door state changes are published through the shared navigation/locomotion passability interface; Door and Interaction does not own the navigation technology that translates those states into enemy walkability.
- **Final escape/victory coordination** owns only the won-state transition, gameplay-suspension coordination, and victory presentation. Player Movement, Door/Interaction, Fireball, Frost Field, and Force Wave remain owners of their own active behavior and must expose owner-controlled suspend/re-enable entry points consumed by victory/reset flows. Final escape logic must not reach into movement, door, or spell internals to stop them.
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
- **Current prototype scene-builder lock:** scene-authoring work that changes objects generated or maintained through `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` must take exclusive-write locks on both that builder and `Assets/Scenes/DoorPrototype.unity`. This specifically applies to doorway-crossing work that creates/configures the forward-side crossing trigger and, under the current scene-built UI approach, to final-victory work that creates/configures the **You Escaped** overlay. If a later approved architecture moves the overlay or another scene object into a separately owned runtime prefab/asset, the task may lock that actual asset instead; the task graph must reflect the implementation that exists when it is dispatched.
- Each task produces changed files, an implementation summary, known risks, and a Play Mode test checklist.
- Source control commits serve as the handoff between implementation, validation, and integration.
- Agents may report a risk or recommend a scope cut, but they cannot redesign the game or add features without developer approval.
- The human developer remains responsible for architecture, merging changes, inspecting Unity scenes and prefabs, playtesting, balance, and final integration.

### Example Game-Specific Agent Task

While the Door and Interaction Agent implements click-to-approach door opening, automatic five-second timing on arrival, and automatic locking after crossing, the Enemy Pursuit Agent can independently implement melee enemies following the wizard through open doors. At the same time, the Dungeon Encounter Agent can define the enemy placement for the first encounter space.

After those tasks are complete, the Unity Validation Agent checks that enemies can cross an open doorway without automatically losing the player, that distance-based target loss leads through last-known-position search before target clearing, that damage or moving away interrupts opening after arrival while cursor drift after selection does not, and that crossing automatically closes and locks the door with no second input. The developer then combines and tests the features inside Unity.

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

### Current Prototype Scene Evidence

The current repository contains two committed `.unity` scenes. This inventory is current repository evidence, not permanent design canon:

- `Assets/Scenes/DoorPrototype.unity` is the current canonical gameplay prototype scene maintained by `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`. It contains the populated gameplay prototype, including the current `PlayerMana` and `PlayerManaUI` wiring.
- `Assets/Scenes/SampleScene.unity` is a non-canonical sample/stub scene.
- The former `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` path no longer exists in the current repository. Historical provenance may still correctly cite that former path when recording earlier repository states.

### 2.5D Isometric Visual and World Representation

- The project targets a **hybrid isometric architecture**. Unity **2D Tilemap Editor** (`com.unity.2d.tilemap`) is the approved authoring package for Isometric Tilemaps used for floors, walls, and repeatable architecture. **SpriteRenderer prefabs** are used for doors, props, obstacles, the wizard, enemies, and other independently sorted or interactive objects.
- A generated or hand-authored visual tile does **not** automatically define gameplay behavior. The simulation layer separately defines collision, door interactions, walkability, trigger zones, and navigation.
- The visible isometric layer and the gameplay/navigation layer should remain decoupled wherever practical so environment art can be regenerated or replaced without rewriting room logic.
- A shared **gameplay navigation/locomotion layer** owns the walkable movement representation and the navigation-facing configuration used by runtime movers. It also owns the navigation-side implementation of the shared door-passability interface: semantic door state is supplied by Door and Interaction, while this layer translates sealed/open/locked/broken state into enemy walkability. Enemy pursuit/search, melee/ranged behavior, status effects, and forced displacement consume this layer instead of each selecting or configuring navigation technology or doorway passability independently.
- The approved enemy-navigation implementation is **Unity AI Navigation** (`com.unity.ai.navigation`) using NavMesh-based runtime movement. A minimal working navigation/locomotion layer and the approved package configuration must exist before locomotion-dependent enemy implementation is dispatched, but room-specific visual authoring does not need to be complete first.
- The reusable visual world foundation (Tilemap/SpriteRenderer conventions and visual/gameplay separation) is distinct from authoring the five named room layouts and encounters. Five-room visual/content authoring consumes this foundation once it exists; encounter placement/content consumes the authored room spaces and the encounter-admission/cap foundation. These are real prerequisite relationships even when the downstream content features remain deferred for future decomposition.
- The camera is fixed in an isometric presentation; the player does not rotate the world view freely.
- Mouse-directed click/hold movement is routed through Unity Input System/Input Actions and projected onto the gameplay plane by the Player Movement-owned shared cursor-targeting foundation. Movement, cursor-aimed spells, and Door/Interaction consume the same world-space pointer target, preserving smooth movement similar to early isometric action/RPG controls without independent screen-to-world projection in each gameplay system.

### Runtime Implementation

- The primary environment visual layer will use Unity **Isometric Tilemaps** through the approved Unity 2D Tilemap Editor package (`com.unity.2d.tilemap`), preferably Isometric Z as Y where useful, for floors, walls, and repeatable architectural tiles. World-space **SpriteRenderer** prefabs will be used for sealed doors, tall props, obstacles, the wizard, enemies, and other independently sorted or interactive objects. Character presentation is therefore part of the reusable visual-world foundation rather than a separate rendering architecture.
- The gameplay layer remains separate from the visible art layer. Walkability, collision, trigger zones, doorway logic, and other simulation rules are defined independently from the Tilemap art so generated or swapped visual assets do not automatically change gameplay behavior.
- Player movement uses mouse-directed click/hold navigation through the project's Unity Input System/Input Actions layer. Player Movement owns the shared cursor-to-gameplay-plane projection and exposes the resulting world-space pointer target; movement, cursor-aimed spells, and Door/Interaction consume that shared result rather than independently polling pointer hardware or projecting screen coordinates. Force Wave is the player-centered radial exception and does not use cursor direction or target selection. Clicking a sealed door requests movement to its interaction position; when arm's-reach proximity is reached, the five-second opening timer begins automatically without a sustained hold, and cursor movement off the door does not cancel the selected interaction.
- A shared gameplay navigation/locomotion layer provides the walkable movement representation and navigation-facing configuration consumed by enemy movement. The approved implementation uses Unity AI Navigation (`com.unity.ai.navigation`) and NavMesh-based runtime movement; enemy detection/pursuit/search logic does not choose or configure a different navigation technology independently. The same layer exposes the navigation side of the shared door-passability interface and translates Door and Interaction's semantic sealed/open/locked/broken state into enemy walkability. Once that shared navigation layer exists, finite-state components control pursuit, attacks, target loss, search, and reacquisition across the floor's spaces. Enemies acquire the player inside Detection Distance and use a larger Lose Target Distance to end exact pursuit. Exceeding Lose Target Distance transitions the enemy to the player's last known position, followed by a short bounded randomized search/wander if the player is not immediately reacquired; doorway crossing alone does not clear pursuit. Exact distance thresholds, search duration, random search weighting, and the underlying Unity mechanism used to update doorway passability are implementation/playtesting details beneath the approved shared contracts. Ranged Enemy attacks include a line-of-sight/occlusion check, and Bone Archive's lane widths are validated against enemy movement/navigation requirements so both rooms' stated tactical geometry holds in practice.
- Enemy movement is the authoritative owner of enemy locomotion and forced displacement. Player abilities may request changes to enemy motion but do not directly manipulate enemy position or navigation state. Force Wave determines which enemies are affected and the radial knockback to request; the enemy movement system applies that displacement, preserves valid movement/navigation state, and resumes the appropriate pursuit/search state afterward. Temporary movement modifiers such as Frost Field slowdown are applied through the enemy status-effect system and restored when the effect ends. The pursuit/search state contract must therefore exist before status-effect/displacement work is treated as independently dispatchable; status/displacement consumes that contract when handing control back to normal enemy behavior.
- A reusable **Enemy Health/Defeat** runtime capability owns each persistent enemy's current health, damage intake, defeat transition, and floor-restart reset. Fireball and any other canon-required enemy-damage source call that capability's damage interface. Defeat then reports removal through the Active Enemy Registry's owner-controlled interface; neither damage sources nor the restart orchestrator directly write enemy-health or registry internals.
- All five encounter spaces exist inside one continuous Unity scene or continuous floor representation. Enemy objects, enemy health, pursuit state, active-enemy bookkeeping, and door state persist naturally as the player advances between spaces; no scene-load or cross-scene state-transfer system is required.
- A reusable status-effect/displacement component will apply Frost Field slowdown, apply enemy-owned forced displacement requests, and restore each enemy to the appropriate pursuit/search movement state afterward, per the Wizard Combat Agent / Enemy Pursuit Agent ownership split defined in Section 4. It consumes the pursuit/search state contract rather than defining a second enemy-state machine.
- A reusable door component will control click-to-approach interaction, automatic five-second timing on arrival, interruption, shared doorway-crossing state, automatic closing/locking after forward-side crossing, runtime durability, the owner-controlled door-damage receive interface, and breaking. It records when the wizard crosses to the forward side of an opened door and exposes that state to automatic locking and final-victory logic; those consumers do not implement separate crossing detection. Enemy locked-door attack behavior requests damage through the Door-owned interface, while the door component owns durability reduction and the locked-to-broken transition. Once a door is automatically locked after crossing or broken by enemies, it does not return to an earlier state.
- A reusable **Game Flow/Victory** capability consumes the final door's shared forward-side crossing state, owns the won-state transition and **You Escaped** presentation, and coordinates gameplay suspension through owner-controlled interfaces. Player Movement, Door/Interaction, Fireball, Frost Field, and Force Wave must each provide a suspend/re-enable entry point that stops current input-driven activity as well as future commands. The victory capability does not directly mutate locomotion, door-interaction, spell-charge, cast, cooldown, or other owner-internal state.
- A shared **Floor Run/Restart Orchestrator** coordinates a new floor attempt when it receives Player Health's zero-health/death transition. It invokes reset entry points owned by each stateful system rather than directly mutating their internals. Player Health, Player Mana, Player Movement/player position, spell-local Fireball/Frost Field/Force Wave state, enemy health and pursuit/search/attack/status/displacement state, Active Enemy Registry bookkeeping, door lifecycle/crossing/durability state, and encounter activation/admission state must all participate once those systems exist. Enemy reset returns each persistent enemy to the authored encounter/spawn region associated with its original room and clears all knowledge/state from the failed run; exact placement inside that region may vary. Early staged restart implementation is valid only as an incremental step; the persistent-systems closure remains required until all implemented state owners are connected to the orchestrator.
- Player Mana owns current mana and the post-cast regeneration-delay state and exposes an owner-controlled spend/reset interface to spells and restart orchestration. Force Wave spends 25 mana per cast through this interface as its initial tuning value. Spell-local cooldown/charge/cast/active-field state stays on the spell that owns it. Player Movement owns position/locomotion, the shared cursor-to-gameplay-plane projection, and the owner-controlled movement-restriction interface consumed by Charged Fireball. Runtime actions are supplied through Unity Input System/Input Actions rather than independent direct hardware polling inside gameplay systems.
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
- The required delivery target is a **Windows Standalone build**. The current canonical gameplay scene is `Assets/Scenes/DoorPrototype.unity`; that scene, or a later human-approved replacement canonical gameplay scene, must be registered in Unity Build Settings before the Windows delivery requirement can be considered complete. A committed `EditorBuildSettings.asset` with no registered canonical gameplay scene is confirmed incomplete build configuration and must remain represented as open configuration work. `Assets/Scenes/SampleScene.unity` remains non-canonical and does not satisfy this requirement merely because it exists.
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
