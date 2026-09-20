"""Contact sheet + GIF for the fireball pieces, at 4x native and at gameplay scale beside the wizard."""
import glob, os
from PIL import Image, ImageDraw, ImageFont

R = "C:/nscrev/reports/art-director/fireball-20260917/raw"
O = "C:/nscrev/reports/art-director/fireball-20260917"
WIZ = "C:/nscrev/reports/art-director/enemy-scale-20260917/wiz/masculine-light_south.png"
G = 67.5 / 64.0


def font(sz, bold=False):
    for p in ([r"C:\Windows\Fonts\segoeuib.ttf"] if bold else []) + [r"C:\Windows\Fonts\segoeui.ttf"]:
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def frames(pattern):
    return [Image.open(p).convert("RGBA") for p in sorted(glob.glob(pattern))]


def strip(ims, label, scale=4):
    """one row of frames at `scale`x on a card"""
    pad, gap, head, foot = 14, 8, 34, 24
    cw = max(i.width for i in ims) * scale
    ch = max(i.height for i in ims) * scale
    card = Image.new("RGBA", (pad * 2 + cw * len(ims) + gap * (len(ims) - 1), pad * 2 + head + ch + foot),
                     (46, 42, 54, 255))
    d = ImageDraw.Draw(card)
    d.text((pad, pad), label, font=font(18, True), fill=(240, 238, 246, 255))
    for n, im in enumerate(ims):
        x = pad + n * (cw + gap)
        up = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        card.alpha_composite(up, (x, pad + head))
        d.rectangle([x, pad + head, x + cw - 1, pad + head + ch - 1], outline=(92, 88, 104, 255))
        d.text((x + 2, pad + head + ch + 4), f"{n}", font=font(13), fill=(170, 166, 186, 255))
    return card


def gif(ims, path, ms=110, scale=4):
    ups = [i.resize((i.width * scale, i.height * scale), Image.NEAREST) for i in ims]
    bg = [Image.new("RGBA", u.size, (46, 42, 54, 255)) for u in ups]
    flat = [Image.alpha_composite(b, u).convert("P", palette=Image.ADAPTIVE) for b, u in zip(bg, ups)]
    flat[0].save(path, save_all=True, append_images=flat[1:], duration=ms, loop=0, disposal=2)


def main():
    proj = frames(f"{R}/core_archive/animations/*flight*/unknown/frame_*.png")
    print("projectile frames:", len(proj))
    strip(proj, "projectile_loop - 4 frames, 4x native (48x48, 0.75 world units)").save(f"{O}/projectile_loop_4x.png")
    gif(proj, f"{O}/projectile_loop.gif", ms=100)
    print("wrote projectile_loop_4x.png and .gif")


main()
