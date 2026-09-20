from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from art_review.gifio import write_gif
from art_review.raster import RGBAImage


def read_subblocks(data: bytes, offset: int) -> tuple[bytes, int]:
    result = bytearray()
    while data[offset]:
        length = data[offset]
        offset += 1
        result.extend(data[offset:offset + length])
        offset += length
    return bytes(result), offset + 1


def lzw_decode(data: bytes, minimum_size: int, expected: int) -> list[int]:
    clear, end = 1 << minimum_size, (1 << minimum_size) + 1
    dictionary = {value: [value] for value in range(clear)}
    next_code = end + 1
    code_size = minimum_size + 1
    bit_offset = 0

    def code(bits: int) -> int:
        nonlocal bit_offset
        value = 0
        for shift in range(bits):
            byte_index, bit_index = divmod(bit_offset + shift, 8)
            if byte_index < len(data) and data[byte_index] & (1 << bit_index):
                value |= 1 << shift
        bit_offset += bits
        return value

    output: list[int] = []
    previous: list[int] | None = None
    while True:
        value = code(code_size)
        if value == clear:
            dictionary = {symbol: [symbol] for symbol in range(clear)}
            next_code, code_size, previous = end + 1, minimum_size + 1, None
            continue
        if value == end:
            break
        if value in dictionary:
            entry = dictionary[value]
        elif value == next_code and previous is not None:
            entry = previous + [previous[0]]
        else:
            raise AssertionError(f"invalid LZW code {value}")
        output.extend(entry)
        if previous is not None and next_code < 4096:
            dictionary[next_code] = previous + [entry[0]]
            next_code += 1
            if next_code == (1 << code_size) and code_size < 12:
                code_size += 1
        previous = entry
    if len(output) != expected:
        raise AssertionError(f"decoded {len(output)} indices, expected {expected}")
    return output


def parse_gif(path: Path) -> dict:
    data = path.read_bytes()
    assert data[:6] == b"GIF89a"
    width, height, packed = struct.unpack_from("<HHB", data, 6)
    offset = 13
    table_count = 1 << ((packed & 7) + 1)
    palette = [tuple(data[offset + index * 3:offset + index * 3 + 3]) for index in range(table_count)]
    offset += table_count * 3
    delays, frames, loop = [], [], False
    current_delay = 0
    while data[offset] != 0x3B:
        marker = data[offset]
        offset += 1
        if marker == 0x21:
            label = data[offset]
            offset += 1
            if label == 0xF9:
                assert data[offset] == 4
                _, current_delay, _ = struct.unpack_from("<BHB", data, offset + 1)
                delays.append(current_delay)
                offset += 6
            elif label == 0xFF:
                block_size = data[offset]
                identifier = data[offset + 1:offset + 1 + block_size]
                offset += block_size + 1
                payload, offset = read_subblocks(data, offset)
                loop = identifier == b"NETSCAPE2.0" and payload[:3] == b"\x01\x00\x00"
            else:
                _, offset = read_subblocks(data, offset)
        elif marker == 0x2C:
            left, top, frame_width, frame_height, descriptor = struct.unpack_from("<HHHHB", data, offset)
            offset += 9
            self_palette = palette
            if descriptor & 0x80:
                count = 1 << ((descriptor & 7) + 1)
                self_palette = [tuple(data[offset + index * 3:offset + index * 3 + 3]) for index in range(count)]
                offset += count * 3
            minimum = data[offset]
            compressed, offset = read_subblocks(data, offset + 1)
            frames.append({"rect": (left, top, frame_width, frame_height), "indices": lzw_decode(compressed, minimum, frame_width * frame_height),
                           "palette": self_palette})
        else:
            raise AssertionError(f"unknown GIF marker {marker:#x}")
    return {"size": (width, height), "delays": delays, "frames": frames, "loop": loop}


class GIFTests(unittest.TestCase):
    def test_animation_structure_and_lzw_round_trip(self) -> None:
        colors = [(0, 0, 0, 255), (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]
        frames = []
        for frame_index in range(3):
            image = RGBAImage.new(40, 20)
            for y in range(image.height):
                for x in range(image.width):
                    image.set(x, y, colors[(x * 3 + y * 5 + frame_index) % len(colors)])
            frames.append(image)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "animation.gif")
            report = write_gif(frames, [30, 30, 40], path)
            parsed = parse_gif(path)
        self.assertEqual(report["delays_centiseconds"], [3, 3, 4])
        self.assertEqual(parsed["delays"], [3, 3, 4])
        self.assertTrue(parsed["loop"])
        self.assertEqual(len(parsed["frames"]), 3)
        for original, decoded in zip(frames, parsed["frames"]):
            decoded_colors = [(*decoded["palette"][index], 255) for index in decoded["indices"]]
            self.assertEqual(decoded_colors, list(original.colors()))

    def test_palette_reduction_reported(self) -> None:
        image = RGBAImage.new(257, 1)
        for x in range(257):
            image.set(x, 0, (x % 256, x // 256, (x * 17) % 256, 255))
        with tempfile.TemporaryDirectory() as directory:
            report = write_gif([image], [10], Path(directory, "reduced.gif"))
        self.assertTrue(report["palette_reduced"])


if __name__ == "__main__":
    unittest.main()
