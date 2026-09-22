"""NSC-065 revalidation at main `ac8ddffa1`.

VAL-001  deterministic inventory: every required state, the final variant, transparent
         backgrounds, consistent dimensions and perspective, unambiguous filenames.
VAL-002  readability at gameplay scale and coherence with the selected wizard art.

VAL-002 is the one that had to be redone: it measures world size, and world size is
canvas / pixelsPerUnit. PPU moved 100 -> 64, so every number it asserted changed.
"""
import io
import json
import subprocess
import sys

from PIL import Image

REPO = r"C:/NSC/NSC/NoSafeCircle"
REF = "ac8ddffa1"
DOORS = "Assets/NoSafeCircle/DoorPrototype/Art/Doors/Source"
STATES = ["sealed", "opening", "open", "locked", "damaged", "broken", "final"]

DOOR_PPU_OLD, DOOR_PPU_NEW = 100.0, 64.0
WIZ = ("Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/"
       "masculine-light/selected/standing/south-east.png")
WIZ_PPU = 180.0          # DoorPrototypeGlobalSceneBuilder.cs:592, unchanged


def blob(path, ref=REF):
    r = subprocess.run(["git", "-C", REPO, "show", f"{ref}:{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def load(path, ref=REF):
    b = blob(path, ref)
    return (Image.open(io.BytesIO(b)).convert("RGBA"), b) if b else (None, None)


def bbox(im):
    a = im.getchannel("A")
    return a.getbbox()          # (left, upper, right, lower), right/lower exclusive


print(f"=== VAL-001 deterministic inventory @ {REF} ===\n")
rows, problems = [], []
canvases, images = set(), {}
for s in STATES:
    p = f"{DOORS}/door_bonestone_{s}_S_000.png"
    im, raw = load(p)
    if im is None:
        problems.append(f"MISSING state: {s}")
        continue
    images[s] = im
    bb = bbox(im)
    alpha = im.getchannel("A")
    transparent = alpha.getextrema()[0] == 0
    opaque_px = sum(1 for v in alpha.getdata() if v > 0)
    canvases.add(im.size)
    rows.append((s, im.size, bb, transparent, opaque_px, len(raw)))
    if not transparent:
        problems.append(f"{s}: no transparent pixels — background not transparent")

print(f"{'state':<9}{'canvas':>10}{'drawn bbox':>22}{'transparent bg':>16}{'opaque px':>11}")
for s, size, bb, tr, op, nbytes in rows:
    print(f"{s:<9}{size[0]}x{size[1]:>5}{str(bb):>24}{str(tr):>14}{op:>12}")

print(f"\nstates found: {len(rows)}/{len(STATES)}   distinct canvases: {canvases}")
if len(canvases) != 1:
    problems.append(f"inconsistent canvases: {canvases}")

# Perspective consistency: identical drawn bbox across states means one silhouette
# footprint, which is what "consistent perspective" means for a door family.
bbs = {r[2] for r in rows}
print(f"distinct drawn bounding boxes: {len(bbs)} -> {bbs if len(bbs) <= 3 else 'many'}")

# Filename ambiguity: every state must map to exactly one file.
listing = subprocess.run(["git", "-C", REPO, "ls-tree", "-r", "--name-only", REF, "--", DOORS],
                         capture_output=True, text=True).stdout.split()
pngs = [p.rsplit("/", 1)[-1] for p in listing if p.endswith(".png")]
print(f"PNG files in the family: {len(pngs)}")
for s in STATES:
    hits = [n for n in pngs if f"_{s}_" in n]
    if len(hits) != 1:
        problems.append(f"ambiguous or missing filename for {s}: {hits}")
extra = [n for n in pngs if not any(f"_{s}_" in n for s in STATES)]
if extra:
    problems.append(f"PNG not mapped to any required state: {extra}")

print(f"\nVAL-001: {'PASS' if not problems else 'PROBLEMS'}")
for p in problems:
    print("   ", p)

print(f"\n\n=== VAL-002 readability at gameplay scale @ {REF} ===\n")
sealed, opened = images.get("sealed"), images.get("open")
w, h = sealed.size

for label, ppu in (("BEFORE (recorded, PPU 100)", DOOR_PPU_OLD),
                   ("NOW    (PPU 64)", DOOR_PPU_NEW)):
    bb = bbox(sealed)
    dw, dh = bb[2] - bb[0], bb[3] - bb[1]
    print(f"{label}: canvas {w}x{h} -> {w/ppu:.3f} x {h/ppu:.3f} u   "
          f"drawn {dw}x{dh}px -> {dw/ppu:.3f} x {dh/ppu:.3f} u")

# The passage: where the sealed leaf is opaque and the open state is not.
ps, po = sealed.load(), opened.load()
cols = [x for x in range(w)
        if any(ps[x, y][3] > 0 and po[x, y][3] == 0 for y in range(h))]
rowsy = [y for y in range(h)
         if any(ps[x, y][3] > 0 and po[x, y][3] == 0 for x in range(w))]
if cols and rowsy:
    pw, ph = cols[-1] - cols[0] + 1, rowsy[-1] - rowsy[0] + 1
    print(f"\npassage (sealed-minus-open): {pw} x {ph} px")
    print(f"   at PPU 100 (recorded): {pw/DOOR_PPU_OLD:.3f} x {ph/DOOR_PPU_OLD:.3f} u")
    print(f"   at PPU  64 (now):      {pw/DOOR_PPU_NEW:.3f} x {ph/DOOR_PPU_NEW:.3f} u")

# Coherence with the wizard that actually ships today.
wim, _ = load(WIZ)
if wim is not None:
    wb = bbox(wim)
    ww, wh = wb[2] - wb[0], wb[3] - wb[1]
    print(f"\nshipping wizard {WIZ.rsplit('/', 1)[-1]}: canvas {wim.size[0]}x{wim.size[1]}, "
          f"drawn {ww}x{wh}px at PPU {WIZ_PPU:.0f} -> {ww/WIZ_PPU:.3f} x {wh/WIZ_PPU:.3f} u")
    if cols and rowsy:
        print(f"   wizard drawn height {wh/WIZ_PPU:.3f} u vs passage height "
              f"{ph/DOOR_PPU_OLD:.3f} u then, {ph/DOOR_PPU_NEW:.3f} u now")

# State distinctness at gameplay scale: how different is each state from sealed
# once shrunk to the size it actually occupies on a 1080p screen?
print("\nstate distinctness after downscaling to gameplay size (vs sealed):")
target = max(1, int(round(h / DOOR_PPU_NEW * 64)))       # px on screen at 64 px/unit
base = sealed.resize((target, target), Image.NEAREST)
bl = base.load()
for s in STATES:
    if s == "sealed" or s not in images:
        continue
    o = images[s].resize((target, target), Image.NEAREST)
    ol = o.load()
    diff = sum(1 for y in range(target) for x in range(target)
               if bl[x, y] != ol[x, y])
    print(f"   {s:<9} {diff:>6} of {target*target} px differ  ({diff/(target*target):.1%})")
