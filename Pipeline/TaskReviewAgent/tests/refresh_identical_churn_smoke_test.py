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
PATHSPEC_MAGIC_PATH = "data[1].txt"
PATHSPEC_SIBLING_PATH = "data1.txt"


def git(root: Path, *args: str, literal_pathspecs: bool = False) -> str:
    env = None
    if literal_pathspecs:
        import os as _os

        env = dict(_os.environ)
        env["GIT_LITERAL_PATHSPECS"] = "1"
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
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


def _make_pathspec_magic_repo(root: Path) -> None:
    """A qualifying path whose name is Git pathspec glob magic (``data[1].txt``)
    alongside a sibling (``data1.txt``) that the glob could accidentally match,
    carrying a real, unstaged edit that must never be touched.
    """

    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Refresh Identical Churn Test")
    git(root, "config", "user.email", "refresh-identical-churn@example.invalid")
    git(root, "config", "core.autocrlf", "true")
    (root / ".gitattributes").write_bytes(b"* text=auto\n")

    magic = root / PATHSPEC_MAGIC_PATH
    magic.write_bytes(b"root:\n  value: one\n  extra: two\n")

    sibling = root / PATHSPEC_SIBLING_PATH
    sibling.write_bytes(b"sibling original\n")

    git(root, "add", ".")
    git(root, "commit", "-m", "Create pathspec fixture")
    assert status(root) == ""

    # Force the same stale-CRLF-size phantom onto the pathspec-magic path.
    # Use literal pathspecs for this setup step so it cannot itself stage or
    # revert the sibling by accident (see the wired probe in the fix report).
    magic.unlink()
    git(root, "checkout", "--", PATHSPEC_MAGIC_PATH, literal_pathspecs=True)
    assert b"\r\n" in magic.read_bytes()
    magic.write_bytes(b"root:\n  value: one\n  extra: two\n")

    # A real, unstaged, unrelated edit to the sibling literal path -- this
    # must never be staged just because "data[1].txt" also matches it as a
    # glob pathspec.
    sibling.write_bytes(b"sibling really edited\n")


def test_pathspec_magic_path_does_not_stage_sibling_real_edit() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        _make_pathspec_magic_repo(root)

        raw_status = status(root)
        assert f" M {PATHSPEC_MAGIC_PATH}" in raw_status, raw_status
        assert f" M {PATHSPEC_SIBLING_PATH}" in raw_status, raw_status

        findings = find_identical_churn(root)
        assert findings["refreshable"] == [PATHSPEC_MAGIC_PATH]
        reasons = {entry["path"]: entry["reason"] for entry in findings["left_modified"]}
        assert reasons[PATHSPEC_SIBLING_PATH] == "content differs"

        sibling_index_oid_before = git(
            root, "ls-files", "-s", "--", PATHSPEC_SIBLING_PATH, literal_pathspecs=True
        ).split()[1]

        report = refresh_identical_churn(root, apply=True)
        assert report["refreshed"] == [PATHSPEC_MAGIC_PATH]

        # The magic path was refreshed and is clean.
        assert f" M {PATHSPEC_MAGIC_PATH}" not in status(root)

        # The sibling's real edit is untouched: still unstaged, still modified,
        # worktree bytes unchanged, and its index entry (oid) unchanged -- it
        # must never have been staged by the glob match.
        raw_status_after = status(root)
        assert f" M {PATHSPEC_SIBLING_PATH}" in raw_status_after, raw_status_after
        assert (root / PATHSPEC_SIBLING_PATH).read_bytes() == b"sibling really edited\n"
        sibling_index_oid_after = git(
            root, "ls-files", "-s", "--", PATHSPEC_SIBLING_PATH, literal_pathspecs=True
        ).split()[1]
        assert sibling_index_oid_after == sibling_index_oid_before
        staged = git(root, "diff", "--cached", "--name-only")
        assert PATHSPEC_SIBLING_PATH not in staged.splitlines(), staged


def test_race_change_before_add_is_dropped_and_index_untouched() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        _make_phantom_churn_repo(root)

        index_path = root / ".git" / "index"
        before_bytes = index_path.read_bytes()

        original_hash_object = ric._hash_object
        call_count = {"n": 0}

        def _spy_hash_object(r: Path, path: str) -> str:
            call_count["n"] += 1
            result = original_hash_object(r, path)
            if path == GENERATED and call_count["n"] == 1:
                # Simulate the file changing on disk right after the initial
                # scan hashed it, in the window before the pre-add re-check.
                (r / path).write_bytes(b"root:\n  value: raced\n  extra: value\n")
            return result

        ric._hash_object = _spy_hash_object
        try:
            report = refresh_identical_churn(root, apply=True)
        finally:
            ric._hash_object = original_hash_object

        assert GENERATED not in report["refreshed"]
        reasons = {entry["path"]: entry["reason"] for entry in report["left_modified"]}
        assert reasons.get(GENERATED) == "changed during refresh", reasons

        after_bytes = index_path.read_bytes()
        assert after_bytes == before_bytes, "index must be untouched when the only candidate races away"

        staged = git(root, "diff", "--cached", "--name-only")
        assert staged == "", f"nothing should be staged when the raced path is dropped: {staged!r}"


def test_forced_post_verify_failure_restores_index_byte_identical() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        _make_phantom_churn_repo(root)

        index_path = root / ".git" / "index"
        before_run_bytes = index_path.read_bytes()

        original_git_text = ric._git_text
        head_rev_parse_calls = {"n": 0}

        def _spy_git_text(r: Path, *args: str, **kwargs):
            if args[:2] == ("rev-parse", "HEAD"):
                head_rev_parse_calls["n"] += 1
                if head_rev_parse_calls["n"] == 2:
                    # Force the post-add "HEAD changed" verification to fail,
                    # without actually touching HEAD.
                    return "0" * 40
            return original_git_text(r, *args, **kwargs)

        ric._git_text = _spy_git_text
        try:
            try:
                refresh_identical_churn(root, apply=True)
            except RefreshIdenticalChurnError as exc:
                assert "restored" in str(exc), str(exc)
            else:
                raise AssertionError(
                    "expected RefreshIdenticalChurnError from the forced post-verify failure"
                )
        finally:
            ric._git_text = original_git_text

        after_run_bytes = index_path.read_bytes()
        assert after_run_bytes == before_run_bytes, (
            "a forced post-verify failure must restore .git/index byte-identical"
        )
        assert f" M {GENERATED}" in status(root), "the rolled-back path must still show as modified"
        staged = git(root, "diff", "--cached", "--name-only")
        assert staged == "", f"nothing should remain staged after a restored rollback: {staged!r}"


def test_hash_object_failure_is_reported_as_error_not_content_differs() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        git(root, "init", "--initial-branch=main")
        git(root, "config", "user.name", "Refresh Identical Churn Test")
        git(root, "config", "user.email", "refresh-identical-churn@example.invalid")

        broken = root / "broken.txt"
        broken.write_bytes(b"hello\n")
        git(root, "add", "broken.txt")
        git(root, "commit", "-m", "Create broken-filter fixture")

        (root / ".gitattributes").write_bytes(b"broken.txt filter=missingfilter\n")
        git(root, "config", "filter.missingfilter.clean", "this-command-does-not-exist-xyz")
        git(root, "config", "filter.missingfilter.required", "true")
        broken.write_bytes(b"hello world\n")
        assert f" M broken.txt" in status(root)

        try:
            find_identical_churn(root)
        except RefreshIdenticalChurnError as exc:
            assert "hash-object" in str(exc), str(exc)
        else:
            raise AssertionError(
                "expected a hash-object filter failure to raise, not be reported as content differs"
            )


def test_intent_to_add_path_is_labeled_intent_to_add() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-refresh-identical-churn-") as temporary:
        root = Path(temporary)
        git(root, "init", "--initial-branch=main")
        git(root, "config", "user.name", "Refresh Identical Churn Test")
        git(root, "config", "user.email", "refresh-identical-churn@example.invalid")

        new_file = root / "new_intent.txt"
        new_file.write_bytes(b"brand new\n")
        git(root, "add", "-N", "--", "new_intent.txt")
        assert " A new_intent.txt" in status(root)

        findings = find_identical_churn(root)
        assert "new_intent.txt" not in findings["refreshable"]
        reasons = {entry["path"]: entry["reason"] for entry in findings["left_modified"]}
        assert reasons["new_intent.txt"] == "intent-to-add", reasons


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
        test_pathspec_magic_path_does_not_stage_sibling_real_edit,
        test_race_change_before_add_is_dropped_and_index_untouched,
        test_forced_post_verify_failure_restores_index_byte_identical,
        test_hash_object_failure_is_reported_as_error_not_content_differs,
        test_intent_to_add_path_is_labeled_intent_to_add,
        test_every_git_subprocess_uses_create_no_window,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"refresh identical churn smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
