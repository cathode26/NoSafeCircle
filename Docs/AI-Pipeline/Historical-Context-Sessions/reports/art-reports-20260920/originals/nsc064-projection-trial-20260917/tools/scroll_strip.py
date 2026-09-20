"""The scrolling strip: floor AND walls under both projection models, at the real camera speed.

Usage: python scroll_strip.py <kit_dir> <out_dir> [floor_px]

Model (b), the chosen direction: the isometric kit's own pieces are blitted in the camera plane, whole pixels.
Model (a), today's pipeline: the same material authored **unprojected** - a square floor tile and a flat wall
elevation - laid on world planes and sampled by the camera, which is what a Point-filter texture does.

The (a) floor is a procedural flagstone built from the kit's own palette, because authoring the real
`square_topdown` kit would cost another generation and the point of the panel is the projection, not the drawing.
That is stated on the image itself so nobody mistakes it for kit art.

Camera: orthographic, Euler(30, -45, 0), 67.5 screen px per world unit at 1080p. The README's measured gameplay
speed is 4 world units per second, which is 170.76 screen px per second, or 2.0125 px per frame at 60 fps.
"""
import os
import sys

from PIL import Image, ImageDraw

S = 67.5
K = 0.7071067811865476
H = 0.3535533905932738
TEX = 64
SPEED_PX = 2.0125          # screen px per frame along the walk direction at 4 units/s, 60 fps
FRAMES = 20
CELLS = 9


def kit_piece(kit_dir, index):
    for f in os.listdir(kit_dir):
        if f.endswith(f"_{index}.png"):
            return Image.open(os.path.join(kit_dir, f)).convert("RGBA")
    raise FileNotFoundError(f"piece {index} not in {kit_dir}")


def palette_of(img, n=8):
    px = [p for p in img.getdata() if p[3] > 0]
    counts = {}
    for p in px:
        counts[p] = counts.get(p, 0) + 1
    return [p for p, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:n]]


def square_floor(pal, n=TEX):
    """A square, unprojected flagstone tile in the kit's palette: what (a) would use."""
    base, dark, light = pal[0], pal[min(1, len(pal) - 1)], pal[min(2, len(pal) - 1)]
    img = Image.new("RGBA", (n, n), base)
    px = img.load()
    for y in range(n):
        for x in range(n):
            if x % 32 == 0 or y % 32 == 0:
                px[x, y] = dark
            elif (x * 7 + y * 13) % 31 == 0:
                px[x, y] = light
    return img


def flat_wall(pal, w=TEX, h=160):
    """A flat wall elevation in the kit's palette: what (a) would use on the vertical plane."""
    base, dark, light = pal[0], pal[min(1, len(pal) - 1)], pal[min(2, len(pal) - 1)]
    img = Image.new("RGBA", (w, h), base)
    px = img.load()
    for y in range(h):
        for x in range(w):
            row = y // 20
            off = 0 if row % 2 == 0 else 16
            if (x + off) % 32 == 0 or y % 20 == 0:
                px[x, y] = dark
            elif (x * 5 + y * 11) % 37 == 0:
                px[x, y] = light
    return img


def render_a(floor_tex, wall_tex, size, cam):
    """Sample world-plane surfaces per screen pixel: floor on XZ, wall on the vertical plane at z = 0."""
    w, h = size
    out = Image.new("RGBA", (w, h), (20, 19, 24, 255))
    fpx, wpx, opx = floor_tex.load(), wall_tex.load(), out.load()
    wh = wall_tex.size[1] / TEX          # wall height in world units
    ox, oy = w * 0.5 - cam[0], h * 0.62 - cam[1]
    for py in range(h):
        for px_ in range(w):
            sx = (px_ - ox) / S
            sy = (oy - py) / S
            # wall first: the vertical plane z = 0, spanning x in [0, CELLS], y in [0, wh]
            # screen = (K*(x+z), H*(z-x) + 0.866*y) with z = 0 -> x = sx/K, y = (sy + H*x)/0.866
            x_w = sx / K
            y_w = (sy + H * x_w) / 0.8660254037844387
            if 0 <= x_w < CELLS and 0 <= y_w < wh:
                u = int((x_w % 1.0) * TEX) % TEX
                v = wall_tex.size[1] - 1 - int(y_w * TEX) % wall_tex.size[1]
                opx[px_, py] = wpx[u, v]
                continue
            x = (sx / K - sy / H) / 2.0
            z = (sx / K + sy / H) / 2.0
            if 0 <= x < CELLS and 0 <= z < CELLS:
                opx[px_, py] = fpx[int((x % 1.0) * TEX) % TEX, int((z % 1.0) * TEX) % TEX]
    return out


def render_b(floor, wall, size, cam, cw, ch):
    """Blit the kit's own pieces in the camera plane, snapped to whole pixels."""
    w, h = size
    out = Image.new("RGBA", (w, h), (20, 19, 24, 255))
    ox, oy = w * 0.5 - round(cam[0]), h * 0.62 - round(cam[1])
    order = sorted(((cx, cz) for cx in range(CELLS) for cz in range(CELLS)), key=lambda c: c[0] + c[1])
    for cx, cz in order:
        px_ = int(ox + (cx + cz) * cw / 2 - cw / 2)
        py = int(oy - (cz - cx) * ch / 2 - ch / 2)
        out.alpha_composite(floor, (px_, py))
    for cx in range(CELLS):          # one wall run along z = 0
        px_ = int(ox + cx * cw / 2 - cw / 2)
        py = int(oy + cx * ch / 2 - ch / 2)
        out.alpha_composite(wall, (px_, py - wall.size[1] + ch))
    return out


def main():
    kit_dir, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    floor_piece = kit_piece(kit_dir, 0)
    wall_piece = kit_piece(kit_dir, 1)
    bb = floor_piece.getchannel("A").getbbox()
    floor = floor_piece.crop(bb)
    cw, ch = floor.size[0], floor.size[1] - 1      # drop the 1 px bottom tip row
    floor = floor.crop((0, 0, cw, ch))
    wbb = wall_piece.getchannel("A").getbbox()
    wall = wall_piece.crop(wbb)
    pal = palette_of(floor_piece, 8)
    ftex, wtex = square_floor(pal), flat_wall(pal)
    size = (560, 300)

    frames_a, frames_b = [], []
    for i in range(FRAMES):
        d = i * SPEED_PX
        cam = (d * K, -d * H)        # walking south-east along the ground, in screen px
        frames_a.append(render_a(ftex, wtex, size, cam))
        frames_b.append(render_b(floor, wall, size, cam, cw, ch))
        print(f"  frame {i + 1}/{FRAMES}")

    lab = 18
    gifs = []
    for name, frames, note in (("a", frames_a, "(a) today: unprojected art on world planes, camera samples it"),
                               ("b", frames_b, "(b) chosen: the kit's own pieces in the camera plane")):
        out_frames = []
        for f in frames:
            sheet = Image.new("RGBA", (size[0], size[1] + lab), (16, 15, 19, 255))
            dr = ImageDraw.Draw(sheet)
            dr.text((6, 4), note, fill=(235, 235, 240, 255))
            sheet.alpha_composite(f, (0, lab))
            out_frames.append(sheet.convert("P", palette=Image.ADAPTIVE, colors=255))
        p = os.path.join(out, f"scroll_{name}.gif")
        out_frames[0].save(p, save_all=True, append_images=out_frames[1:], duration=33, loop=0, disposal=2)
        gifs.append(p)
        print("wrote", p, os.path.getsize(p) // 1024, "KB")

    # one side-by-side gif
    out_frames = []
    for fa, fb in zip(frames_a, frames_b):
        sheet = Image.new("RGBA", (size[0] * 2 + 8, size[1] + lab), (16, 15, 19, 255))
        dr = ImageDraw.Draw(sheet)
        dr.text((6, 4), "(a) today: world-plane surfaces, camera resamples them", fill=(240, 200, 200, 255))
        dr.text((6, size[1] + lab - 12), "art here is a PROCEDURAL stand-in in the kit's palette - judge the projection, not the drawing",
                fill=(210, 190, 190, 255))
        dr.text((size[0] + 14, 4), "(b) chosen: the kit's own painted pieces, camera plane", fill=(200, 240, 210, 255))
        dr.text((size[0] + 14, size[1] + lab - 12), "real kit art, whole pixels", fill=(190, 210, 195, 255))
        sheet.alpha_composite(fa, (0, lab))
        sheet.alpha_composite(fb, (size[0] + 8, lab))
        out_frames.append(sheet.convert("P", palette=Image.ADAPTIVE, colors=255))
    p = os.path.join(out, "scroll_compare.gif")
    out_frames[0].save(p, save_all=True, append_images=out_frames[1:], duration=33, loop=0, disposal=2)
    print("wrote", p, os.path.getsize(p) // 1024, "KB")
    print(f"floor cell used for (b): {cw} x {ch} px")


main()
