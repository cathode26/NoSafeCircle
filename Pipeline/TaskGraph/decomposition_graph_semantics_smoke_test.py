from __future__ import annotations

from copy import deepcopy

from decomposition_graph_semantics import (
    DecompositionGraphSemanticsError,
    aggregate_child_state_summary,
    validate_decomposition_graph_semantics,
)
from work_graph_transform import WorkGraphPlan


def task(task_id: str, key: str, *, parent: str, kind: str = "implementation", depends_on=()) -> dict:
    return {
        "schema_version": "2.0",
        "id": task_id,
        "contract_revision": 1,
        "contract_disposition": "active",
        "title": key,
        "reconciliation_key": key,
        "kind": kind,
        "type": "synthetic",
        "execution_scope": "not_applicable" if kind == "feature" else "single_agent",
        "execution_reason": "synthetic",
        "decomposition_state": "coarse" if kind == "feature" else "concrete",
        "decomposition_reason": "synthetic",
        "parent": parent,
        "depends_on": list(depends_on),
        "exclusive_resources": [],
        "acceptance_criteria": [{"criterion_id": "AC-001", "reference": "synthetic", "requirement": "synthetic"}],
        "completion_gates": [{"gate_id": "VAL-001", "reference": "synthetic", "requirement": "synthetic"}],
        "downstream_integration_obligations": [],
        "gdd_evidence": [],
        "basis": "direct_gdd",
        "source_scope": "required",
        "confidence": "high",
        "notes": "",
        "repository_state_at_bootstrap": "not_applicable",
        "repository_evidence_at_bootstrap": [],
        "provenance": {"origin": "synthetic"},
    }


def strict_plan() -> WorkGraphPlan:
    root = task("NSC-001", "root", parent="", kind="feature")
    parent = task("NSC-010", "aggregate", parent="NSC-001", kind="feature")
    parent["decomposition_state"] = "decomposed"
    parent["decomposition_children"] = ["NSC-020"]
    child = task("NSC-020", "child", parent="NSC-010")
    dependent = task("NSC-030", "dependent", parent="NSC-001", depends_on=("NSC-020",))
    tasks = (root, parent, child, dependent)
    return WorkGraphPlan(
        {item["reconciliation_key"]: item["id"] for item in tasks},
        tasks,
        (),
        ({"title": "review", "requirement_type": "pipeline_constraint", "status": "confirmed"},),
    )


def expect_failure(plan: WorkGraphPlan, fragment: str) -> None:
    try:
        validate_decomposition_graph_semantics(plan)
    except DecompositionGraphSemanticsError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(f"Expected decomposition semantics failure containing {fragment!r}")


def with_tasks(plan: WorkGraphPlan, tasks: list[dict]) -> WorkGraphPlan:
    return WorkGraphPlan(
        {item["reconciliation_key"]: item["id"] for item in tasks},
        tuple(tasks),
        plan.resource_groups,
        plan.project_requirements,
    )


def main() -> int:
    plan = strict_plan()
    validate_decomposition_graph_semantics(plan)

    # Legacy reviewed decompositions without decomposition_children remain readable.
    legacy_tasks = list(deepcopy(plan.tasks))
    legacy_tasks[1].pop("decomposition_children")
    validate_decomposition_graph_semantics(with_tasks(plan, legacy_tasks))

    bad = list(deepcopy(plan.tasks))
    bad[1]["kind"] = "implementation"
    expect_failure(with_tasks(plan, bad), "kind='feature'")

    bad = list(deepcopy(plan.tasks))
    bad[1]["exclusive_resources"] = ["logical:aggregate-lock"]
    expect_failure(with_tasks(plan, bad), "resource")

    bad = list(deepcopy(plan.tasks))
    bad[1]["decomposition_children"] = ["NSC-999"]
    expect_failure(with_tasks(plan, bad), "missing child")

    bad = list(deepcopy(plan.tasks))
    bad[2]["parent"] = "NSC-001"
    expect_failure(with_tasks(plan, bad), "direct child")

    bad = list(deepcopy(plan.tasks))
    bad[3]["depends_on"] = ["NSC-010"]
    expect_failure(with_tasks(plan, bad), "may not depend on decomposed aggregate")

    bad = list(deepcopy(plan.tasks))
    bad.append(task("NSC-021", "second-child", parent="NSC-010"))
    expect_failure(with_tasks(plan, bad), "exactly name all active direct children")

    complete, summary = aggregate_child_state_summary(
        {"NSC-050": "conformant", "NSC-051": "conformant", "NSC-052": "conformant"}
    )
    assert complete
    assert summary == "NSC-050=conformant, NSC-051=conformant, NSC-052=conformant"
    complete, summary = aggregate_child_state_summary(
        {"NSC-050": "conformant", "NSC-051": "needs_testing"}
    )
    assert not complete
    assert "NSC-051=needs_testing" in summary
    complete, summary = aggregate_child_state_summary({})
    assert not complete
    assert "no delegated child states" in summary

    print("decomposition_graph_semantics_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
