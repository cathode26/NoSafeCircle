"""NSC-078 AC-003 review package: the five pilot props at native pixels, at 3x, and at gameplay scale
beside the committed 128 px wizard.

Scale: every prop canvas in plan section 4a was derived at 64 px per world unit, and the committed 128 px
wizard is a 2-unit camera-facing box, also 64 PPU. The gameplay camera gives 67.5 screen px per world unit at
1080p, so ONE factor applies to all of them: 67.5 / 64 = 1.0546875.
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

GAME = 67.5 / 64.0

FINALS = [
    ("shared_bone_pile_a", "round1-48/shared_bone_pile_a.png", "round 1, accepted"),
    ("ba_collapsed_reading_table_z", "round2-48/ba_collapsed_reading_table_z.png", "round 2 re-roll (lantern gone)"),
    ("ca_candelabra_tall", "round1-48/ca_candelabra_tall.png", "round 1, accepted"),
    ("re_broken_masonry_blocks", "round3-48/re_broken_masonry_blocks.png", "round 3 re-roll (cold slate rubble)"),
    ("lv_iron_rail_x", "round1-48/lv_iron_rail_x.png", "round 1, accepted"),
]
WIZARD = "round1/wizard_se_128.png"


def font(sz, bold=False):
    for p in ([r"C:\Windows\Fonts\segoeuib.ttf"] if bold else []) + [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]:
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def measure(im):
    a = im.getchannel("A")
    bbox = a.getbbox()
    px = list(im.convert("RGBA").get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.convert("RGBA").getdata())
    op = [c for c in px if c[3] > 8]
    return {
        "canvas": list(im.size),
        "bbox": list(bbox),
        "opaque_px": len(op),
        "fill_pct": round(100 * len(op) / (im.width * im.height), 1),
        "colours": len({c for c in op}),
    }


def sheet():
    scale = 3
    ims = [(n, Image.open(p).convert("RGBA"), note) for n, p, note in FINALS]
    pad, gap, head, foot = 18, 16, 56, 46
    cw = max(i.width for _, i, _ in ims) * scale
    ch = max(i.height for _, i, _ in ims) * scale
    f_t, f_s, f_c = font(21, True), font(15), font(13)
    card = Image.new("RGBA", (pad * 2 + cw * 5 + gap * 4, pad * 2 + head + ch + foot), (52, 48, 60, 255))
    d = ImageDraw.Draw(card)
    d.text((pad, pad), "NSC-078 style-lock pilot - the five props, 3x native pixels, 48-colour lock", font=f_t,
           fill=(240, 238, 246, 255))
    d.text((pad, pad + 28), "Final candidates after two re-rolls. These ids become the family style_image if you approve them.",
           font=f_s, fill=(178, 174, 192, 255))
    recs = {}
    for n, (name, im, note) in enumerate(ims):
        x = pad + n * (cw + gap)
        up = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        card.alpha_composite(up, (x + (cw - up.width) // 2, pad + head + (ch - up.height)))
        d.rectangle([x, pad + head, x + cw - 1, pad + head + ch - 1], outline=(96, 92, 108, 255))
        d.text((x + 2, pad + head + ch + 6), name, font=f_s, fill=(234, 232, 242, 255))
        d.text((x + 2, pad + head + ch + 24), note, font=f_c, fill=(168, 164, 184, 255))
        recs[name] = measure(im)
    card.save("ac003_props_3x.png")
    print("wrote ac003_props_3x.png", card.size)
    return recs


def gamescale():
    """1:1 screen pixels: what the player sees at 1080p, props and wizard on the same 1.0546875 factor."""
    wiz = Image.open(WIZARD).convert("RGBA")
    ims = [(n, Image.open(p).convert("RGBA")) for n, p, _ in FINALS]
    def up(im):
        return im.resize((round(im.width * GAME), round(im.height * GAME)), Image.NEAREST)
    wz = up(wiz)
    ups = [(n, up(i)) for n, i in ims]
    pad, gap, head, foot = 18, 14, 58, 40
    row_h = max([wz.height] + [i.height for _, i in ups])
    W = pad * 2 + wz.width + gap + sum(i.width + gap for _, i in ups)
    card = Image.new("RGBA", (W, pad * 2 + head + row_h + foot), (30, 28, 36, 255))
    d = ImageDraw.Draw(card)
    f_t, f_s, f_c = font(21, True), font(15), font(13)
    d.text((pad, pad), "NSC-078 AC-003 - gameplay scale, 1:1 screen pixels at 1080p", font=f_t, fill=(240, 238, 246, 255))
    d.text((pad, pad + 28), "Everything scaled 67.5/64 = 1.0546875x, the same factor the game applies to 64-PPU art. "
                            "Wizard first, for size.", font=f_s, fill=(178, 174, 192, 255))
    base = pad + head + row_h
    x = pad
    # floor line, so nothing looks like it is floating
    d.line([pad - 6, base + 1, W - pad + 6, base + 1], fill=(72, 68, 84, 255))
    card.alpha_composite(wz, (x, base - wz.height))
    d.text((x, base + 6), f"wizard 128 -> {wz.width}px", font=f_c, fill=(206, 202, 220, 255))
    x += wz.width + gap
    for name, im in ups:
        card.alpha_composite(im, (x, base - im.height))
        d.text((x, base + 6), f"{im.width}x{im.height}px", font=f_c, fill=(168, 164, 184, 255))
        d.text((x, base + 21), name.split("_", 1)[1][:22], font=f_c, fill=(134, 130, 150, 255))
        x += im.width + gap
    card.save("ac003_gamescale_1080p.png")
    print("wrote ac003_gamescale_1080p.png", card.size)


def main():
    recs = sheet()
    gamescale()
    json.dump({"screen_scale_1080p": GAME, "props": recs}, open("ac003_measurements.json", "w"), indent=2)
    print(json.dumps(recs, indent=2))


if __name__ == "__main__":
    main()
