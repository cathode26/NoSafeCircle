"""RUNNING the selected tests safely: timeouts, killing the whole process
tree, and leaving the clone as it was found.\n
These are the cases that cost real seconds on purpose - a child that sleeps
45 seconds and must be dead at a 2-second timeout cannot be made fast, only
concurrent. Split from test_propagation_check.py; the fixture is shared in
propcheck_fixtures.py.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import propagation_check as pc  # noqa: E402
from propcheck_fixtures import GIT_IDENTITY, RepoCase, commit, run_git, write  # noqa: E402,F401


class RunSafety(RepoCase):
    """--run had no timeout, and read its verdict out of the last line."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        self.base = commit(self.repo, "base")

    def test_a_hung_test_times_out_instead_of_blocking_forever(self):
        write(self.repo, "tests/test_hang.py", """
            import time
            time.sleep(45)
        """)
        commit(self.repo, "a test that hangs")
        run_git(self.repo, "checkout", "-q", "--detach", "HEAD")
        results = pc.run_tests(
            str(self.repo), [pc.SelectedTest(path="tests/test_hang.py")], timeout=2.0
        )
        self.assertEqual("timeout", results[0]["status"])
        self.assertIsNone(results[0]["exit_code"])

    def test_a_failing_test_that_prints_PASS_last_still_reads_as_failed(self):
        """`production_end_to_end_smoke_test.py` did exactly this: a per-case
        "PASS ..." as its final line while exiting 1. The verdict comes from
        the exit code and nothing else."""
        write(self.repo, "tests/test_liar.py", """
            import sys
            print("PASS test_everything_is_fine")
            sys.exit(1)
        """)
        commit(self.repo, "a test that lies in its last line")
        results = pc.run_tests(
            str(self.repo), [pc.SelectedTest(path="tests/test_liar.py")]
        )
        self.assertEqual("fail", results[0]["status"])
        self.assertEqual(1, results[0]["exit_code"])
        self.assertIn("PASS test_everything_is_fine", results[0]["last_line"])

    def test_the_scratch_directory_is_removed(self):
        write(self.repo, "tests/test_ok.py", "print('fine')\n")
        commit(self.repo, "ok")
        before = set(Path(tempfile.gettempdir()).glob("propcheck-*"))
        pc.run_tests(str(self.repo), [pc.SelectedTest(path="tests/test_ok.py")])
        after = set(Path(tempfile.gettempdir()).glob("propcheck-*"))
        self.assertEqual(before, after, "run_tests leaked a scratch directory")

    def test_the_run_carries_its_no_baseline_caveat(self):
        write(self.repo, "tests/test_ok.py", "print('fine')\n")
        head = commit(self.repo, "ok")
        run_git(self.repo, "checkout", "-q", "--detach", head)
        data = self.analyse("%s..%s" % (self.base, head), do_run=True)
        self.assertIsNone(data["run_baseline"])
        self.assertIn("already fail", data["run_caveat"])



# ---------------------------------------------------------------------------
# Round 2 of the review. Each of these is a defect the round-1 fixes either
# introduced or left, and none of them was covered by the 44 tests that were
# green when the round-2 review started.
# ---------------------------------------------------------------------------

class TimeoutReachesTheReport(RepoCase):
    """A timed-out test crashed the default text report with a TypeError.

    `"exit %-3d" % None`. The whole report was lost, after --run had already
    spent up to the timeout on every test.
    """

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        write(self.repo, "tests/test_hang.py", """
            import time
            from pkg.api import VALUE
            time.sleep(45)
        """)
        self.head = commit(self.repo, "head")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def _timed_out_data(self):
        return pc.analyse(
            str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
            run_timeout=2.0,
        )

    def test_the_text_report_survives_a_timeout(self):
        data = self._timed_out_data()
        self.assertTrue(any(r["status"] == "timeout" for r in data["run_results"]))
        report = pc.build_report(data, 10)          # used to raise TypeError
        self.assertIn("TIMEOUT", report)
        self.assertIn("tests/test_hang.py", report)

    def test_a_timeout_counts_as_a_failure_in_the_report_header(self):
        data = self._timed_out_data()
        report = pc.build_report(data, 10)
        self.assertNotIn("0 failed", report)

    def test_main_exits_nonzero_on_a_timeout(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = pc.main([str(self.repo), "%s..%s" % (self.base, self.head),
                            "--run", "--run-timeout", "2"])
        self.assertEqual(1, code, out.getvalue()[-400:])

class TimeoutKillsTheWholeTree(RepoCase):
    """The timeout killed only the direct child, and then blocked on a pipe a
    surviving grandchild still held - the hang it exists to stop."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        self.base = commit(self.repo, "base")

    def test_a_test_that_spawns_a_child_still_times_out_promptly(self):
        write(self.repo, "tests/test_spawner.py", """
            import subprocess
            import sys
            import time
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(45)"])
            print("spawned", child.pid, flush=True)
            time.sleep(45)
        """)
        commit(self.repo, "a test that starts a grandchild")
        started = time.time()
        results = pc.run_tests(
            str(self.repo), [pc.SelectedTest(path="tests/test_spawner.py")], timeout=3.0
        )
        elapsed = time.time() - started
        self.assertEqual("timeout", results[0]["status"])
        # It used to come back only when the grandchild exited, at ~60s here.
        self.assertLess(elapsed, 40, "the timeout waited for the grandchild")

    def test_the_output_written_before_the_hang_is_still_captured(self):
        write(self.repo, "tests/test_noisy_hang.py", """
            import time
            print("MARKER before the hang", flush=True)
            time.sleep(45)
        """)
        commit(self.repo, "a noisy hang")
        results = pc.run_tests(
            str(self.repo), [pc.SelectedTest(path="tests/test_noisy_hang.py")], timeout=3.0
        )
        self.assertEqual("timeout", results[0]["status"])
        self.assertIn("MARKER before the hang", results[0]["last_line"])



# ---------------------------------------------------------------------------
# Round 3 of the review. The first of these was filed by me as "what the tool
# does not catch"; the reviewer proved it is a false green, which is the
# category this tool exists to prevent.
# ---------------------------------------------------------------------------

class TheGrandchildIsActuallyDead(RepoCase):
    """The round-2 mutation for this was caught only by a tearDown error: no
    test asserted the grandchild had been killed, just that we stopped waiting."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        self.base = commit(self.repo, "base")

    def test_the_spawned_child_is_killed_by_the_timeout(self):
        marker = Path(self.tmp.name) / "grandchild.pid"
        write(self.repo, "tests/test_spawner.py", """
            import subprocess
            import sys
            import time
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(45)"])
            open(r"%s", "w").write(str(child.pid))
            time.sleep(45)
        """ % marker)
        commit(self.repo, "spawner")
        results = pc.run_tests(
            str(self.repo), [pc.SelectedTest(path="tests/test_spawner.py")], timeout=3.0
        )
        self.assertEqual("timeout", results[0]["status"])
        pid = int(marker.read_text().strip())
        deadline = time.time() + 15
        while time.time() < deadline and _pid_running(pid):
            time.sleep(0.2)
        self.assertFalse(_pid_running(pid), "the grandchild (pid %d) outlived the kill" % pid)


def _pid_running(pid: int) -> bool:
    proc = subprocess.run(
        ["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=pc.CREATE_NO_WINDOW,
    )
    return str(pid) in proc.stdout.decode("utf-8", "replace")



# ---------------------------------------------------------------------------
# Round 4. Every one of these is a LIVE test id that the first version of
# stale_workflow_test_ids reported as missing - and a false stale id exits 1,
# so it is as harmful as a miss. The guard test that should have caught them
# analysed an empty range and proved nothing.
# ---------------------------------------------------------------------------

class TheCloneIsNotWrittenTo(RepoCase):
    """The always-on git status refreshed .git/index, in a tool whose own CLI
    help calls the clone read-only."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        self.head = commit(self.repo, "head")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def _make_the_stat_cache_stale(self) -> None:
        """Rewrite a tracked file with identical bytes.

        The stat cache has to be STALE for the index test to mean anything:
        straight after a checkout git has nothing to refresh, so even a plain
        `git status` leaves the index alone and the test passes either way.
        Changing only the mtime is exactly what makes git rewrite it.

        Measured, not assumed: with a 0.02 s gap git does not notice and does
        not rewrite the index, so the test passed even with the guard removed.
        Git's stat cache has one-second granularity, so the sleep has to cross
        a whole second for the entry to look stale.
        """
        target = self.repo / "pkg" / "api.py"
        time.sleep(1.1)
        target.write_bytes(target.read_bytes())

    def test_an_analysis_run_leaves_the_index_byte_identical(self):
        import hashlib

        self._make_the_stat_cache_stale()
        index = self.repo / ".git" / "index"
        before = hashlib.sha256(index.read_bytes()).hexdigest()
        self.analyse("%s..%s" % (self.base, self.head))
        after = hashlib.sha256(index.read_bytes()).hexdigest()
        self.assertEqual(before, after, "the analysis wrote to .git/index")

    def test_the_stale_cache_trick_does_not_change_the_content(self):
        """Guards the trick: if it dirtied the tree, the test above would be
        measuring something else entirely."""
        self._make_the_stat_cache_stale()
        self.assertFalse(pc.worktree_is_dirty(str(self.repo)))

class TheTextReportCarriesTheWarnings(RepoCase):
    """The warnings existed only in the JSON, so a reader of the text report
    could mistake the escape hatch's output for the range's."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        write(self.repo, "tests/test_api.py", "print('ok')\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        self.head = commit(self.repo, "head")
        write(self.repo, "unrelated.py", "X = 1\n")
        commit(self.repo, "parked elsewhere")

    def test_the_report_warns_that_the_clone_is_not_at_the_head(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        report = pc.build_report(data, 10)
        self.assertIn("not at the head", report)
        self.assertIn("checkout --detach", report)

    def test_the_report_says_run_results_are_not_the_ranges(self):
        data = pc.analyse(
            str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
            allow_tree_mismatch=True,
        )
        report = pc.build_report(data, 10)
        self.assertIn("NOT THIS RANGE", report)

    def test_the_report_carries_the_no_baseline_caveat(self):
        run_git(self.repo, "checkout", "-q", "--detach", self.head)
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        report = pc.build_report(data, 10)
        self.assertIn("NO BASELINE", report)

    def test_a_clean_run_at_the_head_has_no_tree_warning(self):
        run_git(self.repo, "checkout", "-q", "--detach", self.head)
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        report = pc.build_report(data, 10)
        self.assertNotIn("NOT THIS RANGE", report)
        self.assertNotIn("not at the head", report)

if __name__ == "__main__":
    unittest.main(verbosity=2)
