"""Fixed isometric camera projection and GPU-like sprite sampling."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .raster import Color, RGBAImage

RIGHT = (math.sqrt(0.5), 0.0, math.sqrt(0.5))
UP = (-math.sqrt(0.125), math.sqrt(0.75), math.sqrt(0.125))


def vertical_pixels(resolution: str | int) -> int:
    if isinstance(resolution, int):
        value = resolution
    elif resolution == "1080p":
        value = 1080
    elif resolution == "1440p":
        value = 1440
    else:
        try:
            value = int(resolution)
        except ValueError as exc:
            raise ValueError(f"invalid vertical resolution {resolution!r}") from exc
    if value <= 0:
        raise ValueError("resolution must be positive")
    return value


def pixels_per_world_unit(resolution: str | int) -> float:
    return vertical_pixels(resolution) / 16.0


def camera_facing_scale(canvas_height: int, resolution: str | int = "1080p", *, box_units: float | None = None,
                        scale: float | None = None, ppu: float | None = None) -> float:
    choices = sum(value is not None for value in (box_units, scale, ppu))
    if choices != 1:
        raise ValueError("specify exactly one of box_units, scale, or ppu")
    if scale is not None:
        return scale
    if ppu is not None:
        return pixels_per_world_unit(resolution) / ppu
    assert box_units is not None
    return box_units * pixels_per_world_unit(resolution) / canvas_height


def world_plane_coefficients(ppu: float, local_scale: tuple[float, float], resolution: str | int) -> tuple[float, float, float, float]:
    """Return screen vectors for source +X and source +Y (up)."""
    screen_ppu = pixels_per_world_unit(resolution)
    sx, sy = local_scale
    return (RIGHT[0] * sx / ppu * screen_ppu, -UP[0] * sx / ppu * screen_ppu,
            RIGHT[1] * sy / ppu * screen_ppu, -UP[1] * sy / ppu * screen_ppu)


@dataclass(frozen=True)
class Affine:
    """Map source (u,v-down) offsets about a pivot into screen offsets."""

    ax: float
    ay: float
    bx: float
    by: float
    pivot_u: float
    pivot_v: float
    screen_x: float
    screen_y: float

    def source_at(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        dx, dy = screen_x - self.screen_x, screen_y - self.screen_y
        determinant = self.ax * self.by - self.ay * self.bx
        if abs(determinant) < 1e-12:
            raise ValueError("sprite transform is singular")
        du = (dx * self.by - dy * self.bx) / determinant
        dv = (self.ax * dy - self.ay * dx) / determinant
        return self.pivot_u + du, self.pivot_v + dv

    def screen_at(self, u: float, v: float) -> tuple[float, float]:
        du, dv = u - self.pivot_u, v - self.pivot_v
        return self.screen_x + self.ax * du + self.bx * dv, self.screen_y + self.ay * du + self.by * dv


def camera_facing_affine(scale: float, pivot: tuple[float, float], position: tuple[float, float]) -> Affine:
    return Affine(scale, 0.0, 0.0, scale, pivot[0], pivot[1], position[0], position[1])


def parse_pivot(value: object, width: int, height: int) -> tuple[float, float]:
    """Parse the shared named or custom sprite-pivot representation."""
    if value == "bottom-center":
        return width / 2, float(height)
    if value == "center":
        return width / 2, height / 2
    if isinstance(value, (list, tuple)) and len(value) == 2:
        pivot = float(value[0]), float(value[1])
        if all(math.isfinite(coordinate) for coordinate in pivot):
            return pivot
    raise ValueError("pivot must be bottom-center, center, or [x, y]")


def world_plane_affine(ppu: float, local_scale: tuple[float, float], resolution: str | int,
                       pivot: tuple[float, float], position: tuple[float, float]) -> Affine:
    x_x, x_y, y_x, y_y = world_plane_coefficients(ppu, local_scale, resolution)
    return Affine(x_x, x_y, -y_x, -y_y, pivot[0], pivot[1], position[0], position[1])


def _premultiplied_bilinear(image: RGBAImage, u: float, v: float) -> tuple[float, float, float, float]:
    tx, ty = u - 0.5, v - 0.5
    x0, y0 = math.floor(tx), math.floor(ty)
    fx, fy = tx - x0, ty - y0
    accumulated = [0.0, 0.0, 0.0, 0.0]
    for dy, wy in ((0, 1.0 - fy), (1, fy)):
        for dx, wx in ((0, 1.0 - fx), (1, fx)):
            color = image.get_or_transparent(x0 + dx, y0 + dy)
            weight = wx * wy
            alpha = color[3] / 255.0
            for channel in range(3):
                accumulated[channel] += color[channel] * alpha * weight
            accumulated[3] += color[3] * weight
    return tuple(accumulated)  # type: ignore[return-value]


def _bounds(image: RGBAImage, transform: Affine, margin: int = 0) -> tuple[int, int, int, int]:
    corners = [transform.screen_at(u, v) for u in (0.0, float(image.width)) for v in (0.0, float(image.height))]
    return (math.floor(min(x for x, _ in corners)) - margin,
            math.floor(min(y for _, y in corners)) - margin,
            math.ceil(max(x for x, _ in corners)) + margin,
            math.ceil(max(y for _, y in corners)) + margin)


def render(image: RGBAImage, output_width: int, output_height: int, transform: Affine, sampling: str = "point") -> RGBAImage:
    """Render a transformed sprite into a transparent screen-sized image."""
    if sampling not in ("point", "smooth"):
        raise ValueError("sampling must be point or smooth")
    result = RGBAImage.new(output_width, output_height)
    margin = 0
    if sampling == "smooth":
        longest_texel_step = max(math.hypot(transform.ax, transform.ay),
                                 math.hypot(transform.bx, transform.by))
        margin = math.ceil(0.5 * longest_texel_step + 1.0)
    x0, y0, x1, y1 = _bounds(image, transform, margin)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(output_width, x1), min(output_height, y1)
    if sampling == "point":
        for y in range(y0, y1):
            for x in range(x0, x1):
                u, v = transform.source_at(x + 0.5, y + 0.5)
                if 0 <= u < image.width and 0 <= v < image.height:
                    result.set(x, y, image.get(math.floor(u), math.floor(v)))
        return result
    for y in range(y0, y1):
        for x in range(x0, x1):
            total = [0.0, 0.0, 0.0, 0.0]
            for sub_y in range(4):
                for sub_x in range(4):
                    u, v = transform.source_at(x + (sub_x + 0.5) / 4.0, y + (sub_y + 0.5) / 4.0)
                    sample = _premultiplied_bilinear(image, u, v)
                    for channel in range(4):
                        total[channel] += sample[channel] / 16.0
            alpha = round(total[3])
            if alpha:
                rgb = [max(0, min(255, round(total[channel] * 255.0 / total[3]))) for channel in range(3)]
                result.set(x, y, (rgb[0], rgb[1], rgb[2], max(0, min(255, alpha))))
    return result


def motion_step(world_speed: float, direction: tuple[float, float], fps: float,
                resolution: str | int) -> dict[str, float]:
    """Project a normalized ground-plane direction and return screen motion."""
    dx, dz = direction
    length = math.hypot(dx, dz)
    if length == 0 or fps <= 0:
        raise ValueError("direction and fps must be non-zero")
    dx, dz = dx / length, dz / length
    units_x = RIGHT[0] * dx + RIGHT[2] * dz
    units_up = UP[0] * dx + UP[2] * dz
    ppu = pixels_per_world_unit(resolution)
    per_second_x = units_x * world_speed * ppu
    per_second_y = -units_up * world_speed * ppu
    return {"pixels_per_second_x": per_second_x, "pixels_per_second_y": per_second_y,
            "pixels_per_frame_x": per_second_x / fps, "pixels_per_frame_y": per_second_y / fps,
            "screen_units_per_world_unit": math.hypot(units_x, units_up)}


def down_right_direction() -> tuple[float, float]:
    return (3.0 / math.sqrt(10.0), -1.0 / math.sqrt(10.0))
