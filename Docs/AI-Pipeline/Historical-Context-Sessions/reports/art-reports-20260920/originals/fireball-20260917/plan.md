# Charged fireball VFX: run record

Art Director Agent, 2026-09-17. **Estimate this run was launched against:**
`C:\nscrev\reports\art-director\fireball-estimate-20260917\ESTIMATE.md` (about 43 printed, 43-60 metered).

## Authority, stated plainly because there is no contract

Vincent's words, relayed to me by the Documentation Agent from his own session:

> "Tell it to make me some fireball art with out a task right now, make the task after when we can."

and earlier, the cap:

> "100 for the fireball, they wont need that much"

**So this run deliberately has no task contract.** It is not an unauthorised spend: Vincent instructed it directly
and set the cap himself, the task gets written afterwards against what was actually made, and every call is logged
below with its printed quote. He is filming, so the **charge build and the projectile loop are the priority
shots**; impact and scorch follow.

**Cap: 100 generations. Stop and ask past it.**

## Balance, both columns, queue empty

| When | Remaining | Used |
|---|---|---|
| Before the first call | **4408** | **591** |

That pair was read with `list_jobs` empty. The closing pair goes in the same table, and the total is reported as
the subtraction with the pair quoted beside it.

## The pieces, and why each one exists

Camera-facing sprites at **64 px per world unit**, matching the merged 128 px wizard and the door art. The
projectile core is **radially symmetric** so one sprite serves all eight headings with the trail rotated in code -
the directional comet was the +70 printed option that would have breached the cap on its own.

| Piece | Canvas | World size | How |
|---|---|---|---|
| charge spark | 48x48 | 0.75 u | still, the start pose for the build |
| charge full sphere | 48x48 | 0.75 u | still; also the projectile's base and the cast flash |
| charge build | 48x48 | - | `animate_object` v3 **interpolation**, spark -> sphere. Interpolation is the right tool for a growth, unlike the NSC-095 walk where it removed the stride |
| charge hold loop | 48x48 | - | `animate_object` v3 loop on the sphere |
| projectile loop | 48x48 | - | `animate_object` v3 loop, flicker and trailing tongues |
| impact burst | 96x96 | 1.5 u | still plus an 8-frame burst |
| scorch decal | 136x68 | 1.5 u flat | one still, faded by tint in code |

**Style clause deviation, recorded deliberately:** the committed prop clause (NSC-078 plan section 4a) ends with
"soft key light from the upper left" and "warm lantern-glow highlights". **A fireball is the light source**, so
VFX descriptions replace those two phrases with a self-lit flame palette - white-hot core, saffron, orange, deep
crimson edge. Everything else in the clause is kept verbatim: single colour black outline, basic shading, medium
detail, no anti-aliasing, no gradients, transparent background, no text, no runes, no floor shadow, no other
objects.

## Call log

| # | call | canvas | seed | printed (quoted) | id |
|---|---|---|---|---|---|
| 1 | `create_object_pro_flash` fx_fireball_core | 48x48 | 30001 | **5** | `54bfd8ab-ba92-4a8d-a5c4-a4231cde2987` |
| 2 | `create_object_pro_flash` fx_fireball_spark | 48x48 | 30002 | **5** | `b5eaf332-4d08-4412-9956-366235d6a8ee` |

Note: 48x48 quotes **5 printed**, not the 6 the NSC-078 pilot measured at 100x84 and larger. The estimate said a
smaller canvas might quote less; it does.

## A design change that costs one call less: a held charge needs loops, not a one-shot build

The estimate proposed a 6-frame **build** from spark to sphere, interpolated with `end_frame_base64`. **Dropped,
and for a reason worth keeping:** a charged spell is held for as long as the player holds the button, so a fixed
one-shot growth has nothing to do after it finishes. The correct primitive is **two loops and a code transition**:

1. **`charge_gather_loop`** on the spark - the ember pulses, sparks spiral inward. Plays while charging, for any
   duration.
2. **`charge_hold_loop`** on the core - the full sphere pulsing. Plays once charged, until release.
3. The swap between them is a scale-lerp or crossfade **in code, zero generations** - and it also avoids the v3
   interpolation risk that cost NSC-095 a wasted call when it removed the walk stride.

The last frame of the hold loop doubles as the cast flash, as planned.

| # | call | canvas | printed (quoted) | id / group |
|---|---|---|---|---|
| 3 | `animate_object` v3 projectile_loop, 4 frames, `keep_first_frame false` | 48x48 | see closing balance | group `76bd3529-7edf-4111-8a75-7bfbd13ce53f` on the core |
| 4 | `animate_object` v3 charge_gather_loop, 6 frames, `keep_first_frame false` | 48x48 | see closing balance | group `0bad33ad-29da-4f5c-941d-015bc8efdd80` on the spark |

`animate_object` prints no per-call quote, which the estimate flagged as its one unmeasured number. **This run
measures it:** the closing balance minus 10 printed for the two stills gives the true cost of the animations, and
that figure goes into the guide rather than the estimate's guess of 3 each.

## Stills as generated

| id | canvas | alpha bbox | opaque px | colours as generated |
|---|---|---|---|---|
| `fx_fireball_core` | 48x48 | 5,3 - 41,41 | 768 | 743 |
| `fx_fireball_spark` | 48x48 | 12,10 - 34,36 | 320 | 259 |

Both need the 48-colour lock (`reduce_colors`, 0.1 printed each) for the same reason the NSC-078 props did.

## Full call log, all 11 calls

| # | call | canvas | frames | seed | printed (quoted) | id |
|---|---|---|---|---|---|---|
| 1 | `create_object_pro_flash` fx_fireball_core | 48x48 | - | 30001 | 5 | `54bfd8ab-ba92-4a8d-a5c4-a4231cde2987` |
| 2 | `create_object_pro_flash` fx_fireball_spark | 48x48 | - | 30002 | 5 | `b5eaf332-4d08-4412-9956-366235d6a8ee` |
| 3 | `animate_object` v3 projectile_loop | 48x48 | 4 | - | not quoted | group `76bd3529-7edf-4111-8a75-7bfbd13ce53f` |
| 4 | `animate_object` v3 charge_gather_loop | 48x48 | 6 | - | not quoted | group `0bad33ad-29da-4f5c-941d-015bc8efdd80` |
| 5 | `animate_object` v3 charge_hold_loop | 48x48 | 6 | - | not quoted | group `9d3b9c1f-8e30-452b-b077-8aafa34a3e74` |
| 6 | `create_object_pro_flash` fx_fireball_impact | 96x96 | - | 30003 | 5 | `d3b8f8cf-ea03-4bfb-a2af-9a7c93647e5b` |
| 7 | `animate_object` v3 impact_burst | 96x96 | 8 | - | not quoted | group `711eb02a-8868-481f-91a1-3f956323d5c5` |
| 8 | `create_object_pro_flash` fx_fireball_scorch | 136x68 | - | 30004 | 6 | `3863630f-080b-47f0-89c7-d082996243e7` |
| 9 | `reduce_colors` 18 frames at 48x48, `num_colors 48` | 48x48 | 18 | - | 0.1 | job `548e82a4-789c-45d7-b0e5-56dfbc2daf0c` |
| 10 | `reduce_colors` 9 impact frames, **locked to the fire palette** | 96x96 | 9 | - | 0.1 | job `20ecf3f8-8884-477f-85f7-cfaaef2dbe94` |
| 11 | `reduce_colors` scorch, `num_colors 32` | 136x68 | 1 | - | 0.1 | job `95010ed7-7708-4a88-991f-c63c81e40d66` |

**No re-rolls.** Every piece was accepted on its first generation.

## Spend: the subtraction, with both reading pairs quoted

| When | Remaining | Used |
|---|---|---|
| Before the first call, `list_jobs` empty | **4408** | **591** |
| After the last call, `list_jobs` empty | **4381** | **618** |

**618 - 591 = 27, and 4408 - 4381 = 27.** Both columns agree, so the delta is trustworthy: **27 generations on the
meter, against the 100 cap and against an estimate of 43 to 60.** The run came in at roughly **half** the low end
of its own estimate.

**What the estimate got wrong, in the useful direction:**

- **Stills:** quoted **5** printed at 48x48 and at 96x96, and **6** at 136x68 - 21 for four stills against the
  estimate's 24. The estimate's guess that a smaller canvas quotes less is confirmed.
- **Animations:** `animate_object` prints no quote, and the estimate guessed 3 printed each. Stills plus the three
  colour reductions account for 21.3 printed; if those metered at their printed quotes, the four animations cost
  about **5.7 metered between them, roughly 1.4 each** - less than half the guess. **Stated as an inference, not
  a measurement:** the meter does not itemise, so this is 27 metered minus 21.3 printed and it assumes the stills
  metered at quote. The safe form for the guide is the total: **11 calls, 4 stills and 24 animation frames, 27
  metered.**
- **Re-roll allowance unused:** the estimate budgeted 7 printed for re-rolls at the measured 1-in-5 rate. Nothing
  needed one. **One run is a measurement, not a rate** - this batch simply did not draw on it.

## What was delivered

`final48/` - all frames on **one shared 48-colour palette**, verified: the union of colours across the 18 charge
and projectile frames is exactly 48, and all 9 impact frames use **only** those same 48 (checked as a subset, no
stragglers). The scorch has its own 32-colour palette, because the fire palette carries no greys and locking the
char to it would have flattened the soot.

| Piece | Files | Canvas | World size | Notes |
|---|---|---|---|---|
| `charge_gather_loop` | `gather_0..5` | 48x48 | 0.75 u | charging, loops for any duration |
| `charge_hold_loop` | `hold_0..5` | 48x48 | 0.75 u | charged, held until release; last frame doubles as the cast flash |
| `projectile_loop` | `projectile_0..3` | 48x48 | 0.75 u | in flight; **measured drift 0.0 px in x, 2.5 px in y**, and the y is a flame tongue reaching higher, not the ball moving |
| `impact_burst` | `impact_0..7` | 96x96 | 1.5 u | played once; bbox falls from 91x73 to 39x37 across the eight frames, so it genuinely dies down |
| `fx_fireball_scorch` | `scorch` | 136x68 | 1.5 u flat | one still, faded by tint in code |
| stills | `core_still`, `spark_still`, `impact_still` | - | - | the base poses the animations were built from |

**Two honest notes for Vincent's review:**

1. **The gather loop reads as a pulsing ember rather than sparks spiralling inward.** The prompt asked for the
   spiral; what came back is a flicker-and-swell. At 50 screen pixels the difference is invisible and the
   important read - a small warm glow at the hand that grows - is there. A re-roll would cost about 5 printed.
2. **The impact's smoke curls are dark plum, not grey.** That is a direct consequence of locking the impact to
   the fire palette, which has no greys. It happens to sit with the game's plum shadow palette, but it was a
   side effect of the lock and not a decision.

**And one scale observation:** at 0.75 world units the ball is about a third of the wizard's height. That is
right for the charged payoff; if the flying projectile reads too large in motion, render it at 0.5 u from the same
art - a transform scale, **no new generation**.
