# PixelLab door generation plan

Current status: two families were generated; Family B's seven selected states
are retained for visual review. See `PIXELLAB_GENERATION.md` and
`contact_sheet.png`. The following pre-generation plan is preserved as the
design record; it does not import art or wire art to Unity behavior.

## Target family

Create one coherent dark-but-cute horror-comedy isometric door family for the
five forward exits. The same silhouette, ground contact, opening width, light
direction, palette, and camera perspective must carry across these states:

- `sealed` — closed, intact, visibly impassable;
- `opening` and `open` — the same door visibly swung or parted, with a readable
  doorway opening;
- `locked` — closed and intact, with a clear lock or bar cue;
- `damaged` and `broken` — cracked or breached, with the passage visibly open;
- `final` — the same interaction-sized door with a restrained, obvious escape
  motif (warm rim light, distinctive crest, or magical trim), without implying
  different opening rules.

Use a transparent background and leave a small consistent margin around the
silhouette. Keep the art readable beside wall tiles and wizard/enemy
silhouettes. Avoid gore, severed parts, text, logos, watermarks, franchise
references, photorealism, free-rotation perspective, floor shadows detached
from the door, and any extra furniture or characters.

## PixelLab candidate prompts

Run both prompts with the same model/style, canvas, camera, lighting, palette,
and seed policy. Generate the state variants from the candidate family rather
than mixing unrelated door designs.

**Candidate A — iron-and-wood dungeon door**

`2.5D isometric game sprite, front-facing dungeon doorway viewed from a fixed three-quarter isometric camera, squat arched dark oak door reinforced with chunky black iron bands, tiny expressive brass lock, rounded hand-painted pixel-art forms, dark cute horror-comedy mood, muted charcoal teal and plum palette with one warm amber light, crisp readable silhouette, centered full door and threshold, transparent background, no text`

**Candidate B — bone-and-stone sealed door**

`2.5D isometric game sprite, front-facing dungeon doorway viewed from the same fixed three-quarter isometric camera, compact weathered stone frame with a painted wooden slab and a simple stylized bone-shaped latch, charming eerie pixel-art fantasy, dark violet slate and moss palette with one warm amber light, chunky shapes and clear silhouette at gameplay scale, centered full door and threshold, transparent background, no text`

For each candidate, request the matching `sealed`, `opening`, `open`, `locked`,
`damaged`, `broken`, and `final` variants. Preserve the base silhouette and
threshold in every variant; state changes are limited to door pose, latch,
cracks, breach, and the final-door accent.

## Settings and dimensions

Use square RGBA PNG output at `128x128` pixels for each source sprite, with the
door occupying approximately 80% of the canvas height and a consistent bottom
ground-contact line. Use one fixed isometric three-quarter direction for the
review family. If PixelLab requires directional output, generate exactly four
directions (`N`, `E`, `S`, `W`) using the same seed/style settings, and keep
the direction names explicit; do not accept mixed camera angles.

Animation is optional for source selection. If PixelLab provides animation,
request only a short `opening` sequence of 4 frames and a 2-frame `damage`
flash, keeping frame size, pivot, ground contact, and timing consistent. The
required static states must still be exported separately. Do not add runtime
animation or Unity Animator assets in this task.

## Provenance and deterministic file names

Record the exact PixelLab generation identifier, prompt text, negative prompt,
model/style, seed, dimensions, direction, frame count, and generation date in
the contact-sheet notes. Use this filename pattern for retained source files:

`door_<family>_<state>_<direction>_<frame>.png`

Examples:

`door_ironwood_sealed_S_000.png`
`door_ironwood_open_S_000.png`
`door_ironwood_final_S_000.png`

Use lowercase ASCII family/state names, three-digit zero-based frame numbers,
and no spaces, provider IDs, timestamps, or words such as `final-final` in the
filename. Keep the provider generation ID in the provenance record, not in the
asset filename. A deterministic inventory must list every retained file and
its exact provenance; rejected candidates remain outside the selected source
folder.

## Contact sheet and human visual-selection checklist

Make one labeled contact sheet containing all states for Candidate A and B at
the same display scale, plus a gameplay-scale crop. Human review must confirm:

- [ ] Sealed reads immediately as a closed, impassable door.
- [ ] Opening/open reads as the same door with a genuinely readable passage.
- [ ] Locked is distinct from sealed through a clear lock/bar cue, without a
      new silhouette or altered doorway width.
- [ ] Damaged/broken reads as breach feedback and an open passage without gore.
- [ ] Final is recognizable as the same door and interaction footprint, with a
      coherent escape accent that does not imply special opening behavior.
- [ ] Every state shares the same bottom contact, scale, light direction,
      isometric camera, palette family, and transparent background.
- [ ] Door edges remain legible beside wall art and wizard/enemy silhouettes at
      gameplay scale; details are not dependent on zooming in.
- [ ] No frame introduces text, watermark, franchise imagery, graphic gore,
      detached shadow, extra character, or geometry that changes the passage.
- [ ] Choose one complete family across all required states; do not cherry-pick
      visually incompatible states from different families.
- [ ] Record the human selector, date, selected family, rejected family, and
      any state that needs regeneration. Selection is a review result, not
      evidence that Unity integration or in-game readability has been approved.
