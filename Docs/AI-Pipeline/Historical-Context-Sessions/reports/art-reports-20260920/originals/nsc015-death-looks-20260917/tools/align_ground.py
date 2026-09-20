"""Put every death sprite's lowest opaque row on one row, so corpses sit on the floor instead of floating.

Usage: python align_ground.py <src_dir> <out_dir> [--target-row N] [--check]

Same rule the approved enemies and the NSC-095 rev 4 wizards follow: a whole-pixel vertical shift per sprite,
never a resample, and any shift that would push an opaque pixel off the canvas is refused rather than clipped.
Without --target-row the target is the canvas height minus the bottom margin, clamped so no sprite has to clip.

Prints the pivot each sprite then needs: pivot_y = (H - (row + 1)) / H, which is the same formula the enemy
metas use (walk row 131 of 176 -> 0.25).
"""
import json
import os
import sys

from PIL import Image

BOTTOM_MARGIN = 3


def measure(path):
    im = Image.open(path).convert("RGBA")
    a = im.getchannel("A")
    return im, a.getbbox()


def main():
    src, out = sys.argv[1], sys.argv[2]
    check = "--check" in sys.argv
    target = None
    if "--target-row" in sys.argv:
        target = int(sys.argv[sys.argv.index("--target-row") + 1])

    files = sorted(f for f in os.listdir(src) if f.endswith(".png"))
    info = {}
    H = W = None
    for f in files:
        im, bb = measure(os.path.join(src, f))
        H, W = im.height, im.width
        info[f] = {"bbox": list(bb), "low": bb[3] - 1, "top": bb[1]}

    if target is None:
        # the lowest row every sprite can reach without clipping: limited by the tallest sprite's headroom
        max_down = min(H - 1 - i["low"] for i in info.values())
        want = H - 1 - BOTTOM_MARGIN
        highest_low = max(i["low"] for i in info.values())
        target = min(want, highest_low + max_down)
    print(f"canvas {W}x{H}, target lowest opaque row {target} "
          f"(pivot_y {(H - (target + 1)) / H:.6f})")

    os.makedirs(out, exist_ok=True)
    report = {"canvas": [W, H], "target_row_inclusive": target,
              "pivot_y": round((H - (target + 1)) / H, 6), "sprites": []}
    failures = []
    for f in files:
        i = info[f]
        dy = target - i["low"]
        im = Image.open(os.path.join(src, f)).convert("RGBA")
        if i["top"] + dy < 0 or i["low"] + dy > H - 1:
            failures.append((f, dy, "would clip"))
            continue
        shifted = Image.new("RGBA", im.size, (0, 0, 0, 0))
        shifted.paste(im, (0, dy))
        before = sum(1 for c in im.getdata() if c[3] > 8)
        after = sum(1 for c in shifted.getdata() if c[3] > 8)
        if before != after:
            failures.append((f, dy, f"opaque count changed {before} -> {after}"))
            continue
        bb2 = shifted.getchannel("A").getbbox()
        if bb2[3] - 1 != target:
            failures.append((f, dy, f"landed on {bb2[3] - 1}, not {target}"))
            continue
        if not check:
            shifted.save(os.path.join(out, f))
        report["sprites"].append({"file": f, "row_before": i["low"], "shift_dy": dy,
                                  "row_after": bb2[3] - 1, "bbox_after": list(bb2), "opaque_px": after})
        print(f"  {f:26s} row {i['low']:3d} -> {bb2[3] - 1:3d}  dy {dy:+3d}  opaque {after}")

    if failures:
        print("\nFAILURES:")
        for f, dy, why in failures:
            print(f"  {f}: dy {dy:+d}, {why}")
        report["failures"] = [{"file": f, "dy": dy, "why": w} for f, dy, w in failures]
    rows = {s["row_after"] for s in report["sprites"]}
    print(f"\n{len(report['sprites'])} sprites aligned, rows after: {sorted(rows)}, "
          f"spread {max(rows) - min(rows) if rows else 0}")
    json.dump(report, open(os.path.join(out if not check else src, "ground_line_report.json"), "w"), indent=2)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
