#!/usr/bin/env python3
"""Prove managed merge-closeout Issues remain observable after conformance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.workflow_runtime import (  # noqa: E402
    DurableIssueTaskReviewWorkflow,
)

TASK_ID = "NSC-777"
HEAD = "1" * 40
TREE = "2" * 40
CONTRACT_HASH = "a" * 64
EVIDENCE_HEAD = "3" * 40


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeBaseObserver:
    def observe_goal_state(self):
        return {
            "schema_version": "1.0",
            "request": {"task_id": TASK_ID},
            "environment": {
                "ready": True,
                "controller_clean": True,
                "taskgraph_valid": True,
                "source_head": HEAD,
                "source_tree": TREE,
            },
            "task": {
                "task_id": TASK_ID,
                "id": TASK_ID,
                "title": "Conformant task awaiting merge closeout",
                "contract_disposition": "active",
                "kind": "implementation",
                "execution_scope": "single_agent",
                "decomposition_state": "concrete",
                "derived_state": "conformant",
                "dependencies_conformant": True,
                "task_contract_sha256": CONTRACT_HASH,
            },
            "checkout": {"status": "not_observed"},
            "repository_scope_facts": {"status": "not_observed"},
            "accepted_plan_id": None,
            "execution_run": None,
            "observation_sha256": "b" * 64,
        }


class FakeIssueWorkflow:
    def observe(self, task_id: str):
        require(task_id == TASK_ID, "wrong task observed")
        return {
            "status": "agent_ready",
            "task_id": TASK_ID,
            "worker_id": "worker-two",
            "issue_number": 77,
            "issue_url": "https://example.invalid/issues/77",
            "workflow_state": {
                "schema_version": "1.0",
                "task_id": TASK_ID,
                "state": "agent_ready",
                "phase": "merge_closeout",
                "current_actor": "agent",
                "worker_id": None,
                "lease_id": None,
                "branch": "nsc-777-task",
                "head_commit": EVIDENCE_HEAD,
                "checkout_path": r"C:\NSC\NSC\NSC-777",
                "task_contract_sha256": CONTRACT_HASH,
                "state_version": 6,
                "last_event_id": "c" * 64,
                "human_handoff_commit": HEAD,
                "human_result": "pass",
                "updated_at_utc": "2026-08-27T18:00:00Z",
            },
            "managed": True,
            "valid": True,
            "reasons": [],
            "event_count": 6,
            "last_event_id": "c" * 64,
            "authority": "issue_workflow_read_write",
        }


class FakeCheckoutManager:
    checkout_path = Path(r"C:\NSC\NSC\NSC-777")

    def expected_branch(self, observation):
        return "nsc-777-task"

    def inspect(self, observation):
        coordination = observation.get("coordination") or {}
        state = coordination.get("workflow_state")
        if not isinstance(state, dict):
            # RealTaskReviewWorkflow performs an initial eligibility-gated checkout
            # observation before DurableIssueTaskReviewWorkflow restores the managed
            # closeout Issue. Model that first pass instead of assuming Issue state.
            return {
                "status": "not_observed",
                "path": str(self.checkout_path),
                "branch": None,
                "head_commit": None,
            }
        return {
            "status": "ready",
            "path": str(self.checkout_path),
            "branch": state["branch"],
            "head_commit": state["head_commit"],
        }


def test_managed_issue_survives_conformant_task_state() -> None:
    workflow = DurableIssueTaskReviewWorkflow.__new__(DurableIssueTaskReviewWorkflow)
    workflow.task_id = TASK_ID
    workflow.worker_id = "worker-two"
    workflow.base_observer = FakeBaseObserver()
    workflow.issue_workflow = FakeIssueWorkflow()
    workflow.legacy_coordination_observer = None
    workflow.checkout_manager = FakeCheckoutManager()
    workflow.action_log = []
    workflow.last_observation = None
    workflow.last_lease_result = None
    workflow.last_checkout_result = None
    workflow.last_handoff_result = None
    workflow._remote_url = lambda: "https://github.com/cathode26/NoSafeCircle.git"

    observation = workflow.observe_goal_state()
    require(
        observation["task"]["derived_state"] == "conformant",
        "fixture did not represent conformance",
    )
    require(
        observation["coordination"]["status"] == "available_unassigned",
        "managed Issue was not restored after eligibility gate",
    )
    require(
        observation["coordination"]["workflow_state"]["phase"] == "merge_closeout",
        "merge-closeout phase was lost",
    )
    require(
        observation["checkout"]["head_commit"] == EVIDENCE_HEAD,
        "evidence checkout head was not used",
    )


def main() -> int:
    test_managed_issue_survives_conformant_task_state()
    print("PASS test_managed_issue_survives_conformant_task_state")
    print("TaskReviewAgent workflow runtime tests: PASS (1 test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
