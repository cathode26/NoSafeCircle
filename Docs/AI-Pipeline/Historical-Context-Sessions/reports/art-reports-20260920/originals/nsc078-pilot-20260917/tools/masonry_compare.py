"""Compare the three broken-masonry attempts on the two things the spec pins:
silhouette (rubble, nothing standing / no intact arch) and palette (cold violet slate, no warm stone).

Silhouette measures, all from the alpha channel:
  - enclosed_void_px: transparent pixels NOT reachable from the image border by 4-connected flood fill.
    An intact arch or doorway encloses a void; a rubble heap encloses almost nothing.
  - top_band_fill: fraction of the bbox's top 25% of rows that is opaque. A standing structure carries
    mass high; a heap does not.
  - mass_centroid_y: vertical centre of opaque mass as a fraction of bbox height (0 = top, 1 = bottom).

Palette measures, over opaque pixels with saturation > 0.15 (grey slate is hueless and must not vote):
  - warm_frac: hue in [15, 65) degrees - tan, beige, warm brown.
  - violet_frac: hue in [250, 300) degrees - violet slate, mauve, lilac.
"""
import colorsys
import json
import sys
from collections import deque

from PIL import Image

SETS = [
    ("round 1", "round1-48/re_broken_masonry_blocks.png"),
    ("round 2", "round2-48/re_broken_masonry_blocks.png"),
    ("round 3", "round3-48/re_broken_masonry_blocks.png"),
]


def measure(path):
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    a = im.getchannel("A").load()
    rgba = im.load()
    op = [[a[x, y] > 8 for x in range(w)] for y in range(h)]

    # enclosed void: flood transparent from the border
    seen = [[False] * w for _ in range(h)]
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not op[y][x] and not seen[y][x]:
                seen[y][x] = True
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if not op[y][x] and not seen[y][x]:
                seen[y][x] = True
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not op[ny][nx] and not seen[ny][nx]:
                seen[ny][nx] = True
                q.append((nx, ny))
    enclosed = sum(1 for y in range(h) for x in range(w) if not op[y][x] and not seen[y][x])

    bbox = im.getchannel("A").getbbox()
    x0, y0, x1, y1 = bbox
    bw, bh = x1 - x0, y1 - y0
    top_rows = range(y0, y0 + max(1, bh // 4))
    top_fill = sum(1 for y in top_rows for x in range(x0, x1) if op[y][x]) / (len(list(top_rows)) * bw)

    opaque = [(x, y) for y in range(h) for x in range(w) if op[y][x]]
    cy = sum(y for _, y in opaque) / len(opaque)

    warm = violet = sat_n = 0
    for x, y in opaque:
        r, g, b, _ = rgba[x, y]
        hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if ss <= 0.15:
            continue
        sat_n += 1
        deg = hh * 360
        if 15 <= deg < 65:
            warm += 1
        elif 250 <= deg < 300:
            violet += 1
    return {
        "size": [w, h],
        "bbox": list(bbox),
        "opaque_px": len(opaque),
        "enclosed_void_px": enclosed,
        "enclosed_void_frac_of_bbox": round(enclosed / (bw * bh), 4),
        "top_band_fill": round(top_fill, 4),
        "mass_centroid_y_frac": round((cy - y0) / bh, 4),
        "saturated_px": sat_n,
        "warm_frac": round(warm / sat_n, 4) if sat_n else None,
        "violet_frac": round(violet / sat_n, 4) if sat_n else None,
    }


def main():
    out = {}
    for label, path in SETS:
        out[label] = measure(path)
    print(json.dumps(out, indent=2))
    json.dump(out, open("masonry_compare.json", "w"), indent=2)

    # 3x side-by-side panel, native pixels nearest-upscaled, on a mid-grey card
    scale = 3
    ims = [Image.open(p).convert("RGBA") for _, p in SETS]
    W = max(i.width for i in ims) * scale
    H = max(i.height for i in ims) * scale
    gap, pad, label_h = 12, 12, 22
    card = Image.new("RGBA", (pad * 2 + W * 3 + gap * 2, pad * 2 + H + label_h), (58, 54, 66, 255))
    for n, im in enumerate(ims):
        up = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        card.alpha_composite(up, (pad + n * (W + gap) + (W - up.width) // 2, pad + label_h))
    card.save("masonry_compare_3x.png")
    print("wrote masonry_compare_3x.png", card.size)


if __name__ == "__main__":
    main()
