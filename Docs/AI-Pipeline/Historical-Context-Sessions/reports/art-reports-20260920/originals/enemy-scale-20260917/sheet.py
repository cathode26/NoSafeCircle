"""Are the enemies still the art we want, and do they sit with the wizard at one PPU?
Everything here is at 64 PPU x 1.0546875 (the 1080p screen factor), so sizes are what the camera shows."""
import colorsys, glob, json
from PIL import Image, ImageDraw, ImageFont

E = "C:/nscrev/reports/art-director/enemy-scale-20260917"
G = 67.5 / 64.0

PICKS = [
    ("wizard masculine-light", f"{E}/wiz/masculine-light_south.png", 121),
    ("melee idle S", f"{E}/png/enemy_melee_s_idle_00.png", None),
    ("melee walk S f0", f"{E}/png/enemy_melee_s_walk_00.png", None),
    ("melee walk S f3", f"{E}/png/enemy_melee_s_walk_03.png", None),
    ("ranged idle S", f"{E}/png/enemy_ranged_s_idle_00.png", None),
    ("ranged walk S f0", f"{E}/png/enemy_ranged_s_walk_00.png", None),
]


def font(sz, bold=False):
    for p in ([r"C:\Windows\Fonts\segoeuib.ttf"] if bold else []) + [r"C:\Windows\Fonts\segoeui.ttf"]:
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def bands(im):
    px = [c for c in im.getdata() if c[3] > 8]
    warm = violet = n = 0
    for r, g, b, _ in px:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s <= 0.15:
            continue
        n += 1
        d = h * 360
        if 15 <= d < 65:
            warm += 1
        elif 250 <= d < 300:
            violet += 1
    return (round(100 * warm / n, 1), round(100 * violet / n, 1), len({c for c in px})) if n else (0, 0, 0)


def main():
    rows = []
    for label, path, _ in PICKS:
        im = Image.open(path).convert("RGBA")
        a = im.getchannel("A").load()
        ys = [y for y in range(im.height) if any(a[x, y] > 8 for x in range(im.width))]
        g = ys[-1]
        crop = im.crop(im.getchannel("A").getbbox())
        rows.append((label, im, crop, g, bands(im)))
        w, v, c = bands(im)
        print(f"{label:24s} canvas {im.size} drawn {crop.size} ground {g} warm {w}% violet {v}% colours {c}")

    # gameplay scale, feet on one line
    pad, gap, head, foot = 18, 18, 58, 42
    ups = [(l, c.resize((round(c.width * G), round(c.height * G)), Image.NEAREST)) for l, _, c, _, _ in rows]
    row_h = max(i.height for _, i in ups)
    W = pad * 2 + sum(i.width + gap for _, i in ups)
    card = Image.new("RGBA", (W, pad * 2 + head + row_h + foot), (30, 28, 36, 255))
    d = ImageDraw.Draw(card)
    d.text((pad, pad), "Enemies and the merged 128 wizard at ONE pixels-per-unit (64), 1:1 screen pixels at 1080p",
           font=font(21, True), fill=(240, 238, 246, 255))
    d.text((pad, pad + 28), "Canvas padding removed: this is the drawn figure, which is what the camera shows. "
                            "The 176 canvas is padding, not scale.", font=font(15), fill=(178, 174, 192, 255))
    base = pad + head + row_h
    d.line([pad - 6, base + 1, W - pad + 6, base + 1], fill=(72, 68, 84, 255))
    x = pad
    for (label, im), (_, _, crop, _, _) in zip(ups, rows):
        card.alpha_composite(im, (x, base - im.height))
        d.text((x, base + 6), label, font=font(13), fill=(214, 210, 228, 255))
        d.text((x, base + 21), f"{crop.height}px = {crop.height/64:.2f}u", font=font(13), fill=(150, 146, 166, 255))
        x += im.width + gap
    card.save(f"{E}/enemy_vs_wizard_scale.png")
    print("wrote enemy_vs_wizard_scale.png", card.size)


main()
