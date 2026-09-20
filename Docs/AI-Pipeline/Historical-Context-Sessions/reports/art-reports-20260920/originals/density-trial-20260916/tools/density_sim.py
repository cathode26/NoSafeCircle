r"""Pixel-density review simulation: masculine-light wizard, south-east walk.

Art Director job, local Pillow only (no PixelLab, no AI generation, no
subprocesses). Outputs are review renders, never source art, and nothing is
written under C:\NSC\NSC\NoSafeCircle (read only).

Four panels, always in this order:
  1. "In game today (1x2 box)"  - the 180 px art through today's builder
     transform (SpriteRenderer localScale (1,2,1), identity rotation, NOT
     camera-facing). Reference only.
  2. "Now: 180 px, Point"       - the 180 px art in a camera-facing 2x2-unit
     box, nearest ("Point") sampling.
  3. "A: smoothed"              - the same 180 px art and box, rendered at 4x
     with bilinear sampling on premultiplied alpha, box-averaged 4x4 back
     down, then converted back to straight alpha. Mimics mipmaps + bilinear.
  4. "B: remade at 128"         - the 128 px option-B walk frames in the same
     camera-facing 2x2-unit box, nearest sampling.

Every sampling formula below is the exact pixel-center formula from the job
spec, not an approximation. Loops are restricted to each sprite's screen
bounding rectangle for speed; the un-drawn remainder of a canvas is already
background + grid.
"""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
REPO = Path(r"C:\NSC\NSC\NoSafeCircle")
WIZARD_SRC = REPO / (
    "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/"
    "masculine-light/selected/walk/south-east"
)
OPT_B_SRC = ROOT / "pixellab" / "3c_walk_se_128"

BG = (29, 22, 49)          # #1d1631
GRID = (42, 35, 66)        # #2a2342
LABEL_COLOR = (222, 216, 232)
FOOTER_COLOR = (160, 152, 176)

PPU = {1080: 67.5, 1440: 90.0}
SCALE_180 = {1080: 0.75, 1440: 1.0}
SCALE_128 = {1080: 1.0546875, 1440: 1.40625}

# "In game today" projection: screen px per source px at 1080p, from the job
# spec ("one source pixel along sprite X moves (0.2652 px right, 0.1326 px
# down); one source pixel along sprite Y (up) moves 0.6495 px up"). These
# scale linearly with px-per-unit for 1440p (factor 90/67.5 = 4/3).
TODAY_AX0_1080, TODAY_AX1_1080, TODAY_AY_UP_1080 = 0.2652, 0.1326, 0.6495
TODAY_FACTOR = {1080: 1.0, 1440: PPU[1440] / PPU[1080]}


def today_coeffs(dpi):
    f = TODAY_FACTOR[dpi]
    # dx = Du*ax0 ; dy = Du*ax1 + Dvd*ay1   (Dvd = v - canvas, downward offset
    # from the pivot; ay1 positive because Dvd>0 already means "toward the
    # pivot", i.e. moving down the source image moves the projected point
    # down and to a lesser degree right, consistent with TODAY_AX1).
    return (TODAY_AX0_1080 * f, TODAY_AX1_1080 * f, TODAY_AY_UP_1080 * f)


PLAYER_MOVE_SPEED = 4.0  # world units/s, PlayerMovement.moveSpeed
SCREEN_UNITS_PER_WORLD_UNIT = 0.632  # along the down-right screen direction
STEP_PX = {1080: 2.012, 1440: 2.683}  # px per 1/60 s step, each of X and Y
FPS_SIM = 60
DURATION_S = 1.5
STEPS = int(round(FPS_SIM * DURATION_S))  # 90
WALK_FPS_CLIP = 12
STEPS_PER_WALK_FRAME = FPS_SIM // WALK_FPS_CLIP  # 5

START_FRAC = (0.37, 0.21)
BASE_1080 = (110, 150)
BASE_1440 = (147, 200)
PANEL_MOTION_SIZE_1080 = (420, 380)
PANEL_MOTION_SIZE_1440 = (560, 507)  # metrics-only virtual canvas, no GIF

WINDOW_W, WINDOW_H = 140, 170
WINDOW_PIVOT = (70, 150)  # where the (floor-tracked) pivot sits in the window
ZOOM_3X = 3

CELL_MARGIN_UNITS = 3.0   # cell is 3x3 world units (box is 2x2, plus margin)
GAP_UNITS = 1.0           # >= 1 world unit between cells, per spec
GROUND_MARGIN_UNITS = 0.5


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_walk_180():
    frames = []
    for i in range(6):
        img = Image.open(WIZARD_SRC / f"frame_{i:03d}.png").convert("RGBA")
        assert img.size == (180, 180), img.size
        frames.append(img)
    return frames


def load_walk_128():
    frames = []
    for i in range(1, 7):  # frame_01..frame_06; frame_00 is the start pose
        img = Image.open(OPT_B_SRC / f"frame_{i:02d}.png").convert("RGBA")
        assert img.size == (128, 128), img.size
        frames.append(img)
    return frames


# --------------------------------------------------------------------------
# Sampling primitives (exact, per spec)
# --------------------------------------------------------------------------

def nearest_texel(px, w, h, u, v):
    xt, yt = math.floor(u), math.floor(v)
    if 0 <= xt < w and 0 <= yt < h:
        return px[xt, yt]
    return (0, 0, 0, 0)


def sample_iso_nearest(px, w, h, s, pivot, X, Y):
    pxp, pyp = pivot
    left = pxp - w * s / 2.0
    top = pyp - h * s
    u = (X + 0.5 - left) / s
    v = (Y + 0.5 - top) / s
    return nearest_texel(px, w, h, u, v)


def sample_today(px, w, h, coeffs, pivot, X, Y):
    pxp, pyp = pivot
    ax0, ax1, ay1 = coeffs
    dx = (X + 0.5) - pxp
    dy = (Y + 0.5) - pyp
    Du = dx / ax0
    Dvd = (dy - Du * ax1) / ay1
    u = Du + w / 2.0
    v = Dvd + h
    return nearest_texel(px, w, h, u, v)


def _bilinear_premult(px, w, h, x, y):
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    acc_r = acc_g = acc_b = acc_a = 0.0
    for (dx0, dy0, weight) in (
        (0, 0, (1 - fx) * (1 - fy)),
        (1, 0, fx * (1 - fy)),
        (0, 1, (1 - fx) * fy),
        (1, 1, fx * fy),
    ):
        xt, yt = x0 + dx0, y0 + dy0
        if 0 <= xt < w and 0 <= yt < h:
            r, g, b, a = px[xt, yt]
        else:
            r = g = b = a = 0
        af = a / 255.0
        acc_r += weight * r * af
        acc_g += weight * g * af
        acc_b += weight * b * af
        acc_a += weight * a
    return acc_r, acc_g, acc_b, acc_a


def sample_bilinear_box(px, w, h, s, pivot, X, Y):
    pxp, pyp = pivot
    s4 = 4.0 * s
    left = pxp - w * s / 2.0
    top = pyp - h * s
    left4 = 4.0 * left
    top4 = 4.0 * top
    sum_r = sum_g = sum_b = sum_a = 0.0
    for ky in range(4):
        Yf = 4 * Y + ky
        for kx in range(4):
            Xf = 4 * X + kx
            u = (Xf + 0.5 - left4) / s4
            v = (Yf + 0.5 - top4) / s4
            r, g, b, a = _bilinear_premult(px, w, h, u - 0.5, v - 0.5)
            sum_r += r
            sum_g += g
            sum_b += b
            sum_a += a
    r, g, b, a = sum_r / 16.0, sum_g / 16.0, sum_b / 16.0, sum_a / 16.0
    if a > 1e-6:
        af = a / 255.0
        r, g, b = r / af, g / af, b / af
    else:
        r = g = b = 0.0
    return (
        max(0, min(255, r)),
        max(0, min(255, g)),
        max(0, min(255, b)),
        max(0, min(255, a)),
    )


def composite_over_opaque(dst_rgb, src_rgba):
    r, g, b, a = src_rgba
    if a <= 0:
        return dst_rgb
    af = a / 255.0
    dr, dg, db = dst_rgb
    return (
        round(r * af + dr * (1 - af)),
        round(g * af + dg * (1 - af)),
        round(b * af + db * (1 - af)),
    )


# --------------------------------------------------------------------------
# Bounding boxes
# --------------------------------------------------------------------------

def iso_bbox(w, h, s, pivot):
    pxp, pyp = pivot
    left = pxp - w * s / 2.0
    top = pyp - h * s
    right = left + w * s
    bottom = top + h * s
    return (
        int(math.floor(left)) - 1,
        int(math.floor(top)) - 1,
        int(math.ceil(right)) + 1,
        int(math.ceil(bottom)) + 1,
    )


def today_bbox(w, h, coeffs, pivot):
    pxp, pyp = pivot
    ax0, ax1, ay1 = coeffs
    xs, ys = [], []
    for u, v in ((0, 0), (w, 0), (0, h), (w, h)):
        Du = u - w / 2.0
        Dvd = v - h
        dx = Du * ax0
        dy = Du * ax1 + Dvd * ay1
        xs.append(pxp + dx)
        ys.append(pyp + dy)
    return (
        int(math.floor(min(xs))) - 1,
        int(math.floor(min(ys))) - 1,
        int(math.ceil(max(xs))) + 1,
        int(math.ceil(max(ys))) + 1,
    )


def clip(bbox, w, h):
    x0, y0, x1, y1 = bbox
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


# --------------------------------------------------------------------------
# One panel kind's renderer/metrics, unified
# --------------------------------------------------------------------------

PANEL_KINDS = ("today", "point180", "smoothed180", "point128")
PANEL_LABELS = {
    "today": "In game today (1x2 box)",
    "point180": "Now: 180 px, Point",
    "smoothed180": "A: smoothed",
    "point128": "B: remade at 128",
}


def panel_sprite_and_scale(kind, dpi, frame_180, frame_128):
    if kind == "today":
        return frame_180, 180, 180, None
    if kind == "point180":
        return frame_180, 180, 180, SCALE_180[dpi]
    if kind == "smoothed180":
        return frame_180, 180, 180, SCALE_180[dpi]
    if kind == "point128":
        return frame_128, 128, 128, SCALE_128[dpi]
    raise ValueError(kind)


def panel_bbox(kind, dpi, w, h, s, pivot):
    if kind == "today":
        return today_bbox(w, h, today_coeffs(dpi), pivot)
    return iso_bbox(w, h, s, pivot)


def render_and_measure(kind, dpi, frame_180, frame_128, pivot, canvas_px, canvas_w, canvas_h):
    """Sample `kind` at `pivot` onto canvas_px (clipped to canvas bounds).

    canvas_px may be None for a metrics-only pass (no compositing).
    Returns (opaque_count, bbox_or_None) measured within the canvas bounds.
    """
    sprite, w, h, s = panel_sprite_and_scale(kind, dpi, frame_180, frame_128)
    sp = sprite.load()
    bbox = panel_bbox(kind, dpi, w, h, s, pivot)
    x0, y0, x1, y1 = clip(bbox, canvas_w, canvas_h)
    count = 0
    bx0 = by0 = None
    bx1 = by1 = None
    coeffs = today_coeffs(dpi) if kind == "today" else None
    for Y in range(y0, y1):
        for X in range(x0, x1):
            if kind == "today":
                col = sample_today(sp, w, h, coeffs, pivot, X, Y)
            elif kind == "smoothed180":
                col = sample_bilinear_box(sp, w, h, s, pivot, X, Y)
            else:
                col = sample_iso_nearest(sp, w, h, s, pivot, X, Y)
            if col[3] > 0:
                count += 1
                bx0 = X if bx0 is None else min(bx0, X)
                by0 = Y if by0 is None else min(by0, Y)
                bx1 = X if bx1 is None else max(bx1, X)
                by1 = Y if by1 is None else max(by1, Y)
                if canvas_px is not None:
                    canvas_px[X, Y] = composite_over_opaque(canvas_px[X, Y], col)
    measured_bbox = None if bx0 is None else [bx0, by0, bx1 + 1, by1 + 1]
    return count, measured_bbox


# --------------------------------------------------------------------------
# Grid + label helpers
# --------------------------------------------------------------------------

def draw_grid(draw, x0, y0, x1, y1, ppu, origin=(0, 0)):
    ox, oy = origin
    x = ox % ppu
    while x0 + x < x1:
        xi = int(round(x0 + x))
        draw.line([(xi, y0), (xi, y1 - 1)], fill=GRID, width=1)
        x += ppu
    y = oy % ppu
    while y0 + y < y1:
        yi = int(round(y0 + y))
        draw.line([(x0, yi), (x1 - 1, yi)], fill=GRID, width=1)
        y += ppu


def get_font():
    try:
        return ImageFont.load_default()
    except Exception:
        return None


FONT = get_font()


# --------------------------------------------------------------------------
# Static sheets
# --------------------------------------------------------------------------

def build_static_sheet(dpi, out_path, walk180, walk128, metrics_out):
    ppu = PPU[dpi]
    cell_w = int(round(CELL_MARGIN_UNITS * ppu))
    cell_h = int(round(CELL_MARGIN_UNITS * ppu))
    gap = int(round(GAP_UNITS * ppu))
    label_h = 16
    footer_h = 24
    margin = gap

    columns = []
    for i in range(6):
        columns.append((i, 0.0, 0.0))
    for phase in (0.25, 0.5, 0.75):
        columns.append((0, phase, phase))
    n_cols = len(columns)

    col_pitch = cell_w + gap
    row_pitch = label_h + cell_h + gap
    sheet_w = margin + n_cols * col_pitch
    sheet_h = margin + len(PANEL_KINDS) * row_pitch + footer_h + gap

    sheet = Image.new("RGB", (sheet_w, sheet_h), BG)
    draw = ImageDraw.Draw(sheet)
    sheet_px = sheet.load()

    ground_margin = int(round(GROUND_MARGIN_UNITS * ppu))
    local_px = cell_w / 2.0
    local_py = cell_h - ground_margin

    for row_idx, kind in enumerate(PANEL_KINDS):
        row_top = margin + row_idx * row_pitch
        draw.text((margin, row_top), PANEL_LABELS[kind], fill=LABEL_COLOR, font=FONT)
        cell_top = row_top + label_h
        for col_idx, (frame_idx, phase_x, phase_y) in enumerate(columns):
            cell_left = margin + col_idx * col_pitch
            draw_grid(draw, cell_left, cell_top, cell_left + cell_w, cell_top + cell_h,
                      ppu, origin=(cell_left, cell_top))
            pivot = (cell_left + local_px + phase_x, cell_top + local_py + phase_y)
            frame_180 = walk180[frame_idx]
            frame_128 = walk128[frame_idx]
            count, bbox = render_and_measure(
                kind, dpi, frame_180, frame_128, pivot, sheet_px, sheet_w, sheet_h
            )
            if phase_x == 0.0 and phase_y == 0.0:
                metrics_out.setdefault(kind, {}).setdefault("walk_frames", {})[str(frame_idx)] = {
                    "opaque_pixels": count,
                    "alpha_bbox": bbox,
                }

    footer_y = margin + len(PANEL_KINDS) * row_pitch + gap
    footer_text = (
        "Simulation, not Unity. Assumes a camera-facing 2x2-unit wizard box. "
        + (f"1080p: {PPU[1080]:g} px per world unit." if dpi == 1080
           else f"1440p: {PPU[1440]:g} px per world unit.")
    )
    draw.text((margin, footer_y), footer_text, fill=FOOTER_COLOR, font=FONT)

    sheet.save(out_path)
    return sheet


def build_4x_sheet(sheet_1x_path, out_path):
    sheet = Image.open(sheet_1x_path).convert("RGB")
    zoomed = sheet.resize((sheet.width * 4, sheet.height * 4), Image.NEAREST)
    zoomed.save(out_path)


# --------------------------------------------------------------------------
# Motion simulation
# --------------------------------------------------------------------------

def motion_positions(dpi, base):
    bx, by = base
    fx, fy = START_FRAC
    step_px = STEP_PX[dpi]
    positions = []
    for step in range(STEPS):
        px = bx + fx + step * step_px
        py = by + fy + step * step_px
        positions.append((px, py))
    return positions


def walk_frame_for_step(step):
    return (step // STEPS_PER_WALK_FRAME) % 6


def simulate_motion_metrics(dpi, panel_w, panel_h, base, walk180, walk128):
    """Metrics-only pass (no image drawing) for every one of the 90 steps."""
    positions = motion_positions(dpi, base)
    per_panel_counts = {k: [] for k in PANEL_KINDS}
    for step, pivot in enumerate(positions):
        frame_idx = walk_frame_for_step(step)
        frame_180 = walk180[frame_idx]
        frame_128 = walk128[frame_idx]
        for kind in PANEL_KINDS:
            count, _bbox = render_and_measure(
                kind, dpi, frame_180, frame_128, pivot, None, panel_w, panel_h
            )
            per_panel_counts[kind].append(count)
    return per_panel_counts


def step_deltas(counts):
    deltas = [abs(counts[i] - counts[i - 1]) for i in range(1, len(counts))]
    if not deltas:
        return 0.0, 0
    return sum(deltas) / len(deltas), max(deltas)


# --------------------------------------------------------------------------
# Motion GIFs (1080p only, per spec)
# --------------------------------------------------------------------------

def render_motion_1080_frames(walk180, walk128):
    """Render every step's full 4-panel-wide 1080p frame (RGB) and each
    panel's raw pivot, for reuse by both the 1x and 3x GIFs."""
    dpi = 1080
    panel_w, panel_h = PANEL_MOTION_SIZE_1080
    positions = motion_positions(dpi, BASE_1080)
    label_h = 16
    gap = 12
    frame_w = len(PANEL_KINDS) * panel_w + (len(PANEL_KINDS) + 1) * gap
    frame_h = label_h + panel_h + gap

    frames_1x = []
    frames_3x_windows = []  # per step: list of 4 window RGB images (unzoomed 140x170)

    for step, pivot in enumerate(positions):
        frame_idx = walk_frame_for_step(step)
        frame_180 = walk180[frame_idx]
        frame_128 = walk128[frame_idx]

        composite = Image.new("RGB", (frame_w, frame_h), BG)
        draw = ImageDraw.Draw(composite)
        draw_px = composite.load()

        windows = []
        x = gap
        for kind in PANEL_KINDS:
            draw.text((x, 0), PANEL_LABELS[kind], fill=LABEL_COLOR, font=FONT)
            panel_top = label_h
            draw_grid(draw, x, panel_top, x + panel_w, panel_top + panel_h, PPU[dpi], origin=(0, 0))
            x += panel_w + gap

        # Second pass: composite sprites, kept separate from the label/grid
        # pass above so grid lines are always drawn before any sprite pixel.
        x = gap
        for kind in PANEL_KINDS:
            panel_top = label_h
            panel_pivot = (x + pivot[0], panel_top + pivot[1])
            render_and_measure(kind, dpi, frame_180, frame_128, panel_pivot,
                                draw_px, frame_w, frame_h)
            # window for the 3x GIF: follow the sprite in whole-pixel steps
            wx0 = math.floor(panel_pivot[0]) - WINDOW_PIVOT[0]
            wy0 = math.floor(panel_pivot[1]) - WINDOW_PIVOT[1]
            window = composite.crop((wx0, wy0, wx0 + WINDOW_W, wy0 + WINDOW_H))
            if window.size != (WINDOW_W, WINDOW_H):
                padded = Image.new("RGB", (WINDOW_W, WINDOW_H), BG)
                padded.paste(window, (0, 0))
                window = padded
            windows.append(window)
            x += panel_w + gap

        frames_1x.append(composite)
        frames_3x_windows.append(windows)

    return frames_1x, frames_3x_windows, frame_w, frame_h


def build_shared_palette(images):
    sample = images[0].copy()
    for img in images[1:]:
        thumb = img.resize((max(1, img.width // 4), max(1, img.height // 4)))
        strip = Image.new("RGB", (sample.width + thumb.width, max(sample.height, thumb.height)), BG)
        strip.paste(sample, (0, 0))
        strip.paste(thumb, (sample.width, 0))
        sample = strip
    return sample.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.Dither.NONE)


def to_palette_frames(images, palette_img):
    return [img.quantize(colors=256, palette=palette_img, dither=Image.Dither.NONE) for img in images]


def save_gif(frames_p, out_path):
    durations = []
    cycle = [30, 30, 40]
    for i in range(len(frames_p)):
        durations.append(cycle[i % 3])
    frames_p[0].save(
        out_path,
        save_all=True,
        append_images=frames_p[1:],
        duration=durations,
        loop=0,
        disposal=2,
    )


def build_motion_gifs(frames_1x, frames_3x_windows, out_1x, out_3x):
    step_indices = list(range(0, STEPS, 2))  # every second step -> 45 frames
    sel_1x = [frames_1x[i] for i in step_indices]

    sel_3x = []
    for i in step_indices:
        windows = frames_3x_windows[i]
        zoomed = [w.resize((WINDOW_W * ZOOM_3X, WINDOW_H * ZOOM_3X), Image.NEAREST) for w in windows]
        label_h = 16
        gap = 8
        n = len(zoomed)
        fw = n * zoomed[0].width + (n + 1) * gap
        fh = label_h + zoomed[0].height + gap
        frame = Image.new("RGB", (fw, fh), BG)
        draw = ImageDraw.Draw(frame)
        x = gap
        for kind, z in zip(PANEL_KINDS, zoomed):
            draw.text((x, 0), PANEL_LABELS[kind], fill=LABEL_COLOR, font=FONT)
            frame.paste(z, (x, label_h))
            x += z.width + gap
        sel_3x.append(frame)

    pal_1x = build_shared_palette(sel_1x)
    pal_3x = build_shared_palette(sel_3x)
    p_1x = to_palette_frames(sel_1x, pal_1x)
    p_3x = to_palette_frames(sel_3x, pal_3x)
    save_gif(p_1x, out_1x)
    save_gif(p_3x, out_3x)
    return len(sel_1x), sel_1x[0].size, len(sel_3x), sel_3x[0].size


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    walk180 = load_walk_180()
    walk128 = load_walk_128()

    metrics = {"panels": {}, "motion": {}, "summary": {}}

    print("Building 1080p static sheet...")
    sheet_1x_path = ROOT / "density_sheet_1x.png"
    build_static_sheet(1080, sheet_1x_path, walk180, walk128, metrics["panels"])

    print("Building 1440p static sheet...")
    sheet_1440_path = ROOT / "density_sheet_1440p.png"
    metrics_1440 = {}
    build_static_sheet(1440, sheet_1440_path, walk180, walk128, metrics_1440)
    for kind, data in metrics_1440.items():
        metrics["panels"].setdefault(kind, {})["walk_frames_1440p"] = data["walk_frames"]

    print("Building 4x zoom sheet...")
    build_4x_sheet(sheet_1x_path, ROOT / "density_sheet_4x.png")

    print("Simulating motion metrics at 1080p...")
    counts_1080 = simulate_motion_metrics(1080, *PANEL_MOTION_SIZE_1080, BASE_1080, walk180, walk128)
    print("Simulating motion metrics at 1440p...")
    counts_1440 = simulate_motion_metrics(1440, *PANEL_MOTION_SIZE_1440, BASE_1440, walk180, walk128)

    for kind in PANEL_KINDS:
        metrics["motion"].setdefault(kind, {})["opaque_pixels_per_step_1080p"] = counts_1080[kind]
        metrics["motion"][kind]["opaque_pixels_per_step_1440p"] = counts_1440[kind]
        mean1080, max1080 = step_deltas(counts_1080[kind])
        mean1440, max1440 = step_deltas(counts_1440[kind])
        metrics["summary"][kind] = {
            "mean_abs_step_delta_1080p": round(mean1080, 3),
            "max_abs_step_delta_1080p": max1080,
            "mean_abs_step_delta_1440p": round(mean1440, 3),
            "max_abs_step_delta_1440p": max1440,
        }

    print("Rendering 1080p motion frames (this is the slow step)...")
    frames_1x, frames_3x_windows, fw, fh = render_motion_1080_frames(walk180, walk128)
    print(f"Frame canvas: {fw}x{fh}, {len(frames_1x)} steps rendered")

    print("Building motion GIFs...")
    n1, size1, n3, size3 = build_motion_gifs(
        frames_1x, frames_3x_windows,
        ROOT / "density_motion_1x.gif", ROOT / "density_motion_3x.gif",
    )

    metrics["gif_info"] = {
        "density_motion_1x.gif": {"frames": n1, "size": list(size1)},
        "density_motion_3x.gif": {"frames": n3, "size": list(size3)},
    }

    metrics_path = ROOT / "sim_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print("Wrote", metrics_path)

    for kind in PANEL_KINDS:
        s = metrics["summary"][kind]
        print(kind, s)


if __name__ == "__main__":
    main()
