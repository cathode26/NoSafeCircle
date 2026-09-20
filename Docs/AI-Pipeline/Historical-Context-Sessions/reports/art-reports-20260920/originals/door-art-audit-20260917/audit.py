"""Measure the seven committed NSC-065 door states before anyone binds them to a renderer."""
import colorsys, json, os
from PIL import Image, ImageDraw, ImageFont

O = "C:/nscrev/reports/art-director/door-art-audit-20260917"
STATES = ["sealed", "locked", "opening", "open", "damaged", "broken", "final"]


def font(sz, bold=False):
    for p in ([r"C:\Windows\Fonts\segoeuib.ttf"] if bold else []) + [r"C:\Windows\Fonts\segoeui.ttf"]:
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def measure(path):
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    a = im.getchannel("A").load()
    rgba = im.load()
    rows = [y for y in range(h) if any(a[x, y] > 8 for x in range(w))]
    cols = [x for x in range(w) if any(a[x, y] > 8 for y in range(h))]
    op = [(x, y) for y in range(h) for x in range(w) if a[x, y] > 8]
    warm = violet = sat_n = 0
    for x, y in op:
        r, g, b, _ = rgba[x, y]
        hh, ss, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if ss <= 0.15:
            continue
        sat_n += 1
        deg = hh * 360
        if 15 <= deg < 65:
            warm += 1
        elif 250 <= deg < 300:
            violet += 1
    return {
        "canvas": [w, h],
        "bbox": [cols[0], rows[0], cols[-1] + 1, rows[-1] + 1],
        "ground_row_from_top": rows[-1],
        "top_row": rows[0],
        "opaque_px": len(op),
        "colours": len({rgba[x, y] for x, y in op}),
        "saturated_px": sat_n,
        "warm_pct": round(100 * warm / sat_n, 1) if sat_n else None,
        "violet_pct": round(100 * violet / sat_n, 1) if sat_n else None,
    }


def main():
    out = {}
    for s in STATES:
        p = f"{O}/png/door_bonestone_{s}_S_000.png"
        out[s] = measure(p)
    grounds = {s: out[s]["ground_row_from_top"] for s in STATES}
    widths = {s: out[s]["bbox"][2] - out[s]["bbox"][0] for s in STATES}
    summary = {
        "ground_rows": grounds,
        "ground_row_spread": max(grounds.values()) - min(grounds.values()),
        "drawn_widths": widths,
        "width_spread": max(widths.values()) - min(widths.values()),
        "per_state": out,
    }
    json.dump(summary, open(f"{O}/audit.json", "w"), indent=2)
    print(json.dumps({k: summary[k] for k in ("ground_rows", "ground_row_spread", "drawn_widths", "width_spread")}, indent=1))
    for s in STATES:
        r = out[s]
        print(f"{s:9s} bbox {str(r['bbox']):24s} colours {r['colours']:5d} warm {r['warm_pct']}% violet {r['violet_pct']}%")

    scale = 2
    ims = [Image.open(f"{O}/png/door_bonestone_{s}_S_000.png").convert("RGBA") for s in STATES]
    cw, ch = 128 * scale, 128 * scale
    pad, gap, head, foot = 16, 10, 54, 40
    card = Image.new("RGBA", (pad * 2 + cw * 7 + gap * 6, pad * 2 + head + ch + foot), (52, 48, 60, 255))
    d = ImageDraw.Draw(card)
    d.text((pad, pad), "NSC-065 door states as committed on main - 7 x 128x128, direction S only, 2x",
           font=font(21, True), fill=(240, 238, 246, 255))
    d.text((pad, pad + 28), "inventory.json: human_visual_approval = false. Vincent has never picked this family.",
           font=font(15), fill=(232, 176, 176, 255))
    for n, s in enumerate(STATES):
        x = pad + n * (cw + gap)
        up = ims[n].resize((cw, ch), Image.NEAREST)
        card.alpha_composite(up, (x, pad + head))
        d.rectangle([x, pad + head, x + cw - 1, pad + head + ch - 1], outline=(96, 92, 108, 255))
        g = out[s]["ground_row_from_top"]
        gy = pad + head + g * scale
        d.line([x, gy, x + cw - 1, gy], fill=(120, 220, 160, 190))
        d.text((x + 2, pad + head + ch + 5), s, font=font(15), fill=(234, 232, 242, 255))
        d.text((x + 2, pad + head + ch + 22), f"lowest row {g}", font=font(13), fill=(168, 164, 184, 255))
    card.save(f"{O}/door_states_2x.png")
    print("wrote door_states_2x.png", card.size)


main()
