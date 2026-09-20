"""Expected-appearance reference for the Game Agent's Tilemap-versus-sprites render.

Usage: python wall_reference.py <kit_dir> <out_dir>

This is the picture a **correct camera-facing wall run** must produce. The Game Agent renders two Unity cases to
RenderTextures at the same parameters and diffs them against this: per-tile billboarded sprites as the control,
and a Tilemap with `Orientation.Custom` set before painting as the case under test.

Parameters, from the Game Agent's own reading of the committed builder, not assumed:
  camera rotation Euler(30, -45, 0), orthographic, orthographicSize 8, position (10, 10, -10)
  1920 x 1080, transparent background, nothing else in frame
  wall run of 8 cells, first cell at world (0, 0, 0), running along +X, one cell per world unit
  grid cell size (1, 0.5, 1), tileAnchor (0, 0, 0)
  wall art: the 96 px kit, piece index 1 (`sides: N`)

Camera basis used, which matches Euler(30, -45, 0):
  right = (0.70711, 0, 0.70711)   up = (-0.35355, 0.86603, 0.35355)   forward = (-0.61237, -0.5, 0.61237)
Screen position of a world point p, orthographic:
  x = 960 + dot(p - campos, right) * 67.5        y = 540 - dot(p - campos, up) * 67.5
with 67.5 = 1080 / (2 * orthographicSize).

**Placement rule, which the Unity side must match exactly:** each piece is drawn at its native pixel size with
its **canvas centre** at the cell's projected screen position, rounded to the nearest whole pixel. Cells are drawn
in ascending x, so nearer cells overlap farther ones.
"""
import json
import os
import sys

from PIL import Image

RIGHT = (0.7071067811865476, 0.0, 0.7071067811865476)
UP = (-0.3535533905932738, 0.8660254037844387, 0.3535533905932738)
CAM = (10.0, 10.0, -10.0)
ORTHO = float(os.environ.get("NSC_ORTHO", "8.0"))
W, H = 1920, 1080
PPU = H / (2 * ORTHO)          # 67.5
CELLS = 8
PIECE_INDEX = 1                # sides: N


def project(p):
    d = (p[0] - CAM[0], p[1] - CAM[1], p[2] - CAM[2])
    sx = d[0] * RIGHT[0] + d[1] * RIGHT[1] + d[2] * RIGHT[2]
    sy = d[0] * UP[0] + d[1] * UP[1] + d[2] * UP[2]
    return 960.0 + sx * PPU, 540.0 - sy * PPU


def kit_piece(kit_dir, index):
    for f in sorted(os.listdir(kit_dir)):
        if f.endswith(f"_{index}.png"):
            return f, Image.open(os.path.join(kit_dir, f)).convert("RGBA")
    raise FileNotFoundError(f"piece {index} not in {kit_dir}")


def main():
    kit_dir, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    fname, piece = kit_piece(kit_dir, PIECE_INDEX)
    pw, ph = piece.size
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    placements = []
    for i in range(CELLS):                      # ascending x: nearer cells drawn last
        world = (float(i), 0.0, 0.0)
        cx, cy = project(world)
        px = int(round(cx - pw / 2.0))
        py = int(round(cy - ph / 2.0))
        canvas.alpha_composite(piece, (px, py))
        placements.append({"cell": i, "world": world, "projected_px": [round(cx, 3), round(cy, 3)],
                           "blit_top_left": [px, py]})
    tag = f"ortho{ORTHO:g}".replace(".", "p")
    canvas.save(os.path.join(out, f"wall_reference_1920x1080_{tag}.png"))
    bb = canvas.getchannel("A").getbbox()
    meta = {
        "purpose": "expected appearance of a correct camera-facing 8-cell wall run",
        "camera": {"rotation_euler": [30, -45, 0], "orthographic_size": ORTHO, "position": list(CAM),
                   "resolution": [W, H], "pixels_per_world_unit": PPU},
        "basis": {"right": list(RIGHT), "up": list(UP), "forward": [-0.61237, -0.5, 0.61237]},
        "grid": {"cell_size": [1, 0.5, 1], "tile_anchor": [0, 0, 0], "run_axis": "+X", "cells": CELLS},
        "art": {"kit_piece_file": fname, "piece_index": PIECE_INDEX, "role": "sides: N",
                "native_size": [pw, ph], "scaling": "none - native pixels"},
        "placement_rule": "piece canvas centre at the cell's projected screen position, rounded to whole pixels; "
                          "cells drawn in ascending x",
        "origin_on_screen": [round(project((0, 0, 0))[0], 3), round(project((0, 0, 0))[1], 3)],
        "content_bbox": list(bb) if bb else None,
        "placements": placements,
    }
    json.dump(meta, open(os.path.join(out, f"wall_reference_{tag}.json"), "w", encoding="utf-8"), indent=1)
    print(f"wrote wall_reference_1920x1080_{tag}.png and wall_reference_{tag}.json  (orthographic {ORTHO}, {PPU:.4f} px per unit)")
    print(f"piece {fname} native {pw}x{ph}; world origin lands at screen {meta['origin_on_screen']}")
    print(f"content bbox {bb}")
    for p in placements:
        print(f"  cell {p['cell']}: world {p['world']} -> screen {p['projected_px']} -> blit {p['blit_top_left']}")


main()
