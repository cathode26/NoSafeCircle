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

## 1. SETTLED 2026-09-27 BY VINCENT: THE ANCHOR IS TOWED. And the record had said so all along.

**His words, the ones that decided it:**

> *"The problem is that the enemy post is fixed where it spawned, but it needs to be allowed to
> drag its leash anchor."*

So `maximumPursuitDistanceFromStart` is a **slack radius**, not a cage. Within slack the anchor
holds still; once the enemy runs out of slack it **drags the anchor** along behind it so the rope
stays exactly taut. There is still a home to return to - it simply follows.

**This confirms the older of two conflicting records and refutes my reading of the newer one.**
`Tasks/NSC-125.yaml` had quoted him on 2026-09-26: *"the issue is that leash has a owner and the
owner doesnt move"*, *"the owner must move with enemy"*, *"the enemy must drag the owner when it
runs out of slack"*. That was right. On 2026-09-27 he also said *"the leash is only so many units
and the starting point of the leash will not move, it cant be pulled by the enemy"* and **I read
that as design intent when it was a description of the BUG** - he was telling me what the code
does wrong, and I wrote it down as what it should do.

- **THE LESSON, and it is the expensive one: a bug report and a design statement can be the same
  sentence.** *"X does not move"* is either a complaint or a specification and nothing in the
  words tells you which. When a statement describes current behaviour, ask which of the two it is
  before recording it, because recording it as intent makes the defect permanent and looks like
  diligence. His *"I am sure we spoke about this before and I guess it wasnt written down"* was
  the clue: it HAD been written down, correctly, and the disagreement was with my note, not his
  memory. See the memory `search-for-an-existing-decision-before-recording-a-new-one`.

### And towing alone did NOT fix it. That is the part worth keeping.

An implementation of the tow already existed, unmerged, at `ac1f9691f`: it drags the anchor to stay
exactly one leash-length behind **and still abandons the chase**. Trace it:

    enemy leaves anchor A, pursues            displacement from A grows
    displacement > 5                          anchor towed to A1 = pos - dir * 5, gives up
    walks back to A1                          5 units backwards
    re-acquires, pursues                      reaches pos again, displacement from A1 = 5
    displacement > 5                          tows to A2 ~= A1, gives up again

**The anchor moves once and then stops, and the enemy paces a 5-unit segment for ever.** That is
exactly the defect, relocated five units. **Dragging exists so the enemy does not have to stop, so
the give-up had to go as well** - the anchor moving and the chase continuing are two separate
changes and only the pair is a fix.

### Why the give-up could be removed without un-delivering anything

Both contracts declaring `EnemyTargetKnowledge.cs` are **conformant with delivery records**, so a
criterion change would have un-delivered a delivered task. Read at source first:

| contract | state | what it says about the leash |
|---|---|---|
| NSC-111 | conformant, `DEL-NSC-111-d8683f6afdc5` | criterion (3) requires that a **redirected** enemy taken beyond the leash clears the redirect, keeps the wizard as `CurrentTarget` and searches the start position |
| NSC-091 | conformant, `DEL-NSC-091-2559514826e9` | owns the file and mentions the leash **zero times** |

So the give-up now serves **only** the decoy-redirect path, which is preserved exactly, and the
ordinary path is unconstrained. **Had NSC-091 held a leash criterion this would have been a GER
revision request instead of a change.** The ordinary-pursuit branch also gained a public
`PursuitAnchor`, because with the give-up gone the anchor was no longer observable and the next
test would otherwise have reached for reflection on a private field.

### What would falsify this section

A later statement from Vincent about the anchor, or a leash criterion appearing in **any**
contract's `exclusive_resources` owner (re-read NSC-091 and NSC-111, and grep `Tasks/` for
`leash`). Also: if an enemy is now seen following the wizard onto a doorway and camping the
threshold, the old comment's stated purpose has been lost and the bound needs to return in some
other form - that was the leash's original job and nothing replaces it.

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
