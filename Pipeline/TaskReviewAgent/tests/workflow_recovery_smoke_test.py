#!/usr/bin/env python3
"""Pure/component F2/F4 regressions; real store, scheduler and local Git journal.

Only committed-task discovery, in-memory GitHub, architect and worker process
ports are fixtures. No provider, network, Unity, Docker or canonical assets.
NSC_WORKFLOW_RECOVERY_SOURCE selects the exact frozen parent for paired tests.
"""
from __future__ import annotations

import copy
import datetime as dt
import os
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(os.environ.get("NSC_WORKFLOW_RECOVERY_SOURCE", Path(__file__).resolve().parents[3])).resolve()
sys.path.insert(0, str(ROOT))
# The fixture is test input, including when production is selected from a parent.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow_consumer_fixture import HumanFixture, BASE
from Pipeline.TaskReviewAgent import issue_workflow_store as store
from Pipeline.TaskReviewAgent import polling_orchestrator as polling
from Pipeline.TaskReviewAgent import production_graph_snapshot as producer
from Pipeline.TaskReviewAgent import autonomous_graph_run as graph
from Pipeline.TaskReviewAgent.dispatch_plan import PlanScopedIssueBackend
from Pipeline.TaskReviewAgent.integration_gate import GitIntegrationGate, owner_identity
from Pipeline.TaskReviewAgent.tests.gate_restart_recovery_smoke_test import RecoveryFixture, p, m, FIRST, PREDECESSOR
from Pipeline.TaskReviewAgent.tests import production_graph_snapshot_smoke_test as s


class WorkflowRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(p.CONTRACTS, {PREDECESSOR: "7" * 64, FIRST: "3" * 64}))
        self.enterContext(patch.dict(os.environ, {"NSC_GATE_WAKE_HOST": "127.0.0.1"}))
        self.enterContext(patch.object(store, "pending_transition_now", lambda: BASE + dt.timedelta(seconds=180)))

    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="workflow-recovery-")
        self.addCleanup(temporary.cleanup)
        fixture = RecoveryFixture(Path(temporary.name))
        self.addCleanup(fixture.close)
        fixture.tasks[FIRST]["exclusive_resources"] = ["unity-scene:Assets/Scenes/Delivery.unity"]
        return fixture

    def pending(self, fixture, *, coherent=False):
        pending = HumanFixture(backend=fixture.backend, task=PREDECESSOR, coherent=coherent)
        fixture.tasks[PREDECESSOR] = {**p.task(PREDECESSOR), **pending.task_data()}
        return pending

    def seed_waiter(self, fixture, pending, *, known=True):
        # A durable historical waiter already exists at the audited parent.
        # Seed resource metadata using its actual CAS writer, avoiding a new-API
        # setup failure when running these same regressions on that parent.
        fixture.gate.enqueue(PREDECESSOR, ready_at=pending.body_state.updated_at_utc,
                             ready_event=pending.body_state.last_event_id)
        if known:
            oid, state = fixture.gate.read()
            state["queue"][0]["reservation"] = {
                "issue_number": pending.number, "task_contract_sha256": "7" * 64,
                "exclusive_resources": sorted(fixture.tasks[PREDECESSOR]["exclusive_resources"])}
            self.assertTrue(fixture.gate.compare_and_swap(oid, state, {"kind": "gate_fixture_reservation_bound"}))

    def test_pending_migration_wait_preserves_queue_then_admits_exactly_once(self):
        fixture = self.fixture()
        pending = self.pending(fixture)
        ready = fixture.service.find(FIRST).state
        fixture.gate.enqueue(FIRST, ready_at=ready.updated_at_utc, ready_event=ready.last_event_id)
        fixture.scheduler.reservation_observer = lambda: polling.observe_durable_integration_reservations(
            source=fixture.source, checkout_root=fixture.checkout_root, worker_id="fixture-observer",
            backend=fixture.backend, task_loader=fixture.tasks.__getitem__)
        before = fixture.gate.read()
        for _ in range(2):
            result = fixture.scheduler.poll_capacity_batch()
            self.assertFalse(result.fatal)
            self.assertEqual(fixture.gate.read(), before)
            self.assertEqual(fixture.scheduler.consecutive_observation_failures, 0)
            self.assertFalse(fixture.processes.calls)
            self.assertFalse(fixture.architect.calls)
        self.assertTrue(fixture.events("issue_pending_transition"))
        pending.issue["labels"] = [{"name": "nsc-state:agent-ready"}]
        self.assertTrue(pending.snapshot().valid)
        fixture.architect.values[FIRST] = p.advisory(
            FIRST, fixture.head, exact_paths=("Assets/Feature.cs",), shared_systems=(),
            disjointness=((PREDECESSOR, "Separate committed scene resources; no shared file edits."),))
        self.assertEqual(fixture.scheduler.poll_capacity_batch().status, "worker_launched",
                         fixture.scheduler.events.stream.getvalue())
        fixture.scheduler.poll_capacity_batch()
        self.assertEqual(len(fixture.processes.calls), 1)
        self.assertEqual(fixture.processes.calls[0][0].count(FIRST), 1)
        self.assertTrue(any(item["task_id"] == FIRST for item in fixture.gate.read()[1]["queue"]))

    def test_expired_pending_uses_existing_corruption_budget_without_launch(self):
        fixture = self.fixture()
        self.pending(fixture)
        fixture.scheduler.reservation_observer = lambda: polling.observe_durable_integration_reservations(
            source=fixture.source, checkout_root=fixture.checkout_root, worker_id="fixture-observer",
            backend=fixture.backend, task_loader=fixture.tasks.__getitem__)
        with patch.object(store, "pending_transition_now", lambda: BASE + dt.timedelta(seconds=900)):
            for index in range(fixture.scheduler.max_consecutive_observation_failures):
                result = fixture.scheduler.poll_capacity_batch()
                self.assertEqual(result.fatal, index + 1 == fixture.scheduler.max_consecutive_observation_failures)
        self.assertFalse(fixture.processes.calls)
        self.assertFalse(fixture.architect.calls)
        self.assertEqual(fixture.gate.read()[1]["queue"], [])

    def snapshotter(self, fixture):
        manifest = replace(s.manifest(), source_repository=str(fixture.source),
                           target_task_ids=tuple(sorted((FIRST, PREDECESSOR))), initial_source_commit=fixture.head,
                           initial_source_tree=m.git(fixture.source, "rev-parse", "HEAD^{tree}"))
        return producer.ProductionCoherentSnapshotter(
            manifest=manifest, scheduler=fixture.scheduler, checkout_root=fixture.checkout_root,
            worker_id="fixture-observer", backend_factory=lambda _: fixture.backend)

    def observe_real_snapshot(self, fixture):
        snapshotter = self.snapshotter(fixture)
        with patch.object(snapshotter, "_task_observations", return_value=(
                graph.TaskObservation(FIRST, "conformant"), graph.TaskObservation(PREDECESSOR, "conformant"))), \
             patch.object(producer, "load_committed_task", side_effect=lambda _, task_id, **kw: fixture.tasks[task_id]):
            return snapshotter()

    def make_unusable(self, fixture, pending, kind):
        original = copy.deepcopy(pending.issue)
        if kind == "missing":
            del fixture.backend.issues[pending.number]
        else:
            pending.issue["labels"] = []
        return original

    def test_real_snapshot_and_stage2_keep_quarantine_ownership_without_global_failure(self):
        for kind in ("missing", "malformed"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                pending = self.pending(fixture, coherent=True)
                self.seed_waiter(fixture, pending)
                self.make_unusable(fixture, pending, kind)
                observed = self.observe_real_snapshot(fixture)
                self.assertIn(PREDECESSOR, observed.reservation_task_ids)
                self.assertNotIn(PREDECESSOR, [item.task_id for item in observed.managed_issues])
                oid, durable = fixture.gate.read()
                waiter = durable["queue"][0]
                self.assertIsNotNone(waiter.get("quarantine"), "unusable waiter has no durable reconciliation disposition")
                self.assertEqual(waiter["reservation"]["exclusive_resources"], fixture.tasks[PREDECESSOR]["exclusive_resources"])
                # Same production preparation used before default Stage-2 readers.
                backend = PlanScopedIssueBackend(fixture.backend)
                prepare = getattr(fixture.admission, "prepare_backend", lambda value: value)
                backend = prepare(backend)
                service = store.IssueWorkflowService(backend=backend, task_loader=fixture.tasks.__getitem__, worker_id="stage-two")
                ready = service.list_agent_ready()
                self.assertEqual([item["workflow_state"]["task_id"] for item in ready], [FIRST])
                self.assertEqual(service.resource_conflicts(fixture.tasks[FIRST])[0], [])
                conflicting = {**fixture.tasks[FIRST], "exclusive_resources": fixture.tasks[PREDECESSOR]["exclusive_resources"]}
                self.assertTrue(service.resource_conflicts(conflicting)[0])
                with self.assertRaises(store.IssueWorkflowStoreError):
                    service.find(PREDECESSOR)
                self.assertEqual(fixture.gate.read()[0], oid, "repeat reconciliation rewrote the journal")

    def test_quarantine_reappearance_is_bound_and_reconciles_once(self):
        fixture = self.fixture()
        pending = self.pending(fixture, coherent=True)
        self.seed_waiter(fixture, pending)
        original = self.make_unusable(fixture, pending, "missing")
        self.observe_real_snapshot(fixture)
        quarantined_oid, state = fixture.gate.read()
        self.assertTrue(state["queue"][0].get("quarantine"), "missing waiter was not quarantined")
        fixture.backend.issues[pending.number] = original
        self.observe_real_snapshot(fixture)
        recovered_oid, state = fixture.gate.read()
        self.assertNotEqual(recovered_oid, quarantined_oid)
        self.assertNotIn("quarantine", state["queue"][0])
        self.assertEqual(state["event"]["kind"], "gate_waiter_reconciled")
        self.observe_real_snapshot(fixture)
        self.assertEqual(fixture.gate.read()[0], recovered_oid)
        identity = owner_identity(PREDECESSOR, "reappeared-run", "reappeared-worker")
        self.assertEqual(fixture.gate.acquire(identity)["status"], "acquired")
        resumed = fixture.gate.acquire(identity)
        self.assertTrue(resumed["resumed"])
        self.assertEqual(fixture.gate.read()[1]["queue"], [])

    def test_unknown_or_conflicting_quarantine_cannot_be_acquired_around(self):
        for known in (False, True):
            with self.subTest(known=known):
                fixture = self.fixture()
                pending = self.pending(fixture, coherent=True)
                if known:
                    fixture.tasks[FIRST]["exclusive_resources"] = fixture.tasks[PREDECESSOR]["exclusive_resources"]
                self.seed_waiter(fixture, pending, known=known)
                self.make_unusable(fixture, pending, "missing")
                self.observe_real_snapshot(fixture)
                entry = ((FIRST, "delivery_evidence", {"task": fixture.tasks[FIRST]}),)
                self.assertEqual(fixture.admission.filter(entry), ())
                self.assertEqual(fixture.gate.acquire(owner_identity(FIRST, "unrelated", "worker"))["status"], "deferred")
                self.assertIsNone(fixture.gate.read()[1]["owner"])
                self.assertEqual({item["task_id"] for item in fixture.gate.read()[1]["queue"]}, {FIRST, PREDECESSOR})

    def test_default_scheduler_launches_disjoint_delivery_once_with_quarantine_retained(self):
        for kind in ("missing", "malformed"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                pending = self.pending(fixture, coherent=True)
                self.seed_waiter(fixture, pending)
                self.make_unusable(fixture, pending, kind)
                fixture.scheduler.plan_builder = polling.build_poll_dispatch_plan
                fixture.scheduler._uses_default_plan_builder = True
                fixture.scheduler._uses_default_reservation_observer = True
                fixture.architect.values[FIRST] = p.advisory(
                    FIRST, fixture.head, exact_paths=("Assets/Feature.cs",), shared_systems=(),
                    disjointness=((PREDECESSOR, "Separate committed scene resources; no shared file edits."),))
                with ExitStack() as stack:
                    stack.enter_context(patch.object(polling, "GhIssueBackend", return_value=fixture.backend))
                    stack.enter_context(patch.object(polling, "load_committed_task",
                        side_effect=lambda _, task_id, **kw: fixture.tasks[task_id]))
                    stack.enter_context(patch.object(polling, "repo_root", side_effect=lambda value: Path(value).resolve()))
                    stack.enter_context(patch.object(polling, "source_commit_admission_snapshot",
                        side_effect=lambda source, commit: p.FixtureAdmissionSnapshot(
                            source=source, source_commit=commit, tasks=fixture.tasks,
                            policy_document={"schema_version": "1.0", "tasks": {},
                                             "decomposition_child_templates": {}})))
                    stack.enter_context(patch.object(polling.dispatch_plan_module, "_read_only_claim_observation",
                        return_value=({}, None, {"status": "fixture"}, ())))
                    # Graph fixtures intentionally have no real task-state database.
                    # Resume is still proven by the actual Stage-2 Issue readers.
                    stack.enter_context(patch.object(polling.dispatch_plan_module, "_taskcontrol_states_snapshot",
                        side_effect=polling.TaskcontrolStateObservationError("fixture has no fresh graph work")))
                    result = fixture.scheduler.poll_capacity_batch()
                    self.assertEqual(result.status, "worker_launched", fixture.scheduler.events.stream.getvalue())
                    fixture.scheduler.poll_capacity_batch()
                self.assertEqual(len(fixture.processes.calls), 1)
                self.assertEqual(fixture.scheduler.consecutive_observation_failures, 0)
                _, durable = fixture.gate.read()
                waiter = next(item for item in durable["queue"] if item["task_id"] == PREDECESSOR)
                self.assertIsNotNone(waiter.get("quarantine"))
                self.assertEqual(waiter["reservation"]["exclusive_resources"], fixture.tasks[PREDECESSOR]["exclusive_resources"])
                events = fixture.events("integration_reservations_observed")
                self.assertTrue(any(item["task_id"] == PREDECESSOR
                                    and item["workflow_state"] == "quarantined"
                                    for event in events for item in event["reservations"]))

    def test_expired_queued_pending_is_not_downgraded_into_quarantine(self):
        fixture = self.fixture()
        pending = self.pending(fixture)
        self.seed_waiter(fixture, pending)
        before = fixture.gate.read()
        with patch.object(store, "pending_transition_now", lambda: BASE + dt.timedelta(seconds=900)):
            with self.assertRaises(producer.ProductionGraphSnapshotError):
                self.observe_real_snapshot(fixture)
        self.assertEqual(fixture.gate.read(), before)
        self.assertFalse(fixture.processes.calls)
        self.assertFalse(fixture.architect.calls)

    def test_replacement_issue_cannot_inherit_quarantined_queue_authority(self):
        fixture = self.fixture()
        pending = self.pending(fixture, coherent=True)
        self.seed_waiter(fixture, pending)
        original = self.make_unusable(fixture, pending, "missing")
        self.observe_real_snapshot(fixture)
        number = pending.number + 100
        replacement = {**original, "number": number}
        fixture.backend.issues[number] = replacement
        fixture.backend.comments[number] = copy.deepcopy(fixture.backend.comments[pending.number])
        fixture.backend.issue_events[number] = copy.deepcopy(fixture.backend.issue_events[pending.number])
        observed = self.observe_real_snapshot(fixture)
        self.assertIn(PREDECESSOR, observed.reservation_task_ids)
        waiter = fixture.gate.read()[1]["queue"][0]
        self.assertTrue(waiter.get("quarantine"))
        self.assertEqual(waiter["reservation"]["issue_number"], pending.number)
        self.assertEqual(waiter["quarantine"]["observed_issue_numbers"], [number])
        self.assertNotIn(PREDECESSOR, [item.task_id for item in observed.managed_issues])

    def test_conflicting_eligible_predecessor_does_not_hide_disjoint_waiter(self):
        fixture = self.fixture()
        pending = self.pending(fixture, coherent=True)
        self.seed_waiter(fixture, pending)
        self.make_unusable(fixture, pending, "missing")
        self.observe_real_snapshot(fixture)
        fixture.tasks[FIRST]["exclusive_resources"] = fixture.tasks[PREDECESSOR]["exclusive_resources"]
        third = "NSC-703"
        HumanFixture(backend=fixture.backend, task=third, coherent=True)
        fixture.tasks[third] = {**fixture.tasks[FIRST], "id": third,
                                "task_contract_sha256": "7" * 64,
                                "exclusive_resources": ["unity-scene:Assets/Scenes/Third.unity"]}
        entries = tuple((task_id, "delivery_evidence", {"task": fixture.tasks[task_id]})
                        for task_id in (FIRST, third))
        allowed = fixture.admission.filter(entries)
        self.assertEqual([item[0] for item in allowed], [third])
        self.assertEqual(fixture.gate.acquire(owner_identity(FIRST, "conflict", "worker"))["status"], "deferred")
        self.assertEqual(fixture.gate.acquire(owner_identity(third, "safe", "worker"))["status"], "acquired")
        self.assertEqual({item["task_id"] for item in fixture.gate.read()[1]["queue"]}, {FIRST, PREDECESSOR})

    def test_downstream_repository_authority_accepts_only_known_reconciliation_wrappers(self):
        try:
            from Pipeline.TaskReviewAgent.gate_waiter_reconciliation import ReconciledIssueBackend
        except ImportError:
            self.skipTest("frozen parent has no host reconciliation wrapper")
        from Pipeline.TaskReviewAgent import downstream_pipeline as downstream
        from Pipeline.TaskReviewAgent.tests import downstream_smoke_test as binding
        original_shutil, original_run = binding._fake_gh_environment()
        self.addCleanup(binding._restore_gh_environment, original_shutil, original_run)
        with tempfile.TemporaryDirectory(prefix="workflow-repository-authority-") as temporary:
            root = Path(temporary)
            repository = "fixture-owner/workflow-recovery"
            checkout = binding._origin_checkout(root, "task", f"https://github.com/{repository}.git")
            real = store.GhIssueBackend(source_root=checkout)
            controller = object.__new__(downstream.DownstreamTaskController)
            controller.checkout = checkout
            service = SimpleNamespace(backend=real)
            controller.workflow = SimpleNamespace(issue_workflow=service)
            self.assertEqual(controller._bound_repository(), repository)
            wrapped = ReconciledIssueBackend(real, [], set())
            for backend in (wrapped, ReconciledIssueBackend(wrapped, [], set())):
                with self.subTest(kind="known", layers=1 if backend is wrapped else 2):
                    service.backend = backend
                    self.assertEqual(controller._bound_repository(), repository)
                    self.assertIs(service.backend, backend, "authority lookup must not discard resource reconciliation")
            impostor = SimpleNamespace(_backend=real, repository=repository)
            class ArbitraryReconciliationSubclass(ReconciledIssueBackend):
                pass
            memory = store.MemoryIssueBackend()
            memory.repository = repository
            for backend in (impostor, memory, ReconciledIssueBackend(impostor, [], set()),
                            ReconciledIssueBackend(memory, [], set()),
                            ArbitraryReconciliationSubclass(real, [], set())):
                with self.subTest(kind="untrusted", backend=type(backend).__name__):
                    service.backend = backend
                    with self.assertRaisesRegex(downstream.DownstreamPipelineError, "real GhIssueBackend"):
                        controller._bound_repository()
            other = binding._origin_checkout(root, "other", "https://github.com/fixture-owner/other-workflow.git")
            service.backend = ReconciledIssueBackend(store.GhIssueBackend(source_root=other), [], set())
            with self.assertRaisesRegex(downstream.DownstreamPipelineError, "mismatched repository"):
                controller._bound_repository()


if __name__ == "__main__":
    unittest.main(verbosity=2)
