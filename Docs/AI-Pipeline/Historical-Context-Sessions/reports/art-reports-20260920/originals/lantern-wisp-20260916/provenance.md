# Lantern Wraith attack samples: provenance (2026-09-16)

Samples for Vincent's pick. Nothing here is committed or integrated. Full reasoning, prompts and verdicts: `plan.md`. Download log with every URL and SHA-256: `downloads.json`.

## Source

| File | Size | SHA-256 | Pinned URL |
|---|---|---|---|
| `Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_se_idle_00.png` (repo, read only) | 128x128, 8 colors | `33a6bb9dba7c8d678c0c82e20aa0b9bd51235643ba113c6db63650b41d7d209d` | `https://raw.githubusercontent.com/cathode26/NoSafeCircle/96a6293c47cf2346b5c98f968e8790ce561674d3/Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_se_idle_00.png` |

## Generation inputs (parameters, not art)

| File | What | SHA-256 |
|---|---|---|
| `inputs/windup_mask_128.png` | Inpaint mask, white = regenerate: lantern and halo (89,18) 30x30; hood interior (55,33) 26x28; 1628 px | `5a35320afe42cb635062736b49fd7bddce2e20f713825b89c6ee6e126359b839` |
| `inputs/wisp_teal_ramp_palette.png` | 10-color forced palette for A2 and C2 | `c1f64929e3e0aed39f8f8bb2d1eacb5e92b123cd3207d384e0d4e8f93ccea028` |
| `inputs/wisp_strip_96x48.png` | Flicker-loop input: the three stills placed on transparency. Prepared, **not used** | `f16d8a762204fe897f737c7c010a1e9ef5868419e69dcfb83d80d64605a39626` |
| `inputs/wisp_B2_still_pad48.png`, `inputs/wisp_C2_still_pad48.png` | Lossless 8 px transparent pads for a hit re-roll. Prepared, **not used** | `79c79630...`, `4a12afcd...` (full hashes in `inputs/pad48_report.json`) |

## Candidates shown to Vincent

| Part | Tool and mode | PixelLab ID | Seed | File | Size | SHA-256 | Generations |
|---|---|---|---|---|---|---|---|
| Wind-up (shared) | `inpaint_image_pro_flash`, "Modify current layer", mask above | job `ebe47446-60c2-4db4-b178-e0783b75142d`, image `38c0965d-1ff0-5fcc-9003-0894da4ec72b` | 20260916 | `pixellab/windup_se_128.png` | 128x128 | `9ee59351380322afdb79fc8f961fcd4f634cc952fef21c5d1e08e2474eafdd8d` | 6 (provisional estimate) |
| Wisp A: grumpy ghost-flame | `create_image_pixflux` 32x32, teal ramp palette, single color black outline | `53d87d74-31f7-4760-9e78-600a21ca8ce5` | 1102 | `pixellab/wisp_A2_still.png` | 32x32 | `2ecdfe8abba1d0e82b98c06b2c49088614c932e4bb15f4bb9281f935ccc19c7c` | 1 |
| Wisp B: grumpy skull-comet | `create_image_pixen` 32x32, selective outline | `1f854150-ab7d-4e70-931f-b275f2680cab` | 2203 | `pixellab/wisp_B2_still.png` | 32x32 | `f6c5ecd2545be3637d5e7a80806b0e27cf4f40979e2c84389e34903cf0cc2a82` | 1 |
| Wisp C: ghost-flame, no face | `create_image_pixflux` 32x32, teal ramp palette, single color black outline | `e1e9efad-63f9-4b08-bf84-014391c0656e` | 1102 | `pixellab/wisp_C2_still.png` | 32x32 | `a6555e5bb89b14330b9b01d50c95da79089dc647aeef11b020904a48220a7c53` | 1 |
| Hit, shared (from C) | `animate_image`, frame_count 4 | `1795a439-4047-4e22-9269-99a7d6c27f0f` | 3323 | `pixellab/hit_C2/frame_1.png` to `frame_4.png` (frame_0 = input) | 32x32 | see `downloads.json` | 1 |
| Hit, B's own (weaker) | `animate_image`, frame_count 4 | `27041bc9-1a9c-42c0-b400-2016819de1f1` | 2222 | `pixellab/hit_B2/frame_1.png` to `frame_4.png` (frame_0 = input) | 32x32 | see `downloads.json` | 1 |

Exact prompts for every row are in `plan.md` (sections 1, 2b and 4).

## Rejected (kept, not shown)

| File | PixelLab ID | Seed | SHA-256 | Why |
|---|---|---|---|---|
| `pixellab/wisp_A_still.png` | `d0c65268-6ea9-41bf-aa0d-ad7dc9bf2a28` | 1101 | `32781656d51d92d1ea88dd558067defa8dec5dbfbdf19685572d535d672c3f1f` | Pale blob, almost no teal, no trail |
| `pixellab/wisp_B_still.png` | `5ac6baf1-2396-4efe-9f8e-40c3a557bdbf` | 2202 | `8814f96ea1d03c460896d4a0a1e376afff8107d9e767c072dfb74e064893b2dd` | Grey ghost creature, off-brief colors |
| `pixellab/wisp_C_still.png` | `f2180612-395e-4e01-adcb-ecace1ad7752` | 3303 | `6eb354d282914254d3c9d77cf700e3bc4a1d9381a2e2562bc17ad98475e27457` | Patchy marble, no trail |

These three used `create_image_pixflux` 32x32 with the wraith's own 8 colors forced (1 generation each).

## Generations

- Tool-reported, Job 2: 6 + 3 + 3 + 2 = **14**.
- Shared balance: 4689 remaining at session start, 4669 after both jobs. That change of 20 covers this job's 14, the density trial's 5 and 1 unattributed generation (only this session's jobs were listed). This job may have reached the 15 cap, so spending stopped.

## Checks done (non-Unity)

- Wind-up: 1312 changed pixels, all inside the mask, 0 outside (`tools/check_windup_diff.py`, `inspect/windup_vs_idle_6x.png`). The inpaint added 84 colors (91 in total) and removed the signature teal `#30e0cb`, so 7 of the 8 originals remain. Corrected 2026-09-17 from "83" after the art-review toolkit's `mask-diff` recount.
- Stills: size, alpha bbox, opaque count and palette recorded; viewed at 8-10x on `#1d1631`.
- Hits: per-frame opaque counts recorded; viewed at 7x.
- No fire colors: a hue scan of the wind-up, all three stills and all ten hit frames found **0 warm pixels** (hue below 70 or above 330 degrees with saturation and value above 0.3). A2 and C2 hold only the forced palette; B2 has 55 teal, bone, blue-teal and violet colors.
- Game-scale and motion checks: `wisp_gamescale_1x.png` and the GIFs, a simulation. The in-game look is only proven in Unity.
