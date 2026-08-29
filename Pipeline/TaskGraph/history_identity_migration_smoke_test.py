#!/usr/bin/env python3
"""Deterministic tests for committed repository-history identity translation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKGRAPH = ROOT / "Pipeline" / "TaskGraph"
if str(TASKGRAPH) not in sys.path:
    sys.path.insert(0, str(TASKGRAPH))

from conformance_records import ConformanceRecordError  # noqa: E402
from history_aware_repository import HistoryAwareGitRepository  # noqa: E402


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def run(
    root: Path,
    *args: str,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> str:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(
            f"git {' '.join(args)} failed ({result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout.strip()


def commit(root: Path, message: str) -> str:
    run(root, "add", "-A")
    run(root, "commit", "-m", message)
    return run(root, "rev-parse", "HEAD")


def write_manifest(
    root: Path,
    *,
    old_commit: str,
    new_commit: str,
    tree: str,
    recorded_tree: str | None = None,
) -> Path:
    path = (
        root
        / "Pipeline"
        / "TaskGraph"
        / "migrations"
        / "repository-history-identity-synthetic.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.0",
        "migration_type": "repository_history_identity",
        "migration_id": "synthetic",
        "reason": "git_identity_sanitization",
        "approved_by": "synthetic-test",
        "approved_at": "2026-08-29T00:00:00Z",
        "source_main": old_commit,
        "source_main_tree": tree,
        "target_main": new_commit,
        "target_main_tree": tree,
        "rewrite_report_sha256": "a" * 64,
        "commit_map": [
            {
                "old_commit": old_commit,
                "new_commit": new_commit,
                "tree": recorded_tree or tree,
            }
        ],
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_fixture(root: Path) -> tuple[str, str, str, str]:
    run(root, "init", "-b", "main")
    run(root, "config", "user.name", "History Migration Test")
    run(root, "config", "user.email", "history-test@example.invalid")

    (root / "asset.txt").write_text("tree-preserved payload\n", encoding="utf-8")
    base = commit(root, "base")

    (root / "state.txt").write_text("validated state\n", encoding="utf-8")
    old = commit(root, "validated historical state")
    tree = run(root, "rev-parse", f"{old}^{{tree}}")

    new = run(
        root,
        "commit-tree",
        tree,
        "-p",
        base,
        "-m",
        "validated historical state",
        env={
            "GIT_AUTHOR_NAME": "Sanitized Automation",
            "GIT_AUTHOR_EMAIL": "sanitized@example.invalid",
            "GIT_COMMITTER_NAME": "Sanitized Automation",
            "GIT_COMMITTER_EMAIL": "sanitized@example.invalid",
        },
    )
    require(new != old, "synthetic rewrite did not change commit identity")
    require(
        run(root, "rev-parse", f"{new}^{{tree}}") == tree,
        "synthetic rewritten commit changed the tree",
    )

    run(root, "checkout", "--detach", new)
    run(root, "branch", "-f", "main", new)
    run(root, "checkout", "main")
    write_manifest(root, old_commit=old, new_commit=new, tree=tree)
    manifest_head = commit(root, "record synthetic history migration")
    require(not run(root, "status", "--porcelain"), "fixture is dirty")
    return old, new, tree, manifest_head


def test_translation_works_without_old_object_in_fresh_clone() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        source = temp / "source"
        clone = temp / "clone"
        source.mkdir()
        old, new, tree, _ = build_fixture(source)

        result = subprocess.run(
            ["git", "clone", "--no-local", str(source), str(clone)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        require(result.returncode == 0, f"fresh clone failed: {result.stderr}")
        old_available = subprocess.run(
            ["git", "cat-file", "-e", f"{old}^{{commit}}"],
            cwd=clone,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 0
        require(not old_available, "fresh rewritten clone unexpectedly retained old commit object")

        repo = HistoryAwareGitRepository(clone)
        head = repo.head()
        require(repo.resolve_commit(old) == new, "old commit did not translate")
        require(repo.tree(old) == tree, "translated tree does not match historical tree")
        require(
            repo.read(old, "state.txt") == b"validated state\n",
            "translated historical file read changed bytes",
        )
        require(repo.is_ancestor(old, head), "translated old commit is not an ancestor of HEAD")
        translation = repo.history_identity.translation_for(old)
        require(translation is not None and translation.tree == tree, "translation authority missing")


def test_false_tree_mapping_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "repo"
        root.mkdir()
        old, new, tree, _ = build_fixture(root)
        write_manifest(
            root,
            old_commit=old,
            new_commit=new,
            tree=tree,
            recorded_tree="f" * 40,
        )
        commit(root, "tamper migration tree proof")
        try:
            HistoryAwareGitRepository(root)
        except ConformanceRecordError as exc:
            require(
                "translated commit tree differs" in str(exc),
                f"unexpected fail-closed reason: {exc}",
            )
        else:
            raise AssertionError("false history migration tree proof was accepted")


def main() -> int:
    tests = (
        test_translation_works_without_old_object_in_fresh_clone,
        test_false_tree_mapping_fails_closed,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"History identity TaskGraph migration tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
