"""The disposable repository every propagation-check case is built on.

Extracted when test_propagation_check.py was split into three suites: at 1664
lines and 112 seconds it was 45% of the whole host test run, and one file is one
process, so no amount of suite-level concurrency could get under it. The three
suites share this fixture the way the ger suites share ger_fixtures.py.

Each test gets its own `git init`, which is most of where the time goes - the
cost is the repositories, not any one slow case.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import time
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import propagation_check as pc  # noqa: E402

GIT_IDENTITY = [
    "-c", "user.name=Propagation Check Test",
    "-c", "user.email=propagation-check@nosafecircle.invalid",
    "-c", "commit.gpgsign=false",
]


def run_git(repo: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo)] + GIT_IDENTITY + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=pc.CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "git %s failed:\n%s" % (" ".join(args), proc.stdout.decode("utf-8", "replace"))
        )


def write(repo: Path, relative: str, text: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def commit(repo: Path, message: str) -> str:
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message)
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=pc.CREATE_NO_WINDOW,
    )
    return proc.stdout.decode().strip()



class RepoCase(unittest.TestCase):
    """Base class owning one disposable repository per test."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="propcheck-test-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "clone"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "symbolic-ref", "HEAD", "refs/heads/main")

    def analyse(self, rev_range: str, limit: int = 10, do_run: bool = False):
        return pc.analyse(str(self.repo), rev_range, limit, do_run)

    def symbol_names(self, data) -> list:
        return [s["name"] for s in data["removed_symbols"]]

    def selected_paths(self, data) -> list:
        return [t["path"] for t in data["importing_tests"]]
