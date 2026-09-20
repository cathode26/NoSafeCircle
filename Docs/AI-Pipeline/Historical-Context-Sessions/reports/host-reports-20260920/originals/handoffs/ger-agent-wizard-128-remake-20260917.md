# Handoff: contract the 128x128 wizard source remake (density decision B)

From: Art Director Agent. To: GER Agent. Board row H-20260917-21. 2026-09-17.

## What is needed

Contract an **art-acquisition task** in which the Art Director Agent remakes the four approved wizards at game density:
- 128x128 canvases at 64 PPU, shown in a 2x2-world-unit camera-facing box;
- all 8 standing directions and 6-frame walks in all 8 directions.

It pairs with the **wizard Visual integration** contract the Game Agent already asked for (uniform camera-facing box plus sorting check). Put the PixelLab spend go on Vincent's consolidated decision list.

## Why (Vincent's words)

- Density pick, 2026-09-16: "The wizard should be 128x128"; on the one-facing trial, "yes" (option B: re-make characters at game size).
- Playtest of NSC-077, 2026-09-17, relayed by the Game Agent. The enemies were at 64 PPU in a camera-facing 2x2 box:
  - "The enemies look great."
  - "the wizards dont look nearly as good sadly".
  - "Whatever you have done to make the enemy look great and in perspective, the wizards need that treatment."
- His screenshots show the thin, leaning wizard: `localScale (1,2,1)`, identity rotation, 180 PPU; about 15x96 px at 1080p.
- Evidence: `C:\nscrev\reports\art-director\density-trial-20260916\plan.md`.

## Inputs

- **Approved 180 px sources on main:** `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/<key>/selected/standing/<direction>.png` and `.../walk/<direction>/frame_000-005.png`, for keys `masculine-light`, `masculine-dark`, `feminine-light`, `feminine-dark`. Records: `Docs/Art/Wizard/PIXELLAB_GENERATION.md`, `.../PixelLab/source-inventory.json`.
- **PixelLab characters (180):**
  - masculine-dark `10a82915-82e8-48a3-92bd-a261b2d992e1`;
  - feminine-dark `c00d5bec-0da3-4bce-8d7c-dc2f5d2c33d4`;
  - masculine-light `3b41ccd5-0eb7-4b0b-9f1e-04b3956c5c75`;
  - feminine-light `c0be0b26-4477-4d1b-b6f0-cf57f3213a4f`.
- **The trial's 128 px masculine-light character:** `1d1cd21e-dd13-4bcc-9e0d-4c56f84e5e80`, with 8 rotations and a south-east walk, already downloaded in the density-trial folder.
  - It can be reused as the masculine-light starting point if its rotations pass review, saving 3 generations.
  - Its south-east walk has a 6 px feet jump at the loop seam and needs a re-roll or a custom start frame.

## Production path per wizard (measured costs from the 2026-09-16 trial)

1. `image_to_pixelart`: faithful, `init_image_strength` about 150, output 128x128, on the approved `standing/south.png` via a pinned raw URL. 1 generation. (It returns an opaque gray background; v3 rotation still returns transparent sprites.)
2. `create_character` v3 with `reference_image_url` = the step-1 result. 2 generations; gives 8 rotations.
3. **Review the 8 rotations against the approved 180 standing sprites:**
   - identity: hat and band, hair or beard, face, coat or robe, belt book, boots, no staff;
   - facing labels are screen facings;
   - a gameplay-scale read.
   - Repair defects with masked inpaint before animating.
4. `animate_character` v3, one call per direction, `frame_count 6`, with an action description naming the identity items (as in NSC-073/074). About 2 generations per direction at 128, so 16 per wizard.
5. Lossless normalize of the 152 px raw frames to 128. Record raw size, bbox, offset and SHA-256.
6. Continuity metrics (opaque count, bbox, loop-seam feet jump) with the art-review toolkit (`C:\nscrev\art-tools\ArtReview`: `frame-metrics`, `normalize`, `gamescale`, `gif`). Then Vincent's pick per wizard.

**Estimate:** about 19 generations per wizard, 76 base, **about 80-100 with re-rolls**. Masculine-light can reuse the trial character.

## Files (proposal)

- **Keep the approved 180 px sources untouched** as the fallback until integration switches.
- **New source root:** `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128/<key>/selected/standing/<direction>.png` and `.../selected/walk/<direction>/frame_000-005.png` (4 x (8 + 48) = 224 PNGs).
- **Raw exports under `Docs/Art/Wizard/Raw128/<key>/...`,** with no `.meta`, following the NSC-078 precedent that avoids stub-meta cubemaps.
- **Inventory:** `.../PixelLab128/source-inventory.json`: per frame `raw_size`, `raw_alpha_bbox`, `padding_offset`, `raw_sha256`, `selected_sha256`, plus PixelLab IDs and prompts.
- **Rejects:** the local `art-rejects/<task>` branch, per the new rule.
- **Import:** match the approach the Visual integration contract uses, either a committed importer postprocessor (like NSC-078 rev 4) or the builder's `ImportWizardSprite` at 64 PPU, pivot (0.5, 0), Point, uncompressed, 2D shape, with a Game Agent `unity-runner` import. Say which in the contract, so the art task doesn't produce stub metas that import as cubemaps.

## Coordination with the Visual integration contract

- **Define the wizard Visual as a 2x2-world-unit camera-facing box, independent of source PPU,** the same treatment NSC-077 gave the enemies.
  - The current 180 px art can ship first at 0.75x at 1080p (exactly 1:1 at 1440p).
  - The 128 px remake later changes only the source root and import PPU (64).
- **Tests to revise when integration switches:** `WizardArtIntegrationTests` (180 PPU, Point) and `WizardCardinalSourceAuditTests` (96 cardinal 180 px frames).
- **Sorting:** the door sprite drawn over the wizard's upper body belongs to the integration sorting check, not the art.

## Decisions for Vincent's list

1. PixelLab spend go for the 128 px wizard remake (about 80-100 generations).
2. Order: ship the Visual integration fix first with the current 180 px art (the thin, leaning look goes away at once), then swap in the remake? The Art Director recommends yes.

## Done means

- The remake contract is drafted and committed, and these two decisions are on Vincent's list.
- After his go, the Art Director Agent executes it.
- Reply to: Art Director Agent.
