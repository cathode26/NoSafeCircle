# Handoff: remaining art-bible edits from the 2026-09-16 density and Lantern Wraith jobs

From: Art Director Agent. To: Documentation Agent.

## What is needed and why

Vincent picked density option B and Lantern Wraith wisp A on 2026-09-16. `C:\Users\VincentLiguori\.claude\agents\art-director.md` already records both picks (section 2 "Pixel density: DECIDED", section 5 "Attack look: PICKED"), and the guide's section 11 item 1 is updated. Three gaps remain. Apply them with a dated note.

Vincent's words (2026-09-16): "Yes, update the art bible, ask the documentation agent to fix it."

Evidence for every fact below: `C:\nscrev\reports\art-director\density-trial-20260916\plan.md` and `C:\nscrev\reports\art-director\lantern-wisp-20260916\plan.md` and `provenance.md`.

## Edit 1: bible section 3, "Motion." bullet

After the sub-bullet "PixelLab south walks drift toward the camera: the feet jump 3-11 px when the loop restarts. Measure it and report it.", add:

```text
  - The camera follows the wizard with a fixed offset (`IsometricCameraFollow.LateUpdate`), so the wizard holds one sub-pixel screen position while walking and only his frame-to-frame detail changes. Enemies and the scrolling world move under the camera, so motion shimmer shows on them. Judge wizard walks frame by frame; judge enemies with moving GIFs.
```

## Edit 2: bible section 6, after the `create_object_pro_flash` bullet

Add these bullets:

```text
- **`image_to_pixelart`** flattens a transparent source onto an opaque gray background and has no background option. `create_character` v3 given that image as its reference still returned transparent rotations (density trial, 2026-09-16).
- **Measured costs (2026-09-16):** at 128 px, `create_character` v3 with a reference image costs 2 generations and `animate_character` v3 costs 2 per direction (152x152 raw canvas with a 12 px empty margin per side). At 32x32, `animate_image` with 4 frames costs 1 (its index 0 is the input, re-encoded). `create_image_pixflux` and `create_image_pixen` cost 1 each.
- **`inpaint_image_pro_flash`** keeps unmasked pixels byte-exact (Lantern Wraith wind-up: 1312 pixels changed, 0 outside the mask) and costs about 6 generations at 128x128 (provisional quote), far below `inpaint_image` (20-40). It adds dozens of near-duplicate colors inside the mask (8 colors became 91), so plan a PixelLab `reduce_colors` pass for a picked result.
- **Forcing a small glow effect to a character's own few colors kills the glow.** The wraith's 8 colors gave flat, pale wisps. Pass `color_image` a ramp palette around the accent instead, e.g. `#123c3f`, `#1d7f7a`, `#30e0cb`, `#7ff2e0` for teal.
- **Provisional prices can differ from the charge.** On 2026-09-16 the shared balance moved 1 generation more than the tools reported across 20 generations. Count from the tool results, but keep a 1-2 generation margin under a spending cap.
```

## Edit 3: bible section 5, Ranged Enemy, "Attack look: PICKED 2026-09-16"

Replace the two sub-bullets

```text
  - **Projectile, the "lantern wisp":** a 32x32 teal ghost-flame with a grumpy face as the playful detail.
  - **Hit:** a ring pop.
```

with

```text
  - **Projectile, the "lantern wisp":** a 32x32 upright teal ghost-flame with a grumpy face (angry slanted eyes, small frown) as the playful detail. It uses 5 colors (a teal ramp, a pale bone core, a black outline) and needs no rotation in flight.
  - **Hit:** the flame collapses while a ring of teal light spreads, then sparks scatter and fade (4 frames). It was made from the no-face variant; the face vanishes in the pop.
  - **Sample files** (in the samples folder below): wind-up `pixellab/windup_se_128.png`, wisp `pixellab/wisp_A2_still.png`, hit `pixellab/hit_C2/frame_1.png` to `frame_4.png`.
```

## Check: guide section 11, item 2

`C:\NSC\nsc-art-director-guide.md`, section 11 item 2 ("Ranged Enemy: DECIDED 2026-09-16"). If it doesn't yet say the look was picked, add: "Look picked 2026-09-16: Vincent chose 'grumpy face', sample A; see section 12, 'Ranged enemy attack' row."

## Constraints

- Change only the text above; keep everything else in both files byte for byte.
- Don't touch the art in `C:\nscrev\reports\art-director\`.

## Done means

The three edits and the check are applied. Reply to the Art Director Agent with the changed section headings, and tell Vincent in two lines.
