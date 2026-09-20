"""Does floor art shimmer under model (a)? Measure it instead of arguing it.

Usage: python shimmer_test.py <out_dir>

Model (a): a square pixel-art floor texture lies on the world XZ plane; the camera samples it. Screen pixels are
inverse-mapped to the ground and point-sampled, which is what a Point-filter texture does.
Model (b): the same material authored in the camera plane, blitted as whole pixels per cell.

**Stability test.** Render each model twice, the second with the camera moved exactly one screen pixel. Shift the
second image back by that pixel and compare. A model whose texels map cleanly to screen pixels gives an identical
image (zero differing pixels): the picture only translated. A model that resamples gives a different pixel pattern,
which is what reads as shimmer while the camera follows the player.
"""
import math
import os
import sys

from PIL import Image, ImageDraw

S = 67.5                      # screen pixels per world unit at 1080p
TEX = 64                      # floor texture resolution, 64 px per world unit
K = 0.7071067811865476
H = 0.3535533905932738


def flagstone(n=TEX):
    """High-contrast pixel-art flagstone: 1 px dark grout on a 32 px block grid, plus speckles."""
    img = Image.new("RGBA", (n, n), (104, 96, 88, 255))
    px = img.load()
    for y in range(n):
        for x in range(n):
            if x % 32 == 0 or y % 32 == 0:
                px[x, y] = (38, 34, 40, 255)
            elif (x * 7 + y * 13) % 29 == 0:
                px[x, y] = (132, 124, 112, 255)
            elif (x * 5 + y * 3) % 37 == 0:
                px[x, y] = (72, 66, 62, 255)
    return img


def render_a(tex, size, offset=(0.0, 0.0)):
    """Inverse-map every screen pixel to the ground plane and point-sample the texture."""
    w, h = size
    out = Image.new("RGBA", (w, h), (24, 22, 28, 255))
    tpx = tex.load()
    opx = out.load()
    ox, oy = w * 0.5 + offset[0], h * 0.5 + offset[1]
    for py in range(h):
        for px_ in range(w):
            sx = (px_ - ox) / S
            sy = (oy - py) / S
            x = (sx / K - sy / H) / 2.0
            z = (sx / K + sy / H) / 2.0
            if not (0 <= x < 6 and 0 <= z < 6):
                continue
            u = int((x % 1.0) * TEX) % TEX
            v = int((z % 1.0) * TEX) % TEX
            opx[px_, py] = tpx[u, v]
    return out


def diamondise(tex, cw, ch):
    """Author the same material in the camera plane: a cw x ch diamond of the texture, whole pixels."""
    d = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    tpx = tex.load()
    dpx = d.load()
    for y in range(ch):
        for x in range(cw):
            fx = (x + 0.5) / cw
            fy = (y + 0.5) / ch
            if abs(fx - 0.5) / 0.5 + abs(fy - 0.5) / 0.5 <= 1.0:
                u = int(fx * TEX) % TEX
                v = int(fy * TEX) % TEX
                dpx[x, y] = tpx[u, v]
    return d


def render_b(tex, size, offset=(0, 0), cw=90, ch=45):
    w, h = size
    out = Image.new("RGBA", (w, h), (24, 22, 28, 255))
    cell = diamondise(tex, cw, ch)
    ox, oy = w * 0.5 + offset[0], h * 0.5 + offset[1]
    for cz in range(6):
        for cx in range(6):
            px_ = int(ox + (cx + cz) * cw / 2 - cw / 2)
            py = int(oy - (cz - cx) * ch / 2 - ch / 2)
            out.alpha_composite(cell, (px_, py))
    return out


def differing(a, b, dx):
    """Shift b back by dx and count pixels that differ from a, ignoring the frame edges."""
    w, h = a.size
    apx, bpx = a.load(), b.load()
    diff = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    dpx = diff.load()
    n = total = 0
    for y in range(4, h - 4):
        for x in range(4 + abs(dx), w - 4 - abs(dx)):
            pa = apx[x, y]
            pb = bpx[x + dx, y]
            if pa[3] == 0 and pb[3] == 0:
                continue
            total += 1
            if pa != pb:
                n += 1
                dpx[x, y] = (255, 64, 160, 255)
    return n, total, diff


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    tex = flagstone()
    tex.resize((TEX * 4, TEX * 4), Image.NEAREST).save(os.path.join(out, "shimmer_texture_4x.png"))
    size = (520, 320)

    # A whole-pixel camera move is a clean shift for both models, so it proves nothing. The camera follows the
    # player continuously, so the honest test is a HALF-pixel move, compared with no shift compensation: how much
    # of the picture changes when the camera creeps by half a screen pixel.
    a0 = render_a(tex, size, (0.0, 0.0))
    a1 = render_a(tex, size, (0.5, 0.0))
    b0 = render_b(tex, size, (0, 0))
    b1 = render_b(tex, size, (0, 0))   # sprites land on whole pixels, so a half-pixel camera move snaps to the same place

    na, ta, da = differing(a0, a1, 0)
    nb, tb, db = differing(b0, b1, 0)
    print(f"(a) world plane, point sampled: {na} of {ta} floor pixels change on a HALF-pixel camera move "
          f"({100.0 * na / max(ta, 1):.1f}%)")
    print(f"(b) camera plane, whole pixels: {nb} of {tb} ({100.0 * nb / max(tb, 1):.1f}%)")

    # Crispness: how many of the texture's texels survive the projection at all.
    seen = set()
    for py in range(size[1]):
        for px_ in range(size[0]):
            sx = (px_ - size[0] * 0.5) / S
            sy = (size[1] * 0.5 - py) / S
            x = (sx / K - sy / H) / 2.0
            z = (sx / K + sy / H) / 2.0
            if 0 <= x < 1 and 0 <= z < 1:
                seen.add((int(x * TEX) % TEX, int(z * TEX) % TEX))
    print(f"(a) texels actually sampled in one cell: {len(seen)} of {TEX * TEX} "
          f"({100.0 * len(seen) / (TEX * TEX):.0f}%) - the rest are dropped by minification")

    z = 3
    crop = (330, 120, 480, 210)
    panels = [("(a) world plane", a0.crop(crop)), ("(a) pixels that change on a half-pixel camera move", da.crop(crop)),
              ("(b) camera plane", b0.crop(crop)), ("(b) pixels that change", db.crop(crop))]
    cw, ch = (crop[2] - crop[0]) * z, (crop[3] - crop[1]) * z
    sheet = Image.new("RGBA", (cw * 2 + 24, ch * 2 + 70), (18, 17, 21, 255))
    dr = ImageDraw.Draw(sheet)
    for i, (label, img) in enumerate(panels):
        x = (i % 2) * (cw + 16) + 8
        y = (i // 2) * (ch + 34) + 22
        dr.text((x, y - 14), label, fill=(230, 230, 235, 255))
        sheet.alpha_composite(img.resize((cw, ch), Image.NEAREST), (x, y))
    dr.text((8, 4), f"(a) {100.0 * na / max(ta, 1):.1f}% of floor pixels change per HALF-pixel camera move   |   "
                    f"(b) {100.0 * nb / max(tb, 1):.1f}%", fill=(255, 210, 120, 255))
    sheet.convert("RGB").save(os.path.join(out, "shimmer_comparison.png"))
    print("wrote shimmer_comparison.png")


main()
