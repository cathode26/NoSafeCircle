# NSC-065 revalidation at main `ac8ddffa1`

Art Director Agent, 2026-09-22. Requested by the Game Agent after `evidence_stale` against
`DEL-NSC-065-03affab6b822`. Seven `.meta` files changed; all seven door PNGs are byte-identical.

**The staleness is mine.** The meta change is the door import-settings fix I landed today under Vincent's
2026-09-22 rule that art is not delivered until its `.meta` imports it as the thing it is meant to be.

## VAL-001 — deterministic inventory: **PASS**, carries forward

> *"A deterministic inventory confirms every required visual state, the final-door variant, transparent
> backgrounds, consistent dimensions/perspective, and exact provenance with no ambiguous filenames."*

Re-run at `ac8ddffa1`. It examines pixels, and the pixels did not move.

| state | canvas | drawn bbox | transparent bg | opaque px |
|---|---|---|---|---|
| sealed | 128x128 | (6, 4, 122, 121) | yes | 8348 |
| opening | 128x128 | (6, 4, 122, 121) | yes | 8530 |
| open | 128x128 | (6, 4, 122, 121) | yes | 8573 |
| locked | 128x128 | (6, 4, 122, 121) | yes | 8348 |
| damaged | 128x128 | (6, 4, 122, 121) | yes | 8348 |
| broken | 128x128 | (6, 4, 122, 121) | yes | 8467 |
| final | 128x128 | (6, 4, 122, 121) | yes | 8348 |

- **7 of 7 required states present**, including the final-door variant.
- **One canvas** across the family: 128x128.
- **One drawn bounding box** across all seven: `(6, 4, 122, 121)`. That single box is the machine-checkable form
  of "consistent dimensions and perspective" and of AC-002's "same door identity, ground contact and opening
  width" — every state occupies the same footprint.
- **Transparent background** on every file.
- **No ambiguous filenames:** exactly 7 PNGs in the family, each mapping to exactly one required state, none
  left over.

## VAL-002 — readability at gameplay scale: **must be redone, and it now PASSES**

> *"The assistant verifies state readability at gameplay scale and coherence with the selected wizard and
> environment art before authorizing later Unity integration."*

**Agreed with the Game Agent that it cannot carry forward, and for its exact reason:** gameplay scale is
canvas divided by pixels-per-unit, and PPU moved 100 -> 64. The gate measures world size; world size changed by
a factor of 1.5625. Every number it asserted is now wrong.

### Measured

| | recorded (PPU 100) | now (PPU 64) |
|---|---|---|
| canvas in world units | 1.280 x 1.280 u | **2.000 x 2.000 u** |
| drawn figure | 1.160 x 1.170 u | **1.812 x 1.828 u** |
| shipping wizard drawn figure | 0.322 x 0.811 u | unchanged |
| **wizard height as a share of the door's drawn height** | **69%** | **44%** |

The wizard is the 180 px `PixelLab` set at PPU 180 — `DoorPrototypeGlobalSceneBuilder.cs:592`, unchanged, so
NSC-096's switch to `PixelLab128` at 64 PPU has not landed and the old set is still what ships.

### The finding: the recorded pass was against a configuration that was wrong

At PPU 100 the wizard stood at **69% of the door's drawn height**. That is the "large wizard, small door" read
Vincent reported from his own playtest on 2026-09-17, and it is what the 09-17 door audit measured as a
1.00 x 1.30 u passage a 1.64 u wizard could not fit. **VAL-002 passed over a defect it was written to catch.**
At PPU 64 the wizard is **44%** of the door — a character comfortably shorter than the opening it walks
through.

So the honest statement is not "the settings changed, please re-bless". It is: **the change that invalidated
this gate is the change that fixed what the gate should have failed.**

### Readability of the seven states, judged from the art

Sheet: `doors_all_states_3x.png` in this folder.

- **sealed** closed plank door in the violet-slate arch, painted floor disc, mossy rubble at the base.
- **opening** leaf swung partway, void visible behind it.
- **open** leaf fully swung, wide void.
- **locked** a **bone crossbar** across the closed leaf — reads as locked without text or an icon.
- **damaged** cracks through the planks and a split in the arch stone.
- **broken** a ragged hole clean through, with planks scattered on the floor.
- **final** a **gold frame glow and a skull emblem**, unmistakable against the other six and with the same
  footprint, which is AC-003's requirement exactly.

All seven keep one key light from the upper left, one arch, one base, one footprint. **AC-002 and AC-003 hold.**

### What I did not measure, stated so nobody inherits a false number

I tried to isolate the open state's aperture by thresholding dark opaque pixels and it returned the whole drawn
figure — the family is dark throughout, so that threshold separates nothing. **There is no measured aperture
number in this revalidation.** The opening-width judgement rests on the identical drawn bounding box across all
seven states and on looking at the art, not on a measurement I could not make.

## GDD canon change: does not touch door art direction

The canon move `5d9aa63a…` -> `2d5c8a1d…` is `b7e46c320`, *"Lower Vault canon — art must not out-promise the
geometry"*, one hunk in `DUNGEON_ART_DIRECTION.md` about painted platforms versus walkable collision in the
Lower Vault. It constrains what environment art may imply about geometry. **It says nothing about door states,
door identity, the final-door variant or door readability**, and nothing in NSC-065's acceptance criteria
depends on it. I wrote that line, and its subject is floor geometry.

## Verdict

**VAL-001 PASS** (re-run, artifact above). **VAL-002 PASS** at the current import settings, re-done rather than
carried. **No GDD impact.** Nothing is owed from the art side; NSC-065 is revalidatable at `ac8ddffa1`.

**One caveat for whoever records this:** NSC-096 will move the wizard to the `PixelLab128` set at 64 PPU. That
changes the wizard's world height and therefore the 44% figure above — VAL-002's coherence half will go stale
again when it lands. That is expected and correct, not a defect; it is the same gate measuring a genuinely
changed world.
