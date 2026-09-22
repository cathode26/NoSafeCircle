#!/usr/bin/env python
"""Merge a candidate into local main, serialised by a git ref compare-and-swap.

Two roles merge into main now - the Game Agent owns the Unity surface, the
Pipeline Maintainer owns pipeline work - so main is a two-writer resource and
needs a real lock rather than a convention.

WHY A REF AND NOT A LOCK FILE

`git update-ref <ref> <new> <old>` is a compare-and-swap that git enforces.
Measured, not assumed:

    update-ref refs/locks/main-write <A> ""   -> succeeds when absent
    update-ref refs/locks/main-write <B> ""   -> fatal: reference already exists
    update-ref -d refs/locks/main-write <B>   -> error: is at <A> but expected <B>
    update-ref -d refs/locks/main-write <A>   -> released

That matters more than the atomicity alone: the lock lives in the repository
both mergers write to, so it binds anything that uses it from any clone or
tool. An earlier version of this file used an O_CREAT|O_EXCL lock file, which
is equally atomic and protects only processes that opted into my convention -
a lock the other merger's tool cannot see is decorative.

The holder's identity IS the locked object: a blob naming role, pid and time,
so `git cat-file blob refs/locks/main-write` answers "who holds main" from any
clone. Breaking a stale lock is itself a compare-and-swap against that blob, so
two mergers cannot both break and both acquire.

WHAT THIS REPLACES

The predecessor, and `main_write.start()` itself, are check-then-act: they read
for an open MAIN-WRITE, decide, and append their own claim several steps later.
Two roles both read an empty window, both conclude it is clear, both proceed.
That is not the --role defect fixed on 2026-09-22 - that one made the filter
compare a role against itself - it is the ordering of the check against the
append, and it survived that fix untouched.

The MAIN-WRITE journal record is still written: the ref serialises, the journal
is what a human reads afterwards. They answer different questions.

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
LOCK_REF = "refs/locks/main-write"
ROLE_PATTERN = re.compile(r"^[A-Za-z ]+(?:Agent|Steward|Orchestrator)$")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC")


def append(journal: pathlib.Path, text: str) -> None:
    """One atomic append. Never read-modify-write.

    The predecessor read the journal, concatenated a line and wrote it back;
    two writers doing that lose whichever line was read before the other wrote.
    """
    line = f"- {stamp()} {text}\n".encode("utf-8")
    with open(journal, "ab") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


class Git:
    def __init__(self, repo: pathlib.Path) -> None:
        self.repo = repo

    def __call__(self, *args: str, check: bool = False,
                 stdin: bytes | None = None) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args], input=stdin,
            capture_output=True, creationflags=NO_WINDOW)
        result.out = result.stdout.decode("utf-8", "replace").strip()
        result.err = result.stderr.decode("utf-8", "replace").strip()
        if check and result.returncode != 0:
            raise SystemExit(f"git {' '.join(args)} failed: {result.err}")
        return result


@contextlib.contextmanager
def held(git: Git, role: str, timeout: float, stale_after: float):
    """Hold LOCK_REF for the duration, or refuse.

    Acquire and release and stale-break are all compare-and-swap, so no
    interleaving lets two holders believe they have it.
    """
    mine = git("hash-object", "-w", "--stdin",
               stdin=f"{role}|{os.getpid()}|{time.time():.0f}|{stamp()}\n"
                     .encode("utf-8"), check=True).out
    deadline = time.monotonic() + timeout
    while True:
        taken = git("update-ref", LOCK_REF, mine, "")
        if taken.returncode == 0:
            break

        current = git("rev-parse", "--verify", "-q", LOCK_REF)
        if current.returncode != 0:
            continue                     # released between our try and our look
        holder = git("cat-file", "blob", current.out).out
        age = None
        with contextlib.suppress(ValueError, IndexError):
            age = time.time() - float(holder.split("|")[2])

        if age is not None and age > stale_after:
            # Breaking is itself a CAS against the blob we just read, so two
            # mergers cannot both break and both acquire.
            print(f"breaking a stale main-write lock held {age:.0f}s by "
                  f"{holder.strip()}", file=sys.stderr)
            git("update-ref", "-d", LOCK_REF, current.out)
            continue

        if time.monotonic() >= deadline:
            raise SystemExit(
                f"REFUSED: {holder.strip() or 'another merger'} holds "
                f"{LOCK_REF}. main untouched, nothing written.")
        time.sleep(0.05)

    try:
        yield
    finally:
        released = git("update-ref", "-d", LOCK_REF, mine)
        if released.returncode != 0:
            print(f"WARNING: could not release {LOCK_REF}: {released.err}",
                  file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--authority", required=True)
    ap.add_argument("--not-proven", default="nothing recorded")
    ap.add_argument("--repo", type=pathlib.Path, default=DEFAULT_REPO)
    ap.add_argument("--journal", type=pathlib.Path, default=DEFAULT_JOURNAL)
    ap.add_argument("--lock-timeout", type=float, default=120.0)
    ap.add_argument("--stale-after", type=float, default=1800.0,
                    help="seconds before a held lock is treated as abandoned")
    ap.add_argument("--validate", default="Pipeline/TaskGraph/taskcontrol.py")
    args = ap.parse_args(argv)

    if not ROLE_PATTERN.match(args.role):
        raise SystemExit(
            f"--role {args.role!r} is not a shape the journal can be parsed "
            "back for; it must end in Agent, Steward or Orchestrator.")

    git = Git(args.repo)
    journal = args.journal

    with held(git, args.role, args.lock_timeout, args.stale_after):
        sha = git("rev-parse", "--verify", f"{args.candidate}^{{commit}}",
                  check=True).out
        head = git("rev-parse", "HEAD", check=True).out

        problems: list[str] = []
        if git("status", "--porcelain").out:
            problems.append("canonical worktree is dirty")
        if git("merge-base", "--is-ancestor", sha, head).returncode == 0:
            problems.append(f"{sha[:9]} is already an ancestor of main")
        identities = set(git("log", "--format=%ae%n%ce", f"{head}..{sha}")
                         .out.split())
        leaked = sorted(i for i in identities if not i.endswith(".invalid"))
        if leaked:
            problems.append(f"non-.invalid identity: {', '.join(leaked)}")
        predicted = git("merge-tree", "--write-tree", head, sha)
        if predicted.returncode != 0 or "CONFLICT" in predicted.out.upper():
            problems.append("trial merge against live main is not clean")
        predicted_tree = (predicted.out.splitlines()[0].strip()
                          if predicted.out else "")

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
        files = git("diff", "--name-only", f"{head}..{sha}").out.split()
        commits = len(git("log", "--format=%H", f"{head}..{sha}").out.split())

        append(journal,
               f"MAIN-WRITE START {args.role}: merge {args.candidate} ({sha}) "
               f"into main, expected HEAD {head[:9]}. {args.authority} "
               f"Measured in-process while holding {LOCK_REF}: tree clean, "
               f"every identity .invalid, trial merge clean predicting tree "
               f"{predicted_tree[:12]}, {commits} commit(s), {len(files)} "
               f"file(s), {'fast-forward' if fast_forward else 'merge commit'}.")

        try:
            if git("rev-parse", "HEAD").out != head:
                append(journal, f"MAIN-WRITE END {args.role}: ABORTED, nothing "
                                f"written. main moved between the checks and "
                                f"the merge.")
                print("REFUSED: main moved mid-check; main untouched")
                return 1

            if fast_forward:
                merge_args = ["merge", "--ff-only", sha]
            else:
                slug = args.role.lower().replace(" ", "-")
                merge_args = [
                    "-c", f"user.name=No Safe Circle {args.role}",
                    "-c", f"user.email={slug}@nosafecircle.invalid",
                    "merge", "--no-ff", sha, "-m", f"Merge {args.candidate}"]
            merged = git(*merge_args)
            if merged.returncode != 0:
                detail = f"{merged.out} {merged.err}".strip()[:300]
                append(journal, f"MAIN-WRITE END {args.role}: ABORTED, merge "
                                f"failed, main unchanged at {head[:9]}: {detail}")
                print("MERGE FAILED, main untouched:\n", merged.out, merged.err)
                return 1

            new_head = git("rev-parse", "HEAD", check=True).out
            new_tree = git("rev-parse", "HEAD^{tree}", check=True).out
            dirty = git("status", "--porcelain").out
            validate = subprocess.run(
                [sys.executable, "-B", args.validate, "validate"],
                cwd=str(args.repo), capture_output=True, text=True,
                creationflags=NO_WINDOW)
            ahead = git("rev-list", "--count", "origin/main..main").out or "?"
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
            append(journal, f"MAIN-WRITE END {args.role}: ABORTED on an "
                            f"unexpected error, inspect main before retrying: "
                            f"{type(error).__name__}: {str(error)[:200]}")
            raise


if __name__ == "__main__":
    raise SystemExit(main())
