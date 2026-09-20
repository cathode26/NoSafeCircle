# Binding the enemy art: the scale answer, measured

Art Director Agent, 2026-09-17, for the Documentation Agent ("are the 176x176 enemy sets still your approved
standard... or do the enemies need re-cutting to the 128 standard?"). **No generations spent.** Every number is
measured from the committed blobs on local `main` (`b7e46c320`), extracted with `git show`.

## Answer: no re-cut. The premise has a measurement error in it.

**The canvas is not the scale.** Only the *walk* frames are 176x176; the idle frames are 128x128. The 176 is
PixelLab's square rotation padding, and what the camera shows is the drawn figure inside it.

| Set | Canvas | Drawn height (median) | At 64 PPU |
|---|---|---|---|
| melee idle | 128 | 88 px | **1.38 units** |
| melee walk | 176 | 87 px | **1.36 units** |
| ranged idle | 128 | 99 px | **1.55 units** |
| ranged walk | 176 | 96 px | **1.50 units** |
| **wizard 128 standing (merged today)** | 128 | **105 px** | **1.64 units** |

At one shared 64 PPU the enemies are **already shorter than the wizard**, by 6% to 17% - not a third bigger. A
re-cut to 128 would shrink them further and cost generations to fix a problem that does not exist.

Widths, for completeness: wizard 45 px (0.70 u), melee 81-82 px (1.27 u), ranged 79-82 px (1.23 u). The enemies
read as **squat and wide** against a narrow wizard, which is the silhouette contrast the bible asks for.

## The enemy art is already bind-ready. Do not touch it.

The committed metas and the builder agree, and both are right:

| | Committed `.meta` | Measured ground line |
|---|---|---|
| walk (176) | `alignment: 9`, `spritePivot {0.5, 0.25}`, `spritePixelsToUnits: 64`, `filterMode: 0` (point) | lowest opaque row **131 in all 96 frames, spread 0** -> pivot exactly 0.25 |
| idle (128) | `alignment: 9`, `spritePivot {0.5, 0.1484375}`, PPU 64, point | ground row 108 for that file; the 8 facings run 107-113, and **each meta carries its own pivot** |

`EnemyAnimationAssetBuilder.cs` sets `EnemyPixelsPerUnit = 64f`, `FilterMode.Point` and
`spritePivot = new Vector2(0.5f, frame.PivotY)` - **per frame**. So the 3-to-5 px ground-line spread across the
idle facings is already absorbed by per-frame pivots. Nothing floats, nothing needs `plant_feet.py`.

**The one trap to avoid:** idle and walk have different canvases *and* different ground fractions (0.133 vs
0.250). Anyone who binds both sets with a single hard-coded pivot puts the enemy about 15 px (0.23 units) in the
air while idle and snaps it down when it walks. Use each sprite's own meta pivot, which is what the builder does.

## The real scale bug is on the wizard's importer, not the enemies

`DoorPrototypeGlobalSceneBuilder.ImportWizardSprite` still sets **`spritePixelsPerUnit = 180f`** and
**`spritePivot = (0.5f, 0f)`** - written for the old 180 px art. Bound against the 128 px art merged today, the
wizard would come out **105/180 = 0.58 units tall**, less than half the melee enemy's 1.36. That is NSC-096's
switch, and these are the exact values it needs:

- **PPU 64** for every wizard sheet;
- **pivot `(0.5, y)`** with y per variant, from each variant's own measured ground line (standing and walk share
  it, spread 0 within each variant):

| variant | ground row | pivot y |
|---|---|---|
| masculine-light | 121 | **0.0469** |
| masculine-dark | 120 | **0.0547** |
| feminine-dark | 120 | **0.0547** |
| feminine-light | 119 | **0.0625** |

The committed wizard `.meta` files carry Unity defaults (PPU 100, centre pivot, `filterMode: 1` bilinear). That
is harmless **only because the builder overrides them at import** - it is what the NSC-095 contract asked for.
Anything that binds these PNGs without going through an importer that sets point filtering will render the wizard
blurred.

## And the thing Vincent actually saw: the door is small, not the wizard big

Differencing the `sealed` and `open` door sprites isolates the doorway, because that is the only thing the two
states change. The changed region is **64 x 83 px = 1.00 x 1.30 world units**, rows 18 to 100 - and the sprite's
lowest opaque row is 120, so the bottom 20 px are the painted floor disc in front of the threshold.

**A 1.64-unit wizard does not fit through a 1.30-unit opening.** That is the "large wizard against a small door"
read, and it is the door art's proportions, not the characters. Two ways out, and it is a design call:

- **bind the door sprite larger** - x1.54 makes the opening 2.0 units, enough for a 1.64-unit character with
  headroom, and the stone arch becomes about 3 units tall, which is plausible for a vault gate. Zero generations;
- **re-author with more passage and less arch** - a generation request with its own cap.

## Is the art still current? Yes, with one gap that matters for a video

- **Melee:** the committed north-east set carries **one cleaver in the idle and in all six walk frames**
  (`melee_ne_cleaver_check.png`), which is what Vincent approved on 2026-09-16. The old queue item "melee
  north-east walk pick" is **stale - closed**.
- **Ranged:** the committed art is the Lantern Wraith family, teal `#30e0cb` accent, 8 to 31 colours per frame,
  violet 76%. Consistent with the wisp work Vincent picked.
- **The gap: there is no attack art for either enemy.** Each facing has an idle and a six-frame walk, nothing
  else. The wraith's attack wind-up exists as **one sample facing** - Vincent picked "sample A, grumpy
  ghost-flame" on 2026-09-16 - and the other seven facings (about 42 printed) have never been generated. **If the
  video shows an enemy attacking, it will play a walk or idle pose.** That is a generation request with its own
  cap, not a blocker for binding what exists.
