# NSC-095: 128x128 wizard remake - plan

Art Director Agent. Started 2026-09-17. **No paid call until Vincent's own spend go and the committed NSC-095
contract.** This file is the pre-flight plan the art bible requires; the results section is filled as it runs.

## Why

- Density decision B (Vincent, 2026-09-16): "The wizard should be 128x128", and "yes" on the one-facing trial.
- Playtest (Vincent, 2026-09-17, via the Game Agent): "The enemies look great." / "the wizards dont look nearly
  as good sadly" / "Whatever you have done to make the enemy look great and in perspective, the wizards need that
  treatment."
- Evidence: `C:\nscrev\reports\art-director\density-trial-20260916\plan.md`.

## Contracts this obeys

| Task | State | What it fixes |
|---|---|---|
| NSC-075 rev 5 `433de4b9b` | committed on main | Camera-facing 2x2 Visual, uniform scale, 90 PPU for today's 180 px art, D1 sorting, and AC-008's ground-line pivot (from my board row H-20260917-24) |
| NSC-095 | GER drafting (host Claude CLI) | This art task. Decisions X1-X11 in `C:\nscrev\ger-contract-revisions-20260916\wizard128\WIZARD_128_DECISIONS.md` |
| NSC-096 | GER drafting | The switch: `ImportWizardSprite` to 64 PPU, `PixelLab128` source root, pivot from my inventory |

Fill in the committed NSC-095 revision, commit hash and AC numbers here before the first paid call, and check the
steps below against its ACs.

## Budget

| Step | Per wizard | 4 wizards |
|---|---|---|
| `image_to_pixelart` on the approved `standing/south.png` (faithful, strength ~150, 128x128) | 1 | 4 |
| `create_character` v3 with `reference_image_url` (8 rotations) | 2 | 8 |
| `animate_character` v3, `frame_count 6`, one call per direction, 8 directions | 16 | 64 |
| Base total | 19 | 76 |
| Re-rolls and masked repairs (measured band from the trial and NSC-073/074) | - | 4-24 |
| **Ceiling I will not pass without asking Vincent again** | - | **100** |

- Masculine-light may reuse the trial character `1d1cd21e-dd13-4bcc-9e0d-4c56f84e5e80` if its 8 rotations pass
  review, saving 3 generations. Its south-east walk has a 6 px loop-seam feet jump and needs a re-roll.
- Record the PixelLab balance before the first call and after the last, and `list_jobs` first.
- Download every result as it finishes; jobs expire after about 8 hours.

## Steps

1. **Pre-flight:** balance, `list_jobs`, the committed contract's ACs, and this plan's budget table filled in.
2. **Per wizard:** pixelart pass -> character -> review the 8 rotations against the approved 180 px stills
   (hat and band, hair or beard, face, coat or robe, belt book, boots, no staff; facing labels are screen
   facings; a gameplay-scale read). Repair defects with masked inpaint **before** animating.
3. **Walks:** one `animate_character` call per direction, action text naming the identity items.
4. **Normalize:** losslessly to 128 from the 152 px raw frames, then put every facing on one ground-line row with
   `C:\nscrev\reports\art-director\wizard-ground-line-20260917\tools\ground_line.py` (per group: one variant and
   direction, the standing still plus its six walk frames, shifted together by the group's planted-row offset).
5. **Inventory:** `ground_line_y_from_top` per wizard, `alpha_bottom_y_from_top` per frame, per group the median
   row, deepest row and dip below the line (cap 6 px at 128; a walk over it gets re-rolled), raw size, bbox,
   padding offset and both SHA-256s.
6. **Metrics and review package:** the art-review toolkit (`C:\nscrev\art-tools\ArtReview`: `frame-metrics`,
   `normalize`, `gamescale`, `gif`) for opaque counts, bboxes and loop-seam feet jumps; contact sheet, gameplay-scale
   sheet and motion loops per wizard. Cheap mechanical steps go to a host `claude -p --agent art-director` job on
   the Gmail account.
7. **Vincent's pick per wizard**, quoted and dated here.
8. **Hand to the Game Agent** for the NSC-096 import, with the inventory and the pivot constant.

## Files

- Sources: `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128/<key>/selected/standing/<direction>.png`
  and `.../selected/walk/<direction>/frame_000-005.png` - 4 x (8 + 48) = 224 PNGs.
- Raw exports under `Docs/Art/Wizard/Raw128/<key>/...`, no `.meta` (the NSC-078 precedent that avoids stub-meta
  cubemaps).
- The approved 180 px sources stay untouched as the fallback until NSC-096 switches.
- Rejects go on the local `art-rejects/NSC-095` branch.
- Everything lands through the Game Agent; I never commit to main.

## Vincent's go

**2026-09-17, in this session.** Asked: "Still waiting on your go for the 128 px wizard remake (≈80-100 generations, capped at 100)."
Vincent: **"Yes you have my permission"**.

- Scope as asked: the four approved identities at 128x128, 8 standing directions and a six-frame walk in each, cap 100 generations.
- The NSC-095 contract was still being drafted by the GER Agent at that moment, so the spec I follow is X1-X11 in
  `C:\nscrev\ger-contract-revisions-20260916\wizard128\WIZARD_128_DECISIONS.md` (production path, paths, identity,
  provenance, the ground-line rule and the audit assertions). Re-check against the committed contract when it lands.

## Balance

| When | Remaining | Used |
|---|---|---|
| Before the first call, 2026-09-17 | 4669 | 331 |

`list_jobs` before starting: no active jobs, none finished in the last 30 minutes.

## Results

### masculine-light

**Rotations: reused from the trial character `1d1cd21e-dd13-4bcc-9e0d-4c56f84e5e80`, 0 new generations.**

Identity review at 3x against the approved 180 px stills, all 8 facings, sheet
`identity_ml_trial.png` (built by `tools\identity_sheet.py`):

| Item | Verdict |
|---|---|
| Pointed wide-brim hat with gold band | present in all 8 facings |
| Brown hair and beard | present; the back of the head reads correctly in north |
| Face | the approved grumpy set of the mouth survives at 128; profiles are simplified, as the smaller canvas requires |
| Dark purple coat over a light blue shirt | present |
| Gold belt with the small brown book at the left hip | present; the book reads in east, south-east, north-east and west |
| Brown boots | present |
| No staff | confirmed, none in any facing |

Silhouette sits slightly shorter and broader than the 180 px original, which is the canvas change, not an
identity change. Accepted as the masculine-light base; no inpaint repairs needed before animating.

**Walks:** 8 directions, `animate_character` v3, `frame_count` 6, `keep_first_frame` false so exactly six ordered
frames are stored (the trial's 7-frame group is why its loop seam was awkward). The trial's south-east walk group
`2e1ec5da-1e38-4e70-a2c3-...` is superseded and re-rolled here.

### Alignment results (`ground_line.py`, cap 6 px dip)

| Wizard | Ground line row (incl / `alpha_bottom_y_from_top`) | Pivot y | Max dip | Set by |
|---|---|---|---|---|
| masculine-light | 121 / 122 | 6/128 = 0.046875 | 4 | north-west walk, south walk |
| feminine-light | 119 / 120 | 8/128 = 0.0625 | 6 (at the cap) | south-east walk, south-west walk |

Raw walk frames arrive at mixed canvases per direction (148, 152, 156 and 160 px in this batch), so each direction
is first losslessly centred onto 128 with the trial's `normalize_frames.py`, then aligned. Both wizards: 8
directions x 6 frames, every direction present, no clipped sprite.

feminine-light sits exactly at the 6 px dip cap, so a later re-roll of its south-east or south-west walk would
buy margin. It passes as it stands.

### Belt-book audit (new 128 facings vs the approved 180 set)

Sheets: `book_check_<key>.png`, hip band of all 8 facings, new art over approved.

| Wizard | Book carried over | Missing | Note |
|---|---|---|---|
| masculine-light | 7 of 8 | west | the new north even adds a book the approved north lacks |
| masculine-dark | 0 of 8 | all | its approved **south** has no visible book, so `create_character` v3 had nothing to rotate; the other wizards' south stills do show it |
| feminine-light | 5 of 8 | east, north-east faint | matches the approved pattern except east |
| feminine-dark | 6 of 8 | - | comparable to approved |

Root cause for masculine-dark, verified in `zoom_md_south_chain.png`: approved south -> `image_to_pixelart` ->
rotations all agree, and none of them show the book, because the book hangs on the left hip and is hidden from
the front. This is a property of the approved source, not a generation defect.

### Defects found and acted on

| Wizard | Defect | Action |
|---|---|---|
| feminine-light | north (back) walk: a 5 px near-white band (`#fdfbf8`) reads as a white sock at the boot top in frames 0, 1, 3 and 4 (`zoom_fl_north_feet.png`) | re-rolled that one direction, 2 generations, new group `660311ba-196b-4dd6-b709-8217e0cf2b0c`, prompt names dark boots with no light cuff |
| feminine-dark | hair shorter than the approved long hair (`zoom_fd_hair.png`) | with Vincent |
| masculine-dark | no belt book in any facing | with Vincent |
| masculine-light, feminine-light | one missing book facing each | with Vincent |

No hand edits: every pixel comes from PixelLab, and the only local operations are the lossless centre-crop and
the whole-pixel ground-line shift, both recorded per frame.

### Contract additions from this run (GER Agent, 2026-09-17)

My divergence report produced two new decisions, to be folded into the NSC-095/096 drafts before they commit:

- **X12:** `keep_first_frame: false` (exactly six stored frames, the setting named in the generation record);
  mixed raw canvases (148-160 px) are losslessly centred onto 128 with the offset recorded and refused if any
  opaque pixel would fall outside, then ground-line aligned, and the audit compares `raw_size` and
  `padding_offset` against the decoded raw export; the pivot constant is **per wizard** from that wizard's
  `ground_line_y_from_top` (122 for masculine-light, 120 for feminine-light), never one number for all four.
- **X13** replaces X2's identity sentence: preserve each identity's approved features *as far as the approved
  source facing shows them*, with per-facing exceptions listed in the inventory with a reason and the exact list
  approved by Vincent in VAL-002. The GER Agent took this call itself rather than waiting on him.

So the belt-book gaps are an inventory record plus Vincent's approval, not a failed acceptance criterion. Send
the GER Agent the final per-facing exception list once Vincent decides.

### Vincent's identity decisions (2026-09-17, this session)

Asked with the sheets `zoom_md_hip.png`, `identity_fd.png` and the belt-book audit table. His answers, verbatim:

1. masculine-dark's missing book: **"Paint the book onto the front view first, then rebuild"** - option 2, about
   8 generations.
2. feminine-dark's shorter hair: **"feminine-dark's shorter hair - accept it"**.
3. masculine-light west and feminine-light east book gaps: **"accept the gap"**, then **"go with your
   recommendations"**.

**Per-facing exception list for the inventory (X13), final unless masculine-dark's rebuild changes it:**

| Wizard | Facing | Exception | Reason |
|---|---|---|---|
| masculine-light | west | no belt book | v3 rotation dropped it; Vincent accepted the gap |
| feminine-light | east | no belt book | v3 rotation dropped it; Vincent accepted the gap. north-east carries it faintly |
| feminine-dark | all | hair shorter than the approved 180 px long hair | canvas change; Vincent accepted |
| masculine-dark | south | belt book painted in by masked inpaint | the approved south shows no book, so the rotation had nothing to carry; Vincent chose the repair |

### Repair record (masculine-dark belt book)

- Measured on the candidate south rotation: alpha bbox (45, 11, 83, 109), the gold belt buckle occupies rows
  72-76 at x 62-65, and the body spans x 46-81 across the belt. The other three wizards carry the book at the
  **viewer's left**, below the belt (checked at 7x in `zoom_bookside_and_reroll.png`), so the repair goes there.
- `inpaint_image_pro_flash`, rectangle mask x 46, y 75, w 14, h 15 (that is the `repair_mask` rectangle for the
  inventory), source the character's own south rotation, `output_method` "Modify current layer".
- Job `551870c7-e429-4d6a-a94d-812e44d85c8d`, image `b4b68d59-5811-5c79-8c96-237fc6467929`, estimated 6
  generations (provisional pricing). Byte-exactness outside the mask is the tool's guarantee and is verified
  locally before the rebuild.
- Then `create_character` v3 with the repaired south as the reference image, review the 8 rotations, then the
  8 walks.

### feminine-light north walk re-roll: accepted

The re-rolled group `660311ba-196b-4dd6-b709-8217e0cf2b0c` has brown boots with no near-white band: the recorder
counted 46 pale pixels across the 6 frames, all skin tones (`#fddaca`, `#fbe4d5`), and none of the previous
`#fdfbf8`. Checked at 7x. The original north group is superseded and goes to the rejects branch.

## STOPPED AT THE CAP (2026-09-17 21:41 UTC)

**The real meter, not the tools' printed costs, is the budget.** `get_balance` now reads 4573 remaining / 427
used, against 4669 / 331 at the start: **96 of Vincent's 100 generations are spent.** The sum of the costs the
tools printed for the same calls is 71.

| Checkpoint | Balance used | My ledger from printed costs | Unattributed |
|---|---|---|---|
| Start | 331 | 0 | - |
| After the 3 characters + 2 walk sets (measured by the recorder job) | 388 (57) | 41 | +16 |
| Now | 427 (96) | 71 | +25 |

Attributing the two windows gives the real price at 128x128:

| Call | Printed cost | Measured cost |
|---|---|---|
| `create_character` v3 with a reference image | "2 generations" | about **7** (3 characters, +16 over printed) |
| `inpaint_image_pro_flash` | "estimated 6, pricing_provisional" | about **10.5** (2 repairs, +9 over printed) |
| `animate_character` v3, `frame_count` 6 | 2 per direction | 2 per direction, accurate |

The art bible's cost table needed both corrections; the Documentation Agent applied them on 2026-09-17, plus a
line saying the account meter is the budget, not the printed costs, and the same in the art guide's balance step.

**Caveat on those per-tool figures** (the Documentation Agent's point, and it is right): they come from splitting
one run's 25 unattributed generations between the two call types by elimination, not from a per-call receipt. Use
them as this run's measurements, keep reading the meter at every checkpoint, and re-measure with a single call
type in flight if a future job needs a firm price.

### The masculine-dark book repair failed twice and is abandoned

| Attempt | Mask | Result |
|---|---|---|
| 1 | x 46, y 75, w 14, h 15 | 210 pixels changed inside the mask, **0 outside**; the model redrew coat and hand, no book (`zoom_md_repair.png`) |
| 2 | x 49, y 71, w 13, h 19, seed 7, belt line included, stronger wording | 247 changed inside, **0 outside**; redrew the belt and coat folds, still no book (`zoom_md_repair2.png`) |

`inpaint_image_pro_flash` kept its byte-exactness guarantee both times. The plausible cause is size: a 13x19
pixel target is too small for it to draw a recognisable book. About 21 generations went into the two attempts.

### State of the four wizards

| Wizard | Stills | Walks | Aligned | Notes |
|---|---|---|---|---|
| masculine-light | 8 | 48 | yes, ground line 122, pivot y 6/128 | west facing has no belt book (Vincent accepted) |
| feminine-light | 8 | 48 + a re-rolled north | yes, ground line 120, pivot y 8/128 | east facing has no belt book (accepted); white-boot defect fixed |
| feminine-dark | 8 | 48 generated and paid for | not yet | the first download hit HTTP 403 on every animation URL (they expire); a retry job is running, no new spend |
| masculine-dark | 8 | **none** | no | bookless in all 8 facings; 2 failed repairs; its 8 walks would cost about 16 more |

**Nothing more is queued.** Finishing masculine-dark's walks would put the run at about 112-116 real generations,
so it needs Vincent's decision to raise the cap or to stop with three wizards.

## Committed contract checked against this run (2026-09-17)

**NSC-095 rev 1 and NSC-096 are committed in `36b629f73` on local main** (verified: commit is an ancestor of
main; it adds `Tasks/NSC-095.yaml`, `Tasks/NSC-096.yaml` and the policy rebind).

Read from the committed file, everything this run has done conforms:

| Contract text | This run |
|---|---|
| AC-001: PixelLab only, 4 identities, 8 stills + 6-frame walks in 8 facings, 128x128 transparent | 3 of 4 identities complete; masculine-dark's walks not made |
| AC-001: identity "as far as the approved 180 px source facing shows them", per-facing exceptions listed with a reason and approved in VAL-002 | exception list drafted above; masculine-dark's bookless south is the contract's own example |
| AC-004: one whole-pixel shift per group, planted row = lower median of the six walk frames' lowest opaque row, one `ground_line_y_from_top` per wizard, deepest frame at most `max_dip_below_ground_line` (max 6) below it | exactly what `ground_line.py` does; measured 4 px (masculine-light) and 6 px (feminine-light) |
| AC-002: inventory fields, raws under `Docs/Art/Wizard/Raw128` with no metas | raw frames and hashes recorded per batch by the recorder jobs; inventory assembled at hand-off |
| "Stop and ask Vincent before exceeding 100 PixelLab generations" | stopped at 96 measured; nothing queued |
| Resources claimed: `Source/PixelLab128`, `Docs/Art/Wizard/Raw128`, `PIXELLAB_128_GENERATION.md`, the audit test + `.meta`, `logical:pixellab-wizard-character-art` | my review folders are outside the repo, so no unclaimed file is touched |

**Consequence of stopping at three wizards:** AC-001 requires all four identities, so a three-wizard finish needs
a GER revision to narrow the scope. Finishing masculine-dark's 8 walks costs about 16 more real generations
(about 112-116 total), which needs Vincent to raise the cap.

## Cap raised to 140 (Vincent, 2026-09-17)

Verbatim: **"raise the cap, cost doesnt matter much on art, raise it 40"**. So the budget is 140 generations, with
96 spent when he said it and 44 available. The plan's earlier ceiling of 100 is superseded; NSC-095 AC-001 still
says "stop and ask Vincent before exceeding 100 PixelLab generations", so **the contract needs that number
raised to 140** - told to the GER Agent.

### Third approach to masculine-dark's book: rebuild with the book in the prompt

Masked inpaint failed twice at this size, so the third attempt changes technique rather than repeating it:
`create_character` v3 from the same `image_to_pixelart` reference (`c7ba1b8f`), with the description naming
"a small brown leather-bound book with gold trim hanging from the belt at his left hip, visible in every side and
three-quarter view". v3 takes identity from the reference image and lets the description guide the rotation, which
is the only lever left that can add a prop the front view does not show.

- New character `2a83863a-7286-4f6c-85a5-7d85c82475d8`, about 7 generations measured.
- Both bases are then reviewed side by side against the approved 180 px stills: the original
  `02f0ec58-164f-428d-8b1b-7d5ad6c1ef6b` (good identity, no book anywhere) and this one. The better base gets the
  8 walks, about 16 more.
- Forecast: about 119-123 of 140.

### feminine-dark: aligned, one direction re-rolled

- Ground line 121 (`alpha_bottom_y_from_top`), pivot y 7/128 = 0.0546875, max dip 5 px (south walk), cap 6.
- All 48 walk frames recovered after the 403 failure: the retry job fetched fresh signed URLs per direction and
  downloaded them immediately. **Lesson: PixelLab animation URLs expire fast, so fetch and download one
  direction at a time**, never list all URLs first and download later.
- **Defect:** the north-east walk washed out in frames 4 and 5 - hat, dress and arm turned pale blue, a palette
  shift rather than lighting (`walk_sheet_fd.png`, row 2). Re-rolled that one direction, 2 generations, group
  `07d1e804-5203-4679-b8dd-f85e5bb4d8b1`, with the prompt pinning the navy and brown colours frame to frame.
- Everything else in the sheet reads correctly: identity consistent, hat level, book at the hip in the side and
  three-quarter facings, boots alternating, no clipped sprite.

### Cost finding corrected: the meter lags (2026-09-17, later)

After the two calls that followed the stop (a `create_character` v3 printing 2 and an `animate_character` v3
printing 2, so 4 printed), `generations_used` moved from 427 to **429**: the meter moved *less* than the printed
cost of completed jobs. **Billing lags**, so the earlier 25-generation gap cannot be attributed to
`create_character` and `inpaint_image_pro_flash` with confidence - some of it was lag from jobs still settling.

What survives:
- the account meter, read with an empty queue, is the budget; printed costs are estimates;
- a mid-run reading can sit either side of the truth, so settle it after the queue drains;
- the run-level fact: the meter ran about 25 ahead of 71 printed generations at the stop.

What is withdrawn: the specific "about 7 per v3 character" and "about 10.5 per pro-flash inpaint" prices. They
came from attribution by elimination, not from a receipt. A firm per-call price needs a controlled test with one
call type in flight and the queue empty before and after. The Documentation Agent has been asked to soften the
bible and guide accordingly; the behavioural findings about `inpaint_image_pro_flash` stand.

### masculine-dark: the book cannot be had from PixelLab at this size

Three techniques, all failed:

| Attempt | Technique | Cost (printed) | Result |
|---|---|---|---|
| 1 | `inpaint_image_pro_flash`, mask x 46 y 75 w 14 h 15 | 6 | 210 px changed inside, 0 outside; coat redrawn, no book |
| 2 | same, mask x 49 y 71 w 13 h 19, seed 7, belt line in the mask, stronger wording | 6 | 247 px changed inside, 0 outside; belt and folds redrawn, no book |
| 3 | `create_character` v3 rebuild naming the book at the left hip in the description | 2 | character `2a83863a-7286-4f6c-85a5-7d85c82475d8`, identity equal to the first base, still no book in any facing (`book_check_masculine-dark_r2.png`) |

**Decision (mine):** stop attempting it. The first base `02f0ec58-164f-428d-8b1b-7d5ad6c1ef6b` is kept, the r2
rebuild goes to `art-rejects/NSC-095`, and masculine-dark's bookless facings become a recorded AC-001 identity
exception for Vincent to approve in VAL-002 - which is the case the contract's X13 wording was written for.
Its 8 walks are queued from the kept base (group `23a67b24-e1c9-4cb9-bab8-bc1145267cb9`, 16 printed).

### Two operational findings (2026-09-17, late)

**1. The character archive endpoint is the right way to download a batch.**
`https://api.pixellab.ai/mcp/characters/<id>/download` returns a no-auth zip with every rotation and every
animation group, named `Idle/animations/<group name>/<direction>/frame_000.png`. One request replaces 56 signed
per-frame URLs that expire within minutes, and it never floods the session with URL lists. Use it from now on;
`get_character` is for status only, and only before a character has animations.

**2. The Gmail host CLI is logged out, so cheap delegation is unavailable.**
Both recorder jobs failed with "Not logged in - Please run /login" (`claude auth status --text`: "Not logged in").
Their result JSON also showed two Bash denials, `python3 ...` and `curl ...`, which confirms the Documentation
Agent's point that a Bash rule matches the program name: `Bash(python:*)` does not cover `python3` or `curl`.
Vincent has to run `claude auth login` on the host; nobody else can, and I will not handle credentials. Until
then, batch bookkeeping runs in this session against the archive endpoint.

### masculine-dark and feminine-dark

- **feminine-dark re-aligned with the re-rolled north-east** (`aligned_v2`): ground line 121, pivot y 7/128, max
  dip 5. The washout is gone, measured: pale pixels per frame went from 0, 0, 0, 112, 399, 435 to 0, 2, 0, 0, 0, 0.
- **masculine-dark's south walk was refused by the aligner**: feet rows 106, 104, 107, 115, 113, 113, so the body
  drops about 8 px halfway through the loop, over the 6 px cap. That is a bob, not a toward-camera step, and it
  would read as the wizard hopping while walking at the camera. Re-rolled that one direction (group
  `af5f597d-bd89-4ca7-a26c-e91ef7f76fcc`, 2 printed) with the prompt pinning head and shoulder height.
- This is the dip cap doing its job: the defect was caught by measurement before the art reached Vincent.

## Delivered (2026-09-17)

**Run total, queue empty: 130 generations** (`get_balance` 331 used -> 461 used), against the 140 cap. The tools'
printed costs summed to 93.

**Staged and verified:** `staged/` holds 224 selected 128x128 PNGs, 224 raw exports under `Docs/Art/Wizard/Raw128`,
`source-inventory.json` and `Docs/Art/Wizard/PIXELLAB_128_GENERATION.md`; 450 files, 3.5 MB, no `.meta`.
`tools/verify_staged.py` re-runs VAL-001's assertions and passes: the 224 expected paths, 128x128 with alpha 0 in
all four corners, one inventory row per file with a matching `selected_sha256`, every recorded
`alpha_bottom_y_from_top` equal to the pixels, standing frames on the ground line and each walk group's lower
median on it, every dip at most the recorded value and at most 6, `pivot y == (128 - ground_line) / 128`, a raw
export for all 224, and no `.meta`.

Two defects in my own staging were caught by that verifier before hand-off, both in how raw exports were matched
to selected frames (a folder-suffix test, then a frame-naming mismatch): 84 and then 42 rows had no raw export.
Fixed, re-staged, re-verified.

**Per-wizard result:**

| Wizard | Ground line | Pivot at 64 PPU | Worst dip | South-walk loop seam |
|---|---|---|---|---|
| masculine-light | 122 | 6/128 | 4 px | 7 px (was 10 before a re-roll) |
| masculine-dark | 121 | 7/128 | 5 px | 8 px |
| feminine-light | 120 | 8/128 | 6 px | 6 px |
| feminine-dark | 121 | 7/128 | 5 px | 3 px |

**Review package** (`review/`): four 8-facing walk GIFs at 3x, four true-1080p-scale sheets, per-direction
continuity metrics and `continuity_summary.json`. Sent to Vincent for VAL-002.

**Handed to the Game Agent** as board row H-20260917-31 to commit, with `.meta` minting on its side (AC-002) and
sequencing against Vincent's pick left to it. The GER Agent has the settled total and the final exception list for
NSC-095 rev 3.

**Open:** Vincent's VAL-002 approval, and his call on whether to chase the south-walk loop seam with v3's
interpolation mode (about 3 generations per wizard, up to 9).

## Committed on a branch, awaiting Vincent (2026-09-17, late)

**Branch `nsc095-wizard-128-art`** in the Game Agent's clone `C:
screv\cj-nsc095`, fetched into canonical:
- `dbcdf2d39`: my 450 staged files plus 224 deterministic P34 TextureImporter metas (224 distinct GUIDs);
- `a78c75181`: the 50 folder metas Unity minted on import.

The Game Agent's checks: Unity 6000.1.8f1 imported the branch and **rewrote none of the 224 PNG metas**, so the
deterministic template matches what Unity writes and nothing imports as the P34 cubemap; AC-003 confirmed (no
180 px source changed, `PIXELLAB_GENERATION.md` untouched); my `verify_staged.py` passed for it too. Sequencing,
its call: commit now, Vincent approves this exact commit, and a fix to the south walks would be its own commit.

**NSC-095 is at rev 3 `d6b94af21`:** the cap is 200 generations counted from this task's own call log, with the
balance readings beside it rather than as the basis (the reviewer's point: the meter is account-wide, so a
concurrent art task would contaminate a delta).

**Correction to a number I quoted twice:** itemising all 21 generation calls for that call log gives a printed
total of **95, not 93** - I had missed a single-direction re-roll when summing by hand. The measured 130 stands,
so the under-report is 130 against 95, still about 37%. The call log and the corrected figures go into
`Docs/Art/Wizard/PIXELLAB_128_GENERATION.md` via `nsc095-genrec-call-log.patch`, which the Game Agent lands with
the art. Both the GER Agent and the Game Agent have the correction.

**Still open, both Vincent's:** the VAL-002 approval of `dbcdf2d39` (his merge go too), and item 11, whether to
chase the toward-camera loop seam with v3 interpolation mode (about 9 generations of the 70 still under the cap;
the GER Agent recommends yes).

## Rejects staged (2026-09-17)

AC-002 requires rejected candidates on a local `art-rejects/NSC-095` branch, never the task branch. Staged in
`staged-rejects/Docs/Art/Wizard/Candidates/NSC-095/`: 34 PNGs, no `.meta`, with `REJECTS.md` giving each group's
reason, its replacement group id and per-file SHA-256 prefixes.

| Group | Files | Why rejected |
|---|---|---|
| masculine-dark rebuild rotations | 8 | the prompt-led rebuild that still had no belt book |
| masculine-dark belt-book inpaints | 2 | mask honoured, 0 pixels changed outside, but coat and belt redrawn instead of a book |
| masculine-light south walk | 6 | 10 px loop seam |
| masculine-dark south walk | 6 | about 8 px body drop mid-cycle, over the dip cap |
| feminine-light north walk | 6 | 5 px near-white band reading as a white sock |
| feminine-dark north-east walk | 6 | frames 4 and 5 washed out to pale blue |

**Committed** by the Game Agent as `art-rejects/NSC-095` = `3ca518dcaed5372abf24939fe8a7bdb33e1a6b20`, parent main `24e204b8b`, local only and never to be merged or pushed. Verified by me from the repository: 35 files added and nothing else, all 35 under `Docs/Art/Wizard/Candidates/NSC-095/`, 0 `.meta`, main still `24e204b8b`. It was built with git plumbing against a temporary index, so canonical's worktree, index and HEAD were untouched. No go from Vincent was needed: it touches neither main nor the task branch, and AC-002 requires it.

## Walk drift fixed by alignment, not generation (2026-09-17, late)

Vincent, relayed: "Merge it, and then have the Art Director fix the walk drift so we have that for later."

**The interpolation attempt failed and is recorded as dead.** `animate_character` v3 with `end_frame_url` set to
the standing pose (masculine-dark south, group `0a9d54bd-e6e7-4572-9306-147b9b3f684b`, 2 printed) returned six
near-identical standing frames: forcing the cycle to end where it starts removes the stride. Feet rows were
108, 108, 108, 108, 108, 108 - a perfect seam and no walk. Rejected.

**Then I measured the enemies, and my own rule was the defect.** The approved NSC-077 walks in
`Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/Walk` on main:

| Enemy walk | Foot row per frame | Foot spread / seam | Head spread / seam |
|---|---|---|---|
| melee east | 131 x6 | 0 / 0 | 5 / 1 |
| melee south | 131 x6 | 0 / 0 | 4 / 2 |
| ranged east | 131 x6 | 0 / 0 | 9 / 6 |
| ranged south | 131 x6 | 0 / 0 | 2 / 2 |

The enemies Vincent called great are aligned **per frame** onto one ground line: feet planted, bob in the head.
My X10 rule said one shift per group and never per frame, reasoning that per-frame alignment would flatten the
bob. That reasoning was wrong - the bob lives in the head, not in the lowest foot - and the cost was the 6-8 px
foot wander and loop pop in the wizard south walks.

**The fix, 0 generations:** `tools/plant_feet.py` shifts each frame by whole pixels onto the wizard's existing
ground line, asserting the opaque count and the bbox move, refusing any shift that would clip.

| Wizard | Foot spread / seam after | Head spread | Ground line and pivot |
|---|---|---|---|
| masculine-light | 0 / 0 | 2-7 | 122, 6/128 (unchanged) |
| masculine-dark | 0 / 0 | 2-7 | 121, 7/128 (unchanged) |
| feminine-light | 0 / 0 | 2-6 | 120, 8/128 (unchanged) |
| feminine-dark | 0 / 0 | 2-7 | 121, 7/128 (unchanged) |

Risk checked: in every largest-shift frame the lowest pixel is a **boot**, not a coat hem
(`zoom_md_lowest_part.png`), so no NSC-077-style correction table is needed.

**Re-staged as `staged-v2`** (only the 192 walk PNGs and `source-inventory.json` differ) and `verify_staged.py`
passes: the median rule holds trivially, the recorded dip is 0. Handed to the Game Agent as a second commit on
`c634c6496`; NSC-096 needs nothing because the pivots are unchanged. The GER Agent has been asked to correct
AC-004's "never per frame" wording to the NSC-077 rule.

**Spend: 132 of 200** (meter 463 used against 331 at the start, queue empty; 463 - 331 = 132. I wrote 133 in several places first - a hand-arithmetic slip, corrected 2026-09-17).

### Two corrections the Game Agent caught (2026-09-17)

1. **My re-staged generation record was the stale one.** `staged-v2` was built from `staged`, which predates the
   call-log commit `c634c6496`, so a tree-wide copy would have deleted 2,574 bytes and 23 rows - including the
   itemised call log and the 93->95 correction I had specifically flagged. `verify_staged.py` passed it, because
   a stale-but-valid file is internally consistent. Rebuilt from the committed blob and extended: now 13,589
   bytes with call-log row 22 (the rejected interpolation attempt), printed total 97, measured spend 133, and the
   alignment-correction section.
2. **"The 192 walk frames differ" was wrong: 132 changed, 60 are byte-identical**, because a frame already on the
   ground line needs no shift. I described intent instead of measuring. The commit is 134 files.

**New tool from this:** `tools/compare_to_ref.py <stage_dir> <git_ref>` diffs a staged tree against a committed
ref with `git hash-object`, prints identical/changed/not-in-ref per category, and fails when a staged text file
is shorter than its committed version. It reproduces the Game Agent's figures exactly. Run before every hand-off.

**Superseded frames staged for the rejects branch:** `staged-rejects-v2`, the 132 changed frames under
`Docs/Art/Wizard/Candidates/NSC-095/<key>/walk-per-group-alignment/<direction>/` with
`REJECTS_WALK_ALIGNMENT.md` recording each old alpha bottom and SHA-256.

**NSC-095 rev 4 `7a1bae97a`** makes per-frame ground-line alignment the contract's rule, citing the same enemy
measurement, so the re-aligned frames are its correct implementation.

## VAL-002 satisfied: Vincent approved the shipping art (2026-09-17)

The GER Agent showed him the pre-realignment sheets, flagged that they predated the fix, then sent the **planted**
GIFs and the south-walk before/after; he approved on those. So the approval is against the re-aligned art, not the
earlier set.

- **Merged into main at `9215873ec`** ("Merge nsc095-wizard-128-art: the 128x128 wizard art at game size"),
  verified as an ancestor of main.
- **The approval covers exactly what ships:** all **192/192** walk frames in `staged-v2` are byte-identical by
  SHA-256 to the planted trees the approved GIFs were rendered from, so the replacement-frames commit contains
  nothing beyond the whole-pixel shifts he saw - no re-generation and no pixel edits.
- NSC-095 rev 4 already carries the per-frame alignment rule his approval matches.

**Final spend for NSC-095: 132 generations of the 200 cap** (meter 331 -> 463 used, queue empty; 97 printed; ratio 1.36). Earlier statements of 130/93, 130/95 and 133/97 were successive hand-arithmetic errors; **97 printed against 132 metered is the settled pair**, derived from the recorded balances rather than by hand.

### VAL-002's review elements: done by Vincent himself, twice - do not re-ask

Relayed by the GER Agent, 2026-09-17, his words: **"I did it a second time, all of the wizards walk in the right
8 directions"**, **"I already went and checked each wizard and went in the 8 directions, that was done already"**
and **"I also checked the sorting before, sorting is good."**

That satisfies VAL-002's contact-sheet element for all four identities, and the sorting check besides. **No further
8-direction package is to be prepared or requested.** The only piece of VAL-002 still open is the formal binding of
his approval to the exact candidate commit, which the GER Agent arranges when the art lands as a candidate - not
another thing for him to look at. Recorded by the GER Agent in
`C:
screveports\ger-orchestratorincent-decisions-20260917.md`.

## Generation ledger (cap 100)

| # | Call | Directions / frames | Gens | Running | IDs |
|---|---|---|---|---|---|
| 1 | `animate_character` v3, masculine-light walk, `frame_count` 6, `keep_first_frame` false | south, south-east, east, north-east | 8 | 8 | character `1d1cd21e-dd13-4bcc-9e0d-4c56f84e5e80`, group `f925b6a1-b6e1-419a-a474-bf2128114db4` |
| 2 | same group, remaining facings | north, north-west, west, south-west | 8 | 16 | group `f925b6a1-...` |
| 3 | `image_to_pixelart` faithful, strength 150, 128x128, masculine-dark `standing/south.png` | 1 | 1 | 17 | job `c7ba1b8f-8fe6-4b0b-942a-11be1a907fed` |
| 4 | same, feminine-light | 1 | 1 | 18 | job `e0b19178-3425-4197-9af7-ea0e737a9c85` |
| 5 | same, feminine-dark | 1 | 1 | 19 | job `158d6bd2-5f36-404e-9ce1-514d7520c580` |
| 6 | `create_character` v3 from job 3 | 8 rotations | 2 | 21 | character `02f0ec58-164f-428d-8b1b-7d5ad6c1ef6b` |
| 7 | `create_character` v3 from job 4 | 8 rotations | 2 | 23 | character `53aebb62-452d-4228-bda3-3a873a42f9eb` |
| 8 | `create_character` v3 from job 5 | 8 rotations | 2 | 25 | character `afabd47e-a66e-453d-beee-b90f9856f9e0` |

**Source images** (pinned raw URLs at commit `96a6293c47cf2346b5c98f968e8790ce561674d3`, verified present with
`git show` and hashed): masculine-light `38c4f378898a...`, masculine-dark `538e8d16f8f4...`,
feminine-light `f0d75e2e90da...`, feminine-dark `d55ab6672764...`.

**Downloads:** `downloads.json` logs every fetched URL with bytes, SHA-256, size, alpha bbox and opaque count.
The three `image_to_pixelart` results are opaque 128x128 by design (the tool returns a gray background); v3
rotation still yields transparent sprites, as the 2026-09-16 trial established.

**Bookkeeping:** the masculine-light walk batch (8 directions x 6 frames) is being downloaded and measured by a
host `claude -p --agent pixellab-batch-recorder` job on the Gmail account
(`C:\nscrev\claude-jobs\wizard128-ml-walk-record-20260917.prompt.md`).
