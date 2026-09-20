"""Losslessly center-crop or pad PixelLab v3 walk frames to a square canvas.

Usage: python -B normalize_frames.py <raw_dir> <out_dir> <canvas> <report.json>

For each raw frame_XX.png: record raw size, alpha bbox and SHA-256; place the raw
canvas centered on the target canvas (integer offset, floor division); refuse the crop
if any opaque pixel would fall outside; write the normalized PNG and record its offset
and SHA-256. No resampling and no pixel edits: pixels are only moved as a block.
"""
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image


def main(argv: list) -> int:
    raw_dir, out_dir, canvas, report_path = Path(argv[1]), Path(argv[2]), int(argv[3]), Path(argv[4])
    out_dir.mkdir(parents=True, exist_ok=True)
    report = []
    failures = 0
    for raw_path in sorted(raw_dir.glob("frame_*.png")):
        raw_bytes = raw_path.read_bytes()
        raw = Image.open(raw_path).convert("RGBA")
        width, height = raw.size
        bbox = raw.getchannel("A").getbbox()
        # Offset of the raw canvas's top-left corner on the target canvas.
        offset_x = (canvas - width) // 2
        offset_y = (canvas - height) // 2
        entry = {
            "frame": raw_path.name,
            "raw_size": [width, height],
            "raw_alpha_bbox": list(bbox) if bbox else None,
            "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "canvas": [canvas, canvas],
            "raw_origin_on_canvas": [offset_x, offset_y],
        }
        if bbox is not None:
            left, top, right, bottom = bbox
            fits = (left + offset_x >= 0 and top + offset_y >= 0 and
                    right + offset_x <= canvas and bottom + offset_y <= canvas)
        else:
            fits = True
        entry["opaque_pixels_fit"] = fits
        if not fits:
            failures += 1
            report.append(entry)
            print("REFUSED (opaque pixels outside canvas):", json.dumps(entry))
            continue
        target = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        # paste() with a negative offset crops; with a positive offset pads.
        target.paste(raw, (offset_x, offset_y))
        out_path = out_dir / raw_path.name
        target.save(out_path)
        out_bytes = out_path.read_bytes()
        check = Image.open(out_path).convert("RGBA")
        raw_opaque = sum(raw.getchannel("A").histogram()[1:])
        out_opaque = sum(check.getchannel("A").histogram()[1:])
        entry.update({
            "selected_file": str(out_path),
            "selected_alpha_bbox": list(check.getchannel("A").getbbox() or ()),
            "raw_opaque_pixels": raw_opaque,
            "selected_opaque_pixels": out_opaque,
            "selected_sha256": hashlib.sha256(out_bytes).hexdigest(),
        })
        if raw_opaque != out_opaque:
            failures += 1
            entry["error"] = "opaque pixel count changed"
        report.append(entry)
        print(json.dumps(entry))
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
