#!/usr/bin/env python3
"""Component tests for the local opt-in GauntletView approval controller.

All durable workflow state uses MemoryIssueBackend.  No GitHub, provider,
browser, shell command, autonomous scheduler, or long-lived listener runs.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.GauntletView.approval import (  # noqa: E402
    ApprovalError,
    GauntletApprovalController,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    IssueWorkflowEvent,
    WorkflowState,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)

TASK = "NSC-777"
RUN_ID = "run-approval-a"
REPOSITORY = "owner/repository"
HEAD = "2" * 40
PLAN_A = "GDP-" + "c" * 64
PLAN_B = "GDP-" + "d" * 64


def task() -> dict:
    return {
        "id": TASK,
        "title": "Approval fixture",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Prove guarded approval.",
        "depends_on": [],
        "exclusive_resources": ["unity-scene:Assets/Scenes/Test.unity"],
        "acceptance_criteria": [{"criterion_id": "AC-001", "requirement": "Safe."}],
        "completion_gates": [{"gate_id": "VAL-001", "requirement": "Pass."}],
        "task_contract_sha256": "a" * 64,
    }


class CountingService:
    def __init__(self, service: IssueWorkflowService) -> None:
        self.service = service
        self.find_calls = 0

    @property
    def backend(self):
        return self.service.backend

    def find(self, task_id: str):
        self.find_calls += 1
        return self.service.find(task_id)

    def apply_human_result(self, **kwargs):
        return self.service.apply_human_result(**kwargs)

    def apply_decomposition_result(self, **kwargs):
        return self.service.apply_decomposition_result(**kwargs)


class ApprovalFixture:
    def __init__(self, *, decomposition: bool = False, enabled: bool = True) -> None:
        self.backend = MemoryIssueBackend()
        base = IssueWorkflowService(
            backend=self.backend,
            task_loader=lambda _task_id: task(),
            worker_id="fixture-agent",
        )
        base.acquire_agent_lease(
            task=task(),
            source_head="1" * 40,
            branch="fixture-branch" if not decomposition else "main",
            checkout_path=r"C:\fixture\checkouts\NSC-777",
            planned_approach="fixture",
            expected_validation="fixture",
            now="2026-09-07T01:00:00Z",
        )
        if decomposition:
            base.publish_decomposition_handoff(
                task_id=TASK,
                source_head="1" * 40,
                checkout_path=r"C:\fixture\checkouts\NSC-777",
                decomposition_run_id="decomposition-run-a",
                artifact_root=r"C:\fixture\artifacts",
                graph_delta_plan_id=PLAN_A,
                graph_delta_sha256="e" * 64,
                summary="Fixture plan.",
                now="2026-09-07T01:01:00Z",
            )
        else:
            base.publish_human_handoff(
                task_id=TASK,
                branch="fixture-branch",
                head_commit=HEAD,
                checkout_path=r"C:\fixture\checkouts\NSC-777",
                implementation_summary="Fixture implementation.",
                completed_checks=("Checks passed.",),
                human_steps=("Test exact commit.",),
                expected_result="Expected result.",
                now="2026-09-07T01:01:00Z",
            )
        self.service = CountingService(base)
        self.local_state = {
            "run": {"run_id": RUN_ID, "repository": REPOSITORY},
            "tasks": [{"id": TASK, "state": "human_action", "in_scope": True}],
        }
        self.identity = {
            "source": r"C:\fixture\source",
            "source_branch": "main",
            "source_commit": "1" * 40,
            "state_root": r"C:\fixture\checkouts",
            "run_id": RUN_ID,
            "run_dir": r"C:\fixture\run",
            "repository": REPOSITORY,
            "display_task_ids": [TASK],
            "descendants": "durable_decomposition_closure",
            "human_approval_enabled": enabled,
        }
        self.current_identity = dict(self.identity)
        self.wait_calls = 0
        self.wait_values: list[dict] = []
        self.notified = True
        self.controller = GauntletApprovalController(
            enabled=enabled,
            identity=self.identity,
            service=self.service,
            state_provider=lambda: self.local_state,
            identity_reader=lambda: self.current_identity,
            actor_resolver=lambda: "cathode26",
            handoff_validator=lambda **_kwargs: Path(r"C:\fixture\checkouts\NSC-777"),
            consistency_waiter=self._wait,
            wake_publisher=self._wake,
        )

    def _wait(self, *, task_id: str, **values):
        self.wait_calls += 1
        self.wait_values.append(values)
        return self.service.find(task_id)

    def _wake(self, _source: Path, **_kwargs):
        return SimpleNamespace(
            path=Path(r"C:\fixture\resume-hint.json"),
            architect_notified=self.notified,
        )

    def action(self) -> dict:
        actions = self.controller.list_actions()
        if len(actions) != 1:
            raise AssertionError(actions)
        return actions[0]


class ApprovalTests(unittest.TestCase):
    def test_default_disabled_performs_zero_reads_or_transitions(self):
        fixture = ApprovalFixture(enabled=False)
        before = fixture.service.service.find(TASK).state.state_version
        fixture.service.find_calls = 0
        self.assertEqual(fixture.controller.list_actions(), [])
        self.assertEqual(fixture.service.find_calls, 0)
        after = fixture.service.service.find(TASK).state.state_version
        self.assertEqual(after, before)

    def test_implementation_action_binds_every_exact_identity_and_passes(self):
        fixture = ApprovalFixture()
        action = fixture.action()
        self.assertEqual(action["label"], "Mark exact commit tested PASS and continue")
        self.assertEqual(action["task_id"], TASK)
        self.assertEqual(action["repository"], REPOSITORY)
        self.assertEqual(action["autonomous_run_id"], RUN_ID)
        self.assertEqual(action["workflow_state"], "human_action_required")
        self.assertEqual(action["workflow_phase"], "unity_runtime_validation")
        self.assertEqual(action["exact_commit"], HEAD)
        self.assertRegex(action["workflow_event_id"], r"^[0-9a-f]{64}$")
        result = fixture.controller.approve(action["action_token"])
        self.assertEqual(result["status"], "mutation_succeeded")
        self.assertEqual(fixture.wait_calls, 1)
        self.assertEqual(
            fixture.service.service.find(TASK).state.state,
            WorkflowState.AGENT_READY,
        )

    def test_decomposition_action_is_a_separate_plan_authority(self):
        fixture = ApprovalFixture(decomposition=True)
        action = fixture.action()
        self.assertEqual(action["label"], "Approve exact decomposition plan and continue")
        self.assertEqual(action["decomposition_plan_id"], PLAN_A)
        self.assertEqual(action["decomposition_plan_sha256"], "e" * 64)
        self.assertIsNone(action["exact_commit"])
        result = fixture.controller.approve(action["action_token"])
        self.assertEqual(result["status"], "mutation_succeeded")

    def test_double_click_is_rejected_after_one_transition(self):
        fixture = ApprovalFixture()
        token = fixture.action()["action_token"]
        fixture.controller.approve(token)
        with self.assertRaisesRegex(ApprovalError, "used or unknown"):
            fixture.controller.approve(token)

    def test_changed_commit_and_changed_plan_are_stale(self):
        for decomposition in (False, True):
            fixture = ApprovalFixture(decomposition=decomposition)
            token = fixture.action()["action_token"]
            original_find = fixture.service.find
            calls = 0

            def changed(task_id: str):
                nonlocal calls
                calls += 1
                snap = original_find(task_id)
                if calls == 1 or snap is None or snap.state is None:
                    return snap
                if decomposition:
                    event = snap.events[-1]
                    details = dict(event.details)
                    details["graph_delta_plan_id"] = PLAN_B
                    values = event.to_dict()
                    values.pop("event_id")
                    values["details"] = details
                    changed_event = IssueWorkflowEvent.create(**values)
                    changed_state = replace(
                        snap.state, last_event_id=changed_event.event_id
                    )
                    return replace(
                        snap,
                        state=changed_state,
                        events=(*snap.events[:-1], changed_event),
                    )
                state = replace(
                    snap.state,
                    head_commit="3" * 40,
                    human_handoff_commit="3" * 40,
                )
                return replace(snap, state=state)

            fixture.service.find = changed
            with self.assertRaisesRegex(ApprovalError, "stale|changed"):
                fixture.controller.approve(token)

    def test_wrong_run_blocked_failed_and_complete_local_state_are_rejected(self):
        for state in ("blocked", "failed", "complete"):
            fixture = ApprovalFixture()
            token = fixture.action()["action_token"]
            fixture.local_state["tasks"][0]["state"] = state
            with self.assertRaisesRegex(ApprovalError, "no longer actionable"):
                fixture.controller.approve(token)
        fixture = ApprovalFixture()
        token = fixture.action()["action_token"]
        fixture.local_state["run"]["run_id"] = "wrong-run"
        with self.assertRaisesRegex(ApprovalError, "run identity changed"):
            fixture.controller.approve(token)

    def test_changed_listener_identity_is_rejected_before_mutation(self):
        fixture = ApprovalFixture()
        token = fixture.action()["action_token"]
        fixture.current_identity["source_commit"] = "9" * 40
        self.assertEqual(fixture.controller.list_actions(), [])
        with self.assertRaisesRegex(ApprovalError, "listener identity changed"):
            fixture.controller.approve(token)
        self.assertEqual(
            fixture.service.service.find(TASK).state.state,
            WorkflowState.HUMAN_ACTION_REQUIRED,
        )

    def test_unauthorized_login_cannot_post_a_human_result(self):
        fixture = ApprovalFixture()
        token = fixture.action()["action_token"]
        issue_number = fixture.service.service.find(TASK).issue_number
        before_comments = list(fixture.backend.get_comments(issue_number))
        fixture.controller.actor_resolver = lambda: "not-the-human-operator"
        with self.assertRaisesRegex(ApprovalError, "not authorized"):
            fixture.controller.approve(token)
        self.assertEqual(fixture.backend.get_comments(issue_number), before_comments)
        self.assertEqual(
            fixture.service.service.find(TASK).state.state,
            WorkflowState.HUMAN_ACTION_REQUIRED,
        )

    def test_stale_workflow_version_and_event_chain_are_rejected(self):
        fixture = ApprovalFixture()
        token = fixture.action()["action_token"]
        original_find = fixture.service.find
        calls = 0

        def stale(task_id: str):
            nonlocal calls
            calls += 1
            snap = original_find(task_id)
            if calls == 1 or snap is None or snap.state is None:
                return snap
            return replace(
                snap,
                state=replace(snap.state, state_version=snap.state.state_version + 1),
            )

        fixture.service.find = stale
        with self.assertRaisesRegex(ApprovalError, "hash/event chain|stale"):
            fixture.controller.approve(token)

    def test_consistency_wait_is_bounded_and_poke_failure_is_distinct(self):
        fixture = ApprovalFixture()
        fixture.notified = False
        result = fixture.controller.approve(fixture.action()["action_token"])
        self.assertEqual(result["status"], "mutation_succeeded_poke_failed")
        self.assertEqual(fixture.wait_calls, 1)
        self.assertEqual(fixture.wait_values[0]["timeout_seconds"], 15.0)
        self.assertEqual(fixture.wait_values[0]["poll_seconds"], 0.25)


if __name__ == "__main__":
    unittest.main()
