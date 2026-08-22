from __future__ import annotations

from types import SimpleNamespace

from task_contract_migration import MIGRATION_ID
from work_graph_transform import WorkGraphTransformError, build_work_graph_plan


def candidate_item(key, title, kind, parent, depends_on, execution_scope, resources=None):
    return {
        "key": key,
        "title": title,
        "kind": kind,
        "type": kind,
        "parent_key": parent,
        "graph_status": "open",
        "execution_scope": execution_scope,
        "execution_reason": "test reason",
        "decomposition_state": "concrete" if kind != "feature" else "coarse",
        "decomposition_reason": "test decomposition",
        "depends_on": [{"key": dep} for dep in depends_on],
        "exclusive_resources": [{"key": item} for item in (resources or [])],
        "gdd_evidence": [],
        "repository_evidence": [],
    }


def seed_record(key, title, kind, parent, depends_on, execution_scope, resources=None):
    return {
        "reconciliation_key": key,
        "title": title,
        "kind": kind,
        "proposed_status": "open",
        "execution_scope": execution_scope,
        "parent_reconciliation_key": parent,
        "depends_on_reconciliation_keys": depends_on,
        "exclusive_resource_keys": resources or [],
        "acceptance_criteria": [
            {"reference": "Synthetic", "requirement": f"{title} behaves correctly."}
        ],
        "validation_requirements": [
            {"reference": "Synthetic", "requirement": f"Validate {title}."}
        ],
    }


def make_inputs() -> SimpleNamespace:
    seeds = [
        seed_record("player", "Player", "feature", "no-safe-circle", [], "not_applicable"),
        seed_record(
            "player-movement",
            "Player Movement",
            "implementation",
            "player",
            [],
            "single_agent",
            ["repo-file:Input.inputactions"],
        ),
        seed_record(
            "fireball",
            "Fireball",
            "implementation",
            "player",
            ["player-movement"],
            "single_agent",
            ["repo-file:Input.inputactions"],
        ),
        seed_record("no-safe-circle", "No Safe Circle", "feature", "", [], "not_applicable"),
    ]
    candidate = {
        "work_items": [
            candidate_item("player", "Player", "feature", "no-safe-circle", [], "not_applicable"),
            candidate_item("player-movement", "Player Movement", "implementation", "player", [], "single_agent", ["repo-file:Input.inputactions"]),
            candidate_item("fireball", "Fireball", "implementation", "player", ["player-movement"], "single_agent", ["repo-file:Input.inputactions"]),
            candidate_item("no-safe-circle", "No Safe Circle", "feature", "", [], "not_applicable"),
        ]
    }
    return SimpleNamespace(
        seed_records=seeds,
        candidate=candidate,
        source_reconciliation_run_id="source-run",
        verification_run_id="verification-run",
        approved_by="Synthetic Test Approver",
        exclusive_resource_groups=[
            {
                "resource_key": "repo-file:Input.inputactions",
                "work_keys": ["player-movement", "fireball"],
            }
        ],
        proposed_non_code_records=[
            {
                "title": "Human merge authority",
                "requirement_type": "pipeline_constraint",
                "status": "confirmed",
                "gdd_evidence": [],
                "evidence": "Synthetic fixture requirement.",
            }
        ],
    )


def main() -> int:
    inputs = make_inputs()
    plan = build_work_graph_plan(inputs)
    assert plan.id_map == {
        "no-safe-circle": "NSC-001",
        "player": "NSC-002",
        "player-movement": "NSC-003",
        "fireball": "NSC-004",
    }
    by_key = {task["reconciliation_key"]: task for task in plan.tasks}
    movement = by_key["player-movement"]
    assert len(movement["acceptance_criteria"]) == 1
    assert len(movement["completion_gates"]) == 1
    assert len(movement["downstream_integration_obligations"]) == 0
    fireball = by_key["fireball"]
    assert fireball["schema_version"] == "2.0"
    assert fireball["contract_revision"] == 1
    assert fireball["contract_disposition"] == "active"
    assert "status" not in fireball
    assert "validation_requirements" not in fireball
    assert "bootstrap_source" not in fireball
    assert fireball["depends_on"] == ["NSC-003"]
    assert fireball["acceptance_criteria"][0]["criterion_id"] == "AC-001"
    assert fireball["completion_gates"][0]["gate_id"] == "VAL-001"
    assert fireball["downstream_integration_obligations"] == []
    assert fireball["provenance"] == {
        "origin": "verified_reconciliation_bootstrap",
        "source_schema_version": "1.0",
        "reconciliation_run_id": "source-run",
        "verification_run_id": "verification-run",
        "bootstrap_status_observation": "open",
        "migration_id": MIGRATION_ID,
    }
    assert plan.resource_groups[0]["work_ids"] == ["NSC-003", "NSC-004"]
    assert build_work_graph_plan(inputs).tasks == plan.tasks

    bad_inputs = make_inputs()
    bad_inputs.seed_records[2]["depends_on_reconciliation_keys"] = ["missing-owner"]
    bad_inputs.candidate["work_items"][2]["depends_on"] = [{"key": "missing-owner"}]
    try:
        build_work_graph_plan(bad_inputs)
    except WorkGraphTransformError as exc:
        assert "not a seeded work record" in str(exc)
    else:
        raise AssertionError("Expected unseeded dependency rejection.")

    print("work_graph_transform_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
