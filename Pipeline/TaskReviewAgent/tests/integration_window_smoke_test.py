#!/usr/bin/env python3
"""Gate regressions through real reintegration, managed Issue transitions and host loop.

Pure/component + serialization/migration regression tests. Unity/CI services
are bounded test doubles; branches, leases, hashed Issue events and Git refs are real.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import threading

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from Pipeline.TaskReviewAgent.tests import mainline_reintegration_smoke_test as mainline
from Pipeline.TaskReviewAgent.tests import automated_validation_downstream_smoke_test as automated
from Pipeline.TaskReviewAgent.integration_gate import GitIntegrationGate, IntegrationGateError, owner_identity
from Pipeline.TaskReviewAgent.integration_window import IntegrationWindow, GateAdmission
from Pipeline.TaskReviewAgent.downstream_runtime import ResumableDownstreamTaskController
from Pipeline.TaskReviewAgent.downstream_pipeline import DownstreamPipelineError
from Pipeline.TaskReviewAgent.downstream_determinism import _authoritative_automated_validation
from Pipeline.TaskReviewAgent.mainline_reintegration import _integrate_current_main
from Pipeline.TaskReviewAgent.openai_downstream import run_openai_downstream_pipeline
from Pipeline.TaskReviewAgent.contracts import TaskReviewRequest
from Pipeline.TaskReviewAgent.run_pipeline_agent import _worker_terminal_contract
from Pipeline.TaskReviewAgent.issue_workflow import WorkflowState


class NeverProvider:
    def __init__(self):
        self.calls = 0

    def decide(self, **kwargs):
        self.calls += 1
        raise AssertionError("gate waiting must never invoke a provider")


class ReadyWorkflow(mainline.FakeWorkflow):
    def observe_goal_state(self):
        value = super().observe_goal_state()
        value["environment"].update(ready=True, errors=[], controller_clean=True, taskgraph_valid=True)
        return value


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nsc-window-")
        self.root = Path(self.temp.name)
        checkout, base, task, main = mainline.create_fixture(self.root, sensitive=False)
        self.service, _ = mainline.prepare_service(checkout, base, task, main)
        workflow = ReadyWorkflow(service=self.service, checkout=checkout, main_head=main, worker_id="worker-a")
        self.service.backend.add_comment(self.service.find(mainline.TASK_ID).issue_number,
                                        f"## Human validation result\n\nResult: PASS\nTested commit: `{task}`\n")
        workflow.base_observer = SimpleNamespace(root=checkout)
        workflow.checkout_manager = SimpleNamespace(checkout_path=checkout)
        workflow.task_id = mainline.TASK_ID
        self.controller = ResumableDownstreamTaskController(workflow=workflow)
        from Pipeline.TaskReviewAgent.downstream_resilience import _release_active_lease
        _release_active_lease(self.controller, reason="fixture_ready_for_gate", details={"action": "fixture_setup"})
        self.window = self.controller.integration_window
        self.window.bind_run("real-test-run")
        self.gate = self.window.gate

    def tearDown(self):
        self.temp.cleanup()

    def acquire(self):
        self.assertEqual(self.window.checkpoint(self.controller.observe())["status"], "continue")
        self.assertTrue(self.window.held)
        if self.service.find(mainline.TASK_ID).state.state is WorkflowState.AGENT_READY:
            self.controller.workflow.acquire_agent_lease(planned_approach="Exact gated delivery", expected_validation="Exact commit tests")

    def successor(self):
        identity = owner_identity("NSC-778", "successor-run", "successor-worker")
        self.gate.enqueue("NSC-778", ready_at="2026-09-07T00:00:00Z", ready_event="a" * 64)
        return identity

    def test_real_host_loop_defers_without_provider_or_fatal(self):
        owner = owner_identity("NSC-001", "other-run", "other-controller")
        self.gate.enqueue("NSC-001", ready_at="2026-09-01T00:00:00Z", ready_event="1" * 64)
        self.gate.acquire(owner)
        # Pipeline must bind the same durable run identity through its progress.
        from Pipeline.TaskReviewAgent.progress import NullProgress
        progress = NullProgress()
        progress.run_id = "real-test-run"
        provider = NeverProvider()
        original_head = mainline.git(self.controller.checkout, "rev-parse", "HEAD")
        result = run_openai_downstream_pipeline(TaskReviewRequest(mainline.TASK_ID), self.controller,
                                              decision_provider=provider, progress=progress, max_turns=4)
        self.assertEqual(result["status"], "integration_gate_waiting")
        self.assertEqual(_worker_terminal_contract(result["status"]), ("blocked", 3))
        self.assertEqual(provider.calls, 0)
        self.assertEqual(mainline.git(self.controller.checkout, "rev-parse", "HEAD"), original_head)
        self.assertEqual(self.service.find(mainline.TASK_ID).state.state, WorkflowState.AGENT_READY)

    def test_human_reintegration_releases_and_old_pass_stays_invalid(self):
        self.acquire()
        next_owner = self.successor()
        old_head = mainline.git(self.controller.checkout, "rev-parse", "HEAD")
        self.window.before_action("integrate_current_main")
        result = self.controller.integrate_current_main()
        self.window.after_action("integrate_current_main")
        self.assertEqual(result["status"], "human_revalidation_required")
        observation = self.controller.observe()
        self.window.checkpoint(observation)
        state = self.service.find(mainline.TASK_ID).state
        self.assertIsNone(state.human_result)
        self.assertNotEqual(state.head_commit, old_head)
        self.assertFalse(self.window.held)
        self.assertEqual(self.gate.acquire(next_owner)["status"], "acquired")
        with self.assertRaises(Exception):
            self.service.apply_human_result(task_id=mainline.TASK_ID,
                                           result_body=f"## Human validation result\n\nResult: PASS\nTested commit: `{old_head}`\n",
                                           actor_id="cathode26")

    def test_verified_test_ci_and_provider_failure_release(self):
        for action, error in (("run_authoritative_unity_test", "authoritative tests failed"),
                              ("inspect_or_merge_pull_request", "pull-request checks failed: build"),
                              ("pipeline", "provider unavailable")):
            with self.subTest(action=action):
                if self.window.finished:
                    # New worker run resumes from the service's agent_ready event.
                    self.window = IntegrationWindow(self.controller)
                    self.window.bind_run(action)
                self.acquire()
                if action != "pipeline":
                    self.window.before_action(action)
                self.window.failure(DownstreamPipelineError(error), action=action)
                self.assertIsNone(self.gate.read()[1]["owner"])

    def test_uncertain_merge_and_interruption_quarantine(self):
        self.acquire()
        next_owner = self.successor()
        self.window.before_action("inspect_or_merge_pull_request")
        self.window.failure(KeyboardInterrupt(), action="inspect_or_merge_pull_request")
        self.assertEqual(self.gate.read()[1]["owner"]["status"], "quarantined")
        self.assertEqual(self.gate.acquire(next_owner)["status"], "deferred")

    def test_missing_or_mismatched_durable_completion_never_releases(self):
        self.acquire()
        self.controller.state["merged_commit"] = "f" * 40
        with self.assertRaises(IntegrationGateError):
            self.window.settle(self.controller.observe(), "completed")
        self.assertIsNotNone(self.gate.read()[1]["owner"])

    def test_completed_receipt_matches_exact_durable_event_and_owner(self):
        self.acquire()
        from Pipeline.TaskReviewAgent.downstream_issue import DownstreamIssueCoordinator
        coordinator = DownstreamIssueCoordinator(self.service)
        state = self.service.find(mainline.TASK_ID).state
        coordinator.accept_unchanged_delivery_after_human_pass(
            task_id=mainline.TASK_ID, branch=state.branch, head_commit=state.head_commit,
            checkout_path=str(self.controller.checkout), draft_path="fixture-draft.json", draft_sha256="d" * 64,
            proposal_path="fixture-proposal.json", proposal_sha256="e" * 64)
        self.controller.workflow.acquire_agent_lease(planned_approach="Exact closeout", expected_validation="Verified main")
        merged = mainline.git(self.controller.checkout, "rev-parse", "origin/main")
        coordinator.complete(task_id=mainline.TASK_ID, pull_request_url="https://example.invalid/pull/1",
                             pull_request_number=1, merged_commit=merged, conformant_record_id="fixture-conformant")
        self.controller.state["merged_commit"] = "f" * 40
        with self.assertRaisesRegex(IntegrationGateError, "does not match"):
            self.window.settle(self.controller.observe(), "completed")
        self.assertIsNotNone(self.gate.read()[1]["owner"])
        self.controller.state["merged_commit"] = merged
        self.window.settle(self.controller.observe(), "completed")
        _, journal = self.gate.read()
        self.assertIsNone(journal["owner"])
        self.assertEqual(journal["event"]["receipt"]["verified_main"], merged)

    def test_legacy_active_owner_fails_closed_without_mutation(self):
        self.controller.workflow.acquire_agent_lease(planned_approach="Old run", expected_validation="Existing tests")
        before = self.service.find(mainline.TASK_ID).state.to_dict()
        with self.assertRaisesRegex(IntegrationGateError, "legacy downstream owner"):
            self.window.checkpoint(self.controller.observe())
        self.assertEqual(self.service.find(mainline.TASK_ID).state.to_dict(), before)
        self.assertIsNone(self.gate.read()[1]["owner"])

    def test_scheduler_pending_set_waits_without_architect_and_keeps_implementation(self):
        events = []
        scheduler = SimpleNamespace(source=self.controller.checkout, scheduler_id="controller-b",
                                    worker_completion_event=threading.Event(),
                                    events=SimpleNamespace(emit=lambda kind, **values: events.append((kind, values))))
        admission = GateAdmission(scheduler, service=self.service)
        owner = owner_identity("NSC-001", "other-run", "other-worker")
        self.gate.enqueue("NSC-001", ready_at="2026-09-01T00:00:00Z", ready_event="1" * 64)
        self.gate.acquire(owner)
        delivery = ({"task_id": mainline.TASK_ID}, "delivery_evidence", {"task": {"id": mainline.TASK_ID}})
        implementation = ({"task_id": "NSC-779"}, None, {"task": {"id": "NSC-779"}})
        try:
            self.assertEqual(admission.filter((delivery, implementation)), (implementation,))
            listener = admission.listener
            journal = self.gate.read()[0]
            for _ in range(3):
                self.assertEqual(admission.filter((delivery, implementation)), (implementation,))
                self.assertIs(admission.listener, listener)
                self.assertEqual(self.gate.read()[0], journal)
            self.gate.release(owner, reason="completed", receipt=dict(owner, schema_version="1.0", status="completed",
                                                                      issue_event_id="f" * 64, verified_main=mainline.git(self.controller.checkout, "rev-parse", "origin/main")))
            self.assertTrue(scheduler.worker_completion_event.wait(2))
            self.assertEqual(admission.filter((delivery, implementation)), (delivery, implementation))
            self.assertTrue(any(kind == "gate_next_waiter_woken" for kind, _ in events))
        finally:
            admission.close()

    def test_same_run_handle_resumes_but_unfinished_operation_fails_closed(self):
        self.acquire()
        restarted = IntegrationWindow(self.controller)
        restarted.bind_run("real-test-run")
        self.assertEqual(restarted.identity, self.window.identity)
        self.assertIsNone(restarted.checkpoint(self.controller.observe()))
        self.assertTrue(restarted.held)
        restarted.before_action("run_authoritative_unity_test")
        again = IntegrationWindow(self.controller)
        again.bind_run("real-test-run")
        with self.assertRaises(IntegrationGateError):
            again.checkpoint(self.controller.observe())


class AutomatedWindowTests(unittest.TestCase):
    def test_automated_reintegration_retains_gate_and_uses_exact_new_event(self):
        with tempfile.TemporaryDirectory(prefix="nsc-window-auto-") as temporary:
            root = Path(temporary)
            fixture, service, _, _ = automated.fixture(root / "task")
            controller = object.__new__(ResumableDownstreamTaskController)
            controller.__dict__.update(fixture.__dict__)
            controller.workflow = SimpleNamespace(
                issue_workflow=service, worker_id=automated.WORKER,
                base_observer=SimpleNamespace(root=fixture.checkout),
                publish_human_handoff=lambda **values: service.publish_human_handoff(
                    task_id=automated.TASK_ID, checkout_path=str(fixture.checkout), **values))
            controller.state_root = root / ".task-review-agent"
            controller.explicit_output_root = root / "delivery-output"
            controller.unity_executable = None
            controller.last_observation = None
            main_head = automated.git(controller.checkout, "rev-parse", "origin/main")
            service.acquire_agent_lease(task=automated.selected_task(), source_head=main_head,
                                        branch=automated.BRANCH, checkout_path=str(controller.checkout),
                                        planned_approach="Deliver exact synthetic result", expected_validation="Exact automated checks")
            controller._latest_validation_authority = lambda: _authoritative_automated_validation(controller)
            def observe():
                state = service.find(automated.TASK_ID).state.to_dict()
                return {"task": automated.selected_task(), "environment": {"source_head": main_head, "ready": True},
                        "coordination": {"workflow_state": state},
                        "checkout": {"status": "ready", "head_commit": automated.git(controller.checkout, "rev-parse", "HEAD"),
                                     "branch": automated.BRANCH, "clean": True}}
            controller.observe = observe
            from Pipeline.TaskReviewAgent.downstream_resilience import _release_active_lease
            _release_active_lease(controller, reason="fixture_ready_for_gate", details={"action": "fixture_setup"})
            # Advance main with a non-conflicting committed file using a separate clone.
            main = root / "main"
            automated.git(root, "clone", "--branch", "main", str(root / "origin.git"), str(main))
            automated.git(main, "config", "user.name", "Test")
            automated.git(main, "config", "user.email", "test@example.invalid")
            (main / "Pipeline" / "main-change.txt").write_text("change")
            automated.git(main, "add", "--", "Pipeline/main-change.txt")
            automated.git(main, "commit", "-m", "main advancement")
            automated.git(main, "push", "origin", "main")
            # Select the real automated validation event, never a human PASS.
            snapshot = service.find(automated.TASK_ID)
            from Pipeline.TaskReviewAgent.issue_workflow import WorkflowEventType
            old_evidence = copy.deepcopy(next(e.details for e in snapshot.events if e.event_type is WorkflowEventType.AUTOMATED_VALIDATION_PASSED))
            seen = []
            def validator(state):
                self.assertEqual(window.gate.read()[1]["owner"]["task_id"], automated.TASK_ID)
                self.assertIsNone(service.find(automated.TASK_ID).state.human_result)
                evidence = copy.deepcopy(old_evidence)
                # The deterministic Unity stand-in emits a NEW result bound to
                # the exact integrated tree; committed policy and Issue hashes
                # are still verified by the production transition.
                evidence.pop("evidence_sha256", None)
                evidence["handoff_event_id"] = state["last_event_id"]
                evidence["commit"] = state["head_commit"]
                evidence["tree"] = automated.git(controller.checkout, "rev-parse", "HEAD^{tree}")
                from Pipeline.TaskReviewAgent.tests.synthetic_gauntlet_approver_smoke_test import _write_unity_manifest, _runner_identity
                manifest = _write_unity_manifest(
                    root / "validated-integration", commit=evidence["commit"], tree=evidence["tree"],
                    test_filter=automated.FILTER, schema_version="1.1",
                    runner=_runner_identity(controller.checkout / "Pipeline/Testing/run_unity_tests_clean.ps1",
                                            commit=evidence["commit"], tree=evidence["tree"]))
                manifest_data = json.loads(manifest.read_text())
                for result in evidence["unity_validations"]:
                    result.update(commit=evidence["commit"], tree=evidence["tree"],
                                  post_commit=evidence["commit"], post_tree=evidence["tree"],
                                  manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                                  xml_sha256=manifest_data["artifacts"]["xml"]["sha256"],
                                  log_sha256=manifest_data["artifacts"]["log"]["sha256"])
                service.apply_automated_validation(task_id=automated.TASK_ID, evidence=evidence, actor_id=automated.WORKER)
                window.import_automated_manifest({"manifest_path": str(manifest)})
                seen.append(evidence["commit"])
            window = IntegrationWindow(controller, automated_validator=validator)
            window.bind_run("automated-window")
            window.checkpoint(observe())
            service.acquire_agent_lease(task=automated.selected_task(), source_head=main_head,
                                        branch=automated.BRANCH, checkout_path=str(controller.checkout),
                                        planned_approach="Gated exact synthetic delivery", expected_validation="Exact automated checks")
            window.before_action("integrate_current_main")
            result = _integrate_current_main(controller)
            window.after_action("integrate_current_main")
            self.assertEqual(result["status"], "human_revalidation_required")
            self.assertEqual(window.checkpoint(observe())["status"], "continue")
            self.assertTrue(window.held)
            self.assertEqual(seen, [automated.git(controller.checkout, "rev-parse", "HEAD")])
            self.assertIsNone(service.find(automated.TASK_ID).state.human_result)
            self.assertEqual(len(controller.state["validation_manifests"]), 1)
            self.assertEqual(controller.state["validation_manifests"][0]["commit"], seen[0])
            # Bounded CI holds the same gate and an exact settlement releases it.
            window.before_action("inspect_or_merge_pull_request")
            self.assertEqual(window.gate.read()[1]["owner"]["operation"]["kind"], "ci")
            window.after_action("inspect_or_merge_pull_request")
            window.settle(observe(), "checks_pending")
            self.assertIsNone(window.gate.read()[1]["owner"])


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    run_with_synthetic_authority(unittest.main, verbosity=2)
