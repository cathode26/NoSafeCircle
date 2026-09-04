#!/usr/bin/env python3
"""Prove coordination reads real committed task contracts, not empty stand-ins."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.committed_tasks import (  # noqa: E402
    CommittedTaskError,
    load_committed_task,
)

TASK_ID = "NSC-777"
RESOURCES = [
    "unity-scene:Assets/Scenes/Shared.unity",
    "unity-prefab:Assets/Prefabs/Door.prefab",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def create_repo(root: Path, *, contract_id: str = TASK_ID) -> bytes:
    git(root, "init", "--quiet")
    git(root, "config", "user.name", "Committed Task Loader Smoke")
    git(root, "config", "user.email", "committed-task-loader@example.invalid")
    (root / "Tasks").mkdir()
    contract = {
        "schema_version": "2.0",
        "id": contract_id,
        "title": "Committed loader fixture",
        "exclusive_resources": RESOURCES,
    }
    raw = (json.dumps(contract, indent=2) + "\n").encode("utf-8")
    (root / f"Tasks/{TASK_ID}.yaml").write_bytes(raw)
    git(root, "add", "Tasks")
    git(root, "commit", "--quiet", "-m", "Add fixture task contract")
    return raw


def test_real_committed_exclusive_resources_are_loaded() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-committed-task-") as temporary:
        root = Path(temporary)
        raw = create_repo(root)
        task = load_committed_task(root, TASK_ID)
        require(task["id"] == TASK_ID, "task identity was not verified")
        require(
            task["exclusive_resources"] == RESOURCES,
            f"real committed resources were not loaded: {task['exclusive_resources']}",
        )
        expected_hash = hashlib.sha256(raw).hexdigest()
        require(
            task["task_contract_sha256"] == expected_hash,
            "contract hash does not match committed bytes",
        )
        # Explicit hash pinning verifies the exact committed contract bytes.
        require(
            load_committed_task(root, TASK_ID, expected_sha256=expected_hash)["id"] == TASK_ID,
            "expected-hash load failed",
        )
        try:
            load_committed_task(root, TASK_ID, expected_sha256="0" * 64)
        except CommittedTaskError as exc:
            require("hash mismatch" in str(exc), f"unexpected error: {exc}")
        else:
            raise AssertionError("wrong expected hash was accepted")
        # An uncommitted edit must not change what HEAD-based coordination sees.
        (root / f"Tasks/{TASK_ID}.yaml").write_text("{}\n", encoding="utf-8")
        require(
            load_committed_task(root, TASK_ID)["exclusive_resources"] == RESOURCES,
            "loader read the working tree instead of committed HEAD",
        )


def test_missing_and_mismatched_contracts_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-committed-task-") as temporary:
        root = Path(temporary)
        create_repo(root)
        try:
            load_committed_task(root, "NSC-999")
        except CommittedTaskError as exc:
            require("missing at HEAD" in str(exc), f"unexpected error: {exc}")
        else:
            raise AssertionError("missing contract was accepted")
    with tempfile.TemporaryDirectory(prefix="nsc-committed-task-") as temporary:
        root = Path(temporary)
        # The file exists but declares a different task identity.
        create_repo(root, contract_id="NSC-888")
        try:
            load_committed_task(root, TASK_ID)
        except CommittedTaskError as exc:
            require("identity mismatch" in str(exc), f"unexpected error: {exc}")
        else:
            raise AssertionError("identity mismatch was accepted")


def test_exact_historical_commit_load_is_hash_bound() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-committed-task-") as temporary:
        root = Path(temporary)
        original_raw = create_repo(root)
        original_head = git(root, "rev-parse", "HEAD")
        changed = {
            "schema_version": "2.0",
            "id": TASK_ID,
            "title": "Changed committed loader fixture",
            "exclusive_resources": [],
        }
        (root / f"Tasks/{TASK_ID}.yaml").write_text(
            json.dumps(changed, indent=2) + "\n", encoding="utf-8"
        )
        git(root, "add", "Tasks")
        git(root, "commit", "--quiet", "-m", "Change fixture contract")
        historical_hash = hashlib.sha256(original_raw).hexdigest()
        historical = load_committed_task(
            root,
            TASK_ID,
            commit=original_head,
            expected_sha256=historical_hash,
        )
        require(historical["exclusive_resources"] == RESOURCES, str(historical))
        require(
            load_committed_task(root, TASK_ID)["exclusive_resources"] == [],
            "default load did not remain bound to current HEAD",
        )
        for unsafe in ("HEAD", f"{original_head}^", original_head.upper()):
            try:
                load_committed_task(root, TASK_ID, commit=unsafe)
            except CommittedTaskError as exc:
                require("exact lowercase" in str(exc), str(exc))
            else:
                raise AssertionError(f"unsafe revision expression was accepted: {unsafe}")


def test_shared_loader_is_used_by_selection_and_workflow() -> None:
    """No coordination-facing module should keep a private near-duplicate loader
    or a synthesized empty-resource task_loader lambda."""

    import inspect

    from Pipeline.TaskReviewAgent import (
        durable_selection,
        generic_selection,
        issue_queue,
        issue_state_action,
        issue_workflow_action,
        real_workflow,
        run_pipeline_agent,
    )

    for module in (
        durable_selection,
        generic_selection,
        issue_queue,
        issue_state_action,
        issue_workflow_action,
        real_workflow,
        run_pipeline_agent,
    ):
        source = inspect.getsource(module)
        require(
            "load_committed_task" in source,
            f"{module.__name__} does not use the shared committed-task loader",
        )
        require(
            '"exclusive_resources": []' not in source
            and "'exclusive_resources': []" not in source,
            f"{module.__name__} still synthesizes an empty exclusive_resources task",
        )


def main() -> int:
    tests = (
        test_real_committed_exclusive_resources_are_loaded,
        test_missing_and_mismatched_contracts_fail_closed,
        test_exact_historical_commit_load_is_hash_bound,
        test_shared_loader_is_used_by_selection_and_workflow,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent committed task loader tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
