#!/usr/bin/env python
"""Tests for the mutation harness's scoring. MJ-09.

Run:
    python -B test_mutation_check.py

The harness is the instrument every "N/N mutations killed" claim rests on, and it
was wrong: its pattern matched `FAIL:` and `ERROR:` alike, so a mutation that
raised NameError inside the named test - detecting nothing - counted as caught.
Astra reproduced it with one NameError, zero assertion failures, "1/1 mutations
killed", exit 0. Every mutation total in this family's history was measured that
way, which is why none of them are quoted as evidence any more.

`score` is pure so it can be tested against synthetic unittest output rather than
by running suites. The five conditions each have a test, and
`test_a_crash_in_the_named_test_is_not_a_kill` is Astra's case exactly.

The harness caught a real defect in its first run after the correction: one test
CRASHED under its mutation instead of failing, so it was not detecting the
behaviour it claimed to. That is the whole point of condition 3.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutation_check  # noqa: E402

HOST = Path(__file__).resolve().parent.parent.parent

TARGET = "test_the_guard_refuses"


def output(*, ran: int | None = 65, failures=(), errors=()) -> str:
    """Synthetic unittest output, in the shape and order unittest prints it."""
    lines = []
    for name in failures:
        lines.append(f"FAIL: {name} (__main__.Suite.{name})")
    for name in errors:
        lines.append(f"ERROR: {name} (__main__.Suite.{name})")
    lines.append("-" * 70)
    if ran is not None:
        lines.append(f"Ran {ran} tests in 0.010s")
    lines.append("")
    lines.append("FAILED (failures=1)" if failures or errors else "OK")
    return "\n".join(lines) + "\n"


class Scoring(unittest.TestCase):
    def test_the_named_test_failing_is_a_kill(self):
        killed, reason = mutation_check.score(1, output(failures=[TARGET]), TARGET)
        self.assertTrue(killed, reason)
        self.assertEqual(reason, "")

    def test_a_crash_in_the_named_test_is_not_a_kill(self):
        # Astra round 7, finding 3, exactly: the named test appears, the suite is
        # red, the exit code is non-zero - and nothing was detected.
        killed, reason = mutation_check.score(1, output(errors=[TARGET]), TARGET)
        self.assertFalse(killed)
        self.assertIn("ERRORS", reason)

    def test_an_error_anywhere_disqualifies_the_run(self):
        # Even alongside a genuine failure of the named test: an error means the
        # mutation broke execution, and what the rest of the suite did under a
        # half-broken module is not evidence.
        killed, reason = mutation_check.score(
            1, output(failures=[TARGET], errors=["test_something_else"]), TARGET)
        self.assertFalse(killed)
        self.assertIn("ERRORS", reason)

    def test_a_green_suite_is_not_a_kill(self):
        killed, reason = mutation_check.score(0, output(), TARGET)
        self.assertFalse(killed)
        self.assertIn("green", reason)

    def test_a_missing_summary_is_not_a_kill(self):
        # The suite died before finishing. Red, but it proves nothing.
        killed, reason = mutation_check.score(1, "Traceback (most recent call last):\n",
                                              TARGET)
        self.assertFalse(killed)
        self.assertIn("did not complete", reason)

    def test_zero_collected_tests_is_not_a_kill(self):
        killed, reason = mutation_check.score(1, output(ran=0), TARGET)
        self.assertFalse(killed)
        self.assertIn("zero tests", reason)

    def test_the_wrong_test_failing_is_not_a_kill(self):
        killed, reason = mutation_check.score(
            1, output(failures=["test_an_unrelated_guard"]), TARGET)
        self.assertFalse(killed)
        self.assertIn(TARGET, reason)
        self.assertIn("test_an_unrelated_guard", reason)

    def test_the_last_summary_decides(self):
        # A suite that shells out to another prints more than one summary, and
        # only the outermost - the last to finish - is this suite's.
        nested = "Ran 0 tests in 0.001s\n\nOK\n" + output(failures=[TARGET])
        killed, _ = mutation_check.score(1, nested, TARGET)
        self.assertTrue(killed)


class TheMutationTable(unittest.TestCase):
    """The anchors must still exist, or the harness silently measures nothing."""

    def test_every_anchor_matches_exactly_once(self):
        cache: dict[str, str] = {}
        for file_key, what, old, _new, _suite, _must_die in mutation_check.MUTATIONS:
            with self.subTest(what=what):
                relative = mutation_check.FILES[file_key]
                if file_key not in cache:
                    cache[file_key] = (HOST / relative).read_text(encoding="utf-8")
                self.assertEqual(
                    cache[file_key].count(old), 1,
                    f"anchor for {what!r} matched {cache[file_key].count(old)} "
                    f"times in {relative}; the harness would report ANCHOR LOST "
                    f"and count it as a survivor")

    def test_every_named_test_exists_in_its_suite(self):
        cache: dict[str, str] = {}
        for _file_key, what, _old, _new, suite_key, must_die in mutation_check.MUTATIONS:
            with self.subTest(what=what):
                relative = mutation_check.SUITES[suite_key]
                if suite_key not in cache:
                    cache[suite_key] = (HOST / relative).read_text(encoding="utf-8")
                self.assertIn(f"def {must_die}(", cache[suite_key],
                              f"{must_die} is not defined in {relative}")

    def test_every_referenced_file_exists(self):
        for relative in (list(mutation_check.FILES.values())
                         + list(mutation_check.SUITES.values())
                         + mutation_check.SUPPORT):
            with self.subTest(relative=str(relative)):
                self.assertTrue((HOST / relative).is_file(), HOST / relative)


if __name__ == "__main__":
    unittest.main(verbosity=2)
