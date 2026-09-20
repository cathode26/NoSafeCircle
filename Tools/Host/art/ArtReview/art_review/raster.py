"""Small dependency-free RGBA raster operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

Color = tuple[int, int, int, int]


@dataclass
class RGBAImage:
    """An 8-bit, row-major straight-alpha RGBA image."""

    width: int
    height: int
    pixels: bytearray

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise ValueError("image dimensions must be non-negative")
        if len(self.pixels) != self.width * self.height * 4:
            raise ValueError("RGBA byte count does not match dimensions")

    @classmethod
    def new(cls, width: int, height: int, color: Color = (0, 0, 0, 0)) -> "RGBAImage":
        if any(not 0 <= channel <= 255 for channel in color):
            raise ValueError("color channels must be 0..255")
        return cls(width, height, bytearray(color * (width * height)))

    @classmethod
    def from_rows(cls, rows: Iterable[Iterable[Color]]) -> "RGBAImage":
        materialized = [list(row) for row in rows]
        width = len(materialized[0]) if materialized else 0
        if any(len(row) != width for row in materialized):
            raise ValueError("rows must have equal width")
        data = bytearray()
        for row in materialized:
            for color in row:
                data.extend(color)
        return cls(width, len(materialized), data)

    def copy(self) -> "RGBAImage":
        return RGBAImage(self.width, self.height, bytearray(self.pixels))

    def _offset(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError((x, y))
        return (y * self.width + x) * 4

    def get(self, x: int, y: int) -> Color:
        offset = self._offset(x, y)
        return tuple(self.pixels[offset:offset + 4])  # type: ignore[return-value]

    def get_or_transparent(self, x: int, y: int) -> Color:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return (0, 0, 0, 0)
        return self.get(x, y)

    def set(self, x: int, y: int, color: Color) -> None:
        offset = self._offset(x, y)
        self.pixels[offset:offset + 4] = bytes(color)

    def colors(self) -> Iterator[Color]:
        for offset in range(0, len(self.pixels), 4):
            yield tuple(self.pixels[offset:offset + 4])  # type: ignore[misc]

    def alpha_bbox(self) -> tuple[int, int, int, int] | None:
        """Return inclusive-exclusive alpha bounds, or None for an empty image."""
        xs: list[int] = []
        ys: list[int] = []
        for y in range(self.height):
            for x in range(self.width):
                if self.pixels[(y * self.width + x) * 4 + 3]:
                    xs.append(x)
                    ys.append(y)
        return (min(xs), min(ys), max(xs) + 1, max(ys) + 1) if xs else None

    def opaque_count(self) -> int:
        return sum(self.pixels[offset] > 0 for offset in range(3, len(self.pixels), 4))


def over(foreground: Color, background: Color) -> Color:
    """Composite one straight-alpha color over another."""
    fa = foreground[3] / 255.0
    ba = background[3] / 255.0
    out_a = fa + ba * (1.0 - fa)
    if out_a == 0:
        return (0, 0, 0, 0)
    rgb = [round((foreground[i] * fa + background[i] * ba * (1.0 - fa)) / out_a) for i in range(3)]
    return (rgb[0], rgb[1], rgb[2], round(out_a * 255))


def blit(destination: RGBAImage, source: RGBAImage, left: int, top: int) -> None:
    """Alpha-composite source into destination in place."""
    x0, y0 = max(0, left), max(0, top)
    x1 = min(destination.width, left + source.width)
    y1 = min(destination.height, top + source.height)
    for y in range(y0, y1):
        for x in range(x0, x1):
            destination.set(x, y, over(source.get(x - left, y - top), destination.get(x, y)))


def nearest_zoom(image: RGBAImage, factor: int) -> RGBAImage:
    if factor < 1:
        raise ValueError("zoom must be at least 1")
    result = RGBAImage.new(image.width * factor, image.height * factor)
    for y in range(result.height):
        for x in range(result.width):
            result.set(x, y, image.get(x // factor, y // factor))
    return result


def crop_pad(image: RGBAImage, width: int, height: int, origin_x: int, origin_y: int) -> RGBAImage:
    """Place the source origin at (origin_x, origin_y), clipping transparently."""
    result = RGBAImage.new(width, height)
    blit(result, image, origin_x, origin_y)
    return result


def parse_color(value: str) -> Color:
    text = value.removeprefix("#")
    if len(text) not in (6, 8):
        raise ValueError(f"expected #RRGGBB or #RRGGBBAA, got {value!r}")
    try:
        channels = [int(text[index:index + 2], 16) for index in range(0, len(text), 2)]
    except ValueError as exc:
        raise ValueError(f"invalid color {value!r}") from exc
    if len(channels) == 3:
        channels.append(255)
    return tuple(channels)  # type: ignore[return-value]
