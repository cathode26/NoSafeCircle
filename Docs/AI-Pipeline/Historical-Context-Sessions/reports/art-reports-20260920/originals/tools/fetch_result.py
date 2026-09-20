"""Download PixelLab result files and log size, alpha bbox, opaque pixels and SHA-256.

Usage:
  python -B fetch_result.py <log.json> <url> <dest.png> [<url> <dest.png> ...]

Each download is appended to <log.json> (a JSON list). Existing destination files are
never overwritten; a second download of the same URL goes to a new name with a suffix.
"""
import datetime
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image


def describe_png(data: bytes) -> dict:
    image = Image.open(io.BytesIO(data))
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    histogram = alpha.histogram()
    opaque = sum(histogram[1:])
    return {
        "size": list(image.size),
        "mode": image.mode,
        "alpha_bbox": list(bbox) if bbox else None,
        "opaque_pixels": opaque,
    }


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def main(argv: list) -> int:
    if len(argv) < 4 or len(argv) % 2 != 0:
        print(__doc__)
        return 2
    log_path = Path(argv[1])
    entries = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    for url, dest in zip(argv[2::2], argv[3::2]):
        destination = unique_path(Path(dest))
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "nsc-art-director-review/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        destination.write_bytes(data)
        entry = {
            "downloaded_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "url": url,
            "file": str(destination),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            entry.update(describe_png(data))
        elif data[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entry["zip_members"] = archive.namelist()
        entries.append(entry)
        print(json.dumps(entry))
    log_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
