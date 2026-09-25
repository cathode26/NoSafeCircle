"""Smoke tests for the designer's ownership sheet and its conformance check."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for path in (REPO, REPO / "Pipeline"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from TaskDecomposition.ownership_sheet import (  # noqa: E402
    OwnershipSheetError,
    conformance_problems,
    sheet_from_result,
    validate_sheet,
)

PARENT = {
    "acceptance_criteria": [{"criterion_id": "AC-001"}, {"criterion_id": "AC-002"}],
    "completion_gates": [{"gate_id": "VAL-001"}],
    "downstream_integration_obligations": [],
}


def _child(key: str, resource: str, ac_text: str, val_text: str) -> dict:
    return {
        "local_key": key, "title": f"{key} title", "execution_reason": f"{key} purpose",
        "kind": "implementation", "type": "spell", "execution_scope": "single_agent",
        "exclusive_resources": [resource], "existing_task_dependencies": ["NSC-001"],
        "local_dependencies": [],
        "acceptance_criteria": [{"criterion_id": "AC-001", "reference": "r", "requirement": ac_text}],
        "completion_gates": [{"gate_id": "VAL-001", "reference": "r", "requirement": val_text}],
        "downstream_integration_obligations": [],
    }


def _result() -> dict:
    return {
        "decision": "decomposed",
        "children": [
            _child("cast", "repo-file:Assets/Cast.cs", "Cast the spell.", "Cast test passes."),
            _child("redirect", "repo-file:Assets/Redirect.cs", "Enemies chase the decoy.", "Redirect test passes."),
        ],
        "parent_requirement_coverage": [
            {"parent_entry_type": "acceptance_criteria", "parent_entry_id": "AC-001",
             "child_targets": [{"local_key": "cast", "child_entry_type": "acceptance_criteria",
                                "child_entry_id": "AC-001"}]},
            {"parent_entry_type": "acceptance_criteria", "parent_entry_id": "AC-002",
             "child_targets": [{"local_key": "redirect", "child_entry_type": "acceptance_criteria",
                                "child_entry_id": "AC-001"}]},
            {"parent_entry_type": "completion_gates", "parent_entry_id": "VAL-001",
             "child_targets": [{"local_key": "cast", "child_entry_type": "completion_gates",
                                "child_entry_id": "VAL-001"},
                               {"local_key": "redirect", "child_entry_type": "completion_gates",
                                "child_entry_id": "VAL-001"}]},
        ],
        "inbound_dependency_rewrites": [
            {"dependent_task_id": "NSC-030", "replacement_local_keys": ["redirect"], "reason": "r"}],
    }


def test_a_result_conforms_to_its_own_sheet() -> None:
    result = _result()
    sheet = sheet_from_result(result)
    validate_sheet(sheet, PARENT)
    assert conformance_problems(sheet, result) == []


def test_renumbered_ids_and_new_reasons_still_conform() -> None:
    result = _result()
    sheet = sheet_from_result(result)
    changed = copy.deepcopy(result)
    changed["children"][0]["acceptance_criteria"][0]["criterion_id"] = "AC-009"
    changed["parent_requirement_coverage"][0]["child_targets"][0]["child_entry_id"] = "AC-009"
    changed["inbound_dependency_rewrites"][0]["reason"] = "a different reason"
    assert conformance_problems(sheet, changed) == []


def test_design_changes_are_caught() -> None:
    result = _result()
    sheet = sheet_from_result(result)
    cases = {
        "exclusive_resources changed": lambda r: r["children"][0]["exclusive_resources"].append("repo-file:X.cs"),
        "child entries differ": lambda r: r["children"][1]["acceptance_criteria"][0].update(requirement="Reworded."),
        "existing_task_dependencies changed": lambda r: r["children"][1]["existing_task_dependencies"].clear(),
        "is missing": lambda r: r["parent_requirement_coverage"][2]["child_targets"].pop(),
        "is not in the sheet": lambda r: r["children"].append(_child("extra", "repo-file:E.cs", "e", "e")),
        "rewrites differ": lambda r: r["inbound_dependency_rewrites"][0]["replacement_local_keys"].append("cast"),
        "points at missing entry": lambda r: r["parent_requirement_coverage"][0]["child_targets"][0]
        .update(child_entry_id="AC-404"),
    }
    for expected, mutate in cases.items():
        changed = copy.deepcopy(result)
        mutate(changed)
        problems = conformance_problems(sheet, changed)
        assert any(expected in problem for problem in problems), (expected, problems)


def test_an_incomplete_sheet_is_refused() -> None:
    sheet = sheet_from_result(_result())
    sheet["children"][1]["entries"][0]["covers"] = []
    try:
        validate_sheet(sheet, PARENT)
    except OwnershipSheetError as error:
        assert "acceptance_criteria:AC-002" in str(error)
    else:
        raise AssertionError("a sheet leaving AC-002 uncovered was accepted")
    sheet = sheet_from_result(_result())
    sheet["children"][1]["exclusive_resources"].append("repo-file:Assets/Cast.cs")
    try:
        validate_sheet(sheet, PARENT)
    except OwnershipSheetError as error:
        assert "owned by both" in str(error)
    else:
        raise AssertionError("a resource owned by two children was accepted")


TESTS = (
    test_a_result_conforms_to_its_own_sheet,
    test_renumbered_ids_and_new_reasons_still_conform,
    test_design_changes_are_caught,
    test_an_incomplete_sheet_is_refused,
)

if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition ownership sheet smoke tests: PASS ({len(TESTS)} tests)")
