"""Per-prop palette audit for the AC-003 package, so style-lock flags are numbers and not impressions.

Bands over opaque pixels with saturation > 0.15 (grey and near-grey slate is hueless and must not vote):
  warm  = hue [15, 65)   tan, ochre, warm brown, copper
  red   = hue [340, 360) + [0, 15)  crimson, plum-red
  violet= hue [250, 300) violet slate, mauve, lilac
Also the brightest pixel (value) and the mean saturation, which is what makes one prop shout beside another.
"""
import colorsys
import json

from PIL import Image

FINALS = [
    ("shared_bone_pile_a", "round1-48/shared_bone_pile_a.png"),
    ("ba_collapsed_reading_table_z", "round2-48/ba_collapsed_reading_table_z.png"),
    ("ca_candelabra_tall", "round1-48/ca_candelabra_tall.png"),
    ("re_broken_masonry_blocks", "round3-48/re_broken_masonry_blocks.png"),
    ("lv_iron_rail_x", "round1-48/lv_iron_rail_x.png"),
    ("wizard_se_128 (approved, for reference)", "round1/wizard_se_128.png"),
    ("kit floor piece (NSC-064, for reference)", None),
]


def audit(path):
    im = Image.open(path).convert("RGBA")
    px = [c for c in im.getdata() if c[3] > 8]
    warm = red = violet = 0
    sats = []
    vmax = 0.0
    for r, g, b, _ in px:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        vmax = max(vmax, v)
        sats.append(s)
        if s <= 0.15:
            continue
        deg = h * 360
        if 15 <= deg < 65:
            warm += 1
        elif deg >= 340 or deg < 15:
            red += 1
        elif 250 <= deg < 300:
            violet += 1
    n = max(1, sum(1 for s in sats if s > 0.15))
    return {
        "opaque_px": len(px),
        "saturated_px": n,
        "warm_pct": round(100 * warm / n, 1),
        "red_pct": round(100 * red / n, 1),
        "violet_pct": round(100 * violet / n, 1),
        "mean_sat": round(sum(sats) / len(sats), 3),
        "brightest_value": round(vmax, 3),
    }


def main():
    out = {}
    for name, path in FINALS:
        if path is None:
            continue
        out[name] = audit(path)
    print(json.dumps(out, indent=2))
    json.dump(out, open("ac003_palette_audit.json", "w"), indent=2)


if __name__ == "__main__":
    main()
