"""Measure the read-only masculine-light source sprites used by the density trial.

Prints size, alpha bounding box, opaque pixel count and SHA-256 per file.
Local review tooling only; it never writes into the repository.
"""
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

REPO = Path(r"C:\NSC\NSC\NoSafeCircle")
SELECTED = REPO / "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected"
ENEMY = REPO / "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_se_idle_00.png"


def measure(path: Path) -> dict:
    data = path.read_bytes()
    image = Image.open(path)
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    opaque = sum(1 for value in alpha.getdata() if value > 0)
    return {
        "path": str(path.relative_to(REPO)).replace("\\", "/"),
        "mode": image.mode,
        "size": list(image.size),
        "alpha_bbox": list(bbox) if bbox else None,
        "bbox_size": [bbox[2] - bbox[0], bbox[3] - bbox[1]] if bbox else None,
        "opaque_pixels": opaque,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main() -> int:
    paths = [SELECTED / "standing/south.png", SELECTED / "standing/south-east.png"]
    paths += [SELECTED / f"walk/south-east/frame_00{index}.png" for index in range(6)]
    paths.append(ENEMY)
    results = [measure(path) for path in paths]
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    text = json.dumps(results, indent=2)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
