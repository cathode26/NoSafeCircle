#!/usr/bin/env python3
"""Regression-only abandoned gate-waiter retirement tests.

The tests use a real local bare Git remote and in-memory Issue backend. They do
not contact GitHub, mutate a production ref, run a provider, or invoke Unity.
"""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import integration_gate as gate_module  # noqa: E402
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity  # noqa: E402
from Pipeline.TaskReviewAgent.integration_gate import (  # noqa: E402
    GitIntegrationGate,
    IntegrationGateError,
    admissible_waiters,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_LABELS,
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    initial_state,
    render_event_comment,
    transition,
    update_issue_body,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import MemoryIssueBackend  # noqa: E402
from Pipeline.TaskReviewAgent.real_checkout import branch_name  # noqa: E402
from Pipeline.TaskReviewAgent.reset_task import (  # noqa: E402
    AbandonedGateWaiterRetirement,
    TaskResetError,
    main as reset_main,
)


TASK = "NSC-930"
CONTRACT = "7" * 64
READY_EVENT = "8" * 64
READY_AT = "2026-09-07T01:30:00Z"


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(f"git {args!r} failed\n{result.stdout}\n{result.stderr}")
    return result


class Fixture:
    def __init__(self, root: Path, *, head_on_main: bool = False) -> None:
        self.root = root
        self.remote = root / "remote.git"
        self.source = root / "controller"
        self.checkout_root = root / "checkouts"
        self.checkout_root.mkdir(parents=True)
        git(root, "init", "--bare", "--initial-branch=main", str(self.remote))
        git(root, "clone", str(self.remote), str(self.source))
        name, email = validated_agent_git_identity()
        git(self.source, "config", "user.name", name)
        git(self.source, "config", "user.email", email)
        (self.source / "base.txt").write_text("base\n", encoding="utf-8")
        git(self.source, "add", "--", "base.txt")
        git(self.source, "commit", "-m", "base")
        git(self.source, "push", "origin", "HEAD:refs/heads/main")
        self.main = git(self.source, "rev-parse", "HEAD").stdout.strip()
        self.task = {
            "id": TASK,
            "title": "Abandoned waiter retirement fixture",
            "task_contract_sha256": CONTRACT,
            "exclusive_resources": ["repo-file:Assets/Retired.cs"],
        }
        self.branch = branch_name(TASK, self.task["title"])
        self.recorded_checkout = self.checkout_root / "vanished-run" / TASK
        if head_on_main:
            self.candidate = self.main
        else:
            git(self.source, "switch", "-c", self.branch)
            (self.source / "candidate.txt").write_text("candidate\n", encoding="utf-8")
            git(self.source, "add", "--", "candidate.txt")
            git(self.source, "commit", "-m", "candidate")
            self.candidate = git(self.source, "rev-parse", "HEAD").stdout.strip()
            git(self.source, "switch", "main")

        self.backend = MemoryIssueBackend()
        self.backend.next_issue = 114
        self._create_closed_issue()
        self.wakes: list[dict] = []
        self.gate = GitIntegrationGate(self.source, wake=self.wakes.append)
        self.reservation = {
            "issue_number": self.issue_number,
            "task_contract_sha256": CONTRACT,
            "exclusive_resources": list(self.task["exclusive_resources"]),
        }
        self.gate.enqueue(
            TASK,
            ready_at=READY_AT,
            ready_event=READY_EVENT,
            reservation=self.reservation,
        )
        self.gate.quarantine_waiter(
            TASK,
            reason="workflow_missing_or_invalid",
            observed_issue_numbers=[self.issue_number],
        )

    def _create_closed_issue(self) -> None:
        state = initial_state(
            task_id=TASK,
            task_contract_sha256=CONTRACT,
            now="2026-09-07T01:00:00Z",
        )
        events = []
        state, event = transition(
            state,
            event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
            actor_type=WorkflowActor.AGENT,
            actor_id="fixture-worker",
            to_state=WorkflowState.AGENT_WORKING,
            details={"worker_id": "fixture-worker", "lease_id": "1" * 64},
            now="2026-09-07T01:05:00Z",
        )
        events.append(event)
        state, event = transition(
            state,
            event_type=WorkflowEventType.HUMAN_HANDOFF_CREATED,
            actor_type=WorkflowActor.AGENT,
            actor_id="fixture-worker",
            to_state=WorkflowState.HUMAN_ACTION_REQUIRED,
            to_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
            details={
                "branch": self.branch,
                "head_commit": self.candidate,
                "checkout_path": str(self.recorded_checkout),
            },
            now="2026-09-07T01:10:00Z",
        )
        events.append(event)
        state, event = transition(
            state,
            event_type=WorkflowEventType.HUMAN_VALIDATION_PASSED,
            actor_type=WorkflowActor.HUMAN,
            actor_id="cathode26",
            to_state=WorkflowState.AGENT_READY,
            to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
            details={"tested_commit": self.candidate},
            now="2026-09-07T01:20:00Z",
        )
        events.append(event)
        issue = self.backend.create_issue(
            title=f"{TASK} — Abandoned fixture",
            body=update_issue_body(f"<!-- no-safe-circle-task: {TASK} -->\n", state),
            labels=[STATE_LABELS[WorkflowState.AGENT_READY.value]],
            assignees=["cathode26"],
        )
        self.issue_number = issue["number"]
        for event in events:
            self.backend.add_comment(
                self.issue_number,
                render_event_comment(event, "Fixture event."),
            )
        self.backend.close_issue(self.issue_number)

    def operation(self, *, expected_oid: str | None = None) -> AbandonedGateWaiterRetirement:
        oid, _ = self.gate.read()
        return AbandonedGateWaiterRetirement(
            source=self.source,
            checkout_root=self.checkout_root,
            task_id=TASK,
            expected_gate_oid=expected_oid or oid,
            gate=self.gate,
            issue_backend=self.backend,
            task=self.task,
            claims_reader=lambda: [],
        )

    def duplicate_issue(self) -> None:
        original = self.backend.get_issue(self.issue_number)
        assert original is not None
        duplicate = self.backend.create_issue(
            title=original["title"],
            body=original["body"],
            labels=[item["name"] for item in original["labels"]],
            assignees=[item["login"] for item in original["assignees"]],
        )
        number = duplicate["number"]
        self.backend.comments[number] = copy.deepcopy(self.backend.comments[self.issue_number])
        self.backend.close_issue(number)


class AbandonedWaiterRetirementTests(unittest.TestCase):
    def fixture(self, **kwargs) -> Fixture:
        configured = os.environ.get("NSC_TEST_TEMP_ROOT")
        parent = Path(configured).resolve() if configured else None
        if parent is not None:
            parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(
            prefix="abandoned-waiter-",
            dir=str(parent) if parent is not None else None,
        )
        self.addCleanup(temporary.cleanup)
        return Fixture(Path(temporary.name), **kwargs)

    def test_exact_closed_abandoned_waiter_is_retired_without_completion(self) -> None:
        fixture = self.fixture()
        operation = fixture.operation()
        plan = operation.preflight()
        result = operation.apply(plan)
        self.assertEqual(result["status"], "retired")
        oid, state = fixture.gate.read()
        self.assertNotEqual(oid, plan["expected_gate_oid"])
        self.assertNotIn(TASK, [item["task_id"] for item in state["queue"]])
        event = state["event"]
        self.assertEqual(event["kind"], "gate_abandoned_waiter_retired")
        self.assertEqual(event["proof"]["issue"]["classification"], "closed_incomplete_invalid_not_complete")
        self.assertEqual(event["proof"]["issue"]["number"], 114)
        self.assertNotIn("issue_state", event)
        self.assertNotIn("merged_commit", json.dumps(event).casefold())
        self.assertNotIn("conformant_record", json.dumps(event).casefold())

    def test_cli_requires_and_scopes_exact_expected_gate_oid(self) -> None:
        cases = (
            (
                [TASK, "--retire-abandoned-gate-waiter"],
                "requires --expected-gate-oid",
            ),
            (
                [TASK, "--production-state-cleanup", "--expected-gate-oid", "a" * 40],
                "valid only with --retire-abandoned-gate-waiter",
            ),
        )
        for argv, message in cases:
            with self.subTest(argv=argv):
                output = io.StringIO()
                with patch.object(sys, "stderr", output):
                    self.assertEqual(reset_main(argv), 2)
                self.assertIn(message, output.getvalue())

    def test_open_issue_is_refused(self) -> None:
        fixture = self.fixture()
        fixture.backend.issues[fixture.issue_number]["state"] = "OPEN"
        with self.assertRaisesRegex(TaskResetError, "CLOSED"):
            fixture.operation().preflight()

    def test_remote_branch_is_refused(self) -> None:
        fixture = self.fixture()
        git(fixture.source, "push", "origin", f"{fixture.candidate}:refs/heads/{fixture.branch}")
        with self.assertRaisesRegex(TaskResetError, "remote task branch"):
            fixture.operation().preflight()

    def test_present_or_dirty_recorded_or_canonical_checkout_is_refused(self) -> None:
        for kind in ("recorded", "canonical"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                checkout = (
                    fixture.recorded_checkout
                    if kind == "recorded"
                    else fixture.checkout_root / TASK
                )
                checkout.mkdir(parents=True)
                marker = checkout / "do-not-remove.txt"
                marker.write_text("preserve this checkout\n", encoding="utf-8")
                with self.assertRaisesRegex(TaskResetError, "checkout.*exists"):
                    fixture.operation().preflight()
                self.assertTrue(marker.is_file())

    def test_candidate_already_on_main_is_refused(self) -> None:
        fixture = self.fixture(head_on_main=True)
        with self.assertRaisesRegex(TaskResetError, "contained in main"):
            fixture.operation().preflight()

    def test_gate_owner_for_task_is_refused(self) -> None:
        fixture = self.fixture()
        oid, state = fixture.gate.read()
        state["queue"][0].pop("quarantine")
        self.assertTrue(fixture.gate.compare_and_swap(
            oid, state, {"kind": "gate_waiter_reconciled", "task_id": TASK,
                         "issue_event_id": "9" * 64, "ready_event": READY_EVENT},
        ))
        from Pipeline.TaskReviewAgent.integration_gate import owner_identity
        self.assertEqual(
            fixture.gate.acquire(owner_identity(TASK, "live-run", "live-worker"))["status"],
            "acquired",
        )
        with self.assertRaisesRegex(TaskResetError, "gate owner|quarantined waiter"):
            fixture.operation().preflight()

    def test_changed_gate_oid_refuses_without_mutation(self) -> None:
        fixture = self.fixture()
        operation = fixture.operation()
        plan = operation.preflight()
        fixture.gate.enqueue("NSC-931", ready_at=READY_AT, ready_event="9" * 64)
        before = fixture.gate.read()
        with self.assertRaisesRegex((TaskResetError, IntegrationGateError), "moved|OID|CAS"):
            operation.apply(plan)
        self.assertEqual(fixture.gate.read(), before)
        self.assertIn(TASK, [item["task_id"] for item in before[1]["queue"]])

    def test_mismatched_exact_proof_is_refused(self) -> None:
        for mutation in ("reservation", "issue", "task", "contract"):
            with self.subTest(mutation=mutation):
                fixture = self.fixture()
                plan = fixture.operation().preflight()
                proof = copy.deepcopy(plan["retirement_proof"])
                if mutation == "reservation":
                    proof["retired_waiter"]["reservation"]["issue_number"] += 1
                elif mutation == "issue":
                    proof["issue"]["number"] += 1
                elif mutation == "task":
                    proof["task_id"] = "NSC-931"
                else:
                    proof["task_contract_sha256"] = "a" * 64
                before = fixture.gate.read()
                with self.assertRaises(IntegrationGateError):
                    fixture.gate.retire_abandoned_waiter(
                        expected_oid=plan["expected_gate_oid"],
                        proof=proof,
                    )
                self.assertEqual(fixture.gate.read(), before)

    def test_multiple_candidate_issues_are_refused(self) -> None:
        fixture = self.fixture()
        fixture.duplicate_issue()
        with self.assertRaisesRegex(TaskResetError, "exactly one"):
            fixture.operation().preflight()

    def test_retry_is_idempotent(self) -> None:
        fixture = self.fixture()
        operation = fixture.operation()
        plan = operation.preflight()
        first = operation.apply(plan)
        first_oid = fixture.gate.read()[0]
        second = operation.apply(plan)
        self.assertEqual(first["status"], "retired")
        self.assertEqual(second["status"], "already_retired")
        self.assertEqual(fixture.gate.read()[0], first_oid)

    def test_retirement_push_is_append_only_and_never_forced(self) -> None:
        fixture = self.fixture()
        operation = fixture.operation()
        plan = operation.preflight()
        calls = []
        original = gate_module._run_git

        def recording(repository, *args, **kwargs):
            calls.append(args)
            return original(repository, *args, **kwargs)

        with patch.object(gate_module, "_run_git", side_effect=recording):
            operation.apply(plan)
        pushes = [args for args in calls if args and args[0] == "push"]
        self.assertEqual(len(pushes), 1)
        self.assertFalse(any(arg.startswith("--force") or arg.startswith("+") for arg in pushes[0]))

    def test_retirement_unblocks_only_exactly_disjoint_waiters(self) -> None:
        fixture = self.fixture()
        fixture.gate.enqueue(
            "NSC-931", ready_at=READY_AT, ready_event="9" * 64,
            reservation={"issue_number": 31, "task_contract_sha256": "3" * 64,
                         "exclusive_resources": ["repo-file:Assets/Other.cs"]},
        )
        operation = fixture.operation()
        operation.apply(operation.preflight())
        _, state = fixture.gate.read()
        self.assertIn("NSC-931", [item["task_id"] for item in admissible_waiters(state)])
        self.assertEqual(state["event"]["next_waiter"], "NSC-931")
        self.assertEqual([item["task_id"] for item in fixture.wakes], ["NSC-931"])

        fixture.gate.enqueue(
            "NSC-932", ready_at=READY_AT, ready_event="a" * 64,
            reservation={"issue_number": 32, "task_contract_sha256": "4" * 64,
                         "exclusive_resources": ["repo-file:Assets/Shared.cs"]},
        )
        fixture.gate.quarantine_waiter(
            "NSC-932", reason="workflow_missing_or_invalid", observed_issue_numbers=[32],
        )
        fixture.gate.enqueue(
            "NSC-933", ready_at=READY_AT, ready_event="b" * 64,
            reservation={"issue_number": 33, "task_contract_sha256": "5" * 64,
                         "exclusive_resources": ["repo-file:Assets/Shared.cs"]},
        )
        fixture.gate.enqueue("NSC-934", ready_at=READY_AT, ready_event="c" * 64)
        _, state = fixture.gate.read()
        admitted = {item["task_id"] for item in admissible_waiters(state)}
        self.assertIn("NSC-931", admitted)
        self.assertNotIn("NSC-933", admitted)
        self.assertNotIn("NSC-934", admitted)


if __name__ == "__main__":
    unittest.main()
