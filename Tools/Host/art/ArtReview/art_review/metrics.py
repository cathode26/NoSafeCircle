"""Frame continuity and hue-review metrics."""

from __future__ import annotations

import colorsys
import hashlib
from pathlib import Path
from typing import Any, Iterable

from .pngio import read_png
from .raster import Color, RGBAImage


def image_metrics(image: RGBAImage, path: str | Path | None = None) -> dict[str, Any]:
    bbox = image.alpha_bbox()
    result: dict[str, Any] = {
        "size": [image.width, image.height],
        "alpha_bbox": list(bbox) if bbox else None,
        "opaque_pixel_count": image.opaque_count(),
        "distinct_color_count": len(set(image.colors())),
    }
    if path is not None:
        result["path"] = str(path)
        result["sha256"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return result


def frame_metrics(paths: Iterable[str | Path], *, loop: bool = False, opaque_threshold: float = 15.0,
                  width_threshold: int = 8, baseline_threshold: int = 3) -> dict[str, Any]:
    path_list = [Path(path) for path in paths]
    frames = [image_metrics(read_png(path), path) for path in path_list]
    pairs = [(index - 1, index, False) for index in range(1, len(frames))]
    if loop and len(frames) > 1:
        pairs.append((len(frames) - 1, 0, True))
    deltas = []
    for previous_index, current_index, seam in pairs:
        previous, current = frames[previous_index], frames[current_index]
        previous_count, current_count = previous["opaque_pixel_count"], current["opaque_pixel_count"]
        opaque_percent = ((current_count - previous_count) / previous_count * 100.0) if previous_count else (100.0 if current_count else 0.0)
        previous_bbox, current_bbox = previous["alpha_bbox"], current["alpha_bbox"]
        previous_width = previous_bbox[2] - previous_bbox[0] if previous_bbox else 0
        current_width = current_bbox[2] - current_bbox[0] if current_bbox else 0
        previous_bottom = previous_bbox[3] if previous_bbox else 0
        current_bottom = current_bbox[3] if current_bbox else 0
        flags = []
        if abs(opaque_percent) > opaque_threshold:
            flags.append("opaque_change")
        if abs(current_width - previous_width) > width_threshold:
            flags.append("bbox_width_change")
        if abs(current_bottom - previous_bottom) >= baseline_threshold:
            flags.append("baseline_jump")
        deltas.append({"from": previous_index, "to": current_index, "loop_seam": seam,
                       "opaque_change_percent": opaque_percent,
                       "bbox_width_change": current_width - previous_width,
                       "bbox_bottom_change": current_bottom - previous_bottom, "flags": flags})
    return {"frames": frames, "deltas": deltas, "has_outliers": any(delta["flags"] for delta in deltas),
            "thresholds": {"opaque_change_percent": opaque_threshold, "bbox_width_pixels": width_threshold,
                           "baseline_jump_pixels": baseline_threshold}, "loop": loop}


def hue_scan_image(image: RGBAImage, ranges: list[tuple[float, float]], minimum_saturation: float = 0.3,
                   minimum_value: float = 0.3, example_limit: int = 8, *, default_warm: bool = False) -> dict[str, Any]:
    count = 0
    examples: list[str] = []
    seen: set[Color] = set()
    for color in image.colors():
        if color[3] == 0:
            continue
        hue, saturation, value = colorsys.rgb_to_hsv(color[0] / 255, color[1] / 255, color[2] / 255)
        degrees = hue * 360.0
        hue_matches = ((degrees < 70.0 or degrees > 330.0) if default_warm else any(
            (low <= degrees <= high if low <= high else degrees >= low or degrees <= high)
            for low, high in ranges))
        matched = saturation > minimum_saturation and value > minimum_value and hue_matches
        if matched:
            count += 1
            if color not in seen and len(examples) < example_limit:
                examples.append("#%02x%02x%02x%02x" % color)
                seen.add(color)
    return {"matching_pixel_count": count, "example_colors": examples, "total_nontransparent_pixels": image.opaque_count()}


def hue_scan(paths: Iterable[str | Path], ranges: list[tuple[float, float]] | None = None,
             minimum_saturation: float = 0.3, minimum_value: float = 0.3) -> dict[str, Any]:
    default_warm = ranges is None
    selected_ranges = [(0.0, 70.0), (330.0, 360.0)] if ranges is None else ranges
    files = []
    for path_value in paths:
        path = Path(path_value)
        result = hue_scan_image(read_png(path), selected_ranges, minimum_saturation, minimum_value,
                                default_warm=default_warm)
        result["path"] = str(path)
        files.append(result)
    return {"ranges": [list(item) for item in selected_ranges], "minimum_saturation": minimum_saturation,
            "minimum_value": minimum_value, "range_semantics": "strict_default_warm" if default_warm else "inclusive",
            "files": files,
            "matching_pixel_count": sum(item["matching_pixel_count"] for item in files)}
