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
