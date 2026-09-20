"""Vincent's pick panel for the broken-masonry re-rolls: three attempts at 3x native pixels with labels."""
from PIL import Image, ImageDraw, ImageFont

SETS = [
    ("1. first attempt", "arch still standing", "round1-48/re_broken_masonry_blocks.png"),
    ("2. first re-roll", "rubble, but warm stone", "round2-48/re_broken_masonry_blocks.png"),
    ("3. second re-roll", "rubble, cold violet slate", "round3-48/re_broken_masonry_blocks.png"),
]


def font(sz):
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    scale = 3
    ims = [Image.open(p).convert("RGBA") for _, _, p in SETS]
    cw = max(i.width for i in ims) * scale
    ch = max(i.height for i in ims) * scale
    gap, pad, head, foot = 16, 18, 52, 30
    f_title, f_sub, f_cap = font(20), font(15), font(14)
    card = Image.new("RGBA", (pad * 2 + cw * 3 + gap * 2, pad * 2 + head + ch + foot), (52, 48, 60, 255))
    d = ImageDraw.Draw(card)
    d.text((pad, pad), "NSC-078 pilot - re_broken_masonry_blocks, three attempts (3x native pixels, 48-colour lock)",
           font=f_title, fill=(238, 236, 244, 255))
    d.text((pad, pad + 26), "Same prompt spec, same 124x112 canvas. Pick one and it becomes the palette lock for the kit.",
           font=f_sub, fill=(176, 172, 190, 255))
    for n, (title, sub, _) in enumerate(SETS):
        x = pad + n * (cw + gap)
        up = ims[n].resize((ims[n].width * scale, ims[n].height * scale), Image.NEAREST)
        card.alpha_composite(up, (x + (cw - up.width) // 2, pad + head))
        d.rectangle([x, pad + head, x + cw - 1, pad + head + ch - 1], outline=(96, 92, 108, 255))
        d.text((x + 2, pad + head + ch + 5), title, font=f_sub, fill=(232, 230, 240, 255))
        d.text((x + 2, pad + head + ch + 22), sub, font=f_cap, fill=(168, 164, 184, 255))
    card.save("masonry_pick_3x.png")
    print("wrote masonry_pick_3x.png", card.size)


if __name__ == "__main__":
    main()
