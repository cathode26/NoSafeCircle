from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from work_graph_transform import PROJECT_ROOT_KEY, WorkGraphPlan

WORK_ID_PATTERN = re.compile(r"^NSC-(\d{3,})$")


class WorkGraphValidationError(RuntimeError):
    """Raised when an in-memory work graph violates deterministic graph invariants."""


@dataclass(frozen=True)
class WorkGraphValidationSummary:
    task_count: int
    parent_edge_count: int
    dependency_edge_count: int
    root_id: str
    root_key: str
    resource_group_count: int
    project_requirement_count: int


def _require_non_empty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkGraphValidationError(f"{label} must be a non-empty string.")
    return value.strip()


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise WorkGraphValidationError(f"{label} must be a list.")
    return value


def _detect_cycle(edges: dict[str, list[str]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            try:
                start = stack.index(node)
                cycle = stack[start:] + [node]
            except ValueError:
                cycle = [node, node]
            raise WorkGraphValidationError(
                f"{label} contains a cycle: " + " -> ".join(cycle)
            )

        visiting.add(node)
        stack.append(node)
        for target in edges.get(node, []):
            visit(target)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in edges:
        visit(node)


def validate_work_graph_plan(plan: WorkGraphPlan) -> WorkGraphValidationSummary:
    if not plan.tasks:
        raise WorkGraphValidationError("Work graph contains no tasks.")
    if len(plan.id_map) != len(plan.tasks):
        raise WorkGraphValidationError(
            f"ID map/task count mismatch: id_map={len(plan.id_map)}, tasks={len(plan.tasks)}"
        )

    tasks_by_id: dict[str, dict[str, Any]] = {}
    tasks_by_key: dict[str, dict[str, Any]] = {}
    numeric_ids: list[int] = []

    for index, task in enumerate(plan.tasks):
        if not isinstance(task, dict):
            raise WorkGraphValidationError(f"tasks[{index}] is not an object.")

        task_id = _require_non_empty_text(task.get("id"), f"tasks[{index}].id")
        key = _require_non_empty_text(
            task.get("reconciliation_key"), f"tasks[{index}].reconciliation_key"
        )
        title = _require_non_empty_text(task.get("title"), f"{task_id}.title")
        kind = _require_non_empty_text(task.get("kind"), f"{task_id}.kind")
        status = _require_non_empty_text(task.get("status"), f"{task_id}.status")
        scope = _require_non_empty_text(task.get("execution_scope"), f"{task_id}.execution_scope")

        if task_id in tasks_by_id:
            raise WorkGraphValidationError(f"Duplicate task id: {task_id}")
        if key in tasks_by_key:
            raise WorkGraphValidationError(f"Duplicate reconciliation_key: {key}")

        match = WORK_ID_PATTERN.fullmatch(task_id)
        if not match:
            raise WorkGraphValidationError(f"Invalid persistent task id: {task_id!r}")
        numeric_ids.append(int(match.group(1)))

        expected_id = plan.id_map.get(key)
        if expected_id != task_id:
            raise WorkGraphValidationError(
                f"ID map mismatch for {key}: expected {expected_id!r}, task has {task_id!r}"
            )

        if kind == "feature" and scope == "single_agent":
            raise WorkGraphValidationError(
                f"Feature node {task_id} ({title}) may not be directly single-agent executable."
            )
        if scope == "single_agent" and kind not in {"implementation", "artifact"}:
            raise WorkGraphValidationError(
                f"Single-agent work {task_id} must be implementation/artifact, not {kind!r}."
            )

        for field in ("depends_on", "exclusive_resources", "acceptance_criteria", "validation_requirements"):
            _require_list(task.get(field), f"{task_id}.{field}")

        bootstrap_source = task.get("bootstrap_source")
        if not isinstance(bootstrap_source, dict):
            raise WorkGraphValidationError(f"{task_id}.bootstrap_source must be an object.")
        _require_non_empty_text(
            bootstrap_source.get("reconciliation_run_id"),
            f"{task_id}.bootstrap_source.reconciliation_run_id",
        )
        _require_non_empty_text(
            bootstrap_source.get("verification_run_id"),
            f"{task_id}.bootstrap_source.verification_run_id",
        )

        tasks_by_id[task_id] = task
        tasks_by_key[key] = task

    expected_numbers = list(range(1, len(plan.tasks) + 1))
    if sorted(numeric_ids) != expected_numbers:
        raise WorkGraphValidationError(
            "Persistent task IDs must form one contiguous bootstrap range: "
            f"expected 1..{len(plan.tasks)}, got {sorted(numeric_ids)}"
        )

    root_tasks = [task for task in plan.tasks if not str(task.get("parent") or "").strip()]
    if len(root_tasks) != 1:
        raise WorkGraphValidationError(
            f"Work graph must contain exactly one root task; found {len(root_tasks)}."
        )

    root = root_tasks[0]
    if root["id"] != "NSC-001" or root["reconciliation_key"] != PROJECT_ROOT_KEY:
        raise WorkGraphValidationError(
            "Work graph root must be NSC-001 / no-safe-circle; "
            f"got {root['id']} / {root['reconciliation_key']}"
        )

    parent_edges: dict[str, list[str]] = {task_id: [] for task_id in tasks_by_id}
    parent_edge_count = 0
    for task_id, task in tasks_by_id.items():
        parent = str(task.get("parent") or "").strip()
        if task_id == root["id"]:
            if parent:
                raise WorkGraphValidationError("Project root may not have a parent.")
            continue
        if not parent:
            raise WorkGraphValidationError(f"Non-root task {task_id} is missing its parent.")
        if parent == task_id:
            raise WorkGraphValidationError(f"Task {task_id} may not parent itself.")
        if parent not in tasks_by_id:
            raise WorkGraphValidationError(
                f"Task {task_id} references missing parent {parent!r}."
            )
        parent_edges[task_id].append(parent)
        parent_edge_count += 1

    _detect_cycle(parent_edges, "Parent hierarchy")

    # Every node must eventually reach the single project root.
    for task_id in tasks_by_id:
        cursor = task_id
        seen: set[str] = set()
        while cursor != root["id"]:
            if cursor in seen:
                raise WorkGraphValidationError(
                    f"Parent hierarchy does not terminate at the project root for {task_id}."
                )
            seen.add(cursor)
            parent = str(tasks_by_id[cursor].get("parent") or "").strip()
            if not parent:
                raise WorkGraphValidationError(
                    f"Task {task_id} is disconnected from project root {root['id']}."
                )
            cursor = parent

    dependency_edges: dict[str, list[str]] = {task_id: [] for task_id in tasks_by_id}
    dependency_edge_count = 0
    for task_id, task in tasks_by_id.items():
        dependencies = task["depends_on"]
        if len(dependencies) != len(set(dependencies)):
            raise WorkGraphValidationError(f"Task {task_id} contains duplicate dependencies.")
        for dependency_id in dependencies:
            dependency_id = _require_non_empty_text(
                dependency_id, f"{task_id}.depends_on entry"
            )
            if dependency_id == task_id:
                raise WorkGraphValidationError(f"Task {task_id} may not depend on itself.")
            if dependency_id not in tasks_by_id:
                raise WorkGraphValidationError(
                    f"Task {task_id} references missing dependency {dependency_id!r}."
                )
            dependency_edges[task_id].append(dependency_id)
            dependency_edge_count += 1

    _detect_cycle(dependency_edges, "Dependency graph")

    # All task bootstrap provenance must point at the same approved source/verification pair.
    provenance_pairs = {
        (
            task["bootstrap_source"]["reconciliation_run_id"],
            task["bootstrap_source"]["verification_run_id"],
        )
        for task in plan.tasks
    }
    if len(provenance_pairs) != 1:
        raise WorkGraphValidationError(
            f"Tasks contain mixed bootstrap provenance: {sorted(provenance_pairs)!r}"
        )

    # Validate resource groups and also prove that every resource shared by multiple tasks has
    # one exact group. Single-owner resources do not need a coordination group.
    claimed_by: dict[str, set[str]] = defaultdict(set)
    for task_id, task in tasks_by_id.items():
        resources = task["exclusive_resources"]
        if len(resources) != len(set(resources)):
            raise WorkGraphValidationError(
                f"Task {task_id} contains duplicate exclusive resource keys."
            )
        for resource in resources:
            resource_key = _require_non_empty_text(
                resource, f"{task_id}.exclusive_resources entry"
            )
            claimed_by[resource_key].add(task_id)

    groups_by_resource: dict[str, set[str]] = {}
    for index, group in enumerate(plan.resource_groups):
        if not isinstance(group, dict):
            raise WorkGraphValidationError(f"resource_groups[{index}] is not an object.")
        resource_key = _require_non_empty_text(
            group.get("resource_key"), f"resource_groups[{index}].resource_key"
        )
        if resource_key in groups_by_resource:
            raise WorkGraphValidationError(f"Duplicate resource group: {resource_key}")

        work_ids = _require_list(group.get("work_ids"), f"resource group {resource_key}.work_ids")
        reconciliation_keys = _require_list(
            group.get("reconciliation_keys"),
            f"resource group {resource_key}.reconciliation_keys",
        )
        if len(work_ids) != len(reconciliation_keys):
            raise WorkGraphValidationError(
                f"Resource group {resource_key} has mismatched ID/key membership lengths."
            )
        if len(work_ids) != len(set(work_ids)):
            raise WorkGraphValidationError(
                f"Resource group {resource_key} contains duplicate work IDs."
            )

        members: set[str] = set()
        for work_id, reconciliation_key in zip(work_ids, reconciliation_keys):
            work_id = _require_non_empty_text(work_id, f"resource group {resource_key}.work_id")
            reconciliation_key = _require_non_empty_text(
                reconciliation_key, f"resource group {resource_key}.reconciliation_key"
            )
            if work_id not in tasks_by_id:
                raise WorkGraphValidationError(
                    f"Resource group {resource_key} references missing task {work_id}."
                )
            task = tasks_by_id[work_id]
            if task["reconciliation_key"] != reconciliation_key:
                raise WorkGraphValidationError(
                    f"Resource group {resource_key} maps {work_id} to {reconciliation_key!r}, "
                    f"but task key is {task['reconciliation_key']!r}."
                )
            if resource_key not in task["exclusive_resources"]:
                raise WorkGraphValidationError(
                    f"Resource group {resource_key} includes {work_id}, but task does not claim it."
                )
            members.add(work_id)
        groups_by_resource[resource_key] = members

    for resource_key, owners in claimed_by.items():
        if len(owners) <= 1:
            continue
        grouped = groups_by_resource.get(resource_key)
        if grouped is None:
            raise WorkGraphValidationError(
                f"Shared exclusive resource {resource_key!r} has {len(owners)} owners but no resource group."
            )
        if grouped != owners:
            raise WorkGraphValidationError(
                f"Resource group {resource_key!r} does not exactly match task claims: "
                f"group={sorted(grouped)}, claims={sorted(owners)}"
            )

    for resource_key, members in groups_by_resource.items():
        owners = claimed_by.get(resource_key, set())
        if members != owners:
            raise WorkGraphValidationError(
                f"Resource group {resource_key!r} differs from task claims: "
                f"group={sorted(members)}, claims={sorted(owners)}"
            )

    seen_requirement_titles: set[str] = set()
    for index, requirement in enumerate(plan.project_requirements):
        if not isinstance(requirement, dict):
            raise WorkGraphValidationError(
                f"project_requirements[{index}] is not an object."
            )
        title = _require_non_empty_text(
            requirement.get("title"), f"project_requirements[{index}].title"
        )
        _require_non_empty_text(
            requirement.get("requirement_type"),
            f"project_requirements[{index}].requirement_type",
        )
        _require_non_empty_text(
            requirement.get("status"), f"project_requirements[{index}].status"
        )
        if title in seen_requirement_titles:
            raise WorkGraphValidationError(
                f"Duplicate project requirement title: {title!r}"
            )
        seen_requirement_titles.add(title)

    return WorkGraphValidationSummary(
        task_count=len(plan.tasks),
        parent_edge_count=parent_edge_count,
        dependency_edge_count=dependency_edge_count,
        root_id=root["id"],
        root_key=root["reconciliation_key"],
        resource_group_count=len(plan.resource_groups),
        project_requirement_count=len(plan.project_requirements),
    )
