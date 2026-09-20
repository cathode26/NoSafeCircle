"""Prepare a review-only corrected NSC-025 proposal from the Run 5 result."""

import json
import subprocess
import sys
from pathlib import Path

SOURCE = Path(r"C:\NSC\NSC\NoSafeCircle")
RUN = Path(r"C:\nscrev\realdecomp-Checkouts-r5\.assistant-control\decomposition-runs\run5-nsc-025-f761c05bc291")
OUT = Path(r"C:\nscrev\reports\run5-nsc025-corrected-preview")
sys.path.insert(0, str(SOURCE / "Pipeline" / "TaskGraph"))
sys.path.insert(0, str(SOURCE / "Pipeline"))

from TaskDecomposition.contracts import DecompositionResult
from graph_delta import GraphDeltaPlan, plan_graph_delta
from graph_apply_plan import plan_graph_apply
from persistent_work_graph import load_persistent_work_graph


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()
    assert head == "3a565100697010e444e052dc008620509c0c0113", head
    source = load_persistent_work_graph(SOURCE)
    original = json.loads((RUN / "decomposition_result.json").read_text(encoding="utf-8"))
    candidate = json.loads(json.dumps(original))
    old_plan = GraphDeltaPlan.from_payload(json.loads((RUN / "graph_delta.json").read_text(encoding="utf-8")))
    nav = next(c for c in candidate["children"] if c["local_key"] == "navmesh-agent-configuration-foundation")
    ac = next(e for e in nav["acceptance_criteria"] if e["criterion_id"] == "AC-002")
    val = next(e for e in nav["completion_gates"] if e["gate_id"] == "VAL-001")
    old_ac = ac["requirement"]
    old_val = val["requirement"]
    ac["requirement"] += " Create Assets/NoSafeCircle/DoorPrototype/Tests/Editor/NavMeshAgentConfigurationTests.cs for the configuration and navigation validation in VAL-001."
    val["requirement"] = (
        "The Edit Mode test Assets/NoSafeCircle/DoorPrototype/Tests/Editor/NavMeshAgentConfigurationTests.cs "
        "uses a fresh in-memory scene to verify GameplayNavigationSurface configuration and that a "
        "test-owned NavMeshAgent using the selected agent type finds a complete path across a test-owned "
        "open gameplay floor. That check does not prove canonical room composition. After the authorized "
        "No Safe Circle/Build Door Prototype Scene command materializes Assets/Scenes/DoorPrototype.unity "
        "in the isolated task checkout, validate the built canonical scene without saving or changing it: "
        "the five-room composition has removed the legacy Floor, exactly one builder-owned GameplayNavigation "
        "and GameplayNavigationSurface survive, navigation uses the composed FloorCollision and obstacle "
        "colliders rather than visual Tilemaps, and a configured test-owned NavMeshAgent finds a complete "
        "path across open composed gameplay floor after scene load or the specified runtime rebuild. "
        "Repeat the authorized builder materialization and recheck that exactly one navigation owner "
        "remains and the composed-floor path still works. Validation-only tests must not save or modify "
        "the committed canonical scene."
    )
    result = DecompositionResult.from_dict(candidate)
    selector = {
        "task_id": result.parent_task.task_id,
        "contract_revision": result.parent_task.contract_revision,
        "contract_sha256": result.parent_task.contract_sha256,
    }
    new_plan = plan_graph_delta(source, selector, result)
    apply_preflight = plan_graph_apply(source, selector, result, new_plan)
    assert apply_preflight.status == "fresh", apply_preflight
    assert old_plan.plan_id != new_plan.plan_id
    assert old_plan.allocated_local_key_to_task_id == new_plan.allocated_local_key_to_task_id
    assert set(source.tasks_by_id) == set(task["id"] for task in source.plan.tasks)
    reverted = json.loads(json.dumps(candidate))
    reverted_nav = next(c for c in reverted["children"] if c["local_key"] == "navmesh-agent-configuration-foundation")
    next(e for e in reverted_nav["acceptance_criteria"] if e["criterion_id"] == "AC-002")["requirement"] = old_ac
    next(e for e in reverted_nav["completion_gates"] if e["gate_id"] == "VAL-001")["requirement"] = old_val
    assert reverted == original, "Unexpected proposal change outside the two corrected entries"
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "corrected_decomposition_result.json", candidate)
    write_json(OUT / "corrected_graph_delta.json", new_plan.to_dict())
    write_json(OUT / "correction_summary.json", {
        "source_commit": head,
        "old_run5_plan_id": old_plan.plan_id,
        "corrected_preview_plan_id": new_plan.plan_id,
        "allocated_child_ids": new_plan.allocated_local_key_to_task_id,
        "scope": "review-only deterministic preview; not independently reviewed or authorized for apply",
        "read_only_graph_apply_preflight": apply_preflight.status,
        "changed_entries": [
            {"child": "navmesh-agent-configuration-foundation", "entry": "AC-002", "before": old_ac, "after": ac["requirement"]},
            {"child": "navmesh-agent-configuration-foundation", "entry": "VAL-001", "before": old_val, "after": val["requirement"]},
        ],
    })
    print(f"old_plan={old_plan.plan_id}")
    print(f"corrected_preview_plan={new_plan.plan_id}")
    print(f"allocated_child_ids={new_plan.allocated_local_key_to_task_id}")
    print(f"preview_dir={OUT}")


if __name__ == "__main__":
    main()
