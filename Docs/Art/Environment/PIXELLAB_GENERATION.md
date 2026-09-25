# Dungeon architecture kit — PixelLab generation record

Provenance for NSC-064's floor and wall kit. Written by the Art Director Agent, 2026-09-22.

**Why this kit exists.** Before it, `Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/` was
empty and the room scene builders drew every room as flat coloured boxes — `Color.gray` floors and
`Color.black` walls on a Standard shader. All five levels had props, doors, a wizard and enemies, and
no floor or wall art at all.

**Palette is NSC-078's, deliberately.** Architecture and props share every screen; the whole point of
one palette is that they do not look like two games. Every piece is measured against the prop band —
luminance 68-73, saturation 19-39, warm pixels 4-5% — and floors are allowed to sit darker, because a
floor should sit *under* the things standing on it.

## Style lock

**NSC-064 has no separate style-lock document and claims no resource for one**, unlike NSC-078. The
lock is recorded here instead, in the file the task does claim, so that there is something to check
this kit against rather than nothing.

| setting | value | why |
|---|---|---|
| density | **64 px per world unit** | D-1, the same as the props and the option-B characters. Not 180, which is the wizard's. |
| key light | **upper left** | matches the door family, the wizard and every NSC-078 prop |
| stone | violet slate and mauve, lilac edge highlights, mossy green-grey accents | NSC-078's material clause, unchanged |
| palette band | luminance 68-73, saturation 19-39, warm pixels 4-5% | measured off delivered props, not chosen |
| floors may sit darker | luminance down to ~49 | a floor belongs *under* the things standing on it |
| colour depth | **48 colours**, `reduce_colors`, PixelLab only | D-4 forbids scripted palette reduction |
| floor grid | 32 px Wang tiles, 16 per set | Unity Isometric Tilemaps |
| wall height | 2.5 world units = 160 px | the room layouts' own `WallHeight` |
| import | Sprite, Single, 64 ppu, Point, uncompressed, alphaIsTransparency, no mipmaps, **wrap Clamp**, Texture2D | the same nine settings NSC-078's gate names |

**`wrapU: 0` in a serialized `.meta` is Repeat, not Clamp.** The enum reads inverted from the
intuition, and getting it backwards once failed sixteen assets while every text-level check passed
them.

**What is NOT locked, and is Vincent's to settle:** whether this direction is the one he wants at all.
He pre-approved the spend — *"all runs approved"* — while at work; **that cleared the generation, it
is not a review of the result.** Nothing here has been seen by him.

## Floors — five rooms, one stone

Wang tilesets, 16 tiles of 32 px, `low top-down`, lineless, transition 0.25 unless noted.

**Every room chains off ONE base flagstone, `c60ac121-1445-4190-975d-04722f8addaf`.** That is the
point of `lower_base_tile_id`: five rooms that share a floor and differ only in what has happened to
it. Independently generated floors drift into five different dungeons.

| room | tileset id | upper terrain | lum | sat | warm |
|---|---|---|---|---|---|
| Ruined Entry | `8ea8fbf0-b6e6-4886-939d-08b1c804b12a` | violet rubble, **no transition band** | 66.4 | 26.7 | 4.1% |
| Bone Archive | `e9c70ca4-abeb-4b25-a588-60e63b9984c9` | rubble and grey ash | 71.0 | 21.1 | 2.1% |
| Chapel of Ash | `71d81b9a-13d2-4cc6-a51f-f643c1c9cd5d` | black soot and cinders | 56.2 | 22.2 | 0.3% |
| Lower Vault | `25fbc9a6-ae50-4290-af58-e4dd72caad88` | stagnant black water, olive sheen | 49.6 | 31.6 | 0.5% |
| Final Room | `326ad7bf-1b44-425f-abe7-f9c3e330986b` | scorched stone and bone shards | 50.6 | 22.3 | 3.2% |

### A Wang tileset exists to make two terrains DISTINGUISHABLE, so asking it for low contrast fights it

Three of the first five floors came back bright — gold straw, neon mint, acid-green moss — **through
negatives that named those exact colours.** The Final Room worked first time because scorched stone is
**dark by its own nature**, so the generator could separate the terrains without making one bright.

**The fix is not a stronger negative. It is to choose an upper terrain that is inherently dark** and
let the generator have its contrast. Soot instead of "ash, not pale". Stagnant black water instead of
"slime, not bright". Violet rubble instead of "moss, not acid".

**Known defect:** three of the five draw a bright boundary line where the terrains meet despite
`lineless`. The two whose upper terrain is darkest do not — the same root cause. Usable; worth one
more pass.

## Walls — six pieces

`create_object_pro_flash`, one direction, `low top-down`, 64 px per world unit. Walls are 2.5 world
units high, hence 160 px; a two-unit run is 128 px.

| piece | object id | canvas |
|---|---|---|
| straight run | `a48e7f0d-d10d-4fdb-bc3d-5a17578295b6` | 128x160 |
| outside corner | `f7853eba-913d-43c6-9c04-6fbe62074ceb` | 128x160 |
| end cap with capstone | `fa2f8456-5bb0-45e1-83a9-209fa5350c86` | 80x160 |
| gothic pilaster | `6d3e8df9-3178-419b-831e-6aedf443facd` | 64x176 |
| doorway with jambs and lintel | `88603fc9-c7b2-41f1-9948-8d2cb7fce4b2` | 128x176 |
| broken stub | `0fc20e22-0a69-4583-af44-a443f72c4207` | 128x128 |

### `create_isometric_tile` varies the MATERIAL, not the SHAPE

The walls were first attempted with `create_isometric_tile`. **Six different geometries were
described — corner, end cap, pilaster, doorway, broken stub — and all six came back as the same
generic stone cube.** What varied was the stone: brick size, crack pattern, hue. **No amount of clause
work gets a corner out of that tool**, and a seventh attempt would have produced a seventh cube.

**`create_object_pro_flash` honours described geometry** — it is what drew the three-shelf bookcase,
the carved pew and the skull-capitalled column — and every piece landed correctly on the first attempt
after the switch.

**The cubes did prove the material clause, though:** corner and end cap landed in the palette band
first time with the anti-cyan negatives. **Keep the clause, change the tool.**

## Clause rules carried from NSC-078

- **Anti-cyan negatives are required on stone.** *"no teal, no blue-green, no cyan, no navy"* — the
  first wall came back teal without them.
- **Ash is dark.** *"deep grey almost black, no pale grey, no white, no snow"*. "Pale grey ash" reads
  as snow, every time, in props and in floors alike.
- **Never name a setting** the piece is not.

## Colour measurement, and three metrics that were each too loose

Colour was checked with a hue test, and the test was wrong twice before it was right.

1. **violet = blue > green** passed a **teal** wall at 86.7%.
2. Adding **red > green** fixed teal and then passed **magenta** rubble at 92.9%.
3. A magenta test caught that.

**And the flag set omitted saturation entirely**, so a neon-mint floor at saturation 66.4 against a
prop band of 19-39 printed as "in band".

**A colour test built from one failure does not generalise to the next colour.** The band that is
actually checked now is luminance, saturation, cyan, magenta and warmth together.

## Colour reduction

`reduce_colors` at 48 colours, PixelLab only — D-4 forbids scripted palette reduction. **The five
floors were quantized in ONE call and share a single palette**, which is what the tool is for.
Wall pieces were quantized by canvas group. Staged colour counts: floors 24-31, walls 45-48.

## Spend

Metered as the subtraction between two empty-queue readings, never as a sum of per-call estimates.
**3770 remaining / 1229 used at the first call.** `create_topdown_tileset` costs 1-4 generations and
usually 3 or 4, not 1 — six tilesets is about eighteen generations, not six.

## 2026-09-25 - two wall pieces resized to ONE world unit for NSC-109

**The kit above was authored as TWO-unit runs** - this document's own words, *"a two-unit run is
128 px"* - **while the builders paint ONE-unit cells.** NSC-109 binds these committed sprites to
the architectural Tiles instead of generating them, which turned that mismatch into a test
failure. **The heights were always right. The widths were not.**

| piece | was | now | world at PPU 64 | how |
|---|---|---|---|---|
| straight run | 128x160 | **64x160** | 1.0 x 2.5 | **crop of the approved art**, window x0=32 |
| broken stub | 128x128 | **64x32** | 1.0 x 0.5 | regenerated, `3f888fa6-f9a3-4a66-8512-2b257240bed6` |

### TWO GENERATED WALLS WERE REJECTED ON COLOUR BEFORE THE CROP WAS CHOSEN

`create_object_pro_flash` was tried twice for the straight run, **both times carrying the
anti-cyan clause verbatim, and both came back blue-cast.** Measured as the fraction of opaque
pixels in hue 150-250 deg **AND** saturation > 0.20 - the saturation term is required, because
this document's own colour section records that a hue relation without one is not a band:

    committed original 128x160     19.1%   sat median 0.537   the approved reference
    generated v1       64x160      55.5%   sat median 0.206   REJECTED, and only 52% h-fill
    generated v2       64x160      42.7%   sat median 0.457   REJECTED, a 36%-coverage lattice
    generated stub     64x32        1.1%   sat median 0.072   ACCEPTED, neutral grey
    CROP x0=32         64x160      18.1%   sat median 0.549   ACCEPTED, it IS the kit's pixels

**v1 was landed and committed before it was colour-measured, and that was the error** - a preview
thumbnail read as grey and the measurement says 55.5%. **Measure the colour before you commit the
art, not after.** Cost: 2 generations spent and discarded.

### WHY A CROP AND NOT A UNIFORM SLICE

A uniform 64 px grid over the 128 px sheet was proposed on the basis that the sprite is *"two of
the required tiles side by side"*. **Measured, it is not:** the two halves differ in **71.5%** of
their pixels, and the seam at x=64 is **continuous masonry** - 15 of 160 rows change across it,
against 116 of 160 between col0 and col63. It is one two-unit run, and a 64-grid slice cuts
through blocks.

**All 65 candidate windows were searched.** x0=16..51 are solid (minimum column fill 0.97-0.98);
**x0=32 has the best edge match and is dead centre.** No window tiles perfectly against itself,
which is expected of a continuous run and reads as ordinary irregularity in rough masonry rather
than as a seam.

**The crop is baked into the PNG rather than expressed as `spriteMode Multiple` + a sub-rect**, so
`AssetDatabase.LoadAssetAtPath<Sprite>` keeps returning the single main sprite and no builder code
has to change.

### PIVOTS WERE ALSO WRONG, AND A SIZE FIX ALONE WOULD HAVE MISSED THEM

The tests require `pivot.y == 0` - *"Wall visual sorting must originate at the wall/floor
contact"* - and the generated Tile being replaced used `new Vector2(0.5f, 0f)`. The committed
metas carried `y: 0.11875` (19 px up) and `y: 0.0625` (8 px up). **Both are now `{x: 0.5, y: 0}`.**
PPU stays 64 on every piece and no other import setting changed. The `.meta` GUIDs are untouched,
so every existing reference still resolves.

**`wall_corner` IS DELIBERATELY UNCHANGED** - the candidate uses it only as a deliberately-stale
sprite in a rebuild-repair regression test, so nothing asserts its dimensions.
**`wall_door_jamb`, `wall_end_cap` and `wall_pilaster` have ZERO references in the candidate's
C#**; whether they are dead weight or staged for later rooms was NOT established, and they were
left alone rather than resized on a guess.

**HOW TO CHECK THESE, because the obvious instrument is the wrong one:** they are bound from C# by
PATH STRING, not by GUID. A GUID grep returns each PNG's own `.meta` and nothing else, which reads
exactly like "unused". Grep the path for a C# binding, the GUID for a scene or prefab binding.
