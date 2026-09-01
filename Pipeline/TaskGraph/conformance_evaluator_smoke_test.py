from __future__ import annotations

import copy
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import current_conformance
from conformance_records import CANON_PATH, GitRepository, canonical_text_sha256, semantic_json_sha256
from current_conformance import ConformanceEvaluationContext, evaluate_current_conformance
from decomposition_graph_semantics import aggregate_requirement_sha256
from history_aware_repository import HistoryAwareGitRepository

TASK_ID = "NSC-900"
TASK_PATH = f"Tasks/{TASK_ID}.yaml"
SURFACE = "src/implementation.txt"
ARTIFACT = f"Pipeline/TaskGraph/evidence/{TASK_ID}/artifacts/gate.txt"


def run(root: Path, *args: str) -> str:
    result = subprocess.run(args, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise AssertionError(f"{' '.join(args)} failed:\n{result.stderr}")
    return result.stdout.strip()


def write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def write_json(root: Path, path: str, value: dict) -> None:
    write(root, path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def commit(root: Path, message: str) -> str:
    run(root, "git", "add", "-A")
    run(root, "git", "commit", "-m", message)
    return run(root, "git", "rev-parse", "HEAD")


def task(revision: int = 1, human_gate: bool = False) -> dict:
    return {
        "schema_version": "2.0", "id": TASK_ID, "contract_revision": revision,
        "contract_disposition": "active", "title": "Synthetic implementation",
        "reconciliation_key": "synthetic", "kind": "implementation",
        "execution_scope": "single_agent",
        "completion_gates": [{"gate_id": "VAL-001", "reference": "test", "requirement": "passes"}],
        "human_gate_for_test": human_gate,
    }


def aggregate_task(task_id: str, children: list[str]) -> dict:
    value = {
        "schema_version": "2.0",
        "id": task_id,
        "contract_revision": 1,
        "contract_disposition": "active",
        "title": f"Synthetic aggregate {task_id}",
        "reconciliation_key": f"synthetic-{task_id.lower()}",
        "kind": "feature",
        "execution_scope": "not_applicable",
        "decomposition_state": "decomposed",
        "decomposition_children": children,
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "reference": "test", "requirement": "complete"}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "reference": "test", "requirement": "passes"}
        ],
        "downstream_integration_obligations": [],
    }
    value["decomposition_requirement_sha256"] = aggregate_requirement_sha256(value)
    return value


def initialize(root: Path) -> tuple[str, str]:
    run(root, "git", "init", "-b", "main")
    run(root, "git", "config", "user.email", "phase3a@example.invalid")
    run(root, "git", "config", "user.name", "Phase 3A Test")
    write_json(root, TASK_PATH, task())
    write(root, CANON_PATH, "# Canon\r\n\rRules.\r")
    write(root, SURFACE, "version one\n")
    write(root, ARTIFACT, "gate passed\n")
    validated = commit(root, "validated implementation")
    return validated, run(root, "git", "rev-parse", "HEAD^{tree}")


def record(root: Path, record_id: str, validated: str, tree: str, *,
           record_type: str = "delivery", basis: str = "", human_required: bool = False,
           human_decision: str | None = None) -> dict:
    repo = GitRepository(root)
    contract_raw = repo.read(validated, TASK_PATH)
    contract_value = json.loads(contract_raw.decode())
    value = {
        "schema_version": "1.0", "record_type": record_type, "record_id": record_id,
        "task_id": TASK_ID,
        "task_contract": {"path": TASK_PATH, "revision": contract_value["contract_revision"], "sha256": semantic_json_sha256(contract_raw)},
        "canon": {"path": CANON_PATH, "sha256": canonical_text_sha256(repo.read(validated, CANON_PATH))},
        "validated_state": {"commit": validated, "tree": tree},
        "conformance_surfaces": [{"path": SURFACE, "blob_sha": repo.blob(validated, SURFACE), "role": "implementation"}],
        "gate_results": [{"gate_id": "VAL-001", "result": "pass", "evidence": [{"path": ARTIFACT, "blob_sha": repo.blob(validated, ARTIFACT)}], "notes": "synthetic"}],
        "human_approval": {
            "required": human_required,
            "decision": human_decision or ("approved" if human_required else "not_required"),
            "approved_by": "Reviewer" if human_required and (human_decision or "approved") == "approved" else "",
            "notes": "synthetic",
        },
        "recorded_at": "2026-08-22T00:00:00Z",
    }
    if record_type == "delivery":
        value["delivery"] = {"base_commit": validated, "candidate_commit": validated, "integrated_commit": validated, "integrated_tree": tree}
    elif record_type == "baseline":
        value["baseline"] = {
            "reason_type": "pre_evidence_existing_implementation",
            "summary": "Synthetic pre-evidence implementation baseline",
        }
    else:
        value["revalidation"] = {"basis_record_id": basis, "reason_type": "code_change", "summary": "synthetic revalidation"}
    return value


def add_record(root: Path, value: dict, message: str = "add evidence") -> str:
    path = f"Pipeline/TaskGraph/evidence/{TASK_ID}/records/{value['record_id']}.json"
    write_json(root, path, value)
    return commit(root, message)


def expect(root: Path, state: str) -> None:
    actual = evaluate_current_conformance(root, TASK_ID)
    assert actual.state == state, (state, actual.to_dict())


def scenario_progression(root: Path) -> None:
    validated, tree = initialize(root)
    expect(root, "not_delivered")
    delivery_id = f"DEL-{TASK_ID}-001"
    add_record(root, record(root, delivery_id, validated, tree))
    expect(root, "conformant")
    write(root, "unrelated.txt", "unrelated\n")
    commit(root, "unrelated descendant")
    expect(root, "conformant")
    write(root, SURFACE, "version two\n")
    changed = commit(root, "surface change")
    expect(root, "needs_testing")
    changed_tree = run(root, "git", "rev-parse", "HEAD^{tree}")
    add_record(root, record(root, f"REV-{TASK_ID}-001", changed, changed_tree, record_type="revalidation", basis=delivery_id))
    expect(root, "conformant")
    # Working-copy evidence is deliberately invisible to the evaluator.
    uncommitted = record(root, f"DEL-{TASK_ID}-UNCOMMITTED", changed, changed_tree)
    write_json(root, f"Pipeline/TaskGraph/evidence/{TASK_ID}/records/{uncommitted['record_id']}.json", uncommitted)
    expect(root, "conformant")


def scenario_baseline_progression(root: Path) -> None:
    validated, tree = initialize(root)
    baseline_id = f"BASE-{TASK_ID}-001"
    add_record(root, record(root, baseline_id, validated, tree, record_type="baseline"))
    expect(root, "conformant")
    write(root, SURFACE, "version two\n")
    changed = commit(root, "surface change after baseline")
    expect(root, "needs_testing")
    changed_tree = run(root, "git", "rev-parse", "HEAD^{tree}")
    add_record(root, record(root, f"REV-{TASK_ID}-001", changed, changed_tree,
                            record_type="revalidation", basis=baseline_id))
    expect(root, "conformant")


def scenario_uncommitted_baseline(root: Path) -> None:
    validated, tree = initialize(root)
    value = record(root, f"BASE-{TASK_ID}-UNCOMMITTED", validated, tree, record_type="baseline")
    write_json(root, f"Pipeline/TaskGraph/evidence/{TASK_ID}/records/{value['record_id']}.json", value)
    expect(root, "not_delivered")


def scenario_invalid_baseline(root: Path, corruption: str) -> None:
    validated, tree = initialize(root)
    value = record(root, f"BASE-{TASK_ID}-001", validated, tree, record_type="baseline")
    if corruption == "missing_gate":
        value["gate_results"] = []
    elif corruption == "wrong_gate_evidence":
        value["gate_results"][0]["evidence"][0]["blob_sha"] = "0" * 40
    elif corruption == "delivery_field":
        value["delivery"] = {"base_commit": validated}
    elif corruption == "revalidation_field":
        value["revalidation"] = {"basis_record_id": "anything"}
    elif corruption == "mutable_authority":
        value["ready"] = True
    add_record(root, value)
    expect(root, "invalid_evidence")


def scenario_stale_and_replan(root: Path, change: str) -> None:
    validated, tree = initialize(root)
    add_record(root, record(root, f"DEL-{TASK_ID}-001", validated, tree))
    if change == "gdd":
        # The record keeps the historical whole-GDD hash as audit provenance, but an
        # unrelated later canon edit does not invalidate an unchanged task contract.
        write(root, CANON_PATH, "# Changed canon\n")
        expected = "conformant"
    else:
        changed_task = task(revision=2)
        changed_task["title"] = "Changed contract"
        write_json(root, TASK_PATH, changed_task)
        expected = "needs_replan"
    commit(root, f"{change} change")
    expect(root, expected)


def scenario_human(root: Path) -> None:
    validated, tree = initialize(root)
    value = record(root, f"DEL-{TASK_ID}-001", validated, tree, human_required=True, human_decision="not_required")
    add_record(root, value)
    expect(root, "needs_human")


def scenario_invalid(root: Path, corruption: str) -> None:
    validated, tree = initialize(root)
    value = record(root, f"DEL-{TASK_ID}-001", validated, tree)
    if corruption == "missing_gate":
        value["gate_results"] = []
    elif corruption == "wrong_tree":
        value["validated_state"]["tree"] = "0" * 40
        value["delivery"]["integrated_tree"] = "0" * 40
    elif corruption == "wrong_blob":
        value["conformance_surfaces"][0]["blob_sha"] = "0" * 40
    elif corruption == "wrong_canon_hash":
        # Historical canon provenance still has to match the validated commit.
        value["canon"]["sha256"] = "0" * 64
    add_record(root, value)
    if corruption == "altered_artifact":
        write(root, ARTIFACT, "altered\n")
        commit(root, "alter artifact")
    elif corruption == "modified_record":
        value["recorded_at"] = "2026-08-22T01:00:00Z"
        path = f"Pipeline/TaskGraph/evidence/{TASK_ID}/records/{value['record_id']}.json"
        write_json(root, path, value)
        commit(root, "illegally modify immutable record")
    expect(root, "invalid_evidence")


def scenario_non_ancestral(root: Path) -> None:
    validated, tree = initialize(root)
    run(root, "git", "branch", "other")
    write(root, "main-only.txt", "main\n")
    commit(root, "main lineage")
    run(root, "git", "checkout", "other")
    write(root, "other-only.txt", "other\n")
    other = commit(root, "other lineage")
    other_tree = run(root, "git", "rev-parse", "HEAD^{tree}")
    value = record(root, f"DEL-{TASK_ID}-001", other, other_tree)
    run(root, "git", "checkout", "main")
    add_record(root, value)
    expect(root, "needs_testing")


def scenario_ambiguous(root: Path) -> None:
    base, _ = initialize(root)
    run(root, "git", "checkout", "-b", "left")
    write(root, "left.txt", "left\n")
    left = commit(root, "left validated")
    left_tree = run(root, "git", "rev-parse", "HEAD^{tree}")
    left_record = record(root, f"DEL-{TASK_ID}-LEFT", left, left_tree)
    run(root, "git", "checkout", "-b", "right", base)
    write(root, "right.txt", "right\n")
    right = commit(root, "right validated")
    right_tree = run(root, "git", "rev-parse", "HEAD^{tree}")
    right_record = record(root, f"DEL-{TASK_ID}-RIGHT", right, right_tree)
    run(root, "git", "checkout", "main")
    run(root, "git", "merge", "--no-ff", "left", "-m", "merge left")
    run(root, "git", "merge", "--no-ff", "right", "-m", "merge right")
    add_record(root, left_record)
    add_record(root, right_record)
    expect(root, "ambiguous_evidence")


def scenario_context_public_api_and_aggregate_memo(root: Path) -> None:
    initialize(root)
    parent_id = "NSC-901"
    write_json(root, f"Tasks/{parent_id}.yaml", aggregate_task(parent_id, [TASK_ID]))
    commit(root, "add aggregate parent")

    repository_constructions = 0

    class CountingRepository(HistoryAwareGitRepository):
        def __init__(self, selected_root: Path | str) -> None:
            nonlocal repository_constructions
            repository_constructions += 1
            super().__init__(selected_root)

    with patch("current_conformance.GitRepository", CountingRepository):
        context = ConformanceEvaluationContext(root)
    assert repository_constructions == 1

    expected = evaluate_current_conformance(root, TASK_ID)
    with patch(
        "current_conformance._evaluate_resolved_conformance",
        wraps=current_conformance._evaluate_resolved_conformance,
    ) as derive:
        child = context.evaluate(TASK_ID)
        same_child = context.evaluate("synthetic")
        parent = context.evaluate(parent_id)

    assert child.to_dict() == expected.to_dict()
    assert same_child is child
    assert parent.state == "aggregate"
    derived_ids = [call.kwargs["task"]["id"] for call in derive.call_args_list]
    assert derived_ids.count(TASK_ID) == 1, derived_ids
    assert derived_ids.count(parent_id) == 1, derived_ids


def scenario_recursive_aggregate_cycle(root: Path) -> None:
    initialize(root)
    first_id = "NSC-901"
    second_id = "NSC-902"
    write_json(root, f"Tasks/{first_id}.yaml", aggregate_task(first_id, [second_id]))
    write_json(root, f"Tasks/{second_id}.yaml", aggregate_task(second_id, [first_id]))
    commit(root, "add synthetic aggregate cycle")

    context = ConformanceEvaluationContext(root)
    first = context.evaluate(first_id)
    second = context.evaluate(second_id)
    assert first.state == "invalid_evidence", first.to_dict()
    assert second.state == "invalid_evidence", second.to_dict()
    assert first.findings[0].code == "conformance_evaluation_cycle"
    assert second.findings[0].code == "conformance_evaluation_cycle"
    assert f"{first_id} -> {second_id} -> {first_id}" in first.findings[0].message


def fresh(callback, *args) -> None:
    with tempfile.TemporaryDirectory(prefix="phase3a-conformance-") as temp:
        callback(Path(temp), *args)


def main() -> int:
    fresh(scenario_progression)
    fresh(scenario_baseline_progression)
    fresh(scenario_uncommitted_baseline)
    for corruption in ("missing_gate", "wrong_gate_evidence", "delivery_field", "revalidation_field", "mutable_authority"):
        fresh(scenario_invalid_baseline, corruption)
    fresh(scenario_stale_and_replan, "gdd")
    fresh(scenario_stale_and_replan, "contract")
    fresh(scenario_human)
    for corruption in ("missing_gate", "wrong_tree", "wrong_blob", "wrong_canon_hash", "altered_artifact", "modified_record"):
        fresh(scenario_invalid, corruption)
    fresh(scenario_non_ancestral)
    fresh(scenario_ambiguous)
    fresh(scenario_context_public_api_and_aggregate_memo)
    fresh(scenario_recursive_aggregate_cycle)
    print("conformance_evaluator_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
