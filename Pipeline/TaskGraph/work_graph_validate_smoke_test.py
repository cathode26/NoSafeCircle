from __future__ import annotations

from copy import deepcopy

from work_graph_transform import WorkGraphPlan
from work_graph_validate import WorkGraphValidationError, validate_work_graph_plan


def task(task_id, key, title, kind, parent, depends_on, execution_scope, resources=None, *, run="run-a"):
    return {
        "schema_version": "2.0",
        "id": task_id,
        "contract_revision": 1,
        "contract_disposition": "active",
        "title": title,
        "reconciliation_key": key,
        "kind": kind,
        "type": kind,
        "execution_scope": execution_scope,
        "execution_reason": "test",
        "decomposition_state": "coarse" if kind == "feature" else "concrete",
        "decomposition_reason": "test",
        "parent": parent,
        "depends_on": depends_on,
        "exclusive_resources": resources or [],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "reference": "Synthetic", "requirement": "Acceptance."}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "reference": "Synthetic", "requirement": "Validate."}
        ],
        "downstream_integration_obligations": [],
        "gdd_evidence": [],
        "basis": "direct_gdd",
        "source_scope": "required",
        "confidence": "high",
        "notes": "",
        "repository_state_at_bootstrap": "missing",
        "repository_evidence_at_bootstrap": [],
        "provenance": {
            "origin": "verified_reconciliation_bootstrap",
            "reconciliation_run_id": run,
            "verification_run_id": f"verify-{run}",
        },
    }


def make_plan() -> WorkGraphPlan:
    tasks = (
        task("NSC-001", "no-safe-circle", "No Safe Circle", "feature", "", [], "not_applicable"),
        task("NSC-002", "player", "Player", "feature", "NSC-001", [], "not_applicable", run="run-b"),
        task("NSC-010", "player-movement", "Player Movement", "implementation", "NSC-002", [], "single_agent", ["repo-file:Input.inputactions"]),
        task("NSC-020", "fireball", "Fireball", "implementation", "NSC-002", ["NSC-010"], "single_agent", ["repo-file:Input.inputactions"], run="run-c"),
    )
    return WorkGraphPlan(
        id_map={
            "no-safe-circle": "NSC-001",
            "player": "NSC-002",
            "player-movement": "NSC-010",
            "fireball": "NSC-020",
        },
        tasks=tasks,
        resource_groups=(
            {
                "resource_key": "repo-file:Input.inputactions",
                "work_ids": ["NSC-010", "NSC-020"],
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


def expect_failure(plan, fragment):
    try:
        validate_work_graph_plan(plan)
    except WorkGraphValidationError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected failure containing {fragment!r}")


def main() -> int:
    plan = make_plan()
    summary = validate_work_graph_plan(plan)
    assert summary.task_schema_version == "2.0"
    assert summary.task_count == 4
    # Non-contiguous permanent IDs and per-task provenance are valid in v2.
    assert summary.root_id == "NSC-001"

    legacy_status = list(deepcopy(plan.tasks))
    legacy_status[2]["status"] = "complete"
    expect_failure(WorkGraphPlan(plan.id_map, tuple(legacy_status), plan.resource_groups, plan.project_requirements), "may not contain legacy field 'status'")

    duplicate_gate = list(deepcopy(plan.tasks))
    duplicate_gate[2]["completion_gates"].append(deepcopy(duplicate_gate[2]["completion_gates"][0]))
    expect_failure(WorkGraphPlan(plan.id_map, tuple(duplicate_gate), plan.resource_groups, plan.project_requirements), "duplicate gate_id")

    cycle = list(deepcopy(plan.tasks))
    cycle[2]["depends_on"] = ["NSC-020"]
    expect_failure(WorkGraphPlan(plan.id_map, tuple(cycle), plan.resource_groups, plan.project_requirements), "Dependency graph contains a cycle")

    superseded = list(deepcopy(plan.tasks))
    superseded[2]["contract_disposition"] = "superseded"
    superseded[2]["superseded_by"] = "NSC-020"
    expect_failure(WorkGraphPlan(plan.id_map, tuple(superseded), plan.resource_groups, plan.project_requirements), "may not depend on non-active")

    print("work_graph_validate_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
