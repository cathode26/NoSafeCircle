"""Prove the wind-up inpaint changed pixels only inside the mask, and summarize the change.

Writes inspect/windup_vs_idle_6x.png (idle | wind-up | changed pixels in magenta) and
prints counts plus the new colors the inpaint introduced.
"""
import hashlib
from pathlib import Path

from PIL import Image

JOB = Path(__file__).resolve().parent.parent
SOURCE = Path(r"C:\NSC\NSC\NoSafeCircle\Assets\NoSafeCircle\DoorPrototype\Art\Enemies\Source\enemy_ranged_se_idle_00.png")
RESULT = JOB / "pixellab" / "windup_se_128.png"
MASK = JOB / "inputs" / "windup_mask_128.png"


def main() -> None:
    idle = Image.open(SOURCE).convert("RGBA")
    windup = Image.open(RESULT).convert("RGBA")
    mask = Image.open(MASK).convert("L")
    assert idle.size == windup.size == mask.size == (128, 128)
    changed_inside = changed_outside = 0
    diff = Image.new("RGBA", idle.size, (0, 0, 0, 0))
    idle_colors = set()
    new_colors = {}
    for y in range(128):
        for x in range(128):
            a = idle.getpixel((x, y))
            b = windup.getpixel((x, y))
            if a[3] > 0:
                idle_colors.add(a[:3])
            # Treat fully transparent pixels as equal regardless of their RGB bytes.
            same = a == b or (a[3] == 0 and b[3] == 0)
            if not same:
                if mask.getpixel((x, y)) == 255:
                    changed_inside += 1
                else:
                    changed_outside += 1
                diff.putpixel((x, y), (255, 0, 200, 255))
            if b[3] > 0:
                new_colors[b[:3]] = new_colors.get(b[:3], 0) + 1
    introduced = {c: n for c, n in new_colors.items() if c not in idle_colors}
    print("source sha256", hashlib.sha256(SOURCE.read_bytes()).hexdigest())
    print("result sha256", hashlib.sha256(RESULT.read_bytes()).hexdigest())
    print("changed pixels inside mask:", changed_inside)
    print("changed pixels outside mask:", changed_outside)
    print("result colors:", len(new_colors), "introduced colors:",
          ", ".join("#%02x%02x%02x x%d" % (c[0], c[1], c[2], n) for c, n in sorted(introduced.items(), key=lambda i: -i[1])))
    zoom = 6
    background = (40, 40, 48, 255)
    sheet = Image.new("RGBA", (128 * zoom * 3 + 40, 128 * zoom + 20), (20, 16, 30, 255))
    for index, image in enumerate([idle, windup, diff]):
        tile = Image.new("RGBA", image.size, background)
        tile.alpha_composite(image)
        sheet.paste(tile.resize((128 * zoom, 128 * zoom), Image.NEAREST), (10 + index * (128 * zoom + 10), 10))
    (JOB / "inspect").mkdir(exist_ok=True)
    sheet.save(JOB / "inspect" / "windup_vs_idle_6x.png")


if __name__ == "__main__":
    main()
