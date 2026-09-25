"""The readiness worksheet surfaces what a split must get right, from contracts alone."""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.readiness_worksheet import (  # noqa: E402
    build_worksheet,
    render_worksheet_markdown,
)


def task(task_id: str, *, depends_on=(), resources=(), requirement="", notes="", disposition="active"):
    return {
        "id": task_id, "title": f"{task_id} title", "contract_revision": 1,
        "contract_disposition": disposition, "execution_scope": "single_agent",
        "decomposition_state": "concrete", "depends_on": list(depends_on),
        "exclusive_resources": list(resources),
        "acceptance_criteria": [{"criterion_id": "AC-001", "requirement": requirement}],
        "completion_gates": [{"gate_id": "VAL-001", "requirement": "The PlayMode test passes."}],
        "downstream_integration_obligations": [],
        "notes": notes,
    }


def graph() -> dict:
    parent = task(
        "NSC-100", depends_on=["NSC-010"],
        resources=[
            "repo-file:Assets/Game/Scripts/Decoy.cs", "repo-file:Assets/Game/Scripts/Decoy.cs.meta",
            "repo-file:Assets/Game/Tests/DecoyTests.cs", "repo-file:Assets/Game/Tests/DecoyTests.cs.meta",
            "repo-file:Assets/Game/Scripts/Orphan.cs.meta",
            "unity-scene:Assets/Scenes/Main.unity",
        ],
        requirement=("Decoy calls PlayerInteractionController and checks EnemyHealth. "
                     "SceneBuilder.cs is not modified. Vincent reviews the result."),
    )
    return {
        "NSC-100": parent,
        "NSC-010": task("NSC-010", depends_on=["NSC-019"]),
        "NSC-019": task("NSC-019", resources=["repo-file:Assets/Game/Scripts/PlayerInteractionController.cs"]),
        "NSC-060": task("NSC-060", resources=["repo-file:Assets/Game/Scripts/SceneBuilder.cs"]),
        "NSC-099": task("NSC-099", resources=["repo-file:Assets/Game/Scripts/Retired.cs"], disposition="superseded"),
    }


def test_resources_dependencies_and_owners() -> None:
    sheet = build_worksheet(graph(), "NSC-100", repository_components={"EnemyHealth", "SceneBuilder"})
    resources = sheet["resources"]
    assert resources["production_files"] == ["Assets/Game/Scripts/Decoy.cs"]
    assert resources["test_files"] == ["Assets/Game/Tests/DecoyTests.cs"]
    assert resources["separately_claimable_test_files"] == 1
    assert resources["scene_or_prefab_locks"] == ["unity-scene:Assets/Scenes/Main.unity"]
    assert resources["unpaired_meta_files"] == ["Assets/Game/Scripts/Orphan.cs.meta"]
    assert sheet["dependencies"] == {"declared": ["NSC-010"], "transitive": ["NSC-019"]}
    components = {m["component"]: m for m in sheet["mentioned_components_by_name_match"]}
    # Owned through a transitive dependency: reachable, not flagged.
    assert components["PlayerInteractionController"]["reachable_owners"] == ["NSC-019"]
    # Named, claimed by a task the parent cannot reach: flagged.
    assert sheet["components_with_no_reachable_owner"] == ["SceneBuilder"]
    # In the repository but claimed by no task: a person must name the owner.
    assert sheet["named_identifiers_no_task_claims"] == ["EnemyHealth"]
    assert sheet["authority"] == "worksheet_only_not_a_decision"


def test_clause_flags_and_rendering() -> None:
    sheet = build_worksheet(graph(), "NSC-100", repository_components={"EnemyHealth"})
    assert any("is not modified" in c["text"] for c in sheet["edit_restriction_clauses_by_text_match"])
    assert any("Vincent" in c["text"] for c in sheet["reserved_decision_clauses_by_text_match"])
    markdown = render_worksheet_markdown(sheet)
    assert markdown.startswith("# Decomposition readiness: NSC-100 rev 1")
    assert "text matches for a person to read, not decisions" in markdown
    assert "No task claims these by file" in markdown and "EnemyHealth" in markdown
    assert "a lock is not edit permission" in markdown


def test_superseded_tasks_and_method_names_are_not_owners() -> None:
    tasks = graph()
    tasks["NSC-100"]["acceptance_criteria"][0]["requirement"] += " Retired stays. CalculatePath runs."
    sheet = build_worksheet(tasks, "NSC-100", repository_components=set())
    names = {m["component"] for m in sheet["mentioned_components_by_name_match"]}
    assert "Retired" not in names
    assert sheet["named_identifiers_no_task_claims"] == []


def test_an_unknown_task_is_refused() -> None:
    try:
        build_worksheet(graph(), "NSC-555")
    except ValueError as exc:
        assert "not in the committed graph" in str(exc)
    else:
        raise AssertionError("expected a refusal")


TESTS = (
    test_resources_dependencies_and_owners,
    test_clause_flags_and_rendering,
    test_superseded_tasks_and_method_names_are_not_owners,
    test_an_unknown_task_is_refused,
)


def main() -> int:
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition readiness worksheet smoke tests: PASS ({len(TESTS)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
