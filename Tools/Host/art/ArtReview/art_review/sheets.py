"""Contact sheets and fixed-camera game-scale review sheets."""

from __future__ import annotations

from typing import Any

from .camera import camera_facing_affine, camera_facing_scale, parse_pivot, pixels_per_world_unit, render, world_plane_affine
from .font import draw_text
from .pngio import read_png
from .raster import RGBAImage, blit, nearest_zoom, parse_color


def contact_sheet(rows: list[list[dict[str, Any]]], zoom: int = 1, gap: int = 8,
                  background: str = "#1d1631", cell_background: str = "#2a2342",
                  header: str = "") -> RGBAImage:
    """Lay out a grid using per-column max widths and per-row max image heights."""
    loaded = [[(read_png(cell["path"]), str(cell.get("caption", ""))) for cell in row] for row in rows]
    column_count = max((len(row) for row in loaded), default=0)
    column_widths = [max((row[index][0].width * zoom for row in loaded if index < len(row)), default=0) for index in range(column_count)]
    row_heights = [max((image.height * zoom for image, _ in row), default=0) + 10 for row in loaded]
    header_height = 12 if header else 0
    width = sum(column_widths) + gap * (column_count + 1)
    height = sum(row_heights) + gap * (len(rows) + 1) + header_height
    sheet = RGBAImage.new(max(1, width), max(1, height), parse_color(background))
    if header:
        draw_text(sheet, gap, 2, header)
    y = gap + header_height
    for row_index, row in enumerate(loaded):
        x = gap
        for column_index, (image, caption) in enumerate(row):
            cell_width, cell_height = column_widths[column_index], row_heights[row_index]
            cell = RGBAImage.new(cell_width, cell_height, parse_color(cell_background))
            enlarged = nearest_zoom(image, zoom)
            blit(cell, enlarged, (cell_width - enlarged.width) // 2, (cell_height - 10 - enlarged.height) // 2)
            draw_text(cell, max(0, (cell_width - len(caption) * 6 + 1) // 2), cell_height - 8, caption)
            blit(sheet, cell, x, y)
            x += cell_width + gap
        y += row_heights[row_index] + gap
    return sheet


def game_scale_sheet(manifest: dict[str, Any]) -> tuple[RGBAImage, list[dict[str, Any]]]:
    resolution = manifest.get("resolution", "1080p")
    panel_width = int(manifest.get("panel_width", 320))
    panel_height = int(manifest.get("panel_height", 320))
    gap = int(manifest.get("gap", 8))
    footer = str(manifest.get("footer", ""))
    sprites = manifest["sprites"]
    sheet_height = panel_height + 24 + (10 if footer else 0)
    sheet = RGBAImage.new(len(sprites) * panel_width + (len(sprites) + 1) * gap,
                          sheet_height, parse_color(manifest.get("background", "#1d1631")))
    reports = []
    for index, spec in enumerate(sprites):
        panel = RGBAImage.new(panel_width, panel_height, parse_color(manifest.get("background", "#1d1631")))
        grid_every = spec.get("grid", manifest.get("grid", False))
        if grid_every:
            screen_pixels_per_unit = pixels_per_world_unit(resolution)
            grid_color = parse_color(manifest.get("grid_color", "#2a2342"))
            world_units = int(max(panel_width, panel_height) / screen_pixels_per_unit) + 2
            # Python round intentionally gives half-even positions (for example 202.5 -> 202).
            for coordinate in (round(index * screen_pixels_per_unit) for index in range(world_units)):
                if coordinate < panel_width:
                    for y in range(panel_height): panel.set(coordinate, y, grid_color)
                if coordinate < panel_height:
                    for x in range(panel_width): panel.set(x, coordinate, grid_color)
        image = read_png(spec["path"])
        pivot = parse_pivot(spec.get("pivot", "bottom-center"), image.width, image.height)
        base_position = spec.get("position", [panel_width / 2, panel_height * 0.8])
        phase = spec.get("phase", [0, 0])
        position = (float(base_position[0]) + float(phase[0]), float(base_position[1]) + float(phase[1]))
        if spec["mode"] == "camera-facing":
            scale = camera_facing_scale(image.height, resolution, box_units=spec.get("box_units"),
                                        scale=spec.get("scale"), ppu=spec.get("ppu"))
            transform = camera_facing_affine(scale, pivot, position)
        elif spec["mode"] == "world-plane":
            transform = world_plane_affine(float(spec["ppu"]), tuple(spec.get("local_scale", [1, 1])),
                                           resolution, pivot, position)
        else:
            raise ValueError(f"unknown sprite mode {spec['mode']!r}")
        sprite_layer = render(image, panel_width, panel_height, transform, spec.get("sampling", "point"))
        blit(panel, sprite_layer, 0, 0)
        left = gap + index * (panel_width + gap)
        blit(sheet, panel, left, 0)
        draw_text(sheet, left, panel_height + 3, str(spec.get("label", "")))
        bbox = sprite_layer.alpha_bbox()
        reports.append({"path": spec["path"], "label": spec.get("label", ""),
                        "alpha_bbox": list(bbox) if bbox else None, "opaque_pixel_count": sprite_layer.opaque_count()})
    if footer:
        draw_text(sheet, gap, panel_height + 14, footer)
    return sheet, reports
