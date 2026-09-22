#!/usr/bin/env python
"""Two mergers running at once: one proceeds, the others abort cleanly.

Run:
    python -B test_guarded_merge.py

Vincent's condition for the Pipeline Maintainer's merge half going live was
*"If the atomic merge works and they both can run it and not cause any issue"* -
and that it be shown, not asserted. So every case launches real concurrent
processes against a throwaway repository and a throwaway journal. Nothing here
touches canonical main or the live journal; the tool takes --repo and --journal
precisely so this is possible, which the folder-local predecessor did not.

unittest rather than the plain-function idiom used elsewhere in this tree,
because `run_tool_tests.py` counts tests from a unittest summary and marks a
suite reporting none as FAILED. The first version printed its own PASS line and
the runner correctly called it "ran no tests" - the mismatch Astra warned about
in review, catching me rather than someone else.

The predecessor was atomic about the right thing and not about this one. It
re-derived main and merged inside one process, closing the window where main
moves mid-merge. It then checked the journal for an open MAIN-WRITE and wrote
its own START several steps later, so two processes could both pass that check
before either wrote. The name was accurate for one merger and stopped covering
the case the moment two roles shared the tool.
"""
from __future__ import annotations

import concurrent.futures
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import unittest

TOOL = pathlib.Path(__file__).resolve().parents[1] / "guarded_merge.py"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LOCK_REF = "refs/locks/main-write"
NAMES = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf",
         "Hotel"]
EOL = chr(10)


def git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args],
                            capture_output=True, text=True,
                            creationflags=NO_WINDOW)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {result.stderr}")
    return result.stdout.strip()


class Base(unittest.TestCase):
    def build_fixture(self) -> tuple[pathlib.Path, pathlib.Path, str]:
        """A repo with main and a candidate branch, plus an empty journal."""
        root = pathlib.Path(tempfile.mkdtemp(prefix="guarded-merge-"))
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture Agent")
        git(repo, "config", "user.email", "fixture@nosafecircle.invalid")
        (repo / "base.txt").write_text("base", encoding="utf-8")
        # The tool runs a validate command inside the repo; give it a trivial
        # one. It must be COMMITTED - an untracked file makes the worktree
        # dirty, which the tool correctly refuses to merge into, and the first
        # run of this suite proved that by failing on its own fixture.
        (repo / "stub_validate.py").write_text(
            "import sys" + EOL + "sys.exit(0)" + EOL, encoding="utf-8")
        git(repo, "add", "base.txt", "stub_validate.py")
        git(repo, "commit", "-m", "base", "--no-gpg-sign")

        git(repo, "checkout", "-q", "-b", "candidate")
        (repo / "change.txt").write_text("change", encoding="utf-8")
        git(repo, "add", "change.txt")
        git(repo, "commit", "-m", "candidate work", "--no-gpg-sign")
        candidate = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "main")

        journal = root / "journal.md"
        journal.write_text("# throwaway journal" + EOL, encoding="utf-8")
        return repo, journal, candidate

    def run_tool(self, repo: pathlib.Path, journal: pathlib.Path, role: str,
                 candidate: str, timeout: float = 5.0) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--role", role,
             "--candidate", candidate, "--authority", "test",
             "--not-proven", "nothing; this is a fixture",
             "--repo", str(repo), "--journal", str(journal),
             "--validate", "stub_validate.py",
             "--lock-timeout", str(timeout)],
            capture_output=True, text=True, creationflags=NO_WINDOW)
        return result.returncode, result.stdout + result.stderr

    def journal_lines(self, journal: pathlib.Path) -> list[str]:
        return [l for l in journal.read_text(encoding="utf-8").splitlines()
                if l.startswith("- ")]

    def open_starts(self, journal: pathlib.Path) -> int:
        depth = 0
        for line in self.journal_lines(journal):
            if "MAIN-WRITE START" in line:
                depth += 1
            elif "MAIN-WRITE END" in line:
                depth -= 1
        return depth


class TwoMergersSerialise(Base):
    def test_a_lone_merge_succeeds(self):
        repo, journal, candidate = self.build_fixture()
        code, output = self.run_tool(repo, journal,
                                     "Pipeline Maintainer Agent", candidate)
        self.assertEqual(0, code, f"a lone merge must succeed{EOL}{output}")
        self.assertEqual(candidate, git(repo, "rev-parse", "HEAD"))
        self.assertEqual(0, self.open_starts(journal),
                         "the journal must not carry an unclosed START")

    def test_two_at_once_produce_exactly_one_merge(self):
        """The condition Vincent set, exercised rather than asserted."""
        repo, journal, candidate = self.build_fixture()
        roles = ["Pipeline Maintainer Agent", "Game Agent"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda role: self.run_tool(repo, journal, role, candidate),
                roles))
        winners = [r for r in results if r[0] == 0]
        self.assertEqual(1, len(winners),
                         f"exactly one merger may proceed: {results}")
        self.assertEqual(0, self.open_starts(journal),
                         "no unclosed START may survive a contested merge")
        self.assertEqual(candidate, git(repo, "rev-parse", "HEAD"))

    def test_eight_at_once_still_produce_exactly_one(self):
        """Weak on its own - see the two-candidate case for why."""
        repo, journal, candidate = self.build_fixture()
        roles = [f"{name} Agent" for name in NAMES]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda role: self.run_tool(repo, journal, role, candidate),
                roles))
        self.assertEqual(1, len([r for r in results if r[0] == 0]),
                         "exactly one of eight may merge")
        self.assertEqual(0, self.open_starts(journal))

    def test_two_different_candidates_serialise_rather_than_racing(self):
        """The case that actually discriminates. The others do not.

        Eight mergers of the SAME candidate produce one merge even without a
        lock, because git refuses the rest with "already an ancestor" - that
        assertion observes git's idempotence and passes on a racy tool.
        Measured: seven of seven losers refused for that reason and not one
        ever saw the lock.

        Two DIFFERENT candidates is where a race does damage. Unserialised,
        both read the same HEAD and the second merges from a base that has
        moved. Serialised, the second waits, re-derives, and records the
        first's result as its own expected HEAD - asserted below, and false
        for any racing interleaving.
        """
        repo, journal, first = self.build_fixture()
        git(repo, "checkout", "-q", "-b", "second", "main")
        (repo / "other.txt").write_text("other", encoding="utf-8")
        git(repo, "add", "other.txt")
        git(repo, "commit", "-m", "an independent candidate", "--no-gpg-sign")
        second = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "main")

        work = [("Pipeline Maintainer Agent", first), ("Game Agent", second)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda pair: self.run_tool(repo, journal, pair[0], pair[1]),
                work))
        self.assertTrue(all(code == 0 for code, _ in results),
                        f"both independent candidates should land: {results}")
        self.assertEqual(0, self.open_starts(journal))

        starts = [l for l in self.journal_lines(journal)
                  if "MAIN-WRITE START" in l]
        ends = [l for l in self.journal_lines(journal)
                if "MAIN-WRITE END" in l]
        self.assertEqual(2, len(starts))
        self.assertEqual(2, len(ends))

        expected = [re.search(r"expected HEAD ([0-9a-f]+)", l).group(1)
                    for l in starts]
        self.assertNotEqual(
            expected[0], expected[1],
            "both mergers recorded the SAME expected HEAD, so neither waited "
            "for the other: they raced, and the second merged from a base "
            "that had already moved")
        produced = re.search(r"new HEAD ([0-9a-f]+)", ends[0]).group(1)
        self.assertTrue(
            produced.startswith(expected[1]),
            "the second merger must re-derive HEAD after the first finishes; "
            f"it expected {expected[1]} and the first produced {produced[:12]}")


class TheJournalSurvivesContention(Base):
    def test_no_line_is_lost_or_interleaved(self):
        """Atomic appends, not read-modify-write.

        The predecessor read the whole journal, concatenated a line and wrote
        it back; two writers doing that lose whichever line was read before the
        other wrote.
        """
        repo, journal, candidate = self.build_fixture()
        roles = [f"{name} Agent" for name in NAMES[:6]]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(
                lambda role: self.run_tool(repo, journal, role, candidate),
                roles))
        lines = self.journal_lines(journal)
        self.assertTrue(lines, "the contested run must have written something")
        for line in lines:
            self.assertTrue(line.startswith("- 20"),
                            f"a truncated or interleaved line survived: {line}")
            self.assertTrue("MAIN-WRITE" in line or "MERGE REFUSED" in line,
                            f"unrecognised journal line: {line}")
        self.assertEqual(1, sum("MAIN-WRITE START" in l for l in lines),
                         "exactly one START across six contenders")


class TheGuardRefusesBeforeWriting(Base):
    def test_an_unparseable_role_is_refused(self):
        repo, journal, candidate = self.build_fixture()
        code, output = self.run_tool(repo, journal, "pipeline", candidate)
        self.assertNotEqual(0, code)
        self.assertIn("Agent, Steward or Orchestrator", output)
        self.assertEqual([], self.journal_lines(journal),
                         "a refused role must not write to the journal at all")

    def plant_lock(self, repo: pathlib.Path, holder: bytes) -> str:
        """Point the lock ref at a blob, as a live holder would."""
        blob = subprocess.run(
            ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
            input=holder, capture_output=True, check=True,
            creationflags=NO_WINDOW).stdout.decode().strip()
        subprocess.run(
            ["git", "-C", str(repo), "update-ref", LOCK_REF, blob, ""],
            capture_output=True, check=True, creationflags=NO_WINDOW)
        return blob

    def test_a_live_lock_refuses_rather_than_merging(self):
        """The lock must actually exclude, not merely be consulted."""
        repo, journal, candidate = self.build_fixture()
        self.plant_lock(repo, f"Ghost Agent|99999|{time.time():.0f}|now{EOL}"
                        .encode("utf-8"))
        code, output = self.run_tool(repo, journal,
                                     "Pipeline Maintainer Agent", candidate,
                                     timeout=1.0)
        self.assertNotEqual(0, code, "a held lock must refuse the merge")
        self.assertIn("REFUSED", output)
        self.assertIn("Ghost Agent", output,
                      "the refusal must name who holds it")
        self.assertNotEqual(candidate, git(repo, "rev-parse", "HEAD"),
                            "main must be untouched while another holds it")

    def test_an_old_lock_still_requires_explicit_recovery(self):
        """Age is diagnostic; it never revokes a live writer."""
        repo, journal, candidate = self.build_fixture()
        self.plant_lock(repo, b"Ghost Agent|99999|1|long ago" + EOL.encode())
        code, output = self.run_tool(repo, journal,
                                     "Pipeline Maintainer Agent", candidate,
                                     timeout=0.0)
        self.assertNotEqual(0, code, f"an old lock must still block{EOL}{output}")
        self.assertIn("OVERDUE", output)
        self.assertNotEqual(candidate, git(repo, "rev-parse", "HEAD"))

    def test_only_the_holder_can_release(self):
        """Release is a compare-and-swap, so a foreign delete cannot steal it."""
        repo, _journal, _candidate = self.build_fixture()
        mine = self.plant_lock(repo, b"Holder Agent|1|1|now" + EOL.encode())
        other = subprocess.run(
            ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
            input=b"Other Agent|2|2|now" + EOL.encode(), capture_output=True,
            check=True, creationflags=NO_WINDOW).stdout.decode().strip()
        stolen = subprocess.run(
            ["git", "-C", str(repo), "update-ref", "-d", LOCK_REF, other],
            capture_output=True, creationflags=NO_WINDOW)
        self.assertNotEqual(0, stolen.returncode,
                            "a non-holder must not be able to delete the lock")
        self.assertEqual(mine, git(repo, "rev-parse", LOCK_REF),
                         "the lock must still belong to its holder")


if __name__ == "__main__":
    unittest.main(verbosity=2)
