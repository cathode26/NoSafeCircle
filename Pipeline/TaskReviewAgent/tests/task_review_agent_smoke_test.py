#!/usr/bin/env python3
"""Deterministic regression suite for the first TaskReviewAgent vertical slice."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    ExecutionScopePlan,
    HumanReviewProof,
    OutcomeStatus,
    TaskReviewContractError,
    TaskReviewOutcome,
    TaskReviewRequest,
)
from Pipeline.TaskReviewAgent.fake_tools import FakeTaskReviewTools  # noqa: E402
from Pipeline.TaskReviewAgent.goal_loop import (  # noqa: E402
    ScriptedScopePlanner,
    run_scripted_vertical_slice,
    verify_agent_outcome,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_contract_error(action, expected_text: str) -> None:
    try:
        action()
    except TaskReviewContractError as exc:
        require(expected_text in str(exc), f"unexpected contract error: {exc}")
    else:
        raise AssertionError(f"expected TaskReviewContractError containing {expected_text!r}")


def test_task_identity() -> None:
    require(TaskReviewRequest("NSC-050").task_id == "NSC-050", "valid task ID changed")
    expect_contract_error(lambda: TaskReviewRequest("nsc-050"), "NSC-###")
    expect_contract_error(lambda: TaskReviewRequest("NSC-50"), "NSC-###")


def test_scope_contract() -> None:
    plan = ExecutionScopePlan(
        ("Assets/Game/Feature.cs",),
        (),
        (),
        ("Assets/Game/Tests/FeatureTests.cs",),
    )
    require(len(plan.semantic_sha256) == 64, "scope identity is not SHA-256")
    expect_contract_error(
        lambda: ExecutionScopePlan(
            ("Assets/Game/Feature.cs",),
            (),
            ("Assets/Game/Feature.cs",),
            (),
        ),
        "disjoint",
    )
    expect_contract_error(
        lambda: ExecutionScopePlan(
            ("Assets/Game/Feature.cs.meta",),
            (),
            (),
            ("Assets/Game/Tests/FeatureTests.cs",),
        ),
        ".meta",
    )


def test_vertical_slice() -> None:
    request = TaskReviewRequest("NSC-050")
    tools = FakeTaskReviewTools()
    outcome = run_scripted_vertical_slice(request, tools, ScriptedScopePlanner())
    require(outcome.status is OutcomeStatus.HUMAN_REVIEW_READY, "goal did not reach review")
    require(outcome.proof is not None, "review-ready outcome omitted proof")
    require(outcome.proof.authority == "review_only_not_applied", "authority widened")
    require(tools.action_log.count("validate_execution_scope") == 2, "scope retry not exercised")
    require(
        tools.action_log
        == [
            "observe_goal_state",
            "prepare_task_checkout",
            "observe_goal_state",
            "validate_execution_scope",
            "observe_goal_state",
            "validate_execution_scope",
            "observe_goal_state",
            "run_execution_crew",
            "observe_goal_state",
            "verify_human_review_ready",
        ],
        f"unexpected goal action order: {tools.action_log}",
    )

    round_trip = TaskReviewOutcome.from_dict(json.loads(json.dumps(outcome.to_dict())))
    require(round_trip == outcome, "outcome round trip changed deterministic bytes")


def test_false_success_rejected() -> None:
    tools = FakeTaskReviewTools()
    request = TaskReviewRequest("NSC-050")
    outcome = run_scripted_vertical_slice(request, tools, ScriptedScopePlanner())
    assert outcome.proof is not None

    unknown = HumanReviewProof.create(
        task_id=outcome.proof.task_id,
        run_id="nsc-050-other-run",
        source_head=outcome.proof.source_head,
        task_contract_sha256=outcome.proof.task_contract_sha256,
        candidate_patch_path=outcome.proof.candidate_patch_path,
        candidate_sha256=outcome.proof.candidate_sha256,
        apply_check_passed=True,
        source_unchanged=True,
        authority="review_only_not_applied",
    )
    forged_outcome = replace(outcome, proof=unknown)
    expect_contract_error(
        lambda: verify_agent_outcome(tools, forged_outcome),
        "unknown proof_id",
    )

    tampered_payload = outcome.proof.to_dict()
    tampered_payload["candidate_sha256"] = "d" * 64
    expect_contract_error(
        lambda: HumanReviewProof.from_dict(tampered_payload),
        "identity does not match",
    )


def main() -> int:
    tests = (
        test_task_identity,
        test_scope_contract,
        test_vertical_slice,
        test_false_success_rejected,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
