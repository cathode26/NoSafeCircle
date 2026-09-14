# PixelLab Dungeon Architecture Kit — Source Selection (NSC-064)

## Scope and boundary

This document records the PixelLab MCP source-art acquisition for NSC-064. It
selects source art only. It does not create Unity Tile assets, edit the
`DoorPrototype` scene or scene builder, alter collision/navigation, or author
room layouts. A future task (`INT-001` on `Tasks/NSC-064.yaml`) imports these
sources and builds the actual Tile/Sprite assets.

Tool used: **PixelLab MCP** only (`create_building_kit`, `create_object_pro_flash`,
plus read-only `get_tiles_pro` / `get_object` / `list_tiles_pro` / `get_balance`).
No imagegen or hand-drawn substitutes were used. Approved per
`Tasks/NSC-064.yaml` provenance (`approved_development_tool: PixelLab MCP`,
approved 2026-09-12).

Palette/perspective anchor: the approved wizard family
(`Docs/Art/Wizard/PIXELLAB_GENERATION.md`, NSC-061) uses a "low top-down"
PixelLab camera and the palette phrase *"dark spooky dungeon color palette of
deep plum and teal-black shadows with warm lantern-glow highlights."* Every
generation below reuses that exact palette phrase and the same `low top-down`
view so the environment kit and the wizard read as one coherent presentation.

## Selected architecture kit

Generated with `mcp__pixellab__create_building_kit`:

| Setting | Value |
| --- | --- |
| `wall_description` | "ancient dark dungeon stone brick wall blocks, deep plum and teal-black shadow grooves between blocks, warm lantern-glow highlights on worn upper edges, faint dust and cobwebs in the mortar, gothic dark-fantasy horror-comedy style, readable silhouette, no gore, family-friendly" |
| `floor_description` | "worn dark dungeon flagstone floor tiles, deep plum and teal-black shadow cracks between stones, warm lantern-glow highlights on raised edges, faint dust and moss, gothic dark-fantasy horror-comedy style, readable silhouette, no gore, family-friendly" |
| `tile_type` | `isometric` |
| `tile_size` | `32` px |
| `wall_tiles` | `2` (wall height in tiles) |
| `outline_mode` | `segmentation` (chosen for cleaner seamless edges over gray-outline shading, since Tilemap edge continuity is an acceptance criterion) |
| `seed` | `20260914` |
| PixelLab tile (job) ID | `025d0b90-f546-466f-a7a7-bff2ef855e32` |
| Reported camera/view | `low top-down` |
| Reported kind/type | building kit (floor / walls / doorways / pillar / stairs), isometric, 58 total pieces (20 AI-painted, remainder geometrically derived) |
| PixelLab cost | 20–40 generations by canvas size (billed against the account's Tier 2 subscription allowance) |

The kit returns 58 numbered pieces (floor, 4 wall sides, corners, doors,
pillar, stairs, partitions, and multi-cell "outer_multi"/"partition_multi"
composites) addressable by index; see `placement_rules` in the raw
`get_tiles_pro` response for the full role→index map. Only two pieces were
selected as sources (see below); the rest were inspected for the repeatability
check but are not copied into the repository. Their PixelLab tile IDs are
recorded here for provenance and are retrievable again via `get_tiles_pro`
with the job ID above.

### Selected sources — repeatable Tilemap art

| File | Kit piece | Dimensions | Alpha | SHA-256 |
| --- | --- | --- | --- | --- |
| `architecture-kit-floor-flagstone.png` | `floor` (index 0) | 52×58px | RGBA, 0–255 | `303107b2e3c08a2534eb815ae3b340596545bc3d47779a8c8762919949d194bb` |
| `architecture-kit-wall-brick.png` | `outer_multi EW` (index 55) | 52×58px | RGBA, 0–255 | `bc80376e29b5b20d2fc1a05ca7cfb059660b4391ab9687e585993d5121f39088` |

**Wall piece selection required a correction.** The first candidate wall piece
was index 1 (`sides: N`), a single isolated wall segment with a fully closed
diamond-shaped top cap. Visual review (see below) showed it reads as a
standalone end-cap/column and does not butt or stagger into a continuous run
under any offset tried (flat edge-to-edge, 50%-width horizontal overlap, or a
diagonal isometric stagger all left visible gaps or resets). Index 55
(`outer_multi EW`), one of the kit's pre-composed "this cell continues into
its neighbors" pieces, has an asymmetric/notched top cap designed to
interlock. At a **50%-width horizontal stride (26px at native resolution)**,
four repeated copies show continuous brick coursing and an unbroken merlon
cap silhouette with no gaps or pattern resets. `architecture-kit-wall-brick.png`
was replaced with this piece before selection was finalized; index 1 was not
copied into the repository.

Evidence images (both under `Docs/Art/Environment/`, upscaled 6× nearest-neighbor
for legibility, not committed as selectable game assets):

- `PIXELLAB_WALL_REPEAT_CHECK.png` — 4 copies of the selected wall piece at
  the 50%-width horizontal stride, showing continuous coursing.
- `PIXELLAB_CONTACT_SHEET.png` — all 8 selected sources with room mapping,
  for Vincent's review.

**Limitation, stated plainly:** this check is a flat PNG-compositing sanity
check performed with Python/Pillow outside Unity (Unity was out of scope for
this task). It is not a verified Unity Isometric Tilemap placement proof. The
26px horizontal stride is derived from this kit piece's own canvas geometry,
not from an authored Unity Grid cell size. Downstream integration (`INT-001`)
must confirm the actual Tilemap Grid cell size/Tile pivot reproduces this
same stride (or crop/resize the source so it does) before treating the wall
as gameplay-ready, per `Docs/Engineering/WALL_TILING_IMPLEMENTATION_GUIDE.md`
("the texture repeat period must divide the texture width exactly").
Vertical/corner/doorway continuity was not tested; only the straight EW run
required by this task's acceptance criteria was checked.

### Rejected building-kit candidates

Two other complete building-kit generations already existed in this
PixelLab account when this task started (not generated by this session; the
account is shared across prior NSC-064 attempts). Both were inspected and
rejected in favor of the kit above because their highlight color does not
match the wizard's *"warm lantern-glow highlights"* requirement:

| PixelLab tile ID | Wall/floor description | Rejection reason |
| --- | --- | --- |
| `b669924e-769f-45a8-a86c-b7d7992a7334` | "deep blue-black crypt brick walls with desaturated moss-gray weathering, chipped mortar lines, and small amber candle-glow highlights" / matching crypt flagstone | Close on highlight warmth (amber) but the base wall hue (blue-black) departs from the wizard's "deep plum" note; kept as documented alternative, not selected. |
| `b20baed6-8df7-468c-8c69-5b2c5de03804` | "charcoal basalt dungeon brick walls with warm ash-gray weathering, chipped mortar lines, and small teal magical moss highlights" / matching ash-gray flagstone | Highlight color is teal (cool), contradicting the wizard's explicit warm lantern-glow highlight requirement. Rejected on palette grounds. |

Neither was copied into the repository. This is disclosed for provenance
transparency, not claimed as work performed by this task; no PixelLab credits
were spent by this session to produce them.

## Selected props — transparent, individually sortable SpriteRenderer sources

Generated with `mcp__pixellab__create_object_pro_flash`, `n_directions=1`
(static props, no rotation set needed), `view=low top-down`. Every prompt
shares this style-anchor suffix, mirroring the wizard's palette phrase:

> gothic dark-fantasy horror-comedy dungeon prop, deep plum and teal-black
> shadow tones with warm lantern-glow highlights on worn edges, faint dust,
> matching a worn dark stone flagstone-and-brick dungeon architecture kit,
> readable silhouette, no gore, family-friendly

Each call also passed `style_image`: a 24×24px Lanczos-downscaled crop of the
building kit's wall piece (index 1, native 52×58px — the same generation job
and seed as the selected wall/floor, so the color palette and material are
identical; index 1 was used only as a compact palette/texture reference here,
independent of its rejection as a Tilemap source above), with
`usage_description`: *"Match this isometric dark dungeon architecture kit:
deep plum and teal-black stone shadow tones, warm lantern-glow edge
highlighting, brick/flagstone material texture, low top-down camera angle,
and pixel scale."* The first attempt at 4 of the 6 props used the full
52×58px reference and failed PixelLab's validation ("style image must fit
the native canvas") because it exceeds some of the requested canvas sizes;
this was not a paid generation. All 6 props completed on the first successful
attempt (1 iteration each, well inside the 2-iteration bound).

| File | Object name | PixelLab object ID | Seed | Dimensions | Alpha | SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| `prop-ruined-entry-rubble.png` | Ruined Entry Rubble Pile | `82fc4c44-4ff1-4600-ace6-f4d85a65eea6` | 640001 | 64×48px | RGBA, 0–255 | `cf8cbee12a09c6cb2402fa4dfed963b1b769bec453ea7a168eac839732b470b6` |
| `prop-bone-archive-shelf.png` | Bone Archive Shelf | `089f35da-b826-4c84-89df-fc81885d8336` | 640002 | 48×96px | RGBA, 0–255 | `ef9014c91768355907fef1fd8cb459f7a144bde94062091b0140b7ff05ff764b` |
| `prop-chapel-of-ash-pew.png` | Chapel of Ash Pew | `892b1926-08a3-4e35-b3ba-514028596306` | 640003 | 96×48px | RGBA, 0–255 | `70c589721582d58eb7a1f3e2b1b09cea5101379d342bfcd884b8296a3ad0ceb0` |
| `prop-column.png` | Chapel and Vault Column | `cfd5abf6-bc40-48fb-9154-c6e65e616d5f` | 640004 | 32×96px | RGBA, 0–255 | `7b7b178702346271952fce3ec60f2346e1921112b7ecad907aa5d9a9bad9e779` |
| `prop-lower-vault-storage.png` | Lower Vault Storage Cluster | `d8be8b93-fc0d-4d2b-8a5d-caf99958ab80` | 640005 | 64×64px | RGBA, 0–255 | `f970f851d6f4590cfbb8a4dd5c63c8a897b2e36b57f066f19bee53e7e56cb460` |
| `prop-final-room-obelisk.png` | Final Room Central Obelisk | `d75c4532-d432-42c5-b1c6-4203f8e0a5a5` | 640006 | 64×96px | RGBA, 0–255 | `db451d49ac5ffe4e8506288ddbda813322a3949489e565e3d37e2cdedee594f6` |

Full per-prop description prompts (each also carried the shared suffix above):

| Prop | Description prompt (subject clause) |
| --- | --- |
| Rubble Pile | "A pile of collapsed dark stone masonry rubble with broken column fragments and loose scattered debris, low sprawling clutter silhouette," |
| Archive Shelf | "A tall weathered wooden archive shelf unit stacked with bone piles, dusty scrolls, and cracked pottery jars, upright furniture silhouette," |
| Chapel Pew | "A weathered wooden chapel pew bench with a faint carved sigil and a light dusting of ash, low horizontal furniture silhouette," |
| Column | "A freestanding gothic dark stone support column with a cracked capital and a worn base, tall slender silhouette," |
| Storage Cluster | "A cluster of stacked wooden storage crates beside a sealed barrel bound with iron hoops, grouped clutter silhouette," |
| Central Obelisk | "A dramatic freestanding ritual stone obelisk altar with dripping candle wax and a faint carved sigil, tall central landmark silhouette," |

## Inventory: five-room mapping and Tilemap vs. SpriteRenderer use

| File | Unity use | Rooms supported |
| --- | --- | --- |
| `architecture-kit-floor-flagstone.png` | Isometric **Tilemap** tile (repeatable floor) | All five: Ruined Entry, Bone Archive, Chapel of Ash, Lower Vault, Final Room |
| `architecture-kit-wall-brick.png` | Isometric **Tilemap** tile (repeatable wall run, 26px horizontal stride) | All five |
| `prop-ruined-entry-rubble.png` | Transparent **SpriteRenderer** prop, independently sortable | Ruined Entry (collapsed masonry rubble around the broad circling route) |
| `prop-bone-archive-shelf.png` | Transparent **SpriteRenderer** prop | Bone Archive (tall shelf bank forming narrow aisle lanes) |
| `prop-chapel-of-ash-pew.png` | Transparent **SpriteRenderer** prop | Chapel of Ash (pews flanking the central aisle/side routes) |
| `prop-column.png` | Transparent **SpriteRenderer** prop | Chapel of Ash (line-of-sight-breaking columns) and Lower Vault (columns creating incomplete loops) |
| `prop-lower-vault-storage.png` | Transparent **SpriteRenderer** prop | Lower Vault (storage piles alongside columns) |
| `prop-final-room-obelisk.png` | Transparent **SpriteRenderer** prop | Final Room (the room's one central obstacle/dramatic focal structure) |

This satisfies AC-002 (every named room has at least one supporting motif)
without adding gameplay geometry: none of these files were placed in the
scene, and no collider, sorting layer, or prefab was created.

## Selection review (VAL-002)

- **Palette/lighting coherence:** every source reuses the wizard's exact
  "deep plum and teal-black shadow / warm lantern-glow highlight" phrase and
  the same `low top-down` PixelLab camera, so environment and character read
  as one presentation (AC-003, AC-004).
- **Tone:** no graphic gore, no franchise imagery; props lean "worn and
  charming" (patched shelf clutter, a dramatic-but-not-grisly obelisk) per
  the dark-but-cute horror-comedy direction (AC-004). Compared directly
  against `R16.png`/`R17.png` (the supplied Diablo-style hazard/gore
  references) and deliberately diverged from their graphic spike/blood
  imagery.
- **Edge/tiling coherence:** see the wall-piece correction above; floor tile
  transparency and diamond footprint were visually spot-checked in the
  contact sheet and read as a normal isometric floor diamond.
- **Minimal set:** 8 total selected files (2 architecture + 6 props), within
  the 12-source bound, one PixelLab generation attempt per motif (the
  building kit counts as one architecture-kit generation; each prop is a
  separate motif), well inside the "at most 2 iterations per motif" limit.
  No motif required a second paid iteration.
- **This does not claim the Unity world is authored.** These are still
  loose source images; no Tile/Sprite asset, prefab, or scene placement
  exists yet (see Scope and boundary above).

## Human review

- Contact sheet: `Docs/Art/Environment/PIXELLAB_CONTACT_SHEET.png`
- Wall-repeat evidence: `Docs/Art/Environment/PIXELLAB_WALL_REPEAT_CHECK.png`
- Selected sources: `Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source/`

Vincent's visual approval has not been requested or claimed by this task.

## PixelLab account usage

`get_balance` before this task's first generation: $30.00 credit,
4827/5000 generations remaining this cycle (173 used). After all generations
in this task: $30.00 credit unchanged, 4777/5000 remaining (223 used) —
50 generations consumed by this task (1 building kit + 6 single-direction
object generations; the 4 failed-validation retry attempts were not billed).
