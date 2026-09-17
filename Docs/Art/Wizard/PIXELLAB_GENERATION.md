# PixelLab Wizard Art Selection

## Selected family

The selected source family is the four 180 x 180, eight-direction PixelLab
characters below. They use the same low top-down camera, proportions, clothing,
equipment, palette, and horror-comedy tone. The independent player choices are
presentation (`Masculine` or `Feminine`) and skin (`Light` or `Dark`).

| Source key | PixelLab name | PixelLab character ID |
| --- | --- | --- |
| `masculine-dark` | Wizard - Masculine Dark | `10a82915-82e8-48a3-92bd-a261b2d992e1` |
| `feminine-dark` | Wizard - Feminine Dark | `c00d5bec-0da3-4bce-8d7c-dc2f5d2c33d4` |
| `masculine-light` | Wizard - Masculine Light | `3b41ccd5-0eb7-4b0b-9f1e-04b3956c5c75` |
| `feminine-light` | Wizard - Feminine Light | `c0be0b26-4477-4d1b-b6f0-cf57f3213a4f` |

The separate 128 x 128 `Dark-but-cute horror-comedy pixel art wizard`
generation was rejected because it does not belong to this cohesive four-option
family. It is not authorized input to NSC-062.

## Generation settings

- Tool: PixelLab MCP character generator
- Character template: `mannequin`
- PixelLab export format version: `3.1`
- Service model: not exposed by PixelLab's character or export metadata
- Canvas: 180 x 180 pixels
- Camera: low top-down view
- Base directions: 8
- Background: transparent
- Gameplay movement facings: north-east, north-west, south-east, south-west
- Walk animation: classic `walking`, 6 frames per direction
- Idle animation: the matching standing base frame is used as a one-frame loop
  in Unity

## Prompt construction

Every option used this shared direction:

> A weathered pulp-horror-survivor-turned-charming wizard, 2.5D isometric
> dark-fantasy RPG character, dark spooky dungeon color palette of deep plum
> and teal-black shadows with warm lantern-glow highlights, battle-worn patched
> wizard's robe under a rugged leather duster, tall scuffed boots, a leather
> bandolier of small glass potion vials, a gnarled wooden traveling staff, a
> lopsided patched pointed wizard hat, a dog-eared spellbook tucked under one
> arm, cute expressive proportions, an endearingly overconfident smirk mixed
> with a put-upon exhausted expression, horror-comedy charm, readable heroic
> silhouette, original fantasy character, no real-world celebrity likeness, no
> franchise costume or logo, no chainsaw, no shotgun, no blood or gore, not
> sexualized, family-friendly tone.

The option-specific opening traits were:

- `masculine-dark`: Tall adult male wizard with deep brown Black skin, a short
  trimmed beard, close-cropped natural hair, and broad rugged shoulders.
- `feminine-dark`: Lean adult female wizard with deep brown Black skin, natural
  coily hair twists escaping her hat, and a wiry rugged build.
- `masculine-light`: Stocky adult male wizard with light pale skin, scruffy
  sandy-brown stubble beard, tousled windswept brown hair escaping his hat, and
  broad rugged shoulders.
- `feminine-light`: Lean adult female wizard with light pale skin and freckles,
  a windswept auburn hair braid escaping her hat, and a wiry rugged build.

The authoritative complete prompt strings, including punctuation, are recorded
per source in `source-inventory.json` under `generator.prompt`.

## Selection review

This family was selected because all four characters have equally intentional
designs, clear wizard silhouettes, battered practical clothing, readable skin
and presentation differences, and a shared dark-but-cute horror-comedy style.
The light masculine option is the closest to the requested rugged pulp-horror
energy; the other three preserve that vocabulary without becoming recolors or
imitating an actor or protected character.

## Authorized source inventory

Each `selected` directory is authorized input to NSC-062. Each `raw` ZIP is
retained for provenance and reproducibility; incidental animations in a raw ZIP
are excluded unless they also appear in its `selected` directory.

| Source key | Raw PixelLab ZIP | SHA-256 | Authorized PNGs |
| --- | --- | --- | ---: |
| `masculine-dark` | `masculine-dark/raw/Wizard_-_Masculine_Dark.zip` | `97cc3eeb9a0fd4d7a7c2202b38939e8806668315b5d21f889fa963433c197967` | 32 |
| `feminine-dark` | `feminine-dark/raw/Wizard_-_Feminine_Dark.zip` | `717b1f30ea923a7a13d19c79277328e947871ead114334d17bbb620d52c008cf` | 32 |
| `masculine-light` | `masculine-light/raw/Wizard_-_Masculine_Light.zip` | `a36540da22f603a63535f6275f3c4d5926795270c6798fcad4bc6f289f89fe49` | 32 |
| `feminine-light` | `feminine-light/raw/Wizard_-_Feminine_Light.zip` | `63b30bd14e456fe4210b5045bdf044c332da2d433fc5c7606441dcc356a304d0` | 32 |

For every source, `selected/standing` contains the eight PixelLab directions.
`selected/walk/north-east`, `north-west`, `south-east`, and `south-west` each
contain `frame_000.png` through `frame_005.png`. All 128 authorized PNGs are
180 x 180 RGBA images with transparent pixels. `source-inventory.json` records
the sorted repository-relative path, byte count, and SHA-256 of every one.

PixelLab's compass labels map directly to the game's four diagonal facings.
NSC-062 creates a one-frame looping idle clip from each matching standing image
and a six-frame walk clip from the matching `selected/walk` directory.

The raw masculine-light export also contains an optional four-frame PixelLab
idle animation, and the raw feminine-light export contains the accidental
224 x 224 V3 south walk. Neither is in the selected tree and neither is
authorized for Unity integration.

## NSC-073 correction: feminine-light north-east frames 004/005

Vincent's runtime report on 2026-09-12 found that the selected
`feminine-light/selected/walk/north-east/frame_004.png` and `frame_005.png`
lost the wizard's hat and shifted to an inconsistent left-facing side
profile, breaking continuity with the approved `frame_000.png` through
`frame_003.png`. NSC-073 replaced only those two PNGs at their existing
paths using PixelLab.

Replacement generation:

- Tool: PixelLab MCP `animate_character`, mode `v3` (custom action,
  frame_count 6, `keep_first_frame: true`)
- Character: `Wizard - Feminine Light`, character ID
  `c0be0b26-4477-4d1b-b6f0-cf57f3213a4f`
- Animation group ID: `55641d84-a4ef-423f-ba9f-3526801295bf`
- Animation job ID: `75f2d12d-aabf-4238-bdd7-04b3c8fb5734`
- North-east animation asset ID: `1a6e4335-a4e3-462d-8e2d-f6b297772d1b`
- Direction: `north-east`
- `action_description`: "walking, classic even-paced walk cycle, both arms
  swinging naturally, staff held steady, hat and robe consistent with the
  character's standard pose"
- PixelLab generated 7 frames on a 224 x 224 canvas (index 0 is the
  start-pose reference matching the character's existing north-east
  standing rotation; indices 1-6 are one full walk cycle).

Selection and canvas correction: the generator's 224 x 224 output uses the
same pixel scale as the family's 180 x 180 canvas, offset by a fixed
(+22, +22) pixel translation (confirmed by comparing the index-0 reference
frame's non-transparent bounding box against the existing
`selected/standing/north-east.png` bounding box, and cross-checked against
the bounding boxes of the unmodified `frame_000.png`-`frame_003.png`, all of
which share `x = 57-58`). Both selected replacement frames were cropped from
`(22, 22)` to `(202, 202)` of the 224 x 224 output to produce exact 180 x 180
RGBA PNGs. This crop is a pixel-exact region copy: both replacement PNGs were
verified to contain zero anti-aliased/partial-alpha pixels (0 of 32,400
pixels with `0 < alpha < 255`), so no resampling or hand-painting was
applied to PixelLab's output.

- `frame_004.png` <- generated frame index 1 of animation asset
  `1a6e4335-a4e3-462d-8e2d-f6b297772d1b`, cropped as above.
- `frame_005.png` <- generated frame index 6 of the same animation asset,
  cropped as above.

The existing 004/005 fallback used generated indices 1/5. In this alternate,
frame 005 uses generated index 6 of the same PixelLab animation asset,
cropped at the same (22,22)-(202,202) region. Index 6 returns closer to the
north-east three-quarter view before the loop restarts. Frame 004 still
turns somewhat rearward, so this is a visual review candidate, not an
approved continuity fix.
Generated frame indices 0 (start-pose reference), 2, 3, 4, and 5 were
reviewed and not used; they remain retrievable under the same animation
group ID for future reference. The former selected index-5 frame 005 is
preserved by fallback commit 7fe174fc5 with SHA-256
5e98c6d76a0cebbd4213e45245bf1fee90b5e652b46b9bd4dd51f06f6f8786d3.
This alternate uses cached PixelLab index 6 with SHA-256
a201861900e1c801545b25f181f3bf116f3be079a2c9f872ca6fd92d809ffe5a;
it required no new generator call.

The original NSC-073 source checkout had no `.meta` files for these PNGs.
Current main tracks `.meta` files at both selected paths. This reconciliation
changes only the two PNGs at those paths and preserves their Unity GUIDs.
Full generation and selection provenance, including previous/new size and
SHA-256 for both files, is recorded under `corrections` in `source-inventory.json`.

This candidate still requires the Windows orchestrator to run the committed
`WizardArtIntegrationTests` Unity Edit Mode test on this exact commit, and
Vincent's exact-candidate visual approval in `Assets/Scenes/DoorPrototype.unity`,
before integration (NSC-073 `VAL-001` and `VAL-002`).

## NSC-074 cardinal walk extension: north, east, south, west

NSC-074 adds six-frame walk cycles for the four missing cardinal facings to
the same four PixelLab characters. It adds exactly 96 new 180 x 180
transparent PNGs:

```text
<source key>/selected/walk/<north|east|south|west>/frame_000.png ... frame_005.png
```

No existing standing, diagonal walk, raw export, or NSC-061/NSC-073 file is
changed. The per-file path, direction, frame, dimensions, byte count,
SHA-256, `.meta` GUID, and source PixelLab animation asset are recorded under
`cardinal_walk_extension` in `source-inventory.json`.

NSC-074 was serialized after NSC-073 on 2026-09-16 (NSC-073 merge
`18089b060`). `source-inventory.json` keeps NSC-073's top-level
`corrections` array and this task's sibling `cardinal_walk_extension`, and
both provenance sections remain in this file.

### Generation settings

- Tool: PixelLab MCP `animate_character`, mode `v3`, `frame_count: 6`,
  `keep_first_frame: false`, generated 2026-09-14
- Start pose: each character's existing PixelLab rotation image for the same
  direction (the v3 default)
- Characters: the four IDs in the "Selected family" table above; 180 x 180,
  low top-down, "basic shading, single color black outline, medium detail"
- Service model: not exposed by PixelLab MCP
- Canvas: PixelLab v3 returned square canvases of 200 x 200 to 224 x 224.
  Every frame is a pixel-exact centered crop to 180 x 180 at offset
  `((W - 180) / 2, (W - 180) / 2)`. Before cropping, each frame was checked to
  have no opaque pixel outside the crop window. The crop introduces no
  partial-alpha pixels and applies no resampling, recoloring, or hand editing.
  The canvas and offset per direction are recorded in the inventory.

`action_description` for the first take of every direction (animation name
`NSC-074 cardinal walk v3`):

> walking, classic even-paced six-frame walk loop, feet stepping on one steady
> ground line, arms swinging gently, hat, hair, long robe and belt book kept
> exactly as in the standard pose

`action_description` for the south re-rolls (animation name
`NSC-074 cardinal walk v3 south in-place`):

> walking in place, classic even-paced six-frame walk loop, body stays at the
> same spot in the frame with feet stepping on one steady ground line, arms
> swinging gently, hat, hair, long robe and belt book kept exactly as in the
> standard pose

The masculine-dark south re-roll additionally asked for "arms swinging gently
close to the body, same toothy overconfident grin" and "long robe and belt".

### Selected PixelLab animations

`frame_00N.png` is generated frame index `N` of the listed animation asset.

| Source key | Direction | Animation group ID | Animation asset ID |
| --- | --- | --- | --- |
| `feminine-light` | north | `dbcfdbce-587a-4f96-bb07-3365ec69fc8d` | `c32a0e59-e552-4310-9313-851bc22b240f` |
| `feminine-light` | east | `dbcfdbce-587a-4f96-bb07-3365ec69fc8d` | `8eca9c0f-67db-4577-908a-c933ffa71b2c` |
| `feminine-light` | south | `dbcfdbce-587a-4f96-bb07-3365ec69fc8d` | `a04d5a11-6e65-44d5-8f84-ce65175ce1ab` |
| `feminine-light` | west | `dbcfdbce-587a-4f96-bb07-3365ec69fc8d` | `b0c46e57-5783-4006-8417-b3b6dc925d4c` |
| `feminine-dark` | north | `5f67d9fc-946b-4740-9035-d2c082cb4da4` | `cbbb7854-6684-40ac-b73e-12021018a76e` |
| `feminine-dark` | east | `5f67d9fc-946b-4740-9035-d2c082cb4da4` | `cdb1f481-8ea0-453d-87bd-0964d57be209` |
| `feminine-dark` | south | `0970b1d6-30cc-44af-ac7e-3fb4ced6ad0a` (in-place re-roll) | `2d55c7cc-36dd-4360-8c33-1cda63214775` |
| `feminine-dark` | west | `5f67d9fc-946b-4740-9035-d2c082cb4da4` | `09af4196-7036-40ce-970b-8b6861170c9b` |
| `masculine-light` | north | `496c414c-d31e-4bf8-8aab-64124eee9525` | `13075798-f45c-4d98-bd6b-e2fd5f47c8a4` |
| `masculine-light` | east | `496c414c-d31e-4bf8-8aab-64124eee9525` | `ac5c6013-1a0c-4049-9609-28f6fcc62351` |
| `masculine-light` | south | `496c414c-d31e-4bf8-8aab-64124eee9525` | `e4ba6fc4-2380-4fb5-b691-edc39002abe1` |
| `masculine-light` | west | `496c414c-d31e-4bf8-8aab-64124eee9525` | `fd268c65-ce67-47c8-a43a-b8d6dfdd3954` |
| `masculine-dark` | north | `f04e08e0-361e-4668-a39f-a5434d200cf7` | `420f5619-9e96-439d-ac8b-42770b0b304a` |
| `masculine-dark` | east | `f04e08e0-361e-4668-a39f-a5434d200cf7` | `b2a19034-4081-4e8b-8891-9f3c1dd597a5` |
| `masculine-dark` | south | `f04e08e0-361e-4668-a39f-a5434d200cf7` | `bfd18b5e-73f5-409c-ab95-6b080fbd1589` |
| `masculine-dark` | west | `f04e08e0-361e-4668-a39f-a5434d200cf7` | `04d03c87-e4b6-45a0-a97e-09fce498ca5c` |

### Continuity review

Every selected cycle keeps the character's hat, hair, face, robe, belt
accessories, skin, and palette from the matching standing image, and its
horizontal placement matches that standing image. North, east, and west
cycles loop within 0-3 px on the feet line.

PixelLab's south-facing v3 walks move the figure toward the camera during the
cycle, so the feet line jumps when the loop restarts:

- `feminine-light` south: 11 px jump. This take was kept over its in-place
  re-roll, which jumped 13 px.
- `feminine-dark` south: 5 px jump. The in-place re-roll replaced the first
  take, which jumped 8 px.
- `masculine-dark` south: 8 px jump. The first take was kept because its
  in-place re-roll turns to a three-quarter side view from `frame_003`. The
  kept take also swings the arms wide in frames 002-004 and softens the
  toothy grin.
- `masculine-light` south: 3 px jump.

Vincent should check these south loops specifically during visual approval.

### Rejected candidates

- Template walk cardinals already stored in each character's diagonal walk
  group, created 2026-09-13 with no recorded provenance: `d7be76f3-...`
  (`feminine-light`, `walking-6-frames`), `a78931c2-...` (`feminine-dark`),
  `0bfd96ab-...` (`masculine-light`), and `4f3cd1fd-...` (`masculine-dark`).
  NSC-074's template requests for those directions were deduplicated by
  PixelLab and generated nothing. The stored frames break continuity:
  `feminine-dark` north frames 003-005 lose the long hair, several east/west
  frames 004-005 switch to a trouser-leg walk, and `masculine-dark` south
  frame 002 changes the tunic and face.
- `feminine-light` south in-place re-roll `1b6e8b17-e421-4237-807d-8c3092994591`.
- `feminine-dark` south first take `03efc218-7794-494f-b657-87aeb78d5be3`.
- `masculine-dark` south in-place re-roll `2124a6f9-470f-4edd-8410-3f026b5f45c2`.

Complete group IDs and descriptions are recorded in the inventory.

### Unity `.meta` companions

Each new PNG, each of the 16 new direction folders, and
`Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardCardinalSourceAuditTests.cs`
has a deterministic `.meta` file in the repository's ExecutionCrew format
(`Pipeline/ExecutionCrew/run_crew.py` `unity_meta_bytes`): LF text with
`fileFormatVersion: 2` and a GUID derived from
`sha256("NoSafeCircle.ExecutionCrew.UnityMeta/v1\0" + casefolded path)[:32]`.
Folder `.meta` files also contain `folderAsset: yes`. The source-art task
writes no sprite import settings; NSC-075 owns import and Animator
integration.

Once Unity imports these PNGs, `WizardArtIntegrationTests.ApprovedSourceFramesHavePointUncompressedImportAndGroundPivot`
may count more than its expected 128 sprites under `Source/PixelLab`.
Reconciling that count belongs to NSC-075 integration.

### Validation still required

The source-art worker did not run Unity. The Windows orchestrator runs the
Edit Mode audit `WizardCardinalSourceAuditTests` on the exact committed
candidate (NSC-074 `VAL-001`). Vincent's exact-candidate approval of all four
variants walking north, east, south, and west (`VAL-002`) is also required
before NSC-075 integration.
