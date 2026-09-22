# NSC-078 style lock

The settings every prop in this family was generated against, and the evidence for each. Written by
the Art Director Agent, 2026-09-22.

**This document records what was locked, not what was intended.** Where the committed plan clause and
the shipped sprite disagree, the disagreement is written down here rather than reconciled silently.

## Approved pilot

Vincent approved the style-lock pilot on 2026-09-22, shown `ac003_props_3x.png` and
`ac003_gamescale_1080p.png`, with the caption naming the table's crimson and the candelabra's flames
as the two open questions. His words: **"art looks good!"**

**All five pilot props are therefore Vincent-approved sources.** He later said **"art looks good"** a
second time over a batch-3 baseline/re-roll pair sheet, which confirmed the iron clause and the dark
ash re-cast.

**Read both narrowly. A general compliment is not a per-sprite approval.** `lv_iron_rail_x` appeared on
the second sheet, is the best-drawn sprite in the run, and points the wrong way; he was told so in the
same exchange. It is **not** approved by those words.

## Locked settings

| setting | value | evidence |
|---|---|---|
| density | **64 pixels per world unit** | D-1. Not 180 — that is the wizard's density and was nearly reused here. |
| key light | **upper left** | confirmed against the door family and the wizard highlights during the pilot |
| palette | deep plum and teal-black shadows, warm lantern-glow highlights | global clause, in every prompt |
| stone | violet slate and mauve, lilac edge highlights, mossy green-grey accents | material clause |
| wood | dark red-brown | material clause |
| bone | cream, not pure white | material clause |
| pivot | **the drawn ground line, measured per sprite from the alpha bounds** | see below |
| sorting anchor | same as the pivot | recommendation; downstream owners configure actual sorting |
| colour depth | **48 colours**, `reduce_colors`, PixelLab only | D-4 forbids scripted palette reduction |

## The pivot rule, which changed during this task

**The catalog rule was bottom-centre `(0.5, 0)`. It is wrong for every prop in this family.**

`(0.5, 0)` assumes the art touches the bottom of its canvas. **None of these do** — each carries
between 3 and 19 fully transparent rows beneath the drawn figure, so a bottom-centre pivot hangs the
prop up to **0.23 world units** above the floor at 64 px/unit. That is the same defect the wizard hit
(NSC-075 AC-008, NSC-077 AC-002).

**So the pivot is measured, per sprite, as the lowest opaque row divided by the canvas height**, and
`alignment` is Custom. Measured range across the family: **0.033 to 0.207**. Not one is `0`.

`DungeonPropImportPostprocessor.cs` applies it, `DungeonPropImportSettingsTests.cs` proves it, and
`validate_dungeon_prop_catalog.py` re-derives it from the pixels rather than trusting the catalog.

## Import settings

Sprite, Single, 64 px/unit, Point filter, uncompressed, alphaIsTransparency, no mipmaps, **wrap
Clamp**, Texture2D.

**`wrapU: 0` in a serialized `.meta` is Repeat, not Clamp.** The enum reads inverted from the
intuition. Getting it backwards failed sixteen props on a Unity run while every text-level check passed
them, because those checks asserted the fields copied from a template rather than the nine the contract
names. **Clamp is deliberate and differs from the approved `door_bonestone_*` metas, which are Repeat** —
harmless on a non-tiling door, but `ca_pew_x_*` and `ba_shelf_bank_z_*` tile, and that is where wrap
mode stops being cosmetic. Do not "fix" it back.

## Clause rules that were proven during acquisition

1. **No material clause by default.** Most subject clauses already name their material.
2. **A material clause belongs only on a prop whose mass is ONE material.** Where two are named, send
   the palette half alone. Tested: the sluice gate came back grey granite with no clause and violet
   with the palette half.
3. **Iron needs its own clause** — *"cold blue-grey wrought iron with dull orange-brown rust patches,
   hard metal not timber, no wood, no wood grain, no warm brown planks"*. **Drop the "no wood" half on
   a prop whose body is wood** and keep only the colour, or it fights the prop's own mass.
4. **Never name a setting.** A prop told its setting draws it: `shared_web_corner_a` was told it filled
   a stone wall corner and drew a wall and floor. Describe the geometry instead.
5. **Add the no-lantern negative.** Six unprompted lanterns, and a rotation copies one into all eight
   facings.
6. **Ash is dark.** The committed clauses say "pale grey ash", which reads as snow.
7. **Write a damage state as the thing itself, not as an adjective.** "Collapsed table" came back as a
   table standing on four legs.

## Facing, and the recipe that settled it

**One rotation yields both diagonals.** Generate the prop frontal with **no facing phrase**, rotate it
with `first_frame_url` and `n_directions: 8`, then take **`south-east` for `world_z`** and
**`south-west` for `world_x`**.

Direct diagonal generation was measured at **`_z` 2 successes in 3** and **`_x` 1 in 7**. Three
separate `_x` phrasings were burned before rotation was tried. **`_x` was never a clause problem.**

**Slope sign alone cannot identify a facing** — `north-east` carries the same sign as `south-west` and
is the *back* of the prop. The pair *(slope, front face visible)* identifies it.

**Rotation pads the canvas to square**, so the pivot must be re-measured and never carried from the
frontal. Six props carry a declared canvas deviation for this reason.

## Multi-segment runs (D-7)

A run comes from **one** approved source segment: generate `start` frontal, derive `middle` and `end`
from it with `create_object_state`, rotate all three at the **same seed**, take the same facing from
each. Independently generated segments drift apart silently and only show it when they sit together.

Measured placement offsets, in rotated canvas pixels — **compositing values; the layout scripts own the
real ones**:

| run | facing | frame | offset | draw order |
|---|---|---|---|---|
| `ba_shelf_bank_z_*` | `world_z` | `south-east` | `dx=+74, dy=-28` | furthest first: end, middle, start |
| `ca_pew_x_*` | `world_x` | `south-west` | `dx=+62, dy=+19` | furthest first: start, middle, end |

**The draw orders are opposites and that is load-bearing:** `_z` recedes from the camera, `_x` advances
toward it. A correct offset drawn in the wrong order still reads as broken.

## Recorded deviations

- **`ca_pew_x_*` were re-rolled desaturated.** The first trio read as bright coral beside the purple
  stone. **The cause was saturation, not brightness** — 58.5 against the shelf's 32.7 at the same
  luminance — and it was present in the frontal, not introduced by the rotation. The re-roll gives
  **41.0 at identical luminance**.
- **`lv_crate` reads as a lidded treasure chest.** Well drawn and on palette, but a chest signals
  *lootable* for a prop that is scenery. Flagged for Vincent, not re-rolled unilaterally.
- **`lv_iron_rail_x` is flat**, not diagonal. Known, and not approved by "art looks good".
- **`re_landmark_guardian_statue_broken` was built with `create_object_state`** from the approved
  standing statue, **not from its clause**, which carried operator instructions that would have been
  drawn. Canvas 100x176 against a planned 100x132.
- **Six rotated segments pad to square** and carry declared canvas deviations.
