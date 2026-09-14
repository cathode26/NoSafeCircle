# PixelLab stationary enemy art generation record — NSC-063

Status: PixelLab was available and used. Both required archetypes (Melee Enemy,
Ranged Enemy) have a selected eight-facing idle source set. This record is
provenance and selection evidence only; it does not create Unity prefabs,
Animator assets, scene placement, pursuit, attacks, navigation, or damage.

**2026-09-14 update:** Vincent reviewed the original selection below and chose
REVISE: the Melee Enemy's cleaver needed to be clearly visible in every facing,
and the Ranged Enemy needed a brighter, more immediately readable silhouette in
every facing. A new eight-direction PixelLab generation was created for each
family (see "Revision generation" below) and the revised pair now replaces the
original selection as the retained source under
`Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/`. The original
candidates (`melee_a/`, `melee_b/`, `ranged_a/`, `ranged_b/`) and their record
below are kept intact as review history; they are no longer the retained
source. The pair below (now the revision candidates `melee_c`/`ranged_c`,
described in the new section) is the assistant's proposed selection for
Vincent's visual review. Vincent has not yet approved this revised candidate
commit.

See `generation-plan.md` in this same folder for the approved brief, prompts,
negative-constraint list, deterministic naming rule, and human visual-selection
checklist this record follows.

## Tool and settings

- Tool: PixelLab MCP `create_character`
- Generation mode: `standard` (1 generation charged per character regardless of
  direction count)
- Body type: `humanoid`
- View: `low top-down`
- Requested canvas size: `128` (square). PixelLab's standard mode expands the
  generation canvas internally; every candidate actually rendered at
  **180x180px**, RGBA, transparent background. This expanded size is recorded
  here as the real, consistent dimension — not the requested one.
- Directions requested: `8` (all PixelLab base directions: north, north-east,
  east, south-east, south, south-west, west, north-west). All eight facings
  (`north`, `north-east`, `east`, `south-east`, `south`, `south-west`,
  `west`, `north-west`) were downloaded, retained, and verified as byte-identical
  to their corresponding selected-source copies in
  `Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/`.
- Outline: `single color black outline`
- Shading: `basic shading`
- Detail: `medium detail`
- `text_guidance_scale`: `10` (raised from the tool default of 8 to hold the
  prompt more literally)
- Proportions: default preset (not overridden)
- No animation was requested. Each selected frame is the character's static
  rotation image for that direction, used directly as the idle/standing
  frame. `animate_character` was never called, matching the task's "no
  movement or attack animations" boundary.
- `create_character` exposes no seed parameter and no separate negative-prompt
  field. The PixelLab-issued `character_id` (and its `group_id`) is therefore
  the authoritative generation identity for each candidate, not a seed. The
  negative-constraint list from `generation-plan.md` could not be submitted as
  a discrete API parameter on this tool; it was instead enforced by visual
  review at selection time (see "Selection reasoning" below), and both
  finalists were checked against every item in that list before being
  retained.

## Candidate family prompts (verbatim, shared by both candidates within a family)

These original prompts name four diagonal facings. The PixelLab request used
`directions: 8`, and the retained exports and inventory include all eight.
The prompt text is preserved verbatim as provenance rather than rewritten to
match the later eight-facing contract.

### Melee family — close-range pursuer

```text
Pixel art character sprite for a 2.5D isometric dark-fantasy survival game, dark but cute horror-comedy tone: a squat candle-snuffing dungeon brute with a chipped iron cleaver held low, oversized hood, patched charcoal cloak, ember-orange eyes, heavy boots, and a clear forward-leaning close-range pursuer silhouette. Four separate consistent gameplay facings: north-east, north-west, south-east, south-west. Transparent background, feet anchored to one shared baseline, stable idle stance, restrained charcoal, bone, rust, and ember palette, soft single-direction lighting, crisp readable pixels, no environment, no text.
```

### Ranged family — distant caster/projectile threat

```text
Pixel art character sprite for a 2.5D isometric dark-fantasy survival game, dark but cute horror-comedy tone: a small hunched lantern wraith caster with a tall cracked lantern-staff, round teal ghost-light, trailing violet scarf, narrow silhouette, and an unmistakable distant projectile-threat read. Four separate consistent gameplay facings: north-east, north-west, south-east, south-west. Transparent background, feet anchored to one shared baseline, stable idle stance, restrained charcoal, bone, teal, and violet palette, soft single-direction lighting, crisp readable pixels, no environment, no text.
```

### Negative constraints applied at visual review (both families)

Opaque/colored background, baked floor shadow, cropped limbs, floating feet,
inconsistent scale/baseline, front-facing orthographic or side-view pose,
perspective camera, free-rotation presentation, extra characters, pets,
weapons obscuring the silhouette, gore, blood, dismemberment, exposed organs,
photorealism, smooth vector art, blurry anti-aliasing, gradients, text, logos,
watermark, recognizable franchise characters, wizard robes or wizard staff,
attack pose, projectile in flight, hit reaction, death pose, environmental
scenery.

## Generated candidates and generation identifiers

Two candidate identities were generated per archetype (bounded at the task's
"at most two candidate identities per archetype" limit), using the identical
family prompt above for both candidates in that family.

| Candidate | PixelLab `character_id` | PixelLab `group_id` | Rendered size | Result |
|---|---|---|---|---|
| Melee Candidate A — "Dungeon Brute" | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` | `a9d1ee9f-090f-4df8-9534-a44bba438c12` | 180x180 | **Selected** |
| Melee Candidate B — "Dungeon Brute" | `8d329296-ab6d-4372-a93c-b67319fb964a` | `66c29cda-4417-4258-993a-05eb84080077` | 180x180 | Not selected |
| Ranged Candidate A — "Lantern Wraith" | `21bfad3b-86ab-43f9-94f2-a03cb3ed5ba4` | `fc968dcb-eaf5-4bc8-a1a6-44fedbd6a196` | 180x180 | Not selected |
| Ranged Candidate B — "Lantern Wraith" | `361131dd-8c48-4b99-8b81-c79bd30078dc` | `f8421090-c9f3-42e9-aaae-262ee997238c` | 180x180 | **Selected** |

All four candidates completed successfully; PixelLab was available for the
complete duration of this task and no substitute generator was used.

Raw exports (both selected candidates, all eight facings each — 16 PNGs total)
are preserved under `Docs/Art/Enemies/Candidates/<selected-candidate>/` in this
repository for comparison and provenance evidence. Rejected-candidate diagnostics
remain available under `Docs/Art/Enemies/Candidates/<rejected-candidate>/`.

## Contact sheet

`Docs/Art/Enemies/contact_sheet.png` shows both selected enemies side by side
across all eight gameplay facings (north, north-east, east, south-east, south,
south-west, west, north-west), assembled locally from the raw PixelLab exports
with Pillow (no additional AI generation was used to build the sheet).

## Selection reasoning

**Melee Enemy — selected Candidate A ("Dungeon Brute").** Both melee
candidates render as a hooded, cloaked pursuer silhouette. Candidate A shows
visible leather leg wraps, forearm straps, and heavier boots that read as a
geared, forward-leaning brute ready to close distance, while Candidate B is a
plainer robe-only silhouette closer to a generic cloaked figure. Neither
candidate clearly shows the prompted "chipped iron cleaver" at these
three-quarter diagonal angles — the low-held weapon is occluded by the body's
own silhouette at NE/NW/SE/SW. Candidate A was preferred because its extra
equipment detail gives it a more readable "pursuer, not just cloaked wanderer"
identity even without the weapon visible; this gap is recorded as an open
question below.

**Ranged Enemy — selected Candidate B ("Lantern Wraith").** Candidate B holds
its glowing lantern forward in a grasped, active pose that immediately reads
as a wielded magical implement and plausible projectile source. Candidate A's
teal ghost-light instead floats passively beside the body, reading more like
ambient decoration than a threat the character is actively directing at the
player. Candidate B's hood is also deeper and mostly obscures the face,
reinforcing a distinct "wraith" identity that stays clear of the wizard's
presentation.

Both selected sets share the same restrained dark palette, soft
single-direction lighting, black single-color outline, and 180x180 transparent
canvas, and both avoid gore, franchise likeness, text, watermark, and baked
environment per the negative-constraint checklist.

## Original-selection remaining questions (2026-09-12 — superseded by the 2026-09-14 revision below)

1. ~~Neither selected Melee candidate clearly shows the prompted iron cleaver in
   the NE/NW/SE/SW facings~~ — **Resolved by the 2026-09-14 revision.** The
   cleaver is now clearly visible, held outward and unobscured, in all eight
   facings of the revised Melee Enemy.
2. The original selected Ranged candidate's hood was a fully dark void with no
   visible face in the south-west and north-west facings, while the
   north-east and south-east facings showed a partial jaw/chin. **Superseded**
   — the revised Ranged Enemy uses a brighter, more consistent pale hood
   interior across facings; see the revision's own remaining question below.
3. NSC-061 wizard art was not committed when this candidate was generated;
   it is now present in the current project. The assistant sees a hooded
   Melee Enemy beside a pointed-hat wizard in the two contact sheets, but
   Vincent should confirm their silhouettes remain distinct at gameplay scale.
   **Still open**, carried forward to the revision.
4. Confirm gameplay-scale readability (distinguishing Melee from Ranged at a
   glance, at the isometric camera's actual in-game zoom level) once these
   sprites are available inside the DoorPrototype scene in a future
   integration task. **Still open**, carried forward to the revision.

## Revision generation (2026-09-14) — legibility fixes

Reason for revision: Vincent visually reviewed the original selection above
and chose REVISE rather than approve. Two specific legibility problems were
named: the Melee Enemy's iron cleaver was not clearly visible in its eight
facings, and the Ranged Enemy's silhouette was not immediately readable
(too dark) in its eight facings. This section documents the one new
eight-direction PixelLab `create_character` generation created per family to
fix those two problems, per the bounded-revision task scope (at most one new
candidate identity per family, no other generator substituted).

### Tool and settings (revision)

- Tool: PixelLab MCP `create_character`
- Generation mode: `pro` (AI reference-based generation, always 8 directions,
  40 generations charged per character). Mode was changed from the original
  selection's `standard` mode specifically because `pro` mode does not treat
  the character description as soft guidance the way `standard` mode's style
  parameters do, and the original failure (cleaver occluded by the body's own
  silhouette; the wraith's ghost-light and hood reading as near-black) came
  from `standard` mode not reliably following the prompted weapon pose and
  contrast. Pro mode ignores `n_directions`, `outline`, `shading`, `detail`,
  `text_guidance_scale`, and `proportions` — style now comes entirely from the
  description text below.
- Body type: `humanoid`
- View: `low top-down` (unchanged from the original selection, preserving the
  same fixed isometric camera language)
- Requested canvas size: `128` (square). Unlike the original `standard`-mode
  selection (which PixelLab internally expanded to 180x180), `pro` mode
  rendered every revision candidate at exactly the requested **128x128px**,
  RGBA, transparent background. All 16 replaced selected-source files share
  this same 128x128 dimension; the two revised families remain internally
  coherent with each other even though this differs from the previous
  archetypes' 180x180 canvas.
- Directions requested: `8` (all PixelLab base directions). All eight facings
  were downloaded, retained, and verified byte-identical to their
  corresponding selected-source copies in
  `Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/`.
- No animation was requested; each selected frame is the character's static
  rotation image for that direction, used directly as the idle/standing
  frame, matching the "no movement or attack animations" boundary.
- As with the original selection, `create_character` exposes no seed
  parameter and no separate negative-prompt field in any mode. The PixelLab
  `character_id`/`group_id` pair remains the authoritative generation
  identity. The negative-constraint list from `generation-plan.md` was
  enforced by visual review at selection time (see "Selection reasoning"
  below), the same as the original selection.

### Candidate family prompts (revision, verbatim)

#### Melee family revision — visible cleaver

```text
Pixel art character sprite for a 2.5D isometric dark-fantasy survival game, dark but cute horror-comedy tone: a squat candle-snuffing dungeon brute gripping a large chipped iron cleaver raised diagonally outward and away from the body in a clear high guard, the blade fully unobstructed by the torso, cloak, or hood in every facing. Oversized hood, patched charcoal cloak cut short at the weapon-arm shoulder so the arm and blade silhouette stay completely clear, ember-orange eyes, heavy boots, forward-leaning close-range pursuer stance. The iron cleaver blade is a large, bright, high-contrast steel-gray shape with a visible glinting edge, held out to the side or forward so it is never tucked behind the back, never hidden inside the cloak, and never overlapping the torso silhouette, in all eight consistent gameplay facings: north, north-east, east, south-east, south, south-west, west, north-west. Transparent background, feet anchored to one shared baseline, stable idle stance, restrained charcoal, bone, rust, and ember palette, soft single-direction lighting, crisp readable pixels, no environment, no text, no gore, no blood.
```

#### Ranged family revision — brighter, higher-contrast silhouette

```text
Pixel art character sprite for a 2.5D isometric dark-fantasy survival game, dark but cute horror-comedy tone: a small hunched lantern wraith caster gripping a tall cracked lantern-staff held forward and outward, topped with a bright glowing round teal ghost-light lantern that is the brightest element in the image. Trailing violet scarf, narrow silhouette with a pale bone-white glowing hood interior and faint glowing eyes clearly visible against the dark cloak so the face reads even in silhouette, unmistakable distant projectile-threat read. Strong value contrast between the bright glowing lantern, the glowing hood interior, and the dark charcoal cloak so the whole character stays instantly readable as a bright small silhouette against a transparent background, in all eight consistent gameplay facings: north, north-east, east, south-east, south, south-west, west, north-west. Transparent background, feet anchored to one shared baseline, stable idle stance, restrained charcoal, bone, teal, and violet palette with bright teal glow accents, soft single-direction lighting, crisp readable pixels, no environment, no text, no gore, no blood.
```

Negative constraints applied at visual review are the same list used for the
original selection (see above): opaque/colored background, baked floor
shadow, cropped limbs, floating feet, inconsistent scale/baseline,
non-isometric camera pose, extra characters/pets, weapon fully obscured,
gore/blood/dismemberment, exposed organs, photorealism, smooth vector art,
blurry anti-aliasing, gradients, text, logos, watermark, recognizable
franchise characters, wizard robes/staff, attack pose, projectile in flight,
hit reaction, death pose, environmental scenery. Both revision candidates were
checked against this list before being retained.

### Generated candidates and generation identifiers (revision)

Only one new candidate identity was generated per archetype, matching the
bounded-revision limit of at most one new eight-direction character per
family.

| Candidate | PixelLab `character_id` | PixelLab `group_id` | Mode | Rendered size | Result |
|---|---|---|---|---|---|
| Melee revision — "Melee Enemy Revision - Visible Cleaver" | `070592db-d334-4e7d-b5c9-5dad404d7f98` | `9e547e77-e1f7-4e2e-a55e-9d913d054134` | pro | 128x128 | **Selected** |
| Ranged revision — "Ranged Enemy Revision - Brighter Wraith" | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` | `51e771fd-7269-4c7f-9822-c3f2b34cd91d` | pro | 128x128 | **Selected** |

Both revision generations completed successfully; PixelLab was available for
the complete duration of the revision and no substitute generator was used.
No `animate_character` call was made for either revision candidate (idle
standing frame only, per the task's no-animation boundary).

Raw exports (both revision candidates, all eight facings each — 16 PNGs
total) are preserved under `Docs/Art/Enemies/Candidates/melee_c/` and
`Docs/Art/Enemies/Candidates/ranged_c/` in this repository, as new candidate
folders distinct from the original `melee_a/`, `melee_b/`, `ranged_a/`,
`ranged_b/` folders (which remain intact as review history and are not
authorized Unity-integration inputs).

### Contact sheet (revision)

`Docs/Art/Enemies/contact_sheet.png` was regenerated from the revised,
now-selected source files and shows both revised enemies side by side across
all eight gameplay facings. It replaces the contact sheet built from the
original selection. `Docs/Art/Enemies/Candidates/_inspection/` holds
additional comparison sheets built for this revision only (a full-resolution
128px sheet and a downscaled ~48px "gameplay-scale" sheet, plus an
old-vs-new side-by-side comparison) as supporting visual-review evidence; they
are not part of the deterministic inventory.

### Selection reasoning (revision)

**Melee Enemy — selected the revision candidate.** The cleaver is now a
large, bright steel-gray blade held outward from the body in every one of the
eight facings, including the diagonals where the original selection fully
occluded it. At both full resolution and a downscaled ~48px gameplay-scale
comparison, the blade remains a distinct, separately readable shape against
the dark cloak silhouette in every facing — a direct fix for the named defect
in the original selection, where the weapon was invisible in all eight
facings at the same downscaled comparison.

**Ranged Enemy — selected the revision candidate.** The lantern-staff's teal
ghost-light is now a bright, saturated highlight, and the hood interior
renders as a pale, glowing shape with visible dot-eyes rather than a
near-black void. At the downscaled ~48px gameplay-scale comparison, the
revised silhouette reads immediately as a small bright shape against the dark
cloak, where the original selection was nearly indistinguishable from the
background at the same scale. The violet scarf and narrow cloak silhouette
are preserved, keeping the "wraith" identity intact.

Both revised sets keep the same restrained dark charcoal/bone palette family
(rust/ember for Melee, teal/violet for Ranged), soft single-direction
lighting, black outline, and transparent 128x128 canvas, and both were
checked against the negative-constraint list above before being retained.

## Current remaining human visual-review questions (revision)

1. The revised Ranged Enemy's hood interior and eye glow are brighter and more
   consistent across facings than the original selection, but Vincent should
   confirm facing-to-facing consistency (especially west, where the profile
   view shows less of the hood interior) reads as intentional rather than an
   inconsistent render.
2. NSC-061 wizard art silhouette distinction (original open question 3) is
   unaffected by this revision and remains open: confirm the Melee Enemy's
   silhouette stays visually distinct from the wizard's at gameplay scale.
3. Confirm gameplay-scale readability inside the actual DoorPrototype scene at
   the isometric camera's real in-game zoom level (original open question 4)
   once these revised sprites are available in a future integration task —
   the ~48px comparison sheet in `Candidates/_inspection/` is a desk-check
   approximation, not an in-engine confirmation.
4. Confirm the revised 128x128 native canvas (versus the original
   archetypes' 180x180 canvas) is acceptable for later Unity SpriteRenderer
   scaling; both revised families are internally consistent with each other
   at 128x128, but this is a different base resolution than the original
   NSC-063 selection used.

## Deterministic file naming

Selected source files use the plan's naming rule:
`enemy_<family>_<direction>_idle_00.png`, with `<family>` in `{melee, ranged}`
and `<direction>` in `{n, ne, e, se, s, sw, w, nw}`. See `inventory.md` in
this folder for the complete deterministic inventory mapping each retained
filename to its exact generation identifier, dimensions, and hash.
