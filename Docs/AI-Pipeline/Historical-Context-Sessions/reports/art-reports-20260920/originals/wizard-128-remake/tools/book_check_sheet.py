"""Belt-book check sheet: the hip band of all 8 facings, candidate 128 over approved 180.

Usage: python book_check_sheet.py <key> <candidate_standing_dir> <out_png>

The crops are proportional: the candidate's band is rows 55-105 of 128, the approved's rows 77-148 of 180,
so the same part of the body is shown. Candidate at 5x, approved at 4x (nearest neighbour, no resampling).
"""
import io
import subprocess
import sys

from PIL import Image, ImageDraw

DIRS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
REPO = r"C:\NSC\NSC\NoSafeCircle"
ROOT = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab"
NO_WINDOW = 0x08000000


def approved(key, d):
    out = subprocess.run(["git", "-C", REPO, "show", f"main:{ROOT}/{key}/selected/standing/{d}.png"],
                         capture_output=True, check=True, creationflags=NO_WINDOW).stdout
    return Image.open(io.BytesIO(out)).convert("RGBA")


def main():
    key, cand_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    zc, za = 5, 4
    cw, chh = 60 * zc, 50 * zc          # candidate crop 60x50 at 5x
    aw, ahh = 84 * za, 71 * za          # approved crop 84x71 at 4x
    cell = max(cw, aw) + 12
    sheet = Image.new("RGBA", (cell * len(DIRS), chh + ahh + 60), (24, 22, 28, 255))
    dr = ImageDraw.Draw(sheet)
    for i, d in enumerate(DIRS):
        x = i * cell
        c = Image.open(f"{cand_dir}\\{d}.png").convert("RGBA").crop((34, 55, 94, 105))
        a = approved(key, d).crop((48, 77, 132, 148))
        dr.text((x + 6, 4), f"{d} new 128", fill=(230, 235, 230, 255))
        sheet.alpha_composite(c.resize((cw, chh), Image.NEAREST), (x + 6, 20))
        dr.text((x + 6, chh + 28), f"{d} approved", fill=(200, 205, 210, 255))
        sheet.alpha_composite(a.resize((aw, ahh), Image.NEAREST), (x + 6, chh + 44))
    sheet.convert("RGB").save(out_path)
    print("wrote", out_path, sheet.size)


main()
