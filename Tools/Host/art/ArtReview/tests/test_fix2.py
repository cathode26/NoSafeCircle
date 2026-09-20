from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from art_review.cli import main


class LedgerNumericBoundsRegressionTests(unittest.TestCase):
    def test_add_refuses_each_extreme_finite_cost_without_appending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory, "spend.jsonl")
            self.assertEqual(main(["ledger", "init", "--ledger", str(ledger), "--job", "review",
                                   "--remaining", "10", "--used", "0"]), 0)
            before = ledger.read_bytes()
            codes = []
            with redirect_stderr(io.StringIO()):
                for identifier in ("first", "second"):
                    codes.append(main(["ledger", "add", "--ledger", str(ledger), "--tool", "generate",
                                       "--id", identifier, "--reported-cost", "1e308"]))
            self.assertEqual(codes, [2, 2])
            self.assertEqual(ledger.read_bytes(), before)

    def test_summary_rejects_extreme_finite_cost_on_named_ledger_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory, "spend.jsonl")
            events = [
                {"type": "init", "timestamp_utc": "now", "job": "review", "cap": None,
                 "remaining": 10, "used": 0},
                {"type": "entry", "timestamp_utc": "now", "tool": "generate", "pixellab_id": "first",
                 "reported_cost": 1e308, "provisional": False, "note": None},
                {"type": "entry", "timestamp_utc": "now", "tool": "generate", "pixellab_id": "second",
                 "reported_cost": 1e308, "provisional": False, "note": None},
            ]
            ledger.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors), redirect_stdout(io.StringIO()):
                code = main(["ledger", "summary", "--ledger", str(ledger)])
            self.assertEqual(code, 2)
            self.assertIn("ledger line 2", errors.getvalue())

    def test_normal_float_costs_still_produce_finite_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "spend.jsonl"
            report = root / "summary.json"
            self.assertEqual(main(["ledger", "init", "--ledger", str(ledger), "--job", "review",
                                   "--remaining", "10", "--used", "0"]), 0)
            self.assertEqual(main(["ledger", "add", "--ledger", str(ledger), "--tool", "generate",
                                   "--id", "first", "--reported-cost", "0.5"]), 0)
            self.assertEqual(main(["ledger", "add", "--ledger", str(ledger), "--tool", "generate",
                                   "--id", "second", "--reported-cost", "1.5"]), 0)
            self.assertEqual(main(["ledger", "summary", "--ledger", str(ledger), "--json", str(report)]), 0)
            summary = json.loads(report.read_text(encoding="utf-8"),
                                 parse_constant=lambda value: self.fail(f"non-finite JSON value {value}"))
            self.assertEqual(summary["per_tool"], {"generate": 2.0})
            self.assertEqual(summary["tool_reported_total"], 2.0)
            self.assertEqual(summary["spend"], 2.0)
            before = ledger.read_bytes()
            invalid_init = root / "invalid-init.jsonl"
            with redirect_stderr(io.StringIO()):
                balance_code = main(["ledger", "balance", "--ledger", str(ledger),
                                     "--remaining", "1000000000001", "--used", "0"])
                init_code = main(["ledger", "init", "--ledger", str(invalid_init), "--job", "review",
                                  "--cap", "1000000000001", "--remaining", "10", "--used", "0"])
            self.assertEqual((balance_code, init_code), (2, 2))
            self.assertEqual(ledger.read_bytes(), before)
            self.assertFalse(invalid_init.exists())


if __name__ == "__main__":
    unittest.main()
