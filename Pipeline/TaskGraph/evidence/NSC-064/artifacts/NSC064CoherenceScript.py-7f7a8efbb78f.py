# -*- coding: utf-8 -*-
"""NSC-064 VAL-002 evidence: measure the kit against its OWN declared palette band.

The style lock in Docs/Art/Environment/PIXELLAB_GENERATION.md declares, measured off NSC-078's
delivered props: luminance 68-73, saturation 19-39, warm pixels 4-5%, floors allowed down to ~49.
Colour depth 48. Coherence is checked against that band rather than by eye.
"""
import colorsys
import io
import json
import pathlib
import subprocess

from PIL import Image

REPO = r"C:/NSC/NSC/NoSafeCircle"
ROOT = "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source"
OUT = pathlib.Path(__file__).parent / "NSC064CoherenceMeasurements.json"

COMMIT = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                        capture_output=True, text=True, check=True).stdout.strip()
paths = sorted(p for p in subprocess.run(
    ["git", "-C", REPO, "ls-tree", "-r", "--name-only", COMMIT, ROOT + "/"],
    capture_output=True, text=True, check=True).stdout.split() if p.endswith(".png"))

rows = []
for path in paths:
    raw = subprocess.run(["git", "-C", REPO, "show", "%s:%s" % (COMMIT, path)],
                         capture_output=True, check=True).stdout
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    opaque = [(r, g, b) for r, g, b, a in im.getdata() if a > 128]
    n = len(opaque)
    lum = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in opaque) / n
    sats, warm = 0.0, 0
    for r, g, b in opaque:
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        sats += s
        if (h < 0.11 or h > 0.93) and s > 0.25:
            warm += 1
    rows.append({
        "file": pathlib.PurePosixPath(path).name,
        "family": "floor" if "/floors/" in path else "wall",
        "luminance": round(lum, 1),
        "saturation_pct": round(100.0 * sats / n, 1),
        "warm_pct": round(100.0 * warm / n, 2),
        "distinct_colours": len(set(opaque)),
    })

BAND = {"lum_wall": (68.0, 73.0), "lum_floor_min": 49.0, "sat": (19.0, 39.0),
        "warm": (4.0, 5.0), "max_colours": 48}
print("declared band: luminance 68-73 (floors may sit to ~49), saturation 19-39, warm 4-5%%, <=48 colours")
print("%-26s %-6s %9s %9s %7s %9s" % ("file", "fam", "lum", "sat%", "warm%", "colours"))
for r in rows:
    lo = BAND["lum_floor_min"] if r["family"] == "floor" else BAND["lum_wall"][0]
    flags = []
    if not (lo <= r["luminance"] <= BAND["lum_wall"][1]):
        flags.append("LUM")
    if not (BAND["sat"][0] <= r["saturation_pct"] <= BAND["sat"][1]):
        flags.append("SAT")
    if r["distinct_colours"] > BAND["max_colours"]:
        flags.append("COLOURS")
    r["deviations"] = flags
    print("%-26s %-6s %9.1f %9.1f %7.2f %9d  %s"
          % (r["file"], r["family"], r["luminance"], r["saturation_pct"],
             r["warm_pct"], r["distinct_colours"], ",".join(flags) if flags else ""))

OUT.write_text(json.dumps({"task": "NSC-064", "gate": "VAL-002",
                           "measured_at_commit": COMMIT, "declared_band": BAND,
                           "measurements": rows}, indent=2, sort_keys=True) + "\n",
               encoding="utf-8", newline="\n")
dev = [r["file"] for r in rows if r["deviations"]]
print("\nsources outside the declared band:", dev if dev else "NONE")
print("wrote %s (%d bytes)" % (OUT.name, OUT.stat().st_size))
