#!/usr/bin/env python3
"""Focused smoke tests for the guarded disposable-rehearsal reset utility."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


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
    _require_task_paths_unchanged_since_merge,
    _require_private_rehearsal_repository,
    _resolve_main_state,
    _state_paths,
    _validate_additive_revert_commit,
)
from Pipeline.TaskReviewAgent import reset_rehearsal_task as reset_module  # noqa: E402


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


def test_additive_revert_preserves_later_unrelated_history(root: Path) -> None:
    repository = root / "repo-with-later-history"
    repository.mkdir()
    run("git", "init", "-b", "main", cwd=repository)
    run("git", "config", "user.name", "Smoke Test", cwd=repository)
    run("git", "config", "user.email", "smoke@example.invalid", cwd=repository)
    (repository / "task.txt").write_text("base\n", encoding="utf-8")
    (repository / "later.txt").write_text("base\n", encoding="utf-8")
    run("git", "add", "task.txt", "later.txt", cwd=repository)
    run("git", "commit", "-m", "base", cwd=repository)
    base = run("git", "rev-parse", "HEAD", cwd=repository)
    run("git", "switch", "-c", "nsc-907-smoke", cwd=repository)
    (repository / "task.txt").write_text("delivered\n", encoding="utf-8")
    run("git", "commit", "-am", "task", cwd=repository)
    run("git", "switch", "main", cwd=repository)
    run("git", "merge", "--no-ff", "nsc-907-smoke", "-m", "merge task", cwd=repository)
    merge = run("git", "rev-parse", "HEAD", cwd=repository)
    (repository / "later.txt").write_text("later pipeline fix\n", encoding="utf-8")
    run("git", "commit", "-am", "later unrelated fix", cwd=repository)
    previous_main = run("git", "rev-parse", "HEAD", cwd=repository)
    runner = CommandRunner()
    _require_task_paths_unchanged_since_merge(
        runner,
        repository,
        merge_commit=merge,
        current_main=previous_main,
        paths=("task.txt",),
    )

    run("git", "switch", "-c", "later-task-edit", cwd=repository)
    (repository / "task.txt").write_text("later dependent edit\n", encoding="utf-8")
    run("git", "commit", "-am", "later task-owned edit", cwd=repository)
    changed_main = run("git", "rev-parse", "HEAD", cwd=repository)
    expect_error(
        lambda: _require_task_paths_unchanged_since_merge(
            runner,
            repository,
            merge_commit=merge,
            current_main=changed_main,
            paths=("task.txt",),
        ),
        "task.txt",
    )
    run("git", "switch", "main", cwd=repository)

    run("git", "revert", "-m", "1", "--no-commit", merge, cwd=repository)
    run(
        "git",
        "commit",
        "-m",
        "revert old task merge",
        "-m",
        f"{RESET_TASK_TRAILER}: NSC-907\n{RESET_MERGE_TRAILER}: {merge}",
        cwd=repository,
    )
    revert = run("git", "rev-parse", "HEAD", cwd=repository)
    _validate_additive_revert_commit(
        runner,
        repository,
        previous_main=previous_main,
        revert_commit=revert,
        merge_parent=base,
        expected_paths=("task.txt",),
    )
    expect(
        (repository / "later.txt").read_text(encoding="utf-8")
        == "later pipeline fix\n",
        "later unrelated history was not preserved",
    )
    expect(
        (repository / "task.txt").read_text(encoding="utf-8") == "base\n",
        "task path was not restored to the merge parent",
    )
    resolved, already = _resolve_main_state(
        runner, repository, "NSC-907", revert
    )
    expect(
        resolved == merge and already,
        "reset atop unrelated later main was not recognized for idempotent resume",
    )

    # Infrastructure commits may legitimately land after the additive reset.
    # Recovery must still find the newest matching reset on first-parent main
    # history, while proving those later commits left every task-owned path
    # unchanged.
    (repository / "after-reset.txt").write_text(
        "later launcher fix\n", encoding="utf-8"
    )
    run("git", "add", "after-reset.txt", cwd=repository)
    run("git", "commit", "-m", "later infrastructure fix", cwd=repository)
    after_reset = run("git", "rev-parse", "HEAD", cwd=repository)
    resolved, already = _resolve_main_state(
        runner, repository, "NSC-907", after_reset
    )
    expect(
        resolved == merge and already,
        "a later unrelated commit hid the additive reset recovery point",
    )
    (repository / "task.txt").write_text(
        "changed after reset\n", encoding="utf-8"
    )
    run("git", "commit", "-am", "later task-owned edit after reset", cwd=repository)
    protected_after_reset = run("git", "rev-parse", "HEAD", cwd=repository)
    expect_error(
        lambda: _resolve_main_state(
            runner, repository, "NSC-907", protected_after_reset
        ),
        "later commits changed task-owned paths",
    )

    transient, transient_merge = _merged_reset_fixture(
        root, "repo-transient-task-touch", "NSC-906"
    )
    (transient / "task.txt").write_text(
        "temporary dependent edit\n", encoding="utf-8"
    )
    run("git", "commit", "-am", "temporarily edit task path", cwd=transient)
    (transient / "task.txt").write_text("delivered\n", encoding="utf-8")
    run("git", "commit", "-am", "restore task path bytes", cwd=transient)
    transient_head = run("git", "rev-parse", "HEAD", cwd=transient)
    expect_error(
        lambda: _require_task_paths_unchanged_since_merge(
            runner,
            transient,
            merge_commit=transient_merge,
            current_main=transient_head,
            paths=("task.txt",),
        ),
        "task.txt",
    )


def _merged_reset_fixture(root: Path, name: str, task_id: str) -> tuple[Path, str]:
    repository = root / name
    repository.mkdir()
    run("git", "init", "-b", "main", cwd=repository)
    run("git", "config", "user.name", "Smoke Test", cwd=repository)
    run("git", "config", "user.email", "smoke@example.invalid", cwd=repository)
    (repository / "task.txt").write_text("base\n", encoding="utf-8")
    (repository / "other.txt").write_text("base\n", encoding="utf-8")
    run("git", "add", "task.txt", "other.txt", cwd=repository)
    run("git", "commit", "-m", "base", cwd=repository)
    run("git", "switch", "-c", f"{task_id.lower()}-work", cwd=repository)
    (repository / "task.txt").write_text("delivered\n", encoding="utf-8")
    run("git", "commit", "-am", "task", cwd=repository)
    run("git", "switch", "main", cwd=repository)
    run("git", "merge", "--no-ff", f"{task_id.lower()}-work", "-m", "merge task", cwd=repository)
    return repository, run("git", "rev-parse", "HEAD", cwd=repository)


def test_later_main_reset_resume_refusals(root: Path) -> None:
    runner = CommandRunner()

    nonancestor, unrelated_merge = _merged_reset_fixture(
        root, "repo-nonancestor-source", "NSC-908"
    )
    source_base = run("git", "rev-list", "--max-parents=0", "HEAD", cwd=nonancestor)
    run("git", "switch", "--detach", source_base, cwd=nonancestor)
    run(
        "git",
        "commit",
        "--allow-empty",
        "-m",
        "unrelated reset marker",
        "-m",
        f"{RESET_TASK_TRAILER}: NSC-908\n{RESET_MERGE_TRAILER}: {unrelated_merge}",
        cwd=nonancestor,
    )
    marker = run("git", "rev-parse", "HEAD", cwd=nonancestor)
    expect_error(
        lambda: _resolve_main_state(runner, nonancestor, "NSC-908", marker),
        "not an ancestor",
    )

    touched, touched_merge = _merged_reset_fixture(
        root, "repo-intervening-touch", "NSC-909"
    )
    (touched / "task.txt").write_text("dependent later edit\n", encoding="utf-8")
    run("git", "commit", "-am", "later task path edit", cwd=touched)
    run(
        "git",
        "commit",
        "--allow-empty",
        "-m",
        "reset marker after dependent edit",
        "-m",
        f"{RESET_TASK_TRAILER}: NSC-909\n{RESET_MERGE_TRAILER}: {touched_merge}",
        cwd=touched,
    )
    touched_marker = run("git", "rev-parse", "HEAD", cwd=touched)
    expect_error(
        lambda: _resolve_main_state(runner, touched, "NSC-909", touched_marker),
        "task.txt",
    )

    extra, extra_merge = _merged_reset_fixture(root, "repo-extra-reset-path", "NSC-910")
    run("git", "revert", "-m", "1", "--no-commit", extra_merge, cwd=extra)
    (extra / "other.txt").write_text("reset touched unrelated path\n", encoding="utf-8")
    run("git", "add", "other.txt", cwd=extra)
    run(
        "git",
        "commit",
        "-m",
        "reset with extra path",
        "-m",
        f"{RESET_TASK_TRAILER}: NSC-910\n{RESET_MERGE_TRAILER}: {extra_merge}",
        cwd=extra,
    )
    extra_reset = run("git", "rev-parse", "HEAD", cwd=extra)
    expect_error(
        lambda: _resolve_main_state(runner, extra, "NSC-910", extra_reset),
        "changed an unexpected path",
    )


def test_not_delivered_resume_ignores_an_unrelated_later_merge(root: Path) -> None:
    repository, task_merge = _merged_reset_fixture(
        root, "repo-unrelated-later-merge", "NSC-905"
    )
    run("git", "revert", "-m", "1", "--no-commit", task_merge, cwd=repository)
    run(
        "git",
        "commit",
        "-m",
        "reset task before unrelated merge",
        "-m",
        f"{RESET_TASK_TRAILER}: NSC-905\n{RESET_MERGE_TRAILER}: {task_merge}",
        cwd=repository,
    )
    reset_commit = run("git", "rev-parse", "HEAD", cwd=repository)

    run("git", "switch", "-c", "unrelated-infrastructure", cwd=repository)
    (repository / "infrastructure.txt").write_text("fix\n", encoding="utf-8")
    run("git", "add", "infrastructure.txt", cwd=repository)
    run("git", "commit", "-m", "unrelated infrastructure", cwd=repository)
    run("git", "switch", "main", cwd=repository)
    run(
        "git",
        "merge",
        "--no-ff",
        "unrelated-infrastructure",
        "-m",
        "merge unrelated infrastructure",
        cwd=repository,
    )
    unrelated_merge = run("git", "rev-parse", "HEAD", cwd=repository)
    run(
        "git",
        "merge-base",
        "--is-ancestor",
        reset_commit,
        unrelated_merge,
        cwd=repository,
    )

    runner = CommandRunner()
    default_merge, default_reverted = _resolve_main_state(
        runner, repository, "NSC-905", unrelated_merge
    )
    expect(
        default_merge == unrelated_merge and not default_reverted,
        "ordinary conformant resolution no longer accepts a current merge candidate",
    )
    resolved, already_reverted = _resolve_main_state(
        runner,
        repository,
        "NSC-905",
        unrelated_merge,
        require_reset_marker=True,
    )
    expect(
        resolved == task_merge and already_reverted,
        "not-delivered recovery mistook a later unrelated merge for the task merge",
    )


def test_issue_transfer_retries_transient_archive_validation() -> None:
    class TransferRunner:
        def run(self, args, **_kwargs):
            argv = tuple(args)
            return SimpleNamespace(
                args=argv,
                returncode=0,
                stdout=("https://example.invalid/transferred\n" if "transfer" in argv else ""),
                stderr="",
            )

    operation = object.__new__(reset_module.RehearsalTaskReset)
    operation.runner = TransferRunner()
    operation.source = Path(".").resolve()
    operation.repository = "owner/private-rehearsal"
    operation.archive_repository = "owner/private-rehearsal-archive"
    operation.task_id = "NSC-901"
    operation.branch = "nsc-901-smoke"
    plan = {
        "source_issue": {"number": 7},
        "task_branch": operation.branch,
        "task_head": "a" * 40,
        "pull_request": {"url": "https://example.invalid/pr/1"},
        "merge_commit": "b" * 40,
    }
    original_find = reset_module._find_complete_issue
    original_sleep = reset_module.time.sleep
    attempts = 0

    def transient(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RehearsalResetError("archive event chain is briefly inconsistent")
        return {"url": "https://example.invalid/archive/issues/7"}

    try:
        reset_module._find_complete_issue = transient
        reset_module.time.sleep = lambda _delay: None
        url = operation._transfer_issue(plan, "c" * 40)
        expect(url.endswith("/7"), "transient archive observation did not recover")
        expect(attempts == 2, "transient archive mismatch was not retried once")

        def persistent(*_args, **_kwargs):
            raise RehearsalResetError("persistent archive event mismatch")

        reset_module._find_complete_issue = persistent
        expect_error(
            lambda: operation._transfer_issue(plan, "c" * 40),
            "persistent archive event mismatch",
        )
    finally:
        reset_module._find_complete_issue = original_find
        reset_module.time.sleep = original_sleep

def main() -> int:
    test_repository_guard()
    test_issue_transfer_retries_transient_archive_validation()
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
        test_additive_revert_preserves_later_unrelated_history(root)
        test_later_main_reset_resume_refusals(root)
        test_not_delivered_resume_ignores_an_unrelated_later_merge(root)
    print("reset_rehearsal_task_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
