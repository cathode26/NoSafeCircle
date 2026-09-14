# PixelLab stationary enemy art generation record — NSC-063

Status: PixelLab was available and used. Both required archetypes (Melee Enemy,
Ranged Enemy) have a selected eight-facing idle source set. This record is
provenance and selection evidence only; it does not create Unity prefabs,
Animator assets, scene placement, pursuit, attacks, navigation, or damage.

The pair below is the assistant's proposed selection for Vincent's visual
review. Vincent has not approved these sprites or this candidate commit. In
particular, the Melee Enemy's cleaver is hard to see and the Ranged Enemy may
be too dark at gameplay scale. NSC-077 must wait for an explicit art decision.

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

## Remaining human visual-review questions

1. Neither selected Melee candidate clearly shows the prompted iron cleaver in
   the NE/NW/SE/SW facings (it is occluded by the "held low" pose at these
   angles). Confirm whether the current silhouette — hood, cloak, leg wraps,
   forward-leaning stance — reads clearly enough as a close-range pursuer
   without a visible weapon, or whether a follow-up PixelLab generation should
   be requested that holds the cleaver more visibly at these facings.
2. The selected Ranged candidate's hood is a fully dark void with no visible
   face in the south-west and north-west facings, while the north-east and
   south-east facings show a partial jaw/chin. Confirm this reads as an
   intentional "faceless wraith" identity rather than an inconsistent render
   that should be regenerated for facing-to-facing coherence.
3. NSC-061 wizard art was not committed when this candidate was generated;
   it is now present in the current project. The assistant sees a hooded
   Melee Enemy beside a pointed-hat wizard in the two contact sheets, but
   Vincent should confirm their silhouettes remain distinct at gameplay scale.
4. Confirm gameplay-scale readability (distinguishing Melee from Ranged at a
   glance, at the isometric camera's actual in-game zoom level) once these
   sprites are available inside the DoorPrototype scene in a future
   integration task.

## Deterministic file naming

Selected source files use the plan's naming rule:
`enemy_<family>_<direction>_idle_00.png`, with `<family>` in `{melee, ranged}`
and `<direction>` in `{n, ne, e, se, s, sw, w, nw}`. See `inventory.md` in
this folder for the complete deterministic inventory mapping each retained
filename to its exact generation identifier, dimensions, and hash.
