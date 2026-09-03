#!/usr/bin/env python3
"""Focused local tests for production delivered-task revert safeguards."""

from __future__ import annotations

import os
import json
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.reset_rehearsal_task import (  # noqa: E402
    CommandRunner,
    _remove_tree_exact,
)
from Pipeline.TaskReviewAgent.reset_task import (  # noqa: E402
    TaskResetError,
    _abandoned_rehearsal_state_is_undelivered,
    _fetch_exact_remote_commit_object,
    _require_task_paths_unchanged_since_merge,
    _transitive_active_dependents,
    _tree_entry,
    _validate_branchless_checkout_manifest,
)
from Pipeline.TaskReviewAgent.contracts import semantic_sha256  # noqa: E402


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


def test_undecomposed_aggregate_is_safe_abandoned_rehearsal_state() -> None:
    task = {
        "execution_scope": "needs_execution_decomposition",
        "decomposition_state": "concrete",
    }
    expect(
        _abandoned_rehearsal_state_is_undelivered(task, "aggregate"),
        "undecomposed aggregate was not recognized as undelivered",
    )
    task["decomposition_state"] = "decomposed"
    task["decomposition_children"] = ["NSC-991", "NSC-992"]
    expect(
        not _abandoned_rehearsal_state_is_undelivered(task, "aggregate"),
        "applied decomposition was accepted as an abandoned undecomposed parent",
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


def test_readonly_tree_removal(root: Path) -> None:
    target = root / "readonly-tree"
    target.mkdir()
    readonly = target / "object"
    readonly.write_bytes(b"git object fixture\n")
    readonly.chmod(stat.S_IREAD)
    _remove_tree_exact(target)
    expect(not target.exists(), "read-only checkout tree was not removed")


def test_branchless_checkout_manifest_guard(root: Path) -> None:
    checkout = root / "NSC-901"
    checkout.mkdir()
    task = {
        "id": "NSC-901",
        "contract_revision": 1,
        "task_contract_sha256": "a" * 64,
    }
    payload = {
        "schema_version": "2.0",
        "task_id": "NSC-901",
        "checkout_path": str(checkout),
        "branch": "nsc-901-smoke",
        "remote_url": "https://github.com/example/rehearsal.git",
        "initial_source_head": "1" * 40,
        "initial_source_tree": "2" * 40,
        "task_contract_path": "Tasks/NSC-901.yaml",
        "task_contract_revision": 1,
        "task_contract_sha256": "a" * 64,
        "authority": "durable_checkout_identity",
    }
    manifest = {"manifest_sha256": semantic_sha256(payload), **payload}
    path = root / "NSC-901.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    _validate_branchless_checkout_manifest(
        path,
        task=task,
        checkout=checkout,
        branch="nsc-901-smoke",
        source_head="1" * 40,
        source_tree="2" * 40,
        origin="https://github.com/example/rehearsal.git",
    )
    manifest["initial_source_head"] = "3" * 40
    path.write_text(json.dumps(manifest), encoding="utf-8")
    try:
        _validate_branchless_checkout_manifest(
            path,
            task=task,
            checkout=checkout,
            branch="nsc-901-smoke",
            source_head="1" * 40,
            source_tree="2" * 40,
            origin="https://github.com/example/rehearsal.git",
        )
    except TaskResetError as exc:
        expect("manifest hash" in str(exc), "tampered manifest failure was unclear")
    else:
        raise AssertionError("tampered branchless checkout manifest was accepted")


def test_exact_remote_branch_object_is_fetched_without_local_ref(root: Path) -> None:
    remote = root / "remote.git"
    producer = root / "producer"
    consumer = root / "consumer"
    run("git", "init", "--bare", str(remote), cwd=root)
    run("git", "clone", str(remote), str(producer), cwd=root)
    run("git", "config", "user.name", "Smoke Test", cwd=producer)
    run("git", "config", "user.email", "smoke@example.invalid", cwd=producer)
    run("git", "switch", "-c", "main", cwd=producer)
    (producer / "base.txt").write_text("base\n", encoding="utf-8")
    run("git", "add", "base.txt", cwd=producer)
    run("git", "commit", "-m", "base", cwd=producer)
    run("git", "push", "-u", "origin", "main", cwd=producer)
    run("git", "symbolic-ref", "HEAD", "refs/heads/main", cwd=remote)
    run("git", "clone", "--branch", "main", str(remote), str(consumer), cwd=root)

    run("git", "switch", "-c", "task-branch", cwd=producer)
    (producer / "task.txt").write_text("task\n", encoding="utf-8")
    run("git", "add", "task.txt", cwd=producer)
    run("git", "commit", "-m", "task", cwd=producer)
    task_head = run("git", "rev-parse", "HEAD", cwd=producer)
    run("git", "push", "origin", "HEAD:refs/heads/task-branch", cwd=producer)
    missing = subprocess.run(
        ("git", "cat-file", "-e", f"{task_head}^{{commit}}"),
        cwd=str(consumer),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    expect(missing.returncode != 0, "consumer unexpectedly had remote task object")

    _fetch_exact_remote_commit_object(
        CommandRunner(),
        consumer,
        remote="origin",
        ref="refs/heads/task-branch",
        expected_oid=task_head,
    )
    expect(
        run("git", "cat-file", "-t", task_head, cwd=consumer) == "commit",
        "exact remote task object was not fetched",
    )
    local_ref = subprocess.run(
        ("git", "show-ref", "--verify", "--quiet", "refs/heads/task-branch"),
        cwd=str(consumer),
        check=False,
    )
    expect(local_ref.returncode != 0, "preflight fetch created a local task branch")


def main() -> int:
    test_dependency_walk()
    test_undecomposed_aggregate_is_safe_abandoned_rehearsal_state()
    preferred = Path(os.environ.get("NSC_TEST_TEMP_ROOT", ""))
    temporary_parent = preferred if str(preferred) else None
    if temporary_parent:
        temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="reset-production-task-",
        dir=str(temporary_parent) if temporary_parent else None,
    ) as directory:
        root = Path(directory)
        test_path_guard(root / "repo")
        test_readonly_tree_removal(root)
        test_branchless_checkout_manifest_guard(root)
        test_exact_remote_branch_object_is_fetched_without_local_ref(root)
    print("reset_task_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
