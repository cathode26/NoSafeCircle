# Prop colliders, the NavMesh, and walking around furniture

**Every number here was measured on canonical `main` at `163d7cca` on 2026-09-27**, from the
committed prefab and `ProjectSettings` blobs, not recalled. The script that produced the tables is
reproducible: read each `Resources/Props/*.prefab` blob and pull `m_Size`, `m_Center`, `m_Layer`.

This document exists because Vincent played the game and reported, in his own words:

> *"The path finding for the player doesnt consider the room obstacles and walk around"*
> *"The enemy will not walk around the furniture"*
> *"All the colliders needed to be different. Do you remember we talked about how they should be redone."*

Three separate causes sit behind those three sentences. **They are not the same bug**, and the
first reading of them — "the prop colliders don't carve the NavMesh" — was measured and is **false**.

---

## 1. What the props actually carry

45 prop prefabs under `Assets/NoSafeCircle/DoorPrototype/Resources/Props/`:

| | count |
|---|---|
| `BoxCollider` | **41** |
| no collider (declared walk-through) | 4 |
| `CapsuleCollider`, `SphereCollider`, `MeshCollider` | 0 each |
| `isTrigger` set | **0** |
| `NavMeshObstacle` | **0** |
| `NavMeshModifier` / `NavMeshModifierVolume` | **0** |
| `Rigidbody` | 0 |

The four with no collider are declared, with reasons, in
`Editor/Environment/PropPrefabVerifier.cs` — `shared_web_corner_a`, `shared_web_drape_b`,
`ca_sigil_floor_mark`, `lv_sluice_slime_spill`. That list is a *declared exception*, not a relaxed
check: the verifier also fails a prop on the list that has *acquired* a collider, which is the
guard that actually earns its keep.

### Every box is a square prism taken from the sprite's bounding box

In all 41, **`m_Size.x == m_Size.z`**, `m_Size.y` is the sprite's height, and
`m_Center` is `(0, m_Size.y / 2, 0)`. So each collider is

    sprite_width  x  sprite_height  x  sprite_width      centred at half height

That is the sprite's bounding box extruded into a square column. It is not a footprint. Two
consequences you can see in play:

- **A wide, shallow object gets a deep footprint it does not have.** `ca_pew_x_middle` is
  `1.78 x 1.77 x 1.78`: a church pew as deep as it is wide. `fr_bench_x` is `1.69 x 1.59 x 1.69`.
- **A tall object's collider fills the whole sprite height, so you cannot pass behind it.**
  `shared_stone_column` is `1.31 x 3.02 x 1.31`; `ba_shelf_bank_z_start` is `1.69 x 2.86 x 1.69`.
  This matters for more than movement — see §4.

### THE SPEC, MEASURED FROM VINCENT'S OWN SHIPPED GAME

`PropPrefabVerifier.cs` records the model second-hand: *"his own `chest.prefab` pairs a solid base
collider with a walk-through trigger over the whole sprite."* **That is directionally right and it
omits the part that matters.** `chest.prefab` is not in this repository - it is in
`F:/Petnip/MoveProblems/client`, the isometric Unity 2D game Vincent shipped, which `CLAUDE.md`
names as an approved free reference and says to read **before** deriving behaviour from first
principles. Measured there:

| prefab | collider | x span | y span |
|---|---|---|---|
| `chest` | trigger | -0.59 .. 0.61 | 0.04 .. **1.00** |
| `chest` | solid | -0.59 .. 0.61 | 0.03 .. **0.60** |
| `shrub_harvested_2` | solid | -0.60 .. 0.61 | 0.01 .. **0.52** |
| `Wilds` (x7, one per bush) | solid | ~full width | 0.01 .. **0.39-0.69** |
| `berry_doober`, `chest_doober` | trigger only | -0.18 .. 0.18 | ~0.0 .. 0.32 |

**THE RULE, and all three parts are things this project gets wrong:**

1. **The solid is a POLYGON, not a box.** Every one is a hand-traced 5-12 point
   `PolygonCollider2D` following the isometric diamond of the object's base. An axis-aligned
   rectangle cannot express that shape.
2. **!!! IT COVERS THE BOTTOM HALF OF THE SPRITE, NOT ALL OF IT. !!!** Full width, but y stops
   between 0.39 and 0.69 of sprite height in every single case. **This project's 41 boxes run to
   100% of sprite height**, which is why props block sight lines and cannot be walked behind. This
   is the single biggest difference and it is measurable in one line per prefab.
3. **One collider per visual ELEMENT, not per prefab.** `Wilds` carries seven solids because it
   draws seven bushes. This project has exactly one box per prop however many objects the sprite
   shows.

**The full-height trigger is the EXCEPTION, not the pattern.** Only `chest` (an interactable) and
the two `*_doober` pickups carry one; the pickups have a trigger and no solid at all, because you
walk into them. So *"a solid base plus a walk-through trigger"* describes ONE prefab, and the
universal rule is the base-height solid polygon. A sweep claiming the pair is the pattern would be
over-reading a single file - which is what the second-hand note in `PropPrefabVerifier` invites.

**WHAT DOES NOT TRANSFER, stated so nobody lifts the wrong thing.** Petnip is **2D physics** -
`PolygonCollider2D`, 6 of its 55 prefabs, zero in its scenes. No Safe Circle is **3D**:
`BoxCollider`, a `CharacterController` player and a 3D NavMesh. So the TYPE cannot be copied and
the editor is six majors older (`2019.4.16f1` against `6000.1.8f1`). **The SHAPE RULE transfers
exactly**, and in 3D it means a collider sized to the real footprint depth and only as tall as the
base - not `sprite_width x sprite_height x sprite_width`.

**And the process lesson is mine.** `CLAUDE.md` says to read this project before reasoning from
first principles, and records that four agents reasoned about one sorting problem from first
principles and a render refuted three of them. I measured 41 prefabs, wrote an intent file, and
filed *"what does different mean"* as a question only Vincent could answer - while the answer sat
in a folder he had already granted us and I had already been told to read. He had to say *"You have
forgotten how to do the colliders"* and then hand me the path. **When a spec feels unknowable, check
whether it is already implemented somewhere you have been given.** Credit any lifted code as
`Vincent's code, from his isometric game (~2022), adapted.`
---

## 2. The NavMesh bake, and the hypothesis that turned out to be wrong

The bake is configured in `Scripts/World/GameplayNavigationSurface.cs`:

    surface.agentTypeID  = NavMesh.GetSettingsByIndex(0).agentTypeID
    surface.collectObjects = CollectObjects.All
    surface.useGeometry   = NavMeshCollectGeometry.PhysicsColliders

The single agent type, from `ProjectSettings/NavMeshAreas.asset`:

| setting | value |
|---|---|
| `agentRadius` | 0.5 |
| `agentHeight` | **2** |
| `agentSlope` | 45 |
| `agentClimb` | 0.4 |
| `minRegionArea` | 2 |
| `cellSize` | 0.16666667 |

`Scripts/World/SpawnPhase.cs` puts `Props = 1` before `Navigation = 2`, and says why in its own
remarks: *"navigation must bake AFTER the props exist or it walks through them — which is the same
fact the prop colliders were added for, seen from the navmesh's side."* So the props are alive and
collected when the bake runs.

### !!! The "short colliders do not carve" claim is REFUTED. It was mine, and it was wrong. !!!

The claim was that because **29 of the 41 boxes are shorter than the agent height of 2.0** (they
run from 0.53 to 1.97), the bake lays a walkable surface on top of them instead of cutting a hole,
so a path is computed straight through the furniture.

**A PlayMode measurement killed it.** `NavMesh.SamplePosition` at 0.05 tolerance, directly on each
prop's own XZ, in the assembled runtime world:

    tall prop    ba_shelf_bank_z_middle  (3.25, 0, 8.40)    hit = False    real hole
    short prop   lv_crate                (-11.2, 0, 61.0)   hit = False    real hole
    control      clear floor near enemy  (1.25, 0, 2)       hit = True     the query works

`lv_crate`'s box is 1.20 tall — well under the agent's 2.0 — and it still leaves **no walkable
surface at its footprint**. The bake carves a real hole regardless of collider height.
`NavMesh.CalculatePath` corner lists in the same run show routes detouring around furniture
correctly.

**So there is no NavMesh-carving defect, and no 45-prefab bulk change is needed for navigation
reasons.** Anything that still looks like "the enemy will not walk around the furniture" has a
behavioural cause, not a baking one — see `ENEMY_PURSUIT_AND_THE_LEASH.md`.

Two lessons worth keeping, because both cost real time:

- **The one existing carve test proves the wrong size.**
  `Tests/NavigationSpawnerPlayModeTests.cs:242` `Spawn_CarvesAroundASolidCollider` builds a
  **2 x 2 x 2** box — exactly the agent height — and asserts the path around it has more than two
  corners. It is a good test and it says nothing whatever about the 29 sub-agent-height props.
  A suite can be green, and correct, and blind to the entire population you care about.
- **I reasoned about a voxel bake from first principles and got it backwards.** `CLAUDE.md` already
  says this for art — *dimensions are not the artefact, render it and look*. It is just as true for
  a NavMesh: **bake it and query it.** One `SamplePosition` call settled what two rounds of
  argument could not.

---

## 3. Why the *player* does not walk around obstacles — and it is not the colliders

Measured in `Scripts/PlayerMovement.cs` and `Resources/Player/Player.prefab`:

- `PlayerMovement.cs` contains the string `NavMesh` **zero times**.
- `Player.prefab` carries **1 `CharacterController` and 0 `NavMeshAgent`**.
- `TickDestinationMovement` steers straight at the click point:
  `horizontal = toDestination.normalized * moveSpeed`, then `controller.Move(...)`.
- `PlayerMovement.cs:13-18` declares the give-up rule outright:

      private const float BlockedDestinationTimeout = 0.2f;
      // A clicked destination can be unreachable because CharacterController collision
      // prevents the wizard from making forward progress. Do not keep an unreachable
      // destination alive forever ...

**The player has no pathfinding at all.** He walks in a straight line, slides along whatever he
hits, and after 0.2 s of side-collision with no forward progress the destination is discarded.
That is exactly what Vincent described, and the prop colliders are doing their job perfectly while
it happens.

This is behaving as written. It is **not** behaving as Vincent wants, and his report outranks the
comment: a code comment saying a behaviour is intentional is not evidence that it is correct.
Giving the wizard a NavMesh path (he already has a baked surface and the enemies already use it) is
a real feature change, not a repair, and it needs its own task.

---

## 4. The sight/projectile layer policy, and where the prefabs disagree with it

`Scripts/SightOcclusionLayers.cs` defines one shared rule for every sight and projectile line in
the game:

> *Knee-high dressing props sit on the `LowDressing` layer (`ProjectSettings/TagManager.asset`,
> layer index 8): their colliders still block movement unchanged, but a sight or projectile query
> must never stop on them. Landmark-scale props at or above eye height are left on the `Default`
> layer and keep blocking both.*

`EyeOffset` is `Vector3.up`, i.e. **1.0 unit**, and the comment calls it chest height.
`TagManager.asset` index 8 is indeed `LowDressing`. The prefabs use only layers 0 and 8 — the
policy is wired, not aspirational. Measured against the 1.0 threshold:

| | count |
|---|---|
| `Default`, collider >= 1.0 tall — blocks sight, matches policy | 10 |
| `Default`, collider < 1.0 tall | **0** |
| `LowDressing`, collider < 1.0 tall — matches policy | 6 |
| `LowDressing`, collider **>= 1.0** tall — does *not* match the policy text | **25** |
| no collider | 4 |

So 25 props let sight and fireballs through while physically blocking movement, including
`shared_rubble_pile_a` at 2.33 tall and `re_landmark_guardian_statue_broken` at 1.80. The props
were evidently classified by *category* (dressing versus landmark) rather than by the height the
policy names.

**Whether that is a defect is a design question, not a measurement.** A permissive sight rule may
well be the better game. What is certainly wrong is that **the policy text and the prefabs
disagree and nothing checks the relation**: `PropPrefabVerifier` validates the sprite reference,
the sorting layer, the sorting order, the sort point, the collider's presence, its trigger flag and
its extents — and **never reads `gameObject.layer`**. Either the text or the prefabs should move,
and then a verifier clause should hold them together.

---

## What is not proven

- **What the walk-through trigger in Vincent's `chest.prefab` is for.** His pairing is recorded;
  its purpose is not. `chest.prefab` is not in this repository.
- **What "different" means** in *"All the colliders needed to be different"*. The square-prism
  finding in §1 and the pair model are the two candidates. Neither is confirmed as his intent.
- **Whether the 25 over-eye-height `LowDressing` props are wrong**, or the policy sentence is.
- **Whether every prop carves** — two were sampled (one short, one tall), not 41.
- **Whether the collider erosion around a prop is comfortable to walk past.** The holes exist;
  nobody has measured whether the 0.5 agent radius plus a square footprint leaves aisles the width
  the rooms were laid out for.

## Who owns what

| | owner |
|---|---|
| prop prefab collider shape and layer | Game Agent (the prefabs are authored text, not build output) |
| whether props block sight | design — Vincent, then the contract |
| prop *art* and its `.meta` import settings | Art Director |
| the NavMesh bake and spawn phases | Game Agent |
| giving the player a path | needs a task; Game Agent once scoped |

## What would falsify this document

- **The carving refutation**: re-run `NavMesh.SamplePosition` on a prop footprint in the
  assembled world. If it returns a hit, props have stopped carving and section 2 is wrong -
  most likely because the spawn phase order changed or a prop lost its collider.
- **The collider census**: re-count `m_Size.x == m_Size.z` across `Resources/Props/*.prefab`. If
  it is no longer 41 of 41, the square-prism finding has been partly fixed and the numbers here
  are stale.
- **The layer mismatch**: re-count props on layer 8 with a collider taller than
  `SightOcclusionLayers.EyeOffset`. If it is no longer 25, either the prefabs or the policy moved.
- **The player half**: if `PlayerMovement.cs` ever contains `NavMesh`, section 3 is obsolete.
