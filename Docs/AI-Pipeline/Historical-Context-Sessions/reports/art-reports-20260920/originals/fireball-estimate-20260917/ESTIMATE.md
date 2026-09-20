# Charged fireball: what the art is, and what it should cost

Art Director Agent, 2026-09-17. Written for the Documentation Agent's cap request and for the
estimate-versus-meter comparison afterwards. **No generations spent. Cap relayed as 100 (Vincent: "100 for the
fireball, they wont need that much"); owner still with the GER Agent, so nothing runs yet.**

## 1. The four pieces, and the sizes they need

Camera-facing sprites, like the characters - **never world-plane**, which is the mistake that produced the
checkerboard floor in NSC-064. Camera-facing art scales at a flat 64 px per world unit (the wizard's 2-unit box
is 128 px), so these sizes need no projection maths:

| Piece | World size | Canvas | Frames | Why |
|---|---|---|---|---|
| **Charge build** at the wizard's hands | 0.75 unit sphere | 48x48 | 6 | a spark growing to a held sphere; the last frame is the cast flash, so no separate flash art |
| **Charge hold** loop | same | 48x48 | 4 | the "charged" state has to be holdable for as long as the player holds the button |
| **Projectile** loop | 0.75 unit | 48x48 | 4 | flicker loop, **radially symmetric core** so one sprite serves all eight headings |
| **Impact burst** | 1.5 unit | 96x96 | 8 | airburst. If the flare spreads across the floor instead, it is a ground shape and the canvas becomes **136x96** by the footprint formula in the NSC-078 plan |
| **Scorch decal** | 1.5 unit on the floor | 136x68 | 1 still | flat ground shape: (1.5+1.5) x 0.7071 x 64 = 136 wide, 3 x 0.3536 x 64 = 68 tall. Fade it by tint in code, not by frames |

All at the **48-colour lock** that the NSC-078 pilot established (0.1 printed each).

**The one decision that changes the budget: is the projectile directional?** A symmetric core with the trail
rotated in code is one sprite set. A hand-authored comet with a tail needs four headings plus mirroring, which
adds roughly 8 stills and 8 loops - about 70 printed, and that alone would breach the 100 cap. **Recommendation:
symmetric core first**; it is also the cheaper thing to iterate on.

## 2. Estimate, printed, with the parts I have not measured named as such

| Line | Calls | Printed | Basis |
|---|---|---|---|
| 4 stills (charge, projectile, impact, scorch) | 4 | 24 | **measured**: every NSC-078 pilot still quoted 6 printed at 100x84 to 144x148. A 48x48 canvas may quote less |
| 4 loops (build, hold, projectile, impact) | 4 | 12 | **estimated at 3 each.** `animate_character` v3 measured 2 printed per 6-frame direction; `animate_object` is unmeasured, so the first call gets quoted and recorded before the rest |
| 48-colour reductions | 4 | 0.4 | measured |
| Re-rolls at the rate this week measured (about 1 in 5) | 2 | 7 | measured |
| **Total** | **14** | **about 43 printed** | |

**In meter terms: about 43 to 60.** The two measured runs this week bracket it - NSC-095 ran 1.36x above printed
(97 printed, 132 metered) and the NSC-078 pilot ran level (48.8 printed against a shared-window delta that
agreed with printed). **One run is a measurement, not a rate**, so the honest answer is a range, and both ends
sit well inside 100. Vincent's "they wont need that much" is right.

## 3. How this gets counted

Balance read with `list_jobs` empty before the first call and at the halfway checkpoint, every call logged with
its printed quote in this folder, and the total reported as a subtraction between the two readings with the pair
quoted beside it. Stop at the cap and ask.

**Reading before this line of work starts: 4408 remaining / 591 used, queue empty, 2026-09-17.**
