#!/usr/bin/env python3
"""Regression-only component tests with real controller/wait/gate integration.

Local Git and hashed Issue fixtures; Unity validation and worker processes are
deterministic doubles. NSC_GATE_WAKE_SOURCE selects the untouched paired base.
"""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(os.environ.get("NSC_GATE_WAKE_SOURCE",Path(__file__).resolve().parents[3])).resolve()
sys.path.insert(0,str(ROOT))
from Pipeline.TaskReviewAgent.tests import autonomous_graph_run_smoke_test as g
from Pipeline.TaskReviewAgent.tests import polling_orchestrator_smoke_test as p
from Pipeline.TaskReviewAgent.tests import integration_window_smoke_test as w
from Pipeline.TaskReviewAgent.integration_gate import GitIntegrationGate
from Pipeline.TaskReviewAgent.run_autonomous_graph import _SyntheticEvidencePump
from Pipeline.TaskReviewAgent.run_timeline import RunTimelineJournal


class GateScheduler(g.FakeScheduler):
    def __init__(self, journal):
        super().__init__()
        self.events=p.JsonEventEmitter(io.StringIO(),journal_path=journal)
        self.worker=p.FakeProcess()
        self.active_assignments={g.TASK:SimpleNamespace(process=self.worker)}
        self.worker_completion_event=threading.Event()
        self.pending=threading.Event()
        self.pending.set()
        self.integration_gate_admission=SimpleNamespace(listener=SimpleNamespace(pending=self.pending))
        self.architect_wake_listener=None
        self.architect_notification_revision=0

    _wait_for_architect_activity=p.PollingOrchestrator._wait_for_architect_activity

    def poll_capacity_batch(self):
        result=super().poll_capacity_batch()
        self.events.emit("poll_capacity_batch_completed",fatal=False,result_status="idle")
        if self.poll_calls==2:
            self.worker.returncode=0
            self.active_assignments.clear()
        return result

    def drain_active_workers(self, *, poll_seconds, stop_reason):
        self.events.emit("scheduler_draining",reason=stop_reason)
        # Preserve the running worker: the real scheduler's drain only observes.
        self.drain_calls.append(poll_seconds)
        self.drain_stop_reasons.append(stop_reason)
        return True


class GateWakeTests(unittest.TestCase):
    def run_waiter(self, root, *, failure=None, gate_reader=None):
        journal=root/"events.jsonl"
        scheduler=GateScheduler(journal)
        waiting=g.snapshot(tasks=(g.TaskObservation(g.TASK,"not_delivered"),),
            issues=(g.managed_issue(g.TASK,"human_action_required","unity_runtime_validation"),),
            active=(g.TASK,),reservations=(g.TASK,))
        manifest=g.manifest()
        pump=_SyntheticEvidencePump(manifest=manifest,source=ROOT,checkout_root=root,
            repository=manifest.github_repository,gate_reader=gate_reader)
        pump.processor=SimpleNamespace(process_one=lambda *a,**k: (_ for _ in ()).throw(AssertionError("active validation worker must be excluded from pump")))
        running=g.controller(state=waiting,scheduler=scheduler,pump=pump,
            run_timeline=RunTimelineJournal(root/"run_timeline.jsonl",run_id=manifest.run_id))
        observations=0
        def snapshot():
            nonlocal observations
            observations+=1
            if observations==2 and failure is not None:
                raise failure
            return g.snapshot(revision=2) if scheduler.poll_calls>=2 else waiting
        running.snapshotter=snapshot
        return running,scheduler,journal

    def test_real_gate_wake_reloops_and_worker_finishes(self):
        with tempfile.TemporaryDirectory(prefix="gate-wake-controller-") as text:
            running,scheduler,_=self.run_waiter(Path(text))
            result=running.run()
            self.assertEqual(result.evaluation.classification,"complete")
            self.assertEqual(scheduler.poll_calls,2)
            self.assertEqual(result.progress.wakeups_total,1)
            self.assertFalse(scheduler.drain_calls)
            self.assertEqual(scheduler.worker.kill_calls,0)
            self.assertEqual(scheduler.worker.terminate_calls,0)

    def test_exact_reintegration_validation_active_during_post_poll(self):
        errors=[]
        seen=[]
        original=GitIntegrationGate.progress
        with tempfile.TemporaryDirectory(prefix="gate-wake-reintegration-") as text:
            def progress(gate,identity,stage,**kwargs):
                result=original(gate,identity,stage,**kwargs)
                seen.append(stage)
                if stage=="automated_exact_commit_validation":
                    owner=gate.read()[1]["owner"]
                    self.assertEqual(owner["operation"]["kind"],"unity")
                    self.assertIn("automated_revalidation_pending",seen)
                    running,scheduler,_=self.run_waiter(Path(text),gate_reader=gate.read)
                    try:
                        running.run()
                    except g.AutonomousGraphRunError as exc:
                        errors.append(str(exc))
                    self.assertEqual(scheduler.worker.kill_calls,0)
                    self.assertEqual(scheduler.worker.terminate_calls,0)
                return result
            with patch.object(GitIntegrationGate,"progress",progress):
                # Real merge, invalidation, gate progress, new hash-bound exact
                # validation result and release; only Unity is a test double.
                w.AutomatedWindowTests("test_automated_reintegration_retains_gate_and_uses_exact_new_event").test_automated_reintegration_retains_gate_and_uses_exact_new_event()
        self.assertIn("automated_exact_commit_validation",seen)
        self.assertEqual(errors,[],f"outer controller rejected successful active validation: {errors}")

    def test_unexpected_snapshot_failure_is_durable_before_drain_and_reraised(self):
        with tempfile.TemporaryDirectory(prefix="gate-wake-error-") as text:
            root=Path(text)
            failure=ValueError("malformed post-poll snapshot")
            running,scheduler,journal=self.run_waiter(root,failure=failure)
            with self.assertRaises(ValueError) as caught:
                running.run()
            self.assertIs(caught.exception,failure)
            events=[json.loads(line) for line in journal.read_text().splitlines()]
            kinds=[e["event"] for e in events]
            self.assertIn("autonomous_run_error",kinds)
            self.assertLess(kinds.index("autonomous_run_error"),kinds.index("scheduler_draining"))
            error=events[kinds.index("autonomous_run_error")]
            self.assertEqual(error["exception_type"],"ValueError")
            self.assertEqual(error["stage"],"post_poll_snapshot")
            self.assertEqual(error["message"],"malformed post-poll snapshot")
            timeline=[json.loads(line) for line in (root/"run_timeline.jsonl").read_text().splitlines()]
            self.assertEqual(timeline[-1]["event"],"autonomous_run_error")
            self.assertEqual(scheduler.worker.kill_calls,0)
            self.assertEqual(scheduler.worker.terminate_calls,0)
            self.assertIsNone(scheduler.worker.poll())

    def test_unrecognized_wait_reason_still_raises(self):
        with tempfile.TemporaryDirectory(prefix="gate-wake-unknown-") as text:
            running,scheduler,_=self.run_waiter(Path(text))
            scheduler._wait_for_architect_activity=lambda _: "unrecognized"
            with self.assertRaisesRegex(g.AutonomousGraphRunError,"unsupported wait reason"):
                running.run()
            self.assertTrue(scheduler.drain_calls)
            self.assertEqual(scheduler.worker.kill_calls,0)

    def test_error_message_is_bounded_and_credentials_are_redacted(self):
        with tempfile.TemporaryDirectory(prefix="gate-wake-safe-error-") as text:
            failure=ValueError("Bearer bearer-secret token=token-secret https://user:password@host/path ghp_credential " + "x"*1500)
            running,scheduler,journal=self.run_waiter(Path(text),failure=failure)
            with self.assertRaises(ValueError) as caught:
                running.run()
            self.assertIs(caught.exception,failure)
            errors=[json.loads(line) for line in journal.read_text().splitlines()
                    if json.loads(line)["event"]=="autonomous_run_error"]
            self.assertEqual(len(errors),1)
            message=errors[0]["message"]
            self.assertLessEqual(len(message),900)
            for secret in ("bearer-secret","token-secret","user:password","ghp_credential"):
                self.assertNotIn(secret,message)
            self.assertTrue(scheduler.drain_calls)

    def test_error_journal_write_failure_preserves_drain_and_original_exception(self):
        with tempfile.TemporaryDirectory(prefix="gate-wake-telemetry-error-") as text:
            failure=ValueError("original snapshot failure")
            running,scheduler,_=self.run_waiter(Path(text),failure=failure)
            emit=scheduler.events.emit
            def failing_error_write(event,**fields):
                if event=="autonomous_run_error":
                    raise OSError("fixture journal is unavailable")
                return emit(event,**fields)
            scheduler.events.emit=failing_error_write
            with self.assertRaises(ValueError) as caught:
                running.run()
            self.assertIs(caught.exception,failure)
            self.assertTrue(scheduler.drain_calls)
            self.assertEqual(scheduler.worker.kill_calls,0)
            timeline=[json.loads(line) for line in (Path(text)/"run_timeline.jsonl").read_text().splitlines()]
            self.assertEqual(timeline[-1]["event"],"autonomous_run_error")


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import synthetic_fixture_authority
    with synthetic_fixture_authority():
        unittest.main(verbosity=2)
