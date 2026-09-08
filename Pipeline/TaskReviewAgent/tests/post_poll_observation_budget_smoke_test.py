#!/usr/bin/env python3
"""Regression-only pure/component tests for bounded post-poll observations.

All Git, GitHub, provider, process and clock boundaries are deterministic doubles.
NSC_OBSERVATION_SOURCE selects the unchanged paired base for red-before evidence.
No canonical asset or checkout is mutated by these tests.
"""
from __future__ import annotations

from dataclasses import replace
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(os.environ.get("NSC_OBSERVATION_SOURCE", Path(__file__).resolve().parents[3])).resolve()
sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.tests import autonomous_graph_run_smoke_test as g
from Pipeline.TaskReviewAgent.tests import production_graph_snapshot_smoke_test as s
from Pipeline.TaskReviewAgent.tests import issue_workflow_smoke_test as workflow
from Pipeline.TaskReviewAgent import autonomous_graph_run as controller_module
from Pipeline.TaskReviewAgent import production_graph_snapshot as snapshot_module
from Pipeline.TaskReviewAgent import polling_orchestrator as polling
from Pipeline.TaskReviewAgent.issue_workflow_store import IssueWorkflowStoreError


def observed_failure(error):
    """Get the real adapter's classification of a failed workflow read."""
    producer = snapshot_module.ProductionCoherentSnapshotter(
        manifest=g.manifest(), scheduler=g.FakeScheduler(), checkout_root=ROOT.parent,
        worker_id="observation-fixture", backend_factory=lambda _root: object(),
        source_refresher=lambda _root: {"before": g.HEAD, "after": g.HEAD, "changed": False},
    )
    with (
        patch.object(snapshot_module, "_capture_source_identity", return_value=s.identity()),
        patch.object(producer, "_task_observations", return_value=()),
        patch.object(snapshot_module, "observe_durable_workflows", side_effect=error),
    ):
        try:
            producer()
        except snapshot_module.ProductionGraphSnapshotError as failure:
            return failure
    raise AssertionError("fixture did not fail")


class Scheduler(g.FakeScheduler):
    def __init__(self, *, fatal=False):
        super().__init__(statuses=(("worker_failed" if fatal else "capacity_full", fatal),))
        self.active_assignments = {g.TASK: object()}
        self.stream = io.StringIO()
        self.events = polling.JsonEventEmitter(self.stream)
        self.gate_pending = False

    def poll_capacity_batch(self):
        result = super().poll_capacity_batch()
        if self.poll_calls == 2:
            self.active_assignments.clear()
        return result

    def drain_active_workers(self, *, poll_seconds, stop_reason):
        # A gate wake during fatal drain is advisory only. The controller must
        # not call poll_capacity_batch again or interpret this as admission.
        self.gate_pending = True
        return super().drain_active_workers(poll_seconds=poll_seconds, stop_reason=stop_reason)

    def records(self):
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]


def scenario(*, failures, limit=3, fatal=False):
    scheduler = Scheduler(fatal=fatal)
    waiting = g.snapshot(
        tasks=(g.TaskObservation(g.TASK, "not_delivered"),),
        issues=(g.managed_issue(g.TASK, "agent_working", "delivery_evidence"),),
        active=(g.TASK,), reservations=(g.TASK,),
    )
    run_manifest = g.manifest()
    run_manifest = replace(run_manifest, runtime_configuration=replace(
        run_manifest.runtime_configuration, max_consecutive_observation_failures=limit))
    running = g.controller(state=waiting, scheduler=scheduler, run_manifest=run_manifest)
    sequence = [waiting, *failures]
    calls = []

    def observe():
        calls.append(scheduler.poll_calls)
        if sequence:
            value = sequence.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        return g.snapshot(revision=2) if scheduler.poll_calls >= 2 else waiting

    running.snapshotter = observe
    return running, scheduler, calls


class ObservationBudgetTests(unittest.TestCase):
    def test_incident_open_no_label_snapshot_waits_instead_of_fatal_after_one_poll(self):
        # Load the candidate's fixture while its application imports still use
        # the selected base/candidate checkout for honest paired execution.
        spec = importlib.util.spec_from_file_location(
            "workflow_write_fixture", Path(__file__).with_name("pending_workflow_write_smoke_test.py"))
        fixture_module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"NSC_WORKFLOW_WRITE_SOURCE": str(ROOT)}):
            spec.loader.exec_module(fixture_module)
        fixture = fixture_module.SixEventWorkflowWriteFixture()
        original = copy.deepcopy(fixture.issue)
        task_id = fixture.state.task_id
        scheduler = Scheduler()
        scheduler.active_assignments = {task_id: object()}
        run_manifest = g.manifest(targets=(task_id,))
        waiting = g.snapshot(
            tasks=(g.TaskObservation(task_id, "not_delivered"),),
            issues=(g.managed_issue(task_id, "agent_working", "delivery_evidence"),),
            active=(task_id,), reservations=(task_id,),
        )
        running = g.controller(state=waiting, scheduler=scheduler, run_manifest=run_manifest)
        producer = snapshot_module.ProductionCoherentSnapshotter(
            manifest=run_manifest, scheduler=scheduler, checkout_root=ROOT.parent,
            worker_id="incident-observation-fixture", backend_factory=lambda _root: fixture.backend,
            source_refresher=lambda _root: {"before": g.HEAD, "after": g.HEAD, "changed": False},
        )
        calls = []
        pending = []

        def observe():
            calls.append(scheduler.poll_calls)
            if scheduler.poll_calls == 0:
                return waiting
            if scheduler.poll_calls >= 2:
                return g.snapshot(tasks=(g.TaskObservation(task_id, "conformant"),),
                                  issues=(g.managed_issue(task_id, "complete", "merge_closeout"),))
            result = producer()
            pending.append(result.pending_transition_task_ids)
            return result

        running.snapshotter = observe
        with (
            fixture.frozen_clock(),
            patch.object(snapshot_module, "_capture_source_identity", return_value=s.identity()),
            patch.object(producer, "_task_observations", return_value=waiting.tasks),
            patch.object(snapshot_module, "load_committed_task", return_value={
                "task_contract_sha256": fixture.state.task_contract_sha256, "exclusive_resources": []}),
            patch.object(snapshot_module, "_git_text", return_value=g.TREE),
            patch.object(snapshot_module, "_is_ancestor", return_value=True),
            patch.object(polling, "is_git_checkout", return_value=False),
            patch.object(polling, "read_branch_changed_paths", return_value=()),
        ):
            try:
                result = running.run()
            except snapshot_module.ProductionGraphSnapshotError as exc:
                self.assertEqual(calls, [0, 1])
                self.assertEqual(scheduler.poll_calls, 1)
                self.assertEqual(len(scheduler.drain_calls), 1)
                self.fail(
                    "one post-poll observation killed the controller and drained "
                    f"after poll 1 despite max_consecutive_observation_failures=3: {exc}"
                )
        self.assertEqual(result.evaluation.classification, "complete")
        self.assertEqual(calls, [0, 1, 1, 2])
        self.assertEqual(pending, [(task_id,), (task_id,)])
        self.assertEqual(result.progress.architect_invocations_total, 0)
        self.assertEqual(result.progress.worker_launches_total, 0)
        self.assertFalse(scheduler.drain_calls)
        self.assertEqual(fixture.issue, original)

    def workflow_skew_failure(self, *, other_corruption=False, same_issue_corruption=False):
        backend = workflow.PerIssueSkewMemoryBackend()
        tasks = workflow.seed_scan_issues(backend, count=2 if other_corruption else 1)
        first = min(backend.issues)
        backend.hidden_comment_reads[first] = workflow.NEVER_CONVERGES
        if other_corruption or same_issue_corruption:
            corrupt = max(backend.issues) if other_corruption else first
            backend.issues[corrupt]["labels"] = []
        with workflow.fake_consistency_clock():
            try:
                polling.observe_durable_workflows(
                    source=ROOT, checkout_root=ROOT.parent, worker_id="observation-test",
                    backend=backend, task_loader=lambda task_id: tasks[task_id],
                )
            except polling.IntegrationObservationError as failure:
                return failure
        self.fail("incoherent managed workflow did not fail closed")

    def test_exhausted_body_event_skew_uses_existing_narrow_transient_classifier(self):
        failure = observed_failure(self.workflow_skew_failure())
        self.assertIsInstance(failure, getattr(controller_module, "TransientGraphSnapshotError", ()))
        running, scheduler, calls = scenario(failures=[failure])
        self.assertEqual(running.run().evaluation.classification, "complete")
        self.assertEqual(calls[:3], [0, 1, 1])
        self.assertFalse(scheduler.drain_calls)
        self.assertEqual(running.progress.architect_invocations_total, 0)

    def test_corruption_beside_body_event_skew_remains_immediately_fatal(self):
        for case in ({"same_issue_corruption": True}, {"other_corruption": True}):
            with self.subTest(case=case):
                failure = observed_failure(self.workflow_skew_failure(**case))
                self.assertNotIsInstance(failure, getattr(controller_module, "TransientGraphSnapshotError", ()))
                running, scheduler, calls = scenario(failures=[failure])
                with self.assertRaises(snapshot_module.ProductionGraphSnapshotError):
                    running.run()
                self.assertEqual(calls, [0, 1])
                self.assertFalse(scheduler.wait_calls)

    def test_one_transient_post_poll_failure_retries_without_provider_or_admission(self):
        running, scheduler, calls = scenario(failures=[observed_failure(TimeoutError("read timeout"))])
        result = running.run()
        self.assertEqual(result.evaluation.classification, "complete")
        self.assertEqual(calls[:3], [0, 1, 1], "retry reran preflight/poll before a safe post-poll observation")
        self.assertEqual(scheduler.poll_calls, 2)
        self.assertEqual(result.progress.poll_cycles_total, 2)
        self.assertEqual(result.progress.architect_invocations_total, 0)
        self.assertEqual(result.progress.worker_launches_total, 0)
        self.assertFalse(scheduler.drain_calls)
        retries = [r for r in scheduler.records() if r["event"] == "autonomous_snapshot_observation_wait"]
        self.assertEqual([r["consecutive_observation_failures"] for r in retries], [1])
        self.assertEqual(retries[0]["max_consecutive_observation_failures"], 3)
        self.assertEqual(retries[0]["wait_seconds"], 5.0)

    def test_two_failures_recover_inside_configured_three_observation_budget(self):
        error = observed_failure(TimeoutError("read timeout"))
        running, scheduler, calls = scenario(failures=[error, error])
        self.assertEqual(running.run().evaluation.classification, "complete")
        self.assertEqual(calls[:4], [0, 1, 1, 1])
        self.assertFalse(scheduler.drain_calls)
        retries = [r for r in scheduler.records() if r["event"] == "autonomous_snapshot_observation_wait"]
        self.assertEqual([r["consecutive_observation_failures"] for r in retries], [1, 2])
        self.assertEqual([r["wait_seconds"] for r in retries], [5.0, 10.0])

    def test_third_failure_stops_and_drains_without_repoll_or_counter_reset(self):
        error = observed_failure(TimeoutError("read timeout"))
        running, scheduler, calls = scenario(failures=[error] * 3)
        with self.assertRaises(snapshot_module.ProductionGraphSnapshotError) as caught:
            running.run()
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, [0, 1, 1, 1])
        self.assertEqual(scheduler.poll_calls, 1)
        self.assertEqual(len(scheduler.drain_calls), 1)
        self.assertEqual(len(scheduler.wait_calls), 2)
        self.assertTrue(scheduler.gate_pending)
        self.assertEqual(running.progress.architect_invocations_total, 0)
        self.assertEqual(running.progress.worker_launches_total, 0)
        self.assertEqual(running.progress.poll_cycles_total, 1)
        self.assertEqual(scheduler.lifecycle_events[-2:], ["drain", "close"])

    def test_configured_one_failure_budget_never_retries(self):
        error = observed_failure(TimeoutError("read timeout"))
        running, scheduler, calls = scenario(failures=[error], limit=1)
        with self.assertRaises(snapshot_module.ProductionGraphSnapshotError):
            running.run()
        self.assertEqual(calls, [0, 1])
        self.assertFalse(scheduler.wait_calls)
        self.assertEqual(len(scheduler.drain_calls), 1)

    def test_genuine_fatal_cycle_never_retries_or_launches_a_woken_waiter(self):
        error = observed_failure(TimeoutError("read timeout"))
        running, scheduler, calls = scenario(failures=[error], fatal=True)
        with self.assertRaises(snapshot_module.ProductionGraphSnapshotError):
            running.run()
        self.assertEqual(calls, [0, 1])
        self.assertFalse(scheduler.wait_calls)
        self.assertEqual(scheduler.poll_calls, 1)
        self.assertTrue(scheduler.gate_pending)
        self.assertEqual(running.progress.worker_launches_total, 0)

    def test_malformed_authorized_issue_is_fatal_after_one_post_poll_observation(self):
        error = observed_failure(polling.IntegrationObservationError(
            "managed Issue #7 is invalid: workflow event hash does not match"))
        running, scheduler, calls = scenario(failures=[error])
        with self.assertRaises(snapshot_module.ProductionGraphSnapshotError) as caught:
            running.run()
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, [0, 1])
        self.assertFalse(scheduler.wait_calls)
        self.assertEqual(len(scheduler.drain_calls), 1)

    def test_only_explicit_transport_errors_receive_transient_classification(self):
        transient = getattr(controller_module, "TransientGraphSnapshotError", ())
        for error in (TimeoutError("read timeout"), ConnectionError("connection reset"),
                      subprocess.TimeoutExpired("gh", 180)):
            with self.subTest(error=type(error).__name__):
                self.assertIsInstance(observed_failure(error), transient)
        for error in (PermissionError("denied"), FileNotFoundError("missing git"),
                      IssueWorkflowStoreError("invalid JSON"),
                      polling.IntegrationObservationError("malformed authorized state")):
            with self.subTest(error=type(error).__name__):
                self.assertNotIsInstance(observed_failure(error), transient)


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import synthetic_fixture_authority
    with synthetic_fixture_authority():
        unittest.main(verbosity=2)
