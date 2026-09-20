# NSC-078 style-lock pilot: plan

Art Director Agent, 2026-09-17. The pre-flight plan the art bible requires before any paid call.

## Vincent's go and the cap

- **Go, relayed by the GER Agent:** "Ok prop pilot so I can look at it and approve".
- **Cap: 120 generations for the pilot alone.** Stop and ask him past it. Counted from this file's call log with
  `get_balance` at an empty queue as the cross-check, the NSC-095 method.
- The plan's section 4d numbers are printed quotes: the pilot is about **95 in meter terms**, not 68, because the
  NSC-095 run measured the meter running about a third above the printed costs.
- **No family caps yet.** This pilot measures the real per-object cost; the revision after it sets them.

## What the pilot is for

NSC-078 AC-003 wants a freestanding prop, a repeatable or connected source, and a hazard or route-edge source, and
the set locks the palette for bone, wood, stone and iron plus the light direction. Vincent picks from it, and the
approved images become the `style_image` for the three families.

| # | id | canvas | why it is in the pilot |
|---|---|---|---|
| 1 | `shared_bone_pile_a` | 100x84 | high-frequency freestanding clutter; bone palette; small-prop readability |
| 2 | `ba_collapsed_reading_table_z` | 144x148 | wood furniture; `world_z` facing on the committed BA1 footprint |
| 3 | `ca_candelabra_tall` | 64x148 | tall gothic vertical; warm flames as the brightest pixels; thin shapes |
| 4 | `re_broken_masonry_blocks` | 124x112 | violet-slate stone that must sit beside NSC-064 walls |
| 5 | `lv_iron_rail_x` | 108x116 | connected route edge; two copies butted prove the post-and-panel joint |

## Tool settings (plan section 4c)

`create_object_pro_flash`, `n_directions: 1`, `view: "low top-down"`, canvas per the table, fixed recorded seed,
`name` = the catalog id, **no `style_image` in the pilot**, description = subject clause + the global clause.

Free quote taken first: `get_pro_flash_capabilities(operation="object", 144x148, n_directions=1)` returns
**6 generations, provisional**. Five first attempts therefore print about 30.

## Budget

| Round | Calls | Printed | Running printed |
|---|---|---|---|
| First attempt, 5 sources | 5 | about 30 | 30 |
| Second attempts where the first is weak | up to 5 | about 30 | up to 60 |
| Repairs, if any (`inpaint_image_pro_flash`, measured about 10.5 each on NSC-095) | - | - | - |
| **Cap** | - | - | **120 (meter)** |

## Steps

1. Balance and `list_jobs` before the first call. **Done below.**
2. Generate the five first attempts, one call each, seeds recorded.
3. Download each with `get_object` immediately; results expire after about 8 hours.
4. Measure: size, alpha bbox, opaque count, distinct colours, SHA-256; check the transparent background and that
   nothing is clipped.
5. Judge against the style lock: outline weight, palette, light from the upper left, readability at 64 px per
   world unit, and for the rail that two copies butt without a seam.
6. Re-roll whatever fails, once, with the same canvas and a new seed.
7. Build the AC-003 review package: native pixels, world scale beside the wizard, gameplay-camera density. Use
   the **committed 128 px wizard remake** (now on main at `9215873ec`) at 1.0546875x for 1080p, never the 180 px
   art at 0.375x.
8. Vincent picks. His approved image ids become the family `style_image`.
9. **The first committed candidate waits for NSC-078 rev 6**, which lands the 120 cap and rebinds the plan hash
   after the Game Agent commits my meter-caveat patch. Generating and reviewing do not wait.

## Balance

| When | Remaining | Used | Note |
|---|---|---|---|
| Before the first call, 2026-09-17 | 4537 | 463 | `list_jobs` empty, verified |

## Call log

| # | id | canvas | seed | printed | object id |
|---|---|---|---|---|---|
| 1 | `shared_bone_pile_a` | 100x84 | 101 | 6 | `28c4f29d-46e1-40e5-9c58-051f48a4760c` |
| 2 | `ba_collapsed_reading_table_z` | 144x148 | 102 | 6 | `30372cd0-ec66-4365-8a29-6b8f42f57601` |
| 3 | `ca_candelabra_tall` | 64x148 | 103 | 6 | `cc89c4c3-a991-4e76-8f24-59023e5995ba` |
| 4 | `re_broken_masonry_blocks` | 124x112 | 104 | 6 | `66f2bbc1-fc87-48ee-98c5-876423c5e0b9` |
| 5 | `lv_iron_rail_x` | 108x116 | 105 | 6 | `696e0b20-7364-4132-8493-09a7250e8854` |

**Round 1 printed total: 30.** All five `create_object_pro_flash`, `n_directions: 1`, `view: "low top-down"`, no
`style_image`, description = subject clause + material clause + the global clause verbatim from plan section 4a.

## Results: round 1

All five delivered at the exact requested canvas, transparent corners, nothing clipped at an edge.

| id | canvas | delivered bbox | fill | colours as generated |
|---|---|---|---|---|
| `shared_bone_pile_a` | 100x84 | 8,5 - 89,79 | 48.3% | 2998 |
| `ba_collapsed_reading_table_z` | 144x148 | 6,2 - 135,141 | 46.0% | 7254 |
| `ca_candelabra_tall` | 64x148 | 5,6 - 59,141 | 27.9% | 1831 |
| `re_broken_masonry_blocks` | 124x112 | 4,3 - 114,102 | 43.1% | 4387 |
| `lv_iron_rail_x` | 108x116 | 5,13 - 101,100 | 22.0% | 2031 |

### Scale: correct, and I nearly reported a false defect

At game scale the props *look* large beside the wizard, so I recomputed each one's projected extent from its
footprint instead of trusting the eye: width = (x + z) x 0.7071 x 64, height = (h x 0.866 + (x + z) x 0.3536) x 64.
Bone pile 90x73 intended against 81x74 drawn; table 136x137 against 129x139; masonry 113x101 against 110x99;
candelabra 54x138 against 54x135; rail 100x105 against 96x87. **Every prop is correctly sized.** They read large
because a 1x1 ground footprint alone occupies 45 px of vertical screen space at this camera - the diamond is tall.

### The real finding: the palette

As generated the props carry **1831 to 7254 distinct colours**. The approved art carries **63** (wizard 128
south-east) and **32** (enemy walk frame). The global clause asked for "no anti-aliasing and no gradients", and at
those counts the props would read softer than every character beside them.

`reduce_colors` fixes it for **0.1 generations per prop**, and it is contract-allowed (plan section D-4 lists
PixelLab's own `reduce_colors`). All five at `num_colors: 48`: `round1-48/`, comparison
`round1-48/pilot_palette_compare_3x.png`. The flatter shading is crisper, nothing is lost, and the props now sit
in the same register as the characters. **Recommendation: 48-colour reduction becomes a standard step for prop
art**, recorded in the style lock.

### Two spec deviations to re-roll

1. **`ba_collapsed_reading_table_z` has an added lantern.** The global clause ends "no other objects"; a lantern
   is another object, and it would double-light a room that gets its light from elsewhere.
2. **`re_broken_masonry_blocks` reads as a standing arch**, not "tumbled carved violet-slate masonry blocks with a
   broken arch stone". A whole arch implies a passage; the entry is rubble dressing for
   `RuinedEntryLayout.NorthWestClusterDressingBounds`.

The other three - bone pile, candelabra, rail - match their clauses, including the rail's `world_x` diagonal
running upper-left to lower-right.

### Spend

Round 1: 30 printed (5 x 6) plus 0.5 for the five colour reductions = **30.5 printed of the 120 cap**; meter
cross-check at the next empty queue. Two re-rolls would print about 12 more.

## Results: rounds 2 and 3, the re-rolls

| # | id | canvas | seed | printed | object id | outcome |
|---|---|---|---|---|---|---|
| 6 | `ba_collapsed_reading_table_z` | 144x148 | 112 | 6 | `310a84cc-8fd3-4605-9c77-95915c476c7c` | **accepted** - the added lantern is gone, legs broken, pages scattered |
| 7 | `re_broken_masonry_blocks` | 124x112 | 114 | 6 | `80cc8c6c-ffc7-46f2-9f18-99898b9ed881` | silhouette fixed (rubble), **palette drifted warm** |
| 8 | `re_broken_masonry_blocks` | 124x112 | 116 | 6 | `80dc2857-50dd-47db-a8c2-7c9e438ac464` | **recommended** - rubble and cold violet slate |

Round 2's masonry fixed the silhouette but swapped violet slate for tan stone, so round 3's prompt pinned both
halves at once - the rubble silhouette ("nothing standing, nothing upright, no intact arch") and the palette
("cold violet slate and mauve purple with lilac edge highlights, no tan, no beige, no warm brown stone"). Rather
than pick a palette lock for the kit myself, all three go to Vincent: `masonry_pick_3x.png`.

### The three masonry attempts, measured

`tools/masonry_compare.py` -> `masonry_compare.json`. Hue bands over opaque pixels with saturation > 0.15, so
hueless slate does not vote.

| | round 1 | round 2 | round 3 |
|---|---|---|---|
| silhouette | **arch standing**, bbox 110x99 | rubble heap, bbox 114x75 | rubble heap, bbox 113x83 |
| top-quarter fill | 47.2% | 49.2% | **35.2%** (mass lowest) |
| warm hue (tan/beige/brown) | 12.4% | **17.6%** | **1.8%** |
| violet hue (slate/mauve/lilac) | 32.6% | 7.0% | **56.2%** |
| mean saturation | 0.43 | 0.53 | **0.25** |

For comparison the **approved** 128 px wizard measures violet 43.7%, warm 29.4%, mean saturation 0.489, so
round 3 is the attempt whose palette sits with the characters and the NSC-064 slate kit.

**The honest caveat on round 3:** it is not arch-free. A half-sunken curve of voussoirs survives in the middle of
the heap, so it reads as *a collapsed archway* rather than a random block pile. Nothing stands upright and the
mass is the lowest of the three, so it meets "tumbled ... with a broken arch stone" - but the arch motif is still
legible, and if Vincent wants no arch shape at all that is one more re-roll at 6 printed.

## AC-003 review package

`tools/ac003_package.py`, built from the five finals (round 1 bone pile, candelabra and rail; round 2 table;
round 3 masonry), all at the 48-colour lock:

- `ac003_props_3x.png` - the five props at 3x native pixels, labelled with their provenance;
- `ac003_gamescale_1080p.png` - 1:1 screen pixels at 1080p beside the committed 128 px wizard;
- `ac003_measurements.json`, `ac003_palette_audit.json` - canvases, bboxes, fill, colour counts, hue bands.

**One screen-scale factor for everything: 67.5 / 64 = 1.0546875.** Every prop canvas in plan section 4a was
derived at 64 px per world unit and the committed wizard is a 2-unit box at 64 PPU, so props and characters take
the same factor. The 180 px wizard art at 0.375x is never used here.

**Counter-intuitive but correct:** the collapsed table is 156 px tall on screen against the standing wizard's
135 px. Its footprint is 2.1 x 2.1 units, and a 2.1-unit ground diamond alone occupies about 105 px of vertical
screen space at this camera. Round 1 already verified every prop's projected extent against its footprint.

### Two style-lock decisions the package needs from Vincent

1. **The table's crimson.** It measures 33.6% red hue at mean saturation 0.603 - the loudest thing in the set,
   against the approved wizard's 0.489 and the masonry's 0.246. Approving it makes that crimson part of the
   family palette lock for every later library prop.
2. **The candelabra is emissive.** Five lit flames, brightest pixel 0.996. That is intrinsic to the object, not
   an added one, so it is not the lantern defect - but if props never light a room, the flames are decoration
   that promises light the room does not get.

## Spend: the pilot's own call log, and why the meter cannot be split

| Round | Calls | Printed |
|---|---|---|
| 1, five objects | 5 | 30 |
| 1, five `reduce_colors` at 48 | 5 | 0.5 |
| 2, two re-rolls + two reductions | 4 | 12.2 |
| 3, one re-roll + one reduction | 2 | 6.1 |
| **Total** | **16** | **48.8 printed of the 120 cap** |

Meter readings, both with `list_jobs` empty: **4537 remaining / 463 used** before the first call, **4408
remaining / 591 used** after round 3. The two columns give 4537 - 4408 = **129** and 591 - 463 = **128**; they
disagree by one because `reduce_colors` charges 0.1 and each column rounds separately, so the true delta is about
128.5.

**That delta is not this task's spend.** The same window contains the NSC-064 kit trial's two
`create_building_kit` calls, about 80 printed, which is why both task files count from their own call logs. The
two printed totals add to about 128.8 against a meter delta of about 128.5 - printed and meter agreeing, as the
later NSC-095 batch did, and unlike that run's 1.36 ratio. **One run is a measurement, not a rate.**

The lesson for next time: **take a meter reading between two lines of work, not just at the ends.** Without one
between the pilot and the kit trial, neither line has an independent meter figure.

## Vincent's pick, 2026-09-17

**"I pick masonry 3."** So `re_broken_masonry_blocks` = object `80dc2857-50dd-47db-a8c2-7c9e438ac464`, seed 116,
the 48-colour file `round3-48/re_broken_masonry_blocks.png` - rubble silhouette, violet 56.2% / warm 1.8%, mean
saturation 0.246. Rounds 1 and 2 are rejects and belong on `art-rejects/NSC-078`.

That fixes the **cold violet slate** end of the family palette lock. His two remaining style-lock answers - the
reading table's crimson and the candelabra's lit flames - are still open, and the first **committed** candidate
still waits for NSC-078 rev 6.
