#!/usr/bin/env python
"""Tests for run_tool_tests.py - the runner every other suite's verdict goes through.

It had none until Astra's round-2 finding 2, which is why that finding existed.
Thirteen suites were guarded by a file that nothing guarded, and the guard it
provides - "a suite that skips is not a suite that passed" - was bypassable by
any suite that happened to print the word `skipped=` above its own summary.

The shape of the defect is the one Astra named in the closure checker too:
recognising a matching fragment instead of establishing the result. So the
cases here are mostly about WHERE a number was read from, not what it was.

Run:  python -B test_run_tool_tests.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_tool_tests  # noqa: E402
from run_tool_tests import run_one, terminal_summary  # noqa: E402


def unittest_output(body: str) -> str:
    """What unittest actually prints, dashes and blank line included."""
    return ("-" * 70) + "\n" + body


class TheVerdictIsTheClosingSummary(unittest.TestCase):
    """Astra round 2, finding 2, reproduced at the parse."""

    def test_the_masking_case_astra_reproduced(self):
        """stdout says skipped=0, unittest says skipped=2. Two is the answer."""
        text = ("fixture baseline: skipped=0\n"
                + unittest_output("Ran 9 tests in 0.01s\n\nOK (skipped=2)\n"))
        tests, verdict, counts = terminal_summary(text)
        self.assertEqual(tests, 9)
        self.assertEqual(verdict, "OK")
        self.assertEqual(counts.get("skipped"), 2,
                         "the count must come from the summary, not the stream")

    def test_a_plain_ok_reports_no_skips(self):
        tests, verdict, counts = terminal_summary(
            unittest_output("Ran 4 tests in 0.01s\n\nOK\n"))
        self.assertEqual((tests, verdict), (4, "OK"))
        self.assertEqual(counts.get("skipped", 0), 0)

    def test_several_counts_are_read_separately(self):
        _, _, counts = terminal_summary(
            unittest_output("Ran 6 tests in 0.01s\n\nOK (skipped=1, expected failures=2)\n"))
        self.assertEqual(counts.get("skipped"), 1)
        self.assertEqual(counts.get("expected failures"), 2)

    def test_the_last_summary_wins(self):
        """A suite that shells out to another prints more than one."""
        text = (unittest_output("Ran 2 tests in 0.01s\n\nOK (skipped=5)\n")
                + "\nnow the real suite\n"
                + unittest_output("Ran 30 tests in 0.20s\n\nOK\n"))
        tests, verdict, counts = terminal_summary(text)
        self.assertEqual(tests, 30, "an inner suite's count is not this suite's count")
        self.assertEqual(verdict, "OK")
        self.assertEqual(counts.get("skipped", 0), 0,
                         "nor is an inner suite's skip count")

    def test_a_failure_verdict_is_read_as_a_failure(self):
        _, verdict, counts = terminal_summary(
            unittest_output("Ran 8 tests in 0.01s\n\nFAILED (failures=2, errors=1)\n"))
        self.assertEqual(verdict, "FAILED")
        self.assertEqual(counts.get("failures"), 2)

    def test_no_summary_at_all_is_not_a_zero(self):
        """Absence is not a diagnosis; the caller must be able to tell."""
        self.assertEqual(terminal_summary("ModuleNotFoundError: no module named x"),
                         (None, None, {}))

    def test_a_count_with_no_verdict_line_is_reported_as_such(self):
        tests, verdict, _ = terminal_summary("Ran 3 tests in 0.01s\n")
        self.assertEqual(tests, 3)
        self.assertIsNone(verdict, "a count without a verdict is not a pass")


class Fixture(unittest.TestCase):
    """A real suite on disk, run the way run_one runs one."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._strict = run_tool_tests.NO_SKIPS
        self.addCleanup(self.restore_strict)

    def restore_strict(self):
        run_tool_tests.NO_SKIPS = self._strict

    def suite(self, body: str) -> Path:
        path = self.tmp / "suite_under_test.py"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return path

    def run_it(self, path: Path):
        return run_one(path, self.tmp, None, timeout=60)


class TheRunnerAgainstRealSuites(Fixture):
    """Reproduce the way the program runs: a real interpreter, a real suite.

    Testing terminal_summary alone would be testing a model of the thing. The
    bypass only matters if it reaches run_one's decision, so it is exercised
    there too.
    """

    MASKING = '''
        import unittest
        print("fixture baseline: skipped=0")

        class T(unittest.TestCase):
            def test_one(self):
                pass

            @unittest.skip("a guard case this machine cannot run")
            def test_two(self):
                pass

            @unittest.skip("and another")
            def test_three(self):
                pass

        unittest.main()
    '''

    def test_strict_mode_is_not_fooled_by_the_masking_line(self):
        run_tool_tests.NO_SKIPS = True
        ok, tests, detail = self.run_it(self.suite(self.MASKING))
        self.assertFalse(ok, "two skipped guard cases passed strict mode")
        self.assertEqual(tests, 3)
        self.assertIn("2 test(s) skipped", detail)

    def test_the_same_suite_passes_when_skips_are_allowed(self):
        run_tool_tests.NO_SKIPS = False
        ok, tests, detail = self.run_it(self.suite(self.MASKING))
        self.assertTrue(ok, detail)
        self.assertEqual(detail, "2 skipped", "the real count is still reported")

    def test_a_clean_suite_passes(self):
        ok, tests, detail = self.run_it(self.suite('''
            import unittest

            class T(unittest.TestCase):
                def test_one(self):
                    pass

            unittest.main()
        '''))
        self.assertTrue(ok, detail)
        self.assertEqual((tests, detail), (1, ""))

    def test_a_suite_that_runs_nothing_fails(self):
        ok, tests, detail = self.run_it(self.suite('''
            import unittest
            unittest.main()
        '''))
        self.assertFalse(ok, "a suite collecting nothing is not a pass")
        self.assertEqual(tests, 0)

    def test_a_suite_that_cannot_import_fails_loudly(self):
        ok, tests, detail = self.run_it(self.suite('''
            import a_module_that_does_not_exist
        '''))
        self.assertFalse(ok)
        self.assertIn("ran no tests", detail)

    def test_a_failing_suite_fails(self):
        ok, _, detail = self.run_it(self.suite('''
            import unittest

            class T(unittest.TestCase):
                def test_one(self):
                    self.fail("deliberate")

            unittest.main()
        '''))
        self.assertFalse(ok)
        self.assertIn("exit 1", detail)

    def test_a_suite_that_prints_FAILED_but_exits_0_is_not_a_pass(self):
        """The exit status is not the only thing that can lie.

        A wrapper catching SystemExit from unittest.main() swallows the status
        while the verdict line still says FAILED. Nothing above this reaches
        that branch - an ordinary failing suite exits 1 and is caught by the
        returncode check - so without this case the guard is decorative.
        """
        ok, tests, detail = self.run_it(self.suite("""
            import unittest

            class T(unittest.TestCase):
                def test_one(self):
                    self.fail("deliberate")

            try:
                unittest.main()
            except SystemExit:
                pass
        """))
        self.assertFalse(ok, "unittest said FAILED and the runner believed exit 0")
        self.assertEqual(tests, 1)
        self.assertIn("FAILED", detail)

    def test_a_count_with_no_verdict_line_is_not_a_pass(self):
        """Something printed a plausible summary and stopped."""
        ok, tests, detail = self.run_it(self.suite("""
            print("Ran 5 tests in 0.01s")
        """))
        self.assertFalse(ok)
        self.assertEqual(tests, 5)
        self.assertIn("no verdict", detail)

    def test_a_missing_suite_is_a_failure_not_a_crash(self):
        ok, tests, detail = self.run_it(self.tmp / "never_written.py")
        self.assertFalse(ok)
        self.assertIn("missing", detail)


class TheSuiteListIsHonest(unittest.TestCase):
    """Point 3 of the runner's docstring, enforced rather than asserted.

    The list is explicit so that a renamed suite breaks loudly. Nothing checked
    that the paths in it exist, so a rename would have been caught only by a
    full run - and only if someone read the output.
    """

    def test_every_listed_suite_exists(self):
        missing = [suite for _, suite, _, _ in run_tool_tests.SUITES
                   if not suite.is_file()]
        self.assertEqual(missing, [], "listed suites that are not on disk")

    def test_every_listed_working_directory_exists(self):
        missing = sorted({str(cwd) for _, _, cwd, _ in run_tool_tests.SUITES
                          if not cwd.is_dir()})
        self.assertEqual(missing, [])

    def test_this_suite_is_in_the_list(self):
        """Otherwise it is a guard nobody runs, which is the thing being fixed."""
        here = Path(__file__).resolve()
        self.assertIn(here, [suite.resolve() for _, suite, _, _ in run_tool_tests.SUITES])

    def test_no_suite_is_listed_twice(self):
        listed = [suite.resolve() for _, suite, _, _ in run_tool_tests.SUITES]
        self.assertEqual(len(listed), len(set(listed)),
                         "a duplicated suite inflates the total count")


class TheRunnerSpellsNoMachine(unittest.TestCase):
    """The portability layer landed hours before a suite pinned C:/NSC into CI.

    Cheap to check, and it checks the file that CI actually invokes.
    """

    def test_the_runner_hard_codes_no_absolute_root(self):
        source = Path(run_tool_tests.__file__).read_text(encoding="utf-8")
        for spelling in ("C:\\NSC", "C:/NSC", "C:\\nscrev", "C:/nscrev"):
            self.assertNotIn(spelling, source,
                             f"{spelling} is spelled in the one command CI runs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
