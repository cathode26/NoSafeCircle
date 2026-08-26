from __future__ import annotations

from copy import deepcopy

from decomposition_graph_semantics import (
    DecompositionGraphSemanticsError,
    aggregate_child_state_summary,
    validate_decomposition_graph_semantics,
)
from work_graph_transform import WorkGraphPlan
from work_graph_validate_smoke_test import make_plan


def expect_failure(plan: WorkGraphPlan, fragment: str) -> None:
    try:
        validate_decomposition_graph_semantics(plan)
    except DecompositionGraphSemanticsError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(f"Expected decomposition semantics failure containing {fragment!r}")


def strict_plan() -> WorkGraphPlan:
    base = make_plan()
    tasks = list(deepcopy(base.tasks))
    parent = tasks[1]
    parent["kind"] = "feature"
    parent["execution_scope"] = "not_applicable"
    parent["decomposition_state"] = "decomposed"
    parent["decomposition_children"] = ["NSC-020"]
    parent["exclusive_resources"] = []
    child = tasks[3]
    child["parent"] = "NSC-010"
    child["depends_on"] = []
    groups = tuple(
        group for group in deepcopy(base.resource_groups)
        if "NSC-010" not in group["work_ids"]
    )
    return WorkGraphPlan(base.id_map, tuple(tasks), groups, base.project_requirements)


def main() -> int:
    # Legacy reviewed decompositions without decomposition_children remain readable.
    legacy = make_plan()
    legacy_tasks = list(deepcopy(legacy.tasks))
    legacy_tasks[1]["decomposition_state"] = "decomposed"
    legacy_tasks[1]["execution_scope"] = "not_applicable"
    validate_decomposition_graph_semantics(
        WorkGraphPlan(legacy.id_map, tuple(legacy_tasks), legacy.resource_groups, legacy.project_requirements)
    )

    plan = strict_plan()
    validate_decomposition_graph_semantics(plan)

    bad = deepcopy(plan)
    tasks = list(bad.tasks)
    tasks[1]["kind"] = "implementation"
    expect_failure(WorkGraphPlan(bad.id_map, tuple(tasks), bad.resource_groups, bad.project_requirements), "kind='feature'")

    bad = deepcopy(plan)
    tasks = list(bad.tasks)
    tasks[1]["exclusive_resources"] = ["logical:aggregate-lock"]
    expect_failure(WorkGraphPlan(bad.id_map, tuple(tasks), bad.resource_groups, bad.project_requirements), "resource")

    bad = deepcopy(plan)
    tasks = list(bad.tasks)
    tasks[1]["decomposition_children"] = ["NSC-999"]
    expect_failure(WorkGraphPlan(bad.id_map, tuple(tasks), bad.resource_groups, bad.project_requirements), "missing child")

    bad = deepcopy(plan)
    tasks = list(bad.tasks)
    tasks[3]["parent"] = "NSC-001"
    expect_failure(WorkGraphPlan(bad.id_map, tuple(tasks), bad.resource_groups, bad.project_requirements), "direct child")

    bad = deepcopy(plan)
    tasks = list(bad.tasks)
    tasks[2]["contract_disposition"] = "active"
    tasks[2]["depends_on"] = ["NSC-010"]
    expect_failure(
        WorkGraphPlan(bad.id_map, tuple(tasks), bad.resource_groups, bad.project_requirements),
        "may not depend on decomposed aggregate",
    )

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
