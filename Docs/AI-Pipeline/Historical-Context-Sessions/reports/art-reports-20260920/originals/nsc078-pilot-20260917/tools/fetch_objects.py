"""Download the NSC-078 pilot objects and measure them.

Usage: python fetch_objects.py <out_dir>

Uses `https://api.pixellab.ai/mcp/objects/<id>/download`, the same no-auth endpoint pattern that replaced
expiring per-frame URLs on NSC-095. HTTP 423 means the object is still generating, so it retries.
"""
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter

from PIL import Image

OBJECTS = [
    ("shared_bone_pile_a", "28c4f29d-46e1-40e5-9c58-051f48a4760c", (100, 84), 101),
    ("ba_collapsed_reading_table_z", "30372cd0-ec66-4365-8a29-6b8f42f57601", (144, 148), 102),
    ("ca_candelabra_tall", "cc89c4c3-a991-4e76-8f24-59023e5995ba", (64, 148), 103),
    ("re_broken_masonry_blocks", "66f2bbc1-fc87-48ee-98c5-876423c5e0b9", (124, 112), 104),
    ("lv_iron_rail_x", "696e0b20-7364-4132-8493-09a7250e8854", (108, 116), 105),
]


def fetch(url, tries=8, wait=30):
    for n in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 423:
                print(f"   still generating (423), attempt {n + 1}")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"gave up on {url}")


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    records = []
    for name, oid, expect, seed in OBJECTS:
        dst = os.path.join(out, name + ".png")
        if os.path.exists(dst):
            print(name, "already downloaded")
        else:
            data = fetch(f"https://api.pixellab.ai/mcp/objects/{oid}/download")
            # the endpoint serves a PNG for one direction, or a zip for eight
            if data[:4] == b"\x89PNG":
                open(dst, "wb").write(data)
            else:
                z = zipfile.ZipFile(io.BytesIO(data))
                png = [n for n in z.namelist() if n.endswith(".png")][0]
                open(dst, "wb").write(z.read(png))
        im = Image.open(dst).convert("RGBA")
        a = im.getchannel("A")
        bbox = a.getbbox()
        px = list(im.getdata())
        opaque = [p for p in px if p[3] > 0]
        colours = len(set(opaque))
        w, h = im.size
        corners = [a.getpixel((0, 0)), a.getpixel((w - 1, 0)), a.getpixel((0, h - 1)), a.getpixel((w - 1, h - 1))]
        brightest = max(opaque, key=lambda p: p[0] + p[1] + p[2])
        rec = {
            "id": name, "object_id": oid, "seed": seed, "file": dst,
            "size": [w, h], "expected_size": list(expect),
            "size_ok": [w, h] == list(expect),
            "alpha_bbox": list(bbox) if bbox else None,
            "touches_edge": bool(bbox and (bbox[0] == 0 or bbox[1] == 0 or bbox[2] == w or bbox[3] == h)),
            "transparent_corners": all(c == 0 for c in corners),
            "opaque_pixels": len(opaque), "distinct_colours": colours,
            "fill_percent": round(100.0 * len(opaque) / (w * h), 1),
            "brightest_colour": "#%02x%02x%02x" % brightest[:3],
            "sha256": hashlib.sha256(open(dst, "rb").read()).hexdigest(),
        }
        records.append(rec)
        print(f"{name:30s} {w}x{h} expect {expect[0]}x{expect[1]} "
              f"{'OK' if rec['size_ok'] else 'MISMATCH'}  bbox {bbox}  "
              f"fill {rec['fill_percent']}%  colours {colours}  "
              f"corners {'clear' if rec['transparent_corners'] else 'OPAQUE'}"
              f"{'  EDGE-CLIPPED' if rec['touches_edge'] else ''}")
    json.dump(records, open(os.path.join(out, "measurements.json"), "w", encoding="utf-8"), indent=1)
    print("\nwrote measurements.json")


main()
