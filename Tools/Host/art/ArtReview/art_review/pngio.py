"""Strict stdlib PNG reader and RGBA writer."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .raster import RGBAImage

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PNGError(ValueError):
    """Raised for an unsupported or malformed PNG."""


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    distances = (abs(estimate - left), abs(estimate - up), abs(estimate - upper_left))
    return (left, up, upper_left)[distances.index(min(distances))]


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def read_png(path: str | Path) -> RGBAImage:
    data = Path(path).read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise PNGError("not a PNG file")
    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    seen_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise PNGError("truncated PNG chunk")
        payload = data[offset + 8:offset + 8 + length]
        expected = struct.unpack_from(">I", data, offset + 8 + length)[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != expected:
            raise PNGError(f"bad CRC in {kind.decode('ascii', 'replace')} chunk")
        chunks.append((kind, payload))
        offset = end
        if kind == b"IEND":
            seen_iend = True
            break
    if not seen_iend:
        raise PNGError("missing IEND chunk")
    if offset != len(data):
        raise PNGError("trailing data after IEND chunk")
    ihdrs = [payload for kind, payload in chunks if kind == b"IHDR"]
    if len(ihdrs) != 1 or len(ihdrs[0]) != 13:
        raise PNGError("PNG must contain one valid IHDR")
    width, height, depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", ihdrs[0])
    if depth != 8:
        raise PNGError("only 8-bit PNG images are supported")
    if interlace != 0:
        raise PNGError("interlaced PNG images are not supported")
    if compression != 0 or filtering != 0 or width == 0 or height == 0:
        raise PNGError("unsupported or invalid PNG header")
    channels_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    if color_type not in channels_by_type:
        raise PNGError(f"unsupported PNG color type {color_type}")
    channels = channels_by_type[color_type]
    try:
        raw = zlib.decompress(b"".join(payload for kind, payload in chunks if kind == b"IDAT"))
    except zlib.error as exc:
        raise PNGError(f"invalid compressed image data: {exc}") from exc
    stride = width * channels
    if len(raw) != height * (stride + 1):
        raise PNGError("decompressed PNG data has the wrong length")
    rows: list[bytearray] = []
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        encoded = raw[cursor:cursor + stride]
        cursor += stride
        previous = rows[-1] if rows else bytearray(stride)
        row = bytearray(stride)
        for index, value in enumerate(encoded):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                predictor = _paeth(left, up, upper_left)
            else:
                raise PNGError(f"unsupported PNG filter {filter_type}")
            row[index] = (value + predictor) & 0xFF
        rows.append(row)
    palette_data = next((payload for kind, payload in chunks if kind == b"PLTE"), None)
    transparency = next((payload for kind, payload in chunks if kind == b"tRNS"), b"")
    palette: list[tuple[int, int, int, int]] = []
    if color_type == 3:
        if palette_data is None or len(palette_data) % 3:
            raise PNGError("palette PNG lacks a valid PLTE chunk")
        for index in range(len(palette_data) // 3):
            alpha = transparency[index] if index < len(transparency) else 255
            palette.append((*palette_data[index * 3:index * 3 + 3], alpha))
    output = bytearray()
    transparent_gray = struct.unpack(">H", transparency)[0] & 0xFF if color_type == 0 and len(transparency) == 2 else None
    transparent_rgb = tuple(struct.unpack(">HHH", transparency)) if color_type == 2 and len(transparency) == 6 else None
    for row in rows:
        for x in range(width):
            sample = row[x * channels:(x + 1) * channels]
            if color_type == 0:
                alpha = 0 if transparent_gray == sample[0] else 255
                output.extend((sample[0], sample[0], sample[0], alpha))
            elif color_type == 2:
                alpha = 0 if transparent_rgb == tuple(sample) else 255
                output.extend((*sample, alpha))
            elif color_type == 3:
                if sample[0] >= len(palette):
                    raise PNGError("palette index is outside PLTE")
                output.extend(palette[sample[0]])
            elif color_type == 4:
                output.extend((sample[0], sample[0], sample[0], sample[1]))
            else:
                output.extend(sample)
    return RGBAImage(width, height, output)


def write_png(image: RGBAImage, path: str | Path) -> None:
    """Write a non-interlaced 8-bit RGBA PNG using filter 0."""
    raw = bytearray()
    stride = image.width * 4
    for y in range(image.height):
        raw.append(0)
        raw.extend(image.pixels[y * stride:(y + 1) * stride])
    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    encoded = PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _chunk(b"IEND", b"")
    Path(path).write_bytes(encoded)
