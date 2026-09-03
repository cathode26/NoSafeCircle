#!/usr/bin/env python3
"""Focused local tests for production delivered-task revert safeguards."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.reset_rehearsal_task import CommandRunner  # noqa: E402
from Pipeline.TaskReviewAgent.reset_task import (  # noqa: E402
    TaskResetError,
    _require_task_paths_unchanged_since_merge,
    _transitive_active_dependents,
    _tree_entry,
)


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"command failed: {args}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_dependency_walk() -> None:
    contracts = {
        "NSC-100": {
            "contract_disposition": "active",
            "depends_on": [],
        },
        "NSC-101": {
            "contract_disposition": "active",
            "depends_on": ["NSC-100"],
        },
        "NSC-102": {
            "contract_disposition": "active",
            "depends_on": ["NSC-101"],
        },
        "NSC-103": {
            "contract_disposition": "cancelled",
            "depends_on": ["NSC-100"],
        },
    }
    expect(
        _transitive_active_dependents(contracts, "NSC-100")
        == ("NSC-101", "NSC-102"),
        "direct/transitive active dependents were not discovered exactly",
    )


def test_path_guard(repository: Path) -> None:
    repository.mkdir()
    run("git", "init", "-b", "main", cwd=repository)
    run("git", "config", "user.name", "Smoke Test", cwd=repository)
    run("git", "config", "user.email", "smoke@example.invalid", cwd=repository)
    (repository / "task.txt").write_text("base\n", encoding="utf-8")
    (repository / "later.txt").write_text("base\n", encoding="utf-8")
    run("git", "add", "task.txt", "later.txt", cwd=repository)
    run("git", "commit", "-m", "base", cwd=repository)
    run("git", "switch", "-c", "task", cwd=repository)
    (repository / "task.txt").write_text("delivered\n", encoding="utf-8")
    run("git", "commit", "-am", "delivery", cwd=repository)
    run("git", "switch", "main", cwd=repository)
    run("git", "merge", "--no-ff", "task", "-m", "merge delivery", cwd=repository)
    merge = run("git", "rev-parse", "HEAD", cwd=repository)
    (repository / "later.txt").write_text("later production work\n", encoding="utf-8")
    run("git", "commit", "-am", "later unrelated work", cwd=repository)
    head = run("git", "rev-parse", "HEAD", cwd=repository)
    runner = CommandRunner()
    _require_task_paths_unchanged_since_merge(
        runner,
        repository,
        merge_commit=merge,
        current_main=head,
        paths=("task.txt",),
    )
    expect(
        _tree_entry(runner, repository, merge, "later.txt")
        != _tree_entry(runner, repository, head, "later.txt"),
        "fixture did not create unrelated later production work",
    )
    (repository / "task.txt").write_text("later task edit\n", encoding="utf-8")
    run("git", "commit", "-am", "later task edit", cwd=repository)
    changed_head = run("git", "rev-parse", "HEAD", cwd=repository)
    try:
        _require_task_paths_unchanged_since_merge(
            runner,
            repository,
            merge_commit=merge,
            current_main=changed_head,
            paths=("task.txt",),
        )
    except TaskResetError as exc:
        expect("task.txt" in str(exc), "refusal did not identify the changed path")
    else:
        raise AssertionError("later task-owned changes were not refused")


def main() -> int:
    test_dependency_walk()
    preferred = Path(os.environ.get("NSC_TEST_TEMP_ROOT", ""))
    temporary_parent = preferred if str(preferred) else None
    if temporary_parent:
        temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="reset-production-task-",
        dir=str(temporary_parent) if temporary_parent else None,
    ) as directory:
        test_path_guard(Path(directory) / "repo")
    print("reset_task_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
