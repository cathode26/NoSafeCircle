"""Scale check: what the game builder's wizard Visual setup does to the 180 px art.

Evidence only (review material, never source art):
- left: crop of the NSC-044 Unity camera review render (800x600, ortho size 8,
  wizard SpriteRenderer at localScale (1, 2, 1) with identity rotation, the same
  setup DoorPrototypeGlobalSceneBuilder.BuildPlayer gives the "Visual" child);
- middle: the same source sprite pushed through that projection at 1080p,
  computed from the camera basis (Euler 30, -45, 0);
- right: the source sprite drawn camera-facing and uniform, same on-screen height.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(r"C:\NSC\NSC\NoSafeCircle")
SOURCE = REPO / "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south-east.png"
RENDER = Path(r"C:\NSC\AssistantControlEvidence\nsc044-gameplay-camera-tint-20260914\d1-staging.png")
OUT = Path(__file__).resolve().parent.parent / "scale_check_current_visual.png"

PX_PER_UNIT_1080 = 1080 / 16.0  # orthographic size 8
CANVAS = 180
PPU = 180.0
SCALE_X, SCALE_Y = 1.0, 2.0  # CreateWorldSpriteVisual worldSize for the player
# Camera basis for Euler(30, -45, 0): right = (0.7071, 0, 0.7071), up = (-0.3536, 0.8660, 0.3536).
RIGHT = (math.sqrt(0.5), 0.0, math.sqrt(0.5))
UP = (-0.5 * math.sqrt(0.5), math.sqrt(3) / 2, 0.5 * math.sqrt(0.5))


def projected_affine(ppu_screen: float):
    """Screen px per source px for sprite local X (world X) and local Y (world Y)."""
    unit = ppu_screen / PPU
    ax = (RIGHT[0] * SCALE_X * unit, -UP[0] * SCALE_X * unit)  # (screen right, screen down)
    ay = (RIGHT[1] * SCALE_Y * unit, -UP[1] * SCALE_Y * unit)
    return ax, ay


def render_projected(sprite: Image.Image, ppu_screen: float) -> Image.Image:
    ax, ay = projected_affine(ppu_screen)
    # Forward map: screen = O + (u - 90) * ax + (180 - v) * (-ay)  (v measured down from the top)
    # Sprite local +Y is up; ay already holds screen-down per unit of local up (negative).
    width, height = 120, 140
    ox, oy = width / 2, height - 10
    # Build the inverse of [[ax0, -ay0], [ax1, -ay1]] mapping (du, dvUp) -> (sx, sy).
    m00, m01 = ax[0], ay[0]
    m10, m11 = ax[1], ay[1]
    det = m00 * m11 - m01 * m10
    i00, i01 = m11 / det, -m01 / det
    i10, i11 = -m10 / det, m00 / det
    # du = i00*sx + i01*sy ; dvUp = i10*sx + i11*sy ; u = 90 + du ; v = 180 - dvUp
    a, b = i00, i01
    c = 90 - i00 * ox - i01 * oy
    d, e = -i10, -i11
    f = 180 + i10 * ox + i11 * oy
    return sprite.transform((width, height), Image.AFFINE, (a, b, c, d, e, f), resample=Image.NEAREST)


def main() -> None:
    sprite = Image.open(SOURCE).convert("RGBA")
    background = (29, 22, 49, 255)

    render = Image.open(RENDER).convert("RGBA")
    render_crop = render.crop((370, 285, 430, 360))

    projected = render_projected(sprite, PX_PER_UNIT_1080)
    projected_bbox = projected.getchannel("A").getbbox()

    figure_height = 159 - 13  # south-east standing alpha bbox rows
    onscreen_height = projected_bbox[3] - projected_bbox[1]
    uniform_scale = onscreen_height / figure_height
    uniform = sprite.resize((round(CANVAS * uniform_scale), round(CANVAS * uniform_scale)), Image.NEAREST)

    zoom = 4
    panels = [
        ("Unity NSC-044 render, 800x600 (x6)", render_crop, 6),
        ("Builder setup at 1080p (x4)", projected, zoom),
        ("Camera-facing, same height (x4)", uniform, zoom),
    ]
    gap = 24
    label_height = 22
    sizes = [(image.width * z, image.height * z) for _, image, z in panels]
    sheet_width = sum(w for w, _ in sizes) + gap * (len(panels) + 1)
    sheet_height = max(h for _, h in sizes) + label_height + gap * 2
    sheet = Image.new("RGBA", (sheet_width, sheet_height), background)
    draw = ImageDraw.Draw(sheet)
    x = gap
    for (label, image, z), (w, h) in zip(panels, sizes):
        tile = Image.new("RGBA", image.size, background)
        tile.alpha_composite(image)
        sheet.paste(tile.resize((w, h), Image.NEAREST), (x, gap + label_height))
        draw.text((x, gap), label, fill=(220, 214, 230, 255))
        x += w + gap
    sheet.save(OUT)

    ax, ay = projected_affine(PX_PER_UNIT_1080)
    print("output", OUT)
    print("screen px per source px along sprite X:", [round(v, 4) for v in ax])
    print("screen px per source px along sprite Y (up):", [round(v, 4) for v in ay])
    print("projected wizard bbox at 1080p:", projected_bbox,
          "size", (projected_bbox[2] - projected_bbox[0], projected_bbox[3] - projected_bbox[1]))


if __name__ == "__main__":
    main()
