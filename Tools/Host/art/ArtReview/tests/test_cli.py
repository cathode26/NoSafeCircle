from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from art_review.cli import main
from art_review.pngio import write_png
from art_review.raster import RGBAImage


class CLISmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.frame = self.root / "frame.png"
        self.image = RGBAImage.new(4, 4)
        for y in range(1, 4):
            for x in range(1, 3):
                self.image.set(x, y, (255, 32, 0, 255))
        write_png(self.image, self.frame)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(self, name: str, value: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_gamescale(self) -> None:
        manifest = self.write_json("game.json", {"panel_width": 32, "panel_height": 32, "sprites": [
            {"path": str(self.frame), "label": "Test", "mode": "camera-facing", "scale": 1, "sampling": "point"}]})
        output, report = self.root / "game.png", self.root / "game-report.json"
        self.assertEqual(main(["gamescale", "--manifest", str(manifest), "--output", str(output), "--json", str(report)]), 0)
        self.assertTrue(output.is_file() and report.is_file())

    def test_contact_sheet(self) -> None:
        manifest = self.write_json("contact.json", {"rows": [[{"path": str(self.frame), "caption": "Frame"}]]})
        output = self.root / "contact.png"
        self.assertEqual(main(["contact-sheet", "--manifest", str(manifest), "--output", str(output)]), 0)
        self.assertTrue(output.is_file())

    def test_gif(self) -> None:
        output, report = self.root / "out.gif", self.root / "gif.json"
        self.assertEqual(main(["gif", str(self.frame), "--output", str(output), "--duration", "30", "--json", str(report)]), 0)
        self.assertEqual(json.loads(report.read_text())["frame_count"], 1)

    def test_mask_diff_exit_codes(self) -> None:
        mask = self.root / "mask.png"
        write_png(RGBAImage.new(4, 4, (0, 0, 0, 255)), mask)
        changed = self.image.copy()
        changed.set(0, 0, (1, 2, 3, 255))
        result = self.root / "result.png"
        write_png(changed, result)
        arguments = ["mask-diff", "--source", str(self.frame), "--result", str(result), "--mask", str(mask),
                     "--output", str(self.root / "proof.png"), "--json", str(self.root / "mask.json")]
        self.assertEqual(main(arguments), 1)
        arguments[arguments.index(str(result))] = str(self.frame)
        self.assertEqual(main(arguments), 0)
        arguments[arguments.index(str(self.frame), 4)] = str(result)
        invalid_mask = self.root / "invalid-mask.png"
        write_png(RGBAImage.new(4, 4, (128, 128, 128, 255)), invalid_mask)
        arguments[arguments.index(str(mask))] = str(invalid_mask)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(arguments), 2)

    def test_frame_metrics(self) -> None:
        report = self.root / "metrics.json"
        self.assertEqual(main(["frame-metrics", str(self.frame), "--json", str(report)]), 0)
        self.assertEqual(len(json.loads(report.read_text())["frames"]), 1)

    def test_hue_scan(self) -> None:
        report = self.root / "hue.json"
        self.assertEqual(main(["hue-scan", str(self.frame), "--json", str(report)]), 0)
        self.assertGreater(json.loads(report.read_text())["matching_pixel_count"], 0)
        self.assertEqual(main(["hue-scan", str(self.frame), "--fail-on-match"]), 1)

    def test_normalize(self) -> None:
        report = self.root / "normalize.json"
        output_directory = self.root / "normalized"
        self.assertEqual(main(["normalize", str(self.frame), "--output-dir", str(output_directory), "--size", "8", "--json", str(report)]), 0)
        self.assertTrue((output_directory / self.frame.name).is_file())

    def test_ledger(self) -> None:
        ledger, report = self.root / "spend.jsonl", self.root / "summary.json"
        self.assertEqual(main(["ledger", "init", "--ledger", str(ledger), "--job", "smoke", "--remaining", "99", "--used", "1"]), 0)
        self.assertEqual(main(["ledger", "add", "--ledger", str(ledger), "--tool", "generate", "--id", "abc", "--reported-cost", "1"]), 0)
        self.assertEqual(main(["ledger", "summary", "--ledger", str(ledger), "--json", str(report)]), 0)
        self.assertEqual(json.loads(report.read_text())["tool_reported_total"], 1)


if __name__ == "__main__":
    unittest.main()
