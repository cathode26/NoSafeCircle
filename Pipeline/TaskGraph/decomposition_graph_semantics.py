from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from work_graph_validate import WorkGraphValidationError


class DecompositionGraphSemanticsError(WorkGraphValidationError):
    """Raised when a decomposed aggregate violates post-decomposition graph semantics."""


_AGGREGATE_REQUIREMENT_FIELDS = (
    "acceptance_criteria",
    "completion_gates",
    "downstream_integration_obligations",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def aggregate_requirement_sha256(task: dict[str, Any]) -> str:
    """Hash the parent obligations whose exact coverage justified the decomposition."""

    payload = {
        field: task.get(field, [])
        for field in _AGGREGATE_REQUIREMENT_FIELDS
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_decomposition_graph_semantics(plan: Any) -> None:
    """Validate semantics that apply once a decomposition publishes explicit child identity.

    Older reviewed decompositions predate ``decomposition_children`` and remain readable for
    compatibility. Every new graph delta must publish that field, which opts the aggregate
    into the stricter semantics below.
    """

    tasks = tuple(plan.tasks)
    tasks_by_id = {task["id"]: task for task in tasks}

    for child in tasks:
        if child.get("contract_disposition") != "active":
            continue
        provenance = child.get("provenance")
        if not isinstance(provenance, dict):
            continue
        plan_id = provenance.get("graph_delta_plan_id")
        if not isinstance(plan_id, str) or not plan_id.strip():
            continue

        child_id = child["id"]
        plan_id = plan_id.strip()
        direct_parent_id = child.get("parent")
        recorded_parent_id = provenance.get("parent_task_id")
        if not isinstance(recorded_parent_id, str) or not recorded_parent_id.strip():
            raise DecompositionGraphSemanticsError(
                f"Orphaned active decomposition child {child_id} from graph delta plan "
                f"{plan_id}: provenance.parent_task_id does not identify its parent "
                f"(direct parent={direct_parent_id!r})."
            )
        recorded_parent_id = recorded_parent_id.strip()
        if direct_parent_id != recorded_parent_id:
            raise DecompositionGraphSemanticsError(
                f"Orphaned active decomposition child {child_id} from graph delta plan "
                f"{plan_id}: provenance names parent {recorded_parent_id}, but the "
                f"contract's direct parent is {direct_parent_id!r}."
            )

        parent = tasks_by_id.get(recorded_parent_id)
        if parent is None:
            reason = "that parent contract is missing"
        elif parent.get("decomposition_state") != "decomposed":
            reason = (
                "that parent is not decomposed "
                f"(decomposition_state={parent.get('decomposition_state')!r})"
            )
        else:
            decomposition_children = parent.get("decomposition_children")
            if decomposition_children is None:
                continue
            if (
                isinstance(decomposition_children, list)
                and child_id in decomposition_children
            ):
                continue
            reason = "that parent does not list the child in decomposition_children"
        raise DecompositionGraphSemanticsError(
            f"Orphaned active decomposition child {child_id} from graph delta plan "
            f"{plan_id} under parent {recorded_parent_id}: {reason}."
        )

    for parent in tasks:
        child_ids = parent.get("decomposition_children")
        if child_ids is None:
            continue
        parent_id = parent["id"]
        if not isinstance(child_ids, list) or not child_ids:
            raise DecompositionGraphSemanticsError(
                f"Decomposed aggregate {parent_id}.decomposition_children must be a non-empty list."
            )
        if len(child_ids) != len(set(child_ids)):
            raise DecompositionGraphSemanticsError(
                f"Decomposed aggregate {parent_id} contains duplicate decomposition_children."
            )
        requirement_hash = parent.get("decomposition_requirement_sha256")
        if not isinstance(requirement_hash, str) or not _SHA256_RE.fullmatch(requirement_hash):
            raise DecompositionGraphSemanticsError(
                f"Decomposed aggregate {parent_id} must record decomposition_requirement_sha256."
            )
        if parent.get("decomposition_state") != "decomposed":
            raise DecompositionGraphSemanticsError(
                f"{parent_id}.decomposition_children is only valid when decomposition_state='decomposed'."
            )
        if parent.get("kind") != "feature":
            raise DecompositionGraphSemanticsError(
                f"Decomposed aggregate {parent_id} must have kind='feature', not {parent.get('kind')!r}."
            )
        if parent.get("execution_scope") != "not_applicable":
            raise DecompositionGraphSemanticsError(
                f"Decomposed aggregate {parent_id} must have execution_scope='not_applicable'."
            )
        if parent.get("exclusive_resources") != []:
            raise DecompositionGraphSemanticsError(
                f"Decomposed aggregate {parent_id} may not retain executable exclusive-resource locks."
            )

        for child_id in child_ids:
            if not isinstance(child_id, str) or not child_id.strip():
                raise DecompositionGraphSemanticsError(
                    f"{parent_id}.decomposition_children contains a blank or non-string child ID."
                )
            child = tasks_by_id.get(child_id)
            if child is None:
                raise DecompositionGraphSemanticsError(
                    f"Decomposed aggregate {parent_id} references missing child {child_id!r}."
                )
            if child.get("parent") != parent_id:
                raise DecompositionGraphSemanticsError(
                    f"Decomposition child {child_id} must be a direct child of aggregate {parent_id}."
                )
            if child.get("contract_disposition") != "active":
                raise DecompositionGraphSemanticsError(
                    f"Decomposition child {child_id} of active aggregate {parent_id} must be active."
                )

        expected_active_children = {
            task["id"]
            for task in tasks
            if task.get("contract_disposition") == "active"
            and task.get("parent") == parent_id
        }
        actual_children = set(child_ids)
        if actual_children != expected_active_children:
            missing = sorted(expected_active_children - actual_children)
            extra = sorted(actual_children - expected_active_children)
            raise DecompositionGraphSemanticsError(
                f"Decomposed aggregate {parent_id}.decomposition_children must exactly name all "
                f"active direct children (missing={missing}, extra={extra})."
            )

        for dependent in tasks:
            if dependent.get("contract_disposition") != "active":
                continue
            if parent_id in dependent.get("depends_on", []):
                raise DecompositionGraphSemanticsError(
                    f"Active contract {dependent['id']} may not depend on decomposed aggregate "
                    f"{parent_id}; rewrite the dependency to the concrete decomposition child "
                    "or children whose capability it actually consumes."
                )


def aggregate_child_state_summary(child_states: dict[str, str]) -> tuple[bool, str]:
    """Return whether every delegated child is conformant plus a deterministic summary."""

    if not child_states:
        return False, "no delegated child states were available"
    ordered = sorted(child_states.items())
    complete = all(state == "conformant" for _, state in ordered)
    summary = ", ".join(f"{task_id}={state}" for task_id, state in ordered)
    return complete, summary
