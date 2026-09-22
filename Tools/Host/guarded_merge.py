#!/usr/bin/env python
"""Merge a candidate into local main while holding the shared Git lock.

Every cooperating writer addresses the repository it actually mutates. Linked
worktrees share the ref; independent clones do not. The journal records the
operation but never grants admission. Recovery is explicit in main_write_lock.py;
no owner is displaced merely because its timestamp is old. This tool never pushes.
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
import main_write_lock as lock

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
        self.repo = pathlib.Path(repo).resolve()

    def __call__(self, *args: str, check: bool = False,
                 stdin: bytes | None = None) -> subprocess.CompletedProcess:
        result = lock.run_process(
            ["git", "-C", str(self.repo), *args], input=stdin,
            capture_output=True, creationflags=NO_WINDOW,
            mutation_capable="merge" in args)
        result.out = result.stdout.decode("utf-8", "replace").strip()
        result.err = result.stderr.decode("utf-8", "replace").strip()
        if check and result.returncode != 0:
            raise SystemExit(f"git {' '.join(args)} failed: {result.err}")
        return result


@contextlib.contextmanager
def held(git: Git, role: str, timeout: float, *, operation="merge candidate"):
    """Merger adapter for the same lock used by GER."""
    with lock.held(repo=git.repo, role=role, operation=operation, timeout=timeout) as owner:
        yield owner


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--authority", required=True)
    ap.add_argument("--not-proven", default="nothing recorded")
    ap.add_argument("--repo", type=pathlib.Path, required=True)
    ap.add_argument("--journal", type=pathlib.Path, required=True)
    ap.add_argument("--lock-timeout", type=float, default=120.0)
    ap.add_argument("--validate", default="Pipeline/TaskGraph/taskcontrol.py")
    args = ap.parse_args(argv)

    if not ROLE_PATTERN.match(args.role):
        raise SystemExit(
            f"--role {args.role!r} is not a shape the journal can be parsed "
            "back for; it must end in Agent, Steward or Orchestrator.")

    git = Git(args.repo)
    journal = args.journal

    with held(git, args.role, args.lock_timeout, operation=f"merge {args.candidate}") as owner:
        sha = git("rev-parse", "--verify", f"{args.candidate}^{{commit}}",
                  check=True).out
        head = git("rev-parse", "HEAD", check=True).out

        problems: list[str] = []
        if git("symbolic-ref", "--short", "HEAD", check=True).out != "main":
            problems.append("the target is not checked out on main")
        for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
            path = pathlib.Path(git("rev-parse", "--git-path", marker, check=True).out)
            if not path.is_absolute():
                path = git.repo / path
            if path.exists():
                problems.append(f"unfinished Git operation: {marker}")
        if git("status", "--porcelain", check=True).out:
            problems.append("canonical worktree is dirty")
        ancestor = git("merge-base", "--is-ancestor", sha, head)
        if ancestor.returncode not in (0, 1):
            raise SystemExit(f"cannot check ancestry: {ancestor.err}")
        if ancestor.returncode == 0:
            problems.append(f"{sha[:9]} is already an ancestor of main")
        identities = set(git("log", "--format=%ae%n%ce", f"{head}..{sha}", check=True)
                         .out.split())
        leaked = sorted(i for i in identities if not i.endswith(".invalid"))
        if leaked:
            problems.append(f"non-.invalid identity: {', '.join(leaked)}")
        predicted = git("merge-tree", "--write-tree", head, sha)
        if predicted.returncode not in (0, 1):
            raise SystemExit(f"cannot compute trial merge: {predicted.err}")
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

        ancestor = git("merge-base", "--is-ancestor", head, sha)
        if ancestor.returncode not in (0, 1):
            raise SystemExit(f"cannot check ancestry: {ancestor.err}")
        fast_forward = ancestor.returncode == 0
        files = git("diff", "--name-only", f"{head}..{sha}", check=True).out.split()
        commits = len(git("log", "--format=%H", f"{head}..{sha}", check=True).out.split())

        append(journal,
               f"MAIN-WRITE START {args.role}: merge {args.candidate} ({sha}) "
               f"into main, expected HEAD {head[:9]}; operation {owner.operation_id}. {args.authority} "
               f"Measured in-process while holding {LOCK_REF}: tree clean, "
               f"every identity .invalid, trial merge clean predicting tree "
               f"{predicted_tree[:12]}, {commits} commit(s), {len(files)} "
               f"file(s), {'fast-forward' if fast_forward else 'merge commit'}.")

        ended = False
        def finish(text):
            nonlocal ended
            if not ended:
                ended = True
                append(journal, text)

        try:
            if git("rev-parse", "HEAD", check=True).out != head:
                finish(f"MAIN-WRITE END {args.role}: ABORTED, nothing "
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
                actual = git("rev-parse", "HEAD", check=True).out
                state = git("status", "--porcelain", check=True).out
                finish(f"MAIN-WRITE END {args.role}: merge failed; actual "
                                f"HEAD {actual}; worktree {state or 'clean'}; "
                                f"operation {owner.operation_id}: {detail}")
                print("MERGE FAILED; inspect the recorded HEAD and worktree:\n", merged.out, merged.err)
                return 1

            new_head = git("rev-parse", "HEAD", check=True).out
            new_tree = git("rev-parse", "HEAD^{tree}", check=True).out
            validate = lock.run_process(
                [sys.executable, "-B", args.validate, "validate"],
                cwd=str(args.repo), capture_output=True, text=True,
                creationflags=NO_WINDOW)
            dirty = git("status", "--porcelain", check=True).out
            if git("rev-parse", "HEAD", check=True).out != new_head:
                raise SystemExit("validator changed HEAD; preserve and inspect the result")
            ahead_result = git("rev-list", "--count", "origin/main..main")
            ahead = (ahead_result.out if ahead_result.returncode == 0
                     else f"unavailable ({ahead_result.err})")
            drift = ("" if new_tree == predicted_tree
                     else f" (WARNING: tree differs from predicted "
                          f"{predicted_tree})")

            finish(f"MAIN-WRITE END {args.role}: new HEAD {new_head}, tree "
                   f"{new_tree}{drift}; operation {owner.operation_id}; {commits} commit(s), {len(files)} "
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
            return 0 if validate.returncode == 0 and not dirty and new_tree == predicted_tree else 1
        except lock.MutationChildUncertain:
            raise
        except BaseException as error:              # noqa: BLE001
            finish(f"MAIN-WRITE END {args.role}: ABORTED on an "
                            f"unexpected error; result may already be committed, inspect main before retrying; "
                            f"operation {owner.operation_id}: "
                            f"{type(error).__name__}: {str(error)[:200]}")
            raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except lock.MainWriteLockError as error:
        raise SystemExit(f"REFUSED: {error}") from error
