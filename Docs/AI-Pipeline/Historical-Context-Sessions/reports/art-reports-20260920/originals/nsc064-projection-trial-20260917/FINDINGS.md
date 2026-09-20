# NSC-064 projection trial: findings

Art Director Agent, 2026-09-17. Vincent: "projection trial is fine so b". The GER Agent asked for two numbers for
the NSC-064 revision: the piece count at model (b), and whether the checkerboard floor defect disappears under
camera-plane projection.

**No PixelLab generations were spent on these two answers.**

## 1. The checkerboard floor: yes, (b) fixes it, and the cause is double projection

The committed placeholder floor is a **2:1 diamond drawn into a 64x32 texture**
(`DoorPrototypeSceneBuilder.CreateArchitecturalTileSet` -> `CreateDiamondPixels(64, 32, fill 80/76/70, edge
49/46/43)`) painted at 64 pixels per unit on a Tilemap rotated `Euler(-90, 0, 0)`, so the texture lies flat on the
world XZ plane and the isometric camera projects it a second time.

`tools/project_floor.py` renders a 7x7 patch of that exact tile under both models, using the camera's own screen
basis (`right (0.70711, 0, 0.70711)`, `up (-0.35355, 0.86603, 0.35355)`, 67.5 screen pixels per world unit at
1080p). See `projection_comparison.png`:

- **(a), today:** each diamond is re-projected into a narrow sheared lozenge. The pieces **do not tessellate** -
  dark background shows between them - so the floor reads as a lattice of separate diamonds rather than a
  surface. That is the checkerboard Vincent reported on 2026-09-15.
- **(b), camera-plane:** one diamond per 1x1 ground cell, drawn in screen space. The pieces tile into a
  continuous floor with a clean grid of edges.

**The checkerboard is a projection defect, not only a placeholder-art defect.** Under (b) the tessellation is
exact. What remains under (b) is the placeholder's own dark edge, which draws a visible grid; real floor art with
surface variation removes that, and it is an art question rather than a geometry one.

**The cell size (b) has to hit:** a 1x1 ground cell projects to **1.41421 x 0.70711 world units**, which is
**95.5 x 47.7 px at 1080p** and **90.5 x 45.3 px at 64 pixels per unit**. Adjacent cells along one axis are half
a diamond apart, so the horizontal stride is 45.3 px at 64 PPU.

## 2. Piece count at (b): 58 from one `create_building_kit` call

From the NSC-064 candidate record (`codex/nsc064-connections-20260914:Docs/Art/Environment/PIXELLAB_GENERATION.md`):

- `create_building_kit`, isometric, returns **58 numbered pieces** - floor, 4 wall sides, corners, doorways,
  pillar, stairs - of which **20 are AI-painted** and the rest are geometrically derived.
- Cost: **20 to 40 generations**, by canvas size.
- The candidate was generated at `tile_size 32` and produced **52x58 px pieces with a 26 px horizontal stride**.
- Only the straight east-west wall run was checked on that candidate; vertical, corner and doorway continuity
  were never tested.

## 3. The open question a generation would answer

The candidate kit's 26 px stride is **about a third of the 45.3 px our 64 PPU grid needs**, so that kit cannot be
used as-is without upscaling, which the art rules forbid. `create_building_kit` takes `tile_size` 32 to 96 for
isometric and a `tile_view_angle`, so a kit at `tile_size 96` with `tile_view_angle 30` should land near our cell
size - but the mapping from `tile_size` to the delivered piece size and stride has to be **measured**, not
assumed, since 32 gave 52x58 and a 26 px stride rather than anything obviously proportional.

**Proposed trial, for Vincent's go:** one `create_building_kit` at `tile_size 96`, `tile_type isometric`,
`tile_view_angle 30`, `wall_tiles 2`, the canon wall and floor descriptions. Measure the floor piece's diamond
width and height, the wall stride, and whether the corner, doorway and vertical pieces butt without gaps. Cost 20
to 40 generations; **cap 45**, stop and ask beyond it. This is separate from the NSC-078 pilot's 120-generation
cap.

If the delivered stride cannot reach 45.3 px, the fallback is to lower the world cell size for room geometry,
which is a task-contract change and not mine to make - the GER Agent would own it.

## 4. A third case, which reframes the choice: unprojected art on the existing world plane

`world_plane_square_tile.png` renders a plain **square** 64x64 floor tile - flat fill, one-pixel darker border, no
pre-projection - on the same world-plane Tilemap, through the same camera. It **tessellates perfectly** into a
continuous isometric floor, indistinguishable in result from model (b).

So the world-plane approach is not the defect. **Pre-projected art on a world plane is.** Either model gives a
clean floor as long as the art's projection is authored exactly once:

- **(a), fixed:** keep the Tilemaps, collision, sorting and camera untouched; author floors as square top-down
  tiles and walls as flat elevations, and let the camera project them once. `create_building_kit` supports it with
  `tile_type: square_topdown`. Engineering cost: none.
- **(b):** camera-plane isometric Tilemap with PixelLab's isometric kit. The gain is real - 58 pieces with walls,
  corners, doorways, pillar and stairs pre-drawn in 3/4 perspective - at the price of the builder rework, and it
  places camera-plane sprites beside world-plane geometry, the same failure class that caused the checkerboard.

### The Game Agent's integer-pixel point, which matters

A 1x1 ground cell projects to 90.5 x 45.3 px at 64 PPU, which is **not** whole pixels, so a camera-plane cell of
that size would shimmer as the camera moves. Under **(b)** the fix is to quantise: a 90 x 45 px cell, meaning a
world cell of 1.40625 x 0.703125 units, exact multiples of 1/64. Under **(a)** the question does not arise at all:
a square 64 px tile is exactly 1 x 1 world units and the camera does the projection in floating point.

**Art-side lean: (a).** It fixes the real defect at zero engineering cost, keeps the geometry Vincent's playtest
already likes, and avoids inventing a non-integer world cell. (b) is worth it only if the kit's pre-drawn wall
perspective is judged worth the rework; that price is the Game Agent's to set, and Vincent asked the two of us to
recommend together.

**Trial, approved by Vincent as item 14, cap 45 generations:** one `create_building_kit` for whichever model wins -
`square_topdown` for (a), `isometric` for (b) - then measure the delivered piece size and stride rather than
assuming, since `tile_size 32` gave 52x58 px at a 26 px stride, which is not proportional to anything obvious.

## 5. Vincent chose (b), knowingly, and the trial is running

His words, relayed by the GER Agent: **"(b) pixel-crisp with pre-drawn 3/4 wall perspective, at ~3 contracts of
builder rework"** - decided with the zero-cost (a) alternative in front of him, and with the Game Agent's joint
recommendation of (a) on the table. The Game Agent had first accepted (b)'s rework on the premise that "under (a)
it stays", corrected that after the square-tile measurement, and priced (b) at roughly 3 contracts: collision and
navigation decoupling from visuals (the NavMesh bakes from world-plane colliders), two sorting models in one
scene, the floor's correctness becoming a function of camera state, and about 140 Tilemap assertions plus the room
and wall-tiling tests that assert world-plane facts.

**Target geometry for (b): 90 x 45 px at 64 PPU, world cell 1.40625 x 0.703125 units** - exact multiples of 1/64.
Not 90.5 x 45.3, which lands on a half-pixel stride and shimmers as the camera moves.

**Kit trial, cap 45, this task's own call log:**

| # | call | settings | printed | tile id |
|---|---|---|---|---|
| 1 | `create_building_kit` | isometric, `tile_size 96`, `tile_view_angle 30`, `wall_tiles 2`, `outline_mode segmentation`, seed 20260917, canon wall and floor descriptions | 20-40 by canvas (quoted 1K 20, 2K 25, 4K 40) | `85e1d50b-fa57-49a5-88b6-7558e53d4949` |

Balance before: 4537 remaining, 463 used, queue empty (shared with the NSC-078 pilot round 1, which is why each
task counts from its own call log).

**To measure and report:** the delivered floor piece's diamond width and height, the wall stride, whether the
corner, doorway, pillar and stair pieces butt without gaps, and the closest achievable cell if 90 x 45 is not
reachable - the GER Agent takes the fallback decision (smaller world cell, or a PPU where the projection lands on
integers) rather than me.

## 6. Both kits measured, and the grid arithmetic that follows

| Kit | `tile_size` | piece canvas | floor diamond drawn | wall sides | colours | cost |
|---|---|---|---|---|---|---|
| `85e1d50b-fa57-49a5-88b6-7558e53d4949` | 96 | 154 x 173 | **96 x 48** (+1 px tip row) | 67 x 130 | 15-27 | about 40 |
| `c0142f96-ecc9-43b5-a935-4e8f41db75aa` | 90 | 144 x 162 | **90 x 45** (+1 px tip row) | 62-63 x 121-122 | 22-25 | about 40 |

Both are already in the game's colour register (wizard 63, enemy 32), so **the kit needs no colour reduction** -
unlike the props, which came back at 1831-7254 colours.

**What a 1x1 ground cell measures on screen** (width = 1.41421 x screen px per world unit):

| camera | 1080p | 1440p |
|---|---|---|
| orthographic 8.0 (today) | 95.46 x 47.73 | 127.28 x 63.64 |
| orthographic 7.955 | **96 x 48** | **128 x 64** |
| orthographic 8.485 | **90 x 45** | 120 x 60 |

So "90 x 45 at today's camera" was arithmetically unreachable: at orthographic 8 a cell is 95.46 px wide, not an
integer at any `tile_size`, and the cap is 96. Scale error with the camera untouched: **96 px art +0.57%**,
**90 px art -5.72%**. The 90 px kit is a write-off of about 40 generations - the cost of learning that the mapping
from `tile_size` to delivered geometry is not proportional, which is why the measurement was funded.

**A third argument for the 0.045 tweak, visible in a still.** At orthographic 8 the per-cell stride is
47.73 x 23.86 px, so whole-pixel snapping makes a wall run's spacing **alternate 48, 47, 48, 48, 48, 47, 48** -
a 1 px rhythm break along every run, a property of the stride rather than of the art. At 7.955 the stride is
exactly 48 x 24 and it disappears.

## 7. Reference image for the Game Agent's Tilemap experiment

`reference/wall_reference_1920x1080.png` with `reference/wall_reference.json`. It is the expected appearance of a
correct camera-facing 8-cell wall run, to the Game Agent's stated parameters, using the 96 px kit's piece 1.

**Why a reference and not a verdict:** my renders are my own arithmetic drawn in Pillow. That settles "what does
this projection look like", because the maths determines the picture. It cannot discover what Unity's Tilemap
renderer does with `orientationMatrix` - there it would only draw my assumption and look like proof. So Unity
renders both cases, per-tile sprites as the control, and diffs them against this reference.

Two numbers they must match or their camera differs from the builder's: the world origin lands at screen
**(960.0, 647.27)**, 107 px below centre because the camera position (10, 10, -10) is 1.589 world units off its
own forward axis; and the run's content bbox is (941, 575) to (1342, 872). Per-cell blit coordinates are in the
JSON so a mismatch is diagnosable.

**Caution that survives a positive result:** the wall visual Tilemap carries no collider - gameplay collision is
separate BoxColliders and the NavMesh bakes from those - so under (b) the drawn wall and its collider occupy
different screen areas in **either** representation. That is a property of (b) itself and wants an alignment
guard regardless of how the Tilemap question resolves.

## 8. Accepted into NSC-064 (GER Agent, 2026-09-17)

- **Camera:** Vincent took the tweak, **orthographic 8 -> 7.955**, with the **96 px** kit shipping. The reference
  regenerated at 7.955 came back with x strides uniformly **48** and the 48/47 jitter gone, which is the
  confirmation the change was chosen to produce. The 90 px kit is shelved, about 40 generations written off.
- **Geometry asserted as two separate facts, as I framed it:** stamping **pitch 96 x 48** and **drawn extent
  96 x 49**. Collapsing them is how a builder ends up with a one-pixel error it cannot explain.
- **Tip pixel:** accepted as a harmless artefact, covered by neighbours in any floor interior, **not repaired**.
- The contract will quote the measured kit: 58 pieces, 154 x 173 canvas, wall sides 67 x 130, corners
  37-38 x 115-116, pillar 38 x 115, door 67 x 113, stairs 96 x 97, 15-27 colours, no colour reduction.
- NSC-064 still waits on two inputs that are not mine: the Game Agent's `orientationMatrix` render result, and the
  final re-quote.
