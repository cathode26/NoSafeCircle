from __future__ import annotations

import colorsys
import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from art_review.camera import camera_facing_affine, render
from art_review.cli import _motion_scene, main
from art_review.font import glyph
from art_review.gifio import write_gif
from art_review.metrics import hue_scan
from art_review.pngio import PNGError, read_png, write_png
from art_review.raster import RGBAImage
from art_review.sheets import game_scale_sheet


def _read_subblocks(data: bytes, offset: int) -> tuple[bytes, int]:
    result = bytearray()
    while data[offset]:
        length = data[offset]
        offset += 1
        result.extend(data[offset:offset + length])
        offset += length
    return bytes(result), offset + 1


def _lzw_decode(data: bytes, minimum_size: int, expected: int) -> list[int]:
    clear, end = 1 << minimum_size, (1 << minimum_size) + 1
    dictionary = {value: [value] for value in range(clear)}
    next_code = end + 1
    code_size = minimum_size + 1
    bit_offset = 0

    def read_code(bits: int) -> int:
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
        value = read_code(code_size)
        if value == clear:
            dictionary = {symbol: [symbol] for symbol in range(clear)}
            next_code, code_size, previous = end + 1, minimum_size + 1, None
            continue
        if value == end:
            break
        entry = dictionary.get(value)
        if entry is None:
            if value != next_code or previous is None:
                raise AssertionError(f"invalid LZW code {value}")
            entry = previous + [previous[0]]
        output.extend(entry)
        if previous is not None and next_code < 4096:
            dictionary[next_code] = previous + [entry[0]]
            next_code += 1
            if next_code == 1 << code_size and code_size < 12:
                code_size += 1
        previous = entry
    if len(output) != expected:
        raise AssertionError(f"decoded {len(output)} indices, expected {expected}")
    return output


def _composited_gif_frames(path: Path) -> list[list[tuple[int, int, int, int]]]:
    """Decode full-canvas frames while applying GIF disposal before each frame."""
    data = path.read_bytes()
    width, height, packed, background_index = struct.unpack_from("<HHBB", data, 6)
    offset = 13
    table_count = 1 << ((packed & 7) + 1)
    palette = [tuple(data[offset + index * 3:offset + index * 3 + 3]) for index in range(table_count)]
    offset += table_count * 3
    canvas = [(0, 0, 0, 0)] * (width * height)
    completed: list[list[tuple[int, int, int, int]]] = []
    pending_disposal = 0
    pending_rect = (0, 0, width, height)
    pending_transparent_index: int | None = None
    control = (0, None)
    while data[offset] != 0x3B:
        marker = data[offset]
        offset += 1
        if marker == 0x21:
            label = data[offset]
            offset += 1
            if label == 0xF9:
                block_size = data[offset]
                packed_control, _, transparent_index = struct.unpack_from("<BHB", data, offset + 1)
                control = (packed_control >> 2 & 7, transparent_index if packed_control & 1 else None)
                offset += block_size + 2
            else:
                block_size = data[offset]
                offset += block_size + 1
                _, offset = _read_subblocks(data, offset)
            continue
        if marker != 0x2C:
            raise AssertionError(f"unexpected GIF marker {marker:#x}")
        if completed and pending_disposal == 2:
            left, top, frame_width, frame_height = pending_rect
            background = (*palette[background_index], 255)
            for y in range(top, top + frame_height):
                for x in range(left, left + frame_width):
                    canvas[y * width + x] = background
            if pending_transparent_index == background_index:
                for y in range(top, top + frame_height):
                    for x in range(left, left + frame_width):
                        canvas[y * width + x] = (0, 0, 0, 0)
        left, top, frame_width, frame_height, descriptor = struct.unpack_from("<HHHHB", data, offset)
        offset += 9
        frame_palette = palette
        if descriptor & 0x80:
            count = 1 << ((descriptor & 7) + 1)
            frame_palette = [tuple(data[offset + index * 3:offset + index * 3 + 3]) for index in range(count)]
            offset += count * 3
        minimum_size = data[offset]
        compressed, offset = _read_subblocks(data, offset + 1)
        indices = _lzw_decode(compressed, minimum_size, frame_width * frame_height)
        disposal, transparent_index = control
        for frame_y in range(frame_height):
            for frame_x in range(frame_width):
                index = indices[frame_y * frame_width + frame_x]
                if index != transparent_index:
                    canvas[(top + frame_y) * width + left + frame_x] = (*frame_palette[index], 255)
        completed.append(list(canvas))
        pending_disposal = disposal
        pending_rect = (left, top, frame_width, frame_height)
        pending_transparent_index = transparent_index
    return completed


class ReviewFixRegressionTests(unittest.TestCase):
    def test_outputs_never_overwrite_inputs_or_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame = root / "frame.png"
            result = root / "result.png"
            mask = root / "mask.png"
            write_png(RGBAImage.new(2, 1, (255, 0, 0, 255)), frame)
            write_png(RGBAImage.new(2, 1, (0, 255, 0, 255)), result)
            write_png(RGBAImage.new(2, 1, (255, 255, 255, 255)), mask)
            original = frame.read_bytes()
            manifest = root / "game.json"
            manifest.write_text(json.dumps({"panel_width": 8, "panel_height": 8, "sprites": [
                {"path": str(frame), "mode": "camera-facing", "scale": 1, "sampling": "point"}
            ]}), encoding="utf-8")
            shared_output = root / "same-output"
            with redirect_stderr(io.StringIO()):
                gamescale_code = main(["gamescale", "--manifest", str(manifest), "--output", str(shared_output),
                                       "--json", str(shared_output)])
                mask_code = main(["mask-diff", "--source", str(frame), "--result", str(result),
                                  "--mask", str(mask), "--output", str(frame), "--json", str(root / "proof.json")])
            self.assertEqual((gamescale_code, mask_code), (2, 2))
            self.assertFalse(shared_output.exists())
            self.assertEqual(frame.read_bytes(), original)
            self.assertFalse((root / "proof.json").exists())

    def test_smooth_sampling_conserves_enlarged_texel_alpha(self) -> None:
        texture = RGBAImage.new(1, 1, (255, 255, 255, 255))
        rendered = render(texture, 40, 40, camera_facing_affine(10, (0, 0), (15, 15)), "smooth")
        expected_alpha = 255 * 10 * 10
        actual_alpha = sum(color[3] for color in rendered.colors())
        self.assertLessEqual(abs(actual_alpha - expected_alpha) / expected_alpha, 0.01)

    def test_transparent_gif_frames_clear_previous_canvas(self) -> None:
        first = RGBAImage.new(3, 1)
        first.set(0, 0, (255, 0, 0, 255))
        second = RGBAImage.new(3, 1)
        second.set(2, 0, (0, 255, 0, 255))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "disposal.gif")
            write_gif([first, second], [20, 20], path)
            frames = _composited_gif_frames(path)
        self.assertEqual(frames[0][0], (255, 0, 0, 255))
        self.assertEqual(frames[1][0], (0, 0, 0, 0))
        self.assertEqual(frames[1][2], (0, 255, 0, 255))

    def test_world_grid_rounds_each_line_independently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sprite = Path(directory, "empty.png")
            write_png(RGBAImage.new(1, 1), sprite)
            positions = {}
            for resolution, width in (("1080p", 300), ("1440p", 200)):
                sheet, _ = game_scale_sheet({"resolution": resolution, "panel_width": width,
                                             "panel_height": 20, "gap": 1, "grid": True,
                                             "background": "#000000", "grid_color": "#ffffff",
                                             "sprites": [{"path": str(sprite), "mode": "camera-facing",
                                                          "scale": 1, "sampling": "point", "position": [0, 0]}]})
                positions[resolution] = [x for x in range(width) if sheet.get(x + 1, 1) == (255, 255, 255, 255)]
        self.assertEqual(positions["1080p"][:5], [0, 68, 135, 202, 270])
        self.assertEqual(positions["1440p"][:3], [0, 90, 180])

    def test_ledger_rejects_unknown_missing_and_duplicate_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init = {"type": "init", "timestamp_utc": "now", "job": "review", "cap": None,
                    "remaining": 10, "used": 0}
            invalid_events = (
                ({"type": "entyr", "timestamp_utc": "now"}, 2),
                ({"type": "entry", "timestamp_utc": "now", "tool": "generate", "pixellab_id": "id",
                  "provisional": False, "note": None}, 2),
                (dict(init), 2),
            )
            for index, (bad_event, bad_line) in enumerate(invalid_events):
                with self.subTest(index=index):
                    ledger = root / f"bad-{index}.jsonl"
                    ledger.write_text("\n".join(json.dumps(event) for event in (init, bad_event)) + "\n", encoding="utf-8")
                    report = root / f"bad-{index}.json"
                    errors = io.StringIO()
                    with redirect_stderr(errors):
                        code = main(["ledger", "summary", "--ledger", str(ledger), "--json", str(report)])
                    self.assertEqual(code, 2)
                    self.assertIn(f"line {bad_line}", errors.getvalue())
                    self.assertFalse(report.exists())
            malformed = root / "bad-0.jsonl"
            before = malformed.read_bytes()
            with redirect_stderr(io.StringIO()):
                add_code = main(["ledger", "add", "--ledger", str(malformed), "--tool", "generate",
                                 "--id", "new", "--reported-cost", "1"])
            self.assertEqual(add_code, 2)
            self.assertEqual(malformed.read_bytes(), before)
            valid = root / "valid.jsonl"
            valid.write_text(json.dumps(init) + "\n", encoding="utf-8")
            valid_before = valid.read_bytes()
            with redirect_stderr(io.StringIO()):
                balance_code = main(["ledger", "balance", "--ledger", str(valid), "--remaining", "-1", "--used", "0"])
                cost_code = main(["ledger", "add", "--ledger", str(valid), "--tool", "generate",
                                  "--id", "nan", "--reported-cost", "nan"])
            self.assertEqual((balance_code, cost_code), (2, 2))
            self.assertEqual(valid.read_bytes(), valid_before)

    def test_motion_scene_accepts_custom_top_left_pivot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sprite = Path(directory, "sprite.png")
            write_png(RGBAImage.new(1, 1, (255, 0, 0, 255)), sprite)
            frames, _ = _motion_scene([str(sprite)], {"size": [2, 2], "background_color": "#00000000",
                                                       "start": [0, 0], "end": [0, 0], "screen_speed": 1,
                                                       "mode": "camera-facing", "scale": 1, "pivot": [0, 0]})
        self.assertEqual(frames[0].get(0, 0), (255, 0, 0, 255))

    def test_png_rejects_trailing_data_after_iend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "trailing.png")
            write_png(RGBAImage.new(1, 1, (1, 2, 3, 255)), path)
            path.write_bytes(path.read_bytes() + b"GARBAGE")
            with self.assertRaisesRegex(PNGError, "trailing"):
                read_png(path)

    def test_default_hue_scan_uses_strict_warm_endpoints(self) -> None:
        colors = [(210, 252, 0, 255), (252, 0, 126, 255),
                  (202, 240, 0, 255), (240, 0, 118, 255)]
        expected_hues = [70.0, 330.0, 69.5, 330.5]
        for color, expected in zip(colors, expected_hues):
            hue = colorsys.rgb_to_hsv(*(channel / 255 for channel in color[:3]))[0] * 360
            self.assertAlmostEqual(hue, expected, places=9)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "hues.png")
            write_png(RGBAImage.from_rows([colors]), path)
            default = hue_scan([path])
            inclusive = hue_scan([path], [(70, 70), (330, 330)])
        self.assertEqual(default["matching_pixel_count"], 2)
        # colorsys represents this RGB construction for 70 degrees just above
        # 70.0, while the 330-degree construction is exact.
        self.assertEqual(inclusive["matching_pixel_count"], 1)

    def test_font_covers_every_printable_ascii_character(self) -> None:
        question = glyph("?")
        for codepoint in range(32, 127):
            character = chr(codepoint)
            if character != "?":
                with self.subTest(character=character):
                    self.assertNotEqual(glyph(character), question)
        self.assertTrue(all(row == "00000" for row in glyph(" ")))
        self.assertNotEqual(glyph("("), glyph(")"))


if __name__ == "__main__":
    unittest.main()
