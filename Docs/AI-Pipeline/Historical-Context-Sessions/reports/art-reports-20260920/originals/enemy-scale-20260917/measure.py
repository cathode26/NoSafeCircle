"""Measure the committed enemy art against the committed 128 px wizard, in the only terms that matter:
drawn height above the ground line, and the world height that implies at a given pixels-per-unit."""
import glob, json, os, re
from PIL import Image

O = "C:/nscrev/reports/art-director/enemy-scale-20260917"


def rows(path):
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    a = im.getchannel("A").load()
    ys = [y for y in range(h) if any(a[x, y] > 8 for x in range(w))]
    xs = [x for x in range(w) if any(a[x, y] > 8 for y in range(h))]
    return {
        "canvas": (w, h),
        "top": ys[0], "ground": ys[-1],
        "left": xs[0], "right": xs[-1],
        "drawn_h": ys[-1] - ys[0] + 1,
        "drawn_w": xs[-1] - xs[0] + 1,
        "pivot_y_if_ground": round((h - 1 - ys[-1]) / h, 4),
    }


def summarize(paths, label):
    recs = {os.path.basename(p): rows(p) for p in paths}
    hs = [r["drawn_h"] for r in recs.values()]
    ws = [r["drawn_w"] for r in recs.values()]
    gs = [r["ground"] for r in recs.values()]
    cs = {r["canvas"] for r in recs.values()}
    return {
        "label": label,
        "files": len(recs),
        "canvases": sorted(cs),
        "ground_rows": [min(gs), max(gs)],
        "ground_spread": max(gs) - min(gs),
        "drawn_h": [min(hs), max(hs)],
        "drawn_h_median": sorted(hs)[len(hs) // 2],
        "drawn_w": [min(ws), max(ws)],
    }


def main():
    melee_idle = sorted(glob.glob(f"{O}/png/enemy_melee_*_idle_*.png"))
    ranged_idle = sorted(glob.glob(f"{O}/png/enemy_ranged_*_idle_*.png"))
    melee_walk = sorted(glob.glob(f"{O}/png/enemy_melee_*_walk_*.png"))
    ranged_walk = sorted(glob.glob(f"{O}/png/enemy_ranged_*_walk_*.png"))
    wiz = sorted(glob.glob(f"{O}/wiz/*.png"))
    out = [
        summarize(melee_idle, "enemy melee idle"),
        summarize(melee_walk, "enemy melee walk"),
        summarize(ranged_idle, "enemy ranged idle"),
        summarize(ranged_walk, "enemy ranged walk"),
        summarize(wiz, "wizard 128 standing (committed)"),
    ]
    for r in out:
        if not r["files"]:
            continue
        h = r["drawn_h_median"]
        r["world_h_at_64ppu"] = round(h / 64.0, 3)
        r["world_h_at_88ppu"] = round(h / 88.0, 3)
        print(f"{r['label']:32s} n={r['files']:3d} canvas={r['canvases']} ground={r['ground_rows']} "
              f"spread={r['ground_spread']:2d} drawn_h={r['drawn_h']} median={h:3d} "
              f"-> {r['world_h_at_64ppu']} units at 64 PPU")
    json.dump(out, open(f"{O}/measurements.json", "w"), indent=2)


main()
