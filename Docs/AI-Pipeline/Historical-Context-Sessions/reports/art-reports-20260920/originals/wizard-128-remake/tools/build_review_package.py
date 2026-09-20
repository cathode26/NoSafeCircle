"""Build the VAL-002 review package for the 128 px wizard remake.

For each wizard: an 8-panel walk GIF (all facings cycling together), a true-screen-scale sheet at 1080p via the
art-review toolkit's `gamescale`, and `frame-metrics` for all 8 walk directions.

Usage: python build_review_package.py <out_dir>
"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw

ROOT = r"C:\nscrev\reports\art-director\wizard-128-remake"
TOOLKIT = r"C:\nscrev\art-tools\ArtReview"
NO_WINDOW = 0x08000000
DIRS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]

# aligned folder per wizard: the accepted version, after any re-roll
WIZARDS = {
    "masculine-light": "pixellab/masculine-light/aligned",
    "masculine-dark": "pixellab/masculine-dark/aligned",
    "feminine-light": "pixellab/feminine-light/aligned_v2",
    "feminine-dark": "pixellab/feminine-dark/aligned_v2",
}


def walk_frames(base, direction):
    d = os.path.join(base, "walk", direction)
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".png")][:6]


def panel_gif(key, base, out_path, zoom=3, ms=83):
    """One GIF, eight panels, every facing cycling its own six frames."""
    cell = 128 * zoom
    cols, rows = 4, 2
    label_h = 14
    frames = []
    for i in range(6):
        sheet = Image.new("RGBA", (cell * cols, (cell + label_h) * rows), (24, 22, 28, 255))
        dr = ImageDraw.Draw(sheet)
        for n, direction in enumerate(DIRS):
            cx, cy = (n % cols) * cell, (n // cols) * (cell + label_h)
            dr.text((cx + 4, cy + 3), direction, fill=(210, 215, 220, 255))
            src = Image.open(walk_frames(base, direction)[i]).convert("RGBA")
            sheet.alpha_composite(src.resize((cell, cell), Image.NEAREST), (cx, cy + label_h))
        frames.append(sheet.convert("P", palette=Image.ADAPTIVE, colors=255))
    frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=ms, loop=0, disposal=2)
    print("gif", key, out_path)


def gamescale(key, base, out_dir):
    """True-screen-scale sheet: the eight standing facings in a 2x2-unit camera-facing box at 1080p."""
    manifest = {
        "resolution": "1080p",
        "panel_width": 200,
        "panel_height": 220,
        "gap": 10,
        "background": "#18161c",  # a list crashes parse_color with AttributeError; it wants a hex string
        "footer": f"{key}: 128 px source, 2x2-unit camera-facing box, true 1080p scale",
        "sprites": [
            {
                "path": os.path.join(base, "standing", f"{d}.png"),
                "label": d,
                "mode": "camera-facing",
                "sampling": "nearest",
                "box_units": 2,
                "pivot": "bottom-center",
            }
            for d in DIRS
        ],
    }
    mpath = os.path.join(out_dir, f"gamescale_{key}.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    out_png = os.path.join(out_dir, f"gamescale_{key}.png")
    cp = subprocess.run(
        [sys.executable, "-m", "art_review", "gamescale", "--manifest", mpath,
         "--output", out_png, "--json", os.path.join(out_dir, f"gamescale_{key}_report.json")],
        cwd=TOOLKIT, capture_output=True, text=True, creationflags=NO_WINDOW)
    print("gamescale", key, cp.returncode, (cp.stdout or cp.stderr).strip()[:200])


def metrics(key, base, out_dir):
    summary = {}
    for d in DIRS:
        jpath = os.path.join(out_dir, f"metrics_{key}_{d}.json")
        cp = subprocess.run(
            [sys.executable, "-m", "art_review", "frame-metrics", "--loop", "--json", jpath] + walk_frames(base, d),
            cwd=TOOLKIT, capture_output=True, text=True, creationflags=NO_WINDOW)
        if cp.returncode not in (0, 1):
            print("metrics FAILED", key, d, cp.returncode, (cp.stderr or "").strip()[:200])
            continue
        with open(jpath, encoding="utf-8") as fh:
            data = json.load(fh)
        summary[d] = data
    spath = os.path.join(out_dir, f"metrics_{key}_summary.json")
    with open(spath, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print("metrics", key, "directions:", len(summary))
    return summary


def main():
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    for key, rel in WIZARDS.items():
        base = os.path.join(ROOT, rel)
        panel_gif(key, base, os.path.join(out_dir, f"walk_{key}.gif"))
        gamescale(key, base, out_dir)
        metrics(key, base, out_dir)


main()
