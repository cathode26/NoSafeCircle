"""Refresh Git's stale index stat cache for content-identical worktree churn.

Problem P18: Unity checks out a tracked text asset under ``core.autocrlf=true``
(CRLF on disk, larger stat size cached in the index) and then rewrites the same
file with byte-identical LF content. Git's ``ce_modified`` fast path compares the
cached stat SIZE first; a size mismatch alone is treated as ``DATA_CHANGED`` and
reported as a worktree modification without re-hashing the file. The worktree
blob is provably identical to HEAD, so the path is safe to ``git add`` purely to
refresh its cached stat data -- the object id, and therefore the tree, never
changes.

This is a different policy from :mod:`Pipeline.TaskReviewAgent.safe_unity_churn`,
which restores a small, named set of ProjectSettings/scene paths from an exact
source commit. Here there is no curated path list and no restore-from-source
step: any tracked, unstaged, non-symlink regular file whose worktree bytes hash
to its existing index blob qualifies, and the only mutation is ``git add`` on
the exact qualifying paths (a stat-cache refresh, not a content change). Because
the precondition proof (parse ``status``/``ls-files``, compare hashes) and the
action (stage, then verify) are unrelated to the ProjectSettings restore policy,
this lives in its own module rather than being folded into that one.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

_REGULAR_FILE_MODES = frozenset({"100644", "100755"})


class RefreshIdenticalChurnError(RuntimeError):
    """Raised when refresh-identical cannot prove or complete its precondition."""


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ("git", "--no-optional-locks", "-C", str(root), *args),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATE_NO_WINDOW,
        )
    except OSError as exc:
        raise RefreshIdenticalChurnError("Git could not be invoked") from exc


def _git_bytes(root: Path, *args: str) -> bytes:
    result = _run_git(root, *args)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RefreshIdenticalChurnError(
            f"Git command failed ({result.returncode}): {' '.join(args)}"
            + (f": {detail}" if detail else "")
        )
    return result.stdout


def _git_text(root: Path, *args: str) -> str:
    return _git_bytes(root, *args).decode("utf-8", errors="strict").strip()


def _parse_porcelain_v1_z(raw: bytes) -> list[tuple[str, str]]:
    """Parse ``git status --porcelain=v1 -z`` records into ``(status, path)``."""

    parts = iter(raw.split(b"\0"))
    entries: list[tuple[str, str]] = []
    for record in parts:
        if not record:
            continue
        status = record[:2].decode("ascii")
        path = record[3:].decode("utf-8", "surrogateescape")
        if "R" in status or "C" in status:
            next(parts, b"")  # skip the original path of a rename/copy
        entries.append((status, path))
    return entries


def _parse_ls_files_s_z(raw: bytes) -> dict[str, tuple[str, str]]:
    """Parse ``git ls-files -s -z`` into ``path -> (mode, index_oid)``."""

    index: dict[str, tuple[str, str]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, _, path_bytes = record.partition(b"\t")
        mode_bytes, oid_bytes, _stage = meta.split(b" ")
        path = path_bytes.decode("utf-8", "surrogateescape")
        index[path] = (mode_bytes.decode("ascii"), oid_bytes.decode("ascii"))
    return index


def _hash_object(root: Path, path: str) -> str | None:
    result = _run_git(root, "hash-object", "--path", path, "--", path)
    if result.returncode != 0:
        return None
    return result.stdout.decode("ascii", errors="replace").strip()


def find_identical_churn(repository: Path | str) -> dict[str, object]:
    """Classify every status entry without mutating the repository."""

    root = Path(repository).resolve()
    status_entries = _parse_porcelain_v1_z(
        _git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    )
    index = _parse_ls_files_s_z(_git_bytes(root, "ls-files", "-s", "-z"))

    refreshable: list[str] = []
    left_modified: list[dict[str, str]] = []
    untracked_ignored: list[str] = []

    for status, path in status_entries:
        if status == "??":
            untracked_ignored.append(path)
            continue
        if status[0] != " ":
            left_modified.append({"path": path, "reason": "staged"})
            continue
        if status[1] != "M":
            # Deletions, type changes, etc. are not identical-content churn.
            left_modified.append({"path": path, "reason": "content differs"})
            continue

        mode, index_oid = index.get(path, (None, None))
        full = root / path
        if mode not in _REGULAR_FILE_MODES or full.is_symlink() or not full.is_file():
            left_modified.append({"path": path, "reason": "not a regular file"})
            continue

        worktree_oid = _hash_object(root, path)
        if worktree_oid is not None and worktree_oid == index_oid:
            refreshable.append(path)
        else:
            left_modified.append({"path": path, "reason": "content differs"})

    refreshable.sort(key=str.casefold)
    return {
        "refreshable": refreshable,
        "left_modified": left_modified,
        "untracked_ignored": untracked_ignored,
    }


def refresh_identical_churn(repository: Path | str, *, apply: bool) -> dict[str, object]:
    """Report, and optionally refresh, content-identical churn stat entries.

    Never touches a path unless it proves tracked, worktree-modified-only,
    a regular file, and worktree-hash-identical to the current index blob.
    Applying stages exactly the qualifying paths with ``git add`` and then
    re-verifies: index blobs for refreshed paths are unchanged, HEAD is
    unchanged, no other path's index entry moved, and none of the refreshed
    paths remain in ``git status``. Any verification failure raises without
    resetting anything, so the caller can inspect the repository as-is.
    """

    root = Path(repository).resolve()
    if not root.is_dir():
        raise RefreshIdenticalChurnError(f"repository does not exist: {root}")

    head_before = _git_text(root, "rev-parse", "HEAD")
    findings = find_identical_churn(root)
    refreshable = list(findings["refreshable"])

    refreshed: list[str] = []
    if apply and refreshable:
        pre_index = _parse_ls_files_s_z(_git_bytes(root, "ls-files", "-s", "-z"))
        _git_text(root, "add", "--", *refreshable)

        head_after = _git_text(root, "rev-parse", "HEAD")
        if head_after != head_before:
            raise RefreshIdenticalChurnError(
                f"HEAD changed during refresh-identical apply: {head_before!r} -> {head_after!r}"
            )

        post_index = _parse_ls_files_s_z(_git_bytes(root, "ls-files", "-s", "-z"))
        for path in refreshable:
            before = pre_index.get(path)
            after = post_index.get(path)
            if before is None or after is None or before[1] != after[1]:
                raise RefreshIdenticalChurnError(
                    f"index blob changed unexpectedly for refreshed path: {path}"
                )
        for path, before in pre_index.items():
            if path in refreshable:
                continue
            if post_index.get(path) != before:
                raise RefreshIdenticalChurnError(
                    f"non-qualifying path's index entry changed: {path}"
                )

        remaining_status = _parse_porcelain_v1_z(
            _git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        )
        remaining_paths = {path for _status, path in remaining_status}
        still_dirty = [path for path in refreshable if path in remaining_paths]
        if still_dirty:
            raise RefreshIdenticalChurnError(
                f"refreshed paths still reported modified: {still_dirty}"
            )
        refreshed = refreshable

    return {
        "mode": "apply" if apply else "dry-run",
        "repository": str(root),
        "refreshed": refreshed if apply else refreshable,
        "left_modified": findings["left_modified"],
        "untracked_ignored": findings["untracked_ignored"],
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        report = refresh_identical_churn(args.repo, apply=bool(args.apply))
    except RefreshIdenticalChurnError as exc:
        print(f"REFRESH IDENTICAL CHURN: ERROR: {exc}")
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
