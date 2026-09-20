"""Lossless centered crop/pad for animation frames."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .pngio import read_png, write_png
from .raster import crop_pad


def normalize_frame(source_path: str | Path, output_path: str | Path, width: int, height: int) -> dict[str, Any]:
    raw_sha256 = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    source = read_png(source_path)
    origin_x = (width - source.width) // 2
    origin_y = (height - source.height) // 2
    raw_bbox = source.alpha_bbox()
    if raw_bbox is not None:
        translated = (raw_bbox[0] + origin_x, raw_bbox[1] + origin_y, raw_bbox[2] + origin_x, raw_bbox[3] + origin_y)
        if translated[0] < 0 or translated[1] < 0 or translated[2] > width or translated[3] > height:
            raise ValueError("opaque pixels would fall outside the target canvas")
    selected = crop_pad(source, width, height, origin_x, origin_y)
    if selected.opaque_count() != source.opaque_count():
        raise ValueError("opaque pixel count changed during normalization")
    write_png(selected, output_path)
    return {"raw_size": [source.width, source.height], "raw_bbox": list(raw_bbox) if raw_bbox else None,
            "raw_sha256": raw_sha256,
            "origin_on_canvas": [origin_x, origin_y],
            "selected_bbox": list(selected.alpha_bbox()) if selected.alpha_bbox() else None,
            "selected_sha256": hashlib.sha256(Path(output_path).read_bytes()).hexdigest(),
            "output": str(output_path)}
