#!/usr/bin/env python3
"""Pure/component regression-only tests: real scheduler, local Git, hashed Issues.

NSC_GATE_RESUME_SOURCE selects an untouched application base for paired red runs.
The established route below is explicit fixture input, not a replacement scheduler.
No provider, GitHub, Unity, Docker, or live gauntlet is called.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get("NSC_GATE_RESUME_SOURCE", Path(__file__).resolve().parents[3])).resolve()
sys.path.insert(0, str(ROOT))
from Pipeline.TaskReviewAgent.tests import polling_orchestrator_smoke_test as p
from Pipeline.TaskReviewAgent.tests import mainline_reintegration_smoke_test as m
from Pipeline.TaskReviewAgent.contracts import semantic_sha256
from Pipeline.TaskReviewAgent.execution_routing import resolve_execution_route, resolve_task_rigor, restrict_execution_routing_policy
from Pipeline.TaskReviewAgent.integration_window import GateAdmission
from Pipeline.TaskReviewAgent.integration_gate import owner_identity
from Pipeline.TaskReviewAgent.issue_workflow import WorkflowActor, WorkflowEventType, WorkflowPhase, WorkflowState, transition, render_event_comment, update_issue_body, labels_for_state
from Pipeline.TaskReviewAgent.issue_workflow_store import MemoryIssueBackend, IssueWorkflowService

TASK = m.TASK_ID
p.CONTRACTS[TASK] = m.CONTRACT_HASH


class Fixture:
    def __init__(self, root, *, provider="claude", tier="standard", phase="delivery_evidence"):
        old_checkout, self.base, self.task_head, self.head = m.create_fixture(root, sensitive=True)
        self.source = root / "seed"
        self.checkout_root = root / "checkouts"
        self.checkout_root.mkdir()
        self.checkout = self.checkout_root / TASK
        old_checkout.rename(self.checkout)
        self.task = {**p.task(TASK), **m.task(), "depends_on": []}
        self.backend = MemoryIssueBackend()
        self.service = IssueWorkflowService(backend=self.backend, worker_id="worker-a", task_loader=lambda _: self.task)
        self.service.acquire_agent_lease(task=self.task, source_head=self.base, branch=m.BRANCH,
            checkout_path=str(self.checkout), planned_approach="Implement fixture", expected_validation="Exact tests")
        self.service.publish_human_handoff(task_id=TASK, branch=m.BRANCH, head_commit=self.task_head,
            checkout_path=str(self.checkout), implementation_summary="Feature.cs implementation",
            completed_checks=["Fixture component checks"], human_steps=["Check exact commit"], expected_result="Pass")
        self.pass_body = f"## Human validation result\n\nResult: PASS\nTested commit: `{self.task_head}`\n"
        self.backend.add_comment(self.service.find(TASK).issue_number, self.pass_body)
        self.service.apply_human_result(task_id=TASK, result_body=self.pass_body, actor_id="cathode26")
        if phase == "merge_closeout":
            self.service.acquire_agent_lease(task=self.task, source_head=self.head, branch=m.BRANCH,
                checkout_path=str(self.checkout), planned_approach="Closeout", expected_validation="Exact tests")
            self.release(phase=phase)
        self.phase = phase
        self.advisory = p.advisory(TASK, self.head, exact_paths=("Assets/Feature.cs",), shared_systems=(),
            capability_tier=tier, provider_preference="claude" if provider == "claude" else "openai")
        self.architect = p.FakeArchitect({TASK: self.advisory})
        self.processes = p.ProcessFactory()
        self.stream = io.StringIO()
        self.plan_calls = 0
        self.plan_hook = None
        self.scheduler = p.PollingOrchestrator(source=self.source, checkout_root=self.checkout_root,
            scheduler_id="fixture-scheduler", execution_provider=provider, supervisor_provider=provider, provider_allowlist=(provider,),
            model=None, max_turns=120, max_workers=3, architect_min_confidence=.65,
            architect_runner=self.architect, plan_builder=self.plan, task_loader=lambda _: self.task,
            reservation_observer=lambda: (), source_refresher=lambda _: dict(after=self.head, remote_head=self.head),
            process_factory=self.processes, event_emitter=p.JsonEventEmitter(self.stream))
        self.scheduler._current_admission_snapshot = p.FixtureAdmissionSnapshot(source=self.source,
            source_commit=self.head, tasks={TASK: self.task}, policy_document={"schema_version":"1.0", "tasks":{}, "decomposition_child_templates":{}})
        self.admission = GateAdmission(self.scheduler, service=self.service)
        self.scheduler.integration_gate_admission = self.admission
        self.scheduler.set_admission_allowlist([TASK])
        rigor = resolve_task_rigor(self.advisory.execution_recommendation, task=self.task,
            predicted_change_surface=self.advisory.predicted_change_surface,
            committed_path_probe=self.scheduler._admission_snapshot(self.head).committed_path_probe())
        self.route = resolve_execution_route(self.advisory.execution_recommendation,
            restrict_execution_routing_policy(self.scheduler.routing_policy_loader(), (provider,)), rigor=rigor)
        self.receipt = dict(schema_version="1.0", task_id=TASK, task_contract_sha256=m.CONTRACT_HASH,
            source_head=self.base, repository=self.admission.gate.repository_id, checkout_path=str(self.checkout.resolve()),
            issue_number=None, issue_event_id=None, worker_id="worker-a", run_id="fixture-prior-worker",
            recommendation=self.advisory.execution_recommendation.to_dict(), surface=self.advisory.predicted_change_surface.to_dict(),
            route=asdict(self.route), supervisor_provider=self.scheduler.supervisor_provider, provider_allowlist=[provider])
        self.receipt_path = self.checkout_root / ".task-review-agent/admission-routes" / (TASK + ".json")
        self.write_receipt()

    def write_receipt(self):
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        self.receipt_path.write_text(json.dumps({**self.receipt,"receipt_sha256":semantic_sha256(self.receipt)}),encoding="utf-8")

    def release(self, *, phase="delivery_evidence", reason="integration_gate_waiting"):
        snapshot = self.service.find(TASK)
        state, event = transition(snapshot.state, event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
            actor_type=WorkflowActor.AGENT, actor_id="worker-a", to_state=WorkflowState.AGENT_READY,
            to_phase=WorkflowPhase(phase), details={"reason":reason})
        self.backend.add_comment(snapshot.issue_number, render_event_comment(event, "Fixture lease release"))
        self.backend.update_issue(snapshot.issue_number, body=update_issue_body(snapshot.body,state), labels=labels_for_state(state.state,snapshot.labels))

    def plan(self, **kwargs):
        self.plan_calls += 1
        if self.plan_hook:
            self.plan_hook(self.plan_calls)
        if TASK in kwargs.get("excluded_task_ids", ()):
            return p.terminal_plan(self.head,"no_safe_work")
        snapshot=self.service.find(TASK)
        state=snapshot.state
        plan=p.resume_plan(self.head,TASK,phase=self.phase)
        return replace(plan,resume={**plan.resume,"task_contract_sha256":m.CONTRACT_HASH,
            "issue_number":snapshot.issue_number,"issue_url":snapshot.issue_url,"branch":state.branch,"commit":state.head_commit})

    def events(self, kind):
        return [e for line in self.stream.getvalue().splitlines() if (e:=json.loads(line))["event"] == kind]

    def poll(self):
        return self.scheduler.poll_capacity_batch()

    def close(self):
        self.admission.close()


class GateResumeTests(unittest.TestCase):
    def fixture(self, **kwargs):
        temp = tempfile.TemporaryDirectory(prefix="gate-resume-")
        self.addCleanup(temp.cleanup)
        f = Fixture(Path(temp.name), **kwargs)
        self.addCleanup(f.close)
        return f

    def assert_bypass(self, f):
        result=f.poll()
        self.assertEqual(result.status,"worker_launched",f.stream.getvalue())
        self.assertEqual(len(f.architect.calls),0,f.stream.getvalue())
        self.assertEqual(len(f.processes.calls),1)
        (event,)=f.events("integration_gate_resume_admitted")
        self.assertEqual(event["architect_invocations"],0)
        self.assertIsNone(event["advisory_artifact_path"])
        self.assertEqual(event["evidence"]["source_head"],f.head)
        self.assertEqual(event["evidence"]["task_head"],f.task_head)
        self.assertFalse(f.events("architect_started"))
        self.assertFalse(f.events("architect_completed"))
        self.assertEqual(f.events("poll_capacity_batch_completed")[0]["architect_invocations"],0)
        self.assertIsNone(f.scheduler.active_assignments[TASK].advisory_artifact_path)
        args=f.processes.calls[0][0]
        self.assertEqual(args[args.index("--admission-source-head")+1],f.head)
        for flag,value in (("--execution-provider",f.route.execution_provider),("--crew-profile",f.route.rigor.crew_profile),
                           ("--validation-profile",f.route.rigor.validation_profile)):
            self.assertEqual(args[args.index(flag)+1],value)

    def test_delivery_head_zero_architect(self):
        self.assert_bypass(self.fixture())

    def test_merge_closeout_zero_architect(self):
        self.assert_bypass(self.fixture(phase="merge_closeout"))

    def test_claude_and_codex_preserve_every_rigor_tier(self):
        for provider in ("claude","codex"):
            for tier in ("fast","standard","deep"):
                with self.subTest(provider=provider,tier=tier):
                    self.assert_bypass(self.fixture(provider=provider,tier=tier))

    def test_nonhead_launches_when_unowned_but_conflicting_owner_never_launches(self):
        for owned in (False,True):
            with self.subTest(owned=owned):
                f=self.fixture()
                other={**f.task,"id":"NSC-778"}
                f.service._initialize_issue(other,now="2020-01-01T00:00:00Z")
                f.admission.gate.enqueue("NSC-778",ready_at="2020-01-01T00:00:00Z",ready_event="a"*64)
                if owned:
                    f.admission.gate.acquire(owner_identity("NSC-778","other-run","other-worker"))
                self.assertEqual(f.poll().status,"idle" if owned else "worker_launched")
                self.assertEqual(len(f.processes.calls),0 if owned else 1)
                self.assertEqual(len(f.architect.calls),0)

    def test_unowned_out_of_scope_waiter_does_not_strand_authorized_resume(self):
        f = self.fixture()
        other = {**f.task, "id": "NSC-778"}
        f.service._initialize_issue(other, now="2020-01-01T00:00:00Z")
        f.admission.gate.enqueue(
            "NSC-778",
            ready_at="2020-01-01T00:00:00Z",
            ready_event="a" * 64,
        )

        self.assert_bypass(f)

        _, state = f.admission.gate.read()
        self.assertIsNone(state["owner"])
        self.assertEqual(
            [waiter["task_id"] for waiter in state["queue"]],
            ["NSC-778", TASK],
        )

    def test_stale_wake_does_not_override_current_owner(self):
        f=self.fixture()
        f.scheduler.worker_completion_event.set()
        f.admission.gate.enqueue(TASK,ready_at="2020-01-01T00:00:00Z",ready_event="a"*64)
        f.admission.gate.acquire(owner_identity(TASK,"old-run","old-worker"))
        self.assertEqual(f.poll().status,"idle")
        self.assertFalse(f.processes.calls)

    def test_missing_corrupt_or_changed_route_uses_architect(self):
        for field in ("missing","corrupt","task_contract_sha256","repository","checkout_path","source_head","worker_id","issue_number","provider_allowlist"):
            with self.subTest(field=field):
                f=self.fixture()
                if field == "missing": f.receipt_path.unlink()
                elif field == "corrupt": f.receipt_path.write_text("{}",encoding="utf-8")
                else:
                    f.receipt[field]=[] if field=="provider_allowlist" else 123 if field=="issue_number" else "changed"
                    f.write_receipt()
                f.poll()
                self.assertEqual(len(f.architect.calls),1,f.stream.getvalue())
                self.assertFalse(f.events("integration_gate_resume_admitted"))

    def test_new_feedback_uses_architect(self):
        f=self.fixture()
        f.backend.add_comment(f.service.find(TASK).issue_number,"Please repair the Feature.cs behavior before continuing.")
        f.poll()
        self.assertEqual(len(f.architect.calls),1)

    def test_health_capacity_and_corrupt_downstream_require_judgment(self):
        for condition in ("health", "thousand", "downstream"):
            with self.subTest(condition=condition):
                f=self.fixture()
                if condition == "health":
                    f.scheduler.capacity_health_failures.append((f.scheduler.monotonic_clock(), "fixture health failure"))
                elif condition == "thousand":
                    f.task["provenance"]={"profile":"thousand"}
                    f.scheduler._current_admission_snapshot._tasks[TASK]=dict(f.task)
                else:
                    path=f.checkout_root/".task-review-agent"/(TASK+".downstream.json")
                    path.write_text('{"schema_version":"1.0","task_id":"NSC-777","receipt_sha256":"corrupt"}',encoding="utf-8")
                f.poll()
                self.assertEqual(len(f.architect.calls),1,f.stream.getvalue())
                self.assertFalse(f.events("integration_gate_resume_admitted"))

    def test_failure_release_uses_architect(self):
        f=self.fixture()
        f.service.acquire_agent_lease(task=f.task,source_head=f.head,branch=m.BRANCH,checkout_path=str(f.checkout),
            planned_approach="Resume",expected_validation="Test")
        f.release(reason="provider_failed")
        f.poll()
        self.assertEqual(len(f.architect.calls),1)

    def test_fresh_and_repair_work_still_use_architect(self):
        for fresh in (False,True):
            with self.subTest(fresh=fresh):
                f=self.fixture()
                f.phase="repair"
                if fresh: f.scheduler.plan_builder=lambda **_:p.candidate_plan(f.head,TASK)
                f.poll()
                self.assertEqual(len(f.architect.calls),1)

    def test_prelaunch_source_movement_withdraws_without_provider(self):
        f=self.fixture()
        count=0
        def refresh(_):
            nonlocal count
            count+=1
            return dict(after=f.head if count==1 else "f"*40, remote_head=f.head)
        f.scheduler.source_refresher=refresh
        self.assertEqual(f.poll().status,"batch_revalidation_failed")
        self.assertEqual(len(f.architect.calls),0)
        self.assertFalse(f.processes.calls)

    def test_gate_owner_changes_before_launch_withdraws(self):
        f=self.fixture()
        def race(count):
            if count==2: f.admission.gate.acquire(owner_identity(TASK,"racing-run","racing-worker"))
        f.plan_hook=race
        self.assertEqual(f.poll().status,"idle")
        self.assertEqual(len(f.architect.calls),0)
        self.assertFalse(f.processes.calls)

    def test_capacity_and_scope_exclusion_remain(self):
        for capacity in (False,True):
            with self.subTest(capacity=capacity):
                f=self.fixture()
                if capacity:
                    f.scheduler.max_workers=1
                    p.add_active(f.scheduler,task_id=p.TASK_A,process=p.FakeProcess())
                else: f.scheduler.set_admission_allowlist([p.TASK_A])
                f.poll()
                self.assertFalse(f.architect.calls)
                self.assertFalse(f.processes.calls)

    def test_decomposition_still_uses_architect(self):
        f=self.fixture()
        f.task.update(execution_scope="needs_execution_decomposition", decomposition_state="atomicity_unknown",parent="NSC-001")
        f.phase="decomposition"
        f.advisory=p.advisory(TASK,f.head,work_type="decomposition")
        f.architect.values[TASK]=f.advisory
        f.poll()
        self.assertEqual(len(f.architect.calls),1,f.stream.getvalue())

    def test_reservation_cooldown_and_pending_transition_still_exclude(self):
        for mode in ("resource","paths","unknown","confirmable","cooldown","pending"):
            with self.subTest(mode=mode):
                f=self.fixture()
                if mode=="cooldown":
                    key=f.scheduler._cooldown_key(task_id=TASK,task_contract_sha256=m.CONTRACT_HASH,source_head=f.head)
                    f.scheduler.architect_cooldowns[key]=p.scheduler_module.ArchitectCooldownEntry(
                        not_before=f.scheduler.monotonic_clock()+100,decision=p.scheduler_module.ArchitectPolicyDecision("wait",("Prior judgment remains active",)))
                else:
                    reservation=p.IntegrationReservation(task_id=TASK if mode=="pending" else "NSC-778",
                        workflow_state="human_action_required",phase="unity_runtime_validation",branch=None,head=f.head,checkout_path=None,
                        exclusive_resources=tuple(f.task["exclusive_resources"]) if mode=="resource" else ("repo-file:Assets/Other.cs",) if mode=="confirmable" else (),
                        predicted_paths=(),actual_paths=("Assets/Feature.cs",) if mode=="paths" else (),
                        unity_serialized_assets=(),shared_systems=(),confidence=1.0,evidence_type="fixture_observation",
                        surface_unknown=mode in {"unknown","confirmable"},local_active=False,
                        pending_transition={"status":"pending"} if mode=="pending" else None)
                    f.scheduler.reservation_observer=lambda:(reservation,)
                f.poll()
                self.assertFalse(f.processes.calls,f.stream.getvalue())
                self.assertEqual(len(f.architect.calls),1 if mode in {"paths","confirmable"} else 0,f.stream.getvalue())

    def test_changed_source_issue_checkout_and_surface_keep_architect(self):
        for mode in ("source","issue","checkout","surface","policy"):
            with self.subTest(mode=mode):
                f=self.fixture()
                if mode=="source": f.scheduler.source_refresher=lambda _:dict(after=f.head,remote_head="f"*40)
                elif mode=="issue":
                    original=f.scheduler.plan_builder
                    f.scheduler.plan_builder=lambda **kwargs:replace(original(**kwargs),resume={**original(**kwargs).resume,"issue_number":999})
                elif mode=="checkout": (f.checkout/"untracked.txt").write_text("changed")
                elif mode=="surface":
                    f.receipt["surface"]["exact_paths"]=["Assets/Unrelated.cs"]
                    f.write_receipt()
                else:
                    policy=f.scheduler.routing_policy_loader()
                    f.scheduler.routing_policy_loader=lambda:replace(policy,standard=replace(policy.standard,claude_model="changed-model"))
                f.poll()
                self.assertEqual(len(f.architect.calls),1,f.stream.getvalue())
                self.assertFalse(f.events("integration_gate_resume_admitted"))

    def test_dependency_proof_requires_current_conformant_state(self):
        for state in ("conformant","needs_testing"):
            with self.subTest(state=state):
                f=self.fixture()
                f.task["depends_on"]=["NSC-778"]
                f.scheduler._current_admission_snapshot._tasks[TASK]=dict(f.task)
                with patch.object(p.scheduler_module.dispatch_plan_module,"_taskcontrol_states_snapshot",
                    return_value={"NSC-778":{"state":state}}):
                    if state=="conformant": self.assert_bypass(f)
                    else:
                        f.poll()
                        self.assertEqual(len(f.architect.calls),1,f.stream.getvalue())

    def test_current_main_is_integrated_before_new_validation(self):
        f=self.fixture()
        self.assert_bypass(f)
        from Pipeline.TaskReviewAgent.tests.integration_window_smoke_test import ReadyWorkflow
        from Pipeline.TaskReviewAgent.downstream_runtime import ResumableDownstreamTaskController
        workflow=ReadyWorkflow(service=f.service,checkout=f.checkout,main_head=f.head,worker_id="worker-a")
        workflow.base_observer=SimpleNamespace(root=f.source)
        workflow.checkout_manager=SimpleNamespace(checkout_path=f.checkout)
        workflow.task_id=TASK
        controller=ResumableDownstreamTaskController(workflow=workflow)
        argv=f.processes.calls[0][0]
        window=controller.integration_window
        window.bind_run(argv[argv.index("--run-id")+1])
        self.assertEqual(window.checkpoint(controller.observe())["status"],"continue")
        workflow.acquire_agent_lease(planned_approach="Integrate current main",expected_validation="Validate the new exact commit")
        window.before_action("integrate_current_main")
        result=controller.integrate_current_main()
        window.after_action("integrate_current_main")
        self.assertEqual(result["status"],"human_revalidation_required")
        self.assertEqual(m.git(f.checkout,"merge-base",f.head,"HEAD"),f.head)
        self.assertNotEqual(m.git(f.checkout,"rev-parse","HEAD"),f.task_head)
        self.assertIsNone(f.service.find(TASK).state.human_result)

    def test_automatic_evidence_full_lifecycle_reuses_recorded_route(self):
        from Pipeline.TaskReviewAgent.tests import production_end_to_end_smoke_test as end_to_end
        with end_to_end.disposable_fixture() as fixture, end_to_end.acceptance_environment(fixture):
            # The old fixture uses example.invalid URLs. This case models the
            # exact repository-bound Issue URLs required by deterministic resume.
            for issue in fixture.memory.issues.values():
                issue["url"]=f"https://github.com/{end_to_end.REPOSITORY}/issues/{issue['number']}"
            create_issue=fixture.memory.create_issue
            def create_repository_issue(**values):
                issue=create_issue(**values)
                url=f"https://github.com/{end_to_end.REPOSITORY}/issues/{issue['number']}"
                fixture.memory.issues[issue["number"]]["url"]=url
                return {**issue,"url":url}
            fixture.memory.create_issue=create_repository_issue
            run=end_to_end.build_run(fixture)
            result=run.controller.run()
            self.assertEqual(result.evaluation.classification,"complete")
            self.assertFalse(run.workers.failures)
            end_to_end.assert_completion_receipt(run,result)
            self.assertEqual(result.progress.architect_invocations_total,1,run.events.getvalue())
            admitted=end_to_end.scheduler_events(run,"integration_gate_resume_admitted")
            self.assertEqual(len(admitted),1)
            self.assertEqual(admitted[0]["architect_invocations"],0)
            self.assertEqual(result.progress.worker_launches_total,2)


class GateResumeAuthorityTests(unittest.TestCase):
    """Absent routing history is a fallback; untrustworthy authority is an incident."""

    def fixture(self, **kwargs):
        temp = tempfile.TemporaryDirectory(prefix="gate-resume-authority-")
        self.addCleanup(temp.cleanup)
        f = Fixture(Path(temp.name), **kwargs)
        self.addCleanup(f.close)
        return f

    def test_missing_route_receipt_uses_the_ordinary_architect_path(self):
        from Pipeline.TaskReviewAgent.gate_resume import route_path
        f = self.fixture()
        route_path(f.scheduler, TASK).unlink()
        result = f.poll()
        self.assertEqual(result.status, "worker_launched", f.stream.getvalue())
        self.assertEqual(len(f.architect.calls), 1)
        self.assertTrue(f.events("integration_gate_resume_requires_architect"))
        self.assertFalse(f.events("integration_gate_resume_blocked"))

    def test_corrupt_route_receipt_still_uses_the_architect_path(self):
        """The saved route is history, not authority: doubt means fall back."""

        from Pipeline.TaskReviewAgent.gate_resume import route_path
        f = self.fixture()
        path = route_path(f.scheduler, TASK)
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["source_head"] = "f" * 40
        path.write_text(json.dumps(receipt), encoding="utf-8")
        result = f.poll()
        self.assertEqual(result.status, "worker_launched", f.stream.getvalue())
        self.assertEqual(len(f.architect.calls), 1)
        self.assertTrue(f.events("integration_gate_resume_requires_architect"))
        self.assertFalse(f.events("integration_gate_resume_blocked"))

    def test_unexpected_resume_failure_blocks_instead_of_hiding_behind_architect(self):
        from Pipeline.TaskReviewAgent import gate_resume

        stream = io.StringIO()
        admission = SimpleNamespace(
            scheduler=SimpleNamespace(events=p.JsonEventEmitter(stream)),
            gate=SimpleNamespace(ref="refs/nsc/integration-gates/fixture"),
        )
        entry = (None, "delivery_evidence", {"task": {"id": "NSC-001"}})
        with patch.object(gate_resume, "_prove", side_effect=RuntimeError("fixture boom")):
            with self.assertRaisesRegex(RuntimeError, "fixture boom"):
                gate_resume.prove_resume(
                    admission,
                    (entry,),
                    source_head="a" * 40,
                    refresh={},
                    reservations=(),
                )
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([event["event"] for event in events], ["integration_gate_resume_blocked"])
        self.assertIn("unexpected gate-resume proof failure", events[0]["reason"])

    def test_raw_gate_error_is_normalized_to_authority_block(self):
        from Pipeline.TaskReviewAgent import gate_resume
        from Pipeline.TaskReviewAgent.integration_gate import IntegrationGateError

        stream = io.StringIO()
        admission = SimpleNamespace(
            scheduler=SimpleNamespace(events=p.JsonEventEmitter(stream)),
            gate=SimpleNamespace(ref="refs/nsc/integration-gates/fixture"),
        )
        entry = (None, "delivery_evidence", {"task": {"id": "NSC-001"}})
        with patch.object(
            gate_resume, "_prove", side_effect=IntegrationGateError("fixture journal failure")
        ):
            with self.assertRaisesRegex(gate_resume.GateResumeAuthorityError, "authority failed"):
                gate_resume.prove_resume(
                    admission,
                    (entry,),
                    source_head="a" * 40,
                    refresh={},
                    reservations=(),
                )
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([event["event"] for event in events], ["integration_gate_resume_blocked"])

    def test_unreconciled_publication_blocks_gate_resume(self):
        from Pipeline.TaskReviewAgent.gate_resume import (
            GateResumeAuthorityError, _require_trustworthy_gate)
        f = self.fixture()
        gate = f.admission.gate
        identity = owner_identity("NSC-001", "prior-run", "prior-worker")
        gate.enqueue("NSC-001", ready_at="2026-08-01T00:00:00Z", ready_event="9" * 64)
        self.assertEqual(gate.acquire(identity)["status"], "acquired")
        record = gate.bind_publication(identity, source_head="a" * 40,
                                       validated_commit="a" * 40, expected_main="b" * 40)
        gate.record_publication(identity, operation_id=record["operation_id"],
                                status="uncertain", publication_commit="a" * 40,
                                detail="fixture: transport outcome unknown")
        with self.assertRaisesRegex(GateResumeAuthorityError, "reconcile"):
            _require_trustworthy_gate(f.admission)
        self.assertEqual(len(f.architect.calls), 0)

    def test_legacy_gate_owner_blocks_gate_resume(self):
        from Pipeline.TaskReviewAgent.gate_resume import (
            GateResumeAuthorityError, _require_trustworthy_gate)
        from Pipeline.TaskReviewAgent.integration_gate import LEGACY_OWNER_KEYS
        f = self.fixture()
        gate = f.admission.gate
        identity = owner_identity("NSC-001", "prior-run", "prior-worker")
        gate.enqueue("NSC-001", ready_at="2026-08-01T00:00:00Z", ready_event="9" * 64)
        self.assertEqual(gate.acquire(identity)["status"], "acquired")
        oid, state = gate.read()
        state["owner"] = {k: v for k, v in state["owner"].items() if k in LEGACY_OWNER_KEYS}
        state["revision"] += 1
        state["event"] = dict(kind="gate_legacy_fixture", occurred_at="2026-08-01T00:00:00+00:00",
                              previous_oid=oid)
        root = f.scheduler.source
        tree = m.git(root, "rev-parse", f"{oid}^{{tree}}")
        payload = "nsc-durable-integration-gate\n" + json.dumps(
            state, sort_keys=True, separators=(",", ":")) + "\n"
        forged = subprocess.run(["git", "-C", str(root), "commit-tree", tree, "-p", oid],
                                input=payload.encode(), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True).stdout.decode().strip()
        m.git(root, "push", f"--force-with-lease={gate.ref}:{oid}", "origin", f"{forged}:{gate.ref}")
        with self.assertRaisesRegex(GateResumeAuthorityError, "predates the versioned"):
            _require_trustworthy_gate(f.admission)
        self.assertEqual(len(f.architect.calls), 0)


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    run_with_synthetic_authority(unittest.main, verbosity=2)
