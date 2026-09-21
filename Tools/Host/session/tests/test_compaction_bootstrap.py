#!/usr/bin/env python
"""Unit tests for compaction_bootstrap.py. No network, no provider, no paid calls.

    set TEMP=C:\\nscrev\\tmp\\session & set TMP=C:\\nscrev\\tmp\\session
    C:/Python313/python.exe -B tests/test_compaction_bootstrap.py

This file's first tests, written to close Astra round 6 findings 3 and 4 (board
H-20260921-01). Both findings were the same shape as the rule the hook exists to
enforce, which is why they are tested rather than merely fixed:

  3. a failed `git status` was reported as "0 dirty path(s)", under a line telling
     the reader to prefer it over the compaction summary. Absence is not a
     diagnosis: a missing answer says the work did not finish, never what it found.
  4. the whole-hook budget was checked only AFTER every git call, so the one case
     it existed for - overrunning the host's 15s hook timeout - was the one case
     in which it could not print.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL_DIR = HERE.parent
sys.path.insert(0, str(TOOL_DIR))

import compaction_bootstrap as cb  # noqa: E402


class FakeCompleted:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


class GitResultTests(unittest.TestCase):
    """`None` from _git means "did not answer" and must never become a value."""

    def tearDown(self):
        cb._deadline = None

    def _facts(self, answers):
        """repo_facts() with _git replaced by a dispatch over the first argument."""
        saved = cb._git
        try:
            cb._git = lambda *args: answers.get(args[0], answers.get(" ".join(args)))
            return cb.repo_facts()
        finally:
            cb._git = saved

    # ---- finding 3 --------------------------------------------------------
    def test_status_failure_is_not_reported_as_clean(self):
        """FAILS BEFORE THE FIX: `if dirty else 0` turned None into "0 dirty path(s)"."""
        out = self._facts({
            "rev-parse": "abc1234",
            "status": None,                      # git status did not answer
            "rev-list": "0\t39",
        })
        self.assertNotIn("0 dirty path(s)", out)
        self.assertIn("UNKNOWN", out)

    def test_unknown_field_withdraws_the_prefer_instruction(self):
        """FAILS BEFORE THE FIX: the closing line always claimed precedence.

        An unmeasured field is not better than the summary's figure; telling a
        session to prefer it is worse than saying nothing.
        """
        out = self._facts({
            "rev-parse": "abc1234",
            "status": None,
            "rev-list": "0\t39",
        })
        self.assertNotIn("prefer it over any figure in the summary", out)
        self.assertIn("do not prefer them over anything", out)

    def test_clean_tree_still_reports_zero(self):
        """The over-correction guard: an empty answer IS clean, and must stay so."""
        out = self._facts({
            "rev-parse": "abc1234",
            "status": "",                        # answered, with nothing
            "rev-list": "0\t39",
        })
        self.assertIn("0 dirty path(s)", out)
        self.assertNotIn("UNKNOWN", out)
        self.assertIn("prefer it over any figure in the summary", out)

    def test_dirty_tree_counts_paths(self):
        out = self._facts({
            "rev-parse": "abc1234",
            "status": " M one.py\n?? two.py\n",
            "rev-list": "0\t39",
        })
        self.assertIn("2 dirty path(s)", out)

    def test_head_failure_reports_unavailable(self):
        out = self._facts({"rev-parse": None})
        self.assertIn("unavailable", out)

    def test_position_unknown_also_withdraws_the_prefer_instruction(self):
        out = self._facts({
            "rev-parse": "abc1234",
            "status": "",
            "rev-list": None,
        })
        self.assertIn("position vs origin/main unknown", out)
        self.assertNotIn("prefer it over any figure in the summary", out)


class BudgetTests(unittest.TestCase):
    """The deadline is shared, and it is checked before a call, not after."""

    def setUp(self):
        self.calls = []
        # Replace the module REFERENCE, not `subprocess.run` itself: `cb.subprocess`
        # is the one shared module object, so assigning to its attribute would
        # patch subprocess for the whole process, EntryPointTests included.
        self._saved_subprocess = cb.subprocess
        calls = self.calls

        class FakeSubprocess:
            @staticmethod
            def run(*args, **kwargs):
                calls.append(kwargs)
                return FakeCompleted(stdout="ok", returncode=0)

        cb.subprocess = FakeSubprocess

    def tearDown(self):
        cb.subprocess = self._saved_subprocess
        cb._deadline = None

    # ---- finding 4 --------------------------------------------------------
    def _with_time_left(self, seconds, *args):
        """Drive _git from a fixed remaining budget.

        The budget is stubbed rather than timed, because asserting on elapsed
        wall clock between two adjacent statements is a flake waiting for a
        loaded CI runner, and this suite gates a release. `_time_left` reading
        the real deadline is covered separately, below.
        """
        saved = cb._time_left
        try:
            cb._time_left = lambda: seconds
            return cb._git(*args)
        finally:
            cb._time_left = saved

    def test_git_is_not_called_once_the_budget_is_gone(self):
        """FAILS BEFORE THE FIX: _git always spawned git, whatever the time."""
        self.assertIsNone(self._with_time_left(-1.0, "status", "--porcelain"))
        self.assertEqual(self.calls, [], "git was run after the budget expired")

    def test_call_timeout_is_clamped_to_the_remaining_budget(self):
        """FAILS BEFORE THE FIX: every call passed timeout=4, ignoring the budget."""
        self._with_time_left(1.5, "status", "--porcelain")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["timeout"], 1.5)

    def test_a_long_budget_never_lengthens_a_single_call(self):
        """The clamp is a minimum of the two, not a replacement for the per-call cap."""
        self._with_time_left(999.0, "status", "--porcelain")
        self.assertEqual(self.calls[0]["timeout"], cb.GIT_CALL_TIMEOUT)

    def test_time_left_reads_the_installed_deadline(self):
        """The half _with_time_left stubs out: the deadline is a real clock."""
        cb._deadline = time.monotonic() + 30
        self.assertGreater(cb._time_left(), 25)
        self.assertLessEqual(cb._time_left(), 30)

    def test_four_calls_cannot_outlive_the_host_hook_timeout(self):
        """The arithmetic behind the finding: 4 x GIT_CALL_TIMEOUT > the 15s host
        timeout in .claude/settings.json, but 4 clamped calls cannot exceed TIMEOUT."""
        self.assertGreater(4 * cb.GIT_CALL_TIMEOUT, 15)
        self.assertLess(cb.TIMEOUT, 15)

    def test_no_deadline_installed_uses_the_per_call_timeout(self):
        cb._deadline = None
        cb._git("rev-parse", "HEAD")
        self.assertEqual(self.calls[0]["timeout"], cb.GIT_CALL_TIMEOUT)

    def test_main_installs_a_deadline(self):
        """A deadline nothing installs is a no-op in production, however well tested."""
        cb._deadline = None
        seen = {}
        saved_build, saved_read = cb.build, cb.read_event
        try:
            cb.read_event = lambda: "SessionStart"
            cb.build = lambda: seen.setdefault("deadline", cb._deadline) and ""
            with redirect_stdout(io.StringIO()):   # main() prints its JSON payload
                cb.main()
        finally:
            cb.build, cb.read_event = saved_build, saved_read
        self.assertIsNotNone(seen.get("deadline"), "main() ran build() with no deadline set")


class EntryPointTests(unittest.TestCase):
    """The contract: always exit 0, always print one valid JSON object.

    Run as a real subprocess, because NSC_ROOT and NSC_REPO are read at import.
    """

    def _run(self, stdin_text="{}"):
        tmp = tempfile.TemporaryDirectory(prefix="cbootstrap-")
        self.addCleanup(tmp.cleanup)
        env = dict(os.environ)
        env["NSC_ROOT"] = tmp.name
        env["NSC_REPO"] = tmp.name          # not a git repo: every git call fails
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, "-B", str(TOOL_DIR / "compaction_bootstrap.py")],
            input=stdin_text, capture_output=True, text=True, timeout=30, env=env,
        )
        return proc

    def test_prints_one_valid_json_object_and_exits_zero(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("hookSpecificOutput", payload)
        self.assertIn("additionalContext", payload["hookSpecificOutput"])

    def test_echoes_the_event_name_it_was_given(self):
        proc = self._run(json.dumps({"hook_event_name": "PostCompact"}))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            json.loads(proc.stdout)["hookSpecificOutput"]["hookEventName"], "PostCompact")

    def test_unusable_repo_reports_unavailable_not_clean(self):
        """NOT the end-to-end form of finding 3, and deliberately not labelled as one.

        A non-repo fails at `rev-parse`, so the early head guard returns
        "unavailable" and the status line is never reached -- this passed before
        the fix as well as after. Finding 3's actual window is head succeeding
        while `status` alone fails, which only the mocked unit test reaches.
        Kept as a contract test for the head guard, worth nothing as proof of
        the fix.
        """
        proc = self._run()
        context = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("unavailable", context)
        self.assertNotIn("0 dirty path(s)", context)

    def test_garbage_on_stdin_still_exits_zero(self):
        proc = self._run("not json at all")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        json.loads(proc.stdout)


if __name__ == "__main__":
    unittest.main()
