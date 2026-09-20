# Fireball VFX: provenance

Art Director Agent, 2026-09-17 (local; 2026-09-18 UTC). **Generated on Vincent's direct instruction with no task
contract** - his words, relayed from his own session: *"Tell it to make me some fireball art with out a task right
now, make the task after when we can."* Cap **100 generations**, his own: *"100 for the fireball, they wont need
that much."* The contract is written afterwards against what is here.

Full run record, including the estimate it was measured against:
`C:\nscrev\reports\art-director\fireball-20260917\plan.md`.

## What to import, and how

**Camera-facing sprites at 64 pixels per world unit, point filter** - the same convention as the merged 128 px
wizard (`Source/PixelLab128`) and the NSC-065 door art. Pivots are in `fx-inventory.json` per set:

| Set | Frames | Canvas | World | Pivot | Why |
|---|---|---|---|---|---|
| `charge_gather` | 6 | 48x48 | 0.75 u | 0.5, 0.5 | mid-air; the emitter positions it, so a centred pivot is correct |
| `charge_hold` | 6 | 48x48 | 0.75 u | 0.5, 0.5 | same. **Its last frame doubles as the cast flash** |
| `projectile` | 4 | 48x48 | 0.75 u | 0.5, 0.5 | same. Radially symmetric, so **one set serves all eight headings** - rotate the trail in code rather than authoring per-heading art |
| `impact` | 8 | 96x96 | 1.5 u | 0.5, **0.15625** | sits on the floor. **One pivot for the whole set**, taken from the modal base row 81 of 96, so the burst cannot hop between frames |
| `scorch` | 1 | 136x68 | 2.125 u wide | 0.5, 0.5 | a flat floor decal; 136x68 is the 2:1 ground ellipse. **Fade it by tint, not by frames** |

**Playback:** `charge_gather` loops while charging (any duration), `charge_hold` loops once charged until
release, `projectile` loops in flight, `impact` plays **once** and its bbox falls from 91x73 to 39x37 across the
eight frames so it genuinely dies down.

**A held charge needs two loops and a code transition, not a one-shot growth** - a fixed build has nothing to do
once the player keeps holding. The swap between gather and hold is a scale-lerp or crossfade in code.

## Palette

Every frame except the scorch uses **one shared 48-colour palette** (`fire_palette.png`). This was not luck: all
18 charge and projectile frames were quantized **together** in a single `reduce_colors` call, and the 9 impact
frames were then locked to that same palette by passing it back as a palette image. Verified afterwards: the
union across the 18 is exactly 48, and the impact frames are a strict subset. The scorch carries its own 32,
because the fire palette has no greys and locking char to it would flatten the soot.

## Calls, seeds and ids

| Piece | Call | Canvas | Seed | Printed | Object / job |
|---|---|---|---|---|---|
| core still | `create_object_pro_flash` | 48x48 | 30001 | 5 | `54bfd8ab-ba92-4a8d-a5c4-a4231cde2987` |
| spark still | `create_object_pro_flash` | 48x48 | 30002 | 5 | `b5eaf332-4d08-4412-9956-366235d6a8ee` |
| projectile loop | `animate_object` v3, 4 frames, `keep_first_frame false` | 48x48 | - | not quoted | group `76bd3529-7edf-4111-8a75-7bfbd13ce53f` |
| charge gather loop | `animate_object` v3, 6 frames | 48x48 | - | not quoted | group `0bad33ad-29da-4f5c-941d-015bc8efdd80` |
| charge hold loop | `animate_object` v3, 6 frames | 48x48 | - | not quoted | group `9d3b9c1f-8e30-452b-b077-8aafa34a3e74` |
| impact still | `create_object_pro_flash` | 96x96 | 30003 | 5 | `d3b8f8cf-ea03-4bfb-a2af-9a7c93647e5b` |
| impact burst | `animate_object` v3, 8 frames | 96x96 | - | not quoted | group `711eb02a-8868-481f-91a1-3f956323d5c5` |
| scorch | `create_object_pro_flash` | 136x68 | 30004 | 6 | `3863630f-080b-47f0-89c7-d082996243e7` |
| palette lock, 18 frames | `reduce_colors` `num_colors 48` | 48x48 | - | 0.1 | job `548e82a4-789c-45d7-b0e5-56dfbc2daf0c` |
| palette lock, 9 impact frames | `reduce_colors` with the palette image | 96x96 | - | 0.1 | job `20ecf3f8-8884-477f-85f7-cfaaef2dbe94` |
| scorch palette | `reduce_colors` `num_colors 32` | 136x68 | - | 0.1 | job `95010ed7-7708-4a88-991f-c63c81e40d66` |

**11 calls, no re-rolls** - every piece was accepted on its first generation.

## Spend

| When | Remaining | Used |
|---|---|---|
| Before the first call, `list_jobs` empty | 4408 | 591 |
| After the last call, `list_jobs` empty | 4381 | 618 |

**618 - 591 = 27, and 4408 - 4381 = 27.** Both columns agree: **27 generations on the meter**, against a 43-60
estimate and a 100 cap.

## Known flaws, stated rather than hidden

1. **The gather loop reads as a pulsing ember, not sparks spiralling inward.** The prompt asked for the spiral.
   At about 50 screen pixels the difference is invisible and the read that matters - a small warm glow at the hand
   that grows - is present. A re-roll would cost about 5 printed. **Not re-rolled: it does not change what films.**
2. **The impact's smoke curls are dark plum rather than grey**, a side effect of locking the impact to the fire
   palette. It happens to sit with the game's plum shadow palette, but it was not a decision.
3. **Scale note:** at 0.75 u the ball is about a third of the wizard's height - right for the charged payoff. If
   it reads too large in flight, render the projectile at 0.5 u from the same art. A transform scale, no new art.

## Style clause deviation, recorded

The committed prop clause (NSC-078 plan section 4a) ends "soft key light from the upper left" with "warm
lantern-glow highlights". **A fireball is the light source**, so these descriptions replaced those two phrases
with a self-lit flame palette - white-hot core, saffron, orange, deep crimson edge. Everything else was kept
verbatim: single colour black outline, basic shading, medium detail, no anti-aliasing, no gradients, transparent
background, no text, no runes, no floor shadow, no other objects.
