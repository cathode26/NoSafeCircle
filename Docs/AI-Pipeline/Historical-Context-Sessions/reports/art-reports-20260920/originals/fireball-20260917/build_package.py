"""Fireball review package: the three loops as strips and GIFs from the 48-colour-locked frames, plus a
gameplay-scale panel that puts the charged ball at the wizard's hand at 1:1 screen pixels."""
import glob, os
from PIL import Image, ImageDraw, ImageFont

O = "C:/nscrev/reports/art-director/fireball-20260917"
F = f"{O}/final48"
WIZ = "C:/nscrev/reports/art-director/enemy-scale-20260917/wiz/masculine-light_south.png"
G = 67.5 / 64.0


def font(sz, bold=False):
    for p in ([r"C:\Windows\Fonts\segoeuib.ttf"] if bold else []) + [r"C:\Windows\Fonts\segoeui.ttf"]:
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def load(names):
    return [Image.open(f"{F}/{n}.png").convert("RGBA") for n in names]


def strip(ims, title, out, scale=4):
    pad, gap, head, foot = 14, 8, 36, 22
    cw, ch = max(i.width for i in ims) * scale, max(i.height for i in ims) * scale
    card = Image.new("RGBA", (pad * 2 + cw * len(ims) + gap * (len(ims) - 1), pad * 2 + head + ch + foot),
                     (46, 42, 54, 255))
    d = ImageDraw.Draw(card)
    d.text((pad, pad), title, font=font(18, True), fill=(240, 238, 246, 255))
    for n, im in enumerate(ims):
        x = pad + n * (cw + gap)
        card.alpha_composite(im.resize((cw, ch), Image.NEAREST), (x, pad + head))
        d.rectangle([x, pad + head, x + cw - 1, pad + head + ch - 1], outline=(92, 88, 104, 255))
        d.text((x + 2, pad + head + ch + 3), str(n), font=font(12), fill=(170, 166, 186, 255))
    card.save(out)


def gif(ims, out, ms=110, scale=4):
    ups = [i.resize((i.width * scale, i.height * scale), Image.NEAREST) for i in ims]
    bg = Image.new("RGBA", ups[0].size, (46, 42, 54, 255))
    flat = [Image.alpha_composite(bg, u).convert("P", palette=Image.ADAPTIVE) for u in ups]
    flat[0].save(out, save_all=True, append_images=flat[1:], duration=ms, loop=0, disposal=2)


def main():
    proj = load([f"projectile_{i}" for i in range(4)])
    hold = load([f"hold_{i}" for i in range(6)])
    gather = load([f"gather_{i}" for i in range(6)])
    strip(proj, "projectile_loop - 4 frames, 48-colour lock, 4x native", f"{O}/projectile_loop_4x.png")
    strip(hold, "charge_hold_loop - 6 frames (charged, held until release), 4x native", f"{O}/charge_hold_4x.png")
    strip(gather, "charge_gather_loop - 6 frames (charging, any duration), 4x native", f"{O}/charge_gather_4x.png")
    gif(proj, f"{O}/projectile_loop.gif", 100)
    gif(hold, f"{O}/charge_hold.gif", 110)
    gif(gather, f"{O}/charge_gather.gif", 110)

    # gameplay scale: wizard with the gathering ember, then the charged ball, then the projectile
    wiz = Image.open(WIZ).convert("RGBA")
    def up(im):
        return im.resize((round(im.width * G), round(im.height * G)), Image.NEAREST)
    pieces = [("charging", gather[3]), ("charged", hold[1]), ("in flight", proj[1])]
    wz = up(wiz)
    pad, gap, head, foot = 18, 40, 58, 40
    cellw = wz.width + 60
    card = Image.new("RGBA", (max(pad * 2 + cellw * 3 + gap * 2, 620), pad * 2 + head + wz.height + foot), (28, 26, 34, 255))
    d = ImageDraw.Draw(card)
    d.text((pad, pad), "Fireball at gameplay scale - 1:1 screen pixels, 1080p",
           font=font(21, True), fill=(240, 238, 246, 255))
    d.text((pad, pad + 28), "The ball is 0.75 world units (48 px) against the wizard's 1.64. Hand position is "
                            "indicative, not final.", font=font(15), fill=(178, 174, 192, 255))
    base = pad + head + wz.height
    d.line([pad - 6, base + 1, card.width - pad + 6, base + 1], fill=(70, 66, 82, 255))
    for n, (label, fx) in enumerate(pieces):
        x = pad + n * (cellw + gap)
        card.alpha_composite(wz, (x, base - wz.height))
        f = up(fx)
        # right hand, roughly two thirds up the body and just outside the silhouette
        card.alpha_composite(f, (x + wz.width - 14, base - int(wz.height * 0.62) - f.height // 2))
        d.text((x, base + 6), label, font=font(15), fill=(226, 222, 238, 255))
    card.save(f"{O}/fireball_gamescale_1080p.png")
    print("wrote strips, gifs and fireball_gamescale_1080p.png")


main()
