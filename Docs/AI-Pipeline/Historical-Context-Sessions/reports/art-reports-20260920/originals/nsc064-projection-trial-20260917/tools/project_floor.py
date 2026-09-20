"""NSC-064 projection trial: render the committed placeholder floor tile under both projection models.

Usage: python project_floor.py <out_dir>

Model (a), what the game does today: `DoorPrototypeSceneBuilder` paints a 64x32 tile at 64 pixels per unit on a
Tilemap rotated Euler(-90, 0, 0), so the texture lies flat on the world XZ plane and the isometric camera
re-projects it. The tile's art is already a 2:1 diamond (`CreateDiamondPixels(64, 32, ...)`), so it is projected
twice: once by the artist, once by the camera.

Model (b), the camera-plane proposal: the same diamond is drawn in screen space, so one 1x1 ground cell is
exactly one 2:1 diamond and the art's edges land on the cell grid.

Camera: orthographic, Euler(30, -45, 0). Screen basis in world units:
    right = (0.70711, 0, 0.70711)      up = (-0.35355, 0.86603, 0.35355)
A ground point (x, 0, z) lands at screen (0.70711 * (x + z), 0.35355 * (z - x)) world units, so a 1x1 cell is a
diamond 1.41421 wide and 0.70711 tall: the 2:1 shape. At 1080p the camera shows 67.5 pixels per world unit.
"""
import math
import os
import sys

from PIL import Image, ImageDraw

PPU_SCREEN = 67.5           # screen pixels per world unit at 1080p, orthographic size 8
TILE_PPU = 64.0             # the builder's pixels-per-unit for the tile texture
FILL = (80, 76, 70, 255)    # CreateDiamondPixels fill
EDGE = (49, 46, 43, 255)    # CreateDiamondPixels edge
BG = (24, 22, 28, 255)
COS30, SIN30 = math.cos(math.radians(30)), math.sin(math.radians(30))
RIGHT = (0.7071067811865476, 0.0, 0.7071067811865476)
UP = (-0.3535533905932738, 0.8660254037844387, 0.3535533905932738)


def diamond_pixels(w, h):
    """Reproduce CreateDiamondPixels: a filled 2:1 diamond with a one-pixel darker edge."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    for y in range(h):
        for x in range(w):
            d = abs(x - cx) / (w / 2.0) + abs(y - cy) / (h / 2.0)
            if d <= 1.0:
                px[x, y] = EDGE if d > 0.88 else FILL
    return img


def to_screen(x, z):
    sx = RIGHT[0] * x + RIGHT[2] * z
    sy = UP[0] * x + UP[2] * z
    return sx, sy


def render_world_plane(tile, cells, out_size):
    """Model (a): the tile texture lies on the XZ plane, 1 texture pixel = 1/TILE_PPU world units."""
    w, h = out_size
    canvas = Image.new("RGBA", (w, h), BG)
    tw, th = tile.size
    tpx = tile.load()
    ox, oy = w * 0.12, h * 0.55
    for cz in range(cells):
        for cx in range(cells):
            # the cell's texture occupies [cx, cx+1] x [cz, cz+0.5] world units on the ground
            for ty in range(th):
                for tx in range(tw):
                    p = tpx[tx, ty]
                    if p[3] == 0:
                        continue
                    wx = cx * (tw / TILE_PPU) + tx / TILE_PPU
                    wz = cz * (th / TILE_PPU) + ty / TILE_PPU
                    sx, sy = to_screen(wx, wz)
                    px_x = int(ox + sx * PPU_SCREEN)
                    px_y = int(oy - sy * PPU_SCREEN)
                    for dx in range(2):           # 1 texture pixel covers about 1 screen pixel; splat 2x2
                        for dy in range(2):
                            if 0 <= px_x + dx < w and 0 <= px_y + dy < h:
                                canvas.putpixel((px_x + dx, px_y + dy), p)
    return canvas


def render_camera_plane(tile, cells, out_size):
    """Model (b): the same diamond is blitted in screen space, one diamond per 1x1 ground cell."""
    w, h = out_size
    canvas = Image.new("RGBA", (w, h), BG)
    cell_w = 1.4142135623730951 * PPU_SCREEN      # 95.5 px at 1080p
    cell_h = 0.7071067811865476 * PPU_SCREEN      # 47.7 px
    scaled = tile.resize((int(round(cell_w)), int(round(cell_h))), Image.NEAREST)
    ox, oy = w * 0.12, h * 0.55
    for cz in range(cells):
        for cx in range(cells):
            sx, sy = to_screen(cx, cz)
            px_x = int(round(ox + sx * PPU_SCREEN - scaled.size[0] / 2))
            px_y = int(round(oy - sy * PPU_SCREEN - scaled.size[1] / 2))
            canvas.alpha_composite(scaled, (px_x, px_y))
    return canvas


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    tile = diamond_pixels(64, 32)
    tile.resize((64 * 6, 32 * 6), Image.NEAREST).save(os.path.join(out, "placeholder_tile_6x.png"))
    size = (760, 520)
    a = render_world_plane(tile, 7, size)
    b = render_camera_plane(tile, 7, size)
    sheet = Image.new("RGBA", (size[0] * 2 + 12, size[1] + 26), BG)
    dr = ImageDraw.Draw(sheet)
    dr.text((8, 6), "(a) today: 64x32 diamond on the world plane, camera re-projects it", fill=(235, 200, 200, 255))
    dr.text((size[0] + 20, 6), "(b) camera-plane: one diamond per 1x1 ground cell", fill=(200, 235, 205, 255))
    sheet.alpha_composite(a, (0, 22))
    sheet.alpha_composite(b, (size[0] + 12, 22))
    sheet.convert("RGB").save(os.path.join(out, "projection_comparison.png"))
    print("wrote projection_comparison.png and placeholder_tile_6x.png")
    print(f"model (b) cell size on screen at 1080p: {1.4142135623730951 * PPU_SCREEN:.1f} x "
          f"{0.7071067811865476 * PPU_SCREEN:.1f} px")


main()
