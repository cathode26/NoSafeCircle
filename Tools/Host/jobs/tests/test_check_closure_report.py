#!/usr/bin/env python
"""Tests for check_closure_report.py.

Main-Commit-Review 20260920-180652, finding 2: a fresh, non-empty report saying
"I could not review this task. Please retry later." passed every generic check
and the closure workflow called it a success.

Run:  python -B test_check_closure_report.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_closure_report import inspect, main  # noqa: E402

GOOD_TAIL = (
    "Revised contract sha256 (first 16 hex): 0123456789abcdef\n"
    "\n"
    "Final recommendation: commit_contract\n"
)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def report(self, text: str) -> Path:
        path = self.tmp / "job.report.md"
        path.write_text(text, encoding="utf-8")
        return path


class TheDeclinedReview(Base):
    """The exact reproduction from the review."""

    def test_a_polite_refusal_is_not_a_completed_review(self):
        result = inspect("I could not review this task. Please retry later.\n")
        self.assertFalse(result["complete"])
        self.assertIn("no contract identity (sha256 first 16 hex)", result["missing"])
        self.assertIn("no final recommendation", result["missing"])

    def test_it_exits_7_rather_than_0(self):
        path = self.report("I could not review this task. Please retry later.\n")
        self.assertEqual(main(["--report", str(path)]), 7)

    def test_prose_about_a_recommendation_is_not_a_recommendation(self):
        """A report that discusses the format without reaching a verdict."""
        result = inspect("I would normally give a Final recommendation here, but "
                         "the clone was empty.\n")
        self.assertFalse(result["complete"])


class ARealVerdictIsASuccess(Base):
    def test_commit_contract(self):
        self.assertTrue(inspect("...review...\n" + GOOD_TAIL)["complete"])

    def test_revise_is_a_completed_review_not_a_failed_run(self):
        """The distinction this checker family exists to preserve."""
        text = GOOD_TAIL.replace("commit_contract", "revise")
        result = inspect(text)
        self.assertTrue(result["complete"], result["missing"])
        self.assertEqual(result["recommendation"], "revise")

    def test_revise_exits_zero(self):
        path = self.report(GOOD_TAIL.replace("commit_contract", "revise"))
        self.assertEqual(main(["--report", str(path), "--quiet"]), 0)

    def test_commit_contract_then_decompose(self):
        text = GOOD_TAIL.replace("commit_contract\n", "commit_contract_then_decompose\n")
        self.assertEqual(inspect(text)["recommendation"],
                         "commit_contract_then_decompose")

    def test_the_contract_identity_is_returned_for_binding(self):
        self.assertEqual(inspect(GOOD_TAIL)["sha16"], "0123456789abcdef")


class HalfFinishedReports(Base):
    def test_a_recommendation_without_a_contract_identity_is_incomplete(self):
        """Cannot be tied to the bytes reviewed, so it could be about anything."""
        result = inspect("Final recommendation: commit_contract\n")
        self.assertFalse(result["complete"])
        self.assertEqual(result["recommendation"], "commit_contract")

    def test_a_contract_identity_without_a_recommendation_is_incomplete(self):
        result = inspect("Revised contract sha256 (first 16 hex): 0123456789abcdef\n")
        self.assertFalse(result["complete"])

    def test_an_invented_recommendation_is_refused_by_name(self):
        text = GOOD_TAIL.replace("commit_contract", "looks_fine_to_me")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("looks_fine_to_me", " ".join(result["missing"]))

    def test_a_short_hash_is_not_a_contract_identity(self):
        text = GOOD_TAIL.replace("0123456789abcdef", "0123abc")
        self.assertFalse(inspect(text)["complete"])

    def test_an_empty_report_is_incomplete(self):
        self.assertFalse(inspect("")["complete"])


class Tolerance(Base):
    def test_markdown_emphasis_does_not_hide_the_verdict(self):
        text = ("**Revised contract sha256 (first 16 hex):** 0123456789ABCDEF\n"
                "**Final recommendation:** revise\n")
        result = inspect(text)
        self.assertTrue(result["complete"], result["missing"])
        self.assertEqual(result["sha16"], "0123456789abcdef")
        self.assertEqual(result["recommendation"], "revise")

    def test_an_unreadable_report_exits_2_not_7(self):
        """Missing is a different problem from incomplete, and has its own code."""
        self.assertEqual(main(["--report", str(self.tmp / "absent.md")]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
