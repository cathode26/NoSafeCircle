"""Tests for check_job_result.py — the exact cases audit 20260920-143913 reproduced.

Portable: temp dirs only, no host paths, no provider calls.

Run:  python -B -m unittest discover -s tests -p "test_check_job_result.py"  (from C:\\NSC\\tools\\jobs)
"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_job_result import Outcome, judge, main  # noqa: E402


class AuditReproductions(unittest.TestCase):
    """The two rows from the audit's footer table, as regression tests."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cjr-"))
        self.addCleanup(self._clean)
        self.report = self.tmp / "job.report.md"

    def _clean(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_provider_failure_with_a_good_looking_report_is_NOT_success(self):
        """Audit row 1: rc=7 + 'Final recommendation: ready' used to exit 0."""
        self.report.write_text("Final recommendation: ready\n", encoding="utf-8")
        code, msg = judge(7, self.report)
        self.assertEqual(code, Outcome.PROVIDER_FAILED)
        self.assertNotEqual(code, Outcome.OK)
        self.assertIn("left over", msg)

    def test_provider_failure_with_no_report(self):
        """Audit row 2: this one was already correct; keep it that way."""
        code, _ = judge(7, self.report)
        self.assertEqual(code, Outcome.PROVIDER_FAILED)

    def test_success_with_a_fresh_report(self):
        self.report.write_text("Final recommendation: ready\n", encoding="utf-8")
        code, _ = judge(0, self.report, started_at=time.time() - 60)
        self.assertEqual(code, Outcome.OK)


class SeparatesTheThreeQuestions(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cjr-"))
        self.addCleanup(self._clean)
        self.report = self.tmp / "job.report.md"

    def _clean(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exit_zero_with_no_report_is_a_failure(self):
        self.assertEqual(judge(0, self.report)[0], Outcome.NO_REPORT)

    def test_an_empty_report_is_a_failure(self):
        self.report.write_bytes(b"")
        self.assertEqual(judge(0, self.report)[0], Outcome.EMPTY_REPORT)

    def test_a_report_older_than_this_run_is_stale(self):
        self.report.write_text("old verdict from yesterday\n", encoding="utf-8")
        code, msg = judge(0, self.report, started_at=time.time() + 5)
        self.assertEqual(code, Outcome.STALE_REPORT)
        self.assertIn("leftover", msg)

    def test_without_started_at_staleness_is_not_claimed(self):
        self.report.write_text("something\n", encoding="utf-8")
        self.assertEqual(judge(0, self.report)[0], Outcome.OK)

    def test_a_REJECT_verdict_is_still_a_successful_RUN(self):
        """The review's answer is not the run's outcome. Collapsing them caused the bug."""
        self.report.write_text("Final recommendation: REJECT - do not merge\n", encoding="utf-8")
        code, _ = judge(0, self.report, started_at=time.time() - 10)
        self.assertEqual(code, Outcome.OK)


class CliContract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cjr-"))
        self.addCleanup(self._clean)
        self.report = self.tmp / "job.report.md"

    def _clean(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cli_exit_code_matches_the_judgement(self):
        self.report.write_text("Final recommendation: ready\n", encoding="utf-8")
        self.assertEqual(main(["--rc", "7", "--report", str(self.report)]),
                         Outcome.PROVIDER_FAILED)
        self.assertEqual(main(["--rc", "0", "--report", str(self.report)]), Outcome.OK)

    def test_printing_the_verdict_never_changes_the_exit_code(self):
        """The original bug was literally `grep` being the last command."""
        self.report.write_text("nothing that matches the pattern\n", encoding="utf-8")
        code = main(["--rc", "0", "--report", str(self.report),
                     "--verdict-grep", "Final recommendation"])
        self.assertEqual(code, Outcome.OK, "a non-matching grep must not fail the run")

    def test_an_unreadable_report_does_not_crash_the_verdict_print(self):
        self.report.write_bytes(b"\xff\xfe binary-ish \x00 content")
        self.assertEqual(main(["--rc", "0", "--report", str(self.report),
                               "--verdict-grep", "Final"]), Outcome.OK)


if __name__ == "__main__":
    unittest.main(verbosity=2)
