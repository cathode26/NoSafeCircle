# NSC-080 — Bone Archive dressing design

**Author: Art Director Agent, 2026-09-23. Authored BEFORE the crew runs.** Fourth of five.

**This document is the placement intent the Art Director will approve against at VAL-002.** It is
not a contract and adds no criterion. Where it and NSC-080 disagree, the contract wins.

**Room identity: the Bone Archive.** A library that was still being used when it stopped. Three
tall shelf banks, a reading table that came down, and paper everywhere.

**Every number below was resolved from `BoneArchiveLayout.cs` and `PropCatalog.json` on main.**

---

## THE ROOM, AS THE LAYOUT DEFINES IT

    room bounds        X [-10, 10]   Z [0, 20]       walls 0.5 thick, 2.5 tall
    inner faces        X [-9.75, 9.75]   Z [0.25, 19.75]
    D1  ENTRY          (0, 0)    width 3  -> X [-1.5, 1.5]   in the SOUTH wall
    D2  EXIT           (6, 20)   width 3  -> X [4.5, 7.5]    in the NORTH wall
    ShelfA             X [-6.5, -5]   Z [4, 16]    height 2.5
    ShelfB             X [-1.5, 0]    Z [3, 14]    height 2.5
    ShelfC             X [3.5, 5]     Z [6, 17]    height 2.5
    CollapsedFurnitureBA1   X [0, 1]  Z [9, 11]    height 1.25

**The four lanes the shelves create, computed from those bounds:**

    lane 1   west wall -9.75  -> ShelfA -6.5     3.25
    lane 2   ShelfA -5        -> ShelfB -1.5     3.50    NormalLaneWidth
    lane 3   ShelfB  0        -> ShelfC  3.5     3.50    NormalLaneWidth
    lane 4   ShelfC  5        -> east wall 9.75  4.75

**MinLaneWidth is 2.50, and lane 3 is already there.** `CollapsedFurnitureBA1` occupies X [0, 1] at
Z [9, 11], which eats 1.00 unit out of lane 3 — **3.50 down to 2.50 exactly, at the pinch.**

---

## THE ONE RULE THAT OVERRIDES EVERY PLACEMENT BELOW

**No prop enters a lane. The lanes ARE the room.**

This room is not a space with obstacles in it; it is three walls of shelving with gaps between
them, and the gaps are the entire playable area. **Lane 3 is already at the declared minimum of
2.50 where the collapsed table pinches it.** Any prop added there makes the room narrower than its
own layout says it may be.

**This is the most constrained of the five rooms and the easiest to over-dress**, because a library
invites clutter and the clutter has nowhere to go that is not a route.

### Mechanical tests

1. **Nothing standing in lanes 1–4.** Dressing goes **on the shelf footprints**, **against the
   drawn walls**, or in the **open strips** north and south of the shelves.
2. **Nothing at all in lane 3 between Z 9 and 11** — that span is at 2.50 and has no margin.
3. **The D1 approach X [-1.5, 1.5] stays clear** for at least 2 units north of the south wall, and
   the D2 approach X [4.5, 7.5] for at least 2 units south of the north wall.
4. **No prop against the south or east wall faces.** See below.
5. **Flat props go on floor, not against a shelf base.**

### Where dressing legitimately goes

    open south strip    Z [0.25, 3]      below ShelfB's start, across the room
    open north strip    Z [17, 19.75]    above ShelfC's end, across the room
    shelf footprints    the three banks themselves
    drawn walls         north Z = 20, west X = -10

---

## DRESSABLE WALLS: NORTH AND WEST ONLY

**The camera is `Quaternion.Euler(30, -45, 0)`**, asserted at
`CommittedSceneCameraConformanceTests.cs:45`. At yaw -45 it looks toward -X and +Z:

    FAR, drawn, dressable      north wall  Z = 20      west wall  X = -10
    NEAR, cut away, NOT drawn  south wall  Z = 0       east wall  X = +10

`LowerVaultSceneBuilder.cs:188` says the same in the sibling room. **Props against the south or
east faces are never rendered.**

**The ENTRY door D1 is in the cutaway south wall** — do not dress the entry threshold.

**The far corner is north-west (-10, 20)**, the only corner where two drawn walls meet.
**`shared_web_corner_a` goes there and nowhere else.**

---

## THE TWELVE COMMITTED PROPS

All 64 PPU. **Drawn size is the alpha bounding box.**

| prop | drawn w x h | declared h | pivot | role |
|---|---|---|---|---|
| `ba_shelf_bank_z_start` | 1.69 x 2.86 | 2.50 | ground_line | **segment: start** |
| `ba_shelf_bank_z_middle` | 1.66 x 2.73 | 2.50 | ground_line | **segment: middle** |
| `ba_shelf_bank_z_end` | 1.72 x 2.78 | 2.50 | ground_line | **segment: end** |
| `ba_landmark_chained_grimoire_lectern` | 2.00 x 2.34 | 2.00 | ground_line | **the landmark** |
| `shared_web_corner_a` | 1.48 x 2.02 | 1.50 | ground_line | far corner only |
| `ba_collapsed_reading_table_z` | 1.83 x 1.67 | 1.25 | ground_line | CollapsedFurnitureBA1 |
| `shared_web_drape_b` | 1.28 x 1.30 | 1.00 | ground_line | a drawn wall face |
| `ba_book_and_scroll_stack` | 0.64 x 1.27 | 0.90 | ground_line | on shelves / strips |
| `ba_spilled_scroll_basket` | 0.92 x 1.09 | 0.60 | ground_line | strips |
| `shared_bone_pile_a` | 1.19 x 1.02 | 0.50 | ground_line | remains |
| `ba_comedy_skull_with_spectacles` | 0.72 x 0.67 | 0.40 | ground_line | the one joke |
| `shared_bone_pile_b` | 1.27 x 0.98 | 0.30 | **lie_within** | floor |

### Drawn height above wall height is NOT a defect by itself

All three shelf segments draw at 2.73–2.86 against a 2.5 wall. **Expected, and not a reason to
shrink them.** `footprint_world_size.h` is the *occluding* height; the drawn sprite is taller
because isometric art folds depth into vertical extent. Walls are tile-built and axis-aligned;
props are not. **Check it in the VAL-002 panel, not in the catalog, and never fix it by scaling** —
that breaks the pixel grid at 64 PPU.

### `shared_bone_pile_b` is the only `lie_within` prop here

Anchor is the **centre of its alpha bounding box**, not the bottom edge. **Three flat props were
anchored wrong by 0.49–0.65 world units before this was caught** — fix on main at `fd31ce99f`,
classifying importer at `7fb5259b5`. It needs real floor, in a strip, not tucked against a shelf
base where a flat sprite reads as half-buried.

---

## PLACEMENT

### The three shelf banks — the room's walls, and most of its sprites

**Each bank runs along Z and takes `start`, repeated `middle`, `end`.** ShelfA is 12 units long,
ShelfB 11, ShelfC 11, and the segments draw about 1.7 each, so each bank needs its two ends plus
enough middles to close the run. **Segments must overlap slightly — a shelf run showing gaps
between its own segments reads as separate bookcases, not a bank.**

**Keep every segment inside its footprint.** The banks are 2.5 tall and they are what makes the
lanes lanes. A shelf spilling into a lane is the room lying about where the player can walk.

**Vary the banks.** Three identical runs read as wallpaper. One bank leaning, one with a collapsed
section, one still tidy — the story is that this place stopped mid-use.

### The collapsed reading table

**`ba_collapsed_reading_table_z` on `CollapsedFurnitureBA1`, X [0, 1], Z [9, 11].** It is the
room's one piece of furniture and it is deliberately the pinch in lane 3.

**Keep it inside its footprint. There is no margin here at all** — one unit of spill makes the lane
illegal. **Nothing may be skirted around it**, which is the habit that would be right anywhere else
in this project and is wrong here.

### The landmark — `ba_landmark_chained_grimoire_lectern`

**In the open north strip, around X [-2, 0], Z ≈ 18.5, against the drawn north wall.** Reasons, in
order:

- **It is seen on entry.** From D1 at (0, 0) the player looks north up lane 3 and the north strip
  closes the view.
- **It is against a drawn wall**, so it has a backdrop rather than floating.
- **It is clear of the D2 exit** at X [4.5, 7.5], so the landmark does not read as blocking the way
  out.
- The strip is 2.75 deep and the lectern draws 2.34 — it fits with room to breathe.

**A chained grimoire is the room's thesis: the archive kept its books by force.** Give it space;
nothing else in that strip within about 2 units.

### Books, scrolls, bones

**`ba_book_and_scroll_stack` on the shelf tops and in the strips** — this is the prop that says the
shelves are full. Use it most.

**`ba_spilled_scroll_basket` in the strips**, tipped, with its contents pointing away from the
basket — spill implies motion, and motion implies something happened.

**`shared_bone_pile_a` and `shared_bone_pile_b` sparingly.** This room is named for bone but it is
a *library*; if bone out-reads paper, it becomes a charnel house and the Chapel of Ash and the
Final Room lose their distinction. **Paper is the material here. Bone is the note.**

### The one joke

**`ba_comedy_skull_with_spectacles` on a shelf, mid-height, in the west bank.** A skull still
wearing its reading glasses. 0.72 units — found by a player who looks along the shelves.

**One comedy detail, not three.** Not beside the lectern.

---

## PALETTE AND DENSITY

**Judged against this room's own committed sprites, not a fixed number.**

- **Bone and paper is this room's character** — warmer and lighter than the Lower Vault's iron and
  wet, drier than the Ruined Entry, and distinct from the Chapel's pale ash by being **yellowed
  rather than grey**.
- **The webs are the only cool note**; keep them to the far corner and one drape.
- **Nothing may out-read the lectern.**
- **Density: the shelf banks are dense; the lanes are empty floor.** That is not a compromise, it
  is the room. **The strips take the dressing the lanes cannot.**

---

## WHAT VAL-002 WILL BE JUDGED ON

The gameplay-density panel, not a contact sheet.

**Pass/fail, anyone can check:**

1. Every dressing object is a prop from the committed catalog, at its catalog pivot and PPU —
   including `shared_bone_pile_b` on `lie_within`.
2. No prop stands in any of the four lanes, and nothing at all sits in lane 3 between Z 9 and 11.
3. Every shelf segment is inside its bank's footprint; the collapsed table is inside
   `CollapsedFurnitureBA1`.
4. Both door approaches are clear.
5. No prop is placed against the south or east wall faces, which are cut away.

**The Art Director's judgement:**

6. The lectern reads as the landmark at gameplay distance.
7. The three banks read as a used library, not as three identical runs.
8. The lanes read as walkable and the banks read as impassable.
9. The dressing reads as the same material family as this room's own committed sprites, with paper
   dominant over bone.
