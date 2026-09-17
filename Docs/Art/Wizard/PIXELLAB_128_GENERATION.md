# Wizard 128 px source generation record (NSC-095)

Art Director Agent, 2026-09-17. Companion to
`Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128/source-inventory.json`, which carries the
per-frame provenance. This file records the tools, prompts, settings, spend and rejects.

The approved 180 px sources under `Source/PixelLab/` and `Docs/Art/Wizard/PIXELLAB_GENERATION.md` are unchanged.

## Why these exist

- Vincent, 2026-09-16 (density decision B): "The wizard should be 128x128", and "yes" on the one-facing trial.
- Vincent, NSC-077 playtest, 2026-09-17: "The enemies look great." / "the wizards dont look nearly as good
  sadly" / "Whatever you have done to make the enemy look great and in perspective, the wizards need that
  treatment."
- Vincent's spend go, 2026-09-17: "Yes you have my permission", then "raise the cap, cost doesnt matter much on
  art, raise it 40".

## What shipped

224 transparent 128x128 PNGs: for each of the four approved identities, one standing frame per screen facing and
a six-frame walk in each of the eight facings.

| Wizard | Character | `ground_line_y_from_top` | Import pivot | Worst dip below the line (cap 6) |
|---|---|---|---|---|
| masculine-light | `1d1cd21e-dd13-4bcc-9e0d-4c56f84e5e80` | 122 | (0.5, 6/128 = 0.046875) | 4 px |
| masculine-dark | `02f0ec58-164f-428d-8b1b-7d5ad6c1ef6b` | 121 | (0.5, 7/128 = 0.0546875) | 5 px |
| feminine-light | `53aebb62-452d-4228-bda3-3a873a42f9eb` | 120 | (0.5, 8/128 = 0.0625) | 6 px |
| feminine-dark | `afabd47e-a66e-453d-beee-b90f9856f9e0` | 121 | (0.5, 7/128 = 0.0546875) | 5 px |

NSC-096 reads `ground_line_y_from_top` per wizard from the inventory and imports at 64 pixels per unit; the pivot
is one constant for all 56 sprites of a wizard, so turning never shifts the feet.

## Production path

1. `image_to_pixelart`, `faithful` true, `init_image_strength` 150, output 128x128, from the approved 180 px
   `standing/south.png` at pinned commit `96a6293c47cf2346b5c98f968e8790ce561674d3`. Jobs:
   masculine-dark `c7ba1b8f-8fe6-4b0b-942a-11be1a907fed`, feminine-light `e0b19178-3425-4197-9af7-ea0e737a9c85`,
   feminine-dark `158d6bd2-5f36-404e-9ce1-514d7520c580`. The result is opaque by design; v3 rotation still returns
   transparent sprites.
2. `create_character` mode `v3`, `reference_image_url` the step-1 result, size 128, view `low top-down`.
   masculine-light reused the 2026-09-16 density-trial character instead, at no generation cost, after its eight
   rotations passed the identity review.
3. Identity review of the eight rotations against the approved 180 px stills (hat and band, hair or beard, face,
   coat or robe, belt book, boots, no staff), at 3x and at gameplay scale.
4. `animate_character` mode `v3`, `frame_count` 6, **`keep_first_frame` false** so exactly six ordered frames are
   stored, one call per direction, four directions per call. Walk prompt per wizard, naming the identity items and
   pinning the colours, for example masculine-dark: "walking with a steady even stride, wide-brim pointed hat with
   its red band held level, long dark purple coat hem swinging with each step, brown belt with a gold buckle
   staying in place, arms swinging naturally, brown boots alternating, colours identical in every frame".
5. Lossless normalization to 128x128: v3 returns mixed canvases per direction (148, 152, 156 and 160 px in this
   batch), each centred by whole pixels with the offset recorded, refusing any shift that would move an opaque
   pixel off-canvas.
6. Ground-line alignment per group (one wizard and direction: the standing frame plus its six walk frames),
   shifted together by whole pixels so the group's planted row - the lower median of the six walk frames' lowest
   opaque row - lands on that wizard's single ground line. Never per frame, so the walk bob survives.
7. Verification before hand-off: `tools/verify_staged.py` re-runs VAL-001's assertions over all 224 files
   (paths, 128x128, transparent corners, inventory hashes, recorded alpha bottoms, the median rule, the dip cap,
   the pivot formula, raw export presence, no `.meta`). All passed.

Tools live in `C:\nscrev\reports\art-director\wizard-128-remake\tools\` with the evidence in `plan.md`;
alignment is `C:\nscrev\reports\art-director\wizard-ground-line-20260917\tools\ground_line.py` (22 tests).

## Defects found and fixed

| Wizard | Facing | Defect, as measured | Fix |
|---|---|---|---|
| feminine-light | north | a 5 px near-white band (`#fdfbf8`) at the boot top in 4 of 6 frames, reading as a white sock | re-rolled the direction; pale pixels now 0-2 per frame, all skin tones |
| feminine-dark | north-east | hat, dress and arm washed out to pale blue in frames 4 and 5; pale pixels per frame 0, 0, 0, 112, 399, 435 | re-rolled the direction; now 0, 2, 0, 0, 0, 0 |
| masculine-dark | south | the body dropped about 8 px halfway through the cycle (feet rows 106, 104, 107, 115, 113, 113), over the 6 px dip cap, so the aligner refused it | re-rolled with the prompt pinning head and shoulder height; dip now 4 px |
| masculine-light | south | loop seam of 10 px between the last and first frame | re-rolled with a seamless-loop prompt; seam now 7 px |

## Known characteristic, not yet fixed

The walk *toward* the camera drifts downward across its six frames and snaps back at the loop: masculine-light
7 px, masculine-dark 8 px, feminine-light 6 px, feminine-dark 3 px. Three of the four cycles behave this way even
after a re-roll, so it looks inherent to `animate_character` v3 for the south facing rather than a bad roll.
Measured in `review/continuity_summary.json`. Vincent has the numbers with the review package; the untried option
is v3's interpolation mode with the standing pose as both start and end frame.

## Identity exceptions (AC-001, recorded per the inventory requirement)

| Wizard | Facing | Exception | Reason |
|---|---|---|---|
| masculine-light | west | no belt book | the v3 rotation dropped it. Vincent, 2026-09-17: "accept the gap" |
| feminine-light | east | no belt book | as above, same approval; north-east carries it faintly |
| masculine-dark | all eight | no belt book | the approved 180 px **south** shows no book, since it hangs on the left hip and is hidden from the front, so the rotation had nothing to carry |
| feminine-dark | all eight | hair shorter than the approved long hair | the smaller canvas. Vincent, 2026-09-17: "feminine-dark's shorter hair - accept it" |

masculine-dark's book was attempted three ways on Vincent's instruction ("Paint the book onto the front view
first, then rebuild") and all three failed:

1. `inpaint_image_pro_flash`, mask x 46 y 75 w 14 h 15: 210 pixels changed inside the mask, **0 outside**; it
   redrew coat and hand.
2. the same tool, mask x 49 y 71 w 13 h 19, seed 7, the belt line inside the mask and stronger wording: 247
   pixels changed inside, **0 outside**; it redrew the belt and folds.
3. `create_character` v3 rebuild naming the book at the left hip in the description (character
   `2a83863a-7286-4f6c-85a5-7d85c82475d8`): identity equal to the kept base, still no book in any facing.

The tool keeps its byte-exactness guarantee outside a mask, but will not draw a recognisable object in a mask as
small as 13x19 at 128x128. The rebuild is a reject.

## Call log (NSC-095 rev 3's cap basis)

Rev 3 counts this task's own recorded PixelLab calls, with the balance readings beside them. Twenty-one
generation calls were made; read-only calls (`get_balance`, `list_jobs`, `get_character`, `get_image`, the
character archive downloads) cost nothing and are not listed.

| # | Call | Target | Printed | Running |
|---|---|---|---|---|
| 1 | `animate_character` v3 | masculine-light walk: south, south-east, east, north-east | 8 | 8 |
| 2 | `animate_character` v3 | masculine-light walk: north, north-west, west, south-west | 8 | 16 |
| 3 | `image_to_pixelart` | masculine-dark south | 1 | 17 |
| 4 | `image_to_pixelart` | feminine-light south | 1 | 18 |
| 5 | `image_to_pixelart` | feminine-dark south | 1 | 19 |
| 6 | `create_character` v3 | masculine-dark, 8 rotations | 2 | 21 |
| 7 | `create_character` v3 | feminine-light, 8 rotations | 2 | 23 |
| 8 | `create_character` v3 | feminine-dark, 8 rotations | 2 | 25 |
| 9 | `animate_character` v3 | feminine-light walk: south, south-east, east, north-east | 8 | 33 |
| 10 | `animate_character` v3 | feminine-light walk: north, north-west, west, south-west | 8 | 41 |
| 11 | `animate_character` v3 | feminine-light north re-roll (white sock) | 2 | 43 |
| 12 | `animate_character` v3 | feminine-dark walk: south, south-east, east, north-east | 8 | 51 |
| 13 | `animate_character` v3 | feminine-dark walk: north, north-west, west, south-west | 8 | 59 |
| 14 | `inpaint_image_pro_flash` | masculine-dark belt book, attempt 1 | 6 | 65 |
| 15 | `inpaint_image_pro_flash` | masculine-dark belt book, attempt 2 | 6 | 71 |
| 16 | `create_character` v3 | masculine-dark rebuild naming the book (reject) | 2 | 73 |
| 17 | `animate_character` v3 | feminine-dark north-east re-roll (washout) | 2 | 75 |
| 18 | `animate_character` v3 | masculine-dark walk: south, south-east, east, north-east | 8 | 83 |
| 19 | `animate_character` v3 | masculine-dark walk: north, north-west, west, south-west | 8 | 91 |
| 20 | `animate_character` v3 | masculine-dark south re-roll (8 px body drop) | 2 | 93 |
| 21 | `animate_character` v3 | masculine-light south re-roll (10 px loop seam) | 2 | 95 |

**Printed total: 95.** Of that, 21 went on masculine-dark's belt book across the two inpaints and the rebuild,
and 8 on the four single-direction defect re-rolls.

## Spend

| Measure | Value |
|---|---|
| `get_balance` before the first call | 4669 remaining, 331 used |
| `get_balance` after the last call, queue empty | 4539 remaining, 461 used |
| **Measured spend for the run** | **130 generations** |
| Sum of the per-call costs the tools printed (see the call log) | 95 |
| Cap | NSC-095 rev 3: **200**, counted from this call log with the balance readings beside it. Vincent raised it in steps: "raise it 40" (140, the number this run worked to), then 150, then "Then it needs more like 200". AC-001's guard is stop-and-ask, which triggered once at 96 |

**The printed costs under-report.** The meter moved 130 against 95 printed, about 37% more, over this run, and the meter also
lags behind completed jobs, so a number only counts with the queue empty. The per-tool split of the difference is
not established and no per-call price should be quoted from this run.

## Rejects

Rejected candidates go on the local branch `art-rejects/NSC-095`, never on the task branch:

- masculine-dark rebuild `2a83863a-7286-4f6c-85a5-7d85c82475d8` (8 rotations) and the two inpaint results;
- feminine-light's original north walk group `c92aa47d-7836-423f-a587-cac44dd24f20` north frames (white sock);
- feminine-dark's original north-east walk frames from group `9114df33-56f0-4db8-bac8-66032b078374` (washout);
- masculine-dark's first south walk from group `23a67b24-e1c9-4cb9-bab8-bc1145267cb9` (8 px body drop);
- masculine-light's first south walk from group `f925b6a1-b6e1-419a-a474-bf2128114db4` (10 px loop seam).
