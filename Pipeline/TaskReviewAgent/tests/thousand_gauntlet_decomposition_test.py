"""Disposable-repository application of all twenty thousand-profile plans."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline/TaskGraph"):
    sys.path.insert(0, str(directory))

from Pipeline.TaskReviewAgent import prepare_synthetic_gauntlet as generator
from Pipeline.TaskReviewAgent.tests.prepare_synthetic_gauntlet_smoke_test import _copy_graph
from TaskDecomposition.tests.decomposition_contracts_smoke_test import base, child
from TaskDecomposition.policy import validate_decomposition_result
from persistent_work_graph import load_persistent_work_graph
from graph_delta import plan_graph_delta
from apply_graph_delta import apply_graph_delta
from undo_graph_delta import undo_graph_delta
from graph_apply_smoke_test import git, approved_identity_environment
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.downstream_resilience import validation_plan_for


def proposal(parent, tasks):
    raw = base(parent, "decomposed", "execution")
    keys = [f"{parent['id'].lower()}-{name}" for name in ("alpha", "beta")]
    for index, name in enumerate(("alpha", "beta")):
        item = child(keys[index])
        item["title"] = f"Gauntlet {parent['id']}: {name} value"
        item["exclusive_resources"] = parent["exclusive_resources"][index * 2:index * 2 + 2]
        item["existing_task_dependencies"] = list(parent["depends_on"])
        item["local_dependencies"] = [keys[0]] if index else []
        item["acceptance_criteria"] = [parent["acceptance_criteria"][index]]
        item["completion_gates"] = [parent["completion_gates"][index]]
        raw["children"].append(item)
        for field, id_field in (("acceptance_criteria", "criterion_id"), ("completion_gates", "gate_id")):
            entry = item[field][0]
            raw["parent_requirement_coverage"].append({
                "parent_entry_type": field, "parent_entry_id": entry[id_field],
                "disposition": "assigned_to_child", "child_targets": [{"local_key": keys[index],
                    "child_entry_type": field, "child_entry_id": entry[id_field]}],
                "reason": "Exact source and meta pair assigned to this child.", "integration_rationale": "",
            })
    raw["inbound_dependency_rewrites"] = [{
        "dependent_task_id": task["id"], "replacement_local_keys": keys,
        "reason": "The consumer requires both original values.",
    } for task in tasks if parent["id"] in task["depends_on"]]
    return validate_decomposition_result(raw, parent_task=parent,
        existing_reconciliation_keys=(task["reconciliation_key"] for task in tasks))


def main():
    started = time.perf_counter()
    bundle, manifest = generator.build_bundle(
        ROOT, "thousand", target_repository=generator.PRIVATE_REPOSITORY
    )
    children = set()
    with tempfile.TemporaryDirectory(prefix="thousand-decomposition-") as directory:
        source = Path(directory)
        _copy_graph(source)
        for path, content in bundle.items():
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        git(source, "init")
        git(source, "config", "core.autocrlf", "false")
        git(source, "config", "user.name", "No Safe Circle TaskReviewAgent")
        git(source, "config", "user.email", "task-review-agent@nosafecircle.invalid")
        git(source, "remote", "add", "origin", f"https://github.com/{generator.PRIVATE_REPOSITORY}.git")
        git(source, "add", "--", ".")
        git(source, "commit", "-m", "fixture: thousand graph")
        for task_id in manifest["decomposition_parents"]:
            graph = load_persistent_work_graph(source)
            parent = next(task for task in graph.plan.tasks if task["id"] == task_id)
            result = proposal(parent, graph.plan.tasks)
            plan = plan_graph_delta(graph, result.parent_task, result)
            head = git(source, "rev-parse", "HEAD")
            with approved_identity_environment():
                applied = apply_graph_delta(source, result.parent_task, result, plan, expected_head=head)
                replay = apply_graph_delta(source, result.parent_task, result, plan, expected_head=applied.new_commit_sha)
            assert replay.new_commit_sha is None
            assert git(source, "rev-parse", "HEAD") == applied.new_commit_sha
            after = load_persistent_work_graph(source)
            aggregate = next(task for task in after.plan.tasks if task["id"] == task_id)
            allocated = aggregate["decomposition_children"]
            assert len(allocated) == 2 and not children.intersection(allocated)
            children.update(allocated)
            alpha, beta = [next(task for task in after.plan.tasks if task["id"] == key) for key in allocated]
            assert alpha["depends_on"] == parent["depends_on"]
            assert set(beta["depends_on"]) == set(parent["depends_on"]) | {alpha["id"]}
            for child_id in allocated:
                policy = validation_plan_for(source, load_committed_task(source, child_id))
                assert policy["required_test_platforms"] == ["SyntheticSource"]
            for consumer in graph.plan.tasks:
                if task_id in consumer["depends_on"]:
                    rewritten = next(task for task in after.plan.tasks if task["id"] == consumer["id"])
                    assert task_id not in rewritten["depends_on"] and set(allocated) <= set(rewritten["depends_on"])
        assert len(children) == 40
        assert children == {f"NSC-{number}" for number in range(3000, 3040)}
        assert len([task for task in after.plan.tasks if task["id"] in set(manifest["target_task_ids"]) | children]) == 1040
        # Only the latest unconsumed plan is eligible for automatic undo.
        with approved_identity_environment():
            undone = undo_graph_delta(source, plan, expected_head=applied.new_commit_sha)
        assert git(source, "rev-parse", "HEAD^{tree}") == git(source, "rev-parse", f"{head}^{{tree}}")
        assert git(source, "status", "--porcelain") == ""
        assert int(git(source, "rev-list", "--count", "HEAD")) == 22
    print(json.dumps({"suite": "thousand-decomposition", "result": "PASS", "plans_applied": 20,
        "exact_replays": 20, "dynamic_children": 40, "additive_undo_commits": 1,
        "duration_seconds": round(time.perf_counter() - started, 3)}))


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    run_with_synthetic_authority(main)
