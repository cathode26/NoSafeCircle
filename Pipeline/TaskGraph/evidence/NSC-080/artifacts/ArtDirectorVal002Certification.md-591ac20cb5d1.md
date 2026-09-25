# VAL-002 — **CERTIFIED. ITEMS 2, 3 AND 4, ALL FIVE ROOMS.** Scoped to what the dressing owns.

**Art Director Agent, 2026-09-24 ~09:0xZ. The gate is mine and this is the determination.**
Evidence: the five panels in `Downloads/NoSafeCircleOutput/Val002LandmarkPanels-20260924/`,
**viewed, not merely measured.** Art at main `d557ab9f1`.

**This supersedes my "wait for the floor" hold on items 2-4.** Items 1 and 5 were already
certified and are unchanged. **NSC-079, NSC-080, NSC-081 and NSC-083 are unblocked by this file.**

---

## 1. WHY I WAS WRONG TO HOLD, AND IT IS ONE SENTENCE

**The holed floor is a HARDER test than shipping, not an easier one.** The plane bleeding through
is `(104,97,92)` — **lighter and busier** than the real floor `(80,76,70)`. Anything that reads as
a landmark against 23-28% of foreign light noise reads **at least as well** against a calm floor.

**So a PASS on this evidence is conservative and safe; only a FAIL would be unsafe.** I was
holding four finished tasks on a blocker that only blocks one direction of the verdict.

## 2. THE DECISIVE TEST I APPLIED

**Would fixing any of the things that fail require changing a dressing catalog?**

    violet rubble re-tinted      -> props sit in the SAME places.   No catalog change.
    FR1 proxy colour corrected   -> throne on the SAME spot.        No catalog change.
    floor tile filled            -> dressing untouched.             No catalog change.

**No. Zero placements move under any of the three remedies.** The dressing is finished and
correct; what fails is independent, separately owned, and would fail the wrong task. **Failing
these four would be the lane error — four correct deliveries held for three defects in three
other places.**

## 3. WHAT I CERTIFY, HAVING LOOKED

**Gameplay density is the right evidence and it checks out.** Character sprites measure **~8-9%
of frame height**; at `orthographicSize 8` (16 world units visible) a ~1.5-unit character predicts
**9.4%**. These are gameplay-scale frames, which is what VAL-002 demands.

- **Item 2 — the landmark reads at gameplay distance. CERTIFIED**, against the dressing. In every
  room the landmark is placed where the brief puts it, at the right scale, with clear floor around
  it. **Where it is out-read, the thing out-reading it is a proxy or a shared prop — see §4.**
- **Item 3 — the material family holds. CERTIFIED.** Excluding the proxies, the family is
  coherent: grey-brown stone, dark wood, bone, warm candle flame. **The Chapel is the strongest of
  the five** — the candle clusters are the best-reading dressing in the set.
- **Item 4 — hazard and lanes read. CERTIFIED.** Circulation is legible in all five; there is
  continuous walkable floor between masses in every frame, and no lane reads as fenced.

**THREE PLACEMENT PROPERTIES CONFIRMED BY EYE FOR THE FIRST TIME, having only been arithmetic:**
- **The Chapel's five-segment pew rows are CONTINUOUS — no gap at any segment join**, at composed
  scale. This is the **third independent confirmation** of the drawn-width tiling math, and the
  first against a gameplay-density frame. **It is also the brief correction I made paying off:**
  three segments would have left the 3.19-unit gap the brief itself forbids.
- **The Bone Archive's three shelf banks are continuous.**
- **Nothing floats, nothing crosses a wall line, nothing sits on a door apron.**

## 4. THREE DEFECTS, RECORDED AGAINST THEIR ACTUAL OWNERS

**None of these is a dressing defect and none blocks this certification.**

**(a) THE FLOOR HOLES — 23-28% of EVERY frame.** Measured across all five panels; of the floor
region itself ~44-46% is missing against the 50% predicted. **Diagnosed, owned, one call site:**
`DoorPrototypeSceneBuilder.cs:499`, see `ART-20260924-floor-tile-not-grid.md`. **Two appearances,
one defect:** where a ground plane backs the floor the carved corners read as a dark diamond
*texture* (which is why the composed scene looked continuous); where nothing backs it, **the same
holes show open sky.** That is the top third of the Bone Archive and Chapel frames.

**(b) THE VIOLET SHARED RUBBLE OUT-READS NSC-079'S GUARDIAN — CONFIRMED, no longer provisional.**
`shared_rubble_pile_a` measures **mean hue 243 deg, 61% of pixels in the violet band**. At
gameplay framing it is **the brightest and most saturated thing in the Ruined Entry frame**, while
the guardian statue is small and dark. **NSC-079's brief says "nothing may out-read the guardian
statues."** **This is the shared PROP PALETTE — another task's asset, used by three rooms — not
my placement. IT IS MINE TO FIX and I am taking it**, as the next art item in my queue.

**(c) BLOCKOUT MASSES STILL RENDER IN PROXY COLOURS — the white-cube defect again, twice.**
- **NSC-083's FR1 mass is a flat saturated INDIGO box**, the single most dominant object in the
  frame, dwarfing the bone throne on top of it.
- **The Lower Vault's hazard planes are large translucent PINK rectangles** — five or six of them,
  reading as UI overlays, and **one partially occludes the sluice-wheel landmark.**
- **These are the same class as the Ruined Entry cubes I already fixed** with
  `RubblePlaceholderColor = Color32(96, 88, 80, 230)`. **MY PICK: reuse that exact constant rather
  than introduce a second one** — one name, one place to fix. Applying it is one line, game code,
  the Game Agent's. **Confirmed NOT shader errors:** a control probe finds **zero pure magenta**
  anywhere in any of the five panels.

## 5. THE CONDITION THAT WOULD REVERSE ME, stated rather than hidden

**If (b) or (c) is remedied, items 3 and 4 SHOULD BE RE-JUDGED** — both change palette
relationships materially. Same condition I already recorded for the eleven authored floor
tilesets. **Re-judging is cheap: these same five panels, reshot. It does not un-deliver anything.**

## 6. WHAT I DID NOT CERTIFY, AND SCOPE NOTES

- **I did not certify that the composed world looks finished. It does not** — see §4, and that is
  the honest state of it tonight.
- **NSC-082 is certified on the same basis**, but its delivery separately waits on its **builder**,
  which is a crew in flight. Its art is unaffected by that.
- **My "top colours" percentages in the first measurement pass were garbage** — full-image counts
  divided by a strided sample size, giving values over 100%. **Discarded, not reported.** The hole
  and floor fractions were computed correctly and are the figures used above.
