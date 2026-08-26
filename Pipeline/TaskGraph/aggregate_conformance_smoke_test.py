from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from current_conformance import ConformanceState, _explicit_aggregate_conformance
from decomposition_graph_semantics import aggregate_requirement_sha256


def child_state(task_id: str, state: str) -> ConformanceState:
    return ConformanceState(
        task_id=task_id,
        title=task_id,
        state=state,
        head_commit="a" * 40,
        head_tree="b" * 40,
        selected_record_id=None,
        findings=(),
        dirty_worktree=False,
    )


def aggregate_task() -> dict:
    task = {
        "schema_version": "2.0",
        "id": "NSC-016",
        "contract_revision": 2,
        "contract_disposition": "active",
        "title": "Ranged Enemy Archetype",
        "kind": "feature",
        "execution_scope": "not_applicable",
        "decomposition_state": "decomposed",
        "decomposition_children": ["NSC-050", "NSC-051", "NSC-052"],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "reference": "Synthetic", "requirement": "Finished ranged capability."}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "reference": "Synthetic", "requirement": "Validate finished capability."}
        ],
        "downstream_integration_obligations": [],
    }
    task["decomposition_requirement_sha256"] = aggregate_requirement_sha256(task)
    return task


def evaluate_with_states(task: dict, states: dict[str, str]):
    def fake_evaluate(*, root, selector):
        return child_state(selector, states[selector])

    with patch("current_conformance.evaluate_current_conformance", side_effect=fake_evaluate):
        return _explicit_aggregate_conformance(
            root="synthetic",
            task=task,
            head="a" * 40,
            head_tree="b" * 40,
            dirty=False,
        )


def main() -> int:
    task = aggregate_task()
    conformant = evaluate_with_states(
        task,
        {
            "NSC-050": "conformant",
            "NSC-051": "conformant",
            "NSC-052": "conformant",
        },
    )
    assert conformant is not None
    assert conformant.state == "conformant"
    assert conformant.selected_record_id is None
    assert conformant.findings[0].code == "aggregate_children_conformant"

    incomplete = evaluate_with_states(
        task,
        {
            "NSC-050": "conformant",
            "NSC-051": "needs_testing",
            "NSC-052": "conformant",
        },
    )
    assert incomplete is not None
    assert incomplete.state == "aggregate"
    assert incomplete.findings[0].code == "aggregate_children_incomplete"
    assert "NSC-051=needs_testing" in incomplete.findings[0].message

    changed = deepcopy(task)
    changed["acceptance_criteria"][0]["requirement"] = "Changed after the reviewed decomposition."
    with patch(
        "current_conformance.evaluate_current_conformance",
        side_effect=AssertionError("children must not be evaluated when parent requirements changed"),
    ):
        replanning = _explicit_aggregate_conformance(
            root="synthetic",
            task=changed,
            head="a" * 40,
            head_tree="b" * 40,
            dirty=False,
        )
    assert replanning is not None
    assert replanning.state == "needs_replan"
    assert replanning.findings[0].code == "aggregate_requirements_changed"

    legacy = deepcopy(task)
    legacy.pop("decomposition_children")
    legacy.pop("decomposition_requirement_sha256")
    assert _explicit_aggregate_conformance(
        root="synthetic",
        task=legacy,
        head="a" * 40,
        head_tree="b" * 40,
        dirty=False,
    ) is None

    print("aggregate_conformance_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
