from __future__ import annotations

import math
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from art_review.camera import (
    RIGHT,
    UP,
    camera_facing_affine,
    camera_facing_scale,
    down_right_direction,
    motion_step,
    render,
    world_plane_affine,
    world_plane_coefficients,
)
from art_review.pngio import PNGError, PNG_SIGNATURE, read_png, write_png
from art_review.raster import RGBAImage


def chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


class PNGTests(unittest.TestCase):
    def test_rgba_round_trip(self) -> None:
        image = RGBAImage.from_rows([[(255, 0, 0, 255), (0, 2, 3, 4)], [(5, 6, 7, 8), (9, 10, 11, 0)]])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "roundtrip.png")
            write_png(image, path)
            decoded = read_png(path)
        self.assertEqual((decoded.width, decoded.height), (2, 2))
        self.assertEqual(decoded.pixels, image.pixels)

    def test_palette_transparency_decode(self) -> None:
        header = struct.pack(">IIBBBBB", 2, 1, 8, 3, 0, 0, 0)
        data = (PNG_SIGNATURE + chunk(b"IHDR", header) + chunk(b"PLTE", bytes((10, 20, 30, 40, 50, 60)))
                + chunk(b"tRNS", bytes((0, 128))) + chunk(b"IDAT", zlib.compress(bytes((0, 0, 1)))) + chunk(b"IEND", b""))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "palette.png")
            path.write_bytes(data)
            image = read_png(path)
        self.assertEqual(image.get(0, 0), (10, 20, 30, 0))
        self.assertEqual(image.get(1, 0), (40, 50, 60, 128))

    def test_interlace_and_crc_rejected(self) -> None:
        header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 1)
        interlaced = PNG_SIGNATURE + chunk(b"IHDR", header) + chunk(b"IEND", b"")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "bad.png")
            path.write_bytes(interlaced)
            with self.assertRaisesRegex(PNGError, "interlaced"):
                read_png(path)
            damaged = bytearray(interlaced)
            damaged[29] ^= 1
            path.write_bytes(damaged)
            with self.assertRaisesRegex(PNGError, "CRC"):
                read_png(path)

    def test_all_filter_types_and_non_rgba_color_types(self) -> None:
        def filtered_row(values: bytes, previous: bytes, channels: int, filter_type: int) -> bytes:
            encoded = bytearray()
            for index, value in enumerate(values):
                left = values[index - channels] if index >= channels else 0
                up = previous[index] if previous else 0
                upper_left = previous[index - channels] if previous and index >= channels else 0
                if filter_type == 0:
                    predictor = 0
                elif filter_type == 1:
                    predictor = left
                elif filter_type == 2:
                    predictor = up
                elif filter_type == 3:
                    predictor = (left + up) // 2
                else:
                    estimate = left + up - upper_left
                    options = (left, up, upper_left)
                    predictor = options[min(range(3), key=lambda option: abs(estimate - options[option]))]
                encoded.append((value - predictor) & 0xFF)
            return bytes((filter_type,)) + bytes(encoded)

        first = bytes((10, 20, 30, 255, 40, 50, 60, 128))
        second = bytes((70, 80, 90, 64, 100, 110, 120, 0))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filter_type in range(5):
                header = struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)
                raw = filtered_row(first, b"", 4, filter_type) + filtered_row(second, first, 4, filter_type)
                path = root / f"filter-{filter_type}.png"
                path.write_bytes(PNG_SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
                self.assertEqual(read_png(path).pixels, bytearray(first + second))
            cases = [
                (0, bytes((7,)), (7, 7, 7, 255)),
                (2, bytes((7, 8, 9)), (7, 8, 9, 255)),
                (4, bytes((7, 99)), (7, 7, 7, 99)),
            ]
            for color_type, sample, expected in cases:
                header = struct.pack(">IIBBBBB", 1, 1, 8, color_type, 0, 0, 0)
                path = root / f"type-{color_type}.png"
                path.write_bytes(PNG_SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00" + sample)) + chunk(b"IEND", b""))
                self.assertEqual(read_png(path).get(0, 0), expected)


class CameraTests(unittest.TestCase):
    def test_basis_coefficients_and_scales(self) -> None:
        self.assertAlmostEqual(RIGHT[0], 0.70711, places=5)
        self.assertAlmostEqual(RIGHT[2], 0.70711, places=5)
        self.assertAlmostEqual(UP[0], -0.35355, places=5)
        self.assertAlmostEqual(UP[1], 0.86603, places=5)
        self.assertAlmostEqual(UP[2], 0.35355, places=5)
        coefficients = world_plane_coefficients(180, (1, 2), "1080p")
        for actual, expected in zip(coefficients, (0.26517, 0.13258, 0.0, -0.64952)):
            self.assertAlmostEqual(actual, expected, places=5)
        self.assertEqual(camera_facing_scale(180, "1080p", box_units=2), 0.75)
        self.assertEqual(camera_facing_scale(128, "1080p", box_units=2), 1.0546875)
        self.assertEqual(camera_facing_scale(180, "1440p", box_units=2), 1.0)
        self.assertEqual(camera_facing_scale(128, "1440p", box_units=2), 1.40625)

    def test_point_sampling_hand_cases(self) -> None:
        texture = RGBAImage.from_rows([[(255, 0, 0, 255), (0, 0, 255, 255)]])
        direct = render(texture, 3, 1, camera_facing_affine(1, (0, 0), (0, 0)), "point")
        self.assertEqual(list(direct.colors()), [(255, 0, 0, 255), (0, 0, 255, 255), (0, 0, 0, 0)])
        phase = render(texture, 3, 1, camera_facing_affine(1, (0, 0), (0.5, 0)), "point")
        self.assertEqual(list(phase.colors()), [(255, 0, 0, 255), (0, 0, 255, 255), (0, 0, 0, 0)])
        half = render(texture, 2, 1, camera_facing_affine(0.5, (0, 0), (0, 0.25)), "point")
        self.assertEqual(half.get(0, 0), (0, 0, 255, 255))

    def test_world_plane_known_texel(self) -> None:
        texture = RGBAImage.new(3, 3)
        texture.set(1, 1, (7, 8, 9, 255))
        transform = world_plane_affine(180, (1, 2), "1080p", (1.5, 3), (10.5, 10.5))
        rendered = render(texture, 24, 24, transform, "point")
        self.assertEqual(rendered.get(10, 9), (7, 8, 9, 255))

    def test_smooth_uniform_and_alpha_conservation(self) -> None:
        texture = RGBAImage.new(4, 4, (20, 40, 60, 255))
        rendered = render(texture, 8, 8, camera_facing_affine(1, (0, 0), (2, 2)), "smooth")
        self.assertEqual(rendered.get(3, 3), (20, 40, 60, 255))
        source_alpha = 4 * 4 * 255
        output_alpha = sum(color[3] for color in rendered.colors())
        self.assertLessEqual(abs(source_alpha - output_alpha), 16)

    def test_motion_helper(self) -> None:
        movement = motion_step(4, down_right_direction(), 60, "1080p")
        self.assertAlmostEqual(math.hypot(movement["pixels_per_second_x"], movement["pixels_per_second_y"]), 170.76, delta=0.01)
        self.assertAlmostEqual(movement["pixels_per_frame_x"], 2.0125, delta=0.01)
        self.assertAlmostEqual(movement["pixels_per_frame_y"], 2.0125, delta=0.01)

    def test_projected_figure_bounds(self) -> None:
        image = RGBAImage.new(180, 180)
        for y in range(34, 180):
            for x in range(61, 119):
                image.set(x, y, (255, 255, 255, 255))
        transform = world_plane_affine(180, (1, 2), "1080p", (90, 180), (100, 150))
        rendered = render(image, 220, 220, transform, "point")
        bbox = rendered.alpha_bbox()
        self.assertIsNotNone(bbox)
        assert bbox is not None
        self.assertIn(bbox[2] - bbox[0], range(14, 18))
        self.assertIn(bbox[3] - bbox[1], range(100, 105))


if __name__ == "__main__":
    unittest.main()
