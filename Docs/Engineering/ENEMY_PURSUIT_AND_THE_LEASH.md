# Enemy pursuit: the sight gate, the leash, and why an enemy paces

**Measured on canonical `main` at `163d7cca` on 2026-09-27** from source, from the committed
`MeleeEnemy.prefab`, and from a PlayMode diagnostic run in an isolated checkout. The behavioural
findings in §3 were each reproduced; the ones in §4 were each tested and refuted.

Vincent played the game and reported:

> *"The enemy keeps pacing back and forth"*
> *"The enemy will not walk around the furniture"*
> *"It needs to be able to move the root isnt moving with the enemy"*

The tracked id for the frozen case is **`ba-melee-1`** — the Bone Archive melee enemy that never
begins pursuit.

---

## !!! 1. THE DESIGN INTENT IS RECORDED TWICE, ONE DAY APART, AND THE TWO RECORDS CONTRADICT EACH OTHER. READ THIS FIRST. !!!

Both are Vincent's own words. Both are in the repository or its task graph. They cannot both be
implemented.

**2026-09-26 — a TOWED anchor.** Quoted in `Tasks/NSC-125.yaml`, criterion prose:

> *"the issue is that leash has a owner and the owner doesnt move"*
> *"the owner must move with enemy"*
> *"the enemy must drag the owner when it runs out of slack"*

The contract's own reading of it, and it is a careful one: *"HE DID NOT ASK FOR THE LEASH TO GO; HE
RESPECIFIED ITS ANCHOR. His spec keeps a home to return to — within slack the anchor does not
move."*

**2026-09-27 — a FIXED anchor.** Said directly in a Game Agent session:

> *"I mean it is on a leash"*
> *"the leash is only so many units and the starting point of the leash will not move, it cant be
> pulled by the enemy"*
> *"I am sure we spoke about this before and I guess it wasnt written down."*

**The difference is the whole mechanism.** A towed anchor lets an enemy cross the floor a step at a
time, dragging its post behind it once slack runs out. A fixed anchor holds it to a circle of
`maximumPursuitDistanceFromStart` around its spawn point, for ever.

**Nothing in this repository can settle this. It is Vincent's, and it is one question.** Until he
answers it, do not "fix" the leash in either direction — a change either way will be wrong for one
of his two statements. The last line of the 09-27 quote is worth noticing: he believed it had never
been written down, and it had been, saying the opposite. That is the cost of design intent living in
conversation.

**What is implemented today is the FIXED anchor** (§2). So the 09-27 statement describes the current
code and the 09-26 statement describes a change nobody has made.

---

## 2. What the code implements

`Scripts/Enemies/EnemyTargetKnowledge.cs`. Serialized on `Resources/Enemies/MeleeEnemy.prefab`:

| field | value |
|---|---|
| `detectionDistance` | 6 |
| `loseTargetDistance` | 10 |
| `requiresLineOfSight` | **1** |
| `maximumPursuitDistanceFromStart` | **5** |
| `m_ApplyRootMotion` (Animator) | 0 |
| NavMeshAgent `m_Radius` / `m_Height` / `m_StoppingDistance` | 0.5 / 2 / 0.6 |

**The anchor is set in `Awake`, at `:51-52`**, and the comment above it explains why the lazy path
must never be relied on:

> *`startPosition`/`hasStartPosition` are deliberately not serialized, so the leash must anchor
> itself here rather than relying on `IsBeyondPursuitLeash` being reached. The sight test is
> evaluated first in the acquisition chain, so a lazy anchor would never initialize while sight is
> blocked — and would then measure distance from world origin, which for an enemy at Z 53 exceeds
> any leash and silently prevents it from ever acquiring the wizard.*

`Awake` runs **at the spawn pose**: `Scripts/Enemies/Pooling/EnemyPrefabPool.cs:250-251` uses the
position overload deliberately —
`Object.Instantiate(prefab.Asset, slot.Pose.position, slot.Pose.rotation, activeRoot)` — with the
comment *"The position overload, so Awake runs at the slot's pose"*. So the post stands where the
enemy spawned, and `EnemyEncounter.cs:140`'s later `agent.Warp(entry.Position)` lands at the same
point.

`IsBeyondPursuitLeash()` at `:248` measures **straight-line displacement** from that post,
flattened to the XZ plane, against `maximumPursuitDistanceFromStart`; `<= 0` means unlimited.
`IsBeyondPursuitLeash`'s lazy `if (!hasStartPosition)` branch still exists as a fallback and, given
`Awake`, is unreachable in the shipped flow.

On exceeding the leash, `:110-124` does exactly what its comment says — *"Dragged too far from its
post: give up and head back rather than following the wizard onto a doorway"* — setting
`LastKnownPosition = startPosition` and `State = SearchingLastKnownPosition`.

**The only production caller of `SetMaximumPursuitDistanceFromStart` is
`Editor/World/DoorPrototypeGlobalSceneBuilder.cs:524`** — the old editor authoring path. At runtime
the value comes from the serialized prefab field, and the anchor from `Awake`. The setter also
re-anchors, which is why the editor path could move the post to a mid-room position.

---

## 3. The two behaviours Vincent sees, both reproduced

Both measured on `ba-melee-1` at its real position `(1.38, 0.04, 8.63)`, `isOnNavMesh = True`.

### a. The sight gate freezes it completely — *"the root isnt moving"*

With the player 4 units east, behind `ShelfC-shelfmid-01` (the prefab `ba_shelf_bank_z_middle`,
collider 2.73 tall, on layer `Default` so it legitimately blocks sight):

    independent raycast    hits ShelfC-shelfmid-01 at 1.05 units
    HasUnobstructedViewOfWizard()   False
    IsBeyondPursuitLeash()          False
    State = Idle    hasPath = False    velocity 0
    root position frozen at spawn for the full 4-second window
    NavMesh.CalculatePath            proves a COMPLETE walkable detour exists around the shelf

`HasUnobstructedViewOfWizard()` is at `:263-284`. It raycasts at chest height
(`SightOcclusionLayers.EyeOffset = Vector3.up`) with `ExcludeLowDressing`, and a hit on anything
other than the wizard means no sight. **Sight is evaluated before acquisition, and there is no
fallback**: a melee enemy with a shelf between it and the wizard does not approach, does not edge
around, does not investigate. It idles. The walkable route is right there and it never asks for it.

**This is not a NavMesh defect.** The bake carves real holes around props of every height — see
`PROP_COLLIDERS_AND_NAVMESH.md` §2, where that hypothesis was measured and refuted.

### b. The leash and a detour fight each other — *"pacing back and forth"*

With the player 4 units north and clear line of sight (`HasUnobstructedViewOfWizard() = True`),
pursuit starts correctly. But the walkable route to a point only 4 units away is a long westward
detour — `NavMesh.CalculatePath` corners swing out to `x = -3.167` before reaching `z ~ 12.6`. The
leash measures **straight-line displacement from the post, not distance travelled**, so the detour
carries the enemy past 5 units of displacement before it arrives. Then:

    Pursuing -> (leash exceeded) -> SearchingLastKnownPosition, heading back to the post
             -> arrives, Wandering -> re-acquires -> Pursuing -> leash exceeded -> back ...

The root measurably reverses direction at each flip. **That is the pacing**, and every step of it is
the leash working exactly as designed. The defect is the *interaction*: a 5-unit straight-line
leash cannot survive a room whose furniture forces a route longer than the leash to reach a target
inside it.

Note that this is true under **either** of Vincent's two designs, for the same reason — it is about
straight-line versus path distance, not about whether the post moves. It is the one part of this
that can be worked on before he answers §1.

---

## 4. Hypotheses tested and killed. Do not re-test these.

| hypothesis | how it died |
|---|---|
| **Animator root motion** is moving the visual without the root | `m_ApplyRootMotion: 0` on `MeleeEnemy.prefab`. The Animator is on the root; the only child is `Visual` at local `(0,0,0)`. |
| **The leash anchors lazily, wherever the enemy first happens to be** | `Awake` at `:51-52` anchors it, and `EnemyPrefabPool.cs:250-251` instantiates at the spawn pose so `Awake` runs there. This was **my own leading hypothesis and it was wrong** — I read `IsBeyondPursuitLeash`'s lazy branch and never read `Awake` in the same file. |
| **Props do not carve the NavMesh, so paths run through furniture** | `NavMesh.SamplePosition` returns no hit on both a 1.20-tall crate and a 2.73-tall shelf, with a passing control on clear floor. Refuted by measurement. |
| **Line of sight is a plausible but unconfirmed cause** | No longer a hypothesis: it is now case (a), reproduced with the occluder named and the hit distance measured. |

**And one finding about the test, not the game.** The existing gated regression in
`Tests/RuntimeWorldEnemyNavMeshPlayModeTests.cs:277-460` searches for a player placement using a
helper that **always tries `+X` first** — which in the Bone Archive happens to be the sight-blocked
direction. So "never begins pursuit" is a property of that fixture's direction order as much as of
the enemy: approach from `+Z` and pursuit starts. The test reproduces a real defect and its name
overstates the scope.

That fixture is gated by an env-var `Assert.Ignore` on `NSC_RUN_KNOWN_DEFECTS`, **not** by
`[Explicit]` — see the memory `explicit-does-not-skip-under-a-broad-testfilter`; the attribute does
not keep a test out of a broad `-TestFilter` run in this project.

---

## 5. Nobody owns the fix

`EnemyTargetKnowledge.cs` is **not** in `NSC-125`'s `exclusive_resources` (it carries
`EnemyPursuitMovement.cs`, `DoorPrototypeGlobalSceneBuilder.cs` and the melee prefab family).
NSC-125's own notes say so and draw the right conclusion:

> *the towing behaviour lives in `EnemyTargetKnowledge.cs`, which this task DOES NOT OWN ... so a
> criterion requiring the tow here would be unsatisfiable by construction, which is the defect this
> contract family has already been bitten by once.*

So the anchor respecification Vincent asked for on 09-26 is owned by **no task**, and the sight
fallback in §3a is owned by no task either. That is a real gap, not an oversight to route around: a
criterion naming an unowned file cannot be satisfied.

---

## What is not proven

- **Which of Vincent's two leash designs he wants.** §1. His call, one question, blocking the
  anchor work and nothing else.
- **Whether a sight-blocked melee should approach a last-glimpsed point**, hold, or investigate.
  Design, not measurement.
- **Whether the leash should measure path length instead of displacement, or simply be larger.**
  Both fix the pacing; they are different games.
- **Whether the other melees behave the same.** Only `ba-melee-1` was instrumented. `ca-melee-1`,
  `lv-melee-1`, `fr-melee-1/2` are unmeasured.
- **Why the route to a point 4 units north detours as far west as `x = -3.167`.** Room and shelf
  layout; not investigated.
- **Whether the 25 over-eye-height props on `LowDressing`** (see `PROP_COLLIDERS_AND_NAVMESH.md` §4)
  make case (a) more or less common than it should be.
