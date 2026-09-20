from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from art_review.ledger import add, balance, initialize, summarize
from art_review.maskdiff import compare
from art_review.metrics import frame_metrics, hue_scan
from art_review.normalize import normalize_frame
from art_review.pngio import read_png, write_png
from art_review.raster import RGBAImage
from art_review.sheets import contact_sheet


class AnalysisTests(unittest.TestCase):
    def test_mask_diff_counts_transparent_equality_and_colors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = RGBAImage.from_rows([[(1, 2, 3, 255), (7, 8, 9, 0)], [(4, 5, 6, 255), (1, 1, 1, 255)]])
            result = RGBAImage.from_rows([[(9, 8, 7, 255), (99, 88, 77, 0)], [(8, 5, 6, 255), (1, 1, 1, 255)]])
            mask = RGBAImage.from_rows([[(255, 255, 255, 255), (0, 0, 0, 255)],
                                        [(0, 0, 0, 255), (255, 255, 255, 255)]])
            paths = [root / name for name in ("source.png", "result.png", "mask.png")]
            for image, path in zip((source, result, mask), paths):
                write_png(image, path)
            proof = root / "proof.png"
            report = compare(*paths, proof, zoom=2)
            self.assertEqual(report["changed_inside"], 1)
            self.assertEqual(report["changed_outside"], 1)
            self.assertEqual(report["introduced_colors"]["#090807ff"], 1)
            self.assertTrue(proof.is_file())

    def test_frame_metrics_outliers_and_hue_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, (top, width) in enumerate(((2, 10), (2, 7), (8, 10))):
                image = RGBAImage.new(16, 16)
                for y in range(top, top + 4):
                    for x in range(width):
                        image.set(x, y, (255, 32, 0, 255))
                path = Path(directory, f"{index}.png")
                write_png(image, path)
                paths.append(path)
            report = frame_metrics(paths, loop=True)
            self.assertIn("opaque_change", report["deltas"][0]["flags"])
            self.assertIn("baseline_jump", report["deltas"][-1]["flags"])
            scan = hue_scan(paths)
            self.assertGreater(scan["matching_pixel_count"], 0)

    def test_normalize_crop_and_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            safe = RGBAImage.new(152, 152)
            for y in range(12, 140):
                for x in range(12, 140):
                    safe.set(x, y, (10, 20, 30, 255))
            source, output = root / "safe.png", root / "out.png"
            write_png(safe, source)
            report = normalize_frame(source, output, 128, 128)
            self.assertEqual(report["origin_on_canvas"], [-12, -12])
            self.assertEqual(read_png(output).opaque_count(), safe.opaque_count())
            unsafe = safe.copy()
            unsafe.set(0, 0, (255, 255, 255, 255))
            unsafe_path, refused_path = root / "unsafe.png", root / "refused.png"
            write_png(unsafe, unsafe_path)
            with self.assertRaisesRegex(ValueError, "outside"):
                normalize_frame(unsafe_path, refused_path, 128, 128)
            self.assertFalse(refused_path.exists())

    def test_contact_sheet_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            specifications = [("a.png", 2, 3), ("b.png", 4, 2), ("c.png", 3, 1)]
            for name, width, height in specifications:
                write_png(RGBAImage.new(width, height, (255, 255, 255, 255)), root / name)
            rows = [[{"path": str(root / "a.png"), "caption": "A"}, {"path": str(root / "b.png"), "caption": "B"}],
                    [{"path": str(root / "c.png"), "caption": "C"}]]
            sheet = contact_sheet(rows, zoom=2, gap=2)
            self.assertEqual((sheet.width, sheet.height), (20, 34))


class LedgerTests(unittest.TestCase):
    def make_ledger(self, root: Path, cap: int | None, start: int, end: int, costs: list[int]) -> dict:
        path = root / f"ledger-{cap}-{start}-{end}-{sum(costs)}.jsonl"
        initialize(path, "review", 5000 - start, start, cap)
        for index, cost in enumerate(costs):
            add(path, "generate", f"id-{index}", cost)
        balance(path, 5000 - end, end)
        return summarize(path)

    def test_worked_cap_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            no_cap = self.make_ledger(root, None, 311, 331, [1, 2, 2, 6, 1, 1, 1, 1, 1, 1, 1, 1])
            self.assertEqual(no_cap["tool_reported_total"], 19)
            self.assertEqual(no_cap["unattributed_difference"], 1)
            self.assertEqual(no_cap["cap_status"], "no_cap")
            near = self.make_ledger(root, 15, 317, 332, [14])
            self.assertEqual((near["unattributed_difference"], near["spend"], near["cap_status"]), (1, 15, "near_cap"))
            over = self.make_ledger(root, 15, 317, 334, [14])
            self.assertEqual((over["unattributed_difference"], over["spend"], over["cap_status"]), (3, 17, "over_cap"))
            okay = self.make_ledger(root, 15, 317, 327, [10])
            self.assertEqual((okay["unattributed_difference"], okay["spend"], okay["cap_status"]), (0, 10, "ok"))

    def test_init_refuses_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "ledger.jsonl")
            initialize(path, "first", 10, 1)
            with self.assertRaises(FileExistsError):
                initialize(path, "second", 10, 1)


if __name__ == "__main__":
    unittest.main()
