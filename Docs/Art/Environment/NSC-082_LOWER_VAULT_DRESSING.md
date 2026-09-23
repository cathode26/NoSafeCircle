# NSC-082 — Lower Vault dressing design

**Author: Art Director Agent, 2026-09-23. Authored BEFORE the crew runs, so the first dressed
room in this project is good on the first attempt rather than after a rejection.**

**This document is the placement intent the Art Director will approve against at VAL-002.** It
is not a contract and it adds no criterion. Where it and NSC-082 disagree, the contract wins.

**Room identity: the Broken Sluice Crossing** (NSC-082 INT-002). A drainage vault that failed.
Water and slime came through, and what is left is the machinery that could not hold it and the
debris the flow pushed around.

---

## THE ONE RULE THAT OVERRIDES EVERY PLACEMENT BELOW

**Nothing may read as walkable that is not walkable.** NSC-047's committed layout contains no
bridge, no island, no crossing and no change of elevation the player can use, and AC-005 says the
art must not out-promise the geometry.

**The trap is specific and it is not hypothetical: the two props INT-002 names by function —
"raised-route or rail language" and the broken ledge — are exactly the two most likely to break
this rule.** A rail drawn ACROSS a hazard is a bridge. A ledge chunk sitting ALONE inside a hazard
span is a stepping stone. Both read as walkable to any player, and neither is.

So, as absolute placement constraints:

1. **`lv_iron_rail_x` and `lv_iron_rail_z` run ALONGSIDE a hazard edge, never across it.** A rail
   is a barrier that says *do not step here*. Orient each rail so its long axis is PARALLEL to the
   hazard boundary it guards. **No rail may have hazard on both sides of it.** That single test is
   mechanical and catches every bridge reading.
2. **`lv_broken_ledge_chunk` touches the hazard EDGE and overlaps solid ground.** It is masonry
   that fell in and half-sank, not a stepping stone. **No ledge chunk may be surrounded by hazard
   on all sides**, and no two chunks may be placed in a line across a span — two chunks in a row
   across slime is a path, whatever each one looks like alone.
3. **Depth cues stay below eye height.** No prop may be raised off its ground line to suggest a
   platform. Every prop in this room is `pivot_rule: ground_line` and sits on its drawn base.

---

## THE TEN COMMITTED PROPS, and what each one is FOR here

All ten are on main with `.png` and `.png.meta`, all `ground_line`, all 64 PPU. World size is
`pixels / 64`.

| prop | px | world | role in this room |
|---|---|---|---|
| `lv_landmark_sluice_wheel_gate_x` | 216x216 | 3.38 x 3.38 | **the landmark.** The machinery that failed |
| `shared_stone_column` | 144x216 | 2.25 x 3.38 | vertical mass; collapsed structure |
| `shared_rubble_scatter_b` | 144x104 | 2.25 x 1.63 | spill of debris; reads as a heap with a front base |
| `lv_broken_ledge_chunk` | 124x112 | 1.94 x 1.75 | masonry that fell INTO the runoff |
| `lv_sluice_slime_spill` | 124x112 | 1.94 x 1.75 | the runoff itself |
| `lv_iron_rail_x` | 116x116 | 1.81 x 1.81 | barrier, world-X run |
| `lv_iron_rail_z` | 116x116 | 1.81 x 1.81 | barrier, world-Z run |
| `lv_crate` | 100x112 | 1.56 x 1.75 | stored goods, stacked |
| `lv_barrel` | 84x100 | 1.31 x 1.56 | stored goods |
| `lv_comedy_barrel_striped_socks` | 84x108 | 1.31 x 1.69 | **the horror-comedy detail** |

**Use only these ten.** AC-002 says catalogued props only, and these are the ten whose
`intended_rooms` include LowerVault. Reaching for another room's prop breaks the family read this
room is being judged on.

---

## PLACEMENT BY NAMED FOOTPRINT

NSC-047 requires the dressing prefab to carry collider-free SpriteRenderer proxies for LV-C1,
LV-W1, LV-E1, LV-N1 and each LV-H1 span. **The dressing's job is to make those blockers look like
reasons.** A blocker the player cannot see is a bug; a blocker they can see and understand is the
room working.

### LV-C1 — X [-4,+2] — THE LANDMARK GOES HERE

**`lv_landmark_sluice_wheel_gate_x`, centred on the footprint.** LV-C1 must intersect the straight
D3-to-D4 sight line (NSC-047), so it is the first thing seen on entry and the thing the whole room
is composed around. At 3.38 world units on a 6-unit-wide footprint it reads as a landmark without
filling the block.

**Skirt it with `shared_rubble_scatter_b`** at the base, on the D3-facing side, so the mass meets
the floor instead of being pasted onto it. **Keep the skirt inside the footprint** — rubble spilling
past the collider edge is the commonest way dressing starts lying about where the blocker is.

**The landmark is the anchor of the alternate-approach read.** AC-005 wants a readable alternate
approach around LV-C1, and the layout provides two ~5.0-unit lanes, LV-C1/LV-W1 and LV-C1/LV-E1.
**Both lanes stay visually open: no prop may occupy a lane centre.** Dress the lane EDGES so the
eye is led down them — that is the whole compositional job, and it is what "compose so the eye is
drawn along the route the layout actually provides" means in practice.

### LV-W1 — X [-12,-8] — storage that failed

**`lv_crate` and `lv_barrel`, stacked against the west side, plus `lv_comedy_barrel_striped_socks`
tucked at the back of the group.** Storage pushed aside by water.

**The comedy prop goes here and nowhere else.** It is a barrel wearing striped socks. It has to be
findable but not the first thing seen from D3 — a joke that lands on entry competes with the
landmark. Put it where a player who looks around the west side finds it and smiles. **One comedy
detail in the room, not three.**

### LV-E1 — X [+7,+12] — collapse

**`shared_stone_column` fallen or leaning, with `shared_rubble_scatter_b` at its base.** At 3.38
units tall it balances the landmark across the room without competing — the column is structure
that lost, the landmark is machinery that lost.

**Do not stand the column upright and clean.** An intact column reads as architecture the room was
built with; this room's story is that everything here failed.

### LV-N1 — X from -19.5, joining the west and north inner wall faces

**This footprint exists to stop a second south-to-north path, and it is the one where a wrong read
is most expensive.** If the dressing makes it look like a gap, the player will try to walk it.

**Dress it as continuous collapsed structure — `shared_rubble_scatter_b` and the second
`shared_stone_column` if one is spare — reading as a wall that fell, unbroken from the west wall
face to LV-H1-WestCollision.** No visual gap anywhere along it. **Any gap in the dressing here is
an implied doorway.**

### LV-H1 spans — West X [-15,-6.5], Centre from -6.5, East X [+12,+19.5] — the hazard

**`lv_sluice_slime_spill` is the primary material.** Lay it along each span so the runoff reads as
one connected flow that entered from the failed sluice gate and pooled — the room's whole identity
in one prop.

**`lv_iron_rail_x` on the east and west spans, `lv_iron_rail_z` where a span runs north-south**,
each ALONGSIDE the span edge on the WALKABLE side, guarding it. **Hazard on one side only. Never
both.**

**`lv_broken_ledge_chunk` at the span edge, overlapping solid ground, half in the slime.** One
chunk per span at most. **Never centred in a span, never two in a line across one.**

**Irregular runoff edge** (INT-002): vary where the slime meets the floor rather than laying a
straight band. A straight edge reads as a designed channel with a kerb — which implies a kerb you
could walk.

---

## PALETTE AND DENSITY

**Judged against this room's own committed sprites, not a fixed number.** A band measured on
isolated sprites against transparency does not transfer to a gameplay frame that is mostly floor
and wall — the whole frame will read differently and should.

- **Iron and wet stone is the Lower Vault's character**, set by `lv_iron_rail_z`'s grey-blue iron
  with rust. The slime is the only place saturation should rise, and it should be the most
  saturated thing in the frame **by a visible margin** — that is what marks it as the hazard.
- **Nothing in the dressing should be brighter than the landmark.** If a barrel out-reads the
  sluice gate at gameplay distance, the composition has failed regardless of the palette.
- **Density: clusters, not a scatter.** Group props at the footprints and leave the lanes and the
  D3/D4 approaches genuinely empty. AC-002 requires passages, alcoves, door approach and player
  routes kept clear, and empty floor next to a dense cluster is what makes the cluster read.

---

## WHAT VAL-002 WILL BE JUDGED ON

The gameplay-density panel, not a 3x contact sheet — a contact sheet cannot answer whether a
landmark reads at camera distance.

1. Every dressing object is a prop from the committed catalog, at its catalog pivot and PPU.
   **Objective; anyone can check it.**
2. The sluice gate reads as a landmark at gameplay distance, not as another cluster.
3. The dressing reads as the same material family as this room's own committed sprites.
4. The hazard reads as hazard and the two lanes around LV-C1 read as passable.
5. **Nothing in the frame depicts a walkable surface at another elevation, a span across a gap, or
   a step up.** Checked against the committed layout; not a matter of taste.

**1 and 5 are pass/fail. 2, 3 and 4 are the Art Director's judgement, which is what the gate is
for.** Saying which is which beats dressing judgement as measurement.
