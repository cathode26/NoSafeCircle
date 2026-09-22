#!/usr/bin/env python
"""Merge a candidate into local main as one guarded, serialisable step.

Role-agnostic on purpose. Two roles merge into main now - the Game Agent owns
the Unity surface, the Pipeline Maintainer owns pipeline work - and a tool that
lives in one agent's private folder cannot be shared: you either hand-merge,
which is what reopened the HEAD window twice in one hour on 2026-09-22, or copy
it, which is how two versions drift.

WHAT THIS ADDS OVER A CHECK-THEN-MERGE SCRIPT

Re-deriving main and merging happen inside ONE process, so main cannot move in
the window between them. That much the Game Agent's version already did.

What it did not do is serialise two mergers. It read the journal for an open
MAIN-WRITE, and wrote its own START later; two processes can both pass that
check before either writes, and both then merge. It also journalled by
read-modify-write, so two writers can lose a line outright. Neither has bitten
because only one agent ran it.

So: an OS-level exclusive lock decides who proceeds, taken before any check
that the merge depends on and held until the journal is closed. The lock is a
file created with O_CREAT|O_EXCL, which is atomic on Windows and POSIX alike --
whoever creates it wins, and a loser refuses rather than waiting for a window
that has already closed. Journal writes are atomic appends, never
read-modify-write.

The MAIN-WRITE journal record is still written, because the lock serialises and
the journal is what anyone can read afterwards. They answer different questions.

    python -B guarded_merge.py --role "Pipeline Maintainer Agent" \\
        --candidate <ref> --authority "<why this may land>" \\
        --not-proven "<what it does not establish>"

It never pushes. Publication to origin is the Release Agent's, on Vincent's own
word, and nothing here changes that.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import os
import pathlib
import re
import subprocess
import sys
import time

DEFAULT_REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
DEFAULT_JOURNAL = pathlib.Path(
    r"C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control"
    r"\graph-lead-journal.md")
ROLE_PATTERN = re.compile(r"^[A-Za-z ]+(?:Agent|Steward|Orchestrator)$")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC")


def append(journal: pathlib.Path, text: str) -> None:
    """One atomic append. Never read-modify-write.

    The previous tool read the whole journal, concatenated a line and wrote it
    back. Two writers doing that lose whichever line was read before the other
    wrote. An O_APPEND write of a single short line cannot interleave that way.
    """
    line = f"- {stamp()} {text}\n".encode("utf-8")
    with open(journal, "ab") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


@contextlib.contextmanager
def exclusive(lock_path: pathlib.Path, role: str, timeout: float):
    """Whoever creates the lock file proceeds; everyone else refuses.

    O_EXCL makes the create-or-fail one operation, so there is no window in
    which two processes both believe they hold it. A stale lock older than
    `timeout` is broken rather than inherited, because a crashed merger must not
    block main forever -- and the breaking is recorded, because silently
    stealing a lock is how the guard stops meaning anything.
    """
    payload = f"{role}|{os.getpid()}|{stamp()}\n".encode("utf-8")
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(handle, payload)
            os.close(handle)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                held = lock_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if age > timeout:
                print(f"breaking a stale lock held {age:.0f}s by {held}",
                      file=sys.stderr)
                with contextlib.suppress(OSError):
                    lock_path.unlink()
                continue
            if time.monotonic() >= deadline:
                raise SystemExit(
                    f"REFUSED: another merge holds the lock ({held}). "
                    f"main untouched, nothing written.")
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock_path.unlink()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True,
                    help='the merging role, e.g. "Pipeline Maintainer Agent"')
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--authority", required=True,
                    help="why this may land; recorded in the journal")
    ap.add_argument("--not-proven", default="nothing recorded",
                    help="what this merge does NOT establish")
    ap.add_argument("--repo", type=pathlib.Path, default=DEFAULT_REPO)
    ap.add_argument("--journal", type=pathlib.Path, default=DEFAULT_JOURNAL)
    ap.add_argument("--lock-timeout", type=float, default=120.0)
    ap.add_argument("--validate", default="Pipeline/TaskGraph/taskcontrol.py")
    args = ap.parse_args(argv)

    if not ROLE_PATTERN.match(args.role):
        raise SystemExit(
            f"--role {args.role!r} is not a shape the journal can be parsed "
            "back for; it must end in Agent, Steward or Orchestrator. A role "
            "the guard cannot see writes a START nobody can match.")

    repo, journal = args.repo, args.journal

    def git(*a: str, check: bool = False) -> subprocess.CompletedProcess:
        result = subprocess.run(["git", "-C", str(repo), *a],
                                capture_output=True, text=True,
                                creationflags=NO_WINDOW)
        if check and result.returncode != 0:
            raise SystemExit(
                f"git {' '.join(a)} failed: {result.stdout}{result.stderr}")
        return result

    lock = journal.with_suffix(journal.suffix + ".merge-lock")
    with exclusive(lock, args.role, args.lock_timeout):
        sha = git("rev-parse", "--verify", f"{args.candidate}^{{commit}}",
                  check=True).stdout.strip()
        head = git("rev-parse", "HEAD", check=True).stdout.strip()

        problems: list[str] = []
        if git("status", "--porcelain").stdout.strip():
            problems.append("canonical worktree is dirty")
        if git("merge-base", "--is-ancestor", sha, head).returncode == 0:
            problems.append(f"{sha[:9]} is already an ancestor of main")
        identities = set(git("log", "--format=%ae%n%ce",
                             f"{head}..{sha}").stdout.split())
        leaked = sorted(i for i in identities if not i.endswith(".invalid"))
        if leaked:
            problems.append(f"non-.invalid identity: {', '.join(leaked)}")
        predicted = git("merge-tree", "--write-tree", head, sha)
        if predicted.returncode != 0 or "CONFLICT" in predicted.stdout.upper():
            problems.append("trial merge against live main is not clean")
        predicted_tree = (predicted.stdout.splitlines()[0].strip()
                          if predicted.stdout else "")

        if problems:
            append(journal, f"MERGE REFUSED {args.role}: {args.candidate} "
                            f"({sha[:9]}) not merged, main untouched at "
                            f"{head[:9]}; {'; '.join(problems)}")
            print("REFUSED, main untouched:")
            for problem in problems:
                print(f"  - {problem}")
            return 1

        fast_forward = git("merge-base", "--is-ancestor", head,
                           sha).returncode == 0
        files = git("diff", "--name-only", f"{head}..{sha}").stdout.split()
        commits = len(git("log", "--format=%H",
                          f"{head}..{sha}").stdout.split())

        append(journal,
               f"MAIN-WRITE START {args.role}: merge {args.candidate} ({sha}) "
               f"into main, expected HEAD {head[:9]}. {args.authority} "
               f"Measured in-process under an exclusive lock: tree clean, "
               f"every identity .invalid, trial merge clean predicting tree "
               f"{predicted_tree[:12]}, {commits} commit(s), {len(files)} "
               f"file(s), {'fast-forward' if fast_forward else 'merge commit'}.")

        try:
            if git("rev-parse", "HEAD").stdout.strip() != head:
                append(journal, f"MAIN-WRITE END {args.role}: ABORTED, nothing "
                                f"written, HEAD unchanged. main moved between "
                                f"the checks and the merge.")
                print("REFUSED: main moved mid-check; main untouched")
                return 1

            if fast_forward:
                merge_args = ["merge", "--ff-only", sha]
            else:
                merge_args = [
                    "-c", f"user.name=No Safe Circle {args.role}",
                    "-c", "user.email=" + args.role.lower().replace(" ", "-")
                          + "@nosafecircle.invalid",
                    "merge", "--no-ff", sha, "-m",
                    f"Merge {args.candidate}"]
            merged = git(*merge_args)
            if merged.returncode != 0:
                detail = (merged.stdout + merged.stderr).strip().replace(
                    "\n", " ")[:300]
                append(journal, f"MAIN-WRITE END {args.role}: ABORTED, merge "
                                f"failed, main unchanged at {head[:9]}: {detail}")
                print("MERGE FAILED, main untouched:\n",
                      merged.stdout, merged.stderr)
                return 1

            new_head = git("rev-parse", "HEAD", check=True).stdout.strip()
            new_tree = git("rev-parse", "HEAD^{tree}",
                           check=True).stdout.strip()
            dirty = git("status", "--porcelain").stdout.strip()
            validate = subprocess.run(
                [sys.executable, "-B", args.validate, "validate"],
                cwd=str(repo), capture_output=True, text=True,
                creationflags=NO_WINDOW)
            ahead = git("rev-list", "--count",
                        "origin/main..main").stdout.strip() or "?"
            drift = ("" if new_tree == predicted_tree
                     else f" (WARNING: tree differs from predicted "
                          f"{predicted_tree})")

            append(journal,
                   f"MAIN-WRITE END {args.role}: new HEAD {new_head}, tree "
                   f"{new_tree}{drift}; {commits} commit(s), {len(files)} "
                   f"file(s); validate "
                   f"{'PASS' if validate.returncode == 0 else 'FAIL'}; "
                   f"worktree {'clean' if not dirty else dirty}. "
                   f"WHAT THIS MERGE DOES NOT PROVE: {args.not_proven}. "
                   f"NOT pushed; {ahead} ahead of origin.")

            print(f"merged {sha[:9]}")
            print(f"  new HEAD : {new_head}")
            print(f"  tree     : {new_tree}  "
                  f"{'MATCH' if new_tree == predicted_tree else 'MISMATCH'}")
            print(f"  validate : "
                  f"{'PASS' if validate.returncode == 0 else 'FAIL'}")
            print(f"  worktree : {'clean' if not dirty else dirty}")
            print(f"  ahead of origin: {ahead} (not pushed)")
            return 0 if validate.returncode == 0 and not dirty else 1
        except BaseException as error:              # noqa: BLE001
            # An unclosed START is worse than a failed merge: the next merger
            # cannot tell a crash from a write in progress.
            append(journal, f"MAIN-WRITE END {args.role}: ABORTED on an "
                            f"unexpected error, main may be mid-merge, inspect "
                            f"before retrying: {type(error).__name__}: "
                            f"{str(error)[:200]}")
            raise


if __name__ == "__main__":
    raise SystemExit(main())
