"""Pure deterministic Stage D1A incremental graph-delta planning."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from TaskDecomposition.contracts import (
    DecompositionContractError,
    DecompositionResult,
    ParentTaskIdentity,
)
from TaskDecomposition.policy import DecompositionPolicyError, validate_decomposition_result
from decomposition_graph_semantics import validate_decomposition_graph_semantics
from persistent_work_graph import PersistentWorkGraph
from work_graph_transform import WorkGraphPlan
from work_graph_validate import WorkGraphValidationError, validate_work_graph_plan

GRAPH_DELTA_SCHEMA_VERSION = "1.1"
NSC_ID_RE = re.compile(r"^NSC-(\d{3,})$")


class GraphDeltaPlanningError(RuntimeError):
    """Raised when a proposed decomposition cannot form a valid graph overlay."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise GraphDeltaPlanningError(f"Graph-delta data is not canonical JSON: {exc}") from exc


def semantic_json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _plan_payload(plan: WorkGraphPlan) -> dict[str, Any]:
    return {
        "id_map": deepcopy(plan.id_map),
        "tasks": deepcopy(list(plan.tasks)),
        "resource_groups": deepcopy(list(plan.resource_groups)),
        "project_requirements": deepcopy(list(plan.project_requirements)),
    }


def _identity_dict(identity: Any, label: str) -> dict[str, Any]:
    if type(identity) is ParentTaskIdentity:
        raw = ParentTaskIdentity.to_dict(identity)
    elif type(identity) is dict:
        raw = identity
    else:
        raise GraphDeltaPlanningError(
            f"{label} must be an exact ParentTaskIdentity or built-in object."
        )
    if type(raw) is not dict or set(raw) != {"task_id", "contract_revision", "contract_sha256"}:
        raise GraphDeltaPlanningError(f"{label} must contain exact task_id/revision/hash identity.")
    task_id = raw["task_id"]
    revision = raw["contract_revision"]
    contract_hash = raw["contract_sha256"]
    if type(task_id) is not str or not NSC_ID_RE.fullmatch(task_id):
        raise GraphDeltaPlanningError(f"{label}.task_id is invalid.")
    if type(revision) is not int or revision < 1:
        raise GraphDeltaPlanningError(f"{label}.contract_revision must be a positive integer.")
    if type(contract_hash) is not str or not re.fullmatch(r"[0-9a-f]{64}", contract_hash):
        raise GraphDeltaPlanningError(f"{label}.contract_sha256 must be lowercase SHA-256.")
    return deepcopy(raw)


@dataclass(frozen=True)
class GraphDeltaPlan:
    """Immutable review snapshot; every accessor returns detached JSON data."""

    _serialized: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "GraphDeltaPlan":
        return cls(_canonical_json(payload))

    @property
    def plan_id(self) -> str:
        return self.to_dict()["plan_id"]

    @property
    def source_graph_semantic_hash(self) -> str:
        return self.to_dict()["source_graph_semantic_hash"]

    @property
    def allocated_local_key_to_task_id(self) -> dict[str, str]:
        return self.to_dict()["allocated_local_key_to_task_id"]

    @property
    def proposed_child_contracts(self) -> list[dict[str, Any]]:
        return self.to_dict()["proposed_child_contracts"]

    @property
    def proposed_graph_overlay(self) -> dict[str, Any]:
        return self.to_dict()["proposed_graph_overlay"]

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._serialized)

    def canonical_json(self) -> str:
        return self._serialized


def _detect_local_cycles(children: tuple[Any, ...], local_keys: set[str]) -> None:
    edges: dict[str, tuple[str, ...]] = {}
    for child in children:
        if child.local_key in child.local_dependencies:
            raise GraphDeltaPlanningError(f"Child {child.local_key!r} may not depend on itself.")
        missing = set(child.local_dependencies) - local_keys
        if missing:
            raise GraphDeltaPlanningError(
                f"Child {child.local_key!r} references missing local dependencies: {sorted(missing)}."
            )
        edges[child.local_key] = child.local_dependencies

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(key: str) -> None:
        if key in visited:
            return
        if key in visiting:
            start = stack.index(key)
            raise GraphDeltaPlanningError(
                "Local child dependency graph contains a cycle: "
                + " -> ".join(stack[start:] + [key])
            )
        visiting.add(key)
        stack.append(key)
        for dependency in edges[key]:
            visit(dependency)
        stack.pop()
        visiting.remove(key)
        visited.add(key)

    for key in edges:
        visit(key)


def _entry_dicts(entries: tuple[Any, ...], entry_type: str) -> list[dict[str, str]]:
    return [entry.to_dict(entry_type) for entry in entries]


def _child_contract(
    child: Any,
    task_id: str,
    parent: dict[str, Any],
    parent_hash: str,
    plan_id: str,
    allocation: dict[str, str],
    existing_ids: set[str],
) -> dict[str, Any]:
    missing_existing = set(child.existing_task_dependencies) - existing_ids
    if missing_existing:
        raise GraphDeltaPlanningError(
            f"Child {child.local_key!r} references missing existing dependencies: {sorted(missing_existing)}."
        )
    dependencies = list(child.existing_task_dependencies) + [
        allocation[key] for key in child.local_dependencies
    ]
    if task_id in dependencies:
        raise GraphDeltaPlanningError(f"Child {child.local_key!r} resolves to a self-dependency.")
    if len(dependencies) != len(set(dependencies)):
        raise GraphDeltaPlanningError(f"Child {child.local_key!r} resolves duplicate dependencies.")
    return {
        "schema_version": "2.0",
        "id": task_id,
        "contract_revision": 1,
        "contract_disposition": "active",
        "title": child.title,
        "reconciliation_key": child.local_key,
        "kind": "implementation",
        "type": child.type,
        "execution_scope": "single_agent",
        "execution_reason": child.execution_reason,
        "decomposition_state": "concrete",
        "decomposition_reason": child.decomposition_reason,
        "parent": parent["id"],
        "depends_on": dependencies,
        "exclusive_resources": list(child.exclusive_resources),
        "acceptance_criteria": _entry_dicts(child.acceptance_criteria, "acceptance_criteria"),
        "completion_gates": _entry_dicts(child.completion_gates, "completion_gates"),
        "downstream_integration_obligations": _entry_dicts(
            child.downstream_integration_obligations, "downstream_integration_obligations"
        ),
        "gdd_evidence": [entry.to_dict() for entry in child.gdd_evidence],
        "basis": child.basis,
        "source_scope": child.source_scope,
        "confidence": child.confidence,
        "notes": child.notes,
        "repository_state_at_bootstrap": "not_applicable",
        "repository_evidence_at_bootstrap": [],
        "provenance": {
            "origin": "progressive_decomposition",
            "parent_task_id": parent["id"],
            "parent_contract_revision": parent["contract_revision"],
            "parent_contract_sha256": parent_hash,
            "graph_delta_plan_id": plan_id,
        },
    }


def _update_resource_groups(
    source_groups: tuple[dict[str, Any], ...],
    tasks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    owners: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        for resource in task["exclusive_resources"]:
            owners.setdefault(resource, []).append(task)

    result: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    existing_resources: set[str] = set()
    for source in source_groups:
        before = deepcopy(source)
        resource = source["resource_key"]
        existing_resources.add(resource)
        owner_by_id = {task["id"]: task for task in owners.get(resource, [])}
        ordered_ids = [task_id for task_id in source["work_ids"] if task_id in owner_by_id]
        ordered_ids.extend(task["id"] for task in owners.get(resource, []) if task["id"] not in ordered_ids)
        after = {
            "resource_key": resource,
            "work_ids": ordered_ids,
            "reconciliation_keys": [owner_by_id[task_id]["reconciliation_key"] for task_id in ordered_ids],
        }
        result.append(after)
        if before != after:
            changes.append({"change_type": "updated", "resource_key": resource, "before": before, "after": deepcopy(after)})

    for resource in sorted(set(owners) - existing_resources):
        if len(owners[resource]) <= 1:
            continue
        after = {
            "resource_key": resource,
            "work_ids": [task["id"] for task in owners[resource]],
            "reconciliation_keys": [task["reconciliation_key"] for task in owners[resource]],
        }
        result.append(after)
        changes.append({"change_type": "created", "resource_key": resource, "before": None, "after": deepcopy(after)})
    return result, changes


def _validation_dict(summary: Any) -> dict[str, Any]:
    return {
        "task_count": summary.task_count,
        "parent_edge_count": summary.parent_edge_count,
        "dependency_edge_count": summary.dependency_edge_count,
        "root_id": summary.root_id,
        "root_key": summary.root_key,
        "resource_group_count": summary.resource_group_count,
        "project_requirement_count": summary.project_requirement_count,
        "task_schema_version": summary.task_schema_version,
        "decomposition_aggregate_semantics": "valid",
        "result": "valid",
    }


def _active_inbound_dependents(
    tasks: tuple[dict[str, Any], ...], parent_id: str
) -> dict[str, dict[str, Any]]:
    return {
        task["id"]: task
        for task in tasks
        if task.get("contract_disposition") == "active"
        and parent_id in task.get("depends_on", [])
    }


def _validate_inbound_rewrite_coverage(
    active_dependents: dict[str, dict[str, Any]], result: DecompositionResult
) -> dict[str, Any]:
    rewrites = {
        rewrite.dependent_task_id: rewrite
        for rewrite in result.inbound_dependency_rewrites
    }
    expected = set(active_dependents)
    actual = set(rewrites)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise GraphDeltaPlanningError(
            "Inbound dependency rewrites must exactly cover active direct dependents of the "
            f"selected parent (missing={missing}, extra={extra})."
        )
    return rewrites


def _rewrite_dependent(
    dependent: dict[str, Any],
    *,
    parent_id: str,
    replacement_ids: list[str],
    reason: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before_dependencies = list(dependent["depends_on"])
    after_dependencies: list[str] = []
    for dependency in before_dependencies:
        if dependency == parent_id:
            after_dependencies.extend(replacement_ids)
        else:
            after_dependencies.append(dependency)
    if parent_id in after_dependencies:
        raise GraphDeltaPlanningError(
            f"Dependent {dependent['id']} retained aggregate dependency {parent_id}."
        )
    if len(after_dependencies) != len(set(after_dependencies)):
        raise GraphDeltaPlanningError(
            f"Inbound rewrite for {dependent['id']} resolves duplicate dependencies."
        )
    revised = deepcopy(dependent)
    revised["contract_revision"] = dependent["contract_revision"] + 1
    revised["depends_on"] = after_dependencies
    change = {
        "dependent_task_id": dependent["id"],
        "before_contract_revision": dependent["contract_revision"],
        "after_contract_revision": revised["contract_revision"],
        "before_dependencies": before_dependencies,
        "after_dependencies": deepcopy(after_dependencies),
        "reason": reason,
    }
    return revised, change


def plan_graph_delta(source_graph: Any, parent_selector: Any, decomposition_result: Any) -> GraphDeltaPlan:
    """Build and validate a complete proposed graph overlay without writing files."""

    if type(source_graph) is WorkGraphPlan:
        source = source_graph
    elif type(source_graph) is PersistentWorkGraph:
        source = source_graph.plan
    else:
        raise GraphDeltaPlanningError("source_graph must be a validated WorkGraphPlan or PersistentWorkGraph.")
    try:
        validate_work_graph_plan(source)
        validate_decomposition_graph_semantics(source)
    except WorkGraphValidationError as exc:
        raise GraphDeltaPlanningError(f"Source work graph is invalid: {exc}") from exc

    selector = _identity_dict(parent_selector, "parent_selector")
    if type(decomposition_result) is not DecompositionResult:
        raise GraphDeltaPlanningError(
            "Graph-delta planning requires an exact DecompositionResult contract snapshot."
        )
    result_identity = _identity_dict(
        decomposition_result.parent_task,
        "decomposition_result.parent_task",
    )
    if selector != result_identity:
        raise GraphDeltaPlanningError("Parent selector and decomposition-result identity differ.")

    source_payload = _plan_payload(source)
    source_hash = semantic_json_sha256(source_payload)
    tasks_by_id = {task["id"]: task for task in source.tasks}
    parent = tasks_by_id.get(selector["task_id"])
    if parent is None:
        raise GraphDeltaPlanningError(f"Selected parent task does not exist: {selector['task_id']}.")
    parent_hash = semantic_json_sha256(parent)
    if parent.get("contract_revision") != selector["contract_revision"]:
        raise GraphDeltaPlanningError("Selected parent contract revision changed.")
    if parent_hash != selector["contract_sha256"]:
        raise GraphDeltaPlanningError("Selected parent semantic contract SHA-256 changed.")
    if parent.get("contract_disposition") != "active":
        raise GraphDeltaPlanningError("Selected parent contract is not active.")
    if not (
        parent.get("execution_scope") == "needs_execution_decomposition"
        and parent.get("decomposition_state") == "concrete"
    ):
        raise GraphDeltaPlanningError(
            "Selected parent is ineligible: D1A requires active concrete work with execution_scope needs_execution_decomposition."
        )

    try:
        result = validate_decomposition_result(
            decomposition_result,
            parent_task=parent,
            existing_reconciliation_keys=source.id_map,
        )
    except (DecompositionContractError, DecompositionPolicyError) as exc:
        raise GraphDeltaPlanningError(f"Decomposition result is invalid: {exc}") from exc
    if result.decision != "decomposed":
        raise GraphDeltaPlanningError("Graph-delta planning accepts only a validated decomposed result.")
    validated_identity = _identity_dict(result.parent_task, "decomposition_result.parent_task")
    if selector != validated_identity:
        raise GraphDeltaPlanningError("Parent selector and decomposition-result identity differ.")

    children = result.children
    local_keys = {child.local_key for child in children}
    if len(local_keys) != len(children):
        raise GraphDeltaPlanningError("Child local keys must be unique.")
    collisions = local_keys.intersection(source.id_map)
    if collisions:
        raise GraphDeltaPlanningError(f"Child local keys collide with existing reconciliation keys: {sorted(collisions)}.")
    _detect_local_cycles(children, local_keys)

    active_dependents = _active_inbound_dependents(source.tasks, parent["id"])
    rewrites = _validate_inbound_rewrite_coverage(active_dependents, result)

    existing_numbers = []
    for task_id in tasks_by_id:
        match = NSC_ID_RE.fullmatch(task_id)
        if match is None:
            raise GraphDeltaPlanningError(f"Existing task ID is not numeric NSC form: {task_id!r}.")
        existing_numbers.append(int(match.group(1)))
    next_number = max(existing_numbers) + 1
    allocation = {
        child.local_key: f"NSC-{next_number + index:03d}"
        for index, child in enumerate(children)
    }

    result_dict = DecompositionResult.to_dict(result)
    identity_basis = {
        "graph_delta_schema_version": GRAPH_DELTA_SCHEMA_VERSION,
        "source_graph_semantic_hash": source_hash,
        "parent_identity": selector,
        "validated_decomposition_result": result_dict,
        "allocated_local_key_to_task_id": allocation,
    }
    plan_id = "GDP-" + semantic_json_sha256(identity_basis)

    proposed_children = [
        _child_contract(
            child, allocation[child.local_key], parent, parent_hash, plan_id,
            allocation, set(tasks_by_id),
        )
        for child in children
    ]
    proposed_parent = deepcopy(parent)
    proposed_parent["contract_revision"] = parent["contract_revision"] + 1
    proposed_parent["kind"] = "feature"
    proposed_parent["execution_scope"] = "not_applicable"
    proposed_parent["decomposition_state"] = "decomposed"
    proposed_parent["decomposition_children"] = [
        allocation[child.local_key] for child in children
    ]
    proposed_parent["exclusive_resources"] = []
    child_identity = ", ".join(
        f"{allocation[child.local_key]} ({child.local_key})" for child in children
    )
    proposed_parent["execution_reason"] = (
        "Non-executable aggregate feature. All implementation responsibilities are delegated "
        f"to child contracts: {child_identity}. No later implementation pass on {parent['id']} exists."
    )
    proposed_parent["decomposition_reason"] = (
        f"Decomposed into reviewed child contracts: {child_identity}. "
        "Aggregate conformance is derived from the complete delegated child set; any required "
        "assembly or integration must be an explicit child contract."
    )

    rewritten_dependents: dict[str, dict[str, Any]] = {}
    inbound_changes: list[dict[str, Any]] = []
    for dependent_id in sorted(rewrites, key=lambda value: int(value.split("-", 1)[1])):
        rewrite = rewrites[dependent_id]
        replacement_ids = [allocation[key] for key in rewrite.replacement_local_keys]
        revised, change = _rewrite_dependent(
            active_dependents[dependent_id],
            parent_id=parent["id"],
            replacement_ids=replacement_ids,
            reason=rewrite.reason,
        )
        rewritten_dependents[dependent_id] = revised
        change["replacement_local_keys"] = list(rewrite.replacement_local_keys)
        change["replacement_task_ids"] = replacement_ids
        inbound_changes.append(change)

    proposed_tasks = []
    for task in source.tasks:
        if task["id"] == parent["id"]:
            proposed_tasks.append(proposed_parent)
        elif task["id"] in rewritten_dependents:
            proposed_tasks.append(rewritten_dependents[task["id"]])
        else:
            proposed_tasks.append(deepcopy(task))
    proposed_tasks.extend(deepcopy(proposed_children))
    proposed_id_map = deepcopy(source.id_map)
    proposed_id_map.update(allocation)
    proposed_groups, resource_changes = _update_resource_groups(source.resource_groups, proposed_tasks)
    proposed_overlay = {
        "id_map": proposed_id_map,
        "tasks": proposed_tasks,
        "resource_groups": proposed_groups,
        "project_requirements": deepcopy(list(source.project_requirements)),
    }
    proposed_plan = WorkGraphPlan(
        id_map=proposed_id_map,
        tasks=tuple(proposed_tasks),
        resource_groups=tuple(proposed_groups),
        project_requirements=tuple(deepcopy(list(source.project_requirements))),
    )
    try:
        validation = validate_work_graph_plan(proposed_plan)
        validate_decomposition_graph_semantics(proposed_plan)
    except WorkGraphValidationError as exc:
        raise GraphDeltaPlanningError(f"Proposed graph overlay is invalid: {exc}") from exc

    parent_after_hash = semantic_json_sha256(proposed_parent)
    payload = {
        "graph_delta_schema_version": GRAPH_DELTA_SCHEMA_VERSION,
        "plan_id": plan_id,
        "authority": "review_only_not_applied",
        "source_graph_semantic_hash": source_hash,
        "parent_before_hash": parent_hash,
        "parent_after_hash": parent_after_hash,
        "parent_before_summary": {
            "task_id": parent["id"],
            "kind": parent["kind"],
            "contract_revision": parent["contract_revision"],
            "contract_disposition": parent["contract_disposition"],
            "execution_scope": parent["execution_scope"],
            "decomposition_state": parent["decomposition_state"],
        },
        "parent_after_summary": {
            "task_id": proposed_parent["id"],
            "kind": proposed_parent["kind"],
            "contract_revision": proposed_parent["contract_revision"],
            "contract_disposition": proposed_parent["contract_disposition"],
            "execution_scope": proposed_parent["execution_scope"],
            "decomposition_state": proposed_parent["decomposition_state"],
            "decomposition_children": deepcopy(proposed_parent["decomposition_children"]),
        },
        "allocated_local_key_to_task_id": deepcopy(allocation),
        "id_map_additions": deepcopy(allocation),
        "proposed_child_contracts": deepcopy(proposed_children),
        "inbound_dependency_changes": inbound_changes,
        "resource_group_changes": resource_changes,
        "proposed_graph_semantic_hash": semantic_json_sha256(proposed_overlay),
        "proposed_graph_validation": _validation_dict(validation),
        "proposed_graph_overlay": proposed_overlay,
    }
    return GraphDeltaPlan.from_payload(payload)
