from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from bootstrap_inputs import ApprovedBootstrapInputs, BootstrapInputError, load_approved_bootstrap_inputs

PROJECT_ROOT_KEY = "no-safe-circle"
WORK_ID_PREFIX = "NSC"
WORK_ID_MIN_WIDTH = 3

ALLOWED_KINDS = {"feature", "artifact", "implementation"}
ALLOWED_STATUSES = {"open", "complete"}
ALLOWED_EXECUTION_SCOPES = {
    "single_agent",
    "needs_execution_decomposition",
    "human_integration_required",
    "not_applicable",
    "unknown",
}


class WorkGraphTransformError(RuntimeError):
    """Raised when approved seed records cannot be transformed mechanically."""


@dataclass(frozen=True)
class WorkGraphPlan:
    id_map: dict[str, str]
    tasks: tuple[dict[str, Any], ...]
    resource_groups: tuple[dict[str, Any], ...]
    project_requirements: tuple[dict[str, Any], ...]


def require_text(payload: dict[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise WorkGraphTransformError(f"{context}.{field} must be a non-empty string.")
    return value.strip()


def require_list(payload: dict[str, Any], field: str, context: str) -> list[Any]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise WorkGraphTransformError(f"{context}.{field} must be a list.")
    return value


def normalize_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise WorkGraphTransformError(f"{label} must be a list.")
    result: list[str] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, str) or not entry.strip():
            raise WorkGraphTransformError(f"{label}[{index}] must be a non-empty string.")
        result.append(entry.strip())
    return result


def candidate_dependency_keys(candidate_item: dict[str, Any], context: str) -> list[str]:
    raw = candidate_item.get("depends_on", [])
    if not isinstance(raw, list):
        raise WorkGraphTransformError(f"{context}.depends_on must be a list.")

    keys: list[str] = []
    for index, entry in enumerate(raw):
        if isinstance(entry, str):
            key = entry.strip()
        elif isinstance(entry, dict):
            value = entry.get("key")
            key = value.strip() if isinstance(value, str) else ""
        else:
            key = ""
        if not key:
            raise WorkGraphTransformError(
                f"{context}.depends_on[{index}] must be a key string or object containing key."
            )
        keys.append(key)
    return keys


def candidate_resource_keys(candidate_item: dict[str, Any], context: str) -> list[str]:
    raw = candidate_item.get("exclusive_resources", [])
    if not isinstance(raw, list):
        raise WorkGraphTransformError(f"{context}.exclusive_resources must be a list.")

    keys: list[str] = []
    for index, entry in enumerate(raw):
        if isinstance(entry, str):
            key = entry.strip()
        elif isinstance(entry, dict):
            value = entry.get("key")
            key = value.strip() if isinstance(value, str) else ""
        else:
            key = ""
        if not key:
            raise WorkGraphTransformError(
                f"{context}.exclusive_resources[{index}] must be a key string or object containing key."
            )
        keys.append(key)
    return keys


def allocate_stable_ids(seed_records: list[dict[str, Any]]) -> dict[str, str]:
    """Assign deterministic bootstrap IDs, reserving NSC-001 for the project root.

    The approved proposal contains a real `no-safe-circle` feature record. It is the durable
    project-root node, not an out-of-band sentinel. Give that root NSC-001 for readability,
    then preserve the exact approved seed-record order for every remaining record. The proposal
    is SHA-256 bound by human approval, so the allocation is deterministic for this bootstrap.
    The resulting map becomes durable state; future reconciliation reuses reconciliation_key
    traceability rather than reallocating these IDs.
    """

    approved_keys: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(seed_records):
        if not isinstance(record, dict):
            raise WorkGraphTransformError(f"seed_records[{index}] is not an object.")
        key = require_text(record, "reconciliation_key", f"seed_records[{index}]")
        if key in seen:
            raise WorkGraphTransformError(f"Duplicate reconciliation_key in seed records: {key}")
        seen.add(key)
        approved_keys.append(key)

    if PROJECT_ROOT_KEY not in seen:
        raise WorkGraphTransformError(
            f"Approved seed records are missing required project-root feature {PROJECT_ROOT_KEY!r}."
        )

    ordered_keys = [PROJECT_ROOT_KEY] + [key for key in approved_keys if key != PROJECT_ROOT_KEY]
    return {
        key: f"{WORK_ID_PREFIX}-{index:0{WORK_ID_MIN_WIDTH}d}"
        for index, key in enumerate(ordered_keys, start=1)
    }


def index_candidate(candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_items = candidate.get("work_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise WorkGraphTransformError("Approved candidate contains no work_items.")

    by_key: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise WorkGraphTransformError(f"candidate.work_items[{index}] is not an object.")
        key = require_text(item, "key", f"candidate.work_items[{index}]")
        if key in by_key:
            raise WorkGraphTransformError(f"Duplicate candidate work key: {key}")
        by_key[key] = item
    return by_key


def require_match(label: str, seed_value: Any, candidate_value: Any, key: str) -> None:
    if seed_value != candidate_value:
        raise WorkGraphTransformError(
            f"Approved delta/candidate mismatch for {key}.{label}: "
            f"seed={seed_value!r}, candidate={candidate_value!r}"
        )


def transform_task(
    seed: dict[str, Any],
    candidate_item: dict[str, Any],
    id_map: dict[str, str],
    source_run_id: str,
    verification_run_id: str,
) -> dict[str, Any]:
    key = require_text(seed, "reconciliation_key", "seed record")
    context = f"seed record {key!r}"

    title = require_text(seed, "title", context)
    kind = require_text(seed, "kind", context)
    status = require_text(seed, "proposed_status", context)
    execution_scope = require_text(seed, "execution_scope", context)

    if kind not in ALLOWED_KINDS:
        raise WorkGraphTransformError(f"{key} has unsupported kind: {kind!r}")
    if status not in ALLOWED_STATUSES:
        raise WorkGraphTransformError(f"{key} has unsupported status: {status!r}")
    if execution_scope not in ALLOWED_EXECUTION_SCOPES:
        raise WorkGraphTransformError(f"{key} has unsupported execution_scope: {execution_scope!r}")

    parent_key_raw = seed.get("parent_reconciliation_key", "")
    if parent_key_raw is None:
        parent_key = ""
    elif isinstance(parent_key_raw, str):
        parent_key = parent_key_raw.strip()
    else:
        raise WorkGraphTransformError(f"{context}.parent_reconciliation_key must be a string or null.")

    dependency_keys = normalize_string_list(
        seed.get("depends_on_reconciliation_keys", []),
        f"{context}.depends_on_reconciliation_keys",
    )
    resource_keys = normalize_string_list(
        seed.get("exclusive_resource_keys", []),
        f"{context}.exclusive_resource_keys",
    )

    require_match("title", title, candidate_item.get("title"), key)
    require_match("kind", kind, candidate_item.get("kind"), key)
    require_match("status", status, candidate_item.get("graph_status"), key)
    require_match("execution_scope", execution_scope, candidate_item.get("execution_scope"), key)
    require_match("parent", parent_key, str(candidate_item.get("parent_key") or "").strip(), key)

    candidate_dependencies = candidate_dependency_keys(candidate_item, f"candidate {key!r}")
    require_match("dependencies", dependency_keys, candidate_dependencies, key)

    candidate_resources = candidate_resource_keys(candidate_item, f"candidate {key!r}")
    if set(resource_keys) != set(candidate_resources):
        raise WorkGraphTransformError(
            f"Approved delta/candidate mismatch for {key}.exclusive_resources: "
            f"seed={resource_keys!r}, candidate={candidate_resources!r}"
        )

    if key == PROJECT_ROOT_KEY and parent_key:
        raise WorkGraphTransformError(
            f"Project-root feature {PROJECT_ROOT_KEY!r} must not have a parent; got {parent_key!r}."
        )

    if not parent_key:
        parent_id = ""
    else:
        try:
            parent_id = id_map[parent_key]
        except KeyError as exc:
            raise WorkGraphTransformError(
                f"{key} references parent {parent_key!r}, which is not a seeded work record."
            ) from exc

    dependency_ids: list[str] = []
    for dependency_key in dependency_keys:
        if dependency_key == key:
            raise WorkGraphTransformError(f"{key} may not depend on itself.")
        try:
            dependency_ids.append(id_map[dependency_key])
        except KeyError as exc:
            raise WorkGraphTransformError(
                f"{key} depends on {dependency_key!r}, which is not a seeded work record."
            ) from exc

    acceptance_criteria = require_list(seed, "acceptance_criteria", context)
    validation_requirements = require_list(seed, "validation_requirements", context)

    task: dict[str, Any] = {
        "schema_version": "1.0",
        "id": id_map[key],
        "title": title,
        "reconciliation_key": key,
        "kind": kind,
        "type": str(candidate_item.get("type") or kind),
        "status": status,
        "execution_scope": execution_scope,
        "execution_reason": str(candidate_item.get("execution_reason") or ""),
        "decomposition_state": str(candidate_item.get("decomposition_state") or ""),
        "decomposition_reason": str(candidate_item.get("decomposition_reason") or ""),
        "parent": parent_id,
        "depends_on": dependency_ids,
        "exclusive_resources": resource_keys,
        "acceptance_criteria": deepcopy(acceptance_criteria),
        "validation_requirements": deepcopy(validation_requirements),
        "gdd_evidence": deepcopy(candidate_item.get("gdd_evidence", [])),
        "basis": candidate_item.get("basis", ""),
        "source_scope": candidate_item.get("source_scope", ""),
        "confidence": candidate_item.get("confidence", ""),
        "notes": candidate_item.get("notes", ""),
        "repository_state_at_bootstrap": candidate_item.get("repository_state", ""),
        "repository_evidence_at_bootstrap": deepcopy(candidate_item.get("repository_evidence", [])),
        "bootstrap_source": {
            "reconciliation_run_id": source_run_id,
            "verification_run_id": verification_run_id,
        },
    }

    # Preserve optional operational fields if a future verified candidate starts emitting them.
    for field in (
        "artifact_path",
        "scope",
        "out_of_scope",
        "priority",
        "risk",
        "estimated_effort",
        "claims",
    ):
        if field in candidate_item:
            task[field] = deepcopy(candidate_item[field])
        elif field in seed:
            task[field] = deepcopy(seed[field])

    return task


def transform_resource_groups(
    groups: list[dict[str, Any]],
    id_map: dict[str, str],
    tasks_by_key: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    transformed: list[dict[str, Any]] = []
    seen_resources: set[str] = set()

    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise WorkGraphTransformError(f"exclusive_resource_groups[{index}] is not an object.")
        resource_key = require_text(group, "resource_key", f"exclusive_resource_groups[{index}]")
        if resource_key in seen_resources:
            raise WorkGraphTransformError(f"Duplicate exclusive resource group: {resource_key}")
        seen_resources.add(resource_key)

        work_keys = normalize_string_list(
            group.get("work_keys", []),
            f"exclusive_resource_groups[{index}].work_keys",
        )
        task_ids: list[str] = []
        for work_key in work_keys:
            if work_key not in id_map:
                raise WorkGraphTransformError(
                    f"Resource group {resource_key!r} references unseeded work key {work_key!r}."
                )
            task = tasks_by_key[work_key]
            if resource_key not in task["exclusive_resources"]:
                raise WorkGraphTransformError(
                    f"Resource group {resource_key!r} claims {work_key!r}, but that task does not claim the resource."
                )
            task_ids.append(id_map[work_key])

        transformed.append(
            {
                "resource_key": resource_key,
                "work_ids": task_ids,
                "reconciliation_keys": work_keys,
            }
        )

    return tuple(transformed)


def build_work_graph_plan(inputs: ApprovedBootstrapInputs) -> WorkGraphPlan:
    seed_records = inputs.seed_records
    id_map = allocate_stable_ids(seed_records)
    candidate_by_key = index_candidate(inputs.candidate)

    tasks: list[dict[str, Any]] = []
    tasks_by_key: dict[str, dict[str, Any]] = {}
    for seed in seed_records:
        key = require_text(seed, "reconciliation_key", "seed record")
        candidate_item = candidate_by_key.get(key)
        if candidate_item is None:
            raise WorkGraphTransformError(
                f"Approved seed key {key!r} is absent from the approved candidate."
            )
        task = transform_task(
            seed,
            candidate_item,
            id_map,
            inputs.source_reconciliation_run_id,
            inputs.verification_run_id,
        )
        tasks.append(task)
        tasks_by_key[key] = task

    resource_groups = transform_resource_groups(
        inputs.exclusive_resource_groups,
        id_map,
        tasks_by_key,
    )

    return WorkGraphPlan(
        id_map=id_map,
        tasks=tuple(tasks),
        resource_groups=resource_groups,
        project_requirements=tuple(deepcopy(inputs.proposed_non_code_records)),
    )


def print_plan_summary(plan: WorkGraphPlan, inputs: ApprovedBootstrapInputs, show_id_map: bool) -> None:
    kinds = Counter(task["kind"] for task in plan.tasks)
    statuses = Counter(task["status"] for task in plan.tasks)
    scopes = Counter(task["execution_scope"] for task in plan.tasks)
    dependency_edges = sum(len(task["depends_on"]) for task in plan.tasks)
    root_items = sum(1 for task in plan.tasks if not task["parent"])

    print("Work graph seed transform: PASS")
    print(f"Reconciliation run:   {inputs.source_reconciliation_run_id}")
    print(f"Verification run:     {inputs.verification_run_id}")
    print(f"Task records:         {len(plan.tasks)}")
    print(
        "Kinds:                "
        + ", ".join(f"{name}={kinds.get(name, 0)}" for name in ("feature", "artifact", "implementation"))
    )
    print(
        "Statuses:             "
        + ", ".join(f"{name}={statuses.get(name, 0)}" for name in ("open", "complete"))
    )
    print(
        "Execution scopes:     "
        + ", ".join(f"{name}={count}" for name, count in sorted(scopes.items()))
    )
    print(f"Dependency edges:     {dependency_edges}")
    print(f"Top-level task nodes: {root_items}")
    print(f"Resource groups:      {len(plan.resource_groups)}")
    print(f"Project requirements: {len(plan.project_requirements)}")
    print("ID allocation:        project root NSC-001; remaining approved seed-record order")

    if show_id_map:
        print("\nStable bootstrap ID map:")
        for key, work_id in plan.id_map.items():
            print(f"  {work_id}  {key}")

    print("\nNo Tasks/ files were written.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Transform the exact approved bootstrap proposal into deterministic in-memory task records. "
            "This command does not write Tasks/*.yaml."
        )
    )
    parser.add_argument(
        "--show-id-map",
        action="store_true",
        help="Print the complete reconciliation_key -> NSC-* allocation.",
    )
    args = parser.parse_args()

    try:
        inputs = load_approved_bootstrap_inputs()
        plan = build_work_graph_plan(inputs)
    except (BootstrapInputError, WorkGraphTransformError) as exc:
        print(f"Work graph seed transform: FAIL\n{exc}")
        return 1

    print_plan_summary(plan, inputs, args.show_id_map)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
