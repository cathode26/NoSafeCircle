#!/usr/bin/env python3
"""Deterministic tests for checkout no-progress circuit breaking."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.goal_loop_guard import GuardedTaskController  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowEventType,
    WorkflowState,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)


TASK_ID = "NSC-020"
WORKER = "task-review-agent-guard-test"
HEAD = "1" * 40
CONTRACT_HASH = "a" * 64


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def task() -> dict:
    return {
        "id": TASK_ID,
        "title": "Guard Test",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Exercise the checkout guard.",
        "depends_on": [],
        "acceptance_criteria": [],
        "completion_gates": [],
        "exclusive_resources": [],
        "task_contract_sha256": CONTRACT_HASH,
    }


class FakeWorkflow:
    def __init__(self, service: IssueWorkflowService) -> None:
        self.issue_workflow = service
        self.worker_id = WORKER


class FakeController:
    def __init__(self, service: IssueWorkflowService, *, behavior: str) -> None:
        self.workflow = FakeWorkflow(service)
        self.task_id = TASK_ID
        self.behavior = behavior
        self.checkout_status = "conflict"

    def observe(self) -> dict:
        snapshot = self.workflow.issue_workflow.find(TASK_ID)
        assert snapshot is not None and snapshot.state is not None
        state = snapshot.state.to_dict()
        coordination_status = (
            "claimed_by_worker"
            if state["state"] == "agent_working"
            else "available_unassigned"
        )
        return {
            "environment": {"ready": True, "errors": []},
            "coordination": {
                "status": coordination_status,
                "issue_number": snapshot.issue_number,
                "issue_url": snapshot.issue_url,
                "workflow_state": state,
            },
            "checkout": {
                "status": self.checkout_status,
                "path": "C:/operator/NSC-020",
                "branch": "nsc-020-guard-test",
                "head_commit": HEAD,
                "clean": self.checkout_status == "ready",
                "reasons": (
                    ["checkout working tree is not clean"]
                    if self.checkout_status == "conflict"
                    else []
                ),
            },
            "downstream": {
                "next_action": (
                    "prepare_task_checkout"
                    if self.checkout_status != "ready"
                    else "run_authoritative_unity_tests"
                ),
                "receipt": None,
            },
        }

    def prepare_task_checkout(self) -> dict:
        if self.behavior == "blocked":
            return {
                "status": "blocked",
                "reasons": ["checkout working tree is not clean"],
            }
        if self.behavior == "no_progress":
            return {"status": "ready"}
        self.checkout_status = "ready"
        return {"status": "ready"}


def fixture(behavior: str) -> tuple[IssueWorkflowService, GuardedTaskController]:
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda _task_id: task(),
        worker_id=WORKER,
    )
    acquired = service.acquire_agent_lease(
        task=task(),
        source_head=HEAD,
        branch="nsc-020-guard-test",
        checkout_path="C:/operator/NSC-020",
        planned_approach="Exercise checkout preparation.",
        expected_validation="Observe a deterministic terminal result.",
        now="2026-08-28T10:00:00Z",
    )
    require(acquired["status"] == "acquired", "lease fixture failed")
    return service, GuardedTaskController(FakeController(service, behavior=behavior))


def assert_released(service: IssueWorkflowService) -> None:
    snapshot = service.find(TASK_ID)
    assert snapshot is not None and snapshot.state is not None
    require(snapshot.state.state is WorkflowState.AGENT_READY, "lease was not released")
    require(snapshot.events[-1].event_type is WorkflowEventType.AGENT_LEASE_RELEASED, "wrong final event")
    require(
        snapshot.events[-1].details.get("reason") == "checkout_preparation_blocked",
        "release event omitted blocker identity",
    )


def test_blocked_result_releases_lease_and_becomes_terminal() -> None:
    service, controller = fixture("blocked")
    result = controller.prepare_task_checkout()
    require(result["status"] == "blocked", "blocked result changed")
    assert_released(service)
    observation = controller.observe()
    require(observation["environment"]["ready"] is False, "guard did not become terminal")
    require(
        "checkout working tree is not clean" in observation["environment"]["errors"],
        "terminal observation omitted checkout reason",
    )


def test_no_progress_result_releases_lease() -> None:
    service, controller = fixture("no_progress")
    controller.prepare_task_checkout()
    assert_released(service)
    reasons = controller.observe()["goal_loop_guard"]["reasons"]
    require(any("without changing" in item for item in reasons), "no-progress reason missing")


def test_real_progress_keeps_active_lease() -> None:
    service, controller = fixture("progress")
    result = controller.prepare_task_checkout()
    require(result["status"] == "ready", "progress result changed")
    snapshot = service.find(TASK_ID)
    assert snapshot is not None and snapshot.state is not None
    require(snapshot.state.state is WorkflowState.AGENT_WORKING, "successful action released lease")
    observation = controller.observe()
    require(observation["environment"]["ready"] is True, "successful action became terminal")
    require(observation["checkout"]["status"] == "ready", "checkout did not advance")


def main() -> int:
    tests = (
        test_blocked_result_releases_lease_and_becomes_terminal,
        test_no_progress_result_releases_lease,
        test_real_progress_keeps_active_lease,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent goal-loop guard smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
