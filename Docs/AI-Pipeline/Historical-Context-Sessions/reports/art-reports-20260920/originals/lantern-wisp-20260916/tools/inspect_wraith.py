"""Locate the Lantern Wraith's glow pixels (teal lantern, bone-white hood interior).

Read-only on the repository sprite. Writes an 8x zoom with a 8 px grid to the job
folder so mask rectangles can be chosen by eye, and prints glow-pixel bounds.
"""
import colorsys
from pathlib import Path

from PIL import Image, ImageDraw

SOURCE = Path(r"C:\NSC\NSC\NoSafeCircle\Assets\NoSafeCircle\DoorPrototype\Art\Enemies\Source\enemy_ranged_se_idle_00.png")
OUT_DIR = Path(__file__).resolve().parent.parent / "inspect"


def bounds(points):
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.open(SOURCE).convert("RGBA")
    width, height = image.size
    teal, bright_teal, bone = [], [], []
    colors = {}
    for y in range(height):
        for x in range(width):
            r, g, b, a = image.getpixel((x, y))
            if a == 0:
                continue
            colors[(r, g, b)] = colors.get((r, g, b), 0) + 1
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if 0.42 <= h <= 0.55 and s >= 0.35 and v >= 0.45:
                teal.append((x, y))
                if v >= 0.8:
                    bright_teal.append((x, y))
            if s <= 0.25 and v >= 0.72:
                bone.append((x, y))
    print("size", image.size)
    print("teal pixels", len(teal), "bounds", bounds(teal))
    print("bright teal pixels", len(bright_teal), "bounds", bounds(bright_teal))
    print("bone/pale pixels", len(bone), "bounds", bounds(bone))
    print("distinct colors", len(colors))
    top = sorted(colors.items(), key=lambda item: -item[1])[:40]
    print("top colors:", ", ".join("#%02x%02x%02x x%d" % (c[0], c[1], c[2], n) for c, n in top))

    zoom = 8
    big = Image.new("RGBA", (width * zoom, height * zoom), (40, 40, 48, 255))
    big.alpha_composite(image.resize((width * zoom, height * zoom), Image.NEAREST))
    draw = ImageDraw.Draw(big)
    for i in range(0, width + 1, 8):
        draw.line([(i * zoom, 0), (i * zoom, height * zoom)], fill=(90, 90, 110, 255), width=1)
        draw.line([(0, i * zoom), (width * zoom, i * zoom)], fill=(90, 90, 110, 255), width=1)
        draw.text((i * zoom + 2, 2), str(i), fill=(255, 255, 0, 255))
        draw.text((2, i * zoom + 2), str(i), fill=(255, 255, 0, 255))
    big.save(OUT_DIR / "wraith_se_idle_8x_grid.png")


if __name__ == "__main__":
    main()
