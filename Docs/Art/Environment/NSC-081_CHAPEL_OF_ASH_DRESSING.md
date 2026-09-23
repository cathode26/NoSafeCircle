# NSC-081 — Chapel of Ash dressing design

**Author: Art Director Agent, 2026-09-23. Authored BEFORE the crew runs.** Third of five. Same
shape as the Lower Vault and Ruined Entry briefs.

**This document is the placement intent the Art Director will approve against at VAL-002.** It is
not a contract and adds no criterion. Where it and NSC-081 disagree, the contract wins.

**Room identity: the Chapel of Ash.** A place of worship that burned and was never cleared. The
pews are still in their rows, the bell frame is cracked, and everything is under ash.

**Every number below was resolved from `ChapelOfAshLayout.cs` and `PropCatalog.json` on main.**

---

## THE ROOM, AS THE LAYOUT DEFINES IT

    room bounds        X [-12, 12]   Z [20, 42]      walls 0.5 thick, 2.5 tall
    inner faces        X [-11.75, 11.75]   Z [20.25, 41.75]
    D2  ENTRY          (6, 20)   width 3  -> X [4.5, 7.5]    in the SOUTH wall
    D3  EXIT           (-6, 42)  width 3  -> X [-7.5, -4.5]  in the NORTH wall
    central aisle      X [-2, +2]          CentralAisleWidth 4
    pews  (8 blocks)   west X [-8.5, -3]   east X [3, 8.5]   height 1.25
                       Z rows 24-25.5, 28-29.5, 32-33.5, 36-37.5
    columns (4)        centres (-8.5, 27) (8.5, 27) (-8.5, 35) (8.5, 35)
                       size 1.5 -> X spans [-9.25, -7.75] and [7.75, 9.25], height 2.5
    cover pockets      WEST (-10.5, 31)    EAST (10.5, 35)
    side routes        2.50 each           MinimumSideRouteClearance is 2.50

**The player crosses diagonally: in at D2 in the south-east, out at D3 in the north-west.**

---

## THE ONE RULE THAT OVERRIDES EVERY PLACEMENT BELOW

**Nothing on the aisle floor may read as an obstacle or a hazard.**

This is the inverse of the Lower Vault's rule and it is the right one here. The aisle X [-2, +2] is
the only generous route through the room — the two side routes are at **exactly 2.50**, the
declared minimum. **If the aisle reads as blocked or dangerous, the room's only good path is the
one players avoid.**

**The specific trap: `ca_sigil_floor_mark` is `lie_within`, height 0.00, and the aisle is where it
belongs.** A sigil burned into the floor is right for this room. A sigil that reads as a pit, a
grate or an active hazard is the whole room misfiring. **It must read as marking, not as depth.**

### Mechanical tests

1. **Nothing in the aisle X [-2, +2] except `ca_sigil_floor_mark`.** Nothing standing, nothing
   with height.
2. **No prop may reduce either side route below 2.50.** West route is inner face X -11.75 to the
   column face at -9.25; east is 9.25 to 11.75. **Both are already AT the minimum — there is no
   margin to spend.**
3. **The two cover pockets stay open** — WEST (-10.5, 31) and EAST (10.5, 35). They are gameplay
   features. Dressing may frame a pocket; it may not fill one.
4. **No prop against the south or east wall faces.** See below.
5. **Door approaches at D2 and D3 stay clear** — X [4.5, 7.5] at the south and X [-7.5, -4.5] at
   the north, for at least 2 units in front of each.

---

## DRESSABLE WALLS: NORTH AND WEST ONLY

**The camera is `Quaternion.Euler(30, -45, 0)`**, asserted at
`CommittedSceneCameraConformanceTests.cs:45` — fixed by a test. At yaw -45 it looks toward -X and
+Z, so:

    FAR, drawn, dressable      north wall  Z = 42      west wall  X = -12
    NEAR, cut away, NOT drawn  south wall  Z = 20      east wall  X = +12

`LowerVaultSceneBuilder.cs:188` says the same in the sibling room. **Props placed against the south
or east faces are work that is never rendered** — committed, invisible, and undiagnosable from a
screenshot afterwards.

**Note what that means here, because it is unusual: the ENTRY door D2 is in the cutaway south
wall.** The player walks in through a wall that is not drawn. **Do not try to dress the entry
threshold.** The room's first impression is made by what it shows across the floor, not by a
framed doorway.

**The far corner is north-west (-12, 42)**, and it is the only corner where two drawn walls meet.
**`shared_web_corner_a` goes there and nowhere else** — the catalog says *far corners only; near
corners are cutaway*, and the other three corners each have a cutaway face, so a corner web there
spans a wall that is not drawn. D3 sits at (-6, 42), so this corner is in view on the way out.

---

## THE THIRTEEN COMMITTED PROPS

All 64 PPU. **Drawn size is the alpha bounding box.**

| prop | drawn w x h | declared h | pivot | role |
|---|---|---|---|---|
| `ca_landmark_cracked_bell_frame_x` | 2.03 x 3.11 | 2.50 | ground_line | **the landmark** |
| `shared_stone_column` | 1.31 x 3.02 | 2.50 | ground_line | the four columns |
| `ca_candelabra_tall` | 0.84 x 2.11 | 2.00 | ground_line | vertical accent |
| `shared_web_corner_a` | 1.48 x 2.02 | 1.50 | ground_line | far corner only |
| `ca_pew_x_start` | 2.08 x 2.14 | 1.25 | ground_line | **segment: start** |
| `ca_pew_x_middle` | 1.78 x 1.77 | 1.25 | ground_line | **segment: middle** |
| `ca_pew_x_end` | 1.95 x 1.80 | 1.25 | ground_line | **segment: end** |
| `ca_altar_ash_bowl_x` | 1.66 x 1.97 | 1.20 | ground_line | the altar |
| `shared_candle_cluster_a` | 0.89 x 1.02 | 0.60 | ground_line | small light |
| `shared_bone_pile_a` | 1.19 x 1.02 | 0.50 | ground_line | remains |
| `ca_ash_heap` | 1.42 x 0.97 | 0.40 | ground_line | the room's material |
| `ca_comedy_offering_plate_sock` | 0.66 x 0.53 | 0.20 | ground_line | the one joke |
| `ca_sigil_floor_mark` | 2.09 x 1.19 | 0.00 | **lie_within** | the aisle |

### Drawn height above wall height is NOT a defect by itself

The bell frame (3.11) and the column (3.02) are drawn taller than the 2.5 wall. **That is expected
and is not a reason to shrink them.** `footprint_world_size.h` is the *occluding* height; the drawn
sprite is taller because isometric art folds the object's depth into its vertical extent. Walls are
tile-built and axis-aligned; props are not, so the two numbers are not directly comparable.

**Where it matters, check it in the VAL-002 panel rather than in the catalog.** Do not "fix" it by
scaling a prop — that breaks the pixel grid at 64 PPU and is worse than the thing it corrects.

### `ca_sigil_floor_mark` is the only `lie_within` prop here

Its anchor is the **centre of its alpha bounding box**, not its bottom edge. Every other prop in
this room is `ground_line`. **Three flat props were anchored wrong by 0.49–0.65 world units before
this was caught**; the fix is on main at `fd31ce99f` and the classifying importer at `7fb5259b5`.

---

## PLACEMENT

### The pews — the room's structure, and 24 sprites

**Eight footprints, three segments each: `start`, `middle`, `end`, running along X.** Each footprint
is 5.5 units wide and the three drawn widths total about 5.81, so the segments overlap slightly —
**that is correct; a pew run must not show gaps between its own segments.**

**Keep every pew inside its footprint.** Pews are 1.25 tall and they are what makes the aisle an
aisle. A pew spilling into the aisle or the side route is the room lying about its own geometry.

**Vary the rows.** Eight identical runs read as wallpaper. Ash on some, a bone pile beside another,
one row with a segment knocked askew — the story is that people were sitting here.

### The columns — four, at their own footprints

**`shared_stone_column` at each of the four `ColumnCenters`.** They are 2.5 tall and 1.5 square and
they define the side routes. **Nothing may be added between a column and the wall** — that gap is
the 2.50 minimum clearance and it is the whole margin.

### The landmark — `ca_landmark_cracked_bell_frame_x`

**Against the north wall, west of centre, between the aisle and the D3 exit.** It is the largest
prop in the room at 2.03 x 3.11 and it should be the first thing the eye finds from the entry.
Placing it north puts it on the D2→D3 diagonal and against a **drawn** wall.

**Keep it out of the aisle and out of the D3 approach X [-7.5, -4.5].** A landmark that blocks the
exit reads as a wall.

### The altar — `ca_altar_ash_bowl_x`

**At the north end of the aisle, on the aisle's centre line, clear of the D3 approach.** It is the
thing the pews face. **The pews already point at it**: eight rows facing north, an altar at the
north end. That alignment is free and it is the room's whole composition.

### Ash, bone, candles

**`ca_ash_heap` is the room's material — use it most, and use it where the room burned worst.**
Drifted against the west wall and in the corners of the pew blocks, not evenly scattered.

**`shared_candle_cluster_a` sparingly, near the altar and the landmark.** They are the only light
sources; spreading them flattens the room.

**`shared_bone_pile_a` beside pews, not in the aisle.** People died sitting down.

### The one joke

**`ca_comedy_offering_plate_sock` on or beside a pew in the west block, mid-room.** An offering
plate with a single sock in it. It is 0.66 units — found, not presented.

**One comedy detail, not three.** And **not on the altar**: the altar is doing the room's serious
work.

---

## PALETTE AND DENSITY

**Judged against this room's own committed sprites, not a fixed number.**

- **Pale ash is this room's character** — the greys here should be lighter and flatter than the
  Lower Vault's iron and wet, and than the Ruined Entry's stone and growth. **No living green in
  this room.**
- **The candles are the only saturated thing in the frame**, and they should be, by a visible
  margin. That is what makes them read as light.
- **Nothing may out-read the bell frame and the altar.**
- **Density: the pew blocks are dense and regular; the aisle and the side routes are empty.** That
  contrast is the room. Filling the side routes to make them "interesting" destroys both the
  clearance and the composition.

---

## WHAT VAL-002 WILL BE JUDGED ON

The gameplay-density panel, not a contact sheet.

**Pass/fail, anyone can check:**

1. Every dressing object is a prop from the committed catalog, at its catalog pivot and PPU —
   including `ca_sigil_floor_mark` on `lie_within`.
2. The aisle X [-2, +2] carries nothing but the sigil.
3. Neither side route is reduced below 2.50, and both cover pockets are open.
4. No prop is placed against the south or east wall faces, which are cut away.
5. Every pew is inside its own footprint; no pew enters the aisle or a side route.
6. Both door approaches are clear.

**The Art Director's judgement:**

7. The bell frame reads as the landmark at gameplay distance.
8. The pews read as rows facing an altar, not as eight identical blocks.
9. The aisle reads as walkable and inviting, and the sigil reads as marking rather than depth.
10. The dressing reads as the same material family as this room's own committed sprites.
