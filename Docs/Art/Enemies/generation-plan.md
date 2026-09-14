# Stationary enemy art generation plan

Status: PixelLab generation and the assistant's eight-direction candidate selection are complete; Vincent's visual decision is pending. The proposed source files and exact generation evidence are recorded in `PIXELLAB_GENERATION.md` and `inventory.md`. This plan covers source-art candidates and human selection only; it does not create Unity prefabs, Animator assets, scene placement, pursuit, attacks, navigation, damage, or other behavior.

## Shared PixelLab brief

Use the same fixed 2.5D isometric camera language as the wizard: dark-but-cute horror-comedy dark fantasy, readable silhouette, restrained palette, soft directional light, clean pixel edges, and transparent background. Generate one coherent family at a time with eight gameplay facings: north, north-east, east, south-east, south, south-west, west, and north-west. Keep the character fully in frame, feet visible, and the bottom of both feet at the same baseline in every facing. Use square 128x128 px output unless PixelLab requires another supported size; if so, record the exact size and use it for every candidate in both families. Idle-only is sufficient: one stable standing frame or one short loop of 4–6 frames at 8–12 fps, with no attack or movement claim.

## Candidate family prompts

1. **Melee family — close-range pursuer**

   `Pixel art character sprite for a 2.5D isometric dark-fantasy survival game, dark but cute horror-comedy tone: a squat candle-snuffing dungeon brute with a chipped iron cleaver held low, oversized hood, patched charcoal cloak, ember-orange eyes, heavy boots, and a clear forward-leaning close-range pursuer silhouette. Eight separate consistent gameplay facings: north, north-east, east, south-east, south, south-west, west, north-west. Transparent background, feet anchored to one shared baseline, stable idle stance, restrained charcoal, bone, rust, and ember palette, soft single-direction lighting, crisp readable pixels, no environment, no text.`

2. **Ranged family — distant caster/projectile threat**

   `Pixel art character sprite for a 2.5D isometric dark-fantasy survival game, dark but cute horror-comedy tone: a small hunched lantern wraith caster with a tall cracked lantern-staff, round teal ghost-light, trailing violet scarf, narrow silhouette, and an unmistakable distant projectile-threat read. Eight separate consistent gameplay facings: north, north-east, east, south-east, south, south-west, west, north-west. Transparent background, feet anchored to one shared baseline, stable idle stance, restrained charcoal, bone, teal, and violet palette, soft single-direction lighting, crisp readable pixels, no environment, no text.`

### Negative constraints for both prompts

Exclude: opaque or colored background, floor shadow baked into the image, cropped limbs, floating feet, inconsistent scale or baseline, front-facing orthographic or side-view pose, perspective camera, free-rotation presentation, extra characters, pets, weapons that obscure the silhouette, gore, blood, dismemberment, exposed organs, photorealism, smooth vector art, blurry anti-aliasing, gradients, text, logos, watermark, recognizable franchise characters, wizard robes or wizard staff, attack pose, projectile in flight, hit reaction, death pose, and environmental scenery.

## Generation settings and direction contract

For every request, record the PixelLab model/tool name and version if exposed, prompt verbatim, negative prompt verbatim, seed or generation identifier, output dimensions, frame count, frame rate, transparency setting, and any style or palette controls. Prefer one shared seed/style configuration per family and retain the selected generation identifier for each facing. Directions must be labeled exactly `n`, `ne`, `e`, `se`, `s`, `sw`, `w`, and `nw`; do not infer direction from file order. The selected set must have matching dimensions, scale, lighting, palette, feet baseline, and transparent pixels. If an idle loop is generated, every frame in every facing must preserve those invariants and loop without a visible pop. A stable frame is acceptable when PixelLab cannot provide a coherent loop.

## Deterministic file naming

Retain only selected source files under `Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/` using lowercase ASCII names:

`enemy_<family>_<direction>_idle_<frame>.png`

where `<family>` is `melee` or `ranged`, `<direction>` is `n`, `ne`, `e`, `se`, `s`, `sw`, `w`, or `nw`, and `<frame>` is zero-padded (`00` for a stable frame, or `00` through `05` for a six-frame loop). Examples: `enemy_melee_ne_idle_00.png` and `enemy_ranged_s_idle_00.png`. Store candidate previews/contact sheets outside this selected-source directory. The provenance record must map each retained filename to its exact PixelLab generation identifier and settings; never use timestamps, UI labels, or provider-local filenames as the authoritative identity.

## Human visual-selection checklist

- [ ] PixelLab was available and used; otherwise the worker stopped with `BLOCKED` and named the missing capability.
- [ ] A contact sheet or idle animation preview shows both complete candidate families together.
- [ ] One Melee set is selected and reads immediately as a close-range pursuer through silhouette, cleaver, stance, and mass.
- [ ] One Ranged set is selected and reads immediately as a distant caster/projectile threat through staff, ghost-light, and silhouette.
- [ ] Both sets share the wizard/environment’s dark-but-cute horror-comedy tone, pixel scale, lighting direction, and palette discipline.
- [ ] All eight facings exist for each selected family, with no ambiguous labels, missing views, mirrored mistakes, or inconsistent scale.
- [ ] Every image has a transparent background, visible grounded feet, and a common baseline suitable for later stationary SpriteRenderer placement.
- [ ] Idle frames are stable and coherent; no frame implies an unrequested attack, pursuit, damage, or death behavior.
- [ ] No gore, franchise resemblance, text, watermark, baked environment, or accidental wizard identity is present.
- [ ] The deterministic inventory, exact prompts/settings, and selected generation identifiers are complete before handoff.
- [ ] Selection records why this pair is readable and cohesive; it does not claim Unity integration or gameplay validation.
