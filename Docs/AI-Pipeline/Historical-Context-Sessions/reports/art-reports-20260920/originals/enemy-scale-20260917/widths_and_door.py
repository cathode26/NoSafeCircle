"""Widths beside heights, and the door's passage height - the number that decides whether the wizard is too big
or the door is too small."""
import colorsys, glob, json, os
from PIL import Image

E = "C:/nscrev/reports/art-director/enemy-scale-20260917"
D = "C:/nscrev/reports/art-director/door-art-audit-20260917/png"


def wh(path):
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    a = im.getchannel("A").load()
    ys = [y for y in range(h) if any(a[x, y] > 8 for x in range(w))]
    xs = [x for x in range(w) if any(a[x, y] > 8 for y in range(h))]
    return ys[-1] - ys[0] + 1, xs[-1] - xs[0] + 1


def med(vals):
    return sorted(vals)[len(vals) // 2]


sets = {
    "wizard 128 standing": f"{E}/wiz/*.png",
    "melee idle 128": f"{E}/png/enemy_melee_*_idle_*.png",
    "melee walk 176": f"{E}/png/enemy_melee_*_walk_*.png",
    "ranged idle 128": f"{E}/png/enemy_ranged_*_idle_*.png",
    "ranged walk 176": f"{E}/png/enemy_ranged_*_walk_*.png",
}
out = {}
for k, g in sets.items():
    m = [wh(p) for p in sorted(glob.glob(g))]
    hs, ws = [x[0] for x in m], [x[1] for x in m]
    out[k] = {"drawn_h_median": med(hs), "drawn_w_median": med(ws),
              "world_h_64ppu": round(med(hs) / 64, 2), "world_w_64ppu": round(med(ws) / 64, 2)}
    print(f"{k:22s} h {med(hs):3d}px ({med(hs)/64:.2f}u)  w {med(ws):3d}px ({med(ws)/64:.2f}u)")

# The door's passage: the red leaf in the sealed state, and the dark void in the open state.
im = Image.open(f"{D}/door_bonestone_sealed_S_000.png").convert("RGBA")
w, h = im.size
px = im.load()
red = [(x, y) for y in range(h) for x in range(w)
       if px[x, y][3] > 8 and (lambda c: c[1] > 0.25 and (c[0] * 360 >= 335 or c[0] * 360 < 25))(
           colorsys.rgb_to_hsv(*[v / 255 for v in px[x, y][:3]]))]
ys = [y for _, y in red]
xs = [x for x, _ in red]
leaf_h, leaf_w = max(ys) - min(ys) + 1, max(xs) - min(xs) + 1
print(f"\ndoor leaf (sealed, red pixels) {leaf_h}px tall ({leaf_h/64:.2f}u), {leaf_w}px wide ({leaf_w/64:.2f}u)")

im2 = Image.open(f"{D}/door_bonestone_open_S_000.png").convert("RGBA")
p2 = im2.load()
dark = [(x, y) for y in range(im2.height) for x in range(im2.width)
        if p2[x, y][3] > 8 and sum(p2[x, y][:3]) / 3 < 40]
if dark:
    dys = [y for _, y in dark]
    print(f"door void (open, near-black) {max(dys) - min(dys) + 1}px tall ({(max(dys)-min(dys)+1)/64:.2f}u)")

out["door_leaf_sealed"] = {"h_px": leaf_h, "w_px": leaf_w, "world_h_64ppu": round(leaf_h / 64, 2)}
json.dump(out, open(f"{E}/scale_table.json", "w"), indent=2)
