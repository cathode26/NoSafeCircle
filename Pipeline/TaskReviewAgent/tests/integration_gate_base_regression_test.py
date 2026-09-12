#!/usr/bin/env python3
"""Run identical behavioral assertions against candidate or exact base Python code.

NSC_GATE_TEST_SOURCE selects the application checkout. The candidate gate
primitive only seeds remote journal fixtures when testing the base; no base
controller method or host loop is patched. Assertions inspect actual Git/Issue
behavior. A control proves authorized integration still works in both versions.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

CANDIDATE = Path(__file__).resolve().parents[3]
APPLICATION = Path(os.environ.get("NSC_GATE_TEST_SOURCE", str(CANDIDATE))).resolve()
sys.path.insert(0, str(APPLICATION))
from Pipeline.TaskReviewAgent.tests import mainline_reintegration_smoke_test as fixture
from Pipeline.TaskReviewAgent.downstream_runtime import ResumableDownstreamTaskController
from Pipeline.TaskReviewAgent.downstream_resilience import _release_active_lease
from Pipeline.TaskReviewAgent.contracts import TaskReviewRequest, TaskReviewContractError
from Pipeline.TaskReviewAgent.codex_supervisor import SupervisorDecision
from Pipeline.TaskReviewAgent.openai_downstream import run_openai_downstream_pipeline
from Pipeline.TaskReviewAgent.progress import NullProgress

# The remote gate is input data to the tested application. Loading its writer
# here does not install the candidate host-loop/controller changes in the base.
spec = importlib.util.spec_from_file_location("Pipeline.TaskReviewAgent.integration_gate",
                                             CANDIDATE / "Pipeline/TaskReviewAgent/integration_gate.py")
gate_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate_module
spec.loader.exec_module(gate_module)
GitIntegrationGate, owner_identity = gate_module.GitIntegrationGate, gate_module.owner_identity


class FixtureDecisions:
    def __init__(self, controller):
        self.controller, self.calls = controller, 0

    def decide(self, **kwargs):
        self.calls += 1
        from Pipeline.TaskReviewAgent.downstream_determinism import _ALLOWED_ACTION_CONTEXT
        allowed = _ALLOWED_ACTION_CONTEXT.get()
        _ALLOWED_ACTION_CONTEXT.set(None)
        if not allowed or len(allowed) != 1:
            raise AssertionError("fixture expected a deterministic host action")
        action = allowed[0]
        arguments = {"planned_approach": "Resume exact delivery", "expected_validation": "Exact commit tests"} if action == "acquire_agent_lease" else {}
        if action not in {"acquire_agent_lease", "integrate_current_main"}:
            raise AssertionError(f"unexpected external action {action}")
        return SupervisorDecision(task_id=self.controller.task_id, action=action, arguments=arguments, rationale="Deterministic fixture")


class ReadyWorkflow(fixture.FakeWorkflow):
    def observe_goal_state(self):
        value = super().observe_goal_state()
        value["environment"].update(ready=True, errors=[], controller_clean=True, taskgraph_valid=True)
        return value


class BaseRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nsc-base-gate-")
        self.root = Path(self.temporary.name)
        checkout, base, task, main = fixture.create_fixture(self.root, sensitive=False)
        self.service, _ = fixture.prepare_service(checkout, base, task, main)
        workflow = ReadyWorkflow(service=self.service, checkout=checkout, main_head=main, worker_id="worker-a")
        self.service.backend.add_comment(self.service.find(fixture.TASK_ID).issue_number,
                                        f"## Human validation result\n\nResult: PASS\nTested commit: `{task}`\n")
        workflow.base_observer = SimpleNamespace(root=checkout)
        workflow.checkout_manager = SimpleNamespace(checkout_path=checkout)
        workflow.task_id = fixture.TASK_ID
        self.controller = ResumableDownstreamTaskController(workflow=workflow)
        self.head = task
        self.gate = GitIntegrationGate(checkout)
        self.window = getattr(self.controller, "integration_window", None)
        if self.window:
            self.window.bind_run("regression-run")

    def tearDown(self):
        self.temporary.cleanup()

    def seed_owner(self, *, worker="other-worker", run="other-run", task="NSC-001", operation=None, quarantine=False):
        identity = owner_identity(task, run, worker)
        self.gate.enqueue(task, ready_at="2026-09-01T00:00:00Z", ready_event="1" * 64)
        self.gate.acquire(identity)
        if operation:
            self.gate.progress(identity, operation, operation=operation)
        if quarantine:
            self.gate.quarantine(identity, "crashed worker; no reconciliation receipt")
        return identity

    def assert_no_entry(self):
        rejected = False
        try:
            if self.window:
                self.window.checkpoint(self.controller.observe())
            # Exercise the real public mutation API. Old code enters its real
            # merge/handoff path; new code refuses without a gate operation.
            self.controller.integrate_current_main()
        except TaskReviewContractError:
            rejected = True
        self.assertTrue(rejected, "a controller entered integration without exact gate ownership")
        self.assertEqual(fixture.git(self.controller.checkout, "rev-parse", "HEAD"), self.head)

    def test_second_controller_cannot_enter(self):
        self.seed_owner()
        self.assert_no_entry()

    def test_mismatched_run_cannot_enter(self):
        self.seed_owner(task=fixture.TASK_ID, worker="worker-a", run="foreign-run")
        self.assert_no_entry()

    def test_mismatched_worker_cannot_enter(self):
        self.seed_owner(task=fixture.TASK_ID, run="regression-run")
        self.assert_no_entry()

    def test_stale_lease_identity_cannot_enter(self):
        self.seed_owner(task=fixture.TASK_ID, worker="worker-a", run="regression-run")
        self.assert_no_entry()

    def test_active_unity_not_reaped_by_age(self):
        self.seed_owner(operation="unity")
        self.gate.clock = lambda: "2099-09-06T00:00:00Z"
        self.assert_no_entry()

    def test_active_ci_not_reaped_by_age(self):
        self.seed_owner(operation="ci")
        self.gate.clock = lambda: "2099-09-06T00:00:00Z"
        self.assert_no_entry()

    def test_abandoned_owner_without_recovery_receipt_blocks_successor(self):
        self.seed_owner(operation="merge", quarantine=True)
        self.assert_no_entry()

    def test_legacy_active_run_requires_reconciliation(self):
        self.assert_no_entry()

    def test_waiting_host_loop_never_calls_provider(self):
        _release_active_lease(self.controller, reason="fixture_ready", details={"action": "fixture"})
        self.seed_owner()
        provider = FixtureDecisions(self.controller)
        progress = NullProgress()
        progress.run_id = "regression-run"
        result = run_openai_downstream_pipeline(TaskReviewRequest(fixture.TASK_ID), self.controller,
                                              decision_provider=provider, progress=progress, max_turns=8)
        self.assertEqual(result["status"], "integration_gate_waiting")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(fixture.git(self.controller.checkout, "rev-parse", "HEAD"), self.head)

    def test_equal_ready_time_uses_task_id_before_entering(self):
        _release_active_lease(self.controller, reason="fixture_ready", details={"action": "fixture"})
        state = self.service.find(fixture.TASK_ID).state
        self.gate.enqueue("NSC-001", ready_at=state.updated_at_utc, ready_event="1" * 64)
        provider = FixtureDecisions(self.controller)
        progress = NullProgress()
        progress.run_id = "regression-run"
        result = run_openai_downstream_pipeline(TaskReviewRequest(fixture.TASK_ID), self.controller,
                                              decision_provider=provider, progress=progress, max_turns=8)
        self.assertEqual(result["status"], "integration_gate_waiting")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(fixture.git(self.controller.checkout, "rev-parse", "HEAD"), self.head)

    def test_human_handoff_releases_and_wakes_next_waiter(self):
        import threading
        identity = self.window.identity if self.window else owner_identity(fixture.TASK_ID, "regression-run", "worker-a")
        self.gate.enqueue(fixture.TASK_ID, ready_at="2026-09-01T00:00:00Z", ready_event="1" * 64)
        self.gate.acquire(identity)
        event = threading.Event()
        listener = gate_module.GateWakeListener(event, self.gate.domain)
        try:
            self.gate.enqueue("NSC-778", ready_at="2026-09-02T00:00:00Z", ready_event="2" * 64, endpoint=listener.endpoint)
            if self.window:
                self.window.checkpoint(self.controller.observe())
                self.window.before_action("integrate_current_main")
            result = self.controller.integrate_current_main()
            if self.window:
                self.window.after_action("integrate_current_main")
                self.window.checkpoint(self.controller.observe())
            self.assertEqual(result["status"], "human_revalidation_required")
            self.assertTrue(event.wait(2), "human handoff failed to release and poke the next waiter")
            self.assertIsNone(self.gate.read()[1]["owner"])
        finally:
            listener.close()

    def test_control_authorized_integration_preserves_existing_handoff(self):
        if self.window:
            _release_active_lease(self.controller, reason="fixture_ready", details={"action": "fixture"})
            self.window.checkpoint(self.controller.observe())
            self.controller.workflow.acquire_agent_lease(planned_approach="Exact integration", expected_validation="Exact tests")
            self.window.before_action("integrate_current_main")
        result = self.controller.integrate_current_main()
        if self.window:
            self.window.after_action("integrate_current_main")
            self.window.checkpoint(self.controller.observe())
        self.assertEqual(result["status"], "human_revalidation_required")
        self.assertNotEqual(fixture.git(self.controller.checkout, "rev-parse", "HEAD"), self.head)
        self.assertIsNone(self.service.find(fixture.TASK_ID).state.human_result)

    def seed_this_owner(self):
        identity = self.window.identity if self.window else owner_identity(fixture.TASK_ID, "regression-run", "worker-a")
        self.gate.enqueue(fixture.TASK_ID, ready_at="2026-09-01T00:00:00Z", ready_event="1" * 64)
        self.gate.acquire(identity)
        return identity

    def run_with_provider(self, provider):
        progress = NullProgress()
        progress.run_id = "regression-run"
        return run_openai_downstream_pipeline(TaskReviewRequest(fixture.TASK_ID), self.controller,
                                              decision_provider=provider, progress=progress, max_turns=8)

    def test_provider_failure_relinquishes_verified_issue_and_gate(self):
        self.seed_this_owner()
        class FailedProvider:
            def decide(self, **kwargs):
                raise RuntimeError("fixture provider failure between operations")
        with self.assertRaisesRegex(RuntimeError, "fixture provider failure"):
            self.run_with_provider(FailedProvider())
        self.assertIsNone(self.gate.read()[1]["owner"], "ordinary provider failure leaked the integration window")
        self.assertEqual(self.service.find(fixture.TASK_ID).state.state.value, "agent_ready")

    def test_controller_interruption_persists_quarantine(self):
        self.seed_this_owner()
        class InterruptedProvider:
            def decide(self, **kwargs):
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_with_provider(InterruptedProvider())
        self.assertEqual(self.gate.read()[1]["owner"]["status"], "quarantined")

    def complete_issue(self):
        from Pipeline.TaskReviewAgent.downstream_issue import DownstreamIssueCoordinator
        coordinator = DownstreamIssueCoordinator(self.service)
        state = self.service.find(fixture.TASK_ID).state
        coordinator.accept_unchanged_delivery_after_human_pass(
            task_id=fixture.TASK_ID, branch=state.branch, head_commit=state.head_commit,
            checkout_path=str(self.controller.checkout), draft_path="fixture-draft.json", draft_sha256="d" * 64,
            proposal_path="fixture-proposal.json", proposal_sha256="e" * 64)
        self.controller.workflow.acquire_agent_lease(planned_approach="Exact closeout", expected_validation="Verified main")
        merged = fixture.git(self.controller.checkout, "rev-parse", "origin/main")
        coordinator.complete(task_id=fixture.TASK_ID, pull_request_url="https://example.invalid/pull/1",
                             pull_request_number=1, merged_commit=merged, conformant_record_id="fixture-conformant")
        return merged

    def test_verified_closeout_releases_gate(self):
        self.seed_this_owner()
        self.controller.state["merged_commit"] = self.complete_issue()
        self.run_with_provider(FixtureDecisions(self.controller))
        self.assertIsNone(self.gate.read()[1]["owner"], "verified closeout did not release the integration window")

    def test_mismatched_closeout_artifact_is_not_success(self):
        self.seed_this_owner()
        self.complete_issue()
        self.controller.state["merged_commit"] = "f" * 40
        rejected = False
        try:
            self.run_with_provider(FixtureDecisions(self.controller))
        except TaskReviewContractError:
            rejected = True
        self.assertTrue(rejected, "mismatched local closeout artifact was treated as gate success")
        self.assertIsNotNone(self.gate.read()[1]["owner"])

    def test_automated_reintegration_enters_bounded_validator_without_releasing(self):
        from Pipeline.TaskReviewAgent.tests import automated_validation_downstream_smoke_test as automated
        root = self.root / "automated"
        root.mkdir()
        original, service, _, _ = automated.fixture(root / automated.TASK_ID)
        main_head = automated.git(original.checkout, "rev-parse", "origin/main")
        class Workflow:
            worker_id = automated.WORKER
            task_id = automated.TASK_ID
            base_observer = SimpleNamespace(root=original.checkout)
            checkout_manager = SimpleNamespace(checkout_path=original.checkout)
            issue_workflow = service
            def observe_goal_state(self):
                state = service.find(automated.TASK_ID).state.to_dict()
                return {"schema_version": "1.0", "task": automated.selected_task(),
                        "environment": {"source_head": main_head, "ready": True, "errors": [],
                                        "controller_clean": True, "taskgraph_valid": True},
                        "coordination": {"workflow_state": state},
                        "checkout": {"status": "ready", "clean": True, "branch": automated.BRANCH,
                                     "head_commit": automated.git(original.checkout, "rev-parse", "HEAD")}}
            def acquire_agent_lease(self, **values):
                return service.acquire_agent_lease(task=automated.selected_task(), source_head=main_head,
                    branch=automated.BRANCH, checkout_path=str(original.checkout), **values)
            def publish_human_handoff(self, **values):
                return service.publish_human_handoff(task_id=automated.TASK_ID,
                    checkout_path=str(original.checkout), **values)
        controller = ResumableDownstreamTaskController(workflow=Workflow(), command_runner=original.command_runner)
        main = root / "main"
        automated.git(root, "clone", "--branch", "main", str(root / "origin.git"), str(main))
        automated.git(main, "config", "user.name", "Test")
        automated.git(main, "config", "user.email", "test@example.invalid")
        (main / "Pipeline" / "main-change.txt").write_text("nonconflicting main advancement")
        automated.git(main, "add", "--", "Pipeline/main-change.txt")
        automated.git(main, "commit", "-m", "main advancement")
        automated.git(main, "push", "origin", "main")
        main_head = automated.git(main, "rev-parse", "HEAD")
        automated.git(original.checkout, "fetch", "origin")
        gate = GitIntegrationGate(original.checkout)
        window = getattr(controller, "integration_window", None)
        if window:
            window.bind_run("automated-regression")
        identity = window.identity if window else owner_identity(automated.TASK_ID, "automated-regression", automated.WORKER)
        gate.enqueue(automated.TASK_ID, ready_at="2026-09-01T00:00:00Z", ready_event="a" * 64)
        gate.acquire(identity)
        seen = []
        def bounded_validator(state):
            self.assertEqual(gate.read()[1]["owner"]["lease_id"], identity["lease_id"])
            self.assertEqual(state["head_commit"], automated.git(original.checkout, "rev-parse", "HEAD"))
            self.assertIsNone(state["human_result"])
            seen.append(state["head_commit"])
            # Stop at the external Unity boundary; the candidate runtime suite
            # separately validates and imports real hash-bound stand-in output.
            raise RuntimeError("bounded validator reached")
        if window:
            window.automated_validator = bounded_validator
        progress = NullProgress()
        progress.run_id = "automated-regression"
        try:
            run_openai_downstream_pipeline(TaskReviewRequest(automated.TASK_ID), controller,
                decision_provider=FixtureDecisions(controller), progress=progress, max_turns=8)
        except RuntimeError as exc:
            self.assertEqual(str(exc), "bounded validator reached")
        self.assertEqual(len(seen), 1, "automated reintegration ended as a human wait before bounded validation")

    def test_gated_source_revalidation_emits_new_exact_machine_evidence(self):
        import hashlib
        import inspect
        import json
        from unittest.mock import patch
        from Pipeline.TaskReviewAgent.tests.synthetic_source_validation_test import SourceEvidence
        from Pipeline.TaskReviewAgent.tests.production_end_to_end_smoke_test import FAKE_SSH_TEMPLATE
        from Pipeline.TaskReviewAgent import prepare_synthetic_gauntlet as generator
        from Pipeline.TaskReviewAgent import synthetic_gauntlet_approver as approver
        from Pipeline.TaskReviewAgent.issue_workflow_store import IssueWorkflowService, MemoryIssueBackend
        source_case = SourceEvidence()
        source_case.setUp()
        self.addCleanup(source_case.doCleanups)
        source = source_case.source
        task = dict(source_case.task, task_contract_sha256=hashlib.sha256(generator._json_bytes(source_case.task)).hexdigest())
        runner = source / "Pipeline/Testing/synthetic_source_validation.py"
        runner.parent.mkdir(parents=True)
        runner.write_bytes((APPLICATION / "Pipeline/Testing/synthetic_source_validation.py").read_bytes())
        policy = source / generator.POLICY_RELATIVE
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(json.dumps({"schema_version": "1.0", "tasks": {task["id"]: {
            "task_contract_sha256": task["task_contract_sha256"], "required_test_platforms": ["SyntheticSource"],
            "authority": "committed_private_synthetic_gauntlet_validation_policy",
            "test_filters": {"SyntheticSource": generator._test_filter(2001)}}}}))
        source_case.git("add", "--", "Pipeline/Testing/synthetic_source_validation.py", generator.POLICY_RELATIVE)
        source_case.git("commit", "-m", "fixture: trusted runner and policy")
        remote = source_case.root / "origin.git"
        fixture.git(source_case.root, "clone", "--bare", str(source), str(remote))
        checkout_root = source_case.root / "checkouts"
        checkout_root.mkdir()
        checkout = checkout_root / task["id"]
        fixture.git(source_case.root, "clone", str(remote), str(checkout))
        ssh = source_case.root / "fake_ssh.py"
        ssh.write_text(FAKE_SSH_TEMPLATE % {"bare": remote.as_posix(), "repository_path": generator.PRIVATE_REPOSITORY + ".git"})
        for clone in (source, checkout):
            fixture.git(clone, "remote", "set-url", "origin", "git@github.com:" + generator.PRIVATE_REPOSITORY + ".git")
            fixture.git(clone, "config", "core.sshCommand", f'"{Path(sys.executable).as_posix()}" -S -E "{ssh.as_posix()}"')
            fixture.git(clone, "config", "ssh.variant", "simple")
        head = fixture.git(checkout, "rev-parse", "HEAD")
        backend = MemoryIssueBackend()
        backend.repository = generator.PRIVATE_REPOSITORY
        service = IssueWorkflowService(backend=backend, worker_id="source-worker", task_loader=lambda _: task)
        service.acquire_agent_lease(task=task, source_head=head, branch="main", checkout_path=str(checkout),
                                    planned_approach="Source fixture", expected_validation="Exact source checks")
        service.publish_human_handoff(task_id=task["id"], branch="main", head_commit=head, checkout_path=str(checkout),
            implementation_summary="Exact source fixture", completed_checks=["Committed source"],
            human_steps=["Validate exact source"], expected_result="Exact source checks pass")
        with patch.dict(os.environ, {"GIT_ALLOW_PROTOCOL": "file:ssh"}):
            gate = GitIntegrationGate(source)
            identity = owner_identity(task["id"], "source-run", "source-worker")
            gate.enqueue(task["id"], ready_at="2026-09-01T00:00:00Z", ready_event="a" * 64)
            gate.acquire(identity)
            gate.progress(identity, "automated_exact_commit_validation", operation="source")
            arguments = dict(source=source, checkout_root=checkout_root, repository=generator.PRIVATE_REPOSITORY,
                             snapshot=service.find(task["id"]), task=task)
            # Select only the supported input shape; success is established by
            # real runner output and a real hashed Issue transition below.
            if "integration_owner" in inspect.signature(approver._run_unity_validation).parameters:
                arguments["integration_owner"] = identity
            result = approver._run_unity_validation(**arguments)
            self.assertEqual(result["evidence"]["commit"], head)
            self.assertEqual(result["evidence"]["schema_version"], "2.0")
            service.apply_automated_validation(task_id=task["id"], evidence=result["evidence"], actor_id=service.worker_id)
            self.assertIsNone(service.find(task["id"]).state.human_result)
            self.assertEqual(gate.read()[1]["owner"]["lease_id"], identity["lease_id"])


if __name__ == "__main__":
    print(f"APPLICATION_SOURCE={APPLICATION}", flush=True)
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    run_with_synthetic_authority(unittest.main, verbosity=2)
