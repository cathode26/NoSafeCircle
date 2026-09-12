"""Synchronous worker tests with a temporary real Git scope and fake bridge.

The fake bridge is an explicit provider seam. No paid provider, Docker process,
Unity project, scheduler, GitHub operation, or live task is used.
"""
import hashlib
import json
import os
import unittest
from unittest.mock import patch
from pathlib import Path

from Pipeline.AssistantControl import test_scope as scope_fixture
from Pipeline.AssistantControl.crew_worker import CrewWorkerError, run_worker
from Pipeline.AssistantControl.admission import REGISTRY_SCHEMA, _source_registry_paths
from Pipeline.AssistantControl.checkouts import write_record
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewReceipt


class FakeBridge:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.run_args = None
        self.result = kwargs.pop("result", None)
        self.__class__.instances.append(self)

    def require(self, run_id):
        if run_id != self.result.run_id:
            raise ValueError("wrong crew run")
        self.required_run_id = run_id
        return self.result

    def run(self, **kwargs):
        self.run_args = kwargs
        self.stop_env = os.environ.get("NSC_RUN_STOP_REQUEST_PATH")
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class CrewWorkerTests(scope_fixture.ScopePlannerTests):
    def setUp(self):
        super().setUp()
        # The Compose-file generator is independently tested without Docker.
        # This fixture isolates worker routing from a real Compose project.
        mapping = patch("Pipeline.AssistantControl.crew_worker.compose_environment",
                        return_value={"COMPOSE_FILE": "fixture-compose", "COMPOSE_PATH_SEPARATOR": os.pathsep})
        self.addCleanup(mapping.stop)
        mapping.start()
        from Pipeline.AssistantControl.scope import AssistantScopePlanner
        AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", self.valid(), lease_id="worker-lease")
        record = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        self.record = record
        self.run_id = "worker-run-1"
        self.reservation = {
            "source": str(self.checkouts.source), "task_id": "NSC-042",
            "checkout_root": str(self.checkouts.root),
            "checkout": str(self.checkouts.root / "NSC-042"),
            "run_id": self.run_id, "lease_id": "worker-lease",
            "plan_id": record["scope"]["plan_id"],
            "plan": record["scope"]["plan"],
            "source_head": record["source_commit"],
            "task_contract_sha256": record["task_contract_sha256"],
        }
        self.receipt = ExecutionCrewReceipt(
            run_id="crew-run-generated", task_id="NSC-042", lease_id="worker-lease",
            plan_id=self.reservation["plan_id"], provider="claude",
            execution_model="model-1", execution_reasoning_effort=None,
            crew_profile="full", validation_profile="full_relevant",
            source_head=self.reservation["source_head"],
            task_contract_sha256=self.reservation["task_contract_sha256"],
            crew_status="review_ready", result_path="result", result_sha256="1" * 64,
            candidate_path="patch", candidate_sha256="2" * 64,
            final_actual_changed_paths=(), returncode=0, rejection_reasons=(),
        )
        _, registry_path = _source_registry_paths(self.checkouts.source)
        write_record(registry_path, {
            "schema_version": REGISTRY_SCHEMA, "source": str(self.checkouts.source),
            "reservations": [{**self.reservation, "status": "active"}],
        })
        FakeBridge.instances.clear()

    def config(self, **extra):
        value = {"execution_authorized": True, "provider": "claude",
                 "execution_model": "model-1", "crew_profile": "full",
                 "validation_profile": "full_relevant", "timeout_seconds": 11}
        value.update(extra)
        return value

    def factory(self, result=None):
        def make(**kwargs):
            kwargs["result"] = result
            return FakeBridge(**kwargs)
        return make

    def test_direct_real_provider_entry_requires_contained_launcher(self):
        with self.assertRaisesRegex(CrewWorkerError, "contained worker launcher"):
            run_worker(self.checkouts, "NSC-042", self.reservation, self.config())
        self.assertFalse(self.checkouts.observe("NSC-042").get("worker"))

    def test_revision_feedback_arguments_reach_bridge_invocation(self):
        # Routing seam only: feedback identity/bytes are tested by its adapter.
        expected = {"retry_run_id": "previous-crew", "feedback_file": Path("fixture-feedback.txt")}
        with patch("Pipeline.AssistantControl.revision_feedback.prepare_revision_feedback", return_value=expected):
            result = run_worker(self.checkouts, "NSC-042", self.reservation,
                                self.config(), bridge_factory=self.factory(self.receipt))
        self.assertEqual("succeeded", result["worker"]["status"])
        self.assertEqual(expected, {key: FakeBridge.instances[0].run_args[key] for key in expected})

    def test_stop_during_input_preparation_never_enters_bridge(self):
        def stop_during_preparation(manager, record, reservation, config):
            Path(record["worker"]["stop_request_path"]).write_text("{}")
            return {}
        with patch("Pipeline.AssistantControl.revision_feedback.prepare_revision_feedback", side_effect=stop_during_preparation):
            result = run_worker(self.checkouts, "NSC-042", self.reservation,
                                self.config(), bridge_factory=self.factory(self.receipt))
        self.assertEqual("stopped", result["worker"]["status"])
        self.assertEqual([], FakeBridge.instances)

    def test_runs_once_with_exact_authorization_config_and_receipt(self):
        result = run_worker(self.checkouts, "NSC-042", self.reservation,
                            self.config(), bridge_factory=self.factory(self.receipt))
        worker = result["worker"]
        self.assertEqual("succeeded", worker["status"])
        self.assertEqual(self.run_id, worker["run_id"])
        self.assertEqual("crew-run-generated", worker["crew_run_id"])
        self.assertEqual("crew-run-generated", worker["receipt"]["run_id"])
        bridge = FakeBridge.instances[0]
        self.assertEqual("model-1", bridge.kwargs["execution_model"])
        self.assertEqual("assistant-crew-" + hashlib.sha256(self.run_id.encode()).hexdigest()[:20],
                         bridge.kwargs["compose_project"])
        self.assertEqual({"plan_id": self.reservation["plan_id"], "provider": "claude"}, bridge.run_args)
        self.assertEqual("crew-run-generated", bridge.required_run_id)
        self.assertEqual(worker["stop_request_path"], bridge.stop_env)
        self.assertIsNone(os.environ.get("NSC_RUN_STOP_REQUEST_PATH"))
        self.assertEqual(os.getpid(), worker["process_identity"]["pid"])

    def test_rejected_crew_receipt_is_durable_failed_worker(self):
        rejected = ExecutionCrewReceipt(**{
            **self.receipt.__dict__, "crew_status": "rejected",
            "returncode": 1, "rejection_reasons": ("max_turns",),
        })
        result = run_worker(self.checkouts, "NSC-042", self.reservation,
                            self.config(), bridge_factory=self.factory(rejected))
        self.assertEqual("failed", result["worker"]["status"])
        self.assertEqual("rejected", result["worker"]["receipt"]["crew_status"])
        self.assertIn("max_turns", result["worker"]["error"])

    def test_blocked_crew_receipt_is_not_success(self):
        blocked = ExecutionCrewReceipt(**{
            **self.receipt.__dict__, "crew_status": "blocked",
            "returncode": 1, "rejection_reasons": ("needs review",),
        })
        result = run_worker(self.checkouts, "NSC-042", self.reservation,
                            self.config(), bridge_factory=self.factory(blocked))
        self.assertEqual("failed", result["worker"]["status"])
        self.assertEqual("blocked", result["worker"]["receipt"]["crew_status"])

    def test_stop_before_start_does_not_invoke_bridge(self):
        stop = (self.checkouts.records / "worker-runs" / "NSC-042" /
                hashlib.sha256(self.run_id.encode()).hexdigest() / "stop.request")
        stop.parent.mkdir(parents=True)
        stop.write_text("stop\n")
        result = run_worker(self.checkouts, "NSC-042", self.reservation,
                            self.config(), bridge_factory=self.factory(self.receipt))
        self.assertEqual("stopped", result["worker"]["status"])
        self.assertEqual([], FakeBridge.instances)
        self.assertTrue(stop.is_file())

    def test_missing_authorization_refuses_before_bridge(self):
        with self.assertRaisesRegex(CrewWorkerError, "execution_authorized"):
            run_worker(self.checkouts, "NSC-042", self.reservation,
                       self.config(execution_authorized=False), bridge_factory=self.factory(self.receipt))
        self.assertEqual([], FakeBridge.instances)

    def test_receipt_binding_failure_is_durable_failed_state(self):
        foreign = ExecutionCrewReceipt(**{**self.receipt.__dict__, "lease_id": "foreign-lease"})
        result = run_worker(self.checkouts, "NSC-042", self.reservation,
                            self.config(), bridge_factory=self.factory(foreign))
        self.assertEqual("failed", result["worker"]["status"])
        self.assertIn("receipt identity", result["worker"]["error"])

    def test_provider_failure_is_durable_failed_state(self):
        result = run_worker(self.checkouts, "NSC-042", self.reservation,
                            self.config(), bridge_factory=self.factory(RuntimeError("fixture failure")))
        self.assertEqual("failed", result["worker"]["status"])
        self.assertIn("fixture failure", result["worker"]["error"])

    def test_copied_reservation_root_is_rejected_before_bridge(self):
        copied = dict(self.reservation, checkout_root=str(self.checkouts.root / "other-root"))
        with self.assertRaisesRegex(CrewWorkerError, "checkout_root"):
            run_worker(self.checkouts, "NSC-042", copied, self.config(),
                       bridge_factory=self.factory(self.receipt))
        self.assertEqual([], FakeBridge.instances)

    def test_keyboard_interrupt_records_stopped_then_propagates(self):
        with self.assertRaises(KeyboardInterrupt):
            run_worker(self.checkouts, "NSC-042", self.reservation,
                       self.config(), bridge_factory=self.factory(KeyboardInterrupt()))
        record = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        self.assertEqual("stopped", record["worker"]["status"])
        self.assertIn("cleanup was not confirmed", record["worker"]["error"])

    def test_bridge_constructor_failure_is_durable_failed_state(self):
        def broken(**_kwargs):
            raise RuntimeError("constructor fixture failure")
        result = run_worker(self.checkouts, "NSC-042", self.reservation,
                            self.config(), bridge_factory=broken)
        self.assertEqual("failed", result["worker"]["status"])
        self.assertIn("constructor fixture failure", result["worker"]["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
