#!/usr/bin/env python
"""Two mergers running at once: one proceeds, the others abort cleanly.

Run:
    python -B test_guarded_merge.py

Vincent's condition for the Pipeline Maintainer's merge half going live was
*"If the atomic merge works and they both can run it and not cause any issue"* -
and that it be shown, not asserted. So every case here launches real concurrent
processes against a throwaway repository and a throwaway journal. Nothing
touches canonical main or the live journal; the tool takes --repo and --journal
precisely so this is possible, which the folder-local predecessor did not.

The predecessor was atomic about the right thing and not about this one. It
re-derived main and merged inside one process, closing the window where main
moves mid-merge - the failure that bit twice in one hour on 2026-09-22. It then
checked the journal for an open MAIN-WRITE and wrote its own START several steps
later, so two processes could both pass that check before either wrote. The name
was accurate for one merger and stopped covering the case the moment two roles
shared the tool.
"""
from __future__ import annotations

import concurrent.futures
import os
import pathlib
import re
import subprocess
import sys
import tempfile

TOOL = pathlib.Path(__file__).resolve().parents[1] / "guarded_merge.py"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args],
                            capture_output=True, text=True,
                            creationflags=NO_WINDOW)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {result.stderr}")
    return result.stdout.strip()


def build_fixture() -> tuple[pathlib.Path, pathlib.Path, str]:
    """A repo with main and a candidate branch, plus an empty journal."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="guarded-merge-"))
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Fixture Agent")
    git(repo, "config", "user.email", "fixture@nosafecircle.invalid")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    # The tool runs a validate command inside the repo; give it a trivial one
    # so the fixture does not need the real TaskGraph. It must be COMMITTED --
    # an untracked file makes the worktree dirty, which the tool correctly
    # refuses to merge into, and the first run of this test proved that by
    # failing on its own fixture.
    (repo / "stub_validate.py").write_text(
        "import sys\nprint('stub validate ok')\nsys.exit(0)\n",
        encoding="utf-8")
    git(repo, "add", "base.txt", "stub_validate.py")
    git(repo, "commit", "-m", "base", "--no-gpg-sign")

    git(repo, "checkout", "-q", "-b", "candidate")
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    git(repo, "add", "change.txt")
    git(repo, "commit", "-m", "candidate work", "--no-gpg-sign")
    candidate = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")


    journal = root / "journal.md"
    journal.write_text("# throwaway journal\n", encoding="utf-8")
    return repo, journal, candidate


def run_tool(repo: pathlib.Path, journal: pathlib.Path, role: str,
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


def journal_lines(journal: pathlib.Path) -> list[str]:
    return [l for l in journal.read_text(encoding="utf-8").splitlines()
            if l.startswith("- ")]


def open_starts(journal: pathlib.Path) -> int:
    depth = 0
    for line in journal_lines(journal):
        if "MAIN-WRITE START" in line:
            depth += 1
        elif "MAIN-WRITE END" in line:
            depth -= 1
    return depth


def test_one_merger_succeeds_alone() -> None:
    repo, journal, candidate = build_fixture()
    code, output = run_tool(repo, journal, "Pipeline Maintainer Agent", candidate)
    require(code == 0, f"a lone merge must succeed, got {code}\n{output}")
    require(git(repo, "rev-parse", "HEAD") == candidate,
            "main must be at the candidate after a fast-forward merge")
    require(open_starts(journal) == 0,
            f"the journal must not carry an unclosed START\n"
            f"{journal.read_text(encoding='utf-8')}")


def test_two_mergers_at_once_produce_exactly_one_merge() -> None:
    """The condition Vincent set, exercised rather than asserted."""
    repo, journal, candidate = build_fixture()
    roles = ["Pipeline Maintainer Agent", "Game Agent"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda role: run_tool(repo, journal, role, candidate), roles))

    winners = [r for r in results if r[0] == 0]
    losers = [r for r in results if r[0] != 0]
    detail = "\n".join(f"[exit {c}] {o.strip()[:300]}" for c, o in results)
    require(len(winners) == 1,
            f"exactly one merger may proceed, {len(winners)} did\n{detail}")
    require(len(losers) == 1,
            f"the other must refuse, {len(losers)} did\n{detail}")
    require("REFUSED" in losers[0][1] or "already an ancestor" in losers[0][1],
            f"the loser must say why it refused\n{losers[0][1][:400]}")
    require(open_starts(journal) == 0,
            f"no unclosed START may survive a contested merge\n"
            f"{journal.read_text(encoding='utf-8')}")
    require(git(repo, "rev-parse", "HEAD") == candidate,
            "main must be merged exactly once")


def test_eight_mergers_at_once_still_produce_exactly_one() -> None:
    """Two is the requirement; eight is where a race actually shows itself."""
    repo, journal, candidate = build_fixture()
    roles = [f"{name} Agent" for name in ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda role: run_tool(repo, journal, role, candidate), roles))
    winners = [r for r in results if r[0] == 0]
    require(len(winners) == 1,
            f"exactly one of eight may merge, {len(winners)} did\n"
            + "\n".join(f"[{c}] {o.strip()[:120]}" for c, o in results))
    require(open_starts(journal) == 0, "no unclosed START among eight")


def test_two_different_candidates_serialise_rather_than_racing() -> None:
    """The test that actually discriminates. The others do not.

    Eight mergers of the SAME candidate produce one merge even without a lock,
    because git refuses the rest with "already an ancestor" - so that assertion
    observes git's idempotence and would pass on a racy tool. Measured: seven
    of seven losers refused for that reason and not one ever saw the lock.

    Two DIFFERENT candidates is where a race does damage. Unserialised, both
    mergers read the same HEAD, both predict a tree from it, and the second
    merges from a base that has already moved. With the lock the second waits,
    re-derives, and records the first's result as its own expected HEAD --
    which is the assertion below, and it is false for any racing interleaving.
    """
    repo, journal, first = build_fixture()
    git(repo, "checkout", "-q", "-b", "second", "main")
    (repo / "other.txt").write_text("other\n", encoding="utf-8")
    git(repo, "add", "other.txt")
    git(repo, "commit", "-m", "an independent candidate", "--no-gpg-sign")
    second = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")

    work = [("Pipeline Maintainer Agent", first), ("Game Agent", second)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda pair: run_tool(repo, journal, pair[0], pair[1]), work))

    detail = "\n".join(f"[exit {c}] {o.strip()[:200]}" for c, o in results)
    require(all(code == 0 for code, _ in results),
            f"both independent candidates should land, sequentially\n{detail}")
    require(open_starts(journal) == 0, "no unclosed START after two merges")

    starts = [l for l in journal_lines(journal) if "MAIN-WRITE START" in l]
    ends = [l for l in journal_lines(journal) if "MAIN-WRITE END" in l]
    require(len(starts) == 2 and len(ends) == 2,
            f"expected two complete records, got {len(starts)}/{len(ends)}")

    expected = [re.search(r"expected HEAD ([0-9a-f]+)", l).group(1)
                for l in starts]
    require(expected[0] != expected[1],
            "both mergers recorded the SAME expected HEAD, so neither waited "
            "for the other: they raced, and the second merged from a base that "
            "had already moved")

    produced = re.search(r"new HEAD ([0-9a-f]+)", ends[0]).group(1)
    require(produced.startswith(expected[1]),
            "the second merger must re-derive HEAD after the first finishes; "
            f"it expected {expected[1]} and the first produced {produced[:12]}")


def test_no_journal_line_is_lost_or_interleaved() -> None:
    """Atomic appends, not read-modify-write.

    The predecessor read the whole journal, concatenated a line and wrote it
    back; two writers doing that lose whichever line was read before the other
    wrote. Every line here must be complete and self-contained.
    """
    repo, journal, candidate = build_fixture()
    roles = [f"{name} Agent" for name in ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda role: run_tool(repo, journal, role, candidate),
                      roles))
    lines = journal_lines(journal)
    require(bool(lines), "the contested run must have written something")
    for line in lines:
        require(line.startswith("- 20"),
                f"a truncated or interleaved line survived: {line!r}")
        require("MAIN-WRITE" in line or "MERGE REFUSED" in line,
                f"unrecognised journal line: {line!r}")
    require(sum("MAIN-WRITE START" in l for l in lines) == 1,
            f"exactly one START may exist across six contenders\n{lines}")


def test_a_role_the_journal_cannot_be_parsed_for_is_refused() -> None:
    repo, journal, candidate = build_fixture()
    code, output = run_tool(repo, journal, "pipeline", candidate)
    require(code != 0, "a role outside the parseable shape must be refused")
    require("Agent, Steward or Orchestrator" in output,
            f"the refusal must say what shape is required\n{output}")
    require(not journal_lines(journal),
            "a refused role must not write to the journal at all")


def test_a_stale_lock_is_broken_rather_than_inherited() -> None:
    """A crashed merger must not block main forever - but say so when breaking."""
    repo, journal, candidate = build_fixture()
    lock = journal.with_suffix(journal.suffix + ".merge-lock")
    lock.write_text("Ghost Agent|99999|long ago\n", encoding="utf-8")
    old = 1
    os.utime(lock, (old, old))
    code, output = run_tool(repo, journal, "Pipeline Maintainer Agent",
                            candidate, timeout=1.0)
    require(code == 0, f"a stale lock must not block a merge\n{output}")
    require("stale lock" in output,
            f"breaking a lock must be recorded, not silent\n{output}")


def main() -> int:
    test_one_merger_succeeds_alone()
    test_two_mergers_at_once_produce_exactly_one_merge()
    test_eight_mergers_at_once_still_produce_exactly_one()
    test_two_different_candidates_serialise_rather_than_racing()
    test_no_journal_line_is_lost_or_interleaved()
    test_a_role_the_journal_cannot_be_parsed_for_is_refused()
    test_a_stale_lock_is_broken_rather_than_inherited()
    print("test_guarded_merge: PASS (7 tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
