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
import contextlib
import io
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

TOOL = pathlib.Path(__file__).resolve().parents[1] / "guarded_merge.py"
sys.path.insert(0, str(TOOL.parent))
import guarded_merge as merger
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
    def setUp(self):
        patcher = mock.patch.object(merger.lock, "_boot_stamp", return_value="unavailable: test fixture")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tool_command(self, *args):
        script = ("import sys; sys.path.insert(0,sys.argv.pop(1)); import guarded_merge as m; "
                  "m.lock._boot_stamp=lambda:'unavailable: test fixture'; sys.exit(m.cli())")
        return [sys.executable, "-B", "-c", script, str(TOOL.parent), *args]

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
            self.tool_command("--role", role,
             "--candidate", candidate, "--authority", "test",
             "--not-proven", "nothing; this is a fixture",
             "--repo", str(repo), "--journal", str(journal),
             "--validate", "stub_validate.py",
             "--lock-timeout", str(timeout)),
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


class UncertainMutationReporting(Base):
    def test_postcommit_release_failure_does_not_claim_refusal(self):
        repo, journal, candidate = self.build_fixture()
        args = ["--role", "Fixture Agent", "--candidate", candidate, "--authority", "test",
                "--repo", str(repo), "--journal", str(journal), "--validate", "stub_validate.py"]
        with mock.patch.object(merger.lock, "release", side_effect=merger.lock.MainWriteLockError("fixture release failed")):
            with self.assertRaises(SystemExit) as caught:
                merger.cli(args)
        self.assertIn("FAILED:", str(caught.exception))
        self.assertNotIn("REFUSED", str(caught.exception))
        self.assertIn("result may already be committed", str(caught.exception))
        self.assertEqual(candidate, git(repo, "rev-parse", "HEAD"))
        self.assertIsNotNone(merger.lock.inspect(repo=repo))

    def exercise_uncertain_validator(self, *, broken_journal=False):
        repo, journal, candidate = self.build_fixture()
        real_run = merger.lock.run_process
        real_append = merger.append
        def interrupted(command, **kwargs):
            # The POST-COMMIT validator specifically. guarded_merge now also
            # validates a TRIAL MERGE WORKTREE before it writes main, so
            # matching on the script name alone would interrupt that one
            # instead and main would never move -- which is a different case,
            # covered by its own test. The post-commit run is the one whose cwd
            # is the repository itself.
            if ("stub_validate.py" in command
                    and str(kwargs.get("cwd")) == str(repo)):
                raise merger.lock.MutationChildUncertain("fixture validator child may still run")
            return real_run(command, **kwargs)
        def append(path, text):
            if broken_journal and "MAIN-WRITE END" in text:
                raise OSError("fixture journal unavailable")
            return real_append(path, text)
        args = ["--role", "Fixture Agent", "--candidate", candidate, "--authority", "test",
                "--repo", str(repo), "--journal", str(journal), "--validate", "stub_validate.py"]
        with mock.patch.object(merger.lock, "run_process", side_effect=interrupted), \
                mock.patch.object(merger, "append", side_effect=append):
            with self.assertRaises(SystemExit) as caught:
                merger.cli(args)
        self.assertIn("UNCERTAIN:", str(caught.exception))
        self.assertNotIn("REFUSED", str(caught.exception))
        self.assertIn("result may already be committed", str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, merger.lock.MutationChildUncertain)
        self.assertEqual(candidate, git(repo, "rev-parse", "HEAD"))
        self.assertIsNotNone(merger.lock.inspect(repo=repo), "uncertainty must retain the owner")
        return journal

    def test_uncertain_postcommit_validator_records_end_and_retains_owner(self):
        journal = self.exercise_uncertain_validator()
        text = journal.read_text(encoding="utf-8")
        self.assertEqual(1, text.count("MAIN-WRITE END"))
        self.assertIn("UNCERTAIN; result may already be committed", text)

    def test_failed_uncertainty_journal_does_not_mask_or_release(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            journal = self.exercise_uncertain_validator(broken_journal=True)
        self.assertIn("uncertainty END could not be recorded", output.getvalue())
        self.assertIn("fixture journal unavailable", output.getvalue())
        self.assertEqual(1, journal.read_text().count("MAIN-WRITE START"))

    def test_failed_stderr_diagnostic_still_preserves_uncertainty(self):
        stream = mock.Mock()
        stream.write.side_effect = OSError("fixture stderr unavailable")
        with contextlib.redirect_stderr(stream):
            self.exercise_uncertain_validator(broken_journal=True)


class AdmissionFailureReporting(Base):
    def arguments(self, repo, journal, candidate):
        return ["--role", "Fixture Agent", "--candidate", candidate, "--authority", "test",
                "--repo", str(repo), "--journal", str(journal), "--validate", "stub_validate.py",
                "--lock-timeout", "0"]

    def test_non_git_target_reports_pre_admission_failure(self):
        with tempfile.TemporaryDirectory(prefix="non-git-merge-target-") as tmp:
            repo = pathlib.Path(tmp)
            journal = repo / "journal.md"
            result = subprocess.run(self.tool_command(*self.arguments(repo, journal, "unused")),
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("PRE-ADMISSION FAILED", result.stderr)
            self.assertIn("main untouched by this invocation", result.stderr)
            self.assertNotIn("may already be committed", result.stderr)
            self.assertFalse(journal.exists())
            self.assertEqual([], list(repo.iterdir()))

    def test_acquisition_timeout_reports_pre_admission_failure(self):
        repo, journal, candidate = self.build_fixture()
        head = git(repo, "rev-parse", "HEAD")
        owner = merger.lock.acquire(repo=repo, role="Holder Agent", operation="fixture")
        try:
            # The bounded helper regression proves the real retry deadline.
            # This case checks only its merger-level outcome classification.
            timeout = merger.lock.MainWriteLockError(
                f"timed out acquiring {LOCK_REF}; ownership changed during inspection")
            with mock.patch.object(merger.lock, "acquire", side_effect=timeout):
                with self.assertRaises(SystemExit) as caught:
                    merger.cli(self.arguments(repo, journal, candidate))
            self.assertIn("PRE-ADMISSION FAILED", str(caught.exception))
            self.assertIn("timed out acquiring", str(caught.exception))
            self.assertNotIn("may already be committed", str(caught.exception))
            self.assertEqual(head, git(repo, "rev-parse", "HEAD"))
            self.assertEqual(owner.owner_oid, merger.lock.inspect(repo=repo)[0])
            self.assertEqual([], self.journal_lines(journal))
        finally:
            merger.lock.release(owner)

    def test_uncertain_acquisition_is_not_called_pre_admission_failure(self):
        repo, journal, candidate = self.build_fixture()
        with mock.patch.object(merger.lock, "acquire",
                               side_effect=merger.lock.MutationChildUncertain("fixture acquisition may have taken ownership")):
            with self.assertRaises(SystemExit) as caught:
                merger.cli(self.arguments(repo, journal, candidate))
        self.assertIn("UNCERTAIN:", str(caught.exception))
        self.assertNotIn("PRE-ADMISSION", str(caught.exception))

    def test_completed_reboot_recovery_reports_no_business_admission(self):
        repo, journal, candidate = self.build_fixture()
        head = git(repo, "rev-parse", "HEAD")
        report = repo / ".git/nsc-main-write-recovery/fixture.json"
        with mock.patch.object(merger.lock, "acquire",
                               side_effect=merger.lock.MainWriteLockRecovered(report)):
            with self.assertRaises(SystemExit) as caught:
                merger.cli(self.arguments(repo, journal, candidate))
        self.assertIn("RECOVERED:", str(caught.exception))
        self.assertIn("NOT started", str(caught.exception))
        self.assertIn(str(report), str(caught.exception))
        self.assertNotIn("PRE-ADMISSION FAILED", str(caught.exception))
        self.assertEqual(head, git(repo, "rev-parse", "HEAD"))
        self.assertEqual([], self.journal_lines(journal))

    def test_admitted_body_error_is_not_called_pre_admission_failure(self):
        repo, _, _ = self.build_fixture()
        with self.assertRaises(merger.lock.MainWriteLockError) as caught:
            with merger.held(merger.Git(repo), "Fixture Agent", 0):
                raise merger.lock.MainWriteLockError("fixture admitted observation error")
        self.assertNotIsInstance(caught.exception, merger.PreAdmissionFailure)
        self.assertIsNone(merger.lock.inspect(repo=repo))

    def test_merger_warns_about_recent_legacy_writer_at_entry(self):
        repo, journal, candidate = self.build_fixture()
        journal.write_text(f"- {merger.stamp()} MAIN-WRITE START Legacy Agent: fixture\n")
        result = subprocess.run(self.tool_command(*self.arguments(repo, journal, candidate)),
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("recent legacy writer may bypass", result.stderr)
        self.assertIn("Legacy Agent", result.stderr)
        self.assertEqual(candidate, git(repo, "rev-parse", "HEAD"))

    def test_merger_refuses_non_main_without_writing(self):
        repo, journal, candidate = self.build_fixture()
        head = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-b", "feature")
        code, output = self.run_tool(repo, journal, "Fixture Agent", candidate)
        self.assertNotEqual(0, code)
        self.assertIn("not checked out on main", output)
        self.assertIn("main untouched", output)
        self.assertEqual(head, git(repo, "rev-parse", "HEAD"))
        self.assertEqual("", git(repo, "status", "--porcelain"))
        self.assertIsNone(merger.lock.inspect(repo=repo))


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


class ValidateGatesTheMergeRatherThanReportingOnIt(Base):
    """The post-commit validate is a post-mortem; this is the gate.

    Measured 2026-09-23: guarded_merge merged, THEN ran taskcontrol validate,
    then returned its exit code. Nothing rolled back, so a candidate that fails
    validation left main red and the operator read "validate : FAIL" after the
    fact. The Game Agent re-read its own seven merges that night and found every
    one printed PASS while none of them had been protected by it.
    """

    def break_validate_for_the_candidate(self, repo: pathlib.Path) -> str:
        """Make the CANDIDATE fail validation while main still passes.

        The stub must fail only in the merged state, or the tool would refuse
        for the ordinary reason and prove nothing about the gate.
        """
        git(repo, "checkout", "-q", "candidate")
        (repo / "stub_validate.py").write_text(
            "import pathlib, sys" + EOL
            + "sys.exit(1 if pathlib.Path('change.txt').exists() else 0)" + EOL,
            encoding="utf-8")
        git(repo, "add", "stub_validate.py")
        git(repo, "commit", "-m", "candidate breaks validation", "--no-gpg-sign")
        candidate = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "main")
        return candidate

    def test_a_candidate_that_fails_validate_is_refused_and_main_is_untouched(self):
        repo, journal, _candidate = self.build_fixture()
        candidate = self.break_validate_for_the_candidate(repo)
        before = git(repo, "rev-parse", "HEAD")
        code, output = self.run_tool(repo, journal, "Fixture Agent", candidate)
        self.assertEqual(1, code)
        self.assertIn("main untouched", output)
        self.assertIn("RED", output)
        # The assertion that matters: nothing was written.
        self.assertEqual(before, git(repo, "rev-parse", "HEAD"))
        self.assertEqual("", git(repo, "status", "--porcelain"))
        self.assertEqual(0, self.open_starts(journal),
                         "a refusal must still close its journal window")
        self.assertIsNone(merger.lock.inspect(repo=repo),
                          "a refusal must release the lock")

    def test_the_trial_worktree_is_removed_even_when_it_refuses(self):
        repo, journal, _candidate = self.build_fixture()
        candidate = self.break_validate_for_the_candidate(repo)
        self.run_tool(repo, journal, "Fixture Agent", candidate)
        worktrees = git(repo, "worktree", "list", "--porcelain")
        self.assertEqual(
            1, worktrees.count("worktree "),
            f"a trial worktree was left behind: {worktrees}")

    def test_a_healthy_candidate_still_merges(self):
        """The gate must not refuse the ordinary case."""
        repo, journal, candidate = self.build_fixture()
        code, output = self.run_tool(repo, journal, "Fixture Agent", candidate)
        self.assertEqual(0, code, output)
        self.assertEqual(candidate, git(repo, "rev-parse", "HEAD"))

    def test_an_interrupted_pre_merge_validator_refuses_rather_than_claiming_uncertainty(self):
        """Uncertainty BEFORE the write is a refusal, not "may be committed".

        The outer uncertainty handler exists for a validator interrupted AFTER
        the merge, where main really may have moved. Reporting that here would
        send an operator to inspect a merge that does not exist.
        """
        repo, journal, candidate = self.build_fixture()
        before = git(repo, "rev-parse", "HEAD")
        real_run = merger.lock.run_process

        def interrupted(command, **kwargs):
            if ("stub_validate.py" in command
                    and str(kwargs.get("cwd")) != str(repo)):
                raise merger.lock.MutationChildUncertain("fixture pre-merge child")
            return real_run(command, **kwargs)

        args = ["--role", "Fixture Agent", "--candidate", candidate,
                "--authority", "test", "--repo", str(repo),
                "--journal", str(journal), "--validate", "stub_validate.py"]
        with mock.patch.object(merger.lock, "run_process", side_effect=interrupted):
            code = merger.main(args)
        self.assertEqual(1, code)
        self.assertEqual(before, git(repo, "rev-parse", "HEAD"))
        entries = EOL.join(self.journal_lines(journal))
        self.assertIn("ABORTED, nothing written", entries)
        self.assertNotIn("may already be committed", entries)


if __name__ == "__main__":
    unittest.main(verbosity=2)
