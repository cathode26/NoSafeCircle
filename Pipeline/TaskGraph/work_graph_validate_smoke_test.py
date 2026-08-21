from __future__ import annotations

from copy import deepcopy

from work_graph_transform import WorkGraphPlan
from work_graph_validate import WorkGraphValidationError, validate_work_graph_plan


def task(
    task_id: str,
    key: str,
    title: str,
    kind: str,
    parent: str,
    depends_on: list[str],
    execution_scope: str,
    resources: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "id": task_id,
        "title": title,
        "reconciliation_key": key,
        "kind": kind,
        "type": kind,
        "status": "open",
        "execution_scope": execution_scope,
        "execution_reason": "test",
        "decomposition_state": "coarse" if kind == "feature" else "concrete",
        "decomposition_reason": "test",
        "parent": parent,
        "depends_on": depends_on,
        "exclusive_resources": resources or [],
        "acceptance_criteria": [],
        "validation_requirements": [],
        "gdd_evidence": [],
        "basis": "direct_gdd",
        "source_scope": "required",
        "confidence": "high",
        "notes": "",
        "repository_state_at_bootstrap": "missing",
        "repository_evidence_at_bootstrap": [],
        "bootstrap_source": {
            "reconciliation_run_id": "source-run",
            "verification_run_id": "verification-run",
        },
    }


def make_plan() -> WorkGraphPlan:
    tasks = (
        task("NSC-001", "no-safe-circle", "No Safe Circle", "feature", "", [], "not_applicable"),
        task("NSC-002", "player", "Player", "feature", "NSC-001", [], "not_applicable"),
        task(
            "NSC-003",
            "player-movement",
            "Player Movement",
            "implementation",
            "NSC-002",
            [],
            "single_agent",
            ["repo-file:Input.inputactions"],
        ),
        task(
            "NSC-004",
            "fireball",
            "Fireball",
            "implementation",
            "NSC-002",
            ["NSC-003"],
            "single_agent",
            ["repo-file:Input.inputactions"],
        ),
    )
    return WorkGraphPlan(
        id_map={
            "no-safe-circle": "NSC-001",
            "player": "NSC-002",
            "player-movement": "NSC-003",
            "fireball": "NSC-004",
        },
        tasks=tasks,
        resource_groups=(
            {
                "resource_key": "repo-file:Input.inputactions",
                "work_ids": ["NSC-003", "NSC-004"],
                "reconciliation_keys": ["player-movement", "fireball"],
            },
        ),
        project_requirements=(
            {
                "title": "Human merge authority",
                "requirement_type": "pipeline_constraint",
                "status": "confirmed",
            },
        ),
    )


def expect_failure(plan: WorkGraphPlan, expected_fragment: str) -> None:
    try:
        validate_work_graph_plan(plan)
    except WorkGraphValidationError as exc:
        assert expected_fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected validation failure containing {expected_fragment!r}.")


def main() -> int:
    plan = make_plan()
    summary = validate_work_graph_plan(plan)
    assert summary.task_count == 4
    assert summary.parent_edge_count == 3
    assert summary.dependency_edge_count == 1
    assert summary.root_id == "NSC-001"
    assert summary.root_key == "no-safe-circle"

    # Dependency cycles must be rejected.
    cycle_tasks = list(deepcopy(plan.tasks))
    cycle_tasks[2]["depends_on"] = ["NSC-004"]
    cycle_tasks[3]["depends_on"] = ["NSC-003"]
    expect_failure(
        WorkGraphPlan(plan.id_map, tuple(cycle_tasks), plan.resource_groups, plan.project_requirements),
        "Dependency graph contains a cycle",
    )

    # A second/disconnected root must be rejected.
    orphan_tasks = list(deepcopy(plan.tasks))
    orphan_tasks[3]["parent"] = ""
    expect_failure(
        WorkGraphPlan(plan.id_map, tuple(orphan_tasks), plan.resource_groups, plan.project_requirements),
        "exactly one root task",
    )

    # Shared resource membership must exactly match task claims.
    bad_groups = (
        {
            "resource_key": "repo-file:Input.inputactions",
            "work_ids": ["NSC-003"],
            "reconciliation_keys": ["player-movement"],
        },
    )
    expect_failure(
        WorkGraphPlan(plan.id_map, plan.tasks, bad_groups, plan.project_requirements),
        "does not exactly match task claims",
    )

    # Feature nodes must never become direct single-agent tickets.
    feature_tasks = list(deepcopy(plan.tasks))
    feature_tasks[1]["execution_scope"] = "single_agent"
    expect_failure(
        WorkGraphPlan(plan.id_map, tuple(feature_tasks), plan.resource_groups, plan.project_requirements),
        "may not be directly single-agent executable",
    )

    print("work_graph_validate_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
