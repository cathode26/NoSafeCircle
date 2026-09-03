#!/usr/bin/env python3
"""Focused smoke tests for the guarded disposable-rehearsal reset utility."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.reset_rehearsal_task import (  # noqa: E402
    CommandRunner,
    RehearsalResetError,
    RESET_MERGE_TRAILER,
    RESET_TASK_TRAILER,
    _archive_state_files,
    _commit_parents,
    _commit_tree,
    _create_report,
    _repository_from_origin,
    _require_private_rehearsal_repository,
    _resolve_main_state,
    _state_paths,
)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action, fragment: str) -> None:
    try:
        action()
    except RehearsalResetError as exc:
        expect(fragment in str(exc), f"expected {fragment!r} in {exc!r}")
    else:
        raise AssertionError(f"expected RehearsalResetError containing {fragment!r}")


def run(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"command failed: {args}\n{completed.stdout}\n{completed.stderr}")
    return completed.stdout.strip()


def test_repository_guard() -> None:
    expect(
        _repository_from_origin(
            "https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal.git"
        )
        == "cathode26/NoSafeCircle-Homework-Rehearsal",
        "HTTPS origin was not normalized",
    )
    metadata = {
        "nameWithOwner": "cathode26/NoSafeCircle-Homework-Rehearsal",
        "visibility": "PRIVATE",
        "isArchived": False,
    }
    _require_private_rehearsal_repository(
        metadata, "cathode26/NoSafeCircle-Homework-Rehearsal"
    )
    expect_error(
        lambda: _require_private_rehearsal_repository(
            {**metadata, "nameWithOwner": "cathode26/NoSafeCircle"},
            "cathode26/NoSafeCircle",
        ),
        "production is refused",
    )
    expect_error(
        lambda: _require_private_rehearsal_repository(
            {**metadata, "visibility": "PUBLIC"},
            "cathode26/NoSafeCircle-Homework-Rehearsal",
        ),
        "PRIVATE",
    )


def test_exact_state_archive(root: Path) -> None:
    state_root = root / ".task-review-agent"
    state_root.mkdir(parents=True)
    for path in _state_paths(state_root, "NSC-901"):
        path.write_text(path.name, encoding="utf-8")
    unrelated = state_root / "NSC-042.json"
    unrelated.write_text("untouched", encoding="utf-8")
    outputs = state_root / "outputs" / "NSC-901" / "run-1" / "progress.log"
    outputs.parent.mkdir(parents=True)
    outputs.write_text("retained", encoding="utf-8")
    archive, names = _archive_state_files(
        state_root, "NSC-901", timestamp="20260903-120000Z"
    )
    expect(archive is not None and archive.is_dir(), "state archive was not created")
    expect(len(names) == 5, "all exact task state files were not archived")
    expect(unrelated.read_text(encoding="utf-8") == "untouched", "NSC-042 was changed")
    expect(outputs.read_text(encoding="utf-8") == "retained", "immutable output was changed")
    expect(
        not any(path.exists() for path in _state_paths(state_root, "NSC-901")),
        "active task state remains",
    )
    receipt = state_root / "reset-runs" / "NSC-901" / "run.json"
    _create_report(receipt, {"status": "applying"})
    expect_error(
        lambda: _create_report(receipt, {"status": "replacement"}),
        "already exists",
    )
    expect("applying" in receipt.read_text(encoding="utf-8"), "receipt was overwritten")


def test_additive_revert_identity(root: Path) -> None:
    repository = root / "repo"
    repository.mkdir()
    run("git", "init", "-b", "main", cwd=repository)
    run("git", "config", "user.name", "Smoke Test", cwd=repository)
    run("git", "config", "user.email", "smoke@example.invalid", cwd=repository)
    tracked = repository / "value.txt"
    tracked.write_text("base\n", encoding="utf-8")
    run("git", "add", "value.txt", cwd=repository)
    run("git", "commit", "-m", "base", cwd=repository)
    base = run("git", "rev-parse", "HEAD", cwd=repository)
    run("git", "switch", "-c", "nsc-901-smoke", cwd=repository)
    tracked.write_text("task\n", encoding="utf-8")
    run("git", "commit", "-am", "task", cwd=repository)
    run("git", "switch", "main", cwd=repository)
    run("git", "merge", "--no-ff", "nsc-901-smoke", "-m", "merge task", cwd=repository)
    merge = run("git", "rev-parse", "HEAD", cwd=repository)
    runner = CommandRunner()
    resolved, already = _resolve_main_state(runner, repository, "NSC-901", merge)
    expect(resolved == merge and not already, "merge should be recognized as unreverted")
    run("git", "revert", "-m", "1", "--no-commit", merge, cwd=repository)
    run(
        "git",
        "commit",
        "-m",
        "Revert NSC-901 for rehearsal rerun",
        "-m",
        f"{RESET_TASK_TRAILER}: NSC-901\n{RESET_MERGE_TRAILER}: {merge}",
        cwd=repository,
    )
    revert = run("git", "rev-parse", "HEAD", cwd=repository)
    resolved, already = _resolve_main_state(runner, repository, "NSC-901", revert)
    expect(resolved == merge and already, "additive reset commit was not recognized")
    expect(_commit_parents(runner, repository, revert) == (merge,), "history was rewritten")
    expect(
        _commit_tree(runner, repository, revert) == _commit_tree(runner, repository, base),
        "revert tree did not restore the exact pre-task tree",
    )


def main() -> int:
    test_repository_guard()
    preferred = Path(os.environ.get("NSC_TEST_TEMP_ROOT", ""))
    temporary_parent = preferred if str(preferred) else None
    if temporary_parent is not None:
        temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="reset-rehearsal-task-", dir=str(temporary_parent) if temporary_parent else None
    ) as directory:
        root = Path(directory)
        test_exact_state_archive(root / "state")
        test_additive_revert_identity(root)
    print("reset_rehearsal_task_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
