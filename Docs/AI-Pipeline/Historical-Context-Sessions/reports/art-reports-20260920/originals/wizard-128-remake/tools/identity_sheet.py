"""Identity review sheet: the 128 px candidate rotations above the approved 180 px stills.

Usage:
  python identity_sheet.py <candidate_dir> <key> <out_png>

<candidate_dir> holds <direction>.png at 128x128. The approved 180 px stills come from main via
`git show`. Candidate is drawn at 3x, approved at 2x (both nearest neighbour), on a shared baseline.
"""
import io
import subprocess
import sys

from PIL import Image, ImageDraw

DIRS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
REPO = r"C:\NSC\NSC\NoSafeCircle"
ROOT = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab"
NO_WINDOW = 0x08000000
CELL_W, PAD, LABEL_H = 400, 12, 22
BG = (24, 22, 28, 255)


def approved(key, direction):
    out = subprocess.run(["git", "-C", REPO, "show", f"main:{ROOT}/{key}/selected/standing/{direction}.png"],
                         capture_output=True, check=True, creationflags=NO_WINDOW).stdout
    return Image.open(io.BytesIO(out)).convert("RGBA")


def main():
    cand_dir, key, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    cands = {d: Image.open(f"{cand_dir}\\{d}.png").convert("RGBA") for d in DIRS}
    apps = {d: approved(key, d) for d in DIRS}

    top = max(im.size[1] * 3 for im in cands.values())
    bottom = max(im.size[1] * 2 for im in apps.values())
    sheet = Image.new("RGBA", (CELL_W * len(DIRS), LABEL_H + top + LABEL_H + bottom + PAD * 3), BG)
    draw = ImageDraw.Draw(sheet)

    for i, d in enumerate(DIRS):
        x = i * CELL_W
        draw.text((x + PAD, 4), f"{d}  candidate 128 @3x", fill=(230, 235, 230, 255))
        c = cands[d].resize((cands[d].size[0] * 3, cands[d].size[1] * 3), Image.NEAREST)
        y = LABEL_H + PAD + (top - c.size[1])
        sheet.alpha_composite(c, (x + (CELL_W - c.size[0]) // 2, y))

        y2 = LABEL_H + PAD + top + PAD
        draw.text((x + PAD, y2), f"{d}  approved 180 @2x", fill=(200, 205, 210, 255))
        a = apps[d].resize((apps[d].size[0] * 2, apps[d].size[1] * 2), Image.NEAREST)
        sheet.alpha_composite(a, (x + (CELL_W - a.size[0]) // 2, y2 + LABEL_H + (bottom - a.size[1])))

    sheet.convert("RGB").save(out_path)
    print("wrote", out_path, sheet.size)


main()
