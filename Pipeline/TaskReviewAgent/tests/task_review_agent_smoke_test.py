#!/usr/bin/env python3
"""Deterministic regression suite for TaskReviewAgent development slices."""

from __future__ import annotations

import hashlib
import json
import subprocess
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
    GoalAction,
    ScriptedScopePlanner,
    assess_goal_state,
    run_scripted_vertical_slice,
    verify_agent_outcome,
)
from Pipeline.TaskReviewAgent.real_observation import (  # noqa: E402
    RealObservationError,
    RealTaskObserver,
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


def command_bytes(*args: str) -> bytes:
    return subprocess.run(
        args,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def command_text(*args: str) -> str:
    return command_bytes(*args).decode("utf-8").strip()


def task_state(task_id: str) -> dict:
    raw = command_text(
        sys.executable,
        "Pipeline/TaskGraph/taskcontrol.py",
        "state",
        task_id,
        "--json",
    )
    value = json.loads(raw)
    require(isinstance(value, dict), f"state for {task_id} was not an object")
    return value


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


def test_real_repository_observation() -> None:
    before_head = command_text("git", "rev-parse", "--verify", "HEAD")
    before_tree = command_text("git", "rev-parse", "HEAD^{tree}")
    before_status = command_text(
        "git",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    require(before_status == "", f"real observation test requires clean checkout: {before_status}")

    observer = RealTaskObserver(ROOT, "NSC-050")
    observation = observer.observe_goal_state()

    require(
        observation["observation_authority"] == "real_read_only",
        "real observer reported wrong authority",
    )
    require(len(observation["observation_sha256"]) == 64, "observation hash is invalid")
    environment = observation["environment"]
    task = observation["task"]
    require(environment["taskgraph_valid"] is True, "real TaskGraph validation failed")
    require(environment["controller_clean"] is True, "observer saw a dirty controller")
    require(environment["source_head"] == before_head, "observer changed source HEAD")
    require(environment["source_tree"] == before_tree, "observer changed source tree")
    require(environment["provider_auth_required"] is False, "observation widened into execution")
    require(observation["checkout"]["status"] == "not_observed", "checkout was fabricated")
    require(
        observation["repository_scope_facts"]["status"] == "not_observed",
        "scope facts were fabricated",
    )
    require(observer.action_log == ["observe_goal_state"], "unexpected observer action log")

    contract_path = "Tasks/NSC-050.yaml"
    contract_bytes = command_bytes("git", "show", f"HEAD:{contract_path}")
    contract = json.loads(contract_bytes.decode("utf-8-sig"))
    require(task["task_id"] == contract["id"], "task identity differs from committed contract")
    require(task["title"] == contract["title"], "task title differs from committed contract")
    require(
        task["contract_revision"] == contract["contract_revision"],
        "task revision differs from committed contract",
    )
    require(
        task["task_contract_sha256"] == hashlib.sha256(contract_bytes).hexdigest(),
        "task contract exact-byte hash is wrong",
    )
    require(task["depends_on"] == contract["depends_on"], "dependency list changed")

    selected_state = task_state("NSC-050")
    require(
        task["derived_state"] == selected_state["state"],
        "selected task state differs from taskcontrol",
    )
    observed_dependencies = {
        item["task_id"]: item["state"] for item in task["dependency_states"]
    }
    expected_dependencies = {
        dependency_id: task_state(dependency_id)["state"]
        for dependency_id in contract["depends_on"]
    }
    require(
        observed_dependencies == expected_dependencies,
        f"dependency states differ from taskcontrol: {observed_dependencies}",
    )
    require(
        task["dependencies_conformant"]
        == all(state == "conformant" for state in expected_dependencies.values()),
        "dependencies_conformant was not derived from exact dependency states",
    )

    assessment = assess_goal_state(observation)
    if task["dependencies_conformant"] and task["derived_state"] == "not_delivered":
        require(
            assessment.action is GoalAction.PREPARE_CHECKOUT,
            f"eligible real task did not advance to checkout: {assessment}",
        )
    else:
        require(
            assessment.action is GoalAction.NEEDS_HUMAN,
            f"non-ready real task was not stopped at human authority: {assessment}",
        )

    after_head = command_text("git", "rev-parse", "--verify", "HEAD")
    after_tree = command_text("git", "rev-parse", "HEAD^{tree}")
    after_status = command_text(
        "git",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    require(after_head == before_head, "real observation changed HEAD")
    require(after_tree == before_tree, "real observation changed the Git tree")
    require(after_status == "", f"real observation dirtied the checkout: {after_status}")


def test_real_observation_missing_task() -> None:
    observer = RealTaskObserver(ROOT, "NSC-999")
    try:
        observer.observe_goal_state()
    except RealObservationError as exc:
        require(
            "committed task contract is missing" in str(exc),
            f"unexpected missing-task error: {exc}",
        )
    else:
        raise AssertionError("missing committed task was accepted")


def main() -> int:
    tests = (
        test_task_identity,
        test_scope_contract,
        test_vertical_slice,
        test_false_success_rejected,
        test_real_repository_observation,
        test_real_observation_missing_task,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
