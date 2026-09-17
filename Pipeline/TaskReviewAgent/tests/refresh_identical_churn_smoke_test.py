#!/usr/bin/env python3
"""Regression tests for problem P18: refresh-identical stale-stat churn."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import refresh_identical_churn as ric  # noqa: E402
from Pipeline.TaskReviewAgent.refresh_identical_churn import (  # noqa: E402
    RefreshIdenticalChurnError,
    find_identical_churn,
    refresh_identical_churn,
)


GENERATED = "Generated/Wizard.anim"
REAL_EDIT = "Generated/WallTile.asset"


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.rstrip()


def status(root: Path) -> str:
    return git(root, "status", "--porcelain=v1", "--untracked-files=all")


def _make_phantom_churn_repo(root: Path) -> None:
    """Reproduce the exact stale-index-stat-size phantom described in P18."""

    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Refresh Identical Churn Test")
    git(root, "config", "user.email", "refresh-identical-churn@example.invalid")
    git(root, "config", "core.autocrlf", "true")
    (root / ".gitattributes").write_bytes(b"* text=auto\n")

    generated = root / GENERATED
    generated.parent.mkdir(parents=True)
    # Committed with LF content, as a generated Unity .anim/.asset YAML file
    # would be when written directly by a tool rather than by Git's checkout.
    generated.write_bytes(b"root:\n  value: one\n  extra: two\n")

    real_edit = root / REAL_EDIT
    real_edit.write_bytes(b"root:\n  value: one\n")

    git(root, "add", ".")
    git(root, "commit", "-m", "Create fixture")
    assert status(root) == ""

    # Re-checkout to force core.autocrlf=true to smudge CRLF onto disk and
    # cache that larger CRLF size in the index stat entry.
    generated.unlink()
    git(root, "checkout", "--", GENERATED)
    assert b"\r\n" in generated.read_bytes()

    # Unity (or any tool) rewrites the identical content as LF. The bytes are
    # unchanged relative to HEAD, but the on-disk size no longer matches the
    # index's cached CRLF size.
    generated.write_bytes(b"root:\n  value: one\n  extra: two\n")


def test_status_flags_content_identical_crlf_churn_as_modified() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        _make_phantom_churn_repo(root)

        raw_status = status(root)
        assert f" M {GENERATED}" in raw_status, raw_status

        # Proven content-identical: the worktree blob matches the index blob.
        index_oid = git(root, "rev-parse", f":{GENERATED}")
        worktree_oid = git(
            root, "hash-object", "--path", GENERATED, "--", GENERATED
        )
        assert index_oid == worktree_oid

        # git diff reports no textual difference either.
        assert git(root, "diff", "--", GENERATED) == ""


def test_dry_run_lists_it_and_changes_nothing() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        _make_phantom_churn_repo(root)

        index_path = root / ".git" / "index"
        before = index_path.read_bytes()

        findings = find_identical_churn(root)
        assert findings["refreshable"] == [GENERATED]
        assert findings["untracked_ignored"] == []

        report = refresh_identical_churn(root, apply=False)
        assert report["mode"] == "dry-run"
        assert report["refreshed"] == [GENERATED]

        after = index_path.read_bytes()
        assert before == after, "dry run must not touch .git/index"
        assert f" M {GENERATED}" in status(root)


def test_apply_makes_status_clean_and_index_oid_unchanged() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        _make_phantom_churn_repo(root)

        index_oid_before = git(root, "rev-parse", f":{GENERATED}")
        head_before = git(root, "rev-parse", "HEAD")

        report = refresh_identical_churn(root, apply=True)
        assert report["mode"] == "apply"
        assert report["refreshed"] == [GENERATED]

        assert git(root, "rev-parse", "HEAD") == head_before
        assert git(root, "rev-parse", f":{GENERATED}") == index_oid_before
        assert status(root) == ""


def test_real_edit_stays_modified_and_is_reported_as_content_differs() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        _make_phantom_churn_repo(root)

        real_edit = root / REAL_EDIT
        real_edit.write_bytes(b"root:\n  value: two\n")
        assert f" M {REAL_EDIT}" in status(root)

        findings = find_identical_churn(root)
        assert GENERATED in findings["refreshable"]
        assert REAL_EDIT not in findings["refreshable"]
        reasons = {entry["path"]: entry["reason"] for entry in findings["left_modified"]}
        assert reasons[REAL_EDIT] == "content differs"

        report = refresh_identical_churn(root, apply=True)
        assert REAL_EDIT not in report["refreshed"]
        assert f" M {REAL_EDIT}" in status(root)
        assert real_edit.read_bytes() == b"root:\n  value: two\n"

        staged = git(root, "diff", "--cached", "--name-only")
        assert REAL_EDIT not in staged.splitlines()


def test_staged_change_is_left_alone() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        _make_phantom_churn_repo(root)

        real_edit = root / REAL_EDIT
        real_edit.write_bytes(b"root:\n  value: staged\n")
        git(root, "add", "--", REAL_EDIT)
        raw_status = status(root)
        assert f"M  {REAL_EDIT}" in raw_status, raw_status

        findings = find_identical_churn(root)
        reasons = {entry["path"]: entry["reason"] for entry in findings["left_modified"]}
        assert reasons[REAL_EDIT] == "staged"
        assert REAL_EDIT not in findings["refreshable"]

        report = refresh_identical_churn(root, apply=True)
        assert REAL_EDIT not in report["refreshed"]
        assert f"M  {REAL_EDIT}" in status(root)


def test_unsafe_repository_raises_without_touching_anything() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        try:
            refresh_identical_churn(root, apply=True)
        except RefreshIdenticalChurnError:
            pass
        else:
            raise AssertionError("expected RefreshIdenticalChurnError for a non-repository path")


def test_every_git_subprocess_uses_create_no_window() -> None:
    import subprocess as subprocess_module

    calls = []
    real_run = subprocess_module.run

    def _spy_run(*args, **kwargs):
        calls.append(kwargs.get("creationflags"))
        return real_run(*args, **kwargs)

    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        _make_phantom_churn_repo(root)

        original_run = ric.subprocess.run
        ric.subprocess.run = _spy_run
        try:
            refresh_identical_churn(root, apply=True)
        finally:
            ric.subprocess.run = original_run

    assert calls, "expected at least one subprocess.run call"
    for creationflags in calls:
        assert creationflags == ric._CREATE_NO_WINDOW, calls


def main() -> int:
    tests = [
        test_status_flags_content_identical_crlf_churn_as_modified,
        test_dry_run_lists_it_and_changes_nothing,
        test_apply_makes_status_clean_and_index_oid_unchanged,
        test_real_edit_stays_modified_and_is_reported_as_content_differs,
        test_staged_change_is_left_alone,
        test_unsafe_repository_raises_without_touching_anything,
        test_every_git_subprocess_uses_create_no_window,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"refresh identical churn smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
