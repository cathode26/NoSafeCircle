# -*- coding: utf-8 -*-
"""NSC-064 VAL-001: deterministic inventory of the dungeon architecture source kit.

Every value is MEASURED from the committed blob at a named commit - nothing is transcribed
from the provenance doc. Deterministic: same commit in, byte-identical JSON out.
"""
import hashlib
import io
import json
import pathlib
import re
import subprocess
import sys

from PIL import Image

REPO = r"C:/NSC/NSC/NoSafeCircle"
ROOT = "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Source"
OUT = pathlib.Path(__file__).parent / "NSC064SourceInventory.json"

COMMIT = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                        capture_output=True, text=True, check=True).stdout.strip()

listing = subprocess.run(["git", "-C", REPO, "ls-tree", "-r", "--name-only", COMMIT, ROOT + "/"],
                         capture_output=True, text=True, check=True).stdout.split()
pngs = sorted(p for p in listing if p.endswith(".png"))
if not pngs:
    print("ABORT: no sources found under %s" % ROOT)
    sys.exit(1)

# the nine import settings NSC-064's own style lock names
META_KEYS = ("spriteMode", "spritePixelsToUnits", "filterMode", "textureCompression",
             "alphaIsTransparency", "mipmapEnabled", "wrapU", "textureType", "textureShape")
ENUMS = {
    "spriteMode": {"1": "Single", "2": "Multiple", "3": "Polygon", "0": "None"},
    "filterMode": {"0": "Point", "1": "Bilinear", "2": "Trilinear"},
    "textureCompression": {"0": "Uncompressed", "1": "Compressed"},
    "wrapU": {"0": "Repeat", "1": "Clamp"},        # INVERTED from intuition - see the style lock
    "textureType": {"8": "Sprite", "0": "Default"},
    "textureShape": {"1": "Texture2D", "2": "Cube"},
}


def blob(path):
    return subprocess.run(["git", "-C", REPO, "show", "%s:%s" % (COMMIT, path)],
                          capture_output=True, check=True).stdout


entries = []
for path in pngs:
    raw = blob(path)
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    w, h = im.size
    alpha = im.getchannel("A")
    px = alpha.tobytes()
    opaque = sum(1 for v in px if v == 255)
    partial = sum(1 for v in px if 0 < v < 255)
    corners = [alpha.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]

    meta_raw = blob(path + ".meta").decode("utf-8", "replace")
    meta = {}
    for k in META_KEYS:
        m = re.search(r"^\s*%s:\s*(\S+)\s*$" % k, meta_raw, re.M)
        v = m.group(1) if m else None
        meta[k] = ENUMS.get(k, {}).get(v, v)
    guid = re.search(r"^guid:\s*(\S+)", meta_raw, re.M)

    family = "floor" if "/floors/" in path else "wall"
    # a floor sheet is a 16-tile Wang set at 32 px; a wall piece is one 64x160-family sprite
    tiles = (w // 32) * (h // 32) if family == "floor" else 1
    entries.append({
        "path": path,
        "family": family,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "guid": guid.group(1) if guid else None,
        "pixels": {"width": w, "height": h},
        "world_units_at_64ppu": {"width": round(w / 64.0, 4), "height": round(h / 64.0, 4)},
        "wang_tiles_32px": tiles,
        "tile_world_units_at_64ppu": 0.5 if family == "floor" else None,
        "transparency": {
            "fully_opaque_pct": round(100.0 * opaque / (w * h), 3),
            "partial_alpha_pct": round(100.0 * partial / (w * h), 3),
            "corner_alpha": corners,
            "shape": "full rectangle" if opaque == w * h else "shaped silhouette",
        },
        "intended_use": ("Unity Isometric Tilemap (16-tile Wang set, sliced downstream by INT-001)"
                         if family == "floor" else
                         "Unity Isometric Tilemap wall module (sliced/assembled downstream by INT-001)"),
        "import_settings": meta,
    })

doc = {
    "task": "NSC-064",
    "gate": "VAL-001",
    "measured_at_commit": COMMIT,
    "source_root": ROOT,
    "provenance_document": "Docs/Art/Environment/PIXELLAB_GENERATION.md",
    "source_count": len(entries),
    "families": {"floor": sum(1 for e in entries if e["family"] == "floor"),
                 "wall": sum(1 for e in entries if e["family"] == "wall")},
    "sources": entries,
}
OUT.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

print("commit %s" % COMMIT)
print("wrote %s  (%d bytes, %d sources: %d floor / %d wall)"
      % (OUT.name, OUT.stat().st_size, len(entries), doc["families"]["floor"], doc["families"]["wall"]))
print()
print("%-26s %9s %7s %6s  %-18s %s" % ("file", "px", "opaque%", "tiles", "shape", "import"))
for e in entries:
    print("%-26s %4dx%-4d %6.1f%% %6d  %-18s %s/%s/%s"
          % (pathlib.PurePosixPath(e["path"]).name, e["pixels"]["width"], e["pixels"]["height"],
             e["transparency"]["fully_opaque_pct"], e["wang_tiles_32px"],
             e["transparency"]["shape"], e["import_settings"]["textureType"],
             e["import_settings"]["spriteMode"], e["import_settings"]["wrapU"]))
bad = [e["path"] for e in entries if e["import_settings"]["wrapU"] != "Clamp"
       or e["import_settings"]["textureType"] != "Sprite"
       or e["import_settings"]["filterMode"] != "Point"]
print("\nimport-setting deviations from the style lock:", bad if bad else "NONE")
