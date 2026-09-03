#!/usr/bin/env python3
"""No-network safeguards for the private synthetic gauntlet approver."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.synthetic_gauntlet_approver as approver  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_only_exact_direct_gauntlet_provenance_is_accepted() -> None:
    exact = {
        "provenance": {
            "origin": "human_approved_synthetic_gauntlet",
            "gauntlet_id": approver.GAUNTLET_ID,
        }
    }
    require(approver._direct_gauntlet_task(exact), str(exact))
    wrong = json.loads(json.dumps(exact))
    wrong["provenance"]["gauntlet_id"] = "different"
    require(not approver._direct_gauntlet_task(wrong), str(wrong))


def test_private_rehearsal_preflight_refuses_public_and_production() -> None:
    original = approver._run_text

    def public(command, **_values):
        if command[0] == "git":
            if "get-url" in command:
                return "https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal.git"
            if "branch" in command:
                return "main"
            if "status" in command or "fetch" in command:
                return ""
            if "rev-parse" in command:
                return "a" * 40
            raise AssertionError(command)
        return json.dumps(
            {
                "nameWithOwner": "cathode26/NoSafeCircle-Homework-Rehearsal",
                "isPrivate": False,
                "defaultBranchRef": {"name": "main"},
            }
        )

    approver._run_text = public
    try:
        try:
            approver._require_private_rehearsal(
                ROOT, "cathode26/NoSafeCircle-Homework-Rehearsal"
            )
        except approver.SyntheticApprovalError as exc:
            require("private rehearsal" in str(exc), str(exc))
        else:
            raise AssertionError("public rehearsal was accepted")

        def private(command, **values):
            if command[0] == "gh":
                return json.dumps(
                    {
                        "nameWithOwner": "cathode26/NoSafeCircle-Homework-Rehearsal",
                        "isPrivate": True,
                        "defaultBranchRef": {"name": "main"},
                    }
                )
            return public(command, **values)

        approver._run_text = private
        require(
            approver._require_private_rehearsal(
                ROOT, "cathode26/NoSafeCircle-Homework-Rehearsal"
            )
            == "cathode26/NoSafeCircle-Homework-Rehearsal",
            "exact private rehearsal was rejected",
        )

        approver._run_text = lambda *_args, **_values: (
            "https://github.com/cathode26/NoSafeCircle.git"
        )
        try:
            approver._require_private_rehearsal(ROOT, "cathode26/NoSafeCircle")
        except approver.SyntheticApprovalError as exc:
            require("refuses production" in str(exc), str(exc))
        else:
            raise AssertionError("production repository was accepted")
    finally:
        approver._run_text = original


def test_exact_editmode_filter_is_used_before_approval() -> None:
    with tempfile.TemporaryDirectory(prefix="synthetic-approver-") as temporary:
        checkout_root = Path(temporary)
        checkout = checkout_root / "NSC-912"
        checkout.mkdir()
        state = SimpleNamespace(
            checkout_path=str(checkout),
            head_commit="a" * 40,
        )
        snapshot = SimpleNamespace(state=state)
        task = {"id": "NSC-912", "task_contract_sha256": "b" * 64}
        calls: list[tuple[str, ...]] = []
        original_plan = approver.validation_plan_for
        original_run = approver.subprocess.run
        approver.validation_plan_for = lambda *_args: {
            "required_test_platforms": ["EditMode"],
            "test_filters": {"EditMode": approver.TEST_FILTER},
        }

        def record(command, **_values):
            calls.append(tuple(command))
            return SimpleNamespace(returncode=0)

        approver.subprocess.run = record
        try:
            result = approver._run_unity_validation(
                source=ROOT,
                checkout_root=checkout_root,
                snapshot=snapshot,
                task=task,
            )
        finally:
            approver.validation_plan_for = original_plan
            approver.subprocess.run = original_run
        require(result["status"].endswith("passed"), str(result))
        command = calls[0]
        require(command[command.index("-TestPlatform") + 1] == "EditMode", str(command))
        require(command[command.index("-TestFilter") + 1] == approver.TEST_FILTER, str(command))


def test_decomposition_requires_fresh_exact_disjoint_partition() -> None:
    with tempfile.TemporaryDirectory(prefix="synthetic-decomposition-review-") as temporary:
        artifact_root = Path(temporary)
        (artifact_root / "graph_delta.json").write_text("{}\n", encoding="utf-8")
        (artifact_root / "decomposition_result.json").write_text(
            "{}\n", encoding="utf-8"
        )
        plan_id = "GDP-" + ("a" * 64)
        paths = [
            "Assets/Gauntlet/Alpha.cs",
            "Assets/Gauntlet/Alpha.cs.meta",
            "Assets/Gauntlet/Beta.cs",
            "Assets/Gauntlet/Beta.cs.meta",
        ]
        task = {
            "schema_version": "2.0",
            "id": "NSC-911",
            "contract_revision": 1,
            "exclusive_resources": [f"repo-file:{path}" for path in paths],
            "provenance": {
                "origin": "human_approved_synthetic_gauntlet",
                "gauntlet_id": approver.GAUNTLET_ID,
                "requires_decomposition": True,
                "expected_paths": paths,
            },
        }
        parent_hash = approver.semantic_json_sha256(task)

        def child(task_id: str, resources: list[str]) -> dict:
            return {
                "id": task_id,
                "parent": task["id"],
                "execution_scope": "single_agent",
                "decomposition_state": "concrete",
                "exclusive_resources": resources,
                "completion_gates": [
                    {"requirement": f"Run {approver.TEST_FILTER} for this exact commit."}
                ],
                "provenance": {
                    "origin": "progressive_decomposition",
                    "parent_contract_sha256": parent_hash,
                    "graph_delta_plan_id": plan_id,
                },
            }

        contracts = [
            child("NSC-991", [f"repo-file:{path}" for path in paths[:2]]),
            child("NSC-992", [f"repo-file:{path}" for path in paths[2:]]),
        ]
        graph = SimpleNamespace(
            plan_id=plan_id,
            proposed_child_contracts=contracts,
            to_dict=lambda: {"parent_before_hash": parent_hash},
        )
        decomposition = SimpleNamespace(
            decision="decomposed",
            children=(object(), object()),
            unsupported_assumptions=(),
            unresolved_questions=(),
            parent_task=SimpleNamespace(
                task_id=task["id"], contract_sha256=parent_hash
            ),
        )
        event = SimpleNamespace(
            event_type=approver.WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED,
            details={"artifact_root": str(artifact_root), "graph_delta_plan_id": plan_id},
        )
        snapshot = SimpleNamespace(issue_number=91, events=(event,))

        originals = (
            approver.GraphDeltaPlan,
            approver.DecompositionResult,
            approver.load_persistent_work_graph,
            approver.plan_graph_apply,
        )
        approver.GraphDeltaPlan = SimpleNamespace(from_payload=lambda _payload: graph)
        approver.DecompositionResult = SimpleNamespace(
            from_dict=lambda _payload: decomposition
        )
        approver.load_persistent_work_graph = lambda _source: object()
        approver.plan_graph_apply = lambda *_args: SimpleNamespace(
            status="fresh",
            recomputed_plan_id=plan_id,
            reason="exact deterministic match",
        )
        try:
            result = approver.review_decomposition_plan(ROOT, snapshot, task)
            require(result["child_ids"] == ["NSC-991", "NSC-992"], str(result))
            contracts[1]["exclusive_resources"] = contracts[0][
                "exclusive_resources"
            ]
            try:
                approver.review_decomposition_plan(ROOT, snapshot, task)
            except approver.SyntheticApprovalError as exc:
                require("resource ownership" in str(exc), str(exc))
            else:
                raise AssertionError("overlapping child resources were approved")
        finally:
            (
                approver.GraphDeltaPlan,
                approver.DecompositionResult,
                approver.load_persistent_work_graph,
                approver.plan_graph_apply,
            ) = originals


def test_mutation_is_delegated_to_existing_exact_approval_helper() -> None:
    source = inspect.getsource(approver._approve)
    require("pass_and_resume_task.py" in source, source)
    require('"--defer-launch"' in source, source)
    require("add_comment" not in source and "update_issue" not in source, source)


def main() -> int:
    tests = (
        test_only_exact_direct_gauntlet_provenance_is_accepted,
        test_private_rehearsal_preflight_refuses_public_and_production,
        test_exact_editmode_filter_is_used_before_approval,
        test_decomposition_requires_fresh_exact_disjoint_partition,
        test_mutation_is_delegated_to_existing_exact_approval_helper,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"synthetic gauntlet approver tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
