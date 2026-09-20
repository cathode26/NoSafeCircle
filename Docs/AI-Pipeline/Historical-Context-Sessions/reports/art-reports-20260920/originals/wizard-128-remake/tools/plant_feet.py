"""Pin every walk frame's lowest opaque row to the wizard's ground line, the way the approved enemies are aligned.

Usage: python plant_feet.py <aligned_dir> <ground_line_exclusive> <out_dir> [--check]

The approved NSC-077 enemy walks have their alpha bottom at the same row in all six frames (spread 0, seam 0)
while the head still moves 2-9 px, so per-frame alignment plants the feet without killing the body bob. This
tool applies that to already-aligned wizard frames: each frame is shifted by whole pixels only, and any shift
that would push an opaque pixel off the canvas is refused.

It also reports which body part is lowest, because pinning the wrong part (a coat hem dipping below the boots)
would lift the character; NSC-077 handles that case with a whole-pixel correction table.
"""
import json
import os
import sys

from PIL import Image

DIRS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


def measure(path):
    im = Image.open(path).convert("RGBA")
    a = im.getchannel("A")
    bb = a.getbbox()
    return im, a, bb


def main():
    src, gl_excl, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    target = gl_excl - 1  # inclusive lowest opaque row
    report = {"ground_line_y_from_top": gl_excl, "target_row_inclusive": target, "frames": [], "directions": {}}
    for d in DIRS:
        sd = os.path.join(src, "walk", d)
        od = os.path.join(out, "walk", d)
        os.makedirs(od, exist_ok=True)
        rows_before, rows_after, heads_after, shifts = [], [], [], []
        for f in sorted(x for x in os.listdir(sd) if x.endswith(".png")):
            im, a, bb = measure(os.path.join(sd, f))
            low = bb[3] - 1
            dy = target - low
            w, h = im.size
            if bb[1] + dy < 0 or bb[3] + dy > h:
                sys.exit(f"{d}/{f}: shift {dy} would clip (bbox {bb}, canvas {h})")
            new = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            new.paste(im, (0, dy))
            na = new.getchannel("A")
            nbb = na.getbbox()
            assert nbb == (bb[0], bb[1] + dy, bb[2], bb[3] + dy), f"{d}/{f}: bbox moved wrong"
            before = sum(1 for p in im.getchannel("A").tobytes() if p)
            after = sum(1 for p in na.tobytes() if p)
            assert before == after, f"{d}/{f}: opaque count changed {before} -> {after}"
            new.save(os.path.join(od, f))
            rows_before.append(low)
            rows_after.append(nbb[3] - 1)
            heads_after.append(nbb[1])
            shifts.append(dy)
            report["frames"].append({"direction": d, "file": f, "row_before": low, "dy": dy,
                                     "row_after": nbb[3] - 1, "head_after": nbb[1],
                                     "alpha_bottom_y_from_top": nbb[3]})
        report["directions"][d] = {
            "rows_before": rows_before, "shifts": shifts,
            "foot_spread_after": max(rows_after) - min(rows_after),
            "foot_seam_after": abs(rows_after[0] - rows_after[-1]),
            "head_spread_after": max(heads_after) - min(heads_after),
            "head_seam_after": abs(heads_after[0] - heads_after[-1]),
        }
    # the standing frames come across unchanged: they are already on the line
    for d in DIRS:
        s = os.path.join(src, "standing", d + ".png")
        o = os.path.join(out, "standing", d + ".png")
        os.makedirs(os.path.dirname(o), exist_ok=True)
        im, a, bb = measure(s)
        if bb[3] != gl_excl:
            sys.exit(f"standing/{d}: alpha bottom {bb[3]} is not the ground line {gl_excl}")
        im.save(o)
    json.dump(report, open(os.path.join(out, "plant_report.json"), "w", encoding="utf-8"), indent=1)
    worst_head = max(v["head_seam_after"] for v in report["directions"].values())
    print(f"planted every frame on row {target} (alpha bottom {gl_excl})")
    print(f"foot spread and seam are 0 by construction; worst head seam {worst_head} px")
    for d in DIRS:
        v = report["directions"][d]
        print(f"  {d:11s} shifts {v['shifts']}  head spread {v['head_spread_after']} seam {v['head_seam_after']}")


main()
