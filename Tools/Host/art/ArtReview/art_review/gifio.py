"""Deterministic dependency-free animated GIF89a encoder."""

from __future__ import annotations

import math
import struct
from collections import Counter
from pathlib import Path
from typing import Iterable

from .raster import RGBAImage


def _median_cut(colors: Counter[tuple[int, int, int]], limit: int) -> list[tuple[int, int, int]]:
    boxes = [sorted(colors)]
    while len(boxes) < limit:
        candidates = [box for box in boxes if len(box) > 1]
        if not candidates:
            break
        box = max(candidates, key=lambda item: (max(max(color[channel] for color in item) - min(color[channel] for color in item)
                                                         for channel in range(3)), sum(colors[color] for color in item), item))
        boxes.remove(box)
        ranges = [max(color[channel] for color in box) - min(color[channel] for color in box) for channel in range(3)]
        channel = max(range(3), key=lambda index: (ranges[index], -index))
        ordered = sorted(box, key=lambda color: (color[channel], color))
        total = sum(colors[color] for color in ordered)
        running = 0
        split = 1
        for index, color in enumerate(ordered[:-1], 1):
            running += colors[color]
            if running * 2 >= total:
                split = index
                break
        boxes.extend((ordered[:split], ordered[split:]))
    palette = []
    for box in boxes:
        total = sum(colors[color] for color in box)
        palette.append(tuple(round(sum(color[channel] * colors[color] for color in box) / total) for channel in range(3)))
    return sorted(palette)


def _palette_and_indices(frames: list[RGBAImage]) -> tuple[list[tuple[int, int, int]], list[list[int]], bool, int | None]:
    transparent = any(color[3] < 128 for frame in frames for color in frame.colors())
    counts: Counter[tuple[int, int, int]] = Counter(color[:3] for frame in frames for color in frame.colors() if color[3] >= 128)
    limit = 255 if transparent else 256
    reduced = len(counts) > limit
    opaque_palette = sorted(counts) if not reduced else _median_cut(counts, limit)
    palette = ([(0, 0, 0)] if transparent else []) + opaque_palette
    if not palette:
        palette = [(0, 0, 0)]
    exact = {color: index + (1 if transparent else 0) for index, color in enumerate(opaque_palette)}
    nearest_cache: dict[tuple[int, int, int], int] = {}
    indexed_frames = []
    for frame in frames:
        indices = []
        for color in frame.colors():
            if transparent and color[3] < 128:
                indices.append(0)
            elif color[:3] in exact:
                indices.append(exact[color[:3]])
            else:
                rgb = color[:3]
                if rgb not in nearest_cache:
                    nearest_cache[rgb] = min(range(len(opaque_palette)),
                                             key=lambda index: (sum((rgb[channel] - opaque_palette[index][channel]) ** 2 for channel in range(3)), index)) + (1 if transparent else 0)
                indices.append(nearest_cache[rgb])
        indexed_frames.append(indices)
    return palette, indexed_frames, reduced, 0 if transparent else None


def _lzw(indices: list[int], minimum_code_size: int) -> bytes:
    clear = 1 << minimum_code_size
    end = clear + 1
    dictionary = {(value,): value for value in range(clear)}
    next_code = end + 1
    code_size = minimum_code_size + 1
    emitted: list[tuple[int, int]] = [(clear, code_size)]
    if indices:
        current = (indices[0],)
        for value in indices[1:]:
            combined = current + (value,)
            if combined in dictionary:
                current = combined
                continue
            emitted.append((dictionary[current], code_size))
            if next_code < 4096:
                dictionary[combined] = next_code
                next_code += 1
                # The decoder creates an entry one emitted code later than the
                # encoder, so grow only after crossing the current code range.
                if next_code > (1 << code_size) and code_size < 12:
                    code_size += 1
            else:
                emitted.append((clear, code_size))
                dictionary = {(symbol,): symbol for symbol in range(clear)}
                next_code = end + 1
                code_size = minimum_code_size + 1
            current = (value,)
        emitted.append((dictionary[current], code_size))
    emitted.append((end, code_size))
    output = bytearray()
    accumulator = 0
    bit_count = 0
    for code, bits in emitted:
        accumulator |= code << bit_count
        bit_count += bits
        while bit_count >= 8:
            output.append(accumulator & 0xFF)
            accumulator >>= 8
            bit_count -= 8
    if bit_count:
        output.append(accumulator & 0xFF)
    return bytes(output)


def _subblocks(data: bytes) -> bytes:
    output = bytearray()
    for offset in range(0, len(data), 255):
        block = data[offset:offset + 255]
        output.append(len(block))
        output.extend(block)
    output.append(0)
    return bytes(output)


def write_gif(frames: Iterable[RGBAImage], durations_ms: Iterable[int], path: str | Path,
              loop: bool = True) -> dict[str, object]:
    """Write full canvases, restoring transparent frames to background before the next frame."""
    frame_list = list(frames)
    durations = list(durations_ms)
    if not frame_list or len(frame_list) != len(durations):
        raise ValueError("frames and durations must be non-empty and equal length")
    width, height = frame_list[0].width, frame_list[0].height
    if any((frame.width, frame.height) != (width, height) for frame in frame_list):
        raise ValueError("all GIF frames must have equal dimensions")
    if any(color[3] not in (0, 255) for frame in frame_list for color in frame.colors()):
        raise ValueError("GIF supports only opaque or fully transparent pixels; composite a background first")
    palette, indexed, reduced, transparency = _palette_and_indices(frame_list)
    table_bits = max(1, math.ceil(math.log2(len(palette))))
    table_size = 1 << table_bits
    minimum_code_size = max(2, table_bits)
    padded_palette = palette + [(0, 0, 0)] * (table_size - len(palette))
    packed = 0x80 | (7 << 4) | (table_bits - 1)
    output = bytearray(b"GIF89a")
    output.extend(struct.pack("<HHBBB", width, height, packed, 0, 0))
    for color in padded_palette:
        output.extend(color)
    if loop:
        output.extend(b"!\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00")
    delays = []
    disposal_method = 2 if transparency is not None else 1
    for indices, duration in zip(indexed, durations):
        delay = max(0, round(duration / 10))
        delays.append(delay)
        transparency_flag = 1 if transparency is not None else 0
        output.extend(b"!\xf9\x04")
        output.extend(struct.pack("<BHB", (disposal_method << 2) | transparency_flag, delay, transparency or 0))
        output.append(0)
        output.extend(b",\x00\x00\x00\x00" + struct.pack("<HHB", width, height, 0))
        output.append(minimum_code_size)
        output.extend(_subblocks(_lzw(indices, minimum_code_size)))
    output.append(0x3B)
    Path(path).write_bytes(output)
    return {"frame_count": len(frame_list), "durations_ms": durations, "delays_centiseconds": delays,
            "palette_reduced": reduced, "palette_color_count": len(palette), "loop_forever": loop,
            "disposal_method": disposal_method}
