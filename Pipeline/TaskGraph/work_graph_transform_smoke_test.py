from __future__ import annotations

from types import SimpleNamespace

from work_graph_transform import WorkGraphTransformError, build_work_graph_plan


def candidate_item(
    key: str,
    title: str,
    kind: str,
    parent: str,
    depends_on: list[str],
    execution_scope: str,
    resources: list[str] | None = None,
) -> dict:
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


def seed_record(
    key: str,
    title: str,
    kind: str,
    parent: str,
    depends_on: list[str],
    execution_scope: str,
    resources: list[str] | None = None,
) -> dict:
    return {
        "reconciliation_key": key,
        "title": title,
        "kind": kind,
        "proposed_status": "open",
        "execution_scope": execution_scope,
        "parent_reconciliation_key": parent,
        "depends_on_reconciliation_keys": depends_on,
        "exclusive_resource_keys": resources or [],
        "acceptance_criteria": [],
        "validation_requirements": [],
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
    ]
    candidate = {
        "work_items": [
            candidate_item("player", "Player", "feature", "no-safe-circle", [], "not_applicable"),
            candidate_item(
                "player-movement",
                "Player Movement",
                "implementation",
                "player",
                [],
                "single_agent",
                ["repo-file:Input.inputactions"],
            ),
            candidate_item(
                "fireball",
                "Fireball",
                "implementation",
                "player",
                ["player-movement"],
                "single_agent",
                ["repo-file:Input.inputactions"],
            ),
        ]
    }
    return SimpleNamespace(
        seed_records=seeds,
        candidate=candidate,
        source_reconciliation_run_id="source-run",
        verification_run_id="verification-run",
        exclusive_resource_groups=[
            {
                "resource_key": "repo-file:Input.inputactions",
                "work_keys": ["player-movement", "fireball"],
            }
        ],
        proposed_non_code_records=[{"title": "Human merge authority"}],
    )


def main() -> int:
    inputs = make_inputs()
    plan = build_work_graph_plan(inputs)

    assert plan.id_map == {
        "player": "NSC-001",
        "player-movement": "NSC-002",
        "fireball": "NSC-003",
    }

    by_key = {task["reconciliation_key"]: task for task in plan.tasks}
    assert by_key["player"]["parent"] == ""
    assert by_key["player-movement"]["parent"] == "NSC-001"
    assert by_key["fireball"]["parent"] == "NSC-001"
    assert by_key["fireball"]["depends_on"] == ["NSC-002"]
    assert by_key["fireball"]["bootstrap_source"] == {
        "reconciliation_run_id": "source-run",
        "verification_run_id": "verification-run",
    }

    assert plan.resource_groups == (
        {
            "resource_key": "repo-file:Input.inputactions",
            "work_ids": ["NSC-002", "NSC-003"],
            "reconciliation_keys": ["player-movement", "fireball"],
        },
    )
    assert len(plan.project_requirements) == 1

    # Determinism: same approved inputs produce the same IDs and task records.
    plan_again = build_work_graph_plan(inputs)
    assert plan_again.id_map == plan.id_map
    assert plan_again.tasks == plan.tasks

    # A dependency outside the approved seed set must fail instead of being invented or dropped.
    bad_inputs = make_inputs()
    bad_inputs.seed_records[2]["depends_on_reconciliation_keys"] = ["missing-owner"]
    bad_inputs.candidate["work_items"][2]["depends_on"] = [{"key": "missing-owner"}]
    try:
        build_work_graph_plan(bad_inputs)
    except WorkGraphTransformError as exc:
        assert "not a seeded work record" in str(exc)
    else:
        raise AssertionError("Expected an unseeded dependency to be rejected.")

    # The approved delta and candidate must agree on operational identity/topology.
    mismatch_inputs = make_inputs()
    mismatch_inputs.candidate["work_items"][1]["execution_scope"] = "needs_execution_decomposition"
    try:
        build_work_graph_plan(mismatch_inputs)
    except WorkGraphTransformError as exc:
        assert "execution_scope" in str(exc)
    else:
        raise AssertionError("Expected candidate/delta execution-scope mismatch to be rejected.")

    print("work_graph_transform_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
