from __future__ import annotations

import builtins
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent
for path in (str(HERE), str(PIPELINE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from TaskDecomposition.contracts import DecompositionResult
from TaskDecomposition.policy import semantic_json_sha256 as contract_hash
from TaskDecomposition.policy import validate_decomposition_result
from TaskDecomposition.tests.decomposition_contracts_smoke_test import decomposed_result
from graph_delta import GraphDeltaPlanningError, plan_graph_delta
from work_graph_transform import WorkGraphPlan
from work_graph_validate import validate_work_graph_plan


def entry_set(prefix: str) -> tuple[list[dict], list[dict], list[dict]]:
    return (
        [{"criterion_id": "AC-001", "reference": "Synthetic", "requirement": f"{prefix} acceptance."}],
        [{"gate_id": "VAL-001", "reference": "Synthetic", "requirement": f"{prefix} validation."}],
        [{"obligation_id": "INT-001", "reference": "Synthetic", "requirement": f"{prefix} integration."}],
    )


def task(
    task_id: str,
    key: str,
    kind: str,
    parent: str,
    scope: str,
    decomposition: str,
    *,
    dependencies=(),
    resources=(),
    disposition="active",
) -> dict:
    ac, gates, obligations = entry_set(key)
    return {
        "schema_version": "2.0",
        "id": task_id,
        "contract_revision": 3 if task_id == "NSC-042" else 1,
        "contract_disposition": disposition,
        "title": key.replace("-", " ").title(),
        "reconciliation_key": key,
        "kind": kind,
        "type": "synthetic",
        "execution_scope": scope,
        "execution_reason": "Synthetic execution scope.",
        "decomposition_state": decomposition,
        "decomposition_reason": "Synthetic decomposition scope.",
        "parent": parent,
        "depends_on": list(dependencies),
        "exclusive_resources": list(resources),
        "acceptance_criteria": ac,
        "completion_gates": gates,
        "downstream_integration_obligations": obligations,
        "gdd_evidence": [],
        "basis": "direct_gdd",
        "source_scope": "required",
        "confidence": "high",
        "notes": "",
        "repository_state_at_bootstrap": "missing",
        "repository_evidence_at_bootstrap": [],
        "provenance": {"origin": "synthetic_original", "source": key},
    }


def make_plan() -> WorkGraphPlan:
    tasks = (
        task("NSC-001", "no-safe-circle", "feature", "", "not_applicable", "coarse"),
        task("NSC-010", "existing-runtime", "implementation", "NSC-001", "single_agent", "concrete", resources=("logical:shared",)),
        task("NSC-020", "inactive-history", "implementation", "NSC-001", "single_agent", "concrete", disposition="cancelled"),
        task(
            "NSC-042", "synthetic-parent", "implementation", "NSC-001",
            "needs_execution_decomposition", "concrete",
            dependencies=("NSC-010",), resources=("logical:shared",),
        ),
    )
    return WorkGraphPlan(
        id_map={task["reconciliation_key"]: task["id"] for task in tasks},
        tasks=tasks,
        resource_groups=(
            {
                "resource_key": "logical:shared",
                "work_ids": ["NSC-010", "NSC-042"],
                "reconciliation_keys": ["existing-runtime", "synthetic-parent"],
            },
        ),
        project_requirements=(
            {"title": "Human review", "requirement_type": "pipeline_constraint", "status": "confirmed"},
        ),
    )


def validated_result(plan: WorkGraphPlan, *, invalid_dependency: bool = False):
    parent = next(task for task in plan.tasks if task["id"] == "NSC-042")
    raw = decomposed_result(parent)
    raw["children"][0]["existing_task_dependencies"] = [
        "NSC-020" if invalid_dependency else "NSC-010"
    ]
    raw["children"][0]["exclusive_resources"] = ["logical:shared", "logical:new-shared"]
    raw["children"][1]["exclusive_resources"] = ["logical:new-shared"]
    return validate_decomposition_result(
        raw,
        parent_task=parent,
        existing_reconciliation_keys=plan.id_map,
    )


def expect_failure(callable_, fragment: str) -> None:
    try:
        callable_()
    except GraphDeltaPlanningError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(f"Expected GraphDeltaPlanningError containing {fragment!r}")


def replace_parent(plan: WorkGraphPlan, mutate) -> WorkGraphPlan:
    tasks = list(deepcopy(plan.tasks))
    parent = next(task for task in tasks if task["id"] == "NSC-042")
    mutate(parent)
    return WorkGraphPlan(deepcopy(plan.id_map), tuple(tasks), deepcopy(plan.resource_groups), deepcopy(plan.project_requirements))


def main() -> int:
    source = make_plan()
    validate_work_graph_plan(source)
    result = validated_result(source)
    selector = result.parent_task
    source_before = json.dumps(
        {
            "id_map": source.id_map,
            "tasks": source.tasks,
            "resource_groups": source.resource_groups,
            "requirements": source.project_requirements,
        },
        sort_keys=True,
    )

    delta = plan_graph_delta(source, selector, result)
    payload = delta.to_dict()
    assert payload["graph_delta_schema_version"] == "1.0"
    assert payload["authority"] == "review_only_not_applied"
    assert payload["allocated_local_key_to_task_id"] == {
        "runtime-core": "NSC-043",
        "runtime-integration": "NSC-044",
    }
    assert payload["id_map_additions"] == payload["allocated_local_key_to_task_id"]
    children = payload["proposed_child_contracts"]
    assert [child["id"] for child in children] == ["NSC-043", "NSC-044"]
    assert children[0]["depends_on"] == ["NSC-010"]
    assert children[1]["depends_on"] == ["NSC-043"]
    assert all(child["contract_revision"] == 1 for child in children)
    assert all(child["contract_disposition"] == "active" for child in children)
    assert all(child["repository_state_at_bootstrap"] == "not_applicable" for child in children)
    assert all(child["repository_evidence_at_bootstrap"] == [] for child in children)
    assert all("bootstrap_status_observation" not in child["provenance"] for child in children)
    assert all(child["provenance"]["origin"] == "progressive_decomposition" for child in children)
    assert all(child["provenance"]["graph_delta_plan_id"] == delta.plan_id for child in children)
    assert all(child["provenance"]["parent_task_id"] == "NSC-042" for child in children)
    assert all(child["provenance"]["parent_contract_revision"] == 3 for child in children)
    assert all(child["provenance"]["parent_contract_sha256"] == selector.contract_sha256 for child in children)

    overlay = payload["proposed_graph_overlay"]
    proposed_parent = next(task for task in overlay["tasks"] if task["id"] == "NSC-042")
    original_parent = next(task for task in source.tasks if task["id"] == "NSC-042")
    assert proposed_parent["contract_revision"] == 4
    assert proposed_parent["execution_scope"] == "not_applicable"
    assert proposed_parent["decomposition_state"] == "decomposed"
    assert proposed_parent["execution_reason"].startswith(
        "Execution responsibilities are delegated to child contracts:"
    )
    assert proposed_parent["decomposition_reason"].startswith(
        "Decomposed into reviewed child contracts:"
    )
    assert "Proposed" not in proposed_parent["execution_reason"]
    assert "Proposed" not in proposed_parent["decomposition_reason"]
    for field in (
        "id", "reconciliation_key", "kind", "type", "parent", "depends_on",
        "exclusive_resources", "acceptance_criteria", "completion_gates",
        "downstream_integration_obligations", "gdd_evidence", "provenance",
    ):
        assert proposed_parent[field] == original_parent[field], field
    assert "does not claim implementation completion" in proposed_parent["decomposition_reason"]
    assert payload["parent_before_hash"] == contract_hash(original_parent)
    assert payload["parent_after_hash"] == contract_hash(proposed_parent)

    changes = {change["resource_key"]: change for change in payload["resource_group_changes"]}
    assert changes["logical:shared"]["change_type"] == "extended"
    assert changes["logical:shared"]["after"]["work_ids"] == ["NSC-010", "NSC-042", "NSC-043"]
    assert changes["logical:new-shared"]["change_type"] == "created"
    assert changes["logical:new-shared"]["after"]["work_ids"] == ["NSC-043", "NSC-044"]
    validation = payload["proposed_graph_validation"]
    assert validation["result"] == "valid"
    assert validation["task_count"] == 6
    validate_work_graph_plan(
        WorkGraphPlan(
            overlay["id_map"], tuple(overlay["tasks"]),
            tuple(overlay["resource_groups"]), tuple(overlay["project_requirements"]),
        )
    )

    assert json.dumps(
        {
            "id_map": source.id_map,
            "tasks": source.tasks,
            "resource_groups": source.resource_groups,
            "requirements": source.project_requirements,
        },
        sort_keys=True,
    ) == source_before
    repeat = plan_graph_delta(source, selector, result)
    assert repeat.plan_id == delta.plan_id
    assert repeat.canonical_json() == delta.canonical_json()
    detached = delta.to_dict()
    detached["proposed_child_contracts"][0]["title"] = "mutated"
    assert delta.to_dict()["proposed_child_contracts"][0]["title"] != "mutated"

    with patch.object(builtins, "open", side_effect=AssertionError("planner attempted filesystem write/read")):
        assert plan_graph_delta(source, selector, result).plan_id == delta.plan_id

    duck_typed_result = SimpleNamespace(
        decision=result.decision,
        parent_task=result.parent_task,
        children=result.children,
        to_dict=result.to_dict,
    )
    expect_failure(
        lambda: plan_graph_delta(source, selector, duck_typed_result),
        "exact DecompositionResult",
    )

    parent = next(task for task in source.tasks if task["id"] == "NSC-042")
    incomplete_raw = decomposed_result(parent)
    incomplete_raw["parent_requirement_coverage"].pop()
    incomplete_result = DecompositionResult.from_dict(incomplete_raw)
    expect_failure(
        lambda: plan_graph_delta(source, incomplete_result.parent_task, incomplete_result),
        "missing parent requirement coverage",
    )

    parent_dependency_raw = decomposed_result(parent)
    parent_dependency_raw["children"][0]["existing_task_dependencies"] = ["NSC-042"]
    parent_dependency_result = DecompositionResult.from_dict(parent_dependency_raw)
    expect_failure(
        lambda: plan_graph_delta(
            source,
            parent_dependency_result.parent_task,
            parent_dependency_result,
        ),
        "may not depend on selected aggregate parent",
    )

    cyclic_raw = decomposed_result(parent)
    cyclic_raw["children"][0]["local_dependencies"] = ["runtime-integration"]
    cyclic_raw["children"][1]["local_dependencies"] = ["runtime-core"]
    cyclic_result = validate_decomposition_result(
        cyclic_raw,
        parent_task=parent,
        existing_reconciliation_keys=source.id_map,
    )
    expect_failure(lambda: plan_graph_delta(source, cyclic_result.parent_task, cyclic_result), "cycle")

    collision_plan = deepcopy(source)
    collision_plan.id_map["runtime-core"] = collision_plan.id_map.pop("existing-runtime")
    collision_tasks = list(collision_plan.tasks)
    collision_tasks[1]["reconciliation_key"] = "runtime-core"
    collision_plan = WorkGraphPlan(collision_plan.id_map, tuple(collision_tasks), collision_plan.resource_groups, collision_plan.project_requirements)
    collision_groups = list(deepcopy(collision_plan.resource_groups))
    collision_groups[0]["reconciliation_keys"][0] = "runtime-core"
    collision_plan = WorkGraphPlan(collision_plan.id_map, collision_plan.tasks, tuple(collision_groups), collision_plan.project_requirements)
    validate_work_graph_plan(collision_plan)
    expect_failure(lambda: plan_graph_delta(collision_plan, selector, result), "collide")

    bad_selector = selector.to_dict()
    bad_selector["contract_revision"] += 1
    expect_failure(lambda: plan_graph_delta(source, bad_selector, result), "identity differ")
    revised_source = replace_parent(source, lambda parent: parent.__setitem__("contract_revision", 4))
    expect_failure(lambda: plan_graph_delta(revised_source, selector, result), "revision changed")
    changed_source = replace_parent(source, lambda parent: parent.__setitem__("title", "Changed title"))
    expect_failure(lambda: plan_graph_delta(changed_source, selector, result), "SHA-256 changed")

    inactive_source = replace_parent(source, lambda parent: parent.__setitem__("contract_disposition", "cancelled"))
    inactive_parent = next(task for task in inactive_source.tasks if task["id"] == "NSC-042")
    inactive_raw = decomposed_result(inactive_parent)
    inactive_result = validate_decomposition_result(inactive_raw, parent_task=inactive_parent, existing_reconciliation_keys=inactive_source.id_map)
    expect_failure(lambda: plan_graph_delta(inactive_source, inactive_result.parent_task, inactive_result), "not active")

    invalid_result = validated_result(source, invalid_dependency=True)
    expect_failure(
        lambda: plan_graph_delta(source, invalid_result.parent_task, invalid_result),
        "proposed graph overlay is invalid",
    )
    assert json.dumps(
        {"id_map": source.id_map, "tasks": source.tasks, "resource_groups": source.resource_groups},
        sort_keys=True,
    ) == json.dumps(
        {"id_map": make_plan().id_map, "tasks": make_plan().tasks, "resource_groups": make_plan().resource_groups},
        sort_keys=True,
    )

    print("graph_delta_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
