# Lantern Wraith attack samples: wind-up, lantern wisp, hit (2026-09-16)

Art Director job. Samples for Vincent's pick, not a task deliverable: no task ID, checkout, branch, commit or viewer marker. `C:\NSC\NSC\NoSafeCircle` is read only.

## Approval and decision

- Vincent approved Lantern Wraith attack samples, at most 15 PixelLab generations (2026-09-16, launch prompt `C:\nscrev\reports\art-director\launch-prompt-density-and-wisp-20260916.md`).
- Decision being illustrated (bible section 5; guide section 11 item 2): the in-game ranged enemy becomes the Lantern Wraith and its fireball becomes a ghost-light attack. Vincent, 2026-09-16: "The enemy in the game will change to a latern ghost so it will need to change its attack, to whatever a latern ghost would cast." Gameplay is unchanged; only the look changes.
- Vincent, 2026-09-16, mid-job: "send it to subagent if it is easy so a lower cost subagent can do it." The mechanical sheet and GIF building goes to an `art-director` subagent on Sonnet; PixelLab calls and candidate review stay here.

## Vincent's decision (2026-09-16)

- Question, after the review images were opened in the session side panel (`wisp_sheet_4x.png`, `wisp_gamescale_1x.png`, `wisp_A_3x.gif`, `wisp_B_3x.gif`, `wisp_C_3x.gif`): "Wraith attack: which wisp: A (grumpy flame), B (skull-comet) or C (flame, no face)?"
- Vincent: **"grumpy face"**. Recorded as **A: grumpy ghost-flame**, the only option labeled "grumpy" in that question, and the face version rather than C:
  - projectile: `pixellab/wisp_A2_still.png` (SHA-256 `2ecdfe8abba1d0e82b98c06b2c49088614c932e4bb15f4bb9281f935ccc19c7c`);
  - wind-up: the shared `pixellab/windup_se_128.png`;
  - hit: the shared ring-pop hit, `pixellab/hit_C2/frame_1.png` to `frame_4.png`.
  B (the skull-comet) also had a face; he can correct this record if he meant B.
- These are picked samples, not finished assets. Nothing is committed. Still to do, with his spend go where it costs generations: the other seven facings' wind-up frames, a flicker loop, cleaning the wind-up's colors, a hit re-made from the face wisp if wanted, and integration through a revised contract.

## Game facts used (read from code)

| Fact | Source |
|---|---|
| Today's in-game caster: `FireCasterEnemy` with `EnemyFireballCaster`; projectile is a Unity Sphere primitive at `localScale 0.45`, color (1, 0.25, 0.1), speed 8 units/s, cast interval 1 s, lifetime 4 s | `Scripts/Enemies/EnemyFireballCaster.cs` lines 14-22, 114-121 |
| GDD ranged attack components: `RangedEnemyAttack.windUpSeconds = 0.4`, `cooldownSeconds = 1`; `RangedEnemyProjectile.speed = 3`, `lifetimeSeconds = 5` | `RangedEnemyAttack.cs` lines 13-14, `RangedEnemyProjectile.cs` lines 9-10 |
| 0.45 world units = 30 screen px at 1080p (67.5 px per unit, orthographic size 8) | derived |
| Wizard spells to stay distinct from: Fireball (orange), Frost Field (icy) | launch prompt |

## Source (read only)

`Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_se_idle_00.png`: 128x128 RGBA, alpha bbox (29,11)-(110,114), 3913 opaque px, SHA-256 `33a6bb9dba7c8d678c0c82e20aa0b9bd51235643ba113c6db63650b41d7d209d`.
- Exactly 8 colors: `#2f2c3c` x959, `#42414c` x897, `#1a1328` x843 (outline), `#6f477f` x321 (violet scarf), `#6b8270` x307 (grey-green staff), `#c6d4cd` x255 (bone), `#435a5b` x222, `#30e0cb` x109 (teal ghost-light).
- Lantern: teal ring about (95-110, 25-39) around a bone core, hanging from the staff hook. Hood interior: bone crescent rim about (57-79, 34-61) around a dark face with teal dot eyes at about (64-66, 47-50) and (73-75, 45-48). Inspection: `inspect/wraith_se_idle_8x_grid.png` (`tools/inspect_wraith.py`).
- Pinned URL (verified 2026-09-16: HTTP 200, bytes match the local file):
  `https://raw.githubusercontent.com/cathode26/NoSafeCircle/96a6293c47cf2346b5c98f968e8790ce561674d3/Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_se_idle_00.png`

## Costs checked before planning (tool descriptions and free quotes)

- `inpaint_image_pro_flash`: 6 at 128x128, 6 at 84x104, 5 at 64x64 (`get_pro_flash_capabilities` quotes, provisional). `inpaint_image`: 20-40. `edit_image`: 20-40. `edit_image_pro_flash`: 6 at 128x128.
- `create_image_pixflux`: 1. `create_image_pixen`: 1. `create_image_pro_flash`: 5 at 32x32.
- `animate_image`: scales with total pixels (64x64 x 8 frames = 1), so a 32x32 x 4-frame loop is expected to cost 1.

## Planned PixelLab calls (15 generations, the cap)

Pre-flight 2026-09-16: `list_jobs(include_recent=true)` showed no active jobs and none in the last 30 minutes. Shared-account balance at session start: generations remaining 4689, used 311 of 5000; credits $30.00. Job 1 spends first; the balance is re-read right before this job's first call.

### 1. Wind-up (one frame shared by all variants): 6 generations

`inpaint_image_pro_flash`:
- `image_url`: pinned wraith URL above;
- `mask_image_base64`: `inputs/windup_mask_128.png` (128x128 RGB, pure black/white, 1628 white px, SHA-256 `5a35320afe42cb635062736b49fd7bddce2e20f713825b89c6ee6e126359b839`, `tools/make_windup_mask.py`). White rectangles: lantern and halo margin x 89-118, y 18-47 (30x30); hood interior x 55-80, y 33-60 (26x28). Overlay check: `inspect/windup_mask_overlay_6x.png`;
- `description`: "Lantern Wraith charging its ghost-light attack: the round teal ghost lantern flares much brighter, with a brighter teal ring, a pale mint-white glowing core and a small halo of teal light pixels around it; the bone-white hood rim glows brighter and the two teal dot eyes shine brighter. Same crisp pixel art, same dark palette, single color dark outline, no fire colors, no orange, no yellow.";
- `output_method`: "Modify current layer" (full composite); `no_background` unset (follows the transparent source); `seed`: 20260916.
- Check afterwards: every changed pixel lies inside the mask.

### 2. Lantern wisp stills (32x32): 3 generations

`create_image_pixflux`, common: `width=32`, `height=32`, `no_background=true`, `view="low top-down"`, `shading="basic shading"`, `detail="low detail"`, `color_image_url` = pinned wraith URL (forces the wraith's 8-color palette, so no fire colors), `text_guidance_scale=8`.

| Variant | Outline | Seed | Description |
|---|---|---|---|
| A: grumpy wisp | single color black outline | 1101 | "tiny round teal ghost-light wisp orb with a pale bone-white glowing core and a tiny grumpy frowning face, short wavy teal ghost trail streaming behind it to the left, cute spooky magic projectile sprite, small and centered with empty transparent margin" |
| B: grumpy wisp with violet sparkles | selective outline | 2202 | "tiny round teal ghost-light wisp orb with a pale bone-white glowing core, a tiny grumpy frowning face and two small violet sparkles, short wavy teal ghost trail streaming behind it to the left, cute spooky magic projectile sprite, small and centered with empty transparent margin" |
| C: plain ghost-light, no face | single color black outline | 3303 | "tiny round teal ghost-light wisp orb with a smooth featureless pale bone-white glowing core, short flickering teal ghost trail streaming behind it to the left and one small violet sparkle, spooky magic projectile sprite, small and centered with empty transparent margin" |

### 3. Flicker loops: 3 generations

`animate_image` per variant: `first_frame_url` = that still's PixelLab download URL, `frame_count=4` (returns 5 images; index 0 is the input), `no_background` unset, seeds 1111 / 2212 / 3313.
- A: "ghost-light wisp flickering and pulsing in place, the trail wisps waving, the grumpy face stays the same, same size and position"
- B: "ghost-light wisp flickering and pulsing in place, violet sparkles twinkling, the trail wisps waving, the grumpy face stays the same, same size and position"
- C: "ghost-light wisp flickering and pulsing in place, the violet sparkle twinkling, the trail wisps waving, same size and position"

### 4. Hits: 3 generations

`animate_image` per variant: `first_frame_url` = that still's URL, `frame_count=4`, seeds 1121 / 2222 / 3323, action: "the ghost-light wisp bursts on impact: it squashes into a round teal puff that pops into a few small teal and bone-white sparks which scatter outward and fade away".

Order: 1 and 2 first; review the stills before spending on 3 and 4. A bad result or any cost above plan stops for Vincent's go; no re-rolls beyond 15.

## Review package (local Pillow only; built by a Sonnet art-director subagent from the downloaded files)

- `wisp_sheet_4x.png`: rows A/B/C; columns idle, wind-up, wisp still, loop frames 1-4, hit frames 1-4; 4x nearest; labeled.
- `wisp_gamescale_1x.png`: each variant at 1080p game scale beside the wraith and the wizard on `#1d1631` with a faint 1-unit (67.5 px) grid. Assumed camera-facing boxes: wraith 128 px canvas in 2 units (1.0547x), wizard 180 px canvas in 2 units (0.75x), wisp 32 px canvas at 64 px/unit (1.0547x, about 34 px). The wizard's orange Fireball placeholder color and a pale icy swatch go beside them for the distinctness check.
- `wisp_A.gif`, `wisp_B.gif`, `wisp_C.gif` (1080p scale) plus `_3x` nearest zooms: idle, then wind-up for 0.4 s; the wisp spawns at the lantern, flickers at about 10 fps and travels 6 world units screen-right (world (X+Z)/sqrt2) at 3 units/s (2.0 s, 202.5 px/s); the hit plays at the wizard at about 12 fps, then a short pause.
- `provenance.md`: tools, prompts, IDs, sizes, SHA-256, generations used.

## Results

Download log (URL, SHA-256, size, alpha bbox, opaque count per file): `downloads.json`.

### 1. Wind-up: done, 6 generations (PixelLab estimate; pricing provisional)

- Job `ebe47446-60c2-4db4-b178-e0783b75142d`, image `38c0965d-1ff0-5fcc-9003-0894da4ec72b`, parameters exactly as planned. Saved as `pixellab/windup_se_128.png`: 128x128, SHA-256 `9ee59351380322afdb79fc8f961fcd4f634cc952fef21c5d1e08e2474eafdd8d`, alpha bbox (29,11)-(118,114), 4129 opaque px.
- Mask proof (`tools/check_windup_diff.py`): **1312 pixels changed, all inside the mask; 0 outside.** Sheet: `inspect/windup_vs_idle_6x.png`.
- Look: the lantern flares with a hot core, a brighter teal ring and a dotted teal halo on its open (right and lower) side; the hood rim gains a teal glowing edge; the eyes become glowing teal orbs. It reads as charging.
- Flaws:
  - the inpaint introduced 84 new colors (91 in total, up from 8; corrected 2026-09-17 from "83" after the art-review toolkit's `mask-diff` recount). Only 7 of the 8 original colors remain: the signature teal `#30e0cb` is gone, replaced by nearby teals (`#41efdc`, `#63f5dd`, `#25b2a0`). Many new colors are near-duplicates of the charcoal shades, plus near-white core pixels (`#fcfefe`, `#fafdfd`, one `#ffffff`). A PixelLab `reduce_colors` pass should clean it and restore `#30e0cb` if this direction is picked;
  - the staff hook above the lantern lost a little of its curl inside the halo.

### 2. Wisp stills: first round rejected, 3 generations

| Variant | Job | File | Size, bbox, opaque | SHA-256 | Verdict |
|---|---|---|---|---|---|
| A | `d0c65268-6ea9-41bf-aa0d-ad7dc9bf2a28` | `pixellab/wisp_A_still.png` | 32x32, (8,9)-(24,23), 161 | `32781656d51d92d1...` | Rejected: pale bone blob with two grey marks, almost no teal, no trail |
| B | `5ac6baf1-2396-4efe-9f8e-40c3a557bdbf` | `pixellab/wisp_B_still.png` | 32x32, (5,7)-(27,26), 236 | `8814f96ea1d03c46...` | Rejected: grey squid-like ghost creature, only 2 teal pixels, no sparkles, no trail |
| C | `f2180612-395e-4e01-adcb-ecace1ad7752` | `pixellab/wisp_C_still.png` | 32x32, (7,7)-(25,25), 258 | `6eb354d282914254...` | Replaced: patchy teal and bone marble, no trail |

Cause: forcing the wraith's own 8 colors left one teal and no light teal, so nothing could glow. Sheet: `inspect/wisp_stills_10x.png`.

### 2b. Plan change (within the 15 cap): re-rolls, no standalone flicker loops

- Palette for re-rolls: `inputs/wisp_teal_ramp_palette.png` (10x1, SHA-256 `c1f64929e3e0aed39f8f8bb2d1eacb5e92b123cd3207d384e0d4e8f93ccea028`). It holds `#0b0908`, `#1a1328`, `#123c3f`, `#1d7f7a`, `#30e0cb`, `#7ff2e0`, `#c6d4cd`, `#e6f2ec`, `#6f477f` and `#a47fd2`: the bible outline, the wraith's outline, a teal ramp around `#30e0cb`, bone, pale bone, the scarf violet and the stone lilac. It is a generation parameter, not art.
- The optional flicker loops ("if cheap") were dropped to pay for the re-rolls. A and C share one hit animation, made from C. Only the hits are animated.

| Variant | Tool | Job | Seed | Prompt | File | Size, bbox, opaque, colors | SHA-256 |
|---|---|---|---|---|---|---|---|
| A2: grumpy ghost-flame | `create_image_pixflux`, 32x32, no_background, low top-down, basic shading, low detail, single color black outline, teal ramp palette | `53d87d74-31f7-4760-9e78-600a21ca8ce5` | 1102 | "glowing teal ghost-fire wisp orb projectile, bright teal flame-shaped glow around a small pale bone-white core, tiny grumpy face with two small angry slanted dark eyes and a frown on the core, short wispy teal comet tail trailing to the left, cute spooky pixel art sprite, centered with empty transparent margin" | `pixellab/wisp_A2_still.png` | (8,2)-(24,29), 284 px, 5 colors | `2ecdfe8abba1d0e82b98c06b2c49088614c932e4bb15f4bb9281f935ccc19c7c` |
| B2: grumpy skull-comet | `create_image_pixen`, 32x32, no_background, low top-down, selective outline, low detail, no palette | `1f854150-ab7d-4e70-931f-b275f2680cab` | 2203 | "tiny glowing teal ghost-fire wisp orb projectile with a pale bone-white core, a tiny grumpy frowning face on the core, two small violet sparkles, short wispy teal comet tail trailing to the left, dark-but-cute spooky pixel art, teal and bone-white colors only, no orange, no yellow" | `pixellab/wisp_B2_still.png` | (3,4)-(26,28), 325 px, 55 colors | `f6c5ecd2545be3637d5e7a80806b0e27cf4f40979e2c84389e34903cf0cc2a82` |
| C2: ghost-flame, no face | `create_image_pixflux`, same settings and palette as A2 | `e1e9efad-63f9-4b08-bf84-014391c0656e` | 1102 (same as A2) | A2's prompt with the face clause replaced by "plain featureless glowing core with one small violet sparkle beside it" | `pixellab/wisp_C2_still.png` | (8,2)-(24,29), 237 px | `a6555e5bb89b14330b9b01d50c95da79089dc647aeef11b020904a48220a7c53` |

Final stills sheet: `inspect/wisp_final_stills_8x.png`.
- A2 and C2 are upright teal ghost-flames that need no rotation in flight; neither rendered the requested violet sparkle.
- B2 is directional: its tail points up-left, so it reads as travelling down-right, toward the wizard in the wraith's south-east facing.
- Player Fireball placeholder for the distinctness check: sphere scale 0.5, color (1, 0.45, 0.1) (`DemoRunFlow.cs` lines 115-122). Frost Field has no visual in code yet (only `EnemyStatusEffectMovement` slowdown).

### 4. Hits: done, 2 generations

Action for both: "the ghost-light wisp bursts on impact: it squashes into a round teal puff that pops into a few small teal and bone-white sparks which scatter outward and fade away". `frame_count=4`; PixelLab returned 5 images (index 0 is the input still, re-encoded: same bbox and opaque count, different bytes).

| Hit | Job | Seed | From | Files | Opaque px, frames 0-4 | Verdict |
|---|---|---|---|---|---|---|
| Shared (A and C) | `1795a439-4047-4e22-9269-99a7d6c27f0f` | 3323 | C2 still URL | `pixellab/hit_C2/frame_0.png` to `frame_4.png` | 237, 199, 122, 52, 10 | Good: the flame collapses while a ring of teal light spreads, then scatters into sparks and fades. Sheet `inspect/hit_C2_7x.png` |
| B's own | `27041bc9-1a9c-42c0-b400-2016819de1f1` | 2222 | B2 still URL | `pixellab/hit_B2/frame_0.png` to `frame_4.png` | 325, 266, 227, 206, 209 | Weak: squashes to a puff that drips sparks but never pops or fades, and the face warps. Sheet only. Sheet `inspect/hit_B2_7x.png` |

All GIFs use the shared hit.

### Budget stop

- Shared balance after both jobs: generations remaining **4669**, used 331 (credits $30.00). The change since session start is 20.
- My tool-reported costs total 19 (Job 1: 5; Job 2: 14). `list_jobs` showed only my 13 jobs, so the extra generation is mine but unattributed. Most likely the Pro Flash inpaint's provisional price came in above 6.
- Job 2 may therefore already be at the 15 cap, so spending stopped. The optional flicker loop was skipped: one `animate_image` on a 96x48 strip of the three stills was prepared (`inputs/wisp_strip_96x48.png`, SHA-256 `f16d8a762204fe897f737c7c010a1e9ef5868419e69dcfb83d80d64605a39626`) but **not sent**. The 48x48 padded stills (`inputs/*_pad48.png`, for a hit re-roll) were not used either.

### Review package

Built by an `art-director` subagent on Sonnet from the files above: `wisp_sheet_4x.png`, `wisp_gamescale_1x.png`, `wisp_A.gif`, `wisp_B.gif`, `wisp_C.gif` and their `_3x` zooms. Provenance: `provenance.md`.
