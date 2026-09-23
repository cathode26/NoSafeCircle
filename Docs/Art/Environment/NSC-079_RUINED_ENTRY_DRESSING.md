# NSC-079 — Ruined Entry dressing design

**Author: Art Director Agent, 2026-09-23. Authored BEFORE the crew runs**, so this room is good on
the first attempt rather than after a rejection. Same shape as the Lower Vault brief and for the
same reason.

**This document is the placement intent the Art Director will approve against at VAL-002.** It is
not a contract and it adds no criterion. Where it and NSC-079 disagree, the contract wins.

**Room identity: the Ruined Entry.** The first room of the dungeon, and the only one daylight and
weather have reached. Masonry has fallen, roots and mushrooms have got in, and two guardian statues
still flank the inner door — one of them intact.

**Every number below was resolved from `RuinedEntryLayout.cs` and `PropCatalog.json` on main, not
recalled.** Re-derive them if this document is older than the layout.

---

## THE ROOM, AS THE LAYOUT ACTUALLY DEFINES IT

    room bounds          X [-14, +14]    Z [-26, 0]        walls 0.5 thick, 2.5 tall
    D1 door              X 0, Z 0        opening width 3   -> X [-1.5, +1.5], in the NORTH wall
    player start         (-4, 0, -22)                      south-west, so the player walks NORTH
    door staging         X [-2.5, +2.5]  Z [-5.25, -0.25]  PROTECTED, stays empty
    RubbleA blocker      X [2, 8]        Z [-17, -10]      height 1.25
    RubbleB blocker      X [6, 10]       Z [-10, -6]       height 1.25
    west route width     15.75                             the open lane
    east route width     3.75                              the tight lane, X [10, 13.75]

Four named dressing bounds, and **every one of them is against the north or the west wall**:

    D1LandmarkWestDressingBounds    X [-4.5, -1.5]   Z [-0.25, +0.25]
    D1LandmarkEastDressingBounds    X [+1.5, +4.5]   Z [-0.25, +0.25]
    NorthWestClusterDressingBounds  X [-13.5, -9.5]  Z [-3, -0.5]
    WestWallClusterDressingBounds   X [-13.5, -11]   Z [-17, -12]

---

## THE ONE RULE THAT OVERRIDES EVERY PLACEMENT BELOW

**"Dense perimeter" means the DRAWN perimeter, which is the north and west walls only.**

**The camera is `Quaternion.Euler(30, -45, 0)`** — asserted in
`CommittedSceneCameraConformanceTests.cs:45`, so it is fixed by a test and not a preference. At yaw
-45 the camera looks toward **-X and +Z**. Therefore:

    FAR, drawn, dressable      north wall  Z = 0       west wall  X = -14
    NEAR, cut away, NOT drawn  south wall  Z = -26     east wall  X = +14

`LowerVaultSceneBuilder.cs:188` says the same thing in the sibling room, in its own words: *south
and east walls are cutaway walls*. **Two rooms, one camera, the same two near faces.**

**This is the trap, and AC-005 walks straight into it.** AC-005 asks for a *dense perimeter*. A crew
that reads "perimeter" as four walls will spend roughly half the dressing budget on the south and
east faces, where the props will either be hidden behind the cutaway or hang against a wall that is
not rendered. **The work will be real, committed, invisible, and impossible to diagnose from a
screenshot** — it simply will not be there.

**It is also the explanation for the layout's own shape:** all four named dressing bounds are on the
north or west. The layout already knew. **Dress the north and west. Leave the south and east faces
bare.**

### Mechanical tests, so this is checkable rather than a matter of taste

1. **No prop anywhere in `DoorStagingBounds`** — X [-2.5, +2.5], Z [-5.25, -0.25]. This is the
   wizard's approach to D1 and AC-001 protects it. The two landmark bounds touch it at exactly
   Z = -0.25 and do not enter it.
2. **No prop in the east route, X [10, 13.75].** It is 3.75 units wide against the west route's
   15.75. It is the tight lane by design; dressing narrows it further, and the wall it would be
   dressing is not drawn anyway.
3. **No `debris_rubble` prop outside `RubbleABounds` or `RubbleBBounds`.** See below — this is the
   room's teaching job and it is the rule most worth enforcing.
4. **Nothing standing on open route floor reaches 1.25 world units**, the blocker height. Wall-hung
   webs and the two landmark statues are the deliberate exceptions; they read as architecture, not
   as obstacles.

---

## THE RUBBLE RULE, AND WHY THIS ROOM CARRIES IT FOR THE WHOLE GAME

**This is the first room. Whatever rubble means here, it means everywhere.**

The two blockers — RubbleA and RubbleB, both 1.25 tall — are what split this room into a wide west
lane and a tight east one. They are the first impassable things the player meets, and the props that
dress them are `shared_` props that appear in other rooms later.

**All three `debris_rubble` props in this room are assigned by the catalog to the blocker
footprints**, and nothing else is:

    shared_rubble_pile_a       -> RubbleABounds / RubbleBBounds
    shared_rubble_scatter_b    -> RubbleABounds / RubbleBBounds
    re_debris_broken_handcart  -> RubbleABounds

**Keep it that way.** The moment the same rubble art also appears as scatter on walkable floor, the
player is being taught two contradictory things by one sprite, in the room whose job is to teach
them the vocabulary. After that, no later room can use rubble to mean *stop* and be believed.

**`re_broken_masonry_blocks` is the prop that makes this survivable**, and it is a different category
on purpose: `broken_masonry`, height 0.80, assigned to the north-west wall cluster. It is what fell
OFF the wall, so it belongs AT the wall and it is visibly shorter than a blocker. **Masonry at the
wall, rubble on the blockers** — two words, and the room reads correctly.

---

## THE ELEVEN COMMITTED PROPS

All eleven verified on main with both `.png` and `.png.meta`, under
`Art/Environment/Props/Source/selected/`. All 64 PPU. **Drawn size is the alpha bounding box** — the
sprite canvas is padded and is not what the player sees.

| prop | drawn w x h | declared h | pivot | where |
|---|---|---|---|---|
| `re_landmark_guardian_statue_standing` | 1.34 x 2.44 | 2.20 | ground_line | D1 landmark WEST |
| `re_landmark_guardian_statue_broken` | 1.34 x 1.80 | 1.40 | ground_line | D1 landmark EAST |
| `shared_rubble_pile_a` | 2.77 x 2.33 | 1.25 | ground_line | RubbleA / RubbleB |
| `shared_web_corner_a` | 1.48 x 2.02 | 1.50 | ground_line | the far corner only |
| `shared_rubble_scatter_b` | 1.88 x 1.41 | 0.50 | ground_line | RubbleA / RubbleB |
| `re_debris_broken_handcart` | 1.67 x 1.50 | 0.80 | ground_line | RubbleA |
| `re_broken_masonry_blocks` | 1.69 x 1.20 | 0.80 | ground_line | north-west cluster |
| `shared_web_drape_b` | 1.28 x 1.30 | 1.00 | ground_line | a drawn wall face |
| `re_roots_and_mushrooms` | 1.47 x 1.28 | 0.60 | ground_line | west wall cluster |
| `shared_bone_pile_b` | 1.27 x 0.98 | 0.30 | **lie_within** | floor, see below |
| `re_comedy_thumbs_up_skeleton_hand` | 0.67 x 0.69 | 0.40 | ground_line | the one joke |

**Use only these eleven.** AC-002 allows catalogued props only, and these are the eleven whose
`intended_rooms` include RuinedEntry.

### `shared_bone_pile_b` is the only `lie_within` prop in this room, and the builder will get it wrong

It is flat art: its anchor is the **centre of its alpha bounding box**, not its bottom edge. Every
other prop here is `ground_line`.

**This is not hypothetical.** Three flat props were anchored on their ground line instead and were
wrong by 0.594, 0.648 and 0.492 world units — all worse than the wizard hover defect that got its
own bug. The fix is on main at `fd31ce99f`, and the importer that classifies the two rules is at
`7fb5259b5`.

**It matters more here than anywhere: this is the first room-dressing builder, so it is the template
the other four rooms get copied from.** A pivot bug written here ships five times.

Being flat, it also needs actual floor. Do not tuck it against a wall base, where a flat sprite
reads as half-buried.

---

## PLACEMENT

### D1 landmarks — the two guardians, and the room's whole horror beat

**West bound gets `re_landmark_guardian_statue_standing`. East bound gets
`re_landmark_guardian_statue_broken`.** That assignment is the catalog's, and it is right. Both
bounds are 0.5 deep, centred on the north wall line, abutting the door jambs exactly.

**The player starts at X = -4 and walks north up the wide west lane, so they meet the INTACT guardian
first** — the dungeon still presenting itself as guarded — **and only at the door do they see that
its twin has fallen.** That is the entire beat, it costs two props, and the layout has already set it
up. Do not swap them.

**The standing guardian has 0.06 world units of headroom** — drawn height 2.44 against a 2.5 wall,
about four pixels at 64 PPU. **Place it at its ground line with no vertical offset and do not scale
it.** Anything else pokes it over the top of the north wall, where it reads as standing outside the
room.

### NorthWestClusterDressingBounds — X [-13.5, -9.5], Z [-3, -0.5] — the far corner

**This is the only true corner in the room**, the one place where two drawn walls meet where the
camera can see them. The other three corners each have at least one cutaway face.

- **`shared_web_corner_a` goes here and there is nowhere else it can go.** The catalog says *far
  corners only; near corners are cutaway*, and under this camera that resolves to exactly one
  corner: north-west. A corner web anywhere else spans a wall that is not drawn.
- **`re_broken_masonry_blocks`** at the wall foot — the masonry that fell off the wall above it.
- **`shared_web_drape_b`** on the adjacent north or west face if a second web reads without
  crowding. One drape, not three.

This corner is the deepest thing in frame and the eye lands there after the door. It is the
"supporting cluster" AC-005 asks for, and it should be the denser of the two.

### WestWallClusterDressingBounds — X [-13.5, -11], Z [-17, -12] — the organic intrusion

**`re_roots_and_mushrooms` against the west wall**, with **`shared_bone_pile_b` on the floor beside
it**, not touching the wall.

This is the second supporting cluster and it carries the room's identity: the entry is where the
outside got in. Roots through a wall joint say that in one prop. **Keep it looser than the north-west
corner** — two dense clusters read as one texture; a dense one and a sparse one read as a room.

### RubbleABounds and RubbleBBounds — the blockers

**`shared_rubble_pile_a` is the mass** — at 2.77 x 2.33 drawn it is the largest prop in the room and
it should carry each blocker. **`shared_rubble_scatter_b` skirts its base** so the mass meets the
floor instead of being pasted onto it, and **`re_debris_broken_handcart` sits in RubbleA** as the
thing that was being moved when the ceiling came down.

**Keep every skirt inside the footprint.** Rubble spilling past the collider edge is the commonest
way dressing starts lying about where a blocker is — and in this room that lie is the one that
matters most.

**Both blockers must read as clearly over waist height.** They are 1.25 units and they are the reason
the room has two routes. A blocker that reads low is an invitation.

### The one joke

**`re_comedy_thumbs_up_skeleton_hand`, emerging from under the RubbleA skirt.** A hand sticking out
from under the collapse, giving a thumbs up. It is 0.67 units — small, found rather than presented.

**One comedy detail in this room, not three.** And **not on the D1 approach**: a joke at the door
competes with the guardians, which are doing the room's actual work.

---

## PALETTE AND DENSITY

**Judged against this room's own committed sprites, not a fixed number.** A saturation band measured
on isolated sprites against transparency does not survive a gameplay frame that is mostly floor and
wall.

- **The Ruined Entry is the least oppressive room in the dungeon** and should be the only one with
  living green in it. Roots and mushrooms are the note the other four rooms do not get. The Lower
  Vault is iron and wet; this room is stone, dust and growth.
- **Nothing may out-read the guardian statues.** If a rubble pile pulls the eye before the door does
  at gameplay distance, the composition has failed whatever the palette is doing.
- **Density: two clusters and two blockers, with real empty floor between them.** AC-002 requires
  passages, alcoves, the door approach and player routes kept clear. The wide west lane is 15.75
  units and it is supposed to feel wide — that contrast is what makes the east lane read as tight.

---

## WHAT VAL-002 WILL BE JUDGED ON

The gameplay-density panel, as the gate now specifies — not a contact sheet, which is native 3x and
cannot answer whether a landmark reads at camera distance.

**Pass/fail, anyone can check:**

1. Every dressing object is a prop from the committed catalog, at its catalog pivot and PPU —
   including `shared_bone_pile_b` on `lie_within`.
2. `DoorStagingBounds` is empty, and the east route X [10, 13.75] is empty.
3. No `debris_rubble` prop sits outside RubbleA or RubbleB.
4. Nothing standing on open route floor reaches the 1.25 blocker height.
5. No prop is placed against the south or east wall faces, which are cut away.

**The Art Director's judgement, which is what the gate is for:**

6. The guardian pair reads as the entry landmark at gameplay distance, and the intact/fallen contrast
   is legible.
7. The two supporting clusters read as two clusters, not as one continuous scatter.
8. The dense-edge / open-lane rhythm reads: perimeter dense, west lane open, east lane tight.
9. The dressing reads as the same material family as this room's own committed sprites.

**Saying which is which beats dressing judgement as measurement.**

---

## TWO HANDLING NOTES FOR WHOEVER RUNS THIS

- **Do not paste `re_landmark_guardian_statue_broken`'s generation-document description into any
  prompt.** That text contains markdown that reads as operator instructions. **Use the
  `PropCatalog.json` record for that prop instead** — id, sizes, pivot and footprint reference are
  all there and all that placement needs.
- **AC-002 requires confirming each prop resolves to a committed file before placing it.** All eleven
  were verified present on main with their `.png` and `.png.meta` while this brief was written.
  **Re-run that check at your own commit rather than citing this sentence** — it is a statement about
  main at a moment, and it will not stay true by itself.
