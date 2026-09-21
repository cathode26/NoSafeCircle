#!/usr/bin/env python
"""Tests for check_closure_report.py.

Two rounds of findings are pinned here.

Main-Commit-Review 20260920-180652, finding 2: a fresh, non-empty report saying
"I could not review this task. Please retry later." passed every generic check
and the closure workflow called it a success.

Astra's release review of 17cf1f4c5, finding 1 (BLOCKING): the first fix asked
only whether the markers were present, which is a much weaker question. It
picked the first of two contradictory recommendations, accepted a refusal placed
after a well-formed footer, and accepted ANY 16 hex characters as the contract
identity - so a review of a different revision read as a clean pass.

Run:  python -B test_check_closure_report.py
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_closure_report import contract_sha16, inspect, main  # noqa: E402

SHA = "0123456789abcdef"
GOOD_TAIL = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
             "\n"
             "Final recommendation: commit_contract\n")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def report(self, text: str) -> Path:
        path = self.tmp / "job.report.md"
        path.write_text(text, encoding="utf-8")
        return path

    def contract(self, data: bytes = b'{"task": "NSC-001"}') -> Path:
        path = self.tmp / "REVISED_CONTRACT.json"
        path.write_bytes(data)
        return path


class TheDeclinedReview(Base):
    """Main-Commit-Review 20260920-180652, finding 2."""

    def test_a_polite_refusal_is_not_a_completed_review(self):
        result = inspect("I could not review this task. Please retry later.\n")
        self.assertFalse(result["complete"])
        self.assertIn("no contract identity (sha256 first 16 hex)", result["missing"])
        self.assertIn("no final recommendation", result["missing"])

    def test_it_exits_7_rather_than_0(self):
        path = self.report("I could not review this task. Please retry later.\n")
        self.assertEqual(main(["--report", str(path)]), 7)

    def test_prose_about_a_recommendation_is_not_a_recommendation(self):
        result = inspect("I would normally give a Final recommendation here, but "
                         "the clone was empty.\n")
        self.assertFalse(result["complete"])


class OneVerdictOrNone(Base):
    """Astra finding 1a: .search took the first of two contradictory verdicts."""

    def test_two_different_recommendations_are_a_contradiction_not_a_verdict(self):
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract\n"
                "On reflection, Final recommendation: revise\n")
        result = inspect(text)
        self.assertFalse(result["complete"], "a contradiction must not resolve to one side")
        self.assertIn("contradictory", " ".join(result["missing"]))
        self.assertIsNone(result["recommendation"])

    def test_the_first_one_is_not_silently_chosen(self):
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract\n"
                "Final recommendation: revise\n")
        self.assertNotEqual(inspect(text)["recommendation"], "commit_contract")

    def test_the_same_verdict_stated_twice_is_still_refused(self):
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: revise\n"
                "Final recommendation: revise\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("once", " ".join(result["missing"]))

    def test_two_different_contract_identities_are_refused(self):
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Revised contract sha256 (first 16 hex): fedcba9876543210\n"
                "Final recommendation: revise\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("different contract identities", " ".join(result["missing"]))


class TheVerdictMustBeTheEnd(Base):
    """Astra finding 1b: a refusal after a well-formed footer still passed."""

    def test_a_refusal_after_the_footer_is_not_a_completed_review(self):
        text = (GOOD_TAIL
                + "\nActually, I could not review this task. Please retry later.\n"
                + "There was no usable clone, so none of the above was checked.\n"
                + "Disregard the recommendation above.\n"
                + "This report should not be acted on.\n"
                + "Please re-run the job.\n")
        result = inspect(text)
        self.assertFalse(result["complete"], "trailing text walked the verdict back")
        self.assertIn("closing lines", " ".join(result["missing"]))

    def test_an_ordinary_report_ending_in_its_footer_is_fine(self):
        self.assertTrue(inspect("...the review...\n\n" + GOOD_TAIL)["complete"])

    def test_a_short_sign_off_after_the_footer_is_tolerated(self):
        self.assertTrue(inspect("...\n" + GOOD_TAIL + "\nReviewed by Astra.\n")["complete"])


class TheIdentityMustBeTheContractUnderReview(Base):
    """Astra finding 1c: any 16 hex characters passed, so a review of the wrong
    revision read as a clean pass. This is the one that matters."""

    def test_a_report_about_different_bytes_is_refused(self):
        data = b'{"task": "NSC-001", "revision": 7}'
        real = contract_sha16(data)
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract\n")
        result = inspect(text, expected_sha16=real)
        self.assertFalse(result["complete"])
        self.assertIn("different bytes", " ".join(result["missing"]))

    def test_the_matching_identity_passes_and_is_marked_verified(self):
        data = b'{"task": "NSC-001", "revision": 7}'
        real = contract_sha16(data)
        text = (f"Revised contract sha256 (first 16 hex): {real}\n"
                "Final recommendation: commit_contract\n")
        self.assertTrue(inspect(text, expected_sha16=real)["complete"])

    def test_the_comparison_is_case_insensitive(self):
        data = b"x"
        real = contract_sha16(data)
        text = (f"Revised contract sha256 (first 16 hex): {real.upper()}\n"
                "Final recommendation: revise\n")
        self.assertTrue(inspect(text, expected_sha16=real)["complete"])

    def test_end_to_end_through_the_contract_flag(self):
        data = b'{"task": "NSC-042"}'
        contract = self.contract(data)
        good = self.report(f"Revised contract sha256 (first 16 hex): {contract_sha16(data)}\n"
                           "Final recommendation: revise\n")
        self.assertEqual(main(["--report", str(good), "--contract", str(contract),
                               "--quiet"]), 0)
        wrong = self.report(f"Revised contract sha256 (first 16 hex): {SHA}\n"
                            "Final recommendation: revise\n")
        self.assertEqual(main(["--report", str(wrong), "--contract", str(contract)]), 7)

    def test_contract_sha16_is_the_documented_computation(self):
        data = b"some exact bytes"
        self.assertEqual(contract_sha16(data), hashlib.sha256(data).hexdigest()[:16])

    def test_an_unreadable_contract_exits_2_not_7(self):
        report = self.report(GOOD_TAIL)
        self.assertEqual(main(["--report", str(report),
                               "--contract", str(self.tmp / "absent.json")]), 2)


class ARealVerdictIsASuccess(Base):
    def test_commit_contract(self):
        self.assertTrue(inspect("...review...\n" + GOOD_TAIL)["complete"])

    def test_revise_is_a_completed_review_not_a_failed_run(self):
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
        self.assertEqual(inspect(GOOD_TAIL)["sha16"], SHA)


class HalfFinishedReports(Base):
    def test_a_recommendation_without_a_contract_identity_is_incomplete(self):
        result = inspect("Final recommendation: commit_contract\n")
        self.assertFalse(result["complete"])

    def test_a_contract_identity_without_a_recommendation_is_incomplete(self):
        self.assertFalse(inspect(f"Revised contract sha256 (first 16 hex): {SHA}\n")["complete"])

    def test_an_invented_recommendation_is_refused_by_name(self):
        text = GOOD_TAIL.replace("commit_contract", "looks_fine_to_me")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("looks_fine_to_me", " ".join(result["missing"]))

    def test_a_short_hash_is_not_a_contract_identity(self):
        self.assertFalse(inspect(GOOD_TAIL.replace(SHA, "0123abc"))["complete"])

    def test_an_empty_report_is_incomplete(self):
        self.assertFalse(inspect("")["complete"])


class Tolerance(Base):
    def test_markdown_emphasis_does_not_hide_the_verdict(self):
        text = (f"**Revised contract sha256 (first 16 hex):** {SHA.upper()}\n"
                "**Final recommendation:** revise\n")
        result = inspect(text)
        self.assertTrue(result["complete"], result["missing"])
        self.assertEqual(result["sha16"], SHA)
        self.assertEqual(result["recommendation"], "revise")

    def test_an_unreadable_report_exits_2_not_7(self):
        self.assertEqual(main(["--report", str(self.tmp / "absent.md")]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
