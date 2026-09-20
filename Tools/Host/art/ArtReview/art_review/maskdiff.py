"""Proof that image changes are confined to a binary inpaint mask."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .pngio import read_png, write_png
from .raster import Color, RGBAImage, blit, nearest_zoom, over


def pixels_equal(left: Color, right: Color) -> bool:
    return left == right or (left[3] == 0 and right[3] == 0)


def compare(source_path: str | Path, result_path: str | Path, mask_path: str | Path,
            proof_path: str | Path | None = None, zoom: int = 1) -> dict[str, Any]:
    paths = [Path(source_path), Path(result_path), Path(mask_path)]
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name, path in zip(("source", "result", "mask"), paths)}
    source, result, mask = [read_png(path) for path in paths]
    if (source.width, source.height) != (result.width, result.height) or (source.width, source.height) != (mask.width, mask.height):
        raise ValueError("source, result, and mask dimensions must match")
    source_colors = set(source.colors())
    introduced: dict[str, int] = {}
    changed_inside = changed_outside = 0
    changed_image = RGBAImage.new(source.width, source.height)
    for y in range(source.height):
        for x in range(source.width):
            mask_color = mask.get(x, y)
            if mask_color[:3] == (255, 255, 255) and mask_color[3] == 255:
                inside = True
            elif mask_color[:3] == (0, 0, 0) and mask_color[3] == 255:
                inside = False
            else:
                raise ValueError(f"mask pixel ({x}, {y}) is not opaque black or white")
            source_color, result_color = source.get(x, y), result.get(x, y)
            if not pixels_equal(source_color, result_color):
                if inside:
                    changed_inside += 1
                else:
                    changed_outside += 1
                changed_image.set(x, y, (255, 0, 255, 255))
            if result_color not in source_colors:
                key = "#%02x%02x%02x%02x" % result_color
                introduced[key] = introduced.get(key, 0) + 1
    if proof_path is not None:
        panels = [nearest_zoom(image, zoom) for image in (source, result, changed_image)]
        proof = RGBAImage.new(sum(panel.width for panel in panels) + 2 * 4, panels[0].height, (96, 96, 96, 255))
        left = 0
        for panel in panels:
            opaque_panel = RGBAImage.new(panel.width, panel.height, (96, 96, 96, 255))
            blit(opaque_panel, panel, 0, 0)
            blit(proof, opaque_panel, left, 0)
            left += panel.width + 4
        write_png(proof, proof_path)
    return {"changed_inside": changed_inside, "changed_outside": changed_outside,
            "introduced_colors": dict(sorted(introduced.items())),
            "sha256": hashes}
