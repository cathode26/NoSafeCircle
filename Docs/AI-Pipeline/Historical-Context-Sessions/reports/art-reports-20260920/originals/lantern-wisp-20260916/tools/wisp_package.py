"""Lantern Wraith attack review package: local Pillow rendering only.

No PixelLab calls. No pixel editing of source sprites: only placement,
nearest-neighbour scaling for display, and compositing onto a background.
Reads only from the checkout (read-only) and this job's pixellab/ folder
(never modified). Writes only under this job's folder root.
"""

import math
import os
from PIL import Image, ImageDraw, ImageFont

JOB = r"C:\nscrev\reports\art-director\lantern-wisp-20260916"
PIXELLAB = os.path.join(JOB, "pixellab")
OUT = JOB
INSPECT = os.path.join(JOB, "inspect")

CHECKOUT = r"C:\NSC\NSC\NoSafeCircle"
WRAITH_IDLE_PATH = os.path.join(
    CHECKOUT, "Assets", "NoSafeCircle", "DoorPrototype", "Art", "Enemies",
    "Source", "enemy_ranged_se_idle_00.png")
WIZARD_PATH = os.path.join(
    CHECKOUT, "Assets", "NoSafeCircle", "DoorPrototype", "Art", "Wizard",
    "Source", "PixelLab", "masculine-light", "selected", "standing",
    "south-east.png")

WINDUP_PATH = os.path.join(PIXELLAB, "windup_se_128.png")
STILL_PATHS = {
    "A": os.path.join(PIXELLAB, "wisp_A2_still.png"),
    "B": os.path.join(PIXELLAB, "wisp_B2_still.png"),
    "C": os.path.join(PIXELLAB, "wisp_C2_still.png"),
}
HIT_SHARED_DIR = os.path.join(PIXELLAB, "hit_C2")
HIT_B_OWN_DIR = os.path.join(PIXELLAB, "hit_B2")

LABELS = {
    "A": "A: grumpy ghost-flame",
    "B": "B: grumpy skull-comet",
    "C": "C: ghost-flame, no face",
}

BG_RGB = (0x1d, 0x16, 0x31)
BG_RGBA = (0x1d, 0x16, 0x31, 255)
GRID_RGB = (0x2a, 0x23, 0x42)
TEXT_RGB = (225, 222, 235)
CAPTION_RGB = (190, 186, 205)

# Game-scale model (1080p, 67.5 px per world unit, camera-facing sprites).
S_WRAITH = 1.0546875
S_WIZARD = 0.75
S_WISP = 1.0546875
PIVOT_WRAITH_LOCAL = (64, 128)   # bottom-center of 128x128
PIVOT_WIZARD_LOCAL = (90, 180)   # bottom-center of 180x180
PIVOT_WISP_LOCAL = (16, 16)      # center of 32x32

FONT_PATH = r"C:\Windows\Fonts\arial.ttf"
FONT_BOLD_PATH = r"C:\Windows\Fonts\arialbd.ttf"


def load_fonts():
    try:
        header = ImageFont.truetype(FONT_BOLD_PATH, 18)
        label = ImageFont.truetype(FONT_BOLD_PATH, 15)
        caption = ImageFont.truetype(FONT_PATH, 13)
        footer = ImageFont.truetype(FONT_PATH, 13)
    except Exception:
        header = ImageFont.load_default(size=18)
        label = ImageFont.load_default(size=15)
        caption = ImageFont.load_default(size=13)
        footer = ImageFont.load_default(size=13)
    return header, label, caption, footer


FONT_HEADER, FONT_LABEL, FONT_CAPTION, FONT_FOOTER = load_fonts()


def load_rgba(path):
    im = Image.open(path)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    return im


def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# ---------------------------------------------------------------------------
# Game-scale nearest-neighbour compositing, per the spec's exact formula:
#   left = px - s*pivot_local_x ; top = py - s*pivot_local_y
#   tex_x = floor((X+0.5-left)/s) ; tex_y = floor((Y+0.5-top)/s)
#   composite straight alpha "over" the background.
# ---------------------------------------------------------------------------

def composite_sprite(canvas, sprite, pivot_local, target_xy, scale):
    cw, ch = canvas.size
    sw, sh = sprite.size
    spx = sprite.load()
    cpx = canvas.load()
    canvas_has_alpha = canvas.mode == "RGBA"

    pxp, pyp = pivot_local
    tx, ty = target_xy
    left = tx - scale * pxp
    top = ty - scale * pyp
    out_w = sw * scale
    out_h = sh * scale

    x0 = max(0, int(math.floor(left)))
    x1 = min(cw, int(math.ceil(left + out_w)))
    y0 = max(0, int(math.floor(top)))
    y1 = min(ch, int(math.ceil(top + out_h)))

    for Y in range(y0, y1):
        tex_y = int(math.floor((Y + 0.5 - top) / scale))
        if tex_y < 0 or tex_y >= sh:
            continue
        for X in range(x0, x1):
            tex_x = int(math.floor((X + 0.5 - left) / scale))
            if tex_x < 0 or tex_x >= sw:
                continue
            r, g, b, a = spx[tex_x, tex_y]
            if a == 0:
                continue
            if a == 255:
                cpx[X, Y] = (r, g, b, 255) if canvas_has_alpha else (r, g, b)
            else:
                existing = cpx[X, Y]
                cr, cg, cb = existing[0], existing[1], existing[2]
                af = a / 255.0
                nr = int(round(r * af + cr * (1 - af)))
                ng = int(round(g * af + cg * (1 - af)))
                nb = int(round(b * af + cb * (1 - af)))
                cpx[X, Y] = (nr, ng, nb, 255) if canvas_has_alpha else (nr, ng, nb)
    return canvas


def lerp(p0, p1, t):
    return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)


# ---------------------------------------------------------------------------
# Output 1: wisp_sheet_4x.png
# ---------------------------------------------------------------------------

def build_sheet(wraith_idle, windup, stills, hit_shared, hit_b_own):
    ZOOM = 4
    CELL_H = 512
    CAP_H = 22
    GAP = 8
    ROW_LABEL_H = 24
    ROW_GAP = 18
    MARGIN = 24

    def cell(sprite, caption):
        disp = sprite.width * ZOOM
        img = Image.new("RGBA", (disp, CELL_H + CAP_H), BG_RGBA)
        zoomed = sprite.resize((sprite.width * ZOOM, sprite.height * ZOOM), Image.NEAREST)
        x = (disp - zoomed.width) // 2
        y = (CELL_H - zoomed.height) // 2
        img.alpha_composite(zoomed, (x, y))
        d = ImageDraw.Draw(img)
        tw, th = text_size(d, caption, FONT_CAPTION)
        d.text(((disp - tw) // 2, CELL_H + 3), caption, font=FONT_CAPTION, fill=CAPTION_RGB)
        return img

    rows_cells = {}
    for key in ("A", "B", "C"):
        cells = [
            cell(wraith_idle, "wraith idle"),
            cell(windup, "wind-up"),
            cell(stills[key], "wisp still"),
        ]
        for i in range(4):
            cells.append(cell(hit_shared[i], f"hit {i+1}"))
        if key == "B":
            for i in range(4):
                cells.append(cell(hit_b_own[i], f"B's own hit {i+1}"))
        rows_cells[key] = cells

    row_imgs = []
    max_row_w = 0
    for key in ("A", "B", "C"):
        cells = rows_cells[key]
        row_w = sum(c.width for c in cells) + GAP * (len(cells) - 1)
        row_h = ROW_LABEL_H + CELL_H + CAP_H
        row_img = Image.new("RGBA", (row_w, row_h), BG_RGBA)
        d = ImageDraw.Draw(row_img)
        d.text((0, 0), LABELS[key], font=FONT_LABEL, fill=TEXT_RGB)
        x = 0
        for c in cells:
            row_img.alpha_composite(c, (x, ROW_LABEL_H))
            x += c.width + GAP
        row_imgs.append(row_img)
        max_row_w = max(max_row_w, row_w)

    header_text = ("Lantern Wraith attack samples, 2026-09-16. Wind-up is shared "
                   "by all variants; hit made from C, shared.")
    header_h = 30
    total_w = max_row_w + MARGIN * 2
    total_h = MARGIN + header_h + sum(r.height for r in row_imgs) + ROW_GAP * (len(row_imgs) - 1) + MARGIN

    sheet = Image.new("RGBA", (total_w, total_h), BG_RGBA)
    d = ImageDraw.Draw(sheet)
    d.text((MARGIN, MARGIN), header_text, font=FONT_HEADER, fill=TEXT_RGB)

    y = MARGIN + header_h
    for r in row_imgs:
        sheet.alpha_composite(r, (MARGIN, y))
        y += r.height + ROW_GAP

    return sheet


# ---------------------------------------------------------------------------
# Output 2: wisp_gamescale_1x.png
# ---------------------------------------------------------------------------

def build_gamescale(wraith_windup, wizard_img, stills, hit_shared_frame2):
    CANVAS_W = 900
    LEFT_MARGIN = 40
    LABEL_H = 22
    AREA_H = 230
    ROW_GAP = 16
    LEGEND_LABEL_H = 22
    LEGEND_H = 60
    FOOTER_H = 34
    TOP_MARGIN = 26
    BOTTOM_MARGIN = 12
    GROUND_OFFSET_IN_AREA = 180
    WRAITH_X_OFFSET = 80  # from left margin
    UNIT_PX = 405  # 6 world units at 67.5 px/unit

    total_h = (TOP_MARGIN + 3 * (LABEL_H + AREA_H + ROW_GAP)
               + LEGEND_LABEL_H + LEGEND_H + FOOTER_H + BOTTOM_MARGIN)
    canvas = Image.new("RGBA", (CANVAS_W, total_h), BG_RGBA)
    d = ImageDraw.Draw(canvas)

    y = TOP_MARGIN
    for key in ("A", "B", "C"):
        d.text((LEFT_MARGIN, y), LABELS[key], font=FONT_LABEL, fill=TEXT_RGB)
        area_top = y + LABEL_H
        ground_y = area_top + GROUND_OFFSET_IN_AREA
        wraith_x = LEFT_MARGIN + WRAITH_X_OFFSET
        wizard_x = wraith_x + UNIT_PX
        wraith_pivot = (wraith_x, ground_y)
        wizard_pivot = (wizard_x, ground_y)

        # faint ground line for readability
        d.line([(LEFT_MARGIN, ground_y), (CANVAS_W - LEFT_MARGIN, ground_y)],
               fill=GRID_RGB, width=1)

        composite_sprite(canvas, wraith_windup, PIVOT_WRAITH_LOCAL, wraith_pivot, S_WRAITH)
        composite_sprite(canvas, wizard_img, PIVOT_WIZARD_LOCAL, wizard_pivot, S_WIZARD)

        lantern_point = (wraith_pivot[0] + 40, wraith_pivot[1] - 101)
        chest_point = (wizard_pivot[0] + 0, wizard_pivot[1] - 58)

        for t in (0.0, 0.5, 1.0):
            pos = lerp(lantern_point, chest_point, t)
            composite_sprite(canvas, stills[key], PIVOT_WISP_LOCAL, pos, S_WISP)

        hit_pos = (chest_point[0], chest_point[1] + 26)
        composite_sprite(canvas, hit_shared_frame2, PIVOT_WISP_LOCAL, hit_pos, S_WISP)

        y = area_top + AREA_H + ROW_GAP

    # Legend row
    d.text((LEFT_MARGIN, y), "Reference: existing in-game projectiles at this scale",
           font=FONT_LABEL, fill=TEXT_RGB)
    legend_y = y + LEGEND_LABEL_H + LEGEND_H // 2
    cx1 = LEFT_MARGIN + 40
    r1 = 17  # 34 px disc
    d.ellipse([cx1 - r1, legend_y - r1, cx1 + r1, legend_y + r1], fill=(255, 115, 26, 255))
    label1 = "wizard Fireball placeholder (1, 0.45, 0.1)"
    d.text((cx1 + r1 + 12, legend_y - 8), label1, font=FONT_CAPTION, fill=TEXT_RGB)
    lw1, _ = text_size(d, label1, FONT_CAPTION)

    cx2 = cx1 + r1 + 12 + lw1 + 60
    r2 = 15  # 30 px disc
    d.ellipse([cx2 - r2, legend_y - r2, cx2 + r2, legend_y + r2], fill=(255, 64, 26, 255))
    label2 = "today's enemy fireball (1, 0.25, 0.1)"
    d.text((cx2 + r2 + 12, legend_y - 8), label2, font=FONT_CAPTION, fill=TEXT_RGB)

    y = y + LEGEND_LABEL_H + LEGEND_H

    footer = ("1080p game-scale simulation, 67.5 px per world unit, camera-facing "
              "sprites assumed. Not Unity. Frost Field has no in-game visual yet.")
    d.text((LEFT_MARGIN, y), footer, font=FONT_FOOTER, fill=CAPTION_RGB)

    return canvas


# ---------------------------------------------------------------------------
# Output 3: GIFs at 1080p game scale
# ---------------------------------------------------------------------------

def make_scene_bg(w, h):
    img = Image.new("RGB", (w, h), BG_RGB)
    d = ImageDraw.Draw(img)
    step = 67.5
    n = 0
    while True:
        x = round(n * step)
        if x > w:
            break
        d.line([(x, 0), (x, h)], fill=GRID_RGB, width=1)
        n += 1
    n = 0
    while True:
        y = round(n * step)
        if y > h:
            break
        d.line([(0, y), (w, y)], fill=GRID_RGB, width=1)
        n += 1
    return img


def build_frame(bg, wraith_sprite, wizard_sprite, wraith_pivot, wizard_pivot,
                 wisp_sprite=None, wisp_pos=None):
    frame = bg.copy()
    composite_sprite(frame, wraith_sprite, PIVOT_WRAITH_LOCAL, wraith_pivot, S_WRAITH)
    composite_sprite(frame, wizard_sprite, PIVOT_WIZARD_LOCAL, wizard_pivot, S_WIZARD)
    if wisp_sprite is not None:
        composite_sprite(frame, wisp_sprite, PIVOT_WISP_LOCAL, wisp_pos, S_WISP)
    return frame


def build_gif_frames(wraith_idle, wraith_windup, wizard_img, wisp_still, hit_frames):
    W, H = 600, 240
    wraith_pivot = (80, 210)
    wizard_pivot = (485, 210)
    bg = make_scene_bg(W, H)

    lantern_point = (wraith_pivot[0] + 40, wraith_pivot[1] - 101)
    chest_point = (wizard_pivot[0] + 0, wizard_pivot[1] - 58)

    idle_frame = build_frame(bg, wraith_idle, wizard_img, wraith_pivot, wizard_pivot)
    windup_frame = build_frame(bg, wraith_windup, wizard_img, wraith_pivot, wizard_pivot)

    travel_frames = []
    N_TRAVEL = 40
    for i in range(N_TRAVEL):
        t = i / (N_TRAVEL - 1)
        pos = lerp(lantern_point, chest_point, t)
        travel_frames.append(build_frame(bg, wraith_idle, wizard_img, wraith_pivot,
                                          wizard_pivot, wisp_still, pos))

    hit_seq = []
    for hf in hit_frames:
        hit_seq.append(build_frame(bg, wraith_idle, wizard_img, wraith_pivot,
                                    wizard_pivot, hf, chest_point))

    frames = ([idle_frame] * 10 + [windup_frame] * 8 + travel_frames
              + hit_seq + [idle_frame] * 10)
    durations = ([50] * 10 + [50] * 8 + [50] * 40 + [80] * 4 + [50] * 10)
    assert len(frames) == 72 and len(durations) == 72
    return frames, durations


def quantize_shared(frames):
    """Quantize a list of RGB PIL frames (with possible duplicate object
    references) to P mode against one shared, dither-free palette so the
    GIF does not flicker between frames. Frames sharing an object identity
    are quantized once."""
    distinct = []
    seen_ids = set()
    for f in frames:
        if id(f) not in seen_ids:
            seen_ids.add(id(f))
            distinct.append(f)

    colors = set()
    for f in distinct:
        for count, rgb in f.getcolors(maxcolors=1 << 20):
            colors.add(rgb)
    colors = sorted(colors)

    if len(colors) <= 256:
        pal = []
        for c in colors:
            pal.extend(c)
        while len(pal) < 256 * 3:
            pal.extend(colors[-1] if colors else (0, 0, 0))
        palette_img = Image.new("P", (16, 16))
        palette_img.putpalette(pal)
        exact = True
    else:
        # Fallback: adaptive palette from a strip of all distinct frames.
        strip_w = sum(f.width for f in distinct)
        strip = Image.new("RGB", (strip_w, distinct[0].height))
        x = 0
        for f in distinct:
            strip.paste(f, (x, 0))
            x += f.width
        palette_img = strip.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
        exact = False

    cache = {}
    for f in distinct:
        cache[id(f)] = f.quantize(palette=palette_img, dither=Image.Dither.NONE)

    return [cache[id(f)] for f in frames], len(colors), exact


def save_gif(path, frames, durations):
    q_frames, n_colors, exact = quantize_shared(frames)
    q_frames[0].save(path, save_all=True, append_images=q_frames[1:],
                      duration=durations, loop=0, disposal=2, optimize=False)
    return n_colors, exact


def upscale_frames_nearest(frames, factor):
    distinct = {}
    out = []
    for f in frames:
        key = id(f)
        if key not in distinct:
            distinct[key] = f.resize((f.width * factor, f.height * factor), Image.NEAREST)
        out.append(distinct[key])
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(INSPECT, exist_ok=True)

    wraith_idle = load_rgba(WRAITH_IDLE_PATH)
    wraith_windup = load_rgba(WINDUP_PATH)
    wizard_img = load_rgba(WIZARD_PATH)
    stills = {k: load_rgba(p) for k, p in STILL_PATHS.items()}
    hit_shared = [load_rgba(os.path.join(HIT_SHARED_DIR, f"frame_{i}.png")) for i in range(1, 5)]
    hit_b_own = [load_rgba(os.path.join(HIT_B_OWN_DIR, f"frame_{i}.png")) for i in range(1, 5)]

    print("Loaded sprites:")
    for name, im in [("wraith_idle", wraith_idle), ("wraith_windup", wraith_windup),
                      ("wizard", wizard_img), ("wisp_A", stills["A"]),
                      ("wisp_B", stills["B"]), ("wisp_C", stills["C"])]:
        print(f"  {name}: {im.size} {im.mode}")

    # --- Output 1 ---
    sheet = build_sheet(wraith_idle, wraith_windup, stills, hit_shared, hit_b_own)
    sheet_path = os.path.join(OUT, "wisp_sheet_4x.png")
    sheet.save(sheet_path)
    print(f"Wrote {sheet_path} size={sheet.size}")

    # --- Output 2 ---
    gamescale = build_gamescale(wraith_windup, wizard_img, stills, hit_shared[1])  # frame_2 -> index 1
    gamescale_path = os.path.join(OUT, "wisp_gamescale_1x.png")
    gamescale.save(gamescale_path)
    print(f"Wrote {gamescale_path} size={gamescale.size}")

    # --- Output 3: GIFs ---
    for key in ("A", "B", "C"):
        frames, durations = build_gif_frames(wraith_idle, wraith_windup, wizard_img,
                                              stills[key], hit_shared)
        # flatten to RGB (frames are already RGB from build_frame's RGB bg)
        gif_path = os.path.join(OUT, f"wisp_{key}.gif")
        n_colors, exact = save_gif(gif_path, frames, durations)
        print(f"Wrote {gif_path}: {len(frames)} frames, {n_colors} unique colors, "
              f"exact_palette={exact}")

        frames_3x = upscale_frames_nearest(frames, 3)
        gif3x_path = os.path.join(OUT, f"wisp_{key}_3x.gif")
        n_colors3, exact3 = save_gif(gif3x_path, frames_3x, durations)
        print(f"Wrote {gif3x_path}: {len(frames_3x)} frames, {n_colors3} unique colors, "
              f"exact_palette={exact3}")

        # Inspection frame: middle of the travel phase (phase index 18+10+8=36)
        mid_idx = 10 + 8 + 20
        mid_frame_rgb = frames[mid_idx]
        inspect_path = os.path.join(INSPECT, f"wisp_{key}_travel_mid_frame{mid_idx}.png")
        mid_frame_rgb.save(inspect_path)
        print(f"  inspect frame {mid_idx} -> {inspect_path}")

    print("Done.")


if __name__ == "__main__":
    main()
