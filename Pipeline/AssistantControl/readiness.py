"""Read-only task readiness inspection for conversation-operated selection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from Pipeline.AssistantControl import admission
from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.dependencies import inspect_dependencies
from Pipeline.AssistantControl.inspect_project import changes, git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id


def _dependency_view(result: dict[str, Any]) -> dict[str, Any]:
    task_state = result.get("task_state")
    dependencies = result.get("dependencies")
    return {
        "task_id": result.get("task_id"),
        "source_commit": result.get("source_commit"),
        "contract_sha256": result.get("contract_sha256"),
        "task_state": task_state.get("state") if isinstance(task_state, dict) else None,
        "dependencies": [
            {"task_id": item.get("task_id"), "state": item.get("state")}
            for item in dependencies or [] if isinstance(item, dict)
        ],
        "blocked_dependencies": list(result.get("blocked_dependencies") or []),
        "approved_local_dependencies": dict(result.get("approved_local_dependencies") or {}),
        "source_unchanged_during_read": result.get("source_unchanged_during_read"),
        "dependencies_satisfied": result.get("dependencies_satisfied"),
    }


def _checkout_view(result: dict[str, Any]) -> dict[str, Any]:
    candidate = result.get("candidate")
    return {
        "task_id": result.get("task_id"),
        "path": result.get("checkout"),
        "status": result.get("status"),
        "branch": result.get("current_branch") or result.get("branch"),
        "source_commit": result.get("source_commit"),
        "current_commit": result.get("current_commit"),
        "candidate_commit": candidate.get("commit") if isinstance(candidate, dict) else None,
        "local_changes": list(result.get("local_changes") or []),
    }


def _registry_snapshot(checkouts: Checkouts) -> tuple[dict[str, Any], bool]:
    _, path = admission._source_registry_paths(checkouts.source)
    before = path.read_bytes() if path.is_file() else None
    registry = admission._read_registry(path, checkouts.source)
    after = path.read_bytes() if path.is_file() else None
    return registry, before == after


def inspect_readiness(
    checkouts: Checkouts, task_id: str, *, capacity: int = 1,
    dependency_reader=None,
) -> dict[str, Any]:
    """Explain whether a task can be reserved now, without reserving it."""
    task_id = validate_task_id(task_id)
    if type(capacity) is not int or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("readiness capacity must be a positive integer")
    source = checkouts.source
    source_head = git(source, "rev-parse", "HEAD").decode().strip()
    task = load_committed_task(source, task_id, commit=source_head)
    problems: list[str] = []
    if task.get("contract_disposition") != "active":
        problems.append("task_contract_inactive")
    try:
        admission._executable_task(task)
    except ValueError:
        problems.append("task_not_single_agent_implementation")

    reader = dependency_reader or inspect_dependencies
    try:
        dependency_result = dict(reader(source, task_id, checkouts.root))
        admission._dependency_is_satisfied(dependency_result, task_id, source_head)
    except Exception as exc:
        dependency_result = {
            "task_id": task_id, "source_commit": source_head,
            "dependencies_satisfied": False, "error": str(exc),
        }
        problems.append("dependencies_not_satisfied")
    dependency = _dependency_view(dependency_result)
    if dependency_result.get("error"):
        dependency["error"] = dependency_result["error"]

    record_path = checkouts.records / f"{task_id}.json"
    record: dict[str, Any] | None = None
    checkout_view: dict[str, Any] | None = None
    scope: dict[str, Any] | None = None
    scope_registered = False
    checkout_error: str | None = None
    baseline: str | None = None
    resources = sorted(
        {admission._resource_path(value) for value in task.get("exclusive_resources") or []}
    )
    if not record_path.is_file():
        problems.append("task_checkout_not_prepared")
    else:
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("task record must be an object")
            observed = checkouts.observe(task_id)
            checkout_view = _checkout_view(observed)
            scope_registered = isinstance(record.get("scope"), dict)
            baseline = admission._revision_baseline(
                checkouts, record, task_id, source_head,
            )
            checkout_head = baseline or source_head
            if record.get("status") not in {"prepared", "planned"}:
                problems.append("task_checkout_has_work_or_review_state")
            scope = admission._validate_persisted_scope(
                checkouts, record, task_id,
                admission._clean_checkout(checkouts, record, checkout_head),
                load_committed_task(
                    Path(record["checkout"]), task_id, commit=checkout_head,
                    expected_sha256=record.get("task_contract_sha256"),
                ),
            )
            resources = admission._reservation_resources(task, scope)
        except Exception as exc:
            if "task_checkout_has_work_or_review_state" not in problems:
                problems.append("checkout_or_scope_not_ready")
            checkout_error = str(exc)
            checkout_view = checkout_view or {"task_id": task_id, "error": checkout_error}

    edited = []
    for item in changes(source):
        for key in ("path", "original_path"):
            value = item.get(key)
            if isinstance(value, str) and value:
                edited.append(admission._resource_path(value))
    source_conflicts = sorted({
        edit for edit in edited
        if any(admission._overlap(edit, resource) for resource in resources)
    })
    if source_conflicts:
        problems.append("source_has_conflicting_local_edits")

    registry, registry_stable = _registry_snapshot(checkouts)
    reservations = registry["reservations"]
    if not registry_stable:
        problems.append("admission_registry_changed_during_read")
    if len(reservations) >= capacity:
        problems.append("worker_capacity_exhausted")
    if any(item.get("task_id") == task_id for item in reservations):
        problems.append("task_already_reserved")
    resource_owners = sorted({
        str(item.get("task_id")) for item in reservations
        if item.get("task_id") != task_id
        and any(admission._overlap(left, right)
                for left in resources for right in item.get("resources", []))
    })
    if resource_owners:
        problems.append("resources_reserved_by_other_tasks")
    source_stable = git(source, "rev-parse", "HEAD").decode().strip() == source_head
    if not source_stable:
        problems.append("source_changed_during_read")

    problems = list(dict.fromkeys(problems))
    return {
        "schema_version": "assistant-task-readiness/v1",
        "task_id": task_id,
        "source": str(source),
        "source_commit": source_head,
        "source_unchanged_during_read": source_stable,
        "dependencies": dependency,
        "checkout": checkout_view,
        "scope_registered": scope_registered,
        "scope_validated": scope is not None,
        "checkout_error": checkout_error,
        "revision_baseline": baseline,
        "requested_capacity": capacity,
        "active_reservations": len(reservations),
        "available_capacity": max(0, capacity - len(reservations)),
        "resources": resources,
        "resource_owners": resource_owners,
        "source_edit_conflicts": source_conflicts,
        "ready_to_reserve": not problems,
        "problems": problems,
        "execution_authorized": False,
        "mutations_performed": False,
    }


__all__ = ["inspect_readiness"]
