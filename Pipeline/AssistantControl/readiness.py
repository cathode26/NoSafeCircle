"""Read-only task readiness inspection for conversation-operated selection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl import admission, worker_state
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


# graph_controller emits a `settle_worker` action for exactly these statuses;
# the two must agree, so the set is stated the same way.
_TERMINAL_WORKER_STATUSES = frozenset({"succeeded", "failed", "stopped", "spawn_failed"})


def _reservations_awaiting_settle(checkouts: Checkouts, reservations: Any) -> tuple[list[str], list[str]]:
    """Reservations whose run ENDED but was never settled.

    A bare count cannot tell these from work in flight, so capacity reads as a
    busy pipeline while it is really bookkeeping debt -- and unlike a running
    crew it never clears itself, so nothing dispatches again until someone runs
    `settle-worker`. Naming the holder is the whole point; `is_settled_worker`
    is the record's own proof that the process and containers are gone.

    Control records live under a checkout ROOT while the admissions registry
    lives on the source, so a reservation taken from a different root is not
    readable here. Those are returned separately rather than counted as clean:
    an unreadable record is unknown, not settled.
    """
    awaiting: list[str] = []
    unreadable: list[str] = []
    for item in reservations or []:
        task_id = item.get("task_id") if isinstance(item, Mapping) else None
        if not isinstance(task_id, str) or not task_id:
            continue
        try:
            record = json.loads((checkouts.records / f"{task_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable.append(task_id)
            continue
        if not isinstance(record, Mapping):
            unreadable.append(task_id)
            continue
        worker = record.get("worker") or record.get("launch")
        if not isinstance(worker, Mapping):
            continue
        if (worker.get("status") in _TERMINAL_WORKER_STATUSES
                and not worker_state.is_settled_worker(worker)):
            awaiting.append(task_id)
    return sorted(set(awaiting)), sorted(set(unreadable))


def inspect_readiness(
    checkouts: Checkouts, task_id: str, *, capacity: int = 1,
    dependency_reader=None, allow_resource_overlap: bool = False,
) -> dict[str, Any]:
    """Explain whether a task can be reserved now, without reserving it."""
    task_id = validate_task_id(task_id)
    if type(capacity) is not int or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("readiness capacity must be a positive integer")
    if type(allow_resource_overlap) is not bool:
        raise ValueError("allow_resource_overlap must be a boolean")
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
            if baseline is None:
                # ASK THE SAME QUESTION `reserve` ASKS, OR REPORT A TASK
                # UNREADY THAT `reserve` WOULD ADMIT. `admission.reserve`
                # falls back to this at admission.py:454; readiness did not,
                # so a record sitting on a `revise-on-source` reconciliation
                # was measured against current Source HEAD instead of against
                # its own baseline and came back
                # "checkout_or_scope_not_ready: task checkout is not at
                # current source HEAD" -- a WRONG ANSWER, not a missing
                # feature. NSC-118 read exactly that at 2026-09-25 23:1xZ
                # while every precondition `reserve` has was satisfied.
                #
                # Found by Astra reviewing the seam-1 branch: "admission
                # recognizes reconciled baselines, but readiness checks only
                # ordinary revisions before falling back to current Source
                # HEAD. Consequently, a reconciled merge can fail readiness
                # even before main advances." Re-reconciling cannot satisfy
                # that equality either, which is why the remedy had to be
                # this function and not another merge.
                baseline = admission._revise_on_source_baseline(
                    checkouts, record, source_head,
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
            checkout_error = str(exc)
            if "task_checkout_has_work_or_review_state" not in problems:
                # NAME THE CAUSE WHERE THE READER IS LOOKING. This label is
                # appended from an exception handler, and on its own it says
                # only the CATEGORY -- the actual reason ("task checkout is not
                # at current source HEAD", for instance) sits in the separate
                # `checkout_error` field, which a reader of `problems` has no
                # pointer to. Reported from the floor by the Pipeline Runner,
                # which lost a detour to it while diagnosing why NSC-118 was
                # prepared, dependency-clear, resource-free and still
                # undispatchable. The stable code is kept as a PREFIX so a
                # machine match on it still works.
                problems.append(
                    f"checkout_or_scope_not_ready: {checkout_error}")
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
    awaiting_settle, unreadable_reservations = _reservations_awaiting_settle(checkouts, reservations)
    if len(reservations) >= capacity:
        problems.append("worker_capacity_exhausted")
        if awaiting_settle:
            problems.append("worker_capacity_held_by_unsettled_runs")
    if any(item.get("task_id") == task_id for item in reservations):
        problems.append("task_already_reserved")
    resource_owners = []
    blocking_resource_owners = []
    for item in reservations:
        if item.get("task_id") == task_id:
            continue
        requested_overlap, owner_overlap = admission._overlapping_resources(resources, item)
        if not requested_overlap:
            continue
        owner_id = str(item.get("task_id"))
        resource_owners.append(owner_id)
        if not (allow_resource_overlap and admission._parallel_checkout_overlap_allowed(
            checkouts, task_id, item, requested_overlap, owner_overlap,
        )):
            blocking_resource_owners.append(owner_id)
    resource_owners = sorted(set(resource_owners))
    blocking_resource_owners = sorted(set(blocking_resource_owners))
    if blocking_resource_owners:
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
        "reservations_awaiting_settle": awaiting_settle,
        "reservations_not_readable_here": unreadable_reservations,
        "available_capacity": max(0, capacity - len(reservations)),
        "resources": resources,
        "resource_owners": resource_owners,
        "blocking_resource_owners": blocking_resource_owners,
        "resource_overlap_authorized": allow_resource_overlap,
        "source_edit_conflicts": source_conflicts,
        "ready_to_reserve": not problems,
        "problems": problems,
        "execution_authorized": False,
        "mutations_performed": False,
    }


__all__ = ["inspect_readiness"]
