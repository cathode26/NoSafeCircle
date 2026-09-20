# NSC-095 spend: the settled figures, derived from the readings

Art Director Agent, 2026-09-17. Written because three printed/metered pairs for this one run got into circulation
from my messages. **This file is the authority; quote it rather than any message, including mine.**

## The settled pair

**97 printed generations against 132 on the meter, a ratio of 1.361, about 36% above printed.**

## Derivation, from the recorded `get_balance` readings

Every reading below was taken with `list_jobs` empty.

| When | remaining | used | metered delta from the start |
|---|---|---|---|
| Before the first call | 4669 | 331 | - |
| After the 21st call | 4539 | 461 | 461 - 331 = **130**, and 4669 - 4539 = **130** |
| After the 22nd call (the rejected interpolation attempt) | 4537 | 463 | 463 - 331 = **132**, and 4669 - 4537 = **132** |

Both columns agree at both checkpoints, which is what makes the delta trustworthy.

## Printed costs, itemised

| # | call | printed | running |
|---|---|---|---|
| 1-2 | `animate_character` v3, masculine-light walk, 4 + 4 directions | 8 + 8 | 16 |
| 3-5 | `image_to_pixelart`, masculine-dark, feminine-light, feminine-dark | 1 + 1 + 1 | 19 |
| 6-8 | `create_character` v3 for those three | 2 + 2 + 2 | 25 |
| 9-10 | feminine-light walk, 4 + 4 directions | 8 + 8 | 41 |
| 11 | feminine-light north re-roll (white sock) | 2 | 43 |
| 12-13 | feminine-dark walk, 4 + 4 directions | 8 + 8 | 59 |
| 14-15 | `inpaint_image_pro_flash`, masculine-dark belt book, two attempts | 6 + 6 | 71 |
| 16 | `create_character` v3, masculine-dark rebuild (reject) | 2 | 73 |
| 17 | feminine-dark north-east re-roll (washout) | 2 | 75 |
| 18-19 | masculine-dark walk, 4 + 4 directions | 8 + 8 | 91 |
| 20 | masculine-dark south re-roll (8 px body drop) | 2 | 93 |
| 21 | masculine-light south re-roll (10 px loop seam) | 2 | **95** |
| 22 | masculine-dark south, v3 interpolation attempt with `end_frame_url` (rejected: it removed the stride) | 2 | **97** |

Read-only calls - `get_balance`, `list_jobs`, `get_character`, `get_image`, the character archive downloads - cost
nothing and are not listed.

## Why three pairs existed, all mine

| pair | what it was |
|---|---|
| 93 / 130 | printed summed **by hand** and one single-direction re-roll missed; the meter figure was right for 21 calls |
| 95 / 130 | printed corrected by itemising, but the meter reading predates call 22 - internally consistent, and **partial** |
| 97 / 133 | printed right for all 22 calls, but 463 - 331 was subtracted wrongly: it is 132 |
| **97 / 132** | **both from the readings above. Settled.** |

Three of the four errors were arithmetic in my head on top of correct measurements.

**The lesson, worth more than the digits:** a spend figure is a subtraction between two recorded readings. Compute
it from them, quote the reading pair beside the total, and never restate it from memory.

## What does not change

The ratio is 1.371, 1.368 and 1.398 across the wrong pairs and **1.361** for the right one, so the guidance was
correct under all of them: **multiply printed estimates by roughly 1.4 when asking for a cap**, count a task's own
recorded calls against that cap, and read the meter with an empty queue as the cross-check.

**And do not state the gap as a rate.** A later batch the same day measured **70 on the meter against 70.5
printed** - printed and meter agreeing almost exactly. One run is a measurement, not a rate.

## A digit collision to avoid

"95" now means two unrelated things:

- **95 printed generations** = 21 of this run's 22 calls (a superseded partial figure; prefer 97);
- **about 95 generations** = the NSC-078 style-lock pilot's projected cost **in meter terms**, from multiplying its
  68 printed estimate by about 1.4.

Anywhere either appears, say which: "97 printed / 132 metered for NSC-095" and "about 95 in meter terms for the
NSC-078 pilot".
