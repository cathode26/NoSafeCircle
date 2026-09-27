# Doorway geometry: the gap, and the facing

**Every number here was measured on canonical `main` at `163d7cca` on 2026-09-27** from the
committed blobs — the prefab YAML, the `.png` IHDR chunks, the texture `.meta` files, the layout
constants and `floor01.txt`. Nothing is recalled and nothing is taken from a code comment without
checking it.

Vincent played the game and reported two things:

> *"Door has gaps"*
> *"Door is not facing south west"*

Both now have exact, separate causes. Neither is mysterious and neither needs a redesign.

---

## 1. The gap: four widths that were never reconciled

A doorway is drawn by one system, blocked by a second, and filled by a third. Each picked its own
width.

| what | width | where it comes from |
|---|---|---|
| the hole in the **wall art** | **4.000** | `floor01.txt`, a `++` pair, x `AsciiRoomMap.WorldUnitsPerCell = 2f` |
| the **door leaf** sprite | **3.080** | 128 px / `spritePixelsToUnits: 64` = 2.000, x `DoorSprite` `m_LocalScale 1.54` |
| the **doorway blocker** collider | **3.000** | `Door.prefab`, `DoorVisual` `BoxCollider m_Size {3, 2.5, 0.3}` |
| the gap left in the **wall collider** run | **3.000** | `<Room>Layout.DoorWidth` / `DoorOpeningWidth`, all five = `3f` |

    visible gap  =  4.000 (art opening)  -  3.080 (door leaf CANVAS)  =  0.920 total, 0.460 each side

**!!! THAT 3.080 IS THE CANVAS, NOT THE DOOR, AND THE CANVAS IS PADDED. CORRECTED BELOW. !!!**

The sprite is 128x128 but the drawn door does not fill it. Measured from the alpha channel:

| facing | drawn px | drawn units | x1.54 |
|---|---|---|---|
| `_S_` (was wired) | 116 x 117 | 1.812 x 1.828 | **2.791** wide |
| `_SW_` (wired now) | 95 x 124 | 1.484 x 1.938 | **2.286** wide |

**So no uniform scale fits this art to the opening.** The opening is 4.000 x 2.500, aspect 1.600;
the drawn SW figure is aspect 0.766. Filling the width would need scale 2.695, making the leaf
5.224 tall against a 2.500 wall. **The width shortfall is an art request, not a number anyone can
tune**, which is why the x1.54 scale was left alone when the facing was fixed. `x1.54` is also
Vincent's own approved value (`Docs/Art/Doors/APPROVAL.md`), so changing it is his call twice over.

**AND DO NOT COMPARE THOSE TWO ROWS AS IF THEY MEASURED THE SAME THING.** The Art Director's note
warns why, and it is the sharper half of this entry: *"that door is front-facing, so its threshold
pool spreads toward the camera, and a 3/4 facing foreshortens the same puddle into far fewer
pixels. Coherence transfers between facings; a raw count does not."* The `_SW_` bbox is narrower
partly because of a foreshortened puddle and moss, not necessarily because the door SLAB is
narrower - and the slab is what reads as a gap. **The slab's own width is still unmeasured.** The
registration was built so the slab lands where the `_S_` slab landed: one union box `(16,8,115,133)`,
bottom-aligned, `spritePivot {x: 0.492188, y: 0}`.

**This is my own memory `measure-the-drawn-figure-not-the-canvas` firing against me in the session
that cited it.** I published 0.460 per side from `128 / 64 x 1.54`, which is the padded canvas. Then
I measured the alpha box and nearly published a second wrong number by comparing two facings' boxes
directly. **The question "how wide is the gap" is still open and it wants a render, not arithmetic.**

**That is the gap he can see.** At orthographic size 8 it is tens of screen pixels of open floor
either side of the door leaf, in a 4-unit hole the wall art has already committed to.

The 4.000 figure is measured, not inferred from the comment that asserts it: all **nine** `+` runs
in `Content/Levels/floor01.txt` are exactly two glyphs long, and `WorldUnitsPerCell` is `2f`. Nine
runs describe five doorways — four shared walls contribute two rows each, plus the one boundary
opening.

### The 0.5-per-side jamb overhang is separate, deliberate, and documented

`Scripts/World/Rooms/WallColliderRuns.cs` already records the *collider* half of this in its own
remarks:

> *the map's visual door gap is 4 units (the `'++'` pair) while the contract-pinned collider gap is
> 3, so half a unit of jamb art overhangs the collider on each side, and a per-slot box cannot
> express that.*

So `4.000 - 3.000 = 1.000`, i.e. **0.500 of jamb art per side stands over open floor** rather than
over a collider. That was a considered choice with a named reason (it keeps NSC-048 AC-004's named
boxes exactly as delivered) and it is not the same thing as the visible gap above. **Do not fix one
by changing the other**: the collider gap is contract-pinned at 3, the art opening is 4, and the
leaf is 3.08.

### Heights, for completeness

The leaf is `3.080 x 3.080` world units and the wall is `2.500` tall (`WallHeight = 2.5f` in all
five layouts, `WallThickness = 0.5f`). `DoorSprite` sits at `DoorVisual` local `y +1.25` plus its
own local `y -1.25`, so its pivot is at world `y 0`; the pivot is `0.054688 x 128 px = 7 px` up
from the sprite's bottom edge. The leaf therefore **overshoots the wall top by roughly 0.4 units**.
An overshoot is not a gap and Vincent did not report it, but it is the same
nobody-reconciled-the-numbers problem and belongs in the same fix.

### Which of the four widths should move is a design call

The four candidates are not equivalent:

- **Scale the leaf to 4.000** (`m_LocalScale` 1.54 -> 2.0): closes the visible gap with one number,
  and stretches 128 px of art across 4 units, coarsening it.
- **Narrow the art opening to 3.000**: needs `floor01.txt` to express a 3-unit gap, which a 2-unit
  cell grid cannot do. Not available without changing the cell size.
- **Widen the collider gap to 4.000**: contract-pinned at 3 by NSC-048, and it would move the named
  wall collider boxes.
- **Add jamb art that fills the 0.46 each side**: the Art Director's, and it leaves the geometry
  alone.

The fourth is the only one that changes no gameplay number. It is a visual pick, which `CLAUDE.md`
puts with the Art Director, not with Vincent.

---

## 2. The facing: FIXED 2026-09-27. The art had shipped a day earlier and nothing pointed at it.

**Closed at `71e163a38`**, five guid lines in `Door.prefab`: the four `DoorStateSpriteBinder`
fields and the renderer's own authored `m_Sprite`. Failing-before 4/5 with the exact assertion
naming the wrong facing, passing-after 5/5; `DoorSpawnerPlayModeTests` 5/5 at Play. The `x1.54`
scale was not touched.

**The part worth remembering is not the fix, it is the gap between the two halves.**
`Docs/Art/Doors/APPROVAL.md` records that the Art Director generated the whole `_SW_` set on
**2026-09-26**, for an earlier report of this same defect in Vincent's words (*"Door is pointing
south and it should point south west"*), gated it as a set and showed him the images. **The art
landed and the integration never happened, so he played the game the next day and reported the
same defect again.** An art task can be complete and invisible; nothing in the pipeline noticed
that four committed sprites had no referrer.

**One fixture deliberately still asserts the south facing, and it is not an oversight.**
`Tests/Editor/DoorwayOpeningSealTests.cs` builds its door with
`DoorPrototypeSceneBuilder.BuildInMemoryForTests()`, whose four sprite names are consts at
`Editor/DoorPrototypeSceneBuilder.cs:1004-1007`. That file is declared in the
`exclusive_resources` of **twenty-nine** contracts and every non-test reference to the builder is
a comment, one of which calls it *"a scene-builder file scheduled to die"* - so the facing was not
changed there. The shipped door has one facing; that fixture measures the old authoring path, and
its own comment says so.

### The evidence, for the record

Wiring **before** the fix, resolved by guid against every `.png.meta` on `main`:

| field | resolved file |
|---|---|
| `sealedSprite` | `door_bonestone_sealed_`**`S`**`_000.png` |
| `lockedSprite` | `door_bonestone_locked_`**`S`**`_000.png` |
| `openSprite` | `door_bonestone_open_`**`S`**`_000.png` |
| `finalSprite` | `door_bonestone_final_`**`S`**`_000.png` |

And these are also committed, in the same folder, at the same 128 px and PPU 64:

    door_bonestone_sealed_SW_000.png
    door_bonestone_locked_SW_000.png
    door_bonestone_open_SW_000.png
    door_bonestone_final_SW_000.png

**The south-west art already exists and nothing points at it.** Vincent's *"Door is not facing
south west"* is four guid references, not an art request. That is the whole cause.

**One gap in the swap, and it must be said before anyone calls this closed.** Only those four
states have an `SW` facing. There is **no** `SW` for `broken`, `damaged` or `opening`:

    door_bonestone_broken_S_000.png      S only
    door_bonestone_damaged_S_000.png     S only
    door_bonestone_opening_S_000.png     S only

So swapping the four wired fields leaves the crack/damage stages and the opening frame facing
south, and a door would flip facing as it takes damage. Either the three missing `SW` frames get
generated (Art Director), or the swap ships knowingly incomplete and that is recorded.

### There is no per-door rotation at all, and that is deliberate

`Scripts/World/DoorSpawner.cs:139-143` instantiates every door with `Quaternion.identity` and says
so: *"identity rotation: all five doors face +Z (approach from -Z, cross toward +Z)"*. The spawner
sets **position, name and identity and nothing else** — every offset, size, sprite, colour and
material lives in the prefab.

So the facing is a property of the *art*, not of a transform, and with an isometric camera at
**pitch 30, yaw -45** (decoded from `IsometricCamera.prefab`'s serialized quaternion, not recalled)
a single drawn facing is the right architecture: you change which sprite is assigned, not a
rotation. Fixing the facing by rotating the door would be the wrong fix and would break the
`3 x 2.5 x 0.3` blocker's alignment with the wall.

---

## What is not proven

- **That 0.460 per side is what Vincent is looking at.** The arithmetic is solid; nobody has put a
  labelled render of a doorway beside it. `CLAUDE.md`'s own rule applies — for art, render it and
  look. A captured frame of one doorway with the four widths annotated would settle it in one image.
- **Whether the leaf should be 4.000 wide or the opening filled with jamb art.** Design/art call.
- **Whether the ~0.4 overshoot above the wall top is visible**, or hidden by the wall art's own
  height.
- **Whether all five doorways show the same gap.** All nine ascii runs are 4 units, so they should;
  it has not been observed per door.
- **Whether the three missing `SW` frames are wanted.** Art Director's call, and it may be that the
  damage stages are never seen at a distance where facing reads.

## Who owns what

| | owner |
|---|---|
| the four guid swaps to the `SW` sprites | Game Agent (prefab wiring) |
| the three missing `SW` frames | Art Director |
| jamb art filling the 0.46 per side | Art Director |
| changing the leaf scale, the blocker or the collider gap | Game Agent, and NSC-048's pin must be respected |
| the ascii map cell size and the 4-unit opening | Game Agent |

## What would falsify this document

- **The 4.000 opening**: re-measure the `+` runs in `Content/Levels/floor01.txt` against
  `AsciiRoomMap.WorldUnitsPerCell`. Any run that is not two glyphs, or a cell size that is not
  `2f`, changes every width here.
- **The facing**: if `Door.prefab` stops resolving to `_SW_` sprites, the fix has been reverted -
  the likeliest cause is a crew running NSC-097, whose resource list names only the `_S_` files.
- **The gap arithmetic**: it is derived from alpha bounding boxes that include a threshold puddle,
  not from the door slab. A render, or a measurement of the slab alone, can overturn the
  per-side figures without changing the opening or the collider.
