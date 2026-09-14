"""Focused guards for the one-time NSC-089 managed Issue recovery."""

import unittest
from types import SimpleNamespace

from Pipeline.TaskReviewAgent.issue_workflow import (
    WorkflowActor, WorkflowEventType, WorkflowState, initial_state, transition,
)
from Pipeline.TaskReviewAgent.recover_nsc089 import ADDED_RESOURCES, recover, verify_contract_repair


OLD_SHA = "a" * 64
NEW_SHA = "b" * 64
WORKER = "graph-sol-20260914"
LEASE = "c" * 64


class Backend:
    def __init__(self):
        self.comments = []
        self.updates = []

    def add_comment(self, number, body):
        self.comments.append((number, body))

    def update_issue(self, number, **values):
        self.updates.append((number, values))


class Service:
    assignee = "cathode26"

    def __init__(self, *, active=False, sha=OLD_SHA):
        state = initial_state(task_id="NSC-089", task_contract_sha256=sha)
        state, acquired = transition(
            state, event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
            actor_type=WorkflowActor.AGENT, actor_id=WORKER,
            to_state=WorkflowState.AGENT_WORKING,
            details={"worker_id": WORKER, "lease_id": LEASE},
        )
        events = [acquired]
        if not active:
            state, blocked = transition(
                state, event_type=WorkflowEventType.BLOCKED,
                actor_type=WorkflowActor.AGENT, actor_id=WORKER,
                to_state=WorkflowState.BLOCKED, details={"summary": "scope stop"},
            )
            events.append(blocked)
        self.snapshot = SimpleNamespace(
            valid=True, issue_number=125, state=state, events=events,
            body="<!-- no-safe-circle-task: NSC-089 -->\nTask", labels=["nsc-state:blocked"],
        )
        self.backend = Backend()

    def find(self, task_id):
        return self.snapshot

    def verify_post_mutation_state(self, task_id, state, *, transition_name):
        assert state.state is WorkflowState.AGENT_READY
        assert state.task_contract_sha256 == NEW_SHA
        return SimpleNamespace(to_dict=lambda: {"verified": True})


class RecoveryTests(unittest.TestCase):
    def test_exact_resource_only_revision(self):
        old = {"id": "NSC-089", "contract_revision": 1, "exclusive_resources": ["repo-file:Existing.cs"]}
        new = {**old, "contract_revision": 2, "exclusive_resources": old["exclusive_resources"] + sorted(ADDED_RESOURCES)}
        verify_contract_repair(old, new)
        with self.assertRaisesRegex(RuntimeError, "exact repair"):
            verify_contract_repair(old, {**new, "exclusive_resources": old["exclusive_resources"]})
        with self.assertRaisesRegex(RuntimeError, "beyond exact"):
            verify_contract_repair(old, {**new, "acceptance_criteria": ["changed"]})

    def test_blocked_exact_issue_migrates_once(self):
        service = Service()
        result = recover(service, OLD_SHA, NEW_SHA)
        self.assertEqual(result["status"], "agent_ready")
        self.assertEqual(len(service.backend.comments), 1)
        self.assertEqual(service.backend.updates[0][1]["labels"], ["nsc-state:agent-ready"])

    def test_wrong_sha_or_active_worker_fails_before_write(self):
        for service, sha in ((Service(), "d" * 64), (Service(active=True), OLD_SHA)):
            with self.assertRaisesRegex(RuntimeError, "exact stopped"):
                recover(service, sha, NEW_SHA)
            self.assertEqual(service.backend.comments, [])
            self.assertEqual(service.backend.updates, [])


if __name__ == "__main__":
    unittest.main()
