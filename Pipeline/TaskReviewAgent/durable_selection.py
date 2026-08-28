"""Select a validated agent-ready Issue without assuming the task is not_delivered."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .contracts import TaskReviewContractError, validate_task_id
from .issue_workflow_store import GhIssueBackend, IssueWorkflowService


class DurableSelectionError(TaskReviewContractError):
    """Raised when no safe generic Issue resume candidate exists."""


def _repo_root(source: Path | str) -> Path:
    source = Path(source).resolve()
    result = subprocess.run(
        ("git", "-C", str(source), "rev-parse", "--show-toplevel"),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60.0,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise DurableSelectionError("source is not a readable Git repository")
    return Path(result.stdout.strip()).resolve()


def _committed_task(root: Path, task_id: str) -> dict[str, Any]:
    task_id = validate_task_id(task_id)
    path = f"Tasks/{task_id}.yaml"
    result = subprocess.run(
        ("git", "-C", str(root), "show", f"HEAD:{path}"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60.0,
    )
    if result.returncode != 0:
        raise DurableSelectionError(f"managed Issue task contract is missing: {path}")
    try:
        value = json.loads(result.stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DurableSelectionError(f"managed Issue task contract is invalid: {path}") from exc
    if not isinstance(value, dict) or value.get("id") != task_id:
        raise DurableSelectionError(f"managed Issue task identity mismatch: {path}")
    return {
        **value,
        "task_contract_sha256": hashlib.sha256(result.stdout).hexdigest(),
    }


def select_agent_ready_issue(
    *,
    source: Path | str,
    worker_id: str,
) -> dict[str, Any]:
    """Return the first fully validated Issue whose current contract still matches.

    No TaskGraph delivery-state filter is applied here. That is deliberate: a task can
    already be `conformant` while its managed Issue still has merge/check/closeout work.
    The phase recorded in the validated Issue controls the downstream route.
    """

    root = _repo_root(source)
    service = IssueWorkflowService(
        backend=GhIssueBackend(source_root=root),
        task_loader=lambda task_id: _committed_task(root, task_id),
        worker_id=worker_id,
    )
    ready = service.list_agent_ready()
    if not ready:
        raise DurableSelectionError(
            "no fully validated nsc-state:agent-ready Issue is available"
        )

    stale: list[str] = []
    for item in ready:
        state = item.get("workflow_state") or {}
        task_id = state.get("task_id")
        if not isinstance(task_id, str):
            stale.append(f"Issue #{item.get('issue_number')} has no task identity")
            continue
        task = _committed_task(root, task_id)
        if state.get("task_contract_sha256") != task["task_contract_sha256"]:
            stale.append(
                f"{task_id} Issue contract hash differs from current committed contract"
            )
            continue
        return {
            "schema_version": "1.0",
            "selection_priority": "resume_agent_ready_before_new_task",
            "task_id": task_id,
            "issue_number": item.get("issue_number"),
            "issue_url": item.get("issue_url"),
            "workflow_state": state,
            "event_count": item.get("event_count"),
            "task_contract_sha256": task["task_contract_sha256"],
            "authority": "validated_issue_queue_and_current_contract",
        }

    raise DurableSelectionError(
        "agent-ready Issues exist but none match current committed task contracts: "
        + "; ".join(stale)
    )
