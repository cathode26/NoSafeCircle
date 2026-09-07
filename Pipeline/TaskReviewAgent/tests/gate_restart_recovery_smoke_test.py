#!/usr/bin/env python3
"""Regression-only component tests for a gate waiter across controller restart.

Real scheduler admission, hashed in-memory Issues, disposable Git CAS remotes,
and loopback wake packets; worker processes and the architect are test doubles.
No provider, GitHub, Unity, Docker, or preserved incident checkout is contacted.
NSC_GATE_RECOVERY_SOURCE selects an untouched base for paired verification.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(os.environ.get("NSC_GATE_RECOVERY_SOURCE", Path(__file__).resolve().parents[3])).resolve()
sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.tests import polling_orchestrator_smoke_test as p
from Pipeline.TaskReviewAgent.tests import mainline_reintegration_smoke_test as m
from Pipeline.TaskReviewAgent.tests import architect_session_owner_smoke_test as a
from Pipeline.TaskReviewAgent.contracts import semantic_sha256
from Pipeline.TaskReviewAgent.execution_routing import resolve_execution_route, resolve_task_rigor, restrict_execution_routing_policy
from Pipeline.TaskReviewAgent.integration_gate import GitIntegrationGate, IntegrationGateError, owner_identity, send_wake
from Pipeline.TaskReviewAgent.integration_window import GateAdmission
from Pipeline.TaskReviewAgent.issue_workflow import WorkflowActor, WorkflowEventType, WorkflowState, transition, render_event_comment, update_issue_body, labels_for_state
from Pipeline.TaskReviewAgent.issue_workflow_store import IssueWorkflowService, MemoryIssueBackend

PREDECESSOR, FIRST, SECOND = "NSC-701", "NSC-702", "NSC-703"
READY_AT = "2026-09-01T00:00:00Z"


class RecoveryFixture:
    """Use the established exact-commit fixture with a fresh scheduler per restart."""

    def __init__(self, root: Path, task_ids=(FIRST,)):
        self.root = root
        old_checkout, self.base, self.task_head, self.head = m.create_fixture(root, sensitive=True)
        self.source = root / "seed"
        self.checkout_root = root / "checkouts"
        self.checkout_root.mkdir()
        self.tasks = {task_id: {**p.task(task_id), **m.task(), "id": task_id,
            "task_contract_sha256": p.CONTRACTS[task_id], "contract_path": f"Tasks/{task_id}.yaml",
            "depends_on": [], "exclusive_resources": []} for task_id in task_ids}
        self.backend = MemoryIssueBackend()
        self.service = IssueWorkflowService(backend=self.backend, worker_id="worker-a", task_loader=self.tasks.__getitem__)
        self.schedulers = []
        self.processes = p.ProcessFactory()
        self.architect = p.FakeArchitect({})
        for index, task_id in enumerate(task_ids):
            checkout = self.checkout_root / task_id
            if index == 0:
                old_checkout.rename(checkout)
            else:
                m.run("git", "clone", str(root / "remote.git"), str(checkout), cwd=root)
            branch = task_id.casefold() + "-gate-recovery"
            m.git(checkout, "switch", "-c", branch, self.task_head)
            m.git(checkout, "push", "-u", "origin", branch)
            acquired = self.service.acquire_agent_lease(task=self.tasks[task_id], source_head=self.base,
                branch=branch, checkout_path=str(checkout), planned_approach="Implement fixture",
                expected_validation="Exact fixture checks", now=READY_AT)
            assert acquired["status"] == "acquired", acquired
            self.service.publish_human_handoff(task_id=task_id, branch=branch, head_commit=self.task_head,
                checkout_path=str(checkout), implementation_summary="Feature.cs fixture",
                completed_checks=["Fixture component checks"], human_steps=["Check exact commit"],
                expected_result="Pass", now=READY_AT)
            body = f"## Human validation result\n\nResult: PASS\nTested commit: `{self.task_head}`\n"
            self.backend.add_comment(self.service.find(task_id).issue_number, body)
            applied = self.service.apply_human_result(task_id=task_id, result_body=body, actor_id="cathode26", now=READY_AT)
            assert self.service.find(task_id).state.state.value == "agent_ready", applied
        self.scheduler = self.restart()
        for task_id in task_ids:
            advisory = p.advisory(task_id, self.head, exact_paths=("Assets/Feature.cs",),
                shared_systems=(), provider_preference="claude")
            self.architect.values[task_id] = advisory
            rigor = resolve_task_rigor(advisory.execution_recommendation, task=self.tasks[task_id],
                predicted_change_surface=advisory.predicted_change_surface,
                committed_path_probe=self.scheduler._admission_snapshot(self.head).committed_path_probe())
            route = resolve_execution_route(advisory.execution_recommendation,
                restrict_execution_routing_policy(self.scheduler.routing_policy_loader(), ("claude",)), rigor=rigor)
            receipt = dict(schema_version="1.0", task_id=task_id, task_contract_sha256=p.CONTRACTS[task_id],
                source_head=self.base, repository=self.gate.repository_id,
                checkout_path=str((self.checkout_root / task_id).resolve()), issue_number=None,
                issue_event_id=None, worker_id="worker-a", run_id="fixture-prior-worker",
                recommendation=advisory.execution_recommendation.to_dict(),
                surface=advisory.predicted_change_surface.to_dict(), route=asdict(route),
                supervisor_provider="claude", provider_allowlist=["claude"])
            path = self.checkout_root / ".task-review-agent/admission-routes" / (task_id + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({**receipt, "receipt_sha256": semantic_sha256(receipt)}), encoding="utf-8")

    @property
    def admission(self):
        return self.scheduler.integration_gate_admission

    @property
    def gate(self):
        return self.admission.gate

    def restart(self, *, architect=None):
        if self.schedulers:
            self.scheduler.close_activity_listener()
        scheduler = p.PollingOrchestrator(source=self.source, checkout_root=self.checkout_root,
            scheduler_id="gate-recovery", execution_provider="claude", supervisor_provider="claude",
            provider_allowlist=("claude",), model=None, max_turns=120, max_workers=3,
            architect_min_confidence=.65, architect_runner=architect or self.architect,
            plan_builder=self.plan, task_loader=self.tasks.__getitem__, reservation_observer=lambda: (),
            source_refresher=lambda _: dict(after=self.head, remote_head=self.head),
            process_factory=self.processes, event_emitter=p.JsonEventEmitter(io.StringIO()))
        scheduler._current_admission_snapshot = p.FixtureAdmissionSnapshot(source=self.source,
            source_commit=self.head, tasks=self.tasks,
            policy_document={"schema_version": "1.0", "tasks": {}, "decomposition_child_templates": {}})
        scheduler.integration_gate_admission = GateAdmission(scheduler, service=self.service)
        scheduler.set_admission_allowlist(tuple(self.tasks))
        self.scheduler = scheduler
        self.schedulers.append(scheduler)
        return scheduler

    def plan(self, **kwargs):
        # The actual Issue queue supplies resume identities; only graph discovery
        # is replaced because these fixtures intentionally have no real TaskGraph.
        excluded = set(kwargs.get("excluded_task_ids", ()))
        ready = [value["workflow_state"] for value in self.service.list_agent_ready()
                 if value["workflow_state"]["task_id"] in self.tasks
                 and value["workflow_state"]["task_id"] not in excluded]
        if not ready:
            return p.terminal_plan(self.head, "no_safe_work")
        candidates = []
        for value in ready:
            snapshot = self.service.find(value["task_id"])
            state = snapshot.state
            candidates.append(dict(task_id=state.task_id, task_contract_sha256=state.task_contract_sha256,
                phase=state.phase.value, resume_phase=state.phase.value, issue_number=snapshot.issue_number,
                issue_url=snapshot.issue_url, branch=state.branch, commit=state.head_commit))
        return replace(p.terminal_plan(self.head, "no_safe_work"), decision="resume_existing",
            resume=candidates[0], ranked_eligible_candidates=tuple(candidates[1:]), agent_ready_count=len(candidates))

    def occupy_with_predecessor(self):
        task = p.task(PREDECESSOR)
        self.service.acquire_agent_lease(task=task, source_head=self.base, branch="predecessor-fixture",
            checkout_path=str(self.checkout_root / PREDECESSOR), planned_approach="Fixture predecessor",
            expected_validation="Fixture checks", now="2020-01-01T00:00:00Z")
        snapshot = self.service.find(PREDECESSOR)
        state, event = transition(snapshot.state, event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
            actor_type=WorkflowActor.AGENT, actor_id="worker-a", to_state=WorkflowState.AGENT_READY,
            details={"reason": "integration_gate_waiting"}, now="2020-01-01T00:00:00Z")
        self.backend.add_comment(snapshot.issue_number, render_event_comment(event, "Fixture predecessor settlement"))
        self.backend.update_issue(snapshot.issue_number, body=update_issue_body(snapshot.body, state),
                                  labels=labels_for_state(state.state, snapshot.labels))
        ready = self.service.find(PREDECESSOR).state
        self.gate.enqueue(PREDECESSOR, ready_at=ready.updated_at_utc, ready_event=ready.last_event_id)
        identity = owner_identity(PREDECESSOR, "previous-worker-run", "previous-worker")
        assert self.gate.acquire(identity)["status"] == "acquired"
        return identity

    def release(self, gate, identity):
        return gate.release(identity, reason="fixture quiescent worker settlement",
            receipt=dict(identity, schema_version="1.0", status="quiescent",
                         issue_event_id=self.service.find(identity["task_id"]).state.last_event_id))

    def settle_launched_worker(self, task_id):
        assignment = self.scheduler.active_assignments[task_id]
        identity = owner_identity(task_id, assignment.run_id, assignment.worker_id)
        assert self.gate.acquire(identity)["status"] == "acquired"
        service = IssueWorkflowService(backend=self.backend, worker_id=assignment.worker_id,
                                      task_loader=self.tasks.__getitem__)
        snapshot = service.find(task_id)
        service.acquire_agent_lease(task=self.tasks[task_id], source_head=self.head, branch=snapshot.state.branch,
            checkout_path=str(assignment.checkout_path), planned_approach="Resume fixture", expected_validation="Exact checks")
        service.publish_human_handoff(task_id=task_id, branch=snapshot.state.branch, head_commit=self.task_head,
            checkout_path=str(assignment.checkout_path), implementation_summary="Fixture revalidation handoff",
            completed_checks=["Fixture checks"], human_steps=["Review fixture"], expected_result="Pass")
        self.release(self.gate, identity)
        p.initialize_worker_run(output_root=assignment.result_artifact_path.parents[2], task_id=task_id,
            run_id=assignment.run_id, worker_id=assignment.worker_id, started_at_utc=assignment.start_time_utc)
        p.write_worker_result(run_dir=assignment.result_artifact_path.parent, run_id=assignment.run_id,
            worker_id=assignment.worker_id, task_id=task_id, source_head=assignment.source_head,
            task_contract_sha256=assignment.task_contract_sha256, terminal_status="human_action_required",
            outcome_authority="fixture_terminal_authority", issue_number=assignment.issue_number,
            exit_code=0, pid=assignment.pid)
        assignment.process.returncode = 0
        return identity

    def events(self, kind):
        return [value for scheduler in self.schedulers for line in scheduler.events.stream.getvalue().splitlines()
                if (value := json.loads(line))["event"] == kind]

    def close(self):
        for scheduler in self.schedulers:
            scheduler.close_activity_listener()


class GateRestartRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(p.CONTRACTS, {PREDECESSOR: "2" * 64, FIRST: "3" * 64, SECOND: "4" * 64}))
        self.enterContext(patch.dict(os.environ, {"NSC_GATE_WAKE_HOST": "127.0.0.1"}))

    def fixture(self, task_ids=(FIRST,)):
        temporary = tempfile.TemporaryDirectory(prefix="gate-controller-restart-")
        self.addCleanup(temporary.cleanup)
        fixture = RecoveryFixture(Path(temporary.name), task_ids)
        self.addCleanup(fixture.close)
        return fixture

    def launch_ids(self, fixture):
        return [command[command.index("--task-id") + 1] for command, _ in fixture.processes.calls]

    def assert_zero_architect(self, fixture):
        self.assertEqual(fixture.architect.calls, [])
        self.assertFalse(fixture.events("architect_started"))
        self.assertTrue(all(value["architect_invocations"] == 0
                            for value in fixture.events("integration_gate_resume_admitted")))

    def test_stopped_wake_consumer_then_restart_launches_durable_waiter_once(self):
        f = self.fixture()
        identity = f.occupy_with_predecessor()
        self.assertEqual(f.scheduler.poll_capacity_batch().status, "idle")
        old_scheduler, old_gate, old_listener = f.scheduler, f.gate, f.admission.listener
        queued_oid, queued = old_gate.read()
        self.assertEqual([value["task_id"] for value in queued["queue"]], [FIRST])
        old_scheduler.close_activity_listener()
        self.assertTrue(old_listener.closed.is_set())
        self.assertFalse(old_listener.thread.is_alive())
        self.assertEqual(f.release(old_gate, identity)["next_waiter"], FIRST)
        released_oid, released = old_gate.read()
        self.assertNotEqual(queued_oid, released_oid)
        self.assertIsNone(released["owner"])
        self.assertEqual(released["event"]["next_waiter"], FIRST)
        self.assertEqual(released["queue"], queued["queue"])
        self.assertFalse(old_listener.pending.is_set())
        self.assertFalse(f.processes.calls)

        restarted = f.restart()
        self.assertIsNot(restarted, old_scheduler)
        self.assertEqual(restarted.active_assignments, {})
        self.assertEqual(f.gate.read()[0], released_oid)
        snapshot = f.service.find(FIRST)
        self.assertEqual((snapshot.state.state.value, snapshot.state.phase.value), ("agent_ready", "delivery_evidence"))
        self.assertIsNone(snapshot.state.worker_id)
        self.assertIsNone(snapshot.state.lease_id)
        self.assertEqual(restarted.poll_capacity_batch().status, "worker_launched")
        restarted.poll_capacity_batch()
        self.assertEqual(self.launch_ids(f), [FIRST])
        self.assertEqual(set(restarted.active_assignments), {FIRST})
        self.assert_zero_architect(f)

    def test_duplicate_poke_and_fallback_poll_do_not_duplicate_assignment(self):
        f = self.fixture()
        identity = f.occupy_with_predecessor()
        f.scheduler.poll_capacity_batch()
        f.release(f.gate, identity)
        self.assertTrue(f.admission.listener.pending.wait(timeout=2))
        self.assertEqual(f.scheduler._wait_for_architect_activity(0), "integration_gate_released")
        self.assertEqual(f.scheduler.poll_capacity_batch().status, "worker_launched")
        assignment = f.scheduler.active_assignments[FIRST]
        for _ in range(2):
            waiter = f.gate.read()[1]["queue"][0]
            send_wake(dict(waiter, domain=f.gate.domain))
            self.assertTrue(f.admission.listener.pending.wait(timeout=2))
            self.assertEqual(f.scheduler._wait_for_architect_activity(0), "integration_gate_released")
            f.scheduler.poll_capacity_batch()
        self.assertEqual(f.scheduler._wait_for_architect_activity(0), "fallback_elapsed")
        f.scheduler.poll_capacity_batch()
        self.assertIs(f.scheduler.active_assignments[FIRST], assignment)
        self.assertEqual(self.launch_ids(f), [FIRST])
        self.assert_zero_architect(f)

    def test_restart_preserves_all_waiters_and_equal_time_order(self):
        # Reverse discovery order proves the gate's ready-time/task-ID ordering.
        f = self.fixture((SECOND, FIRST))
        identity = f.occupy_with_predecessor()
        f.scheduler.poll_capacity_batch()
        old_gate = f.gate
        expected = [FIRST, SECOND]
        queued = old_gate.read()[1]["queue"]
        self.assertEqual([value["task_id"] for value in queued], expected)
        self.assertEqual(queued[0]["ready_at"], queued[1]["ready_at"])
        f.scheduler.close_activity_listener()
        f.release(old_gate, identity)
        f.restart()
        self.assertEqual(f.scheduler.poll_capacity_batch().status, "worker_launched")
        self.assertEqual(self.launch_ids(f), [FIRST])
        original_owner = f.settle_launched_worker(FIRST)
        self.assertEqual(f.scheduler.poll_capacity_batch().status, "worker_launched")
        self.assertEqual(self.launch_ids(f), expected)
        self.assertEqual(set(f.scheduler.active_assignments), {SECOND})
        successor = f.scheduler.active_assignments[SECOND]
        successor_owner = owner_identity(SECOND, successor.run_id, successor.worker_id)
        self.assertEqual(f.gate.acquire(successor_owner)["status"], "acquired")
        with self.assertRaises(IntegrationGateError):
            f.release(f.gate, original_owner)
        self.assertEqual(f.gate.read()[1]["owner"]["lease_id"], successor_owner["lease_id"])
        f.scheduler.poll_capacity_batch()
        self.assertEqual(self.launch_ids(f), expected)
        self.assert_zero_architect(f)

    def test_fatal_drain_receives_release_without_admitting_waiter(self):
        f = self.fixture()
        identity = f.occupy_with_predecessor()
        f.scheduler.poll_capacity_batch()
        process = p.FakeProcess()
        p.add_result_active(f.scheduler, root=f.root, task_id=PREDECESSOR, process=process,
                            terminal_status="completed", artifact_exit_code=0)
        before = f.scheduler.active_assignments[PREDECESSOR]
        sleeps = []
        def release_during_drain(seconds):
            sleeps.append(seconds)
            self.assertIs(f.scheduler.active_assignments[PREDECESSOR], before)
            self.assertFalse(f.processes.calls)
            f.release(f.gate, identity)
            self.assertTrue(f.admission.listener.pending.wait(timeout=2))
            process.returncode = 0
        with patch.object(p.scheduler_module.time, "sleep", side_effect=release_during_drain), \
                patch.object(f.scheduler, "poll_capacity_batch", side_effect=AssertionError("fatal drain admitted work")):
            self.assertTrue(f.scheduler.drain_active_workers(poll_seconds=.01, stop_reason="unsafe graph observation"))
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(f.scheduler.active_assignments, {})
        self.assertTrue(f.admission.listener.pending.is_set())
        self.assertEqual([value["task_id"] for value in f.gate.read()[1]["queue"]], [FIRST])
        self.assertEqual((process.kill_calls, process.terminate_calls), (0, 0))
        self.assertFalse(f.events("worker_failed"))
        self.assertEqual(self.launch_ids(f), [])
        self.assert_zero_architect(f)

    def test_restart_requires_exact_scheduler_lock_and_retires_interrupted_architect(self):
        for phase in ("between_assignments", "assigned"):
            with self.subTest(phase=phase):
                f = self.fixture()
                store = a.JsonArchitectSessionStore(f.root / "architect-session")
                initial = a.SessionLifecycleState.create(provider_identifier=a.PROVIDER,
                    role=a.ROLE, session_id=a.SESSION_A, session_class="architect")
                state = replace(initial, phase=phase, sequence=1,
                    active_assignment_id="prior-architect-cycle" if phase == "assigned" else None,
                    active_workload_class="admission_cycle" if phase == "assigned" else None)
                store.save_initial(state, a.COMPATIBILITY)
                runner = a.FakeArchitectRunner()
                owner = a.owner(f.root / "architect-session", runner)
                scheduler = f.restart(architect=owner)
                lock = p.SchedulerLock(p.scheduler_lock_path(checkout_root=f.checkout_root))
                with self.assertRaisesRegex(p.scheduler_module.PollingOrchestratorError, "exact acquired scheduler lock"):
                    scheduler.reconcile_interrupted_architect_session(lock=lock)
                self.assertEqual(store.load(), state)
                with lock:
                    contender = p.SchedulerLock(lock.path)
                    with self.assertRaises(p.SchedulerAlreadyActive):
                        contender.acquire()
                    changed = scheduler.reconcile_interrupted_architect_session(lock=lock)
                    self.assertEqual(changed, phase == "assigned")
                    self.assertEqual(scheduler.poll_capacity_batch().status, "worker_launched")
                    scheduler.poll_capacity_batch()
                self.assertEqual(runner.bindings, [])
                if phase == "assigned":
                    self.assertEqual(owner.state.retirement_reason, "interrupted_assignment")
                    self.assertEqual(owner.state.phase, "retired")
                    self.assertEqual(f.events("architect_session_reconciled")[0]["assignment_id"], "prior-architect-cycle")
                else:
                    self.assertEqual(owner.state, state)
                self.assertEqual(self.launch_ids(f), [FIRST])
                self.assert_zero_architect(f)


if __name__ == "__main__":
    unittest.main(verbosity=2)
