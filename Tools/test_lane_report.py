#!/usr/bin/env python3
"""Regression test for lane_report.py's verification-worktree safety.

WHY THIS EXISTS. The original code built a PREDICTABLE path from the branch name alone
("lane-verify-" + branch) and force-removed whatever was registered there before adding a new
worktree, and again in `finally`, unconditionally, with no ownership check and no dirty check. So
a second run of the tool for the same branch - or anyone who had checked out that exact path by
hand to investigate a failed lane - had their uncommitted work silently discarded. The fix
allocates a fresh, uniquely-named path per run and never force-removes anything it did not itself
create in that run.

This test builds a THROWAWAY git repository (never canonical, never a checkout under
C:/nscrev this fix did not create) with a branch to report on, registers a worktree at the
path the OLD naming scheme would collide with, and puts an uncommitted file in it. It then runs
lane_report.py against that throwaway repo and asserts the uncommitted file survives.

Run:

    python -B Tools/test_lane_report.py
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
LANE_REPORT = REPO_ROOT / "Tools" / "lane_report.py"


def _run(cwd, *args, check=True):
    finished = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True)
    if check and finished.returncode != 0:
        raise RuntimeError("git {0} failed: {1}".format(
            " ".join(args), finished.stderr.decode("utf-8", errors="replace")))
    return finished.stdout.decode("utf-8", errors="replace").strip()


class WorktreeSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lane_report_test_")
        self.repo = pathlib.Path(self.tmp) / "repo"
        self.repo.mkdir()
        _run(self.repo, "init", "-q", "-b", "main")
        _run(self.repo, "config", "user.email", "test@test.local")
        _run(self.repo, "config", "user.name", "test")
        (self.repo / "file.txt").write_text("hello\n", encoding="utf-8")
        _run(self.repo, "add", "file.txt")
        _run(self.repo, "commit", "-q", "-m", "init")
        _run(self.repo, "checkout", "-q", "-b", "lane/test")
        (self.repo / "file.txt").write_text("hello\nlane change\n", encoding="utf-8")
        _run(self.repo, "commit", "-q", "-am", "lane change")
        _run(self.repo, "checkout", "-q", "main")

        # The path the OLD naming scheme derives deterministically from the branch name alone -
        # exactly what a second run, or a by-hand investigation checkout, would occupy.
        self.collision_path = pathlib.Path(self.tmp) / "lane-verify-lane-test"
        _run(self.repo, "worktree", "add", "-q", "--detach", str(self.collision_path), "main")
        self.precious_file = self.collision_path / "precious_uncommitted_work.txt"
        self.precious_file.write_text("DO NOT LOSE THIS\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_preexisting_worktree_survives_a_lane_report_run(self):
        """THE REGRESSION THIS FIX ADDRESSES: running lane_report.py for the same branch name must
        never touch a worktree it did not itself create in this run. Restoring the old
        force-remove-by-predictable-path code makes this test fail (the file is destroyed)."""
        self.assertTrue(self.precious_file.exists(), "fixture sanity: precious file must exist "
                         "before the tool ever runs")
        subprocess.run([sys.executable, "-B", str(LANE_REPORT), "lane/test",
                         "--repo", str(self.repo)], capture_output=True)
        self.assertTrue(self.collision_path.exists(),
                         "a pre-existing worktree at the old predictable path must survive")
        self.assertTrue(self.precious_file.exists(),
                         "the uncommitted file inside a pre-existing worktree must survive")
        self.assertEqual(self.precious_file.read_text(encoding="utf-8"), "DO NOT LOSE THIS\n",
                          "the uncommitted file's content must be untouched")

    def test_own_verification_worktree_is_cleaned_up(self):
        """The tool must still clean up after ITSELF - only the pre-existing, unrelated worktree
        is protected. Two runs must not accumulate worktrees forever."""
        before = _run(self.repo, "worktree", "list")
        subprocess.run([sys.executable, "-B", str(LANE_REPORT), "lane/test",
                         "--repo", str(self.repo)], capture_output=True)
        after = _run(self.repo, "worktree", "list")
        # Exactly the two worktrees that existed before (main's checkout + the collision one)
        # should remain; the tool's own trial-merge worktree must not linger.
        self.assertEqual(len(before.splitlines()), len(after.splitlines()),
                          "the tool's own verification worktree must be removed after the run:\n"
                          "before:\n{0}\nafter:\n{1}".format(before, after))


if __name__ == "__main__":
    unittest.main()
